# app/models/login_log.py
from datetime import datetime
from app.extensions import db

class LoginLog(db.Model):
    __tablename__ = "login_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    ip_address = db.Column(db.String(45))  # รองรับ IPv6
    user_agent = db.Column(db.Text)
    success = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="login_logs")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "success": self.success,
            "created_at": self.created_at.isoformat(),
        }
