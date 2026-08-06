import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
LINKEDIN_DIR = BASE_DIR / "data" / "linkedin"
POSTS_FILE = LINKEDIN_DIR / "posts.md"

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")
PROFILE_URL = os.getenv("LINKEDIN_PROFILE_URL", "https://www.linkedin.com/in/neuralarun/")


def fetch_linkedin_posts_apify():
    if not APIFY_TOKEN or APIFY_TOKEN.startswith("your_"):
        print("[ERROR] Missing APIFY_API_TOKEN in .env file.")
        print("Please sign up at https://apify.com (free plan) and set APIFY_API_TOKEN in .env")
        sys.exit(1)

    print(f"Connecting to Apify LinkedIn Post Scraper for {PROFILE_URL}...")

    # Using Apify's active LinkedIn Profile Posts Scraper actor
    run_url = f"https://api.apify.com/v2/acts/harvestapi~linkedin-profile-posts/run-sync-get-dataset-items?token={APIFY_TOKEN}"

    payload = {
        "profileUrls": [PROFILE_URL],
        "limit": 30
    }

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(run_url, json=payload, headers=headers, timeout=120)
        if response.status_code not in (200, 201):
            print(f"[ERROR] Apify API returned error {response.status_code}: {response.text}")
            sys.exit(1)

        items = response.json()
        print(f"Successfully scraped {len(items)} LinkedIn posts!")
        return items

    except Exception as e:
        print(f"[ERROR] Failed to fetch LinkedIn posts via Apify: {e}")
        sys.exit(1)


def save_posts_to_markdown(items):
    LINKEDIN_DIR.mkdir(parents=True, exist_ok=True)

    def get_item_date(item):
        p = item.get("postedAt", {})
        if isinstance(p, dict):
            return p.get("date") or ""
        return str(item.get("postedAtISO") or item.get("postedDate") or item.get("date") or "")

    # Sort posts chronologically descending (newest post FIRST)
    items.sort(key=get_item_date, reverse=True)

    header = """---
type: linkedin_posts
source: harvestapi_linkedin_scraper
---

# Arun Yadav — LinkedIn Posts & Insights

This file contains public LinkedIn posts and technical insights written by Arun Yadav (@arun-yadav-768052368).

---

"""

    post_blocks = []
    for index, post in enumerate(items, start=1):
        text = post.get("text") or post.get("content") or post.get("postText") or ""
        
        posted_at_info = post.get("postedAt", {})
        if isinstance(posted_at_info, dict):
            date = posted_at_info.get("date", "N/A")[:10]
        else:
            date = str(post.get("postedAtISO") or post.get("postedDate") or post.get("date") or "N/A")[:10]

        url = post.get("url") or post.get("postUrl") or post.get("link") or PROFILE_URL

        if not text.strip():
            continue

        label = "MOST RECENT / LATEST LINKEDIN POST" if index == 1 else f"LinkedIn Post #{index}"
        block = f"""---

## {label}
**Date:** {date}
**Post Title / Status:** {label}
> **Link:** [{url}]({url})

{text.strip()}
"""
        post_blocks.append(block)

    full_md = header + "\n\n".join(post_blocks)

    with open(POSTS_FILE, "w", encoding="utf-8") as f:
        f.write(full_md)

    print(f"Updated {POSTS_FILE} with {len(post_blocks)} clean posts.")


def main():
    print("=" * 60)
    print("ArunCore LinkedIn Auto-Sync Pipeline")
    print("=" * 60)

    items = fetch_linkedin_posts_apify()
    if items:
        save_posts_to_markdown(items)

        # Trigger auto-ingest into ChromaDB
        print("\nTriggering vector ingestion into ChromaDB...")
        import subprocess
        subprocess.run([sys.executable, str(BASE_DIR / "core" / "ingest.py")], check=True)
        print("\n[SUCCESS] LinkedIn posts synced and indexed in ChromaDB successfully!")
    else:
        print("[WARNING] No posts retrieved from Apify.")


if __name__ == "__main__":
    main()
