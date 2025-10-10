# app/routes/llm_api.py
import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import google.generativeai as genai

bp = Blueprint("llm_api", __name__, url_prefix="/api/llm")

@bp.route("/analyze-payload", methods=["POST"])
@jwt_required(locations=["cookies"])
def analyze_payload():
    """
    Receives a payload from the client, sends it to the LLM for analysis, and returns the result.
    """
    try:
        data = request.get_json()
        payload = data.get("payload")

        if not payload:
            return jsonify({"ok": False, "error": "Payload is required"}), 400

        api_key = os.getenv("GEMINI_API_KEY")
        print(api_key)
        if not api_key:
            return jsonify({"ok": False, "error": "AI service is not configured on the server"}), 500

        genai.configure(api_key=api_key)

        # ✅ FIX: Changed the model name to the more compatible 'gemini-1.0-pro'
        model = genai.GenerativeModel('gemini-1.0-pro')

        # The prompt for the AI
        prompt = f"""
        You are a security expert. Analyze the following SQL Injection payload.
        Explain its purpose, how it works, and its potential impact.
        Most importantly, provide clear, actionable remediation steps to fix this vulnerability.
        Provide code examples for the fix if possible (e.g., using parameterized queries in PHP or Python).
        Format the entire response in Markdown for readability.

        Payload:
        ```{payload}```
        """

        response = model.generate_content(prompt)
        analysis_result = response.text

        return jsonify({"ok": True, "analysis": analysis_result})

    except Exception as e:
        # Log the error for easier debugging
        print(f"Error in LLM API: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500