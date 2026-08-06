
import sys
sys.path.append('backend')
from services.crypto_service import crypto_service

print("Fetcing BTC Details from Binance...")
details = crypto_service.get_asset_detail("BTC")

print(details)
