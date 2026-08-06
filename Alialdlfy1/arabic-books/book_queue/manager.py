import logging
import random
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from core.interfaces import IBookRepository, IAIService
from core.models import Book, Post
from books.downloader import download_pdf
from books.validator import validate_pdf
from books.fingerprint import calculate_file_sha256, generate_fingerprint
from sources.manager import SourcesManager
import config

logger = logging.getLogger("QUEUE")

# Genre search keywords to rotate
SEARCH_KEYWORDS = [
    "رواية", "تاريخ", "فلسفة", "علم نفس", "أدب", 
    "علوم", "سياسة", "اقتصاد", "شعر", "تنمية"
]

class QueueManager:
    def __init__(
        self, 
        repository: IBookRepository, 
        ai_service: IAIService, 
        sources_manager: SourcesManager
    ):
        self.repo = repository
        self.ai_service = ai_service
        self.sources_manager = sources_manager

    async def check_and_replenish(self) -> int:
        """
        Checks the pending queue size. If it falls below threshold,
        replenishes it up to the target size.
        """
        count = await self.repo.get_queue_count()
        logger.debug(f"Current pending queue size: {count}/{config.QUEUE_TARGET_SIZE}")
        
        if count >= config.QUEUE_REPLENISH_THRESHOLD:
            logger.debug("Queue size is above threshold. No replenishment needed.")
            return 0
            
        needed = config.QUEUE_TARGET_SIZE - count
        logger.debug(f"Queue size below threshold ({config.QUEUE_REPLENISH_THRESHOLD}). Replenishing {needed} post(s)...")
        
        added_count = 0
        attempts = 0
        max_attempts = needed * 3  # Prevent infinite loop if sources are empty
        
        while added_count < needed and attempts < max_attempts:
            attempts += 1
            # Select a random search query word to get diverse books
            keyword = random.choice(SEARCH_KEYWORDS)
            
            logger.debug(f"Searching for new books using keyword '{keyword}' (Replenishment progress: {added_count}/{needed})...")
            books = await self.sources_manager.search_all(keyword, limit_per_source=5)
            
            if not books:
                logger.warning(f"No books returned for keyword '{keyword}'. Rotating keywords.")
                continue
                
            for book in books:
                if added_count >= needed:
                    break
                    
                # 1. Skip books with unknown/anonymous author or invalid title
                safe_title = book.title.strip() if book.title else ""
                safe_author = book.author.strip() if book.author else ""
                
                import re
                def is_arabic_text(text: str) -> bool:
                    return bool(re.search(r"[\u0600-\u06FF]", text))
                
                if not safe_title or len(safe_title) < 2 or not is_arabic_text(safe_title):
                    logger.debug(f"Skipping book '{safe_title}' because title is invalid or does not contain Arabic text.")
                    continue
                    
                if not safe_author or any(x in safe_author.lower() for x in ["مجهول", "unknown", "anonymous", "لا يوجد", "غير معروف", "منوع", "عدة مؤلفين", "author"]):
                    logger.debug(f"Skipping book '{safe_title}' because author is unknown or generic: '{book.author}'")
                    continue
                    
                # Preliminary check: title/author duplicate in DB (fingerprint without hash first as optimization)
                temp_fp = generate_fingerprint(safe_title, safe_author, "")
                if await self.repo.is_book_published(temp_fp):
                    logger.debug(f"Book '{safe_title}' by '{safe_author}' is already published/queued. Skipping download.")
                    continue
                    
                # 2. Download PDF (with a rate-limiting delay to respect free-tier Gemini API 15 RPM limits)
                import asyncio
                await asyncio.sleep(4)
                
                pdf_path = None
                try:
                    pdf_path = await download_pdf(book.url)
                except Exception as e:
                    logger.warning(f"Failed to download book '{book.title}': {e}")
                    await self.sources_manager.report_failure(book.source, "network_error")
                    continue
                    
                # 3. Validate PDF
                val_result = validate_pdf(pdf_path)
                if not val_result["is_valid"]:
                    logger.warning(f"Downloaded file for '{book.title}' failed validation: {val_result['error']}")
                    await self.sources_manager.report_failure(book.source, "invalid_file")
                    # Clean up
                    if pdf_path and pdf_path.exists():
                        pdf_path.unlink()
                    if val_result["cover_path"] and Path(val_result["cover_path"]).exists():
                        Path(val_result["cover_path"]).unlink()
                    continue
                    
                # 4. Resolve metadata using BookMetadataResolver
                from books.metadata_resolver import BookMetadataResolver
                
                try:
                    resolved = await BookMetadataResolver.resolve(
                        book=book,
                        pdf_path=pdf_path,
                        val_result=val_result,
                        ai_service=self.ai_service,
                        repo=self.repo
                    )
                    book.title = resolved["title"]
                    book.author = resolved["author"]
                    book.translator = resolved["translator"]
                    book.verifier = resolved["verifier"]
                    book.page_count = resolved["page_count"]
                    book.isbn = resolved["isbn"]
                except ValueError as ve:
                    logger.warning(f"Metadata Resolver rejected book: {ve}")
                    if pdf_path.exists():
                        pdf_path.unlink()
                    if val_result.get("cover_path") and Path(val_result["cover_path"]).exists():
                        Path(val_result["cover_path"]).unlink()
                    continue

                # 5. Check for duplicates in database
                # A. Duplicate Title Check
                if await self.repo.is_title_duplicate(book.title):
                    logger.warning(f"Skipping book '{book.title}' because a book with the same normalized title already exists in the database.")
                    if pdf_path.exists():
                        pdf_path.unlink()
                    if val_result.get("cover_path") and Path(val_result["cover_path"]).exists():
                        Path(val_result["cover_path"]).unlink()
                    continue

                # B. Duplicate ISBN Check
                if book.isbn and await self.repo.is_isbn_duplicate(book.isbn):
                    logger.warning(f"Skipping book '{book.title}' because a book with the same ISBN ({book.isbn}) already exists in the database.")
                    if pdf_path.exists():
                        pdf_path.unlink()
                    if val_result.get("cover_path") and Path(val_result["cover_path"]).exists():
                        Path(val_result["cover_path"]).unlink()
                    continue

                intro_text = resolved["intro_text"]

                # 5. Generate final duplicate check fingerprint with content hash
                file_hash = calculate_file_sha256(pdf_path)
                final_fp = generate_fingerprint(book.title, book.author, file_hash)
                
                # Check DB with final fingerprint
                if await self.repo.is_book_published(final_fp):
                    logger.debug(f"Book '{book.title}' has duplicate file content fingerprint in DB. Skipping.")
                    if pdf_path.exists():
                        pdf_path.unlink()
                    if val_result.get("cover_path") and Path(val_result["cover_path"]).exists():
                        Path(val_result["cover_path"]).unlink()
                    continue
                    
                # 6. Process metadata with AI
                logger.debug(f"Processing '{book.title}' with AI...")
                ai_details = await self.ai_service.process_book(
                    book.title, book.author, book.description, intro_text
                )
                
                # 6. Upload cover/files if necessary (in this stateless app, we keep remote URLs)
                # Note: The extracted cover is temporarily stored locally. Since we schedule it immediately, 
                # we don't need to host it permanently; we will download the PDF and extract it again at schedule time.
                # Alternatively, we could keep the cover_url as the remote source thumbnail if it exists.
                cover_url = book.cover_url if book.cover_url else None
                
                # 7. Create Post and save to Queue
                post = Post(
                    fingerprint=final_fp,
                    title=book.title,
                    author=book.author,
                    description=book.description or "",
                    summary=ai_details["summary"],
                    hashtags=ai_details["hashtags"],
                    pdf_url=book.url,
                    category=ai_details["category"],
                    cover_url=cover_url,
                    status="pending",
                    translator=getattr(book, "translator", None),
                    verifier=getattr(book, "verifier", None),
                    page_count=getattr(book, "page_count", None),
                    isbn=getattr(book, "isbn", None)
                )
                
                await self.repo.add_post_to_queue(post)
                # Mark book as published (temporary metadata block to prevent other scraper threads picking it)
                book.fingerprint = final_fp
                await self.repo.mark_book_published(book)
                
                # Clean up local temporary downloads
                if pdf_path.exists():
                    pdf_path.unlink()
                if val_result["cover_path"] and Path(val_result["cover_path"]).exists():
                    Path(val_result["cover_path"]).unlink()
                    
                added_count += 1
                await self.sources_manager.report_success(book.source)
                
        logger.success(f"Queue replenishment process finished. Added {added_count} post(s) to queue.")
        return added_count
