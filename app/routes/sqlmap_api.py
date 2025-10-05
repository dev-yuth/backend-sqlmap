# app/routes/sqlmap_api.py
import os
import json
import shlex
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import datetime

from flask import Blueprint, request, current_app

from app.config import get_python_path, get_sqlmap_path

# --- PDF (reportlab) ---
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily  # เพิ่มบรรทัดนี้
from reportlab.lib.units import cm

from flask_jwt_extended import jwt_required
from flask import Blueprint, request, current_app, send_from_directory, url_for, abort


bp = Blueprint("sqlmap_api", __name__)

# --- regex / helpers (same as original) ---
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

# --- PDF utilities ---
THAI_FONT_NAME = "Sarabun"

# หา path ของโฟลเดอร์ app/fonts
project_app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
font_dir = os.path.join(project_app_dir, "fonts")

# กำหนดไฟล์ฟอนต์ทั้ง 4 แบบ
font_files = {
    'regular': 'Sarabun-Regular.ttf',
    'bold': 'Sarabun-Bold.ttf',
    'italic': 'Sarabun-Italic.ttf',
    'bolditalic': 'Sarabun-BoldItalic.ttf'
}

try:
    # ตรวจสอบว่าโฟลเดอร์ fonts มีอยู่หรือไม่
    if not os.path.exists(font_dir):
        raise FileNotFoundError(f"Font directory not found: {font_dir}")
    
    # ลงทะเบียนฟอนต์ทั้ง 4 แบบ
    registered_fonts = {}
    for variant, filename in font_files.items():
        font_path = os.path.join(font_dir, filename)
        if not os.path.exists(font_path):
            print(f"Warning: {filename} not found at {font_path}")
            continue
        
        font_name = f"{THAI_FONT_NAME}-{variant}" if variant != 'regular' else THAI_FONT_NAME
        pdfmetrics.registerFont(TTFont(font_name, font_path))
        registered_fonts[variant] = font_name
        print(f"Registered: {font_name} from {filename}")
    
    # ตรวจสอบว่ามีฟอนต์ regular อย่างน้อย
    if 'regular' not in registered_fonts:
        raise FileNotFoundError("Sarabun-Regular.ttf is required but not found")
    
    # ลงทะเบียน font family
    registerFontFamily(
        THAI_FONT_NAME,
        normal=registered_fonts.get('regular', THAI_FONT_NAME),
        bold=registered_fonts.get('bold', registered_fonts['regular']),
        italic=registered_fonts.get('italic', registered_fonts['regular']),
        boldItalic=registered_fonts.get('bolditalic', registered_fonts['regular'])
    )
    
    print(f"Registered Sarabun font family successfully")
    
except Exception as e:
    print(f"Error: Thai font registration failed: {e}")
    raise

def thai_datetime_str():
    months = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
              'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
    d = datetime.datetime.now()
    return f"{d.day:02d} {months[d.month-1]} {d.year+543} เวลา {d.hour:02d}:{d.minute:02d} น."

def generate_pdf_report(results: List[Dict[str, Any]]) -> str:
    """
    Generate a PDF report from results list.
    Returns absolute path to generated PDF file.
    """
    output_dir = os.path.join(os.getcwd(), "app", "files")
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(output_dir, f"sqlmap_report_{int(datetime.datetime.now().timestamp())}.pdf")

    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    # Override default fonts if THAI font loaded
    for key in styles.byName:
        try:
            styles[key].fontName = THAI_FONT_NAME
        except Exception:
            pass

    story = []

    # Header
    story.append(Paragraph("รายงานผลการสแกน SQLMap", styles["Title"]))
    story.append(Paragraph(f"จัดทำเมื่อ: {thai_datetime_str()}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # Summary
    total_items = len(results)
    total_db_names = sum(len(r.get("listDb", {}).get("names", [])) for r in results)
    story.append(Paragraph(f"สรุปผล: จำนวนรายการ {total_items} | จำนวนฐานข้อมูลรวม {total_db_names}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # Details per URL
    for idx, r in enumerate(results, 1):
        story.append(Paragraph(f"รายการที่ {idx}: {r.get('url','')}", styles["Heading2"]))
        story.append(Paragraph(f"สถานะ: {'OK' if r.get('ok') else 'FAILED'}", styles["Normal"]))
        story.append(Spacer(1, 6))

        # Databases
        list_db = r.get("listDb", {})
        db_names = list_db.get("names", [])
        db_count = list_db.get("count", 0)

        story.append(Paragraph(f"ฐานข้อมูลที่พบ ({db_count}):", styles["Heading3"]))
        if db_names:
            data = [["#", "Database Name"]] + [[str(i+1), name] for i, name in enumerate(db_names)]
            table = Table(data, colWidths=[1.2*cm, 14*cm])
            table.setStyle(TableStyle([
                ("GRID", (0,0), (-1,-1), 0.5, colors.black),
                ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
                ("FONTNAME", (0,0), (-1,-1), THAI_FONT_NAME),
                ("FONTSIZE", (0,0), (-1,-1), 10),
            ]))
            story.append(table)
        else:
            story.append(Paragraph("ไม่พบฐานข้อมูล", styles["Normal"]))
        story.append(Spacer(1, 6))

        # Parameters
        params = r.get("parametersRaw", [])
        story.append(Paragraph("รายละเอียดพารามิเตอร์:", styles["Heading3"]))
        if params:
            for p in params:
                story.append(Paragraph(f"Parameter: {p.get('parameter')} (Location: {p.get('location')})", styles["Normal"]))
                for f in p.get("findings", []):
                    story.append(Paragraph(f"- Type: {f.get('type','')}", styles["Normal"]))
                    story.append(Paragraph(f"  Title: {f.get('title','')}", styles["Normal"]))
                    story.append(Paragraph(f"  Payload: {f.get('payload','')}", styles["Normal"]))
                story.append(Spacer(1, 6))
        else:
            story.append(Paragraph("ไม่พบพารามิเตอร์ที่มีช่องโหว่", styles["Normal"]))

        story.append(PageBreak())

    doc.build(story)
    return pdf_path

@bp.route("/health", methods=["GET"])
def health():
    return {"ok": True, "service": "sqlmap-api", "version": 1}, 200

@bp.route("/api/run-sqlmap", methods=["POST"])
@jwt_required(locations=["cookies"])  # ✅ เพิ่ม locations=["cookies"]
def run_sqlmap():
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
        # Determine createPdf flag: prefer explicit query param, else first item flag, else False
        create_pdf = False
        qv = request.args.get("createPdf")
        if qv is not None and str(qv).lower() in ("1", "true", "yes", "on"):
            create_pdf = True
        elif body and isinstance(body[0], dict) and body[0].get("createPdf"):
            create_pdf = True

        requested_max_concurrency = body[0].get("maxConcurrency") if body and isinstance(body[0], dict) else None
        try:
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

        if create_pdf:
            try:
                # generate PDF from results_sorted
                pdf_path = generate_pdf_report(results_sorted)
                # return filesystem path to PDF (as in sqlmap_urls.py). Optionally you can convert to URL here.
                response["reportPdf"] = pdf_path
            except Exception as e:
                return {"ok": False, "error": f"Report generation failed: {e}"}, 500

        return response, status_code

    # -------------------------
    # Single object support
    # -------------------------
    if not isinstance(body, dict):
        return {"ok": False, "error": "Request body must be an object or list"}, 400

    # Check if single-request asks for PDF
    create_pdf_single = False
    qv_single = request.args.get("createPdf")
    if qv_single is not None and str(qv_single).lower() in ("1", "true", "yes", "on"):
        create_pdf_single = True
    elif body.get("createPdf"):
        create_pdf_single = True

    result = run_one(body)
    status = 200 if result.get("ok", False) else 500

    # If PDF requested for single item, wrap into list and generate
    if create_pdf_single:
        try:
            wrapped = [{"index": 0, "url": body.get("url"), **result}]
            pdf_path = generate_pdf_report(wrapped)
            result["reportPdf"] = pdf_path
        except Exception as e:
            return {"ok": False, "error": f"Report generation failed: {e}"}, 500
            

    return result, status
