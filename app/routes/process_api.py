# app/routes/process_api.py
from flask import Blueprint, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
import os

from app.models.api_process import ApiProcess
from app.models.user import User
from app.models.network_scan import NetworkScan
from app.utils.decorators import admin_required

bp = Blueprint("api_process", __name__)

# --- Existing ApiProcess Routes ---
# (โค้ดส่วนนี้ยังคงเหมือนเดิม)
@bp.route("/api/processes/me", methods=["GET"])
@jwt_required(locations=["cookies"])
def get_my_processes():
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
@admin_required
def get_all_processes():
    try:
        processes = ApiProcess.query.order_by(ApiProcess.created_at.desc()).limit(200).all()
        result = []
        for p in processes:
            data = p.to_dict()
            process_user = User.query.get(p.user_id)
            data["username"] = process_user.username if process_user else "Unknown"
            result.append(data)
        return jsonify(result), 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

@bp.route("/api/processes/<int:process_id>/pdf", methods=["GET"])
@jwt_required(locations=["cookies"])
def download_process_pdf(process_id):
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        process = ApiProcess.query.get(process_id)
        if not process:
            return {"ok": False, "error": "Process not found"}, 404
        if process.user_id != current_user_id and not user.is_admin:
            return {"ok": False, "error": "Access denied"}, 403
        if not process.result_pdf:
            return {"ok": False, "error": "No PDF report available"}, 404
        pdf_path = process.result_pdf
        if not os.path.exists(pdf_path):
            return {"ok": False, "error": "PDF file not found"}, 404
        return send_file(pdf_path, as_attachment=True)
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

# --- Network Scan Routes ---

@bp.route("/api/network-scans/all", methods=["GET"])
@admin_required
def get_all_scans():
    try:
        scans = NetworkScan.query.order_by(NetworkScan.created_at.desc()).limit(200).all()
        return jsonify([scan.to_dict() for scan in scans]), 200
    except Exception as e:
        current_app.logger.error(f"Error fetching all network scans: {e}")
        return jsonify({"ok": False, "error": "Internal server error"}), 500

@bp.route("/api/network-scans/results/<int:scan_id>", methods=["GET"])
@jwt_required(locations=["cookies"])
def get_scan_result(scan_id):
    """
    ดาวน์โหลดผลลัพธ์ JSON ของ network scan
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        scan = NetworkScan.query.get(scan_id)
        if not scan:
            return jsonify({"ok": False, "error": "Scan not found"}), 404
        
        if scan.user_id != current_user_id and not user.is_admin:
            return jsonify({"ok": False, "error": "Access denied"}), 403
            
        if not scan.result_json_path:
            return jsonify({"ok": False, "error": "Result file not available"}), 404
        
        # --- FIX STARTS HERE ---
        # สร้าง Absolute Path ให้ถูกต้อง
        # โดย `current_app.root_path` จะชี้ไปยังโฟลเดอร์ `app`
        # แล้วนำไปรวมกับ 'static' และพาธจากฐานข้อมูล
        absolute_path = os.path.join(current_app.root_path, 'static', scan.result_json_path)
        # --- FIX ENDS HERE ---

        if not os.path.exists(absolute_path):
            # Loggin จะแสดงพาธเต็มที่มันพยายามหา เพื่อให้ดีบักได้ง่ายขึ้น
            current_app.logger.error(f"Result file not found at path: {absolute_path}")
            return jsonify({"ok": False, "error": "Result file not found on server"}), 404
            
        return send_file(absolute_path, mimetype='application/json', as_attachment=False)

    except Exception as e:
        current_app.logger.error(f"Error fetching network scan result for scan_id={scan_id}: {e}")
        return jsonify({"ok": False, "error": "Internal server error"}), 500
