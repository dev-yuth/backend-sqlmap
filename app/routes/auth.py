from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.user import User
from app.models.token_blacklist import TokenBlocklist
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt, get_jwt_identity

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    if not username or not password:
        return {"msg":"username & password required"}, 400
    if User.query.filter((User.username==username) | (User.email==email)).first():
        return {"msg":"user exists"}, 400
    u = User(username=username, email=email)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return {"ok": True, "user": u.to_dict()}, 201

@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    identifier = data.get("username") or data.get("email")
    password = data.get("password")
    if not identifier or not password:
        return {"msg":"missing credentials"}, 400
    user = User.query.filter((User.username==identifier) | (User.email==identifier)).first()
    if not user or not user.check_password(password):
        return {"msg":"invalid credentials"}, 401
    access = create_access_token(identity=user.id)
    refresh = create_refresh_token(identity=user.id)
    return {"access_token": access, "refresh_token": refresh, "user": user.to_dict()}

@bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    access = create_access_token(identity=identity)
    return {"access_token": access}

@bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    db.session.add(TokenBlocklist(jti=jti, token_type="access"))
    db.session.commit()
    return {"msg":"logged out"}
