import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai

load_dotenv()


def _make_client():
    """Buat Gemini client. Dipanggil LAZY (bukan saat import) supaya masalah key
    tidak menjatuhkan seluruh app saat startup — app tetap hidup, error muncul jelas
    per-request."""
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY tidak ditemukan/kosong di environment server. "
            "Cek Secret 'GEMINI_API_KEY' di Settings Space (pastikan terisi, tanpa spasi)."
        )
    return genai.Client(api_key=key)


class _LazyClient:
    """Proxy: bikin client asli saat pertama kali dipakai (client.models.dst), bukan saat import."""
    _real = None

    def __getattr__(self, name):
        if _LazyClient._real is None:
            _LazyClient._real = _make_client()
        return getattr(_LazyClient._real, name)


client = _LazyClient()

CONTOH_FORMAT = """<h1>Konten Carousel Instagram — Realita Kehidupan Laboran</h1>
<p><strong>Jenis Konten:</strong> Entertaining / Relatable</p>
<p><strong>Format:</strong> Carousel</p>
<p><strong>Warna Dominan:</strong> Merah</p>
<p><strong>Sumber/Referensi:</strong> Timbangan Laboratorium / https://timbanganindonesia.com/product/orion-series/</p>

<h2>SLIDE 1 — Thumbnail</h2>
<p><strong>Visual:</strong></p>
<ul>
  <li>Ilustrasi karakter laboran yang bingung di depan timbangan.</li>
</ul>
<p><strong>Headline:</strong> Momen "Dugaan" di Laboratorium</p>
<p><strong>Sub Headline:</strong> Saat Kamu Sudah Yakin, Tapi Angka Terus Berubah</p>

<h2>SLIDE 2 — Penyebabnya Apa?</h2>
<p><strong>Visual:</strong></p>
<ul>
  <li>Foto timbangan dengan area kerja sedikit berantakan.</li>
</ul>
<p><strong>Headline:</strong> Penyebab Drama Timbangan</p>
<p><strong>Isi:</strong></p>
<ul>
  <li>Pintu Kaca Belum Tertutup Rapat: aliran udara memengaruhi hasil.</li>
</ul>

<h2>SLIDE 3 — Call To Action</h2>
<ul>
  <li>Template CTA yang biasa digunakan.</li>
</ul>"""


# Daftar "sudut konten" untuk variasi brief saat 1 platform diminta banyak brief.
# Dipakai bergiliran (brief ke-1 pakai sudut ke-1, dst).
SUDUT_KONTEN = [
    "Edukasi / Tips Praktis",
    "Product Knowledge (kenalkan fitur & keunggulan produk)",
    "Storytelling / Relatable (cerita keseharian yang nyambung dengan produk)",
    "Promosi / Penawaran (dorong audiens untuk action / beli)",
    "Testimoni / Social Proof (bukti & kepercayaan dari pengguna)",
    "Behind The Scenes / Proses (di balik layar produk atau layanan)",
    "Mitos vs Fakta / FAQ (luruskan salah kaprah, jawab pertanyaan umum)",
    "Inspirasi / Motivasi (angkat semangat yang relevan dengan audiens)",
]


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


def buat_brief_satu_platform(topik, link, isi_link, platform, sudut=None):
    instruksi_sudut = (
        f"- SUDUT KONTEN brief ini: {sudut}. Fokuskan seluruh isi brief ke sudut ini.\n"
        if sudut else ""
    )
    perintah = f"""Kamu adalah content planner profesional untuk brand alat industri/laboratorium.
Buatkan brief konten untuk platform {platform}, untuk dikerjakan tim desain.

PENTING:
- Ikuti PERSIS format dan gaya dari contoh di bawah.
- OUTPUT HARUS HTML. Aturan struktur:
  * Judul narasi (paling atas) pakai <h1>.
  * Judul tiap slide (mis. "SLIDE 1 — Thumbnail") pakai <h2>.
  * Daftar/poin (Visual, Isi, dll) pakai bullet list <ul><li>...</li></ul>.
  * Label singkat (Jenis Konten, Headline, Sub Headline, dsb) pakai <p><strong>Label:</strong> nilai</p>.
- HANYA keluarkan HTML mentah. JANGAN bungkus dengan ```html atau ``` , JANGAN pakai markdown.
- Sesuaikan NUANSA dengan platform {platform}: kalau Instagram lebih santai/relatable, kalau LinkedIn lebih profesional dan informatif.
{instruksi_sudut}- Jangan menambah bagian "Tips Tambahan", "Caption", atau "Hashtag".
- Maksimal 5 slide (termasuk CTA). Umumnya 3-4 slide. Slide terakhir selalu CTA (isi CTA seperti biasa).
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
    hasil = response.text

    # Brief Checker: cek koherensi/relevansi, rewrite otomatis kalau perlu (maks 2x)
    try:
        from mesin_brief_checker import periksa_dan_perbaiki
        hasil = periksa_dan_perbaiki(hasil, topik, platform)
    except Exception:
        pass  # kalau checker error, pakai brief asli supaya generate tetap jalan

    return hasil


def buat_brief(topik, link, daftar_platform, jumlah=1):
    # Batasi jumlah brief per platform supaya wajar (hindari request kelamaan).
    try:
        jumlah = int(jumlah)
    except (TypeError, ValueError):
        jumlah = 1
    jumlah = max(1, min(jumlah, 8))

    isi_link = baca_link(link)
    hasil = {}
    for platform in daftar_platform:
        daftar_brief = []
        for i in range(jumlah):
            # Kalau cuma 1 brief, biarkan tanpa sudut khusus (perilaku lama).
            sudut = SUDUT_KONTEN[i % len(SUDUT_KONTEN)] if jumlah > 1 else None
            isi = buat_brief_satu_platform(topik, link, isi_link, platform, sudut)
            daftar_brief.append({"sudut": sudut or "Umum", "isi": isi})
        hasil[platform] = daftar_brief
    return hasil