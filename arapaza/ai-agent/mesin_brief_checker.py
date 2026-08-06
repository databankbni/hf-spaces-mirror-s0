"""
Brief Checker — agent QC untuk hasil Content Planner.

Memeriksa koherensi/relevansi brief:
- Antar-slide nyambung & satu alur (slide 1 -> 2 -> dst tidak loncat topik).
- Deskripsi Visual (instruksi gambar) sesuai dengan Headline/teks tiap slide.
- Seluruh isi relevan dengan topik.

Kalau tidak konsisten, agent memerintahkan rewrite (maks 2 putaran).
"""
import re
import json

from mesin_agent import client  # reuse client Gemini


def _periksa(brief_html, topik, platform):
    prompt = (
        f"Kamu QC editor untuk brief konten media sosial platform {platform}, topik \"{topik}\".\n\n"
        "Periksa brief HTML di bawah pada 3 aspek:\n"
        "1. KOHERENSI ANTAR-SLIDE: apakah slide mengalir satu alur logis (slide 1 -> 2 -> dst membahas tema yang sama, tidak loncat topik).\n"
        "2. VISUAL vs TEKS: apakah deskripsi 'Visual' (instruksi gambar) tiap slide SESUAI dengan Headline/Isi teks slide itu.\n"
        "3. RELEVANSI TOPIK: apakah seluruh isi relevan dengan topik di atas.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): {\"konsisten\": true/false, \"masalah\": [\"masalah konkret (sebut slide & apa yang salah)\", \"...\"]}\n"
        "Set \"konsisten\": false bila ADA masalah berarti.\n\n"
        "=== BRIEF ===\n" + (brief_html or "")
    )
    try:
        resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        txt = re.sub(r"```json|```", "", resp.text or "").strip()
        data = json.loads(txt)
        return {
            "konsisten": bool(data.get("konsisten", True)),
            "masalah": data.get("masalah", []) if isinstance(data.get("masalah"), list) else [],
        }
    except Exception:
        # Kalau gagal menilai, anggap konsisten supaya tidak mengganggu alur generate
        return {"konsisten": True, "masalah": []}


def _rewrite(brief_html, topik, platform, masalah):
    daftar = "\n".join("- " + str(m) for m in masalah) or "- (perbaiki koherensi umum)"
    prompt = (
        f"Kamu content editor. Perbaiki brief HTML berikut (platform {platform}, topik \"{topik}\") agar:\n"
        "- Antar-slide nyambung & satu alur.\n"
        "- Deskripsi Visual cocok dengan teks tiap slide.\n"
        "- Semua isi relevan dengan topik.\n\n"
        "MASALAH yang HARUS diperbaiki:\n" + daftar + "\n\n"
        "PERTAHANKAN format & struktur HTML: <h1> untuk judul narasi, <h2> untuk tiap slide, "
        "<ul><li> untuk poin/Visual, slide terakhir tetap Call To Action. "
        "Jangan menambah penjelasan/komentar apa pun.\n"
        "Kembalikan HANYA HTML brief yang sudah diperbaiki (tanpa backtick).\n\n"
        "=== BRIEF LAMA ===\n" + (brief_html or "")
    )
    resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
    out = re.sub(r"^```html|^```|```$", "", (resp.text or "").strip(), flags=re.MULTILINE).strip()
    return out or brief_html


def periksa_dan_perbaiki(brief_html, topik, platform, maks=2):
    """Cek koherensi; rewrite kalau perlu (maksimal `maks` putaran)."""
    hasil = brief_html
    for _ in range(maks):
        cek = _periksa(hasil, topik, platform)
        if cek["konsisten"]:
            break
        baru = _rewrite(hasil, topik, platform, cek["masalah"])
        if not baru or baru.strip() == (hasil or "").strip():
            break
        hasil = baru
    return hasil
