# app/routes/views/views.py
from flask import Blueprint, render_template, redirect, url_for, session, request
import jwt  # หรือใช้ flask_jwt_extended


bp = Blueprint("views", __name__)

@bp.route("/login")
def login_page():
    return render_template("login.html")

@bp.route("/dashboard")
def dashboard_page():
    # ตอนนี้เรายังเช็ค token ใน localStorage ฝั่ง client อยู่
    # แต่ถ้าอยากให้ Flask redirect ไป login เลย ก็ควรเปลี่ยนมาเก็บ token ใน cookie
    return render_template("dashboard.html")

@bp.route("/")
def index():
    # default redirect ไป login (กัน user กด / แล้วเข้า dashboard ได้ตรงๆ)
    return redirect(url_for("views.login_page"))
    
@bp.route("/admin/dashboard")
def admin_dashboard():
    return render_template("admin_dashboard.html")

@bp.route("/user/dashboard")
def user_dashboard():
    return render_template("user_dashboard.html")
    
@bp.route("/sqlmap_urls")
def sqlmap_urls():
    return render_template("sqlmap_ulrs.html")
