import sys
import sqlite3
import re
from datetime import datetime
import os

# Set path to allow importing database.py from parent/same directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from database import get_db_connection
except ImportError:
    # Try parent directory if running from utils or similar
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from database import get_db_connection

# Heuristic mapping for Country ID
COUNTRY_MAP = {
    'USD': 5, 'ABD': 5, 'USA': 5, 'AMERIKA': 5,
    'TRY': 63, 'TUR': 63, 'TURKEY': 63, 'TÜRKİYE': 63, 'TL': 63,
    'EUR': 72, 'EURO ZONE': 72, 'AVRUPA': 72, 'EU': 72,
    'GBP': 12, 'UK': 12, 'İNGİLTERE': 12, 'STERLIN': 12,
    'CAD': 6, 'KANADA': 6,
    'JPY': 37, 'JAPONYA': 37,
    'AUD': 7, 'AVUSTRALYA': 7,
    'NZD': 35, 'YENİ ZELANDA': 35,
    'CHF': 110, 'İSVİÇRE': 110,
    'CNY': 51, 'ÇİN': 51,
    'DEM': 4, 'ALMANYA': 4,
    'INR': 160, 'HİNDİSTAN': 160
}

def parse_importance(imp_str):
    """
    Parses importance string to Low/Medium/High.
    Supports stars (***), text (High, Yüksek), or numeric (3).
    """
    imp_str = str(imp_str).lower().strip()
    if '⭐⭐⭐' in imp_str or 'high' in imp_str or 'yüksek' in imp_str or 'kritik' in imp_str or imp_str == '3':
        return 'High'
    if '⭐⭐' in imp_str or 'medium' in imp_str or 'orta' in imp_str or imp_str == '2':
        return 'Medium'
    return 'Low'

def parse_markdown_table(content):
    lines = content.split('\n')
    headers = []
    data = []
    
    for line in lines:
        line = line.strip()
        if not line.startswith('|'):
            continue
        
        # Remove leading/trailing pipes and split
        cells = [c.strip() for c in line.strip('|').split('|')]
        
        if not headers:
            # First row is headers
            headers = [h.lower() for h in cells]
            continue
            
        if '---' in cells[0]:
            # Separator row
            continue
            
        if len(cells) != len(headers):
            # Handle mismatch or empty trailing cells
            if len(cells) < len(headers):
                cells += [''] * (len(headers) - len(cells))
            else:
                cells = cells[:len(headers)]
            
        row = dict(zip(headers, cells))
        data.append(row)
        
    return data

def import_data(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        return

    print(f"Reading {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    events = parse_markdown_table(content)
    print(f"Found {len(events)} events in markdown table.")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if table is empty, maybe clear it? For now, we append.
    # User can request clear via flag if this was an API call.
    
    count = 0
    skipped = 0
    
    for evt in events:
        # Flexible key matching
        date_str = evt.get('date') or evt.get('tarih') or evt.get('zaman')
        time_str = evt.get('time') or evt.get('saat')
        currency = evt.get('currency') or evt.get('para birimi') or evt.get('ülke') or evt.get('döviz') or ''
        title = evt.get('event') or evt.get('olay') or evt.get('başlık') or evt.get('gösterge') or ''
        importance = evt.get('importance') or evt.get('önem') or evt.get('derece') or ''
        actual = evt.get('actual') or evt.get('açıklanan') or '-'
        forecast = evt.get('forecast') or evt.get('beklenti') or '-'
        previous = evt.get('previous') or evt.get('önceki') or '-'

        # Combine Date and Time if separated
        # Heuristic: If date_str contains time, use it. If time_str is separate, combine.
        # We need a standard ISO format: YYYY-MM-DD HH:MM:SS
        
        final_datetime = None
        
        # Try to clean strings
        date_str = date_str.strip() if date_str else ""
        time_str = time_str.strip() if time_str else "00:00"
        
        if "tüm gün" in time_str.lower():
            time_str = "00:00"
            
        try:
            # Try formatting like "10 Ocak 2026" + "16:30"
            # Need Turkish month mapping if text is in Turkish
            months = {
                'ocak': '01', 'şubat': '02', 'mart': '03', 'nisan': '04', 'mayıs': '05', 'haziran': '06',
                'temmuz': '07', 'ağustos': '08', 'eylül': '09', 'ekim': '10', 'kasım': '11', 'aralık': '12'
            }
            
            clean_date = date_str.lower()
            for m_name, m_num in months.items():
                if m_name in clean_date:
                    clean_date = clean_date.replace(m_name, m_num).replace(' ', '.')
                    break
            
            # Now try parsing standard formats
            # Common formats: DD.MM.YYYY, YYYY-MM-DD, DD/MM/YYYY
            date_formats = ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]
            
            dt_date = None
            for fmt in date_formats:
                try:
                    dt_date = datetime.strptime(clean_date, fmt)
                    break
                except ValueError:
                    continue
            
            if dt_date:
                # Combine with time
                # Time formats: HH:MM
                try:
                    h, m = map(int, time_str.split(':'))
                    dt_final = dt_date.replace(hour=h, minute=m)
                    final_datetime = dt_final.strftime("%Y-%m-%d %H:%M:00")
                except:
                   final_datetime = dt_date.strftime("%Y-%m-%d 00:00:00")
            
        except Exception as e:
            print(f"Date parse error for {date_str} {time_str}: {e}")

        if not final_datetime:
            # Skip rows without valid date
            skipped += 1
            continue

        country_id = COUNTRY_MAP.get(currency.upper(), 0)
        # If currency not found but looks like a country name, try that
        if country_id == 0:
             # Basic lookup in keys
             for k, v in COUNTRY_MAP.items():
                 if k in currency.upper():
                     country_id = v
                     break
        
        impact = parse_importance(importance)
        
        # Generate a unique event_id if not present??
        # Database has event_id column. We can generate one or leave it null?
        # Schema: event_id TEXT.
        # Let's generate a simple hash or random ID
        event_id = f"{country_id}-{final_datetime.replace(' ','').replace(':','').replace('-','')}-{title[:5]}"
        
        try:
            cursor.execute("""
                INSERT INTO calendar_events 
                (event_id, date_time, country_id, currency, title, impact, actual, forecast, previous)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (event_id, final_datetime, country_id, currency, title, impact, actual, forecast, previous))
            count += 1
        except Exception as e:
            print(f"DB Error: {e}")
            skipped += 1

    conn.commit()
    conn.close()
    print(f"Import complete: {count} added, {skipped} skipped.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        import_data(sys.argv[1])
    else:
        print("Usage: python import_calendar.py <filename>")
