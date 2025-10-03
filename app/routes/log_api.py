# app/routes/log_api.py
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.user import User
from app.models.login_log import LoginLog

bp = Blueprint("log_api", __name__, url_prefix="/api/logs")

# ------------------------------
# USER: ดู log ของตัวเอง
# ------------------------------
@bp.route("/me", methods=["GET"])
@jwt_required()
def my_logs():
    user_id = get_jwt_identity()
    logs = (
        LoginLog.query.filter_by(user_id=user_id)
        .order_by(LoginLog.created_at.desc())
        .all()
    )
    return jsonify([l.to_dict() for l in logs])


# ------------------------------
# ADMIN: ดู log ของทุกคน
# ------------------------------
@bp.route("/all", methods=["GET"])
@jwt_required()
def all_logs():
    user_id = get_jwt_identity()
    current_user = User.query.get(user_id)

    if not current_user or not current_user.is_admin:
        return {"msg": "forbidden"}, 403

    logs = LoginLog.query.order_by(LoginLog.created_at.desc()).all()
    return jsonify([l.to_dict() for l in logs])
