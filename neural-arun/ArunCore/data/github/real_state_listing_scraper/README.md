---
project_name: real_state_listing_scraper
github_url: https://github.com/neural-arun/real_state_listing_scraper
language: Python
stars: 0
topics: 
updated_at: 2026-03-14T10:48:12Z
---

# real_state_listing_scraper

> **GitHub Repository:** [https://github.com/neural-arun/real_state_listing_scraper](https://github.com/neural-arun/real_state_listing_scraper)  
> **Primary Language:** Python | **Stars:** 0 | **Forks:** 0  
> **Description:** No description provided.

---

# 99acres Real Estate Scraper Suite

A comprehensive set of Python scrapers designed to extract property listing data (Price, Location, Size, Contact) from 99acres.com.

## 📁 Project Structure

```
Real_estate_listing_scraper/
├── semantic_browser_scraper/  # Scraper v1: Uses browser text (Best for quick previews)
├── deep_browser_scraper/      # Scraper v2: Clicks every page (Best for zero N/A data)
├── parallel_http_scraperapi/  # Scraper v3: Parallel HTTP (High-scale professional)
├── data/                      # Output CSVs and HTML logic
├── research_and_debug/        # Initial recon and debugging scripts
└── venv/                      # Python virtual environment
```

## 🚀 Getting Started

### 1. Prerequisite: Virtual Environment
This project uses a shared virtual environment in the root folder. If you haven't created it yet:
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install playwright pandas beautifulsoup4 playwright-stealth httpx[http2]
playwright install chromium
```

### 2. Choose Your Scraper
Each scraper is designed for a different need:

*   **[Semantic Browser Scraper](./semantic_browser_scraper):** 
    Fast and free. Reads property cards directly from search results using text matching. Best for quick scans.
*   **[Deep Browser Scraper](./deep_browser_scraper):** 
    The most accurate free method. It visits every individual listing page to extract hidden details. Use this if you want the highest quality data for free.
*   **[Parallel HTTP Scraper](./parallel_http_scraperapi):** 
    Professional scale. No browser needed. It uses ScraperAPI to bypass Cloudflare and fetches 5+ pages in parallel. Best for large-scale data collection.

### 3. Running a Scraper
Navigate to any of the three folders and follow the instructions in its specific `README.md`. 
Example:
```powershell
cd semantic_browser_scraper
..\venv\Scripts\activate
python scraper.py
```

## 📊 Data Output
All results are exported as CSV files. Each scraper is pre-configured to output data with these columns:
- **City**: Target city name
- **Price**: Listing price (e.g., ₹2.5 Cr)
- **Location**: Full address or locality
- **Size (sqft)**: Area in sqft or yards
- **Contact Info**: Agent/Builder/Owner details
- **URL**: Link to the property (v2 and v3 only)

## ⚖️ Disclaimer & Ethics
This tool is for educational purposes. Scraping websites may violate their Terms of Service. Always check `robots.txt`, respect scraping limits, and ensure you have permission to use the data you collect.

---
**Author:** Arun Yadav
**Built for:** Freelance Property Listing Demand
