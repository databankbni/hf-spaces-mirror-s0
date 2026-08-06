import hashlib
import re
from pathlib import Path
import logging

logger = logging.getLogger("BOOK")

# Arabic unicode character ranges for diacritics (tashkeel)
TASHKEEL_PATTERN = re.compile(r"[\u064B-\u0652\u0670]")

def normalize_arabic(text: str) -> str:
    """
    Normalizes Arabic text to make string comparison robust against spelling variations.
    - Strips tashkeel (diacritics).
    - Normalizes alef forms (أ, إ, آ) to plain alef (ا).
    - Normalizes ta marbuta (ة) to heh (ه).
    - Normalizes yeh (ى) to dotless/dotted equivalent (ي).
    - Removes punctuation, symbols, and extra whitespace.
    """
    if not text:
        return ""
        
    text = text.strip().lower()
    
    # Remove diacritics
    text = TASHKEEL_PATTERN.sub("", text)
    
    # Normalize Alef forms
    text = re.sub(r"[أإآ]", "ا", text)
    
    # Normalize Ta Marbuta to Heh
    text = re.sub(r"ة", "ه", text)
    
    # Normalize Yeh forms
    text = re.sub(r"ى", "ي", text)
    
    # Remove non-alphanumeric characters (excluding spaces)
    # We keep Arabic letters, numbers, and basic English letters
    text = re.sub(r"[^\w\s\u0621-\u064A\u0660-\u0669]", "", text)
    
    # Normalize multiple spaces to a single space
    text = re.sub(r"\s+", " ", text).strip()
    
    return text

def calculate_file_sha256(file_path: Path) -> str:
    """
    Calculates the SHA-256 checksum of a file.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks of 64KB
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def generate_fingerprint(title: str, author: str, file_hash: str) -> str:
    """
    Generates a unique fingerprint for a book by hashing normalized title, author, and file hash.
    Format: sha256(norm_title + "_" + norm_author + "_" + file_hash)
    """
    norm_title = normalize_arabic(title)
    norm_author = normalize_arabic(author)
    
    combined_str = f"{norm_title}_{norm_author}_{file_hash}"
    fingerprint = hashlib.sha256(combined_str.encode("utf-8")).hexdigest()
    
    logger.debug(f"Generated fingerprint for '{title}' (normalized: '{norm_title}' by '{norm_author}'): {fingerprint}")
    return fingerprint
