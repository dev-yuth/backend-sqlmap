# app/models/token_blacklist.py
from datetime import datetime
from app.extensions import db   # <-- เปลี่ยนที่นี่

class TokenBlocklist(db.Model):
    __tablename__ = "token_blocklist"
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(100), nullable=False, unique=True)
    token_type = db.Column(db.String(10), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<TokenBlocklist {self.jti}>"
