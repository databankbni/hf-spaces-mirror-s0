# AI Agent — Micro-Epsilon (Sensor Presisi)

Asisten **sales & service** untuk produk sensor **Micro-Epsilon** (pabrikan Jerman, merek keagenan/principal Taharica). Pola pipeline sama persis dengan agent HOBO/Load Cell: chat multi-turn, Router untuk chat lanjutan, Compare merek lain, Riset Harga + Budget, dan Agent Konfirmasi.

## File
- Backend: [`mesin_microepsilon.py`](../mesin_microepsilon.py) (di root, dipanggil `main.py`)
- Endpoint: `POST /microepsilon-sales`
- Frontend: [`microepsilon.html`](microepsilon.html) — tempel ke widget HTML Elementor (halaman sendiri, mis. `eknowledge.taharica.com/ai-microepsilon/`)

## Lini produk yang dicakup
optoNCDT (laser triangulation), optoNCDT ILR (laser distance/ToF), confocalDT (confocal chromatic — presisi tinggi, benda transparan/mengkilap, ketebalan), interferoMETER (sub-nanometer), eddyNCDT (eddy current — lingkungan kotor/oli/panas, target logam), capaNCDT (capacitive — nanometer), induSENSOR/mainSENSOR (inductive/LVDT), wireSENSOR (draw-wire, stroke panjang), thermoMETER (IR pyrometer) & thermoIMAGER TIM (kamera termal), colorSENSOR/colorCONTROL, scanCONTROL (2D/3D laser scanner), optoCONTROL (optical micrometer).

## Pipeline agent
`Reader Teks → Reader Visual → Product (pilih teknologi + cek micro-epsilon.com) → Technical → Service → Checker (koordinator, loop maks 2) → Konfirmasi → Compare (merek lain) → Riset Harga → Budget → Flow (Mermaid) → Result (3 output)`.

Kunci Agent Product: **memilih teknologi sensor** sesuai besaran, target/material & lingkungan (mis. target logam berminyak/panas → eddyNCDT; ketebalan kaca → confocalDT; nanometer di lab bersih → capaNCDT; stroke panjang → wireSENSOR; suhu non-kontak → thermoMETER).

## Field respons (JSON)
Sama seperti agent lain: `reader_teks`, `reader_visual`, `info_terverifikasi`, `konfirmasi`, `inkonsistensi[]`, `pertanyaan_klarifikasi[]`, `produk`, `teknis`, `service`, `compare`, `harga_riset`, `budget_modal`, `budget_penawaran`, `flow_mermaid`, `output_awam_hobo` (versi Micro-Epsilon), `output_awam_lain` (versi merek lain), `output_technical`, `rute_agent[]`, `rute_alasan`.

> Catatan: nama field `output_awam_hobo` sengaja dipertahankan sama di semua agent supaya satu frontend template dipakai bersama.

## Konfigurasi (opsional, via Secret Space)
- `MICROEPSILON_SITES` — default `micro-epsilon.com`
- `MICROEPSILON_FAMILIES` — daftar lini produk yang jadi acuan Agent Product
- `GEMINI_API_KEY` — wajib (dipakai semua agent)

## Compare — prioritas asal produk
Barat (Eropa/Amerika) **dan Jepang** dulu (kompetitor utama sensor presisi: Keyence, Omron, Panasonic, SICK, Baumer, Balluff, Acuity, dll) → China → Lokal.

## Update / deploy
Backend berubah → `git push origin main` lalu deploy kode-saja ke `hf` (lihat catatan deploy HF). Frontend → paste ulang `microepsilon.html` ke Elementor → Update → Ctrl+F5. Jangan lupa isi `LINK_MICROEPSILON` di `dashboard/dashboard.html` setelah halaman Elementor dibuat.
