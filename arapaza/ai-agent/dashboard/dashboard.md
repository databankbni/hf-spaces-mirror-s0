# Dashboard AI Agent (Hub)

Halaman "pusat" berisi kartu semua AI agent. Dark mode, HTML mandiri (tempel di Elementor widget HTML).

## File
- `dashboard.html`
- Halaman WP: `eknowledge.taharica.com/taharica-ai-agent/`

## Isi
Kartu per agent (Content Planner, Article + SEO Generator, SEO Checker, BMS Sales Assistant) — deskripsi + status online/offline + tombol akses.

## Konfigurasi (di dalam JS `dashboard.html`)
- `BACKEND_URL` = `https://arapaza-ai-agent.hf.space`
- `LINK_DASHBOARD_INTERN`, `LINK_SPREADSHEET`, `LINK_API_DOCS`, `LINK_BMS` — URL tujuan tombol.
- Kalau URL masih `GANTI_...`, kartu menampilkan "⚠️ Set URL dulu".

## Status backend
Sekali `fetch(BACKEND_URL + "/")` untuk cek online/offline (butuh CORS — sudah aktif di `main.py`).

## Tombol di halaman IT (hero)
Ada tombol expand-on-hover "TAHARICA AI AGENT" di hero halaman IT eknowledge yang menuju halaman dashboard ini (kode hero terpisah, di Elementor halaman IT).
