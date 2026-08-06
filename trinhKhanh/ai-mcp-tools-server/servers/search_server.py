# File: mcp_search_server.py
import os
import sys
import logging
import requests
from bs4 import BeautifulSoup
from fastmcp import FastMCP

# Cấu hình hệ thống Logging đồng bộ với main.py
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(message)s',
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger('SearchServer')

# Fix lỗi hiển thị tiếng Việt trên Terminal Windows
if sys.platform == 'win32':
    sys.stderr.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')

# URL của SearXNG: dùng biến môi trường, mặc định cho dev local
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")

mcp = FastMCP("SearchServer")


def search_searxng(query: str, max_results: int = 5) -> list[dict]:
    """Gọi SearXNG JSON API và trả về danh sách kết quả."""
    try:
        params = {
            "q": query,
            "format": "json",
            "categories": "general",
            "language": "vi-VN",
        }
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SonicAI/1.0)"}
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params=params,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])[:max_results]
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ [MCP Search] Không kết nối được SearXNG tại {SEARXNG_URL}")
        return []
    except Exception as e:
        logger.error(f"❌ [MCP Search] Lỗi khi gọi SearXNG: {e}")
        return []


def scrape_webpage(url: str, max_chars: int = 2500) -> str:
    """Truy cập URL và cào văn bản. Cắt bớt nếu quá dài để tiết kiệm Token LLM."""
    try:
        # Giả lập User-Agent của Chrome để không bị các trang web chặn Bot
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        # Tăng timeout lên 8 giây để các trang web chậm ở Việt Nam kịp phản hồi
        response = requests.get(url, headers=headers, timeout=8)
        response.raise_for_status()

        # Dùng content (bytes) thay vì text để BeautifulSoup tự phát hiện encoding đúng
        soup = BeautifulSoup(response.content, 'html.parser')

        # Xoá các thẻ nhiễu
        for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer',
                                   'aside', 'form', 'noscript', 'iframe']):
            tag.decompose()

        # Ưu tiên lấy từ <article> hoặc <main>, fallback về toàn body
        container = soup.find('article') or soup.find('main') or soup.body or soup

        lines = []
        for tag in container.find_all(['p', 'li', 'h1', 'h2', 'h3']):
            line = ' '.join(tag.get_text(separator=' ', strip=True).split())
            if len(line) > 20:   # bỏ qua dòng quá ngắn (menu, label...)
                lines.append(line)

        text_content = "\n".join(lines)

        # Cắt bớt chuỗi nếu vượt quá giới hạn Token mong muốn
        if len(text_content) > max_chars:
            text_content = text_content[:max_chars] + "\n...[Nội dung đã được cắt bớt để tối ưu hệ thống]..."

        return text_content
    except requests.exceptions.RequestException as e:
        logger.warning(f"⚠️ [MCP Search] Không thể truy cập {url} (Lỗi mạng: {e})")
        return ""
    except Exception as e:
        logger.exception(f"❌ [MCP Search] Lỗi bóc tách HTML từ {url}:")
        return ""


@mcp.tool()
def google_search(query: str) -> dict:
    """
    Sử dụng công cụ này để tìm kiếm thông tin sự kiện thực tế, kiến thức trên internet.
    """
    logger.info(f"🔍 [MCP Search] Đang tìm kiếm qua SearXNG: {query}")

    results = search_searxng(query, max_results=5)

    if not results:
        return {"success": False, "error": "SearXNG không trả về kết quả. Kiểm tra lại service."}

    full_text = ""
    used_result = None

    # Lặp qua các kết quả để tìm một đường link hợp lệ có thể cào được nội dung
    for res in results:
        url = res.get("url")
        if not url:
            continue

        logger.info(f"🔗 [MCP Search] Đang thử cào dữ liệu từ URL: {url}")
        full_text = scrape_webpage(url, max_chars=2500)

        if full_text:
            used_result = res
            break  # Nếu cào thành công thì thoát vòng lặp ngay lập tức
        else:
            logger.warning(f"⚠️ [MCP Search] Cào thất bại, thử link tiếp theo...")

    # Nếu tất cả link đều cào thất bại, dùng tạm snippet của SearXNG
    if not full_text:
        used_result = results[0]
        full_text = used_result.get("content", "Không có nội dung mô tả chi tiết.")
        logger.warning("⚠️ [MCP Search] Không cào được link nào, sử dụng tạm snippet từ SearXNG.")

    result_data = {
        "title": used_result.get("title", "Không có tiêu đề"),
        "source_url": used_result.get("url", ""),
        "content": full_text
    }

    logger.info(f"✅ [MCP Search] Đã lấy thành công {len(full_text)} ký tự.")
    return {"success": True, "data": result_data}


if __name__ == "__main__":
    mcp.run(transport="stdio")
