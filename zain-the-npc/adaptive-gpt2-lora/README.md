---
title: Adaptive Gpt2 LoRA
emoji: 🎭
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: "6.20.0"
app_file: app.py
pinned: false
---

# One Model, Many Minds

One frozen GPT-2, five swappable LoRA personas — **hand-written LoRA implementation, no `peft` library**.

Live demo: (add your Hugging Face Spaces link here after deploy)

## What this is

A single GPT-2 base model with 5 tiny LoRA adapters (few MB each) trained on different personas. Same model, instant persona swap — no reload, no separate models.

- 🏴‍☠️ Pirate
- 🎭 Shakespearean
- 😏 Sarcastic Gen-Z
- 💪 Motivational Coach
- 🕵️ Noir Detective

## Why hand-written LoRA

Most fine-tuning projects import `peft` and call it done. This implements the actual LoRA math from scratch (`lora/lora_linear.py`, `lora/gpt2_lora.py`) — frozen base weight `W`, trainable low-rank matrices `A`, `B`, computing `y = Wx + (alpha/r) * B(Ax)` manually, injected directly into GPT-2's `Conv1D` attention layers.

Verified: adapter output equals base model output at initialization (B starts at zero) — confirms the math is correct before any training happens.

## Results

| Persona | Sample output (prompt: "hi") |
|---|---|
| Pirate | "hi sire! I hear the rumble of hooves and the drum beat of iron against the drums against the metal..." |
| Shakespearean | "hi, I am the light that shines in the dark, My life is a tale of tales of sorrow and poverty..." |
| Noir Detective | "hi on a rainy night in the city. The driver had parked his car in front of my desk..." |
| Sarcastic Gen-Z | "hi, but you're telling me there's no need to be a leader in my life because I wear an outfit..." |
| Motivational Coach | "hi to you. It is not easy to fall asleep every day. When you do fall asleep, your focus is on getting back to work..." |

## Architecture

```
GPT-2 (frozen)
   +
LoRA adapter (A, B matrices, r=8, alpha=16)
   =
Persona-specific behavior, swappable at inference
```

Each adapter trains ~295K parameters (~0.24% of GPT-2's 124M) — trained on Tiny custom persona datasets (~250 lines each), 3 epochs, on an RTX 3050.

## Project structure

```
lora-personas/
├── lora/
│   ├── lora_linear.py      # generic LoRA linear layer (from scratch)
│   └── gpt2_lora.py        # GPT-2 specific (handles Conv1D)
├── train.py                 # training script, one persona per run
├── compare.py                # base vs fine-tuned comparison
├── app.py                    # Gradio multi-persona demo
├── adapters/                 # trained adapter weights (not in repo, .pt files)
└── *_lines.txt                # training datasets, one per persona
```

## Run it yourself

```bash
pip install torch transformers gradio
py app.py
```

## What I learned

Wrote the LoRA math myself instead of using `peft`, to actually understand what fine-tuning does inside a transformer — not just call an API. Verified against expected behavior (adapter = no-op at init) before trusting the training results.
