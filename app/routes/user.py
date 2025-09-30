# app/routes/user.py
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.user import User

# สร้าง Blueprint สำหรับ user API (prefix: /api/user)
bp = Blueprint("user", __name__, url_prefix="/api/user")

# ------------------------------
# GET /api/user/me
# คืนข้อมูลผู้ใช้ปัจจุบัน (ต้องมี access token)
# ------------------------------
@bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    # ดึง identity (เราบันทึกเป็น user.id ตอนสร้าง token)
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    # ถ้าไม่พบหรือถูกปิดการใช้งาน
    if not user or not user.is_active:
        return {"msg": "User not found or inactive"}, 404

    # คืนข้อมูลผู้ใช้ (method to_dict ใน model)
    return user.to_dict()

# ------------------------------
# GET /api/user/all
# คืนรายชื่อผู้ใช้ทั้งหมด — จำกัดเฉพาะ admin
# ------------------------------
@bp.route("/all", methods=["GET"])
@jwt_required()
def all_users():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    # ตรวจสิทธิ์ admin
    if not user or not user.is_admin:
        return {"msg": "Admin only"}, 403

    users = User.query.all()
    return {"users": [u.to_dict() for u in users]}
