# Agent: Brief Checker

Agent QC untuk hasil [Content Planner](agent-content-planner.md). Mengecek koherensi/relevansi brief; kalau tidak konsisten → perintah rewrite otomatis.

## File
- `mesin_brief_checker.py` — fungsi `periksa_dan_perbaiki(brief_html, topik, platform, maks=2)`.
- Dipanggil otomatis di dalam `mesin_agent.buat_brief_satu_platform()` (lazy import), jadi TIDAK ada endpoint tersendiri.

## Yang dicek
1. Koherensi antar-slide (slide 1 → 2 → dst satu alur, tidak loncat topik).
2. Kesesuaian narasi Visual (instruksi gambar) dengan Headline/teks tiap slide.
3. Relevansi ke topik.

## Cara kerja
- `_periksa()` → Gemini balikin JSON `{konsisten: bool, masalah: [...]}`.
- Kalau `konsisten=false`, `_rewrite()` memperbaiki brief (pertahankan format HTML), lalu dicek lagi.
- Loop maksimal 2 putaran. Kalau checker error → pakai brief asli (aman, tidak menggagalkan generate).

## Catatan
Menambah 1–4 panggilan Gemini per brief → generate lebih lama, terutama bila `jumlah` besar.
