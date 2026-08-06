---
title: Semantic Density Monitor
emoji: 📊
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 6.19.0
app_file: app.py
pinned: false
---

# Semantic Density Monitor

## A Structural Baseline for LLMs

This tool provides a **structural baseline** for evaluating the geometric integrity of a Large Language Model's embedding manifold. It is a calibration test for the material, designed to detect if a model has developed a stable representational topology.

### What it measures

The tool computes **ΔS = S(coherent) - S(broken)** over a parallel corpus of **50 coherent sentences** and **50 syntactically degraded counterparts**.

- **ΔS < 0**: The model has developed a robust, low-entropy representational topology (a "stable manifold"). It distinguishes between sense and noise at a geometric level.
- **ΔS ≥ 0**: The model is structurally fragile. It does not differentiate between coherent text and syntactic noise.

### A Note on the Bilingual Results (DistilBERT)

This demo runs on DistilBERT (66M params) to ensure accessibility on Hugging Face's free-tier hardware. Its performance is not a flaw but a striking empirical validation of the findings in *The Stone Guest* paper (v2.0, 2026):

- **🇬🇧 English (ΔS > 0):** In English, the model operates in a pre-critical regime. This is consistent with the paper, which identifies the critical phase transition for English near ~410M parameters.
- **🇪🇸 Spanish (ΔS < 0):** Crucially, the same model exhibits a clear phase inversion in Spanish. This empirically corroborates the paper's theory of **language-geometry interaction**: lower-density training languages force earlier geometric compression, making the phase transition detectable at much smaller model scales.

This result proves the metric's sensitivity and confirms the theoretical prediction that phase transitions depend on both model scale and the statistical structure of the training data.

### Languages supported

- 🇪🇸 **Spanish**: 50 coherent + 50 broken sentences
- 🇬🇧 **English**: 50 coherent + 50 broken sentences

### Model

- **DistilBERT** (`distilbert-base-uncased`): 66M parameters
- Lightweight and fast for the Hugging Face free tier
- Estimated processing time: ~5-10 seconds per corpus

### Reference

Cerda Seguel, D. (2026). *The Stone Guest: Harmonic Quantization of Semantic Phase Transitions in Large Language Models* (Version 2.0). Zenodo. [https://doi.org/10.5281/zenodo.20820598](https://doi.org/10.5281/zenodo.20820598)

---

*For dynamic, real-time monitoring of Prompt → Response, see the CTAG framework (contact: geosemantica@gmail.com).*