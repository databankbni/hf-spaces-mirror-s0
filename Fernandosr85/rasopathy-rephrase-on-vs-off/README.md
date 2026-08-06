---
title: RASopathy VUS Output Audit
emoji: 🧬
colorFrom: blue
colorTo: purple
sdk: gradio
python_version: "3.12"
sdk_version: 4.44.1
app_file: app.py
pinned: false
license: cc-by-4.0
---

# RASopathy VUS Output Audit

GPU-backed controlled-output generation and side-by-side review for two
AutoScientist pipelines:

- Pipeline A: Mixtral 8x7B / Rephrase ON
- Pipeline B: Llama 4 Scout / Rephrase OFF

The Space uses a pinned legacy-compatible inference stack because both published
4-bit checkpoints contain pre-quantized Mixture-of-Experts router weights created
for the Transformers 4.52 generation. Upgrading the runtime to Transformers 5.x
can attach packed router tensors to ordinary linear layers and produce invalid
matrix shapes during generation.

The application generates fixed JSON outputs on the Space GPU, commits them back
to this repository, and then serves the audit UI without rerunning inference.
