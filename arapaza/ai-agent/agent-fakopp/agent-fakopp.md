# Agent: Fakopp — Sales & Service Assistant (pipeline multi-agent, chat mode)

Bantu tim sales & service alat **Fakopp** (uji pohon & kayu berbasis akustik) memahami permintaan customer → 2 output (awam & teknis) + skematik. Pola sama seperti HOBO; Agent Product mengecek website Fakopp.

## File
- Backend: `mesin_fakopp.py` — fungsi `analisa_fakopp(chat, image_base64, image_mime, riwayat)`.
- Endpoint: `POST /fakopp-sales` di `main.py`.
- Frontend: `agent-fakopp/fakopp.html` (chat mode 2 kolom, tema hijau, download PNG skematik).

## Input (JSON)
```json
{ "chat":"...pesan customer terbaru...", "image_base64":"...", "image_mime":"image/png | application/pdf",
  "riwayat":"transkrip percakapan sebelumnya (opsional)" }
```

## Pipeline
1. **🅰️ Reader Teks** — tujuan uji (deteksi busuk/rongga, stabilitas pohon, grading kayu/MOE, riset), objek (pohon/log/kayu), jumlah, konteks.
2. **🅱️ Reader Visual** — foto pohon/lokasi/kondisi batang, datasheet, hasil uji.
3. **📦 Product** — rekomendasi produk Fakopp; **utamakan cek** `fakopp.com`. Contoh: ArborSonic 3D Tomograph (busuk/rongga), DynaRoot (stabilitas/risiko tumbang), Microsecond Timer (MOE/deteksi kerusakan).
4. **🔧 Technical** — metode & setup pengukuran + BOM + catatan interpretasi.
5. **🛠️ Service** — kalibrasi, software (ArborSonic/DynaRoot), training, troubleshooting, garansi.
6. **✅ Checker — KOORDINATOR** — cek Product/Technical/Service vs Reader (mis. tujuan stabilitas harus DynaRoot, bukan tomograph); kirim koreksi (loop maks 2x).
7. **🔄 Compare** (`_agent_compare`) — cari alternatif merek lain via web (PiCUS/Argus, IML-RESI Resistograph, TreeQinetic, dll) → tabel banding + beda metode.
8. **💰 Budget** (`_agent_budget`) — estimasi biaya dari Product + Compare → **2 sub-output**: `modal` (harga beli Taharica) & `penawaran` (harga jual customer). Estimasi kasar + asumsi eksplisit; wajib diverifikasi.
9. **🗺️ Flow** — MermaidJS alur pengukuran.
10. **🎯 Result** — **3 output**: sales versi Fakopp, sales versi produk lain, teknis.

## Output (JSON)
```json
{ "reader_teks","reader_visual","info_terverifikasi","inkonsistensi":[],
  "pertanyaan_klarifikasi":[],"produk","teknis","service","compare",
  "budget_modal","budget_penawaran","flow_mermaid",
  "output_awam_hobo","output_awam_lain","output_technical" }
```
(`output_awam_hobo` = versi Fakopp — nama field disamakan dengan HOBO agar frontend seragam.)

## Routing (chat lanjutan)
Frontend mengirim `sebelumnya` (hasil turn sebelumnya). Di turn lanjutan, **Agent Router** (`_agent_router`) memilih agent yang perlu bekerja ulang saja (mis. revisi produk → `product`+checker; hitung ulang harga → `budget`; ubah gaya → tidak ada). Response menyertakan `rute_agent`.

## Konfigurasi
- `FAKOPP_SITES` (Secret, default `fakopp.com`) — website acuan Agent Product. Tambah distributor lokal bila ada.

## Model
Gemini `gemini-3.1-flash-lite` (vision + text + Google Search grounding untuk Product).
