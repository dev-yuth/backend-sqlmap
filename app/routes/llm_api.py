# app/routes/llm_api.py
import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

# 💡 เราจะใช้ SDK 'google-genai' ที่คุณติดตั้งไว้
try:
    from google import genai
except ImportError:
    genai = None

bp = Blueprint("llm_api", __name__, url_prefix="/api/llm")


@bp.route("/analyze-payload", methods=["POST"])
@jwt_required(locations=["cookies"])
def analyze_payload():
    """
    Receives vulnerability type and title, then returns remediation steps from the LLM.
    """
    if not genai:
        return jsonify({"ok": False, "error": "Google GenAI SDK not installed (run: pip install google-genai)"}), 500

    try:
        data = request.get_json(silent=True) or {}
        vuln_title = data.get("title")
        vuln_type = data.get("type")

        if not vuln_title or not vuln_type:
            return jsonify({"ok": False, "error": "Vulnerability 'title' and 'type' are required"}), 400

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return jsonify({"ok": False, "error": "AI service is not configured (missing GEMINI_API_KEY)"}), 500

        prompt = f"""
You are a security expert. Provide clear, actionable remediation steps for the following SQL Injection vulnerability.
Provide code examples for the fix if possible (e.g., using parameterized queries in PHP or Python).
Format the entire response in Markdown.

Vulnerability Title: "{vuln_title}"
Vulnerability Type: "{vuln_type}"
"""
        
        # 💡 **สำคัญ:** ใช้โมเดล 'gemini-pro' ซึ่งเป็นโมเดลฟรีที่เสถียรที่สุด
        # การใช้ 'gemini-1.5-flash' อาจทำให้เกิด Error 404 หาก API Key ของคุณยังไม่รองรับ
        model_name = "gemini-2.5-flash"

        # 💡 **แก้ไขถาวร:** ใช้วิธีการเรียกที่เรียบง่ายและถูกต้องที่สุด
        
        # 1. สร้าง Client object
        client = genai.Client(api_key=api_key)
        
        # 2. เรียกใช้ generate_content โดยตรงจาก client.models
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        
        analysis_result = response.text

        return jsonify({"ok": True, "analysis": analysis_result})

    except Exception as e:
        print(f"Error in LLM API: {type(e).__name__} - {e}")
        return jsonify({"ok": False, "error": f"An error occurred with the AI service: {str(e)}"}), 500