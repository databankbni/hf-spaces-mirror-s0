
import sys
sys.path.append('backend')
from services.fmp_service import fmp_service

print("Fetching Dynamic Stocks (Score Model)...")
stocks = fmp_service.get_stocks_dynamic()
print(f"Total Stocks: {len(stocks)}")
if stocks:
    print("Top 3 Stocks:")
    for s in stocks[:3]:
        print(f"{s['symbol']} - Cap: {s['market_cap']} - Price: {s['price']}")

print("\nFetching Commodities...")
com = fmp_service.get_commodities()
print(f"Items: {len(com)}")
if com: print(com[0])

print("\nFetching Forex...")
fx = fmp_service.get_forex()
print(f"Items: {len(fx)}")
if fx: print(fx[0])
