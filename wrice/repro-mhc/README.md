---
title: mHC CPU Evidence
emoji: 🧭
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 6.20.0
app_file: app.py
python_version: "3.12"
tags:
  - paper-mDhyxu8WRb
  - icml2026-repro
---

# mHC CPU Evidence

This project independently computes narrow CPU evidence for ICML 2026 paper
`mDhyxu8WRb`, “mHC: Manifold-Constrained Hyper-Connections.” The pinned source
context is:

`arxiv:2512.24880v2+github:tokenbender/mHC-manifold-constrained-hyper-connections@ad20d0d8db4d6fc7e8d9b148281167141da20d47`

The committed `evidence.json` contains computed values. Paper statements in the
claim text are context, not reproduced measurements.

## Claim scope

| Claim | Status | Evidence kind | What was measured |
|---|---|---|---|
| 1 | partial | `computed_projection_invariant` | One seeded 4×4 Sinkhorn projection satisfies the implemented nonnegativity, row/column-sum, and spectral-norm diagnostics. This does not verify full trained-model stability. |
| 2 | partial | `toy_dimensional_ablation` | Synthetic tensors preserve expected shapes across 216 rows. This tests dimensional consistency only, not Table 1 task quality. |
| 3 | partial | `toy_random_matrix_propagation` | Paired raw/projected random residual matrices are composed across 27 configurations. This does not reproduce loss gaps or trained gradient norms. |
| 4 | unavailable | `unavailable` | No kernel fusion, recomputing, communication-overlap, or systems-overhead benchmark was run. |
| 5 | unavailable | `unavailable` | No 27B training or downstream benchmark was run. |

## Reproduce

```bash
uv sync --frozen
uv run python -m mhc_repro.cli \
  --output-json evidence.json \
  --output-csv summary.csv \
  --n-iters 100
uv run python -m pytest tests -q
```

The dimensional audit covers stream counts `(2, 4, 8)`, hidden dimensions
`(8, 16, 32)`, seeds `(17, 42, 123)`, and eight mapping variants. Shape
agreement is exact. Projection diagnostics use absolute tolerance `1e-6`.
The toy propagation audit covers depths `(10, 50, 100)` with the same stream
counts and seeds; it records gains without treating them as a trained-model
acceptance test.

Execution is CPU-only. The evidence records the Python and PyTorch versions,
fixed inputs, exact command, and USD 0.00 API cost. The Space and
`poster.html` only render the committed bundle; they do not recompute evidence
or call external services.
