def match_historical_pattern(raw_data: dict, macro_score: float) -> dict:
    """
    Mencari pola krisis/reli masa lalu yang paling mirip dengan kondisi makro saat ini
    menggunakan perhitungan jarak Euclidean (Euclidean distance).
    """
    try:
        current_usdidr = raw_data.get('market', {}).get('USDIDR', {}).get('price', 15000)
        current_dxy = raw_data.get('market', {}).get('DXY', {}).get('price', 100)
        current_oil = raw_data.get('market', {}).get('CRUDE_OIL', {}).get('price', 70)
        current_bi_rate = raw_data.get('indonesia', {}).get('bi_rate', 6.0)
        current_fed_rate = raw_data.get('macro', {}).get('fed_funds_rate', 5.0)
        current_inflation = raw_data.get('indonesia', {}).get('inflation', 2.5)
        current_gdp = raw_data.get('indonesia', {}).get('gdp_growth', 5.0)
        current_trade = raw_data.get('indonesia', {}).get('trade_balance', 3.0)
        
        events = [
            {
                "name": "1999: Rebound Pre-Dotcom Bubble",
                "vec": {"usdidr": 7500, "bi_rate": 12.5, "inflation": 2.0, "gdp": 0.8, "trade": 2.5, "fed_rate": 5.5, "dxy": 100, "oil": 25},
                "ihsg_impact": 0.10,
                "desc": {
                    "usdidr": "Rupiah mulai pulih dari Krismon (Rp 7.000-an)",
                    "bi_rate": "Bunga super tinggi (12%) redam inflasi",
                    "fed_rate": "The Fed menahan bunga cukup tinggi (5.5%)",
                    "dxy": "Dolar Index relatif stabil (100)",
                    "oil": "Minyak sangat murah ($25/bbl)"
                },
                "what_happened": "Pemulihan dari Krisis Moneter 1998. Rupiah menguat signifikan dari belasan ribu ke 7.000-an. Suku bunga BI masih sangat tinggi untuk menstabilkan nilai tukar, namun optimisme mulai bangkit seiring meledaknya 'Dotcom Bubble' di AS.",
                "rebound_info": "IHSG melesat pelan namun pasti dari titik terendahnya, memulai siklus Bull Market baru.",
                "action_strategy": "ENTRY: Akumulasi saat suku bunga BI mulai dipotong dari pucuk. EXIT: Ketika valuasi sektor teknologi di AS mulai tidak masuk akal. SAAT INI: Cicil beli bluechip perbankan, waspadai bubble AI global pecah."
            },
            {
                "name": "2006-2007: Era Komoditas Pre-Subprime",
                "vec": {"usdidr": 9000, "bi_rate": 8.0, "inflation": 6.5, "gdp": 6.3, "trade": 3.5, "fed_rate": 5.25, "dxy": 80, "oil": 90},
                "ihsg_impact": 0.35,
                "desc": {
                    "usdidr": "Rupiah kuat (Rp 9.000) ditopang ekspor",
                    "bi_rate": "Suku bunga normal (8%) memacu kredit",
                    "fed_rate": "The Fed mulai menahan bunga tinggi (5.25%)",
                    "dxy": "Dolar AS melemah (80), memicu *commodity boom*",
                    "oil": "Harga minyak terbang menyentuh rekor tinggi"
                },
                "what_happened": "Supercycle Komoditas! Dolar AS (DXY) anjlok dan harga minyak serta batu bara terbang. Ekonomi Indonesia melaju kencang dengan pertumbuhan di atas 6%. IHSG mencetak rekor tertinggi berturut-turut didorong sektor energi dan perbankan.",
                "rebound_info": "Bull market terkuat dalam sejarah IHSG sebelum dihancurkan oleh krisis 2008.",
                "action_strategy": "ENTRY: Harga komoditas breakout & Dolar AS breakdown. EXIT: Suku bunga The Fed mencapai puncak dan kurva yield terbalik. SAAT INI: All-in sektor energi/tambang jika DXY tren turun, exit saat BI Rate menyusul The Fed."
            },
            {
                "name": "2009-2013: QE Era & Pre-Taper Tantrum",
                "vec": {"usdidr": 9500, "bi_rate": 5.75, "inflation": 4.3, "gdp": 6.2, "trade": 0.5, "fed_rate": 0.25, "dxy": 80, "oil": 100},
                "ihsg_impact": 0.25,
                "desc": {
                    "usdidr": "Rupiah sangat perkasa (< Rp 10.000)",
                    "bi_rate": "Bunga BI rendah (5.75%), ekonomi 'Goldilocks'",
                    "fed_rate": "The Fed potong bunga ke 0% (ZIRP) & cetak uang",
                    "dxy": "Dolar tertekan di dasar (80)",
                    "oil": "Minyak bertahan di level >$100 membebani CAD"
                },
                "what_happened": "The Fed mencetak uang tak terbatas (Quantitative Easing) dan menurunkan suku bunga hingga 0%. Uang murah ini mengalir membanjiri Emerging Markets. IHSG mengalami reli panjang tak terhentikan berkat banjir likuiditas global.",
                "rebound_info": "Fase Goldilocks bagi IHSG. Buy and Hold adalah strategi terbaik di era ini.",
                "action_strategy": "ENTRY: Likuiditas banjir, asing net buy beruntun. EXIT: Isu penghentian QE (Tapering). SAAT INI: Beli dan tahan saham fundamental kuat. Bersiap buang barang jika The Fed beri sinyal hawkish ekstrem."
            },
            {
                "name": "2017: Bull Market & Tax Amnesty",
                "vec": {"usdidr": 13300, "bi_rate": 4.25, "inflation": 3.6, "gdp": 5.1, "trade": 1.0, "fed_rate": 1.5, "dxy": 92, "oil": 60},
                "ihsg_impact": 0.12,
                "desc": {
                    "usdidr": "Rupiah sangat stabil (Rp 13.300)",
                    "bi_rate": "Pelonggaran agresif BI, bunga turun",
                    "fed_rate": "The Fed perlahan naikkan bunga bertahap",
                    "dxy": "Dolar Index melunak tanpa gejolak (92)",
                    "oil": "Harga energi moderat dan kondusif ($50/bbl)"
                },
                "what_happened": "Stabilitas makro yang luar biasa. Inflasi rendah, nilai tukar stabil, dan suksesnya program Tax Amnesty memicu sentimen super positif. Asing terus memborong saham bluechip.",
                "rebound_info": "IHSG terus mencetak All-Time High hampir setiap bulan tanpa gejolak berarti.",
                "action_strategy": "ENTRY: Stabilitas politik dan rupiah kuat. EXIT: Valuasi IHSG (P/E) tembus +2 Standard Deviasi. SAAT INI: Fokus saham Big Banks dan infrastruktur. Jual bertahap jika arus asing mulai melambat."
            },
            {
                "name": "2020-2021: Rebound Covid-19 (ZIRP)",
                "vec": {"usdidr": 14200, "bi_rate": 3.5, "inflation": 1.8, "gdp": 3.7, "trade": 3.0, "fed_rate": 0.25, "dxy": 90, "oil": 75},
                "ihsg_impact": 0.15,
                "desc": {
                    "usdidr": "Rupiah pulih pasca kepanikan awal pandemi",
                    "bi_rate": "BI potong bunga ke titik terendah (3.5%)",
                    "fed_rate": "Bunga 0% & Injeksi stimulus The Fed triliunan dolar",
                    "dxy": "Dolar anjlok memicu 'Everything Bubble'",
                    "oil": "Pemulihan bertahap aktivitas pasca lockdown"
                },
                "what_happened": "Respon The Fed terhadap pandemi sangat agresif. Suku bunga 0% dan stimulus triliunan dolar memicu 'Everything Bubble'. IHSG melesat dari dasar jurang Covid didorong oleh ledakan investor ritel (Angkatan Corona) dan fenomena saham bank digital.",
                "rebound_info": "SUPER V-SHAPE: IHSG melesat +70% hanya dalam waktu 11 bulan.",
                "action_strategy": "ENTRY: Panic selling mereda, stimulus bank sentral cair. EXIT: Inflasi mulai meroket tak terkendali. SAAT INI: Rotasi dari defensif ke growth/tech. Exit saat inflasi di luar batas toleransi BI."
            },
            {
                "name": "Des 2025 - Jan 2026: ATH Terbaru (Extreme Bullish)",
                "vec": {"usdidr": 16800, "bi_rate": 4.5, "inflation": 2.5, "gdp": 5.5, "trade": 4.0, "fed_rate": 3.0, "dxy": 95, "oil": 70},
                "ihsg_impact": 0.15,
                "data_verified": False,
                "verification_note": "Angka dalam skenario ini (Fed 3.0%, DXY 95, dll) adalah proyeksi hipotetis yang belum diverifikasi terhadap data resmi BI/The Fed. Gunakan sebagai skenario optimis, bukan anchor historis.",
                "desc": {
                    "usdidr": "Rupiah terapresiasi kuat pasca pemotongan bunga",
                    "bi_rate": "Pelonggaran moneter masif BI (4.5%)",
                    "fed_rate": "Soft Landing berhasil & Bunga Fed turun tajam",
                    "dxy": "Pelemahan struktural Dolar AS",
                    "oil": "Minyak stabil tanpa syok pasokan"
                },
                "what_happened": "Kondisi 'Utopia' makro. The Fed kembali memangkas suku bunga dengan agresif (Soft Landing tercapai), Dolar melemah, dan aliran dana asing (Capital Inflow) masuk masif ke Asia. IHSG menembus rekor tertingginya sepanjang masa berkat valuasi yang murah dan dividen jumbo.",
                "rebound_info": "IHSG mencetak sejarah baru, didorong oleh rotasi dana dari pasar AS yang sudah kemahalan ke Emerging Markets.",
                "action_strategy": "ENTRY: Soft landing terkonfirmasi, Fed pangkas bunga agresif. EXIT: Euforia berlebihan (IHSG overbought bulanan). SAAT INI: Ride the trend. Tetap hold selama asing inflow. Waspadai Black Swan."
            },
            {
                "name": "2000-2001: Dotcom Bubble Crash",
                "vec": {"usdidr": 10500, "bi_rate": 14.0, "inflation": 9.3, "gdp": 3.6, "trade": 2.0, "fed_rate": 6.5, "dxy": 115, "oil": 28},
                "ihsg_impact": -0.30,
                "desc": {
                    "usdidr": "Rupiah tertekan gejolak transisi politik",
                    "bi_rate": "BI rate meroket (14%) bendung inflasi",
                    "fed_rate": "Pengetatan ekstrem The Fed pecahkan 'Bubble' IT",
                    "dxy": "Dolar Index terbang (118) menyedot likuiditas dunia",
                    "oil": "Harga minyak sangat murah ($30/bbl)"
                },
                "what_happened": "Gelembung saham-saham teknologi (Dotcom) di AS pecah. Runtuhnya Nasdaq menyeret bursa global. Ditambah suku bunga yang masih sangat tinggi, pasar saham kehilangan gairahnya dan memasuki Bear Market berkepanjangan.",
                "rebound_info": "Butuh waktu bertahun-tahun bagi bursa global untuk pulih ke level sebelum crash.",
                "action_strategy": "ENTRY: Tunggu kebangkrutan emiten beruntun mereda. EXIT: Saham tak berfundamental naik ribuan persen. SAAT INI: Jauhi saham 'gorengan' tech/AI overvalued. Lindung nilai di emas/deposito."
            },
            {
                "name": "2008: Krisis Finansial Global (Subprime)",
                "vec": {"usdidr": 11000, "bi_rate": 9.5, "inflation": 11.0, "gdp": 6.0, "trade": 0.8, "fed_rate": 2.0, "dxy": 85, "oil": 140},
                "ihsg_impact": -0.50,
                "desc": {
                    "usdidr": "Kepanikan global jatuhkan Rupiah (Rp 12.000)",
                    "bi_rate": "Bunga tinggi akibat hiperinflasi energi (9.5%)",
                    "fed_rate": "Kepanikan Lehman Brothers memaksa Fed cut rate",
                    "dxy": "Volatilitas ekstrem akibat kepanikan finansial",
                    "oil": "Minyak capai >$140 merusak inflasi global"
                },
                "what_happened": "Bermula dari pecahnya gelembung kredit perumahan (Subprime Mortgage) di AS. Kepanikan global terjadi (Credit Crunch). Asing mencabut dananya. IHSG terpaksa disuspensi setelah ambruk tajam hingga -50%.",
                "rebound_info": "V-SHAPE RECOVERY: Kesempatan beli seumur hidup (generational wealth opportunity).",
                "action_strategy": "ENTRY: Terjadi likuidasi paksa massal & intervensi bail-out. EXIT: Krisis kredit meluas mematikan sektor riil. SAAT INI: Cash is King. Siapkan amunisi 'Buy The Blood' di bluechip diskon 50%."
            },
            {
                "name": "2013: Taper Tantrum Shock",
                "vec": {"usdidr": 12000, "bi_rate": 7.5, "inflation": 8.4, "gdp": 5.6, "trade": -0.5, "fed_rate": 0.25, "dxy": 80, "oil": 105},
                "ihsg_impact": -0.15,
                "desc": {
                    "usdidr": "Depresiasi kilat Rupiah karena Outflow",
                    "bi_rate": "Kenaikan drastis (5.75% ke 7.5%) tahan arus modal keluar",
                    "fed_rate": "Sinyal penghentian QE (Tapering) dari The Fed",
                    "dxy": "Awal mula Dolar kembali menguat dari dasar",
                    "oil": "Minyak tinggi yang membebani defisit neraca dagang"
                },
                "what_happened": "The Fed mengisyaratkan akan mengurangi stimulus (Tapering). Kepanikan melanda Emerging Markets. Rupiah terpuruk dari Rp9.700 menuju Rp12.000, memaksa BI menaikkan suku bunga secara agresif. Dana asing keluar deras dari IHSG.",
                "rebound_info": "STRONG REBOUND: IHSG berhasil pulih mantap +30% dalam 10 bulan setelah pasar menyadari ekonomi RI masih solid.",
                "action_strategy": "ENTRY: BI rate memuncak dan asing berhenti jualan. EXIT: Rupiah terdepresiasi tak wajar mendadak (>1% per hari). SAAT INI: Jauhi bank kecil & properti. Tunggu BI naikan rate agresif, lalu serok bawah."
            },
            {
                "name": "2018-2019: Trade War & Fed Hiking",
                "vec": {"usdidr": 15200, "bi_rate": 6.0, "inflation": 3.1, "gdp": 5.2, "trade": -0.7, "fed_rate": 2.5, "dxy": 97, "oil": 70},
                "ihsg_impact": -0.10,
                "desc": {
                    "usdidr": "Rupiah tertekan The Fed menembus Rp 15.000",
                    "bi_rate": "Kenaikan moderat (6.0%) menahan gejolak",
                    "fed_rate": "Siklus kenaikan bunga agresif mencapai puncak",
                    "dxy": "Flight to safety ke Dolar karena Trade War",
                    "oil": "Tekanan manufaktur global menahan laju energi"
                },
                "what_happened": "Perang dagang AS-China dan kampanye kenaikan suku bunga The Fed (Quantitative Tightening) memicu sentimen Risk-Off. Dolar AS menguat, dan likuiditas mengering, menyebabkan IHSG bergerak volatile dan sideways cenderung turun.",
                "rebound_info": "Pasar menunggu kepastian kesepakatan dagang dan pelonggaran moneter sebelum berani masuk kembali.",
                "action_strategy": "ENTRY: Negosiasi tarif menemui titik terang/damai. EXIT: Retorika perang dagang memanas di media global. SAAT INI: Rotasi ke saham defensif (consumer/telco) yang tahan banting goncangan luar negeri."
            },
            {
                "name": "Maret 2020: Covid-19 Crash",
                "vec": {"usdidr": 16500, "bi_rate": 4.5, "inflation": 2.9, "gdp": 2.9, "trade": 0.7, "fed_rate": 1.0, "dxy": 100, "oil": 20},
                "ihsg_impact": -0.38,
                "desc": {
                    "usdidr": "Panic buying USD menyentuh rekor Rp 16.500",
                    "bi_rate": "Pemangkasan darurat untuk mencegah keruntuhan",
                    "fed_rate": "Pemotongan darurat 100 bps merespon pandemi",
                    "dxy": "Lonjakan 'cash is king' Dolar seiring crash pasar",
                    "oil": "Kontrak minyak hancur lebur (<$20/bbl)"
                },
                "what_happened": "Kepanikan luar biasa akibat Lockdown global. IHSG jatuh terkilat sepanjang sejarah, anjlok -37% hanya dalam waktu kurang dari sebulan, memicu Trading Halt berulang kali. Harga minyak dunia hancur lebur.",
                "rebound_info": "Kepanikan irasional, saham bluechip dijual di harga diskon tidak masuk akal sebelum akhirnya V-Shape rebound.",
                "action_strategy": "ENTRY: Trading halt berjilid-jilid reda & kepanikan puncak. EXIT: Tanda awal aktivitas masyarakat mati total. SAAT INI: Panic selling massal adalah peluang. Serok bertahap saat valuasi P/B Bluechip jatuh -2SD."
            }
        ]

        # ---------------------------------------------------------------
        # Normalisasi -- diganti dari min-max dengan batas hardcoded
        # (mis. USDIDR 6000-18000) menjadi z-score memakai mean/std dari
        # SEBARAN 10 event historis itu sendiri. Ini konsisten dengan
        # prinsip yang dipakai backtest_engine.py (semua komponen komposit
        # di-z-score sebelum digabung, supaya tidak ada variabel yang
        # mendominasi jarak hanya karena rentang mentahnya lebih besar).
        # Batas hardcoded sebelumnya arbitrary (tidak mencerminkan sebaran
        # data historis sebenarnya) dan berbeda skema dari backtest_engine.py
        # -- sekarang dua bagian sistem memakai pendekatan yang sama.
        # ---------------------------------------------------------------
        var_keys = ["usdidr", "bi_rate", "inflation", "gdp", "trade", "fed_rate", "dxy", "oil"]
        vecs_by_key = {k: [e["vec"][k] for e in events] for k in var_keys}
        stats_by_key = {}
        for k in var_keys:
            arr = vecs_by_key[k]
            mean = sum(arr) / len(arr)
            var = sum((x - mean) ** 2 for x in arr) / len(arr)
            std = var ** 0.5
            stats_by_key[k] = (mean, std if std > 0 else 1.0)

        def zscore(val, key):
            if val is None:
                return 0.0  # netral (rata-rata historis) kalau data hilang
            mean, std = stats_by_key[key]
            return (val - mean) / std

        current_vals = {
            "usdidr": current_usdidr, "bi_rate": current_bi_rate, "inflation": current_inflation, "gdp": current_gdp, "trade": current_trade,
            "fed_rate": current_fed_rate, "dxy": current_dxy, "oil": current_oil,
        }

        # Bobot di bawah ini TETAP heuristik berbasis penalaran domain
        # (USDIDR & BI Rate diberi bobot lebih besar karena keduanya proksi
        # stres pasar EM yang paling relevan untuk Indonesia secara
        # spesifik), BUKAN hasil fitting/optimisasi terhadap data historis.
        # Ini caveat yang sama seperti guardrail #5 di backtest_engine.py:
        # tidak ada pencarian kombinasi bobot yang dicoba-coba di sini.
        weights = {"usdidr": 2.0, "bi_rate": 1.5, "inflation": 1.0, "gdp": 1.0, "trade": 1.0, "fed_rate": 1.5, "dxy": 1.0, "oil": 0.5}

        def squared_distance(vec_a: dict, vec_b: dict) -> float:
            return sum(
                weights[k] * (zscore(vec_a[k], k) - zscore(vec_b[k], k)) ** 2
                for k in var_keys
            )

        best_match = None
        best_distance = float("inf")
        for event in events:
            dist = squared_distance(current_vals, event["vec"])
            if dist < best_distance:
                best_distance = dist
                best_match = event

        # ---------------------------------------------------------------
        # Similarity -- diganti dari "99 - dist*400" (konstanta 400 tidak
        # punya justifikasi apapun) menjadi kernel eksponensial yang
        # dikalibrasi dari SKALA JARAK ANTAR-EVENT HISTORIS ITU SENDIRI
        # (median pairwise distance di antara 10 event). Interpretasinya
        # eksplisit: "seberapa dekat kondisi saat ini dibanding seberapa
        # jauh biasanya dua episode historis berbeda satu sama lain" --
        # bukan angka presisi yang seolah dikalibrasi ke probabilitas nyata.
        # ---------------------------------------------------------------
        pairwise = [
            squared_distance(events[i]["vec"], events[j]["vec"])
            for i in range(len(events))
            for j in range(i + 1, len(events))
        ]
        pairwise_sorted = sorted(pairwise)
        n = len(pairwise_sorted)
        median_pairwise = (
            pairwise_sorted[n // 2] if n % 2 == 1
            else (pairwise_sorted[n // 2 - 1] + pairwise_sorted[n // 2]) / 2
        ) if n > 0 else 1.0
        scale = median_pairwise if median_pairwise > 0 else 1.0

        import math
        similarity = int(round(max(1, min(99, 100 * math.exp(-best_distance / scale)))))

        matching_indicators = [
            {"name": "Nilai Tukar Rupiah", "current": f"Rp {current_usdidr:,.0f}", "historical": best_match['desc']['usdidr']},
            {"name": "Inflasi RI", "current": f"{current_inflation}%", "historical": f"Berdasarkan dataset historis"}, 
            {"name": "PDB (GDP)", "current": f"{current_gdp}%", "historical": f"Berdasarkan dataset historis"}, 
            {"name": "Neraca Dagang", "current": f"${current_trade}B", "historical": f"Berdasarkan dataset historis"},
            {"name": "Suku Bunga BI", "current": f"{current_bi_rate}%", "historical": best_match['desc']['bi_rate']},
            {"name": "Suku Bunga The Fed", "current": f"{current_fed_rate}%", "historical": best_match['desc']['fed_rate']},
            {"name": "Indeks Dolar (DXY)", "current": f"{current_dxy:,.1f}", "historical": best_match['desc']['dxy']},
            {"name": "Harga Minyak WTI", "current": f"${current_oil:,.1f}", "historical": best_match['desc']['oil']}
        ]

        return {
            "matched": True,
            "event_name": best_match["name"],
            "similarity": similarity,
            "similarity_method": (
                "Jarak Euclidean berbobot pada variabel yang di-z-score dari sebaran "
                "10 event historis, dikonversi ke similarity via kernel eksponensial "
                "dikalibrasi dari median jarak antar-event historis itu sendiri."
            ),
            "what_happened": best_match["what_happened"],
            "implication": "Sejarah tidak mengulang dirinya secara persis, namun ia sering kali berima. Posisikan portofolio Anda sesuai dengan probabilitas skenario di atas.",
            "disclaimer": (
                "Pencocokan pola ini berbasis n=10 episode historis yang dipilih manual "
                "-- bukan hasil uji statistik dan tidak boleh dibaca sebagai probabilitas "
                "yang terkalibrasi. Perlakukan sebagai konteks naratif, bukan sinyal kuantitatif."
            ),
            "matching_indicators": matching_indicators,
            "rebound_info": best_match.get("rebound_info", ""),
            "action_strategy": best_match.get("action_strategy", ""),
            "ihsg_impact": best_match.get("ihsg_impact", 0),
            "data_verified": best_match.get("data_verified", True),
            "verification_note": best_match.get("verification_note", None)
        }
    except Exception as e:
        print(f"[Pattern Matcher] Error: {e}")
        return {"matched": False, "error": str(e)}
