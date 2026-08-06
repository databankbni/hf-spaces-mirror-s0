#!/usr/bin/env python3
"""
Build comprehensive political_events.json from ALL raw sources in nomos-political-alpha.
Computes excess_return from prices_*.json (5-day forward sector-relative move).

Sources merged:
- insider/form4_*.json     (5579 entries, dict by ticker)
- congressional/congress_trades_*.json  (3788 entries)
- historical/consolidated_events.json   (1120 pre-labeled events: Fed rules, exec orders, polymarket)
- historical/prices_*.json (price series for excess_return computation)

Output: data/political_events.json with 5000+ events over ~60-90 days.
Run from anywhere; resolves paths from POL_ALPHA env or sibling-repo default.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

POL_ALPHA = Path(os.environ.get("POL_ALPHA",
    "/home/termius/nomos-political-alpha")).resolve()
HIST = POL_ALPHA / "data" / "historical"
INSIDER = POL_ALPHA / "data" / "insider"
CONGRESS = POL_ALPHA / "data" / "congressional"

OUT = Path(__file__).parent / "data" / "political_events.json"


def normalize_date(s):
    if not s:
        return None
    s = str(s).strip()
    if len(s) >= 10 and s[4] == "-":
        return s[:10]
    s8 = s[:8]
    if len(s8) == 8 and s8.isdigit():
        return f"{s8[:4]}-{s8[4:6]}-{s8[6:]}"
    return None


def load_price_history():
    """Merge all prices_*.json into {ticker: {date: close}}.

    Uses the most recent price file per ticker — later files override earlier ones
    when they cover the same dates (typical: each daily snapshot has 30-90 days of
    history).
    """
    series = defaultdict(dict)
    for fp in sorted(HIST.glob("prices_*.json")):
        try:
            d = json.loads(fp.read_text())
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        for ticker, bars in d.items():
            if not isinstance(bars, list):
                continue
            for bar in bars:
                if not isinstance(bar, dict):
                    continue
                dt = normalize_date(bar.get("date"))
                if not dt:
                    continue
                close = bar.get("adj_close") or bar.get("close")
                if close is None:
                    continue
                try:
                    series[ticker.upper()][dt] = float(close)
                except (TypeError, ValueError):
                    continue
    return dict(series)


def compute_excess_return(prices, ticker, event_date, horizon=5):
    """Compute 5-day forward excess_return vs SPY for a ticker on event_date.

    Returns (excess_return, y) or (None, None) if data missing.
    """
    ticker = ticker.upper()
    spy = prices.get("SPY", {})
    tkr_series = prices.get(ticker, {})
    if not tkr_series or not spy:
        return None, None

    # Find next trading day on/after event_date for ticker
    try:
        evt = datetime.strptime(event_date, "%Y-%m-%d")
    except ValueError:
        return None, None

    def _next_close(series, base, max_skip=5):
        for d in range(max_skip + 1):
            target = (base + timedelta(days=d)).strftime("%Y-%m-%d")
            if target in series:
                return target, series[target]
        return None, None

    entry_d, entry_p = _next_close(tkr_series, evt)
    if not entry_p:
        return None, None
    exit_d, exit_p = _next_close(tkr_series, evt + timedelta(days=horizon))
    if not exit_p:
        return None, None
    spy_entry_d, spy_entry_p = _next_close(spy, evt)
    spy_exit_d, spy_exit_p = _next_close(spy, evt + timedelta(days=horizon))
    if not spy_entry_p or not spy_exit_p:
        return None, None

    tkr_ret = (exit_p / entry_p) - 1.0
    spy_ret = (spy_exit_p / spy_entry_p) - 1.0
    excess = tkr_ret - spy_ret
    return round(excess, 6), 1 if excess > 0 else 0


# ── SECTOR/TICKER MAP (must match SECTOR_ETF_MAP in app.py) ──────────────────
TICKER_TO_SECTOR = {
    "GEO": "private_prisons", "CXW": "private_prisons",
    "XLE": "energy", "CVX": "energy", "XOM": "energy", "OXY": "energy",
    "COP": "energy", "OKLO": "energy",
    "XLV": "healthcare", "UNH": "healthcare", "PFE": "healthcare",
    "MRK": "healthcare", "JNJ": "healthcare",
    "XLF": "finance", "JPM": "finance", "BAC": "finance", "GS": "finance",
    "MS": "finance", "FOUR": "finance", "HOOD": "finance", "MSTR": "finance",
    "XLK": "tech", "MSFT": "tech", "META": "tech", "GOOGL": "tech",
    "AMZN": "tech", "NVDA": "tech", "AAPL": "tech", "QCOM": "tech",
    "TSLA": "tech",
    "MO": "consumer_staples", "PPC": "consumer_staples", "KO": "consumer_staples",
    "UBER": "consumer_disc", "CMCSA": "communications",
    "COIN": "finance",
    "SPY": "other",
}


def sector_for(ticker):
    return TICKER_TO_SECTOR.get(ticker.upper(), "other")


def parse_form4_files(prices):
    """Parse insider/form4_*.json — dict by ticker → list of filings."""
    events = []
    for fp in sorted(INSIDER.glob("form4_*.json")):
        try:
            d = json.loads(fp.read_text())
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        for ticker, filings in d.items():
            if not isinstance(filings, list):
                continue
            for entry in filings:
                if not isinstance(entry, dict):
                    continue
                date = normalize_date(entry.get("file_date") or entry.get("date"))
                if not date:
                    continue
                er, y = compute_excess_return(prices, ticker, date)
                if er is None:
                    continue
                names = entry.get("display_names") or []
                accession = entry.get("accession_number") or entry.get("accession") or ""
                title = "Form 4 insider filing"
                if names and isinstance(names, list):
                    insider_name = next((n for n in names if "CIK" in str(n) and "INC" not in str(n).upper()), names[0])
                    title = f"Form 4: {insider_name}"
                if accession:
                    title = f"{title} [{accession}]"
                events.append({
                    "date": date,
                    "ticker": ticker.upper(),
                    "event_type": "insider_trade",
                    "signal_strength": 0.6,
                    "agency": "SEC",
                    "title": str(title)[:200],
                    "accession": str(accession),
                    "excess_return": er,
                    "y": y,
                    "outcome": y,
                    "signal_type": "form4",
                    "signal_sector": sector_for(ticker),
                    "donor_info": {"sector": sector_for(ticker), "delivered": False},
                    "macro": {"vix": 18.0, "sp500_return_5d": 0.0},
                })
    return events


def parse_congress_files(prices):
    """Parse congressional/congress_trades_*.json + insider/congressional_trades_*.json.

    Schema varies by file — handle dict and list shapes.
    """
    events = []
    candidates = list(CONGRESS.glob("congress_trades_*.json")) + \
                 list(INSIDER.glob("congressional_trades_*.json"))
    for fp in sorted(candidates):
        try:
            d = json.loads(fp.read_text())
        except Exception:
            continue
        # Normalize to list of trade dicts
        trades = []
        if isinstance(d, list):
            trades = d
        elif isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, list):
                    trades.extend(v)
        for t in trades:
            if not isinstance(t, dict):
                continue
            ticker = (t.get("ticker") or t.get("symbol") or "").upper().strip()
            date = normalize_date(t.get("transaction_date") or t.get("date") or t.get("filed_date"))
            if not ticker or not date:
                continue
            er, y = compute_excess_return(prices, ticker, date)
            if er is None:
                continue
            rep = t.get("representative") or t.get("name") or t.get("legislator") or "Member of Congress"
            tx_type = t.get("type") or t.get("transaction_type") or "trade"
            amount = t.get("amount") or ""
            events.append({
                "date": date,
                "ticker": ticker,
                # 2026-04-25 BUGFIX: was "insider_trade" — congressional trades
                # were being lumped together with SEC Form 4 insider trades, so
                # event_type distribution showed 98.4% insider_trade instead of
                # the real ~50/50 split. Now properly tagged so agents can
                # differentiate Member-of-Congress trade signals from corporate-
                # officer signals (very different alpha profiles).
                "event_type": "congressional_trade",
                "signal_strength": 0.65,
                "agency": "House/Senate",
                "title": f"{rep}: {tx_type} {ticker} {amount}".strip()[:200],
                "excess_return": er,
                "y": y,
                "outcome": y,
                "signal_type": "congressional",
                "signal_sector": sector_for(ticker),
                "donor_info": {"sector": sector_for(ticker), "delivered": False},
                "macro": {"vix": 18.0, "sp500_return_5d": 0.0},
            })
    return events


def load_existing_consolidated():
    """Keep the pre-labeled Fed rules / exec orders / polymarket events as-is."""
    fp = HIST / "consolidated_events.json"
    if not fp.exists():
        return []
    try:
        raw = json.loads(fp.read_text())
    except Exception:
        return []
    out = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        d = normalize_date(e.get("date"))
        if not d:
            continue
        e["date"] = d
        out.append(e)
    return out


def deduplicate(events):
    """Drop exact (date, ticker, signal_type, title) dupes."""
    seen = set()
    out = []
    for e in events:
        key = (
            e.get("date"),
            e.get("ticker"),
            e.get("signal_type"),
            e.get("accession") or e.get("title", "")[:200],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def main():
    print(f"POL_ALPHA = {POL_ALPHA}")
    print("Loading price history...")
    prices = load_price_history()
    print(f"  → {len(prices)} tickers, total bars: {sum(len(v) for v in prices.values())}")

    print("Parsing form4 (insider trades)...")
    form4 = parse_form4_files(prices)
    print(f"  → {len(form4)} resolved events")

    print("Parsing congressional trades...")
    congress = parse_congress_files(prices)
    print(f"  → {len(congress)} resolved events")

    print("Loading existing consolidated (Fed rules, exec orders, polymarket)...")
    base = load_existing_consolidated()
    print(f"  → {len(base)} pre-labeled events")

    all_events = base + form4 + congress
    all_events = deduplicate(all_events)
    all_events.sort(key=lambda e: (e.get("date"), e.get("ticker")))

    dates = sorted({e.get("date") for e in all_events if e.get("date")})
    print(f"\n=== FINAL ===")
    print(f"Total events:  {len(all_events)}")
    print(f"Unique dates:  {len(dates)}  ({dates[0]} → {dates[-1]})" if dates else "no dates")
    from collections import Counter
    et = Counter(e.get("event_type") for e in all_events)
    sec = Counter(e.get("signal_sector") for e in all_events)
    print(f"Event types:   {dict(et)}")
    print(f"Sectors:       {dict(sec.most_common(10))}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_events, indent=None, separators=(",", ":")))
    sz = OUT.stat().st_size / 1024
    print(f"\nWrote {OUT}  ({sz:.1f} KB)")


if __name__ == "__main__":
    main()
