
import sys
sys.path.append('backend')
from services.market_service import market_provider

print("Fetching Stock Lists (TradingView)...")
stocks = market_provider.get_stock_markets()
print(f"Total: {len(stocks)}")
if stocks:
    print("First 3:")
    for s in stocks[:3]:
        print(f"[{s['symbol']}] {s['price']} | Signal: {s['recommendation']}")

print("\nFetching Forex...")
fx = market_provider.get_tcmb_currencies()
if fx: print(fx[0])
