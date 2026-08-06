import logging
import random
import urllib.parse
from typing import List
import aiohttp
from core.interfaces import IBookSource
from core.models import Book
import config

logger = logging.getLogger("BOOK")

class ArchiveOrgSource(IBookSource):
    def get_name(self) -> str:
        return "archive"

    async def search_books(self, query: str, limit: int = 10) -> List[Book]:
        """
        Searches Archive.org for Arabic PDF books.
        Uses advanced search query and resolves direct PDF URLs from file lists.
        """
        logger.book(f"Searching Archive.org for query: '{query}'...")
        
        search_query = (
            f"language:ara AND mediatype:texts AND {query}"
        )
        
        encoded_query = urllib.parse.quote(search_query)
        search_url = (
            f"https://archive.org/advancedsearch.php?q={encoded_query}"
            f"&fl[]=identifier&fl[]=title&fl[]=creator&fl[]=description"
            f"&sort[]=downloads+desc&output=json&rows={limit * 2}"
        )

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

        books = []
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                logger.book(f"Requesting Archive.org URL: {search_url}")
                async with session.get(search_url) as response:
                    if response.status != 200:
                        logger.warning(f"Archive.org Search API returned status {response.status}")
                        return []
                    
                    data = await response.json()
                    docs = data.get("response", {}).get("docs", [])
                    logger.book(f"Archive.org search returned {len(docs)} raw docs for query: '{query}'")
                    
                    for doc in docs:
                        if len(books) >= limit:
                            break
                            
                        identifier = doc.get("identifier")
                        title = doc.get("title")
                        creator = doc.get("creator")
                        description = doc.get("description", "")
                        
                        if not identifier or not title:
                            logger.book(f"Skipped IA doc: missing identifier or title")
                            continue
                            
                        # Handle creator formatting (sometimes is list, sometimes string)
                        author = "مؤلف مجهول"
                        if creator:
                            if isinstance(creator, list):
                                author = ", ".join(creator)
                            else:
                                author = str(creator)
                                
                        # Fetch the file list of this identifier to find the exact PDF
                        files_url = f"https://archive.org/metadata/{identifier}"
                        async with session.get(files_url) as files_response:
                            if files_response.status != 200:
                                continue
                                
                            files_data = await files_response.json()
                            files_list = files_data.get("files", [])
                            
                            pdf_file = None
                            for f in files_list:
                                filename = f.get("name", "")
                                # Look for PDF files, skip auto-generated/metadata PDFs
                                if (
                                    filename.lower().endswith(".pdf")
                                    and not filename.lower().endswith("_archive.pdf")
                                    and not filename.lower().endswith("_meta.pdf")
                                ):
                                    pdf_file = f
                                    break
                            
                            if not pdf_file:
                                logger.book(f"Skipped IA doc '{identifier}': no valid PDF file in metadata")
                                continue
                                
                            filename = pdf_file["name"]
                            size_bytes = int(pdf_file.get("size", 0))
                            
                            # Skip if file exceeds limits (20MB)
                            if size_bytes > config.MAX_BOOK_SIZE_BYTES or size_bytes == 0:
                                logger.book(f"Skipped IA doc '{identifier}': PDF size {size_bytes} is 0 or > 20MB limit")
                                continue
                                
                            pdf_url = f"https://archive.org/download/{identifier}/{urllib.parse.quote(filename)}"
                            checksum = pdf_file.get("sha1", "") or pdf_file.get("md5", "") or identifier
                            
                            # Attempt to find a cover thumbnail if archive.org has one
                            cover_url = None
                            for f in files_list:
                                f_name = f.get("name", "").lower()
                                if f_name.endswith(".jpg") or f_name.endswith(".png"):
                                    if "thumb" in f_name or "cover" in f_name:
                                        cover_url = f"https://archive.org/download/{identifier}/{urllib.parse.quote(f['name'])}"
                                        break
                            
                            book = Book(
                                fingerprint=identifier,  # Initial placeholder, will be recalculated using actual validator
                                title=title,
                                author=author,
                                source="archive",
                                url=pdf_url,
                                size_bytes=size_bytes,
                                checksum=checksum,
                                cover_url=cover_url,
                                description=description
                            )
                            books.append(book)
                            
            logger.book(f"Archive.org search returned {len(books)} eligible books.")
            return books
        except Exception as e:
            logger.error(f"Error searching Archive.org: {e}")
            return []
