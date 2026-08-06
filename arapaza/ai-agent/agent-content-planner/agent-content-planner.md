# Agent: Content Planner (Brief)

Bikin brief konten media sosial per-slide (Instagram, LinkedIn, dll) otomatis dari topik + link referensi. Hasilnya jadi task untuk tim desain (intern).

## File
- `mesin_agent.py` — fungsi `buat_brief(topik, link, daftar_platform, jumlah=1)`.
- Endpoint: `POST /buat-brief` di `main.py`.

## Input (JSON)
```json
{ "topik": "...", "link": "https://...", "platform": ["Instagram","LinkedIn"], "jumlah": 1 }
```
- `jumlah` = jumlah brief per platform (1–8). Kalau >1, tiap brief pakai SUDUT KONTEN berbeda (Edukasi, Product Knowledge, Storytelling, dll — lihat `SUDUT_KONTEN`).

## Output
Dict per platform → list `{sudut, isi}`. `isi` berupa **HTML terstruktur**:
- Judul narasi → `<h1>`
- Judul tiap slide → `<h2>`
- Poin (Visual/Isi) → `<ul><li>`
- Slide terakhir selalu CTA.

## Cara kerja
1. `baca_link()` ambil isi halaman referensi (BeautifulSoup) untuk konteks.
2. `buat_brief_satu_platform()` susun prompt (contoh format + aturan) → Gemini.
3. Hasil dicek [Brief Checker](agent-brief-checker.md) (koherensi) → auto-rewrite bila perlu.

## Integrasi WordPress
Plugin `intern-dashboard` (`includes/class-api-planner.php`) memanggil `/buat-brief`, lalu bikin 1 task per platform (tipe Design, status pending, detail = brief HTML). Tombol "✨ Brief AI" di dashboard admin/intern.

## Model
Gemini `gemini-3.1-flash-lite`.
