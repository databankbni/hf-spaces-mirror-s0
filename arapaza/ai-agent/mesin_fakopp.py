"""
Mesin AI multi-agent untuk tim SALES & SERVICE produk FAKOPP (alat uji pohon & kayu).

Fakopp = alat non-destruktif berbasis akustik untuk arborikultur (deteksi busuk/rongga,
stabilitas pohon) & industri kayu (grading mutu/MOE). Mirip pipeline HOBO. Agent Product
mengecek website Fakopp via Google Search grounding.

Pipeline:
  Reader Teks -> Reader Visual -> Product (cek web Fakopp) -> Technical -> Service
    -> Checker (KOORDINATOR, loop maks 2) -> Flow (Mermaid) -> Result (awam + technical)
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
FAKOPP_SITES = os.getenv("FAKOPP_SITES", "fakopp.com").strip()


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
        "Kamu Agent Reader (teks) untuk tim sales & service alat FAKOPP (uji pohon & kayu). Baca chat customer, lalu "
        "ekstrak SEMUA info penting secara terstruktur (poin '-'): tujuan pengujian (deteksi busuk/rongga batang, "
        "stabilitas pohon/risiko tumbang, grading mutu kayu/log, estimasi MOE/kekakuan, riset), objek uji (pohon "
        "berdiri + spesies, log/gelondongan, kayu gergajian), lokasi & lingkungan, jumlah pohon/titik/sampel, "
        "konteks (inspeksi keselamatan, tata kota, kehutanan, QC industri), kebutuhan software/pelatihan/kalibrasi, "
        "budget/timeline bila ada, serta hal yang ambigu. JANGAN menyimpulkan solusi, hanya rangkum yang tertulis.\n\n"
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
        "Kamu Agent Reader (visual) untuk tim FAKOPP. Baca gambar/PDF/datasheet terlampir. Ekstrak info terstruktur "
        "(poin '-'): jenis dokumen (foto pohon/lokasi, kondisi batang, foto log/kayu, datasheet, hasil uji, dll), "
        "objek uji & kondisi terlihat (retak, luka, pembusukan, kemiringan), spesies bila tampak, skala/dimensi, "
        "label/anotasi penting. Kalau ada bagian tidak terbaca, katakan jujur. Baca ulang & verifikasi tiap angka, spesies/kondisi, dan label yang terlihat sebelum ditulis; utamakan BENAR walau lebih lama. JANGAN mengarang."
    )
    return _gen(prompt, file_bytes, mime)


# ── Agent Product (fokus Fakopp, cek website) ─────────────────────────
def _agent_product(info, koreksi=""):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB dipatuhi) ===\n" + koreksi) if koreksi else ""
    prompt = (
        "Kamu Agent Product untuk produk FAKOPP. Berdasarkan kebutuhan (dari Reader) di bawah, rekomendasikan produk "
        "Fakopp yang tepat untuk tiap kebutuhan.\n"
        "UTAMAKAN mencari & memverifikasi dari website Fakopp: " + FAKOPP_SITES + ". "
        "Contoh lini produk Fakopp (verifikasi & sesuaikan): ArborSonic 3D Acoustic Tomograph (deteksi busuk/rongga "
        "batang), DynaRoot Dynamic Root Stability (uji stabilitas/risiko tumbang), Microsecond Timer (stress wave "
        "timer untuk deteksi kerusakan & indikasi kekakuan/MOE kayu & log), serta alat/aksesori & software terkait.\n"
        "Untuk tiap rekomendasi: nama produk + fungsi + kenapa cocok dengan kebutuhan. Sebutkan aksesori/software/"
        "sensor bila perlu.\n"
        "Produk HARUS sesuai kebutuhan Reader (mis. kebutuhan 'stabilitas pohon' -> DynaRoot, bukan tomograph). "
        "Jangan mengarang model/seri yang tidak kamu yakini; kalau ragu sebut kategori & tandai 'perlu verifikasi'.\n\n"
        "=== KEBUTUHAN (DARI READER) ===\n" + info + fb
    )
    return _gen_search(prompt)


# ── Agent Technical (metode ukur, prosedur, kebutuhan alat) ───────────
def _agent_technical(info, produk, koreksi=""):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB dipatuhi) ===\n" + koreksi) if koreksi else ""
    prompt = (
        "Kamu Agent Technical FAKOPP. Dari kebutuhan + produk terpilih di bawah, susun:\n"
        "1. METODE & SETUP PENGUKURAN: cara kerja & prosedur di lapangan (mis. penempatan sensor keliling batang untuk "
        "tomografi, jumlah titik sensor, pengukuran keliling/diameter, setup DynaRoot dgn inclinometer + anemometer, "
        "atau pengukuran kecepatan gelombang untuk MOE).\n"
        "2. BILL OF MATERIALS: daftar alat + sensor/probe + aksesori + software + estimasi jumlah unit. Bila jumlah "
        "titik/pohon tidak pasti, beri estimasi + tulis asumsinya.\n"
        "3. CATATAN TEKNIS: interpretasi hasil (mis. gambar tomografi, indeks stabilitas), faktor lapangan (cuaca, "
        "spesies, kelembapan kayu), hal penting saat pengukuran.\n"
        "Bahasa Indonesia teknis yang jelas. Jangan mengarang angka pasti; tandai estimasi.\n\n"
        "=== KEBUTUHAN ===\n" + info + "\n\n=== PRODUK TERPILIH ===\n" + produk + fb
    )
    return _gen(prompt)


# ── Agent Service (kalibrasi, software, training, interpretasi) ───────
def _agent_service(info, produk, koreksi=""):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB dipatuhi) ===\n" + koreksi) if koreksi else ""
    prompt = (
        "Kamu Agent Service untuk produk FAKOPP (after-sales). Dari kebutuhan + produk di bawah, berikan info service "
        "relevan:\n"
        "- KALIBRASI & PERAWATAN: perlu kalibrasi/verifikasi berkala? cara rawat sensor/probe agar akurat & awet.\n"
        "- SOFTWARE: setup & penggunaan software (mis. ArborSonic 3D, DynaRoot), ekspor & interpretasi hasil/laporan.\n"
        "- TRAINING: kebutuhan pelatihan pengukuran & pembacaan hasil (penting karena interpretasi butuh keahlian).\n"
        "- TROUBLESHOOTING: masalah umum (sensor tidak terbaca, hasil aneh, koneksi) + langkah diagnosa.\n"
        "- GARANSI: umum untuk produk Fakopp + saran (konfirmasi kebijakan spesifik ke distributor).\n"
        "Kalau chat tidak menyangkut service, cukup beri tips singkat setup, kalibrasi & interpretasi. "
        "Jangan mengarang kebijakan garansi spesifik.\n\n"
        "=== KEBUTUHAN ===\n" + info + "\n\n=== PRODUK ===\n" + produk + fb
    )
    return _gen(prompt)


# ── Agent Checker (KOORDINATOR) ───────────────────────────────────────
def _agent_checker_all(teks_info, visual_info, produk, teknis, service):
    prompt = (
        "Kamu Agent Checker (KOORDINATOR) untuk tim FAKOPP. Pastikan SEMUA hasil agent SALING KONSISTEN dan sesuai "
        "apa yang dibaca Reader. Reader adalah acuan kebenaran kebutuhan customer.\n\n"
        "Periksa:\n"
        "- Apakah PRODUK Fakopp yang direkomendasikan benar-benar sesuai TUJUAN uji Reader? (mis. tujuan stabilitas "
        "pohon -> DynaRoot; deteksi busuk -> ArborSonic Tomograph; grading kayu/MOE -> Microsecond Timer). Salah "
        "pasang produk = tidak konsisten.\n"
        "- Apakah TECHNICAL (metode/BOM) sesuai kebutuhan & produk?\n"
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
        "Kamu Agent Flow. Dari deskripsi metode/teknis di bawah, buat DIAGRAM ALUR (flowchart) proses pengukuran "
        "FAKOPP dalam sintaks MermaidJS.\n"
        "Aturan:\n"
        "- Baris pertama WAJIB: flowchart TD  (boleh LR bila lebih pas).\n"
        "- Node = tahap/komponen (objek uji, sensor, alat, software, hasil/laporan, dll). Pakai ID pendek + label "
        "dalam kurung siku, mis. A1[ArborSonic 3D]. HINDARI tanda kutip, koma, titik dua, kurung bulat, karakter "
        "khusus di label.\n"
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
        "Kamu Agent Compare untuk tim sales FAKOPP. Berdasarkan kebutuhan + produk Fakopp yang direkomendasikan di "
        "bawah, cari produk ALTERNATIF dari MEREK LAIN yang fungsinya mirip / setara untuk tiap kebutuhan (supaya "
        "sales punya opsi selain Fakopp).\n"
        "PRIORITAS ASAL PRODUK (WAJIB, berurutan): (1) utamakan produk BARAT dulu — Eropa & Amerika; (2) kalau tidak "
        "ada padanan Barat yang cocok, baru cari produk CHINA; (3) kalau tetap tidak ada, baru produk LOKAL "
        "(Indonesia). Untuk tiap alternatif, SEBUTKAN asal/negara mereknya.\n"
        "Cari & verifikasi di web. Contoh pembanding sesuai metode: tomografi akustik pohon -> PiCUS Sonic Tomograph "
        "(Argus Electronic); deteksi busuk via resistance drilling -> IML-RESI / Resistograph (IML/Rinntech); uji "
        "stabilitas/pulling -> TreeQinetic (Argus Electronic); stress wave / MOE kayu -> Director/HM200 (Fibre-gen), "
        "dll. Metode bisa beda (akustik vs bor resistansi) — jelaskan.\n"
        "Untuk tiap produk Fakopp, beri 1-2 padanan + kenapa setara + perbedaan metode. Buat TABEL Markdown: "
        "Kebutuhan | Produk Fakopp | Alternatif (merek+model) | Perbedaan utama (metode/hasil/kepraktisan).\n"
        "Realistis; jangan mengarang model. Kalau ragu, sebut kategori + tandai 'perlu verifikasi'.\n\n"
        "=== KEBUTUHAN ===\n" + info + "\n\n=== PRODUK FAKOPP TERPILIH ===\n" + produk
    )
    return _gen_search(prompt)


# ── Agent Riset Harga (search web real-time untuk harga pasar) ────────
def _agent_harga_riset(produk, compare):
    prompt = (
        "Kamu Agent Riset Harga. Tugasmu MENCARI HARGA PASAR TERKINI (real, hari ini) dari WEB untuk SETIAP produk di "
        "bawah — baik produk Fakopp maupun alternatif merek lain.\n"
        "Untuk tiap produk cari: harga jual/list ke END-USER, mata uang aslinya (USD/EUR/dll), dan sumber/domain bila "
        "ada (toko resmi, distributor, marketplace B2B).\n"
        "PENTING: alat uji pohon/kayu ini PREMIUM (sering ribuan sampai puluhan ribu USD/EUR). JANGAN menebak terlalu "
        "murah. Kalau angka pasti tak ketemu, beri RENTANG realistis berdasar produk sekelas + tandai 'perkiraan'. "
        "Konversikan kasar ke IDR (asumsi kurs USD≈Rp 16.000, EUR≈Rp 17.500 — sebutkan asumsimu).\n"
        "Keluarkan daftar per produk: nama | harga pasar (mata uang asli) | ~Rp | sumber/catatan. Jujur soal "
        "ketidakpastian; jangan mengarang angka pasti.\n\n"
        "=== PRODUK FAKOPP ===\n" + produk +
        "\n\n=== ALTERNATIF (COMPARE) ===\n" + compare
    )
    return _gen_search(prompt)


# ── Agent Budget (estimasi modal & penawaran dari harga pasar) ────────
def _agent_budget(info, produk, compare, harga):
    prompt = (
        "Kamu Agent Budget untuk Taharica (distributor alat ukur). Basiskan estimasi pada HARGA PASAR hasil riset di "
        "bawah (jangan mengarang angka baru yang jauh berbeda).\n"
        "LOGIKA HARGA (WAJIB, jangan sampai under-price):\n"
        "- HARGA PENAWARAN ke customer ≈ HARGA PASAR end-user. Boleh sedikit di atas untuk layanan/garansi lokal. "
        "JANGAN menetapkan penawaran JAUH DI BAWAH harga pasar.\n"
        "- HARGA MODAL (biaya beli Taharica) = HARGA PENAWARAN DIKURANGI margin distributor ~20-35%. Jadi modal SELALU "
        "LEBIH KECIL dari penawaran, dan penawaran mendekati harga pasar.\n"
        "- Sanity check: modal < penawaran, penawaran tidak lebih rendah dari harga pasar tanpa alasan. Sebut mata uang "
        "& konversi Rp. Beri RENTANG. Tandai '(estimasi, wajib diverifikasi)'. Catat: bea masuk, kurs, kuantitas, dan "
        "kebijakan margin asli Taharica dapat mengubah angka.\n\n"
        "Hasilkan DUA bagian (mencakup Fakopp DAN alternatif, buat tabel: produk | harga pasar | modal | penawaran):\n"
        "- modal: kisaran harga beli Taharica per item + total kasar.\n"
        "- penawaran: kisaran harga jual ke customer per item + total kasar.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): {\"modal\":\"...markdown...\", \"penawaran\":\"...markdown...\"}\n\n"
        "=== HARGA PASAR (HASIL RISET WEB) ===\n" + harga +
        "\n\n=== KEBUTUHAN ===\n" + info +
        "\n\n=== PRODUK FAKOPP ===\n" + produk +
        "\n\n=== ALTERNATIF (COMPARE) ===\n" + compare
    )
    return _json(_gen_search(prompt), {"modal": "", "penawaran": ""})


# ── Agent Result (3 output: sales Fakopp, sales produk lain, teknis) ──
def _agent_result(info, inkon, tanya, produk, teknis, service, compare, budget, instruksi=""):
    modal = (budget or {}).get("modal", "") or "-"
    penawaran = (budget or {}).get("penawaran", "") or "-"
    fb = ("\n\n=== PERMINTAAN LANJUTAN DARI USER (utamakan penuhi ini di jawaban) ===\n" + instruksi) if instruksi else ""
    prompt = (
        "Kamu Agent Result untuk tim sales & service FAKOPP. Berdasarkan SELURUH data di bawah, buat TIGA output "
        "Bahasa Indonesia:\n"
        "1. output_awam_hobo: rekomendasi balasan untuk SALES memakai produk FAKOPP (bahasa sederhana, siap dipakai "
        "membalas customer; sebut produk Fakopp + poin service + kisaran harga penawaran bila relevan).\n"
        "2. output_awam_lain: rekomendasi balasan versi PRODUK ALTERNATIF (merek lain dari Agent Compare) sebagai opsi "
        "kedua (sebut merek+model + kelebihan/kekurangan + beda metode + kisaran harga penawaran).\n"
        "3. output_technical: rangkuman teknis mendetail untuk tim teknik/service (produk Fakopp + alternatif, metode/"
        "BOM, kalibrasi/software/training, perbandingan teknis, dan ringkasan estimasi biaya modal vs penawaran).\n"
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
        "\n\n=== PRODUK FAKOPP ===\n" + produk +
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
        "Produk (Fakopp): " + _clip(prev.get("produk")) +
        "\nTechnical: " + _clip(prev.get("teknis")) +
        "\nService: " + _clip(prev.get("service")) +
        "\nCompare: " + _clip(prev.get("compare")) +
        "\nBudget modal: " + _clip(prev.get("budget_modal"), 200) +
        "\nBalasan sebelumnya: " + _clip(prev.get("output_awam_hobo"))
    )
    prompt = (
        "Kamu Agent Router (dispatcher) untuk percakapan lanjutan tim sales FAKOPP. Ada HASIL ANALISA SEBELUMNYA dan "
        "PESAN BARU dari user. Tentukan agent MANA saja yang perlu BEKERJA ULANG supaya efisien — JANGAN jalankan "
        "semua agent kalau perubahan tidak relevan.\n"
        "Agent tersedia (pakai kata kunci ini): "
        "reader (baca ulang kebutuhan), product (rekomendasi produk Fakopp), technical (metode/BOM), "
        "service (after-sales), compare (alternatif merek lain), budget (estimasi harga).\n"
        "Aturan:\n"
        "- Pilih HANYA agent yang relevan dengan pesan baru. Contoh: 'ganti alatnya' -> [product] (dan technical/budget "
        "bila jelas terpengaruh); 'hitung ulang harga' -> [budget]; 'carikan alternatif China' -> [compare]; "
        "'jumlah pohonnya jadi 50' -> [technical, budget].\n"
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


def analisa_fakopp(chat, image_base64="", image_mime="image/png", riwayat="", sebelumnya=None):
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
