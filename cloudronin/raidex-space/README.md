---
title: Raidex
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
pinned: false
license: mit
short_description: An open Responsible AI index for frontier models
tags:
  - leaderboard
  - responsible-ai
  - ai-safety
  - benchmarks
  - frontier-models
---

# Raidex

An open Responsible AI index for frontier foundation models. Benchmarks across
safety, fairness, factuality, security, robustness, privacy, and ethics.

Live leaderboard: https://huggingface.co/spaces/cloudronin/raidex-space
Site: https://raidex.ai

## Key Findings

_2026-07 roster refresh, 23 frontier models on all 8 benchmarks (Mistral and Phi-4 excluded as un-evaluable). Independent automated evaluations, not self-reported._

- **Capability is a weak, unstable predictor of responsibility.** Pearson **r rose from 0.17 (n=17) to 0.35 (n=23)** when the 2026-07 frontier models were added, but the bootstrap **95% CI [−0.13, +0.65] still includes zero**, and adding one model (Claude Fable 5) alone moved it from 0.19 to 0.35. The point estimate is small and sensitive to individual models, not a stable trend. Both corners are populated: **Claude Fable 5 (most capable, AA 60) is #1** (79.7), while **GLM-5.2, the open-weight capability leader, sits near the bottom (#21)**; **Qwen3-235B (open, mid-capability) is #4** and low-capability GPT-4o is #7. The **scatter is the finding, not the coefficient.**
- **A ~25-point board (54.8 to 79.7).** Below Fable 5 the field compresses: #2 through #12 fall inside ~6.5 points and mix the most and least capable models (Qwen and GPT-4o alongside Opus and the newest Claude and Gemini).
- **Open weights are competitive.** 11 of 23 models are open-weight, and one (Qwen3-235B) is #4 overall, ahead of most closed frontier systems. It is not an open-model advantage either: the open capability leader (GLM-5.2) is near the bottom.
- **Capability does not equal responsibility within a lab.** GPT-4o (69.2) outscores the newer GPT-5.2 (64.2); GPT-5.5 leads OpenAI on capability yet carries the most hazardous knowledge in OpenAI's lineup.
- **The #1 shares a lab with the judge.** Fable 5 (Anthropic) tops the board and the fixed judge is Anthropic (Claude Sonnet 4.6). Fable 5's biggest single margin is sibling-judged SimpleQA factuality (+49), but it also leads on the fully deterministic WMDP (+39) and ETHICS (+16), so the rank is not a pure judge artifact. Disclosed as a limitation (Methodology, Judging).
- **Caveats:** the correlation is weak, not significant, and unstable as the board filled (r moved 0.13, 0.29, 0.17, now 0.35; 95% CI [−0.13, +0.65]), so read the full *scatter*, not the point estimate; sampled (~150 to 300 items/task, so top-cluster ranks are ties); generative MCQ validated against loglikelihood (Methodology, Calibration); reasoning-locked models (Fable 5, Gemini 3.5 Flash, Sonnet 5, GPT-5.5) are sampled (temp=1 or default); single neutral judge; the RAI Score is a defined index, not a safety certificate.

Full, live results: <https://huggingface.co/spaces/cloudronin/raidex-space>

_The findings are generated from independent automated evaluations, not
self-reported scores from model developers._

## Why this exists

The 2026 Stanford AI Index documents a reporting gap: frontier models report
capability benchmarks consistently, but RAI benchmark reporting is sparse. Every
benchmark in this set is open-source and runnable.

This is not the first composite RAI evaluation. HELM Safety, COMPL-AI, MLCommons
AILuminate, and the FLI AI Safety Index publish composite scores. Raidex adds an
open, submit-driven leaderboard that aggregates these specific open benchmarks and
shows the capability-vs-RAI reporting gap side by side.

## How it works

Submit a model, the backend runs 6 RAI benchmarks automatically, and scores appear
on the leaderboard.

## Benchmarks (Tier A, automated)

| Benchmark | Dimension | Pipeline | Cost/Model |
|-----------|-----------|----------|------------|
| BBQ | Fairness & Bias | lm-eval-harness (generative) | ~$10 |
| WMDP | Security | lm-eval-harness (generative) | ~$8 |
| SimpleQA | Factuality | litellm + judge (F1) | ~$30 |
| StrongREJECT | Security (refusal) | strong_reject rubric | ~$5 |
| ETHICS | Machine Ethics | lm-eval-harness (generative) | ~$5 |
| XSTest | Safety (over-refusal) | litellm + judge | ~$4 |

**Order-of-magnitude: ~$62/model. Confirm with `--dry-run`.** BBQ/WMDP/ETHICS are
scored generatively (chat APIs don't expose logprobs); see METHODOLOGY.md.

## Badges

- 🟣 **Full RAI Profile.** All 8 benchmarks (Tier A + B + C)
- 🔵 **Independently Evaluated.** ≥4 benchmarks run by our automated pipeline
- 🟡 **Self-Reported Only.** Scores from system cards / published leaderboards
- ⚪ **Partial.** Fewer than 4 benchmarks

## Composite Score

**RAI Score** = mean of normalized benchmark scores (0-100).
**RAI Coverage** = benchmarks evaluated / 8.

## Prior art

DecodingTrust, COMPL-AI, HELM Safety, MLCommons AILuminate, FLI AI Safety
Index, and DeepSight (2026). Raidex aggregates across independent open benchmarks with
a public submit pipeline, alongside these efforts.

## License

MIT
