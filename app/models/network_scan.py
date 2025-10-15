# app/models/network_scan.py
from datetime import datetime
from app.extensions import db

class NetworkScan(db.Model):
    __tablename__ = "network_scans"

    # Status mapping: 0=pending, 1=running, 2=completed, 3=error
    STATUS_MAP = {
        0: 'Pending',
        1: 'Running',
        2: 'Success',
        3: 'Error'
    }

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    ip_range = db.Column(db.String(255), nullable=False)
    concurrency = db.Column(db.Integer, default=150)
    status = db.Column(db.Integer, default=0, nullable=False)
    found_hosts_count = db.Column(db.Integer, default=0)
    result_json_path = db.Column(db.String(255), nullable=True) # Path to the result JSON file
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref="network_scans")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            # --- FIX STARTS HERE ---
            "username": self.user.username if self.user else "Unknown", # 1. เพิ่ม username
            "ip_range": self.ip_range,
            "concurrency": self.concurrency,
            "status": self.STATUS_MAP.get(self.status, 'unknown'), # 2. แปลง status เป็นข้อความ
            "status_code": self.status, 
            # --- FIX ENDS HERE ---
            "found_hosts_count": self.found_hosts_count,
            "result_json_path": self.result_json_path,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }