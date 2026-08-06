---
title: Latin to Khmer Transliteration
colorFrom: blue
colorTo: red
sdk: gradio
app_file: app.py
pinned: false
license: mit
---

# Khmer Latin → Khmer Script Transliteration

Compare three transliteration models that convert romanized Khmer (Latin script) into Khmer script (ខ្មែរ).

## Models

| Model | Architecture | Notes |
|-------|-------------|-------|
| **GRU** | Seq2Seq GRU encoder-decoder | `gru_v3_bs64_ed128_ld512` |
| **LSTM** | Seq2Seq LSTM encoder-decoder | `lstm_v3_bs32_ed64_ld512` |
| **Fuzzy N-gram** | Fuzzy matching + greedy backoff | Rule-augmented lookup |

## Security Note

`hf_models/fuzzy_ngram_greedy_backoff/checkpoints/model.pkl` is flagged by HuggingFace's scanner because it is a pickle file. This file is a serialized `KhmerFuzzyContextualPredictor` object trained solely on Khmer romanization data — it contains no executable payloads. You can inspect the training code in `models/fuzzy_and_ngram_greedy_backoff.py`.

## Usage

Type any romanized Khmer word or phrase and click **Transliterate**:

- `soksabay` → សុខសប្បាយ
- `krong phnom penh` → ក្រុងភ្នំពេញ
- `bong srey mean snaeh` → បងស្រីមានស្នេហ៍
