# app/routes/views/views.py
from flask import Blueprint, render_template, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity # เพิ่ม get_jwt_identity
from app.utils.decorators import admin_required

bp = Blueprint("views", __name__)

@bp.route("/login")
@jwt_required(locations=["cookies"], optional=True) # ✅ ทำให้ decorator ไม่บังคับ
def login_page():
        # ตรวจสอบว่ามี identity (ล็อกอินอยู่) หรือไม่
    if get_jwt_identity():
        # ถ้ามี ให้ redirect ไป dashboard ทันทีจากฝั่ง server
        return redirect(url_for("views.dashboard_page"))
    
    # ถ้าไม่มี ก็แสดงหน้า login ตามปกติ
    return render_template("login.html")

@bp.route("/dashboard")
@jwt_required(locations=["cookies"])
def dashboard_page():
    return render_template("dashboard.html")

@bp.route("/")
def index():
    return redirect(url_for("views.login_page"))

@bp.route("/admin/dashboard")
@jwt_required(locations=["cookies"])
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")

@bp.route("/sqlmap-urls")
@jwt_required(locations=["cookies"])
@admin_required
def sqlmap_urls():
    return render_template("sqlmap_ulrs.html")

@bp.route("/user/dashboard")
@jwt_required(locations=["cookies"])
def user_dashboard():
    return render_template("user_dashboard.html")

@bp.route("/sqlmap-basic")
@jwt_required(locations=["cookies"])
def sqlmap_basic():
    return render_template("sqlmap_basic.html")

@bp.route("/admin/users")
@jwt_required(locations=["cookies"])
@admin_required
def admin_users_page():
    """Renders the user management page for admins."""
    return render_template("admin_user_management.html")

