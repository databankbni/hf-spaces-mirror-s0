import sys
sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# The Market Oracle - Oracle Engine
# Combines all analysis pillars into a final verdict
# =============================================================================

import os
import json
from datetime import datetime
from data_fetcher import fetch_all_data
from macro_scorer import compute_macro_scores
from news_sentiment import analyze_news_sentiment
from mentor_analyzer import analyze_mentors_original, get_mentor_file_age_days
from legends_engine import run_all_legends
from sectors import calculate_sectors_and_picks
from market_cycle import analyze_market_cycle
from macro_calendar import get_macro_calendar
from pattern_matcher import match_historical_pattern
from config import VERDICT_THRESHOLDS, VERDICT_LABELS


# =============================================================================
# Statistical honesty layer
# -----------------------------------------------------------------------------
# oracle.py generates user-facing narrative/action-plan text. That text used
# to carry the same confident tone (STRONG_BULLISH, "meyakinkan", "mengonfirmasi
# ketepatan") no matter how weak the actual out-of-sample evidence was.
# backtest_engine.py already computes proper significance tests (R2_OOS,
# Clark-West, Pesaran-Timmermann) for the underlying signal -- this layer reads
# that cached result (read-only, never triggers a re-fetch) and uses it to pick
# a "statistical tier" that downstream text/position-sizing must respect.
# If no backtest result is available, oracle.py must NOT assume validation --
# it defaults to the most conservative tier ("unvalidated").
# =============================================================================

_BACKTEST_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "backtest_cache.json"
)

STAT_TIER_PHRASES = {
    # Both PT (directional accuracy) and Clark-West (MSPE superiority) are
    # significant at 5% out-of-sample.
    "confirmed": {
        "prob": "tingginya probabilitas (signal ini lolos uji signifikansi statistik out-of-sample)",
        "confirm": "secara meyakinkan",
        "align_confirm": "mengonfirmasi validitas statistik dari",
    },
    # Only one of the two tests is significant.
    "partial": {
        "prob": "kecenderungan arah yang cukup didukung data (signifikansi statistik out-of-sample masih parsial)",
        "confirm": "dengan indikasi yang cukup konsisten",
        "align_confirm": "sejalan secara arah dengan, meski belum sepenuhnya mengonfirmasi secara statistik,",
    },
    # Backtest exists but neither test clears 5% significance.
    "unconfirmed": {
        "prob": "kecenderungan arah historis (BELUM terbukti signifikan secara statistik pada uji out-of-sample)",
        "confirm": "namun perlu dicatat bahwa validasi statistiknya masih lemah, dan",
        "align_confirm": "belum didukung signifikansi statistik yang teruji untuk",
    },
    # No cached backtest result at all.
    "unvalidated": {
        "prob": "estimasi arah awal (belum ada hasil backtest yang tersedia untuk memvalidasi sinyal saat ini)",
        "confirm": "sebagai estimasi yang belum divalidasi backtest, dan",
        "align_confirm": "belum divalidasi lewat pengujian statistik out-of-sample untuk",
    },
}

# Multiplier applied to the composite confidence score, and a hard cap on the
# stock-allocation aggressiveness of the action plan, per tier. Weak/absent
# statistical validation should never produce a "FULL BUY 100%" recommendation
# no matter how bullish the raw macro composite looks.
STAT_TIER_CONFIDENCE_FACTOR = {
    "confirmed": 1.0,
    "partial": 0.85,
    "unconfirmed": 0.65,
    "unvalidated": 0.75,  # neutral-conservative: no evidence either way
}
STAT_TIER_MAX_STOCK_ALLOCATION_PCT = {
    "confirmed": 100,
    "partial": 85,
    "unconfirmed": 60,
    "unvalidated": 70,
}


def _load_backtest_confidence() -> dict:
    """Baca cache hasil backtest_engine.py (read-only -- tidak pernah memicu
    re-fetch data atau re-run backtest dari sini). Mengembalikan tier statistik
    yang dipakai untuk menyelaraskan bahasa/aksi di seluruh oracle.py dengan
    kekuatan bukti yang benar-benar teruji, bukan sekadar skor makro mentah.
    
    PRIORITAS: Gunakan 'live_model_oos_test' (model discrete scoring yang sama
    dengan production) jika tersedia. Jika hanya ada 'oos_test' (Phase Angle
    z-score model), downgrade tier satu tingkat karena itu proxy, bukan model
    yang benar-benar dipakai."""
    _TIER_DOWNGRADE = {
        "confirmed": "partial",
        "partial": "unconfirmed",
        "unconfirmed": "unconfirmed",
        "unvalidated": "unvalidated",
    }
    try:
        if not os.path.exists(_BACKTEST_CACHE_FILE):
            return {"tier": "unvalidated", "cw_p_value": None, "r2_oos_pct": None,
                     "pt_significant": None, "n_oos": None,
                     "backtest_model_alignment": "none"}
        with open(_BACKTEST_CACHE_FILE, "r") as f:
            data = json.load(f)

        # --- Try live discrete model first (aligned with production) ---
        live_test = data.get("live_model_oos_test") or {}
        if live_test and "error" not in live_test:
            cw_sig = bool(live_test.get("cw_significant_at_005", False))
            pt_test = live_test.get("pt_test") or {}
            pt_sig = bool(pt_test.get("significant_at_005", False))

            if cw_sig and pt_sig:
                tier = "confirmed"
            elif cw_sig or pt_sig:
                tier = "partial"
            else:
                tier = "unconfirmed"

            return {
                "tier": tier,
                "cw_p_value": live_test.get("cw_p_value"),
                "r2_oos_pct": live_test.get("r2_oos_pct"),
                "pt_significant": pt_sig,
                "n_oos": live_test.get("n_total"),
                "backtest_model_alignment": "aligned",
                "sensitivity_model": data.get("sensitivity_model", {})
            }

        # --- Fallback: Phase Angle model (PROXY — downgrade tier) ---
        oos_test = data.get("oos_test", {}) or {}
        sample_adequacy = data.get("sample_adequacy", {}) or {}
        pt_test = oos_test.get("pt_test") or {}

        cw_sig = bool(oos_test.get("cw_significant_at_005", False))
        pt_sig = bool(pt_test.get("significant_at_005", False))

        if cw_sig and pt_sig:
            tier = "confirmed"
        elif cw_sig or pt_sig:
            tier = "partial"
        else:
            tier = "unconfirmed"

        # Downgrade karena ini bukan model yang dipakai di production
        tier = _TIER_DOWNGRADE.get(tier, tier)

        return {
            "tier": tier,
            "cw_p_value": oos_test.get("cw_p_value"),
            "r2_oos_pct": oos_test.get("r2_oos_pct"),
            "pt_significant": pt_sig,
            "n_oos": sample_adequacy.get("n_oos_months"),
            "backtest_model_alignment": "proxy_penalty",
            "sensitivity_model": data.get("sensitivity_model", {})
        }
    except Exception as e:
        print(f"[Warning] Failed to load backtest stats: {e}")
        return {"tier": "unvalidated", "cw_p_value": None, "r2_oos_pct": None,
                 "pt_significant": None, "n_oos": None,
                 "backtest_model_alignment": "none"}


def _determine_verdict(composite_score: float) -> dict:
    """Determine the final verdict based on composite score."""
    if composite_score >= VERDICT_THRESHOLDS["STRONG_BULLISH"]:
        key = "STRONG_BULLISH"
    elif composite_score >= VERDICT_THRESHOLDS["BULLISH"]:
        key = "BULLISH"
    elif composite_score >= VERDICT_THRESHOLDS["NEUTRAL_LOW"]:
        key = "NEUTRAL"
    elif composite_score >= VERDICT_THRESHOLDS["BEARISH"]:
        key = "BEARISH"
    else:
        key = "STRONG_BEARISH"

    return {
        "key": key,
        "label": VERDICT_LABELS[key],
        "composite_score": composite_score,
    }


def _generate_summary(verdict_key: str, composite_score: float,
                      legends: list, macro_scores: dict,
                      stat_conf: dict = None) -> str:
    """Generate a comprehensive Indonesian summary of the analysis.

    stat_conf datang dari _load_backtest_confidence(): dipakai untuk memilih
    kekuatan bahasa (prob/confirm/align_confirm) yang proporsional dengan
    signifikansi statistik out-of-sample yang benar-benar teruji di
    backtest_engine.py, bukan bahasa superlatif yang sama terlepas dari bukti."""
    if stat_conf is None:
        stat_conf = _load_backtest_confidence()
    tier = stat_conf.get("tier", "unvalidated")
    ph = STAT_TIER_PHRASES[tier]

    # Find strongest individual signal
    individual = macro_scores.get("individual_scores", {})
    strongest_positive = None
    strongest_negative = None
    for key, info in individual.items():
        score = info["score"]
        if strongest_positive is None or score > strongest_positive["score"]:
            strongest_positive = {"key": key, "score": score, "indicator": info["indicator"]}
        if strongest_negative is None or score < strongest_negative["score"]:
            strongest_negative = {"key": key, "score": score, "indicator": info["indicator"]}

    summary_parts = []

    # Paragraph 1: Executive Summary -- strength of language now scales with
    # `ph["prob"]` / `ph["confirm"]`, which come from the statistical tier.
    if verdict_key == "STRONG_BULLISH":
        summary_parts.append(
            f"Berdasarkan hasil komputasi sistem The Market Oracle, IHSG saat ini berada dalam fase SANGAT BULLISH dengan skor komposit mencapai {composite_score:.2f} dari skala 2.00. Konvergensi indikator makroekonomi, teknikal, dan sentimen {ph['confirm']} menunjukkan momentum ekspansif yang kuat, mengisyaratkan {ph['prob']} untuk apresiasi harga saham secara luas dalam waktu dekat."
        )
    elif verdict_key == "BULLISH":
        summary_parts.append(
            f"Berdasarkan pemodelan kuantitatif The Market Oracle, pergerakan IHSG berada di teritori BULLISH dengan skor komposit {composite_score:.2f} dari skala 2.00. Meskipun tidak berada pada fase akselerasi puncak, mayoritas indikator leading dan coincident membentuk divergensi positif {ph['confirm']} mendukung bias kenaikan pasar (uptrend) secara agregat -- ini {ph['prob']}."
        )
    elif verdict_key == "NEUTRAL":
        summary_parts.append(
            f"The Market Oracle mengkalkulasi arah pasar saat ini berada pada kondisi NETRAL (Konsolidasi) dengan skor komposit marjinal {composite_score:.2f} dari skala 2.00. Telah terjadi tarik-menarik kekuatan yang seimbang antara katalis makro yang menekan pasar dengan valuasi/teknikal yang menopang harga, menciptakan kondisi ekuilibrium sementara (wait-and-see)."
        )
    elif verdict_key == "BEARISH":
        summary_parts.append(
            f"Analisis kuantitatif The Market Oracle mendeteksi terbentuknya sinyal BEARISH, terefleksi dari skor komposit sebesar {composite_score:.2f}/2.00 -- {ph['prob']}. Tekanan makroekonomi dan sentimen yang memburuk mulai membebani valuasi IHSG secara agregat, sehingga risiko koreksi atau downtrend jangka pendek hingga menengah kini lebih mendominasi profil risiko-imbal hasil pasar."
        )
    else:
        summary_parts.append(
            f"Peringatan: The Market Oracle menangkap sinyal SANGAT BEARISH dengan skor komposit yang anjlok ke level {composite_score:.2f} dari batas bawah -2.00. Kerusakan pada indikator makro utama, dikombinasikan dengan sentimen kepanikan pasar (risk-off) dan patahnya level support teknikal, mengindikasikan {ph['prob']} untuk pelemahan lanjutan IHSG."
        )

    # Paragraph 2: Macro Drivers
    macro_text = "Dari perspektif penggerak utama (drivers), "
    if strongest_positive and strongest_negative:
        macro_text += (
            f"kekuatan terbesar yang menopang pasar saat ini bersumber dari {strongest_positive['indicator']} (Skor Aksi: +{strongest_positive['score']}). "
            f"Namun demikian, bobot tersebut mendapatkan perlawanan/tekanan paling berat dari pemburukan pada metrik {strongest_negative['indicator']} (Skor Deviasi: {strongest_negative['score']}). "
            f"Dinamika polarisasi dari komponen-komponen makro inilah yang mendikte volatilitas arah IHSG saat ini."
        )
    elif strongest_positive:
        macro_text += f"penguatan {strongest_positive['indicator']} (Skor: +{strongest_positive['score']}) menjadi tulang punggung utama sentimen positif pasar."
    elif strongest_negative:
        macro_text += f"pelemahan pada {strongest_negative['indicator']} (Skor: {strongest_negative['score']}) memberikan efek destruktif paling masif terhadap likuiditas pasar."
    summary_parts.append(macro_text)

    # Paragraph 3: Legends Reframing
    legends_verdicts = [l["verdict"] for l in legends]
    bullish_legends = legends_verdicts.count("bullish")
    bearish_legends = legends_verdicts.count("bearish")
    neutral_legends = legends_verdicts.count("neutral")
    
    summary_parts.append(
        f"Sebagai layer reframing (sudut pandang gaya investasi berbeda), "
        f"mesin telah mensintesis matriks pendapat dari {len(legends)} legenda investasi global. "
        f"Terpantau {bullish_legends} model legenda berposisi bullish, {neutral_legends} mengambil sikap netral, "
        f"dan {bearish_legends} berpihak pada skenario bearish. "
        f"Penyelarasan antara data fundamental dengan bias psikologis kuantitatif dari para legenda ini "
        f"belum didukung signifikansi statistik yang teruji untuk Trading Action Plan yang direkomendasikan di bawah."
    )

    # Paragraph 4: Explicit statistical validation status -- always shown,
    # regardless of tier, so the reader sees the actual evidence quality
    # rather than inferring it from adjectives alone.
    n_oos = stat_conf.get("n_oos")
    cw_p = stat_conf.get("cw_p_value")
    r2_oos = stat_conf.get("r2_oos_pct")
    if tier == "unvalidated":
        stat_note = (
            "Catatan Validasi Statistik: belum ada hasil backtest out-of-sample yang tersedia untuk sinyal ini. "
            "Verdict di atas murni cerminan skor makro/teknikal/sentimen saat ini -- BUKAN klaim yang sudah teruji "
            "secara statistik terhadap data historis."
        )
    else:
        stat_note = (
            f"Catatan Validasi Statistik: berdasarkan backtest out-of-sample ({n_oos if n_oos is not None else '?'} observasi bulanan sejak periode holdout), "
            f"Clark-West p-value = {cw_p if cw_p is not None else 'n/a'}, R2_OOS = {r2_oos if r2_oos is not None else 'n/a'}%. "
            f"Status validasi saat ini: {tier.upper()}. "
            + ("Kedua uji signifikansi (Clark-West & Pesaran-Timmermann) lolos ambang 5%." if tier == "confirmed"
               else "Hanya sebagian uji signifikansi yang lolos ambang 5% -- perlakukan sinyal ini dengan hati-hati ekstra." if tier == "partial"
               else "Belum ada uji signifikansi yang lolos ambang 5% -- secara historis sinyal ini belum terbukti mengalahkan baseline (rata-rata historis) secara statistik.")
        )
    summary_parts.append(stat_note)

    return "\n\n".join(summary_parts)


def _calculate_confidence_level(legends: list, macro_scores: dict,
                                 stat_conf: dict = None) -> dict:
    """Calculate overall confidence level based on legend agreement, signal
    strength, AND the statistical tier from backtest_engine.py.

    Legend agreement and raw signal strength describe how strong the
    *current* reading looks; they say nothing about whether that reading has
    historically predicted anything. The stat_conf factor scales the final
    score down when out-of-sample significance is weak/absent, so "Tinggi"
    confidence can't be reached purely from legends agreeing with each other
    while the signal itself has no proven predictive power."""
    if stat_conf is None:
        stat_conf = _load_backtest_confidence()
    tier = stat_conf.get("tier", "unvalidated")
    stat_factor = STAT_TIER_CONFIDENCE_FACTOR[tier]

    # Legend agreement
    verdicts = [l["verdict"] for l in legends]
    bullish_count = verdicts.count("bullish")
    bearish_count = verdicts.count("bearish")
    total = len(verdicts)

    max_agreement = max(bullish_count, bearish_count)
    agreement_ratio = max_agreement / total if total > 0 else 0

    # Average legend confidence
    avg_legend_confidence = sum(l["confidence"] for l in legends) / len(legends) if legends else 0.5

    # Raw confidence from legend agreement + legend self-confidence
    # Legend opinions are highly correlated as they use the same underlying macro/valuation data.
    # We drop the agreement ratio weight to 0.3 (from 0.6) to avoid overstating confidence.
    raw_overall = (agreement_ratio * 0.3 + avg_legend_confidence * 0.7)
    raw_overall = min(1.0, max(0.0, raw_overall))

    # Statistically-adjusted confidence -- this is the number that should be
    # shown/used downstream, since it reflects proven predictive power.
    overall = round(raw_overall * stat_factor, 4)
    overall = min(1.0, max(0.0, overall))

    if overall >= 0.75:
        label = "Tinggi"
    elif overall >= 0.5:
        label = "Sedang"
    elif overall >= 0.3:
        label = "Rendah"
    else:
        label = "Sangat Rendah (belum divalidasi statistik)"

    return {
        "score": round(overall, 2),
        "raw_score_before_statistical_adjustment": round(raw_overall, 2),
        "label": label,
        "legend_agreement": f"{max_agreement}/{total} legenda setuju",
        "avg_legend_confidence": round(avg_legend_confidence, 2),
        "statistical_tier": tier,
        "statistical_adjustment_factor": stat_factor,
        "statistical_note": (
            "Skor confidence sudah diskalakan turun sesuai kekuatan validasi "
            "out-of-sample dari backtest_engine.py (Clark-West & Pesaran-Timmermann). "
            "raw_score_before_statistical_adjustment adalah skor sebelum penyesuaian ini. "
            "Bobot komposit ini adalah pilihan tetap dari iterasi desain sebelumnya; p-value di atas belum dikoreksi untuk kemungkinan model-selection bias."
        ),
    }


def _cap_allocation_range(action: str, max_pct: int) -> str:
    """Clamp the human-readable 'Saham X%-Y%' range in an action-plan label to
    a hard ceiling, so weak statistical validation can never surface as a
    100% (or near-100%) stock allocation recommendation."""
    import re
    match = re.search(r"Saham\s+(\d+)%-(\d+)%", action)
    if not match:
        return action
    lo, hi = int(match.group(1)), int(match.group(2))
    if hi <= max_pct:
        return action
    width = hi - lo
    new_hi = max_pct
    new_lo = max(0, new_hi - width)
    new_cash_lo = 100 - new_hi
    new_cash_hi = 100 - new_lo
    return re.sub(
        r"Saham\s+\d+%-\d+%,\s*Cash\s+\d+%-\d+%",
        f"Saham {new_lo}%-{new_hi}%, Cash {new_cash_lo}%-{new_cash_hi}%",
        action,
    )


def _generate_action_plan(composite_score: float, technical_trend: str,
                           stat_conf: dict = None) -> dict:
    """Generate actionable trading plan based on composite score and technicals.

    The stock-allocation ceiling is capped by the statistical tier from
    backtest_engine.py (STAT_TIER_MAX_STOCK_ALLOCATION_PCT): a bullish macro
    composite alone should not translate into a 100% stock allocation
    recommendation unless that signal has actually cleared out-of-sample
    significance tests."""
    if stat_conf is None:
        stat_conf = _load_backtest_confidence()
    tier = stat_conf.get("tier", "unvalidated")
    max_pct = STAT_TIER_MAX_STOCK_ALLOCATION_PCT[tier]
    caveat = (
        "" if tier == "confirmed" else
        f" [Alokasi saham dibatasi maks. {max_pct}% karena status validasi statistik sinyal ini masih '{tier}' -- lihat catatan validasi statistik di summary.]"
    )

    if composite_score >= 1.0:
        if technical_trend == "uptrend":
            plan = {
                "action": "FULL BUY (Saham 80%-100%, Cash 0%-20%)",
                "rationale": "Kondisi makro sangat mendukung dan teknikal IHSG terkonfirmasi uptrend. Momentum ini ideal untuk alokasi dana besar ke saham-saham berfundamental kuat. Sisakan sedikit cash untuk peluru cadangan." + caveat,
                "timeframe": "1-3 Bulan ke depan"
            }
        else:
            plan = {
                "action": "CICIL BELI (Saham 50%-70%, Cash 30%-50%)",
                "rationale": "Meskipun data makro sangat positif, teknikal IHSG masih tertahan. Disarankan untuk mulai mengakumulasi saham (Cicil Beli / DCA) memanfaatkan harga diskon. Siapkan cash untuk menangkap pantulan bawah." + caveat,
                "timeframe": "1-2 Minggu ke depan"
            }
    elif composite_score >= 0.2:
        plan = {
            "action": "CICIL BELI (Saham 30%-50%, Cash 50%-70%)",
            "rationale": "Kondisi pasar cukup positif namun belum sepenuhnya solid. Strategi Dollar Cost Averaging (DCA) bertahap adalah pilihan terbaik. Jaga level cash lebih dominan untuk meminimalisir risiko fluktuasi." + caveat,
            "timeframe": "Beberapa hari ke depan"
        }
    elif composite_score >= -0.5:
        plan = {
            "action": "WAIT & SEE (Saham 20%, Cash 80%)",
            "rationale": "Indikator makro dan sentimen saling tarik menarik (Netral). Sangat disarankan untuk menahan cash sebagai amunisi dan tidak gegabah masuk pasar, kecuali untuk trading kilat porsi kecil." + caveat,
            "timeframe": "Pantau 1-2 Minggu"
        }
    elif composite_score >= -1.2:
        plan = {
            "action": "KURANGI PORSI (Saham 10%-20%, Cash 80%-90%)",
            "rationale": "Tekanan makro mulai terasa signifikan. Lakukan Sell on Strength: kurangi porsi saham Anda saat terjadi pantulan harga sementara (rebound) untuk memperbesar porsi cash." + caveat,
            "timeframe": "Dalam minggu ini"
        }
    else:
        plan = {
            "action": "DEFENSIF (Saham 0%, Cash 100%)",
            "rationale": "Kondisi makro sangat tidak menguntungkan dengan risiko penurunan lanjutan yang besar. Lindungi portofolio dengan beralih ke Cash atau aset lindung nilai (Emas/Obligasi). Tunggu pasar stabil untuk mulai akumulasi." + caveat,
            "timeframe": "Hingga badai makro mereda"
        }

    plan["action"] = _cap_allocation_range(plan["action"], max_pct)
    plan["statistical_tier"] = tier
    return plan

def get_verdict() -> dict:
    """
    Main Oracle function: combines all pillars and returns complete analysis.

    Returns a comprehensive analysis object with:
    - verdict (final bullish/bearish call)
    - macro_scores (individual + composite)
    - legends (analysis from each legend)
    - mentor_sentiment
    - market_data (raw data snapshot)
    - summary (Indonesian text summary)
    - confidence
    - timestamp
    """
    print("[Oracle] Memulai analisis komprehensif The Market Oracle...")
    analysis_start = datetime.now()

    # -------------------------------------------------------------------------
    # PILLAR 1: Fetch all market/macro data
    # -------------------------------------------------------------------------
    print("[Oracle] Pilar 1: Mengambil data pasar dan makro ekonomi...")
    raw_data = fetch_all_data()

    # -------------------------------------------------------------------------
    # PILLAR 2: Get news sentiment
    # -------------------------------------------------------------------------
    print("[Oracle] Pilar 2: Menganalisis sentimen berita...")
    news_sentiment = analyze_news_sentiment(raw_data)
    raw_data["news_sentiment"] = news_sentiment

    # -------------------------------------------------------------------------
    # PILLAR 3: Score macro indicators
    # -------------------------------------------------------------------------
    print("[Oracle] Pilar 3: Menghitung skor makro ekonomi...")
    macro_scores = compute_macro_scores(raw_data, news_score=news_sentiment["score"])

    # -------------------------------------------------------------------------
    # PILLAR 4: Run legends analysis
    # -------------------------------------------------------------------------
    print("[Oracle] Pilar 4: Menjalankan analisis legenda investasi...")
    legends = run_all_legends(raw_data)

    # -------------------------------------------------------------------------
    # PILLAR 5: Sector Rotation & Top Picks (New Brain)
    # -------------------------------------------------------------------------
    print("[Oracle] Pilar 5: Menghitung rotasi sektoral dan stock picks...")
    sector_data = calculate_sectors_and_picks(macro_scores)

    # -------------------------------------------------------------------------
    # PILLAR 6: Mentors Analysis (Original Text + Oracle Dynamic Conclusion)
    # -------------------------------------------------------------------------
    print("[Oracle] Pilar 6: Membaca tesis mentor original...")
    mentors_analysis = analyze_mentors_original(macro_scores["composite_score"], raw_data)
    mentor_file_age = get_mentor_file_age_days()
    if mentor_file_age > 7:
        if "warnings" not in raw_data:
            raw_data["warnings"] = []
        raw_data["warnings"].append(f"File sentimen mentor sudah berusia >7 hari ({mentor_file_age} hari). Pertimbangkan untuk mengupdate manual.")

    # -------------------------------------------------------------------------
    # PILLAR 7: Calculate final composite and verdict
    # -------------------------------------------------------------------------
    print("[Oracle] Pilar 8: Menganalisis siklus, katalis, & pola historis...")
    slope = _load_backtest_confidence().get("sensitivity_model", {}).get("slope", 0.075)
    market_cycle_data = analyze_market_cycle(raw_data, macro_scores['composite_score'], sensitivity_slope=slope)
    foreign_flow_data = None # Dinonaktifkan sesuai permintaan pengguna
    macro_calendar_data = get_macro_calendar()
    pattern_data = match_historical_pattern(raw_data, macro_scores['composite_score'])

    print("[Oracle] Pilar 9: Menentukan verdict akhir...")
    composite_score = macro_scores["composite_score"]

    # Adjust composite slightly based on legend consensus
    legend_verdicts = [l["verdict"] for l in legends]
    legend_bullish = legend_verdicts.count("bullish")
    legend_bearish = legend_verdicts.count("bearish")

    # Legend consensus is kept separate from the quantitative composite score to ensure 100% data-driven verdicts.
    legend_consensus_score = 0.0
    if legend_bullish >= 4:
        legend_consensus_score = 0.04
    elif legend_bullish >= 3:
        legend_consensus_score = 0.02
    elif legend_bearish >= 4:
        legend_consensus_score = -0.04
    elif legend_bearish >= 3:
        legend_consensus_score = -0.02

    final_composite = round(composite_score, 4) # No longer injecting opinions
    final_composite = max(-2.0, min(2.0, final_composite))

    verdict = _determine_verdict(final_composite)

    # -------------------------------------------------------------------------
    # Generate summary and confidence
    # -------------------------------------------------------------------------
    stat_conf = _load_backtest_confidence()
    
    summary = _generate_summary(verdict["key"], final_composite, legends, macro_scores, stat_conf)
    confidence = _calculate_confidence_level(legends, macro_scores, stat_conf)
    action_plan = _generate_action_plan(final_composite, raw_data.get("market", {}).get("IHSG", {}).get("trend", "sideways"))
    
    analysis_end = datetime.now()
    duration = (analysis_end - analysis_start).total_seconds()

    # -------------------------------------------------------------------------
    # Build final response
    # -------------------------------------------------------------------------
    result = {
        "timestamp": analysis_end.isoformat(),
        "analysis_duration_seconds": round(duration, 2),
        "is_simulated": False,
        
        "statistical_validation": {
            "tier": stat_conf.get("tier", "unvalidated"),
            "tier_label": {
                "confirmed": "Tervalidasi", 
                "partial": "Sebagian Tervalidasi",
                "unconfirmed": "Belum Terbukti Signifikan", 
                "unvalidated": "Belum Ada Backtest"
            }.get(stat_conf.get("tier", "unvalidated"), "Belum Terbukti Signifikan"),
            "r2_oos_pct": stat_conf.get("r2_oos_pct"),
            "cw_p_value": stat_conf.get("cw_p_value"),
            "max_stock_allocation_pct": STAT_TIER_MAX_STOCK_ALLOCATION_PCT.get(stat_conf.get("tier", "unvalidated"), 60),
        },

        "verdict": {
            "key": verdict["key"],
            "label": verdict["label"],
            "composite_score": final_composite,
            "macro_composite": composite_score,
            "legend_consensus_score": legend_consensus_score,
            "max_score": 2.0,
            "min_score": -2.0,
        },

        "action_plan": action_plan,
        "sectors": sector_data,
        "summary": summary,
        "confidence": confidence,

        "macro_scores": {
            "individual": {
                key: {
                    "indicator": info["indicator"],
                    "value": info["value"],
                    "unit": info["unit"],
                    "score": info["score"],
                    "max_score": 2,
                    "min_score": -2,
                    "description": info["description"],
                    "reasoning": info["reasoning"],
                    "history": info.get("history", []),
                    "type": info.get("type", ""),
                    "weight": macro_scores["weighted_details"][key]["weight"],
                    "weighted_score": macro_scores["weighted_details"][key]["weighted_score"],
                }
                for key, info in macro_scores["individual_scores"].items()
            },
            "composite_score": composite_score,
        },

        "legends": [
            {
                "name": l["legend"],
                "philosophy": l["philosophy"],
                "verdict": l["verdict"],
                "confidence": l["confidence"],
                "reasoning": l["reasoning"],
                "icon": l.get("icon", ""),
                "full_explanation": l.get("full_explanation", ""),
                "extra": {k: v for k, v in l.items()
                          if k not in ("legend", "philosophy", "verdict",
                                       "confidence", "reasoning", "icon", "full_explanation")},
            }
            for l in legends
        ],

        "news_sentiment": {
            "score": news_sentiment["score"],
            "label": news_sentiment["label"],
            "total_news": news_sentiment["total_news"],
            "bullish_count": news_sentiment["bullish_count"],
            "bearish_count": news_sentiment["bearish_count"],
            "neutral_count": news_sentiment["neutral_count"],
            "warnings": news_sentiment["warnings"],
            "headlines": news_sentiment.get("headlines", []),
        },

        "mentors_analysis": mentors_analysis,
        "mentor_file_age_days": mentor_file_age,
        "market_cycle": market_cycle_data,
        "foreign_flow": foreign_flow_data,
        "macro_calendar": macro_calendar_data,
        "historical_pattern": pattern_data,

        "market_snapshot": {
            key: {
                "price": info.get("price"),
                "change_pct": info.get("change_pct"),
                "trend": info.get("trend"),
                "sma_50": info.get("sma_50"),
                "sma_200": info.get("sma_200"),
                "rsi_14": info.get("rsi_14"),
                "sma_cross": info.get("sma_cross"),
            }
            for key, info in raw_data.get("market", {}).items()
        },

        "macro_data": raw_data.get("macro", {}),
        "indonesia_data": raw_data.get("indonesia", {}),

        "data_errors": raw_data.get("errors", []),
        
        # Attach raw_data for simulation endpoint
        "raw_data": raw_data,
    }

    print(f"[Oracle] Analisis selesai dalam {duration:.1f} detik. Verdict: {verdict['label']}")
    return result


def get_simulated_verdict(cached_result: dict, override_data: dict, force_target_price: float = None) -> dict:
    """
    Generate a full oracle verdict based on simulated macro indicators.
    Bypasses data fetching, mentor sentiment analysis, and legend evaluation.
    """
    from datetime import datetime
    from copy import deepcopy

    raw_data = cached_result.get("raw_data", {})
    if not raw_data:
        raise ValueError("No raw_data available in cached result for simulation.")

    analysis_start = datetime.now()

    # Recalculate macro scores with overrides
    news_score = cached_result.get("news_sentiment", {}).get("score", 0.0)
    macro_scores = compute_macro_scores(raw_data, news_score=news_score, override_data=override_data)

    composite_score = macro_scores["composite_score"]
    legend_consensus_score = cached_result.get("verdict", {}).get("legend_consensus_score", 0.0)

    final_composite = round(composite_score, 4) # Pure quantitative
    final_composite = max(-2.0, min(2.0, final_composite))

    verdict = _determine_verdict(final_composite)

    # Regenerate simulated raw_data for legends
    simulated_raw_data = deepcopy(raw_data)
    if override_data:
        if "bi_rate" in override_data: simulated_raw_data.setdefault("indonesia", {})["bi_rate"] = override_data["bi_rate"]
        if "usdidr" in override_data: simulated_raw_data.setdefault("market", {}).setdefault("USDIDR", {})["price"] = override_data["usdidr"]
        if "inflation_id" in override_data: simulated_raw_data.setdefault("indonesia", {})["inflation"] = override_data["inflation_id"]
        if "trade_balance_id" in override_data: simulated_raw_data.setdefault("indonesia", {})["trade_balance"] = override_data["trade_balance_id"]
        if "gdp_growth_id" in override_data: simulated_raw_data.setdefault("indonesia", {})["gdp_growth"] = override_data["gdp_growth_id"]
        if "fed_rate" in override_data: simulated_raw_data.setdefault("macro", {})["fed_funds_rate"] = override_data["fed_rate"]
        if "dxy" in override_data: simulated_raw_data.setdefault("market", {}).setdefault("DXY", {})["price"] = override_data["dxy"]
        if "wti" in override_data: simulated_raw_data.setdefault("market", {}).setdefault("CRUDE_OIL", {})["price"] = override_data["wti"]

    from legends_engine import run_all_legends
    legends_raw = run_all_legends(simulated_raw_data)
    
    # Required for summary and confidence
    legends = []
    for l in legends_raw:
        legends.append({
            "legend": l.get("legend"),
            "philosophy": l.get("philosophy"),
            "verdict": l.get("verdict"),
            "confidence": l.get("confidence"),
            "reasoning": l.get("reasoning")
        })

    # Format for final response
    legends_formatted = [
        {
            "name": l["legend"],
            "philosophy": l["philosophy"],
            "verdict": l["verdict"],
            "confidence": l["confidence"],
            "reasoning": l["reasoning"],
            "icon": l.get("icon", ""),
            "full_explanation": l.get("full_explanation", ""),
            "extra": {k: v for k, v in l.items()
                      if k not in ("legend", "philosophy", "verdict",
                                   "confidence", "reasoning", "icon", "full_explanation")}
        }
        for l in legends_raw
    ]

    summary = _generate_summary(verdict["key"], final_composite, legends, macro_scores)
    confidence = _calculate_confidence_level(legends, macro_scores)
    action_plan = _generate_action_plan(final_composite, raw_data.get("market", {}).get("IHSG", {}).get("trend", "sideways"))
    
    # Calculate sectors and top picks
    sectors_data = calculate_sectors_and_picks(macro_scores)

    # -------------------------------------------------------------------------
    # PILLAR 5: Simulated Mentor Analysis (Dynamic conclusion adjusts to simulated macro)
    # -------------------------------------------------------------------------
    mentors_analysis = analyze_mentors_original(macro_scores["composite_score"], simulated_raw_data)
    mentor_file_age = get_mentor_file_age_days()
    
    # -------------------------------------------------------------------------
    # PILLAR 6: Simulated Market Direction Features
    # -------------------------------------------------------------------------
    pattern_data = match_historical_pattern(simulated_raw_data, macro_scores['composite_score'])
    slope = _load_backtest_confidence().get("sensitivity_model", {}).get("slope", 0.075)
    market_cycle_data = analyze_market_cycle(simulated_raw_data, macro_scores['composite_score'], is_simulated=True, pattern_data=pattern_data, force_target_price=force_target_price, sensitivity_slope=slope)
    foreign_flow_data = None
    macro_calendar_data = get_macro_calendar()

    analysis_end = datetime.now()
    duration = (analysis_end - analysis_start).total_seconds()

    # Create new result by deeply copying the cached result and applying updates
    simulated_result = deepcopy(cached_result)
    simulated_result["timestamp"] = analysis_end.isoformat()
    simulated_result["analysis_duration_seconds"] = round(duration, 2)
    simulated_result["is_simulated"] = True
    
    simulated_result["verdict"].update({
        "key": verdict["key"],
        "label": verdict["label"],
        "composite_score": final_composite,
        "macro_composite": composite_score,
    })

    simulated_result["action_plan"] = action_plan
    simulated_result["sectors"] = sectors_data
    simulated_result["summary"] = summary
    simulated_result["confidence"] = confidence
    simulated_result["mentors_analysis"] = mentors_analysis
    simulated_result["mentor_file_age_days"] = mentor_file_age
    simulated_result["legends"] = legends_formatted
    
    simulated_result["market_cycle"] = market_cycle_data
    simulated_result["foreign_flow"] = foreign_flow_data
    simulated_result["macro_calendar"] = macro_calendar_data
    simulated_result["historical_pattern"] = pattern_data

    simulated_result["macro_scores"] = {
        "individual": {
            key: {
                "indicator": info["indicator"],
                "value": info["value"],
                "unit": info["unit"],
                "score": info["score"],
                "max_score": 2,
                "min_score": -2,
                "description": info["description"],
                "reasoning": info["reasoning"],
                "history": info.get("history", []),
                "type": info.get("type", ""),
                "source": info.get("source", "live"),
                "is_live": info.get("is_live", True),
                "weight": macro_scores["weighted_details"][key]["weight"],
                "weighted_score": macro_scores["weighted_details"][key]["weighted_score"],
            }
            for key, info in macro_scores["individual_scores"].items()
        },
        "composite_score": composite_score,
    }

    return simulated_result


def get_reverse_simulated_verdict(cached_result: dict, target_price: float) -> dict:
    """
    Reverse engineers the macro indicators required to reach a specific target price,
    and then runs a full simulation with those indicators.
    """
    import backtest_engine
    raw_data = cached_result.get("raw_data", {})
    if not raw_data:
        raise ValueError("No raw_data available in cached result for simulation.")
        
    ihsg_price = raw_data.get("market", {}).get("IHSG", {}).get("price")
    if not ihsg_price:
        raise ValueError("IHSG price not found in cached data.")
        
    stat_conf = _load_backtest_confidence()
    slope = stat_conf.get("sensitivity_model", {}).get("slope", 0.075)
    
    # Reverse engineer the macro score
    required_macro_score = ((target_price / ihsg_price) - 1.0) / slope
    ms = max(-2.0, min(2.0, required_macro_score))
    
    # Load historical data to find empirical percentiles
    df_full = backtest_engine.get_historical_data()
    # Compute live_composite on historical data
    df_full["live_composite"] = df_full.apply(lambda r: backtest_engine._apply_live_discrete_scoring(r, df_full), axis=1)
    
    # Filter to similar macro score ranges (+- 0.5 margin)
    margin = 0.5
    df_similar = df_full[(df_full["live_composite"] >= ms - margin) & (df_full["live_composite"] <= ms + margin)]
    
    if len(df_similar) < 5: # Fallback to a wider margin if not enough data
        df_similar = df_full[(df_full["live_composite"] >= ms - 1.0) & (df_full["live_composite"] <= ms + 1.0)]
        if len(df_similar) < 5:
            df_similar = df_full # Fallback to all data
            
    # Helper to calculate quantiles
    def get_q(col, is_inverted=False):
        if col not in df_similar.columns: return {"min": 0, "max": 0, "point": 0}
        s = df_similar[col].dropna()
        if len(s) == 0: return {"min": 0, "max": 0, "point": 0}
        p10 = round(s.quantile(0.1), 2)
        p50 = round(s.quantile(0.5), 2)
        p90 = round(s.quantile(0.9), 2)
        if is_inverted:
            return {"min": p90, "max": p10, "point": p50}
        return {"min": p10, "max": p90, "point": p50}
    
    # Create empirical scenarios
    scenarios = [{
        "name": "Skenario Empiris Berdasarkan Data Historis",
        "description": f"Rentang nilai (persentil 10-90) diekstraksi secara empiris dari distribusi historis saat Macro Score berada di kisaran {ms:.2f}.",
        "data": {
            "usdidr": get_q("USDIDR"),
            "bi_rate": get_q("BI_RATE"),
            "inflation_id": get_q("ID_CPI_YOY"),
            "gdp_growth_id": get_q("ID_GDP_YOY"),
            "trade_balance_id": get_q("ID_TRADE"),
            "fed_rate": get_q("FEDFUNDS"),
            "dxy": get_q("DXY"),
            "wti": get_q("WTI"),
        }
    }]
        
    # Untuk menjalankan simulasi engine ke downstream (seperti technical degree dll), 
    # kita gunakan 'point' dari skenario utama (Scenario 0) sebagai titik representatif,
    # namun UI frontend akan menerima seluruh rentang ensemble ini.
    primary_scenario = scenarios[0]["data"]
    reverse_macro_point = {k: v["point"] for k, v in primary_scenario.items()}
    
    # Run the normal simulation with these new macro values
    result = get_simulated_verdict(cached_result, reverse_macro_point, force_target_price=target_price)
    
    # Force the target price to exactly what the user typed to avoid rounding artifacts
    if "market_cycle" in result:
        result["market_cycle"]["target_price"] = target_price
        
    # Inject the ensemble scenarios so the frontend can display ranges!
    result["macro_scenarios"] = scenarios
    
    # Backward compatibility: Inject reverse_macro (using Scenario A points) so existing UI sliders don't crash
    result["reverse_macro"] = reverse_macro_point
    
    return result


if __name__ == "__main__":
    print("Menjalankan The Market Oracle...\n")
    result = get_verdict()

    print(f"\n{'='*60}")
    print(f"  THE MARKET ORACLE - VERDICT")
    print(f"{'='*60}")
    print(f"  {result['verdict']['label']}")
    print(f"  Skor Komposit: {result['verdict']['composite_score']:.2f} / 2.00")
    print(f"  Confidence: {result['confidence']['label']} ({result['confidence']['score']})")
    print(f"{'='*60}")
    print(f"\n{result['summary']}")

    print(f"\n--- Skor Individual ---")
    for key, info in result['macro_scores']['individual'].items():
        print(f"  {info['indicator']}: {info['score']:+d} (bobot {info['weight']*100:.0f}%)")

    print(f"\n--- Analisis Legenda ---")
    for legend in result['legends']:
        print(f"  {legend['name']}: {legend['verdict'].upper()} (confidence: {legend['confidence']})")

    if result['data_errors']:
        print(f"\n--- Error Data ({len(result['data_errors'])}) ---")
        for err in result['data_errors']:
            print(f"  ! {err}")
