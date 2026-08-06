import urllib.request
import urllib.parse
import json
from bs4 import BeautifulSoup
from typing import Dict

def get_moneycontrol_url(fund_name: str) -> str:
    """Uses MoneyControl's auto-suggest API to find the fund's URL."""
    try:
        # type=2 means Mutual Funds
        url = f"https://www.moneycontrol.com/mccode/common/autosuggestion_solr.php?query={urllib.parse.quote(fund_name)}&type=2&format=json"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            
            # MoneyControl autosuggest often returns a list of dicts or just a JSON array
            try:
                data = json.loads(content)
                if isinstance(data, list) and len(data) > 0:
                    for item in data:
                        if 'link_src' in item:
                            return item['link_src']
            except json.JSONDecodeError:
                pass
                
            # Fallback if it returned HTML li tags
            soup = BeautifulSoup(content, 'html.parser')
            link = soup.find('a')
            if link and link.has_attr('href'):
                return link['href']
    except Exception as e:
        print(f"Failed to resolve MoneyControl URL for {fund_name}: {e}")
        
    return ""

def scrape_holdings_from_url(url: str) -> Dict[str, float]:
    """Scrapes the portfolio holdings table from a MoneyControl Mutual Fund page."""
    holdings = {}
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        # MoneyControl uses a generic portfolio page URL structure. 
        # Usually: moneycontrol.com/mutual-funds/nav/fund-name/ID
        # The portfolio is loaded directly on this page under a table with class 'mctable1' or id 'equityTopHoldingTable'
        
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8')
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # Look for the holdings table. MoneyControl often uses 'equityTopHoldingTable' or a generic table class inside the portfolio section
        tables = soup.find_all('table', {'id': 'equityTopHoldingTable'})
        if not tables:
            # Fallback to look for a table that has "Stock" and "Sector" in headers
            for t in soup.find_all('table'):
                if 'Stock' in t.text and 'Sector' in t.text:
                    tables = [t]
                    break
                    
        if tables:
            table = tables[0]
            rows = table.find_all('tr')
            for row in rows[1:]: # Skip header
                cols = row.find_all('td')
                if len(cols) >= 4:
                    stock_name = cols[0].text.strip()
                    try:
                        # Weight is usually in the 4th column (Value/Assets %) or 3rd column
                        # Moneycontrol format: Stock | Sector | Value(Mn) | % of Total Holdings
                        weight_str = cols[-1].text.strip().replace('%', '')
                        weight = float(weight_str)
                        # Filter out empty stocks or cash
                        if stock_name and weight > 0:
                            holdings[stock_name] = weight
                    except ValueError:
                        continue
    except Exception as e:
        print(f"Failed to scrape MoneyControl URL {url}: {e}")
        
    return holdings

def get_holdings_via_scraper(fund_name: str) -> Dict[str, float]:
    """Orchestrates the resolution and scraping of a mutual fund."""
    url = get_moneycontrol_url(fund_name)
    if not url:
        return {}
    
    # If the URL is just HTTP, ensure HTTPS
    if url.startswith("http://"):
        url = url.replace("http://", "https://")
        
    return scrape_holdings_from_url(url)
