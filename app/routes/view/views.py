# app/routes/views/views.py
from flask import Blueprint, render_template

bp = Blueprint("views", __name__)

@bp.route("/login")
def login_page():
    return render_template("login.html")

@bp.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")
