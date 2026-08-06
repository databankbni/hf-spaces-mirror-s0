# Agent: Konten Instagram Generator (4:5, multi-agent)

Dari brief → susun 1–5 slide konten Instagram format **4:5** (1080×1350) siap-unduh. Aset & referensi diambil dari folder GitHub.

## File
- Backend: `mesin_konten_ig.py` — fungsi `buat_konten_ig(brief, jumlah)`.
- Endpoint: `POST /konten-ig` di `main.py`.
- Frontend: `agent-konten-ig/konten-ig.html` (render slide + export PNG via html2canvas).
- Aset: folder `agent-konten-ig/aset/` · Referensi: `agent-konten-ig/referensi/` (lihat `CARA-UPLOAD-GAMBAR.md`).

## Input (JSON)
```json
{ "brief": "...deskripsi konten...", "jumlah": 0,
  "produk_base64": "", "produk_mime": "image/png" }
```
`jumlah` 0 = agent tentukan sendiri (1–5). `produk_base64` = foto produk khusus untuk konten ini (opsional).

### Foto produk per-konten
- Foto produk yang di-upload masuk sebagai aset khusus bernama `PRODUK_UTAMA` yang bisa dipilih Agent Layouting (jadi bg atau foto tempel).
- Kalau layout memilih `bg_tipe: generate` + `GEMINI_IMAGE_MODEL` aktif → gambar di-generate dari foto produk + referensi (produk dipertahankan, gaya disesuaikan referensi).
- Kalau generative **belum aktif** → foto produk **ditempel langsung** ke layout (fallback, tetap berguna).
- Slide punya flag `bg_pakai_produk` / `tempel_pakai_produk`; frontend memasang foto produk yang di-upload di posisi itu.

## Pipeline
1. **🅰️ Detailing** (`_agent_detailing`) — dari brief → arahan detail per slide (headline, subteks, poin, cta, mood, warna, arahan visual).
2. **🅱️ Layouting** (`_agent_layouting`) — susun layout tiap slide; **hanya** pakai aset dari folder GitHub (pilih by nama file), atau bg warna/gradient/generate.
3. **✅ Checker — KOORDINATOR** (`_agent_checker`) — cek brief↔detailing↔layouting konsisten; bila tidak → kirim koreksi ke agent terkait (loop maks 2x).
4. **👁️ Checker Visual** (`_agent_checker_visual`) — bandingkan rencana layout dengan gambar **referensi** (Gemini vision); bila belum sejalan → revisi layout 1x.

## Output (JSON)
```json
{ "detailing":{...}, "layout":{...}, "checker":{...}, "checker_visual":{...},
  "slides":[ { "bg_tipe","bg_warna","bg_gradient","bg_aset_url","aset_tempel_url",
               "overlay","bg_generate_b64","teks":[{isi,peran,posisi,align,warna,ukuran}] } ],
  "jumlah_aset","jumlah_referensi","generative_aktif" }
```
Render 4:5 final dilakukan **di browser** (html2canvas) → unduh PNG per slide / semua.

## Sumber gambar (GitHub)
- Backend baca folder repo via GitHub API (repo public, tanpa token): `KONTEN_GH_REPO` (default `Alfaza-R/ai-agent`), `KONTEN_GH_BRANCH` (`main`).
- Tambah gambar = upload ke folder (web GitHub / git push). Tidak perlu re-deploy.

## Generative background
Slide `bg_tipe: generate` diisi berurutan:
1. **Gemini image** (`GEMINI_IMAGE_MODEL`) — paling menyatu, tapi **butuh billing** (free tier = kuota 0, sudah dites 2026-07: error `limit: 0`).
2. **Pollinations.ai** (GRATIS, tanpa key) — default aktif (`POLLINATIONS_ENABLE=1`), text-to-image FLUX 1080x1350. Foto produk asli tetap ditempel terpisah (akurat).
3. Fallback: foto produk sebagai bg → gradient.

Response: `generative_aktif`, `generative_sumber` ("gemini"/"pollinations"). Matikan Pollinations via Secret `POLLINATIONS_ENABLE=0`.

## Model
Gemini `gemini-3.1-flash-lite` (text + vision). Image gen opsional via `GEMINI_IMAGE_MODEL`.
