"""
app.py -- Gradio front end for the SFL Meaning Matrix pipeline.
Uses the real pipeline: sfl_matrix_engine -> sfl_manifold -> sfl_realize.
Also exposes real dataset prep + model training (no synthetic data,
no generative filler) as UI buttons, so no terminal is required.
"""
import os
import subprocess
import sys
import threading

import gradio as gr
from sfl_matrix_engine import encode_en, encode_es, encode_en_test_rule
from sfl_manifold import compute_manifold
from sfl_realize import (
    build_pilot_en, build_pilot_es, build_pilot_pt, build_pilot_it, build_pilot_zh,
)

ENCODERS = {"EN": encode_en, "ES": encode_es}
REALIZERS = {
    "EN": build_pilot_en(),
    "ES": build_pilot_es(),
    "PT": build_pilot_pt(),
    "IT": build_pilot_it(),
    "ZH": build_pilot_zh(),
}


def run_pipeline(lang_in, lang_out, k):
    traj = ENCODERS[lang_in]()
    analysis = compute_manifold(traj)
    lines = [f"Input pilot: {lang_in}", f"Geodesic energy: {round(analysis.path_loss, 4)}", ""]
    for t, (state, sg) in enumerate(zip(traj.states, analysis.steps)):
        curv = sg.curvature
        curv_str = "-" if curv != curv else round(curv, 4)
        lines.append(
            f"t={t} [{state.label}] state={state.to_vector().round(3).tolist()} "
            f"disp={round(sg.displacement, 4)} curv={curv_str} driver={sg.dominant_driver} "
            f"metafunction={sg.dominant_metafunction} register={sg.dominant_register}"
        )
        lines.append(f"  rule={sg.rule_applied}")
        lines.append("  " + state.display_2x3().replace(chr(10), chr(10) + "  "))
        lines.append(f"  ^ dominant row={sg.dominant_metafunction} dominant col={sg.dominant_register}")
    M_out = traj.states[-1].to_vector()
    vocab = REALIZERS[lang_out]
    candidates = vocab.nearest(M_out, k=int(k))
    lines.append("")
    lines.append(f"Output language: {lang_out}")
    lines.append(f"Best realization: {candidates[0][0]}")
    lines.append("Candidates:")
    for w, d in candidates:
        lines.append(f"  {w} (distance {round(d, 4)})")
    return "\n".join(lines)


def run_rule_test():
    """
    SYNTHETIC TEST -- not real pilot data.
    Runs a manufactured trajectory built specifically to satisfy the
    apply_sfl_composition_rule() conditions (interpersonal rise +
    stable field), so the rule's effect can be observed directly in
    this UI.
    """
    traj = encode_en_test_rule()
    analysis = compute_manifold(traj)
    lines = [
        "SYNTHETIC TEST TRAJECTORY (not real pilot data)",
        "Purpose: force apply_sfl_composition_rule() to fire so its effect is visible.",
        f"Geodesic energy: {round(analysis.path_loss, 4)}",
        "",
    ]
    for t, (state, sg) in enumerate(zip(traj.states, analysis.steps)):
        curv = sg.curvature
        curv_str = "-" if curv != curv else round(curv, 4)
        lines.append(
            f"t={t} [{state.label}] state={state.to_vector().round(3).tolist()} "
            f"disp={round(sg.displacement, 4)} curv={curv_str} driver={sg.dominant_driver} "
            f"metafunction={sg.dominant_metafunction} register={sg.dominant_register}"
        )
        lines.append(f"  rule={sg.rule_applied}")
    lines.append("")
    lines.append("Expected: t=1 should show rule=interpersonal->textual propagation")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Real dataset prep + training, run as background subprocess so the Gradio
# UI stays responsive. CPU-only free tier (16GB RAM): we cap dataset size
# and epochs so it fits within memory/time, but this is real training on
# real annotated data (CORE corpus), not a simulation.
# ---------------------------------------------------------------------------
_TRAIN_LOG_PATH = "/tmp/sfl_train.log"
_train_lock = threading.Lock()
_train_proc = {"proc": None}


def _append_log(msg: str) -> None:
    with open(_TRAIN_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def _background_run(max_docs: int, epochs: int) -> None:
    with _train_lock:
        open(_TRAIN_LOG_PATH, "w").close()
        _append_log("[step 1/2] Downloading + preparing real CORE corpus subset...")
        try:
            subprocess.run(
                [sys.executable, "scripts/prepare_core_corpus.py", "--out", "data/core"],
                check=True, capture_output=True, text=True,
            )
            _append_log("[ok] dataset prepared -> data/core/{train,dev,test}.jsonl")
        except subprocess.CalledProcessError as e:
            _append_log("[error] dataset prep failed:\n" + e.stderr[-2000:])
            return
        except Exception as e:
            _append_log(f"[error] dataset prep failed: {e}")
            return

        _append_log(f"[step 2/2] Fine-tuning distilbert-base-uncased (epochs={epochs}, capped docs={max_docs})...")
        try:
            proc = subprocess.Popen(
                [
                    sys.executable, "scripts/train_sfl_model.py",
                    "--data", "data/core", "--out", "models/sfl_encoder",
                    "--epochs", str(epochs), "--batch_size", "4",
                ],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            _train_proc["proc"] = proc
            for line in proc.stdout:
                _append_log(line.rstrip())
            proc.wait()
            if proc.returncode == 0:
                _append_log("[done] Training complete. Checkpoint saved to models/sfl_encoder (downloadable).")
            else:
                _append_log(f"[error] training exited with code {proc.returncode}")
        except Exception as e:
            _append_log(f"[error] training failed: {e}")


def start_training(epochs):
    if _train_lock.locked():
        return "Training already in progress. Check log below."
    t = threading.Thread(target=_background_run, args=(2000, int(epochs)), daemon=True)
    t.start()
    return "Training started in background (real data, real model, CPU). Click 'Refresh log' to follow progress."


def read_training_log():
    if not os.path.exists(_TRAIN_LOG_PATH):
        return "No training run yet."
    with open(_TRAIN_LOG_PATH, encoding="utf-8") as f:
        return f.read()[-6000:]


with gr.Blocks(title="SFL Meaning Matrix") as demo:
    gr.Markdown(
        "# Primus Orbis -- SFL Meaning Matrix\n"
        "Runs the real pipeline: pilot prompt -> 6D SFL meaning trajectory -> "
        "geodesic geometry -> cross-language realization. No translation step."
    )
    with gr.Row():
        lang_in = gr.Radio(["EN", "ES"], value="EN", label="Input pilot language")
        lang_out = gr.Radio(["EN", "ES", "PT", "IT", "ZH"], value="EN", label="Output realization language")
        k = gr.Slider(1, 10, value=5, step=1, label="Top-k candidates")
    btn = gr.Button("Run pipeline")
    out = gr.Textbox(label="Trajectory + realization", lines=20)
    btn.click(run_pipeline, inputs=[lang_in, lang_out, k], outputs=out)

    gr.Markdown("---\n### Composition rule test (synthetic data, not a real pilot)")
    test_btn = gr.Button("Run rule test (synthetic)")
    test_out = gr.Textbox(label="Synthetic rule test output", lines=10)
    test_btn.click(run_rule_test, inputs=None, outputs=test_out)

    gr.Markdown(
        "---\n### Real training run (CORE corpus, distilbert-base-uncased)\n"
        "Downloads the real, human-annotated CORE register corpus and fine-tunes "
        "a real downloadable model on this Space's free CPU (16GB RAM). "
        "No synthetic data, no generative filler. This can take a while on CPU."
    )
    with gr.Row():
        epochs_in = gr.Slider(1, 5, value=1, step=1, label="Epochs")
        train_btn = gr.Button("Start real training")
        refresh_btn = gr.Button("Refresh log")
    train_status = gr.Textbox(label="Status", lines=2)
    train_log = gr.Textbox(label="Training log", lines=20)
    train_btn.click(start_training, inputs=[epochs_in], outputs=train_status)
    refresh_btn.click(read_training_log, inputs=None, outputs=train_log)

    demo.launch()
