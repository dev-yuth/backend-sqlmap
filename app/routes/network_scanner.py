# app/routes/network_scanner.py
import asyncio
import aiohttp
import os
import re
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from app.utils.decorators import admin_required

bp = Blueprint("network_scanner", __name__, url_prefix="/api/network")

_WORDLIST_CACHE = None

FALLBACK_PATHS = [
    "admin", "login", "dashboard", "test", "phpinfo.php", "e-learning",
    "backup", "dev", "staging", "api", "phpmyadmin", "wordpress", "wp-admin"
]

def load_wordlist():
    """
    Loads wordlist from ../wordlists/common.txt, falling back to an internal list if not found.
    This is called only once within the application context.
    """
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
    """Checks if a given path exists on a base URL using the shared session."""
    url_to_check = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        # The session is passed in, not created here.
        async with session.get(url_to_check, timeout=2, allow_redirects=False) as response:
            if response.status in [200, 301, 302, 403]:
                return url_to_check
    except (asyncio.TimeoutError, aiohttp.ClientError):
        pass # Ignore timeouts and connection errors
    return None

async def discover_content(session, base_url, wordlist):
    """Discovers content using the shared aiohttp session."""
    # This function no longer creates its own session.
    tasks = [check_path(session, base_url, path) for path in wordlist]
    results = await asyncio.gather(*tasks)
    return [res for res in results if res]

async def check_port(host, port, timeout=0.5):
    """Checks if a TCP port is open."""
    try:
        conn = asyncio.open_connection(host, port)
        _, writer = await asyncio.wait_for(conn, timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False

async def scan_host(session, host, wordlist):
    """
    Scans a single host for open ports and discovers content using the shared session.
    """
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
            # Pass the shared session down to the discovery task
            discovery_tasks.append(discover_content(session, base_url, wordlist))

        if discovery_tasks:
            all_found_paths = await asyncio.gather(*discovery_tasks)
            for paths in all_found_paths:
                result["found_paths"].extend(paths)
        
        return result
        
    return None

def parse_ip_range(ip_range_str: str):
    """Parses an IP range string like '192.168.1.1-254' into a list of IPs."""
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
@jwt_required(locations=["cookies"])
@admin_required
def scan_range():
    """API endpoint to scan an IP range."""
    global _WORDLIST_CACHE 

    if _WORDLIST_CACHE is None:
        _WORDLIST_CACHE = load_wordlist()

    data = request.get_json()
    ip_range_str = data.get("ip_range")
    concurrency = int(data.get("concurrency", 150))

    if not ip_range_str:
        return jsonify({"ok": False, "error": "ip_range is required"}), 400

    try:
        target_ips = parse_ip_range(ip_range_str)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    
    # --- START: Major Change - Centralized Session Management ---
    async def run_scan():
        # Define connection limits to prevent resource exhaustion.
        # This is the key fix for WinError 10055.
        conn = aiohttp.TCPConnector(limit_per_host=20, limit=100)
        headers = {"User-Agent": "Mozilla/5.0"}

        # Create ONE session that will be shared by all tasks.
        async with aiohttp.ClientSession(connector=conn, headers=headers) as session:
            sem = asyncio.Semaphore(concurrency)
            
            async def bounded_scan(ip):
                async with sem:
                    # Pass the shared session into the scan_host function.
                    return await scan_host(session, ip, _WORDLIST_CACHE)
            
            tasks = [bounded_scan(ip) for ip in target_ips]
            results = await asyncio.gather(*tasks)
            return [res for res in results if res]
    # --- END: Major Change ---

    found_hosts = asyncio.run(run_scan())

    return jsonify({
        "ok": True,
        "ip_range": ip_range_str,
        "found_hosts": found_hosts,
        "count": len(found_hosts)
    })