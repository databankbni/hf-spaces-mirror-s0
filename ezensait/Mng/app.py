import gradio as gr
import edge_tts
import asyncio
import tempfile
import os

# ============================================================
# Cloudflare functions/api/tts.js-ийн ХҮЛЭЭЖ буй inputs дараалал:
# [text, engine_select, voice_select, voice_gemini, rate, pitch, volume]
# api_name="generate_audio" — БҮҮ ӨӨРЧИЛ, эс бол proxy тасарна.
# ============================================================

EDGE_VOICE_MAP = {
    'Батаа (эрэгтэй)': 'mn-MN-BataaNeural',
    'Есүй (эмэгтэй)': 'mn-MN-YesuiNeural',
}

GEMINI_VOICE_CHOICES = [
    'Лхагваа (эрэгтэй)', 'Доржоо (эрэгтэй)', 'Батбаяр (эрэгтэй)',
    'Мөнхбат (эрэгтэй)', 'Энхбаяр (эрэгтэй)', 'Ганбаатар (эрэгтэй)',
    'Дулмаа (эмэгтэй)', 'Номин (эмэгтэй)', 'Нарантуяа (эмэгтэй)'
]


async def _edge_tts_save(text, voice_id, rate, pitch, volume):
    rate_str = f"{'+' if rate >= 0 else ''}{int(rate)}%"
    pitch_str = f"{'+' if pitch >= 0 else ''}{int(pitch)}Hz"
    volume_str = f"{'+' if volume >= 0 else ''}{int(volume)}%"

    communicate = edge_tts.Communicate(
        text, voice_id, rate=rate_str, pitch=pitch_str, volume=volume_str
    )
    out_path = tempfile.mktemp(suffix=".mp3")
    await communicate.save(out_path)
    return out_path


def generate_audio(text, engine, voice, voice_gemini, rate, pitch, volume, progress=gr.Progress()):
    if not text or not text.strip():
        raise gr.Error("Текст оруулна уу")

    if engine == 'Gemini TTS (Байгалийн)':
        # Энэ Space дээр Gemini хөдөлгүүр идэвхжээгүй байна.
        raise gr.Error("Gemini TTS энэ Space дээр идэвхгүй байна. Edge TTS-ийг ашиглана уу.")

    voice_id = EDGE_VOICE_MAP.get(voice, EDGE_VOICE_MAP['Батаа (эрэгтэй)'])

    progress(0.3, desc="Дуу үүсгэж байна...")

    try:
        out_path = asyncio.run(_edge_tts_save(text, voice_id, float(rate), float(pitch), float(volume)))
    except Exception as e:
        raise gr.Error(f"Edge TTS алдаа: {e}")

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise gr.Error("Аудио файл үүсгэгдсэнгүй (хоосон гарц)")

    progress(1.0, desc="Бэлэн боллоо")
    return out_path


with gr.Blocks(title="КиноЭзэн TTS Backend") as demo:
    gr.Markdown("## КиноЭзэн TTS Backend (Edge TTS: Батаа / Есүй)")

    with gr.Row():
        with gr.Column():
            text_in = gr.Textbox(label="Текст", lines=4)
            engine_in = gr.Radio(
                ['Edge TTS (Батаа / Есүй)', 'Gemini TTS (Байгалийн)'],
                label="Хөдөлгүүр",
                value='Edge TTS (Батаа / Есүй)'
            )
            voice_in = gr.Radio(
                ['Батаа (эрэгтэй)', 'Есүй (эмэгтэй)'],
                label="Хоолой",
                value='Батаа (эрэгтэй)'
            )
            voice_gemini_in = gr.Dropdown(
                GEMINI_VOICE_CHOICES,
                label="Gemini хоолой (одоогоор ашиглагдахгүй)",
                value=GEMINI_VOICE_CHOICES[0]
            )
            rate_in = gr.Slider(-50, 50, value=15, label="Хурд (%)")
            pitch_in = gr.Slider(-50, 50, value=-8, label="Өнгө (Hz)")
            volume_in = gr.Slider(-50, 50, value=0, label="Дуу чанга (%)")
            btn = gr.Button("Дуу үүсгэх", variant="primary")

        with gr.Column():
            audio_out = gr.Audio(label="Гарц", type="filepath")

    btn.click(
        generate_audio,
        inputs=[text_in, engine_in, voice_in, voice_gemini_in, rate_in, pitch_in, volume_in],
        outputs=audio_out,
        api_name="generate_audio"
    )

demo.queue(max_size=20).launch(ssr_mode=False)