# app/routes/crawler.py
import asyncio
from urllib.parse import urlparse, urljoin
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import aiohttp
from bs4 import BeautifulSoup
from yarl import URL

bp = Blueprint("crawler", __name__, url_prefix="/api/crawler")


async def _fetch(session, url, timeout=10):
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status == 200 and 'text/html' in (resp.headers.get('Content-Type','')):
                return await resp.text()
            return None
    except Exception:
        return None


async def _crawl_async(start_url, max_pages=500, concurrency=20):
    parsed = urlparse(start_url)
    base_domain = parsed.netloc

    to_visit = asyncio.Queue()
    await to_visit.put(start_url)
    seen = set([start_url])
    results = []

    sem = asyncio.Semaphore(concurrency)
    timeout = aiohttp.ClientTimeout(total=15)
    connector = aiohttp.TCPConnector(limit=concurrency, force_close=True)
    headers = {"User-Agent": "simple-crawler/1.0"}

    async with aiohttp.ClientSession(timeout=timeout, connector=connector, headers=headers) as session:

        async def worker():
            while not to_visit.empty() and len(results) < max_pages:
                url = await to_visit.get()
                async with sem:
                    html = await _fetch(session, url)
                if not html:
                    to_visit.task_done()
                    continue
                results.append(url)
                # parse links
                soup = BeautifulSoup(html, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a.get("href").strip()
                    if href.startswith("mailto:") or href.startswith("javascript:"):
                        continue
                    new = URL(urljoin(url, href)).with_fragment(None)
                    new_str = str(new)
                    p = urlparse(new_str)
                    if p.netloc != base_domain:
                        continue
                    if new_str not in seen:
                        seen.add(new_str)
                        await to_visit.put(new_str)
                to_visit.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
        await to_visit.join()
        for w in workers:
            w.cancel()
        return list(dict.fromkeys(results))


@bp.route("/scan", methods=["POST"])
@jwt_required()  # เอาออกถ้าต้องการ public endpoint
def scan():
    """
    POST JSON:
    {
        "url": "http://localhost/e-learning/",
        "max_pages": 200
    }

    Response JSON:
    {
        "ok": true,
        "url": "...",
        "urls": ["http://localhost/e-learning/", "http://localhost/e-learning/controllers/chkLogin.php", ...]
    }
    """
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    max_pages = int(data.get("max_pages", 500))

    if not url or not urlparse(url).scheme in ("http","https"):
        return jsonify({"ok": False, "msg": "invalid or missing url"}), 400

    # run async crawl
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        urls = loop.run_until_complete(_crawl_async(url, max_pages=max_pages))
        loop.close()
    except Exception as e:
        return jsonify({"ok": False, "msg": "crawl failed", "error": str(e)}), 500

    return jsonify({"ok": True, "url": url, "urls": urls})
