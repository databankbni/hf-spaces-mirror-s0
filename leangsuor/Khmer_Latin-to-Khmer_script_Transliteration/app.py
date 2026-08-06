"""
Gradio app for Hugging Face Spaces.
Khmer Latin → Khmer Script Transliteration
"""

import os
import pickle
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import tensorflow as tf
# Force CPU — Metal/CUDA floating-point differences cause the decoder to never
# emit the EOS token, producing infinite garbage output.
tf.config.set_visible_devices([], "GPU")

import gradio as gr  # type: ignore[import]

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── Download models from HF model repo if not present ─────────────────────────

def _ensure_models():
    marker = ROOT / "hf_models/gru_v3_bs64_ed128_ld512/checkpoints/best_encoder_model.keras"
    if marker.exists():
        return
    print("Downloading models from HuggingFace Hub...")
    from huggingface_hub import snapshot_download
    snapshot_download(
        repo_id="leangsuor/latin_to_khmer_transliteration_model",
        local_dir=str(ROOT / "hf_models"),
        allow_patterns=[
            "**/best_*.keras",
            "**/vocab_config.json",
            "**/model.pkl",
        ],
    )
    print("Models ready.")

_ensure_models()

# ── Load models ───────────────────────────────────────────────────────────────

models = {}

def _load():
    # GRU
    gru_path = os.environ.get("GRU_MODEL", "hf_models/gru_v3_bs64_ed128_ld512")
    if Path(gru_path).exists():
        from models.seq2seq_gru_transliteration import Seq2SeqGRUTransliterator
        models["GRU"] = Seq2SeqGRUTransliterator(gru_path).transliterate_sentence
        print(f"GRU loaded from {gru_path}")

    # LSTM
    lstm_path = os.environ.get("LSTM_MODEL", "hf_models/lstm_v3_bs32_ed64_ld512")
    if Path(lstm_path).exists():
        from models.seq2seq_lstm_transliteration import Seq2SeqTransliterator
        models["LSTM"] = Seq2SeqTransliterator(lstm_path).transliterate_sentence
        print(f"LSTM loaded from {lstm_path}")

    # Fuzzy
    fuzzy_path = os.environ.get("FUZZY_MODEL", "hf_models/fuzzy_ngram_greedy_backoff")
    pkl = Path(fuzzy_path) / "checkpoints" / "model.pkl"
    if pkl.exists():
        with open(pkl, "rb") as f:
            predictor = pickle.load(f)
        models["Fuzzy Frequency Matching"] = lambda s: " ".join(predictor.translate_with_beam_search(s))
        print(f"Fuzzy loaded from {fuzzy_path}")

_load()

# ── Inference ─────────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    import re
    return re.sub(r'(.)\1{2,}', r'\1\1', text)


MAX_CHARS = 100


NAMES = ["GRU", "LSTM", "Fuzzy Frequency Matching"]


def _run(name: str, text: str) -> str:
    if name not in models:
        return "Model not loaded"
    started = time.perf_counter()
    result = models[name](text)
    print(f"[{name}] {time.perf_counter() - started:.2f}s  {result}")
    return result


def transliterate(text: str):
    raw = text.strip().lower()
    text = normalize(raw)
    print(f"\n[INPUT]  raw='{raw}'  normalized='{text}'  words={text.split()}")

    if not text:
        print("[INPUT]  empty — returning blanks")
        yield "", "", "", ""
        return

    if len(text) > MAX_CHARS:
        yield "", "", "", f"⚠️ Input too long ({len(text)} chars). Please keep it under {MAX_CHARS} characters."
        return

    out = {name: "" for name in NAMES}
    with ThreadPoolExecutor(max_workers=len(NAMES)) as pool:
        futures = {pool.submit(_run, name, text): name for name in NAMES}
        for future in as_completed(futures):
            out[futures[future]] = future.result()
            yield out["GRU"], out["LSTM"], out["Fuzzy Frequency Matching"], ""

# ── UI ────────────────────────────────────────────────────────────────────────

examples = [
    ["sl oun doch doch knea"],
     ["krong phnom penh"],
    ["bong srey mean snaeh"],
    ["kal na del ban bay hz"],
    ["som sl ban ot"],
]

with gr.Blocks(title="Khmer Transliteration") as demo:
    gr.Markdown("""
    # 🇰🇭 Khmer Latin → Khmer Script Transliteration
    Type Khmer romanization (Latin) and compare GRU, LSTM, and Fuzzy Frequency Matching models.
    """)

    with gr.Row():
        inp = gr.Textbox(label="Roman Input (max 100 chars)", placeholder="e.g. soksabay bong", max_lines=1, scale=3)
        btn = gr.Button("Transliterate", variant="primary", scale=1)

    with gr.Row():
        out_gru   = gr.Textbox(label="GRU",          interactive=False)
        out_lstm  = gr.Textbox(label="LSTM",         interactive=False)
        out_fuzzy = gr.Textbox(label="Fuzzy Frequency Matching", interactive=False)

    status = gr.Markdown("")

    gr.Examples(examples=examples, inputs=inp)

    inp.change(
        fn=lambda t: (
            gr.update(interactive=len(t) <= MAX_CHARS),
            f"⚠️ {len(t)}/{MAX_CHARS} characters — shorten your input." if len(t) > MAX_CHARS else "",
        ),
        inputs=inp,
        outputs=[btn, status],
    )

    btn.click(transliterate, inputs=inp, outputs=[out_gru, out_lstm, out_fuzzy, status])
    inp.submit(transliterate, inputs=inp, outputs=[out_gru, out_lstm, out_fuzzy, status])

if __name__ == "__main__":
    demo.launch()
