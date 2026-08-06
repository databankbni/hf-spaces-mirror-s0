import pandas as pd
import requests
import numpy as np
import concurrent.futures
import warnings
import traceback
import gradio as gr
import base64
import json

warnings.filterwarnings("ignore")

BASE_URL = "https://data-api.binance.vision/api/v3"
QUOTE_ASSET = 'USDT'

def format_mcap(value):
    try:
        if value >= 1_000_000_000_000: return f"${value / 1_000_000_000_000:.2f}T"
        elif value >= 1_000_000_000: return f"${value / 1_000_000_000:.2f}B"
        return f"${value:,.0f}"
    except Exception: return "$0"

def get_intent_badge(df):
    try:
        if df is None or len(df) == 0: return ""
        last_candle = df.iloc[-1]
        h, l, c = last_candle['high'], last_candle['low'], last_candle['close']
        rng = h - l if h != l else 1
        pos_ratio = (c - l) / rng
        if pos_ratio >= 0.50: return '<span style="color:#10b981; background:rgba(16, 185, 129, 0.15); padding:4px 8px; border-radius:6px; font-weight:800; font-size:11px; text-transform:uppercase; border:1px solid rgba(16, 185, 129, 0.3);">🟢 Buying</span>'
        else: return '<span style="color:#ef4444; background:rgba(239, 68, 68, 0.15); padding:4px 8px; border-radius:6px; font-weight:800; font-size:11px; text-transform:uppercase; border:1px solid rgba(239, 68, 68, 0.3);">🔴 Selling</span>'
    except Exception: return ""

def get_high_volume_pairs(min_volume_threshold):
    try: 
        min_vol = float(min_volume_threshold) if min_volume_threshold else 0.0
        info_res = requests.get(f"{BASE_URL}/exchangeInfo", timeout=10).json()
        active_symbols = {s['symbol'] for s in info_res.get('symbols', []) if s['status'] == 'TRADING'}
        data = requests.get(f"{BASE_URL}/ticker/24hr", timeout=10).json()
        
        valid_coins = []
        for item in data:
            symbol = item.get('symbol', '')
            if symbol not in active_symbols: continue
            if symbol.endswith(QUOTE_ASSET) and 'UPUSDT' not in symbol and 'DOWNUSDT' not in symbol:
                try:
                    vol_usdt = float(item['quoteVolume'])
                    if vol_usdt >= min_vol:
                        valid_coins.append({'coin': symbol, 'volume': vol_usdt, 'change': float(item['priceChangePercent']), 'price': float(item['lastPrice'])})
                except Exception: continue
        valid_coins.sort(key=lambda x: x.get('volume', 0), reverse=True)
        return valid_coins
    except Exception: return []

def fetch_data(symbol, interval, limit=1000):
    try:
        res = requests.get(f"{BASE_URL}/klines?symbol={symbol}&interval={interval}&limit={limit}", timeout=10).json()
        if isinstance(res, dict) and 'code' in res: return None
        df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'])
        for col in ['open', 'high', 'low', 'close', 'volume']: df[col] = df[col].astype(float)
        df['hlc3'] = (df['high'] + df['low'] + df['close']) / 3
        return df
    except Exception: return None

def calculate_macd(series, fast, slow, signal):
    fast_ema = series.ewm(span=fast, adjust=False).mean()
    slow_ema = series.ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    return macd_line - macd_line.ewm(span=signal, adjust=False).mean()

def check_strategy(df, tf_string, lookback_candles):
    try:
        lookback = int(lookback_candles) if lookback_candles else 2
        close, hlc3 = df['close'], df['hlc3']
        ema21 = close.ewm(span=21, adjust=False).mean()
        hist1 = calculate_macd(hlc3, 8, 21, 5)
        hist2 = calculate_macd(close, 50, 200, 10)
        
        bothGreen = (hist1 > 0) & (hist2 > 0)
        longCondition1 = bothGreen & (~bothGreen.shift(1, fill_value=False))
        longCondition2 = (hist1 > 0) & (hist1.shift(1) <= 0) & (hist2 > 0)
        longCondition3 = (close > ema21) & (close.shift(1) <= ema21.shift(1)) & (hist1 > 0) & (hist2 > 0)
        earlyEntry = (hist1 < 0) & (hist1 > hist1.shift(1)) & (hist1.shift(1) > hist1.shift(2)) & (hist2 > 0)
        
        raw_buy_trigger = (longCondition1 | longCondition2 | longCondition3 | earlyEntry) & (close > ema21)
        exit_trigger = close < ema21
        
        buy_arr, exit_arr = raw_buy_trigger.to_numpy(), exit_trigger.to_numpy()
        in_trade, bars_since_entry = False, -1
        
        for i in range(len(buy_arr)):
            if not in_trade:
                if buy_arr[i]: in_trade, bars_since_entry = True, 0
            else:
                bars_since_entry += 1
                if exit_arr[i]: in_trade, bars_since_entry = False, -1
                    
        if in_trade and (0 <= bars_since_entry < lookback):
            avg_vol = df['volume'].iloc[-25:-1].mean()
            return True, (df['volume'].iloc[-1] / avg_vol if avg_vol > 0 else 1.0)
        return False, 0.0
    except Exception: return False, 0.0

def fetch_global_metrics():
    try:
        cg = requests.get('https://api.coingecko.com/api/v3/global', timeout=5).json()
        mcap_val = cg['data']['total_market_cap']['usd']
        mcap_change = cg['data']['market_cap_change_percentage_24h_usd']
    except Exception:
        mcap_val, mcap_change = 0, 0
    try:
        btc_klines = requests.get(f"{BASE_URL}/klines?symbol=BTCUSDT&interval=1h&limit=24", timeout=5).json()
        btc_closes = [float(k[4]) for k in btc_klines]
        if mcap_val == 0 and len(btc_closes) > 0:
            mcap_change = ((btc_closes[-1] - btc_closes[0]) / btc_closes[0]) * 100
    except Exception: btc_closes = []
    return mcap_val, mcap_change, ""

def build_report_html(title, color, meta_dict, rows_html):
    meta_html = "".join([f'<div class="meta-row"><span class="meta-label">{k}</span><span class="meta-value">{v}</span></div>' for k, v in meta_dict.items()])
    return f"""
    <div class="market-report-container fade-in">
        <div class="report-header" style="background: linear-gradient(135deg, {color} 0%, #0f172a 100%);"><h2>{title}</h2></div>
        <div class="report-meta">{meta_html}</div>
        <div class="table-wrapper">
            <table class="report-table">
                <thead><tr><th style="text-align: center;">#</th><th>Asset</th><th style="text-align: right;">Price</th><th style="text-align: right;">24h %</th><th style="text-align: right;">Metrics</th></tr></thead>
                <tbody>{rows_html if rows_html else '<tr><td colspan="5" class="no-results">❌ No matching assets found for this scan.</td></tr>'}</tbody>
            </table>
        </div>
    </div>
    """

def format_row(rank, coin, intent, price, change, volume, metric_badge):
    c_color, c_bg, c_sign = ("#10b981", "rgba(16, 185, 129, 0.15)", "+") if change >= 0 else ("#ef4444", "rgba(239, 68, 68, 0.15)", "")
    return f"""
    <tr class="report-row">
        <td class="col-rank" style="vertical-align:top; padding-top:20px;">{rank:02d}</td>
        <td class="col-coin"><div style="display:flex; flex-direction:column; gap:6px;"><a href="https://www.tradingview.com/chart/?symbol=BINANCE:{coin}" target="_blank" class="tv-link"><span class="coin-badge">{coin}</span></a><div style="margin-top:2px;">{intent}</div></div></td>
        <td class="col-price" style="vertical-align:top; padding-top:20px;">${price:,.4f}</td>
        <td class="col-change" style="vertical-align:top; padding-top:20px;"><span style="color: {c_color}; background: {c_bg}; padding: 4px 8px; border-radius: 6px; font-weight: 600;">{c_sign}{change:.2f}%</span></td>
        <td class="col-vol" style="vertical-align:top; padding-top:20px;"><div style="display: flex; align-items: center; justify-content: flex-end; gap: 8px;">{metric_badge}<span>${volume:,.0f}</span></div></td>
    </tr>"""

def get_spinner(color, text):
    return f"""<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 20px; text-align: center; min-height: 250px;"><div class="modern-spinner" style="border-top-color: {color};"></div><h3 style="margin-top: 24px; color: {color}; font-weight: 600; font-size: 1.2rem;">{text}</h3></div>"""

# --- 1. MARKET REGIME ---
def run_market_regime():
    try:
        yield get_spinner("#3b82f6", "Analyzing Market Regime...")
        res = requests.get(f"{BASE_URL}/klines?symbol=BTCUSDT&interval=4h&limit=200", timeout=10).json()
        df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'])
        closes = df['close'].astype(float)
        
        ema50 = closes.ewm(span=50, adjust=False).mean().iloc[-1]
        price_12h_ago = closes.iloc[-4]
        initial_cp = closes.iloc[-1]
        initial_drop = ((initial_cp - price_12h_ago) / price_12h_ago) * 100
        
        if initial_drop <= -3.0: status, c, bg = "🚨 RISK-OFF (FLASH CRASH)", "#ef4444", "rgba(239, 68, 68, 0.15)"
        elif initial_cp < ema50: status, c, bg = "⚠️ RISK-NEUTRAL / BEARISH", "#f59e0b", "rgba(245, 158, 11, 0.15)"
        else: status, c, bg = "🟢 RISK-ON (BULLISH)", "#10b981", "rgba(16, 185, 129, 0.15)"

        raw_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
        <style>
            :root {{ --bg-main: #ffffff; --border: #e5e7eb; --text-main: #111827; --text-mut: #6b7280; }}
            @media (prefers-color-scheme: dark) {{ :root {{ --bg-main: #0f172a; --border: #1e293b; --text-main: #f8fafc; --text-mut: #94a3b8; }} }}
            body {{ margin: 0; font-family: 'Inter', sans-serif; background: transparent; color: var(--text-main); }}
            .market-report-container {{ max-width: 650px; margin: 0 auto; background: var(--bg-main); border: 1px solid var(--border); border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); overflow: hidden; transition: all 0.3s; }}
            @media (prefers-color-scheme: dark) {{ .market-report-container {{ box-shadow: 0 10px 30px rgba(0,0,0,0.5); }} }}
            .report-header {{ padding: 20px; text-align: center; color: white; background: linear-gradient(135deg, #3b82f6 0%, #0f172a 100%); }}
            .report-header h2 {{ margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }}
            .market-overview-card {{ display: flex; flex-direction: column; align-items: center; text-align: center; padding: 40px 20px; border-bottom: 1px solid var(--border); }}
            .report-meta {{ padding: 20px 24px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
            .meta-row {{ display: flex; flex-direction: column; gap: 4px; }}
            .meta-label {{ color: var(--text-mut); font-size: 11px; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px; }}
            .meta-value {{ font-weight: 700; font-size: 16px; color: var(--text-main); }}
            .meta-accent {{ font-weight: 800; font-size: 18px; }}
        </style></head>
        <body>
            <div class="market-report-container">
                <div class="report-header"><h2 style="display:flex; align-items:center; justify-content:center; gap:10px;">🚦 Live Market Regime <span style="display:inline-block; width:10px; height:10px; background:#10b981; border-radius:50%; box-shadow: 0 0 10px #10b981; animation: pulse 1.5s infinite;"></span></h2></div>
                <div class="market-overview-card">
                    <div id="status-badge" style="color: {c}; background: {bg}; padding: 14px 24px; border-radius: 12px; font-size: 24px; font-weight: 900; border: 2px solid {c}; margin: 0; transition: all 0.3s; letter-spacing: -0.5px;">{status}</div>
                </div>
                <div class="report-meta">
                    <div class="meta-row"><span class="meta-label">BTC Live Price</span><span class="meta-value" id="val-price">${initial_cp:,.2f}</span></div>
                    <div class="meta-row"><span class="meta-label">4H 50-EMA Level</span><span class="meta-value">${ema50:,.2f}</span></div>
                    <div class="meta-row"><span class="meta-label">12-Hour Velocity</span><span class="meta-accent" id="val-drop" style="color: {'#ef4444' if initial_drop < 0 else '#10b981'}; transition: color 0.3s;">{initial_drop:.2f}%</span></div>
                    <div class="meta-row"><span class="meta-label">Trend Delta</span><span class="meta-value" id="val-delta" style="color: {'#10b981' if (initial_cp - ema50) > 0 else '#ef4444'}; transition: color 0.3s;">${initial_cp - ema50:,.2f}</span></div>
                </div>
            </div>
            <style>@keyframes pulse {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} 100% {{ opacity: 1; }} }}</style>
            <script>
                const ema = {ema50}, p12 = {price_12h_ago};
                const ws = new WebSocket('wss://stream.binance.com:9443/ws/btcusdt@ticker');
                ws.onmessage = e => {{
                    const res = JSON.parse(e.data);
                    const cp = parseFloat(res.c);
                    const drop = ((cp - p12) / p12) * 100;
                    const delta = cp - ema;
                    
                    document.getElementById('val-price').innerText = '$' + cp.toLocaleString('en-US', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                    document.getElementById('val-drop').innerText = (drop > 0 ? '+' : '') + drop.toFixed(2) + '%';
                    document.getElementById('val-drop').style.color = drop < 0 ? '#ef4444' : '#10b981';
                    document.getElementById('val-delta').innerText = (delta > 0 ? '+$' : '-$') + Math.abs(delta).toLocaleString('en-US', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                    document.getElementById('val-delta').style.color = delta > 0 ? '#10b981' : '#ef4444';
                    
                    let s = "🟢 RISK-ON (BULLISH)", c = "#10b981", bg = "rgba(16, 185, 129, 0.15)";
                    if (drop <= -3.0) {{ s = "🚨 RISK-OFF (FLASH CRASH)"; c = "#ef4444"; bg = "rgba(239, 68, 68, 0.15)"; }} 
                    else if (cp < ema) {{ s = "⚠️ RISK-NEUTRAL / BEARISH"; c = "#f59e0b"; bg = "rgba(245, 158, 11, 0.15)"; }}
                    
                    const badge = document.getElementById('status-badge');
                    badge.innerText = s; badge.style.color = c; badge.style.borderColor = c; badge.style.backgroundColor = bg;
                }};
            </script>
        </body></html>"""
        b64 = base64.b64encode(raw_html.encode('utf-8')).decode('utf-8')
        yield f'<div style="width:100%; display:flex; justify-content:center;"><iframe src="data:text/html;charset=utf-8;base64,{b64}" style="width:100%; max-width:650px; height:450px; border:none; overflow:hidden;" scrolling="no"></iframe></div>'
    except Exception as e: yield f"<div class='lookup-error'>❌ Error: {str(e)}</div>"

# --- 2. TREND SCREENER ---
def run_web_screener(timeframe, min_volume, lookback):
    try:
        yield get_spinner("#4f46e5", "Scanning Live Markets...")
        mcap_val, mcap_change, _ = fetch_global_metrics()
        mcap_str = format_mcap(mcap_val) if mcap_val > 0 else "Est. from BTC"
        
        coins = get_high_volume_pairs(min_volume)
        signals = []
        def proc(c):
            df = fetch_data(c['coin'], timeframe)
            if df is not None and len(df) > 250:
                is_buy, vol_mult = check_strategy(df, timeframe, lookback)
                if is_buy:
                    c['vol_mult'] = vol_mult
                    c['intent'] = get_intent_badge(df)
                    return c
            return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as e:
            for r in e.map(proc, coins):
                if r: signals.append(r)
        
        signals.sort(key=lambda x: x.get('volume', 0), reverse=True)
        rows = "".join([format_row(i, c['coin'], c['intent'], c['price'], c['change'], c['volume'], f'<span class="spike-badge high-spike">🔥 {c["vol_mult"]:.1f}x</span>' if c["vol_mult"]>=3 else (f'<span class="spike-badge med-spike">🌊 {c["vol_mult"]:.1f}x</span>' if c["vol_mult"]>=1.5 else "")) for i, c in enumerate(signals, 1)])
        
        meta = {"Global MCap": mcap_str, "24h Shift": f"{'+' if mcap_change>=0 else ''}{mcap_change:.2f}%", "Timeframe": timeframe, "Active Setups": len(signals)}
        yield build_report_html("🎯 Trend Breakout Results", "#4f46e5", meta, rows)
    except Exception as e: yield f"<div class='lookup-error'>❌ Error: {str(e)}</div>"

# --- 3. SQUEEZE ---
def run_volatility_squeeze(timeframe, min_volume):
    yield get_spinner("#f59e0b", "Scanning for Squeezes...")
    coins = get_high_volume_pairs(min_volume)
    sqz = []
    def proc(c):
        df = fetch_data(c['coin'], timeframe)
        if df is not None and len(df) > 100:
            cl = df['close']
            sma, std = cl.rolling(20).mean(), cl.rolling(20).std()
            bw = ((sma + 2*std) - (sma - 2*std)) / sma * 100
            if bw.iloc[-1] <= (bw.iloc[-100:-1].min() * 1.15):
                d = "BULLISH COIL" if cl.iloc[-1] > sma.iloc[-1] else "BEARISH COIL"
                clr = "#10b981" if d == "BULLISH COIL" else "#ef4444"
                c['bw'], c['intent'] = bw.iloc[-1], f'<span style="color:{clr}; background:rgba({("16,185,129" if clr=="#10b981" else "239,68,68")}, 0.15); padding:4px 8px; border-radius:6px; font-weight:800; font-size:11px; text-transform:uppercase; border:1px solid {clr};">🗜️ {d}</span>'
                return c
        return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as e:
        for r in e.map(proc, coins):
            if r: sqz.append(r)
    sqz.sort(key=lambda x: x.get('bw', 100))
    rows = "".join([format_row(i, c['coin'], c['intent'], c['price'], c['change'], c['volume'], f'<span class="spike-badge high-spike" style="background:#fffbeb; color:#f59e0b; border-color:#fde68a;">Tightness: {c["bw"]:.2f}%</span>') for i, c in enumerate(sqz[:15], 1)])
    yield build_report_html("🗜️ Volatility Squeeze", "#f59e0b", {"Timeframe": timeframe, "Min Volume": f"${min_volume:,.0f}", "Coils Found": f"<span style='color:#f59e0b'>{len(sqz)}</span>"}, rows)

# --- 4. VOLUME PROFILE (POINT OF CONTROL) ---
def run_volume_profile(timeframe, min_volume):
    yield get_spinner("#8b5cf6", "Mapping Volume Profiles...")
    coins, pocs = get_high_volume_pairs(min_volume), []
    def proc(c):
        df = fetch_data(c['coin'], timeframe, limit=300)
        if df is not None and len(df) > 50:
            bins = np.linspace(df['low'].min(), df['high'].max(), 50)
            df['bin'] = pd.cut(df['close'], bins=bins)
            poc_bin = df.groupby('bin', observed=False)['volume'].sum().idxmax()
            poc_price = poc_bin.mid
            dist = abs(c['price'] - poc_price) / poc_price * 100
            if dist <= 1.5:
                c['dist'], c['poc'] = dist, poc_price
                c['intent'] = f'<span style="color:#8b5cf6; background:rgba(139, 92, 246, 0.15); padding:4px 8px; border-radius:6px; font-weight:800; font-size:11px; text-transform:uppercase; border:1px solid #8b5cf6;">🧲 RESTING ON PoC</span>'
                return c
        return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as e:
        for r in e.map(proc, coins):
            if r: pocs.append(r)
    pocs.sort(key=lambda x: x.get('dist', 100))
    rows = "".join([format_row(i, c['coin'], c['intent'], c['price'], c['change'], c['volume'], f'<span class="spike-badge" style="background:#f3e8ff; color:#7e22ce; border:1px solid #e9d5ff;">PoC: ${c["poc"]:,.4f}</span>') for i, c in enumerate(pocs[:15], 1)])
    yield build_report_html("🧲 Point of Control", "#8b5cf6", {"Timeframe": timeframe, "Min Volume": f"${min_volume:,.0f}", "Retests": f"<span style='color:#8b5cf6'>{len(pocs)}</span>"}, rows)

# --- 5. THE WHALE HUNTER ---
def run_whale_hunter(timeframe, min_volume):
    yield get_spinner("#0ea5e9", "Hunting Volume Anomalies...")
    coin_list = get_high_volume_pairs(min_volume)
    coins, spikes = coin_list if isinstance(coin_list, list) else [], []
    def proc(c):
        df = fetch_data(c['coin'], timeframe)
        if df is not None and len(df) > 26:
            avg_v = df['volume'].iloc[-26:-2].mean()
            last_closed_vol = df['volume'].iloc[-2]
            if avg_v > 0 and (last_closed_vol / avg_v) >= 2.0:
                c['vol_mult'], c['intent'] = last_closed_vol / avg_v, get_intent_badge(df.iloc[:-1])
                return c
        return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as e:
        for r in e.map(proc, coins):
            if r: spikes.append(r)
    spikes.sort(key=lambda x: x.get('vol_mult', 0), reverse=True)
    rows = "".join([format_row(i, c['coin'], c['intent'], c['price'], c['change'], c['volume'], f'<span class="spike-badge high-spike">🔥 {c["vol_mult"]:.1f}x</span>' if c["vol_mult"]>=4.0 else f'<span class="spike-badge med-spike">🌊 {c["vol_mult"]:.1f}x</span>') for i, c in enumerate(spikes[:15], 1)])
    yield build_report_html("🐋 Top Whale Anomalies", "#0ea5e9", {"Timeframe": timeframe, "Min Volume": f"${min_volume:,.0f}", "Anomalies": f"<span style='color:#0ea5e9'>{len(spikes)}</span>"}, rows)

# --- 6. WHALE BUY SPREE ---
def run_whale_buyer(timeframe, min_volume):
    yield get_spinner("#10b981", "Tracking Whale Orders...")
    coins, buys = get_high_volume_pairs(min_volume), []
    def proc(c):
        df = fetch_data(c['coin'], timeframe)
        if df is not None and len(df) > 25:
            avg_v = df['volume'].iloc[-25:-1].mean()
            v_rat = df['volume'].iloc[-1] / avg_v if avg_v > 0 else 1.0
            r = df.iloc[-1]['high'] - df.iloc[-1]['low']
            p_rat = (df.iloc[-1]['close'] - df.iloc[-1]['low']) / (r if r != 0 else 1)
            if v_rat >= 2.5 and p_rat >= 0.75:
                c['vol_mult'], c['intent'] = v_rat, '<span style="color:#10b981; background:rgba(16, 185, 129, 0.15); padding:4px 8px; border-radius:6px; font-weight:800; font-size:11px; text-transform:uppercase; border:1px solid #10b981;">🐋 ACCUMULATION</span>'
                return c
        return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as e:
        for r in e.map(proc, coins):
            if r: buys.append(r)
    buys.sort(key=lambda x: x.get('vol_mult', 0), reverse=True)
    rows = "".join([format_row(i, c['coin'], c['intent'], c['price'], c['change'], c['volume'], f'<span class="spike-badge" style="background:#dcfce7; color:#15803d; border:1px solid #bbf7d0;">🔥 {c["vol_mult"]:.1f}x Spurt</span>') for i, c in enumerate(buys[:15], 1)])
    yield build_report_html("🟢 Whale Accumulation", "#10b981", {"Timeframe": timeframe, "Min Volume": f"${min_volume:,.0f}", "Assets Found": f"<span style='color:#10b981'>{len(buys)}</span>"}, rows)

# --- 7. HIGH VOLATILITY SCANNER ---
def run_volatility_scanner(timeframe, min_volume):
    yield get_spinner("#ef4444", "Scanning for Extreme Volatility...")
    coins, vol_coins = get_high_volume_pairs(min_volume), []
    def proc(c):
        df = fetch_data(c['coin'], timeframe, limit=100)
        if df is not None and len(df) > 15:
            prev_close = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - prev_close).abs()
            tr3 = (df['low'] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]
            close_price = df['close'].iloc[-1]
            if close_price > 0:
                atr_pct = (atr / close_price) * 100
                if atr_pct >= 2.0:
                    c['atr_pct'] = atr_pct
                    c['intent'] = '<span style="color:#ef4444; background:rgba(239, 68, 68, 0.15); padding:4px 8px; border-radius:6px; font-weight:800; font-size:11px; text-transform:uppercase; border:1px solid #ef4444;">⚡ HIGH RISK</span>'
                    return c
        return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as e:
        for r in e.map(proc, coins):
            if r: vol_coins.append(r)
    vol_coins.sort(key=lambda x: x.get('atr_pct', 0), reverse=True)
    rows = "".join([format_row(i, c['coin'], c['intent'], c['price'], c['change'], c['volume'], f'<span class="spike-badge high-spike" style="background:#fef2f2; color:#b91c1c; border-color:#fecaca;">Swing: {c["atr_pct"]:.2f}%</span>') for i, c in enumerate(vol_coins[:15], 1)])
    meta = {"Timeframe": timeframe, "Min Volume": f"${min_volume:,.0f}", "Wild Assets": f"<span style='color:#ef4444'>{len(vol_coins)}</span>"}
    yield build_report_html("⚡ Extreme Volatility Screener", "#ef4444", meta, rows)

# --- 8. STEALTH ACCUMULATION ---
def run_buy_the_rumor(timeframe, min_volume):
    yield get_spinner("#14b8a6", "Detecting Stealth Accumulation...")
    coins, rumors = get_high_volume_pairs(min_volume), []
    def proc(c):
        df = fetch_data(c['coin'], timeframe)
        if df is not None and len(df) > 30:
            recent = df.iloc[-6:-1]
            baseline = df.iloc[-26:-6]
            baseline_vol = baseline['volume'].mean()
            recent_vol = recent['volume'].mean()
            if baseline_vol > 0:
                vol_surge = recent_vol / baseline_vol
                period_max = df['high'].iloc[-26:-1].max()
                period_min = df['low'].iloc[-26:-1].min()
                price_range_pct = ((period_max - period_min) / period_min) * 100
                recent_closes = recent['close'].values
                recent_opens = recent['open'].values
                bullish_creeps = sum([1 for i in range(len(recent_closes)) if recent_closes[i] > recent_opens[i]])
                if vol_surge >= 1.5 and price_range_pct <= 10.0 and bullish_creeps >= 3:
                    c['vol_surge'] = vol_surge
                    c['tightness'] = price_range_pct
                    c['intent'] = '<span style="color:#14b8a6; background:rgba(20, 184, 166, 0.15); padding:4px 8px; border-radius:6px; font-weight:800; font-size:11px; text-transform:uppercase; border:1px solid #14b8a6;">🤫 ACCUMULATING</span>'
                    return c
        return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as e:
        for r in e.map(proc, coins):
            if r: rumors.append(r)
    rumors.sort(key=lambda x: x.get('vol_surge', 0), reverse=True)
    rows = "".join([format_row(i, c['coin'], c['intent'], c['price'], c['change'], c['volume'], f'<span class="spike-badge high-spike" style="background:#ccfbf1; color:#0f766e; border-color:#99f6e4;">Volume Up {c["vol_surge"]:.1f}x</span>') for i, c in enumerate(rumors[:15], 1)])
    meta = {"Timeframe": timeframe, "Min Volume": f"${min_volume:,.0f}", "Rumors Detected": f"<span style='color:#14b8a6'>{len(rumors)}</span>"}
    yield build_report_html("🤫 Buy The Rumor", "#14b8a6", meta, rows)

# --- 9. SINGLE-PAGE TRACKER APP (WITH VELOCITY) ---

def render_tracker_table(state_json):
    try: tracked = json.loads(state_json) if state_json else []
    except: tracked = []

    btc_p12, btc_ema = 1.0, 1.0
    try:
        res = requests.get(f"{BASE_URL}/klines?symbol=BTCUSDT&interval=4h&limit=200", timeout=5).json()
        if isinstance(res, list) and len(res) > 4:
            df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'])
            closes = df['close'].astype(float)
            btc_ema = closes.ewm(span=50, adjust=False).mean().iloc[-1]
            btc_p12 = closes.iloc[-4]
    except: pass
    
    tracker_data_for_js = []
    rows_html = ""
    
    if not tracked:
        rows_html = "<tr><td colspan='3' style='text-align:center; padding:40px; color:#6b7280; font-weight:600;'>No assets tracked. Add a coin above.</td></tr>"
    else:
        for i, a in enumerate(tracked):
            sym = a['sym']
            tf = a['tf']
            
            # Fetch the 12H historical price for the coin's specific velocity
            ref_p12 = 0.0
            try:
                k_res = requests.get(f"{BASE_URL}/klines?symbol={sym}&interval=4h&limit=4", timeout=2).json()
                if isinstance(k_res, list) and len(k_res) >= 4:
                    ref_p12 = float(k_res[0][4])
            except: pass
            
            tracker_data_for_js.append({
                "sym": sym,
                "ent": a.get("ent", 0.0),
                "tf": tf,
                "avg_v": a.get("avg_v", 1.0),
                "ref_p12": ref_p12
            })
            
            rows_html += f"""
            <tr>
                <td>
                    <div style="display:flex; align-items:center; margin-bottom:6px;">
                        <a href="https://www.tradingview.com/chart/?symbol=BINANCE:{sym}" target="_blank" style="text-decoration:none; font-weight:800; font-size:16px; color:var(--text-main);">
                            {sym.replace('USDT','')}
                        </a>
                        <span style="font-size:11px; font-weight:700; color:var(--text-mut); background:rgba(107,114,128,0.1); padding:2px 6px; border-radius:4px; margin-left:6px;">{tf}</span>
                    </div>
                    <div style="display:flex; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:4px;">
                        <span id="p_{i}" style="font-weight:800; font-size:15px; color:var(--text-main);">--</span>
                        <span id="c_{i}" style="font-weight:700; font-size:12px;">--</span>
                    </div>
                    <div style="display:flex; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:6px;">
                        <span id="vel_{i}" style="font-size:10px; font-weight:800; padding:2px 6px; border-radius:4px; background: rgba(107,114,128,0.1); color: var(--text-mut);">12H Vel: --</span>
                        <span id="v_{i}" style="font-size:11px; font-weight:600; color:var(--text-mut);">Vol: --</span>
                    </div>
                    <div style="display:flex; align-items:center; flex-wrap:wrap; gap:6px;">
                        <span id="vm_{i}">--</span>
                        <span id="int_{i}">--</span>
                        <span id="alg_{i}" style="font-size:10px; font-weight:800; border-radius:4px; padding:2px 6px;">--</span>
                    </div>
                </td>
                <td style="text-align:right; vertical-align:top;">
                    <span class="pnl" id="pnl_{i}" style="font-size: 16px; font-weight: 900; display:block;">--</span>
                    <span class="stop" id="stp_{i}" style="font-size: 11px; font-weight: 600; color: var(--text-mut); display: block; margin-top: 4px;">--</span>
                </td>
                <td style="text-align:right; width:40px; vertical-align:top;">
                    <button class="del-btn" onclick="window.parent.postMessage(JSON.stringify({{action:'delete', idx:{i}}}), '*')" style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; width: 32px; height: 32px; cursor: pointer; transition: 0.2s; font-size: 12px; display: flex; justify-content: center; align-items: center; margin-left: auto;">❌</button>
                </td>
            </tr>
            """
    
    js_arrays = json.dumps(tracker_data_for_js)
    
    html_code = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        :root {{ --bg-card: #f8fafc; --border: #e5e7eb; --text-main: #111827; --text-mut: #6b7280; --danger: #ef4444; --shadow: 0 4px 6px rgba(0,0,0,0.05); }}
        @media (prefers-color-scheme: dark) {{ :root {{ --bg-card: #1e293b; --border: #334155; --text-main: #f8fafc; --text-mut: #94a3b8; --shadow: 0 10px 20px rgba(0,0,0,0.3); }} }}
        body {{ margin: 0; padding: 5px; font-family: 'Inter', sans-serif; background: transparent; color: var(--text-main); }}
        
        .tracker-header {{ display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); border: 1px solid var(--border); border-bottom: none; border-radius: 12px 12px 0 0; padding: 16px 20px; }}
        
        .table-wrap {{ width: 100%; background: var(--bg-card); border: 1px solid var(--border); border-radius: 0 0 12px 12px; box-shadow: var(--shadow); }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; min-width: 100%; }}
        th {{ padding: 12px 16px; font-size: 11px; text-transform: uppercase; font-weight: 800; color: var(--text-mut); border-bottom: 1px solid var(--border); letter-spacing: 0.5px; white-space: nowrap; }}
        td {{ padding: 14px 16px; border-bottom: 1px solid var(--border); vertical-align: top; }}
        tr:last-child td {{ border-bottom: none; }}
        
        /* Mobile Specific Header */
        @media (max-width: 600px) {{
            .tracker-header {{ flex-direction: column; align-items: flex-start; gap: 8px; }}
            .header-price-row {{ flex-direction: column; align-items: flex-start; }}
        }}
    </style></head>
    <body>
        
        <div class="tracker-header">
            <div class="header-price-row" style="display:flex; align-items:center;">
                <span id="mr-badge" style="font-size:20px; margin-right:8px;">⏳</span>
                <div style="display:flex; flex-direction:column; gap:4px;">
                    <span id="mr-price" style="font-weight:800; font-size:20px; letter-spacing:-0.5px; color:var(--text-main);">--</span>
                    <div style="display:flex; align-items:center;">
                        <span style="font-size:11px; font-weight:700; color:var(--text-mut); text-transform:uppercase;">VELOCITY:</span>
                        <span id="mr-vel" style="font-size:13px; font-weight:900; margin-left:6px;">--</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Asset Details</th>
                        <th style="text-align:right;">Open PnL</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>

        <script>
            const tracked = {js_arrays};
            const btc_p12 = {btc_p12:.8f};
            const btc_ema = {btc_ema:.8f};
            let liveData = {{}};
            
            tracked.forEach(a => {{ liveData[a.sym] = {{ cP: 0, cC: 0, vM: 0, vol: 0, isB: false, hP: a.ent }}; }});
            
            function updateDOM() {{
                tracked.forEach((a, i) => {{
                    const d = liveData[a.sym];
                    if(d.cP === 0) return; 

                    const pEl = document.getElementById('p_'+i);
                    if(pEl) pEl.innerText = '$' + d.cP.toLocaleString('en-US', {{minimumFractionDigits:4}});
                    
                    const cEl = document.getElementById('c_'+i);
                    if(cEl) {{
                        cEl.innerText = (d.cC >= 0 ? '+' : '') + d.cC.toFixed(2) + '%';
                        cEl.style.color = d.cC >= 0 ? '#10b981' : '#ef4444';
                    }}

                    const velEl = document.getElementById('vel_'+i);
                    if(velEl && d.cP > 0 && a.ref_p12 > 0) {{
                        let v_val = ((d.cP - a.ref_p12) / a.ref_p12) * 100;
                        velEl.innerText = '12H Vel: ' + (v_val > 0 ? '+' : '') + v_val.toFixed(2) + '%';
                        velEl.style.color = v_val < 0 ? '#ef4444' : '#10b981';
                        velEl.style.background = v_val < 0 ? 'rgba(239, 68, 68, 0.1)' : 'rgba(16, 185, 129, 0.1)';
                    }}
                    
                    const vEl = document.getElementById('v_'+i);
                    if(vEl && d.vol > 0) {{
                        let volVal = d.vol;
                        let volStr = '';
                        if(volVal >= 1000000) volStr = '$' + (volVal/1000000).toFixed(2) + 'M';
                        else if(volVal >= 1000) volStr = '$' + (volVal/1000).toFixed(2) + 'K';
                        else volStr = '$' + volVal.toFixed(0);
                        vEl.innerText = 'Vol: ' + volStr;
                    }}

                    const intEl = document.getElementById('int_'+i);
                    if(intEl) intEl.innerHTML = d.isB ? '<span style="color:#10b981; background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.3); padding:2px 6px; border-radius:4px; font-size:9px; font-weight:800;">🟢 BUY</span>' : '<span style="color:#ef4444; background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.3); padding:2px 6px; border-radius:4px; font-size:9px; font-weight:800;">🔴 SELL</span>';
                    
                    const vmEl = document.getElementById('vm_'+i);
                    if(vmEl) vmEl.innerHTML = d.vM >= 3 ? '<span style="background:#fff7ed; color:#ea580c; border:1px solid #fed7aa; padding:2px 6px; border-radius:4px; font-size:9px; font-weight:800;">🔥 ' + d.vM.toFixed(1) + 'x</span>' : (d.vM >= 1.5 ? '<span style="background:#eff6ff; color:#2563eb; border:1px solid #bfdbfe; padding:2px 6px; border-radius:4px; font-size:9px; font-weight:800;">🌊 ' + d.vM.toFixed(1) + 'x</span>' : '<span style="background:transparent; color:var(--text-mut); border:1px solid var(--border); padding:2px 6px; border-radius:4px; font-size:9px; font-weight:800;">📊 ' + d.vM.toFixed(1) + 'x</span>');

                    let aSP=0, sT='';
                    let t_alg='', c_alg='', bg_alg='';
                    
                    if(a.ent > 0) {{
                        const pct = ((d.cP - a.ent) / a.ent) * 100;
                        const isW = pct >= 0;
                        
                        const pnlEl = document.getElementById('pnl_'+i);
                        if(pnlEl) {{
                            pnlEl.innerText = (isW ? '+' : '') + pct.toFixed(2) + '%';
                            pnlEl.style.color = isW ? '#10b981' : '#ef4444';
                        }}
                        
                        const stpEl = document.getElementById('stp_'+i);
                        if(stpEl) {{
                            if(isW) {{ if(d.cP > d.hP) d.hP = d.cP; aSP = d.hP * 0.97; sT = 'Trail'; stpEl.innerHTML = '🛡️ Trail: $' + aSP.toFixed(4); }}
                            else {{ aSP = a.ent * 0.95; sT = 'STOP'; stpEl.innerHTML = '<span style="color:#ef4444;">🛑 STOP: $' + aSP.toFixed(4) + '</span>'; }}
                        }}
                    }}

                    if(a.ent > 0 && d.cP <= aSP) {{ t_alg = 'SELL (' + sT + ')'; c_alg = '#ef4444'; bg_alg = 'rgba(239,68,68,0.1)'; }}
                    else if(a.ent > 0) {{ t_alg = 'HOLD'; c_alg = '#10b981'; bg_alg = 'rgba(16,185,129,0.1)'; if(!d.isB && d.vM >= 1.5) {{ t_alg = 'HOLD (Drop)'; c_alg = '#eab308'; bg_alg = 'rgba(234,179,8,0.1)'; }} }}
                    else {{ t_alg = 'NEUTRAL'; c_alg = 'var(--text-mut)'; bg_alg = 'transparent'; if(d.cC > 20) {{ t_alg = 'WAIT'; c_alg = '#eab308'; bg_alg = 'rgba(234,179,8,0.1)'; }} else if(d.isB && d.vM >= 1.5) {{ t_alg = 'BUY'; c_alg = '#10b981'; bg_alg = 'rgba(16,185,129,0.1)'; }} }}
                    
                    const algEl = document.getElementById('alg_'+i);
                    if(algEl) {{ 
                        algEl.innerText = t_alg; 
                        algEl.style.color = c_alg; 
                        algEl.style.border = '1px solid ' + c_alg;
                        algEl.style.backgroundColor = bg_alg;
                        algEl.style.padding = '2px 6px';
                        algEl.style.borderRadius = '4px';
                    }}
                }});
            }}

            let streams = ['btcusdt@ticker'];
            if (tracked.length > 0) {{
                tracked.forEach(a => {{
                    let s = a.sym.toLowerCase();
                    streams.push(`${{s}}@ticker`);
                    streams.push(`${{s}}@kline_${{a.tf}}`);
                }});
            }}

            const ws = new WebSocket('wss://stream.binance.com:9443/stream?streams=' + streams.join('/'));
            ws.onmessage = e => {{
                try {{
                    const p = JSON.parse(e.data); if(!p||!p.stream) return;
                    
                    if(p.stream === 'btcusdt@ticker') {{
                        const btc_c = parseFloat(p.data.c);
                        const btc_vel = ((btc_c - btc_p12) / btc_p12) * 100;
                        
                        const mrPrice = document.getElementById('mr-price');
                        if(mrPrice) mrPrice.innerText = '$' + btc_c.toLocaleString('en-US', {{minimumFractionDigits: 2}});
                        
                        let s = "🟢";
                        if (btc_vel <= -3.0) {{ s = "🚨"; }} 
                        else if (btc_c < btc_ema) {{ s = "⚠️"; }}
                        
                        const b = document.getElementById('mr-badge');
                        if(b) b.innerText = s;

                        const vEl = document.getElementById('mr-vel');
                        if(vEl) {{
                            vEl.innerText = (btc_vel > 0 ? '+' : '') + btc_vel.toFixed(2) + '%';
                            vEl.style.color = btc_vel < 0 ? '#ef4444' : '#10b981';
                        }}
                    }}
                    
                    let streamSym = p.stream.split('@')[0].toUpperCase();
                    if(liveData[streamSym]) {{
                        if(p.stream.includes('@ticker')) {{
                            liveData[streamSym].cP = parseFloat(p.data.c);
                            liveData[streamSym].cC = parseFloat(p.data.P);
                            liveData[streamSym].vol = parseFloat(p.data.q);
                        }}
                        else if(p.stream.includes('@kline')) {{
                            const k = p.data.k;
                            liveData[streamSym].isB = ((k.c - k.l) / (k.h - k.l || 1)) >= 0.5;
                            let obj = tracked.find(a => a.sym === streamSym);
                            if(obj && obj.avg_v > 0) liveData[streamSym].vM = parseFloat(k.v) / obj.avg_v;
                        }}
                        updateDOM();
                    }}
                }} catch(err){{}}
            }};
            
            updateDOM();
        </script>
    </body></html>
    """
    
    b64_html = base64.b64encode(html_code.encode('utf-8')).decode('utf-8')
    h = 250 + (len(tracked) * 175)
    return html_code

def process_add(sym, ent, tf, current_state_str):
    try: state = json.loads(current_state_str) if current_state_str else []
    except: state = []

    if not sym or not str(sym).strip():
        html_str = render_tracker_table(json.dumps(state))
        
        b64_html = base64.b64encode(html_str.encode('utf-8')).decode('utf-8')
        h = 250 + (len(state) * 175)
        iframe_html = f'<div style="width: 100%; display: flex; justify-content: center; padding-bottom: 20px;"><iframe src="data:text/html;charset=utf-8;base64,{b64_html}" style="width: 100%; height: {h}px; border: none; overflow: hidden;" scrolling="no"></iframe></div>'
        
        return json.dumps(state), iframe_html, gr.update()

    sym = str(sym).strip().upper()
    if not sym.endswith('USDT'): sym += 'USDT'

    if any(x.get('sym') == sym and x.get('tf') == tf for x in state):
        html_str = render_tracker_table(json.dumps(state))
        
        b64_html = base64.b64encode(html_str.encode('utf-8')).decode('utf-8')
        h = 250 + (len(state) * 175)
        iframe_html = f'<div style="width: 100%; display: flex; justify-content: center; padding-bottom: 20px;"><iframe src="data:text/html;charset=utf-8;base64,{b64_html}" style="width: 100%; height: {h}px; border: none; overflow: hidden;" scrolling="no"></iframe></div>'
        
        return json.dumps(state), iframe_html, gr.update()

    avg_v = 1.0
    try:
        df = fetch_data(sym, tf, limit=26)
        if df is not None and len(df) > 25:
            avg_v = df['volume'].iloc[-26:-1].mean()
    except Exception: pass

    state.append({"sym": sym, "ent": float(ent) if ent else 0.0, "tf": tf, "avg_v": avg_v})
    new_state = json.dumps(state)
    html_str = render_tracker_table(new_state)
    
    b64_html = base64.b64encode(html_str.encode('utf-8')).decode('utf-8')
    h = 250 + (len(state) * 175)
    iframe_html = f'<div style="width: 100%; display: flex; justify-content: center; padding-bottom: 20px;"><iframe src="data:text/html;charset=utf-8;base64,{b64_html}" style="width: 100%; height: {h}px; border: none; overflow: hidden;" scrolling="no"></iframe></div>'
    
    return new_state, iframe_html, gr.update(value="")

def process_load(state_json):
    try: state = json.loads(state_json) if state_json else []
    except: state = []
    
    html_str = render_tracker_table(state_json)
    
    b64_html = base64.b64encode(html_str.encode('utf-8')).decode('utf-8')
    h = 250 + (len(state) * 175)
    iframe_html = f'<div style="width: 100%; display: flex; justify-content: center; padding-bottom: 20px;"><iframe src="data:text/html;charset=utf-8;base64,{b64_html}" style="width: 100%; height: {h}px; border: none; overflow: hidden;" scrolling="no"></iframe></div>'
    
    return state_json, iframe_html


# --- GRADIO UI & CSS ---
custom_css = """
footer, #huggingface-space-header, div.gradio-container header { display: none !important; } 
.top-aligned-row { align-items: flex-start !important; } 
#out1 .wrap.default, #out2 .wrap.default, #out3 .wrap.default, #out4 .wrap.default, #out5 .wrap.default, #out6 .wrap.default, #out7 .wrap.default, #out9 .wrap.default, #tracker_frame .wrap.default { display: none !important; opacity: 0 !important; } 
.modern-spinner { width: 48px; height: 48px; border: 4px solid #e0e7ff; border-top: 4px solid #4f46e5; border-radius: 50%; animation: spin 1s infinite; } 
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } } 
.fade-in { animation: fadeIn 0.4s ease-in-out; } 
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } } 

.market-report-container { background: #ffffff; color: #111827; max-width: 650px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); overflow: hidden; transition: all 0.3s; } 
@media (prefers-color-scheme: dark) { 
    .market-report-container { background: #0f172a !important; color: #f8fafc !important; border-color: #1e293b !important; box-shadow: 0 10px 30px rgba(0,0,0,0.5) !important; } 
    .report-table th, .report-meta, .market-overview-card { background: #0f172a !important; border-color: #1e293b !important; } 
    .report-row { border-color: #1e293b !important; } 
    .report-row:hover { background: #1e293b !important; } 
    .meta-label { color: #94a3b8 !important; } 
} 
.report-header { padding: 20px; text-align: center; color: white; } 
.report-header h2 { margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; } 
.market-overview-card { display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; border-bottom: 1px solid #e5e7eb; } 
.report-meta { padding: 16px 24px; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; border-bottom: 1px solid #e5e7eb; } 
.meta-row { display: flex; flex-direction: column; gap: 4px; } 
.meta-label { color: #6b7280; font-size: 11px; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px; } 
.meta-value { font-weight: 700; font-size: 15px; } 
.meta-accent { font-weight: 800; font-size: 18px; } 
.table-wrapper { overflow-x: auto; } 
.report-table { width: 100%; border-collapse: collapse; font-size: 14px; text-align: left; } 
.report-table th { padding: 16px 15px; color: #6b7280; text-transform: uppercase; font-size: 11px; font-weight: 800; letter-spacing: 0.5px; border-bottom: 1px solid #e5e7eb; white-space: nowrap; } 
.report-row { border-bottom: 1px solid #e5e7eb; transition: background 0.2s; } 
.report-table td { padding: 16px 15px; white-space: nowrap; vertical-align: middle; } 
.col-rank { text-align: center; color: #6b7280; width: 40px; font-weight: 700; } 
.col-price, .col-change, .col-vol { text-align: right; font-weight: 600; } 
.tv-link { text-decoration: none !important; display: inline-block; transition: transform 0.2s; } 
.tv-link:hover { transform: scale(1.08) translateY(-1px); } 
.coin-badge { font-weight: 800; color: inherit; background: rgba(107,114,128,0.15); padding: 6px 10px; border-radius: 8px; border: 1px solid rgba(107,114,128,0.2); } 
.spike-badge { padding: 4px 6px; border-radius: 6px; font-size: 11px; font-weight: 800; letter-spacing: 0.5px; } 
.app-header-container { margin: 0; } 
#btn_reload, #q_state { position: absolute !important; opacity: 0 !important; pointer-events: none !important; height: 0 !important; width: 0 !important; overflow: hidden !important; border: none !important; padding: 0 !important; margin: 0 !important; min-height: 0 !important; min-width: 0 !important; }
"""

anti_pinch_zoom_head = """
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<script>
    window.addEventListener('message', (e) => {
        try {
            let msg = (typeof e.data === 'string') ? JSON.parse(e.data) : e.data;
            if (msg.action === 'delete') {
                let state = JSON.parse(localStorage.getItem('pro_tracker_v46') || '[]');
                state.splice(msg.idx, 1);
                
                let newState = JSON.stringify(state);
                localStorage.setItem('pro_tracker_v46', newState);
                
                let qStateTextarea = document.querySelector('#q_state textarea');
                if(qStateTextarea) {
                    qStateTextarea.value = newState;
                    qStateTextarea.dispatchEvent(new Event('input', {bubbles: true}));
                }
                
                let reloadDiv = document.getElementById('btn_reload');
                if (reloadDiv) {
                    let actualBtn = reloadDiv.querySelector('button');
                    if (actualBtn) {
                        actualBtn.click();
                    } else {
                        reloadDiv.click();
                    }
                }
            }
        } catch(err) {}
    });
</script>
"""
modern_theme = gr.themes.Soft(primary_hue="indigo", secondary_hue="blue", neutral_hue="slate", font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "sans-serif"])

with gr.Blocks(title="Crypto Intelligence Dashboard", theme=modern_theme, css=custom_css, head=anti_pinch_zoom_head) as app:
    with gr.Tabs():
        
        with gr.Tab("🚦 Regime"):
            with gr.Row(equal_height=False, elem_classes="top-aligned-row"):
                with gr.Column(scale=1):
                    btn1 = gr.Button("🚦 Force Refresh", variant="primary", size="lg")
                with gr.Column(scale=2): out1 = gr.HTML("<div class='lookup-placeholder'>Loading Live Stream...</div>", elem_id="out1")
            btn1.click(fn=run_market_regime, inputs=[], outputs=out1)

        with gr.Tab("🎯 Trend"):
            with gr.Row(equal_height=False, elem_classes="top-aligned-row"):
                with gr.Column(scale=1):
                    in_tf1 = gr.Dropdown(choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"], value="4h", label="Timeframe")
                    in_v1 = gr.Number(value=1000000, label="Min 24H Volume (USDT)")
                    in_l1 = gr.Slider(1, 20, 2, step=1, label="Lookback Window")
                    btn2 = gr.Button("🚀 Scan Market", variant="primary", size="lg")
                with gr.Column(scale=2): out2 = gr.HTML("<div class='lookup-placeholder'>Click to scan.</div>", elem_id="out2")
            btn2.click(fn=run_web_screener, inputs=[in_tf1, in_v1, in_l1], outputs=out2)

        with gr.Tab("🗜️ Squeeze"):
            with gr.Row(equal_height=False, elem_classes="top-aligned-row"):
                with gr.Column(scale=1):
                    in_tf3 = gr.Dropdown(choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"], value="4h", label="Timeframe")
                    in_v3 = gr.Number(value=1000000, label="Min 24H Volume (USDT)")
                    btn3 = gr.Button("🗜️ Scan For Pinches", variant="primary", size="lg")
                with gr.Column(scale=2): out3 = gr.HTML("<div class='lookup-placeholder'>Click to locate coiled setups.</div>", elem_id="out3")
            btn3.click(fn=run_volatility_squeeze, inputs=[in_tf3, in_v3], outputs=out3)

        with gr.Tab("🧲 PoC"):
            with gr.Row(equal_height=False, elem_classes="top-aligned-row"):
                with gr.Column(scale=1):
                    in_tf4 = gr.Dropdown(choices=["15m", "30m", "1h", "4h", "1d"], value="1h", label="Profile Timeframe")
                    in_v4 = gr.Number(value=1000000, label="Min 24H Volume (USDT)")
                    btn4 = gr.Button("🧲 Map Volume Profiles", variant="primary", size="lg")
                with gr.Column(scale=2): out4 = gr.HTML("<div class='lookup-placeholder'>Click to map institutional magnets.</div>", elem_id="out4")
            btn4.click(fn=run_volume_profile, inputs=[in_tf4, in_v4], outputs=out4)
            
        with gr.Tab("🐋 Hunter"):
            with gr.Row(equal_height=False, elem_classes="top-aligned-row"):
                with gr.Column(scale=1):
                    in_tf_wh = gr.Dropdown(choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"], value="15m", label="Timeframe")
                    in_v_wh = gr.Number(value=1000000, label="Min 24H Volume (USDT)")
                    btn5 = gr.Button("🐋 Hunt Whales", variant="primary", size="lg")
                with gr.Column(scale=2): out5 = gr.HTML("<div class='lookup-placeholder'>Click to hunt whale volume.</div>", elem_id="out5")
            btn5.click(fn=run_whale_hunter, inputs=[in_tf_wh, in_v_wh], outputs=out5)

        with gr.Tab("🟢 Spree"):
            with gr.Row(equal_height=False, elem_classes="top-aligned-row"):
                with gr.Column(scale=1):
                    in_tf6 = gr.Dropdown(choices=["1m", "5m", "15m", "30m", "1h", "4h"], value="5m", label="Timeframe")
                    in_v6 = gr.Number(value=500000, label="Min 24H Volume (USDT)")
                    btn6 = gr.Button("🟢 Scan Whales", variant="primary", size="lg")
                with gr.Column(scale=2): out6 = gr.HTML("<div class='lookup-placeholder'>Click to detect surges.</div>", elem_id="out6")
            btn6.click(fn=run_whale_buyer, inputs=[in_tf6, in_v6], outputs=out6)

        with gr.Tab("⚡ Swings"):
            with gr.Row(equal_height=False, elem_classes="top-aligned-row"):
                with gr.Column(scale=1):
                    in_tf_vol = gr.Dropdown(choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"], value="15m", label="Timeframe")
                    in_v_vol = gr.Number(value=1000000, label="Min 24H Volume (USDT)")
                    btn_vol = gr.Button("⚡ Scan Volatility", variant="primary", size="lg")
                with gr.Column(scale=2): out7 = gr.HTML("<div class='lookup-placeholder'>Click to find wild assets.</div>", elem_id="out7")
            btn_vol.click(fn=run_volatility_scanner, inputs=[in_tf_vol, in_v_vol], outputs=out7)

        with gr.Tab("🤫 Rumors"):
            with gr.Row(equal_height=False, elem_classes="top-aligned-row"):
                with gr.Column(scale=1):
                    in_tf_rumor = gr.Dropdown(choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"], value="15m", label="Timeframe")
                    in_v_rumor = gr.Number(value=1000000, label="Min 24H Volume (USDT)")
                    btn_rumor = gr.Button("🤫 Scan Rumors", variant="primary", size="lg")
                with gr.Column(scale=2): out9 = gr.HTML("<div class='lookup-placeholder'>Click to detect stealth accumulation.</div>", elem_id="out9")
            btn_rumor.click(fn=run_buy_the_rumor, inputs=[in_tf_rumor, in_v_rumor], outputs=out9)

        with gr.Tab("🔍 Tracker"):
            with gr.Row(elem_classes="tracker-inputs"):
                with gr.Column(scale=2):
                    q_sym = gr.Textbox(placeholder="Coin (e.g. SOL)", show_label=False)
                with gr.Column(scale=2):
                    q_ent = gr.Number(label="Entry Price (Opt)", value=0)
                with gr.Column(scale=1):
                    q_tf = gr.Dropdown(choices=["1m", "5m", "15m", "30m", "1h", "4h"], value="15m", show_label=False)
                with gr.Column(scale=1):
                    btn_add = gr.Button("➕ Add", variant="primary")
                with gr.Column(scale=1):
                    btn_reload = gr.Button("🔄 Refresh Tracker", elem_id="btn_reload")
            
            q_state = gr.Textbox(visible=False, elem_id="q_state")
            tracker_html = gr.HTML("<div class='lookup-placeholder'>Loading Tracker...</div>", elem_id="tracker_frame")

            btn_add.click(
                fn=process_add,
                inputs=[q_sym, q_ent, q_tf, q_state],
                outputs=[q_state, tracker_html, q_sym],
            )

            q_state.change(
                fn=None, 
                inputs=[q_state], 
                outputs=None, 
                js="(s) => { if(s){ localStorage.setItem('pro_tracker_v46', s); } return []; }"
            )

            btn_reload.click(
                fn=process_load,
                inputs=[q_state],
                outputs=[q_state, tracker_html],
                js="() => { return [localStorage.getItem('pro_tracker_v46') || '[]']; }"
            )

    app.load(fn=run_market_regime, inputs=[], outputs=[out1])
    app.load(
        fn=process_load,
        inputs=[q_state],
        outputs=[q_state, tracker_html],
        js="() => { return [localStorage.getItem('pro_tracker_v46') || '[]']; }"
    )

app.launch(server_name="0.0.0.0", server_port=7860)
