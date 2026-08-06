import xml.etree.ElementTree as ET
from datetime import datetime
import re
import concurrent.futures
from utils.cache import cache
from utils.network import SafeRequest
from bs4 import BeautifulSoup

class NewsService:
    def __init__(self):
        self.sources = [
            {"name": "Bloomberg HT", "url": "https://www.bloomberght.com/rss", "base_url": "https://www.bloomberght.com", "type": "rss"},
            {"name": "Habertürk", "url": "https://www.haberturk.com/rss/ekonomi.xml", "base_url": "https://www.haberturk.com", "type": "rss"},
            {"name": "Investing", "url": "https://tr.investing.com/rss/news.rss", "base_url": "https://tr.investing.com", "type": "rss"},
            {"name": "Dünya Gazetesi", "url": "https://www.dunya.com/rss", "base_url": "https://www.dunya.com", "type": "rss"}
        ]

    def get_latest_news(self, limit=20):
        """Birden fazla kaynaktan haberleri paralel olarak derler ve cache'ler."""
        cached = cache.get("latest_news")
        if cached:
            return cached[:limit]

        all_news = []
        # Kaynakları paralel olarak çek (Hız optimizasyonu)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.sources)) as executor:
            future_to_source = {
                executor.submit(self._fetch_source, source): source 
                for source in self.sources
            }
            
            for future in concurrent.futures.as_completed(future_to_source):
                try:
                    news_items = future.result()
                    if news_items:
                        all_news.extend(news_items)
                except Exception as e:
                    source = future_to_source[future]
                    print(f"Error fetching news from {source['name']}: {e}")

        # Tarihe göre sırala
        import email.utils
        def parse_date(date_str):
            try:
                if not date_str: return 0
                return email.utils.mktime_tz(email.utils.parsedate_tz(date_str))
            except:
                return 0

        all_news.sort(key=lambda x: parse_date(x.get('pub_date', '')), reverse=True)

        if all_news:
            # Önbelleğe al (15 dakika)
            cache.set("latest_news", all_news, ttl_seconds=900)
        
        return all_news[:limit]

    def _fetch_source(self, source):
        """Tek bir kaynağı çeker (Parallel helper)"""
        if source["type"] == "rss":
            return self._fetch_rss(source["url"], source["name"], source.get("base_url", ""))
        return []

    def _fetch_rss(self, url, source_name, base_url):
        items = []
        try:
            # SafeRequest kullanarak anti-bot önlemlerini aş ve timeout'u düşür
            resp = SafeRequest.get(url, timeout=7)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, 'xml')
                for item in soup.find_all('item'):
                    try:
                        title = item.title.text.strip() if item.title else ""
                        link = item.link.text.strip() if item.link else ""
                        
                        if not title or not link: continue

                        if link and link.startswith('/') and base_url:
                            link = base_url + link

                        # Görsel yakalama
                        image_url = None
                        # enclosure kontrolü
                        enclosure = item.find('enclosure')
                        if enclosure and enclosure.get('url'):
                            image_url = enclosure['url']
                        
                        # Diğer medya tagları
                        if not image_url:
                            media_content = item.find('media:content') or item.find('content')
                            if media_content and media_content.get('url'):
                                image_url = media_content['url']
                        
                        # Description içinden görsel çıkarma (BS4 ile)
                        desc_raw = item.description.text if item.description else ""
                        desc_soup = BeautifulSoup(desc_raw, 'html.parser')
                        
                        if not image_url:
                            img_tag = desc_soup.find('img')
                            if img_tag and img_tag.get('src'):
                                image_url = img_tag['src']
                        
                        if image_url and image_url.startswith('/') and base_url:
                            image_url = base_url + image_url

                        # HTML taglarını temizle
                        clean_desc = desc_soup.get_text(separator=' ').strip()
                        if not clean_desc and desc_raw:
                            clean_desc = re.sub('<[^<]+?>', '', desc_raw).strip()
                            
                        if len(clean_desc) > 300:
                            clean_desc = clean_desc[:300] + "..."

                        pub_date = item.pubDate.text if item.pubDate else ""

                        items.append({
                            "title": title,
                            "link": link,
                            "description": clean_desc.replace('\n', ' ').replace('\r', '').strip(),
                            "pub_date": pub_date,
                            "source": source_name,
                            "image_url": image_url
                        })
                    except Exception as item_err:
                        # Tekil haber hatası tüm listeyi bozmasın
                        continue
        except Exception as e:
            print(f"RSS Fetch Error for {source_name} ({url}): {e}")
        return items

news_service = NewsService()
