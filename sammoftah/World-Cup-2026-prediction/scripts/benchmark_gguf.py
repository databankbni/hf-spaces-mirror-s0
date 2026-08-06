from __future__ import annotations

"""Benchmark GGUF variants against the frozen test set.

Produces the comparison table required by Phase 0.6:
  Model | Quant | Factor F1 | Team Attribution | Exact Match | Median | P90 | Fallback

Usage:
  # Base model
  UNDERDOG_MODEL_PATH=models/SmolLM2-360M-Instruct-Q4_K_M.gguf \
    python scripts/benchmark_gguf.py --label "Base Q4" --output results/base_q4.json

  # Tuned model
  UNDERDOG_MODEL_PATH=models/underdog-lab-qlora-Q4_K_M.gguf \
    python scripts/benchmark_gguf.py --label "Tuned Q4" --output results/tuned_q4.json

  # Compare all
  python scripts/benchmark_gguf.py --compare results/base_q4.json results/base_q5.json ...
"""

import argparse
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

from underdog_lab.domain import MatchRecord
from underdog_lab.scenarios.factory import build_extractor
from underdog_lab.scenarios.schemas import ScenarioExtraction


def factor_keys(extraction: ScenarioExtraction) -> set[tuple[str, str]]:
    return {(f.factor_type.value, f.team) for f in extraction.factors}


def benchmark(test_set: Path, label: str, output_path: Path) -> dict:
    extractor = build_extractor()
    backend = extractor.name
    tp = fp = fn = 0
    team_correct = team_total = 0
    unsupported_tp = unsupported_fp = unsupported_fn = 0
    ambiguity_tp = ambiguity_fp = ambiguity_fn = 0
    severity_errors = []
    exact_matches = 0
    per_factor = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    latencies = []
    schema_valid = 0
    fallback_count = 0
    examples = []

    with test_set.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            expected = ScenarioExtraction.model_validate(row["expected"])
            match = MatchRecord(
                match_id=row["id"],
                kickoff_date="2026-01-01",
                competition="Evaluation",
                stage="Test",
                home_team=row["home_team"],
                away_team=row["away_team"],
                venue="Evaluation venue",
                neutral_venue=True,
                home_goals=0,
                away_goals=0,
                pre_match_home_elo=1800,
                pre_match_away_elo=1800,
                lambda_home=1.18,
                lambda_away=1.18,
                context="Frozen extraction benchmark.",
            )
            started = time.perf_counter()
            actual = extractor.extract(row["text"], match)
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies.append(elapsed_ms)

            actual_backend = getattr(extractor, "last_backend", backend)
            if "fallback" in actual_backend.lower():
                fallback_count += 1

            # Schema validity (Pydantic validation already passed; check JSON round-trip)
            try:
                json.dumps(actual.model_dump(mode="json"))
                schema_valid += 1
            except Exception:
                pass

            expected_keys = factor_keys(expected)
            actual_keys = factor_keys(actual)
            tp += len(expected_keys & actual_keys)
            fp += len(actual_keys - expected_keys)
            fn += len(expected_keys - actual_keys)

            for ft, _ in expected_keys & actual_keys:
                per_factor[ft]["tp"] += 1
            for ft, _ in actual_keys - expected_keys:
                per_factor[ft]["fp"] += 1
            for ft, _ in expected_keys - actual_keys:
                per_factor[ft]["fn"] += 1

            # Team attribution: only count when factor type matches
            expected_by_type = {f.factor_type.value: f for f in expected.factors}
            actual_by_type = {f.factor_type.value: f for f in actual.factors}
            for ft, e_factor in expected_by_type.items():
                team_total += 1
                a_factor = actual_by_type.get(ft)
                if a_factor and a_factor.team == e_factor.team:
                    team_correct += 1
                    severity_errors.append(abs(e_factor.severity - a_factor.severity))

            expected_unsup = bool(expected.unsupported_claims)
            actual_unsup = bool(actual.unsupported_claims)
            unsupported_tp += expected_unsup and actual_unsup
            unsupported_fp += not expected_unsup and actual_unsup
            unsupported_fn += expected_unsup and not actual_unsup

            expected_ambig = bool(expected.ambiguities)
            actual_ambig = bool(actual.ambiguities)
            ambiguity_tp += expected_ambig and actual_ambig
            ambiguity_fp += not expected_ambig and actual_ambig
            ambiguity_fn += expected_ambig and not actual_ambig

            exact_matches += (
                expected_keys == actual_keys
                and expected_unsup == actual_unsup
                and expected_ambig == actual_ambig
            )

            examples.append({
                "id": row["id"],
                "text": row["text"],
                "expected": expected.model_dump(mode="json"),
                "actual": actual.model_dump(mode="json"),
            })

    def _binary_f1(tp_val, fp_val, fn_val):
        p = tp_val / (tp_val + fp_val) if tp_val + fp_val else 0.0
        r = tp_val / (tp_val + fn_val) if tp_val + fn_val else 0.0
        return 2 * p * r / (p + r) if p + r else 0.0

    micro_prec = tp / (tp + fp) if tp + fp else 0.0
    micro_rec = tp / (tp + fn) if tp + fn else 0.0
    micro_f1 = (
        2 * micro_prec * micro_rec / (micro_prec + micro_rec)
        if micro_prec + micro_rec else 0.0
    )

    factor_f1s = {
        ft: _binary_f1(c["tp"], c["fp"], c["fn"])
        for ft, c in sorted(per_factor.items())
    }
    macro_f1 = statistics.mean(factor_f1s.values()) if factor_f1s else 0.0

    result = {
        "label": label,
        "backend": backend,
        "examples": len(examples),
        "factor_micro_f1": micro_f1,
        "factor_macro_f1": macro_f1,
        "factor_f1_by_type": factor_f1s,
        "team_attribution_accuracy": team_correct / team_total if team_total else 0.0,
        "end_to_end_exact_match": exact_matches / len(examples) if examples else 0.0,
        "severity_mae": statistics.mean(severity_errors) if severity_errors else None,
        "unsupported_claim_f1": _binary_f1(unsupported_tp, unsupported_fp, unsupported_fn),
        "ambiguity_detection_f1": _binary_f1(ambiguity_tp, ambiguity_fp, ambiguity_fn),
        "schema_validity_rate": schema_valid / len(examples) if examples else 0.0,
        "fallback_rate": fallback_count / len(examples) if examples else 0.0,
        "median_latency_ms": statistics.median(latencies) if latencies else 0.0,
        "p90_latency_ms": (
            sorted(latencies)[int(len(latencies) * 0.9)] if latencies else 0.0
        ),
        "cold_start_warning": "Run once before benchmarking to exclude model-load time.",
        "details": examples,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
    return result


def compare(paths: list[Path]) -> None:
    results = []
    for p in paths:
        results.append(json.loads(p.read_text()))

    header = f"{'Model':<12} {'F1':>7} {'TeamAttr':>9} {'Exact':>7} {'Med(ms)':>9} {'P90(ms)':>9} {'Fallback':>9}"
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)
    for r in results:
        print(
            f"{r['label']:<12} "
            f"{r['factor_micro_f1']:>7.3f} "
            f"{r['team_attribution_accuracy']:>9.3f} "
            f"{r['end_to_end_exact_match']:>7.3f} "
            f"{r['median_latency_ms']:>9.1f} "
            f"{r['p90_latency_ms']:>9.1f} "
            f"{r['fallback_rate']:>9.3f}"
        )
    print(sep)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark a GGUF variant against the frozen test set."
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("data/scenarios/test.jsonl"),
    )
    parser.add_argument("--label", default="unnamed")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/benchmarks/result.json"),
    )
    parser.add_argument(
        "--compare",
        nargs="*",
        type=Path,
        help="Print a comparison table from saved benchmark files.",
    )
    args = parser.parse_args()

    if args.compare:
        compare(args.compare)
    else:
        result = benchmark(args.test_set, args.label, args.output)
        summary = {k: v for k, v in result.items() if k != "details"}
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
