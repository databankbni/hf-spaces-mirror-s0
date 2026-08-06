import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import re

# =============================================================================
# The Market Oracle - Live News Sentiment Engine
# Fetches RSS feeds and calculates sentiment based on keywords
# =============================================================================

# Daftar RSS Feed Berita Ekonomi
RSS_FEEDS = [
    "https://www.cnbcindonesia.com/market/rss",
    "https://www.antaranews.com/rss/ekonomi-bisnis.xml"
]

BULLISH_WORDS = [
    "naik", "menguat", "reli", "cuan", "laba", "profit", "rekor", "bullish",
    "untung", "investasi", "meroket", "tumbuh", "positif", "optimis", "lonjakan",
    "pemulihan", "bantuan", "stimulus", "surplus"
]

BEARISH_WORDS = [
    "turun", "melemah", "anjlok", "ambles", "rugi", "boncos", "bearish",
    "resesi", "krisis", "phk", "inflasi", "merah", "negatif", "pesimis",
    "ancaman", "bahaya", "waspada", "jatuh", "jeblok", "defisit"
]

def parse_rss_feed(url):
    """Fetch and parse RSS feed returning list of dictionaries."""
    headlines = []
    try:
        response = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            # Find all item tags
            for item in root.findall('.//item'):
                title = item.find('title')
                link = item.find('link')
                pubDate = item.find('pubDate')
                if title is not None:
                    headlines.append({
                        "title": title.text.strip(),
                        "link": link.text.strip() if link is not None else "",
                        "date": pubDate.text.strip() if pubDate is not None else datetime.now().isoformat()
                    })
    except Exception as e:
        print(f"[NewsSentiment] Error fetching {url}: {e}")
    return headlines

def analyze_news_sentiment(raw_data=None):
    """
    Fetch news from RSS feeds, calculate sentiment score, and format output.
    Returns dict similar to the old mentor_analyzer but for news.
    """
    all_headlines = []
    for feed in RSS_FEEDS:
        all_headlines.extend(parse_rss_feed(feed))
        
    # Jika gagal fetch semua (misal no internet), gunakan mock data
    if not all_headlines:
        all_headlines = [
            {"title": "IHSG Ditutup Menguat, Sektor Perbankan Jadi Penopang", "link": "#", "date": datetime.now().isoformat()},
            {"title": "Waspada Inflasi Global, Investor Mulai Melirik Emas", "link": "#", "date": datetime.now().isoformat()},
            {"title": "Harga Batubara Anjlok, Emiten Energi Tertekan", "link": "#", "date": datetime.now().isoformat()},
            {"title": "Ekonomi RI Tumbuh 5%, Rekor Baru di Tengah Ketidakpastian", "link": "#", "date": datetime.now().isoformat()},
        ]
        
    # Analisis sentimen tiap headline
    scored_headlines = []
    total_score = 0.0
    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    
    # Ambil maksimal 20 berita terbaru untuk dianalisis
    for item in all_headlines[:20]:
        title_lower = item["title"].lower()
        
        # Hitung kemunculan kata kunci
        bull_hits = sum(1 for word in BULLISH_WORDS if re.search(rf'\b{word}\b', title_lower))
        bear_hits = sum(1 for word in BEARISH_WORDS if re.search(rf'\b{word}\b', title_lower))
        
        if bull_hits > bear_hits:
            item_sentiment = "Bullish"
            item_score = 0.5 + (0.1 * bull_hits)
            bullish_count += 1
        elif bear_hits > bull_hits:
            item_sentiment = "Bearish"
            item_score = -0.5 - (0.1 * bear_hits)
            bearish_count += 1
        else:
            item_sentiment = "Netral"
            item_score = 0.0
            neutral_count += 1
            
        total_score += item_score
        
        scored_headlines.append({
            "title": item["title"],
            "link": item["link"],
            "date": item["date"],
            "sentiment": item_sentiment
        })
        
    # Rata-rata skor dari semua berita (maksimal range -2.0 hingga +2.0)
    avg_score = total_score / len(scored_headlines) if scored_headlines else 0.0
    # Amplifikasi sedikit agar pergerakan lebih terasa
    final_score = max(-2.0, min(2.0, avg_score * 2.5))
    
    if final_score >= 0.5:
        overall_label = "Bullish"
    elif final_score <= -0.5:
        overall_label = "Bearish"
    else:
        overall_label = "Netral"
        
    # Berikan warning jika kondisi ekstrem
    warnings = []
    if final_score <= -1.0:
        warnings.append("Berita pasar didominasi oleh kepanikan. Hati-hati terhadap volatilitas tinggi.")
    elif final_score >= 1.0:
        warnings.append("Berita pasar sangat optimis (Euphoria). Rentan terhadap profit taking.")

    return {
        "score": round(final_score, 2),
        "label": overall_label,
        "total_news": len(scored_headlines),
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "headlines": scored_headlines[:10], # Kirim 10 terbaik ke frontend
        "warnings": warnings,
    }

if __name__ == "__main__":
    result = analyze_news_sentiment()
    print("Skor Keseluruhan:", result["score"], f"({result['label']})")
    print("Statistik:", f"Bullish={result['bullish_count']}, Bearish={result['bearish_count']}, Netral={result['neutral_count']}")
    print("\n10 Headline Terbaru:")
    for h in result["headlines"]:
        print(f"[{h['sentiment']}] {h['title']}")
