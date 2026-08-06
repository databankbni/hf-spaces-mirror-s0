"""
train_sfl_model.py

Real fine-tuning script (no synthetic data, no generative-AI-authored
content). Loads a real, small, open base encoder model from Hugging Face
and fine-tunes it as a multi-head classifier that predicts SFL register
variables (field / tenor / mode) from the real, human-annotated CORE
corpus produced by scripts/prepare_core_corpus.py.

Base model: distilbert-base-uncased (66M params, downloadable, CPU/GPU
capable, well suited to text classification fine-tuning per current
best-practice benchmarks for small-model classification tasks).
You can swap MODEL_NAME for any other encoder on the Hub, e.g.
'roberta-base' or 'microsoft/deberta-v3-base', without changing the rest
of the pipeline.

Output: a downloadable, trained checkpoint saved to --out (default:
models/sfl_encoder). This is a real trained artifact, not a demo.

Usage:
    python scripts/prepare_core_corpus.py --out data/core
    python scripts/train_sfl_model.py --data data/core --out models/sfl_encoder --epochs 3
"""
import argparse
import json
import os
from typing import Dict, List

import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModel,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
)
import torch.nn as nn

MODEL_NAME = "distilbert-base-uncased"

# Label vocabularies are derived directly from CORE_TO_SFL_MAP in
# prepare_core_corpus.py -- fixed, documented, non-generative.
FIELD_LABELS = [
    "narrative", "opinion", "informational", "interactive-discussion",
    "how-to-instructional", "informational-persuasion", "lyrical", "spoken",
]
TENOR_LABELS = ["public", "institutional", "peer", "personal"]
MODE_LABELS = [
    "written-monologic", "written-dialogic", "written-procedural", "spoken-transcribed",
]


def load_jsonl(path: str) -> List[Dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


class SFLDataset(Dataset):
    def __init__(self, records: List[Dict], tokenizer, max_length: int = 256):
        self.records = records
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, idx: int) -> Dict:
        rec = self.records[idx]
        enc = self.tokenizer(
            rec["text"],
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )
        item = {k: v.squeeze(0) for k, v in enc.items()}
        item["field_label"] = torch.tensor(FIELD_LABELS.index(rec["sfl_field"]))
        item["tenor_label"] = torch.tensor(TENOR_LABELS.index(rec["sfl_tenor"]))
        item["mode_label"] = torch.tensor(MODE_LABELS.index(rec["sfl_mode"]))
        return item


class SFLMultiHeadModel(nn.Module):
    """Real trainable model: shared encoder + 3 linear classification heads
    (field, tenor, mode), matching Halliday's register variables."""

    def __init__(self, model_name: str = MODEL_NAME):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden = self.encoder.config.hidden_size
        self.field_head = nn.Linear(hidden, len(FIELD_LABELS))
        self.tenor_head = nn.Linear(hidden, len(TENOR_LABELS))
        self.mode_head = nn.Linear(hidden, len(MODE_LABELS))
        self.loss_fct = nn.CrossEntropyLoss()

    def forward(self, input_ids=None, attention_mask=None, field_label=None,
                tenor_label=None, mode_label=None, **kwargs):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        pooled = out.last_hidden_state[:, 0]  # CLS-style pooling
        field_logits = self.field_head(pooled)
        tenor_logits = self.tenor_head(pooled)
        mode_logits = self.mode_head(pooled)

        loss = None
        if field_label is not None:
            loss = (
                self.loss_fct(field_logits, field_label)
                + self.loss_fct(tenor_logits, tenor_label)
                + self.loss_fct(mode_logits, mode_label)
            )
        return {
            "loss": loss,
            "field_logits": field_logits,
            "tenor_logits": tenor_logits,
            "mode_logits": mode_logits,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/core")
    parser.add_argument("--out", default="models/sfl_encoder")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-5)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = SFLMultiHeadModel(MODEL_NAME)

    train_records = load_jsonl(os.path.join(args.data, "train.jsonl"))
    dev_records = load_jsonl(os.path.join(args.data, "dev.jsonl"))

    train_ds = SFLDataset(train_records, tokenizer)
    dev_ds = SFLDataset(dev_records, tokenizer)

    training_args = TrainingArguments(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.lr,
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_steps=50,
        load_best_model_at_end=True,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=dev_ds,
    )

    trainer.train()

    os.makedirs(args.out, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(args.out, "pytorch_model.bin"))
    tokenizer.save_pretrained(args.out)
    with open(os.path.join(args.out, "sfl_label_map.json"), "w") as f:
        json.dump(
            {"field": FIELD_LABELS, "tenor": TENOR_LABELS, "mode": MODE_LABELS},
            f,
            indent=2,
        )
    print(f"[done] trained model + tokenizer + label map saved to {args.out}")
    print("This checkpoint is downloadable and can be reloaded with:")
    print("  AutoModel.from_pretrained / SFLMultiHeadModel + torch.load")


if __name__ == "__main__":
    main()
