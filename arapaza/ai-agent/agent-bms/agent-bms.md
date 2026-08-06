# Agent: BMS Sales Assistant (pipeline multi-agent)

Bantu sales Building Management System memahami permintaan customer (teks + gambar/CAD/PDF) → keluar 2 output (awam & teknis) + diagram alur.

## File
- Backend: `mesin_bms.py` — fungsi `analisa_bms(chat, image_base64, image_mime)`.
- Endpoint: `POST /bms-sales` di `main.py`.
- Frontend: `bms.html` (halaman WP terpisah, render Mermaid + Markdown).
- Secret: `CLOUDCONVERT_API_KEY` (konversi DWG).

## Input (JSON)
```json
{ "chat":"...pesan customer terbaru...", "image_base64":"...", "image_mime":"image/png | application/pdf | ...",
  "riwayat":"transkrip percakapan sebelumnya (opsional, untuk chat lanjutan)" }
```
- File DWG → dikonversi ke PDF dulu via **CloudConvert** (`_dwg_to_pdf_cloudconvert`), karena Gemini tidak bisa baca DWG mentah.
- **Chat mode (multi-turn):** frontend `bms.html` kini antarmuka chat (bubble). Tiap kirim, frontend menyertakan `riwayat` (transkrip turn sebelumnya) supaya balasan nyambung. `output_awam` = bubble balasan agent; `output_technical` + kartu per-agent + flow tampil di panel "Detail kerja tiap agent" (balasan terbaru).

## Pipeline (urutan)
1. **🅰️ Reader Teks** (`_agent_reader_teks`) — ekstrak info dari chat.
2. **🅱️ Reader Visual** (`_agent_reader_visual`) — baca gambar/CAD/PDF (Gemini vision).
   → keduanya = **acuan kebenaran**.
3. **📦 Product** (`_agent_product`) — rekomendasi produk, **prioritas Azbil**; kalau tak ada → cari web (Google Search grounding, fallback ke pengetahuan model).
4. **🔧 Technical** (`_agent_technical`) — skematik cara kerja + Bill of Materials (jumlah barang).
5. **✅ Checker — KOORDINATOR** (`_agent_checker_all`) — cek SEMUA hasil (Product & Technical vs Reader). Kalau tidak selaras → kirim **koreksi** → Product/Technical **ulang** (loop maks 2x).
6. **🗺️ Flow** (`_agent_flow`) — bikin kode MermaidJS → dirender jadi flowchart di halaman.
7. **🎯 Result** (`_agent_result`) — rangkum semua → 2 output.

## Output (JSON)
```json
{ "reader_teks","reader_visual","info_terverifikasi","inkonsistensi":[],
  "pertanyaan_klarifikasi":[],"produk","teknis","flow_mermaid",
  "output_awam","output_technical","konversi_error" }
```
- `output_awam` = bahasa simpel (untuk sales balas customer).
- `output_technical` = detail untuk tim teknik.
- `flow_mermaid` = kode diagram alur.

## Frontend (`bms.html`)
- Render Markdown (marked + DOMPurify) → bold/heading/**tabel** rapi.
- Render `flow_mermaid` jadi diagram (mermaid.js).
- Dropdown "Lihat proses tiap agent" menampilkan respons tiap agent.
- Tombol Salin menyalin teks bersih (tanpa markdown).

## Catatan
Pipeline panjang (≤7+ panggilan AI, ada loop koreksi) → ~1–2 menit per analisa.

## Model
Gemini `gemini-3.1-flash-lite` (vision + text). Konversi DWG via CloudConvert.
