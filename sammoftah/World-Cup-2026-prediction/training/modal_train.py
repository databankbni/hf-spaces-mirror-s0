from __future__ import annotations

import json
import os

import modal

# ── Hugging Face secret ──
_hf_secret = modal.Secret.from_name("huggingface-secret")

# ── Runtime prompt components (inlined for Modal portability) ──────────
# These MUST match src/underdog_lab/scenarios/prompts.py exactly.
# Verified by tests/unit/test_prompt_alignment.py.

SYSTEM_PROMPT = (
    "You extract football scenario factors into JSON.\n"
    "Use only the allowed factor taxonomy. Do not predict scores or probabilities.\n"
    "Resolve team references as home, away, both, or unknown.\n"
    "Put claims outside the taxonomy in unsupported_claims.\n"
    "Put unclear team references or contradictions in ambiguities.\n"
    "Keep evidence short and copied from the user text.\n"
    "\n"
    "Examples:\n"
    '- "Canada\'s striker is confirmed out." means\n'
    "  key_attacker_unavailable for the home team.\n"
    '- "The away goalkeeper is injured." means\n'
    "  goalkeeper_unavailable for the away team.\n"
    '- "They are playing at home." means home_advantage only when a team is clear.\n'
    "- Never emit home_advantage, neutral_venue, or squad_rotation unless the\n"
    "  scenario explicitly says so.\n"
    "\n"
    "Return only the JSON object."
)


def user_content(
    *,
    home_team: str = "",
    away_team: str = "",
    text: str = "",
    neutral_venue: bool = True,
) -> str:
    """Build the user message content (mirrors prompts.user_content)."""
    venue = "neutral" if neutral_venue else "home venue"
    return (
        f"Home team: {home_team}\n"
        f"Away team: {away_team}\n"
        f"Recorded venue: {venue}\n"
        f"Scenario: {text}"
    )


app = modal.App("underdog-lab-smollm2-qlora")
volume = modal.Volume.from_name("underdog-lab-training", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "accelerate>=1.6",
        "bitsandbytes>=0.45",
        "datasets>=3",
        "huggingface-hub>=0.30",
        "peft>=0.14",
        "transformers>=4.51",
        "trl>=0.16",
    )
)


@app.function(
    image=image,
    cpu=2,
    timeout=60 * 10,
)
def validate_apis(
    dataset_repo: str,
    base_model: str = "HuggingFaceTB/SmolLM2-360M-Instruct",
) -> dict:
    """Cheap CPU validation before requesting A10G.

    Verifies that the installed TRL/Transformers APIs match what the training
    function expects, and that the dataset has the right shape.
    """
    from datasets import load_dataset
    from peft import LoraConfig
    from transformers import AutoTokenizer
    from trl import SFTConfig

    results = {"passed": [], "warnings": [], "errors": []}

    # 1. Tokenizer and chat template
    try:
        tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        if not getattr(tokenizer, "chat_template", None):
            results["errors"].append("Tokenizer has no chat_template.")
        else:
            results["passed"].append("tokenizer chat_template")
    except Exception as e:
        results["errors"].append(f"tokenizer load: {e}")
        return results

    # 2. Validate a single format_example produces correct ChatML
    dummy = {
        "home_team": "Canada",
        "away_team": "Mexico",
        "text": "Test scenario.",
        "expected": {
            "factors": [],
            "unsupported_claims": ["Test scenario."],
            "ambiguities": [],
        },
        "neutral_venue": True,
    }
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": user_content(
                    home_team=dummy["home_team"],
                    away_team=dummy["away_team"],
                    text=dummy["text"],
                    neutral_venue=dummy["neutral_venue"],
                ),
            },
            {"role": "assistant", "content": json.dumps(dummy["expected"], ensure_ascii=True, sort_keys=True)},
        ]
        formatted = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        assert "<|im_start|>system" in formatted, "Missing system token"
        assert "<|im_start|>user" in formatted, "Missing user token"
        assert "<|im_start|>assistant" in formatted, "Missing assistant token"
        assert "Test scenario" in formatted, "Missing scenario text"
        results["passed"].append("chat_template format_example")
    except Exception as e:
        results["errors"].append(f"format_example: {e}")

    # 3. SFTConfig argument names (validate what we'll pass)
    try:
        cfg = SFTConfig(
            output_dir="/tmp/test",
            learning_rate=2e-4,
            num_train_epochs=1,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=1,
            max_length=128,
            logging_steps=1,
            save_strategy="no",
            eval_strategy="no",
            bf16=False,
            report_to="none",
            dataset_text_field="text",
            seed=42,
        )
        results["passed"].append("SFTConfig arguments")
    except TypeError as e:
        results["errors"].append(f"SFTConfig argument mismatch: {e}")
    except Exception as e:
        results["errors"].append(f"SFTConfig: {e}")

    # 4. LoraConfig validates
    try:
        lora = LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
        )
        results["passed"].append("LoraConfig")
    except Exception as e:
        results["errors"].append(f"LoraConfig: {e}")

    # 5. Dataset shape — load and inspect splits/columns
    try:
        dataset = load_dataset(dataset_repo)
        splits = list(dataset.keys())
        results["passed"].append(f"dataset splits: {splits}")
        if "train" not in splits:
            results["errors"].append("No 'train' split in dataset.")
        if "test" in splits:
            results["errors"].append(
                "Dataset contains a 'test' split. "
                "The frozen test set must never be uploaded to the training repo."
            )
        train_cols = list(dataset["train"].column_names)
        required_cols = {"home_team", "away_team", "text", "expected"}
        missing = required_cols - set(train_cols)
        if missing:
            results["errors"].append(f"Training split missing columns: {missing}")
        results["passed"].append(f"train columns: {train_cols}")
        results["passed"].append(f"train rows: {len(dataset['train'])}")
    except Exception as e:
        results["errors"].append(f"dataset load: {e}")

    # 6. Verify No bitsandbytes dtype issues (validate config shape only)
    try:
        from transformers import BitsAndBytesConfig
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype="bfloat16",
            bnb_4bit_quant_type="nf4",
        )
        results["passed"].append("BitsAndBytesConfig")
    except Exception as e:
        results["errors"].append(f"BitsAndBytesConfig: {e}")

    all_ok = len(results["errors"]) == 0
    results["ready_for_gpu"] = all_ok
    print(json.dumps(results, indent=2))
    return results


@app.function(
    image=image,
    gpu="A10G",
    timeout=60 * 60 * 4,
    volumes={"/artifacts": volume},
    secrets=[_hf_secret],
)
def train(
    dataset_repo: str,
    output_repo: str,
    base_model: str = "HuggingFaceTB/SmolLM2-360M-Instruct",
    seed: int = 42,
) -> dict:
    if "test" in dataset_repo.lower() and "test" not in output_repo.lower():
        raise ValueError(
            "Refusing to train on a dataset that appears to be a test split. "
            "The frozen test set must never be used for training. "
            f"Got dataset_repo={dataset_repo!r}. "
            "Use a training or validation split instead."
        )

    from datasets import load_dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Verify the tokenizer has a chat template before training.
    # SmolLM2 uses ChatML: <|im_start|>system\n...<|im_end|>\n<|im_start|>user\n...<|im_end|>\n...
    if not getattr(tokenizer, "chat_template", None):
        raise ValueError(
            f"Tokenizer for {base_model} has no chat_template. "
            "Training and runtime must use the same chat template."
        )
    print(f"Chat template prefix: {str(tokenizer.chat_template)[:120]}...")
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype="bfloat16",
        bnb_4bit_quant_type="nf4",
    )
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        device_map="auto",
        quantization_config=quantization,
        torch_dtype="auto",
        trust_remote_code=True,
    )
    dataset = load_dataset(dataset_repo)

    def format_example(example):
        expected = example["expected"]
        assistant_json = json.dumps(expected, ensure_ascii=True, sort_keys=True)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": user_content(
                    home_team=example["home_team"],
                    away_team=example["away_team"],
                    text=example["text"],
                    neutral_venue=example.get("neutral_venue", True),
                ),
            },
            {"role": "assistant", "content": assistant_json},
        ]
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
        return {"text": text}

    train_dataset = dataset["train"].map(format_example)
    validation_dataset = dataset.get("validation")
    if validation_dataset is not None:
        validation_dataset = validation_dataset.map(format_example)

    output_dir = "/artifacts/adapter"
    training_config = {
        "base_model": base_model,
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "learning_rate": 2e-4,
        "num_train_epochs": 3,
        "per_device_train_batch_size": 2,
        "gradient_accumulation_steps": 8,
        "max_length": 768,
        "seed": seed,
        "dataset_repo": dataset_repo,
        "output_repo": output_repo,
    }
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        peft_config=LoraConfig(
            r=training_config["lora_r"],
            lora_alpha=training_config["lora_alpha"],
            lora_dropout=training_config["lora_dropout"],
            bias="none",
            task_type="CAUSAL_LM",
        ),
        args=SFTConfig(
            output_dir=output_dir,
            learning_rate=training_config["learning_rate"],
            num_train_epochs=training_config["num_train_epochs"],
            per_device_train_batch_size=training_config["per_device_train_batch_size"],
            gradient_accumulation_steps=training_config["gradient_accumulation_steps"],
            max_length=training_config["max_length"],
            logging_steps=10,
            save_strategy="epoch",
            eval_strategy="epoch" if validation_dataset is not None else "no",
            bf16=True,
            report_to="none",
            dataset_text_field="text",
            seed=training_config["seed"],
            data_seed=training_config["seed"],
        ),
    )
    trainer.train()

    # Save training configuration alongside the adapter
    config_path = f"{output_dir}/training_config.json"
    with open(config_path, "w") as fh:
        json.dump(training_config, fh, indent=2)

    trainer.model.push_to_hub(output_repo, token=os.environ["HF_TOKEN"])
    volume.commit()
    return {"adapter": output_repo, "artifacts": output_dir, "config": training_config}


@app.local_entrypoint()
def main(dataset_repo: str, output_repo: str) -> None:
    print(train.remote(dataset_repo, output_repo))
