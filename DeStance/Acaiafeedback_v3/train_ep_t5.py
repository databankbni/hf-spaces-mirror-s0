import os
import json
import numpy as np
import torch

from datasets import Dataset

from transformers import (
    AutoTokenizer,
    AutoModelForSeq2SeqLM,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainingArguments,
    Seq2SeqTrainer,
    set_seed,
)

set_seed(42)

# Cargar data_ready_ep.json

DATA_PATH = "nueva_base_datos.json"
MODEL_CHECKPOINT = "strozz1/t5_ep"
SAVE_DIR = "t5_ep_final_june"

with open(DATA_PATH, "r", encoding="utf-8") as f:
    raw = json.load(f)

cleaned = []
for ex in raw:
    labels = ex["labels"]

    new_labels = [l for l in labels if not l.startswith("EF")]

    # opcional: descartar si se queda sin EP
    if any(l.startswith("EP") for l in new_labels):
        ex2 = dict(ex)
        ex2["labels"] = new_labels
        cleaned.append(ex2)
import re

def remove_ef_tags(text):
    return re.sub(r"<EF_[^>]*>", "", text)

targets = [remove_ef_tags(ex["sentence_with_labels"]) for ex in cleaned]
def clean_tags(text):
    return text.replace("<", "").replace(">", "")

targets = [clean_tags(ex["sentence_with_labels"]) for ex in cleaned]

for t in targets[:10]:
    print(repr(t))

inputs = [
    f"epistemic_tagging\nexpected labels: {' | '.join(ex['labels'])}\ntext: {ex['sentence']}"
    for ex in cleaned
]

#inputs = [
        #    f"epistemic_tagging\nexpected labels: {' | '.join(ex['labels'])}\ntext: {ex['sentence']}"
        #for ex in raw
        #]

#targets = [ex["sentence_with_labels"] for ex in raw]

print(f"Total ejemplos: {len(inputs)}")


# Crear Dataset HF y split train / valid

dataset = Dataset.from_dict({
    "input_text": inputs,
    "output_text": targets
})
print(targets)

split = dataset.train_test_split(test_size=0.2, seed=42)
train_ds = split["train"]
valid_ds = split["test"]

print(f"Train: {len(train_ds)} | Valid: {len(valid_ds)}")


# Tokenizador y preprocesado

tokenizer = AutoTokenizer.from_pretrained(MODEL_CHECKPOINT, use_fast=True)

MAX_SOURCE_LENGTH = 256
MAX_TARGET_LENGTH = 256

def preprocess(batch):
    model_inputs = tokenizer(
        batch["input_text"],
        truncation=True,
        max_length=MAX_SOURCE_LENGTH,
    )

    labels = tokenizer(
        text_target=batch["output_text"],
        truncation=True,
        max_length=MAX_TARGET_LENGTH,
    )

    model_inputs["labels"] = labels["input_ids"]
    return model_inputs

train_tok = train_ds.map(
    preprocess,
    batched=True,
    remove_columns=["input_text", "output_text"]
)

valid_tok = valid_ds.map(
    preprocess,
    batched=True,
    remove_columns=["input_text", "output_text"]
)


#  Modelo T5-base 

model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_CHECKPOINT)

data_collator = DataCollatorForSeq2Seq(
    tokenizer,
    model=model,
    label_pad_token_id=-100,
)

# Métrica: exact match

def postprocess_text(preds, labels):
    preds = [p.strip() for p in preds]
    labels = [l.strip() for l in labels]
    return preds, labels

def compute_metrics(eval_pred):
    preds, labels = eval_pred

    if isinstance(preds, tuple):
        preds = preds[0]

    preds = np.where(preds != -100, preds, tokenizer.pad_token_id)
    decoded_preds = tokenizer.batch_decode(preds, skip_special_tokens=True)

    labels = np.where(labels != -100, labels, tokenizer.pad_token_id)
    decoded_labels = tokenizer.batch_decode(labels, skip_special_tokens=True)

    decoded_preds, decoded_labels = postprocess_text(decoded_preds, decoded_labels)

    for i in range(min(5, len(decoded_preds))):
        print("\n=== SAMPLE ===")
        print("PRED :", repr(decoded_preds[i]))
        print("TRUE :", repr(decoded_labels[i]))

    exact = np.mean([int(p == l) for p, l in zip(decoded_preds, decoded_labels)])
    return {"exact_match": float(exact)}

# TrainingArguments 

use_cuda = torch.cuda.is_available()
use_bf16 = use_cuda and hasattr(torch.cuda, "is_bf16_supported") and torch.cuda.is_bf16_supported()
use_fp16 = use_cuda and not use_bf16

training_args = Seq2SeqTrainingArguments(
    output_dir="./results_t5_ep_june",

    # hiperparámetros 
    learning_rate=2e-5,
    weight_decay=0.01,
    num_train_epochs=10,

    per_device_train_batch_size=4,
    per_device_eval_batch_size=4,
    gradient_accumulation_steps=1,

    eval_strategy="epoch",
    save_strategy="epoch",
    load_best_model_at_end=True,
    metric_for_best_model="exact_match",
    greater_is_better=True,

    warmup_ratio=0.1,

    predict_with_generate=True,
    generation_max_length=MAX_TARGET_LENGTH,
    generation_num_beams=4,

    fp16=bool(use_fp16),
    bf16=bool(use_bf16),

    logging_steps=50,
    report_to="none",
)

trainer = Seq2SeqTrainer(
    model=model,
    args=training_args,
    train_dataset=train_tok,
    eval_dataset=valid_tok,
    processing_class=tokenizer,
    data_collator=data_collator,
    compute_metrics=compute_metrics,
)

trainer.train()


# Guardar modelo final

os.makedirs(SAVE_DIR, exist_ok=True)
trainer.save_model(SAVE_DIR)
tokenizer.save_pretrained(SAVE_DIR)

print(f"\n Modelo T5-base final guardado en: {SAVE_DIR}")
