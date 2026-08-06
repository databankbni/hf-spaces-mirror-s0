import os
import json
import requests
import html
from pydantic import BaseModel

CONFIG_FILE = "telegram_config.json"

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"bot_token": "", "chat_id": ""}

def save_config(bot_token: str, chat_id: str):
    config = {"bot_token": bot_token, "chat_id": chat_id}
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)
    return config

def send_telegram_message(message: str) -> dict:
    config = load_config()
    token = config.get("bot_token")
    chat_id = config.get("chat_id")
    
    if not token or not chat_id:
        return {"status": "error", "message": "Konfigurasi Telegram belum lengkap. Harap masukkan Token dan Chat ID."}
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        if response.status_code == 200 and data.get("ok"):
            return {"status": "success", "message": "Pesan berhasil dikirim."}
        else:
            return {"status": "error", "message": data.get("description", "Gagal mengirim ke Telegram")}
    except Exception as e:
        return {"status": "error", "message": f"Koneksi gagal: {str(e)}"}

def broadcast_verdict_change(result: dict):
    """
    Broadcasts a massive, rich-formatted executive report to Telegram.
    """
    # 1. VERDICT & ACTION
    verdict_info = result.get("verdict", {})
    score = verdict_info.get("composite_score", 0)
    label = verdict_info.get("label", "NEUTRAL")
    action = html.escape(result.get("action_plan", {}).get("action", ""))
    summary = html.escape(result.get("summary", "Tidak ada ringkasan."))
    
    emoji = "🟢"
    if "SELL" in label.upper() or "DEFENSIF" in label.upper() or "KURANGI" in label.upper():
        emoji = "🔴"
    elif "WAIT" in label.upper() or "NEUTRAL" in label.upper() or "NETRAL" in label.upper():
        emoji = "🟡"

    # 2. IHSG & FEAR GREED
    ihsg_data = result.get("market_snapshot", {}).get("IHSG", {})
    try:
        ihsg_price = float(ihsg_data.get("price", 0) or 0)
        ihsg_pct = float(ihsg_data.get("change_pct", 0) or 0)
    except:
        ihsg_price, ihsg_pct = 0.0, 0.0
    ihsg_arrow = "📈" if ihsg_pct > 0 else "📉"
    
    fg_data = result.get("fear_and_greed", {})
    if not fg_data:
        try:
            from fear_greed import fetch_fear_and_greed
            fg_data = fetch_fear_and_greed()
        except:
            pass
            
    fg_val = fg_data.get("score", "N/A")
    fg_label = fg_data.get("rating", "Neutral")

    # 3. MACRO INDICATORS
    macros = result.get("macro_scores", {}).get("individual", {})
    
    def safe_format(val):
        try: return f"{float(val or 0):,.2f}"
        except: return "N/A"
        
    usdidr = macros.get("USDIDR", {}).get("value", "N/A")
    usdidr_str = safe_format(usdidr)
    fed = macros.get("FED_RATE", {}).get("value", "N/A")
    bi = macros.get("BI_RATE", {}).get("value", "N/A")
    wti = result.get("market_snapshot", {}).get("CRUDE_OIL", {}).get("price", "N/A")
    wti_str = safe_format(wti)

    # 4. NEWS
    news_list = result.get("news_sentiment", {}).get("headlines", [])
    news_text = ""
    for n in news_list[:3]:
        title = html.escape(n.get("title", ""))
        link = n.get("link", "#")
        news_text += f"• <a href='{link}'>{title}</a>\n"
    if not news_text:
        news_text = "• Belum ada berita signifikan.\n"

    # 5. CYCLE & CALENDAR
    cycle_phase = result.get("market_cycle", {}).get("phase", "Unknown")
    
    cal_data = result.get("macro_calendar", [])
    calendar_events = cal_data.get("events", []) if isinstance(cal_data, dict) else cal_data
    
    event_str = "\n"
    months_id = {"Jan": "Januari", "Feb": "Februari", "Mar": "Maret", "Apr": "April", "May": "Mei", "Jun": "Juni", "Jul": "Juli", "Aug": "Agustus", "Sep": "September", "Oct": "Oktober", "Nov": "November", "Dec": "Desember"}
    
    for event in calendar_events[:3]:
        date_raw = event.get('date', '')
        # "03 Jul 2026" -> "3 Juli"
        parts = date_raw.split(" ")
        if len(parts) >= 2:
            day = parts[0].lstrip("0")
            month = months_id.get(parts[1], parts[1])
            date_fmt = f"{day} {month}"
        else:
            date_fmt = date_raw
        
        title = html.escape(event.get('event', ''))
        event_str += f"- {date_fmt}: {title}\n"
    if event_str == "\n":
        event_str = "- Tidak ada agenda dekat.\n"

    # 6. HISTORICAL PATTERN
    pattern = result.get("historical_pattern", {})
    if pattern and pattern.get("matched", False):
        pattern_name = html.escape(pattern.get("event_name", "Tidak ada pola terdeteksi"))
    else:
        pattern_name = "Tidak ada pola terdeteksi"

    # 7. SECTORS
    sectors = result.get("sectors", {}).get("top_picks", [])
    top_picks_str = html.escape(", ".join([s.get("sector", "") for s in sectors[:3]]) if sectors else "Belum ada rekomendasi.")

    # BUILD MESSAGE
    msg = f"🚨 <b>THE MARKET ORACLE EXECUTIVE BRIEF</b> 🚨\n\n"
    
    msg += f"🧭 <b>VERDICT:</b> {emoji} <b>{label}</b> (Score: {score})\n"
    msg += f"🎯 <b>ACTION:</b> {action}\n\n"
    
    msg += f"📊 <b>MARKET SNAPSHOT</b>\n"
    msg += f"• IHSG: {ihsg_price:,.0f} ({ihsg_arrow} {ihsg_pct:.2f}%)\n"
    msg += f"• Fear &amp; Greed: {fg_val} ({fg_label})\n\n"
    
    msg += f"🌍 <b>MACRO DASHBOARD</b>\n"
    msg += f"• USD/IDR: {usdidr_str}\n"
    msg += f"• The Fed Rate: {fed}%\n"
    msg += f"• BI Rate: {bi}%\n"
    msg += f"• WTI Oil: ${wti_str}\n\n"
    
    msg += f"🌊 <b>CYCLE &amp; PATTERN</b>\n"
    msg += f"• Fase Siklus: {cycle_phase}\n"
    msg += f"• Pola Historis: {pattern_name}\n"
    msg += f"• Agenda Terdekat:{event_str}\n"
    
    msg += f"📰 <b>TOP HEADLINES</b>\n{news_text}\n"
    
    msg += f"🏆 <b>TOP SECTORS</b>\n{top_picks_str}\n\n"
    
    msg += f"📝 <b>ORACLE INSIGHT</b>\n<i>{summary}</i>\n"
    
    return send_telegram_message(msg)

