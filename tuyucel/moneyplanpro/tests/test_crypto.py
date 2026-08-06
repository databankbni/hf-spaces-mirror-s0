
import sys
# Backend dizinini path'e ekle
sys.path.append('backend')

from services.crypto_service import crypto_service

print("Fetching Crypto Data from Binance...")
coins = crypto_service.get_top_coins(limit=10)

print(f"Total Coins Fetched: {len(coins)}")
for coin in coins:
    print(f"{coin['symbol']}: ${coin['price']} ({coin['change_24h']}%) - Vol: {coin['volume']:,.0f}")
