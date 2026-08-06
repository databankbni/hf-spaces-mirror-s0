# Agent: Timbangan Indonesia — Sales & Service Assistant (chat mode)

Bantu tim sales & service produk **timbangan & load cell** (katalog timbanganindonesia.com). Pola sama seperti HOBO/Fakopp/HMP: chat multi-turn + Router + Compare + Riset Harga + Budget.

## File
- Backend: `mesin_timbangan.py` — fungsi `analisa_timbangan(chat, image_base64, image_mime, riwayat, sebelumnya)`.
- Endpoint: `POST /timbangan-sales` di `main.py`.
- Frontend: `agent-timbangan/timbangan.html` (chat 2 kolom, tema steel/indigo, download PNG skematik).

## Domain
Timbangan: badan, counting, gantung/crane, portable, duduk, emas, harga, hewan, hybrid, laboratorium/analytical, lantai/floor, platform, truk/jembatan timbang; load cell; indikator; anak timbangan; junction box. Fokus: cocokkan **jenis + kapasitas (Max) + ketelitian (d)**, dan ingatkan **TERA/legal-for-trade** untuk transaksi.

## Pipeline
Reader Teks/Visual → **Product** (cek `timbanganindonesia.com`) → Technical (spesifikasi/BOM) → Service (kalibrasi/tera/perawatan) → Checker → **Compare** (Mettler Toledo, Sartorius, Ohaus, Dini Argeo, dll — prioritas Barat→China→Lokal) → **Riset Harga** (web real-time) → **Budget** (modal & penawaran, anti under-price) → Flow → **Result** (3 output: katalog / produk lain / teknis).

**Routing (chat lanjutan):** Agent Router pilih agent yang perlu kerja ulang berdasar pesan baru + `sebelumnya`.

## Output (JSON)
```json
{ "reader_teks","reader_visual","info_terverifikasi","inkonsistensi":[],
  "pertanyaan_klarifikasi":[],"produk","teknis","service","compare","harga_riset",
  "budget_modal","budget_penawaran","flow_mermaid",
  "output_awam_hobo","output_awam_lain","output_technical","rute_agent","rute_alasan" }
```

## Konfigurasi
- `TIMBANGAN_SITES` (Secret, default `timbanganindonesia.com`) — website acuan Agent Product.

## Model
Gemini `gemini-3.1-flash-lite` (vision + text + Google Search grounding).
