import sys
import time
import random
import logging
import unicodedata
import requests
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from fastmcp import FastMCP
from pydantic import Field

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s',
                    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger('StoryServer')

if sys.platform == 'win32':
    sys.stderr.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')

mcp = FastMCP("StoryServer")

RSS_URL = "https://anchor.fm/s/b0e954c/podcast/rss"
CACHE_TTL = 1800  # 30 phút

_cache: dict = {"episodes": [], "fetched_at": 0.0, "etag": ""}


def _normalize(text: str) -> str:
    """Chuyển tiếng Việt có dấu → không dấu, chữ thường để so sánh fuzzy."""
    nfkd = unicodedata.normalize('NFKD', text.lower())
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _extract_cdn_url(anchor_url: str) -> str:
    """Trích URL CloudFront trực tiếp từ Anchor.fm relay URL.

    Anchor URL format: .../play/{episode_id}/{url_encoded_cdn_path}
    → giải mã lấy CDN URL trực tiếp để giảm latency.
    """
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
    """Fetch RSS feed và parse thành list episodes, có cache 30 phút."""
    global _cache
    now = time.time()

    if not force and _cache["episodes"] and (now - _cache["fetched_at"]) < CACHE_TTL:
        return _cache["episodes"]

    logger.info("🔄 [StoryServer] Đang tải RSS feed từ Anchor.fm...")
    try:
        headers = {"User-Agent": "AI-Robot-Story/1.0"}
        if _cache["etag"]:
            headers["If-None-Match"] = _cache["etag"]

        resp = requests.get(RSS_URL, headers=headers, timeout=15)

        if resp.status_code == 304:
            logger.info("✅ [StoryServer] RSS không đổi (304 Not Modified), dùng cache.")
            _cache["fetched_at"] = now
            return _cache["episodes"]

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
            cdn_url = _extract_cdn_url(anchor_url)

            dur_el = item.find('itunes:duration', ns)
            ep_el = item.find('itunes:episode', ns)
            pub_el = item.find('pubDate')

            ep_num = 0
            raw_ep = (ep_el.text or "").strip() if ep_el is not None else ""
            if raw_ep.isdigit():
                ep_num = int(raw_ep)

            episodes.append({
                'title': title,
                'title_norm': _normalize(title),
                'audio_url': cdn_url,
                'anchor_url': anchor_url,
                'duration': (dur_el.text or '?').strip() if dur_el is not None else '?',
                'episode': ep_num,
                'pub_date': (pub_el.text or '').strip() if pub_el is not None else '',
            })

        _cache["episodes"] = episodes
        _cache["fetched_at"] = now
        _cache["etag"] = resp.headers.get("ETag", "")
        logger.info(f"✅ [StoryServer] Đã load {len(episodes)} tập truyện vào cache.")
        return episodes

    except Exception as e:
        logger.error(f"❌ [StoryServer] Lỗi fetch RSS: {e}")
        return _cache.get("episodes", [])


def _search(keyword: str, episodes: list[dict], max_results: int = 8) -> list[dict]:
    """Tìm kiếm episode theo từ khóa, tính điểm theo mức độ khớp."""
    kw_norm = _normalize(keyword)
    tokens = [t for t in kw_norm.split() if len(t) > 1]  # bỏ ký tự đơn lẻ

    scored = []
    for ep in episodes:
        norm = ep['title_norm']
        score = 0

        # Khớp toàn bộ cụm từ → điểm cao nhất
        if kw_norm in norm:
            score += 5
        # Mỗi token khớp thêm điểm
        for token in tokens:
            if token in norm:
                score += 2
        # Bonus: tập có số tập cao hơn (mới hơn) được ưu tiên khi điểm bằng nhau
        if score > 0:
            scored.append((score, ep['episode'], ep))

    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [ep for _, _, ep in scored[:max_results]]


@mcp.tool()
def search_stories(
    keyword: str = Field(..., description=(
        "Từ khóa tìm truyện cổ tích. Ví dụ: 'bạch tuyết', 'tam cám', "
        "'cô bé quàng khăn đỏ', 'grimm', 'việt nam', 'bạch dương'"
    ))
) -> dict:
    """
    Tìm kiếm truyện cổ tích trong kho CMDD Audio (506+ tập) theo từ khóa.
    Trả về danh sách tên truyện phù hợp để bé chọn hoặc robot giới thiệu.
    Dùng khi bé hỏi 'có truyện gì không', 'có truyện X không', hoặc muốn xem danh sách.
    KHÔNG dùng khi bé đã muốn nghe ngay - hãy dùng play_story cho trường hợp đó.
    """
    logger.info(f"🔍 [StoryServer] search_stories: '{keyword}'")
    episodes = _fetch_episodes()

    if not episodes:
        return {"success": False, "error": "Không thể tải danh sách truyện. Vui lòng kiểm tra kết nối mạng."}

    results = _search(keyword, episodes)

    if not results:
        return {
            "success": False,
            "error": f"Không tìm thấy truyện nào về '{keyword}' trong kho CMDD Audio ({len(episodes)} tập).",
            "suggestion": "Thử tìm với từ khóa ngắn hơn, ví dụ: 'bạch tuyết', 'grimm', 'nga', 'việt nam'."
        }

    return {
        "success": True,
        "keyword": keyword,
        "found": len(results),
        "total_in_library": len(episodes),
        "stories": [
            {
                "episode": ep["episode"],
                "title": ep["title"],
                "duration": ep["duration"],
            }
            for ep in results
        ]
    }


@mcp.tool()
def play_story(
    keyword: str = Field(
        default="",
        description=(
            "Tên hoặc từ khóa của truyện muốn phát. "
            "Ví dụ: 'bạch tuyết', 'tam cám', 'cô bé quàng khăn đỏ', 'rapunzel'. "
            "Bỏ trống hoặc để '' để phát truyện ngẫu nhiên."
        )
    ),
    episode: int = Field(
        default=0,
        description="Số tập cụ thể muốn phát (1–506). Mặc định 0 = tự chọn theo keyword."
    )
) -> dict:
    """
    Phát một truyện cổ tích từ kho CMDD Audio (506+ tập) cho bé nghe.
    Gọi tool này khi bé muốn nghe truyện ngay: 'kể chuyện X đi', 'robot kể truyện đi',
    'cho tớ nghe truyện', 'phát truyện X'. Tool trả về audio_url để stream trực tiếp.
    """
    logger.info(f"▶️ [StoryServer] play_story: keyword='{keyword}', episode={episode}")
    episodes = _fetch_episodes()

    if not episodes:
        return {"success": False, "error": "Không thể tải danh sách truyện. Vui lòng kiểm tra kết nối mạng."}

    selected = None

    # Ưu tiên 1: tìm theo số tập cụ thể
    if episode > 0:
        selected = next((ep for ep in episodes if ep['episode'] == episode), None)
        if not selected:
            return {"success": False, "error": f"Không tìm thấy tập số {episode}. Kho có {len(episodes)} tập (EP.1 – EP.506)."}

    # Ưu tiên 2: tìm theo từ khóa
    if selected is None and keyword.strip():
        results = _search(keyword.strip(), episodes)
        if not results:
            return {
                "success": False,
                "error": f"Không tìm thấy truyện nào về '{keyword}'.",
                "suggestion": f"Thử dùng search_stories('{keyword}') để xem kho có gì gần giống."
            }
        selected = results[0]

    # Ưu tiên 3: chọn ngẫu nhiên nếu không có keyword
    if selected is None:
        selected = random.choice(episodes)
        logger.info(f"🎲 [StoryServer] Chọn ngẫu nhiên: EP.{selected['episode']}")

    logger.info(f"✅ [StoryServer] Phát: EP.{selected['episode']} - {selected['title']} ({selected['duration']})")

    return {
        "success": True,
        "title": selected["title"],
        "episode": selected["episode"],
        "duration": selected["duration"],
        "audio_url": selected["audio_url"],
        "pub_date": selected["pub_date"],
        "intro": (
            f"Chú Robot sẽ kể truyện «{selected['title']}» cho bé nghe nhé! "
            f"Câu chuyện kéo dài {selected['duration']}. Bé hãy lắng tai nghe!"
        )
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
