# app/routes/network_scanner.py
import asyncio
import aiohttp
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app.utils.decorators import admin_required

bp = Blueprint("network_scanner", __name__, url_prefix="/api/network")

# --- START: ส่วนที่เพิ่มเข้ามาสำหรับ Content Discovery ---

# Wordlist สำหรับเดาชื่อ Path (ในโปรแกรมจริงควรใช้ไฟล์ขนาดใหญ่)
COMMON_PATHS = [
    "admin", "login", "dashboard", "test", "phpinfo.php", "e-learning",
    "backup", "dev", "staging", "api", "v1", "v2", "phpmyadmin", "wordpress", "wp-admin"
]

async def check_path(session, base_url, path):
    """ ตรวจสอบว่า Path ที่กำหนดมีอยู่จริงหรือไม่ """
    url_to_check = f"{base_url}/{path}"
    try:
        # ใช้ aiohttp session ที่ส่งต่อมา
        async with session.get(url_to_check, timeout=2, allow_redirects=False) as response:
            # สถานะ 200 (OK), 301/302 (Redirect), 403 (Forbidden) มักหมายความว่า Path นั้นมีอยู่
            if response.status in [200, 301, 302, 403]:
                return url_to_check
    except asyncio.TimeoutError:
        pass # ถ้า timeout ก็ข้ามไป
    except aiohttp.ClientError:
        pass # ถ้าเกิดข้อผิดพลาดในการเชื่อมต่อ ก็ข้ามไป
    return None

async def discover_content(base_url):
    """ ค้นหา Path ที่มีอยู่จริงจาก Wordlist """
    found = []
    headers = {"User-Agent": "Mozilla/5.0"}
    # สร้าง ClientSession เพียงครั้งเดียวเพื่อประสิทธิภาพ
    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [check_path(session, base_url, path) for path in COMMON_PATHS]
        results = await asyncio.gather(*tasks)
        # คืนค่าเฉพาะผลลัพธ์ที่ไม่ใช่ None
        found = [res for res in results if res]
    return found

# --- END: ส่วนที่เพิ่มเข้ามา ---


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
    except Exception:
        return False

async def scan_host(host):
    """ สแกนหา port และค้นหา content บน host ที่กำหนด (แก้ไขแล้ว) """
    http_task = asyncio.create_task(check_port(host, 80))
    https_task = asyncio.create_task(check_port(host, 443))

    open_protocols = []
    if await http_task:
        open_protocols.append("http")
    if await https_task:
        open_protocols.append("https")
            
    if open_protocols:
        # ถ้ามี port เปิด, ให้สร้างผลลัพธ์พื้นฐานก่อน
        result = {"host": host, "status": "open", "urls": [], "found_paths": []}
        
        # --- START: เรียกใช้ Content Discovery ---
        discovery_tasks = []
        for proto in open_protocols:
            base_url = f"{proto}://{host}"
            result["urls"].append(base_url)
            # เพิ่ม task การค้นหา content เข้าไปใน list
            discovery_tasks.append(discover_content(base_url))

        # รันการค้นหา content ทั้งหมดพร้อมกัน
        if discovery_tasks:
            all_found_paths = await asyncio.gather(*discovery_tasks)
            # รวบรวมผลลัพธ์จากทุก task (http และ https)
            for paths in all_found_paths:
                result["found_paths"].extend(paths)
        # --- END: เรียกใช้ Content Discovery ---
        
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
    data = request.get_json()
    ip_range_str = data.get("ip_range")
    concurrency = int(data.get("concurrency", 100))

    if not ip_range_str:
        return jsonify({"ok": False, "error": "ip_range is required"}), 400

    try:
        target_ips = parse_ip_range(ip_range_str)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "Invalid IP range format. Example: '192.168.1.1-254'"}), 400

    async def run_scan():
        sem = asyncio.Semaphore(concurrency)
        async def bounded_scan(ip):
            async with sem:
                return await scan_host(ip)
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