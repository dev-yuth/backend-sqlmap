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

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:@localhost/sqlmapdb"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret")
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_EXPIRES", 3600))
    JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv("JWT_REFRESH_EXPIRES", 604800))
    CORS_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "*")
