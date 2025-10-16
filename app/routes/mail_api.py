from flask import request, jsonify, Blueprint, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.api_process import ApiProcess
from app.utils.mailer import send_security_report_email
from app.utils.decorators import admin_required
import os
import datetime
import json # <-- Import the json library
from flask import url_for # <-- เพิ่มการ import url_for

bp = Blueprint('mail_api', __name__)

@bp.route('/api/send-report/<int:process_id>', methods=['POST'])
@jwt_required()
@admin_required
def send_report(process_id):
    data = request.get_json()
    recipient = data.get('recipient')

    if not recipient:
        return jsonify({"ok": False, "error": "Recipient email is required"}), 400

    process = ApiProcess.query.get(process_id)
    if not process:
        return jsonify({"ok": False, "error": "Process not found"}), 404

    # --- PDF File Check (Corrected from previous step) ---
    if not process.result_pdf:
        return jsonify({"ok": False, "error": "No PDF path recorded"}), 404
    
    absolute_pdf_path = os.path.join(current_app.root_path, 'static', process.result_pdf)
    if not os.path.exists(absolute_pdf_path):
        return jsonify({"ok": False, "error": "PDF report not found on server storage"}), 404

    # --- START: NEW FIX FOR JSON FILE ---
    json_content = None
    db_count = 0
    
    if process.result_json:
        absolute_json_path = os.path.join(current_app.root_path, 'static', process.result_json)
        if os.path.exists(absolute_json_path):
            try:
                with open(absolute_json_path, 'r', encoding='utf-8') as f:
                    json_content = json.load(f)
                # Safely calculate db_count from the loaded JSON content
                if json_content and isinstance(json_content, list) and len(json_content) > 0:
                    db_count = len(json_content[0].get("listDb", {}).get("names", []))
            except Exception as e:
                current_app.logger.error(f"Failed to read or parse JSON for process {process.id}: {e}")
    # --- END: NEW FIX FOR JSON FILE ---

    try:
        with open(absolute_pdf_path, 'rb') as f:
            pdf_data = f.read()

        sender_username = get_jwt_identity()
        timestamp = datetime.datetime.now().strftime("%d %B %Y, %H:%M")
        pdf_download_url = url_for('static', filename=process.result_pdf, _external=True)

        report_data = {
            "url": process.endpoint,
            "ok": process.status_ok,
            "db_count": db_count, # <-- Use the correctly calculated db_count
            "sender": sender_username,
            "sent_at": timestamp,
            "pdf_download_url": pdf_download_url
        }
        
        subject = f"SQLMap Scan Report for {process.endpoint}"
        
        success, message = send_security_report_email(
            recipient, 
            subject, 
            report_data, 
            pdf_attachment=pdf_data,
            pdf_filename=os.path.basename(process.result_pdf)
        )
        
        if success:
            return jsonify({"ok": True, "message": "Email sent successfully"}), 200
        else:
            return jsonify({"ok": False, "error": message}), 500
            
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500