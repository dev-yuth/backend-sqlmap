import os
import json
from pyclbr import Class
import shlex
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, request
from flask_restful import Api, Resource
from flask_cors import CORS
import subprocess
import math
from flask import Flask, request, send_from_directory  # ensure send_from_directory is imported
import os, re

from config import get_python_path, get_sqlmap_path, get_allowed_origins

app = Flask(__name__)
api = Api(app)
CORS(app, resources={r"*": {"origins": list(get_allowed_origins()) or ["*"]}})

BLOCK_RE = re.compile(r"---\n(Parameter:.*?)\n---", flags=re.DOTALL | re.IGNORECASE)
PARAM_LINE_RE = re.compile(r"Parameter:\s*(?P<name>[\w\-\._]+)\s*(?:\((?P<loc>[^)]+)\))?", flags=re.IGNORECASE)



# --- add these regexes near top of file with other regex defs ---
RESUMED_RE = re.compile(r"resumed:\s*'?(?P<val>[^']+)'?", flags=re.IGNORECASE)
FETCH_START_RE = re.compile(r"fetching (database names|number of databases)", flags=re.IGNORECASE)
FETCH_END_RE = re.compile(r"fetched data logged to text files under", flags=re.IGNORECASE)

# --- add this helper function (place it near other helpers) ---
def extract_databases_from_stdout_v3(stdout: str):
    if not stdout:
        return {"names": [], "count": 0, "rawMatches": []}

    lines = stdout.splitlines()
    names = []
    raw_matches = []

    # try explicit "available databases [N]" first
    count = None
    count_m = re.search(r"available databases\s*\[(\d+)\]", stdout, flags=re.IGNORECASE)
    if count_m:
        try:
            count = int(count_m.group(1))
        except:
            count = None

    # stricter pattern: match lines like "[*] `db_name`" or "[*] db_name"
    # allow only common DB name characters (alnum, underscore, hyphen, dot)
    list_item_re = re.compile(r"^\s*\[\*\]\s*`?([A-Za-z0-9_\-\.]+)`?\s*$")
    for ln in lines:
        m = list_item_re.match(ln)
        if m:
            name = m.group(1).strip()
            raw_matches.append(name)
            if name not in names:
                names.append(name)

    # fallback: look for "resumed: <val>" lines (ignore pure numbers)
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


# --- parsing helpers (unchanged) ---
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

    return {
        "parameter": name,
        "location": loc,
        "raw": raw_block.strip(),
        "findings": findings,
    }

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

# --- security: allowed flags for extraArgs (whitelist) ---
ALLOWED_FLAGS = {
    "--level", "--risk", "--threads", "--timeout", "--timeout", "--technique",
    "--smart", "-p", "--dbs", "--batch", "--skip", "--start"
}
# regex to validate single token pattern (basic)
EXTRA_ARG_SAFE_RE = re.compile(r"^[-]{1,2}[A-Za-z0-9\-\._/]+=?.*$")

class Health(Resource):
    def get(self):
        return {"ok": True, "service": "sqlmap-api", "version": 1}, 200

class RunSqlmap(Resource):
    def post(self):
        try:
            body = request.get_json(force=True, silent=False) or {}
        except Exception as e:
            return {"ok": False, "error": f"Invalid JSON body: {e}"}, 400

        python_path = get_python_path()
        sqlmap_path = get_sqlmap_path()

        # default concurrency for batch runs (can be overridden by request: maxConcurrency)
        try:
            DEFAULT_MAX_CONCURRENCY = int(os.getenv("SQLMAP_MAX_CONCURRENCY", "3"))
        except ValueError:
            DEFAULT_MAX_CONCURRENCY = 3

        # process-level timeout (seconds) for subprocess.run
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
                # only flags allowed here (no bare values). support `--flag=val` or `--flag` style
                if not t.startswith("-"):
                    i += 1
                    continue
                # basic allowed pattern
                if not EXTRA_ARG_SAFE_RE.match(t):
                    i += 1
                    continue
                # whitelist check: extract flag name (before '=' if present)
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
            headers = one_body.get("headers")  # allow client to provide headers per-item
            if not url:
                raise ValueError("URL is required.")

            cmd: List[str] = [python_path, sqlmap_path, "-u", str(url), "--batch"]

            # sensible defaults for headers
            if not headers:
                headers = {"User-Agent": "Mozilla/5.0"}
            elif isinstance(headers, dict):
                headers.setdefault("User-Agent", "Mozilla/5.0")

            # If no data provided and headers is dict, ensure content-type default for consistency
            if (data is None or data == "") and isinstance(headers, dict):
                headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

            # data handling
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

            # default "fast" options (can be overridden by extraArgs)
            # per-request sqlmap http timeout (smaller => faster but may miss slow responses)
            sqlmap_http_timeout = str(one_body.get("sqlmap_timeout", 10))  # seconds
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

            # If param given explicitly, use it (-p)
            target_param = one_body.get("param")
            if not target_param and isinstance(data, dict):
                keys = list(data.keys())
                if keys:
                    target_param = keys[0]
            if target_param:
                cmd.extend(["-p", str(target_param)])

            # Always request dbs by default (but can be overridden/left)
            cmd.append("--dbs")

            # Merge extraArgs but only safe ones (whitelist)
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
                        # new: try extract database list/count
            try:
                list_db = extract_databases_from_stdout_v3(stdout)
                # only expose names (without rawMatches) if you prefer minimal output:
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

        # --- Batch support with concurrency ---
        if isinstance(body, list):
            # optional override of concurrency per-request
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

            # keep results in original order
            results_sorted = sorted(results, key=lambda x: x["index"])
            return {"ok": all_ok, "results": results_sorted}, 200 if all_ok else 207

        # single object
        if not isinstance(body, dict):
            return {"ok": False, "error": "Request body must be an object or list"}, 400

        result = run_one(body)
        status = 200 if result.get("ok", False) else 500
        return result, status


class UploadReport(Resource):   
    def post(self):
        try:
            filename = request.args.get("filename") or request.headers.get("X-Filename") or "report.pdf"
            safe_name = re.sub(r"[^A-Za-z0-9_\-\.]+", "_", filename)
            if not safe_name.lower().endswith(".pdf"):
                safe_name += ".pdf"

            base_dir = os.path.join(os.path.dirname(__file__), "files")
            os.makedirs(base_dir, exist_ok=True)
            out_path = os.path.join(base_dir, safe_name)

            # print(f"[upload-report] saved {safe_name} -> {out_path}")
            raw = request.get_data() or b""
            with open(out_path, "wb") as f:
                f.write(raw)

            return {"ok": True, "path": out_path.replace("\\", "/"), "filename": safe_name}
        except Exception as e:
            return {"ok": False, "error": str(e)}, 500


api.add_resource(Health, "/health")
api.add_resource(RunSqlmap, "/api/run-sqlmap")
api.add_resource(UploadReport, "/api/upload-report")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    py_path = get_python_path()
    sm_path = get_sqlmap_path()
    print(f"[startup] Using PYTHON_PATH={py_path} (exists={os.path.exists(py_path)})")
    print(f"[startup] Using SQLMAP_PATH={sm_path} (exists={os.path.exists(sm_path)})")
    app.run(host="0.0.0.0", port=port, debug=True)
