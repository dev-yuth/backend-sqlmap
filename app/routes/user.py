# app/routes/user.py
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.user import User

bp = Blueprint("user", __name__, url_prefix="/api/user")

# ------------------------------
# GET /api/user/me
# คืนข้อมูลผู้ใช้ปัจจุบัน (ต้องมี access token จาก cookies)
# ------------------------------
@bp.route("/me", methods=["GET"])
@jwt_required(locations=["cookies"])  # ✅ เพิ่ม locations=["cookies"]
def me():
    user_id = get_jwt_identity()
    # ✅ แปลง string เป็น int เพราะ identity ถูกเก็บเป็น string
    user = User.query.get(int(user_id))

    if not user or not user.is_active:
        return {"msg": "User not found or inactive"}, 404

    return user.to_dict()

# ------------------------------
# GET /api/user/all
# คืนรายชื่อผู้ใช้ทั้งหมด — จำกัดเฉพาะ admin
# ------------------------------
@bp.route("/all", methods=["GET"])
@jwt_required(locations=["cookies"])  # ✅ เพิ่ม locations=["cookies"]
def all_users():
    user_id = get_jwt_identity()
    # ✅ แปลง string เป็น int
    user = User.query.get(int(user_id))

    if not user or not user.is_admin:
        return {"msg": "Admin only"}, 403

    users = User.query.all()
    return {"users": [u.to_dict() for u in users]}