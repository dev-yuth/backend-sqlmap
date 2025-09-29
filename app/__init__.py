# app/__init__.py
from flask import Flask
from .config import Config
from .extensions import db
from .routes import register_routes  # import ฟังก์ชันเดียว

def create_app(config_object: object | None = None):
    app = Flask(__name__, static_folder="../static", static_url_path="/static")
    app.config.from_object(config_object or Config)

    # register blueprints
    register_routes(app)

    # init extensions
    db.init_app(app)

    return app
