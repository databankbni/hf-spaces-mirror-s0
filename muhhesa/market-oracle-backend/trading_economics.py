from curl_cffi import requests
from bs4 import BeautifulSoup
import traceback

def scrape_calendar():
    url = "https://tradingeconomics.com/calendar?importance=3"
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1'
    }
    
    events = []
    
    try:
        res = requests.get(url, headers=headers, impersonate='chrome110', timeout=15)
        # res.raise_for_status() isn't always reliable with curl_cffi, check manually
        if res.status_code != 200:
            return {"status": "error", "message": f"HTTP {res.status_code}"}
        
        soup = BeautifulSoup(res.text, 'html.parser')
        table = soup.find('table', id='calendar')
        
        if not table:
            return {"status": "error", "message": "Table not found"}
            
        rows = table.find_all('tr')
        current_date = ""
        
        for row in rows:
            # Check if this is a date header row (typically has a single th or td)
            th = row.find('th')
            if th and 'colspan' in th.attrs:
                current_date = th.text.strip()
                continue
                
            # If no th, it might be a date row if it has class table-header
            if 'class' in row.attrs and 'table-header' in row['class']:
                tds = row.find_all('td')
                if tds:
                    current_date = tds[0].text.strip()
                continue

            # Process event row
            if 'data-event' in row.attrs:
                country = row.get('data-country', '').title()
                event_name = row.get('data-event', '').title()
                
                # Time is usually in the first td
                time_td = row.find('td')
                time_str = time_td.text.strip() if time_td else ""
                
                # Look for actual, previous, consensus, forecast
                actual = row.find(id='actual')
                actual = actual.text.strip() if actual else ""
                
                previous = row.find(id='previous')
                previous = previous.text.strip() if previous else ""
                
                consensus = row.find(id='consensus')
                consensus = consensus.text.strip() if consensus else ""
                
                forecast = row.find(id='forecast')
                forecast = forecast.text.strip() if forecast else ""
                
                events.append({
                    "date": current_date,
                    "time": time_str,
                    "country": country,
                    "event": event_name,
                    "actual": actual,
                    "previous": previous,
                    "consensus": consensus,
                    "forecast": forecast
                })
                
        return {"status": "success", "data": events}
        
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import pprint
    res = scrape_calendar()
    if res['status'] == 'success':
        pprint.pprint(res['data'][:5])
    else:
        print(res)
