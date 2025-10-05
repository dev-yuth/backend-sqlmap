# app/routes/auth.py
from flask import Blueprint, request, jsonify, make_response
from app.extensions import db, jwt
from app.models.user import User
from app.models.token_blacklist import TokenBlocklist
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt,
    get_jwt_identity,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
    get_csrf_token,
)
from app.models.login_log import LoginLog

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

@bp.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception as e:
        print("Error parsing JSON:", e)
        return {"msg": "Invalid JSON"}, 400

    print("REQUEST JSON:", data)

    identifier = data.get("username") or data.get("email")
    password = data.get("password")
    if not identifier or not password:
        return {"msg": "missing credentials"}, 400

    user = User.query.filter(
        (User.username == identifier) | (User.email == identifier)
    ).first()

    ip = request.remote_addr
    ua = request.headers.get("User-Agent", "")

    if not user or not user.check_password(password):
        log = LoginLog(
            user_id=user.id if user else None,
            username=identifier,
            ip_address=ip,
            user_agent=ua,
            success=False,
        )
        db.session.add(log)
        db.session.commit()
        return {"msg": "invalid credentials"}, 401

    # ✅ แก้ไข: แปลง user.id เป็น string
    access = create_access_token(
        identity=str(user.id), 
        additional_claims={"is_admin": user.is_admin}
    )
    refresh = create_refresh_token(
        identity=str(user.id), 
        additional_claims={"is_admin": user.is_admin}
    )

    # log success
    log = LoginLog(
        user_id=user.id,
        username=user.username,
        ip_address=ip,
        user_agent=ua,
        success=True,
    )
    db.session.add(log)
    db.session.commit()

    resp = make_response({
        "msg": "Login success",
        "user": user.to_dict(),
        "access_csrf": get_csrf_token(access),
        "refresh_csrf": get_csrf_token(refresh),
    })

    set_access_cookies(resp, access)
    set_refresh_cookies(resp, refresh)

    return resp

@bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True, locations=["cookies"])
def refresh():
    identity = get_jwt_identity()
    # ✅ แปลง identity กลับเป็น int เมื่อใช้ query
    user = User.query.get(int(identity))
    if not user or not user.is_active:
        return {"msg": "User not found or inactive"}, 404

    access = create_access_token(
        identity=identity,  # identity นี้เป็น string อยู่แล้ว
        additional_claims={"is_admin": user.is_admin}
    )
    resp = make_response({
        "msg": "Token refreshed",
        "access_csrf": get_csrf_token(access)
    })
    set_access_cookies(resp, access)
    return resp

@bp.route("/logout", methods=["POST"])
@jwt_required(verify_type=False, locations=["cookies"])
def logout():
    jti = get_jwt()["jti"]
    token_type = get_jwt()["type"]
    db.session.add(TokenBlocklist(jti=jti, token_type=token_type))
    db.session.commit()

    resp = make_response({"msg": f"{token_type} token revoked"})
    unset_jwt_cookies(resp)
    return resp