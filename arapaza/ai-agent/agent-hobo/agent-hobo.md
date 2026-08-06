# Agent: HOBO Data Logger — Sales & Service Assistant (pipeline multi-agent)

Bantu tim sales & service memahami permintaan customer soal produk **HOBO (Onset) data logger** → keluar 2 output (awam & teknis) + diagram alur. Mirip agent BMS, tapi fokus data logger + ada Agent Service, dan Agent Product mengecek website HOBO.

## File
- Backend: `mesin_hobo.py` — fungsi `analisa_hobo(chat, image_base64, image_mime)`.
- Endpoint: `POST /hobo-sales` di `main.py`.
- Frontend: `agent-hobo/hobo.html` (render Mermaid + Markdown).

## Input (JSON)
```json
{ "chat":"...pesan customer terbaru...", "image_base64":"...", "image_mime":"image/png | application/pdf",
  "riwayat":"transkrip percakapan sebelumnya (opsional, chat lanjutan)" }
```
File (foto lokasi/datasheet/PDF) opsional — dibaca Gemini vision.

**Routing (chat lanjutan):** frontend mengirim `sebelumnya` (hasil turn sebelumnya). Di turn lanjutan, **Agent Router** (`_agent_router`) memutuskan agent mana yang perlu bekerja ulang (mis. minta revisi produk → hanya `product` + downstream + checker; minta hitung ulang harga → hanya `budget`; ubah gaya balasan → tidak ada agent, cukup susun ulang). Agent lain memakai hasil lama → hemat waktu. Response menyertakan `rute_agent` (agent yang bekerja).

**Chat mode (multi-turn):** frontend `hobo.html` = antarmuka chat 2 kolom (chat kiri, detail agent kanan, scroll independen, background mesh gradient, skematik bisa di-download PNG). Tiap kirim menyertakan `riwayat` agar balasan nyambung. `output_awam` = bubble balasan; `output_technical` + kartu per-agent (termasuk Service) + skematik di panel kanan.

## Pipeline (urutan)
1. **🅰️ Reader Teks** (`_agent_reader_teks`) — ekstrak kebutuhan dari chat (parameter, lokasi, jumlah titik, interval, software, sales/service).
2. **🅱️ Reader Visual** (`_agent_reader_visual`) — baca foto/datasheet/PDF.
   → keduanya = **acuan kebenaran**.
3. **📦 Product** (`_agent_product`) — rekomendasi produk HOBO; **utamakan cek website** `onsetcomp.com` & `loggerindo.com` (Google Search grounding). Sebut seri/model (MX, U/UX-series, Pendant, RX3000, Smart Sensor, dll).
4. **🔧 Technical** (`_agent_technical`) — setup/arsitektur pengukuran + Bill of Materials + catatan teknis.
5. **🛠️ Service** (`_agent_service`) — troubleshooting, kalibrasi, software HOBOware/HOBOlink, garansi/perawatan.
6. **✅ Checker — KOORDINATOR** (`_agent_checker_all`) — cek Product/Technical/Service vs Reader; bila tak selaras → kirim koreksi → agent ulang (loop maks 2x).
7. **🔄 Compare** (`_agent_compare`) — cari produk ALTERNATIF merek lain yang setara (Campbell, Lascar, Testo, dll) via web → tabel banding. Supaya sales punya opsi selain HOBO.
8. **🔎 Riset Harga** (`_agent_harga_riset`) — **search web real-time** untuk harga pasar terkini tiap produk (HOBO & alternatif), + konversi Rp. Hasil (`harga_riset`) jadi basis Budget. Dibuat agar tidak under-price (alat premium).
9. **💰 Budget** (`_agent_budget`) — dari harga pasar → **2 sub-output**: `penawaran` (≈ harga pasar end-user) & `modal` (= penawaran − margin distributor ~20-35%, jadi modal < penawaran). Estimasi, wajib diverifikasi.
9. **🗺️ Flow** (`_agent_flow`) — MermaidJS flowchart alur pengukuran.
10. **🎯 Result** (`_agent_result`) — **3 output**: sales versi HOBO, sales versi produk lain, teknis.

## Output (JSON)
```json
{ "reader_teks","reader_visual","info_terverifikasi","inkonsistensi":[],
  "pertanyaan_klarifikasi":[],"produk","teknis","service","compare",
  "budget_modal","budget_penawaran","flow_mermaid",
  "output_awam_hobo","output_awam_lain","output_technical" }
```
Catatan: budget = **estimasi**, AI tidak tahu harga beli/margin asli Taharica.

## Konfigurasi
- `HOBO_SITES` (Secret, default `onsetcomp.com, loggerindo.com`) — website acuan Agent Product.

## Model
Gemini `gemini-3.1-flash-lite` (vision + text + Google Search grounding untuk Product).
