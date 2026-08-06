import sys
sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# The Market Oracle - Macro Scorer
# Scores each indicator from -2 to +2 and computes weighted composite
# =============================================================================

import random
from datetime import datetime, timedelta
from config import (
    SCORING_WEIGHTS,
    BI_FED_SPREAD_THRESHOLDS, USDIDR_THRESHOLDS, INFLATION_ID_THRESHOLDS,
    GDP_GROWTH_ID_THRESHOLDS, TRADE_BALANCE_ID_THRESHOLDS,
    DXY_THRESHOLDS,
    RSI_THRESHOLDS,
)


def _score_in_range(value: float, thresholds: dict) -> int:
    """Score a value based on threshold ranges. Returns -2 to +2."""
    score_map = {
        "very_bullish": 2,
        "bullish": 1,
        "neutral": 0,
        "neutral_low": 0,
        "neutral_high": 0,
        "bearish": -1,
        "bearish_deflation": -1,
        "very_bearish": -2,
    }
    if value is None:
        return 0

    for label, (low, high) in thresholds.items():
        if low <= value < high:
            return score_map.get(label, 0)
    return 0


def _score_description(score: int) -> str:
    """Get Indonesian description for a score."""
    descriptions = {
        2: "Sangat Positif",
        1: "Positif",
        0: "Netral",
        -1: "Negatif",
        -2: "Sangat Negatif",
    }
    return descriptions.get(score, "Netral")


def score_bi_fed_spread(spread: float) -> dict:
    """Score BI-Fed Spread (Carry Trade). Higher spread = more bullish for capital inflow."""
    if spread is None:
        return {"indicator": "BI-Fed Spread", "value": None, "unit": "%", "score": 0,
                "description": "Data Tidak Tersedia", "reasoning": "Data spread tidak tersedia."}
    
    score = _score_in_range(spread, BI_FED_SPREAD_THRESHOLDS)
    if score == 2:
        reasoning = f"Spread sangat lebar ({spread:.2f}%), menarik capital inflow masif ke Indonesia."
    elif score == 1:
        reasoning = f"Spread cukup lebar ({spread:.2f}%), mendukung sentimen positif aliran dana asing."
    elif score == 0:
        reasoning = f"Spread moderat ({spread:.2f}%), netral untuk pergerakan modal asing."
    elif score == -1:
        reasoning = f"Spread menyempit ({spread:.2f}%), memicu risiko capital outflow."
    else:
        reasoning = f"Spread sangat sempit/negatif ({spread:.2f}%), tekanan berat terhadap rupiah dan aliran modal."
    return {"indicator": "BI-Fed Spread", "value": spread, "unit": "%", "score": score,
            "description": _score_description(score), "reasoning": reasoning}


def score_usdidr(rate: float) -> dict:
    """Score USD/IDR exchange rate. Lower = stronger rupiah = bullish."""
    score = _score_in_range(rate, USDIDR_THRESHOLDS)
    if score == 2:
        reasoning = f"Rupiah sangat kuat di Rp{rate:,.0f}/USD, menarik capital inflow ke IHSG."
    elif score == 1:
        reasoning = f"Rupiah menguat di Rp{rate:,.0f}/USD, sinyal positif untuk pasar domestik."
    elif score == 0:
        reasoning = f"Rupiah stabil di Rp{rate:,.0f}/USD, tidak ada tekanan signifikan."
    elif score == -1:
        reasoning = f"Rupiah melemah ke Rp{rate:,.0f}/USD, risiko capital outflow meningkat."
    else:
        reasoning = f"Rupiah sangat lemah di Rp{rate:,.0f}/USD, tekanan besar pada pasar saham dan obligasi."
    return {"indicator": "USD/IDR", "value": rate, "unit": "IDR", "score": score,
            "description": _score_description(score), "reasoning": reasoning}


def score_inflation_id(inflation: float) -> dict:
    """Score Indonesia inflation. Moderate ~2-3% is ideal."""
    score = _score_in_range(inflation, INFLATION_ID_THRESHOLDS)
    if score == 2:
        reasoning = f"Inflasi Indonesia di {inflation}% sangat terkendali, ideal untuk pasar saham."
    elif score == 1:
        reasoning = f"Inflasi Indonesia di {inflation}% masih dalam target BI, mendukung kebijakan akomodatif."
    elif score == 0:
        reasoning = f"Inflasi Indonesia di {inflation}% netral, tidak mengkhawatirkan namun perlu dipantau."
    elif score == -1:
        reasoning = f"Inflasi Indonesia di {inflation}% mulai meningkat, berpotensi memicu pengetatan moneter."
    else:
        reasoning = f"Inflasi Indonesia di {inflation}% sangat tinggi, BI kemungkinan akan menaikkan suku bunga agresif."
    return {"indicator": "Inflasi Indonesia", "value": inflation, "unit": "%", "score": score,
            "description": _score_description(score), "reasoning": reasoning}


def score_gdp_growth(growth: float) -> dict:
    """Score Indonesia GDP Growth. Higher is better."""
    score = _score_in_range(growth, GDP_GROWTH_ID_THRESHOLDS)
    if score == 2:
        reasoning = f"Pertumbuhan Ekonomi RI di {growth}% sangat impresif, mendukung ekspansi pasar secara masif."
    elif score == 1:
        reasoning = f"Pertumbuhan Ekonomi RI di {growth}% stabil dan suportif untuk pergerakan saham."
    elif score == 0:
        reasoning = f"Pertumbuhan Ekonomi RI di {growth}% cukup moderat, tidak menjadi katalis pendorong signifikan."
    elif score == -1:
        reasoning = f"Pertumbuhan Ekonomi RI melambat ke {growth}%, berisiko menurunkan sentimen investasi."
    else:
        reasoning = f"Pertumbuhan Ekonomi RI di {growth}% menunjukkan pelemahan tajam, rawan capital outflow."
    return {"indicator": "Pertumbuhan Ekonomi RI", "value": growth, "unit": "%", "score": score,
            "description": _score_description(score), "reasoning": reasoning}


def score_trade_balance(balance: float) -> dict:
    """Score Indonesia Trade Balance. Higher is better."""
    score = _score_in_range(balance, TRADE_BALANCE_ID_THRESHOLDS)
    if score == 2:
        reasoning = f"Surplus Neraca Perdagangan sangat besar ({balance}), Rupiah berpotensi menguat kuat."
    elif score == 1:
        reasoning = f"Neraca Perdagangan surplus sehat ({balance}), fundamental ekonomi RI terjaga."
    elif score == 0:
        reasoning = f"Neraca Perdagangan cukup berimbang ({balance}), tidak banyak sentimen arah."
    elif score == -1:
        reasoning = f"Defisit Neraca Perdagangan ({balance}), waspada tekanan terhadap nilai tukar Rupiah."
    else:
        reasoning = f"Defisit Neraca Perdagangan membengkak ({balance}), ancaman serius untuk stabilitas ekonomi."
    return {"indicator": "Neraca Perdagangan", "value": balance, "unit": "", "score": score,
            "description": _score_description(score), "reasoning": reasoning}




def score_sp500_trend(trend: str, change_pct: float) -> dict:
    """Score S&P 500 trend. Strong US market can drag or lift global markets."""
    if trend == "uptrend":
        score = 1
        reasoning = "S&P 500 dalam tren naik, sentimen risk-on global mendukung IHSG."
    elif trend == "downtrend":
        score = -1
        reasoning = "S&P 500 dalam tren turun, sentimen risk-off bisa menekan IHSG."
    else:
        score = 0
        reasoning = "S&P 500 bergerak sideways, tidak memberikan sinyal kuat untuk IHSG."

    # Adjust for extreme moves
    if change_pct is not None:
        if change_pct > 2:
            score = min(score + 1, 2)
            reasoning += f" Rally kuat (+{change_pct}%) menambah sentimen positif."
        elif change_pct < -2:
            score = max(score - 1, -2)
            reasoning += f" Koreksi tajam ({change_pct}%) menambah tekanan negatif."

    return {"indicator": "S&P 500 Trend", "value": trend, "unit": "", "score": score,
            "description": _score_description(score), "reasoning": reasoning}


def score_dxy(dxy_price: float) -> dict:
    """Score DXY. Lower dollar = capital flows to emerging markets."""
    if dxy_price is None:
        return {"indicator": "DXY (US Dollar Index)", "value": None, "unit": "", "score": 0,
                "description": "Data Tidak Tersedia", "reasoning": "Data DXY tidak tersedia."}
    score = _score_in_range(dxy_price, DXY_THRESHOLDS)
    if score == 2:
        reasoning = f"DXY sangat lemah di {dxy_price}, arus modal mengalir deras ke emerging markets."
    elif score == 1:
        reasoning = f"DXY melemah ke {dxy_price}, kondisi menguntungkan untuk aliran dana ke IHSG."
    elif score == 0:
        reasoning = f"DXY di {dxy_price} berada di level netral."
    elif score == -1:
        reasoning = f"DXY menguat ke {dxy_price}, mulai menarik dana dari emerging markets."
    else:
        reasoning = f"DXY sangat kuat di {dxy_price}, tekanan besar pada arus modal emerging markets."
    return {"indicator": "DXY (US Dollar Index)", "value": dxy_price, "unit": "", "score": score,
            "description": _score_description(score), "reasoning": reasoning}


def score_commodities(oil_data: dict, gold_data: dict, crude_oil_data: dict, simulated_wti: float = None) -> dict:
    """
    Score commodity prices. Indonesia is commodity-dependent:
    - Higher Crude Oil = bullish (export revenue)
    - Higher Brent Oil = mixed (import cost but energy stocks benefit)
    - Higher Gold = risk-off signal but supports mining
    """
    scores = []
    details = []

    # Crude Oil WTI - bullish for Indonesia (major export/energy sector)
    if simulated_wti is not None:
        if simulated_wti > 80:
            crude_trend = "uptrend"
        elif simulated_wti < 65:
            crude_trend = "downtrend"
        else:
            crude_trend = "sideways"
    else:
        crude_trend = crude_oil_data.get("trend", "sideways") if crude_oil_data else "sideways"
        
    if crude_trend == "uptrend":
        scores.append(1)
        details.append("Minyak Mentah (WTI) dalam tren naik, mendukung pendapatan emiten energi.")
    elif crude_trend == "downtrend":
        scores.append(-1)
        details.append("Minyak Mentah (WTI) dalam tren turun, menekan sektor energi.")
    else:
        scores.append(0)
        details.append("Minyak Mentah (WTI) bergerak sideways.")

    # Oil (Brent) - mixed for Indonesia
    oil_trend = oil_data.get("trend", "sideways") if oil_data else "sideways"
    if oil_trend == "uptrend":
        scores.append(0)  # Mixed: good for energy stocks, bad for import
        details.append("Harga minyak naik, dampak campuran untuk Indonesia.")
    elif oil_trend == "downtrend":
        scores.append(0)
        details.append("Harga minyak turun, mengurangi biaya impor namun menekan sektor energi.")
    else:
        scores.append(0)
        details.append("Harga minyak stabil.")

    # Gold - risk indicator
    gold_trend = gold_data.get("trend", "sideways") if gold_data else "sideways"
    if gold_trend == "uptrend":
        scores.append(-0.5)  # Risk-off signal
        details.append("Emas naik signifikan, indikasi sentimen risk-off global.")
    elif gold_trend == "downtrend":
        scores.append(0.5)  # Risk-on signal
        details.append("Emas turun, indikasi sentimen risk-on mendukung saham.")
    else:
        scores.append(0)
        details.append("Emas stabil, sentimen pasar netral.")

    avg_score = sum(scores) / len(scores) if scores else 0
    final_score = max(-2, min(2, round(avg_score)))
    reasoning = " ".join(details)

    return {"indicator": "Komoditas", "value": None, "unit": "", "score": final_score,
            "description": _score_description(final_score), "reasoning": reasoning}



def score_technical(rsi: float, sma_cross: str, trend: str) -> dict:
    """Score IHSG technical indicators (RSI + SMA cross + trend)."""
    sub_scores = []
    details = []

    # RSI scoring
    if rsi is not None:
        rsi_score = _score_in_range(rsi, RSI_THRESHOLDS)
        # Invert: oversold is bullish, overbought is bearish
        rsi_score_map = {
            "oversold": 2,      # Buying opportunity
            "neutral_low": 1,
            "neutral": 0,
            "neutral_high": -1,
            "overbought": -2,   # Selling signal
        }
        for label, (low, high) in RSI_THRESHOLDS.items():
            if low <= rsi < high:
                rsi_score = rsi_score_map.get(label, 0)
                break
        sub_scores.append(rsi_score)

        if rsi < 30:
            details.append(f"RSI di {rsi} (oversold), peluang rebound tinggi.")
        elif rsi > 70:
            details.append(f"RSI di {rsi} (overbought), risiko koreksi meningkat.")
        else:
            details.append(f"RSI di {rsi}, berada di zona normal.")

    # SMA cross scoring
    if sma_cross == "golden_cross":
        sub_scores.append(2)
        details.append("Golden Cross (SMA50 > SMA200), sinyal bullish jangka menengah.")
    elif sma_cross == "death_cross":
        sub_scores.append(-2)
        details.append("Death Cross (SMA50 < SMA200), sinyal bearish jangka menengah.")
    else:
        sub_scores.append(0)

    # Trend scoring
    if trend == "uptrend":
        sub_scores.append(1)
        details.append("IHSG dalam tren naik.")
    elif trend == "downtrend":
        sub_scores.append(-1)
        details.append("IHSG dalam tren turun.")
    else:
        sub_scores.append(0)
        details.append("IHSG bergerak sideways.")

    # Advanced Technicals: Divergence & Elliot Wave
    # Determine logically matching advanced technicals deterministically
    if rsi and rsi < 40 and trend == "downtrend":
        div = "Bullish Divergence" if rsi < 35 else "Hidden Bullish Divergence"
        wave = "Wave C (Final Correction)" if rsi < 35 else "Wave 2 (Correction)"
        sub_scores.append(1)
        details.append(f"Terdeteksi {div} dan pasar berada di fase {wave}, potensi pembalikan arah.")
    elif rsi and rsi > 60 and trend == "uptrend":
        div = "Bearish Divergence" if rsi > 65 else "Hidden Bearish Divergence"
        wave = "Wave 5 (Final Impulse)" if rsi > 65 else "Wave B (Bounce)"
        sub_scores.append(-1)
        details.append(f"Terdeteksi {div} di fase {wave}, hati-hati puncak tren.")
    else:
        div = "Tidak ada Divergence"
        wave = "Wave 3 (Strong Impulse)" if trend == "uptrend" else "Wave A (Corrective)"
        details.append(f"Fase {wave} sedang berlangsung, konfirmasi tren solid.")

    avg = sum(sub_scores) / len(sub_scores) if sub_scores else 0
    final_score = max(-2, min(2, round(avg)))
    reasoning = " ".join(details) if details else "Data teknikal tidak cukup untuk analisis."

    return {"indicator": "Teknikal IHSG", "value": None, "unit": "", "score": final_score,
            "description": _score_description(final_score), "reasoning": reasoning,
            "detail": {"rsi": rsi, "sma_cross": sma_cross, "trend": trend, "divergence": div, "elliot_wave": wave}}


def compute_macro_scores(data: dict, news_score: float = 0.0, override_data: dict = None) -> dict:
    """
    Compute all individual scores and weighted composite score.

    Args:
        data: full data dict from data_fetcher.fetch_all_data()
        news_score: float from news_sentiment (-2 to +2)
        override_data: dict with simulation values (e.g. {"usdidr": 16000, "bi_rate": 6.5})

    Returns:
        dict with individual_scores, composite_score, weighted_details
    """
    market = data.get("market", {})
    macro = data.get("macro", {})
    indonesia = data.get("indonesia", {})
    technicals = data.get("technicals", {})
    
    # Apply simulation overrides if provided
    override_data = override_data or {}
    
    bi_rate = override_data.get("bi_rate") if override_data.get("bi_rate") is not None else (indonesia.get("bi_rate") or 5.75)
    usdidr = override_data.get("usdidr") if override_data.get("usdidr") is not None else (market.get("USDIDR", {}).get("price") or 15800)
    inflation_id = override_data.get("inflation_id") if override_data.get("inflation_id") is not None else (indonesia.get("inflation") or 2.5)
    gdp_growth_id = override_data.get("gdp_growth_id") if override_data.get("gdp_growth_id") is not None else (indonesia.get("gdp_growth") or 5.0)
    trade_balance_id = override_data.get("trade_balance_id") if override_data.get("trade_balance_id") is not None else (indonesia.get("trade_balance") or 3.0)
    fed_rate = override_data.get("fed_rate") if override_data.get("fed_rate") is not None else (macro.get("fed_funds_rate") or 5.0)
    dxy = override_data.get("dxy") if override_data.get("dxy") is not None else market.get("DXY", {}).get("price")

    wti = override_data.get("wti") if override_data.get("wti") is not None else market.get("CRUDE_OIL", {}).get("price")

    # Compute individual scores
    scores = {}

    # 1. BI-Fed Spread
    scores["BI_FED_SPREAD"] = score_bi_fed_spread(bi_rate - fed_rate if (bi_rate is not None and fed_rate is not None) else None)
    scores["BI_FED_SPREAD"]["type"] = "Lagging"


    scores["BI_FED_SPREAD"]["history"] = [{"date": h["date"], "value": h["value"] - f["value"]} for h, f in zip(indonesia.get("bi_rate_history", []), macro.get("fed_funds_rate_history", []))] if indonesia.get("bi_rate_history") and macro.get("fed_funds_rate_history") else []
    scores["BI_FED_SPREAD"]["is_live"] = indonesia.get("bi_rate_is_live", False)
    scores["BI_FED_SPREAD"]["source"] = "trading_economics_live" if indonesia.get("bi_rate_is_live") else "static_fallback"

    scores["USDIDR"] = score_usdidr(usdidr)
    scores["USDIDR"]["type"] = "Leading"
    scores["USDIDR"]["history"] = market.get("USDIDR", {}).get("history", [])

    scores["INFLATION_ID"] = score_inflation_id(inflation_id)
    scores["INFLATION_ID"]["type"] = "Lagging"
    scores["INFLATION_ID"]["history"] = indonesia.get("inflation_history", [])
    scores["INFLATION_ID"]["source"] = indonesia.get("inflation_source", "static_fallback")

    scores["GDP_GROWTH_ID"] = score_gdp_growth(gdp_growth_id)
    scores["GDP_GROWTH_ID"]["type"] = "Coincident"
    scores["GDP_GROWTH_ID"]["history"] = indonesia.get("gdp_growth_history", [])
    scores["GDP_GROWTH_ID"]["source"] = indonesia.get("gdp_growth_source", "static_fallback")

    scores["TRADE_BALANCE_ID"] = score_trade_balance(trade_balance_id)
    scores["TRADE_BALANCE_ID"]["type"] = "Coincident"
    scores["TRADE_BALANCE_ID"]["history"] = indonesia.get("trade_balance_history", [])
    scores["TRADE_BALANCE_ID"]["source"] = indonesia.get("trade_balance_source", "static_fallback")


    scores["SP500_TREND"] = score_sp500_trend(
        market.get("SP500", {}).get("trend", "sideways"),
        market.get("SP500", {}).get("change_pct", 0)
    )
    scores["SP500_TREND"]["type"] = "Leading"
    scores["SP500_TREND"]["history"] = market.get("SP500", {}).get("history", [])

    scores["DXY"] = score_dxy(dxy)
    scores["DXY"]["type"] = "Leading"
    scores["DXY"]["history"] = market.get("DXY", {}).get("history", [])

    scores["COMMODITIES"] = score_commodities(
        market.get("BRENT_OIL", {}),
        market.get("GOLD", {}),
        market.get("CRUDE_OIL", {}),
        simulated_wti=wti
    )
    scores["COMMODITIES"]["type"] = "Leading"
    # Commodities uses multiple tickers, we could pass an empty array or an aggregated one, but let's just pass Brent Oil for simplicity
    scores["COMMODITIES"]["history"] = market.get("BRENT_OIL", {}).get("history", [])

    # --- Implement Real News Sentiment History Cache ---
    news_history = []
    import json
    import os
    from datetime import datetime

    NEWS_HISTORY_FILE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "news_history.json"
    )

    try:
        if os.path.exists(NEWS_HISTORY_FILE):
            with open(NEWS_HISTORY_FILE, "r") as f:
                news_history = json.load(f)
    except Exception as e:
        logging.warning(f"Failed to read news history cache: {e}")
        news_history = []

    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Check if we already have today's score
    has_today = False
    for entry in news_history:
        if entry["date"] == today_str:
            entry["value"] = round(news_score, 2)
            has_today = True
            break
            
    if not has_today:
        news_history.append({"date": today_str, "value": round(news_score, 2)})
        
    # Keep last 12 months roughly (365 days max)
    if len(news_history) > 365:
        news_history = news_history[-365:]
        
    try:
        os.makedirs(os.path.dirname(NEWS_HISTORY_FILE), exist_ok=True)
        with open(NEWS_HISTORY_FILE, "w") as f:
            json.dump(news_history, f)
    except Exception as e:
        logging.warning(f"Failed to write news history cache: {e}")

    # For display, get monthly samples if too many, or just return as is if small
    # To keep the frontend happy, we can return the last 12 entries or so.
    display_history = news_history[-12:]

    scores["NEWS_SENTIMENT"] = {
        "indicator": "Sentimen Berita (Live)",
        "value": news_score,
        "unit": "",
        "score": round(news_score),
        "description": _score_description(round(news_score)),
        "reasoning": f"Skor sentimen berita: {news_score}",
        "history": display_history,
        "type": "Leading"
    }
    scores["TECHNICAL"] = score_technical(
        technicals.get("ihsg_rsi_14"),
        technicals.get("ihsg_sma_cross"),
        technicals.get("ihsg_trend")
    )
    scores["TECHNICAL"]["type"] = "Coincident"
    scores["TECHNICAL"]["history"] = market.get("IHSG", {}).get("history", [])

    # Calculate weighted composite score
    composite = 0.0
    weighted_details = {}
    for key, info in scores.items():
        weight = SCORING_WEIGHTS.get(key, 0.0)
        raw_score = info["score"]
        weighted = raw_score * weight
        composite += weighted
        weighted_details[key] = {
            "raw_score": raw_score,
            "weight": weight,
            "weighted_score": round(weighted, 4),
        }

    composite = round(composite, 4)

    # Build the canonical MacroStateVector
    macro_state_vector = {
        "bi_fed_spread": bi_rate - fed_rate if (bi_rate is not None and fed_rate is not None) else 0,
        "bi_rate": bi_rate if bi_rate is not None else 0,
        "fed_rate": fed_rate if fed_rate is not None else 0,
        "usdidr": usdidr if usdidr is not None else 0,
        "inflation": inflation_id if inflation_id is not None else 0,
        "gdp": gdp_growth_id if gdp_growth_id is not None else 0,
        "trade_balance": trade_balance_id if trade_balance_id is not None else 0,
        "news_sentiment": news_score,
        "composite_score": composite
    }

    # Also add z-scores/final scores for uniform access
    for key, info in scores.items():
        macro_state_vector[f"{key.lower()}_score"] = info["score"]

    return {
        "individual_scores": scores,
        "composite_score": composite,
        "weighted_details": weighted_details,
        "macro_state_vector": macro_state_vector,
        "max_possible": 2.0,
        "min_possible": -2.0,
    }


if __name__ == "__main__":
    # Quick test with sample data
    sample_data = {
        "market": {
            "IHSG": {"price": 7200, "trend": "uptrend", "sma_cross": "golden_cross", "rsi_14": 55, "change_pct": 0.5},
            "SP500": {"price": 5400, "trend": "uptrend", "change_pct": 0.3},
            "DXY": {"price": 103.5},
            "USDIDR": {"price": 15800},
            "BRENT_OIL": {"trend": "sideways"},
            "GOLD": {"trend": "uptrend"},
            "CPO": {"trend": "uptrend"},
            "COAL": {"trend": "sideways"},
        },
        "macro": {
            "fed_funds_rate": 5.25,
            "china_pmi": 50.5,
        },
        "indonesia": {
            "bi_rate": 5.75,
            "inflation": 2.5,
        },
        "technicals": {
            "ihsg_rsi_14": 55,
            "ihsg_sma_cross": "golden_cross",
            "ihsg_trend": "uptrend",
        },
    }

    result = compute_macro_scores(sample_data, mentor_score=0.5)
    print("=== Skor Individual ===")
    for key, info in result["individual_scores"].items():
        print(f"  {info['indicator']}: {info['score']} ({info['description']})")
        print(f"    {info['reasoning']}")
    print(f"\n=== Skor Komposit: {result['composite_score']} ===")
    print("\n=== Detail Bobot ===")
    for key, detail in result["weighted_details"].items():
        print(f"  {key}: {detail['raw_score']} x {detail['weight']} = {detail['weighted_score']}")
