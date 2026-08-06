from __future__ import annotations

from pipesd_repro.evidence import load_evidence_bundle, render_summary_markdown


def load_bundle() -> dict:
    return load_evidence_bundle()


def _claim_rows(bundle: dict) -> list[list[str]]:
    return [
        [
            claim["claim_id"],
            claim["status"],
            claim["challenge_claim_sha256"],
            "; ".join(claim["evidence"]),
        ]
        for claim in bundle["claims"]
    ]


try:
    import gradio as gr
except ImportError:
    demo = None
else:
    bundle = load_bundle()
    with gr.Blocks(title="PipeSD Reproduction Evidence") as demo:
        gr.Markdown(render_summary_markdown(bundle))
        gr.Dataframe(
            headers=["Claim", "Status", "Challenge SHA256", "Evidence"],
            value=_claim_rows(bundle),
            wrap=True,
            interactive=False,
        )
        gr.JSON(value=bundle["implementation_summary"], label="Implementation checks")
        gr.JSON(value=bundle["file_hashes"], label="Pinned source hashes")


if __name__ == "__main__" and demo is not None:
    demo.launch()
