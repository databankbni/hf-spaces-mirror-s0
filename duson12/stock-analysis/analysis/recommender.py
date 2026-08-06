import pandas as pd
from dataclasses import dataclass
from typing import Literal


Signal = Literal["강력매수", "매수", "중립", "매도", "강력매도"]


@dataclass
class Recommendation:
    signal: Signal
    score: float          # -100 ~ +100 (양수=매수, 음수=매도)
    confidence: str       # 높음 / 보통 / 낮음
    reasons: list[str]
    warnings: list[str]


def _score_rsi(rsi: float) -> tuple[float, list[str], list[str]]:
    reasons, warnings = [], []
    if rsi < 30:
        score = 30
        reasons.append(f"RSI {rsi:.1f} — 과매도 구간 (매수 신호)")
    elif rsi < 40:
        score = 15
        reasons.append(f"RSI {rsi:.1f} — 약세 이탈 구간")
    elif rsi > 70:
        score = -30
        warnings.append(f"RSI {rsi:.1f} — 과매수 구간 (매도 주의)")
    elif rsi > 60:
        score = -10
        reasons.append(f"RSI {rsi:.1f} — 강세권")
    else:
        score = 0
        reasons.append(f"RSI {rsi:.1f} — 중립")
    return score, reasons, warnings


def _score_macd(macd: float, signal: float, hist: float, prev_hist: float) -> tuple[float, list[str], list[str]]:
    reasons, warnings = [], []
    score = 0
    if hist > 0 and prev_hist <= 0:
        score = 25
        reasons.append("MACD 골든크로스 발생 (강한 매수 신호)")
    elif hist < 0 and prev_hist >= 0:
        score = -25
        warnings.append("MACD 데드크로스 발생 (강한 매도 신호)")
    elif hist > 0:
        score = 10
        reasons.append("MACD 히스토그램 양전 (상승 모멘텀)")
    else:
        score = -10
        warnings.append("MACD 히스토그램 음전 (하락 모멘텀)")
    return score, reasons, warnings


def _score_ma(close: float, ma5: float, ma20: float, ma60: float) -> tuple[float, list[str], list[str]]:
    reasons, warnings = [], []
    score = 0
    if close > ma5 > ma20 > ma60:
        score = 20
        reasons.append("정배열 — MA5 > MA20 > MA60 (강한 상승 추세)")
    elif close < ma5 < ma20 < ma60:
        score = -20
        warnings.append("역배열 — MA5 < MA20 < MA60 (강한 하락 추세)")
    elif close > ma20:
        score = 10
        reasons.append("현재가 MA20 위 (단기 강세)")
    else:
        score = -10
        warnings.append("현재가 MA20 아래 (단기 약세)")
    return score, reasons, warnings


def _score_bollinger(bb_pct: float, close: float, bb_upper: float, bb_lower: float) -> tuple[float, list[str], list[str]]:
    reasons, warnings = [], []
    if bb_pct < 0.1:
        score = 20
        reasons.append(f"볼린저밴드 하단 근접 (현재가 {close:,.0f}, 하단 {bb_lower:,.0f}) — 반등 기대")
    elif bb_pct > 0.9:
        score = -20
        warnings.append(f"볼린저밴드 상단 근접 (현재가 {close:,.0f}, 상단 {bb_upper:,.0f}) — 조정 가능성")
    else:
        score = 0
        reasons.append(f"볼린저밴드 중간 구간 ({bb_pct*100:.0f}%)")
    return score, reasons, warnings


def _score_volume(vol_ratio: float) -> tuple[float, list[str], list[str]]:
    reasons, warnings = [], []
    if vol_ratio > 2.0:
        score = 5
        reasons.append(f"거래량 평균 대비 {vol_ratio:.1f}배 — 세력 관심 가능성")
    elif vol_ratio < 0.5:
        score = -5
        warnings.append("거래량 급감 — 관심 부족")
    else:
        score = 0
    return score, reasons, warnings


def recommend(df: pd.DataFrame) -> Recommendation:
    """지표 기반 매수/매도 추천 생성"""
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else latest

    all_reasons: list[str] = []
    all_warnings: list[str] = []
    total_score = 0.0

    # RSI
    if pd.notna(latest.get("rsi")):
        s, r, w = _score_rsi(latest["rsi"])
        total_score += s
        all_reasons += r
        all_warnings += w

    # MACD
    if pd.notna(latest.get("macd")) and pd.notna(latest.get("macd_signal")):
        s, r, w = _score_macd(latest["macd"], latest["macd_signal"], latest["macd_hist"], prev.get("macd_hist", 0))
        total_score += s
        all_reasons += r
        all_warnings += w

    # 이동평균
    if pd.notna(latest.get("ma60")):
        s, r, w = _score_ma(latest["close"], latest.get("ma5", latest["close"]), latest.get("ma20", latest["close"]), latest["ma60"])
        total_score += s
        all_reasons += r
        all_warnings += w

    # 볼린저밴드
    if pd.notna(latest.get("bb_pct")):
        s, r, w = _score_bollinger(latest["bb_pct"], latest["close"], latest["bb_upper"], latest["bb_lower"])
        total_score += s
        all_reasons += r
        all_warnings += w

    # 거래량
    if pd.notna(latest.get("vol_ratio")):
        s, r, w = _score_volume(latest["vol_ratio"])
        total_score += s
        all_reasons += r
        all_warnings += w

    # 신호 결정
    score = max(-100, min(100, total_score))
    if score >= 50:
        signal: Signal = "강력매수"
    elif score >= 20:
        signal = "매수"
    elif score <= -50:
        signal = "강력매도"
    elif score <= -20:
        signal = "매도"
    else:
        signal = "중립"

    confidence = "높음" if abs(score) >= 50 else ("보통" if abs(score) >= 20 else "낮음")

    return Recommendation(
        signal=signal,
        score=score,
        confidence=confidence,
        reasons=all_reasons,
        warnings=all_warnings,
    )
