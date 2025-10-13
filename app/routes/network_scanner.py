# app/routes/network_scanner.py
import asyncio
import aiohttp
import os
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from app.utils.decorators import admin_required

bp = Blueprint("network_scanner", __name__, url_prefix="/api/network")

# --- START: ส่วนที่แก้ไข ---

# 1. สร้าง Cache variable ไว้ที่ระดับ Module, เริ่มต้นเป็น None
_WORDLIST_CACHE = None

# 2. กำหนด List สำรองไว้เหมือนเดิม
FALLBACK_PATHS = [
    "admin", "login", "dashboard", "test", "phpinfo.php", "e-learning",
    "backup", "dev", "staging", "api", "phpmyadmin", "wordpress", "wp-admin"
]

def load_wordlist():
    """
    โหลด Wordlist จากไฟล์ ../wordlists/common.txt
    ฟังก์ชันนี้จะถูกเรียกใช้ภายใน request context เท่านั้น จึงปลอดภัย
    """
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        print(base_dir)
        wordlist_path = os.path.join(base_dir, 'wordlists', 'common.txt')
        print(wordlist_path)
        
        if not os.path.exists(wordlist_path):
            raise FileNotFoundError

        with open(wordlist_path, 'r', encoding='utf-8') as f:
            wordlist = [line.strip() for line in f if line.strip()]
            return wordlist if wordlist else FALLBACK_PATHS
            
    except FileNotFoundError:
        # ตอนนี้การเรียก logger ปลอดภัยแล้ว
        current_app.logger.warning("wordlists/common.txt not found. Using internal fallback wordlist.")
        return FALLBACK_PATHS

# --- END: ส่วนที่แก้ไข ---


async def check_path(session, base_url, path):
    """ ตรวจสอบว่า Path ที่กำหนดมีอยู่จริงหรือไม่ """
    url_to_check = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        async with session.get(url_to_check, timeout=2, allow_redirects=False) as response:
            if response.status in [200, 301, 302, 403]:
                return url_to_check
    except (asyncio.TimeoutError, aiohttp.ClientError):
        pass
    return None

async def discover_content(base_url, wordlist):
    """ ค้นหา Path ที่มีอยู่จริงจาก Wordlist ที่ส่งเข้ามา """
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [check_path(session, base_url, path) for path in wordlist]
        results = await asyncio.gather(*tasks)
        return [res for res in results if res]

async def check_port(host, port, timeout=0.5):
    """ ตรวจสอบว่า port เปิดอยู่หรือไม่ """
    try:
        conn = asyncio.open_connection(host, port)
        _, writer = await asyncio.wait_for(conn, timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False

async def scan_host(host, wordlist):
    """ สแกนหา port และค้นหา content บน host ที่กำหนด """
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
            # ส่ง wordlist ที่โหลดมาแล้วเข้าไปใน task
            discovery_tasks.append(discover_content(base_url, wordlist))

        if discovery_tasks:
            all_found_paths = await asyncio.gather(*discovery_tasks)
            for paths in all_found_paths:
                result["found_paths"].extend(paths)
        
        return result
        
    return None

def parse_ip_range(ip_range_str: str):
    """ แปลง string '127.0.0.1-10' เป็น list ของ IP """
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
    """ รับช่วง IP และสแกนหา Web Server พร้อมทั้งค้นหา Content """
    global _WORDLIST_CACHE # บอก Python ว่าเราจะแก้ไขตัวแปร global

    # --- START: ส่วนที่แก้ไข ---
    # 3. ตรวจสอบ Cache: ถ้ายังว่างอยู่ (เป็น None) ให้เรียก load_wordlist()
    #    ขั้นตอนนี้จะเกิดขึ้นแค่ครั้งแรกที่ API ถูกเรียกเท่านั้น
    if _WORDLIST_CACHE is None:
        _WORDLIST_CACHE = load_wordlist()
    # --- END: ส่วนที่แก้ไข ---

    data = request.get_json()
    ip_range_str = data.get("ip_range")
    concurrency = int(data.get("concurrency", 150))

    if not ip_range_str:
        return jsonify({"ok": False, "error": "ip_range is required"}), 400

    try:
        target_ips = parse_ip_range(ip_range_str)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    
    async def run_scan():
        sem = asyncio.Semaphore(concurrency)
        async def bounded_scan(ip):
            async with sem:
                # 4. ส่ง wordlist ที่อยู่ใน cache ไปให้ scan_host ใช้
                return await scan_host(ip, _WORDLIST_CACHE)
        tasks = [bounded_scan(ip) for ip in target_ips]
        results = await asyncio.gather(*tasks)
        return [res for res in results if res]

    found_hosts = asyncio.run(run_scan())

    return jsonify({
        "ok": True,
        "ip_range": ip_range_str,
        "found_hosts": found_hosts,
        "count": len(found_hosts)
    })