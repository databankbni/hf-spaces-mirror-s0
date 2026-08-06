"""
Combined MCP Server – gộp tất cả tools vào 1 subprocess để tiết kiệm RAM trên Render free tier.
Tools: calculator, google_search, get_gold_price, get_news, get_weather,
       control_light, control_lights_batch, search_stories, play_story
"""
import asyncio
import json
import os
import re
import sys
import time
import random
import logging
import unicodedata
import threading
import requests
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote
import urllib.parse
import uuid
import tempfile
import http.server
import socket
import asyncpg
from dotenv import load_dotenv
from fastmcp import FastMCP
from pydantic import Field
from bs4 import BeautifulSoup

# Chạy như subprocess của app (đã kế thừa env qua os.environ.copy) HOẶC standalone.
# load_dotenv() đảm bảo cả 2 đều đọc được .env; không ghi đè env đã có sẵn (HF Secrets).
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(message)s',
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger('CombinedServer')

if sys.platform == 'win32':
    sys.stderr.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')

mcp = FastMCP("CombinedServer")

# ─────────────────────────────────────────────────────────────
# ENV VARS
# ─────────────────────────────────────────────────────────────
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")
SMARTLIGHT_API_URL = os.getenv("SMARTLIGHT_API_URL", "http://localhost:5067")
MEDIA_API_BASE_URL = os.getenv("MEDIA_API_BASE_URL", "http://127.0.0.1:7860").rstrip("/")

# Public URL mà thiết bị ESP32 sẽ dùng để poll /api/image_queue.
# Ưu tiên: PUBLIC_URL env var → tự suy ra từ SPACE_ID (HuggingFace) → MEDIA_API_BASE_URL
def _derive_public_url() -> str:
    if os.getenv("PUBLIC_URL"):
        return os.getenv("PUBLIC_URL").rstrip("/")
    space_id = os.getenv("SPACE_ID", "")          # HuggingFace tự set, vd: "trinhKhanh/ai-mcp-tools-server"
    if space_id:
        return "https://" + space_id.replace("/", "-").lower() + ".hf.space"
    return MEDIA_API_BASE_URL                      # fallback: local dev

PUBLIC_URL = _derive_public_url()
logger.info("🌐 PUBLIC_URL (device poll): %s", PUBLIC_URL)

# IP của thiết bị ESP32 trên mạng LAN (ví dụ: http://192.168.1.100)
# Để trống nếu không dùng tính năng push trực tiếp.
DEVICE_API_URL = os.getenv("DEVICE_API_URL", "")
# Thời gian chờ (giây) trước khi gửi lệnh phát đến thiết bị,
# để TTS của LLM phát xong trước khi radio bắt đầu.
DEVICE_PLAY_DELAY = float(os.getenv("DEVICE_PLAY_DELAY", "4"))
# Tốc độ đọc TTS ước tính (ký tự/giây) — dùng để tính delay ảnh theo độ dài text.
WHY_TTS_SPEED = float(os.getenv("WHY_TTS_SPEED", "15"))
# Thời gian (giây) cần để download + decode ảnh từ wsrv.nl trước khi hiển thị.
WHY_DOWNLOAD_LEAD = float(os.getenv("WHY_DOWNLOAD_LEAD", "3"))

# Kết nối DB why_questions (Neon) — KHÔNG hardcode, lấy từ env (.env / HF Secrets)
_WHY_DB_HOST     = os.getenv("WHY_DB_HOST")
_WHY_DB_PORT     = int(os.getenv("WHY_DB_PORT", "5432"))
_WHY_DB_NAME     = os.getenv("WHY_DB_NAME")
_WHY_DB_USER     = os.getenv("WHY_DB_USER")
_WHY_DB_PASSWORD = os.getenv("WHY_DB_PASSWORD")

# ─────────────────────────────────────────────────────────────
# IMAGE CACHE (local HTTP server → fast device downloads from LAN)
# Thay vì để thiết bị download từ wsrv.nl (~2-3s), server tải ảnh trước
# rồi serve từ LAN (~0.3s) để ảnh hiện đúng lúc với từng câu hỏi.
# ─────────────────────────────────────────────────────────────
IMAGE_CACHE_PORT = int(os.getenv("IMAGE_CACHE_PORT", "8765"))
_img_cache_dir: str | None = None
_img_cache_ip: str = ""
_img_cache_ready = threading.Event()


def _start_image_cache_server() -> None:
    global _img_cache_dir, _img_cache_ip
    try:
        _img_cache_dir = tempfile.mkdtemp(prefix="esp32_why_img_")
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        _img_cache_ip = s.getsockname()[0]
        s.close()

        class _Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=_img_cache_dir, **kwargs)
            def log_message(self, *args): pass  # suppress access logs

        server = http.server.HTTPServer(("0.0.0.0", IMAGE_CACHE_PORT), _Handler)
        _img_cache_ready.set()
        logger.info(
            "📡 Image cache: http://%s:%d → %s",
            _img_cache_ip, IMAGE_CACHE_PORT, _img_cache_dir,
        )
        server.serve_forever()
    except Exception as exc:
        logger.warning("⚠️ Image cache server failed to start: %s", exc)


if DEVICE_API_URL:
    threading.Thread(target=_start_image_cache_server, daemon=True).start()


def _to_baseline_jpg(url: str) -> str:
    """Proxy through wsrv.nl to convert progressive JPEG → baseline (ESP32 requirement)."""
    if "wsrv.nl" in url:
        return url  # Already proxied; avoid double-encoding
    # Unquote first so URLs that already contain %XX sequences are not double-encoded
    # (e.g. Cyrillic filenames like %D0%94... become %2525D0%252594 without this step)
    clean = urllib.parse.unquote(url)
    # Wikipedia SVG thumbnails may include a language prefix (e.g. "langvi-330px-")
    # that wsrv.nl cannot resolve → strip it to get the plain thumbnail
    clean = re.sub(r'/lang\w+-(\d+px-)', r'/\1', clean)
    encoded = urllib.parse.quote(clean, safe="")
    return f"https://wsrv.nl/?url={encoded}&output=jpg&q=75&w=320"


def _clean_source_url(url: str) -> str:
    """URL ảnh gốc để tải TRỰC TIẾP: bóc ?url= nếu là link wsrv.nl, unquote,
    và bỏ tiền tố ngôn ngữ của thumbnail SVG Wikipedia (langvi-330px-)."""
    if "wsrv.nl" in url:
        try:
            q = urllib.parse.urlparse(url).query
            inner = urllib.parse.parse_qs(q).get("url", [""])[0]
            if inner:
                url = inner
        except Exception:
            pass
    clean = urllib.parse.unquote(url)
    clean = re.sub(r'/lang\w+-(\d+px-)', r'/\1', clean)
    return clean


# User-Agent theo chính sách của Wikimedia (mô tả rõ + có liên hệ) để giảm bị
# rate-limit 429. UA chung chung / giống bot bị Wikimedia siết mạnh hơn.
_WIKI_UA = ("XiaozhiVN-WhyImageBot/1.0 "
            "(+https://github.com/78/xiaozhi-esp32; educational AI robot)")


def _download_baseline_jpeg(src_url: str) -> bytes | None:
    """Tải ảnh gốc trực tiếp + convert sang baseline JPEG rộng 320px cho ESP32.
    Xử lý cả PNG/GIF (flatten RGB) và progressive JPEG → baseline. None nếu lỗi.
    Retry 429/5xx (Wikimedia rate-limit ngẫu nhiên). Import Pillow nội bộ để
    thiếu thư viện chỉ vô hiệu tối ưu, không sập server."""
    try:
        import io
        import time
        from PIL import Image
    except Exception as exc:
        logger.warning("⚠️ [WHY-IMG] Pillow không khả dụng: %s", exc)
        return None

    raw = None
    for attempt in range(1, 4):
        try:
            resp = requests.get(src_url, headers={"User-Agent": _WIKI_UA}, timeout=12)
            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning("⚠️ [WHY-IMG] HTTP %d (lần %d/3): %.60s",
                               resp.status_code, attempt, src_url)
                if attempt < 3:
                    time.sleep(0.6 * attempt)
                    continue
                return None
            resp.raise_for_status()
            raw = resp.content
            break
        except Exception as exc:
            logger.warning("⚠️ [WHY-IMG] tải lỗi (lần %d/3): %s", attempt, exc)
            if attempt < 3:
                time.sleep(0.6 * attempt)
                continue
            return None

    if not raw:
        return None
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = im.size
        if w > 320:
            im = im.resize((320, max(1, round(h * 320 / w))), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=75, progressive=False, optimize=True)
        return out.getvalue()
    except Exception as exc:
        logger.warning("⚠️ [WHY-IMG] convert lỗi (%.60s): %s", src_url, exc)
        return None


def _fetch_to_cache(img_url: str) -> str:
    """
    Tải ảnh GỐC trực tiếp (không qua wsrv.nl — hay bị Wikimedia rate-limit 429),
    convert baseline JPEG bằng Pillow, lưu vào cache dir và trả URL LAN (nhanh,
    thiết bị tải trong ~0.3s). Fallback URL wsrv.nl nếu cache chưa sẵn sàng
    hoặc bước tải/convert thất bại.
    """
    if not _img_cache_ready.is_set():
        return _to_baseline_jpg(img_url)
    jpeg = _download_baseline_jpeg(_clean_source_url(img_url))
    if jpeg is None:
        return _to_baseline_jpg(img_url)  # last-resort fallback
    try:
        filename = uuid.uuid4().hex[:10] + ".jpg"
        with open(os.path.join(_img_cache_dir, filename), "wb") as f:
            f.write(jpeg)
        return f"http://{_img_cache_ip}:{IMAGE_CACHE_PORT}/{filename}"
    except Exception as exc:
        logger.warning("⚠️ Image cache write failed for %s: %s", img_url[:60], exc)
        return _to_baseline_jpg(img_url)


# Mapping original_url → cached local URL (populated by get_why_questions prefetch)
_img_cache_map: dict[str, str] = {}
_img_cache_map_lock = threading.Lock()


def _get_or_fetch_cache(img_url: str) -> str:
    """Return cached URL for img_url; download synchronously on cache miss."""
    with _img_cache_map_lock:
        cached = _img_cache_map.get(img_url)
    if cached:
        return cached
    result = _fetch_to_cache(img_url)
    with _img_cache_map_lock:
        _img_cache_map[img_url] = result
    return result


_why_pool: asyncpg.Pool | None = None


async def _get_why_pool() -> asyncpg.Pool:
    global _why_pool
    if _why_pool is None:
        _why_pool = await asyncpg.create_pool(
            host=_WHY_DB_HOST, port=_WHY_DB_PORT,
            database=_WHY_DB_NAME, user=_WHY_DB_USER, password=_WHY_DB_PASSWORD,
            min_size=1, max_size=3,
            ssl="require",
        )
    return _why_pool


# ─────────────────────────────────────────────────────────────
# MATH
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def calculator(
    action: str = Field(..., description=(
        "Loại phép tính. Dùng 'add' cho phép CỘNG (thêm, cộng thêm, tổng cộng, bao nhiêu tất cả). "
        "Dùng 'subtract' cho phép TRỪ (bớt đi, trừ, còn lại, mất đi)."
    )),
    a: float = Field(..., description="Số thứ nhất (số bị cộng hoặc số bị trừ). Trích xuất từ câu nói của người dùng."),
    b: float = Field(..., description="Số thứ hai (số cộng thêm hoặc số trừ đi). Trích xuất từ câu nói của người dùng.")
) -> dict:
    """
    Thực hiện phép tính cộng hoặc trừ. LUÔN gọi tool này thay vì tự tính khi người dùng hỏi về số học.

    GỌI KHI nghe các cụm từ:
    - Phép CỘNG: "cộng", "thêm", "tổng", "tất cả là", "gộp lại", "bao nhiêu tất cả", "cộng thêm"
      Ví dụ: "3 cộng 5 bằng bao nhiêu?", "tôi có 10 cái kẹo, mẹ cho thêm 7 cái, bây giờ có mấy cái?",
              "hôm nay bán 150 cái, hôm qua bán 200 cái, tổng cộng bao nhiêu?"
    - Phép TRỪ: "trừ", "bớt", "còn lại", "mất đi", "tiêu hết", "đã dùng"
      Ví dụ: "100 trừ 37 bằng bao nhiêu?", "có 20 viên kẹo ăn 8 viên còn mấy viên?",
              "tiêu 50 nghìn, còn lại bao nhiêu trong 200 nghìn?"

    KHÔNG gọi tool này cho: nhân, chia, lũy thừa, căn bậc hai (không hỗ trợ).
    """
    try:
        if action == "add":
            result = a + b
        elif action == "subtract":
            result = a - b
        else:
            return {"success": False, "error": "Phép tính không được hỗ trợ"}
        logger.info(f"🧮 calculator: {a} {action} {b} = {result}")
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# SEARCH (SearXNG + web scrape)
# ─────────────────────────────────────────────────────────────

SEARCH_TIMEOUT = 6    # timeout SearXNG (giây)
SCRAPE_TIMEOUT = 4    # timeout mỗi URL scrape (giây)
SCRAPE_WORKERS = 3    # số URL scrape song song


def _search_searxng(query: str, max_results: int = 5) -> list[dict]:
    params = {"q": query, "format": "json", "categories": "general", "language": "vi-VN"}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SonicAI/1.0)"}
    resp = requests.get(f"{SEARXNG_URL}/search", params=params, headers=headers, timeout=SEARCH_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("results", [])[:max_results]


def _scrape_webpage(url: str, max_chars: int = 2500) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=SCRAPE_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'html.parser')
        for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'noscript', 'iframe']):
            tag.decompose()
        container = soup.find('article') or soup.find('main') or soup.body or soup
        lines = []
        for tag in container.find_all(['p', 'li', 'h1', 'h2', 'h3']):
            line = ' '.join(tag.get_text(separator=' ', strip=True).split())
            if len(line) > 20:
                lines.append(line)
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n...[Nội dung đã được cắt bớt]..."
        return text
    except Exception as e:
        logger.warning(f"⚠️ [Search] Không thể scrape {url}: {e}")
        return ""


def _scrape_first_available(results: list[dict], max_chars: int = 2500) -> tuple[str, str]:
    """Scrape song song tất cả URL, trả về (content, title) của URL thành công đầu tiên."""
    candidates = [(r.get("url", ""), r.get("title", "")) for r in results if r.get("url")]
    if not candidates:
        return "", ""

    with ThreadPoolExecutor(max_workers=min(SCRAPE_WORKERS, len(candidates))) as executor:
        future_to_meta = {
            executor.submit(_scrape_webpage, url, max_chars): (url, title)
            for url, title in candidates[:SCRAPE_WORKERS]
        }
        for future in as_completed(future_to_meta):
            text = future.result()
            if text:
                _, title = future_to_meta[future]
                # Hủy các task còn lại
                for f in future_to_meta:
                    f.cancel()
                return text, title
    return "", ""


@mcp.tool()
def google_search(query: str = Field(..., description=(
    "Câu truy vấn tìm kiếm. Viết bằng tiếng Việt tự nhiên hoặc từ khóa ngắn gọn. "
    "Ví dụ: 'sức khỏe Trump 2025', 'Sơn Tùng MTP album mới', 'lũ lụt miền Bắc hôm nay'."
))) -> dict:
    """
    Tìm kiếm thông tin thực tế, sự kiện, tin tức cụ thể về một người hoặc chủ đề trên internet.

    GỌI KHI người dùng hỏi về:
    - Thông tin cụ thể về một người: "ông Trump sức khỏe thế nào?", "Sơn Tùng có tin gì mới không?",
      "ronaldo đang ở câu lạc bộ nào?", "thủ tướng Việt Nam là ai?"
    - Sự kiện đang xảy ra: "hôm nay có chuyện gì xảy ra?", "vụ tai nạn trên cao tốc hôm qua thế nào?",
      "tình hình chiến sự Ukraine mới nhất?", "trận động đất ở Nhật vừa rồi ra sao?"
    - Kiến thức, định nghĩa cần tra cứu: "AI là gì?", "cách làm bánh flan?", "lịch sử tháp Eiffel"
    - Giá cả sản phẩm, thông tin mua sắm: "giá iPhone 16 bao nhiêu?", "xe Honda Wave đời mới giá bao nhiêu?"
    - Lịch chiếu phim, sự kiện giải trí: "Avatar 2 chiếu ở đâu?", "concert Blackpink bao giờ?"
    - Kết quả, điểm số, bảng xếp hạng thể thao: "kết quả World Cup hôm nay?", "điểm số trận...",
      "ai thắng trận...", "bảng xếp hạng Premier League", "kết quả SEA Games mới nhất"

    KHÔNG gọi tool này cho:
    - Giá vàng → dùng get_gold_price
    - Thời tiết → dùng get_weather
    - Đọc tiêu đề tin tức tổng hợp → dùng get_news
    - Tìm/phát truyện cổ tích → dùng search_stories hoặc play_story

    Cách chuyển câu nói thành query:
    - "sức khỏe ông Trump dạo này ra sao?" → query = "sức khỏe Trump 2025"
    - "hôm nay Việt Nam có tin gì nóng không?" → query = "tin tức Việt Nam hôm nay"
    - "Sơn Tùng ra bài mới chưa?" → query = "Sơn Tùng MTP bài hát mới nhất 2025"
    """
    logger.info(f"🔍 google_search: {query}")
    try:
        results = _search_searxng(query, max_results=5)
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ [Search] SearXNG không chạy tại {SEARXNG_URL}")
        return {"success": False, "error": f"SearXNG chưa khởi động (không kết nối được {SEARXNG_URL}). Hãy chạy: docker-compose up -d searxng"}
    except Exception as e:
        logger.error(f"❌ [Search] Lỗi SearXNG: {e}")
        return {"success": False, "error": f"Lỗi SearXNG: {e}"}
    if not results:
        return {"success": False, "error": "SearXNG không trả về kết quả cho truy vấn này."}

    full_text, source_title = _scrape_first_available(results)

    if not full_text:
        # Fallback: ghép snippets từ SearXNG
        snippets = [
            f"- {r.get('title', '')}: {r.get('content', '')}"
            for r in results if r.get("content")
        ]
        full_text = "\n".join(snippets) if snippets else "Không tìm thấy nội dung."
        source_title = results[0].get("title", "")

    logger.info(f"✅ google_search: '{query}' → '{source_title}' ({len(full_text)} ký tự)")
    return {
        "success": True,
        "result": f"[Nguồn: {source_title}]\n\n{full_text}"
    }


# ─────────────────────────────────────────────────────────────
# GOLD PRICE
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_gold_price() -> dict:
    """
    Lấy giá vàng trong nước (SJC, PNJ, DOJI, vàng 9999, vàng 24k…) và vàng thế giới (XAU/USD) theo thời gian thực.

    GỌI KHI người dùng hỏi bất cứ điều gì liên quan đến GIÁ VÀNG:
    - "giá vàng hôm nay là bao nhiêu?"
    - "vàng SJC đang bán giá mấy?"
    - "vàng có lên không? vàng tăng hay giảm?"
    - "mua vàng 9999 bây giờ giá bao nhiêu một chỉ?"
    - "giá vàng thế giới hiện tại?"
    - "vàng 24k giá bao nhiêu?"
    - "hôm nay vàng PNJ bán bao nhiêu?"
    - "so sánh giá vàng mua vào và bán ra"
    - "đầu tư vàng có lời không?" (khi cần biết giá hiện tại)

    KHÔNG cần tham số nào. Luôn trả về giá mới nhất theo thời gian thực.
    KHÔNG dùng google_search để tra giá vàng — tool này cho kết quả nhanh và chính xác hơn.
    """
    try:
        resp = requests.get("https://www.vang.today/api/prices", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return {"success": False, "error": "API không trả về dữ liệu hợp lệ."}

        prices = data.get("prices", {})
        date_str = data.get("date", "")
        time_str = data.get("time", "")

        vnd_lines = []
        usd_lines = []
        for item in prices.values():
            name = item.get("name", "")
            buy = item.get("buy")
            sell = item.get("sell")
            currency = item.get("currency", "VND")
            change_sell = item.get("change_sell", 0)
            trend = "▲" if change_sell > 0 else ("▼" if change_sell < 0 else "—")

            if currency == "VND":
                buy_fmt = f"{buy:,.0f}" if buy else "N/A"
                sell_fmt = f"{sell:,.0f}" if sell else "N/A"
                vnd_lines.append(f"  • {name}: Mua {buy_fmt} / Bán {sell_fmt} đ {trend}")
            else:
                usd_lines.append(f"  • {name}: ${sell:,.2f}/oz {trend}" if sell else f"  • {name}: N/A")

        sections = [f"Giá vàng cập nhật lúc {time_str} ngày {date_str}:\n"]
        if vnd_lines:
            sections.append("[VÀNG TRONG NƯỚC]\n" + "\n".join(vnd_lines))
        if usd_lines:
            sections.append("[VÀNG THẾ GIỚI]\n" + "\n".join(usd_lines))

        logger.info(f"💰 get_gold_price: {len(prices)} loại vàng, cập nhật {time_str} {date_str}")
        return {"success": True, "result": "\n\n".join(sections)}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Không kết nối được nguồn dữ liệu giá vàng."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# NEWS (VNExpress RSS)
# ─────────────────────────────────────────────────────────────

RSS_FEEDS = {
    "latest":     "https://vnexpress.net/rss/tin-moi-nhat.rss",
    "technology": "https://vnexpress.net/rss/so-hoa.rss",
    "news":       "https://vnexpress.net/rss/thoi-su.rss",
    "business":   "https://vnexpress.net/rss/kinh-doanh.rss",
    "sports":     "https://vnexpress.net/rss/the-thao.rss",
    "world":      "https://vnexpress.net/rss/the-gioi.rss",
}

_CATEGORY_ALIASES = {
    # latest
    "tin mới nhất": "latest", "mới nhất": "latest", "tổng hợp": "latest", "tin tức": "latest",
    # world
    "thế giới": "world", "quốc tế": "world", "tin quốc tế": "world",
    "chiến sự": "world", "xung đột": "world", "tin thế giới": "world",
    # news / thời sự
    "thời sự": "news", "chính trị": "news", "xã hội": "news", "trong nước": "news",
    # technology
    "công nghệ": "technology", "khoa học": "technology", "số hóa": "technology",
    "kỹ thuật số": "technology", "khoa học công nghệ": "technology",
    # business
    "kinh doanh": "business", "kinh tế": "business", "tài chính": "business",
    "chứng khoán": "business", "thị trường": "business",
    # sports
    "thể thao": "sports", "bóng đá": "sports", "thể dục": "sports",
}


def _resolve_category(raw: str) -> str:
    key = raw.strip().lower()
    if key in RSS_FEEDS:
        return key
    return _CATEGORY_ALIASES.get(key, "latest")


@mcp.tool()
def get_news(
    category: str = Field(default="latest", description=(
        "Chủ đề tin tức. Nhận tiếng Việt tự nhiên hoặc tiếng Anh:\n"
        "- 'latest' / 'tin mới nhất' / 'tổng hợp' / 'tin tức' → tin mới nhất mọi chủ đề\n"
        "- 'technology' / 'công nghệ' / 'khoa học' / 'số hóa' → tin công nghệ\n"
        "- 'news' / 'thời sự' / 'trong nước' / 'chính trị' / 'xã hội' → tin thời sự trong nước\n"
        "- 'business' / 'kinh doanh' / 'kinh tế' / 'tài chính' / 'chứng khoán' → tin kinh tế\n"
        "- 'sports' / 'thể thao' / 'bóng đá' → tin thể thao\n"
        "- 'world' / 'thế giới' / 'quốc tế' / 'chiến sự' / 'xung đột' → tin thế giới"
    )),
    limit: int = Field(default=5, description="Số lượng bài tin muốn lấy, mặc định 5 bài.")
) -> dict:
    """
    Đọc danh sách tiêu đề tin tức mới nhất từ VNExpress theo từng chủ đề.

    GỌI KHI người dùng muốn nghe TIN TỨC TỔNG HỢP (nhiều bài, không hỏi về sự kiện cụ thể):
    - "đọc tin tức cho tôi nghe đi"
    - "hôm nay có tin gì hot không?"
    - "cho tôi nghe vài tin tức buổi sáng"
    - "có tin gì về thể thao không?"
    - "tin kinh tế hôm nay như thế nào?"
    - "điểm tin công nghệ đi"
    - "tin tức thế giới mới nhất"
    - "có gì mới về bóng đá không?"
    - "đọc báo cho tôi nghe"
    - "tóm tắt tin tức hôm nay"

    KHÔNG gọi tool này khi:
    - Người dùng hỏi về MỘT sự kiện/người cụ thể → dùng google_search
      (VD: "vụ tai nạn trên cao tốc hôm qua thế nào?" → google_search)
    - Hỏi giá vàng → dùng get_gold_price
    - Hỏi thời tiết → dùng get_weather
    """
    resolved = _resolve_category(category)
    try:
        resp = requests.get(RSS_FEEDS[resolved], timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        articles = []
        for item in channel.findall("item")[:limit]:
            articles.append({
                "title":     item.findtext("title", ""),
                "link":      item.findtext("link", ""),
                "published": item.findtext("pubDate", ""),
                "summary":   item.findtext("description", ""),
            })
        logger.info(f"📰 get_news: category='{category}'→'{resolved}', {len(articles)} bài")
        return {"success": True, "category": resolved, "total": len(articles), "articles": articles}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_news_detail(
    link: str = Field(..., description=(
        "URL đầy đủ của bài báo VNExpress cần đọc chi tiết, ví dụ "
        "'https://vnexpress.net/thi-sinh-do-vao-cac-nganh-ky-thuat-cong-nghe-tang-5093484.html'. "
        "Lấy đúng giá trị 'link' của bài mà người dùng chọn từ danh sách do get_news trả về trước đó."
    ))
) -> dict:
    """
    Đọc TOÀN VĂN nội dung một bài báo VNExpress cụ thể (tiêu đề, sapo, các đoạn thân bài).

    GỌI KHI người dùng đã nghe danh sách tin (từ get_news) và muốn nghe CHI TIẾT một bài:
    - "đọc bài đầu tiên cho tôi nghe"
    - "đọc chi tiết bài về Haaland đi"
    - "bài thứ 3 nói gì, đọc nghe xem"
    - "cho tôi nghe nội dung tin về World Cup"

    Cách chọn 'link': dựa vào câu nói của người dùng, tìm bài khớp nhất trong danh sách
    get_news vừa trả (theo số thứ tự hoặc theo từ khoá trong tiêu đề), rồi truyền đúng 'link' của bài đó.

    KHÔNG gọi tool này để lấy danh sách tin tổng hợp → dùng get_news.
    """
    if "vnexpress.net" not in link:
        return {"success": False, "error": "Chỉ hỗ trợ đọc chi tiết bài viết từ vnexpress.net"}
    try:
        resp = requests.get(link, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        title_el = soup.select_one("h1.title-detail")
        title = title_el.get_text(strip=True) if title_el else ""

        desc_el = soup.select_one("p.description")
        description = desc_el.get_text(strip=True) if desc_el else ""

        paragraphs = [
            p.get_text(strip=True)
            for p in soup.select("article.fck_detail p.Normal")
            if p.get_text(strip=True)
        ]

        if not paragraphs and not description:
            return {
                "success": False,
                "error": "Không bóc được nội dung (có thể là bài video/ảnh hoặc trang đã đổi cấu trúc).",
                "link": link,
            }

        content = "\n\n".join(paragraphs)
        logger.info(f"📰 get_news_detail: '{title[:40]}...', {len(paragraphs)} đoạn")
        return {
            "success": True,
            "title": title,
            "description": description,
            "content": content,
            "link": link,
        }
    except Exception as e:
        logger.exception("get_news_detail failed")
        return {"success": False, "error": str(e), "link": link}


# ─────────────────────────────────────────────────────────────
# WEATHER (Open-Meteo)
# ─────────────────────────────────────────────────────────────

WMO_CODES = {
    0: "Trời trong xanh, nắng đẹp",
    1: "Chủ yếu trời nắng", 2: "Có mây cụm", 3: "Nhiều mây u ám",
    45: "Có sương mù", 48: "Sương mù có băng giá",
    51: "Mưa phùn nhẹ", 53: "Mưa phùn vừa", 55: "Mưa phùn dày hạt",
    56: "Mưa phùn có đóng băng nhẹ", 57: "Mưa phùn có đóng băng nặng",
    61: "Mưa rào nhẹ", 63: "Mưa vừa", 65: "Mưa to",
    66: "Mưa có đóng băng nhẹ", 67: "Mưa có đóng băng nặng",
    71: "Tuyết rơi nhẹ", 73: "Tuyết rơi vừa", 75: "Tuyết rơi dày",
    77: "Hạt tuyết",
    80: "Mưa rào nhẹ từng cơn", 81: "Mưa rào vừa", 82: "Mưa rào rất to",
    85: "Mưa tuyết nhẹ", 86: "Mưa tuyết nặng",
    95: "Có sấm chớp", 96: "Sấm chớp và mưa đá nhỏ", 99: "Sấm chớp và mưa đá lớn",
}


@mcp.tool()
def get_weather(
    city: str = Field(..., description=(
        "Tên thành phố cần tra thời tiết. Trích xuất từ câu nói của người dùng. "
        "Nếu người dùng không nói tên thành phố, hỏi lại hoặc dùng thành phố mặc định 'Hà Nội'. "
        "Ví dụ: 'Hà Nội', 'Hồ Chí Minh', 'Đà Nẵng', 'Đà Lạt', 'Huế', 'Cần Thơ', 'Nha Trang', "
        "'Hải Phòng', 'Vũng Tàu', 'Bình Dương'. Có thể dùng tên tiếng Anh: 'Hanoi', 'Ho Chi Minh City'."
    ))
) -> dict:
    """
    Tra cứu thời tiết hiện tại (nhiệt độ, cảm giác như, độ ẩm, gió, mưa) và dự báo 7 ngày tới.
    Nguồn: Open-Meteo API (miễn phí, không cần API key).

    GỌI KHI người dùng hỏi về THỜI TIẾT:
    - "thời tiết Hà Nội hôm nay thế nào?"
    - "mai Sài Gòn có mưa không?"
    - "trời Đà Nẵng hôm nay nắng hay mưa?"
    - "ở Đà Lạt có lạnh không?"
    - "tuần này thời tiết Hải Phòng ra sao?"
    - "hôm nay có cần mang ô không?" (trích xuất thành phố từ ngữ cảnh, nếu chưa biết hỏi lại)
    - "nhiệt độ ngoài trời bao nhiêu độ?"
    - "dự báo thời tiết cuối tuần"
    - "tôi đang ở Cần Thơ, thời tiết thế nào?"

    Cách trích xuất tham số city:
    - "thời tiết Đà Nẵng" → city = "Đà Nẵng"
    - "trời ở Sài Gòn"   → city = "Hồ Chí Minh"
    - Không rõ thành phố → hỏi lại: "Bạn đang ở thành phố nào ạ?"

    KHÔNG dùng google_search để tra thời tiết — tool này cho kết quả nhanh và có dự báo 7 ngày.
    """
    logger.info(f"🌤️ get_weather: {city}")
    try:
        # Bước 1: Geocoding — lấy tọa độ thành phố
        geo_resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "vi"},
            timeout=6
        )
        geo_resp.raise_for_status()
        geo = geo_resp.json()
        if not geo.get("results"):
            return {"success": False, "error": f"Không tìm thấy thành phố '{city}'. Hãy thử tên khác."}

        loc = geo["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        city_name = loc.get("name", city)
        country = loc.get("country", "")

        # Bước 2: Lấy thời tiết — dùng API mới (current thay vì current_weather)
        weather_resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,weather_code,"
                           "relative_humidity_2m,wind_speed_10m,precipitation,is_day",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
                         "wind_speed_10m_max",
                "timezone": "auto",
                "forecast_days": 7,
            },
            timeout=6
        )
        weather_resp.raise_for_status()
        data = weather_resp.json()

        cur = data.get("current", {})
        temp        = cur.get("temperature_2m", "?")
        feels_like  = cur.get("apparent_temperature", "?")
        humidity    = cur.get("relative_humidity_2m", "?")
        wind        = cur.get("wind_speed_10m", "?")
        precip      = cur.get("precipitation", 0)
        wcode       = cur.get("weather_code", 0)
        is_day      = cur.get("is_day", 1)
        condition   = WMO_CODES.get(wcode, "Thời tiết thất thường")

        time_label = "ban ngày" if is_day else "ban đêm"
        precip_note = f", lượng mưa {precip}mm" if precip > 0 else ""

        current_block = (
            f"Thời tiết tại {city_name}{', ' + country if country else ''} ({time_label}):\n"
            f"  Hiện tại : {temp}°C (cảm giác như {feels_like}°C)\n"
            f"  Tình trạng: {condition}{precip_note}\n"
            f"  Độ ẩm   : {humidity}%\n"
            f"  Gió     : {wind} km/h"
        )

        # Dự báo 7 ngày
        daily = data.get("daily", {})
        forecast_lines = []
        times      = daily.get("time", [])
        wcodes     = daily.get("weather_code", [])
        t_max      = daily.get("temperature_2m_max", [])
        t_min      = daily.get("temperature_2m_min", [])
        precip_sum = daily.get("precipitation_sum", [])
        wind_max   = daily.get("wind_speed_10m_max", [])

        for i in range(1, min(7, len(times))):
            rain = f", mưa {precip_sum[i]}mm" if i < len(precip_sum) and precip_sum[i] > 0 else ""
            wind_d = f", gió {wind_max[i]}km/h" if i < len(wind_max) else ""
            forecast_lines.append(
                f"  {times[i]}: {WMO_CODES.get(wcodes[i] if i < len(wcodes) else 0, '?')} "
                f"({t_min[i] if i < len(t_min) else '?'}–{t_max[i] if i < len(t_max) else '?'}°C{rain}{wind_d})"
            )

        result = current_block
        if forecast_lines:
            result += "\n\nDự báo 7 ngày tới:\n" + "\n".join(forecast_lines)

        logger.info(f"✅ get_weather: {city_name} {temp}°C, {condition}")
        return {"success": True, "result": result}

    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Không kết nối được Open-Meteo. Kiểm tra mạng."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# SMART LIGHT
# ─────────────────────────────────────────────────────────────

# @mcp.tool()  # Đã ẩn: không đăng ký tool điều khiển đèn với Gemini
def control_light(
    deviceCode: str,
    isOn: bool,
    brightness: int = 100
) -> dict:
    """
    Điều khiển đèn LED – bật, tắt hoặc điều chỉnh độ sáng của MỘT đèn LED duy nhất.
    Mapping deviceCode: 'đèn 1' → DEV-LAMP01, 'đèn 2' → DEV-LAMP02, 'đèn 3' → DEV-LAMP03.
    isOn: True bật / False tắt. brightness: 0-100.
    """
    brightness = max(0, min(100, brightness))
    if not isOn:
        brightness = 0
    try:
        resp = requests.post(
            f"{SMARTLIGHT_API_URL}/api/mqtt/control",
            json={"deviceCode": deviceCode, "isOn": isOn, "brightness": brightness},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        return {"success": True, "message": data.get("message", ""), "commandId": data.get("commandId")}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Không kết nối được hệ thống đèn."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# @mcp.tool()  # Đã ẩn: không đăng ký tool điều khiển đèn với Gemini
def control_lights_batch(
    deviceCodes: list[str],
    isOn: bool,
    brightness: int = 100
) -> dict:
    """
    Điều khiển đèn LED – bật, tắt hoặc điều chỉnh độ sáng của NHIỀU đèn LED cùng lúc.
    deviceCodes: 'tất cả đèn' → ["DEV-LAMP01","DEV-LAMP02","DEV-LAMP03"].
    isOn: True bật / False tắt. brightness: 0-100.
    """
    brightness = max(0, min(100, brightness))
    if not isOn:
        brightness = 0
    try:
        resp = requests.post(
            f"{SMARTLIGHT_API_URL}/api/mqtt/control-batch",
            json={"deviceCodes": deviceCodes, "isOn": isOn, "brightness": brightness},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "success": True,
            "message": data.get("message", ""),
            "totalFound": data.get("totalFound", 0),
            "totalNotFound": data.get("totalNotFound", 0),
        }
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Không kết nối được hệ thống đèn."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# STORY (CMDD Audio – Anchor.fm RSS, 506+ tập truyện cổ tích)
# ─────────────────────────────────────────────────────────────

STORY_RSS_URL = "https://anchor.fm/s/b0e954c/podcast/rss"
STORY_CACHE_TTL = 1800  # 30 phút
_story_cache: dict = {"episodes": [], "fetched_at": 0.0, "etag": ""}


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize('NFKD', text.lower())
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _extract_cdn_url(anchor_url: str) -> str:
    if '/podcast/play/' in anchor_url:
        try:
            after_play = anchor_url.split('/podcast/play/')[1]
            parts = after_play.split('/', 1)
            if len(parts) == 2:
                return unquote(parts[1])
        except Exception:
            pass
    return anchor_url


def _fetch_episodes(force: bool = False) -> list[dict]:
    global _story_cache
    now = time.time()
    if not force and _story_cache["episodes"] and (now - _story_cache["fetched_at"]) < STORY_CACHE_TTL:
        return _story_cache["episodes"]

    logger.info("🔄 [Story] Đang tải RSS feed từ Anchor.fm...")
    try:
        headers = {"User-Agent": "AI-Robot-Story/1.0"}
        if _story_cache["etag"]:
            headers["If-None-Match"] = _story_cache["etag"]

        resp = requests.get(STORY_RSS_URL, headers=headers, timeout=15)

        if resp.status_code == 304:
            _story_cache["fetched_at"] = now
            return _story_cache["episodes"]

        resp.raise_for_status()
        ns = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}
        root = ET.fromstring(resp.content)
        episodes = []

        for item in root.findall('.//item'):
            title_el = item.find('title')
            enc_el = item.find('enclosure')
            if title_el is None or enc_el is None:
                continue
            title = (title_el.text or "").strip()
            anchor_url = enc_el.get('url', '')
            dur_el = item.find('itunes:duration', ns)
            ep_el = item.find('itunes:episode', ns)
            pub_el = item.find('pubDate')
            ep_num = 0
            raw_ep = (ep_el.text or "").strip() if ep_el is not None else ""
            if raw_ep.isdigit():
                ep_num = int(raw_ep)
            episodes.append({
                'title':      title,
                'title_norm': _normalize(title),
                'audio_url':  _extract_cdn_url(anchor_url),
                'anchor_url': anchor_url,
                'duration':   (dur_el.text or '?').strip() if dur_el is not None else '?',
                'episode':    ep_num,
                'pub_date':   (pub_el.text or '').strip() if pub_el is not None else '',
            })

        _story_cache["episodes"] = episodes
        _story_cache["fetched_at"] = now
        _story_cache["etag"] = resp.headers.get("ETag", "")
        logger.info(f"✅ [Story] Đã load {len(episodes)} tập vào cache.")
        return episodes
    except Exception as e:
        logger.error(f"❌ [Story] Lỗi fetch RSS: {e}")
        return _story_cache.get("episodes", [])


def _story_search(keyword: str, episodes: list[dict], max_results: int = 8) -> list[dict]:
    kw_norm = _normalize(keyword)
    tokens = [t for t in kw_norm.split() if len(t) > 1]
    scored = []
    for ep in episodes:
        norm = ep['title_norm']
        score = 5 if kw_norm in norm else 0
        for token in tokens:
            if token in norm:
                score += 2
        if score > 0:
            scored.append((score, ep['episode'], ep))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [ep for _, _, ep in scored[:max_results]]


@mcp.tool()
def search_stories(
    keyword: str = Field(..., description=(
        "Từ khóa tìm truyện. Trích xuất tên truyện hoặc chủ đề từ câu nói. "
        "Dùng từ khóa ngắn: 'bạch tuyết', 'tam cám', 'cô bé quàng khăn đỏ', 'grimm', 'việt nam', "
        "'công chúa', 'hoàng tử', 'rồng', 'phép màu'. Không cần viết nguyên câu đầy đủ."
    ))
) -> dict:
    """
    Tìm kiếm trong kho 506+ truyện cổ tích CMDD Audio theo từ khóa, trả về DANH SÁCH tên truyện phù hợp.

    GỌI KHI người dùng muốn TÌM KIẾM / XEM CÓ TRUYỆN NÀO không (chưa muốn nghe ngay):
    - "có truyện bạch tuyết không?"
    - "tìm truyện về công chúa xem có gì"
    - "kho truyện có những truyện gì của Grimm?"
    - "có bao nhiêu truyện cổ tích Việt Nam?"
    - "liệt kê truyện có nhân vật rồng"
    - "truyện nào có từ 'cô bé' trong tên?"

    KHÔNG gọi tool này khi bé muốn NGHE NGAY → dùng play_story thay thế.
    Phân biệt:
    - "tìm xem có truyện tam cám không?" → search_stories (chỉ tìm, chưa phát)
    - "kể truyện tam cám đi" / "cho tôi nghe truyện tam cám" → play_story (phát ngay)
    """
    logger.info(f"🔍 search_stories: '{keyword}'")
    episodes = _fetch_episodes()
    if not episodes:
        return {"success": False, "error": "Không thể tải danh sách truyện."}
    results = _story_search(keyword, episodes)
    if not results:
        return {
            "success": False,
            "error": f"Không tìm thấy truyện nào về '{keyword}' ({len(episodes)} tập).",
            "suggestion": "Thử từ khóa ngắn hơn: 'bạch tuyết', 'grimm', 'việt nam'."
        }
    return {
        "success": True,
        "keyword": keyword,
        "found": len(results),
        "total_in_library": len(episodes),
        "stories": [{"episode": ep["episode"], "title": ep["title"], "duration": ep["duration"]} for ep in results]
    }


@mcp.tool()
def play_story(
    keyword: str = Field(default="", description=(
        "Tên hoặc từ khóa truyện muốn phát. Trích xuất từ câu nói của người dùng. "
        "Ví dụ: 'bạch tuyết', 'tam cám', 'cô bé lọ lem', 'alibaba', 'hoàng tử ếch'. "
        "Để TRỐNG ('') nếu người dùng muốn nghe ngẫu nhiên hoặc không chỉ định truyện cụ thể."
    )),
    episode: int = Field(default=0, description=(
        "Số tập cụ thể từ 1 đến 506. Chỉ dùng khi người dùng nói số tập rõ ràng "
        "(VD: 'tập 12', 'tập số 50'). Mặc định 0 = chọn theo keyword."
    ))
) -> dict:
    """
    Tìm và trả về URL audio của truyện cổ tích. TOOL NÀY KHÔNG TỰ PHÁT — CHỈ TÌM URL.

    ⚠️ SAU KHI TOOL NÀY TRẢ VỀ, AUDIO CHƯA ĐƯỢC PHÁT.
    Bước bắt buộc duy nhất: gọi self.audio.play_url(url=<url>, title=<title>) NGAY.
    KHÔNG được nói bất kỳ câu nào trước hoặc sau khi gọi self.audio.play_url.
    Nói trong khi audio đang phát sẽ LÀM GIÁN ĐOẠN và DỪNG audio ngay lập tức.
    Im lặng hoàn toàn = để bé nghe truyện không bị cắt ngang.

    GỌI KHI người dùng (hoặc bé nhỏ) muốn NGHE TRUYỆN NGAY LẬP TỨC:
    - "kể truyện bạch tuyết và bảy chú lùn cho con nghe đi"
    - "cho tôi nghe truyện tam cám"
    - "phát truyện cô bé lọ lem"
    - "bật truyện lên đi"
    - "con muốn nghe truyện cổ tích"
    - "kể chuyện cho con nghe đi robot ơi"
    - "cho bé nghe truyện nào đó đi" (keyword = "", sẽ phát ngẫu nhiên)
    - "có truyện gì hay hay kể cho con nghe với" (keyword = "", phát ngẫu nhiên)
    - "tập 25 đi" (episode = 25)
    - "phát tập tiếp theo" (tùy ngữ cảnh, có thể gọi với keyword rỗng)

    Cách trích xuất tham số:
    - "kể truyện tam cám" → keyword = "tam cám", episode = 0
    - "phát tập 10" → keyword = "", episode = 10
    - "kể truyện gì đó ngẫu nhiên" → keyword = "", episode = 0
    - "cho con nghe truyện về công chúa" → keyword = "công chúa", episode = 0

    KHÔNG gọi tool này khi người dùng chỉ hỏi "có truyện gì không" → dùng search_stories.
    """
    logger.info(f"▶️ play_story: keyword='{keyword}', episode={episode}")
    episodes = _fetch_episodes()
    if not episodes:
        return {"success": False, "error": "Không thể tải danh sách truyện."}

    selected = None
    if episode > 0:
        selected = next((ep for ep in episodes if ep['episode'] == episode), None)
        if not selected:
            return {"success": False, "error": f"Không tìm thấy tập số {episode}."}
    if selected is None and keyword.strip():
        results = _story_search(keyword.strip(), episodes)
        if not results:
            return {"success": False, "error": f"Không tìm thấy truyện nào về '{keyword}'."}
        selected = results[0]
    if selected is None:
        selected = random.choice(episodes)

    logger.info(f"✅ [Story] Phát: EP.{selected['episode']} – {selected['title']}")

    if DEVICE_API_URL:
        # Push trực tiếp đến thiết bị sau delay để TTS của LLM phát xong trước.
        url_to_play   = selected["audio_url"]
        title_to_play = selected["title"]
        def _push_to_device():
            time.sleep(DEVICE_PLAY_DELAY)
            try:
                resp = requests.post(
                    f"{DEVICE_API_URL}/api/play",
                    json={"url": url_to_play, "title": title_to_play},
                    timeout=5
                )
                logger.info(f"✅ [Story] Pushed to device: {resp.status_code} – {title_to_play}")
            except Exception as e:
                logger.warning(f"⚠️ [Story] Failed to push to device: {e}")
        threading.Thread(target=_push_to_device, daemon=True).start()
        return {"success": True, "title": title_to_play}

    # Fallback khi không có DEVICE_API_URL: để LLM gọi self.audio.play_url
    return {
        "status":             "url_ready_not_playing",
        "warning":            "Gọi self.audio.play_url(url, title) NGAY. KHÔNG nói gì thêm.",
        "required_next_call": "self.audio.play_url",
        "url":                selected["audio_url"],
        "title":              selected["title"],
    }



@mcp.tool()
def prepare_media_download(
    query: str = Field(description=(
        "Tên hoặc từ khóa của ảnh, nhạc hoặc video người dùng muốn tải về thẻ SD. "
        "Giữ nguyên tiếng Việt của tên media, ví dụ: 'ảnh gia đình', 'nhạc thiếu nhi'."
    )),
) -> dict:
    """
    Tìm media đã upload và tạo ticket tải một lần cho ESP32.

    Nếu success=true, BẮT BUỘC gọi ngay self.sdcard.download_file với CHÍNH XÁC toàn bộ
    trường trong arguments; không sửa URL, đường dẫn, SHA-256 hoặc ACK ticket.
    Nếu error=ambiguous, hỏi người dùng chọn một mục trong candidates rồi gọi lại tool này.
    Tool này chỉ chuẩn bị ticket, chưa tải file xuống thiết bị.
    """
    logger.info(f"📥 [MCP] prepare_media_download được gọi với query: '{query}'")
    try:
        response = requests.post(
            f"{MEDIA_API_BASE_URL}/api/media/prepare-download",
            json={"query": query},
            timeout=15,
        )
        data = response.json()
        if not response.ok:
            err_msg = data.get("detail", f"Media API HTTP {response.status_code}")
            logger.warning(f"⚠️ [MCP] prepare_media_download thất bại từ API: {err_msg}")
            return {
                "success": False,
                "error": err_msg,
            }
        
        if data.get("success"):
            logger.info(f"✅ [MCP] prepare_media_download chuẩn bị ticket thành công cho '{query}'. Dest path: {data.get('arguments', {}).get('dest_path')}")
        else:
            logger.warning(f"⚠️ [MCP] prepare_media_download trả về kết quả không thành công: {data.get('error')}")
            
        return data
    except requests.exceptions.ConnectionError:
        logger.error("❌ [MCP] Không thể kết nối tới Media API Backend (chưa chạy hoặc cấu hình sai port).")
        return {"success": False, "error": "Không kết nối được Media API."}
    except Exception as exc:
        logger.exception(f"❌ [MCP] Lỗi xử lý prepare_media_download: {exc}")
        return {"success": False, "error": str(exc)}


# ─────────────────────────────────────────────────────────────
# WHY IMAGE DISPLAY
# Local mode (DEVICE_API_URL set): push ảnh qua LAN cache → device HTTP API
# Cloud mode: push qua broker WebSocket (main app /api/internal/push_image)
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def show_why_image(
    image_url: str = Field(..., description=(
        "URL ảnh cần hiển thị (lấy từ image_urls[0] của câu hỏi). "
        "Gọi NGAY TRƯỚC khi đọc câu hỏi."
    ))
) -> dict:
    """
    Hiển thị ảnh minh họa lên màn hình thiết bị trước khi đọc câu hỏi.
    Gọi NGAY TRƯỚC khi đọc mỗi câu hỏi.
    Không cần làm gì thêm sau khi gọi — thiết bị tự tải và hiển thị ảnh.
    """
    if DEVICE_API_URL:
        # Local mode: push trực tiếp qua LAN cache
        push_url = _get_or_fetch_cache(image_url)
        try:
            resp = requests.post(
                f"{DEVICE_API_URL}/api/display_image",
                json={"url": push_url}, timeout=5,
            )
            logger.info("✅ [WHY] show_why_image (local): %d – %s", resp.status_code, push_url[:70])
            return {"image_displayed": True}
        except Exception as exc:
            logger.warning("⚠️ [WHY] show_why_image (local) thất bại: %s", exc)
            return {"image_displayed": False, "error": str(exc)}

    # Cloud mode: gửi URL GỐC cho app. App tự tải ảnh trực tiếp từ nguồn
    # (server có IP riêng → không bị Wikimedia rate-limit như wsrv.nl), convert
    # baseline JPEG 320px bằng Pillow rồi serve từ chính domain của mình.
    # Bỏ wsrv.nl khỏi đường truyền → hết cả 429 lẫn cache-lỗi 404.
    # (App tự fallback về wsrv.nl nếu bước tải/convert thất bại.)
    try:
        requests.post(
            f"{MEDIA_API_BASE_URL}/api/internal/set_image",
            json={"url": image_url}, timeout=15,
        )
        logger.info("🖼️ [WHY] show_why_image (cloud queue): %.70s", image_url)
        return {"status": "image_queued", "message": "Ảnh đang được hiển thị trên thiết bị."}
    except Exception as exc:
        logger.warning("⚠️ [WHY] show_why_image (cloud queue) thất bại: %s", exc)
        return {"status": "error", "error": str(exc)}


@mcp.tool()
def hide_why_image() -> dict:
    """
    Ẩn ảnh minh họa sau khi đọc xong câu hỏi CUỐI CÙNG.
    Không cần gọi giữa các câu hỏi — show_why_image cho câu tiếp theo
    sẽ tự thay thế ảnh cũ.
    """
    if DEVICE_API_URL:
        try:
            requests.post(
                f"{DEVICE_API_URL}/api/display_image",
                json={"url": None}, timeout=5,
            )
            logger.info("✅ [WHY] hide_why_image (local): màn hình đã xóa ảnh")
            return {"success": True}
        except Exception as exc:
            logger.warning("⚠️ [WHY] hide_why_image (local) thất bại: %s", exc)
            return {"success": False, "error": str(exc)}

    # Cloud mode: firmware xử lý % hide_why_image trực tiếp, không cần LLM làm gì
    logger.info("🖼️ [WHY] hide_why_image (cloud): firmware sẽ tự xóa ảnh")
    return {"status": "ok", "message": "Ảnh sẽ được ẩn khỏi màn hình."}


# ─────────────────────────────────────────────────────────────
# WHY QUESTIONS (1 vạn câu hỏi vì sao — PostgreSQL db_tools)
# ─────────────────────────────────────────────────────────────

async def _locked_products(conn, kind: str, endpoint_key: str) -> list[dict]:
    """Sản phẩm PHẢI MUA mà thiết bị này CHƯA có quyền (theo tools.entitlements).

    `kind` là loại nội dung ('why_category' → lọc why_questions.category qua `ref`).
    Sản phẩm free, hoặc entitlement còn hiệu lực (expires_at NULL/tương lai) → không khoá.
    Nội dung KHÔNG có dòng nào trong tools.products thì mặc định mở (products là
    danh sách những thứ bị khoá, không phải danh sách trắng).

    Quyền có 2 loại chủ (migration 008), tính cả hai:
      1. Theo TÀI KHOẢN — resolve endpoint_key → user_subscriptions.account_id
         → entitlements của account đó (mua đi theo người, đổi robot vẫn còn).
      2. Theo THIẾT BỊ — entitlements.endpoint_key khớp trực tiếp (admin cấp tay
         cho máy chưa có chủ).

    Chưa chạy migration 006 → coi như không khoá gì (tính năng vẫn chạy như cũ).
    """
    try:
        rows = await conn.fetch(
            """
            SELECT p.product_code, p.ref, p.title, p.price_vnd
            FROM tools.products p
            WHERE p.kind = $1
              AND p.is_active
              AND NOT p.is_free
              AND NOT EXISTS (
                  SELECT 1 FROM tools.entitlements e
                  WHERE e.product_code = p.product_code
                    AND (e.expires_at IS NULL OR e.expires_at > NOW())
                    AND (
                          e.endpoint_key = $2
                       OR (e.account_id IS NOT NULL AND e.account_id = (
                               SELECT s.account_id
                               FROM tools.user_subscriptions s
                               WHERE s.endpoint_key = $2
                                 AND s.account_id IS NOT NULL
                               LIMIT 1))
                    )
              )
            ORDER BY p.sort_order
            """,
            kind, endpoint_key,
        )
        return [dict(r) for r in rows]
    except asyncpg.UndefinedTableError:
        logger.warning("⚠️ [STORE] Chưa có tools.products/entitlements (migration 006) — bỏ qua kiểm tra quyền")
        return []
    except asyncpg.UndefinedColumnError:
        logger.warning("⚠️ [STORE] tools.entitlements thiếu cột account_id (migration 008) — bỏ qua kiểm tra quyền")
        return []


@mcp.tool()
async def get_why_questions(
    count: int = Field(default=3, description=(
        "Số câu hỏi muốn lấy (1–10). Mặc định 3 câu."
    )),
    endpoint_key: str = Field(default="", description=(
        "KHÔNG dùng — hệ thống tự điền định danh thiết bị."
    ))
) -> dict:
    """
    Lấy câu hỏi vì sao ngẫu nhiên từ kho "1 vạn câu hỏi vì sao".
    Ưu tiên câu hỏi ít được hiển thị nhất để tránh lặp lại.

    GỌI KHI người dùng nói:
    - "1 vạn câu hỏi vì sao", "câu hỏi vì sao đi"
    - "hỏi tôi câu hỏi vì sao", "đố tôi vì sao"
    - "cho tôi biết một câu hỏi hay", "tại sao trời lại xanh?"
    - "hỏi tôi về vũ trụ / động vật / thực vật"
    - "con muốn học câu hỏi thú vị"

    Sau khi nhận kết quả, đọc lần lượt từng câu:
    "Câu hỏi 1: [question]... [answer]"
    KHÔNG dùng google_search cho loại yêu cầu này.
    """
    count = max(1, min(10, count))
    try:
        pool = await _get_why_pool()
        async with pool.acquire() as conn:
            # Chỉ trả chủ đề được phép: free + đã mua. endpoint_key rỗng
            # (gọi từ /api/tools/run, broker không có JWT…) → chỉ nội dung free.
            locked = await _locked_products(conn, "why_category", endpoint_key)
            locked_refs = [p["ref"] for p in locked if p["ref"]]
            rows = await conn.fetch("""
                SELECT id, question, answer, image_urls, category
                FROM tools.why_questions
                WHERE category IS NULL OR category <> ALL($2::text[])
                ORDER BY
                    CASE WHEN image_urls != '[]'::jsonb THEN 0 ELSE 1 END,
                    shown_count ASC,
                    RANDOM()
                LIMIT $1
            """, count, locked_refs)
            if not rows:
                if locked_refs:
                    logger.info("🔒 [STORE] endpoint_key='%s' chưa mua chủ đề nào khả dụng", endpoint_key)
                    return {
                        "success": False,
                        "error": "locked",
                        "locked_products": [
                            {"title": p["title"], "price_vnd": p["price_vnd"]} for p in locked
                        ],
                        "INSTRUCTION": (
                            "Nói với người dùng rằng các chủ đề câu hỏi vì sao này là nội dung "
                            "mở rộng cần mua thêm, và họ có thể mở khoá trên trang quản lý của "
                            "robot. KHÔNG tự bịa câu hỏi vì sao, KHÔNG dùng google_search để thay thế."
                        ),
                    }
                return {"success": False, "error": "Database chưa có câu hỏi. Hãy chạy build_why_db.py trước."}
            if locked_refs:
                logger.info("🔒 [STORE] Ẩn %d chủ đề chưa mua: %s", len(locked_refs), locked_refs)
            ids = [r["id"] for r in rows]
            await conn.execute("""
                UPDATE tools.why_questions SET shown_count = shown_count + 1
                WHERE id = ANY($1::int[])
            """, ids)
        def _parse_imgs(raw) -> list:
            if isinstance(raw, list):
                return raw
            if isinstance(raw, str):
                try:
                    return json.loads(raw)
                except Exception:
                    return []
            return []

        questions = [
            {
                "id":         r["id"],
                "question":   r["question"],
                "answer":     r["answer"],
                "image_urls": _parse_imgs(r["image_urls"]),
                "category":   r["category"],
            }
            for r in rows
        ]
        logger.info("❓ get_why_questions: trả về %d câu hỏi", len(questions))

        if DEVICE_API_URL:
            # Tải ảnh Q1 trước (blocking ~2-3s) rồi cache map để show_why_image
            # trả về gần như ngay lập tức.  Q2+ tải song song trong background.
            img_urls = [(q.get("image_urls") or [None])[0] for q in questions]

            # Q1: block để đảm bảo ảnh sẵn sàng trước khi LLM gọi show_why_image
            if img_urls and img_urls[0]:
                q1_cached = await asyncio.to_thread(_fetch_to_cache, img_urls[0])
                with _img_cache_map_lock:
                    _img_cache_map[img_urls[0]] = q1_cached
                logger.info("📦 [WHY] Q1 pre-cached: %s", q1_cached[:70])

            # Q2+: tải song song trong background
            def _prefetch_rest():
                for url in img_urls[1:]:
                    if url and url not in _img_cache_map:
                        cached = _fetch_to_cache(url)
                        with _img_cache_map_lock:
                            _img_cache_map[url] = cached
                        logger.info("📦 [WHY] pre-cached: %s", cached[:70])
            threading.Thread(target=_prefetch_rest, daemon=True).start()

            return {
                "success": True,
                "questions": questions,
                "INSTRUCTION": (
                    "Đọc câu hỏi theo ĐÚNG QUY TRÌNH sau với MỖI câu hỏi i:\n"
                    "  Bước 1 — Gọi show_why_image(image_url=questions[i]['image_urls'][0]) "
                    "nếu questions[i]['image_urls'] không rỗng.\n"
                    "  Bước 2 — Đọc câu hỏi i và câu trả lời i.\n"
                    "Sau câu hỏi CUỐI CÙNG: gọi hide_why_image() để xóa ảnh.\n"
                    "QUAN TRỌNG: Gọi show_why_image TRƯỚC khi nói bất kỳ từ nào của câu hỏi đó."
                ),
            }

        # Cloud mode: firmware tự lấy ảnh từ queue khi nhận % show_why_image
        logger.info("🖼️ [WHY] cloud mode — firmware polls /api/image_queue")
        return {
            "success":      True,
            "questions":    questions,
            "image_server": PUBLIC_URL,
            "INSTRUCTION": (
                "BƯỚC 0 — BẮT BUỘC TRƯỚC TIÊN:\n"
                "  Gọi NGAY system.set_why_image_server(url=image_server).\n"
                "  Không gọi bước này = màn hình KHÔNG hiển thị ảnh.\n"
                "\n"
                "BƯỚC 1–N — Với MỖI câu hỏi i:\n"
                "  a) Nếu questions[i]['image_urls'] không rỗng:\n"
                "     Gọi show_why_image(image_url=questions[i]['image_urls'][0])\n"
                "  b) Đọc câu hỏi i và câu trả lời i.\n"
                "\n"
                "BƯỚC CUỐI: Gọi hide_why_image().\n"
                "QUAN TRỌNG: Gọi show_why_image TRƯỚC khi nói bất kỳ từ nào của câu hỏi đó."
            ),
        }
    except OSError as exc:
        logger.error("❌ get_why_questions: không kết nối được DB why_questions: %s", exc)
        return {"success": False, "error": "Không kết nối được database câu hỏi. Kiểm tra WHY_DB_* env vars."}
    except Exception as exc:
        logger.exception("❌ get_why_questions: %s", exc)
        return {"success": False, "error": str(exc)}


# ─────────────────────────────────────────────────────────────
# ĐẠI VIỆT SỬ KÝ TOÀN THƯ  (tim_su_kien, ke_su_ky, tiep_tuc_su_ky)
# Dữ liệu: bảng tools.su_ky_events trên Neon (dùng chung _get_why_pool).
# Mỗi dòng là 1 đoạn ~900 ký tự đã cắt sẵn cho TTS, sắp theo `ordinal`
# (thứ tự đọc toàn bộ sách). Bookmark theo user trong tools.su_ky_bookmark.
# ─────────────────────────────────────────────────────────────
_SU_KY_READ_INSTRUCTION = (
    "Đọc trọn vẹn phần 'content' như một người kể chuyện lịch sử cho trẻ em: "
    "giọng ấm áp, rõ ràng, có thể diễn giải nhẹ những từ Hán-Việt khó. "
    "KHÔNG đọc các nhãn kỹ thuật (ordinal, tờ mộc bản). "
    "Đọc xong, nói một câu mời gọn như 'Con muốn nghe tiếp không?'. "
    "Khi trẻ muốn nghe tiếp → gọi tiep_tuc_su_ky."
)


async def _su_ky_bookmark_get(conn, user_id: str) -> int:
    val = await conn.fetchval(
        "SELECT last_ordinal FROM tools.su_ky_bookmark WHERE user_id = $1", user_id
    )
    return val or 0


async def _su_ky_bookmark_set(conn, user_id: str, ordinal: int) -> None:
    await conn.execute(
        """
        INSERT INTO tools.su_ky_bookmark (user_id, last_ordinal, updated_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (user_id) DO UPDATE
            SET last_ordinal = EXCLUDED.last_ordinal, updated_at = NOW()
        """,
        user_id, ordinal,
    )


async def _su_ky_serve(conn, row, user_id: str) -> dict:
    """Đánh dấu đã đọc (bookmark + shown_count) và đóng gói payload trả về."""
    await conn.execute(
        "UPDATE tools.su_ky_events SET shown_count = shown_count + 1 WHERE ordinal = $1",
        row["ordinal"],
    )
    await _su_ky_bookmark_set(conn, user_id, row["ordinal"])
    has_next = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM tools.su_ky_events WHERE ordinal > $1)",
        row["ordinal"],
    )
    return {
        "success":     True,
        "ordinal":     row["ordinal"],
        "label":       row["label"],
        "ky":          row["ky"],
        "quyen":       row["quyen"],
        "nam":         row["nam"],
        "nien_hieu":   row["nien_hieu"],
        "content":     row["content"],
        "has_next":    bool(has_next),
        "INSTRUCTION": _SU_KY_READ_INSTRUCTION,
    }


_SU_KY_COLS = "ordinal, label, ky, quyen, nam, nien_hieu, content"

# Tên hiện đại trẻ hay dùng → từ khóa dạng cổ thực sự xuất hiện trong bản dịch 1697.
# (Văn bản gọi "Trưng Nữ Vương", "Bố Cái", "Lam Sơn"... không dùng "Hai Bà Trưng".)
# Đã xác minh số lần khớp trên DB. Lưu ý: sách chép tới 1675 nên KHÔNG có
# Quang Trung / Tây Sơn / nhà Nguyễn.
_SU_KY_ALIASES = {
    "hai bà trưng": "Trưng Nữ Vương", "trưng trắc": "Trưng", "trưng nhị": "Trưng",
    "bà triệu": "Triệu Ẩu", "triệu thị trinh": "Triệu Ẩu",
    "an dương vương": "An Dương", "thục phán": "An Dương",
    "lý bí": "Lý Nam Đế", "lý nam đế": "Lý Nam Đế",
    "triệu quang phục": "Triệu Quang Phục", "dạ trạch vương": "Dạ Trạch",
    "mai thúc loan": "Mai Thúc Loan", "mai hắc đế": "Mai Thúc Loan",
    "phùng hưng": "Bố Cái", "bố cái đại vương": "Bố Cái",
    "đinh bộ lĩnh": "Đinh Bộ Lĩnh", "đinh tiên hoàng": "Đinh Tiên Hoàng",
    "lê hoàn": "Lê Hoàn", "lê đại hành": "Lê Hoàn",
    "trần hưng đạo": "Hưng Đạo", "hưng đạo vương": "Hưng Đạo", "trần quốc tuấn": "Hưng Đạo",
    "lê lợi": "Lam Sơn", "lê thái tổ": "Lam Sơn", "khởi nghĩa lam sơn": "Lam Sơn",
}


def _su_ky_kw(keyword: str) -> str:
    """Chuẩn hóa từ khóa tìm kiếm: ánh xạ tên hiện đại → dạng cổ nếu có."""
    k = (keyword or "").strip()
    kl = k.lower()
    if kl in _SU_KY_ALIASES:
        return _SU_KY_ALIASES[kl]
    for alias, target in _SU_KY_ALIASES.items():
        if alias in kl:
            return target
    return k


@mcp.tool()
async def tim_su_kien(
    keyword: str = Field(..., description=(
        "Từ khóa tìm trong Đại Việt Sử Ký Toàn Thư: tên nhân vật, địa danh, triều đại, "
        "hoặc sự kiện. Dùng từ khóa ngắn, có dấu: 'Bạch Đằng', 'Hai Bà Trưng', "
        "'Trần Hưng Đạo', 'Lê Lợi', 'Ngô Quyền', 'Lý Thường Kiệt'. Không cần cả câu."
    ))
) -> dict:
    """
    Tìm trong Đại Việt Sử Ký Toàn Thư, trả về DANH SÁCH các đoạn sử khớp từ khóa
    (không đọc ngay). Dùng để tra cứu 'sử có chép gì về ...'.

    GỌI KHI người dùng muốn TÌM/TRA trong sử (chưa muốn nghe kể ngay):
    - "sử có chép gì về trận Bạch Đằng không?"
    - "tìm trong sử về Hai Bà Trưng"
    - "Đại Việt Sử Ký có nói gì về Lê Lợi?"
    - "có sự kiện nào năm 1288 không?"

    KHÔNG gọi khi trẻ muốn NGHE KỂ ngay → dùng ke_su_ky.
    """
    if not (keyword or "").strip():
        return {"success": False, "error": "Thiếu từ khóa."}
    kw = _su_ky_kw(keyword)
    try:
        pool = await _get_why_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_SU_KY_COLS}, LEFT(content, 140) AS snippet
                FROM tools.su_ky_events
                WHERE content ILIKE $1
                ORDER BY ordinal
                LIMIT 12
                """,
                f"%{kw}%",
            )
        if not rows:
            return {
                "success": False,
                "error": f"Không tìm thấy đoạn sử nào về '{kw}'.",
                "suggestion": "Thử từ khóa ngắn có dấu: 'Bạch Đằng', 'Trần Hưng Đạo', 'Lê Lợi'.",
            }
        logger.info("📜 tim_su_kien '%s' → %d kết quả", kw, len(rows))
        return {
            "success": True,
            "keyword": kw,
            "found": len(rows),
            "results": [
                {
                    "ordinal": r["ordinal"], "label": r["label"],
                    "ky": r["ky"], "quyen": r["quyen"], "nam": r["nam"],
                    "snippet": r["snippet"],
                }
                for r in rows
            ],
            "INSTRUCTION": (
                "Đọc danh sách gọn cho trẻ chọn. Muốn nghe kể một mục "
                "→ gọi ke_su_ky(keyword=... hoặc nam=...)."
            ),
        }
    except OSError as exc:
        logger.error("❌ tim_su_kien: không kết nối được DB: %s", exc)
        return {"success": False, "error": "Không kết nối được database sử ký. Kiểm tra WHY_DB_* env vars."}
    except Exception as exc:
        logger.exception("❌ tim_su_kien: %s", exc)
        return {"success": False, "error": str(exc)}


@mcp.tool()
async def ke_su_ky(
    keyword: str = Field(default="", description=(
        "Tên nhân vật/địa danh/sự kiện muốn bắt đầu nghe. Ví dụ: 'Bạch Đằng', "
        "'Hai Bà Trưng', 'Lê Lợi'. Để TRỐNG ('') nếu trẻ muốn nghe kể sử từ đầu "
        "(thời Hồng Bàng, họ Hồng Bàng dựng nước)."
    )),
    nam: int = Field(default=0, description=(
        "Năm (dương lịch) muốn bắt đầu nghe, VD 1288, 1428. Chỉ dùng khi trẻ nói rõ năm. "
        "Mặc định 0 = không lọc theo năm."
    )),
    user_id: str = Field(default="default", description=(
        "Định danh thiết bị/trẻ để nhớ chỗ đang đọc. Thường để mặc định 'default'."
    )),
) -> dict:
    """
    Bắt đầu KỂ Đại Việt Sử Ký Toàn Thư: nhảy tới một điểm và trả về đoạn để đọc NGAY,
    đồng thời ghi nhớ chỗ này để 'kể tiếp' sau đó.

    GỌI KHI người dùng muốn NGHE KỂ sử:
    - "kể sử Việt Nam cho con nghe", "kể Đại Việt Sử Ký đi" (để trống keyword → từ đầu)
    - "kể về trận Bạch Đằng", "kể chuyện Hai Bà Trưng" (keyword)
    - "kể chuyện sử năm 1288", "hồi năm 1428 có gì?" (nam)

    Mỗi lần chỉ trả 1 đoạn ngắn (~1 phút đọc). Muốn nghe tiếp → tiep_tuc_su_ky.
    KHÔNG dùng google_search hay search_stories cho yêu cầu kể sử.
    """
    kw = _su_ky_kw(keyword)
    try:
        pool = await _get_why_pool()
        async with pool.acquire() as conn:
            if kw:
                row = await conn.fetchrow(
                    f"SELECT {_SU_KY_COLS} FROM tools.su_ky_events "
                    f"WHERE content ILIKE $1 ORDER BY ordinal LIMIT 1",
                    f"%{kw}%",
                )
                if not row:
                    return {
                        "success": False,
                        "error": f"Không tìm thấy đoạn sử nào về '{kw}'.",
                        "suggestion": "Thử từ khóa khác, hoặc để trống để nghe từ đầu.",
                    }
            elif nam:
                row = await conn.fetchrow(
                    f"SELECT {_SU_KY_COLS} FROM tools.su_ky_events "
                    f"WHERE nam IS NOT NULL ORDER BY ABS(nam - $1), ordinal LIMIT 1",
                    nam,
                )
                if not row:
                    return {"success": False, "error": "Không có dữ liệu năm phù hợp."}
            else:
                # Kể từ đầu sách (ordinal nhỏ nhất = thời Hồng Bàng)
                row = await conn.fetchrow(
                    f"SELECT {_SU_KY_COLS} FROM tools.su_ky_events ORDER BY ordinal LIMIT 1"
                )
                if not row:
                    return {"success": False, "error": "Database sử ký trống. Chạy scripts/parse_dvsktt.py trước."}
            payload = await _su_ky_serve(conn, row, user_id or "default")
        logger.info("📜 ke_su_ky kw='%s' nam=%s → ordinal %d (%s)",
                    kw, nam or "-", payload["ordinal"], payload["label"])
        return payload
    except OSError as exc:
        logger.error("❌ ke_su_ky: không kết nối được DB: %s", exc)
        return {"success": False, "error": "Không kết nối được database sử ký. Kiểm tra WHY_DB_* env vars."}
    except Exception as exc:
        logger.exception("❌ ke_su_ky: %s", exc)
        return {"success": False, "error": str(exc)}


@mcp.tool()
async def tiep_tuc_su_ky(
    user_id: str = Field(default="default", description=(
        "Định danh thiết bị/trẻ để đọc tiếp đúng chỗ đã dừng. Thường để mặc định 'default'."
    )),
) -> dict:
    """
    Kể TIẾP Đại Việt Sử Ký Toàn Thư — đọc đoạn kế tiếp ngay sau chỗ đã dừng lần trước
    (theo bookmark). Dùng nối tiếp sau ke_su_ky hoặc chính tiep_tuc_su_ky.

    GỌI KHI người dùng nói:
    - "kể tiếp đi", "rồi sao nữa?", "tiếp theo thế nào?"
    - "nghe tiếp phần sử vừa rồi"

    Nếu chưa từng kể (chưa có bookmark) → tự bắt đầu từ đoạn đầu sách.
    Khi đã hết sách → trả về has_next=false để báo đã kể xong.
    """
    uid = user_id or "default"
    try:
        pool = await _get_why_pool()
        async with pool.acquire() as conn:
            last = await _su_ky_bookmark_get(conn, uid)
            row = await conn.fetchrow(
                f"SELECT {_SU_KY_COLS} FROM tools.su_ky_events "
                f"WHERE ordinal > $1 ORDER BY ordinal LIMIT 1",
                last,
            )
            if not row:
                if last == 0:
                    return {"success": False, "error": "Database sử ký trống. Chạy scripts/parse_dvsktt.py trước."}
                return {
                    "success": True,
                    "finished": True,
                    "has_next": False,
                    "message": "Đã kể hết Đại Việt Sử Ký Toàn Thư rồi.",
                    "INSTRUCTION": "Báo cho trẻ biết đã nghe hết bộ sử. Muốn nghe lại từ đầu → ke_su_ky (để trống keyword).",
                }
            payload = await _su_ky_serve(conn, row, uid)
        logger.info("📜 tiep_tuc_su_ky uid=%s → ordinal %d (%s)",
                    uid, payload["ordinal"], payload["label"])
        return payload
    except OSError as exc:
        logger.error("❌ tiep_tuc_su_ky: không kết nối được DB: %s", exc)
        return {"success": False, "error": "Không kết nối được database sử ký. Kiểm tra WHY_DB_* env vars."}
    except Exception as exc:
        logger.exception("❌ tiep_tuc_su_ky: %s", exc)
        return {"success": False, "error": str(exc)}


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
