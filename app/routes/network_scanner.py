# app/routes/network_scanner.py
import asyncio
import aiohttp
import os
import re
import json
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
# --- CHANGE HERE: Import get_jwt_identity instead of get_current_user ---
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.decorators import admin_required
from app.extensions import db
from app.models.network_scan import NetworkScan

bp = Blueprint("network_scanner", __name__, url_prefix="/api/network")

_WORDLIST_CACHE = None

FALLBACK_PATHS = [
    "admin", "login", "dashboard", "test", "phpinfo.php", "e-learning",
    "backup", "dev", "staging", "api", "phpmyadmin", "wordpress", "wp-admin"
]

# ... (โค้ดส่วนอื่นๆ ตั้งแต่ load_wordlist จนถึง parse_ip_range ยังคงเหมือนเดิม) ...

def load_wordlist():
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        wordlist_path = os.path.join(base_dir, 'wordlists', 'common.txt')
        
        if not os.path.exists(wordlist_path):
            raise FileNotFoundError

        with open(wordlist_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f]
            wordlist = [line for line in lines if line and not re.search(r'\s', line) and not line.startswith('#')]
            return wordlist if wordlist else FALLBACK_PATHS
            
    except FileNotFoundError:
        current_app.logger.warning("wordlists/common.txt not found. Using internal fallback wordlist.")
        return FALLBACK_PATHS

async def check_path(session, base_url, path):
    url_to_check = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        async with session.get(url_to_check, timeout=2, allow_redirects=False) as response:
            if response.status in [200, 301, 302, 403]:
                return url_to_check
    except (asyncio.TimeoutError, aiohttp.ClientError):
        pass
    return None

async def discover_content(session, base_url, wordlist):
    tasks = [check_path(session, base_url, path) for path in wordlist]
    results = await asyncio.gather(*tasks)
    return [res for res in results if res]

async def check_port(host, port, timeout=0.5):
    try:
        conn = asyncio.open_connection(host, port)
        _, writer = await asyncio.wait_for(conn, timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False

async def scan_host(session, host, wordlist):
    http_task = asyncio.create_task(check_port(host, 80))
    https_task = asyncio.create_task(check_port(host, 443))

    open_protocols = []
    if await http_task: open_protocols.append("http")
    if await https_task: open_protocols.append("https")
            
    if open_protocols:
        result = {"host": host, "status": "open", "urls": [], "found_paths": []}
        discovery_tasks = []
        for proto in open_protocols:
            base_url = f"{proto}://{host}"
            result["urls"].append(base_url)
            discovery_tasks.append(discover_content(session, base_url, wordlist))

        if discovery_tasks:
            all_found_paths = await asyncio.gather(*discovery_tasks)
            for paths in all_found_paths:
                result["found_paths"].extend(paths)
        return result
    return None

def parse_ip_range(ip_range_str: str):
    if '-' not in ip_range_str:
        return [ip_range_str.strip()]
    parts = ip_range_str.split('-')
    base_ip_str = '.'.join(parts[0].split('.')[:-1])
    try:
        start_ip_last_octet = int(parts[0].split('.')[-1])
        end_ip_last_octet = int(parts[1])
    except (ValueError, IndexError):
        raise ValueError("Invalid IP range format")
    if not (0 <= start_ip_last_octet <= 255 and 0 <= end_ip_last_octet <= 255 and start_ip_last_octet <= end_ip_last_octet):
        raise ValueError("Invalid IP range format")
    return [f"{base_ip_str}.{i}" for i in range(start_ip_last_octet, end_ip_last_octet + 1)]


@bp.route("/scan-range", methods=["POST"])
@jwt_required(locations=["cookies", "headers"])
@admin_required
def scan_range():
    """API endpoint to scan an IP range and save the process."""
    global _WORDLIST_CACHE
    if _WORDLIST_CACHE is None:
        _WORDLIST_CACHE = load_wordlist()

    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "error": "Invalid JSON payload"}), 400

    ip_range_str = data.get("ip_range")
    concurrency = int(data.get("concurrency", 150))
    
    # --- CHANGE HERE: Get user ID directly from the token's identity ---
    current_user_id = get_jwt_identity()

    if not ip_range_str:
        return jsonify({"ok": False, "error": "ip_range is required"}), 400

    try:
        target_ips = parse_ip_range(ip_range_str)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    new_scan = NetworkScan(
        # --- CHANGE HERE: Use the ID we got from the identity ---
        user_id=current_user_id,
        ip_range=ip_range_str,
        concurrency=concurrency,
        status='running'
    )
    db.session.add(new_scan)
    db.session.commit()

    async def run_scan():
        conn = aiohttp.TCPConnector(limit_per_host=20, limit=100)
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(connector=conn, headers=headers) as session:
            sem = asyncio.Semaphore(concurrency)
            async def bounded_scan(ip):
                async with sem:
                    return await scan_host(session, ip, _WORDLIST_CACHE)
            tasks = [bounded_scan(ip) for ip in target_ips]
            results = await asyncio.gather(*tasks)
            return [res for res in results if res]

    try:
        found_hosts = asyncio.run(run_scan())
        
        reports_dir = os.path.join(current_app.static_folder, 'reports', 'network_scans')
        os.makedirs(reports_dir, exist_ok=True)
        result_filename = f"network_scan_{new_scan.id}_{uuid.uuid4().hex}.json"
        result_filepath = os.path.join(reports_dir, result_filename)

        scan_data = {
            "scan_id": new_scan.id,
            "ip_range": ip_range_str,
            "found_hosts": found_hosts,
            "count": len(found_hosts)
        }
        with open(result_filepath, 'w', encoding='utf-8') as f:
            json.dump(scan_data, f, ensure_ascii=False, indent=4)
        
        new_scan.status = 'completed'
        new_scan.found_hosts_count = len(found_hosts)
        new_scan.result_json_path = os.path.join('reports', 'network_scans', result_filename).replace('\\', '/')
        new_scan.completed_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            "ok": True,
            "found_hosts": found_hosts,
            "count": len(found_hosts),
            "scan_id": new_scan.id,
            "message": "Scan completed successfully."
        })

    except Exception as e:
        db.session.rollback() # Rollback transaction on error
        new_scan.status = 'error'
        new_scan.completed_at = datetime.utcnow()
        db.session.add(new_scan)
        db.session.commit()
        current_app.logger.error(f"Error during network scan for id {new_scan.id}: {e}")
        return jsonify({"ok": False, "error": "An internal error occurred during the scan."}), 500