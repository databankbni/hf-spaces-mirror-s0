import logging
import urllib.parse
from typing import List
import aiohttp
from core.interfaces import IBookSource
from core.models import Book
import config

logger = logging.getLogger("BOOK")

class OpenLibrarySource(IBookSource):
    def get_name(self) -> str:
        return "openlibrary"

    async def search_books(self, query: str, limit: int = 10) -> List[Book]:
        """
        Searches Open Library for Arabic books and maps them to Archive.org PDF files.
        """
        logger.book(f"Searching Open Library for query: '{query}'...")
        
        search_query = f"{query} language:ara"
        encoded_query = urllib.parse.quote(search_query)
        # Search specifically for Arabic language books
        search_url = f"https://openlibrary.org/search.json?q={encoded_query}&rows={limit * 2}"
        
        headers = {
            "User-Agent": "ArabicBooksPublisher/1.0 (contact@arabicbookspublisher.local)"
        }
        
        books = []
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(search_url) as response:
                    if response.status != 200:
                        logger.warning(f"Open Library search returned status {response.status}")
                        return []
                        
                    data = await response.json()
                    docs = data.get("docs", [])
                    
                    for doc in docs:
                        if len(books) >= limit:
                            break
                            
                        title = doc.get("title")
                        authors_list = doc.get("author_name", [])
                        ia_list = doc.get("ia", [])
                        
                        # We need at least title and an Internet Archive identifier (ia) to get PDF
                        if not title or not ia_list:
                            continue
                            
                        author = ", ".join(authors_list) if authors_list else "مؤلف مجهول"
                        
                        # Find the first valid ia identifier
                        ia_id = ia_list[0]
                        
                        # Resolve Archive.org files to get the direct PDF URL
                        files_url = f"https://archive.org/metadata/{ia_id}/files"
                        try:
                            async with session.get(files_url) as files_response:
                                if files_response.status != 200:
                                    continue
                                    
                                files_data = await files_response.json()
                                files_list = files_data.get("files", [])
                                
                                pdf_file = None
                                for f in files_list:
                                    filename = f.get("name", "")
                                    if (
                                        filename.lower().endswith(".pdf")
                                        and not filename.lower().endswith("_archive.pdf")
                                        and not filename.lower().endswith("_meta.pdf")
                                    ):
                                        pdf_file = f
                                        break
                                        
                                if not pdf_file:
                                        continue
                                        
                                filename = pdf_file["name"]
                                size_bytes = int(pdf_file.get("size", 0))
                                
                                # Skip if file exceeds limits (20MB)
                                if size_bytes > config.MAX_BOOK_SIZE_BYTES or size_bytes == 0:
                                    continue
                                    
                                pdf_url = f"https://archive.org/download/{ia_id}/{urllib.parse.quote(filename)}"
                                checksum = pdf_file.get("sha1", "") or pdf_file.get("md5", "") or ia_id
                                
                                # Resolve cover
                                cover_id = doc.get("cover_i")
                                cover_url = None
                                if cover_id:
                                    cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                                else:
                                    # Fallback: Look for image in Archive files
                                    for f in files_list:
                                        f_name = f.get("name", "").lower()
                                        if f_name.endswith(".jpg") or f_name.endswith(".png"):
                                            if "thumb" in f_name or "cover" in f_name:
                                                cover_url = f"https://archive.org/download/{ia_id}/{urllib.parse.quote(f['name'])}"
                                                break
                                
                                # Construct description
                                # Open Library sometimes has a description or subject
                                subjects = doc.get("subject", [])
                                description = f"موضوعات الكتاب: {', '.join(subjects[:5])}" if subjects else ""
                                
                                book = Book(
                                    fingerprint=ia_id,
                                    title=title,
                                    author=author,
                                    source="openlibrary",
                                    url=pdf_url,
                                    size_bytes=size_bytes,
                                    checksum=checksum,
                                    cover_url=cover_url,
                                    description=description
                                )
                                books.append(book)
                                
                        except Exception as e:
                            logger.warning(f"Error resolving Archive.org files for OL ia {ia_id}: {e}")
                            continue
                            
            logger.book(f"Open Library search returned {len(books)} eligible books.")
            return books
        except Exception as e:
            logger.error(f"Error searching Open Library: {e}")
            return []
