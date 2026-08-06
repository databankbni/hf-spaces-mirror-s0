"""Read-only Gradio presentation for the committed mHC evidence bundle."""

import json
from pathlib import Path

import gradio as gr

PROJECT_ROOT = Path(__file__).resolve().parent


def load_evidence() -> dict[str, object]:
    """Load the committed evidence without recomputing or mutating it."""
    return json.loads(
        (PROJECT_ROOT / "evidence.json").read_text(encoding="utf-8")
    )


def evidence_summary() -> list[list[str]]:
    """Return one presentation row per live challenge claim."""
    return [
        [
            claim["claim_id"],
            claim["status"],
            claim["evidence_kind"],
            claim["observation"],
            claim["limitation"],
        ]
        for claim in load_evidence()["claims"]
    ]


with gr.Blocks(title="mHC CPU Evidence") as demo:
    gr.Markdown(
        "# mHC: Manifold-Constrained Hyper-Connections\n"
        "Pinned CPU evidence. Toy results are not full-training measurements."
    )
    gr.Dataframe(
        value=evidence_summary,
        headers=["Claim", "Status", "Evidence kind", "Observation", "Limitation"],
        interactive=False,
    )


if __name__ == "__main__":
    demo.launch()
