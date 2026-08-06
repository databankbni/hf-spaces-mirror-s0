# AI Agents — Peta Proyek & Struktur Folder

Kumpulan AI agent (backend FastAPI di Hugging Face Spaces + integrasi WordPress/Google Sheet).

## 📁 Struktur folder

```
ai-agent/
├── main.py                     ← backend (semua endpoint + CORS) — JANGAN dipindah
├── mesin_agent.py              ← mesin Content Planner        ┐
├── mesin_brief_checker.py      ← mesin Brief Checker          │ file inti,
├── mesin_seo.py                ← mesin SEO Checker            │ dipanggil main.py,
├── mesin_bms.py                ← mesin BMS                    │ harus tetap di root
├── mesin_penetrasi.py          ← mesin Market Penetration     │ (dipakai deploy HF)
├── mesin_konten_ig.py          ← mesin Konten Instagram 4:5   │
├── mesin_hobo.py               ← mesin HOBO data logger       │
├── mesin_fakopp.py             ← mesin Fakopp (pohon & kayu)  │
├── mesin_hmp.py                ← mesin HMP (uji tanah)        │
├── mesin_timbangan.py          ← mesin Timbangan             │
├── mesin_loadcell.py           ← mesin Load Cell             │
├── mesin_microepsilon.py       ← mesin Micro-Epsilon         │
├── Dockerfile, requirements.txt, README.md                   ┘
│
├── agent-content-planner/      📝 dokumentasi Content Planner + Brief Checker
├── agent-seo/                  🔎 dokumentasi SEO + Apps Script + app password
├── agent-bms/                  🏢 dokumentasi BMS + bms.html (frontend)
├── agent-penetrasi/            🚀 dokumentasi Market Penetration + penetrasi.html
├── agent-konten-ig/            🎨 Konten IG 4:5 + konten-ig.html + folder aset/ & referensi/
├── agent-hobo/                 🌡️ HOBO data logger + hobo.html
├── agent-fakopp/               🌳 Fakopp (uji pohon & kayu) + fakopp.html
├── agent-hmp/                  🏗️ HMP (uji tanah) + hmp.html
├── agent-timbangan/            ⚖️ Timbangan + timbangan.html
├── agent-loadcell/             🔩 Load Cell + loadcell.html
├── agent-microepsilon/         📏 Micro-Epsilon (sensor presisi) + microepsilon.html
├── dashboard/                  📊 dokumentasi + dashboard.html (frontend hub)
└── _arsip-latihan/             🗑️ file latihan lama (tidak dipakai)
```

> **Kenapa file `.py` inti tetap di root?** `main.py` meng-`import` semua `mesin_*.py`, dan Hugging Face menjalankan semuanya dari root. Kalau dipindah ke subfolder, backend gagal jalan.

## Backend (Hugging Face Space: `arapaza/ai-agent`)
- URL: `https://arapaza-ai-agent.hf.space`
- Deploy: `git push hf main` → Space rebuild otomatis.
- Secret di Space: `GEMINI_API_KEY`, `CLOUDCONVERT_API_KEY`.

## Daftar Agent & Endpoint
| Agent | File backend | Endpoint | Dipakai di | Dokumentasi |
|---|---|---|---|---|
| Content Planner (brief) | `mesin_agent.py` | `POST /buat-brief` | Plugin WP intern-dashboard | [agent-content-planner/](agent-content-planner/agent-content-planner.md) |
| Brief Checker | `mesin_brief_checker.py` | (nempel di /buat-brief) | otomatis saat generate brief | [agent-content-planner/](agent-content-planner/agent-brief-checker.md) |
| SEO Checker (Yoast) | `mesin_seo.py` | `POST /cek-seo` | Apps Script generator | [agent-seo/](agent-seo/agent-seo-checker.md) |
| Article + SEO Generator | Apps Script (`agent-seo/appscript-baru.txt`) | — (di Google Sheet) | Google Spreadsheet | [agent-seo/](agent-seo/agent-seo-generator.md) |
| BMS Sales Assistant | `mesin_bms.py` | `POST /bms-sales` | `agent-bms/bms.html` | [agent-bms/](agent-bms/agent-bms.md) |
| Market Penetration | `mesin_penetrasi.py` | `POST /penetrasi-market` | `agent-penetrasi/penetrasi.html` | [agent-penetrasi/](agent-penetrasi/agent-penetrasi.md) |
| Konten Instagram 4:5 | `mesin_konten_ig.py` | `POST /konten-ig` | `agent-konten-ig/konten-ig.html` | [agent-konten-ig/](agent-konten-ig/agent-konten-ig.md) |
| HOBO Data Logger | `mesin_hobo.py` | `POST /hobo-sales` | `agent-hobo/hobo.html` | [agent-hobo/](agent-hobo/agent-hobo.md) |
| Fakopp (pohon & kayu) | `mesin_fakopp.py` | `POST /fakopp-sales` | `agent-fakopp/fakopp.html` | [agent-fakopp/](agent-fakopp/agent-fakopp.md) |
| HMP (uji tanah) | `mesin_hmp.py` | `POST /hmp-sales` | `agent-hmp/hmp.html` | [agent-hmp/](agent-hmp/agent-hmp.md) |
| Timbangan | `mesin_timbangan.py` | `POST /timbangan-sales` | `agent-timbangan/timbangan.html` | [agent-timbangan/](agent-timbangan/agent-timbangan.md) |
| Load Cell | `mesin_loadcell.py` | `POST /loadcell-sales` | `agent-loadcell/loadcell.html` | [agent-loadcell/](agent-loadcell/agent-loadcell.md) |
| Micro-Epsilon (sensor presisi) | `mesin_microepsilon.py` | `POST /microepsilon-sales` | `agent-microepsilon/microepsilon.html` | [agent-microepsilon/](agent-microepsilon/agent-microepsilon.md) |
| Dashboard (hub) | — | — | `dashboard/dashboard.html` | [dashboard/](dashboard/dashboard.md) |

## Cara update singkat
- **Backend berubah** → `git add -A && git commit -m "..." && git push origin main && git push hf main` → tunggu Space Running.
- **Frontend** → re-paste isi `agent-bms/bms.html` atau `dashboard/dashboard.html` ke widget HTML Elementor → Update → Ctrl+F5.
- **Apps Script** → salin `agent-seo/appscript-baru.txt` ke editor Apps Script → Save.

## Catatan keamanan (belum dikerjakan)
Kredensial yang pernah ter-expose sebaiknya dirotate: `GEMINI_API_KEY`, 9 App Password WordPress, `CLOUDCONVERT_API_KEY`. File rahasia (`agent-seo/appscript-baru.txt`, `agent-seo/appscriptsheetlama.txt`, `agent-seo/App Password web baru.txt`) sudah di-`.gitignore`. **`_arsip-latihan/API Key.txt` masih ke-track di git history → rotasi key-nya.**
