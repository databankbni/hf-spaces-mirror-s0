import sys
sys.stdout.reconfigure(encoding='utf-8')

def analyze_revalue(bi_rate: float, inflation_id: float, ihsg_trend: str, 
                    ihsg_per: float, us_cpi_yoy: float) -> dict:
    """
    Revalue Academy Analysis:
    - Market Cycle Phases (Contraction, Recovery, Expansion, Slowdown)
    - Sectoral Rotation based on the cycle
    - Reflexivity & Psychology
    - Valuation Context (Cyclicals get PE discounts)
    """
    confidence = 0.5
    reasons = []
    verdict = "neutral"
    
    # 1. Menentukan Fase Siklus Makro (4 Phases of Market Cycle)
    # Logika sederhana berdasarkan Suku Bunga dan Inflasi (sesuai Modul 18)
    # Asumsi:
    # - Suku bunga turun & inflasi turun -> Recovery
    # - Suku bunga stabil rendah & inflasi naik perlahan -> Expansion
    # - Suku bunga tinggi & inflasi tinggi/melandai -> Slowdown
    # - Suku bunga ditahan tinggi & inflasi turun tajam (resesi) -> Contraction
    
    phase = "Unknown"
    recommended_sectors = []
    
    if bi_rate >= 6.0 and inflation_id >= 3.0:
        phase = "Slowdown"
        verdict = "bearish"
        confidence += 0.2
        recommended_sectors = ["Consumer Non-Cyclicals", "Health Care", "Defensives"]
        reasons.append(
            f"Fase SLOWDOWN: Suku bunga BI tinggi ({bi_rate}%) dan inflasi bertahan ({inflation_id}%). "
            "Revalue Academy memperingatkan perlambatan daya beli dan ekspansi bisnis yang tertahan. "
            "Investor umumnya mulai FOMO padahal valuasi memahalkan (overvalued)."
        )
    elif bi_rate < 6.0 and inflation_id < 3.0 and ihsg_trend == "uptrend":
        phase = "Recovery"
        verdict = "bullish"
        confidence += 0.3
        recommended_sectors = ["Basic Materials", "Consumer Cyclicals", "Industrials"]
        reasons.append(
            f"Fase RECOVERY: Era suku bunga terkendali ({bi_rate}%) dan inflasi stabil ({inflation_id}%). "
            "Ini adalah momen terbaik mengoleksi saham siklikal karena laba emiten mulai bertumbuh kembali (turnaround)."
        )
    elif bi_rate < 6.0 and ihsg_trend == "uptrend":
        phase = "Expansion"
        verdict = "bullish"
        confidence += 0.2
        recommended_sectors = ["Financials", "Property", "Infrastruktur"]
        reasons.append(
            f"Fase EXPANSION: Ekonomi sedang panas-panasnya. "
            "Revalue mengingatkan bahwa 'Every good thing must come to an end', namun tren masih kuat. "
            "Fokus pada saham dengan Growth (PEG) atraktif."
        )
    elif bi_rate >= 6.0 and ihsg_trend == "downtrend":
        phase = "Contraction"
        verdict = "bearish"
        confidence += 0.3
        recommended_sectors = ["Cash", "Bonds", "Emas"]
        reasons.append(
            "Fase CONTRACTION (Krisis): Pasar dilanda ketakutan yang real (Refleksivitas Soros). "
            "Revalue Academy mengajarkan ini adalah waktu memegang cash atau mencari saham yang harganya overly cheap."
        )
    else:
        phase = "Transisi"
        verdict = "neutral"
        recommended_sectors = ["Selektif / Stock Picking"]
        reasons.append(
            "Fase TRANSISI: Siklus tidak menunjukkan arah yang ekstrem. "
            "Terapkan pendekatan Bottom-Up untuk valuasi SOTP atau RNAV pada saham spesifik."
        )

    # 2. Penilaian Valuasi Sektoral (Modul 12 & 19)
    if phase in ["Recovery", "Expansion"]:
        reasons.append(
            f"Rotasi Sektoral: Alihkan bobot portofolio ke {', '.join(recommended_sectors)}. "
            "Perhatian: Untuk emiten tambang/siklikal, berikan diskon P/E (jangan bayar mahal saat laba pucuk)."
        )
    elif phase in ["Slowdown", "Contraction"]:
        reasons.append(
            f"Rotasi Sektoral: Bertahan di sektor defensif seperti {', '.join(recommended_sectors)}. "
            "Waspadai jebakan valuasi (Value Trap) pada emiten yang tampaknya murah tapi labanya akan tergerus."
        )

    # 3. Teori Refleksivitas (Modul 18)
    if verdict == "bearish" and ihsg_trend == "uptrend":
        reasons.append(
            "Peringatan Refleksivitas: IHSG masih naik secara irasional meski makro mendukung pelemahan. "
            "Waspadai 'Bubble Forming' yang berpotensi meletus."
        )

    confidence = min(confidence, 1.0)
    
    # Generate full explanation
    base_explanation = (
        "Revalue Academy memadukan analisis Makroekonomi (4 Fase Siklus Pasar), "
        "Rotasi Sektoral, dan Valuasi spesifik (misalnya P/E discount untuk siklikal). "
        "Fokus utama mereka adalah menavigasi ombak 'Business Cycle' agar investor "
        "tahu kapan harus agresif dan kapan harus defensif. "
    )

    full_explanation = base_explanation + "\n\n=== Kondisi Terkini ===\n" + " ".join(reasons)

    return {
        "legend": "Revalue Academy",
        "philosophy": "Macro Cycle & Sectoral Rotation",
        "verdict": verdict,
        "confidence": round(confidence, 2),
        "reasoning": " ".join(reasons),
        "phase": phase,
        "full_explanation": full_explanation,
        "icon": "revalue", # custom icon logic in frontend
    }
