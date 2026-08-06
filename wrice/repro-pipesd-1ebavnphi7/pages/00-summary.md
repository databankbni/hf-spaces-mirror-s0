# PipeSD Evidence Summary

This submission verifies two implementation-level claims from the pinned PipeSD repository. The checked files are `edge/src/merge.py`, `edge/src/util.py`, and `edge/src/engine.py`.

The reproduced evidence is static and CPU-only: it confirms the dynamic-programming scheduler implementation and the hybrid NAV trigger using single-token and cumulative-confidence thresholds. Performance, energy, bandwidth, and ablation claims require the original cloud-edge testbed and are explicitly marked unreplicated.
