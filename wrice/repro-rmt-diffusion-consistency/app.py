from __future__ import annotations

import json
from pathlib import Path

import gradio as gr


ROOT = Path(__file__).resolve().parent
BUNDLE_PATH = ROOT / "evidence" / "bundle.json"


def load_bundle() -> tuple[str, str]:
    bundle = json.loads(BUNDLE_PATH.read_text())
    rows = []
    for item in bundle["claims"]:
        metrics = json.dumps(item["metrics"], indent=2, sort_keys=True)
        rows.append(
            f"### {item['verdict'].upper()}: {item['claim']}\n\n"
            f"{item['evidence']}\n\n```json\n{metrics}\n```"
        )
    return bundle["title"], "\n\n".join(rows)


with gr.Blocks(title="RMT Diffusion Consistency Reproduction") as demo:
    title, body = load_bundle()
    gr.Markdown(f"# {title}")
    gr.Markdown(body)
    gr.JSON(value=json.loads(BUNDLE_PATH.read_text()), label="Evidence bundle")


if __name__ == "__main__":
    demo.launch()
