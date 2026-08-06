---
title: Smart MCQ Solver
emoji: 🧠
colorFrom: blue
colorTo: indigo
sdk: gradio
python_version: "3.11"
app_file: app.py
pinned: false
---

# Smart MCQ Solver

A fine-tuned **DeBERTa-v3-base** model for ranking multiple-choice answers.

## Model

- Base Model: `microsoft/deberta-v3-base`
- Fine-tuned on the Smart MCQ Solver dataset
- Hosted Model:
  https://huggingface.co/vvenkata/smart-mcq-solver-deberta-base

## Features

- Predicts the **Top-3** most likely answers.
- Uses a fine-tuned DeBERTa-v3-base model.
- Interactive Gradio interface.

## Author

Venkata Ganapathi Subramanian