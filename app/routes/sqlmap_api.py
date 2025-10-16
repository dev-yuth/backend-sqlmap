# app/routes/sqlmap_api.py
import os
import json
import shlex
import re
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import datetime

from flask import Blueprint, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.config import get_python_path, get_sqlmap_path
from app.extensions import db
from app.models.api_process import ApiProcess
from app.utils.pdf_generator import generate_sqlmap_pdf_report

bp = Blueprint("sqlmap_api", __name__)

# --- regex / helpers ---
BLOCK_RE = re.compile(r"---\n(Parameter:.*?)\n---", flags=re.DOTALL | re.IGNORECASE)
PARAM_LINE_RE = re.compile(r"Parameter:\s*(?P<name>[\w\-\._]+)\s*(?:\((?P<loc>[^)]+)\))?", flags=re.IGNORECASE)
RESUMED_RE = re.compile(r"resumed:\s*'?(?P<val>[^']+)'?", flags=re.IGNORECASE)

def extract_databases_from_stdout_v3(stdout: str):
    if not stdout:
        return {"names": [], "count": 0, "rawMatches": []}
    lines = stdout.splitlines()
    names = []
    raw_matches = []
    count = None
    count_m = re.search(r"available databases\s*\[(\d+)\]", stdout, flags=re.IGNORECASE)
    if count_m:
        try:
            count = int(count_m.group(1))
        except:
            count = None
    list_item_re = re.compile(r"^\s*\[\*\]\s*`?([A-Za-z0-9_\-\.]+)`?\s*$")
    for ln in lines:
        m = list_item_re.match(ln)
        if m:
            name = m.group(1).strip()
            raw_matches.append(name)
            if name not in names:
                names.append(name)
    if not names:
        resumed_re = re.compile(r"resumed:\s*'?(?P<val>[^']+)'?", flags=re.IGNORECASE)
        for ln in lines:
            m = resumed_re.search(ln)
            if m:
                val = m.group("val").strip().strip("'\"")
                if val and not re.fullmatch(r"\d+", val):
                    raw_matches.append(val)
                    if val not in names:
                        names.append(val)
    final_count = int(count) if count is not None else len(names)
    return {"names": names, "count": final_count, "rawMatches": raw_matches}

def parse_parameter_block(raw_block: str) -> Dict[str, Any]:
    lines = raw_block.splitlines()
    if not lines:
        return {}
    m = PARAM_LINE_RE.match(lines[0].strip())
    name = m.group("name") if m else None
    loc = m.group("loc").strip() if (m and m.group("loc")) else None
    findings = []
    cur = None
    for raw in lines[1:]:
        s = raw.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("type:"):
            if cur:
                findings.append(cur)
            cur = {"type": s[len("Type:"):].strip(), "title": None, "payload": None}
        elif low.startswith("title:"):
            if cur is None:
                cur = {"type": None, "title": s[len("Title:"):].strip(), "payload": None}
            else:
                cur["title"] = s[len("Title:"):].strip()
        elif low.startswith("payload:"):
            if cur is None:
                cur = {"type": None, "title": None, "payload": s[len("Payload:"):].strip()}
            else:
                cur["payload"] = s[len("Payload:"):].strip()
        else:
            if cur and cur.get("payload") is not None:
                cur["payload"] = cur["payload"] + "\n" + s
    if cur:
        findings.append(cur)
    return {"parameter": name, "location": loc, "raw": raw_block.strip(), "findings": findings}

def extract_parameters_from_stdout(stdout: str) -> List[Dict[str, Any]]:
    if not stdout:
        return []
    matches = BLOCK_RE.findall(stdout)
    results = []
    for idx, block in enumerate(matches):
        parsed = parse_parameter_block(block)
        parsed["index"] = idx
        results.append(parsed)
    return results

def normalize_headers(headers: Any) -> Optional[str]:
    if not headers:
        return None
    if isinstance(headers, str):
        return headers.strip() or None
    if isinstance(headers, dict):
        parts: List[str] = []
        for k, v in headers.items():
            if k and v is not None:
                parts.append(f"{k}: {v}")
        return "\r\n".join(parts) if parts else None
    try:
        return json.dumps(headers)
    except Exception:
        return None

ALLOWED_FLAGS = {
    "--level", "--risk", "--threads", "--timeout", "--technique",
    "--smart", "-p", "--dbs", "--batch", "--skip", "--start"
}
EXTRA_ARG_SAFE_RE = re.compile(r"^[-]{1,2}[A-Za-z0-9\-\._/]+=?.*$")

@bp.route("/health", methods=["GET"])
def health():
    return {"ok": True, "service": "sqlmap-api", "version": 1}, 200

@bp.route("/api/run-sqlmap", methods=["POST"])
@jwt_required(locations=["cookies"])
def run_sqlmap():
    current_user_id = get_jwt_identity()
    
    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception as e:
        return {"ok": False, "error": f"Invalid JSON body: {e}"}, 400

    python_path = get_python_path()
    sqlmap_path = get_sqlmap_path()

    try:
        DEFAULT_MAX_CONCURRENCY = int(os.getenv("SQLMAP_MAX_CONCURRENCY", "3"))
    except ValueError:
        DEFAULT_MAX_CONCURRENCY = 3
    try:
        PROCESS_TIMEOUT = int(os.getenv("SQLMAP_PROCESS_TIMEOUT", "300"))
    except ValueError:
        PROCESS_TIMEOUT = 300

    def validate_and_split_extra_args(extra_args_raw: Any) -> List[str]:
        tokens: List[str] = []
        if not extra_args_raw:
            return tokens
        if isinstance(extra_args_raw, str):
            try:
                tokens = shlex.split(extra_args_raw)
            except Exception:
                tokens = [extra_args_raw]
        elif isinstance(extra_args_raw, list):
            tokens = [str(x) for x in extra_args_raw]
        else:
            return []
        safe_tokens: List[str] = []
        i = 0
        while i < len(tokens):
            t = tokens[i].strip()
            if not t:
                i += 1
                continue
            if not t.startswith("-"):
                i += 1
                continue
            if not EXTRA_ARG_SAFE_RE.match(t):
                i += 1
                continue
            flag_name = t.split("=", 1)[0]
            if flag_name not in ALLOWED_FLAGS:
                i += 1
                continue
            safe_tokens.append(t)
            i += 1
        return safe_tokens

    def build_cmd_from_item(one_body: Dict[str, Any]) -> List[str]:
        url = one_body.get("url")
        data = one_body.get("data")
        headers = one_body.get("headers")
        if not url:
            raise ValueError("URL is required.")
        cmd: List[str] = [python_path, sqlmap_path, "-u", str(url), "--batch"]
        if not headers:
            headers = {"User-Agent": "Mozilla/5.0"}
        elif isinstance(headers, dict):
            headers.setdefault("User-Agent", "Mozilla/5.0")
        if (data is None or data == "") and isinstance(headers, dict):
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        if data is not None and data != "":
            if isinstance(data, dict):
                data_str = urlencode(data)
                if isinstance(headers, dict):
                    headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            else:
                data_str = str(data)
            cmd.extend(["--data", data_str])
        hdrs = normalize_headers(headers)
        if hdrs:
            cmd.extend(["--headers", hdrs])
        sqlmap_http_timeout = str(one_body.get("sqlmap_timeout", 10))
        sqlmap_threads = str(one_body.get("threads", 4))
        sqlmap_level = str(one_body.get("level", 1))
        sqlmap_risk = str(one_body.get("risk", 1))
        use_smart = one_body.get("smart", True)
        cmd.extend([
            "--timeout", sqlmap_http_timeout,
            "--threads", sqlmap_threads,
            "--level", sqlmap_level,
            "--risk", sqlmap_risk,
        ])
        if use_smart:
            cmd.append("--smart")
        target_param = one_body.get("param")
        if not target_param and isinstance(data, dict):
            keys = list(data.keys())
            if keys:
                target_param = keys[0]
        if target_param:
            cmd.extend(["-p", str(target_param)])
        cmd.append("--dbs")
        safe_extra = validate_and_split_extra_args(one_body.get("extraArgs"))
        if safe_extra:
            cmd.extend(safe_extra)
        return cmd

    def run_one(one_body: Dict[str, Any]) -> Dict[str, Any]:
        try:
            cmd = build_cmd_from_item(one_body)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                timeout=PROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "sqlmap execution timed out", "command": cmd}
        except FileNotFoundError as e:
            return {"ok": False, "error": f"Executable not found: {e}", "command": cmd}
        except Exception as e:
            return {"ok": False, "error": f"Unexpected error: {e}", "command": cmd}

        ok = completed.returncode == 0
        max_len = 2_000_000
        stdout = (completed.stdout or "")
        stderr = (completed.stderr or "")
        if len(stdout) > max_len:
            stdout = stdout[:max_len] + "\n... [truncated]"
        if len(stderr) > max_len:
            stderr = stderr[:max_len] + "\n... [truncated]"
        chunks = stdout.split("\n") if stdout else []
        log_tags = {"INFO": [], "WARNING": [], "CRITICAL": []}
        if stdout:
            for line in stdout.splitlines():
                if "[INFO]" in line:
                    log_tags["INFO"].append(line)
                if "[WARNING]" in line:
                    log_tags["WARNING"].append(line)
                if "[CRITICAL]" in line:
                    log_tags["CRITICAL"].append(line)
        parameters_structured = extract_parameters_from_stdout(stdout)
        try:
            list_db = extract_databases_from_stdout_v3(stdout)
            list_db_minimal = {"names": list_db["names"], "count": list_db["count"]}
        except Exception:
            list_db_minimal = {"names": [], "count": 0}
        return {
            "ok": ok,
            "exitCode": completed.returncode,
            "command": cmd,
            "stdout": stdout,
            "stderr": stderr,
            "stdoutChunks": chunks,
            "logMatches": log_tags,
            "parametersRaw": parameters_structured,
            "listDb": list_db_minimal,
        }

    # -------------------------
    # Batch support (list body)
    # -------------------------
    if isinstance(body, list):
        create_pdf = False
        qv = request.args.get("createPdf")
        if qv is not None and str(qv).lower() in ("1", "true", "yes", "on"):
            create_pdf = True
        elif body and isinstance(body[0], dict) and body[0].get("createPdf"):
            create_pdf = True

        try:
            requested_max_concurrency = body[0].get("maxConcurrency") if body and isinstance(body[0], dict) else None
            max_concurrency = int(request.args.get("maxConcurrency") or requested_max_concurrency or DEFAULT_MAX_CONCURRENCY)
        except Exception:
            max_concurrency = DEFAULT_MAX_CONCURRENCY
        max_concurrency = max(1, min(len(body), max_concurrency))
        
        results: List[Dict[str, Any]] = []
        all_ok = True
        with ThreadPoolExecutor(max_workers=max_concurrency) as ex:
            future_to_index = {ex.submit(run_one, item): i for i, item in enumerate(body)}
            for fut in as_completed(future_to_index):
                idx = future_to_index[fut]
                try:
                    result = fut.result()
                except Exception as e:
                    result = {"ok": False, "error": f"Exception in worker: {e}"}
                entry = {"index": idx, "url": (body[idx].get("url") if isinstance(body[idx], dict) else None), **result}
                results.append(entry)
                if not result.get("ok", False):
                    all_ok = False
        
        results_sorted = sorted(results, key=lambda x: x["index"])
        response = {"ok": all_ok, "results": results_sorted}
        status_code = 200 if all_ok else 207

        # --- ส่วนจัดการไฟล์และฐานข้อมูล ---
        process = None
        try:
            process = ApiProcess(
                user_id=current_user_id,
                endpoint="/api/run-sqlmap (batch)",
                payload_count=len(body),
                status_ok=all_ok
            )
            db.session.add(process)
            db.session.commit()

            base_reports_dir = os.path.join(current_app.static_folder, 'reports', 'sqlmap_basic')
            
            json_dir = os.path.join(base_reports_dir, 'json')
            os.makedirs(json_dir, exist_ok=True)
            json_filename = f"sqlmap_results_{process.id}_{uuid.uuid4().hex}.json"
            json_filepath = os.path.join(json_dir, json_filename)
            with open(json_filepath, 'w', encoding='utf-8') as f:
                json.dump(results_sorted, f, ensure_ascii=False, indent=4)
            
            process.result_json = os.path.join('reports', 'sqlmap_basic', 'json', json_filename).replace('\\', '/')

            if create_pdf:
                try:
                    pdf_dir = os.path.join(base_reports_dir, 'pdf')
                    pdf_filename = f"sqlmap_report_{process.id}_{uuid.uuid4().hex}.pdf"
                    
                    generate_sqlmap_pdf_report(results_sorted, output_dir=pdf_dir, output_filename=pdf_filename)
                    
                    process.result_pdf = os.path.join('reports', 'sqlmap_basic', 'pdf', pdf_filename).replace('\\', '/')
                    response["reportPdf"] = process.result_pdf
                except Exception as e:
                    current_app.logger.error(f"PDF generation failed for process {process.id}: {e}")
            
            db.session.commit()
            response["processId"] = process.id

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"❌ Error saving process to database: {e}")
            return {"ok": False, "error": "Failed to save scan process to database."}, 500

        return response, status_code

    # -------------------------
    # Single object support
    # -------------------------
    if not isinstance(body, dict):
        return {"ok": False, "error": "Request body must be an object or list"}, 400

    create_pdf_single = False
    qv_single = request.args.get("createPdf")
    if qv_single is not None and str(qv_single).lower() in ("1", "true", "yes", "on"):
        create_pdf_single = True
    elif body.get("createPdf"):
        create_pdf_single = True

    result = run_one(body)
    status = 200 if result.get("ok", False) else 500
    
    # --- ส่วนจัดการไฟล์และฐานข้อมูล (Single) ---
    process = None
    try:
        process = ApiProcess(
            user_id=current_user_id,
            endpoint="/api/run-sqlmap (single)",
            payload_count=1,
            status_ok=result.get("ok", False)
        )
        db.session.add(process)
        db.session.commit()

        base_reports_dir = os.path.join(current_app.static_folder, 'reports', 'sqlmap_basic')
        wrapped_result = [{"index": 0, "url": body.get("url"), **result}]

        json_dir = os.path.join(base_reports_dir, 'json')
        os.makedirs(json_dir, exist_ok=True)
        json_filename = f"sqlmap_results_{process.id}_{uuid.uuid4().hex}.json"
        json_filepath = os.path.join(json_dir, json_filename)
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(wrapped_result, f, ensure_ascii=False, indent=4)
        process.result_json = os.path.join('reports', 'sqlmap_basic', 'json', json_filename).replace('\\', '/')

        if create_pdf_single:
            try:
                pdf_dir = os.path.join(base_reports_dir, 'pdf')
                pdf_filename = f"sqlmap_report_{process.id}_{uuid.uuid4().hex}.pdf"
                
                generate_sqlmap_pdf_report(wrapped_result, output_dir=pdf_dir, output_filename=pdf_filename)
                
                process.result_pdf = os.path.join('reports', 'sqlmap_basic', 'pdf', pdf_filename).replace('\\', '/')
                result["reportPdf"] = process.result_pdf
            except Exception as e:
                current_app.logger.error(f"Single PDF generation failed for process {process.id}: {e}")

        db.session.commit()
        result["processId"] = process.id

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"❌ Error saving single process to database: {e}")
        return {"ok": False, "error": "Failed to save scan process to database."}, 500

    return result, status