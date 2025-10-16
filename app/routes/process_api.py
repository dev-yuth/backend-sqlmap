# app/routes/process_api.py
from flask import Blueprint, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
import json
from app.extensions import db
from app.models.api_process import ApiProcess
from app.models.user import User
from app.models.network_scan import NetworkScan
from app.utils.decorators import admin_required

bp = Blueprint("api_process", __name__)

# --- Existing ApiProcess Routes ---
# (โค้ดส่วนนี้ยังคงเหมือนเดิม)
# นี่คือฟังก์ชัน _enrich_process_dict ที่ควรมีอยู่แล้ว
def _enrich_process_dict(p_dict):
    """Helper function to read and embed JSON content."""
    json_path = p_dict.get('result_json')
    
    # เปลี่ยนชื่อ field เดิมเพื่อเก็บแค่ path
    p_dict['result_json_file'] = json_path 
    
    # field ใหม่สำหรับเก็บเนื้อหา JSON
    p_dict['result_json'] = None 

    if json_path:
        absolute_path = os.path.join(current_app.root_path, 'static', json_path)
        if os.path.exists(absolute_path):
            try:
                with open(absolute_path, 'r', encoding='utf-8') as f:
                    p_dict['result_json'] = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                current_app.logger.error(f"Could not read or parse JSON for process {p_dict['id']}: {e}")
                p_dict['result_json'] = [{"error": "Failed to load result file."}]
    return p_dict


@bp.route("/api/processes/me", methods=["GET"])
@jwt_required(locations=["cookies"])
def get_my_processes():
    try:
        current_user_id = get_jwt_identity()
        processes = ApiProcess.query.filter_by(user_id=current_user_id)\
            .order_by(ApiProcess.created_at.desc())\
            .limit(100)\
            .all()
        
        # --- ส่วนที่ปรับปรุง ---
        # สร้าง list ใหม่เพื่อเก็บข้อมูล process ที่ผ่านการแก้ไขแล้ว
        enriched_processes = []
        for p in processes:
            # แปลง object เป็น dictionary
            data = p.to_dict()
            
            # เรียกใช้ helper function เพื่ออ่านไฟล์ JSON และเพิ่มข้อมูลเข้าไปใน dictionary
            enriched_data = _enrich_process_dict(data) 
            
            enriched_processes.append(enriched_data)
        
        return jsonify(enriched_processes), 200
        # --- สิ้นสุดส่วนที่ปรับปรุง ---

    except Exception as e:
        current_app.logger.error(f"Error in get_my_processes: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@bp.route("/api/processes/all", methods=["GET"])
@admin_required
def get_all_processes():
    try:
        # ใช้ joinedload เพื่อให้โหลดข้อมูล User มาพร้อมกัน ซึ่งมีประสิทธิภาพดีกว่าการ query ใน loop
        processes = ApiProcess.query.options(db.joinedload(ApiProcess.user)).order_by(ApiProcess.created_at.desc()).limit(200).all()
        
        result_list = []
        for p in processes:
            # แปลง object เป็น dictionary
            data = p.to_dict()
            
            # เพิ่มข้อมูล username จาก object user ที่โหลดมาด้วยกัน
            data["username"] = p.user.username if p.user else "Unknown"

            # --- ส่วนที่ปรับปรุง ---
            json_path_from_db = data.get('result_json')
            
            # 1. เปลี่ยนชื่อ key เดิมเพื่อเก็บ "ที่อยู่ของไฟล์"
            data['result_json_file'] = json_path_from_db
            
            # 2. เตรียม key ใหม่สำหรับ "เนื้อหาในไฟล์"
            data['result_json'] = None 

            if json_path_from_db:
                # สร้าง absolute path ไปยังไฟล์
                absolute_path = os.path.join(current_app.root_path, 'static', json_path_from_db)
                
                # ตรวจสอบว่าไฟล์มีอยู่จริงหรือไม่
                if os.path.exists(absolute_path):
                    try:
                        # อ่านและแปลงข้อมูลจากไฟล์ JSON
                        with open(absolute_path, 'r', encoding='utf-8') as f:
                            data['result_json'] = json.load(f)
                    except Exception as e:
                        current_app.logger.error(f"Could not read or parse JSON for process {data['id']}: {e}")
                        # ถ้าไฟล์มีปัญหา ให้ส่งค่า error ไปแทน
                        data['result_json'] = {"error": f"Failed to read result file: {e}"}
            
            result_list.append(data)
            
        return jsonify(result_list), 200
        
    except Exception as e:
        current_app.logger.error(f"Error in get_all_processes: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# --- CHANGE START: แก้ไข Route ให้ตรงกับ HTML (ใช้ processes พหูพจน์) ---
@bp.route("/api/processes/<int:process_id>/pdf", methods=["GET"])
@jwt_required(locations=["cookies"])
def download_process_pdf(process_id):
    """
    Endpoint สำหรับดาวน์โหลดไฟล์ Report ฉบับ PDF
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        process = ApiProcess.query.get(process_id)
        if not process:
            return jsonify({"ok": False, "error": "Process not found"}), 404
        
        # # ตรวจสอบสิทธิ์การเข้าถึง
        # if process.user_id != current_user_id and not user.is_admin:
        #     return jsonify({"ok": False, "error": "Access denied"}), 403
            
        # ตรวจสอบว่ามีไฟล์ PDF หรือไม่
        if not process.result_pdf:
            return jsonify({"ok": False, "error": "PDF report not available for this process"}), 404
        
        # สร้าง Path เต็มไปยังไฟล์ PDF
        absolute_path = os.path.join(current_app.root_path, 'static', process.result_pdf)

        if not os.path.exists(absolute_path):
            current_app.logger.error(f"PDF file not found at path: {absolute_path}")
            return jsonify({"ok": False, "error": "PDF file not found on server"}), 404
            
        # ✅ ใช้ send_file เพื่อส่งไฟล์ให้ผู้ใช้ดาวน์โหลด
        return send_file(absolute_path, as_attachment=True)

    except Exception as e:
        current_app.logger.error(f"Error downloading PDF for process id {process_id}: {e}")
        return jsonify({"ok": False, "error": "An internal error occurred while processing the PDF download."}), 500
# --- CHANGE END ---

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
