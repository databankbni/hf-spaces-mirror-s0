import logging
import re
import urllib.parse
from typing import List
import aiohttp
from bs4 import BeautifulSoup
from core.interfaces import IBookSource
from core.models import Book
import config

logger = logging.getLogger("BOOK")

class HindawiSource(IBookSource):
    def get_name(self) -> str:
        return "hindawi"

    async def search_books(self, query: str, limit: int = 10) -> List[Book]:
        """
        Scrapes Hindawi.org search page and fetches book metadata.
        Uses BeautifulSoup to parse the pages.
        """
        logger.book(f"Searching Hindawi for query: '{query}'...")
        
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.hindawi.org/books/search/?q={encoded_query}"
        
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ar,en;q=0.9"
        }
        
        books = []
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                logger.book(f"Requesting Hindawi URL: {search_url}")
                async with session.get(search_url) as response:
                    logger.book(f"Hindawi search returned status: {response.status}")
                    if response.status != 200:
                        logger.warning(f"Hindawi search returned status {response.status}")
                        return []
                        
                    html = await response.text()
                    logger.book(f"Hindawi HTML length: {len(html)}")
                    if "cloudflare" in html.lower() or "challenge" in html.lower() or "verify you are human" in html.lower():
                        logger.warning("Hindawi search page is blocked by Cloudflare / Challenge!")
                        
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # Search results are typically in list items or anchor links containing "/books/"
                    book_links = []
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        # Matches "/books/12345678/" or "/books/category/slug/"
                        # Hindawi books IDs are usually integers, e.g., /books/84918237/
                        match = re.search(r"/books/(\d+)", href)
                        if match:
                            book_id = match.group(1)
                            full_url = f"https://www.hindawi.org/books/{book_id}/"
                            if full_url not in book_links:
                                book_links.append((book_id, full_url))
                                
                    logger.book(f"Found {len(book_links)} matching Hindawi book URLs in search.")
                    
                    for book_id, url in book_links:
                        if len(books) >= limit:
                            break
                            
                        # Scrape the individual book page
                        try:
                            async with session.get(url) as book_resp:
                                if book_resp.status != 200:
                                    continue
                                    
                                book_html = await book_resp.text()
                                book_soup = BeautifulSoup(book_html, "html.parser")
                                
                                # 1. Extract Title
                                title_meta = book_soup.find("meta", property="og:title")
                                title = title_meta["content"] if title_meta else None
                                if not title:
                                    h1 = book_soup.find("h1")
                                    title = h1.text.strip() if h1 else f"كتاب {book_id}"
                                    
                                # Remove "تحميل كتاب ..." prefix if Hindawi includes it in title
                                title = re.sub(r"^تحميل كتاب\s+", "", title).strip()
                                
                                # 2. Extract Author
                                author = None
                                author_meta = book_soup.find("meta", name="author")
                                if author_meta:
                                    author = author_meta["content"].strip()
                                if not author:
                                    # Fallback: Look for contributor link or text
                                    author_tag = book_soup.find("a", href=re.compile(r"/contributors/\d+/"))
                                    if author_tag:
                                        author = author_tag.text.strip()
                                    else:
                                        author = "مؤلف مجهول"
                                        
                                # 3. Extract Description
                                description = ""
                                desc_meta = book_soup.find("meta", name="description")
                                if desc_meta:
                                    description = desc_meta["content"].strip()
                                if not description:
                                    summary_div = book_soup.find("div", class_="summary") or book_soup.find("div", class_="description")
                                    if summary_div:
                                        description = summary_div.text.strip()
                                        
                                # 4. Extract Cover Image
                                cover_url = None
                                cover_meta = book_soup.find("meta", property="og:image")
                                if cover_meta:
                                    cover_url = cover_meta["content"].strip()
                                    if cover_url.startswith("/"):
                                        cover_url = f"https://www.hindawi.org{cover_url}"
                                        
                                # 5. PDF Download Link (Format: https://www.hindawi.org/books/{book_id}/pdf/)
                                pdf_url = f"https://www.hindawi.org/books/{book_id}/pdf/"
                                
                                # We don't have the size_bytes beforehand because it's dynamic.
                                # The downloader will check Content-Length during download.
                                # We set a default size placeholder of 0.
                                book = Book(
                                    fingerprint=book_id,
                                    title=title,
                                    author=author,
                                    source="hindawi",
                                    url=pdf_url,
                                    size_bytes=0,  # Determined dynamically during download
                                    checksum=book_id,
                                    cover_url=cover_url,
                                    description=description
                                )
                                books.append(book)
                                
                        except Exception as e:
                            logger.warning(f"Error scraping individual Hindawi book {book_id}: {e}")
                            continue
                            
            logger.book(f"Hindawi search returned {len(books)} eligible books.")
            return books
        except Exception as e:
            logger.error(f"Error searching Hindawi: {e}")
            return []
