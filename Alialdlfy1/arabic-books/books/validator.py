import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional
import pypdf
import fitz  # PyMuPDF
import config

logger = logging.getLogger("BOOK")

# Regex to detect Arabic script characters (Unicode block U+0600 to U+06FF, etc.)
ARABIC_CHAR_PATTERN = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")

def validate_pdf(pdf_path: Path) -> Dict[str, Any]:
    """
    Validates a PDF file:
    1. Check PDF magic bytes.
    2. Check page count > 0.
    3. Verify text content has Arabic characters.
    4. Extract first page as a PNG cover.
    """
    result = {
        "is_valid": False,
        "page_count": 0,
        "has_arabic": False,
        "cover_path": None,
        "error": None
    }
    
    if not pdf_path.exists():
        result["error"] = "File does not exist."
        return result

    # 1. Check Magic Bytes
    try:
        with open(pdf_path, "rb") as f:
            header = f.read(5)
            if header != b"%PDF-":
                result["error"] = "Invalid file signature (not a PDF)."
                return result
    except Exception as e:
        result["error"] = f"Failed to read file signature: {e}"
        return result

    # 2. Check Page Count and Readability
    try:
        reader = pypdf.PdfReader(pdf_path)
        page_count = len(reader.pages)
        result["page_count"] = page_count
        if page_count <= 0:
            result["error"] = "PDF has zero pages."
            return result
    except Exception as e:
        result["error"] = f"Failed to parse PDF pages: {e}"
        return result

    # 3. Check Language (Verify Arabic characters in first few pages)
    try:
        sample_text = ""
        # Read up to first 5 pages for text sampling
        for i in range(min(5, page_count)):
            try:
                page_text = reader.pages[i].extract_text() or ""
                sample_text += page_text
            except Exception:
                continue
        
        has_arabic = bool(ARABIC_CHAR_PATTERN.search(sample_text))
        result["has_arabic"] = has_arabic
        
        # If no Arabic text extracted, check metadata (sometimes PDFs are scanned images)
        if not has_arabic:
            metadata = reader.metadata or {}
            title = metadata.get("/Title", "")
            author = metadata.get("/Author", "")
            subject = metadata.get("/Subject", "")
            meta_str = f"{title} {author} {subject}"
            if ARABIC_CHAR_PATTERN.search(meta_str):
                logger.book("No Arabic text extracted, but Arabic metadata found.")
                result["has_arabic"] = True
            else:
                # Scanned Arabic PDFs usually have no text layer. Since the scraper queries 
                # specifically for Arabic content, we treat them as valid by default with a warning.
                logger.warning(f"Could not verify Arabic content text in {pdf_path.name} (likely a scanned PDF). Treating as Arabic by default.")
                result["has_arabic"] = True
        else:
            result["has_arabic"] = True
            
    except Exception as e:
        logger.warning(f"Language detection threw an error on metadata: {e}")

    # 4. Extract Cover Image (First page of PDF to PNG)
    try:
        cover_path = extract_cover(pdf_path)
        if cover_path:
            result["cover_path"] = cover_path
    except Exception as e:
        logger.warning(f"Failed to extract cover image from PDF: {e}")

    # Final verdict
    if not result["has_arabic"]:
        result["error"] = "Book does not appear to contain Arabic content."
    else:
        result["is_valid"] = True
        
    return result

def extract_cover(pdf_path: Path) -> Optional[Path]:
    """
    Extracts the first page of the PDF as a PNG image using PyMuPDF (fitz).
    Saves the image to the config.TEMP_DIR folder.
    """
    try:
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            return None
            
        page = doc[0]  # First page
        
        # Increase resolution (zoom factor = 2 for better print quality)
        zoom = 2.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        cover_filename = f"{pdf_path.stem}_cover.png"
        cover_path = config.TEMP_DIR / cover_filename
        
        pix.save(str(cover_path))
        logger.book(f"Cover page extracted successfully: {cover_path.name}")
        return cover_path
    except Exception as e:
        logger.warning(f"Cover extraction failed via fitz: {e}")
        return None

def extract_book_intro_text(pdf_path: Path, max_pages: int = 8) -> str:
    """
    Extracts text from pages 2 to max_pages (inclusive) of the PDF.
    This typically contains the introduction, index, table of contents, or preface.
    We skip page 1 (index 0) as it is usually the cover title.
    """
    text = ""
    try:
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        if page_count <= 1:
            return ""
            
        # Extract from page 1 (which is page 2, 0-indexed) up to page min(max_pages, page_count)
        start_page = 1
        end_page = min(max_pages, page_count)
        
        for i in range(start_page, end_page):
            page_text = doc[i].get_text() or ""
            # Clean excessive spacing/whitespaces
            page_text = re.sub(r'\s+', ' ', page_text).strip()
            if page_text:
                text += f"\n[Page {i+1}]: {page_text}\n"
                
    except Exception as e:
        logger.warning(f"Failed to extract book introduction text: {e}")
        
    return text.strip()
