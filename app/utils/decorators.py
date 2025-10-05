# app/utils/decorators.py
from flask import request, jsonify
from functools import wraps
from flask_jwt_extended import verify_jwt_in_request, get_csrf_token, get_jwt

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
