"""Hugging Face Space app for HALT-CoT."""

from __future__ import annotations

import os

import gradio as gr

from halt_cot import HaltCoTConfig
from halt_cot.transformers_backend import HaltCoTForCausalLM


DEFAULT_MODEL_ID = os.getenv("HALT_COT_MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")
DEFAULT_DEVICE_MAP = os.getenv("HALT_COT_DEVICE_MAP") or None
DEFAULT_THETA = float(os.getenv("HALT_COT_THETA", "0.6"))

_RUNNER: HaltCoTForCausalLM | None = None


def get_runner() -> HaltCoTForCausalLM:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = HaltCoTForCausalLM.from_pretrained(
            DEFAULT_MODEL_ID,
            device_map=DEFAULT_DEVICE_MAP,
        )
    return _RUNNER


def parse_candidates(candidate_text: str) -> list[str]:
    lines = []
    for raw_line in candidate_text.replace(",", "\n").splitlines():
        line = raw_line.strip()
        if line:
            lines.append(line)
    if len(lines) < 2:
        raise gr.Error("Provide at least two candidate answers.")
    return lines


def run_halt_cot(
    question: str,
    candidate_text: str,
    theta: float,
    consecutive: int,
    max_steps: int,
    step_max_new_tokens: int,
):
    if not question.strip():
        raise gr.Error("Question is required.")

    config = HaltCoTConfig(
        theta=float(theta),
        consecutive_low_entropy=int(consecutive),
        max_steps=int(max_steps),
        step_max_new_tokens=int(step_max_new_tokens),
    )
    result = get_runner().run(question.strip(), parse_candidates(candidate_text), config=config)
    trace_rows = [
        [
            step.index,
            round(step.entropy, 4),
            step.prediction,
            step.generated_tokens,
            step.halted,
            step.text,
        ]
        for step in result.steps
    ]
    final_probs = []
    if result.steps:
        final_probs = sorted(
            result.steps[-1].probabilities.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        final_probs = [[label, round(probability, 6)] for label, probability in final_probs]

    status = "halted" if result.halted else "reached max steps"
    summary = (
        f"Answer: {result.answer}\n"
        f"Status: {status}\n"
        f"Generated reasoning tokens: {result.generated_tokens}"
    )
    return summary, result.reasoning, trace_rows, final_probs


with gr.Blocks(title="HALT-CoT") as demo:
    gr.Markdown("# HALT-CoT")
    with gr.Row():
        with gr.Column(scale=2):
            question = gr.Textbox(
                label="Question",
                lines=5,
                value="If a shop has 12 apples and sells 5, how many apples are left?",
            )
            candidates = gr.Textbox(
                label="Candidate answers",
                lines=6,
                value="5\n6\n7\n8\n9",
            )
            run_button = gr.Button("Run HALT-CoT", variant="primary")
        with gr.Column(scale=1):
            theta = gr.Slider(0.0, 2.0, value=DEFAULT_THETA, step=0.05, label="Entropy threshold")
            consecutive = gr.Slider(1, 4, value=2, step=1, label="Consecutive low-entropy steps")
            max_steps = gr.Slider(1, 12, value=8, step=1, label="Maximum steps")
            step_max_new_tokens = gr.Slider(8, 160, value=64, step=8, label="Step token cap")

    summary = gr.Textbox(label="Result", lines=3)
    reasoning = gr.Textbox(label="Generated reasoning", lines=8)
    trace = gr.Dataframe(
        headers=["Step", "Entropy", "Prediction", "Tokens", "Halted", "Text"],
        label="HALT trace",
    )
    probabilities = gr.Dataframe(headers=["Candidate", "Probability"], label="Final answer distribution")

    run_button.click(
        run_halt_cot,
        inputs=[question, candidates, theta, consecutive, max_steps, step_max_new_tokens],
        outputs=[summary, reasoning, trace, probabilities],
    )


if __name__ == "__main__":
    demo.launch()
