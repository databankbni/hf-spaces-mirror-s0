from curl_cffi import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import calendar

def adjust_weekend(d):
    """Jika jatuh di hari libur (Sabtu/Minggu), geser ke hari kerja berikutnya (Senin)."""
    if d.weekday() == 5: # Sabtu
        return d + timedelta(days=2)
    elif d.weekday() == 6: # Minggu
        return d + timedelta(days=1)
    return d

def get_te_calendar():
    """Mencoba scrape agenda makro Indonesia langsung dari TradingEconomics."""
    try:
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        }
        res = requests.get('https://tradingeconomics.com/indonesia/calendar', headers=headers, impersonate='chrome110', timeout=15)
        if res.status_code != 200: return None
        soup = BeautifulSoup(res.text, 'html.parser')
        
        events = []
        for tr in soup.find_all('tr'):
            if not tr.get('data-id'): continue # Pastikan ini adalah baris event
            tds = tr.find_all('td', recursive=False)
            if len(tds) < 5: continue
            
            date_class = tds[0].get('class', [])
            date_str = ''
            for c in date_class:
                if c.startswith('202'):
                    date_str = c
                    break
                    
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = dt.strftime('%d %b %Y')
            except:
                formatted_date = date_str
                
            time_span = tds[0].find('span')
            time_str = time_span.text.strip() if time_span else ''
            
            event_name = tr.get('data-event', '').title()
            if not event_name:
                event_a = tds[2].find('a', class_='calendar-event')
                if event_a: event_name = event_a.text.strip()
                
            actual = tds[3].text.strip() if len(tds) > 3 else ''
            previous = tds[4].text.strip() if len(tds) > 4 else ''
            consensus = tds[5].text.strip() if len(tds) > 5 else ''
            forecast = tds[6].text.strip() if len(tds) > 6 else ''
            
            desc = ''
            if actual: desc += f'Actual: {actual}. '
            if consensus: desc += f'Konsensus: {consensus}. '
            elif forecast: desc += f'Forecast: {forecast}. '
            if previous: desc += f'Previous: {previous}.'
            
            impact = 'Sedang'
            if any(word in event_name for word in ['Rate', 'Gdp', 'Inflation', 'Trade', 'Interest']):
                impact = 'Sangat Tinggi'
            elif any(word in event_name for word in ['Sales', 'Confidence', 'Reserve', 'Production']):
                impact = 'Tinggi'
                
            events.append({
                'event': event_name,
                'date': f'{formatted_date} {time_str}'.strip(),
                'impact': impact,
                'prediction': 'Netral', 
                'description': desc.strip() or 'Rilis indikator makro ekonomi Indonesia.'
            })
            
        if len(events) >= 1:
            return events
    except Exception as e:
        print(f"[Macro Calendar] Gagal mengambil data dari TradingEconomics: {e}")
    return None

def get_macro_calendar() -> list:
    """
    Menghasilkan jadwal rilis data makro ekonomi (katalis) terdekat untuk Indonesia.
    Prioritas utama: Live Data dari Trading Economics.
    Fallback: Dihitung secara dinamis berdasarkan standar BPS & Bank Indonesia.
    """
    # 1. Coba ambil dari TradingEconomics terlebih dahulu
    te_events = get_te_calendar()
    if te_events:
        return te_events

    # 2. Jika gagal/terblokir, gunakan Fallback Dinamis internal
    today = datetime.now().date()
    events = []
    
    for m_offset in range(3):
        target_month = today.month + m_offset
        target_year = today.year
        while target_month > 12:
            target_month -= 12
            target_year += 1
            
        try:
            inflasi_date = adjust_weekend(datetime(target_year, target_month, 1).date())
            if inflasi_date >= today:
                events.append({
                    "event": "Rilis Data Inflasi (CPI) Indonesia",
                    "date": inflasi_date.strftime("%d %b %Y"),
                    "raw_date": inflasi_date,
                    "impact": "Sangat Tinggi",
                    "prediction": "Volatile",
                    "description": "Pengumuman inflasi bulanan oleh BPS. Sangat krusial menentukan arah kebijakan BI dan daya beli."
                })
        except ValueError:
            pass
            
        if target_month in [2, 5, 8, 11]:
            try:
                gdp_date = adjust_weekend(datetime(target_year, target_month, 5).date())
                if gdp_date >= today:
                    events.append({
                        "event": "Pertumbuhan Ekonomi (PDB/GDP) RI",
                        "date": gdp_date.strftime("%d %b %Y"),
                        "raw_date": gdp_date,
                        "impact": "Sangat Tinggi",
                        "prediction": "Volatile",
                        "description": "Rilis PDB Kuartalan (BPS). Barometer utama kondisi makro Indonesia."
                    })
            except ValueError:
                pass

        try:
            cadev_date = adjust_weekend(datetime(target_year, target_month, 7).date())
            if cadev_date >= today:
                events.append({
                    "event": "Posisi Cadangan Devisa (Cadev) RI",
                    "date": cadev_date.strftime("%d %b %Y"),
                    "raw_date": cadev_date,
                    "impact": "Tinggi",
                    "prediction": "Netral",
                    "description": "Laporan Bank Indonesia terkait ketahanan eksternal dan amunisi stabilisasi nilai tukar Rupiah."
                })
        except ValueError:
            pass
            
        try:
            trade_date = adjust_weekend(datetime(target_year, target_month, 15).date())
            if trade_date >= today:
                events.append({
                    "event": "Neraca Perdagangan & Ekspor-Impor",
                    "date": trade_date.strftime("%d %b %Y"),
                    "raw_date": trade_date,
                    "impact": "Sangat Tinggi",
                    "prediction": "Volatile",
                    "description": "Rilis data BPS (surplus/defisit neraca dagang). Sangat mempengaruhi Rupiah dan sektor komoditas."
                })
        except ValueError:
            pass
            
        try:
            c = calendar.monthcalendar(target_year, target_month)
            kamis_dates = [week[3] for week in c if week[3] != 0]
            if len(kamis_dates) >= 3:
                rdg_date = datetime(target_year, target_month, kamis_dates[2]).date()
            else:
                rdg_date = datetime(target_year, target_month, 20).date()
                
            if rdg_date >= today:
                events.append({
                    "event": "Rapat Dewan Gubernur (RDG) Bank Indonesia",
                    "date": rdg_date.strftime("%d %b %Y"),
                    "raw_date": rdg_date,
                    "impact": "Sangat Tinggi",
                    "prediction": "Volatile",
                    "description": "Pengumuman suku bunga BI Rate. Dampak masif untuk sektor Perbankan, Properti, dan Otomotif."
                })
        except ValueError:
            pass
                
    events.sort(key=lambda x: x["raw_date"])
    
    final_events = []
    for ev in events[:20]:
        del ev["raw_date"]
        final_events.append(ev)
        
    return final_events
