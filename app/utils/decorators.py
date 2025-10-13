# app/utils/decorators.py
from flask import request, jsonify, redirect, url_for # เพิ่ม redirect, url_for
from functools import wraps
from flask_jwt_extended import verify_jwt_in_request, get_csrf_token, get_jwt, get_jwt_identity # เพิ่ม get_jwt_identity
from app.models.user import User # เพิ่ม User model

def csrf_protect(fn):
    """ตรวจสอบ access token (cookie) และ X-CSRF-TOKEN header."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # ตรวจ JWT ใน cookie (ชัดเจน)
        verify_jwt_in_request(locations=["cookies"])

        # ดึง CSRF token จาก header
        csrf_token = request.headers.get("X-CSRF-TOKEN")
        if not csrf_token:
            return jsonify({"msg": "CSRF token missing"}), 403

        # get_csrf_token() อ่านจาก JWT ที่ verify แล้ว
        if csrf_token != get_csrf_token():
            return jsonify({"msg": "CSRF token invalid"}), 403

        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    """ตรวจสอบ claim is_admin ใน JWT claims (จาก cookie)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request(locations=["cookies"])
        claims = get_jwt()
        if not claims.get("is_admin"):
            return jsonify({"msg": "Forbidden: admin only"}), 403
        return fn(*args, **kwargs)
    return wrapper

# เพิ่ม decorator ใหม่ตรงนี้
def active_user_required(fn):
    """ตรวจสอบว่าผู้ใช้ที่ login อยู่มีสถานะ is_active หรือไม่"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # ดึง user id จาก token
        user_id = get_jwt_identity()
        if user_id:
            user = User.query.get(int(user_id))
            # ตรวจสอบว่ามี user และสถานะเป็น active
            if user and user.is_active:
                return fn(*args, **kwargs)

        # ถ้าไม่มี user หรือไม่ active ให้ redirect ไปหน้า login
        response = redirect(url_for("views.login_page"))
        from flask_jwt_extended import unset_jwt_cookies
        unset_jwt_cookies(response) # ลบ cookie ที่ไม่ถูกต้องออก
        return response
    return wrapper