from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO)

from chatbot.rag import refresh_product_db

print("Syncing WooCommerce products to Chroma DB...")
store = refresh_product_db()

if store:
    count = store._collection.count()
    print(f"\n✅ Sync complete! {count} products indexed in Chroma DB.")
else:
    print("\n❌ Sync failed - check WooCommerce connection.")