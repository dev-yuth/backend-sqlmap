# app/routes/views/views.py
from flask import Blueprint, render_template, redirect, url_for
from flask_jwt_extended import jwt_required
from app.utils.decorators import admin_required

bp = Blueprint("views", __name__)

@bp.route("/login")
def login_page():
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

@bp.route("/sqlmap_urls")
@jwt_required(locations=["cookies"])
@admin_required
def sqlmap_urls():
    return render_template("sqlmap_ulrs.html")

@bp.route("/user/dashboard")
@jwt_required(locations=["cookies"])
def user_dashboard():
    return render_template("user_dashboard.html")

@bp.route("/sqlmap_basic")
@jwt_required(locations=["cookies"])
def sqlmap_basic():
    return render_template("sqlmap_basic.html")
