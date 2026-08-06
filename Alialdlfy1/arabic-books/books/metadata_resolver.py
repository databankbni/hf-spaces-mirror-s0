import re
import logging
import fitz
from pathlib import Path
from typing import Dict, Any, Optional
from core.models import Book
from books.fingerprint import normalize_arabic

logger = logging.getLogger("BOOK")

class BookMetadataResolver:
    @staticmethod
    def clean_text_field(text: str) -> str:
        """
        Cleans title or author from common trash words, years, websites, and file extensions.
        """
        if not text:
            return ""
            
        # Remove file extension
        text = re.sub(r"\.pdf$", "", text, flags=re.IGNORECASE)
        
        # Remove website domains/URLs
        text = re.sub(r"(https?://)?(www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,6}(/[a-zA-Z0-9-_]+)*", "", text)
        text = re.sub(r"[a-zA-Z0-9-]+\.(org|com|net|info|edu|gov|ly|iq|eg|sa|me|site|online|club)", "", text, flags=re.IGNORECASE)
        
        # Remove years (4-digit numbers starting with 1 or 2, e.g. 1999, 2026) or Hijri years (3-4 digits followed by هـ)
        text = re.sub(r"\b(19|20)\d{2}\b", "", text)
        text = re.sub(r"\b\d{3,4}\s*هـ?\b", "", text)
        
        # Remove common PDF/Scan keywords and generic tags
        trash_words = [
            "نسخة", "مصورة", "كاملة", "كامل", "تحميل", "كتاب", "رابط", "مكتبة", "مجلد", "جزء",
            "pdf", "scan", "archive", "ocr", "v2", "final", "printed", "طبعة", "جديدة", "ملون",
            "ملونة", "تنزيل", "قراءة", "اونلاين", "موقع", "حصريا", "حصري", "مجهول"
        ]
        for word in trash_words:
            text = re.sub(rf"\b{word}\b", "", text, flags=re.IGNORECASE)
            text = text.replace(word, "")
            
        # Clean extra symbols, dashes, underscores, brackets
        text = re.sub(r"[_#\-+:*?\"<>|\[\]()【】]", " ", text)
        
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def is_arabic_text(text: str) -> bool:
        """Verifies if the text contains at least one Arabic character."""
        if not text:
            return False
        return bool(re.search(r"[\u0600-\u06FF]", text))

    @staticmethod
    def is_chinese_or_placeholder(text: str) -> bool:
        """Returns True if the text contains Chinese characters or common placeholder strings."""
        if not text:
            return False
        if re.search(r"[\u4e00-\u9fff]", text):
            return True
        placeholders = ["unknown", "anonymous", "不知道", "لا أعرف", "مجهول", "unknown author", "غير معروف"]
        if any(p in text.lower() for p in placeholders):
            return True
        return False

    @staticmethod
    def extract_isbn(text: str) -> Optional[str]:
        """
        Attempts to extract ISBN from book text.
        """
        if not text:
            return None
        isbn_patterns = [
            r"ISBN\s*[-:]?\s*(97[89][-\s]?)?\d[-\s]?\d{3}[-\s]?\d{5}[-\s]?\d",
            r"ISBN\s*[-:]?\s*\d{1,5}[-\s]?\d{1,7}[-\s]?\d{1,6}[-\s]?[\dX]"
        ]
        for pattern in isbn_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                clean_isbn = "".join(c for c in match.group(0) if c.isdigit() or c.upper() == 'X')
                if len(clean_isbn) >= 9:
                    return clean_isbn
        return None

    @classmethod
    async def resolve(cls, book: Book, pdf_path: Path, val_result: Dict[str, Any], ai_service, repo) -> Dict[str, Any]:
        """
        Resolves the most accurate title, author, translator, and verifier from all metadata sources.
        """
        # 1. Fetch PDF internal metadata
        pdf_title = ""
        pdf_author = ""
        try:
            doc = fitz.open(pdf_path)
            meta = doc.metadata or {}
            pdf_title = meta.get("title", "")
            pdf_author = meta.get("author", "")
            doc.close()
        except Exception as e:
            logger.warning(f"Failed to read PDF metadata for resolver: {e}")

        # 2. Extract intro text sample
        from books.validator import extract_book_intro_text
        intro_text = extract_book_intro_text(pdf_path, max_pages=8)

        # 3. Extract ISBN
        combined_text = f"Metadata Description:\n{book.description or ''}\n\nPDF Extract:\n{intro_text or ''}"
        isbn = cls.extract_isbn(combined_text)

        # 4. Compile inputs for scoring prompt
        file_name_clean = cls.clean_text_field(pdf_path.name)
        scraper_title_clean = cls.clean_text_field(book.title)
        scraper_author_clean = cls.clean_text_field(book.author)
        pdf_title_clean = cls.clean_text_field(pdf_title)
        pdf_author_clean = cls.clean_text_field(pdf_author)

        cover_path_str = str(val_result["cover_path"]) if val_result.get("cover_path") else None

        # Build prompt for AI
        system_prompt = (
            "You are the core Book Metadata Resolver for an Arabic enterprise cataloging system.\n"
            "Compare all metadata inputs from different sources, analyze the cover page image (if present), and select the most accurate Arabic Title, Author, Translator, and Verifier.\n"
            "SCORING PRIORITY RULES:\n"
            "1. Cover page image visual text (attached) is the absolute highest priority. Read it carefully.\n"
            "2. PDF Internal Title/Author is second priority (only if in valid Arabic).\n"
            "3. Scraper/Source metadata is third priority.\n"
            "4. File Name is the lowest fallback priority.\n\n"
            "CLEANING RULES:\n"
            "- Determine the real book title (e.g. 'الأربعين في أصول الدين').\n"
            "- Ignore cataloging series like 'كتب الهيئة العامة' or 'مجموعات...'.\n"
            "- Translate or transliterate names written in English to clean Arabic.\n"
            "- Extract the Translator (المترجم) if it is a translated book. Otherwise use an empty string.\n"
            "- Extract the Verifier/Editor (المحقق / المدقق / الشارح / المراجع / الشارح) if present. Otherwise use an empty string.\n\n"
            "Output format MUST be strictly JSON (no backticks, no extra text, just raw JSON):\n"
            "{\n"
            "  \"title\": \"Arabic Title\",\n"
            "  \"author\": \"Arabic Author\",\n"
            "  \"translator\": \"Arabic Translator or empty string\",\n"
            "  \"verifier\": \"Arabic Verifier or empty string\"\n"
            "}"
        )

        user_prompt = (
            f"Metadata Inputs for Evaluation:\n"
            f"- File Name (cleaned): '{file_name_clean}'\n"
            f"- Scraper Source Title: '{scraper_title_clean}' | Author: '{scraper_author_clean}'\n"
            f"- PDF Internal Title: '{pdf_title_clean}' | Author: '{pdf_author_clean}'\n"
            f"- ISBN: '{isbn or ''}'\n"
            f"- Sample Pages Extract: {intro_text[:1500]}\n"
        )

        resolved_meta = {}
        try:
            resolved_meta = await ai_service.extract_title_author_from_text(user_prompt, cover_path_str)
        except Exception as e:
            logger.error(f"AI metadata resolver call failed: {e}")

        # Require AI to successfully verify/resolve the title to prevent wrong fallback publishing
        if not resolved_meta or not resolved_meta.get("title"):
            logger.error("AI failed to resolve/verify book title from cover or text. Skipping book to prevent wrong metadata publishing.")
            raise ValueError("AI failed to resolve title metadata.")

        res_title = cls.clean_text_field(resolved_meta.get("title"))
        res_author = cls.clean_text_field(resolved_meta.get("author") or book.author)
        res_translator = cls.clean_text_field(resolved_meta.get("translator") or "")
        res_verifier = cls.clean_text_field(resolved_meta.get("verifier") or "")

        # Check if resolved title is a generic catalog indicator
        GENERIC_KEYWORDS = [
            "كتب الهيئة", "مجموعة", "مقدمات وقائمة", "مكتبة", "منشورات", "ديوان", "مجلة", "معرض",
            "قائمة المحتويات", "كتب في التراجم", "كتب التراجم", "كتب متنوعة", "كتب في", "مخطوطات",
            "مؤلفات", "سلسلة كتب"
        ]
        if any(gk in res_title for gk in GENERIC_KEYWORDS):
            logger.error(f"Resolved book title '{res_title}' is a generic catalog title. Rejecting.")
            raise ValueError("Resolved title is a generic catalog name.")

        # 5. Strict Language Check
        if not cls.is_arabic_text(res_title):
            logger.error(f"Resolved book title '{res_title}' does not contain Arabic text. Rejecting book.")
            raise ValueError("Resolved title is not in Arabic.")

        # Strip placeholder words
        if cls.is_chinese_or_placeholder(res_title):
            logger.error(f"Resolved book title '{res_title}' contains placeholders or Chinese characters. Rejecting.")
            raise ValueError("Resolved title contains invalid placeholder/foreign text.")

        if cls.is_chinese_or_placeholder(res_author):
            res_author = cls.clean_text_field(book.author)
            if cls.is_chinese_or_placeholder(res_author):
                res_author = "غير معروف"

        return {
            "title": res_title,
            "author": res_author,
            "translator": res_translator if not cls.is_chinese_or_placeholder(res_translator) else "",
            "verifier": res_verifier if not cls.is_chinese_or_placeholder(res_verifier) else "",
            "isbn": isbn,
            "page_count": val_result.get("page_count", 0),
            "intro_text": intro_text
        }
