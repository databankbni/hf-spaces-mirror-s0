import sys
sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# The Market Oracle - Legends Engine
# Rule-based analysis inspired by investing legends
# =============================================================================

from config import PER_THRESHOLDS, DALIO_PHASES


def _per_category(per: float) -> str:
    """Determine PER category."""
    for label, (low, high) in PER_THRESHOLDS.items():
        if low <= per < high:
            return label
    return "fair"


def analyze_buffett_graham(ihsg_per: float, mentor_sentiment_label: str,
                           ihsg_earnings_growth: float, bi_rate: float) -> dict:
    """
    Warren Buffett & Benjamin Graham Analysis:
    - Focus on valuation (PER) vs intrinsic value
    - 'Be greedy when others are fearful'
    - Margin of safety principle
    """
    confidence = 0.5
    reasons = []
    verdict = "neutral"

    # PER analysis
    per_cat = _per_category(ihsg_per)
    if per_cat == "very_cheap":
        verdict = "bullish"
        confidence += 0.3
        reasons.append(
            f"IHSG PER di {ihsg_per}x sangat murah secara historis. "
            "Graham akan melihat margin of safety yang besar di level ini."
        )
    elif per_cat == "cheap":
        verdict = "bullish"
        confidence += 0.2
        reasons.append(
            f"IHSG PER di {ihsg_per}x tergolong undervalued. "
            "Valuasi menarik bagi investor value."
        )
    elif per_cat == "fair":
        reasons.append(
            f"IHSG PER di {ihsg_per}x berada di zona wajar. "
            "Buffett akan menunggu harga lebih murah atau melihat kualitas earnings."
        )
    elif per_cat == "expensive":
        verdict = "bearish"
        confidence += 0.15
        reasons.append(
            f"IHSG PER di {ihsg_per}x mulai mahal. "
            "Graham akan memperingatkan kurangnya margin of safety."
        )
    else:
        verdict = "bearish"
        confidence += 0.3
        reasons.append(
            f"IHSG PER di {ihsg_per}x sangat mahal. "
            "Buffett akan mengatakan 'market sedang serakah'."
        )

    # Contrarian sentiment check (Buffett's 'be greedy when fearful')
    sentiment_lower = mentor_sentiment_label.lower()
    if "bearish" in sentiment_lower and per_cat in ("very_cheap", "cheap"):
        if verdict != "bullish":
            verdict = "bullish"
        confidence += 0.15
        reasons.append(
            "Sentimen mentor mayoritas bearish sementara valuasi murah. "
            "Buffett: 'Be greedy when others are fearful.' Ini bisa menjadi peluang beli."
        )
    elif "bullish" in sentiment_lower and per_cat in ("expensive", "very_expensive"):
        if verdict != "bearish":
            verdict = "bearish"
        confidence += 0.15
        reasons.append(
            "Sentimen mentor mayoritas bullish sementara valuasi mahal. "
            "Buffett: 'Be fearful when others are greedy.' Waspada potensi koreksi."
        )

    # Earnings yield vs bond yield (Buffett style)
    earnings_yield = (1 / ihsg_per) * 100 if ihsg_per > 0 else 0
    if earnings_yield > bi_rate + 2:
        reasons.append(
            f"Earnings yield IHSG ({earnings_yield:.1f}%) jauh di atas BI rate ({bi_rate}%), "
            "saham lebih menarik dibanding obligasi menurut Buffett."
        )
        if verdict == "neutral":
            verdict = "bullish"
            confidence += 0.1
    elif earnings_yield < bi_rate:
        reasons.append(
            f"Earnings yield IHSG ({earnings_yield:.1f}%) di bawah BI rate ({bi_rate}%), "
            "obligasi bisa lebih menarik menurut valuasi Buffett."
        )

    confidence = min(confidence, 1.0)
    reasons.append(
        f"[DATA STATIS] Analisis ini menggunakan PER={ihsg_per}x dan EPS Growth={ihsg_earnings_growth}% "
        "yang TIDAK di-update otomatis dari sumber live. Angka ini dikalibrasi secara manual."
    )

    return {
        "legend": "Warren Buffett & Benjamin Graham",
        "philosophy": "Value Investing - Margin of Safety",
        "verdict": verdict,
        "confidence": round(confidence, 2),
        "conviction_score": round(confidence, 2),
        "methodology": "rule_based_heuristic",
        "disclaimer": "Skor ini adalah estimasi heuristik berdasarkan prinsip value investing Buffett/Graham, bukan hasil kalibrasi statistik atau machine learning.",
        "uses_static_data": True,
        "reasoning": " ".join(reasons),
        "icon": "buffett",
    }


def analyze_soros(dxy_price: float, usdidr_price: float,
                  ihsg_price: float, ihsg_trend: str,
                  sp500_trend: str) -> dict:
    """
    George Soros Analysis:
    - Reflexivity theory: market perceptions create reality
    - Focus on currency/capital flow divergences
    - Look for boom-bust patterns
    """
    confidence = 0.5
    reasons = []
    verdict = "neutral"

    # DXY vs USD/IDR divergence analysis
    if dxy_price is not None and usdidr_price is not None:
        # Check if rupiah is weaker than DXY implies (capital outflow signal)
        # High DXY + very weak IDR = double negative
        if dxy_price > 105 and usdidr_price > 16500:
            verdict = "bearish"
            confidence += 0.25
            reasons.append(
                f"DXY kuat di {dxy_price} dan Rupiah lemah di Rp{usdidr_price:,.0f}. "
                "Soros melihat tekanan ganda pada aset emerging market Indonesia. "
                "Risiko capital outflow yang reflexive - pelemahan memicu pelemahan lebih lanjut."
            )
        elif dxy_price < 100 and usdidr_price < 15500:
            verdict = "bullish"
            confidence += 0.25
            reasons.append(
                f"DXY melemah di {dxy_price} dan Rupiah menguat di Rp{usdidr_price:,.0f}. "
                "Soros melihat arus modal mengalir ke emerging markets. "
                "Feedback loop positif - penguatan menarik lebih banyak investasi."
            )
        elif dxy_price > 105 and usdidr_price < 15800:
            reasons.append(
                f"Divergensi menarik: DXY kuat ({dxy_price}) tapi Rupiah relatif stabil "
                f"(Rp{usdidr_price:,.0f}). Soros akan memantau apakah ini sustainable "
                "atau Rupiah akan menyusul melemah."
            )
        elif dxy_price < 100 and usdidr_price > 16000:
            reasons.append(
                f"Anomali: DXY lemah ({dxy_price}) tapi Rupiah masih lemah "
                f"(Rp{usdidr_price:,.0f}). Ada faktor domestik yang menekan. "
                "Soros akan mencari katalis perubahan."
            )

    # Capital flow vs IHSG divergence
    if ihsg_trend is not None and sp500_trend is not None:
        if sp500_trend == "uptrend" and ihsg_trend == "downtrend":
            if verdict != "bearish":
                verdict = "bearish"
            confidence += 0.15
            reasons.append(
                "S&P500 naik tapi IHSG turun - divergensi negatif. "
                "Soros melihat capital lebih memilih US market. "
                "Kemungkinan ada masalah domestik yang belum terefleksi sepenuhnya."
            )
        elif sp500_trend == "downtrend" and ihsg_trend == "uptrend":
            if verdict != "bullish":
                verdict = "bullish"
            confidence += 0.15
            reasons.append(
                "IHSG naik meskipun S&P500 turun - divergensi positif. "
                "Soros melihat kekuatan relatif pasar Indonesia. "
                "Possible rotation dari US ke emerging markets."
            )
        elif sp500_trend == "uptrend" and ihsg_trend == "uptrend":
            reasons.append(
                "Kedua pasar naik bersamaan. Soros akan waspada terhadap "
                "boom yang reflexive - apakah fundamental mendukung?"
            )

    # Boom-bust reflexivity check
    if ihsg_price is not None:
        if ihsg_trend == "uptrend":
            reasons.append(
                "Soros memperingatkan: setiap boom membawa benih bust-nya sendiri. "
                "Perhatikan tanda-tanda euphoria berlebihan."
            )
        elif ihsg_trend == "downtrend":
            reasons.append(
                "Dalam teori reflexivity Soros, penurunan bisa menjadi self-reinforcing "
                "sampai menemukan katalis pembalikan. Cari tanda-tanda kapitulasi."
            )

    if not reasons:
        reasons.append("Tidak ada divergensi signifikan yang terdeteksi. Soros akan menunggu setup yang lebih jelas.")

    confidence = min(confidence, 1.0)

    return {
        "legend": "George Soros",
        "philosophy": "Reflexivity Theory - Capital Flows",
        "verdict": verdict,
        "confidence": round(confidence, 2),
        "conviction_score": round(confidence, 2),
        "methodology": "rule_based_heuristic",
        "disclaimer": "Skor ini adalah estimasi heuristik berdasarkan teori reflexivity Soros, bukan hasil kalibrasi statistik atau machine learning.",
        "reasoning": " ".join(reasons),
        "icon": "soros",
    }


def analyze_dalio(inflation_id: float, bi_rate: float, fed_rate: float,
                  us_gdp_growth: float, us_cpi_yoy: float) -> dict:
    """
    Ray Dalio Analysis:
    - All Weather / Economic Machine framework
    - Determine current economic cycle phase
    - Inflation + growth matrix
    """
    confidence = 0.5
    reasons = []
    verdict = "neutral"

    # Determine cycle phase using inflation + interest rate combination
    # Use both Indonesian and US data
    avg_inflation = inflation_id
    if us_cpi_yoy is not None:
        avg_inflation = (inflation_id + us_cpi_yoy) / 2

    avg_rate = bi_rate
    if fed_rate is not None:
        avg_rate = (bi_rate + fed_rate) / 2

    growth_positive = True
    if us_gdp_growth is not None:
        growth_positive = us_gdp_growth > 0

    # Phase determination
    phase = None
    if avg_inflation < 3.5 and avg_rate < 5.0 and growth_positive:
        phase = "goldilocks"
        verdict = "bullish"
        confidence += 0.3
    elif avg_inflation >= 3.5 and avg_inflation < 5.0 and avg_rate < 6.0 and growth_positive:
        phase = "reflation"
        verdict = "neutral"
        confidence += 0.1
    elif avg_inflation >= 5.0 and avg_rate >= 5.5:
        if growth_positive:
            phase = "overheating"
            verdict = "bearish"
            confidence += 0.25
        else:
            phase = "stagflation"
            verdict = "bearish"
            confidence += 0.35
    elif avg_inflation < 3.5 and avg_rate >= 5.0 and not growth_positive:
        phase = "deleveraging"
        verdict = "neutral"
        confidence += 0.15
    else:
        # Default: determine based on dominant factor
        if avg_inflation > 4.5:
            phase = "overheating"
            verdict = "bearish"
            confidence += 0.15
        elif avg_rate < 4.0:
            phase = "goldilocks"
            verdict = "bullish"
            confidence += 0.15
        else:
            phase = "reflation"
            confidence += 0.05

    phase_info = DALIO_PHASES.get(phase, DALIO_PHASES["reflation"])

    reasons.append(
        f"Fase ekonomi saat ini menurut kerangka Dalio: {phase_info['label']}. "
        f"{phase_info['description']}"
    )

    reasons.append(
        f"Inflasi rata-rata: {avg_inflation:.1f}%, suku bunga rata-rata: {avg_rate:.1f}%."
    )

    if us_gdp_growth is not None:
        if us_gdp_growth > 3:
            reasons.append(f"Pertumbuhan GDP AS di {us_gdp_growth}% - ekonomi ekspansif.")
        elif us_gdp_growth > 0:
            reasons.append(f"Pertumbuhan GDP AS di {us_gdp_growth}% - pertumbuhan moderat.")
        else:
            reasons.append(f"GDP AS mengalami kontraksi ({us_gdp_growth}%) - risiko resesi meningkat.")

    # Dalio's debt cycle perspective
    if bi_rate >= 6.5 and fed_rate is not None and fed_rate >= 5.0:
        reasons.append(
            "Suku bunga tinggi secara global menurut Dalio meningkatkan risiko debt distress. "
            "Perhatikan tanda-tanda stress di sektor perbankan dan properti."
        )

    confidence = min(confidence, 1.0)

    return {
        "legend": "Ray Dalio",
        "philosophy": "Economic Machine - Siklus Ekonomi",
        "verdict": verdict,
        "confidence": round(confidence, 2),
        "conviction_score": round(confidence, 2),
        "methodology": "rule_based_heuristic",
        "disclaimer": "Skor ini adalah estimasi heuristik berdasarkan Economic Machine framework Dalio, bukan hasil kalibrasi statistik atau machine learning.",
        "reasoning": " ".join(reasons),
        "phase": phase_info["label"],
        "icon": "dalio",
    }


def analyze_lynch(ihsg_per: float, earnings_growth: float,
                  ihsg_trend: str) -> dict:
    """
    Peter Lynch Analysis:
    - PEG ratio (PER / Earnings Growth)
    - 'Invest in what you know'
    - Growth at a reasonable price (GARP)
    """
    confidence = 0.5
    reasons = []
    verdict = "neutral"

    # PEG Ratio calculation
    peg = None
    if earnings_growth > 0:
        peg = ihsg_per / earnings_growth
    elif earnings_growth == 0:
        peg = float('inf')
    else:
        peg = None  # Negative earnings growth = problematic

    if peg is not None and peg != float('inf'):
        if peg < 0.5:
            verdict = "bullish"
            confidence += 0.3
            reasons.append(
                f"PEG ratio IHSG di {peg:.2f} (PER {ihsg_per}x / pertumbuhan {earnings_growth}%). "
                "Sangat murah menurut Lynch! Pasar belum menghargai pertumbuhan earnings dengan semestinya."
            )
        elif peg < 1.0:
            verdict = "bullish"
            confidence += 0.2
            reasons.append(
                f"PEG ratio IHSG di {peg:.2f}, di bawah 1.0 - 'sweet spot' Peter Lynch. "
                "Pertumbuhan earnings masih lebih cepat dari valuasi pasar."
            )
        elif peg < 1.5:
            reasons.append(
                f"PEG ratio IHSG di {peg:.2f}, mendekati fair value. "
                "Lynch masih tertarik tapi akan lebih selektif memilih saham."
            )
        elif peg < 2.0:
            verdict = "bearish"
            confidence += 0.1
            reasons.append(
                f"PEG ratio IHSG di {peg:.2f}, mulai mahal untuk pertumbuhan yang ditawarkan. "
                "Lynch akan mencari peluang di sektor lain."
            )
        else:
            verdict = "bearish"
            confidence += 0.25
            reasons.append(
                f"PEG ratio IHSG di {peg:.2f}, sangat mahal. "
                "Lynch: 'Jangan bayar terlalu mahal untuk pertumbuhan.'"
            )
    elif peg == float('inf'):
        verdict = "bearish"
        confidence += 0.2
        reasons.append(
            "Pertumbuhan earnings 0% - Lynch tidak tertarik dengan saham tanpa pertumbuhan."
        )
    else:
        verdict = "bearish"
        confidence += 0.2
        reasons.append(
            f"Pertumbuhan earnings negatif ({earnings_growth}%). "
            "Lynch akan menghindari pasar dengan earnings yang menurun."
        )

    # Lynch's practical approach
    if ihsg_trend == "uptrend" and verdict == "bullish":
        confidence += 0.1
        reasons.append(
            "Tren IHSG naik sejalan dengan valuasi yang menarik. "
            "Lynch: 'Tenbagger dimulai dari cerita pertumbuhan yang sederhana.'"
        )
    elif ihsg_trend == "downtrend" and verdict == "bullish":
        reasons.append(
            "Meski valuasi menarik, tren masih turun. "
            "Lynch akan sabar menunggu konfirmasi pembalikan sebelum menambah posisi."
        )

    # Lynch's sector insight for Indonesia
    if earnings_growth > 10:
        reasons.append(
            f"Pertumbuhan earnings {earnings_growth}% menunjukkan ekonomi Indonesia yang dinamis. "
            "Lynch akan mencari emiten domestik dengan cerita pertumbuhan yang kuat."
        )

    confidence = min(confidence, 1.0)
    reasons.append(
        f"[DATA STATIS] Analisis PEG ini menggunakan PER={ihsg_per}x dan EPS Growth={earnings_growth}% "
        "yang TIDAK di-update otomatis dari sumber live. Angka ini dikalibrasi secara manual."
    )

    return {
        "legend": "Peter Lynch",
        "philosophy": "Growth at Reasonable Price (GARP)",
        "verdict": verdict,
        "confidence": round(confidence, 2),
        "conviction_score": round(confidence, 2),
        "methodology": "rule_based_heuristic",
        "disclaimer": "Skor ini adalah estimasi heuristik berdasarkan prinsip GARP Lynch, bukan hasil kalibrasi statistik atau machine learning.",
        "uses_static_data": True,
        "reasoning": " ".join(reasons),
        "peg_ratio": round(peg, 2) if peg is not None and peg != float('inf') else None,
        "icon": "lynch",
    }


def analyze_simons(rsi: float, sma_cross: str, ihsg_trend: str,
                   sma_50: float, sma_200: float, ihsg_price: float) -> dict:
    """
    Jim Simons / Quant Analysis:
    - Pure technical/quantitative approach
    - SMA crossovers, RSI, trend following
    - No emotion, just the data
    """
    confidence = 0.5
    reasons = []
    signals = {"bullish": 0, "bearish": 0, "neutral": 0}

    # Signal 1: SMA Crossover
    if sma_cross == "golden_cross":
        signals["bullish"] += 2
        reasons.append(
            "SINYAL 1 - Golden Cross: SMA-50 memotong SMA-200 ke atas. "
            "Secara kuantitatif, ini sinyal bullish jangka menengah dengan win-rate historis ~65%."
        )
    elif sma_cross == "death_cross":
        signals["bearish"] += 2
        reasons.append(
            "SINYAL 1 - Death Cross: SMA-50 memotong SMA-200 ke bawah. "
            "Secara kuantitatif, ini sinyal bearish jangka menengah."
        )
    else:
        signals["neutral"] += 1
        reasons.append("SINYAL 1 - SMA Cross: Tidak ada crossover terbaru, tidak ada sinyal kuat.")

    # Signal 2: RSI
    if rsi is not None:
        if rsi < 25:
            signals["bullish"] += 2
            reasons.append(
                f"SINYAL 2 - RSI({rsi:.1f}): Extremely oversold. "
                "Probabilitas rebound dalam 5-10 hari sangat tinggi berdasarkan data historis."
            )
        elif rsi < 35:
            signals["bullish"] += 1
            reasons.append(
                f"SINYAL 2 - RSI({rsi:.1f}): Oversold territory. "
                "Peluang rebound meningkat."
            )
        elif rsi > 75:
            signals["bearish"] += 2
            reasons.append(
                f"SINYAL 2 - RSI({rsi:.1f}): Extremely overbought. "
                "Probabilitas koreksi dalam 5-10 hari sangat tinggi."
            )
        elif rsi > 65:
            signals["bearish"] += 1
            reasons.append(
                f"SINYAL 2 - RSI({rsi:.1f}): Mendekati overbought. "
                "Momentum mulai melemah."
            )
        else:
            signals["neutral"] += 1
            reasons.append(
                f"SINYAL 2 - RSI({rsi:.1f}): Zona netral, tidak ada edge signifikan."
            )

    # Signal 3: Price vs SMA
    if ihsg_price is not None and sma_50 is not None and sma_200 is not None:
        above_50 = ihsg_price > sma_50
        above_200 = ihsg_price > sma_200

        if above_50 and above_200:
            signals["bullish"] += 1
            pct_above = ((ihsg_price / sma_200) - 1) * 100
            reasons.append(
                f"SINYAL 3 - Harga di atas SMA-50 dan SMA-200 (+{pct_above:.1f}% dari SMA-200). "
                "Struktur harga bullish."
            )
        elif not above_50 and not above_200:
            signals["bearish"] += 1
            pct_below = ((ihsg_price / sma_200) - 1) * 100
            reasons.append(
                f"SINYAL 3 - Harga di bawah SMA-50 dan SMA-200 ({pct_below:.1f}% dari SMA-200). "
                "Struktur harga bearish."
            )
        else:
            signals["neutral"] += 1
            reasons.append(
                "SINYAL 3 - Harga berada di antara SMA-50 dan SMA-200. Zona transisi."
            )

    # Signal 4: Trend momentum
    if ihsg_trend == "uptrend":
        signals["bullish"] += 1
        reasons.append("SINYAL 4 - Momentum: Tren naik terkonfirmasi oleh price action 20/60 hari.")
    elif ihsg_trend == "downtrend":
        signals["bearish"] += 1
        reasons.append("SINYAL 4 - Momentum: Tren turun terkonfirmasi oleh price action 20/60 hari.")
    else:
        signals["neutral"] += 1
        reasons.append("SINYAL 4 - Momentum: Tidak ada tren yang jelas, volatilitas rendah.")

    # Aggregate quant verdict
    total_bullish = signals["bullish"]
    total_bearish = signals["bearish"]

    if total_bullish >= 4:
        verdict = "bullish"
        confidence += 0.35
    elif total_bullish >= 3 and total_bearish <= 1:
        verdict = "bullish"
        confidence += 0.2
    elif total_bearish >= 4:
        verdict = "bearish"
        confidence += 0.35
    elif total_bearish >= 3 and total_bullish <= 1:
        verdict = "bearish"
        confidence += 0.2
    else:
        verdict = "neutral"
        confidence += 0.05

    reasons.append(
        f"RINGKASAN KUANTITATIF: {total_bullish} sinyal bullish, "
        f"{total_bearish} sinyal bearish, {signals['neutral']} netral."
    )

    confidence = min(confidence, 1.0)

    return {
        "legend": "Jim Simons",
        "philosophy": "Quantitative / Systematic Trading",
        "verdict": verdict,
        "confidence": round(confidence, 2),
        "conviction_score": round(confidence, 2),
        "methodology": "rule_based_heuristic",
        "disclaimer": "Skor ini adalah estimasi heuristik berdasarkan model kuantitatif teknikal, bukan hasil kalibrasi statistik atau machine learning.",
        "reasoning": " ".join(reasons),
        "signals_summary": signals,
        "icon": "simons",
    }



def _generate_textbook_explanation(legend: dict) -> str:
    name = legend.get("legend", "")
    verdict = legend.get("verdict", "")
    reasoning = legend.get("reasoning", "")
    
    if "Buffett" in name:
        base = "Pendekatan Benjamin Graham dan Warren Buffett selalu berakar pada konsep 'Margin of Safety'. Dalam buku ikonik 'The Intelligent Investor', Graham menekankan bahwa investor tidak boleh membeli saham hanya karena tren pasar sedang naik, melainkan harus melihat nilai intrinsik perusahaan. "
        if verdict == "bullish":
            base += "Kondisi saat ini mengingatkan pada adagium terkenal Buffett: 'Be greedy when others are fearful.' Karena valuasi pasar (IHSG PER) sedang berada di level yang sangat rasional atau bahkan di bawah rata-rata historisnya, ini adalah waktu yang tepat untuk mengumpulkan saham-saham perusahaan berkualitas tinggi (Blue Chips) yang memiliki neraca keuangan solid dan rekam jejak dividen konsisten."
        elif verdict == "bearish":
            base += "Dengan valuasi pasar yang mulai menembus batas kewajaran, Buffett akan menyarankan sikap defensif. Sesuai prinsip 'Be fearful when others are greedy', pasar yang terlalu optimis seringkali mengabaikan risiko fundamental. Dalam kondisi ini, akumulasi uang tunai (cash) atau beralih ke obligasi berisiko rendah adalah langkah paling bijak sambil menunggu 'koreksi sehat' yang akan mengembalikan margin of safety."
        else:
            base += "Pasar saat ini berada di wilayah 'fair value' (harga wajar). Buffett jarang melakukan manuver agresif di zona netral. Alih-alih membeli indeks secara keseluruhan, pendekatannya akan beralih ke 'stock picking' ultra-selektif—mencari anomali harga pada perusahaan dengan 'Economic Moat' yang luar biasa kuat, atau sekadar menahan posisi yang ada dan mengakumulasi dividen."
            
    elif "Soros" in name:
        base = "Teori Refleksivitas (Reflexivity) dari George Soros mengajarkan bahwa persepsi pelaku pasar sering kali mendikte realitas ekonomi, dan sebaliknya. Soros sangat memperhatikan siklus 'Boom and Bust' serta pergerakan arus modal global (capital flows) yang tercermin dari divergensi nilai tukar mata uang dan indeks saham asing. "
        if verdict == "bullish":
            base += "Divergensi positif antara melemahnya Dolar AS (DXY) dan menguatnya nilai tukar lokal menunjukkan adanya rotasi modal besar-besaran (capital inflow) menuju emerging markets seperti Indonesia. Dalam bukunya 'The Alchemy of Finance', Soros menyebut ini sebagai 'positive feedback loop', di mana penguatan aset memicu lebih banyak investor masuk. Ini adalah momentum untuk 'ride the trend' sebelum siklus mencapai puncaknya."
        elif verdict == "bearish":
            base += "Terjadi divergensi negatif yang mengkhawatirkan. Kuatnya Dolar AS yang menekan Rupiah sering menjadi indikasi awal pelarian modal (capital outflow). Soros akan membaca ini sebagai potensi 'negative feedback loop' atau fase awal dari Bust cycle. Ketika pasar menyadari bahwa fundamental tidak mampu menopang valuasi akibat likuiditas yang mengering, koreksi tajam bisa terjadi kapan saja. Soros akan menyiapkan posisi short atau lindung nilai (hedging)."
        else:
            base += "Saat ini tidak ada divergensi ekstrem atau disequilibrium yang signifikan antara nilai tukar dan indeks. Arus modal bergerak dalam rentang normal tanpa indikasi rotasi yang kuat. Soros, yang dikenal sebagai spekulan makro yang agresif, umumnya akan menahan diri dari posisi besar di pasar yang 'sideways' dan tidak memiliki arah makro yang jelas."

    elif "Dalio" in name:
        base = "Kerangka 'All Weather' dan 'Economic Machine' milik Ray Dalio membagi ekonomi ke dalam empat kuadran berdasarkan pertumbuhan (growth) dan inflasi (inflation). Dalio sangat memperhatikan kebijakan suku bunga bank sentral karena kredit/utang adalah pendorong utama siklus ekonomi jangka pendek. "
        if verdict == "bullish":
            base += "Pasar saat ini berada dalam fase 'Goldilocks'—pertumbuhan ekonomi positif dengan inflasi yang terkendali. Ini memungkinkan bank sentral mempertahankan suku bunga rendah, memicu ekspansi kredit. Berdasarkan siklus utang Dalio, ini adalah fase 'Beautiful Deleveraging' atau ekspansi awal di mana aset berisiko (saham) memberikan imbal hasil optimal. Portofolio sebaiknya dimiringkan secara agresif ke arah ekuitas."
        elif verdict == "bearish":
            base += "Ekonomi sedang memasuki fase kontraksi atau stagflasi (inflasi tinggi, pertumbuhan melambat). Dalam kondisi ini, bank sentral dipaksa menaikkan suku bunga yang berujung pada pengetatan likuiditas. Menurut model All Weather, saham adalah kelas aset berkinerja paling buruk di siklus ini. Bobot investasi sebaiknya dialihkan secara drastis ke aset pelindung nilai (inflation-linked bonds, emas) atau uang tunai untuk melindungi nilai pokok."
        else:
            base += "Kondisi makroekonomi sedang berada dalam masa transisi atau reflasi, di mana indikator pertumbuhan dan inflasi memberikan sinyal yang saling bertentangan (mixed signals). Dalio akan menerapkan strategi 'All Weather' klasik: menyeimbangkan bobot portofolio ke berbagai kelas aset (Saham, Obligasi Pemerintah, Emas, dan Komoditas) untuk meminimalisir volatilitas sambil mengamati ke arah mana siklus utang jangka pendek akan berayun."

    elif "Lynch" in name:
        base = "Peter Lynch adalah pionir konsep 'Growth at a Reasonable Price' (GARP) dan prinsip 'Buy What You Know'. Dalam bukunya 'One Up On Wall Street', ia mempopulerkan metrik PEG Ratio (Price/Earnings to Growth) untuk memastikan investor tidak membayar terlalu mahal untuk sebuah pertumbuhan. "
        if verdict == "bullish":
            base += "Kombinasi PER yang rendah dan proyeksi pertumbuhan laba (earnings growth) yang solid menghasilkan PEG Ratio yang sangat atraktif (di bawah 1.0). Ini adalah skenario impian Peter Lynch: mendapatkan perusahaan dengan prospek pertumbuhan tinggi di harga diskon. Di pasar seperti ini, Lynch akan mencari 'Tenbaggers' (saham yang bisa naik 10x lipat) secara agresif, terutama di sektor-sektor yang sedang mengalami turnaround atau fast-growers."
        elif verdict == "bearish":
            base += "PEG Ratio pasar menunjukkan angka yang tidak wajar (overvaluation yang parah relatif terhadap pertumbuhan laba). Lynch memperingatkan bahaya saham 'Whisper' atau saham populer yang valuasinya sudah tidak masuk akal. Ketika indeks secara umum terlalu mahal, Lynch akan menyarankan rotasi portofolio dengan melepas saham-saham high-flyer yang sudah jenuh (stalwarts) dan bersembunyi di sektor utilitas atau defensif."
        else:
            base += "Valuasi pasar berada pada level pertumbuhan yang sepadan dengan harganya (PEG Ratio ~ 1.0 hingga 1.5). Dalam situasi ini, Lynch tidak akan terpaku pada indeks secara keseluruhan, melainkan turun langsung ke lapangan (bottom-up analysis). Ia akan mencari saham lapis kedua atau perusahaan menengah (mid-caps) yang masih luput dari pantauan institusi raksasa Wall Street namun memiliki katalis pertumbuhan bisnis yang nyata."

    elif "Simons" in name:
        base = "Jim Simons (Renaissance Technologies) adalah pelopor investasi kuantitatif (Quant) yang menghilangkan emosi manusia dari perdagangan. Algoritmanya bekerja dengan mencari pola matematika tersembunyi dari pergerakan harga historis dan volume. "
        if verdict == "bullish":
            base += "Sinyal kuantitatif murni menunjukkan konfirmasi tren naik (uptrend) yang valid. Indikator momentum (seperti RSI) berada di zona ekspansi tanpa mencapai overbought ekstrem, dan Moving Averages (misal SMA 50 > SMA 200) membentuk 'Golden Cross'. Algoritma tren-following akan mengidentifikasi ini sebagai 'High Probability Setup' dan secara sistematis menambah bobot kepemilikan (scaling in) tanpa keraguan emosional."
        elif verdict == "bearish":
            base += "Berdasarkan pemrosesan sinyal, harga telah menembus support kunci ke bawah (breakdown), didorong oleh momentum negatif yang kuat. Pola 'Death Cross' (SMA 50 memotong SMA 200 ke bawah) mendikte sistem algoritmik untuk beralih ke mode 'Risk-Off'. Model Simons secara otomatis akan memicu instruksi jual, memangkas bobot portofolio saham, atau mengeksekusi strategi short-selling untuk mengambil untung dari penurunan volatilitas."
        else:
            base += "Data statistik menunjukkan kondisi pasar 'Choppy' atau 'Whipsaw' (tanpa tren yang jelas). Volatilitas tanpa arah yang pasti ini sering kali memicu sinyal palsu (false breakouts) yang membakar modal investor ritel. Dalam skema kuantitatif, parameter risk/reward tidak memenuhi syarat untuk mengambil posisi agresif. Algoritma akan mengurangi frekuensi trading secara drastis (mean-reversion mode) hingga arah tren terkonfirmasi kembali secara matematis."

    else:
        base = reasoning

    return base + "\n\n=== Kondisi Terkini ===\n" + reasoning


def run_all_legends(data: dict) -> list:
    """Run all legend analyses based on compiled data."""
    legends = []

    market = data.get("market", {})
    macro = data.get("macro", {})
    indonesia = data.get("indonesia", {})
    technicals = data.get("technicals", {})
    sentiment = data.get("mentor_sentiment", {})

    # 1. Buffett & Graham
    legends.append(analyze_buffett_graham(
        ihsg_per=indonesia.get("ihsg_per", 14.0),
        mentor_sentiment_label=sentiment.get("label", "Neutral"),
        ihsg_earnings_growth=indonesia.get("ihsg_earnings_growth", 8.0),
        bi_rate=indonesia.get("bi_rate", 5.75),
    ))

    # 2. Soros
    legends.append(analyze_soros(
        dxy_price=market.get("DXY", {}).get("price"),
        usdidr_price=market.get("USDIDR", {}).get("price"),
        ihsg_price=market.get("IHSG", {}).get("price"),
        ihsg_trend=market.get("IHSG", {}).get("trend", "sideways"),
        sp500_trend=market.get("SP500", {}).get("trend", "sideways"),
    ))

    # 3. Dalio
    legends.append(analyze_dalio(
        inflation_id=indonesia.get("inflation", 2.5),
        bi_rate=indonesia.get("bi_rate", 5.75),
        fed_rate=macro.get("fed_funds_rate", 5.25),
        us_gdp_growth=macro.get("us_gdp_growth", 2.0),
        us_cpi_yoy=macro.get("us_cpi_yoy", 3.0),
    ))

    # 4. Lynch
    legends.append(analyze_lynch(
        ihsg_per=indonesia.get("ihsg_per", 14.0),
        earnings_growth=indonesia.get("ihsg_earnings_growth", 8.0),
        ihsg_trend=technicals.get("ihsg_trend", "sideways"),
    ))

    # 5. Simons
    legends.append(analyze_simons(
        rsi=technicals.get("ihsg_rsi_14"),
        sma_cross=technicals.get("ihsg_sma_cross"),
        ihsg_trend=technicals.get("ihsg_trend", "sideways"),
        sma_50=technicals.get("ihsg_sma_50"),
        sma_200=technicals.get("ihsg_sma_200"),
        ihsg_price=technicals.get("ihsg_price"),
    ))

    for legend in legends:
        if "full_explanation" not in legend:
            legend["full_explanation"] = _generate_textbook_explanation(legend)

    return legends


if __name__ == "__main__":
    sample_data = {
        "market": {
            "IHSG": {"price": 7200, "trend": "uptrend"},
            "SP500": {"trend": "uptrend"},
            "DXY": {"price": 103.5},
            "USDIDR": {"price": 15800},
        },
        "macro": {
            "fed_funds_rate": 5.25,
            "us_gdp_growth": 2.8,
            "us_cpi_yoy": 3.2,
        },
        "indonesia": {
            "bi_rate": 5.75,
            "inflation": 2.5,
            "ihsg_per": 14.0,
            "ihsg_earnings_growth": 8.0,
        },
        "technicals": {
            "ihsg_rsi_14": 55,
            "ihsg_sma_cross": "golden_cross",
            "ihsg_trend": "uptrend",
            "ihsg_sma_50": 7100,
            "ihsg_sma_200": 6900,
            "ihsg_price": 7200,
        },
        "mentor_sentiment": {
            "score": 0.5,
            "label": "Bullish",
        },
    }

    legends = run_all_legends(sample_data)
    for legend in legends:
        print(f"\n{'='*60}")
        print(f"{legend['legend']} ({legend['philosophy']})")
        print(f"Verdict: {legend['verdict'].upper()}")
        print(f"Confidence: {legend['confidence']}")
        print(f"Reasoning: {legend['reasoning']}")
