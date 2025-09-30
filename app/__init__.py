# app/__init__.py
from flask import Flask
from .config import Config
from .extensions import db, jwt, cors, migrate
from .routes import register_routes

def create_app(config_object: object | None = None):
    app = Flask(__name__, static_folder="../static", static_url_path="/static")
    app.config.from_object(config_object or Config)

    # init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, origins=app.config['CORS_ORIGINS'])

    # register blueprints
    register_routes(app)

    return app
