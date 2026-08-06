import os

import gradio as gr
from transformers import pipeline

MODEL_ID = "inimuhalfian/mms-tts-tdt-agostinho"
HF_TOKEN = os.environ.get("HF_TOKEN")

tts = pipeline("text-to-speech", model=MODEL_ID, token=HF_TOKEN)


def synthesize(text: str):
    if not text or not text.strip():
        raise gr.Error("Tulis dulu teks dalam bahasa Tetun sebelum menekan tombol Dengarkan.")
    output = tts(text)
    audio = output["audio"].squeeze()
    return (output["sampling_rate"], audio), "Audio berhasil dibuat dan sedang diputar."


# Ukuran teks besar, kontras tinggi, dan focus ring tebal untuk pengguna low-vision.
CSS = """
.gradio-container { font-size: 20px !important; max-width: 900px !important; margin: auto !important; }
h1 { font-size: 34px !important; }
label span { font-size: 20px !important; font-weight: 600 !important; }
textarea, input { font-size: 22px !important; line-height: 1.5 !important; }
#submit-btn { font-size: 24px !important; font-weight: 700 !important; padding: 20px 32px !important; min-height: 64px !important; }
#status-box textarea { font-size: 18px !important; color: #1a1a1a !important; }
*:focus, *:focus-visible { outline: 4px solid #005fcc !important; outline-offset: 3px !important; }
"""

theme = gr.themes.Default(
    text_size="lg",
    spacing_size="lg",
    radius_size="lg",
).set(
    button_primary_background_fill="#0b3d91",
    button_primary_background_fill_hover="#0a2f70",
    button_primary_text_color="#ffffff",
    body_text_color="#111111",
    background_fill_primary="#ffffff",
)

with gr.Blocks(theme=theme, css=CSS, title="Tetun TTS - Uji Coba Model") as demo:
    gr.Markdown(
        "# Tetun Text-to-Speech\n"
        "Tulis teks berbahasa Tetun, lalu tekan tombol **Dengarkan** (atau tekan Enter). "
        "Audio akan otomatis diputar setelah selesai dibuat."
    )

    text_input = gr.Textbox(
        label="Teks Tetun",
        lines=4,
        placeholder="Falesimentu Saudozu Presidente Lú-Olo Lori Triste Ba Povu no Nasaun",
        elem_id="text-input",
    )

    submit_btn = gr.Button("🔊 Dengarkan", variant="primary", elem_id="submit-btn", size="lg")

    audio_output = gr.Audio(label="Hasil Suara", autoplay=True, elem_id="audio-output")
    status = gr.Textbox(
        label="Status",
        interactive=False,
        elem_id="status-box",
        show_label=True,
    )

    submit_btn.click(fn=synthesize, inputs=text_input, outputs=[audio_output, status])
    text_input.submit(fn=synthesize, inputs=text_input, outputs=[audio_output, status])

if __name__ == "__main__":
    demo.launch()