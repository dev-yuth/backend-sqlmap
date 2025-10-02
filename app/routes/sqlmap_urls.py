# app/routes/sqlmap_urls.py
import os
import json
import shlex
import re
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import datetime

from flask import Blueprint, request

from app.config import get_python_path, get_sqlmap_path

# --- PDF ---
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import cm


from flask_jwt_extended import jwt_required

bp = Blueprint("sqlmap_urls", __name__)

# --- regex / parsing helpers (kept functional) ---
BLOCK_RE = re.compile(r"---\n(Parameter:.*?)\n---", flags=re.DOTALL | re.IGNORECASE)
PARAM_LINE_RE = re.compile(r"Parameter:\s*(?P<name>[\w\-\._]+)\s*(?:\((?P<loc>[^)]+)\))?", flags=re.IGNORECASE)

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

# --- small utility helpers ---
def _safe_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default

EXTRA_ARG_SAFE_RE = re.compile(r"^[-]{1,2}[A-Za-z0-9\-\._/]+=?.*$")
ALLOWED_FLAGS = {
    "--level", "--risk", "--threads", "--timeout", "--technique",
    "--smart", "-p", "--dbs", "--batch", "--skip", "--start", "--passwords", "--password"
}

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

# --- command builder and runner ---
def _build_cmd(python_path: str, sqlmap_path: str, url: str, options: Dict[str, Any]) -> List[str]:
    cmd: List[str] = [python_path, sqlmap_path, "-u", str(url), "--batch", "--dbs"]
    sqlmap_http_timeout = str(_safe_int(options.get("timeout"), 10))
    sqlmap_threads = str(_safe_int(options.get("threads"), 10))
    sqlmap_level = str(_safe_int(options.get("level"), 1))
    sqlmap_risk = str(_safe_int(options.get("risk"), 1))
    use_smart = options.get("smart", True)

    cmd.extend([
        "--timeout", sqlmap_http_timeout,
        "--threads", sqlmap_threads,
        "--level", sqlmap_level,
        "--risk", sqlmap_risk,
    ])
    if use_smart:
        cmd.append("--smart")

    safe_extra = validate_and_split_extra_args(options.get("extraArgs"))
    if safe_extra:
        cmd.extend(safe_extra)

    return cmd

def _run_cmd(cmd: List[str], timeout_seconds: int) -> Dict[str, Any]:
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=timeout_seconds,
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

# --- Register Thai font ---
THAI_FONT_NAME = "THSarabunNew"
try:
    pdfmetrics.registerFont(TTFont(THAI_FONT_NAME, "THSarabunNew.ttf"))
except Exception as e:
    print(f"Warning: Thai font registration failed: {e}")

def thai_datetime_str():
    months = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
              'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
    d = datetime.datetime.now()
    return f"{d.day:02d} {months[d.month-1]} {d.year+543} เวลา {d.hour:02d}:{d.minute:02d} น."

def generate_pdf_report(results: List[Dict[str, Any]]) -> str:
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, PageBreak, SimpleDocTemplate
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    import os, datetime

    output_dir = os.path.join(os.getcwd(), "app", "files")
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(output_dir, f"sqlmap_report_{int(datetime.datetime.now().timestamp())}.pdf")

    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    # Override default fonts
    for key in styles.byName:
        styles[key].fontName = THAI_FONT_NAME

    story = []

    # --- Header ---
    story.append(Paragraph("รายงานผลการสแกน SQLMap", styles["Title"]))
    story.append(Paragraph(f"จัดทำเมื่อ: {thai_datetime_str()}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # --- Summary ---
    total_items = len(results)
    total_db_names = sum(len(r.get("listDb", {}).get("names", [])) for r in results)
    story.append(Paragraph(f"สรุปผล: จำนวนรายการ {total_items} | จำนวนฐานข้อมูลรวม {total_db_names}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # --- Details per URL ---
    for idx, r in enumerate(results, 1):
        story.append(Paragraph(f"รายการที่ {idx}: {r.get('url','')}", styles["Heading2"]))
        story.append(Paragraph(f"สถานะ: {'OK' if r.get('ok') else 'FAILED'}", styles["Normal"]))
        story.append(Spacer(1, 6))

        # --- Databases ---
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

        # --- Parameters ---
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

# --- endpoint: POST /api/run-sqlmap-urls ---
@bp.route("/api/run-sqlmap-urls", methods=["POST"])
@jwt_required()
def run_sqlmap_urls_post():
    python_path = get_python_path()
    sqlmap_path = get_sqlmap_path()

    DEFAULT_MAX_CONCURRENCY = _safe_int(os.getenv("SQLMAP_MAX_CONCURRENCY"), 3)
    PROCESS_TIMEOUT = _safe_int(os.getenv("SQLMAP_PROCESS_TIMEOUT"), 300)
    default_timeout = _safe_int(os.getenv("SQLMAP_DEFAULT_TIMEOUT"), 15)
    default_threads = _safe_int(os.getenv("SQLMAP_DEFAULT_THREADS"), 5)
    default_level = _safe_int(os.getenv("SQLMAP_DEFAULT_LEVEL"), 2)
    default_risk = _safe_int(os.getenv("SQLMAP_DEFAULT_RISK"), 1)
    smart_env = os.getenv("SQLMAP_DEFAULT_SMART", "1").lower()
    default_smart = smart_env in ("1", "true", "yes", "on")

    env_extra = os.getenv("SQLMAP_EXTRA_ARGS", "").strip()
    combined_extra = env_extra.split() if env_extra else []
    if "--passwords" not in combined_extra:
        combined_extra.append("--passwords")
    combined_extra_str = " ".join(combined_extra) if combined_extra else None

    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception as e:
        return {"ok": False, "error": f"Invalid JSON body: {e}"}, 400

    raw_urls = body.get("cleaned_urls") or []
    if not isinstance(raw_urls, list) or not raw_urls:
        return {"ok": False, "error": "Missing or invalid 'cleaned_urls' (must be non-empty list)."}, 400

    create_pdf = body.get("createPdf", False)  # <--- new flag, default False

    try:
        requested = body.get("maxConcurrency")
        max_concurrency = int(requested) if requested is not None else DEFAULT_MAX_CONCURRENCY
    except Exception:
        max_concurrency = DEFAULT_MAX_CONCURRENCY
    max_concurrency = max(1, min(len(raw_urls), max_concurrency))

    options = {
        "timeout": default_timeout,
        "threads": default_threads,
        "level": default_level,
        "risk": default_risk,
        "smart": default_smart,
        "extraArgs": combined_extra_str,
    }

    results: List[Dict[str, Any]] = []
    all_ok = True

    with ThreadPoolExecutor(max_workers=max_concurrency) as ex:
        future_to_index = {}
        for i, url in enumerate(raw_urls):
            u = str(url).strip()
            if not u:
                results.append({"index": i, "url": url, "ok": False, "error": "invalid url"})
                all_ok = False
                continue
            cmd = _build_cmd(python_path, sqlmap_path, u, options)
            fut = ex.submit(_run_cmd, cmd, PROCESS_TIMEOUT)
            future_to_index[fut] = (i, u)

        for fut in as_completed(future_to_index):
            idx, url = future_to_index[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"ok": False, "error": f"worker exception: {e}"}
            entry = {"index": idx, "url": url, **res}
            results.append(entry)
            if not res.get("ok", False):
                all_ok = False

    results_sorted = sorted(results, key=lambda x: x["index"])
    status_code = 200 if all_ok else 207

    report_pdf_path = None
    if create_pdf:  # <--- only generate PDF if flag is True
        try:
            report_pdf_path = generate_pdf_report(results_sorted)
        except Exception as e:
            return {"ok": False, "error": f"Report generation failed: {e}"}, 500

    response = {
        "ok": all_ok,
        "count": len(raw_urls),
        "results": results_sorted,
    }
    if report_pdf_path:
        response["reportPdf"] = report_pdf_path

    return response, status_code
