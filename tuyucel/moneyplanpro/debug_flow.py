from services.market_service import market_provider

print("--- Debugging TCD ---")
symbol = "TCD"

print(f"1. Is TEFAS Fund? {market_provider._is_tefas_fund(symbol)}")

print("2. Fetching via _fetch_tefas_direct...")
direct = market_provider._fetch_tefas_direct(symbol)
print(f"Direct result: {direct is not None}")
if direct is not None:
    print(direct.head(1))

print("3. Fetching via _fetch_from_tefas_crawler...")
crawler = market_provider._fetch_from_tefas_crawler(symbol)
print(f"Crawler result: {crawler is not None}")

print("4. Fetching via _fetch_fund_from_investpy...")
investpy = market_provider._fetch_fund_from_investpy(symbol)
print(f"Investpy result: {investpy is not None}")

print("5. Full get_asset_detail...")
detail = market_provider.get_asset_detail(symbol)
print(f"Detail: {detail}")
