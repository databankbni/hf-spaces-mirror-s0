"""
Chạy từ root dự án: python tests/test_tools.py
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "servers"))

def pprint(label, result):
    print(f"\n{'='*50}")
    print(f"  {label}")
    print('='*50)
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ── WEATHER ──────────────────────────────────────────
from weather_server import get_weather
pprint("🌤 Thời tiết Hà Nội", get_weather("Ha Noi"))
pprint("🌤 Thời tiết TP.HCM", get_weather("Ho Chi Minh City"))

# ── VN EXPRESS NEWS ──────────────────────────────────
from news_server import get_news
pprint("📰 Tin mới nhất (3 bài)", get_news(category="latest", limit=3))
pprint("📰 Tin công nghệ (3 bài)", get_news(category="technology", limit=3))

# ── GIÁ VÀNG ─────────────────────────────────────────
from gold_server import get_gold_price
pprint("🪙 Giá vàng", get_gold_price())