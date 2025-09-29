import os
from typing import Tuple

# Default paths based on your environment. You can override via environment variables.
DEFAULT_PYTHON_PATH = r"C:\\Users\\Kios02\\AppData\\Local\\Programs\\Python\\Python313\\python.exe"
DEFAULT_SQLMAP_PATH = r"C:\\Users\\Kios02\\Desktop\\test\\angular\\py\\sqlmap-dev\\sqlmap.py"


def get_python_path() -> str:
    return os.getenv("PYTHON_PATH", DEFAULT_PYTHON_PATH)


def get_sqlmap_path() -> str:
    return os.getenv("SQLMAP_PATH", DEFAULT_SQLMAP_PATH)


def get_allowed_origins() -> Tuple[str, ...]:
    # Comma-separated list of origins; default to allow all for dev
    origins = os.getenv("CORS_ALLOWED_ORIGINS", "*")
    return tuple(o.strip() for o in origins.split(",") if o.strip())
