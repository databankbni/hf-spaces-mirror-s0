---
title: HALT-CoT
sdk: gradio
app_file: app.py
license: mit
tags:
  - chain-of-thought
  - reasoning
  - early-stopping
  - entropy
  - transformers
  - inference-optimization
---

# HALT-CoT

> 📦 **Source & method repo:** [**yass4/halt-cot**](https://huggingface.co/yass4/halt-cot) — full code, tests, and paper. If this demo is useful, a ❤️ on the repo helps.

HALT-CoT is an inference-time early stopping method for chain-of-thought reasoning. After each generated reasoning step, it computes the Shannon entropy of the model's answer distribution over candidate answers. When entropy stays below a threshold, generation stops and the current most likely answer is returned.

This repository packages the method from:

**HALT-CoT: Model-Agnostic Early Stopping for Chain-of-Thought Reasoning via Answer Entropy**  
Yassir Laaouach

[Official paper page](https://openreview.net/forum?id=CX5c7C1CZa) · [PDF mirror](paper/halt-cot-paper.pdf).

The release is a method implementation and Hugging Face Space, not trained model weights.

## What Is Included

- Dependency-free core entropy and halting controller in `halt_cot/core.py`.
- Hugging Face Transformers backend in `halt_cot/transformers_backend.py`.
- CLI entrypoint: `halt-cot`.
- Gradio Space app in `app.py`.
- Publish helper for `huggingface_hub`.
- Focused tests for entropy, candidate sets, and halting behavior.
- Paper PDF in `paper/halt-cot-paper.pdf`.

## Install

```bash
pip install -e ".[transformers]"
```

For the Gradio Space locally:

```bash
pip install -e ".[demo]"
python app.py
```

## CLI Example

```bash
python -m halt_cot.cli \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --question "If a shop has 12 apples and sells 5, how many apples are left?" \
  --candidates 5 6 7 8 9 \
  --theta 0.6 \
  --consecutive 2
```

## Python Example

```python
from halt_cot import HaltCoTConfig
from halt_cot.transformers_backend import HaltCoTForCausalLM

runner = HaltCoTForCausalLM.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")
config = HaltCoTConfig(theta=0.6, consecutive_low_entropy=2, max_steps=8)

result = runner.run(
    "If a shop has 12 apples and sells 5, how many apples are left?",
    candidates=["5", "6", "7", "8", "9"],
    config=config,
)

print(result.answer)
print(result.reasoning)
```

## Method

At reasoning step `i`, HALT-CoT scores candidate answers `a in A` from the next-token logits after the current partial chain. It normalizes those candidate scores into `p_i(a)` and computes:

```text
H_i = - sum_a p_i(a) log p_i(a)
```

The controller halts when `H_i < theta`, optionally requiring the condition for multiple consecutive steps. This implementation uses bits by default, which aligns with the entropy traces in the paper. If you tune thresholds in nats, set `entropy_unit="nats"`.

Suggested starting thresholds from the paper:

- Math-style numeric tasks: `theta` in `[0.5, 0.7]`.
- StrategyQA-style yes/no tasks: `theta = 0.8`.
- CommonsenseQA-style multiple choice: `theta = 0.7`.

For numeric tasks, use task-specific candidate answers where possible. The helper `numeric_candidates_from_texts` can build candidates from training answers plus an integer range.

## Publish To Hugging Face

Log in once:

```bash
python -m huggingface_hub.commands.huggingface_cli login
```

### Free Code/Method Repository

Hugging Face may require a PRO subscription for hosted Gradio Spaces on `cpu-basic`. To publish the method, code, docs, and tests for free, upload this folder as a normal Hugging Face model repository:

```bash
python scripts/publish_to_hf.py --repo-id <your-username>/halt-cot --repo-type model
```

For this account, the repo id is:

```bash
python scripts/publish_to_hf.py --repo-id yass4/halt-cot --repo-type model
```

### Interactive Gradio Space

If your account can create Gradio Spaces, upload the same folder as a Space:

```bash
python scripts/publish_to_hf.py --repo-id <your-username>/halt-cot --repo-type space
```

The default Space model is controlled by `HALT_COT_MODEL_ID`. Set it in the Space variables to use a different causal LM. Use `HALT_COT_DEVICE_MAP=auto` on hardware that supports Accelerate device placement.

## Citation

```bibtex
@misc{laaouach2026haltcot,
  title = {HALT-CoT: Model-Agnostic Early Stopping for Chain-of-Thought Reasoning via Answer Entropy},
  author = {Laaouach, Yassir},
  year = {2026}
}
```
