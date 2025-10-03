# app/models/api_process.py
from datetime import datetime
from app.extensions import db

class ApiProcess(db.Model):
    __tablename__ = "api_processes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    endpoint = db.Column(db.String(255), nullable=False)
    payload_count = db.Column(db.Integer, default=0)
    status_ok = db.Column(db.Boolean, default=False)
    result_pdf = db.Column(db.String(255), nullable=True)
    result_json = db.Column(db.Text(length=4294967295), nullable=True)  # LONGTEXT
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="api_processes")

    def to_dict(self):
        import json
        try:
            json_data = json.loads(self.result_json) if self.result_json else None
        except Exception:
            json_data = self.result_json  # ถ้า decode ไม่ได้
        return {
            "id": self.id,
            "user_id": self.user_id,
            "endpoint": self.endpoint,
            "payload_count": self.payload_count,
            "status_ok": self.status_ok,
            "result_pdf": self.result_pdf,
            "result_json": json_data,
            "created_at": self.created_at.isoformat(),
        }
