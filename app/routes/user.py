# app/routes/user.py
from flask import Blueprint, jsonify, request
from app.models.user import User
from app.extensions import db
from app.utils.decorators import admin_required
from flask_jwt_extended import jwt_required, get_jwt_identity

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

# --- ✅ โค้ดที่เพิ่มเข้ามาสำหรับจัดการผู้ใช้ ---

@bp.route("/users", methods=["GET"])
@jwt_required()
@admin_required
def get_all_users():
    """Admin-only endpoint to get all users."""
    try:
        users = User.query.order_by(User.id).all()
        return jsonify([user.to_dict_admin() for user in users]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 💡 **เพิ่ม: Endpoint สำหรับสร้าง User ใหม่ (Admin only)**
@bp.route("/users", methods=["POST"])
@jwt_required()
@admin_required
def create_user():
    """Admin-only endpoint to create a new user."""
    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    # Admin สามารถกำหนดสิทธิ์ is_admin ได้
    is_admin = data.get("is_admin", False) 

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409
    
    if email and User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 409

    new_user = User(username=username, email=email, is_admin=is_admin)
    new_user.set_password(password)
    
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify(new_user.to_dict_admin()), 201
# 💡 **เพิ่ม: Endpoint สำหรับอัปเดตรหัสผ่าน (Admin only)**
@bp.route("/users/<int:user_id>/password", methods=["PUT"])
@jwt_required()
@admin_required
def update_user_password(user_id):
    """Admin-only endpoint to update a user's password."""
    data = request.get_json()
    password = data.get('password')

    if not password or len(password) < 4: # เพิ่มเงื่อนไขความยาวรหัสผ่าน
        return jsonify({"error": "Password is required and must be at least 4 characters."}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    user.set_password(password)
    db.session.commit()
    
    return jsonify({"message": f"Password for user {user.username} updated successfully."}), 200



@bp.route("/users/<int:user_id>/status", methods=["PUT"])
@jwt_required()
@admin_required
def update_user_status(user_id):
    """Admin-only endpoint to update a user's active status."""
    data = request.get_json()
    is_active = data.get('is_active')

    if not isinstance(is_active, bool):
        return jsonify({"error": "Invalid 'is_active' value. Must be boolean."}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # ป้องกันไม่ให้ admin ปิดการใช้งานบัญชีของตัวเอง
    current_admin_id = get_jwt_identity()
    if str(user.id) == str(current_admin_id):
        return jsonify({"error": "Admin cannot deactivate their own account."}), 403

    try:
        user.is_active = is_active
        db.session.commit()
        return jsonify(user.to_dict_admin()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500