# Agent: Load Cell — Sales & Service Assistant (chat mode)

Bantu tim sales & service produk **load cell** dari merek **keagenan Taharica** (katalog rajaloadcell.com). Pola sama seperti HOBO/Timbangan: chat multi-turn + Router + Compare + Riset Harga + Budget.

## File
- Backend: `mesin_loadcell.py` — fungsi `analisa_loadcell(chat, image_base64, image_mime, riwayat, sebelumnya)`.
- Endpoint: `POST /loadcell-sales` di `main.py`.
- Frontend: `agent-loadcell/loadcell.html` (chat 2 kolom, tema crimson, download PNG skematik).

## Domain
Load cell: compression, tension/tarik-tekan, S-type/S-beam, single point, shear beam, double-ended shear beam, canister/column, bending beam, load pin, weigh module. Fokus: cocokkan **aplikasi + tipe + kapasitas + kelas akurasi (OIML C3/C6) + output mV/V + IP/material**.

## Merek keagenan (diutamakan Agent Product)
CAS, MKCells, AS Sonic, Dini Argeo, Fujitsu, Zemic, ANT, Excellent, Kistler, Showa Sokki (昭和測器), Vibra, dll. Diatur via Secret `LOADCELL_BRANDS`. Katalog acuan: `LOADCELL_SITES` (default `rajaloadcell.com`).

## Pipeline
Reader Teks/Visual → **Product** (utamakan merek keagenan, cek rajaloadcell.com) → Technical (konfigurasi sistem, jumlah load cell, junction box, indikator, wiring/BOM) → Service (kalibrasi/sertifikat, troubleshooting, penggantian) → Checker → **Compare** (HBM, Flintec, Vishay, dll — prioritas Barat→China→Lokal) → **Riset Harga** (web real-time) → **Budget** (modal & penawaran, anti under-price) → Flow → **Result** (3 output: keagenan / produk lain / teknis).

**Routing (chat lanjutan):** Agent Router pilih agent yang perlu kerja ulang.

## Output (JSON)
```json
{ "reader_teks","reader_visual","info_terverifikasi","inkonsistensi":[],
  "pertanyaan_klarifikasi":[],"produk","teknis","service","compare","harga_riset",
  "budget_modal","budget_penawaran","flow_mermaid",
  "output_awam_hobo","output_awam_lain","output_technical","rute_agent","rute_alasan" }
```

## Model
Gemini `gemini-3.1-flash-lite` (vision + text + Google Search grounding).
