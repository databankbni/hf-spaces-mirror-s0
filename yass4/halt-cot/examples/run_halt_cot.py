"""Minimal HALT-CoT example using a Hugging Face causal LM."""

from halt_cot import HaltCoTConfig
from halt_cot.transformers_backend import HaltCoTForCausalLM


def main() -> None:
    runner = HaltCoTForCausalLM.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")
    result = runner.run(
        "If a shop has 12 apples and sells 5, how many apples are left?",
        candidates=["5", "6", "7", "8", "9"],
        config=HaltCoTConfig(theta=0.6, consecutive_low_entropy=2, max_steps=8),
    )
    print(result.answer)
    print(result.reasoning)


if __name__ == "__main__":
    main()
