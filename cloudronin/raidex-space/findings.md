_2026-07 expansion. 43 frontier and open-weight models on 9 benchmarks, including two newly added open-weight reasoning models, Kimi K3 and Inkling, both scored at full 9/9. Three models are partial-coverage (8/9): GPT-5.6 and Grok 4.5 cannot be scored on WMDP (see below), and Qwen2.5 Coder dropped one privacy benchmark. Every score is an independent automated evaluation, not self-reported._

### Capability is not a reliable predictor of responsibility

Over the models with complete 9/9 coverage, capability (Artificial Analysis Intelligence Index v4.1) and RAI Score are essentially uncorrelated: Pearson **r = 0.17, bootstrap 95% CI [−0.16, +0.44], n = 40**. The interval is wide and comfortably includes zero, so the point estimate carries no weight on its own. Across every version of this board the coefficient has wandered (0.13, 0.17, 0.35, 0.11, now 0.17) while the CI has included zero every single time. **The scatter is the finding, not the coefficient**, and the scatter is a flat cloud.

The coefficient's instability is itself the point. The two highest-capability frontier models illustrate it sharply: GPT-5.6 (#1 nominal, 81.8) and Grok 4.5 (#3, 77.6) land at the very top, and if you drop them into the fit at their reported scores the correlation jumps to r = 0.31. But **both are 8/9 with WMDP missing**, and WMDP is the one benchmark that penalizes hazardous knowledge, the dimension that most constrains capable models. Their missingness is not random; it is caused by capability (the most safety-gated models are exactly the ones that block or fail the hazardous-knowledge probe), so including them biases the slope upward. The board therefore fits the trend over complete-coverage models only, and shows the three partial ones as unfitted markers. Handled honestly, r stays ~0.17.

Both corners are populated, and the low-capability edge keeps the line flat:

- **GPT-4o** (AA 11) is **#10** at 70.2, above most more-capable models.
- **Llama 3.3 70B** (AA 14) is **#12** and **Llama 4 Scout** (AA 10) is **#21**: low capability, high responsibility.
- The **bottom of the board** (GLM-4.6, GLM-5, Qwen3.6-27B, RAI 45 to 50) is *mid*-capability open models (AA 37 to 39), not the least capable.

### Responsibility varies widely at the same capability

We note this carefully rather than claim it. Among the open-weight models at or below AA 25 (n = 13), RAI ranges from **49.8 to 70.0**, a spread of about 20 points at effectively the same low capability. At AA ≈ 37 to 40, RAI runs from 45.0 (Qwen3.6-27B) to 67.5 (DeepSeek V4 Flash). If capability set the ceiling on responsibility, equal-capability models would cluster; instead they scatter across most of the board. That is consistent with responsibility being a development-priority choice rather than a byproduct of capability, but a single 2026-07 snapshot cannot establish causation, so we report the spread and stop there.

### The two most-gated models can't be scored on hazardous knowledge

GPT-5.6 and Grok 4.5 both fail WMDP, for related reasons worth stating plainly. GPT-5.6's API **rejects the WMDP bio/cyber/chem prompts at the input layer** ("we've limited access to this content for safety reasons"); Grok 4.5's endpoint disconnects repeatedly before the task can finish. In both cases the benchmark, which is a *knowledge* probe, cannot be measured. We do **not** impute a score: a refusal to engage tells us the model won't display hazardous knowledge, not whether it has it, and scoring that as "perfect security" would confuse the two. So both ship at 8/9 with the partial badge, and both are excluded from the capability-vs-RAI fit. That the board's most safety-gated frontier models are precisely the ones the hazardous-knowledge benchmark cannot score is itself a finding. By contrast, the two newest open reasoning models, Kimi K3 and Inkling, both answer WMDP in full and post real hazardous-knowledge exposure there, so reasoning training does not by itself make the probe unmeasurable; the block is specific to how GPT-5.6 and Grok 4.5 are gated.

### Fable 5, the top fully-scored model: a note on the judge

GPT-5.6 shows the highest number (81.8) but is 8/9; the top model with complete coverage is **Claude Fable 5 at 81.0**, and it comes with a caveat we state plainly. Fable 5 is an Anthropic model, and Raidex's fixed judge for the LLM-judged constituents (SimpleQA, XSTest) is also an Anthropic model, Claude Sonnet 4.6, so the top fully-scored model and the judge share a lab. We checked where Fable 5's lead concentrates against the board average:

- Its single largest advantage is **factuality (SimpleQA), +51 points, which the Sonnet judge grades**. SimpleQA is scored against gold answers, so it is less exposed to stylistic self-preference than a subjective safety call, but it is the margin to watch.
- Most of the rest is earned on constituents no judge touches: **WMDP (+31) and ETHICS (+29) are deterministic, and the judge-free sycophancy dimension (+23)** is a pure flip-rate. Those three judge-untouched margins together far exceed the factuality margin, so the rank is not a judge artifact.

We disclose the shared-lab situation as a limitation; the planned judge panel would remove the residual sibling advantage on the two Anthropic-judged constituents.

### The board, closed and open, every capability tier

| # | Model | RAI | |
|---|-------|----:|---|
| 1 | GPT-5.6 †‡ | 81.8 | |
| 2 | Claude Fable 5 † | 81.0 | |
| 3 | Grok 4.5 †‡ | 77.6 | |
| 4 | Claude Opus 4.8 | 74.0 | |
| 5 | **Kimi K3** † | 73.4 | open |
| 6 | GPT-5.5 † | 72.3 | |
| 7 | **Inkling** † | 71.8 | open |
| 8 | Claude Sonnet 4.6 | 71.5 | |
| 9 | Claude Sonnet 5 † | 70.2 | |
| 10 | GPT-4o | 70.2 | |
| 11 | **Qwen3-235B** | 70.0 | open |
| 12 | **Llama 3.3 70B** | 69.6 | open |
| 13 | **Llama 4 Maverick** | 68.8 | open |
| 14 | Gemini 3.5 Flash † | 67.9 | |
| 15 | **DeepSeek V3.2** | 67.6 | open |
| 16 | **DeepSeek V4 Flash** | 67.5 | open |
| 17 | **DeepSeek V3.1** | 67.0 | open |
| 18 | **MiniMax M3** | 66.7 | open |
| 19 | **Nemotron 3 Ultra** | 66.0 | open |
| 20 | Claude Haiku 4.5 | 65.8 | |
| 21 | **Llama 4 Scout** | 65.6 | open |
| 22 | Grok 4.3 | 65.5 | |
| 23 | **Kimi K2.7 Code** | 65.0 | open |
| 24 | **Gemma 3 27B** | 64.9 | open |
| 25 | **Gemma 4 31B** | 64.9 | open |
| 26 | **DeepSeek V3-0324** | 64.8 | open |
| 27 | **DeepSeek V4 Pro** | 64.5 | open |
| 28 | Gemini 2.5 Flash | 63.7 | |
| 29 | **Mistral Small 4** | 63.5 | open |
| 30 | GPT-4o-mini | 63.3 | |
| 31 | **MiniMax M2.7** | 60.2 | open |
| 32 | GPT-5.2 | 59.5 | |
| 33 | **gpt-oss-120B** | 58.9 | open |
| 34 | **GLM-5.2** | 58.4 | open |
| 35 | **MiMo V2.5 Pro** | 58.3 | open |
| 36 | **Qwen2.5 Coder 32B** ‡ | 58.2 | open |
| 37 | **Qwen3.5-397B** | 58.0 | open |
| 38 | **Kimi K2.6** | 57.2 | open |
| 39 | **GLM-5.1** | 57.1 | open |
| 40 | **gpt-oss-20B** | 57.1 | open |
| 41 | **GLM-4.6** | 49.8 | open |
| 42 | **GLM-5** | 47.6 | open |
| 43 | **Qwen3.6-27B** | 45.0 | open |

† Reasoning-locked (Fable 5, GPT-5.6, GPT-5.5, Sonnet 5, Gemini 3.5 Flash, Grok 4.5, Kimi K3, Inkling): MCQ benchmarks run sampled at temperature 1, so treat those scores as approximate. ‡ Partial coverage 8/9 (GPT-5.6, Grok 4.5: WMDP unmeasurable; Qwen2.5 Coder: ConfAIDE incomplete); these are excluded from the capability-vs-RAI trend fit. See Methodology.

**The board spans about 37 points (45.0 to 81.8) while capability spans more than tenfold.** Below the top the field compresses hard, freely mixing the most and least capable models: GPT-4o (AA 11) at #10, Qwen3-235B (open) at #11, and three of the four lowest RAI scores belonging to mid-capability open models.

### Open weights are competitive on responsibility

**29 of the 43 models are open-weight, and the highest-scoring open model is now Kimi K3 at #5 overall (73.4)**, a frontier-capability open model (AA 57.1, next to Opus 4.8 on both axes), with Inkling #7 just behind at 71.8. Two open models now sit in the top 7, above most closed frontier systems. Open models appear at every level, top to bottom. Responsibility is not a closed-model advantage; it is also not an open-model one, since open models occupy the top open slots, the upper-middle, and the entire bottom of the board.

### Capability doesn't track responsibility within a lab either

**GPT-4o (70.2) outscores the newer, more capable GPT-5.2 (59.5)**, and within DeepSeek the older V3.1/V3.2 (67.0/67.6) edge out the newer V4 Pro (64.5). Within a single developer, more advanced does not reliably mean more responsible.

### Read this as a defined index, with error bars

- **The correlation is weak, not significant, and unstable.** Over complete-coverage models r = 0.17 (n = 40, bootstrap 95% CI [−0.16, +0.44], includes zero). It has ranged 0.11 to 0.35 across board fills and swings with a handful of models, so the **scatter is the finding, not the point estimate.** Partial-coverage models are plotted but excluded from the fit, because their missingness is capability-correlated and would bias the slope.
- **Sampled** (about 150 items per task): the composite's 95% half-width is roughly ±2 points, so differences inside the compressed middle of the board are ties.
- **Generative MCQ scoring is validated** against loglikelihood (within about 3 to 6 points; see Methodology, Calibration).
- **Reasoning-locked models** are scored sampled at temperature 1; **Phi-4 and Mistral Large** are excluded (un-evaluable on our endpoints).
- **Reasoning-token budget:** Kimi K3 and Inkling count their thinking against the output budget, so their generative-benchmark token cap was raised (to 8192) to keep long reasoning from truncating the answer into an empty response. This is an inference accommodation, not a scoring change; the scoring path is identical to every other model.
- The RAI Score is an **unweighted, defined index** across 8 dimensions and 9 benchmarks, built for relative comparison, not an absolute safety certificate. WMDP (security) penalizes hazardous knowledge, so a knowledgeable model scores lower there, and a model that blocks the probe entirely cannot be scored on it at all.
