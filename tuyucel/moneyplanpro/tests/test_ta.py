
import sys
sys.path.append('backend')
from services.ta_service import ta_service

print("Fetching BIST (THYAO) Analysis...")
bist = ta_service.get_analysis("THYAO.IS")
print(bist)

print("\nFetching Crypto (BTC) Analysis...")
crypto = ta_service.get_analysis("BTCUSDT")
print(crypto)

print("\nFetching US (AAPL) Analysis...")
us = ta_service.get_analysis("AAPL")
print(us)
