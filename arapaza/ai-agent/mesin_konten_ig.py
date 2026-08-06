"""
Mesin AI multi-agent untuk KONTEN INSTAGRAM (format 4:5).

Agent:
- Detailing      : dari brief -> arahan detail per slide untuk layouting.
- Layouting      : susun layout tiap slide, ambil aset dari folder GitHub milik user.
- Checker        : KOORDINATOR — cek konsistensi brief/detailing/layouting, kirim koreksi.
- Checker Visual  : bandingkan rencana layout dengan REFERENSI design (folder GitHub), beri feedback.

Referensi & aset diambil dari folder GitHub:
  agent-konten-ig/aset/       -> aset yang ditempel ke layout
  agent-konten-ig/referensi/  -> contoh design acuan

Output: daftar 1-5 "slide spec". Gambar 4:5 final dirender di browser (html2canvas).
Background bertipe "generate" dibuat via model image Gemini bila Secret GEMINI_IMAGE_MODEL diisi
(kalau tidak, otomatis fallback ke warna/gradient/aset — tetap jalan di free tier).
"""
import os
import re
import json
import base64

import requests

from mesin_agent import client

try:
    from google.genai import types
except Exception:
    types = None

MODEL = "gemini-3.1-flash-lite"
IMG_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "").strip()  # mis. "gemini-3-pro-image" (opsional, berbayar)

# Repo GitHub sumber aset & referensi
GH_REPO = os.getenv("KONTEN_GH_REPO", "Alfaza-R/ai-agent").strip()
GH_BRANCH = os.getenv("KONTEN_GH_BRANCH", "main").strip()
GH_DIR_ASET = "agent-konten-ig/aset"
GH_DIR_REF = "agent-konten-ig/referensi"
_IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


# ── GitHub: list & unduh gambar dari folder ───────────────────────────
def _github_list(folder):
    """Kembalikan [{name, url}] gambar di folder repo (public, tanpa auth)."""
    url = "https://api.github.com/repos/" + GH_REPO + "/contents/" + folder + "?ref=" + GH_BRANCH
    try:
        r = requests.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=30)
        if r.status_code >= 400:
            return []
        out = []
        for it in r.json():
            if it.get("type") == "file" and it.get("name", "").lower().endswith(_IMG_EXT):
                out.append({"name": it["name"], "url": it.get("download_url", "")})
        return out
    except Exception:
        return []


def _fetch_bytes(url):
    try:
        r = requests.get(url, timeout=30)
        if r.status_code < 400:
            ct = r.headers.get("Content-Type", "image/png")
            mime = ct.split(";")[0].strip() or "image/png"
            return r.content, mime
    except Exception:
        pass
    return None, None


# ── Helper generik ────────────────────────────────────────────────────
def _gen(prompt, images=None):
    contents = [prompt]
    if images and types is not None:
        for b, m in images:
            if b:
                contents.append(types.Part.from_bytes(data=b, mime_type=m or "image/png"))
    resp = client.models.generate_content(model=MODEL, contents=contents)
    return (resp.text or "").strip()


def _json(txt, fallback):
    t = re.sub(r"```json|```", "", txt or "").strip()
    try:
        d = json.loads(t)
        return d if isinstance(d, (dict, list)) else fallback
    except Exception:
        return fallback


def _gen_image(prompt, input_images=None):
    """Generate/edit gambar via model image Gemini (boleh dikondisikan gambar input).
    Return base64 PNG atau '' (fallback)."""
    if not IMG_MODEL or types is None:
        return ""
    try:
        contents = [prompt]
        for b, m in (input_images or []):
            if b:
                contents.append(types.Part.from_bytes(data=b, mime_type=m or "image/png"))
        cfg = types.GenerateContentConfig(response_modalities=["IMAGE"])
        resp = client.models.generate_content(model=IMG_MODEL, contents=contents, config=cfg)
        for cand in (resp.candidates or []):
            for part in (cand.content.parts or []):
                data = getattr(getattr(part, "inline_data", None), "data", None)
                if data:
                    if isinstance(data, bytes):
                        return base64.b64encode(data).decode()
                    return str(data)  # sebagian SDK sudah base64 string
    except Exception:
        pass
    return ""


# Pollinations.ai — generate background GRATIS (tanpa API key). Text-to-image (FLUX).
POLLINATIONS_ON = os.getenv("POLLINATIONS_ENABLE", "1").strip() not in ("0", "false", "")


def _gen_image_pollinations(prompt, seed=None):
    """Generate gambar 4:5 via Pollinations.ai (gratis). Return base64 PNG atau ''."""
    if not POLLINATIONS_ON:
        return ""
    try:
        p = (prompt or "instagram content background, minimal, high quality").strip()[:600]
        q = requests.utils.quote(p, safe="")
        url = ("https://image.pollinations.ai/prompt/" + q +
               "?width=1080&height=1350&nologo=true&model=flux")
        if seed is not None:
            url += "&seed=" + str(seed)
        r = requests.get(url, timeout=120)
        ct = r.headers.get("Content-Type", "")
        if r.status_code < 400 and r.content and ct.startswith("image"):
            return base64.b64encode(r.content).decode()
    except Exception:
        pass
    return ""


# ── Agent Detailing ───────────────────────────────────────────────────
def _agent_detailing(brief, jumlah, koreksi="", produk_img=None):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB) ===\n" + koreksi) if koreksi else ""
    jml = ("Buat tepat " + str(jumlah) + " slide.") if jumlah else "Tentukan jumlah slide 1-5 sesuai kebutuhan brief."
    pr = ("\nCATATAN: ada FOTO PRODUK terlampir — perhatikan produknya dan buat arahan visual yang menonjolkan produk ini."
          if produk_img else "")
    prompt = (
        "Kamu Agent Detailing untuk konten Instagram (format 4:5). Dari brief di bawah, buat ARAHAN DETAIL per slide "
        "yang akan dipakai Agent Layouting.\n" + jml + "\n"
        "Tiap slide tentukan: peran (cover/isi/cta), headline, subteks, poin isi (bila ada), CTA (bila slide cta), "
        "mood/nuansa, saran warna dominan, dan arahan visual singkat (aset seperti apa yang cocok).\n"
        "Bahasa Indonesia, ringkas & konkret. JANGAN mengarang klaim yang tak ada di brief." + pr + "\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{ \"jumlah_slide\": N, \"slides\": [ {\"peran\":\"cover/isi/cta\", \"headline\":\"...\", \"subteks\":\"...\", "
        "\"poin\":[\"...\"], \"cta\":\"...\", \"mood\":\"...\", \"warna\":\"#hex atau nama\", \"arahan_visual\":\"...\"} ] }\n\n"
        "=== BRIEF ===\n" + brief + fb
    )
    imgs = [produk_img] if produk_img else None
    d = _json(_gen(prompt, imgs), {"jumlah_slide": 0, "slides": []})
    return d if isinstance(d, dict) else {"jumlah_slide": 0, "slides": []}


# ── Agent Layouting ───────────────────────────────────────────────────
def _agent_layouting(detailing, aset_list, koreksi="", produk_img=None):
    fb = ("\n\n=== KOREKSI (WAJIB) ===\n" + koreksi) if koreksi else ""
    daftar_aset = "\n".join("- " + a["name"] for a in aset_list) or "(tidak ada aset — pakai warna/gradient)"
    prod_note = ("\nADA FOTO PRODUK terlampir dengan nama khusus 'PRODUK_UTAMA' (sudah masuk daftar aset). "
                 "Utamakan pakai 'PRODUK_UTAMA' sebagai bg_aset atau aset_tempel pada slide yang menonjolkan produk. "
                 "Bila ingin latar hasil olahan AI dari produk, pakai bg_tipe 'generate' dan tulis bg_generate_prompt "
                 "yang mendeskripsikan scene di sekitar produk.") if produk_img else ""
    prompt = (
        "Kamu Agent Layouting konten Instagram 4:5 (1080x1350). Dari arahan Detailing di bawah, susun LAYOUT tiap slide.\n"
        "Kamu HANYA boleh memakai aset gambar dari DAFTAR ASET (sebut persis nama filenya). Kalau tidak ada aset yang cocok, "
        "pakai background 'warna' atau 'gradient', atau 'generate' (bila ingin ilustrasi AI).\n"
        "Untuk tiap slide tentukan background + elemen teks beserta posisi & gaya. Pastikan teks terbaca (kontras dengan bg).\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{ \"slides\": [ {"
        "\"bg_tipe\":\"aset|warna|gradient|generate\", "
        "\"bg_aset\":\"nama file dari daftar (bila bg_tipe=aset)\", "
        "\"bg_warna\":\"#hex (bila warna)\", "
        "\"bg_gradient\":[\"#hex\",\"#hex\"] , "
        "\"bg_generate_prompt\":\"deskripsi gambar (bila generate)\", "
        "\"overlay\": true, "
        "\"aset_tempel\":\"nama file aset yang ditempel sebagai foto (opsional)\", "
        "\"teks\": [ {\"isi\":\"...\", \"peran\":\"headline|sub|body|cta\", \"posisi\":\"atas|tengah|bawah\", "
        "\"align\":\"kiri|tengah|kanan\", \"warna\":\"#hex\", \"ukuran\":\"besar|sedang|kecil\"} ] } ] }" + prod_note + "\n\n"
        "=== DAFTAR ASET (pakai nama persis) ===\n" + daftar_aset +
        "\n\n=== ARAHAN DETAILING ===\n" + json.dumps(detailing, ensure_ascii=False) + fb
    )
    imgs = [produk_img] if produk_img else None
    d = _json(_gen(prompt, imgs), {"slides": []})
    return d if isinstance(d, dict) else {"slides": []}


# ── Agent Checker (KOORDINATOR) ───────────────────────────────────────
def _agent_checker(brief, detailing, layout):
    prompt = (
        "Kamu Agent Checker (KOORDINATOR) konten IG. Pastikan brief -> detailing -> layouting SALING KONSISTEN.\n"
        "Cek: apakah semua pesan penting di brief masuk? apakah layouting sesuai arahan detailing? apakah teks tiap slide "
        "lengkap & tidak ada slide kosong? apakah aset yang dipakai masuk akal?\n"
        "Kalau ADA yang salah, tulis instruksi koreksi spesifik untuk agent terkait.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{ \"konsisten\": true/false, \"koreksi_detailing\":\"(kosong bila ok)\", \"koreksi_layouting\":\"(kosong bila ok)\", "
        "\"catatan\":[\"...\"] }\n\n"
        "=== BRIEF ===\n" + brief +
        "\n\n=== DETAILING ===\n" + json.dumps(detailing, ensure_ascii=False) +
        "\n\n=== LAYOUTING ===\n" + json.dumps(layout, ensure_ascii=False)
    )
    return _json(_gen(prompt), {"konsisten": True, "koreksi_detailing": "", "koreksi_layouting": "", "catatan": []})


# ── Agent Checker Visual ──────────────────────────────────────────────
def _agent_checker_visual(layout, ref_images):
    if not ref_images:
        return {"sesuai": True, "koreksi_layouting": "", "feedback": ["(Tidak ada referensi design — checker visual dilewati.)"]}
    prompt = (
        "Kamu Agent Checker Visual konten IG. Ada beberapa gambar REFERENSI DESIGN terlampir (acuan gaya). "
        "Nilai apakah RENCANA LAYOUT di bawah (warna, komposisi, gaya teks) SUDAH SEJALAN dengan gaya referensi.\n"
        "Kalau belum sejalan, beri instruksi koreksi konkret untuk Agent Layouting (mis. samakan palet warna, posisi teks, "
        "gaya font, penggunaan whitespace).\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{ \"sesuai\": true/false, \"koreksi_layouting\":\"(kosong bila sudah sesuai)\", \"feedback\":[\"...\"] }\n\n"
        "=== RENCANA LAYOUT ===\n" + json.dumps(layout, ensure_ascii=False)
    )
    imgs = [(b, m) for (b, m) in ref_images]
    return _json(_gen(prompt, imgs), {"sesuai": True, "koreksi_layouting": "", "feedback": []})


# ── Normalisasi & generate background ─────────────────────────────────
def _aset_url(aset_list, name):
    for a in aset_list:
        if a["name"] == name:
            return a["url"]
    return ""


_PRODUK_KEY = "PRODUK_UTAMA"


def _finalize_slides(layout, aset_list, produk_img=None, ref_images=None):
    slides = []
    for s in (layout.get("slides") or []):
        if not isinstance(s, dict):
            continue
        bg_tipe = (s.get("bg_tipe") or "warna").lower()
        bg_aset = s.get("bg_aset") or ""
        aset_tempel = s.get("aset_tempel") or ""
        slide = {
            "bg_tipe": bg_tipe,
            "bg_warna": s.get("bg_warna") or "#111827",
            "bg_gradient": s.get("bg_gradient") if isinstance(s.get("bg_gradient"), list) else [],
            "bg_aset_url": "" if bg_aset == _PRODUK_KEY else _aset_url(aset_list, bg_aset),
            "aset_tempel_url": "" if aset_tempel == _PRODUK_KEY else _aset_url(aset_list, aset_tempel),
            "bg_pakai_produk": bg_aset == _PRODUK_KEY,       # frontend tempel foto produk yang di-upload
            "tempel_pakai_produk": aset_tempel == _PRODUK_KEY,
            "overlay": bool(s.get("overlay", bg_tipe in ("aset", "generate"))),
            "bg_generate_b64": "",
            "teks": [t for t in (s.get("teks") or []) if isinstance(t, dict) and (t.get("isi"))],
        }
        # Generative background (opsional, hanya bila model image diset) — dikondisikan foto produk + referensi
        if bg_tipe == "generate":
            prompt_bg = (s.get("bg_generate_prompt") or "").strip()
            # 1) Gemini image (paling nyatu, bila GEMINI_IMAGE_MODEL diisi + billing aktif)
            kondisi = ([produk_img] if produk_img else []) + list(ref_images or [])[:3]
            b64 = _gen_image(
                prompt_bg + " — vertical 4:5 Instagram content background. Jika ada foto produk terlampir, tampilkan "
                "produk itu secara akurat (jangan mengubah bentuk produk), selaraskan gaya dengan gambar referensi.",
                kondisi,
            )
            # 2) Pollinations (GRATIS) — generate background dari teks (produk ditempel terpisah via aset_tempel)
            if not b64:
                b64 = _gen_image_pollinations(
                    prompt_bg + ", vertical 4:5 social media background, clean, modern, high quality, no text"
                )
            if b64:
                slide["bg_generate_b64"] = b64
                slide["bg_sumber"] = "ai"
            elif produk_img:
                # Fallback terakhir: pakai foto produk asli sebagai background
                slide["bg_tipe"] = "aset"
                slide["bg_pakai_produk"] = True
            else:
                slide["bg_tipe"] = "gradient"
                if not slide["bg_gradient"]:
                    slide["bg_gradient"] = ["#6d28d9", "#2563eb"]
        slides.append(slide)
    return slides


# ── PIPELINE UTAMA ────────────────────────────────────────────────────
def buat_konten_ig(brief="", jumlah=0, produk_base64="", produk_mime="image/png"):
    brief = (brief or "").strip()
    try:
        jumlah = int(jumlah or 0)
    except (TypeError, ValueError):
        jumlah = 0
    if jumlah:
        jumlah = max(1, min(5, jumlah))

    # Foto produk yang di-upload di brief (opsional)
    produk_img = None
    if produk_base64:
        try:
            produk_img = (base64.b64decode(produk_base64), produk_mime or "image/png")
        except Exception:
            produk_img = None

    # Ambil aset & referensi dari GitHub
    aset_list = _github_list(GH_DIR_ASET)
    if produk_img:
        # Foto produk jadi aset khusus yang bisa dipilih Agent Layouting
        aset_list = [{"name": _PRODUK_KEY, "url": ""}] + aset_list
    ref_list = _github_list(GH_DIR_REF)
    ref_images = []
    for r in ref_list[:6]:
        b, m = _fetch_bytes(r["url"])
        if b:
            ref_images.append((b, m))

    # 1) Detailing + Layouting + Checker (koordinator) — loop maks 2
    kor_d = kor_l = ""
    detailing = layout = {}
    checker = {}
    for _ in range(2):
        detailing = _agent_detailing(brief, jumlah, kor_d, produk_img)
        layout = _agent_layouting(detailing, aset_list, kor_l, produk_img)
        checker = _agent_checker(brief, detailing, layout)
        if checker.get("konsisten", True):
            break
        kor_d = checker.get("koreksi_detailing", "") or ""
        kor_l = checker.get("koreksi_layouting", "") or ""
        if not kor_d and not kor_l:
            break

    # 2) Checker Visual — bandingkan dengan referensi; bila perlu, revisi layout sekali
    visual = _agent_checker_visual(layout, ref_images)
    if not visual.get("sesuai", True) and (visual.get("koreksi_layouting") or ""):
        layout = _agent_layouting(detailing, aset_list, visual.get("koreksi_layouting", ""), produk_img)

    # 3) Finalisasi slide (+ generate bg dari foto produk & referensi bila diaktifkan)
    slides = _finalize_slides(layout, aset_list, produk_img, ref_images)

    return {
        "detailing":       detailing,
        "layout":          layout,
        "checker":         checker,
        "checker_visual":  visual,
        "slides":          slides,
        "jumlah_aset":     len(aset_list) - (1 if produk_img else 0),
        "jumlah_referensi": len(ref_list),
        "ada_produk":      bool(produk_img),
        "generative_aktif": bool(IMG_MODEL) or POLLINATIONS_ON,
        "generative_sumber": ("gemini" if IMG_MODEL else ("pollinations" if POLLINATIONS_ON else "")),
    }
