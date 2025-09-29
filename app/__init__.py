# app/__init__.py
from flask import Flask
from .config import Config
from .extensions import db, jwt  # import jwt
from .routes import register_routes

def create_app(config_object: object | None = None):
    app = Flask(__name__, static_folder="../static", static_url_path="/static")
    app.config.from_object(config_object or Config)

    # init extensions
    db.init_app(app)
    jwt.init_app(app)  # <-- เพิ่ม JWTManager

    # register blueprints หลังจาก extensions init
    register_routes(app)

    return app
