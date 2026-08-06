"""
Mesin AI multi-agent untuk STRATEGI PENETRASI PASAR (market penetration).

Pola kerja (orchestrator + feedback loop):

    Orchestrator (rangkai brief + tentukan objektif)
        │
        ├─ RESEARCH  : Market Research → Competitor → Customer Insight
        │                    │ (hasil riset jadi acuan)
        ├─ STRATEGY  : Positioning → Pricing → Channel
        │                    │ (strategi berdasar riset)
        ├─ EXECUTION : Content → SEO/Keyword → Social/Ads → Lead Gen
        │                    │
        └─ ANALYTICS : review semua → KPI + rekomendasi iterasi → balik ke Orchestrator

Semua agent = 1 panggilan Gemini. Agent riset pakai Google Search grounding
(fallback ke pengetahuan model bila tidak didukung). Tiap agent output-nya
kelihatan (dikembalikan terpisah di JSON).
"""
import re
import json

from mesin_agent import client  # reuse client Gemini yang sudah ada

try:
    from google.genai import types
except Exception:
    types = None

MODEL = "gemini-3.1-flash-lite"


# ── Helper generik ────────────────────────────────────────────────────
def _gen(prompt):
    resp = client.models.generate_content(model=MODEL, contents=[prompt])
    return (resp.text or "").strip()


def _gen_search(prompt):
    """Generate dengan Google Search grounding; fallback ke tanpa-search."""
    if types is not None:
        try:
            cfg = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
            resp = client.models.generate_content(model=MODEL, contents=[prompt], config=cfg)
            return (resp.text or "").strip()
        except Exception:
            pass
    return _gen(prompt)


def _json(txt, fallback):
    t = re.sub(r"```json|```", "", txt or "").strip()
    try:
        d = json.loads(t)
        return d if isinstance(d, dict) else fallback
    except Exception:
        return fallback


# ── TAHAP 1: REKOMENDASI target market & lokasi (kalau user tak mengisi) ─
def rekomendasi_target(nama_produk="", deskripsi="", target_market="", lokasi=""):
    """
    Riset awal: usulkan pilihan target market & lokasi berdasarkan produk.
    Hanya mengusulkan untuk field yang KOSONG. Field yang sudah diisi user
    dihormati (perlu_* = False) dan tidak diusulkan.
    """
    perlu_target = not (target_market or "").strip()
    perlu_lokasi = not (lokasi or "").strip()

    if not perlu_target and not perlu_lokasi:
        return {"perlu_target": False, "perlu_lokasi": False,
                "target_options": [], "lokasi_options": []}

    minta = []
    if perlu_target:
        minta.append('"target_options": [ {"label":"segmen singkat","alasan":"kenapa prospektif"} , ... 4-6 item ]')
    if perlu_lokasi:
        minta.append('"lokasi_options": [ {"label":"wilayah/pasar","alasan":"kenapa cocok"} , ... 4-6 item ]')

    konteks = ""
    if target_market:
        konteks += "\nUser sudah menentukan target: " + target_market
    if lokasi:
        konteks += "\nUser sudah menentukan lokasi: " + lokasi

    prompt = (
        "Kamu Research Agent tahap awal untuk strategi penetrasi pasar. Berdasarkan produk di bawah, "
        "USULKAN pilihan " +
        ("target market (segmen pelanggan) " if perlu_target else "") +
        ("dan " if perlu_target and perlu_lokasi else "") +
        ("lokasi/pasar geografis " if perlu_lokasi else "") +
        "yang paling prospektif. Beri opsi konkret & beragam supaya user tinggal memilih (centang).\n"
        "Tiap opsi: label singkat + alasan 1 kalimat. Realistis, jangan mengada-ada.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n{ " + ", ".join(minta) + " }\n\n"
        "=== PRODUK ===\nNama: " + (nama_produk or "-") + "\nDeskripsi: " + (deskripsi or "-") + konteks
    )
    hasil = _json(_gen_search(prompt), {})

    def _bersih(items):
        out = []
        for it in (items or []):
            if isinstance(it, dict) and it.get("label"):
                out.append({"label": str(it["label"]).strip(),
                            "alasan": str(it.get("alasan", "")).strip()})
            elif isinstance(it, str) and it.strip():
                out.append({"label": it.strip(), "alasan": ""})
        return out

    return {
        "perlu_target":   perlu_target,
        "perlu_lokasi":   perlu_lokasi,
        "target_options": _bersih(hasil.get("target_options")) if perlu_target else [],
        "lokasi_options": _bersih(hasil.get("lokasi_options")) if perlu_lokasi else [],
    }


# ── ORCHESTRATOR ──────────────────────────────────────────────────────
def _orchestrator(brief):
    prompt = (
        "Kamu ORCHESTRATOR untuk sistem AI penetrasi pasar. Dari brief bisnis di bawah, rumuskan:\n"
        "1. Ringkasan bisnis (1-2 kalimat).\n"
        "2. Tujuan penetrasi pasar yang jelas & terukur (mis. rebut X% pangsa di segmen Y dalam Z bulan).\n"
        "3. Asumsi/parameter kunci yang dipakai (kalau ada info yang kurang, tulis asumsimu).\n"
        "4. Fokus utama yang harus digali tim riset.\n"
        "Bahasa Indonesia, ringkas, pakai poin '-'. JANGAN mengarang angka pasti; tandai bila estimasi.\n\n"
        "=== BRIEF BISNIS ===\n" + brief
    )
    return _gen(prompt)


# ── RESEARCH ──────────────────────────────────────────────────────────
def _market_research(brief, arahan):
    prompt = (
        "Kamu Market Research Agent. Tugas: analisis pasar untuk bisnis di bawah.\n"
        "Keluarkan (poin '-', Bahasa Indonesia):\n"
        "- Tren pasar terkini yang relevan.\n"
        "- Ukuran pasar: TAM / SAM / SOM (beri estimasi + tulis dasar asumsinya, tandai '(estimasi)').\n"
        "- Gap/peluang yang belum tergarap kompetitor.\n"
        "- Faktor pendorong & hambatan masuk pasar.\n"
        "Kalau kamu tidak yakin angka, sebut kisaran & sumbernya bila ada. Jangan mengarang data spesifik.\n\n"
        "=== BRIEF ===\n" + brief + "\n\n=== ARAHAN ORCHESTRATOR ===\n" + arahan
    )
    return _gen_search(prompt)


def _competitor_analysis(brief, kompetitor):
    extra = ("\n\n=== KOMPETITOR YANG DISEBUT USER ===\n" + kompetitor) if kompetitor else ""
    prompt = (
        "Kamu Competitor Analysis Agent. Analisis kompetitor untuk bisnis di bawah.\n"
        "Keluarkan (Bahasa Indonesia):\n"
        "- Daftar 3-6 kompetitor utama (langsung & tidak langsung).\n"
        "- Untuk tiap kompetitor: positioning, kisaran harga/pricing model, kekuatan, kelemahan, "
        "channel & campaign yang terlihat, sentimen review pelanggan (bila ada).\n"
        "- Tabel ringkas perbandingan (format Markdown | ... | ...).\n"
        "- Celah kompetitif yang bisa kita manfaatkan.\n"
        "Jangan mengarang; kalau data tidak ditemukan, tulis 'perlu diverifikasi'.\n\n"
        "=== BRIEF ===\n" + brief + extra
    )
    return _gen_search(prompt)


def _customer_insight(brief):
    prompt = (
        "Kamu Customer Insight Agent. Dari brief di bawah, hasilkan:\n"
        "- 2-3 BUYER PERSONA (nama julukan, demografi/firmografi, peran, tujuan).\n"
        "- PAIN POINT utama tiap persona + pemicu keputusan beli.\n"
        "- SEGMENTASI audiens (berdasarkan kebutuhan/perilaku), urutkan dari yang paling prospektif.\n"
        "- Pesan/hook yang paling nyambung untuk tiap segmen.\n"
        "Bahasa Indonesia, terstruktur. Realistis, jangan mengada-ada.\n\n"
        "=== BRIEF ===\n" + brief
    )
    return _gen(prompt)


# ── STRATEGY ──────────────────────────────────────────────────────────
def _positioning(brief, riset):
    prompt = (
        "Kamu Positioning Agent. Berdasarkan brief + hasil riset di bawah, rumuskan:\n"
        "- VALUE PROPOSITION inti (1 kalimat kuat).\n"
        "- Diferensiasi vs kompetitor (kenapa pilih kita, bukan mereka).\n"
        "- Positioning statement (format: Untuk [target] yang [kebutuhan], [produk] adalah [kategori] yang [benefit], "
        "tidak seperti [kompetitor], kami [pembeda]).\n"
        "- 3-5 pesan kunci (key messages).\n"
        "Bahasa Indonesia. Harus konsisten dengan riset & pain point pelanggan.\n\n"
        "=== BRIEF ===\n" + brief + "\n\n=== HASIL RISET ===\n" + riset
    )
    return _gen(prompt)


def _pricing(brief, riset, positioning):
    prompt = (
        "Kamu Pricing Agent. Rekomendasikan strategi harga untuk penetrasi pasar.\n"
        "Keluarkan (Bahasa Indonesia):\n"
        "- Strategi harga yang disarankan (mis. penetration pricing, freemium, bundling, tiered) + alasannya.\n"
        "- Struktur/paket harga usulan (kalau bisa beri kisaran angka + tandai '(estimasi)').\n"
        "- Taktik promo awal untuk merebut pasar (diskon perkenalan, trial, dll).\n"
        "- Risiko strategi harga ini & cara mitigasinya.\n"
        "Harus selaras dengan positioning & kondisi kompetitor. Jangan mengarang biaya internal.\n\n"
        "=== BRIEF ===\n" + brief + "\n\n=== RISET ===\n" + riset +
        "\n\n=== POSITIONING ===\n" + positioning
    )
    return _gen(prompt)


def _channel_strategy(brief, riset, personas):
    prompt = (
        "Kamu Channel Strategy Agent. Tentukan channel go-to-market paling efektif.\n"
        "Keluarkan (Bahasa Indonesia):\n"
        "- Rekomendasi channel diurutkan prioritas (organic/SEO, paid ads, social, marketplace, partnership, "
        "sales langsung, email, dll) + alasan kenapa cocok untuk persona ini.\n"
        "- Perkiraan effort vs dampak tiap channel (tinggi/sedang/rendah).\n"
        "- Channel mix untuk 90 hari pertama (fokus di mana dulu).\n"
        "Selaraskan dengan persona & segmentasi. Realistis untuk skala bisnis di brief.\n\n"
        "=== BRIEF ===\n" + brief + "\n\n=== RISET & PERSONA ===\n" + riset + "\n" + personas
    )
    return _gen(prompt)


# ── EXECUTION ─────────────────────────────────────────────────────────
def _seo_keyword(brief, riset, channel):
    prompt = (
        "Kamu SEO/Keyword Agent. Riset kata kunci untuk penetrasi pasar bisnis di bawah.\n"
        "Keluarkan (Bahasa Indonesia):\n"
        "- 10-15 keyword relevan, kelompokkan: high-intent (siap beli), informational, dan long-tail.\n"
        "- Untuk tiap kelompok, sebut estimasi tingkat persaingan (tinggi/sedang/rendah) & maksud pencari.\n"
        "- 5 ide topik konten/artikel SEO yang menyasar keyword tersebut.\n"
        "- Saran on-page singkat (judul, meta, struktur).\n"
        "Tandai angka volume sebagai '(estimasi)' bila tidak pasti.\n\n"
        "=== BRIEF ===\n" + brief + "\n\n=== RISET ===\n" + riset + "\n\n=== CHANNEL ===\n" + channel
    )
    return _gen_search(prompt)


def _content(brief, positioning, personas, seo):
    prompt = (
        "Kamu Content Agent. Buat materi kampanye siap pakai berdasarkan positioning, persona, & keyword.\n"
        "Keluarkan (Bahasa Indonesia):\n"
        "- 3 headline/hook utama.\n"
        "- 1 draf copywriting iklan pendek (untuk social/ads).\n"
        "- 1 kerangka artikel SEO (judul + H2/H3 + poin isi) yang memakai keyword dari SEO Agent.\n"
        "- 3 ide caption social media + CTA.\n"
        "Nada sesuai positioning & pain point persona. Jangan mengulang, buat konkret & tajam.\n\n"
        "=== POSITIONING ===\n" + positioning + "\n\n=== PERSONA ===\n" + personas +
        "\n\n=== KEYWORD/SEO ===\n" + seo + "\n\n=== BRIEF ===\n" + brief
    )
    return _gen(prompt)


def _social_ads(brief, channel, personas, content):
    prompt = (
        "Kamu Social/Ads Agent. Susun rencana kampanye iklan & social media.\n"
        "Keluarkan (Bahasa Indonesia):\n"
        "- Rekomendasi platform ads (Meta, Google, TikTok, LinkedIn, dll) sesuai persona + alasan.\n"
        "- Struktur campaign (objective, targeting, format kreatif).\n"
        "- Jadwal posting 1 minggu contoh (tabel Markdown: hari | platform | jenis konten).\n"
        "- 2 varian copy untuk A/B testing + metrik yang dibandingkan.\n"
        "- Saran alokasi budget kasar antar platform (persentase, tandai '(estimasi)').\n"
        "Selaraskan dengan channel strategy & materi content.\n\n"
        "=== CHANNEL ===\n" + channel + "\n\n=== PERSONA ===\n" + personas +
        "\n\n=== CONTENT ===\n" + content + "\n\n=== BRIEF ===\n" + brief
    )
    return _gen(prompt)


def _lead_gen(brief, personas, channel):
    prompt = (
        "Kamu Lead Gen Agent. Rancang cara cari & kualifikasi prospek.\n"
        "Keluarkan (Bahasa Indonesia):\n"
        "- Sumber prospek per persona (mis. direktori industri, LinkedIn, komunitas, event, marketplace).\n"
        "- Kriteria kualifikasi lead (framework BANT/ICP: budget, authority, need, timeline / ideal customer profile).\n"
        "- Contoh 1 pesan outreach pertama (email/DM) yang personal & tidak spammy.\n"
        "- Alur follow-up singkat (kapan & isinya apa).\n"
        "- Metrik lead gen yang dipantau (MQL, SQL, conversion rate).\n"
        "Realistis sesuai channel & persona.\n\n"
        "=== PERSONA ===\n" + personas + "\n\n=== CHANNEL ===\n" + channel + "\n\n=== BRIEF ===\n" + brief
    )
    return _gen(prompt)


# ── ANALYTICS (feedback loop ke Orchestrator) ─────────────────────────
def _analytics(brief, semua):
    prompt = (
        "Kamu Analytics Agent — penutup yang memberi FEEDBACK LOOP ke Orchestrator. Baca SELURUH hasil agent "
        "di bawah, lalu keluarkan JSON.\n"
        "Nilai apakah strategi antar-agent SUDAH SELARAS & MASUK AKAL (positioning cocok dg riset, pricing cocok "
        "dg positioning, channel cocok dg persona, execution cocok dg strategi). Beri KPI yang harus dipantau, "
        "rencana 30/60/90 hari, dan rekomendasi iterasi.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{\"selaras\": true/false, "
        "\"catatan_inkonsistensi\": [\"...\"], "
        "\"kpi\": [\"...\"], "
        "\"rencana_30_60_90\": \"teks Markdown rencana 30/60/90 hari\", "
        "\"rekomendasi_iterasi\": [\"...\"], "
        "\"ringkasan_eksekutif\": \"3-5 kalimat rangkuman strategi penetrasi pasar untuk pengambil keputusan\"}\n\n"
        "=== BRIEF ===\n" + brief + "\n\n=== SEMUA HASIL AGENT ===\n" + semua
    )
    return _json(_gen(prompt), {
        "selaras": True, "catatan_inkonsistensi": [], "kpi": [],
        "rencana_30_60_90": "", "rekomendasi_iterasi": [], "ringkasan_eksekutif": "",
    })


# ── ACTION PLAN (kesimpulan tindakan konkret) ─────────────────────────
def _action_plan(brief, semua):
    prompt = (
        "Kamu Action Plan Agent. Dari SELURUH hasil strategi di bawah, simpulkan menjadi DAFTAR TINDAKAN KONKRET "
        "yang harus dilakukan pemilik bisnis. Harus spesifik & bisa langsung dieksekusi.\n"
        "Untuk tiap tindakan jawab: APA yang dilakukan, DI MANA (channel/platform/tempat), BERAPA (jumlah/frekuensi, "
        "mis. '4 konten/minggu di Instagram'), PRIORITAS (Tinggi/Sedang/Rendah), dan catatan singkat bila perlu.\n"
        "Urutkan dari prioritas tertinggi. Realistis sesuai skala bisnis & budget di brief.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{ \"ringkas\": \"1-2 kalimat arahan utama\", "
        "\"aksi\": [ {\"tindakan\":\"...\", \"dimana\":\"...\", \"jumlah\":\"...\", \"prioritas\":\"Tinggi/Sedang/Rendah\", \"catatan\":\"...\"} ] }\n\n"
        "=== BRIEF ===\n" + brief + "\n\n=== SEMUA HASIL STRATEGI ===\n" + semua
    )
    hasil = _json(_gen(prompt), {"ringkas": "", "aksi": []})
    aksi = []
    for a in (hasil.get("aksi") or []):
        if isinstance(a, dict) and (a.get("tindakan") or a.get("dimana")):
            aksi.append({
                "tindakan":  str(a.get("tindakan", "")).strip(),
                "dimana":    str(a.get("dimana", "")).strip(),
                "jumlah":    str(a.get("jumlah", "")).strip(),
                "prioritas": str(a.get("prioritas", "")).strip(),
                "catatan":   str(a.get("catatan", "")).strip(),
            })
    return {"ringkas": (hasil.get("ringkas") or "").strip(), "aksi": aksi}


# ── TIMELINE PLANNER (rencana waktu berbentuk timeline) ───────────────
def _timeline(brief, semua, action):
    prompt = (
        "Kamu Timeline Planner Agent. Susun RENCANA WAKTU (timeline) eksekusi penetrasi pasar berdasarkan strategi & "
        "daftar tindakan di bawah. Bagi menjadi beberapa fase berurutan (mis. Minggu 1-2, Minggu 3-4, Bulan 2, Bulan 3, "
        "dst) sepanjang kira-kira 90 hari.\n"
        "Tiap fase: periode, fokus/judul fase, dan daftar aktivitas konkret pada fase itu. Aktivitas harus selaras "
        "dengan action plan. Realistis, jangan menumpuk semua di satu fase.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{ \"timeline\": [ {\"periode\":\"mis. Minggu 1-2\", \"fokus\":\"judul fase\", \"aktivitas\":[\"...\",\"...\"]} ] }\n\n"
        "=== BRIEF ===\n" + brief +
        "\n\n=== ACTION PLAN ===\n" + json.dumps(action, ensure_ascii=False) +
        "\n\n=== SEMUA HASIL STRATEGI ===\n" + semua
    )
    hasil = _json(_gen(prompt), {"timeline": []})
    fases = []
    for f in (hasil.get("timeline") or []):
        if isinstance(f, dict) and (f.get("periode") or f.get("fokus")):
            akt = f.get("aktivitas") or []
            if isinstance(akt, str):
                akt = [akt]
            fases.append({
                "periode":   str(f.get("periode", "")).strip(),
                "fokus":     str(f.get("fokus", "")).strip(),
                "aktivitas": [str(x).strip() for x in akt if str(x).strip()],
            })
    return fases


# ── PIPELINE UTAMA ────────────────────────────────────────────────────
def analisa_penetrasi(nama_produk="", deskripsi="", target_market="",
                      lokasi="", kompetitor="", budget="", tujuan=""):
    # Rangkai brief terstruktur dari form
    brief = (
        "Nama produk/jasa: " + (nama_produk or "-") +
        "\nDeskripsi: " + (deskripsi or "-") +
        "\nTarget market: " + (target_market or "-") +
        "\nLokasi/pasar: " + (lokasi or "-") +
        "\nKompetitor (bila disebut): " + (kompetitor or "-") +
        "\nBudget (bila disebut): " + (budget or "-") +
        "\nTujuan/goal: " + (tujuan or "-")
    )

    # 0) Orchestrator
    arahan = _orchestrator(brief)

    # 1) RESEARCH
    market   = _market_research(brief, arahan)
    kompetit = _competitor_analysis(brief, kompetitor)
    customer = _customer_insight(brief)
    riset = ("MARKET:\n" + market + "\n\nKOMPETITOR:\n" + kompetit +
             "\n\nCUSTOMER INSIGHT:\n" + customer)

    # 2) STRATEGY
    positioning = _positioning(brief, riset)
    pricing     = _pricing(brief, riset, positioning)
    channel     = _channel_strategy(brief, riset, customer)

    # 3) EXECUTION
    seo       = _seo_keyword(brief, riset, channel)
    content   = _content(brief, positioning, customer, seo)
    social    = _social_ads(brief, channel, customer, content)
    lead      = _lead_gen(brief, customer, channel)

    # 4) ANALYTICS (feedback loop)
    semua = (
        "[ORCHESTRATOR]\n" + arahan +
        "\n\n[MARKET RESEARCH]\n" + market +
        "\n\n[COMPETITOR]\n" + kompetit +
        "\n\n[CUSTOMER INSIGHT]\n" + customer +
        "\n\n[POSITIONING]\n" + positioning +
        "\n\n[PRICING]\n" + pricing +
        "\n\n[CHANNEL]\n" + channel +
        "\n\n[SEO/KEYWORD]\n" + seo +
        "\n\n[CONTENT]\n" + content +
        "\n\n[SOCIAL/ADS]\n" + social +
        "\n\n[LEAD GEN]\n" + lead
    )
    analytics = _analytics(brief, semua)

    # 5) ACTION PLAN + TIMELINE (kesimpulan tindakan + rencana waktu)
    semua_plus = semua + "\n\n[ANALYTICS RINGKAS]\n" + (analytics.get("ringkasan_eksekutif") or "") + \
        "\n" + (analytics.get("rencana_30_60_90") or "")
    action   = _action_plan(brief, semua_plus)
    timeline = _timeline(brief, semua_plus, action)

    return {
        "orchestrator":        arahan,
        "market_research":     market,
        "competitor_analysis": kompetit,
        "customer_insight":    customer,
        "positioning":         positioning,
        "pricing":             pricing,
        "channel_strategy":    channel,
        "seo_keyword":         seo,
        "content":             content,
        "social_ads":          social,
        "lead_gen":            lead,
        "analytics": {
            "selaras":              analytics.get("selaras", True),
            "catatan_inkonsistensi": analytics.get("catatan_inkonsistensi", []) or [],
            "kpi":                  analytics.get("kpi", []) or [],
            "rencana_30_60_90":     analytics.get("rencana_30_60_90", "") or "",
            "rekomendasi_iterasi":  analytics.get("rekomendasi_iterasi", []) or [],
        },
        "ringkasan_eksekutif": (analytics.get("ringkasan_eksekutif") or "").strip(),
        "action_plan":         action,
        "timeline":            timeline,
    }
