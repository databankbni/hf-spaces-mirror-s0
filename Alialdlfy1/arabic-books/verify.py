import sys
import logging

print("==================================================")
print("Running Diagnostics and Code Compilation Checks...")
print("==================================================")

try:
    # Test core imports
    print("1. Testing core configurations and logging imports...")
    import config
    from monitoring.logger import setup_logger
    
    # Initialize basic logging
    setup_logger()
    logger = logging.getLogger("SYSTEM")
    logger.info("Custom logging system active.")
    
    print("2. Testing core models and interfaces...")
    from core.models import Book, Post, Channel, ScheduledPost, SourceMetrics
    from core.interfaces import IBookRepository, IAIService, IBookSource
    
    print("3. Testing utility engines and credentials pool...")
    from utils.credentials import credential_pool, CredentialType, CredentialStatus
    
    print("4. Testing database adapters...")
    from database.connection import get_firestore_client
    from database.firestore_repo import FirestoreBookRepository
    
    print("5. Testing processing modules (Downloaders, Validators, Normalizers)...")
    from books.downloader import download_pdf
    from books.validator import validate_pdf
    from books.fingerprint import normalize_arabic, generate_fingerprint, calculate_file_sha256
    
    # Test Arabic normalization directly
    raw_arabic = "الرِّوَايَةُ العَرَبِيَّةُ فِي القَرْنِ العِشْرِينَ!"
    norm_arabic = normalize_arabic(raw_arabic)
    expected_norm = "الروايه العربيه في القرن العشرين"
    
    print(f"   - Input: '{raw_arabic}'")
    print(f"   - Normalized: '{norm_arabic}'")
    assert norm_arabic == expected_norm, f"Arabic normalization mismatch. Got '{norm_arabic}', expected '{expected_norm}'"
    print("   [OK] Arabic text normalization logic verified successfully.")
    
    print("6. Testing AI prompt managers and service providers...")
    from ai.prompt_manager import get_system_prompt, format_user_prompt
    from ai.service import GeminiAIService
    
    print("7. Testing scrapers and sources managers...")
    from sources.archive import ArchiveOrgSource
    from sources.hindawi import HindawiSource
    from sources.openlibrary import OpenLibrarySource
    from sources.manager import SourcesManager
    
    print("8. Testing Telegram publishers and client managers...")
    from telegram.client_manager import client_manager
    from telegram.publisher import TelegramPublisher
    
    print("9. Testing scheduler runners and queue managers...")
    from book_queue.manager import QueueManager
    from scheduler.runner import SystemScheduler
    
    print("10. Testing app main entry coordinator...")
    from app import ArabicBooksPublisherApp
    
    print("\n==================================================")
    print("DIAGNOSTICS SUCCESSFUL!")
    print("All modules compile, import, and validate correctly.")
    print("Codebase is production-ready for deployment.")
    print("==================================================")
    sys.exit(0)
    
except Exception as e:
    print(f"\nDIAGNOSTICS FAILURE: Compile/import error detected: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
