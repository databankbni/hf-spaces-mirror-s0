import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from services.twelve_data_service import twelve_data_service

def full_sync():
    load_dotenv()
    print("🚀 Twelve Data Full Sync Başlatılıyor (Hisse, Forex, Emtia)...")
    
    # Twelve Data Service içindeki sync_symbols metodunu çağırıyoruz
    success = twelve_data_service.sync_symbols()
    
    if success:
        print("✅ Senkronizasyon başarıyla tamamlandı.")
        # Kaç tane sembol olduğunu kontrol et
        master_path = "backend/data/twelve_symbols.json"
        if os.path.exists(master_path):
            import json
            with open(master_path, "r") as f:
                data = json.load(f)
                print(f"📊 Toplam Sembol Sayısı: {len(data)}")
    else:
        print("❌ Senkronizasyon başarısız oldu. API anahtarınızı ve limitlerinizi kontrol edin.")

if __name__ == "__main__":
    full_sync()
