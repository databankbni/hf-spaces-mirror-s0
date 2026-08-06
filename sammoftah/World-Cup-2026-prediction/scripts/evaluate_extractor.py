from __future__ import annotations

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
    return {(factor.factor_type.value, factor.team) for factor in extraction.factors}


def score(path: Path) -> dict:
    extractor = build_extractor()
    tp = fp = fn = 0
    team_correct = team_total = 0
    unsupported_tp = unsupported_fp = unsupported_fn = 0
    ambiguity_tp = ambiguity_fp = ambiguity_fn = 0
    severity_errors = []
    exact_matches = 0
    per_factor = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    latencies = []
    examples = []
    claim_ready = True

    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            claim_ready = claim_ready and row.get("review_status") == "approved"
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
                context="Frozen extraction evaluation.",
            )
            started = time.perf_counter()
            actual = extractor.extract(row["text"], match)
            latencies.append((time.perf_counter() - started) * 1000)
            expected_keys = factor_keys(expected)
            actual_keys = factor_keys(actual)
            tp += len(expected_keys & actual_keys)
            fp += len(actual_keys - expected_keys)
            fn += len(expected_keys - actual_keys)
            for factor_type, team in expected_keys & actual_keys:
                per_factor[factor_type]["tp"] += 1
            for factor_type, team in actual_keys - expected_keys:
                per_factor[factor_type]["fp"] += 1
            for factor_type, team in expected_keys - actual_keys:
                per_factor[factor_type]["fn"] += 1

            expected_unsupported = bool(expected.unsupported_claims)
            actual_unsupported = bool(actual.unsupported_claims)
            unsupported_tp += expected_unsupported and actual_unsupported
            unsupported_fp += not expected_unsupported and actual_unsupported
            unsupported_fn += expected_unsupported and not actual_unsupported

            expected_ambiguous = bool(expected.ambiguities)
            actual_ambiguous = bool(actual.ambiguities)
            ambiguity_tp += expected_ambiguous and actual_ambiguous
            ambiguity_fp += not expected_ambiguous and actual_ambiguous
            ambiguity_fn += expected_ambiguous and not actual_ambiguous

            actual_by_key = {
                (factor.factor_type.value, factor.team): factor
                for factor in actual.factors
            }
            for expected_factor in expected.factors:
                team_total += 1
                team_correct += any(
                    actual_factor.factor_type == expected_factor.factor_type
                    and actual_factor.team == expected_factor.team
                    for actual_factor in actual.factors
                )
                key = (expected_factor.factor_type.value, expected_factor.team)
                if key in actual_by_key:
                    severity_errors.append(
                        abs(expected_factor.severity - actual_by_key[key].severity)
                    )
            exact_matches += (
                expected_keys == actual_keys
                and expected_unsupported == actual_unsupported
                and expected_ambiguous == actual_ambiguous
            )
            examples.append(
                {
                    "id": row["id"],
                    "text": row["text"],
                    "expected": expected.model_dump(mode="json"),
                    "actual": actual.model_dump(mode="json"),
                }
            )

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    unsupported_f1 = _binary_f1(unsupported_tp, unsupported_fp, unsupported_fn)
    ambiguity_f1 = _binary_f1(ambiguity_tp, ambiguity_fp, ambiguity_fn)
    factor_f1s = {
        factor: _binary_f1(counts["tp"], counts["fp"], counts["fn"])
        for factor, counts in sorted(per_factor.items())
    }
    return {
        "extractor": extractor.name,
        "examples": len(examples),
        "factor_micro_precision": precision,
        "factor_micro_recall": recall,
        "factor_micro_f1": f1,
        "factor_macro_f1": (
            statistics.mean(factor_f1s.values()) if factor_f1s else 0.0
        ),
        "factor_f1_by_type": factor_f1s,
        "team_attribution_accuracy": team_correct / team_total if team_total else 0.0,
        "severity_mae_on_matched_factors": (
            statistics.mean(severity_errors) if severity_errors else None
        ),
        "unsupported_claim_f1": unsupported_f1,
        "ambiguity_detection_f1": ambiguity_f1,
        "exact_semantic_match_rate": exact_matches / len(examples) if examples else 0.0,
        "median_latency_ms": statistics.median(latencies) if latencies else 0.0,
        "claim_ready": claim_ready,
        "warning": (
            "" if claim_ready else "This test set contains unreviewed synthetic labels."
        ),
        "details": examples,
    }


def _binary_f1(tp: int, fp: int, fn: int) -> float:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("data/scenarios/test.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/scenarios/evaluation.json"),
    )
    args = parser.parse_args()
    report = score(args.test_set)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in report.items() if key != "details"}, indent=2))


if __name__ == "__main__":
    main()
