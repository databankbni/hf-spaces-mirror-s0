
import sys
sys.path.append('backend')
from services.crypto_service import crypto_service

print("Fetcing USDC History from Binance...")
klines = crypto_service.get_history("USDC", "1mo", "1d")

print(f"Total Candles: {len(klines)}")
if klines:
    print("First 3 Candles:")
    for k in klines[:3]:
        print(k)
else:
    print("No data returned")
