import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from pathlib import Path
import config

# Define custom logging levels
LEVEL_DATABASE = 21
LEVEL_BOOK = 22
LEVEL_QUEUE = 23
LEVEL_SYSTEM = 24
LEVEL_SUCCESS = 25
LEVEL_AI = 26
LEVEL_TELEGRAM = 27

logging.addLevelName(LEVEL_DATABASE, "DATABASE")
logging.addLevelName(LEVEL_BOOK, "BOOK")
logging.addLevelName(LEVEL_QUEUE, "QUEUE")
logging.addLevelName(LEVEL_SYSTEM, "SYSTEM")
logging.addLevelName(LEVEL_SUCCESS, "SUCCESS")
logging.addLevelName(LEVEL_AI, "AI")
logging.addLevelName(LEVEL_TELEGRAM, "TELEGRAM")

# ANSI color codes for console formatting
COLORS = {
    "INFO": "\033[94m",       # Blue
    "SUCCESS": "\033[92m",    # Green
    "WARNING": "\033[93m",    # Yellow
    "ERROR": "\033[91m",      # Red
    "DATABASE": "\033[96m",   # Cyan
    "BOOK": "\033[35m",       # Magenta
    "QUEUE": "\033[95m",      # Light Magenta
    "SYSTEM": "\033[97m",     # White
    "AI": "\033[33m",         # Orange/Brown
    "TELEGRAM": "\033[36m",   # Dark Cyan
    "RESET": "\033[0m"
}

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        levelname = record.levelname
        color = COLORS.get(levelname, COLORS["RESET"])
        reset = COLORS["RESET"]
        
        # Format time and levelname in color
        record.levelname = f"{color}[{levelname}]{reset}"
        
        # If we have a custom name or category, prepended
        original_msg = record.msg
        record.msg = f"{color}{original_msg}{reset}"
        
        result = super().format(record)
        
        # Restore record values
        record.levelname = levelname
        record.msg = original_msg
        return result

class FileFormatter(logging.Formatter):
    def format(self, record):
        # Plain text for files (no ANSI colors)
        return super().format(record)

def setup_logger():
    # Base logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # Log everything, filters are at handler levels
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Ensure log directory exists
    log_dir = Path(config.LOG_DIR)
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "publisher.log"

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_fmt = "%(asctime)s %(levelname)s %(message)s"
    console_handler.setFormatter(ColoredFormatter(console_fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(console_handler)

    # File Handler with Rotation (512KB size limit, 2 backups max)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=2,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    file_handler.setFormatter(FileFormatter(file_fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(file_handler)

    # Define helper methods on logging module/class dynamically
    def success(self, msg, *args, **kwargs):
        self.log(LEVEL_SUCCESS, msg, *args, **kwargs)

    def database(self, msg, *args, **kwargs):
        self.log(LEVEL_DATABASE, msg, *args, **kwargs)

    def book(self, msg, *args, **kwargs):
        self.log(LEVEL_BOOK, msg, *args, **kwargs)

    def queue(self, msg, *args, **kwargs):
        self.log(LEVEL_QUEUE, msg, *args, **kwargs)

    def system(self, msg, *args, **kwargs):
        self.log(LEVEL_SYSTEM, msg, *args, **kwargs)

    def ai(self, msg, *args, **kwargs):
        self.log(LEVEL_AI, msg, *args, **kwargs)

    def telegram(self, msg, *args, **kwargs):
        self.log(LEVEL_TELEGRAM, msg, *args, **kwargs)

    logging.Logger.success = success
    logging.Logger.database = database
    logging.Logger.book = book
    logging.Logger.queue = queue
    logging.Logger.system = system
    logging.Logger.ai = ai
    logging.Logger.telegram = telegram

    return logger

def rotate_and_clean_logs():
    """
    Runs file retention and time-based rotation.
    Cleans logs older than config.LOG_RETENTION_DAYS.
    """
    sys_logger = logging.getLogger("SYSTEM")
    log_dir = Path(config.LOG_DIR)
    
    if not log_dir.exists():
        return
        
    sys_logger.system("Running log maintenance (rotation & cleanup)...")
    now = datetime.now()
    retention_limit = now - timedelta(days=config.LOG_RETENTION_DAYS)
    
    deleted_count = 0
    for file in log_dir.glob("publisher.log*"):
        try:
            file_mtime = datetime.fromtimestamp(file.stat().st_mtime)
            if file_mtime < retention_limit:
                file.unlink()
                deleted_count += 1
        except Exception as e:
            sys_logger.error(f"Failed to clean log file {file.name}: {e}")
            
    if deleted_count > 0:
        sys_logger.success(f"Log cleanup completed. Deleted {deleted_count} file(s) older than {config.LOG_RETENTION_DAYS} days.")
    else:
        sys_logger.system("No log files expired retention limit.")

# Initialize logging immediately
setup_logger()
