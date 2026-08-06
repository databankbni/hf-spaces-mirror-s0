import html as _html
import io
import os
import base64
import pickle
from urllib.parse import quote
from datetime import date, datetime
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from data.fetcher_kr import get_kr_price, get_kr_info
from data.fetcher_us import get_us_price, get_us_info
from data.scanner import get_financial_grades, scan_stocks
from analysis.indicators import add_indicators
from analysis.recommender import recommend

st.set_page_config(page_title="주식 분석/추천", page_icon="📈", layout="wide")

# ── 세션 상태 초기화
if "page" not in st.session_state:
    st.session_state.page = "개별 종목 분석"
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "005930"
if "auto_analyze" not in st.session_state:
    st.session_state.auto_analyze = False

SIGNAL_COLOR = {
    "강력매수": "#e53935", "매수": "#ef9a9a", "중립": "#9e9e9e",
    "매도": "#64b5f6", "강력매도": "#1565c0",
}
SIGNAL_EMOJI = {
    "강력매수": "🔴 강력매수", "매수": "🟠 매수", "중립": "⚪ 중립",
    "매도": "🔵 매도", "강력매도": "🟣 강력매도",
}
GRADE_COLOR = {
    "A+": "#e53935", "A": "#fb8c00", "B": "#fdd835", "C": "#78909c", "N/A": "#424242",
}
SIGNAL_COLOR_SCAN = {
    "강력매수": "#b71c1c", "매수": "#e53935", "중립": "#546e7a",
    "매도": "#1565c0", "강력매도": "#0d47a1", "N/A": "#424242",
}
SIG_ORDER = {"강력매도": 0, "매도": 1, "중립": 2, "매수": 3, "강력매수": 4}
SIG_HIST_FILE = "briefing_sig_hist.pkl"


def load_data(market, ticker, period):
    if market == "국내 (KRX)":
        return get_kr_price(ticker, days=period), get_kr_info(ticker)
    return get_us_price(ticker, days=period), get_us_info(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def _krx_list():
    from data.fetcher_kr import get_kr_stock_list
    return get_kr_stock_list()


def resolve_kr(query):
    """종목명 또는 6자리 코드 → (code, 매칭된 이름 or None). 못 찾으면 (None, None)."""
    q = str(query).strip()
    if q.isdigit() and len(q) == 6:
        return q, None
    try:
        lst = _krx_list()
        m = lst[lst["Name"].str.contains(q, case=False, na=False)]
        if m.empty:
            return None, None
        row = m.iloc[0]
        return str(row["Code"]).zfill(6), row["Name"]
    except Exception:
        return None, None


def draw_chart(df, ticker, name):
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True,
        row_heights=[0.5, 0.15, 0.2, 0.15], vertical_spacing=0.03,
        subplot_titles=("주가 / 볼린저밴드 / 이동평균", "거래량", "MACD", "RSI"),
    )
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="주가", increasing_line_color="#e53935", decreasing_line_color="#1565c0",
    ), row=1, col=1)
    for col, color, label in [
        ("ma5", "#f59e0b", "MA5"), ("ma20", "#10b981", "MA20"),
        ("ma60", "#6366f1", "MA60"), ("ma120", "#ec4899", "MA120"),
    ]:
        if col in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df[col], name=label,
                                     line=dict(color=color, width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"],
                             line=dict(color="rgba(150,150,150,0.5)", dash="dot"),
                             showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"],
                             line=dict(color="rgba(150,150,150,0.5)", dash="dot"),
                             fill="tonexty", fillcolor="rgba(150,150,150,0.05)",
                             showlegend=False), row=1, col=1)
    colors = ["#e53935" if c >= o else "#1565c0" for c, o in zip(df["close"], df["open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], marker_color=colors,
                         showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["vol_ma20"],
                             line=dict(color="#f59e0b", width=1), showlegend=False), row=2, col=1)
    macd_colors = ["#e53935" if v >= 0 else "#1565c0" for v in df["macd_hist"]]
    fig.add_trace(go.Bar(x=df.index, y=df["macd_hist"], marker_color=macd_colors,
                         showlegend=False), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["macd"], name="MACD",
                             line=dict(color="#10b981", width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["macd_signal"], name="Signal",
                             line=dict(color="#f59e0b", width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["rsi"], name="RSI",
                             line=dict(color="#6366f1", width=1.5)), row=4, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=4, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="blue", row=4, col=1)
    fig.update_layout(
        title=f"{name} ({ticker})", height=800, xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=0, r=0, t=60, b=0), template="plotly_dark",
    )
    return fig


def draw_financial_chart(grades, name):
    quarters = grades["quarters"]
    metrics = {
        "매출": (grades["revenue"], grades["grade_revenue"]),
        "영업이익": (grades["operating"], grades["grade_operating"]),
        "당기순이익": (grades["net"], grades["grade_net"]),
    }
    fig = make_subplots(rows=1, cols=3, subplot_titles=[
        f"매출  [{grades['grade_revenue']}]",
        f"영업이익  [{grades['grade_operating']}]",
        f"당기순이익  [{grades['grade_net']}]",
    ])
    for col_idx, (label, (values, grade)) in enumerate(metrics.items(), start=1):
        bar_colors = [GRADE_COLOR.get(grade, "#9e9e9e") if i == 0 else "#546e7a"
                      for i, _ in enumerate(values)]
        vals_eok = [v / 1e8 if v is not None and not pd.isna(v) else 0 for v in values]
        fig.add_trace(go.Bar(
            x=quarters, y=vals_eok, marker_color=bar_colors,
            text=[f"{v:,.0f}억" if v != 0 else "N/A" for v in vals_eok],
            textposition="outside", showlegend=False,
        ), row=1, col=col_idx)
    fig.update_layout(
        title=f"{name} — 분기 재무 현황 (최근 4분기, 억원)",
        height=420, template="plotly_dark", margin=dict(l=20, r=20, t=80, b=40),
    )
    return fig


# ══════════════════════════════════════════════════
# 공통 헬퍼
# ══════════════════════════════════════════════════
def grade_badge(val):
    color = GRADE_COLOR.get(val, "#424242")
    return f"background-color:{color}55; color:white; font-weight:bold; text-align:center;"


def signal_badge(val):
    color = SIGNAL_COLOR_SCAN.get(val, "#424242")
    return f"background-color:{color}88; color:white; font-weight:bold; text-align:center;"


def make_sparkline(vals, width=110, height=26, pad=3):
    """최근 종가 흐름 인라인 SVG (상승=빨강, 하락=파랑)."""
    vals = [float(v) for v in vals if v is not None and not pd.isna(v)]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    xs = lambda i: pad + i * (width - 2 * pad) / (n - 1)
    ys = lambda v: pad + (height - 2 * pad) * (1 - (v - lo) / rng)
    pts = " ".join(f"{xs(i):.1f},{ys(v):.1f}" for i, v in enumerate(vals))
    color = "#e53935" if vals[-1] >= vals[0] else "#1565c0"
    lx, ly = xs(n - 1), ys(vals[-1])
    return (f"<svg width='{width}' height='{height}' viewBox='0 0 {width} {height}' "
            f"style='vertical-align:middle;'>"
            f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='1.5'/>"
            f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='2' fill='{color}'/></svg>")


def signal_change_badge(prev_sig, today_sig):
    if not prev_sig:
        return ("<span style='background:#eee;color:#666;border-radius:5px;"
                "padding:1px 6px;font-size:0.72rem;'>NEW</span>")
    if prev_sig == today_sig:
        return "<span style='color:#9e9e9e;font-size:0.78rem;'>↔ 유지</span>"
    up = SIG_ORDER.get(today_sig, 2) > SIG_ORDER.get(prev_sig, 2)
    arrow = "▲" if up else "▼"
    color = "#e53935" if up else "#1565c0"
    return (f"<span style='color:{color};font-size:0.8rem;font-weight:bold;'>"
            f"{prev_sig} {arrow} {today_sig}</span>")


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
with open(os.path.join(STATIC_DIR, "ping.txt"), "w") as _f:
    _f.write("ok")   # 정적 파일 서빙 동작 확인용


def xlsx_download_button(data, filename, label, key, sheets=None):
    """엑셀 보기 버튼 — 상단에 ✕ 닫기 버튼이 있는 자체 뷰어 페이지를 새 창으로 연다.
    (xlsx 를 바로 열면 아이폰 전체화면 앱에서 iOS 파일 미리보기가 화면을 덮어
     닫을 방법이 없으므로, 우리가 만든 HTML 뷰어를 거친다)
    뷰어 = ✕ 닫기 버튼 + 표 내용(sheets) + 'Excel로 열기' 링크."""
    now_ts = datetime.now().timestamp()
    for old in os.listdir(STATIC_DIR):          # 하루 지난 파일 정리
        fp = os.path.join(STATIC_DIR, old)
        try:
            if old.endswith((".xlsx", ".html")) and now_ts - os.path.getmtime(fp) > 86400:
                os.remove(fp)
        except OSError:
            pass
    with open(os.path.join(STATIC_DIR, filename), "wb") as f:
        f.write(data)

    title = _html.escape(os.path.splitext(filename)[0].replace("_", " "))
    parts = []
    for sheet_name, sdf in (sheets or {}).items():
        parts.append(f"<h2>{_html.escape(str(sheet_name))} ({len(sdf)}행)</h2>")
        parts.append("<div class='scroll'>"
                     + sdf.to_html(index=False, border=0, na_rep="", classes="tbl")
                     + "</div>")
    viewer_name = os.path.splitext(filename)[0] + ".html"
    viewer_html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
body{{margin:0;font-family:-apple-system,'Malgun Gothic',sans-serif;background:#fafafa;}}
.topbar{{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:10px;
 background:#0d47a1;color:#fff;padding:10px 12px;
 padding-top:calc(10px + env(safe-area-inset-top));}}
.topbar button{{background:#fff;color:#0d47a1;border:none;border-radius:8px;
 padding:10px 16px;font-size:16px;font-weight:bold;}}
.topbar .t{{flex:1;font-size:14px;font-weight:bold;overflow:hidden;
 text-overflow:ellipsis;white-space:nowrap;}}
.topbar a{{color:#fff;font-size:13px;text-decoration:underline;white-space:nowrap;}}
.wrap{{padding:10px;}}
h2{{font-size:15px;margin:14px 2px 6px;}}
.scroll{{overflow-x:auto;background:#fff;border:1px solid #e0e0e0;border-radius:8px;}}
table.tbl{{border-collapse:collapse;font-size:12.5px;white-space:nowrap;}}
.tbl th{{position:sticky;top:0;background:#eceff1;padding:7px 9px;text-align:left;
 border-bottom:2px solid #b0bec5;}}
.tbl td{{padding:6px 9px;border-bottom:1px solid #eceff1;}}
.tbl tr:nth-child(even) td{{background:#f7f9fa;}}
td.sig-buy{{color:#c62828;font-weight:bold;}} td.sig-sell{{color:#1565c0;font-weight:bold;}}
.note{{color:#78909c;font-size:12px;margin:10px 2px 20px;}}
</style></head><body>
<div class="topbar">
  <button onclick="closeMe()">✕ 닫기</button>
  <span class="t">{title}</span>
  <a href="{quote(filename)}">📊 Excel로 열기</a>
</div>
<div class="wrap">
{''.join(parts)}
<p class="note">'Excel로 열기'로 나간 뒤에는 홈 화면에서 앱을 다시 열어 주세요 —
오늘 만든 결과는 저장되어 있어 다시 스캔하지 않고 바로 표시됩니다.</p>
</div>
<script>
document.querySelectorAll("td").forEach(function(td){{
  var v = td.textContent.trim();
  if (v === "매수" || v === "강력매수") td.className = "sig-buy";
  else if (v === "매도" || v === "강력매도") td.className = "sig-sell";
}});
function closeMe(){{
  if (history.length > 1) {{ history.back(); }}
  else {{ window.close();
          setTimeout(function(){{ location.href = document.referrer || "/"; }}, 300); }}
}}
</script></body></html>"""
    with open(os.path.join(STATIC_DIR, viewer_name), "w", encoding="utf-8") as f:
        f.write(viewer_html)

    url = "app/static/" + quote(viewer_name)
    st.markdown(
        f'<a href="{url}" target="_blank" rel="noopener" '
        f'style="display:block;width:100%;box-sizing:border-box;text-align:center;'
        f'padding:11px 0;background:#1565c0;color:#fff;border-radius:8px;'
        f'text-decoration:none;font-weight:bold;margin:2px 0;">📥 {label}</a>',
        unsafe_allow_html=True)


APP_DIR = os.path.dirname(os.path.abspath(__file__))


def disk_cache_load(fname, key):
    """디스크 캐시 읽기 — 접속이 끊겨 세션이 사라져도 당일 결과 재사용."""
    try:
        with open(os.path.join(APP_DIR, fname), "rb") as f:
            c = pickle.load(f)
        if c.get("key") == key:
            return c.get("data")
    except Exception:
        pass
    return None


def disk_cache_save(fname, key, data):
    try:
        with open(os.path.join(APP_DIR, fname), "wb") as f:
            pickle.dump({"key": key, "data": data}, f)
    except Exception:
        pass


def get_scan_result(n, workers=10, market="KR"):
    """스캔 결과를 세션+디스크에 캐시 (같은 날·같은 N·같은 시장이면 재사용)."""
    key = f"scan_{market}_{date.today().isoformat()}_{n}"
    if st.session_state.get(key) is not None:
        return st.session_state[key]
    df = disk_cache_load(f"scan_cache_{market}.pkl", key)
    if df is not None:
        st.session_state[key] = df
        return df
    mkt_label = "미국" if market == "US" else "국내"
    pb = st.progress(0.0, text=f"{mkt_label} 시총 상위 {n}개 종목 재무 스캔 중... (수 분 소요)")
    stt = st.empty()
    df = scan_stocks(n=n, progress_bar=pb, status_text=stt, max_workers=workers, market=market)
    pb.empty()
    stt.empty()
    st.session_state[key] = df
    disk_cache_save(f"scan_cache_{market}.pkl", key, df)
    return df


def load_today_brief(market):
    """오늘 만들어 둔 브리핑을 디스크에서 복원 (새 접속 시 재스캔 방지)."""
    try:
        with open(os.path.join(APP_DIR, f"brief_cache_{market}.pkl"), "rb") as f:
            c = pickle.load(f)
        if str(c.get("key", "")).startswith(f"brief_{market}_{date.today().isoformat()}_"):
            return c["key"], c["data"]
    except Exception:
        pass
    return None


def _briefing_detail(code, name, market="KR"):
    try:
        price_df = get_us_price(code, 365) if market == "US" else get_kr_price(code, 365)
        df = add_indicators(price_df)
        rec = recommend(df)
        latest = df.iloc[-1]
        prevc = df.iloc[-2]["close"] if len(df) >= 2 else latest["close"]
        chg = latest["close"] - prevc
        c, m5, m20, m60 = latest["close"], latest.get("ma5"), latest.get("ma20"), latest.get("ma60")
        if all(pd.notna(x) for x in [m5, m20, m60]):
            ma = ("정배열" if c > m5 > m20 > m60 else
                  "역배열" if c < m5 < m20 < m60 else
                  "MA20 상회" if c > m20 else "MA20 하회")
        else:
            ma = "-"
        return {"ok": True, "code": code, "name": name, "price": c, "chg": chg,
                "chg_pct": (chg / prevc * 100) if prevc else 0, "signal": rec.signal,
                "score": rec.score, "rsi": latest.get("rsi"), "macd_hist": latest.get("macd_hist"),
                "ma": ma, "bb_pct": latest.get("bb_pct"), "vol_ratio": latest.get("vol_ratio"),
                "asof": df.index[-1].strftime("%Y-%m-%d"),
                "reasons": rec.reasons[:2], "warnings": rec.warnings[:2],
                "spark": df["close"].tail(40).tolist()}
    except Exception:
        return {"ok": False, "code": code, "name": name}


def fetch_briefing_details(codes_names, workers=10, market="KR"):
    out = [None] * len(codes_names)
    total = len(codes_names)
    if total == 0:
        return []
    pb = st.progress(0.0, text="현재가·신호 수집 중...")
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_briefing_detail, c, n, market): i for i, (c, n) in enumerate(codes_names)}
        for f in as_completed(futs):
            out[futs[f]] = f.result()
            done += 1
            pb.progress(done / total, text=f"현재가·신호 수집 중... {done}/{total}")
    pb.empty()
    return [o for o in out if o]


def update_sig_hist(today_signals, hist_file=SIG_HIST_FILE):
    """직전 브리핑일 신호 스냅샷을 파일로 관리하고 (prev_signals, prev_date) 반환."""
    today_date = date.today().isoformat()
    hist = {}
    if os.path.exists(hist_file):
        try:
            with open(hist_file, "rb") as f:
                hist = pickle.load(f)
        except Exception:
            hist = {}
    if hist.get("today_date") == today_date:
        prev_signals, prev_date = hist.get("prev", {}), hist.get("prev_date")
    else:
        prev_signals, prev_date = hist.get("today", {}), hist.get("today_date")
    try:
        with open(hist_file, "wb") as f:
            pickle.dump({"today_date": today_date, "today": today_signals,
                         "prev_date": prev_date, "prev": prev_signals}, f)
    except Exception:
        pass
    return prev_signals, prev_date


@st.dialog("📊 개별 종목 분석", width="large")
def analysis_dialog(code: str, name: str, market: str = "국내 (KRX)"):
    period = 365
    is_us = market != "국내 (KRX)"
    with st.spinner(f"{name} ({code}) 데이터 로딩 중..."):
        try:
            df_raw, info = load_data(market, code, period)
            df = add_indicators(df_raw)
            rec = recommend(df)
        except Exception as e:
            st.error(f"데이터 조회 실패: {e}")
            return

    latest = df.iloc[-1]
    prev_close = df.iloc[-2]["close"] if len(df) >= 2 else latest["close"]
    change = latest["close"] - prev_close
    change_pct = change / prev_close * 100

    c1, c2, c3 = st.columns(3)
    c1.metric("종목명", info.get("name", code))
    price_txt = f"$ {latest['close']:,.2f}" if is_us else f"{latest['close']:,.0f} 원"
    c2.metric("현재가", price_txt, f"{change:+,.2f} ({change_pct:+.2f}%)" if is_us
              else f"{change:+,.0f} ({change_pct:+.2f}%)")
    c3.metric("시장", info.get("market", "-"))

    sc = SIGNAL_COLOR[rec.signal]
    st.markdown(
        f"<div style='background:{sc}22; border:2px solid {sc}; border-radius:10px; "
        f"padding:12px; text-align:center; margin:8px 0;'>"
        f"<span style='color:{sc}; font-size:1.6rem; font-weight:bold;'>{SIGNAL_EMOJI[rec.signal]}</span>"
        f" &nbsp; 종합 점수: {rec.score:+.0f}점</div>", unsafe_allow_html=True)

    if is_us:
        grades = get_financial_grades(code)
    else:
        kr_info = get_kr_info(code)
        suffix = ".KQ" if "KOSDAQ" in kr_info.get("market", "") else ".KS"
        grades = get_financial_grades(code + suffix)
    if grades:
        gc1, gc2, gc3 = st.columns(3)
        for col, label, grade in [
            (gc1, "매출", grades["grade_revenue"]),
            (gc2, "영업이익", grades["grade_operating"]),
            (gc3, "당기순이익", grades["grade_net"]),
        ]:
            color = GRADE_COLOR.get(grade, "#9e9e9e")
            col.markdown(
                f"<div style='background:{color}33; border:2px solid {color}; border-radius:8px; "
                f"padding:10px; text-align:center;'>"
                f"<div style='font-size:0.8rem; color:#ccc;'>{label}</div>"
                f"<div style='font-size:2rem; font-weight:bold; color:{color};'>{grade}</div></div>",
                unsafe_allow_html=True)
        st.plotly_chart(draw_financial_chart(grades, info.get("name", code)), use_container_width=True)

    st.plotly_chart(draw_chart(df, code, info.get("name", code)), use_container_width=True)


# ══════════════════════════════════════════════════
# 사이드바 — 모드 선택
# ══════════════════════════════════════════════════
st.sidebar.title("📈 주식 분석/추천")
PAGES = ["개별 종목 분석", "종목 스캔", "🌅 아침 브리핑"]
idx = PAGES.index(st.session_state.page) if st.session_state.page in PAGES else 0
page = st.sidebar.radio("모드 선택", PAGES, index=idx, key="_page_radio")
if page != st.session_state.page:
    st.session_state.page = page


# ══════════════════════════════════════════════════
# 페이지 1: 개별 종목 분석
# ══════════════════════════════════════════════════
if st.session_state.page == "개별 종목 분석":
    market = st.sidebar.radio("시장 선택", ["국내 (KRX)", "해외 (US)"])
    if market == "국내 (KRX)":
        ticker_input = st.sidebar.text_input("종목명 또는 코드", value=st.session_state.selected_ticker,
                                             help="예: 삼성전자 또는 005930")
        st.sidebar.caption("종목명(예: 삼화전자) 또는 6자리 코드를 입력하세요")
    else:
        ticker_input = st.sidebar.text_input("티커 입력", value="AAPL", help="예: AAPL, TSLA, MSFT")
        st.sidebar.caption("미국 주식 티커를 입력하세요")

    period = st.sidebar.selectbox("조회 기간", [90, 180, 365, 730], index=2,
                                  format_func=lambda x: f"{x}일 ({x // 30}개월)")
    analyze_btn = st.sidebar.button("분석 시작", use_container_width=True, type="primary")
    if st.session_state.auto_analyze:
        analyze_btn = True
        st.session_state.auto_analyze = False

    st.sidebar.markdown("---")
    st.sidebar.markdown("**인기 종목**")
    presets = ({"삼성전자": "005930", "SK하이닉스": "000660", "NAVER": "035420",
                "카카오": "035720", "LG에너지솔루션": "373220"} if market == "국내 (KRX)"
               else {"Apple": "AAPL", "NVIDIA": "NVDA", "Tesla": "TSLA",
                     "Microsoft": "MSFT", "Amazon": "AMZN"})
    for pname, code in presets.items():
        if st.sidebar.button(pname, key=f"preset_{code}", use_container_width=True):
            ticker_input = code
            analyze_btn = True

    st.title("📈 주식 기술적 분석 & 추천 시스템")
    st.caption("RSI · MACD · 이동평균 · 볼린저밴드 · 거래량 기반 종합 분석 | 투자 참고용")

    if not analyze_btn:
        st.info("왼쪽 사이드바에서 종목코드를 입력하고 **분석 시작** 버튼을 누르세요.")
        st.stop()

    if market == "국내 (KRX)":
        code, matched = resolve_kr(ticker_input)
        if code is None:
            st.error(f'"{ticker_input}" 에 해당하는 종목을 찾을 수 없습니다. 종목명 또는 6자리 코드를 확인하세요.')
            st.stop()
        ticker = code
        if matched:
            st.info(f'🔎 "{ticker_input}" → **{matched} ({code})** 로 분석합니다.')
    else:
        ticker = ticker_input.strip().upper()
    st.session_state.selected_ticker = ticker

    with st.spinner(f"{ticker} 데이터 로딩 중..."):
        try:
            df_raw, info = load_data(market, ticker, period)
            df = add_indicators(df_raw)
            rec = recommend(df)
        except Exception as e:
            st.error(f"데이터 조회 실패: {e}")
            st.stop()

    latest = df.iloc[-1]
    prev_close = df.iloc[-2]["close"] if len(df) >= 2 else latest["close"]
    change = latest["close"] - prev_close
    change_pct = change / prev_close * 100

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("종목명", info.get("name", ticker))
    c2.metric("현재가", f"{latest['close']:,.0f}" + (" 원" if market == "국내 (KRX)" else " $"),
              f"{change:+,.0f} ({change_pct:+.2f}%)")
    c3.metric("시장", info.get("market", "-"))
    c4.metric("섹터", info.get("sector", "-"))
    c5.metric("업종", info.get("industry", "-"))
    st.markdown("---")

    sc = SIGNAL_COLOR[rec.signal]
    rec_col, detail_col = st.columns([1, 2])
    with rec_col:
        st.markdown(f"""
        <div style="background:{sc}22; border:2px solid {sc}; border-radius:12px; padding:24px; text-align:center;">
            <h1 style="color:{sc}; margin:0; font-size:2.2rem;">{SIGNAL_EMOJI[rec.signal]}</h1>
            <h3 style="margin:8px 0 0;">종합 점수: {rec.score:+.0f}점</h3>
            <p style="margin:4px 0; color:#aaa;">신뢰도: {rec.confidence}</p>
        </div>""", unsafe_allow_html=True)
    with detail_col:
        t1, t2 = st.tabs(["✅ 매수 근거", "⚠️ 주의 사항"])
        with t1:
            for r in rec.reasons:
                st.success(r)
            if not rec.reasons:
                st.info("특이 매수 신호 없음")
        with t2:
            for w in rec.warnings:
                st.warning(w)
            if not rec.warnings:
                st.info("특이 위험 신호 없음")

    st.markdown("---")
    st.subheader("주요 지표 현황")
    i1, i2, i3, i4, i5, i6 = st.columns(6)
    i1.metric("RSI (14)", f"{latest.get('rsi', 0):.1f}",
              "과매도" if latest.get("rsi", 50) < 30 else ("과매수" if latest.get("rsi", 50) > 70 else "중립"))
    i2.metric("MACD", f"{latest.get('macd', 0):.2f}", "양전" if latest.get("macd_hist", 0) > 0 else "음전")
    i3.metric("MA20 대비", f"{(latest['close']/latest.get('ma20', latest['close'])-1)*100:+.1f}%")
    i4.metric("MA60 대비", f"{(latest['close']/latest.get('ma60', latest['close'])-1)*100:+.1f}%")
    i5.metric("BB 위치", f"{latest.get('bb_pct', 0.5)*100:.0f}%",
              "하단" if latest.get("bb_pct", 0.5) < 0.2 else ("상단" if latest.get("bb_pct", 0.5) > 0.8 else "중간"))
    i6.metric("거래량 비율", f"{latest.get('vol_ratio', 1):.1f}x")
    st.markdown("---")

    st.subheader("분기 재무 등급")
    with st.spinner("재무 데이터 로딩 중..."):
        if market == "국내 (KRX)":
            kr_info = get_kr_info(ticker)
            suffix = ".KQ" if "KOSDAQ" in kr_info.get("market", "") else ".KS"
            grades = get_financial_grades(ticker + suffix)
        else:
            grades = get_financial_grades(ticker)
    if grades:
        gc1, gc2, gc3 = st.columns(3)
        for col, label, grade in [
            (gc1, "매출", grades["grade_revenue"]),
            (gc2, "영업이익", grades["grade_operating"]),
            (gc3, "당기순이익", grades["grade_net"]),
        ]:
            color = GRADE_COLOR.get(grade, "#9e9e9e")
            col.markdown(
                f"<div style='background:{color}33; border:2px solid {color}; border-radius:10px; "
                f"padding:16px; text-align:center;'>"
                f"<div style='font-size:0.9rem; color:#ccc;'>{label}</div>"
                f"<div style='font-size:2.5rem; font-weight:bold; color:{color};'>{grade}</div></div>",
                unsafe_allow_html=True)
        st.caption("A+: 최근 분기 > 직전 3분기 모두  |  A: 2개보다 큼  |  B: 1개보다 큼  |  C: 모두보다 작음")
        st.plotly_chart(draw_financial_chart(grades, info.get("name", ticker)), use_container_width=True)
    else:
        st.info("재무 데이터를 가져올 수 없습니다.")
    st.markdown("---")

    st.subheader("기술적 분석 차트")
    st.plotly_chart(draw_chart(df, ticker, info.get("name", ticker)), use_container_width=True)
    st.markdown("---")
    st.caption("⚠️ 본 프로그램은 기술적 분석 지표 기반 참고용 정보입니다. 투자 판단 및 손익 책임은 투자자 본인에게 있습니다.")


# ══════════════════════════════════════════════════
# 페이지 2: 종목 스캔 (2그룹 + 신호 점수 정렬)
# ══════════════════════════════════════════════════
elif st.session_state.page == "종목 스캔":
    st.title("🏆 종목 스캔 — 최근 분기 순이익 A+ 찾기")

    scan_market = st.sidebar.radio("시장", ["🇰🇷 국내", "🇺🇸 미국"], horizontal=True, key="scan_market")
    scan_mkt = "US" if "미국" in scan_market else "KR"
    if scan_mkt == "US":
        st.caption("미국(NASDAQ·NYSE) 시총 상위 종목 중 **당기순이익 A+** 종목을 두 그룹으로 나눠, 매매신호 점수 순으로 보여줍니다. (전일 마감 기준)")
    else:
        st.caption("KOSPI+KOSDAQ 시총 상위 종목 중 **당기순이익 A+** 종목을 두 그룹으로 나눠, 오늘 매매신호 점수 순으로 보여줍니다.")

    scan_n = st.sidebar.slider("스캔 종목 수", 50, 1000, 500, 50)
    workers = st.sidebar.slider("병렬 처리 수", 5, 20, 10, 5, help="높을수록 빠르지만 서버 부하 증가")
    if st.sidebar.button("스캔 시작", use_container_width=True, type="primary"):
        st.session_state["_do_scan"] = (scan_n, workers, scan_mkt)

    trig = st.session_state.get("_do_scan")
    if not trig or len(trig) != 3 or trig[2] != scan_mkt:
        st.info("왼쪽에서 시장·종목 수를 정하고 **스캔 시작**을 누르세요. (무료 서버 기준 500개 수 분, 1000개는 10분 이상 걸릴 수 있습니다)")
        st.stop()

    n_, w_, mkt_ = trig
    df_scan = get_scan_result(n_, w_, mkt_)
    if df_scan is None or df_scan.empty:
        st.error("스캔 결과가 없습니다.")
        st.stop()

    df_ni = df_scan[df_scan["순이익 A+"]].copy()
    df_all = df_ni[df_ni["전체 A+"]].sort_values("신호 점수", ascending=False).reset_index(drop=True)
    df_part = df_ni[~df_ni["전체 A+"]].sort_values("신호 점수", ascending=False).reset_index(drop=True)

    grade_cols = ["매출 등급", "영업이익 등급", "당기순이익 등급"]
    disp_cols = ["종목명", "코드", "시장", "매출 등급", "영업이익 등급", "당기순이익 등급", "매매 신호", "신호 점수"]

    def show_group(df, label):
        if df.empty:
            st.info("해당 종목이 없습니다.")
            return
        disp = df.rename(columns={"Name": "종목명", "Code": "코드", "Market": "시장"})[disp_cols]
        styled = (disp.style.map(grade_badge, subset=grade_cols)
                            .map(signal_badge, subset=["매매 신호"]))
        event = st.dataframe(styled, use_container_width=True,
                             height=min(600, 45 + len(disp) * 35),
                             on_select="rerun", selection_mode="single-row", key=f"tbl_{label}")
        rows = event.selection.rows if event.selection else []
        if rows:
            sel = disp.iloc[rows[0]]
            if st.button(f"📊 {sel['종목명']} 상세 분석", key=f"go_{label}_{sel['코드']}",
                         type="primary", use_container_width=True):
                analysis_dialog(sel["코드"], sel["종목명"],
                                "해외 (US)" if mkt_ == "US" else "국내 (KRX)")

    # 엑셀 다운로드
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_all.to_excel(writer, sheet_name="3개모두A+", index=False)
        df_part.to_excel(writer, sheet_name="순이익만A+", index=False)
        df_scan.to_excel(writer, sheet_name="전체스캔", index=False)
    buf.seek(0)
    mkt_name = "미국" if mkt_ == "US" else "국내"
    xlsx_download_button(buf.getvalue(), f"주식스캔_{mkt_name}_{date.today()}.xlsx",
                         f"스캔결과 엑셀로 보기 — {mkt_name} {date.today()} (상위 {n_}개)", key="dl_scan",
                         sheets={"3개모두A+": df_all, "순이익만A+": df_part, "전체스캔": df_scan})
    st.markdown("---")

    st.subheader(f"🏅 3개 항목 모두 A+ (매출·영업이익·순이익) — {len(df_all)}개")
    show_group(df_all, "all")
    st.markdown("---")
    st.subheader(f"✅ 순이익 A+ · 매출/영업이익은 A·B·C 포함 — {len(df_part)}개")
    show_group(df_part, "part")
    st.caption("⚠️ 맨 오른쪽 신호·점수는 오늘 종가 기준 기술적 판단이며 매일 달라집니다. 종목 행을 선택하면 상세 분석을 볼 수 있습니다.")


# ══════════════════════════════════════════════════
# 페이지 3: 아침 브리핑
# ══════════════════════════════════════════════════
else:
    st.title("🌅 오늘의 아침 브리핑")

    b_market = st.sidebar.radio("시장", ["🇰🇷 국내", "🇺🇸 미국"], horizontal=True, key="brief_market")
    b_mkt = "US" if "미국" in b_market else "KR"
    if b_mkt == "US":
        st.caption("미국 시장: 매출·영업이익·순이익 **모두 A+** 종목 요약 — 미국 장은 한국시간 밤에 열리므로 **전일(미국) 마감 기준**입니다.")
    else:
        st.caption("매출·영업이익·순이익이 **모두 A+** 인 종목을 현재가·기술적 신호와 함께 매수 신호 강한 순으로 요약합니다.")

    b_n = st.sidebar.slider("스캔 종목 수", 50, 1000, 500, 50, key="brief_n")
    b_w = st.sidebar.slider("병렬 처리 수", 5, 20, 10, 5, key="brief_w")
    if st.sidebar.button("브리핑 생성", use_container_width=True, type="primary"):
        st.session_state["_do_brief"] = (b_n, b_w, b_mkt)
        st.session_state.pop(f"brief_{b_mkt}_{date.today().isoformat()}_{b_n}", None)  # 강제 새로 생성

    trig = st.session_state.get("_do_brief")
    if not trig or len(trig) != 3 or trig[2] != b_mkt:
        restored = load_today_brief(b_mkt)
        if restored:
            r_key, r_data = restored
            st.session_state[r_key] = r_data
            st.session_state["_do_brief"] = (int(r_key.rsplit("_", 1)[1]), b_w, b_mkt)
            trig = st.session_state["_do_brief"]
            st.caption("💾 오늘 만들어 둔 브리핑을 불러왔습니다 — 새로 만들려면 왼쪽 **브리핑 생성**을 누르세요.")
        else:
            st.info("왼쪽에서 시장을 고르고 **브리핑 생성**을 누르세요. (스캔이 필요해 무료 서버 기준 500개 수 분, 1000개는 10분 이상 걸릴 수 있습니다)")
            st.stop()

    bn, bw, bm = trig
    is_us_brief = bm == "US"
    brief_key = f"brief_{bm}_{date.today().isoformat()}_{bn}"
    if st.session_state.get(brief_key) is None:
        # 처음 한 번만 계산하고 세션에 저장 → 다운로드 등으로 새로고침돼도 재계산 안 함
        df_scan = get_scan_result(bn, bw, bm)
        if df_scan is None or df_scan.empty:
            st.error("스캔 결과가 없습니다.")
            st.stop()
        df_all = df_scan[df_scan["전체 A+"]]
        codes_names = list(zip(df_all["Code"], df_all["Name"]))
        details = fetch_briefing_details(codes_names, bw, bm)
        _ok = sorted([d for d in details if d.get("ok")], key=lambda d: d["score"], reverse=True)
        _asof = Counter(d["asof"] for d in _ok).most_common(1)[0][0] if _ok else "-"
        _today_signals = {d["code"]: d["signal"] for d in _ok}
        _hist_file = "briefing_sig_hist_us.pkl" if is_us_brief else SIG_HIST_FILE
        _prev_signals, _prev_date = update_sig_hist(_today_signals, _hist_file)
        st.session_state[brief_key] = {"ok": _ok, "asof": _asof,
                                       "prev_signals": _prev_signals, "prev_date": _prev_date}
        disk_cache_save(f"brief_cache_{bm}.pkl", brief_key, st.session_state[brief_key])
    _c = st.session_state[brief_key]
    ok, asof = _c["ok"], _c["asof"]
    prev_signals, prev_date = _c["prev_signals"], _c["prev_date"]

    dist = Counter(d["signal"] for d in ok)
    dist_html = " &nbsp;·&nbsp; ".join(f"{SIGNAL_EMOJI[s]} {dist[s]}"
                                       for s in ["강력매수", "매수", "중립", "매도", "강력매도"] if dist.get(s))
    prev_note = (f"직전 브리핑({prev_date}) 대비 신호 변화 표시" if prev_date
                 else "(첫 브리핑 — 다음 실행부터 신호 변화 표시)")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    brief_title = "🇺🇸 오늘의 미국 매매 브리핑" if is_us_brief else "🌅 오늘의 매매 브리핑"
    st.markdown(
        f"<div style='background:#0d47a1;color:#fff;padding:14px 18px;border-radius:10px;margin-bottom:10px;'>"
        f"<div style='font-size:1.2rem;font-weight:bold;'>{brief_title}</div>"
        f"<div style='opacity:0.9;font-size:0.88rem;margin-top:3px;'>{now_str} 실행 · 종가기준일 <b>{asof}</b> · 3개 항목 모두 A+ "
        f"<b>{len(ok)}</b>개 · {prev_note}</div>"
        f"<div style='margin-top:6px;'>{dist_html or '신호 집계 없음'}</div></div>",
        unsafe_allow_html=True)

    if not ok:
        st.info("분석 가능한 종목이 없습니다.")
        st.stop()

    # 브리핑 엑셀 다운로드
    brief_rows = []
    for d in ok:
        ps = prev_signals.get(d["code"])
        change = "NEW" if not ps else ("유지" if ps == d["signal"] else f"{ps}→{d['signal']}")
        brief_rows.append({
            "종목명": d["name"], "코드": d["code"], "기준거래일": d["asof"],
            "현재가": round(d["price"], 2) if is_us_brief else round(d["price"]),
            "등락": round(d["chg"], 2) if is_us_brief else round(d["chg"]),
            "등락률(%)": round(d["chg_pct"], 2),
            "신호": d["signal"], "점수": int(round(d["score"])), "전일대비신호": change,
            "RSI": round(d["rsi"], 1) if pd.notna(d["rsi"]) else None,
            "MACD": "양전" if (pd.notna(d["macd_hist"]) and d["macd_hist"] > 0) else "음전",
            "이평상태": d["ma"],
            "BB위치(%)": round(d["bb_pct"] * 100) if pd.notna(d["bb_pct"]) else None,
            "거래량비율": round(d["vol_ratio"], 2) if pd.notna(d["vol_ratio"]) else None,
            "매수근거": " / ".join(d["reasons"]),
            "주의사항": " / ".join(d["warnings"]),
        })
    brief_df = pd.DataFrame(brief_rows)
    bbuf = io.BytesIO()
    with pd.ExcelWriter(bbuf, engine="openpyxl") as writer:
        brief_df.to_excel(writer, sheet_name="아침브리핑", index=False)
    bbuf.seek(0)
    bmkt_name = "미국" if is_us_brief else "국내"
    xlsx_download_button(bbuf.getvalue(), f"아침브리핑_{bmkt_name}_{date.today()}.xlsx",
                         f"브리핑 엑셀로 보기 — {bmkt_name} {date.today()} ({len(ok)}종목)", key="dl_brief",
                         sheets={"아침브리핑": brief_df})
    st.markdown("---")

    for d in ok:
        sig = d["signal"]
        color = SIGNAL_COLOR_SCAN.get(sig, "#546e7a")
        chg_color = "#e53935" if d["chg"] >= 0 else "#1565c0"
        change_badge = signal_change_badge(prev_signals.get(d["code"]), sig)
        spark = make_sparkline(d["spark"])
        rsi, bb, vr = d["rsi"], d["bb_pct"], d["vol_ratio"]
        metrics = (f"RSI {rsi:.0f}" if pd.notna(rsi) else "RSI -")
        metrics += f" &nbsp;·&nbsp; MACD {'▲' if (pd.notna(d['macd_hist']) and d['macd_hist'] > 0) else '▼'}"
        metrics += f" &nbsp;·&nbsp; {d['ma']}"
        if pd.notna(bb):
            metrics += f" &nbsp;·&nbsp; BB {bb*100:.0f}%"
        if pd.notna(vr):
            metrics += f" &nbsp;·&nbsp; 거래량 {vr:.1f}x"
        reasons = "".join(f"<li>✅ {x}</li>" for x in d["reasons"]) or "<li style='color:#aaa;'>-</li>"
        warns = "".join(f"<li>⚠️ {x}</li>" for x in d["warnings"]) or "<li style='color:#aaa;'>-</li>"

        col1, col2 = st.columns([9, 1])
        with col1:
            st.markdown(
                f"<div style='border:1px solid #ddd;border-radius:10px;padding:10px 14px;margin-bottom:6px;'>"
                f"<div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap;'>"
                f"<span style='font-size:1.1rem;font-weight:bold;'>{d['name']}</span>"
                f"<span style='color:#888;font-size:0.8rem;'>{d['code']}</span>"
                f"<span style='font-weight:bold;'>{'$' + format(d['price'], ',.2f') if is_us_brief else format(d['price'], ',.0f') + '원'}</span>"
                f"<span style='color:{chg_color};'>{format(d['chg'], '+,.2f') if is_us_brief else format(d['chg'], '+,.0f')} ({d['chg_pct']:+.2f}%)</span>"
                f"<span style='background:{color}22;color:{color};border:1px solid {color};"
                f"border-radius:6px;padding:1px 8px;font-weight:bold;'>{SIGNAL_EMOJI[sig]} {d['score']:+.0f}</span>"
                f"{change_badge} {spark}</div>"
                f"<div style='color:#666;font-size:0.85rem;margin:5px 0;'>{metrics}</div>"
                f"<div style='display:flex;gap:16px;flex-wrap:wrap;font-size:0.82rem;'>"
                f"<ul style='margin:0;padding-left:16px;color:#2e7d32;'>{reasons}</ul>"
                f"<ul style='margin:0;padding-left:16px;color:#e65100;'>{warns}</ul></div></div>",
                unsafe_allow_html=True)
        with col2:
            if st.button("📊", key=f"brief_{d['code']}", help="상세 차트"):
                analysis_dialog(d["code"], d["name"],
                                "해외 (US)" if is_us_brief else "국내 (KRX)")

    st.caption("⚠️ 스파크라인은 최근 약 40거래일 종가, 신호 변화는 직전 브리핑일과 비교입니다. 참고용이며 투자 책임은 본인에게 있습니다.")
