# app/routes/process_api.py
from flask import Blueprint, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
import os

from app.models.api_process import ApiProcess
from app.models.user import User

bp = Blueprint("api_process", __name__)

@bp.route("/api/processes/me", methods=["GET"])
@jwt_required(locations=["cookies"])
def get_my_processes():
    """ดึงประวัติการทำงานของ user ปัจจุบัน"""
    try:
        current_user_id = get_jwt_identity()
        
        processes = ApiProcess.query.filter_by(user_id=current_user_id)\
            .order_by(ApiProcess.created_at.desc())\
            .limit(100)\
            .all()
        
        return jsonify([p.to_dict() for p in processes]), 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@bp.route("/api/processes/all", methods=["GET"])
@jwt_required(locations=["cookies"])
def get_all_processes():
    """ดึงประวัติการทำงานของ user ทั้งหมด (Admin only)"""
    try:
        current_user_id = get_jwt_identity()
        
        # ตรวจสอบว่าเป็น admin หรือไม่
        user = User.query.get(current_user_id)
        if not user or not user.is_admin:
            return {"ok": False, "error": "Admin access required"}, 403
        
        processes = ApiProcess.query\
            .order_by(ApiProcess.created_at.desc())\
            .limit(200)\
            .all()
        
        result = []
        for p in processes:
            data = p.to_dict()
            # เพิ่มข้อมูล username
            process_user = User.query.get(p.user_id)
            data["username"] = process_user.username if process_user else "Unknown"
            result.append(data)
        
        return jsonify(result), 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@bp.route("/api/processes/<int:process_id>/pdf", methods=["GET"])
@jwt_required(locations=["cookies"])
def download_process_pdf(process_id):
    """ดาวน์โหลด PDF report ของ process"""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        process = ApiProcess.query.get(process_id)
        if not process:
            return {"ok": False, "error": "Process not found"}, 404
        
        # ตรวจสอบสิทธิ์: ต้องเป็น owner หรือ admin
        if process.user_id != current_user_id and not user.is_admin:
            return {"ok": False, "error": "Access denied"}, 403
        
        if not process.result_pdf:
            return {"ok": False, "error": "No PDF report available"}, 404
        
        pdf_path = process.result_pdf
        if not os.path.exists(pdf_path):
            return {"ok": False, "error": "PDF file not found"}, 404
        
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"sqlmap_report_{process_id}.pdf"
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500