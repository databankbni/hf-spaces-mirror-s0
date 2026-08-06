
import sys
sys.path.append('backend')
from services.market_service import market_provider

print("Fetching AAPL Details (Yahoo)...")
details = market_provider.get_asset_detail("AAPL")
print(details)

print("\nFetching THYAO Details (Yahoo)...")
details_tr = market_provider.get_asset_detail("THYAO")
print(details_tr)

print("\nFetching AAPL History (Yahoo)...")
hist = market_provider.get_history("AAPL", "1mo", "1d")
print(f"Candles: {len(hist)}")
if hist: print(hist[0])
