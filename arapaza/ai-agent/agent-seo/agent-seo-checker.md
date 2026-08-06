# Agent: SEO Checker (standar Yoast)

Menilai artikel ala Yoast (SEO + readability), kasih skor + checklist + saran, dan bisa auto-revisi.

## File
- `mesin_seo.py` — fungsi `cek_seo(title, content, meta, keyphrase, perbaiki=False)`.
- Endpoint: `POST /cek-seo` di `main.py`.

## Input (JSON)
```json
{ "title":"...", "content":"<p>...</p>", "meta_description":"...", "focus_keyphrase":"...", "perbaiki": true }
```

## Output
```json
{ "seo_score": 0-100, "seo_status":"hijau/kuning/merah",
  "readability_score": 0-100, "readability_status":"...",
  "word_count": 0, "checklist":[{label,status,pesan}], "saran":[...],
  "revisi": { title, content, meta_description, focus_keyphrase, seo_score, readability_score } | null }
```

## Cara kerja (hybrid)
- **Metrik objektif dihitung di Python** (mirip aturan Yoast): keyphrase di judul/meta/paragraf awal/subheading, densitas, panjang meta, jumlah kata, link, panjang kalimat, kalimat pasif (heuristik ID), panjang paragraf, distribusi subheading.
- **Gemini** dipakai untuk: `saran_perbaikan()` dan `perbaiki_artikel()` (rewrite bila `perbaiki=True` dan skor < 80).

## Dipakai oleh
Google Apps Script generator artikel — tiap artikel yang digenerate otomatis dicek + diperbaiki sebelum publish (lihat [agent-seo-generator.md](agent-seo-generator.md)).
