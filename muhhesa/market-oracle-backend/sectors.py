def calculate_sectors_and_picks(macro_scores):
    """
    Menghitung skor sektoral dan merekomendasikan saham (Top Picks) 
    berdasarkan kondisi makro saat ini.
    """
    # Menggunakan MacroStateVector sebagai Single Source of Truth
    state_vector = macro_scores.get("macro_state_vector", {})
    
    bi_rate_z = state_vector.get("bi_fed_spread_score", 0) # Fallback using spread score if individual z-scores for rate don't exist
    usdidr_z = state_vector.get("usdidr_score", 0)
    commodities_z = state_vector.get("commodities_score", 0)
    gdp_z = state_vector.get("gdp_growth_id_score", 0)
    inflation_z = state_vector.get("inflation_id_score", 0)
    
    # We use proxy rates derived from spread score for property and tech since we no longer score them individually
    bi_rate_proxy = -bi_rate_z
    fed_rate_proxy = -bi_rate_z * 0.5
    
    # Kalkulasi korelasi Sektor terhadap kondisi makro
    # Menggunakan bobot yang selaras dengan narasi makro:
    raw_sectors = {
        "Financials": (bi_rate_proxy * 1.5) + (gdp_z * 1.0) + (usdidr_z * 0.5),
        "Energy": (commodities_z * 2.0) - (usdidr_z * 0.5), # Rupiah lemah (usdidr negatif) sedikit menguntungkan ekspor
        "Consumer": (usdidr_z * 1.5) + (inflation_z * 1.0) + (gdp_z * 0.5), # Rupiah kuat dan inflasi rendah bagus
        "Property": (bi_rate_proxy * 2.0) + (fed_rate_proxy * 0.5), # Sangat sensitif terhadap suku bunga
        "Technology": (fed_rate_proxy * 1.5) + (bi_rate_proxy * 1.0), # Sensitif suku bunga global & lokal
        "Basic Materials": (commodities_z * 1.5) + (gdp_z * 1.0),
    }
    
    # Kumpulan saham bluechip / terbaik per sektor
    stock_pool = {
        "Financials": [
            {"ticker": "BBCA", "name": "BCA", "reason": "Suku bunga stabil/rendah menjaga kualitas kredit dan NIM."},
            {"ticker": "BMRI", "name": "Bank Mandiri", "reason": "Pertumbuhan ekonomi solid mendorong kredit korporasi."},
            {"ticker": "BBRI", "name": "BRI", "reason": "Ekonomi makro mendukung pertumbuhan segmen mikro."}
        ],
        "Energy": [
            {"ticker": "ADRO", "name": "Adaro Energy", "reason": "Harga komoditas energi menguat, dividen yield atraktif."},
            {"ticker": "MEDC", "name": "Medco Energi", "reason": "Diuntungkan dari reli harga minyak WTI."},
            {"ticker": "PTBA", "name": "Bukit Asam", "reason": "Harga komoditas naik menopang laba perseroan."}
        ],
        "Consumer": [
            {"ticker": "ICBP", "name": "Indofood CBP", "reason": "Rupiah kuat menekan biaya impor gandum."},
            {"ticker": "MYOR", "name": "Mayora", "reason": "Inflasi terkendali mendukung daya beli masyarakat."},
            {"ticker": "AMRT", "name": "Alfamart", "reason": "Daya beli konsumen solid berkat makro yang positif."}
        ],
        "Property": [
            {"ticker": "CTRA", "name": "Ciputra", "reason": "Suku bunga BI turun merangsang permintaan KPR."},
            {"ticker": "BSDE", "name": "Bumi Serpong", "reason": "Iklim suku bunga rendah mendukung penjualan properti."}
        ],
        "Technology": [
            {"ticker": "GOTO", "name": "GoTo", "reason": "Suku bunga global turun membawa angin segar ke saham growth/tech."},
            {"ticker": "ARTO", "name": "Bank Jago", "reason": "Likuiditas membaik seiring pemotongan suku bunga acuan."}
        ],
        "Basic Materials": [
            {"ticker": "MDKA", "name": "Merdeka Copper", "reason": "Tren harga emas dan logam mulia sedang naik."},
            {"ticker": "INCO", "name": "Vale Indonesia", "reason": "Diuntungkan dari stabilitas harga komoditas tambang."}
        ]
    }
    
    # Format output sektoral
    sectors_output = []
    top_sectors_names = []
    
    for name, score in raw_sectors.items():
        # Normalisasi ke skala -2 hingga +2 untuk konsistensi
        norm_score = max(-2.0, min(2.0, score / 2.0))
        
        if norm_score >= 1.0:
            sentiment = "Sangat Bullish"
        elif norm_score >= 0.3:
            sentiment = "Bullish"
        elif norm_score >= -0.3:
            sentiment = "Netral"
        elif norm_score >= -1.0:
            sentiment = "Bearish"
        else:
            sentiment = "Sangat Bearish"
            
        sectors_output.append({
            "name": name,
            "score": round(norm_score, 2),
            "sentiment": sentiment
        })
        
    # Sort sector by score descending
    sectors_output.sort(key=lambda x: x["score"], reverse=True)
    
    # Ambil 2 sektor terbaik yang skornya >= 0.3
    best_sectors = [s for s in sectors_output if s["score"] >= 0.3][:2]
    
    top_picks = []
    if best_sectors:
        # Ambil masing-masing 2 saham dari 2 sektor terbaik
        for bs in best_sectors:
            candidates = stock_pool.get(bs["name"], [])
            for c in candidates[:2]:
                top_picks.append({
                    "ticker": c["ticker"],
                    "name": c["name"],
                    "sector": bs["name"],
                    "reason": c["reason"]
                })
    else:
        # Jika tidak ada sektor yang bagus (Bearish market), cari yang paling defensif
        top_picks = [
            {
                "ticker": "CASH", 
                "name": "Money Market/RDPU", 
                "sector": "Defensive", 
                "reason": "Kondisi makro sangat tidak menentu. Simpan dana di instrumen likuid."
            },
            {
                "ticker": "ANTM", 
                "name": "Aneka Tambang", 
                "sector": "Basic Materials", 
                "reason": "Emas biasa menjadi safe-haven saat ekonomi tertekan."
            }
        ]
        
    # Limit max 4 picks
    top_picks = top_picks[:4]
    
    return {
        "heatmap": sectors_output,
        "top_picks": top_picks
    }
