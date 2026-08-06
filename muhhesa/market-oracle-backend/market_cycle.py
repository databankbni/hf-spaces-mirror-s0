import math

def analyze_market_cycle(raw_data: dict, macro_score: float, is_simulated: bool = False, pattern_data: dict = None, force_target_price: float = None, sensitivity_slope: float = 0.075) -> dict:
    """
    Menentukan fase siklus pasar menggunakan 2D Phase-Space Geometry (Trigonometri).
    Fase: Accumulation, Mark-Up, Distribution, Mark-Down.
    """
    try:
        ihsg = raw_data.get('market', {}).get('IHSG', {})
        current_price = ihsg.get('price')
        sma_50 = ihsg.get('sma_50')
        sma_200 = ihsg.get('sma_200')
        
        if not all([current_price, sma_50, sma_200]):
            return {"phase": "Unknown", "description": "Data teknikal tidak lengkap.", "degree": 0}
            
        target_price = current_price
        
        if force_target_price is not None:
            target_price = float(force_target_price)
        elif is_simulated:
            # Jika pola historikal terdeteksi sangat identik, gunakan dampak historisnya!
            if pattern_data and pattern_data.get('matched') and pattern_data.get('similarity', 0) >= 80:
                impact = pattern_data.get('ihsg_impact', 0)
                target_price = sma_200 * (1 + impact)
            else:
                target_price = current_price * (1 + (macro_score * sensitivity_slope))
        
        # 1. Hitung Deviasi Persentase (Posisi Relatif)
        x_pct = (target_price - sma_200) / sma_200 * 100  # Sumbu X: Jarak ke Tren Jangka Panjang
        y_pct = (target_price - sma_50) / sma_50 * 100    # Sumbu Y: Jarak ke Momentum Jangka Menengah
        
        # 2. Hitung Sudut Matematis dengan Invers Tangen (Atan2)
        # Hasilnya adalah radian, kita ubah ke derajat (-180 hingga 180)
        math_degree = math.degrees(math.atan2(y_pct, x_pct))
        
        # 3. Hitung Conviction Score (r) - Jarak Euklides dari Origin
        conviction_score = math.sqrt(x_pct**2 + y_pct**2)
        
        # 4. Transformasi Sudut Matematika ke Sudut UI (Murni Teknikal)
        # Matematika: Q1(45) -> Mark-Up, Q4(-45) -> Dist, Q3(-135) -> Mark-Down, Q2(135) -> Accumulation
        # UI: Mark-Up=180, Dist=270, Mark-Down=360/0, Accumulation=90
        # Rumus pemetaan linear eksak:
        technical_degree = (225 - math_degree) % 360
        if technical_degree == 0:
            technical_degree = 360

        phase = "Unknown"
        description = ""
        
        # Pembagian Fase Berdasarkan Sudut Lingkaran Penuh & Conviction
        noise_threshold = 1.5 # Jika jarak deviasi < 1.5%, dianggap Sideways/Noise
        
        if conviction_score < noise_threshold:
            phase = "Sideways"
            description = "Fase Sideways (Noise). Harga berada sangat dekat dengan MA50 dan MA200, mengindikasikan ketiadaan tren yang solid. Sinyal teknikal tidak reliabel."
        else:
            if technical_degree >= 45 and technical_degree < 135:
                phase = "Accumulation"
                description = "Fase Akumulasi. Tren jangka panjang masih di bawah, namun momentum jangka menengah mulai berbalik positif (Recovery)."
            elif technical_degree >= 135 and technical_degree < 225:
                phase = "Mark-Up"
                description = "Fase Mark-Up (Bullish). Akselerasi kuat dimana harga berada di atas tren makro (MA200) dan mikro (MA50)."
            elif technical_degree >= 225 and technical_degree < 315:
                phase = "Distribution"
                description = "Fase Distribusi. Tren makro masih positif, namun momentum jangka pendek mulai melemah (Deceleration)."
            else:
                phase = "Mark-Down"
                description = "Fase Mark-Down (Bearish Panic). Momentum negatif ekstrem dimana harga tenggelam di bawah MA50 dan MA200."
                
        # Tentukan Macro Regime secara independen
        macro_regime = "Neutral"
        if macro_score >= 0.5:
            macro_regime = "Bullish"
        elif macro_score <= -0.5:
            macro_regime = "Bearish"
            
        if is_simulated:
            description += f" [Simulasi Macro: {macro_score:.2f} ({macro_regime})]"
            
        result = {
            "phase": phase,
            "description": description,
            "technical_degree": round(technical_degree, 2),
            "degree": round(technical_degree, 2), # Keep for backward compatibility with frontend if needed
            "conviction_score": round(conviction_score, 2),
            "macro_regime": macro_regime,
            "sma_50": round(sma_50, 2),
            "sma_200": round(sma_200, 2),
            "current_price": round(current_price, 2),
            "math_metrics": {
                "x_pct": round(x_pct, 2),
                "y_pct": round(y_pct, 2),
                "r": round(conviction_score, 2)
            }
        }
        
        if is_simulated:
            result["target_price"] = round(target_price, 2)
            
        return result
    except Exception as e:
        print(f"[Market Cycle] Error: {e}")
        return {"phase": "Unknown", "description": "Error analyzing cycle.", "degree": 0}
