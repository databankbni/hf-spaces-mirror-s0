from services.market_service import market_provider
import json

try:
    print("Fetching top funds...")
    funds = market_provider.get_top_funds()
    print(f"Count: {len(funds)}")
    print(json.dumps(funds, indent=2, default=str))
except Exception as e:
    print(f"Error: {e}")
