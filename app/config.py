# app/config.py
import os
from typing import Tuple
from dotenv import load_dotenv

# โหลดไฟล์ .env
load_dotenv()

def get_python_path() -> str:
    return os.getenv("PYTHON_PATH", "")

def get_sqlmap_path() -> str:
    return os.getenv("SQLMAP_PATH", "")

def get_allowed_origins() -> Tuple[str, ...]:
    origins = os.getenv("CORS_ALLOWED_ORIGINS", "*")
    return tuple(o.strip() for o in origins.split(",") if o.strip())

from datetime import timedelta

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "mysql+pymysql://root:@localhost/sqlmapdb"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret")

    # แปลงเป็น timedelta
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=int(os.getenv("JWT_ACCESS_EXPIRES", 3600)))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(seconds=int(os.getenv("JWT_REFRESH_EXPIRES", 604800)))

    CORS_ORIGINS = tuple(o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",") if o.strip())

    # Mail server settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')

