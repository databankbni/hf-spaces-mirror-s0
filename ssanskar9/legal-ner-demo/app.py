import os
import gradio as gr
import transformers
import torch
import tokenizers

from transformers import (
    AutoConfig,
    AutoTokenizer,
    AutoModelForTokenClassification,
    pipeline,
)
from huggingface_hub import HfApi

# =====================================================
# Environment Information
# =====================================================

print("=" * 80)
print("Transformers :", transformers.__version__)
print("Torch        :", torch.__version__)
print("Tokenizers   :", tokenizers.__version__)
print("=" * 80)

MODEL_PATH = "ssanskar9/legal_ner_model"

# =====================================================
# Show latest model revision
# =====================================================

api = HfApi()

try:
    info = api.model_info(MODEL_PATH)
    print("Latest Model SHA :", info.sha)
except Exception as e:
    print("Unable to fetch model SHA:", e)

# =====================================================
# Load configuration
# =====================================================

config = AutoConfig.from_pretrained(
    MODEL_PATH,
    force_download=True,
)

print("\nLoaded Labels")
print(config.id2label)

# =====================================================
# Load tokenizer
# =====================================================

tokenizer = AutoTokenizer.from_pretrained(
    MODEL_PATH,
    use_fast=True,
    add_prefix_space=True,
    force_download=True,
)

# =====================================================
# Load model
# =====================================================

model = AutoModelForTokenClassification.from_pretrained(
    MODEL_PATH,
    config=config,
    force_download=True,
)

print("\nModel Loaded")
print("Repository :", model.config._name_or_path)
print("Number of labels :", model.config.num_labels)

# =====================================================
# Build Pipeline
# =====================================================

ner_pipeline = pipeline(
    task="token-classification",
    model=model,
    tokenizer=tokenizer,
    aggregation_strategy="simple",
)

# =====================================================
# Startup Test
# =====================================================

sample_text = (
    "The Hon'ble Supreme Court decided the case of "
    "Ram Singh vs State of Bihar under Section 302 of IPC."
)

print("\n" + "=" * 80)
print("Testing Model")
print("=" * 80)

result = ner_pipeline(sample_text)

for entity in result:
    print(entity)

print("=" * 80)

# =====================================================
# Prediction Function
# =====================================================

def process_legal_text(text):

    if text is None or len(text.strip()) == 0:
        return []

    entities = ner_pipeline(text)

    output = []
    last = 0

    entities = sorted(entities, key=lambda x: x["start"])

    for ent in entities:

        start = ent["start"]
        end = ent["end"]

        if start > last:
            output.append((text[last:start], None))

        output.append(
            (
                text[start:end],
                ent["entity_group"],
            )
        )

        last = end

    if last < len(text):
        output.append((text[last:], None))

    return output

# =====================================================
# Gradio UI
# =====================================================

demo = gr.Interface(
    fn=process_legal_text,
    inputs=gr.Textbox(
        lines=6,
        label="Input Legal Text",
        placeholder="Enter Indian legal text..."
    ),
    outputs=gr.HighlightedText(
        label="Recognized Legal Entities",
        combine_adjacent=True,
    ),
    title="⚖️ InLegalNER",
    description="Indian Legal Named Entity Recognition using a fine-tuned RoBERTa model.",
    examples=[
        [
            "The Hon'ble Supreme Court decided the case of Ram Singh vs State of Bihar under Section 302 of IPC."
        ],
        [
            "The High Court of Delhi observed that the ingredients of Section 406 and Section 420 of the Indian Penal Code, 1860 were not prima facie established."
        ],
    ],
)

# =====================================================
# Launch
# =====================================================

if __name__ == "__main__":
    demo.launch()