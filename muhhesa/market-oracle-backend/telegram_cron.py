import os
import sys

# Ensure backend directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from telegram_notifier import save_config, broadcast_verdict_change
from oracle import get_verdict

def main():
    print("[Telegram Cron] Starting autonomous Market Oracle analysis...")
    
    # 1. Inject GitHub Secrets if they exist
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if bot_token and chat_id:
        print("[Telegram Cron] Injecting credentials from Environment Variables...")
        save_config(bot_token, chat_id)
    else:
        print("[Telegram Cron] Using existing local configuration...")
        
    # 2. Run Heavy Macro Analysis (Takes ~40 seconds)
    print("[Telegram Cron] Fetching macro data and running Oracle Engine...")
    try:
        result = get_verdict()
    except Exception as e:
        print(f"[Telegram Cron] Error running oracle engine: {str(e)}")
        sys.exit(1)
    
    # 3. Broadcast to Telegram
    print("[Telegram Cron] Broadcasting verdict to Telegram...")
    response = broadcast_verdict_change(result)
    
    if response.get("status") == "success":
        print("[Telegram Cron] Successfully delivered message to Telegram.")
    else:
        print(f"[Telegram Cron] Error: {response.get('message')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
