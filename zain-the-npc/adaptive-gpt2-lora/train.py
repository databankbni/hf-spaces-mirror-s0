"""
Trains a LoRA adapter on GPT-2 for the Motivational Coach persona.
Run: py train.py
"""

import torch
from torch.utils.data import Dataset, DataLoader
from transformers import GPT2LMHeadModel, GPT2Tokenizer
from lora.gpt2_lora import inject_lora_gpt2, freeze_base_unfreeze_lora, get_lora_trainable_params

DATA_PATH = "pirate_speak_lines.txt"
OUTPUT_PATH = "adapters/pirate_speak_lines.pt"
EPOCHS = 3
BATCH_SIZE = 4
LR = 3e-4
MAX_LEN = 128


class TextDataset(Dataset):
    def __init__(self, path, tokenizer, max_len):
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        self.encodings = tokenizer(
            lines, truncation=True, max_length=max_len,
            padding="max_length", return_tensors="pt"
        )

    def __len__(self):
        return self.encodings["input_ids"].shape[0]

    def __getitem__(self, idx):
        ids = self.encodings["input_ids"][idx]
        mask = self.encodings["attention_mask"][idx]
        return {"input_ids": ids, "attention_mask": mask, "labels": ids.clone()}


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("Using device:", device)

    tokenizer = GPT2Tokenizer.from_pretrained("gpt2")
    tokenizer.pad_token = tokenizer.eos_token

    model = GPT2LMHeadModel.from_pretrained("gpt2").to(device)
    inject_lora_gpt2(model, r=8, alpha=16)
    freeze_base_unfreeze_lora(model)
    model.to(device)

    trainable = get_lora_trainable_params(model)
    print(f"Training {len(trainable)} tensors, "
          f"{sum(p.numel() for p in trainable)} params")

    dataset = TextDataset(DATA_PATH, tokenizer, MAX_LEN)
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    optimizer = torch.optim.AdamW(trainable, lr=LR)

    model.train()
    for epoch in range(EPOCHS):
        total_loss = 0
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            loss = outputs.loss

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()

        avg_loss = total_loss / len(loader)
        print(f"Epoch {epoch+1}/{EPOCHS} - loss: {avg_loss:.4f}")

    # Save only the LoRA weights (A, B) - not the whole model
    lora_state = {k: v for k, v in model.state_dict().items() if ".A" in k or ".B" in k}
    import os
    os.makedirs("adapters", exist_ok=True)
    torch.save(lora_state, OUTPUT_PATH)
   

if __name__ == "__main__":
    main()