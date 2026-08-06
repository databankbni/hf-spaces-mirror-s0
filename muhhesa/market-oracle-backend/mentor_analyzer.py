import pandas as pd
from datetime import datetime
from config import MENTOR_SENTIMENT_FILE

def get_mentor_file_age_days() -> int:
    try:
        import os, time
        if os.path.exists(MENTOR_SENTIMENT_FILE):
            mtime = os.path.getmtime(MENTOR_SENTIMENT_FILE)
            return int((time.time() - mtime) / (24 * 3600))
    except:
        pass
    return 0
def get_dynamic_conclusion(mentor_sentiment: str, macro_score: float) -> str:
    """
    Generate a dynamic conclusion based on the mentor's sentiment and current macro score.
    """
    mentor_sent = mentor_sentiment.lower()
    
    # Determine macro condition
    if macro_score >= 1.0:
        macro_desc = "Sangat Bullish (Data makro sangat mendukung pergerakan pasar)"
        macro_dir = "bullish"
    elif macro_score >= 0.3:
        macro_desc = "Bullish (Kondisi makro cenderung positif)"
        macro_dir = "bullish"
    elif macro_score <= -1.0:
        macro_desc = "Sangat Bearish (Risiko makro sedang sangat tinggi)"
        macro_dir = "bearish"
    elif macro_score <= -0.3:
        macro_desc = "Bearish (Kondisi makro sedang penuh tekanan)"
        macro_dir = "bearish"
    else:
        macro_desc = "Netral (Data makro bercampur tanpa arah yang dominan)"
        macro_dir = "neutral"

    # Match mentor's sentiment with macro reality
    if mentor_sent == "bullish":
        if macro_dir == "bullish":
            return f"🌟 Konfirmasi Positif: Opini bullish mentor didukung penuh oleh kondisi makro saat ini yang {macro_desc}. Ini adalah momen yang ideal untuk mengakumulasi aset sesuai tesis mentor."
        elif macro_dir == "bearish":
            return f"⚠️ Peringatan Divergensi: Meskipun mentor sangat optimis, The Market Oracle mencatat kondisi makro riil saat ini {macro_desc}. Disarankan untuk menunggu konfirmasi teknikal atau mencicil bertahap (DCA) agar tidak terjebak."
        else:
            return f"⚖️ Tesis Menunggu Konfirmasi: Mentor melihat peluang bullish, namun indikator makro saat ini masih {macro_desc}. Tesis mentor berpotensi valid jika data makro membaik dalam waktu dekat."
    elif mentor_sent == "bearish":
        if macro_dir == "bearish":
            return f"🛡️ Konfirmasi Negatif: Kewaspadaan mentor sangat tepat. Data makro oracle memvalidasi bahwa pasar sedang {macro_desc}. Disarankan untuk menumpuk kas (CASH) dan menghindari saham berisiko tinggi."
        elif macro_dir == "bullish":
            return f"💡 Kontrarian: Mentor bersikap defensif (bearish), namun secara objektif kondisi makro saat ini {macro_desc}. Tesis mentor mungkin berfokus pada risiko spesifik yang belum tertangkap oleh data makro umum."
        else:
            return f"⚖️ Masa Transisi: Mentor mengantisipasi penurunan, sementara makro mencatat {macro_desc}. Investor disarankan memperketat money management (pasang stop-loss ketat)."
    else:
        # Mentor is neutral
        return f"🔍 Pantauan Ketat: Mentor mengambil sikap netral / wait-and-see. Di sisi lain, indikator makro saat ini berada di fase {macro_desc}. Padukan pandangan mentor dengan data ini untuk mengambil keputusan."


def analyze_mentors_original(macro_score: float, raw_data: dict = None) -> list:
    """
    Reads the mentor sentiment Excel file and returns the latest analysis for each mentor,
    appended with a dynamic AI conclusion based on the current macro_score.
    """
    try:
        df = pd.read_excel(MENTOR_SENTIMENT_FILE)
        
        # Sort by Waktu descending so the first one we pick is the latest
        if 'Waktu' in df.columns:
            df['Waktu'] = pd.to_datetime(df['Waktu'], format='mixed', errors='coerce', utc=True)
            df = df.sort_values(by='Waktu', ascending=False)
            
        # Drop duplicates by Mentor to get the latest per mentor
        latest_df = df.drop_duplicates(subset=['Mentor'], keep='first')
        
        mentors = []
        for _, row in latest_df.iterrows():
            mentor_name = str(row.get('Mentor', 'Unknown Mentor'))
            waktu = row.get('Waktu', '')
            if pd.notna(waktu) and hasattr(waktu, 'isoformat'):
                waktu_str = waktu.isoformat()
            else:
                waktu_str = str(waktu)
                
            judul = str(row.get('Judul', ''))
            sentimen = str(row.get('Sentimen', 'Neutral'))
            jargons = row.get('Jargon_Terdeteksi', '')
            cuplikan = str(row.get('Cuplikan_Isi', ''))
            isi_full = str(row.get('Isi_Full', ''))
            
            # Format jargons
            jargons_list = [j.strip() for j in str(jargons).split(',')] if pd.notna(jargons) and str(jargons).strip() else []
            
            # Create dynamic conclusion
            kesimpulan = get_dynamic_conclusion(sentimen, macro_score)
            
            mentors.append({
                "mentor": mentor_name,
                "waktu": waktu_str,
                "judul": judul,
                "sentimen": sentimen,
                "jargons": jargons_list,
                "cuplikan": cuplikan,
                "isi_full": isi_full,
                "kesimpulan_oracle": kesimpulan
            })
            
        # Tambahkan Revalue Academy secara dinamis
        if raw_data:
            try:
                from revalue_engine import analyze_revalue
                technicals = raw_data.get("technicals", {})
                indonesia = raw_data.get("indonesia", {})
                macro = raw_data.get("macro", {})
                
                _bi = indonesia.get("bi_rate")
                _inf = indonesia.get("inflation")
                _trend = technicals.get("ihsg_trend")
                _per = indonesia.get("ihsg_per")
                _cpi = macro.get("us_cpi_yoy")
                revalue_data = analyze_revalue(
                    bi_rate=_bi if _bi is not None else 5.75,
                    inflation_id=_inf if _inf is not None else 2.5,
                    ihsg_trend=_trend if _trend is not None else "sideways",
                    ihsg_per=_per if _per is not None else 14.0,
                    us_cpi_yoy=_cpi if _cpi is not None else 3.0,
                )
                
                mentors.append({
                    "mentor": "Revalue Academy",
                    "waktu": datetime.now().isoformat(),
                    "judul": "Analisis Makro & Rotasi Sektoral",
                    "sentimen": revalue_data["verdict"],
                    "jargons": [revalue_data["phase"], "Sectoral Rotation", "Business Cycle"],
                    "cuplikan": revalue_data["reasoning"],
                    "isi_full": revalue_data["full_explanation"],
                    "kesimpulan_oracle": get_dynamic_conclusion(revalue_data["verdict"], macro_score)
                })
            except Exception as e:
                print(f"[Mentor Analyzer] Gagal mengintegrasikan Revalue Academy: {e}")
            
        return mentors
        
    except Exception as e:
        print(f"[Error] Failed to read mentor sentiment Excel: {e}")
        return []

if __name__ == "__main__":
    # Test
    res = analyze_mentors_original(macro_score=-1.2)
    for m in res:
        print(m['mentor'], "-", m['sentimen'])
        print(m['kesimpulan_oracle'])
        print("-" * 40)
