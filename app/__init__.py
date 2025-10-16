# app/__init__.py
from flask import Flask
from .config import Config
from .extensions import db, migrate, jwt, cors, mail
from .routes import register_routes


# import models for alembic
from app.models.user import User
from app.models.login_log import LoginLog
from app.models.api_process import ApiProcess

def create_app(config_object: object | None = None):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.from_object(config_object or Config)

    # --- JWT / cookie / CSRF config BEFORE jwt.init_app ----
    app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
    app.config["JWT_COOKIE_CSRF_PROTECT"] = True
    app.config["JWT_ACCESS_COOKIE_PATH"] = "/"
    app.config["JWT_REFRESH_COOKIE_PATH"] = "/api/auth/refresh"
    app.config["JWT_COOKIE_SAMESITE"] = "Lax"
    app.config["JWT_COOKIE_SECURE"] = False  # Dev

    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 3600  # 1 ชั่วโมง
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = 60*60*24*30  # 30 วัน

    # optional: set cookie names or expirations ifต้องการ
    # app.config["JWT_ACCESS_COOKIE_NAME"] = "access_token_cookie"
 
    # init extensions (หลังตั้งค่า)
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)   # ใช้ jwt จาก app.extensions
    # CORS: allow credentials ถ้า frontend แยก origin (เช่น localhost:3000)
    # cors.init_app(app, origins=app.config.get("CORS_ORIGINS", []), supports_credentials=True)
    cors.init_app(app, origins=["http://localhost:5000"], supports_credentials=True)

    # Initialize Flask-Mail
    mail.init_app(app)
    # register blueprints
    register_routes(app)

   

    return app
