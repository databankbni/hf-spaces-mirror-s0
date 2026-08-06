import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from services.market_service import market_provider

def debug_commodities():
    load_dotenv()
    print("Fetching commodities via market_provider...")
    data = market_provider.get_commodity_markets()
    print(f"Total items received: {len(data)}")
    for item in data:
        print(f"Symbol: {item.get('symbol')}, Price: {item.get('price')}, Source: {item.get('source', 'Unknown')}")

if __name__ == "__main__":
    debug_commodities()
