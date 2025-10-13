# app/routes/views/views.py
from flask import Blueprint, render_template, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.decorators import admin_required, active_user_required # เพิ่ม active_user_required

bp = Blueprint("views", __name__)

@bp.route("/login")
@jwt_required(locations=["cookies"], optional=True)
def login_page():
    if get_jwt_identity():
        return redirect(url_for("views.dashboard_page"))
    
    return render_template("login.html")

@bp.route("/dashboard")
@jwt_required(locations=["cookies"])
@active_user_required # เพิ่ม decorator ตรงนี้
def dashboard_page():
    return render_template("dashboard.html")

@bp.route("/")
def index():
    return redirect(url_for("views.login_page"))

@bp.route("/admin/dashboard")
@jwt_required(locations=["cookies"])
@admin_required
@active_user_required # เพิ่ม decorator ตรงนี้
def admin_dashboard():
    return render_template("admin_dashboard.html")

@bp.route("/sqlmap-urls")
@jwt_required(locations=["cookies"])
@admin_required
@active_user_required # เพิ่ม decorator ตรงนี้
def sqlmap_urls():
    return render_template("sqlmap_ulrs.html")

@bp.route("/user/dashboard")
@jwt_required(locations=["cookies"])
@active_user_required # เพิ่ม decorator ตรงนี้
def user_dashboard():
    return render_template("user_dashboard.html")

@bp.route("/sqlmap-basic")
@jwt_required(locations=["cookies"])
@active_user_required # เพิ่ม decorator ตรงนี้
def sqlmap_basic():
    return render_template("sqlmap_basic.html")

@bp.route("/admin/user-management")
@jwt_required(locations=["cookies"])
@admin_required
@active_user_required # เพิ่ม decorator ตรงนี้
def admin_users_page():
    """Renders the user management page for admins."""
    return render_template("admin_user_management.html")