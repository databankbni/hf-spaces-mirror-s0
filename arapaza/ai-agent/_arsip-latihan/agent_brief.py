import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# === CONTOH FORMAT BRIEF (cetakan IG, dipakai semua platform dulu) ===
CONTOH_FORMAT = """Konten Carousel Instagram — Realita Kehidupan Laboran
Jenis Konten: Entertaining / Relatable
Format: Carousel
Warna Dominan: Merah
Sumber/Referensi: Timbangan Laboratorium / https://timbanganindonesia.com/product/orion-series/

---
SLIDE 1 — Thumbnail
Visual:
- Ilustrasi karakter laboran yang bingung di depan timbangan.
Headline:
Momen "Dugaan" di Laboratorium
Sub Headline:
Saat Kamu Sudah Yakin, Tapi Angka Terus Berubah

---
SLIDE 2 — Penyebabnya Apa?
Visual:
- Foto timbangan dengan area kerja sedikit berantakan.
Headline:
Penyebab Drama Timbangan
Isi:
- Pintu Kaca Belum Tertutup Rapat: aliran udara memengaruhi hasil.

---
SLIDE 3 — Call To Action
Visual:
- Template CTA yang biasa digunakan."""


# === FUNGSI 1: baca isi link ===
def baca_link(url):
    if not url:
        return "(tidak ada link referensi)"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        halaman = requests.get(url, headers=headers, timeout=20)
        sup = BeautifulSoup(halaman.text, "html.parser")
        return sup.get_text(separator=" ", strip=True)[:2000]
    except Exception as e:
        return f"(Gagal baca link: {e})"


# === FUNGSI 2: bikin brief untuk SATU platform ===
def buat_brief_satu_platform(topik, link, isi_link, platform):
    perintah = f"""Kamu adalah content planner profesional untuk brand alat industri/laboratorium.
Buatkan brief konten untuk platform {platform}, untuk dikerjakan tim desain.

PENTING:
- Ikuti PERSIS format dan gaya dari contoh di bawah.
- Sesuaikan NUANSA dengan platform {platform}: kalau Instagram lebih santai/relatable, kalau LinkedIn lebih profesional dan informatif.
- Jangan menambah bagian "Tips Tambahan", "Caption", atau "Hashtag".
- Maksimal 5 slide (termasuk CTA). Umumnya 3-4 slide. Slide terakhir selalu CTA.
- Pada bagian "Sumber/Referensi", tulis link ini: {link}

=== CONTOH FORMAT YANG HARUS DIIKUTI ===
{CONTOH_FORMAT}
=== AKHIR CONTOH ===

=== INFORMASI PRODUK (hasil baca link, pakai untuk konteks isi) ===
{isi_link}
=== AKHIR INFORMASI PRODUK ===

Sekarang buat brief BARU dengan format sama persis untuk:
Topik: {topik}
Platform: {platform}
Pastikan isi nyambung dengan produk dari informasi di atas."""

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=perintah,
    )
    return response.text


# === FUNGSI 3: mesin utama — terima banyak platform ===
def buat_brief(topik, link, daftar_platform):
    isi_link = baca_link(link)  # baca link sekali aja, dipakai semua platform
    hasil = {}
    for platform in daftar_platform:
        print(f"... lagi bikin brief untuk {platform} ...")
        hasil[platform] = buat_brief_satu_platform(topik, link, isi_link, platform)
    return hasil


# === COBA JALANIN ===
# Ini bagian "input" — nanti diganti input dari dashboard
input_topik = "Tips merawat timbangan laboratorium biar awet"
input_link = "https://timbanganindonesia.com/product/orion-series/"
input_platform = ["Instagram", "LinkedIn"]

semua_brief = buat_brief(input_topik, input_link, input_platform)

# Tampilin hasilnya per platform
for platform, brief in semua_brief.items():
    print("\n" + "=" * 50)
    print(f"BRIEF UNTUK: {platform}")
    print("=" * 50)
    print(brief)