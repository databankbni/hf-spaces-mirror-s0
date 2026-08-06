import gradio as gr
import joblib
import pandas as pd

# ==========================
# Load Model
# ==========================

MODEL_PATH = "diabetes_model (2).pkl"
model = joblib.load(MODEL_PATH)

# ==========================
# Nama Feature (HARUS sama seperti saat training)
# ==========================

FEATURES = [
    'Usia',
    'Indeks Massa Tubuh (BMI)',
    'Apakah ada anggota keluarga Anda yang menderita diabetes?',
    'Apakah Anda melakukan olahraga fisik selama 30 menit setiap hari?',
    'Apakah Anda sering merokok/menggunakan tembakau?',
    'Apakah Anda berada di bawah stres mental?',
    'Apakah Anda menghabiskan lebih banyak waktu pada perangkat elektronik?',
    'Apakah Anda menghabiskan waktu untuk pekerjaan fisik yang berat setiap hari?',
    'Apakah Anda tiba-tiba mengalami kenaikan atau penurunan berat badan?',
    'Apakah tekanan darah Anda berada di kisaran 80-120?',
    'Apakah Anda tinggal di kota besar?',
    'Apakah Anda tidur 7-9 jam setiap hari?',
    'Apakah Anda mendapatkan tidur yang aman dan nyenyak setiap hari?',
    'Apakah Anda selalu makan makanan dengan gizi seimbang?',
    'Do you always eat fresh food?',
    'Apakah Anda makan tiga kali sehari setiap hari?',
    'Apakah Anda makan tiga kali sehari tepat waktu setiap hari?',
    'Apakah Anda makan lebih banyak pada setiap kali makan?',
    'Apakah kualitas makanan Anda baik?',
    'Apakah Anda minum 3 liter air secara rutin?',
    'Apakah Anda memakan makanan vegetarian?',
    'Apakah Anda memiliki makanan alergen dalam diet Anda?',
    'Apakah Anda memakan makanan apa pun untuk menambah atau menurunkan berat badan?',
    'Apakah proses memasak Anda berbasis pengukusan?',
    'Apakah proses memasak Anda berbasis penggorengan?',
    'Apakah proses memasak Anda berbasis pemanggangan (grilling)?',
    'Apakah proses memasak Anda berbasis pemanggangan (baking)?',
    'Apakah Anda makan makanan kemasan?',
    'Apakah Anda makan makanan cepat saji secara rutin?',
    'Apakah Anda makan di rumah hampir sepanjang waktu?',
    'Apakah Anda merasa stres secara mental saat makan?',
    'Apakah makanan bergizi selalu dimasak di rumah?',
    'Apakah Anda selalu makan di tengah kesibukan?',
    'Apakah Anda paling menyukai makanan manis atau bergula?',
    'Apakah Anda makan sebagian besar makanan berkarbohidrat tinggi?',
    'Apakah Anda makan daging dalam jumlah besar?',
    'Apakah Anda makan makanan kaya zat besi?',
    'Apakah Anda makan makanan kaya seng (zinc)?'
]

# Nama fitur dikumpulkan sesuai urutan radio DIBUAT (bukan urutan FEATURES),
# supaya tata letak grid boleh disusun bebas tanpa merusak mapping ke model.
RADIO_FEATURE_NAMES = []


def add_question(feature_name, custom_label=None, info=None):
    label = custom_label or feature_name
    comp = gr.Radio(
        choices=[("Ya", 1), ("Tidak", 0)],
        value=0,
        label=label,
        info=info,
        elem_classes=["risk-radio"],
    )
    RADIO_FEATURE_NAMES.append(feature_name)
    return comp


def render_question_grid(inputs_list, items, cols=3):
    """items: list berisi nama fitur (str) atau tuple.

    Bentuk tuple yang didukung:
      (nama_fitur, label_custom)
      (nama_fitur, label_custom, teks_info)
    label_custom / teks_info boleh None jika tidak dipakai.
    """
    for i in range(0, len(items), cols):
        chunk = items[i:i + cols]
        with gr.Row():
            for item in chunk:
                if isinstance(item, tuple):
                    name = item[0]
                    custom = item[1] if len(item) > 1 else None
                    info = item[2] if len(item) > 2 else None
                else:
                    name, custom, info = item, None, None
                inputs_list.append(add_question(name, custom_label=custom, info=info))


def section_header(number, eyebrow, title):
    gr.HTML(
        f'<div class="section-banner">'
        f'<p class="section-eyebrow">{number} &middot; {eyebrow}</p>'
        f'<p class="section-title">{title}</p>'
        f'</div>'
    )


# ==========================
# Fungsi Prediksi
# ==========================

def build_result_html(bmi, prob):
    if prob > 0.65:
        level = "high"
        status_text = "Risiko Tinggi"
        advice = "Segera konsultasikan dengan dokter dan lakukan pemeriksaan gula darah."
    elif prob > 0.35:
        level = "mid"
        status_text = "Risiko Sedang"
        advice = "Mulai perbaiki pola makan, rutin berolahraga, dan lakukan pemeriksaan berkala."
    else:
        level = "low"
        status_text = "Risiko Rendah"
        advice = "Pertahankan gaya hidup sehat dan lakukan pemeriksaan kesehatan secara rutin."

    pct = prob * 100

    return f"""
<div class="result-card risk-{level}">
  <div class="result-top">
    <div class="vital-chip">
      <span class="vital-label">IMT</span>
      <span class="vital-value">{bmi:.1f}</span>
    </div>
    <div class="result-status">
      <span class="status-dot"></span>
      <span class="status-text">{status_text}</span>
    </div>
  </div>

  <div class="prob-block">
    <div class="prob-number">{pct:.1f}<span class="prob-percent">%</span></div>
    <div class="prob-label">Probabilitas Risiko Diabetes</div>
    <div class="prob-bar-track">
      <div class="prob-bar-fill" style="width:{pct:.1f}%"></div>
    </div>
  </div>

  <div class="advice-block">
    <p class="advice-title">Rekomendasi</p>
    <p class="advice-text">{advice}</p>
  </div>

  <p class="disclaimer">Catatan: hasil ini merupakan skrining berbasis Machine Learning dan <strong>bukan diagnosis medis</strong>.</p>
</div>
"""


def predict(age, weight, height, *answers):
    if not height or not weight or height <= 0 or weight <= 0:
        return '<div class="result-card risk-mid"><p class="advice-text">Mohon isi berat dan tinggi badan dengan benar terlebih dahulu.</p></div>'

    bmi = weight / ((height / 100) ** 2)

    answer_map = dict(zip(RADIO_FEATURE_NAMES, answers))
    row = {'Usia': age, 'Indeks Massa Tubuh (BMI)': bmi}
    row.update(answer_map)

    df = pd.DataFrame([row])

    if hasattr(model, "feature_names_in_"):
        df = df.reindex(columns=model.feature_names_in_, fill_value=0)
    else:
        df = df.reindex(columns=FEATURES, fill_value=0)

    prob = float(model.predict_proba(df)[0][1])

    return build_result_html(bmi, prob)


# ==========================
# Tema & CSS Kustom
# ==========================

THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.teal,
    secondary_hue=gr.themes.colors.amber,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Plus Jakarta Sans"), "ui-sans-serif", "system-ui", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"],
).set(
    body_background_fill="#F1F7F6",
    block_background_fill="#FFFFFF",
    block_border_width="1px",
    block_border_color="#DCEAE7",
    block_radius="18px",
    block_shadow="0 4px 24px rgba(14, 92, 86, 0.06)",
    block_label_background_fill="transparent",
    block_label_border_width="0px",
    block_label_text_color="#0A4440",
    block_label_text_weight="700",
    block_label_radius="0px",
    button_primary_background_fill="#0E5C56",
    button_primary_background_fill_hover="#0B4A45",
    button_primary_text_color="#FFFFFF",
    button_large_radius="14px",
    input_radius="12px",
    checkbox_background_color="#FFFFFF",
    checkbox_background_color_selected="#0E5C56",
    checkbox_border_color="#0E5C56",
    checkbox_border_color_selected="#0E5C56",
    checkbox_label_background_fill="#FFFFFF",
    checkbox_label_background_fill_selected="#0E5C56",
    checkbox_label_background_fill_hover="#E3F3EF",
    checkbox_label_text_color="#0E5C56",
    checkbox_label_text_color_selected="#FFFFFF",
    checkbox_label_border_color="#0E5C56",
    checkbox_label_border_width="2px",
)

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&display=swap');

:root {
  --brand: #0E5C56;
  --brand-dark: #093C38;
  --accent: #E08A00;
  --accent-soft: #F6D488;
  --ink: #16302C;
  --muted: #5B7D77;
  --line: #DCEAE7;
  --risk-low: #1F9D64;
  --risk-mid: #E08A00;
  --risk-high: #D1453D;
}

/* ===== Full width, no more narrow centered column ===== */
.gradio-container {
  max-width: 100% !important;
  width: 100% !important;
  margin: 0 !important;
  padding: 28px clamp(20px, 5vw, 64px) !important;
  box-sizing: border-box !important;
  font-family: 'Plus Jakarta Sans', ui-sans-serif, sans-serif !important;
  color: var(--ink);
}

/* Header */
.app-header { text-align: left; padding: 8px 4px 0 4px; }
.app-eyebrow {
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 6px 0;
}
.app-title {
  font-family: 'Fraunces', serif;
  font-weight: 600;
  font-size: 38px;
  line-height: 1.15;
  color: var(--brand-dark);
  margin: 0 0 8px 0;
}
.app-subtitle {
  font-size: 15.5px;
  color: var(--muted);
  max-width: 70ch;
  margin: 0 0 18px 0;
}

/* Pulse divider (elemen ciri khas) */
.pulse-divider { width: 100%; margin: 4px 0 26px 0; }
.pulse-divider svg { width: 100%; height: 30px; display: block; }
.pulse-path {
  fill: none;
  stroke: var(--brand);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 1600;
  stroke-dashoffset: 1600;
  animation: draw-pulse 1.8s ease-out forwards;
}
@keyframes draw-pulse { to { stroke-dashoffset: 0; } }
@media (prefers-reduced-motion: reduce) {
  .pulse-path { animation: none; stroke-dashoffset: 0; }
}

/* Section banner: solid, vivid, bukan chip pudar */
.section-banner {
  background: linear-gradient(120deg, var(--brand) 0%, var(--brand-dark) 100%);
  border-radius: 12px;
  padding: 14px 20px;
  margin-bottom: 18px;
}
.section-banner .section-eyebrow {
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent-soft);
  margin: 0 0 3px 0;
}
.section-banner .section-title {
  font-family: 'Fraunces', serif;
  font-weight: 600;
  font-size: 20px;
  color: #FFFFFF;
  margin: 0;
}

.persona-card, .question-section { border-color: var(--line) !important; }

/* Result card */
.result-card {
  border: 1px solid var(--line);
  border-left: 6px solid var(--muted);
  border-radius: 16px;
  padding: 22px 24px;
  background: #FFFFFF;
}
.result-card.risk-low { border-left-color: var(--risk-low); }
.result-card.risk-mid { border-left-color: var(--risk-mid); }
.result-card.risk-high { border-left-color: var(--risk-high); }

.result-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 18px;
}
.vital-chip {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  background: #F1F7F6;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 5px 14px;
}
.vital-label { font-size: 11px; font-weight: 700; letter-spacing: 0.08em; color: var(--muted); text-transform: uppercase; }
.vital-value { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 15px; color: var(--brand-dark); }

.result-status { display: inline-flex; align-items: center; gap: 8px; font-weight: 700; font-size: 15px; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--muted); }
.risk-low .status-dot { background: var(--risk-low); }
.risk-mid .status-dot { background: var(--risk-mid); }
.risk-high .status-dot { background: var(--risk-high); }
.risk-low .status-text { color: var(--risk-low); }
.risk-mid .status-text { color: var(--risk-mid); }
.risk-high .status-text { color: var(--risk-high); }

.prob-block { margin-bottom: 18px; }
.prob-number { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 42px; color: var(--brand-dark); line-height: 1; }
.prob-percent { font-size: 22px; margin-left: 2px; color: var(--muted); }
.prob-label { font-size: 13px; color: var(--muted); margin: 4px 0 10px 0; }
.prob-bar-track { width: 100%; height: 10px; border-radius: 999px; background: #EAF1F0; overflow: hidden; }
.prob-bar-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--risk-low), var(--risk-mid), var(--risk-high)); }

.advice-block { border-top: 1px solid var(--line); padding-top: 14px; margin-bottom: 10px; }
.advice-title { font-weight: 700; font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--brand-dark); margin: 0 0 4px 0; }
.advice-text { font-size: 14.5px; color: var(--ink); margin: 0; }

.disclaimer { font-size: 12px; color: var(--muted); margin: 12px 0 0 0; }

footer { display: none !important; }

@media (max-width: 900px) {
  .app-title { font-size: 28px; }
  .prob-number { font-size: 34px; }
}
"""

PULSE_SVG = """
<div class="pulse-divider">
  <svg viewBox="0 0 1200 30" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
    <path class="pulse-path" d="M0,15 L440,15 L458,3 L476,27 L494,3 L512,23 L530,15 L1200,15" />
  </svg>
</div>
"""

# ==========================
# UI
# ==========================

with gr.Blocks(theme=THEME, css=CUSTOM_CSS, title="Skrining Risiko Diabetes") as demo:

    gr.HTML(
        """
        <div class="app-header">
          <p class="app-eyebrow">Skrining Kesehatan &middot; Machine Learning</p>
          <h1 class="app-title">Skrining Risiko Diabetes</h1>
          <p class="app-subtitle">Jawab beberapa pertanyaan singkat tentang gaya hidup dan kebiasaan makan Anda untuk mendapatkan estimasi risiko diabetes.</p>
        </div>
        """
    )
    gr.HTML(PULSE_SVG)

    inputs = []

    # ------------------------
    # Data Diri
    # ------------------------

    with gr.Group(elem_classes=["persona-card"]):
        section_header("01", "Mulai di sini", "Data Diri")
        with gr.Row():
            age = gr.Number(label="Usia (Tahun)", value=30, minimum=13, maximum=120, precision=0)
            weight = gr.Number(label="Berat Badan (kg)", value=60, minimum=20)
            height = gr.Number(label="Tinggi Badan (cm)", value=170, minimum=100)

    inputs.extend([age, weight, height])

    # ------------------------
    # Kuesioner (dikelompokkan per topik, grid mengikuti lebar layar)
    # ------------------------

    with gr.Group(elem_classes=["question-section"]):
        section_header("02", "Riwayat & fisik", "Riwayat Keluarga & Kondisi Fisik")
        render_question_grid(inputs, [
            'Apakah ada anggota keluarga Anda yang menderita diabetes?',
            'Apakah tekanan darah Anda berada di kisaran 80-120?',
            'Apakah Anda tiba-tiba mengalami kenaikan atau penurunan berat badan?',
            'Apakah Anda tinggal di kota besar?',
        ], cols=4)

    with gr.Group(elem_classes=["question-section"]):
        section_header("03", "Gaya hidup", "Aktivitas & Kebiasaan Harian")
        render_question_grid(inputs, [
            'Apakah Anda melakukan olahraga fisik selama 30 menit setiap hari?',
            'Apakah Anda sering merokok/menggunakan tembakau?',
            'Apakah Anda menghabiskan lebih banyak waktu pada perangkat elektronik?',
            'Apakah Anda menghabiskan waktu untuk pekerjaan fisik yang berat setiap hari?',
        ], cols=4)

    with gr.Group(elem_classes=["question-section"]):
        section_header("04", "Stres & istirahat", "Kualitas Tidur & Stres")
        render_question_grid(inputs, [
            'Apakah Anda berada di bawah stres mental?',
            'Apakah Anda tidur 7-9 jam setiap hari?',
            'Apakah Anda mendapatkan tidur yang aman dan nyenyak setiap hari?',
        ], cols=3)

    with gr.Group(elem_classes=["question-section"]):
        section_header("05", "Pola makan", "Pola Makan Harian")
        render_question_grid(inputs, [
            'Apakah Anda selalu makan makanan dengan gizi seimbang?',
            ('Do you always eat fresh food?', 'Apakah Anda selalu mengonsumsi makanan segar?'),
            'Apakah Anda makan tiga kali sehari setiap hari?',
            'Apakah Anda makan tiga kali sehari tepat waktu setiap hari?',
            'Apakah Anda makan lebih banyak pada setiap kali makan?',
            'Apakah kualitas makanan Anda baik?',
            'Apakah Anda minum 3 liter air secara rutin?',
            'Apakah Anda memakan makanan vegetarian?',
            'Apakah Anda memiliki makanan alergen dalam diet Anda?',
            'Apakah Anda memakan makanan apa pun untuk menambah atau menurunkan berat badan?',
        ], cols=5)

    with gr.Group(elem_classes=["question-section"]):
        section_header("06", "Cara memasak", "Metode Memasak")
        render_question_grid(inputs, [
            'Apakah proses memasak Anda berbasis pengukusan?',
            'Apakah proses memasak Anda berbasis penggorengan?',
            'Apakah proses memasak Anda berbasis pemanggangan (grilling)?',
            'Apakah proses memasak Anda berbasis pemanggangan (baking)?',
        ], cols=4)

    with gr.Group(elem_classes=["question-section"]):
        section_header("07", "Kebiasaan makan", "Kebiasaan & Lingkungan Makan")
        render_question_grid(inputs, [
            'Apakah Anda makan makanan kemasan?',
            'Apakah Anda makan makanan cepat saji secara rutin?',
            'Apakah Anda makan di rumah hampir sepanjang waktu?',
            'Apakah Anda merasa stres secara mental saat makan?',
            'Apakah makanan bergizi selalu dimasak di rumah?',
            'Apakah Anda selalu makan di tengah kesibukan?',
        ], cols=3)

    with gr.Group(elem_classes=["question-section"]):
        section_header("08", "Preferensi", "Preferensi & Kandungan Makanan")
        render_question_grid(inputs, [
            (
                'Apakah Anda paling menyukai makanan manis atau bergula?',
                None,
                "Contoh: permen, cokelat, kue, es krim, donat, minuman bersoda, sirup",
            ),
            (
                'Apakah Anda makan sebagian besar makanan berkarbohidrat tinggi?',
                None,
                "Contoh: nasi, roti putih, mie, pasta, kentang, jagung, ubi",
            ),
            'Apakah Anda makan daging dalam jumlah besar?',
            (
                'Apakah Anda makan makanan kaya zat besi?',
                None,
                "Contoh: daging merah, hati ayam/sapi, bayam, kacang merah, tahu/tempe, kerang",
            ),
            (
                'Apakah Anda makan makanan kaya seng (zinc)?',
                None,
                "Contoh: tiram, daging sapi, biji labu, kacang mete, susu, telur",
            ),
        ], cols=5)

    # ------------------------
    # Output
    # ------------------------

    output = gr.HTML()

    with gr.Row():
        btn = gr.Button("Hitung Risiko Saya", variant="primary", size="lg")
        clear = gr.ClearButton(components=inputs, value="Atur Ulang")

    btn.click(predict, inputs, output)

    gr.HTML(
        """
        <div style="margin-top:22px; padding-top:16px; border-top:1px solid var(--line); font-size:13px; color:var(--muted);">
          <strong style="color:var(--ink);">Cara membaca hasil:</strong>
          0&ndash;35% risiko rendah &middot; 35&ndash;65% risiko sedang &middot; 65&ndash;100% risiko tinggi.
          Alat ini adalah skrining awal dan tidak menggantikan diagnosis tenaga medis.
        </div>
        """
    )

demo.launch()