"""
Mesin cek SEO + readability ala Yoast.

Pendekatan hybrid:
- Metrik objektif (keyphrase di judul/meta/paragraf awal/subheading, densitas,
  panjang meta, jumlah kata, link, panjang kalimat, dll) dihitung PASTI di Python
  supaya konsisten — mirip cara Yoast yang berbasis aturan.
- Saran perbaikan & revisi artikel pakai Gemini.
"""
import re
import json
from mesin_agent import client  # reuse client Gemini yang sudah ada


# ---------- util teks ----------
def _strip_tags(html):
    txt = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", txt).strip()


def _words(text):
    return [w for w in re.findall(r"[0-9A-Za-zÀ-ÿ\-']+", text or "")]


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text or "")
    return [s.strip() for s in parts if s.strip()]


def _paragraphs(html):
    paras = re.findall(r"<p\b[^>]*>(.*?)</p>", html or "", flags=re.I | re.S)
    return [_strip_tags(p) for p in paras if _strip_tags(p)]


def _subheadings(html):
    return [_strip_tags(h) for h in re.findall(r"<h[23]\b[^>]*>(.*?)</h[23]>", html or "", flags=re.I | re.S)]


# ---------- penilaian objektif (ala Yoast) ----------
def _check(label, status, msg):
    # status: "good" (hijau), "ok" (kuning), "bad" (merah)
    return {"label": label, "status": status, "pesan": msg}


def hitung_metrik(title, content, meta, keyphrase):
    kp = (keyphrase or "").strip().lower()
    plain = _strip_tags(content)
    words = _words(plain)
    wc = len(words)
    plain_low = plain.lower()

    seo = []
    read = []

    # ===== SEO =====
    # 1. Keyphrase ada
    if not kp:
        seo.append(_check("Focus keyphrase", "bad", "Focus keyphrase kosong."))
    else:
        # 2. di judul
        seo.append(_check("Keyphrase di judul",
                          "good" if kp in (title or "").lower() else "bad",
                          "Keyphrase ada di judul." if kp in (title or "").lower()
                          else "Keyphrase tidak ada di judul."))
        # 3. di meta description
        seo.append(_check("Keyphrase di meta description",
                          "good" if kp in (meta or "").lower() else "bad",
                          "Ada di meta description." if kp in (meta or "").lower()
                          else "Tidak ada di meta description."))
        # 4. di paragraf pertama
        paras = _paragraphs(content)
        first = paras[0].lower() if paras else ""
        seo.append(_check("Keyphrase di paragraf awal",
                          "good" if kp in first else "bad",
                          "Ada di paragraf pembuka." if kp in first
                          else "Tidak ada di paragraf pembuka."))
        # 5. di subheading
        subs = " ".join(_subheadings(content)).lower()
        seo.append(_check("Keyphrase di subheading (H2/H3)",
                          "good" if kp in subs else "ok",
                          "Ada di minimal satu subheading." if kp in subs
                          else "Belum ada subheading yang mengandung keyphrase."))
        # 6. densitas keyphrase
        kp_count = plain_low.count(kp)
        density = (kp_count * len(_words(kp)) / wc * 100) if wc else 0
        if 0.5 <= density <= 3.0:
            seo.append(_check("Kepadatan keyphrase", "good", f"{density:.1f}% (ideal 0.5-3%)."))
        elif density < 0.5:
            seo.append(_check("Kepadatan keyphrase", "bad", f"{density:.1f}% terlalu rendah (ideal 0.5-3%)."))
        else:
            seo.append(_check("Kepadatan keyphrase", "ok", f"{density:.1f}% agak tinggi (ideal 0.5-3%)."))

    # 7. panjang meta description
    ml = len(meta or "")
    if 120 <= ml <= 156:
        seo.append(_check("Panjang meta description", "good", f"{ml} karakter (ideal 120-156)."))
    elif ml == 0:
        seo.append(_check("Panjang meta description", "bad", "Meta description kosong."))
    else:
        seo.append(_check("Panjang meta description", "ok", f"{ml} karakter (ideal 120-156)."))

    # 8. panjang judul (karakter)
    tl = len(title or "")
    seo.append(_check("Panjang judul SEO", "good" if 30 <= tl <= 60 else "ok",
                      f"{tl} karakter (ideal 30-60)."))

    # 9. jumlah kata konten
    if wc >= 800:
        seo.append(_check("Panjang artikel", "good", f"{wc} kata."))
    elif wc >= 300:
        seo.append(_check("Panjang artikel", "ok", f"{wc} kata (idealnya 800+ untuk SEO)."))
    else:
        seo.append(_check("Panjang artikel", "bad", f"{wc} kata terlalu pendek."))

    # 10. link
    nlink = len(re.findall(r"<a\b[^>]*href=", content or "", flags=re.I))
    seo.append(_check("Link dalam artikel", "good" if nlink >= 1 else "bad",
                      f"{nlink} link ditemukan." if nlink else "Tidak ada link sama sekali."))

    # ===== READABILITY =====
    sents = _sentences(plain)
    ns = len(sents)
    if ns:
        long_s = sum(1 for s in sents if len(_words(s)) > 20)
        pct_long = long_s / ns * 100
        read.append(_check("Panjang kalimat", "good" if pct_long <= 25 else "bad",
                           f"{pct_long:.0f}% kalimat >20 kata (maks 25%)."))

        # kalimat pasif (heuristik bahasa Indonesia: awalan di- + akhiran umum / 'oleh')
        passive = 0
        for s in sents:
            sw = s.lower()
            if re.search(r"\bdi[a-z]{3,}", sw) or " oleh " in sw:
                passive += 1
        pct_pass = passive / ns * 100
        read.append(_check("Kalimat pasif", "good" if pct_pass <= 10 else "ok",
                           f"~{pct_pass:.0f}% kalimat berpotensi pasif (maks 10%)."))

    # panjang paragraf
    paras = _paragraphs(content)
    long_p = [p for p in paras if len(_words(p)) > 150]
    read.append(_check("Panjang paragraf", "good" if not long_p else "ok",
                       "Tidak ada paragraf terlalu panjang." if not long_p
                       else f"{len(long_p)} paragraf >150 kata, sebaiknya dipecah."))

    # distribusi subheading
    subs_n = len(_subheadings(content))
    if wc > 300 and subs_n == 0:
        read.append(_check("Distribusi subheading", "bad", "Artikel panjang tanpa subheading."))
    else:
        read.append(_check("Distribusi subheading", "good", f"{subs_n} subheading."))

    # ===== skor =====
    def skor(items):
        if not items:
            return 0
        pts = sum(1.0 if i["status"] == "good" else 0.5 if i["status"] == "ok" else 0 for i in items)
        return round(pts / len(items) * 100)

    seo_score = skor(seo)
    read_score = skor(read)

    return {
        "seo_score": seo_score,
        "readability_score": read_score,
        "seo_checks": seo,
        "readability_checks": read,
        "word_count": wc,
    }


def _status_label(score):
    if score >= 80:
        return "hijau"
    if score >= 50:
        return "kuning"
    return "merah"


# ---------- saran perbaikan (Gemini) ----------
def saran_perbaikan(metrik, title, keyphrase):
    masalah = [c for c in (metrik["seo_checks"] + metrik["readability_checks"]) if c["status"] != "good"]
    if not masalah:
        return ["Artikel sudah memenuhi standar Yoast. Tidak ada perbaikan kritikal."]

    daftar = "\n".join(f"- {m['label']}: {m['pesan']}" for m in masalah)
    perintah = (
        f"Kamu konsultan SEO. Artikel berjudul \"{title}\" dengan focus keyphrase \"{keyphrase}\" "
        f"punya masalah berikut menurut standar Yoast:\n{daftar}\n\n"
        "Berikan saran perbaikan singkat, konkret, dan actionable dalam Bahasa Indonesia. "
        "Kembalikan HANYA JSON array string, contoh: [\"saran 1\", \"saran 2\"]. Maksimal 6 saran."
    )
    try:
        resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=perintah)
        txt = re.sub(r"```json|```", "", resp.text).strip()
        arr = json.loads(txt)
        return arr if isinstance(arr, list) else [str(arr)]
    except Exception as e:
        return [f"(Gagal ambil saran AI: {e})"] + [m["pesan"] for m in masalah]


# ---------- auto-perbaiki artikel (Gemini) ----------
def perbaiki_artikel(title, content, meta, keyphrase, metrik):
    masalah = [c for c in (metrik["seo_checks"] + metrik["readability_checks"]) if c["status"] != "good"]
    daftar = "\n".join(f"- {m['label']}: {m['pesan']}" for m in masalah) or "(minor)"
    perintah = (
        "Kamu SEO content editor. Perbaiki artikel HTML berikut agar memenuhi standar Yoast SEO & readability, "
        "TANPA mengubah topik dan TANPA menghapus link <a> yang sudah ada.\n\n"
        f"FOCUS KEYPHRASE: {keyphrase}\n"
        f"MASALAH yang harus diperbaiki:\n{daftar}\n\n"
        "ATURAN: heading tertinggi <h2> (tanpa <h1>); mayoritas kalimat aktif & <=20 kata; "
        "keyphrase muncul di judul, paragraf pertama, dan minimal satu subheading; densitas keyphrase 0.5-3%; "
        "pertahankan/segarkan struktur (paragraf + bullet list bila relevan); jangan pakai em dash.\n\n"
        f"JUDUL SAAT INI: {title}\n"
        f"META SAAT INI: {meta}\n"
        "KONTEN HTML SAAT INI:\n" + (content or "") + "\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): "
        '{\"title\":\"...\",\"meta_description\":\"...(120-156 char)\",\"focus_keyphrase\":\"...\",\"content\":\"<p>...</p>\"}'
    )
    resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=perintah)
    txt = re.sub(r"```json|```", "", resp.text).strip()
    return json.loads(txt)


# ---------- entrypoint ----------
def cek_seo(title, content, meta, keyphrase, perbaiki=False):
    metrik = hitung_metrik(title, content, meta, keyphrase)
    hasil = {
        "seo_score": metrik["seo_score"],
        "seo_status": _status_label(metrik["seo_score"]),
        "readability_score": metrik["readability_score"],
        "readability_status": _status_label(metrik["readability_score"]),
        "word_count": metrik["word_count"],
        "checklist": metrik["seo_checks"] + metrik["readability_checks"],
        "saran": saran_perbaikan(metrik, title, keyphrase),
        "revisi": None,
    }

    # Auto-perbaiki hanya jika ada yang belum hijau
    perlu = metrik["seo_score"] < 80 or metrik["readability_score"] < 80
    if perbaiki and perlu:
        try:
            revisi = perbaiki_artikel(title, content, meta, keyphrase, metrik)
            metrik2 = hitung_metrik(
                revisi.get("title", title),
                revisi.get("content", content),
                revisi.get("meta_description", meta),
                revisi.get("focus_keyphrase", keyphrase),
            )
            revisi["seo_score"] = metrik2["seo_score"]
            revisi["readability_score"] = metrik2["readability_score"]
            hasil["revisi"] = revisi
        except Exception as e:
            hasil["revisi_error"] = str(e)

    return hasil
