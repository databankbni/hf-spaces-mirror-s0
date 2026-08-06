"""
Sala AI - Facebook Graph API Data Source
Pulls posts + comments from your own sala.lk Facebook Page (legitimate, official API)
"""

import os
import requests

FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
GRAPH_API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def get_recent_posts(limit=25):
    """Fetch recent posts from the Page."""
    url = f"{BASE_URL}/{FB_PAGE_ID}/posts"
    params = {
        "access_token": FB_PAGE_ACCESS_TOKEN,
        "fields": "id,message,created_time,permalink_url",
        "limit": limit,
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json().get("data", [])


def get_comments_for_post(post_id, limit=100):
    """Fetch all comments for a given post (handles pagination)."""
    url = f"{BASE_URL}/{post_id}/comments"
    params = {
        "access_token": FB_PAGE_ACCESS_TOKEN,
        "fields": "id,message,from,created_time,like_count",
        "limit": limit,
    }
    all_comments = []
    while url:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        all_comments.extend(data.get("data", []))
        url = data.get("paging", {}).get("next")
        params = {}  # next url already has params embedded
    return all_comments


def get_all_recent_comments(post_limit=25, comment_limit=100):
    """
    Convenience function: pulls recent posts + all their comments.
    Returns a flat list of comment dicts with post context attached.
    """
    posts = get_recent_posts(limit=post_limit)
    all_comments = []
    for post in posts:
        comments = get_comments_for_post(post["id"], limit=comment_limit)
        for c in comments:
            c["post_id"] = post["id"]
            c["post_message"] = post.get("message", "")
        all_comments.extend(comments)
    return all_comments


if __name__ == "__main__":
    comments = get_all_recent_comments(post_limit=5)
    print(f"Fetched {len(comments)} comments")
    for c in comments[:3]:
        print(f"- {c.get('from', {}).get('name', 'Unknown')}: {c.get('message', '')[:80]}")
