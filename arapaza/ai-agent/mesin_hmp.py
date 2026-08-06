"""
Mesin AI multi-agent untuk tim SALES & SERVICE produk HMP (Magdeburger Pruefgeraetebau GmbH).

HMP = alat uji geoteknik: daya dukung & pemadatan tanah untuk konstruksi jalan/earthworks
(Light Weight Deflectometer / Leichtes Fallgewichtsgeraet LFG -> Evd; Static Plate Load Test
-> Ev1/Ev2). Pola sama seperti HOBO/Fakopp: chat multi-turn + Router + Compare + Riset Harga + Budget.
Agent Product mengecek website HMP via Google Search grounding.
"""
import re
import os
import base64
import binascii

from mesin_agent import client

try:
    from google.genai import types
except Exception:
    types = None

MODEL = "gemini-3.1-flash-lite"

# Website acuan Agent Product (bisa diubah via Secret; tambah distributor bila ada)
HMP_SITES = os.getenv("HMP_SITES", "hmp-online.de").strip()


def _gen(prompt, file_bytes=None, mime=None):
    contents = [prompt]
    if file_bytes and types is not None:
        contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime or "image/png"))
    resp = client.models.generate_content(model=MODEL, contents=contents)
    return (resp.text or "").strip()


def _gen_search(prompt):
    if types is not None:
        try:
            cfg = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            resp = client.models.generate_content(model=MODEL, contents=[prompt], config=cfg)
            return (resp.text or "").strip()
        except Exception:
            pass
    return _gen(prompt)


def _json(txt, fallback):
    import json
    t = re.sub(r"```json|```", "", txt or "").strip()
    try:
        d = json.loads(t)
        return d if isinstance(d, dict) else fallback
    except Exception:
        return fallback


# ── Agent 1: Reader teks ──────────────────────────────────────────────
def _agent_reader_teks(chat):
    if not chat:
        return "(Tidak ada teks chat dari customer.)"
    prompt = (
        "Kamu Agent Reader (teks) untuk tim sales & service alat HMP (uji daya dukung & pemadatan TANAH). Baca chat "
        "customer, lalu ekstrak SEMUA info penting secara terstruktur (poin '-'): tujuan pengujian (uji pemadatan/"
        "kepadatan tanah, daya dukung/bearing capacity, modulus deformasi dinamis Evd, uji beban pelat statis Ev1/Ev2, "
        "QC subgrade/timbunan), jenis proyek (jalan, rel, timbunan/earthworks, fondasi, area parkir), jenis material/"
        "lapisan tanah, jumlah titik uji, standar yang diminta (mis. DIN 18134, TP BF-StB, ASTM), kebutuhan software/"
        "printer/pelatihan/kalibrasi/sertifikat, budget/timeline bila ada, serta hal yang ambigu. JANGAN menyimpulkan "
        "solusi, hanya rangkum yang tertulis.\n\n"
        "TELITI (utamakan BENAR walau lebih lama): baca ulang chat pelan-pelan, verifikasi tiap angka, satuan, dan "
        "model/tipe/istilah sebelum ditulis; jangan sampai salah baca atau tertukar antar item.\n\n"
        "=== CHAT CUSTOMER ===\n" + chat
    )
    return _gen(prompt)


# ── Agent 2: Reader visual ────────────────────────────────────────────
def _agent_reader_visual(file_bytes, mime):
    if not file_bytes:
        return "(Tidak ada gambar/datasheet/PDF dari customer.)"
    prompt = (
        "Kamu Agent Reader (visual) untuk tim HMP. Baca gambar/PDF/datasheet terlampir. Ekstrak info terstruktur "
        "(poin '-'): jenis dokumen (foto lokasi proyek/tanah, kondisi lapangan, datasheet alat, hasil uji/laporan Evd "
        "atau Ev1/Ev2, spesifikasi/RKS), objek & kondisi terlihat (jenis lapisan, area uji), nilai/spesifikasi yang "
        "tertera, standar yang disebut, label/anotasi penting. Kalau ada bagian tidak terbaca, katakan jujur. Baca ulang & verifikasi tiap angka, nilai uji, satuan, standar, dan label yang terlihat sebelum ditulis; utamakan BENAR walau lebih lama. JANGAN "
        "mengarang."
    )
    return _gen(prompt, file_bytes, mime)


# ── Agent Product (fokus HMP, cek website) ────────────────────────────
def _agent_product(info, koreksi=""):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB dipatuhi) ===\n" + koreksi) if koreksi else ""
    prompt = (
        "Kamu Agent Product untuk produk HMP (Magdeburger Pruefgeraetebau GmbH). Berdasarkan kebutuhan (dari Reader) di "
        "bawah, rekomendasikan produk HMP yang tepat untuk tiap kebutuhan.\n"
        "UTAMAKAN mencari & memverifikasi dari website HMP: " + HMP_SITES + ". "
        "Contoh lini produk HMP (verifikasi & sesuaikan): Light Weight Deflectometer / Leichtes Fallgewichtsgeraet "
        "(LFG) untuk uji beban pelat DINAMIS -> modulus Evd (uji cepat pemadatan tanah di lapangan); alat Static Plate "
        "Load Test / Plattendruckgeraet untuk uji beban pelat STATIS -> Ev1/Ev2; beserta software evaluasi, printer, "
        "pelat beban, dan aksesori.\n"
        "Untuk tiap rekomendasi: nama produk + fungsi + kenapa cocok + standar yang dipenuhi (mis. DIN 18134 untuk "
        "statis, TP BF-StB Teil B 8.3 / DIN untuk LWD) bila kamu yakin.\n"
        "Produk HARUS sesuai kebutuhan Reader (mis. butuh uji cepat lapangan -> LWD/LFG; butuh Ev1/Ev2 formal -> Static "
        "Plate Load Test). Jangan mengarang model/seri yang tidak kamu yakini; kalau ragu sebut kategori & tandai "
        "'perlu verifikasi'.\n\n"
        "=== KEBUTUHAN (DARI READER) ===\n" + info + fb
    )
    return _gen_search(prompt)


# ── Agent Technical (metode uji, prosedur, standar, BOM) ──────────────
def _agent_technical(info, produk, koreksi=""):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB dipatuhi) ===\n" + koreksi) if koreksi else ""
    prompt = (
        "Kamu Agent Technical HMP. Dari kebutuhan + produk terpilih di bawah, susun:\n"
        "1. METODE & PROSEDUR UJI: cara kerja & langkah di lapangan (mis. LWD: jatuhkan beban ke pelat, ukur defleksi "
        "-> hitung Evd; Static Plate Load Test: pembebanan bertahap dgn dongkrak & reaksi kendaraan -> Ev1/Ev2), "
        "persiapan titik uji, jumlah titik disarankan, standar acuan (DIN 18134, TP BF-StB, dll).\n"
        "2. BILL OF MATERIALS: daftar alat utama + pelat beban + software/printer + aksesori + estimasi jumlah unit. "
        "Bila jumlah titik/proyek tidak pasti, beri estimasi + tulis asumsinya.\n"
        "3. CATATAN TEKNIS: interpretasi hasil (nilai Evd, Ev2/Ev1, kriteria lulus/pemadatan), faktor lapangan (jenis "
        "tanah, kadar air, ketebalan lapisan), hal penting saat pengujian & keselamatan.\n"
        "Bahasa Indonesia teknis yang jelas. Jangan mengarang angka pasti; tandai estimasi.\n\n"
        "=== KEBUTUHAN ===\n" + info + "\n\n=== PRODUK TERPILIH ===\n" + produk + fb
    )
    return _gen(prompt)


# ── Agent Service (kalibrasi, software, training, interpretasi) ───────
def _agent_service(info, produk, koreksi=""):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB dipatuhi) ===\n" + koreksi) if koreksi else ""
    prompt = (
        "Kamu Agent Service untuk produk HMP (after-sales). Dari kebutuhan + produk di bawah, berikan info service "
        "relevan:\n"
        "- KALIBRASI & SERTIFIKAT: LWD/plate load test butuh kalibrasi berkala (biasanya tahunan) + sertifikat agar "
        "hasil sah; jelaskan pentingnya & interval umum.\n"
        "- SOFTWARE: setup & penggunaan software evaluasi HMP, transfer data, cetak laporan Evd/Ev.\n"
        "- TRAINING: kebutuhan pelatihan operator (prosedur uji & pembacaan hasil sesuai standar).\n"
        "- TROUBLESHOOTING: masalah umum (sensor/akselerometer, hasil tidak konsisten, baterai, printer) + langkah "
        "diagnosa.\n"
        "- GARANSI & PERAWATAN: umum untuk produk HMP + tips perawatan alat & pelat. Jangan mengarang kebijakan "
        "garansi spesifik; sebut 'konfirmasi ke distributor'.\n"
        "Kalau chat tidak menyangkut service, cukup beri tips singkat kalibrasi, software & interpretasi.\n\n"
        "=== KEBUTUHAN ===\n" + info + "\n\n=== PRODUK ===\n" + produk + fb
    )
    return _gen(prompt)


# ── Agent Checker (KOORDINATOR) ───────────────────────────────────────
def _agent_checker_all(teks_info, visual_info, produk, teknis, service):
    prompt = (
        "Kamu Agent Checker (KOORDINATOR) untuk tim HMP. Pastikan SEMUA hasil agent SALING KONSISTEN dan sesuai apa "
        "yang dibaca Reader. Reader adalah acuan kebenaran kebutuhan customer.\n\n"
        "Periksa:\n"
        "- Apakah PRODUK HMP yang direkomendasikan sesuai TUJUAN uji Reader? (mis. butuh uji cepat lapangan -> LWD/LFG; "
        "butuh Ev1/Ev2 formal DIN 18134 -> Static Plate Load Test). Salah pasang metode = tidak konsisten.\n"
        "- Apakah TECHNICAL (metode/standar/BOM) sesuai kebutuhan & produk?\n"
        "- Apakah SERVICE relevan dengan konteks?\n"
        "- Kontradiksi antar agent atau info yang miss/ambigu?\n\n"
        "Kalau ADA yang tidak sesuai, tulis INSTRUKSI KOREKSI spesifik untuk agent terkait.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{\"konsisten\": true/false, \"koreksi_product\":\"(kosong bila benar)\", \"koreksi_technical\":\"(kosong bila benar)\", "
        "\"koreksi_service\":\"(kosong bila benar)\", \"inkonsistensi\":[\"...\"], \"pertanyaan_klarifikasi\":[\"...\"], "
        "\"info_terverifikasi\":\"ringkasan kebutuhan final yang sudah selaras\"}\n\n"
        "=== READER TEKS ===\n" + teks_info +
        "\n\n=== READER VISUAL ===\n" + visual_info +
        "\n\n=== HASIL PRODUCT ===\n" + produk +
        "\n\n=== HASIL TECHNICAL ===\n" + teknis +
        "\n\n=== HASIL SERVICE ===\n" + service
    )
    return _json(_gen(prompt), {
        "konsisten": True, "koreksi_product": "", "koreksi_technical": "", "koreksi_service": "",
        "inkonsistensi": [], "pertanyaan_klarifikasi": [],
        "info_terverifikasi": teks_info + "\n" + visual_info,
    })


# ── Agent Flow (flowchart Mermaid) ────────────────────────────────────
def _agent_flow(teknis):
    prompt = (
        "Kamu Agent Flow. Dari deskripsi metode/teknis di bawah, buat DIAGRAM ALUR (flowchart) proses pengujian HMP "
        "(uji tanah) dalam sintaks MermaidJS.\n"
        "Aturan:\n"
        "- Baris pertama WAJIB: flowchart TD  (boleh LR bila lebih pas).\n"
        "- Node = tahap/komponen (persiapan titik, pelat beban, alat LWD/plate load, sensor, software, hasil/laporan). "
        "Pakai ID pendek + label dalam kurung siku, mis. A1[LWD LFG]. HINDARI tanda kutip, koma, titik dua, kurung "
        "bulat, karakter khusus di label.\n"
        "- Edge = urutan proses/aliran data; beri label singkat bila perlu.\n"
        "- Maksimal ~15 node, ringkas & jelas.\n"
        "- Kembalikan HANYA kode Mermaid (tanpa backtick, tanpa penjelasan).\n\n"
        "=== METODE/TEKNIS ===\n" + teknis
    )
    out = _gen(prompt)
    return re.sub(r"```mermaid|```", "", out or "").strip()


# ── Agent Compare (cari produk alternatif merek lain) ─────────────────
def _agent_compare(info, produk):
    prompt = (
        "Kamu Agent Compare untuk tim sales HMP. Berdasarkan kebutuhan + produk HMP yang direkomendasikan di bawah, "
        "cari produk ALTERNATIF dari MEREK LAIN yang fungsinya mirip / setara untuk tiap kebutuhan (supaya sales punya "
        "opsi selain HMP).\n"
        "PRIORITAS ASAL PRODUK (WAJIB, berurutan): (1) utamakan produk BARAT dulu — Eropa & Amerika; (2) kalau tidak "
        "ada padanan Barat yang cocok, baru cari produk CHINA; (3) kalau tetap tidak ada, baru produk LOKAL "
        "(Indonesia). Untuk tiap alternatif, SEBUTKAN asal/negara mereknya.\n"
        "Cari & verifikasi di web. Contoh pembanding sesuai metode: Light Weight Deflectometer / LWD -> Zorn "
        "Instruments (ZFG, Jerman), TERRATEC, Dynatest, Controls Group / Matest (Italia); Static Plate Load Test -> "
        "Controls, Matest, dll. Sebutkan beda ringkas (standar didukung, software, kepraktisan).\n"
        "Untuk tiap produk HMP, beri 1-2 padanan + kenapa setara + perbedaan utama. Buat TABEL Markdown: "
        "Kebutuhan | Produk HMP | Alternatif (merek+model+negara) | Perbedaan utama (standar/hasil/kepraktisan).\n"
        "Realistis; jangan mengarang model. Kalau ragu, sebut kategori + tandai 'perlu verifikasi'.\n\n"
        "=== KEBUTUHAN ===\n" + info + "\n\n=== PRODUK HMP TERPILIH ===\n" + produk
    )
    return _gen_search(prompt)


# ── Agent Riset Harga (search web real-time untuk harga pasar) ────────
def _agent_harga_riset(produk, compare):
    prompt = (
        "Kamu Agent Riset Harga. Tugasmu MENCARI HARGA PASAR TERKINI (real, hari ini) dari WEB untuk SETIAP produk di "
        "bawah — baik produk HMP maupun alternatif merek lain.\n"
        "Untuk tiap produk cari: harga jual/list ke END-USER, mata uang aslinya (USD/EUR/dll), dan sumber/domain bila "
        "ada (toko resmi, distributor, marketplace B2B).\n"
        "PENTING: alat uji geoteknik (LWD/plate load test) ini PREMIUM (sering ribuan sampai puluhan ribu EUR). JANGAN "
        "menebak terlalu murah. Kalau angka pasti tak ketemu, beri RENTANG realistis berdasar produk sekelas + tandai "
        "'perkiraan'. Konversikan kasar ke IDR (asumsi kurs USD≈Rp 16.000, EUR≈Rp 17.500 — sebutkan asumsimu).\n"
        "Keluarkan daftar per produk: nama | harga pasar (mata uang asli) | ~Rp | sumber/catatan. Jujur soal "
        "ketidakpastian; jangan mengarang angka pasti.\n\n"
        "=== PRODUK HMP ===\n" + produk +
        "\n\n=== ALTERNATIF (COMPARE) ===\n" + compare
    )
    return _gen_search(prompt)


# ── Agent Budget (estimasi modal & penawaran dari harga pasar) ────────
def _agent_budget(info, produk, compare, harga):
    prompt = (
        "Kamu Agent Budget untuk Taharica (distributor alat ukur). Basiskan estimasi pada HARGA PASAR hasil riset di "
        "bawah (jangan mengarang angka baru yang jauh berbeda).\n"
        "LOGIKA HARGA (WAJIB, jangan sampai under-price):\n"
        "- HARGA PENAWARAN ke customer ≈ HARGA PASAR end-user. Boleh sedikit di atas untuk layanan/garansi/kalibrasi "
        "lokal. JANGAN menetapkan penawaran JAUH DI BAWAH harga pasar.\n"
        "- HARGA MODAL (biaya beli Taharica) = HARGA PENAWARAN DIKURANGI margin distributor ~20-35%. Jadi modal SELALU "
        "LEBIH KECIL dari penawaran, dan penawaran mendekati harga pasar.\n"
        "- Sanity check: modal < penawaran, penawaran tidak lebih rendah dari harga pasar tanpa alasan. Sebut mata uang "
        "& konversi Rp. Beri RENTANG. Tandai '(estimasi, wajib diverifikasi)'. Catat: bea masuk, kurs, kuantitas, dan "
        "kebijakan margin asli Taharica dapat mengubah angka.\n\n"
        "Hasilkan DUA bagian (mencakup HMP DAN alternatif, buat tabel: produk | harga pasar | modal | penawaran):\n"
        "- modal: kisaran harga beli Taharica per item + total kasar.\n"
        "- penawaran: kisaran harga jual ke customer per item + total kasar.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): {\"modal\":\"...markdown...\", \"penawaran\":\"...markdown...\"}\n\n"
        "=== HARGA PASAR (HASIL RISET WEB) ===\n" + harga +
        "\n\n=== KEBUTUHAN ===\n" + info +
        "\n\n=== PRODUK HMP ===\n" + produk +
        "\n\n=== ALTERNATIF (COMPARE) ===\n" + compare
    )
    return _json(_gen_search(prompt), {"modal": "", "penawaran": ""})


# ── Agent Result (3 output: sales HMP, sales produk lain, teknis) ─────
def _agent_result(info, inkon, tanya, produk, teknis, service, compare, budget, instruksi=""):
    modal = (budget or {}).get("modal", "") or "-"
    penawaran = (budget or {}).get("penawaran", "") or "-"
    fb = ("\n\n=== PERMINTAAN LANJUTAN DARI USER (utamakan penuhi ini di jawaban) ===\n" + instruksi) if instruksi else ""
    prompt = (
        "Kamu Agent Result untuk tim sales & service HMP. Berdasarkan SELURUH data di bawah, buat TIGA output Bahasa "
        "Indonesia:\n"
        "1. output_awam_hobo: rekomendasi balasan untuk SALES memakai produk HMP (bahasa sederhana, siap dipakai "
        "membalas customer; sebut produk HMP + poin service + kisaran harga penawaran bila relevan).\n"
        "2. output_awam_lain: rekomendasi balasan versi PRODUK ALTERNATIF (merek lain dari Agent Compare) sebagai opsi "
        "kedua (sebut merek+model + kelebihan/kekurangan + kisaran harga penawaran).\n"
        "3. output_technical: rangkuman teknis mendetail untuk tim teknik/service (produk HMP + alternatif, metode/"
        "standar/BOM, kalibrasi/software/training, perbandingan teknis, dan ringkasan estimasi biaya modal vs penawaran).\n"
        "ATURAN ANTI-TERTUKAR (WAJIB): blok berlabel 'PRODUK ...' berisi produk UTAMA/keagenan kita — HANYA produk dari "
        "blok itu yang boleh dipakai untuk output_awam_hobo. Blok 'ALTERNATIF (COMPARE)' berisi merek LAIN — HANYA itu "
        "yang boleh dipakai untuk output_awam_lain. JANGAN PERNAH menukar/membalik keduanya; sebelum menulis, cek lagi "
        "setiap nama produk sudah berada di output yang benar.\n"
        "GAYA BALASAN: output_awam_hobo & output_awam_lain harus PADAT — langsung ke inti, maksimal 4-6 kalimat atau "
        "beberapa poin singkat, tanpa basa-basi & tanpa pengulangan. Hanya output_technical yang boleh panjang/detail.\n"
        "Sertakan pertanyaan klarifikasi bila ada. Tandai angka harga sebagai estimasi. JANGAN mengarang di luar data.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): "
        "{\"output_awam_hobo\":\"...\", \"output_awam_lain\":\"...\", \"output_technical\":\"...\"}\n\n"
        "=== INFO TERVERIFIKASI ===\n" + info +
        "\n\n=== INKONSISTENSI ===\n" + ("; ".join(map(str, inkon)) or "-") +
        "\n\n=== PERTANYAAN KLARIFIKASI ===\n" + ("; ".join(map(str, tanya)) or "-") +
        "\n\n=== PRODUK HMP ===\n" + produk +
        "\n\n=== ALTERNATIF (COMPARE) ===\n" + compare +
        "\n\n=== TEKNIS ===\n" + teknis +
        "\n\n=== SERVICE ===\n" + service +
        "\n\n=== ESTIMASI MODAL ===\n" + modal +
        "\n\n=== ESTIMASI PENAWARAN ===\n" + penawaran + fb
    )
    return _json(_gen(prompt), {"output_awam_hobo": "", "output_awam_lain": "", "output_technical": ""})


# ── Agent Router (dispatcher untuk chat lanjutan) ─────────────────────
def _clip(s, n=600):
    s = str(s or "")
    return s if len(s) <= n else s[:n] + " ..."


def _agent_router(chat, riwayat, prev):
    ringkas = (
        "Produk (HMP): " + _clip(prev.get("produk")) +
        "\nTechnical: " + _clip(prev.get("teknis")) +
        "\nService: " + _clip(prev.get("service")) +
        "\nCompare: " + _clip(prev.get("compare")) +
        "\nBudget modal: " + _clip(prev.get("budget_modal"), 200) +
        "\nBalasan sebelumnya: " + _clip(prev.get("output_awam_hobo"))
    )
    prompt = (
        "Kamu Agent Router (dispatcher) untuk percakapan lanjutan tim sales HMP. Ada HASIL ANALISA SEBELUMNYA dan "
        "PESAN BARU dari user. Tentukan agent MANA saja yang perlu BEKERJA ULANG supaya efisien — JANGAN jalankan "
        "semua agent kalau perubahan tidak relevan.\n"
        "Agent tersedia (pakai kata kunci ini): "
        "reader (baca ulang kebutuhan), product (rekomendasi produk HMP), technical (metode/standar/BOM), "
        "service (after-sales), compare (alternatif merek lain), budget (estimasi harga).\n"
        "Aturan:\n"
        "- Pilih HANYA agent yang relevan dengan pesan baru. Contoh: 'ganti alatnya' -> [product] (dan technical/budget "
        "bila jelas terpengaruh); 'hitung ulang harga' -> [budget]; 'carikan alternatif China' -> [compare]; "
        "'jumlah titik uji jadi 50' -> [technical, budget].\n"
        "- Kalau pesan hanya minta ubah GAYA/BAHASA balasan, mempersingkat, atau klarifikasi kecil -> kembalikan "
        "agents KOSONG [] (cukup susun ulang jawaban).\n"
        "- Kalau kebutuhan berubah total -> boleh sertakan banyak agent.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): {\"agents\":[\"product\"], \"alasan\":\"...singkat...\"}\n\n"
        "=== HASIL SEBELUMNYA (ringkas) ===\n" + ringkas +
        "\n\n=== PESAN BARU ===\n" + chat
    )
    d = _json(_gen(prompt), {"agents": ["reader", "product", "technical", "service", "compare", "budget"], "alasan": ""})
    valid = {"reader", "product", "technical", "service", "compare", "budget"}
    d["agents"] = [a for a in (d.get("agents") or []) if a in valid]
    return d


# ── Agent Konfirmasi (konfirmasi permintaan + pertanyaan penjelas) ────
def _agent_konfirmasi(info):
    prompt = (
        "Kamu Agent Konfirmasi untuk tim sales & service. Berdasarkan kebutuhan customer (hasil Reader/verifikasi) di "
        "bawah, kerjakan HANYA dua hal:\n"
        "1. KONFIRMASI: tulis ulang SINGKAT & JELAS pemahaman kita atas permintaan customer, sebagai kalimat siap kirim "
        "untuk dikonfirmasi ke customer (mis. 'Jadi kebutuhan Bapak/Ibu adalah ... , benar ya?'). Maksimal 2-4 kalimat.\n"
        "2. PERTANYAAN PENJELAS: daftar pertanyaan SPESIFIK yang perlu ditanyakan ke customer agar permintaan makin jelas "
        "& tidak salah tafsir (mis. jumlah/kapasitas, lokasi/lingkungan, parameter, budget, timeline). HANYA tanyakan "
        "yang benar-benar belum jelas dari info; kalau sudah jelas jangan ditanyakan lagi. Maksimal 6 poin.\n"
        "Bahasa Indonesia, sopan, ringkas. Jangan mengarang kebutuhan yang tidak disebut customer.\n\n"
        "Kembalikan HANYA Markdown dengan format persis:\n"
        "**Konfirmasi permintaan:**\n(kalimat konfirmasi)\n\n**Perlu ditanyakan ke customer:**\n- (pertanyaan 1)\n"
        "- (pertanyaan 2)\n\n"
        "=== KEBUTUHAN CUSTOMER (TERVERIFIKASI) ===\n" + info
    )
    return _gen(prompt)


def _bungkus(teks_info, visual_info, info, inkon, tanya, produk, teknis, service, compare, budget, flow, hasil, rute=None, harga="", konfirmasi=""):
    return {
        "reader_teks":            teks_info,
        "reader_visual":          visual_info,
        "info_terverifikasi":     info,
        "konfirmasi":             (konfirmasi or "").strip(),
        "inkonsistensi":          inkon,
        "pertanyaan_klarifikasi": tanya,
        "produk":                 produk,
        "teknis":                 teknis,
        "service":                service,
        "compare":                compare,
        "harga_riset":            (harga or "").strip(),
        "budget_modal":           (budget.get("modal") or "").strip(),
        "budget_penawaran":       (budget.get("penawaran") or "").strip(),
        "flow_mermaid":           flow,
        "output_awam_hobo":       (hasil.get("output_awam_hobo") or "").strip(),
        "output_awam_lain":       (hasil.get("output_awam_lain") or "").strip(),
        "output_technical":       (hasil.get("output_technical") or "").strip(),
        "rute_agent":             (rute or {}).get("agents", []),
        "rute_alasan":            (rute or {}).get("alasan", ""),
    }


def analisa_hmp(chat, image_base64="", image_mime="image/png", riwayat="", sebelumnya=None):
    chat = (chat or "").strip()
    riwayat = (riwayat or "").strip()
    prev = sebelumnya if isinstance(sebelumnya, dict) and sebelumnya else None
    file_bytes = None
    mime = None

    if riwayat:
        chat_ctx = ("=== RIWAYAT PERCAKAPAN SEBELUMNYA ===\n" + riwayat +
                    "\n\n=== PESAN CUSTOMER TERBARU (fokus utama balasan) ===\n" + chat)
    else:
        chat_ctx = chat

    if image_base64 and types is not None:
        try:
            file_bytes = base64.b64decode(image_base64)
        except (binascii.Error, ValueError):
            file_bytes = None
        if file_bytes:
            mime = image_mime or "image/png"

    # ===== TURN PERTAMA -> pipeline PENUH =====
    if not prev:
        teks_info   = _agent_reader_teks(chat_ctx)
        visual_info = _agent_reader_visual(file_bytes, mime)
        sumber      = "TEKS:\n" + teks_info + "\n\nVISUAL:\n" + visual_info

        koreksi_p = koreksi_t = koreksi_s = ""
        produk = teknis = service = ""
        checker = {}
        for _ in range(2):
            produk  = _agent_product(sumber, koreksi_p)
            teknis  = _agent_technical(sumber, produk, koreksi_t)
            service = _agent_service(sumber, produk, koreksi_s)
            checker = _agent_checker_all(teks_info, visual_info, produk, teknis, service)
            if checker.get("konsisten", True):
                break
            koreksi_p = checker.get("koreksi_product", "") or ""
            koreksi_t = checker.get("koreksi_technical", "") or ""
            koreksi_s = checker.get("koreksi_service", "") or ""
            if not (koreksi_p or koreksi_t or koreksi_s):
                break

        info  = checker.get("info_terverifikasi", "") or sumber
        inkon = checker.get("inkonsistensi", []) or []
        tanya = checker.get("pertanyaan_klarifikasi", []) or []
        compare = _agent_compare(info, produk)
        harga   = _agent_harga_riset(produk, compare)
        budget  = _agent_budget(info, produk, compare, harga)
        flow  = _agent_flow(teknis)
        hasil = _agent_result(info, inkon, tanya, produk, teknis, service, compare, budget)
        konfirmasi = _agent_konfirmasi(info)
        return _bungkus(teks_info, visual_info, info, inkon, tanya, produk, teknis, service, compare, budget, flow, hasil, harga=harga, konfirmasi=konfirmasi)

    # ===== TURN LANJUTAN -> Router pilih agent =====
    rute = _agent_router(chat, riwayat, prev)
    agents = set(rute.get("agents") or [])
    if file_bytes:
        agents.add("reader")

    teks_info   = prev.get("reader_teks", "") or ""
    visual_info = prev.get("reader_visual", "") or ""
    produk  = prev.get("produk", "") or ""
    teknis  = prev.get("teknis", "") or ""
    service = prev.get("service", "") or ""
    compare = prev.get("compare", "") or ""
    harga   = prev.get("harga_riset", "") or ""
    budget  = {"modal": prev.get("budget_modal", "") or "", "penawaran": prev.get("budget_penawaran", "") or ""}
    info    = prev.get("info_terverifikasi", "") or ""
    inkon   = prev.get("inkonsistensi", []) or []
    tanya   = prev.get("pertanyaan_klarifikasi", []) or []
    flow    = prev.get("flow_mermaid", "") or ""

    instr = "PERMINTAAN LANJUTAN DARI USER (WAJIB dipenuhi):\n" + chat

    if "reader" in agents:
        teks_info = _agent_reader_teks(chat_ctx)
        if file_bytes:
            visual_info = _agent_reader_visual(file_bytes, mime)
    sumber = "TEKS:\n" + teks_info + "\n\nVISUAL:\n" + visual_info

    if "product" in agents:
        produk = _agent_product(sumber, instr)
    if "technical" in agents:
        teknis = _agent_technical(sumber, produk, instr)
    if "service" in agents:
        service = _agent_service(sumber, produk, instr)

    if agents & {"reader", "product", "technical", "service"}:
        checker = _agent_checker_all(teks_info, visual_info, produk, teknis, service)
        if not checker.get("konsisten", True):
            kp = checker.get("koreksi_product", "") or ""
            kt = checker.get("koreksi_technical", "") or ""
            ks = checker.get("koreksi_service", "") or ""
            if kp and "product" in agents:   produk  = _agent_product(sumber, kp)
            if kt and "technical" in agents: teknis  = _agent_technical(sumber, produk, kt)
            if ks and "service" in agents:   service = _agent_service(sumber, produk, ks)
        info  = checker.get("info_terverifikasi", "") or info
        inkon = checker.get("inkonsistensi", []) or []
        tanya = checker.get("pertanyaan_klarifikasi", []) or []

    if "compare" in agents:
        compare = _agent_compare(info, produk)
    if "budget" in agents or ("compare" in agents):
        harga  = _agent_harga_riset(produk, compare)
        budget = _agent_budget(info, produk, compare, harga)
    if "technical" in agents:
        flow = _agent_flow(teknis)

    hasil = _agent_result(info, inkon, tanya, produk, teknis, service, compare, budget, instr)
    konfirmasi = _agent_konfirmasi(info)
    return _bungkus(teks_info, visual_info, info, inkon, tanya, produk, teknis, service, compare, budget, flow, hasil, rute, harga, konfirmasi=konfirmasi)
