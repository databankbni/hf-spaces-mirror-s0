# Agent: Market Penetration Strategist (multi-agent + feedback loop)

Sistem 11 AI agent untuk menyusun strategi penetrasi pasar dari profil bisnis: riset → strategi → eksekusi → analitik (feedback loop).

## File
- Backend: `mesin_penetrasi.py` — fungsi `analisa_penetrasi(nama_produk, deskripsi, target_market, lokasi, kompetitor, budget, tujuan)`.
- Endpoint: `POST /penetrasi-market` di `main.py`.
- Frontend: `agent-penetrasi/penetrasi.html` (form terstruktur, halaman WP terpisah).

## Input (JSON, form terstruktur)
```json
{ "nama_produk":"...", "deskripsi":"...", "target_market":"...",
  "lokasi":"", "kompetitor":"", "budget":"", "tujuan":"" }
```
Wajib: `nama_produk`, `deskripsi`. Sisanya opsional.

### Alur 2 tahap (target market & lokasi)
- Kalau `target_market`/`lokasi` **diisi** → agent langsung ikutin.
- Kalau **kosong** → frontend panggil `POST /penetrasi-rekomendasi` dulu (fungsi `rekomendasi_target`) → agent riset & usulkan opsi (checkbox). User centang → nilai terpilih dikirim ke `/penetrasi-market` untuk full pipeline.
- Kompetitor, budget, goal → opsional biasa (tanpa checkbox).

`POST /penetrasi-rekomendasi` → `{ perlu_target, perlu_lokasi, target_options:[{label,alasan}], lokasi_options:[{label,alasan}] }` (hanya field kosong yang diusulkan).

## Pipeline (urutan)
**🧭 Orchestrator** — rangkai brief, tetapkan objektif & arahan riset.

**🔬 Research** (pakai Google Search grounding, fallback pengetahuan model):
1. **Market Research** — tren, TAM/SAM/SOM (estimasi), gap pasar.
2. **Competitor Analysis** — pricing, positioning, campaign, review, tabel banding.
3. **Customer Insight** — buyer persona, pain point, segmentasi.

**🧠 Strategy** (berdasar hasil riset):
4. **Positioning** — value proposition & diferensiasi.
5. **Pricing** — strategi harga (penetration/bundling/tiered) + risiko.
6. **Channel Strategy** — channel go-to-market prioritas, mix 90 hari.

**⚙️ Execution** (berdasar strategi):
7. **SEO/Keyword** — riset kata kunci (high-intent/info/long-tail) + ide konten.
8. **Content** — headline, copywriting, kerangka artikel SEO, caption.
9. **Social/Ads** — rencana campaign, jadwal posting, A/B test, alokasi budget.
10. **Lead Gen** — sumber prospek, kriteria kualifikasi (ICP/BANT), outreach, follow-up.

**📈 Analytics** (feedback loop ke Orchestrator) — cek keselarasan antar-agent, KPI, rencana 30/60/90 hari, rekomendasi iterasi, ringkasan eksekutif.

**✅ Action Plan** — simpulkan jadi daftar tindakan konkret: apa, di mana (channel), berapa (jumlah/frekuensi), prioritas, catatan (dirender jadi tabel).

**🗓️ Timeline Planner** — susun rencana waktu ± 90 hari berbentuk fase berurutan (periode + fokus + aktivitas), dirender jadi timeline visual.

## Output (JSON)
```json
{ "orchestrator","market_research","competitor_analysis","customer_insight",
  "positioning","pricing","channel_strategy",
  "seo_keyword","content","social_ads","lead_gen",
  "analytics": { "selaras", "catatan_inkonsistensi":[], "kpi":[],
                 "rencana_30_60_90", "rekomendasi_iterasi":[] },
  "ringkasan_eksekutif",
  "action_plan": { "ringkas", "aksi":[{"tindakan","dimana","jumlah","prioritas","catatan"}] },
  "timeline": [ {"periode","fokus","aktivitas":[...]} ] }
```

## Frontend (`penetrasi.html`)
- Form terstruktur → hasil dikelompokkan per fase (Research / Strategy / Execution / Analytics) + ringkasan eksekutif di atas (badge selaras/perlu-iterasi).
- Render Markdown (marked + DOMPurify) → tabel/heading/bold rapi. Tombol Salin per kartu.

## Catatan
Pipeline panjang (~12 panggilan AI) → **~1–3 menit** per analisa. Agent riset butuh Google Search grounding (fallback otomatis bila tak didukung tier).

## Model
Gemini `gemini-3.1-flash-lite` (text + search grounding).
