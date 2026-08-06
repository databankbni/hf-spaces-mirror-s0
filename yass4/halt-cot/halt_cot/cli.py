"""Command line entrypoint for HALT-CoT."""

from __future__ import annotations

import argparse
import json

from .core import (
    HaltCoTConfig,
    integer_candidates,
    multiple_choice_candidates,
    yes_no_candidates,
)
from .transformers_backend import HaltCoTForCausalLM


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run HALT-CoT with a Hugging Face causal LM.")
    parser.add_argument("--model", required=True, help="Hugging Face model id or local model path.")
    parser.add_argument("--question", required=True, help="Question to answer.")
    parser.add_argument(
        "--candidate-set",
        choices=("custom", "yes-no", "multiple-choice", "integers"),
        default="custom",
        help="Candidate answer set.",
    )
    parser.add_argument(
        "--candidates",
        nargs="*",
        default=None,
        help="Custom candidate labels, e.g. --candidates Yes No or --candidates A B C D E.",
    )
    parser.add_argument("--integer-start", type=int, default=0)
    parser.add_argument("--integer-end", type=int, default=100)
    parser.add_argument("--theta", type=float, default=0.6)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--min-steps", type=int, default=1)
    parser.add_argument("--consecutive", type=int, default=2)
    parser.add_argument("--step-max-new-tokens", type=int, default=96)
    parser.add_argument("--entropy-unit", choices=("bits", "nats"), default="bits")
    parser.add_argument("--device-map", default=None, help="Optional Transformers device_map, e.g. auto.")
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    candidates = _resolve_candidates(args)
    config = HaltCoTConfig(
        theta=args.theta,
        max_steps=args.max_steps,
        min_steps=args.min_steps,
        consecutive_low_entropy=args.consecutive,
        step_max_new_tokens=args.step_max_new_tokens,
        entropy_unit=args.entropy_unit,
    )

    runner = HaltCoTForCausalLM.from_pretrained(
        args.model,
        config=config,
        device_map=args.device_map,
        trust_remote_code=args.trust_remote_code,
    )
    result = runner.run(args.question, candidates)

    if args.json:
        print(
            json.dumps(
                {
                    "answer": result.answer,
                    "halted": result.halted,
                    "generated_tokens": result.generated_tokens,
                    "steps": [
                        {
                            "index": step.index,
                            "text": step.text,
                            "entropy": step.entropy,
                            "prediction": step.prediction,
                            "probabilities": step.probabilities,
                            "halted": step.halted,
                            "generated_tokens": step.generated_tokens,
                        }
                        for step in result.steps
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"Answer: {result.answer}")
        print(f"Halted: {result.halted}")
        print(f"Generated tokens: {result.generated_tokens}")
        print("\nTrace:")
        for step in result.steps:
            marker = " HALT" if step.halted else ""
            print(
                f"- Step {step.index}: H={step.entropy:.3f} "
                f"pred={step.prediction!r}{marker} | {step.text}"
            )
    return 0


def _resolve_candidates(args: argparse.Namespace):
    if args.candidate_set == "yes-no":
        return yes_no_candidates()
    if args.candidate_set == "multiple-choice":
        labels = args.candidates or ["A", "B", "C", "D", "E"]
        return multiple_choice_candidates(labels)
    if args.candidate_set == "integers":
        return integer_candidates(args.integer_start, args.integer_end)
    if not args.candidates:
        raise SystemExit("--candidates is required when --candidate-set custom")
    return args.candidates


if __name__ == "__main__":
    raise SystemExit(main())
