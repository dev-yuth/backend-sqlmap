# app/routes/crawler.py
import asyncio
from urllib.parse import urlparse, urljoin, parse_qsl, urlencode, urlunparse
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import aiohttp
from bs4 import BeautifulSoup
from yarl import URL
import os
from dotenv import load_dotenv
import re

# for dedupe / similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()  # โหลดตัวแปรจาก .env

# อ่านค่า default

DEFAULT_DEDUPE_THRESHOLD = float(os.getenv("CRAWLER_DEDUPE_THRESHOLD", 0.85))
DEFAULT_MAX_PAGES = int(os.getenv("CRAWLER_MAX_PAGES", 500))
DEFAULT_CONCURRENCY = int(os.getenv("CRAWLER_CONCURRENCY", 20))

bp = Blueprint("crawler", __name__, url_prefix="/api/crawler")

# tracking params to drop when normalizing
TRACKING_PARAMS_RE = re.compile(r'^(utm_|fbclid$|gclid$|sessionid$|phpsessid$)', re.IGNORECASE)

# -------------------------
# Async crawler
# -------------------------
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

# -------------------------
# URL normalization / dedupe
# -------------------------
def normalize_url(u: str) -> str:
    try:
        p = urlparse(u)
    except Exception:
        return u

    scheme = p.scheme.lower()
    netloc = p.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = p.path or "/"
    q = parse_qsl(p.query, keep_blank_values=True)
    q_filtered = [(k, v) for (k, v) in q if not TRACKING_PARAMS_RE.match(k)]
    q_filtered.sort(key=lambda kv: (kv[0], kv[1]))
    query = urlencode(q_filtered, doseq=True)

    return urlunparse((scheme, netloc, path, "", query, ""))

def url_to_text_signature(u: str) -> str:
    """
    ใช้เฉพาะ path + ชื่อ query param (ไม่เอาค่า) เพื่อรวม URLs คล้ายกัน
    """
    p = urlparse(u)
    path_tokens = [seg for seg in (p.path or "/").split("/") if seg]
    q = parse_qsl(p.query, keep_blank_values=True)
    q_keys = sorted([k for k, v in q])  # เอาเฉพาะ key
    tokens = path_tokens + q_keys
    if not tokens:
        tokens = [p.netloc]
    return " ".join(tokens)

def dedupe_urls_by_tfidf(urls, threshold=0.85):
    if not urls:
        return [], {}

    normalized = [normalize_url(u) for u in urls]
    texts = [url_to_text_signature(u) for u in normalized]

    vec = TfidfVectorizer(analyzer="word", ngram_range=(1,2))
    X = vec.fit_transform(texts)
    sim = cosine_similarity(X)

    n = len(urls)
    assigned = [False] * n
    groups = {}
    representatives = []

    for i in range(n):
        if assigned[i]:
            continue
        cluster_idxs = [i]
        assigned[i] = True
        for j in range(i+1, n):
            if not assigned[j] and sim[i, j] >= threshold:
                assigned[j] = True
                cluster_idxs.append(j)
        cluster_urls = [normalized[k] for k in cluster_idxs]
        rep = min(cluster_urls, key=lambda s: (len(s), s))
        groups[rep] = [urls[k] for k in cluster_idxs]
        representatives.append(rep)

    return representatives, groups

# -------------------------
# Flask route
# -------------------------
@bp.route("/scan", methods=["POST"])
@jwt_required()
def scan():

    data = request.get_json(silent=True) or {}
    url = data.get("url")
    max_pages = int(data.get("max_pages", DEFAULT_MAX_PAGES))
    threshold = float(data.get("dedupe_threshold", DEFAULT_DEDUPE_THRESHOLD))
    concurrency = int(data.get("concurrency", DEFAULT_CONCURRENCY))

    if not url or not urlparse(url).scheme in ("http", "https"):
        return jsonify({"ok": False, "msg": "invalid or missing url"}), 400

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        urls = loop.run_until_complete(_crawl_async(url, max_pages=max_pages, concurrency=concurrency))
        loop.close()
    except Exception as e:
        return jsonify({"ok": False, "msg": "crawl failed", "error": str(e)}), 500

    try:
        representatives, groups = dedupe_urls_by_tfidf(urls, threshold=threshold)
    except Exception:
        representatives = []
        groups = {}
        seen = set()
        for u in urls:
            n = normalize_url(u)
            if n not in seen:
                seen.add(n)
                representatives.append(n)
                groups[n] = [u]

    result = {
        "ok": True,
        "url": url,
        "count_raw": len(urls),
        "urls": urls,
        "cleaned_count": len(representatives),
        "cleaned_urls": representatives,
        "duplicates": groups
    }
    return jsonify(result)
