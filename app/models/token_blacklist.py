from datetime import datetime
from app.extensions import db

class TokenBlocklist(db.Model):
    __tablename__ = "token_blocklist"
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), unique=True, nullable=False, index=True)  # JWT ID
    token_type = db.Column(db.String(10))  # access / refresh
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
