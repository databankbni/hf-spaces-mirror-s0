# mHC CPU evidence

This project computes narrow CPU evidence for `mDhyxu8WRb`,
“mHC: Manifold-Constrained Hyper-Connections,” using arXiv `2512.24880v2` and
`tokenbender/mHC-manifold-constrained-hyper-connections@ad20d0d8db4d6fc7e8d9b148281167141da20d47`.

## Claim evidence

A seeded 4×4 Sinkhorn projection satisfies the implemented nonnegativity,
row/column-sum, and spectral-norm diagnostics. This is partial invariant
evidence, not verification of trained-model stability. A dimensional ablation
checks 216 synthetic rows across stream counts `(2,4,8)`, hidden dimensions
`(8,16,32)`, three seeds, and eight mapping variants; every expected shape
matches. A paired raw/projected random-matrix propagation audit covers 27
configurations over depths `(10,50,100)`. Both are explicitly toy mechanism
checks, not reproductions of downstream quality or trained gradient norms.

Kernel fusion, recomputation, communication overlap, systems overhead, 27B
training, and downstream benchmarks were not run and remain unavailable. The
committed `evidence.json` and `summary.csv` contain the computed records,
environment, commands, and USD 0.00 API cost.
