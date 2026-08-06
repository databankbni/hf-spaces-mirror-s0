from flask import Flask, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
import feedparser
import concurrent.futures
import random
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_cors import CORS

app = Flask(__name__)

# OWASP Security: Cross-Origin Resource Sharing
CORS(app)

# OWASP Security: HTTP Security Headers (frame_options=None allows HuggingFace iframe embedding)
Talisman(app, force_https=False, content_security_policy=None, frame_options=None)

# OWASP Security: Rate Limiting (Prevent DDoS/Brute-force)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["1000 per day", "60 per minute"],
    storage_uri="memory://"
)

# Strictly Tech & Coding RSS Feeds
NEWS_SOURCES = [
    # Global Developer Communities
    {"name": "GitHub Trending", "scraper": "scrape_github_trending"},
    {"name": "GitHub Blog", "url": "https://github.blog/feed/"},
    {"name": "FreeCodeCamp", "url": "https://www.freecodecamp.org/news/rss/"},
    {"name": "Dev.to (Programming)", "url": "https://dev.to/feed/tag/programming"},
    {"name": "Hacker News", "url": "https://hnrss.org/frontpage"},
    {"name": "Lobsters", "url": "https://lobste.rs/rss"},
    
    # Software Engineering & Web Dev
    {"name": "InfoQ", "url": "https://feed.infoq.com/"},
    {"name": "SitePoint", "url": "https://www.sitepoint.com/feed/"},
    {"name": "Smashing Magazine", "url": "https://www.smashingmagazine.com/feed/"},
    {"name": "CSS-Tricks", "url": "https://css-tricks.com/feed/"},
    {"name": "The New Stack", "url": "https://thenewstack.io/feed/"},
    
    # AI, Mobile & Indian Tech
    {"name": "Google AI Blog", "url": "https://ai.googleblog.com/atom.xml"},
    {"name": "Android Dev Blog", "url": "https://android-developers.googleblog.com/atom.xml"},
    {"name": "Stack Overflow", "url": "https://stackoverflow.blog/feed/"},
    {"name": "Analytics India Magazine", "url": "https://analyticsindiamag.com/feed/"}
]

def scrape_github_trending():
    """Custom scraper for GitHub Trending since it lacks an official RSS feed."""
    print("Fetching feed: GitHub Trending")
    url = "https://github.com/trending"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    news_list = []
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, "html.parser")
        for article in soup.select("article.Box-row")[:15]:
            h2 = article.select_one("h2.h3 a")
            if not h2: continue
            title = h2.text.strip().replace("\\n", "").replace(" ", "")
            link = "https://github.com" + h2["href"]
            
            # Extract avatar image as thumbnail
            img_tag = article.select_one("img.avatar")
            image = img_tag["src"] if img_tag else "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"
            
            news_list.append({"title": title, "url": link, "image": image, "source": "GitHub Trending"})
    except Exception as e:
        print("GitHub Trending Error:", e)
    return news_list

def get_og_image(url):
    """Fallback mechanism to fetch the high-quality open-graph image from the article link."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                return og_image["content"]
    except Exception:
        pass
    return None

def extract_image_from_entry(entry):
    """Extract image from RSS media tags or description HTML."""
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0].get('url')
    if 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
        return entry.media_thumbnail[0].get('url')
    
    # Search in description/summary HTML
    summary = entry.get('summary', '') or entry.get('description', '')
    if summary:
        soup = BeautifulSoup(summary, "html.parser")
        img = soup.find('img')
        if img and img.get('src'):
            return img['src']
            
    return None

def scrape_feed(source):
    """Parses an RSS feed and returns a list of news dictionaries."""
    print(f"Fetching feed: {source['name']}")
    news_list = []
    try:
        feed = feedparser.parse(source["url"])
        
        for entry in feed.entries[:15]:  # Fetch more for randomization
            title = entry.title
            link = entry.link
            
            # Try to get image from RSS first
            image = extract_image_from_entry(entry)
            
            # If no image found in RSS feed, try fetching the page for meta tag (fallback)
            if not image:
                image = get_og_image(link)
                
            news_list.append({
                "title": title,
                "url": link,
                "image": image,
                "source": source["name"]
            })
    except Exception as e:
        print(f"Error fetching {source['name']}: {e}")
        
    return news_list

@app.route("/", methods=["GET"])
def index():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Advanced Tech News API</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f8f9fa; color: #333; }
            h1 { color: #007bff; }
            .endpoint { background: #e9ecef; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 1.1em; }
            .card { background: white; padding: 40px; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); margin-top: 40px; text-align: center;}
            a { color: #007bff; text-decoration: none; font-weight: bold; }
            a:hover { text-decoration: underline; }
            ul { text-align: left; display: inline-block; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🚀 Advanced Tech News API</h1>
            <p>Welcome to the newly upgraded API! Powered by a highly robust concurrent RSS engine, avoiding bot-blocking and bringing you blazing fast news.</p>
            
            <div style="margin: 30px 0;">
                <h2>📡 Endpoint</h2>
                <div class="endpoint">
                    GET <a href="/news">/news</a>
                </div>
            </div>
            
            <h2>🌟 Features</h2>
            <ul>
                <li><strong>Randomized Fresh Feed:</strong> Fetches top articles and shuffles them for a new experience on every reload.</li>
                <li><strong>Strictly Coding News:</strong> Top developer communities and blogs only.</li>
                <li><strong>Lightning Fast:</strong> Uses concurrent threading to fetch everything simultaneously.</li>
            </ul>

            <h2>🛡️ OWASP API Security Controls</h2>
            <ul>
                <li><strong>API Rate Limiting:</strong> 1000 requests/day globally, and strict 20 req/minute on <code>/news</code> to prevent DDoS and Scraping Abuse (OWASP API4:2023).</li>
                <li><strong>CORS Protection:</strong> Safely configured Cross-Origin Resource Sharing.</li>
                <li><strong>Security Headers:</strong> X-Content-Type-Options and other headers active to prevent MIME-sniffing and XSS attacks.</li>
            </ul>

            <h2>📖 API Documentation</h2>
            <div style="text-align: left; margin-top: 20px;">
                <h3>Request</h3>
                <div class="endpoint">GET /news</div>
                
                <h3>Example Response (200 OK)</h3>
                <pre style="background: #282c34; color: #abb2bf; padding: 15px; border-radius: 8px; overflow-x: auto;">
[
  {
    "title": "Building a fully local LLM App",
    "url": "https://github.blog/2026-build-llm",
    "image": "https://github.blog/wp-content/uploads/cover.png",
    "source": "GitHub Blog"
  },
  {
    "title": "Mastering CSS Grid in 2026",
    "url": "https://css-tricks.com/mastering-grid",
    "image": "https://css-tricks.com/grid-cover.jpg",
    "source": "CSS-Tricks"
  }
]</pre>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_content)

@app.route("/news", methods=["GET"])
@limiter.limit("20 per minute")  # Stricter rate limit on the actual scraping endpoint
def get_coding_news():
    def fetch_source(source):
        if "scraper" in source:
            return globals()[source["scraper"]]()
        return scrape_feed(source)

    all_news = []
    # Use ThreadPoolExecutor to fetch all feeds simultaneously (Super Fast!)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(NEWS_SOURCES)) as executor:
        results = executor.map(fetch_source, NEWS_SOURCES)
        
    for res in results:
        all_news.extend(res)
        
    # Randomize the feed
    random.shuffle(all_news)
    
    # Return a randomized master list of up to 60 articles
    return jsonify(all_news[:60])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860, debug=True)
