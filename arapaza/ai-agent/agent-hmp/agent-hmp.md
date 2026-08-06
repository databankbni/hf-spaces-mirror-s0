# Agent: HMP — Sales & Service Assistant (pipeline multi-agent, chat mode)

Bantu tim sales & service alat **HMP (Magdeburger Prüfgerätebau GmbH)** — uji daya dukung & pemadatan **tanah** (geoteknik/konstruksi). Pola sama seperti HOBO/Fakopp: chat multi-turn + Router + Compare + Riset Harga + Budget.

## File
- Backend: `mesin_hmp.py` — fungsi `analisa_hmp(chat, image_base64, image_mime, riwayat, sebelumnya)`.
- Endpoint: `POST /hmp-sales` di `main.py`.
- Frontend: `agent-hmp/hmp.html` (chat 2 kolom, tema earth/amber, download PNG skematik).

## Domain
HMP = alat uji tanah: **Light Weight Deflectometer (LFG/LWD)** → modulus Evd (uji cepat pemadatan lapangan), **Static Plate Load Test** → Ev1/Ev2 (DIN 18134), untuk QC konstruksi jalan, timbunan/earthworks, subgrade, fondasi.

## Input (JSON)
```json
{ "chat":"...", "image_base64":"", "image_mime":"image/png|application/pdf",
  "riwayat":"", "sebelumnya": {..hasil turn sebelumnya..} }
```

## Pipeline
Reader Teks/Visual → **Product** (cek `hmp-online.de`) → Technical (metode/standar/BOM) → Service (kalibrasi/software/training) → Checker (koordinator) → **Compare** (alternatif: Zorn ZFG, Controls/Matest, dll — prioritas Barat→China→Lokal) → **Riset Harga** (search web real-time) → **Budget** (modal & penawaran, anti under-price) → Flow → **Result** (3 output: HMP / produk lain / teknis).

**Routing (chat lanjutan):** Agent Router pilih agent yang perlu kerja ulang berdasar pesan baru + `sebelumnya`.

## Output (JSON)
```json
{ "reader_teks","reader_visual","info_terverifikasi","inkonsistensi":[],
  "pertanyaan_klarifikasi":[],"produk","teknis","service","compare","harga_riset",
  "budget_modal","budget_penawaran","flow_mermaid",
  "output_awam_hobo","output_awam_lain","output_technical","rute_agent","rute_alasan" }
```

## Konfigurasi
- `HMP_SITES` (Secret, default `hmp-online.de`) — website acuan Agent Product. Tambah distributor lokal bila ada.

## Model
Gemini `gemini-3.1-flash-lite` (vision + text + Google Search grounding).
