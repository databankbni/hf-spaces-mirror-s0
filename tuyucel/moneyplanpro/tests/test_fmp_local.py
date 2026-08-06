
import sys
sys.path.append('backend')
from services.fmp_service import fmp_service
import json

def print_pretty(data):
    print(json.dumps(data, indent=2, default=str))

print("=== FMP LOCAL TEST BAŞLIYOR ===")
print("Senin IP'den istek atılıyor...\n")

# 1. TEST: Dinamik Liste (Screener)
print("--- 1. Screener Testi (Hacim Sıralı) ---")
try:
    stocks = fmp_service.get_stocks_dynamic()
    print(f"Toplam Hisse Sayısı: {len(stocks)}")
    if stocks:
        print("İlk 3 Hisse (En Yüksek Hacim):")
        for s in stocks[:3]:
            print(f"- {s['symbol']} | Fiyat: {s['price']} | Hacim: {s['volume']:,.0f}")
    else:
        print("!!! LİSTE BOŞ GELDİ (API Sorunu veya Limit) !!!")
except Exception as e:
    print(f"HATA: {e}")

# 2. TEST: Fallback Kontrolü (Manuel Batch)
# Screener çalışsa bile tekil veri çekmeyi deneyelim
print("\n--- 2. Batch Quote Testi (AAPL, THYAO.IS) ---")
try:
    quotes = fmp_service._fetch_quotes_batch(["AAPL", "THYAO.IS"])
    print(f"Gelen Veri Sayısı: {len(quotes)}")
    for q in quotes:
         print(f"- {q['symbol']} ({q['name']}): {q['price']}")
except Exception as e:
    print(f"HATA: {e}")

# 3. TEST: Tarihsel Veri (Grafik)
print("\n--- 3. Grafik Verisi Testi (AAPL - 1 Ay) ---")
try:
    hist = fmp_service.get_history("AAPL", "1mo")
    print(f"Gelen Mum Sayısı: {len(hist)}")
    if hist:
        print("İlk Mum Verisi:", hist[0])
        print("Son Mum Verisi:", hist[-1])
    else:
        print("!!! GRAFİK VERİSİ BOŞ (Limit Dolmuş Olabilir) !!!")
except Exception as e:
    print(f"HATA: {e}")

print("\n=== TEST BİTTİ ===")
