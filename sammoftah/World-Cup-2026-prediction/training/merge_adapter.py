from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="HuggingFaceTB/SmolLM2-360M-Instruct")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--output", type=Path, default=Path("models/merged"))
    parser.add_argument("--push-to-hub")
    args = parser.parse_args()

    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype="auto",
        device_map="cpu",
    )
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    merged = PeftModel.from_pretrained(model, args.adapter).merge_and_unload()
    args.output.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(args.output, safe_serialization=True)
    tokenizer.save_pretrained(args.output)
    if args.push_to_hub:
        merged.push_to_hub(args.push_to_hub)
        tokenizer.push_to_hub(args.push_to_hub)


if __name__ == "__main__":
    main()
