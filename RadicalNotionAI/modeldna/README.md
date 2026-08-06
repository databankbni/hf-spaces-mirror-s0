---
title: ModelDNA
emoji: 🧬
colorFrom: blue
colorTo: gray
sdk: gradio
sdk_version: "5.50.0"
app_file: app.py
pinned: true
license: apache-2.0
short_description: Verify AI model provenance before you download
---

# 🧬 ModelDNA

**Verify AI model provenance before you download.**

Paste any HuggingFace model ID (or URL) to instantly check:

- **Architecture confirmation** — what base model does this actually use?
- **Claim validation** — does the name match the architecture?
- **Unverifiable claim flags** — e.g. "Claude-distilled" cannot be confirmed from weights
- **Derivative discovery** — models sharing the same base that don't declare attribution

Stage 1 uses only `config.json` (~2 KB). No weight download. Results in ~2 seconds.

---

*Powered by [ModelAtlas](https://modeldna.ai) · a [RadicalNotion](https://radicalnotion.ai) product*
