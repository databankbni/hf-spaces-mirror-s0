import os
from dotenv import load_dotenv

load_dotenv(override=True)

MODEL = os.getenv("MODEL", "gpt-4o-mini")  # default to gpt-4o-mini if MODEL is not set

NO_OF_CLARIFYING_QUESTIONS = 3
NO_OF_SEARCHES = 3

# Notification settings: send an email when SEND_EMAIL is true, otherwise push a Pushover alert.
SEND_EMAIL = os.getenv("SEND_EMAIL", "false").strip().lower() == "true"
USER_EMAIL = os.environ.get("USER_EMAIL", "anurupborah2001@gmail.com")

PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")
