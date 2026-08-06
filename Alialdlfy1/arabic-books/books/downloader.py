import asyncio
import logging
import aiohttp
import uuid
from pathlib import Path
import config

logger = logging.getLogger("BOOK")

class DownloadError(Exception):
    pass

class FileTooLargeError(DownloadError):
    pass

async def download_pdf(url: str) -> Path:
    """
    Downloads a PDF file asynchronously from a URL.
    Checks file size limitations and retries on failure.
    """
    retries = config.MAX_DOWNLOAD_RETRIES
    backoff = config.DOWNLOAD_RETRY_BACKOFF_FACTOR
    
    # Generate a unique temp filename
    temp_filename = f"{uuid.uuid4()}.pdf"
    temp_path = config.TEMP_DIR / temp_filename

    # Client headers to mimic browser
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }

    for attempt in range(1, retries + 1):
        try:
            logger.book(f"Downloading PDF from {url} (Attempt {attempt}/{retries})...")
            
            timeout = aiohttp.ClientTimeout(total=config.DOWNLOAD_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as response:
                    if response.status != 200:
                        raise DownloadError(f"HTTP response status {response.status}")
                    
                    # 1. Check Content-Length header if available
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        size_bytes = int(content_length)
                        if size_bytes > config.MAX_BOOK_SIZE_BYTES:
                            raise FileTooLargeError(
                                f"File size from header ({size_bytes} bytes) exceeds limit of {config.MAX_BOOK_SIZE_BYTES} bytes."
                            )
                    
                    # 2. Stream download to limit memory consumption and enforce size limits dynamically
                    total_downloaded = 0
                    with open(temp_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            total_downloaded += len(chunk)
                            if total_downloaded > config.MAX_BOOK_SIZE_BYTES:
                                # Clean up partial download
                                f.close()
                                if temp_path.exists():
                                    temp_path.unlink()
                                raise FileTooLargeError(
                                    f"File size exceeded limit of {config.MAX_BOOK_SIZE_BYTES} bytes during streaming."
                                )
                            f.write(chunk)
                            
            logger.success(f"Successfully downloaded PDF to {temp_path} ({total_downloaded} bytes)")
            return temp_path
            
        except FileTooLargeError as fe:
            logger.error(f"Download failed: {fe}")
            # Do not retry if the file is too large
            if temp_path.exists():
                temp_path.unlink()
            raise
            
        except Exception as e:
            logger.warning(f"Attempt {attempt} failed for URL {url}: {e}")
            if temp_path.exists():
                temp_path.unlink()
                
            if attempt == retries:
                logger.error(f"Failed to download PDF after {retries} attempts.")
                raise DownloadError(f"Failed to download PDF: {e}") from e
            
            # Wait with exponential backoff
            sleep_time = backoff ** attempt
            logger.book(f"Waiting {sleep_time}s before next download attempt...")
            await asyncio.sleep(sleep_time)

    raise DownloadError("Unreachable state in download_pdf")
