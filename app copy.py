import os
import json
import shlex
from typing import Any, Dict, List, Optional
from flask import Flask, request, jsonify
from flask_restful import Api, Resource
from flask_cors import CORS
import subprocess
from urllib.parse import urlencode

from config import get_python_path, get_sqlmap_path, get_allowed_origins


app = Flask(__name__)
api = Api(app)
CORS(app, resources={r"*": {"origins": list(get_allowed_origins()) or ["*"]}})


def normalize_headers(headers: Any) -> Optional[str]:
    """
    Accepts either a string (already formatted) or an object of key: value pairs.
    Returns a CRLF-joined header string suitable for sqlmap's --headers option.
    """
    if not headers:
        return None

    if isinstance(headers, str):
        return headers.strip() or None

    if isinstance(headers, dict):
        # Join as `Key: Value` per line
        parts: List[str] = []
        for k, v in headers.items():
            if k and v is not None:
                parts.append(f"{k}: {v}")
        return "\r\n".join(parts) if parts else None

    # Fallback: try to dump as JSON if given a list or unknown
    try:
        return json.dumps(headers)
    except Exception:
        return None


class Health(Resource):
    def get(self):
        return {"ok": True, "service": "sqlmap-api", "version": 1}, 200


class RunSqlmap(Resource):
    def post(self):
        try:
            body: Dict[str, Any] = request.get_json(force=True, silent=False) or {}
        except Exception as e:
            return {"ok": False, "error": f"Invalid JSON body: {e}"}, 400

        url = body.get("url")
        param = body.get("param")
        data = body.get("data")
        headers = body.get("headers")
        method = body.get("method")  # e.g., GET, POST, PUT...
        json_mode = bool(body.get("json", False))
        raw_mode = bool(body.get("raw", False))

        # Enumeration flags (booleans)
        enum_flags = {
            "users": body.get("users"),
            "passwords": body.get("passwords"),
            "privileges": body.get("privileges"),
            "roles": body.get("roles"),
            "dbs": body.get("dbs"),
            "tables": body.get("tables"),
            "columns": body.get("columns"),
            "schema": body.get("schema"),
        }

        if not url or not param:
            return {"ok": False, "error": "URL and parameter (param) are required."}, 400

        python_path = get_python_path()
        sqlmap_path = get_sqlmap_path()

        # Build command as a list (secure, no shell)
        cmd: List[str] = [
            python_path,
            sqlmap_path,
            "-u", str(url),
            "-p", str(param),
            "--batch",
        ]

        # Optional additions: data handling
        if data is not None and data != "":
            data_str: str
            if json_mode and not isinstance(data, str):
                # When json mode, serialize objects to JSON and ensure header
                try:
                    data_str = json.dumps(data)
                except Exception:
                    data_str = str(data)
                # Ensure Content-Type header
                if not headers:
                    headers = {"Content-Type": "application/json"}
                elif isinstance(headers, dict):
                    headers.setdefault("Content-Type", "application/json")
            elif not raw_mode and isinstance(data, dict):
                # url-encode dict when not JSON/raw
                data_str = urlencode(data)
                if isinstance(headers, dict):
                    headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            else:
                data_str = str(data)

            cmd.extend(["--data", data_str])

        hdrs = normalize_headers(headers)
        if hdrs:
            cmd.extend(["--headers", hdrs])

        # HTTP method: explicit or auto POST when data present
        final_method = method or ("POST" if (data is not None and data != "") else None)
        if final_method:
            cmd.extend(["--method", str(final_method)])

        # Apply enumeration flags when True
        for flag, enabled in enum_flags.items():
            if enabled is True:
                cmd.append(f"--{flag}")

        # Optional additional arguments array for advanced usage
        extra_args = body.get("extraArgs")
        if isinstance(extra_args, list):
            for a in extra_args:
                if isinstance(a, str) and a.strip():
                    cmd.append(a.strip())

        # Timeout
        try:
            timeout = int(os.getenv("SQLMAP_TIMEOUT", "300"))
        except ValueError:
            timeout = 300

        # Execute
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            return {
                "ok": False,
                "error": "sqlmap execution timed out",
                "timeoutSeconds": timeout,
                "command": cmd,
            }, 504
        except FileNotFoundError as e:
            return {
                "ok": False,
                "error": f"Executable not found: {e}",
                "command": cmd,
            }, 500
        except Exception as e:
            return {
                "ok": False,
                "error": f"Unexpected error: {e}",
                "command": cmd,
            }, 500

        ok = completed.returncode == 0
        # Trim very long output to avoid huge payloads (keep ~2MB combined)
        max_len = 2_000_000
        stdout = (completed.stdout or "")
        stderr = (completed.stderr or "")
        if len(stdout) > max_len:
            stdout = stdout[:max_len] + "\n... [truncated]"
        if len(stderr) > max_len:
            stderr = stderr[:max_len] + "\n... [truncated]"

        return {
            "ok": ok,
            "exitCode": completed.returncode,
            "command": cmd,
            "stdout": stdout,
            "stderr": stderr,
        }, 200 if ok else 500


api.add_resource(Health, "/health")
api.add_resource(RunSqlmap, "/api/run-sqlmap")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    # Show configured executables and their existence to help diagnose path issues on Windows
    py_path = get_python_path()
    sm_path = get_sqlmap_path()
    print(f"[startup] Using PYTHON_PATH={py_path} (exists={os.path.exists(py_path)})")
    print(f"[startup] Using SQLMAP_PATH={sm_path} (exists={os.path.exists(sm_path)})")
    app.run(host="0.0.0.0", port=port, debug=True)
