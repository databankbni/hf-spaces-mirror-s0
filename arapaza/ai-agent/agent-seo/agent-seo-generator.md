# Agent: Article + SEO Generator (Google Sheet)

Generate artikel SEO dari keyword → auto cek & perbaiki ala Yoast → publish draft ke banyak website WordPress.

## Lokasi
- Google Apps Script (di Google Spreadsheet). Kode lengkap tersimpan di `appscript-baru.txt` (root repo, berisi kredensial → **jangan** commit).
- Backupnya versi lama: `appscriptsheetlama.txt`.

## Arsitektur (config-driven)
- Semua website ada di **satu array `SITES`** (9 web). Tambah web = tambah 1 objek `{ sheet, siteName, url, user, pass, warna... }`.
- Menu bekerja pada **sheet/tab yang aktif** (klik tab web dulu, lalu menu).
- Menu: **▶️ Generate (sheet aktif)**, **🎨 Refresh Warna**, **⚙️ Setup/Buat SEMUA Sheet**, **📋 Daftar Web**.

## Kolom sheet
Keyword, Internal Links, Outbound Links, Custom Prompt, Jenis Artikel (Pilar/Turunan 1/2), Products, Jasa, Generate?(checkbox), Status, **SEO Score, Readability, Catatan SEO** (J/K/L).

## Alur per baris (dicentang Generate?)
1. `_callGemini` → artikel JSON (title, content HTML, meta, focus_keyphrase, slug, tags, category).
2. `_cekSEO` panggil backend `POST /cek-seo` (`perbaiki:true`) → kalau ada revisi, artikel diganti versi perbaikan.
3. `_trimMeta` pangkas meta ≤ 140 char.
4. `_publishToWP` → buat **draft** di WP (REST API + Application Password) + set Yoast (`yoast_meta`).
5. Tulis skor SEO/Readability + catatan ke kolom J/K/L.

## Web terdaftar (9)
taharica.co.id, alatuji.co.id, taharicadatamonitoring.com, automationindo.com, timbanganindonesia.com, taharica.com, rajaloadcell.com, loggerindo.co.id, loggerindo.com.

## Model
Gemini `gemini-3.1-flash-lite` (dipanggil langsung dari Apps Script).
