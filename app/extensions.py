# app/extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_mail import Mail

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()
mail = Mail()

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    # import ภายในฟังก์ชัน เพื่อลดปัญหา circular import / ชื่อไฟล์ไม่ตรง
    from app.models.token_blacklist import TokenBlocklist  # <-- ปรับชื่อให้ตรงไฟล์ของคุณ
    jti = jwt_payload.get("jti")
    return TokenBlocklist.query.filter_by(jti=jti).first() is not None
