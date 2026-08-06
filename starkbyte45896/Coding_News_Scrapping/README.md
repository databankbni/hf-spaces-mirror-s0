---
title: Coding News Scrapping
emoji: 🚀
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# 🚀 Coding News Scraper API

![Hugging Face Space](https://img.shields.io/badge/🤗%20Hugging%20Face-Deployed-yellow)
![Flask](https://img.shields.io/badge/Flask-API-blue)
![Python](https://img.shields.io/badge/Python-3.x-blue)

A powerful, fast, and lightweight web scraping API built with **Flask** and **BeautifulSoup**. It automatically fetches the latest programming and tech-related news, articles, cover images, and links from top developer platforms.

You can view the live deployment and test the UI on Hugging Face Spaces:
👉 **[Coding News Scrapping on Hugging Face](https://huggingface.co/spaces/starkbyte45896/Coding_News_Scrapping)**

## 🌟 Features
- **Aggregated Tech News:** Fetches top stories from 12+ leading coding sites (InfoQ, Hackernoon, Medium, FreeCodeCamp, DZone, and more).
- **Rich Data:** Returns article titles, source links, and thumbnail images for beautiful UI integrations (perfect for masonry or card layouts).
- **Fast & Lightweight:** Built using `requests` and `BeautifulSoup` for quick HTML parsing.
- **RESTful Endpoint:** Easy-to-use JSON response format.

## 📡 API Endpoint

### `GET /news`
Returns a JSON array of the latest tech articles.

**Example Response:**
```json
[
  {
    "title": "State of CSS 2024",
    "url": "https://css-tricks.com/...",
    "image": "https://css-tricks.com/wp-content/...",
    "source": "CSS-Tricks"
  },
  {
    "title": "Stateless MCP for Beginners",
    "url": "https://hackernoon.com/...",
    "image": "https://hackernoon.com/images/...",
    "source": "Hackernoon"
  }
]
```

## 🛠️ Supported Sources
- InfoQ
- Hackernoon
- Medium (Programming tag)
- DZone
- FreeCodeCamp
- CSS-Tricks
- SitePoint
- Android Dev Blog
- Google AI Blog
- GitHub Blog
- Smashing Magazine
- The New Stack

## 🚀 How to Run Locally

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Aditya948351/Web_Scrapping_API.git
   cd Web_Scrapping_API
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Flask API:**
   ```bash
   python Web_scrapper.py
   ```
   *(Note: You may need to set your preferred port in `Web_scrapper.py` at the bottom before running).*

4. **Access the API:**
   Open your browser and navigate to `http://localhost:<YOUR_PORT>/news`


