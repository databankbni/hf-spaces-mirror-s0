---
title: MHRA Drug Safety RAG
emoji: 💊
colorFrom: green
colorTo: indigo
sdk: static
pinned: false
license: mit
short_description: Provenance-first RAG over UK MHRA Drug Safety Updates
---

# 💊 Grounded Medical RAG - UK Drug-Safety Q&A

A **provenance-first** retrieval-augmented QA demo over 143 UK MHRA Drug Safety Update
articles. Every answer is shown beside the **exact source passages** it was grounded in
(article title, date, retrieval score); unsupported questions are **refused** rather than
answered.

This page is static: the example answers are pre-computed, so it runs instantly with no
API key. Click an example to see the answer and its retrieval provenance side by side.

**Measured** on a hand-built 64-question gold set (+16 adversarial): correctness 63/64,
faithfulness 64/64, refusal 16/16 (0 false answers, 0 false refusals).

> ⚠️ Information-retrieval demonstrator - **NOT medical advice**.

Source code, evaluation harness, and full methodology:
**https://github.com/PrinceOkunade/mhra-drug-safety-rag**
