"""
Mesin AI untuk membantu tim SALES Building Management System (BMS).

Sales menempel chat customer (kadang + gambar CAD/denah). Agent menerjemahkan
kebutuhan teknis yang rumit jadi mudah dipahami, lalu memberi rekomendasi
balasan yang siap dipakai sales.
"""
import re
import os
import json
import base64
import binascii

import requests

from mesin_agent import client  # reuse client Gemini yang sudah ada

CC_API = "https://api.cloudconvert.com/v2"

try:
    from google.genai import types
except Exception:  # jaga-jaga kalau path import beda
    types = None


def _is_dwg(b):
    # DWG diawali signature "AC10xx" (mis. AC1027, AC1032)
    return len(b) >= 6 and b[:2] == b"AC" and b[2:6].isdigit()


def _dwg_to_pdf_cloudconvert(dwg_bytes):
    """Konversi DWG -> PDF via CloudConvert. Butuh env CLOUDCONVERT_API_KEY."""
    api_key = os.getenv("CLOUDCONVERT_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CLOUDCONVERT_API_KEY belum diset di Secret backend")
    H = {"Authorization": "Bearer " + api_key}

    # 1) Buat job: upload -> convert(dwg->pdf) -> export url
    job = {"tasks": {
        "imp":  {"operation": "import/upload"},
        "conv": {"operation": "convert", "input": "imp", "input_format": "dwg", "output_format": "pdf"},
        "exp":  {"operation": "export/url", "input": "conv"},
    }}
    r = requests.post(CC_API + "/jobs", json=job, headers=H, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError("buat job " + str(r.status_code) + ": " + r.text[:300])
    tasks = r.json()["data"]["tasks"]
    imp = next(t for t in tasks if t["name"] == "imp")
    exp = next(t for t in tasks if t["name"] == "exp")

    # 2) Upload file DWG ke form yang diberikan CloudConvert
    form = imp["result"]["form"]
    up = requests.post(form["url"], data=form["parameters"],
                       files={"file": ("drawing.dwg", dwg_bytes)}, timeout=180)
    if up.status_code >= 400:
        raise RuntimeError("upload " + str(up.status_code) + ": " + up.text[:200])

    # 3) Tunggu task export selesai (long-poll), lalu unduh PDF
    w = requests.get(CC_API + "/tasks/" + exp["id"] + "/wait", headers=H, timeout=300)
    if w.status_code >= 400:
        raise RuntimeError("wait " + str(w.status_code) + ": " + w.text[:200])
    task = w.json()["data"]
    if task.get("status") != "finished":
        raise RuntimeError("convert gagal: " + str(task.get("message") or task.get("status")))
    pdf_url = task["result"]["files"][0]["url"]
    pdf = requests.get(pdf_url, timeout=180)
    if pdf.status_code >= 400:
        raise RuntimeError("download pdf " + str(pdf.status_code))
    return pdf.content


def _gen(prompt, file_bytes=None, mime=None):
    contents = [prompt]
    if file_bytes and types is not None:
        contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime or "image/png"))
    resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=contents)
    return (resp.text or "").strip()


def _json(txt, fallback):
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
        "Kamu Agent Reader (teks) untuk tim sales BMS. Baca chat customer, lalu ekstrak SEMUA info penting "
        "secara terstruktur (poin '-'): permintaan/kebutuhan, sistem/perangkat yang disebut (HVAC, fire alarm, "
        "CCTV, access control, lighting, sensor, controller, protokol BACnet/Modbus/SCADA, dll), skala/lokasi/"
        "jumlah titik, budget/timeline bila ada, serta hal yang ambigu/kurang jelas. JANGAN menyimpulkan solusi, "
        "hanya rangkum yang tertulis.\n\n=== CHAT CUSTOMER ===\n" + chat
    )
    return _gen(prompt)


# ── Agent 2: Reader visual (gambar / CAD / PDF) ───────────────────────
def _agent_reader_visual(file_bytes, mime):
    if not file_bytes:
        return "(Tidak ada gambar/CAD/PDF dari customer.)"
    prompt = (
        "Kamu Agent Reader (visual) untuk tim sales BMS. Baca gambar/CAD/PDF terlampir (denah/skema/diagram). "
        "Ekstrak info teknis terstruktur (poin '-'): jenis gambar (denah lantai, single-line diagram, diagram "
        "sistem, dll), sistem/perangkat yang terlihat, titik/zona/jumlah unit, label/anotasi/legenda penting, "
        "skala/dimensi bila ada. Kalau ada bagian tidak terbaca, katakan jujur. JANGAN mengarang."
    )
    return _gen(prompt, file_bytes, mime)


# ── Agent Checker (KOORDINATOR — cek semua hasil agent, beri koreksi) ──
def _agent_checker_all(teks_info, visual_info, produk, teknis):
    prompt = (
        "Kamu Agent Checker (KOORDINATOR) untuk tim BMS. Tugasmu memastikan SEMUA hasil agent SALING KONSISTEN "
        "dan sesuai dengan apa yang dibaca Reader (teks & gambar). Reader adalah acuan kebenaran kebutuhan customer.\n\n"
        "Periksa:\n"
        "- Apakah PRODUK yang direkomendasikan benar-benar sesuai kebutuhan yang disebut Reader? (mis. Reader minta A, "
        "tapi Product menawarkan barang yang tidak nyambung -> tidak konsisten).\n"
        "- Apakah TEKNIS/SKEMATIK sesuai dengan kebutuhan Reader dan produk yang dipilih?\n"
        "- Apakah ada kontradiksi antara teks & gambar, atau info yang miss/ambigu?\n\n"
        "Kalau ADA yang tidak sesuai, tulis INSTRUKSI KOREKSI spesifik untuk agent terkait (apa yang harus diperbaiki "
        "agar sesuai kata Reader).\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{\"konsisten\": true/false, \"koreksi_product\":\"instruksi perbaikan utk Agent Product (kosong bila sudah benar)\", "
        "\"koreksi_technical\":\"instruksi perbaikan utk Agent Technical (kosong bila sudah benar)\", "
        "\"inkonsistensi\":[\"...\"], \"pertanyaan_klarifikasi\":[\"...\"], \"info_terverifikasi\":\"ringkasan kebutuhan final yang sudah selaras\"}\n\n"
        "=== READER TEKS ===\n" + teks_info +
        "\n\n=== READER VISUAL ===\n" + visual_info +
        "\n\n=== HASIL AGENT PRODUCT ===\n" + produk +
        "\n\n=== HASIL AGENT TECHNICAL ===\n" + teknis
    )
    return _json(_gen(prompt), {
        "konsisten": True, "koreksi_product": "", "koreksi_technical": "",
        "inkonsistensi": [], "pertanyaan_klarifikasi": [],
        "info_terverifikasi": teks_info + "\n" + visual_info,
    })


# ── Agent: Product (fokus Azbil, fallback cari web) ───────────────────
def _gen_search(prompt):
    """Generate dengan Google Search grounding; fallback ke tanpa-search bila tidak didukung."""
    if types is not None:
        try:
            cfg = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=[prompt], config=cfg)
            return (resp.text or "").strip()
        except Exception:
            pass
    return _gen(prompt)


def _agent_product(info, koreksi=""):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB dipatuhi) ===\n" + koreksi) if koreksi else ""
    prompt = (
        "Kamu Agent Product untuk solusi Building Management System. Berdasarkan kebutuhan (dari Reader) di bawah, "
        "rekomendasikan produk untuk tiap kebutuhan.\n"
        "PRIORITAS UTAMA: produk merek AZBIL (Yamatake) — mis. controller, sensor suhu/kelembapan/tekanan, "
        "actuator, control valve, damper actuator, differential pressure switch, dll. Sebutkan seri/model Azbil "
        "yang cocok bila kamu yakin.\n"
        "Jika TIDAK ADA produk Azbil yang cocok untuk suatu kebutuhan, CARI di web produk alternatif dari merek "
        "lain yang relevan, sebutkan merek + tipe-nya dan tandai '(alternatif non-Azbil)'.\n"
        "Produk yang kamu rekomendasikan HARUS sesuai dengan kebutuhan yang disebut Reader. Jangan menawarkan "
        "produk yang tidak relevan.\n"
        "Format: daftar per kebutuhan -> produk + merek + fungsi singkat. Jangan mengarang model spesifik yang "
        "tidak kamu yakini; kalau ragu sebut kategori produknya.\n\n"
        "=== KEBUTUHAN (DARI READER) ===\n" + info + fb
    )
    return _gen_search(prompt)


# ── Agent: Technical (skematik kerja + jumlah barang) ─────────────────
def _agent_technical(info, produk, koreksi=""):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB dipatuhi) ===\n" + koreksi) if koreksi else ""
    prompt = (
        "Kamu Agent Technical BMS. Dari kebutuhan + produk terpilih di bawah, susun:\n"
        "1. SKEMATIK / ALUR KERJA SISTEM: jelaskan topologi & cara kerja secara teknis (boleh diagram teks/ASCII "
        "sederhana, mis. sensor -> controller -> actuator, jalur komunikasi BACnet/Modbus).\n"
        "2. BILL OF MATERIALS (jumlah barang): daftar komponen + estimasi jumlah unit. Kalau jumlah titik tidak "
        "pasti, beri estimasi dan tulis asumsinya.\n"
        "3. CATATAN INTEGRASI: protokol, wiring/power, hal teknis penting.\n"
        "Bahasa Indonesia teknis yang jelas. Jangan mengarang angka pasti; tandai yang berupa estimasi.\n\n"
        "=== KEBUTUHAN ===\n" + info +
        "\n\n=== PRODUK TERPILIH ===\n" + produk + fb
    )
    return _gen(prompt)


# ── Agent: Flow (diagram alur kerja / flowchart Mermaid) ──────────────
def _agent_flow(teknis):
    prompt = (
        "Kamu Agent Flow. Dari deskripsi skematik/teknis di bawah, buat DIAGRAM ALUR (flowchart) sistem BMS "
        "dalam sintaks MermaidJS.\n"
        "Aturan:\n"
        "- Baris pertama WAJIB: flowchart TD  (boleh LR bila lebih pas).\n"
        "- Node = komponen (sensor, controller, actuator, valve, panel, HMI, dll). Pakai ID pendek + label dalam "
        "kurung siku, mis. C1[Controller Azbil]. HINDARI tanda kutip, koma, titik dua, kurung bulat, dan karakter "
        "khusus di dalam label.\n"
        "- Edge = aliran sinyal/kontrol/komunikasi; beri label protokol bila ada, mis. S1 -->|Modbus| C1.\n"
        "- Maksimal sekitar 15 node, ringkas & jelas.\n"
        "- Kembalikan HANYA kode Mermaid (tanpa backtick, tanpa penjelasan).\n\n"
        "=== SKEMATIK/TEKNIS ===\n" + teknis
    )
    out = _gen(prompt)
    return re.sub(r"```mermaid|```", "", out or "").strip()


# ── Agent: Result (2 output: awam & teknis) ───────────────────────────
def _agent_result(info, inkon, tanya, produk, teknis):
    prompt = (
        "Kamu Agent Result untuk tim sales BMS. Berdasarkan SELURUH data di bawah, buat DUA output Bahasa Indonesia:\n"
        "1. output_awam: penjelasan singkat + rekomendasi balasan untuk SALES yang tidak teknis (bahasa sederhana, "
        "siap dipakai membalas customer; boleh sebut produk secara umum).\n"
        "2. output_technical: rangkuman teknis mendetail untuk tim teknik (sistem, produk Azbil/alternatif, skematik "
        "kerja, jumlah barang/BOM, protokol, dan pertanyaan teknis).\n"
        "Sertakan pertanyaan klarifikasi bila ada. JANGAN mengarang di luar data.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): {\"output_awam\":\"...\", \"output_technical\":\"...\"}\n\n"
        "=== INFO TERVERIFIKASI ===\n" + info +
        "\n\n=== INKONSISTENSI ===\n" + ("; ".join(map(str, inkon)) or "-") +
        "\n\n=== PERTANYAAN KLARIFIKASI ===\n" + ("; ".join(map(str, tanya)) or "-") +
        "\n\n=== PRODUK ===\n" + produk +
        "\n\n=== TEKNIS/SKEMATIK ===\n" + teknis
    )
    return _json(_gen(prompt), {"output_awam": "", "output_technical": ""})


def analisa_bms(chat, image_base64="", image_mime="image/png", riwayat=""):
    chat = (chat or "").strip()
    riwayat = (riwayat or "").strip()
    dwg_error = ""
    file_bytes = None
    mime = None

    # Percakapan berlanjut: gabungkan riwayat + pesan terbaru sebagai konteks untuk Reader.
    if riwayat:
        chat_ctx = ("=== RIWAYAT PERCAKAPAN SEBELUMNYA ===\n" + riwayat +
                    "\n\n=== PESAN CUSTOMER TERBARU (fokus utama balasan) ===\n" + chat)
    else:
        chat_ctx = chat

    # Siapkan file (gambar / PDF / DWG->PDF) — opsional
    if image_base64 and types is not None:
        try:
            file_bytes = base64.b64decode(image_base64)
        except (binascii.Error, ValueError):
            file_bytes = None
        if file_bytes:
            mime = image_mime or "image/png"
            if _is_dwg(file_bytes) or (image_mime or "").lower().find("dwg") != -1:
                try:
                    file_bytes = _dwg_to_pdf_cloudconvert(file_bytes)
                    mime = "application/pdf"
                except Exception as e:
                    dwg_error = str(e)
                    file_bytes = None

    # ── Pipeline multi-agent ──
    # 1) Reader baca sumber (acuan kebenaran) — termasuk riwayat bila ada
    teks_info   = _agent_reader_teks(chat_ctx)
    visual_info = _agent_reader_visual(file_bytes, mime)
    sumber      = "TEKS:\n" + teks_info + "\n\nVISUAL:\n" + visual_info

    # 2) Product + Technical, lalu Checker (koordinator) verifikasi semua.
    #    Kalau tidak konsisten, Checker kirim koreksi -> agent perbaiki (maks 2 putaran).
    koreksi_p = koreksi_t = ""
    produk = teknis = ""
    checker = {}
    for _ in range(2):
        produk  = _agent_product(sumber, koreksi_p)
        teknis  = _agent_technical(sumber, produk, koreksi_t)
        checker = _agent_checker_all(teks_info, visual_info, produk, teknis)
        if checker.get("konsisten", True):
            break
        koreksi_p = checker.get("koreksi_product", "") or ""
        koreksi_t = checker.get("koreksi_technical", "") or ""
        if not koreksi_p and not koreksi_t:
            break

    info  = checker.get("info_terverifikasi", "") or sumber
    inkon = checker.get("inkonsistensi", []) or []
    tanya = checker.get("pertanyaan_klarifikasi", []) or []

    # 3) Flow + Result dari hasil yang sudah diselaraskan Checker
    flow  = _agent_flow(teknis)
    hasil = _agent_result(info, inkon, tanya, produk, teknis)

    return {
        "reader_teks":            teks_info,
        "reader_visual":          visual_info,
        "info_terverifikasi":     info,
        "inkonsistensi":          inkon,
        "pertanyaan_klarifikasi": tanya,
        "produk":                 produk,
        "teknis":                 teknis,
        "flow_mermaid":           flow,
        "output_awam":            (hasil.get("output_awam") or "").strip(),
        "output_technical":       (hasil.get("output_technical") or "").strip(),
        "konversi_error":         dwg_error,
    }
