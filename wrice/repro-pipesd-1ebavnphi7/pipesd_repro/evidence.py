from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.request import urlopen


PAPER_ID = "1ebAvNphi7"
ATTEMPT_ID = "b14aa81b-94e3-44ef-9348-6b07ea0b5a5c"
UPSTREAM_COMMIT = "dac0f52eae7ba55e5def2d82003d8413cb58340c"
UPSTREAM_REVISION = (
    "arxiv:2605.13319+github:Ghanyunhe/PipeSD@"
    "dac0f52eae7ba55e5def2d82003d8413cb58340c"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE_PATH = PROJECT_ROOT / "evidence" / "bundle.json"
DEFAULT_GENERATED_AT = "2026-07-31T22:10:00+00:00"
RAW_BASE_URL = (
    "https://raw.githubusercontent.com/Ghanyunhe/PipeSD/"
    f"{UPSTREAM_COMMIT}"
)
SOURCE_FILES = {
    "edge/src/merge.py": "merge",
    "edge/src/util.py": "util",
    "edge/src/engine.py": "engine",
}

CLAIM_BINDINGS = [
    {
        "claim_id": "dynamic_token_batch_pipeline_scheduling",
        "challenge_claim": (
            "PipeSD overlaps draft-token generation and communication using "
            "token-batch pipeline scheduling optimized by dynamic programming "
            "(Section 3.2)"
        ),
        "challenge_claim_sha256": (
            "19a23e4cc1dfac8ce0e14f60a54e7e0936077f6a149691b73bd82ab72db5672e"
        ),
    },
    {
        "claim_id": "dual_threshold_nav_trigger",
        "challenge_claim": (
            "PipeSD uses a dual-threshold NAV triggering mechanism that jointly "
            "considers cumulative sequence confidence and single-token "
            "confidence (Section 3.3)"
        ),
        "challenge_claim_sha256": (
            "ef7fc12943849e199ae46aa7e3e68b0392afb74ad1d465c887bcb3a9b645066b"
        ),
    },
    {
        "claim_id": "cloud_edge_tpt_speedup",
        "challenge_claim": (
            "On a real-world cloud-edge testbed, PipeSD achieves 1.16x-2.16x "
            "average TPT speedups over Vanilla, HSL, and EdgeLLM baselines "
            "across evaluated scenarios (Table 1)"
        ),
        "challenge_claim_sha256": (
            "651f5398d2c1c126833b744194616b752fc60b9cef263682a222b6249f70abc6"
        ),
    },
    {
        "claim_id": "cloud_energy_reduction",
        "challenge_claim": (
            "PipeSD reduces cloud-side energy consumption per 100 accepted "
            "tokens by 14.3%-25.3% in Scenario 1 compared with baselines "
            "(Table 2)"
        ),
        "challenge_claim_sha256": (
            "3c511c720fbd513d61ff2a39da8ca826396895a24df8c3aa298a2dcee8ab1c5e"
        ),
    },
    {
        "claim_id": "bandwidth_speedup_robustness",
        "challenge_claim": (
            "PipeSD maintains speedup advantages across tested bandwidth levels "
            "on HumanEval in Scenario 1 (Figure 5)"
        ),
        "challenge_claim_sha256": (
            "37e3fa7419bffd7cac19378b322436bf0441863e6280dfe7cb474032731b5981"
        ),
    },
    {
        "claim_id": "ablation_attribution",
        "challenge_claim": (
            "Ablation results attribute performance improvements to token-batch "
            "pipeline scheduling and dual-threshold NAV triggering (Table 6)"
        ),
        "challenge_claim_sha256": (
            "bcac47ee366ac75226729fc824ae41974abea417562e27947dddfa93d85e184d"
        ),
    },
]


def _now_iso() -> str:
    override = os.environ.get("ICML_REPRO_GENERATED_AT")
    if override:
        return override
    return DEFAULT_GENERATED_AT


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_source_file(source_root: Path | None, relative_path: str) -> str:
    if source_root is not None:
        return (source_root / relative_path).read_text(encoding="utf-8")
    with urlopen(f"{RAW_BASE_URL}/{relative_path}", timeout=30) as response:
        return response.read().decode("utf-8")


def _collect_source_files() -> dict[str, dict[str, str]]:
    source_env = os.environ.get("PIPESD_SOURCE_DIR")
    source_root = Path(source_env).resolve() if source_env else None
    collected: dict[str, dict[str, str]] = {}
    for relative_path in SOURCE_FILES:
        text = _read_source_file(source_root, relative_path)
        collected[relative_path] = {
            "sha256": _sha256_text(text),
            "text": text,
            "source": (
                str(source_root / relative_path)
                if source_root is not None
                else f"{RAW_BASE_URL}/{relative_path}"
            ),
        }
    return collected


def _contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def _implementation_summary(sources: dict[str, dict[str, str]]) -> dict[str, bool]:
    merge = sources["edge/src/merge.py"]["text"]
    util = sources["edge/src/util.py"]["text"]
    engine = sources["edge/src/engine.py"]["text"]

    dynamic_dp = _contains_all(
        merge,
        [
            "dynamic_token_scheduling_dp",
            "DP =",
            "P =",
            "for j in range(i + 1)",
            "batches.reverse()",
        ],
    )
    engine_uses_dp = _contains_all(
        engine,
        [
            "from .merge import dynamic_token_scheduling_dp",
            "self.merge_policy",
            "dynamic_token_scheduling_dp(",
            "return [len(batch) for batch in batches",
        ],
    )
    threshold_args = _contains_all(
        util,
        [
            "verify_thresh_single",
            "verify_thresh_multi",
            "single-token",
            "multiple-tokens",
            "hybrid",
        ],
    )
    pipesd_sets_hybrid = _contains_all(
        util,
        [
            "pipesd",
            "verify_strategy",
            "hybrid",
        ],
    )
    engine_hybrid = _contains_all(
        engine,
        [
            "verify_mode",
            "hybrid",
            "single_flag",
            "multi_flag",
            "self.verify_thresh_single",
            "self.verify_thresh_multi",
            "return (single_flag or multi_flag)",
        ],
    )

    return {
        "dynamic_token_scheduling_dp": dynamic_dp,
        "engine_uses_dp_merge_plan": engine_uses_dp,
        "single_and_multi_threshold_args": threshold_args,
        "hybrid_strategy_sets_dual_thresholds": pipesd_sets_hybrid and engine_hybrid,
    }


def _claim_results(summary: dict[str, bool]) -> list[dict[str, object]]:
    source_claims = [
        {
            **CLAIM_BINDINGS[0],
            "status": (
                "verified"
                if summary["dynamic_token_scheduling_dp"]
                and summary["engine_uses_dp_merge_plan"]
                else "unavailable"
            ),
            "evidence": [
                "edge/src/merge.py defines dynamic_token_scheduling_dp with DP/P tables and backtracked batches.",
                "edge/src/engine.py imports dynamic_token_scheduling_dp and resolves dp merge plans into batch lengths.",
            ],
            "limitations": [
                "This verifies released implementation structure, not cloud-edge throughput measurements.",
            ],
        },
        {
            **CLAIM_BINDINGS[1],
            "status": (
                "verified"
                if summary["single_and_multi_threshold_args"]
                and summary["hybrid_strategy_sets_dual_thresholds"]
                else "unavailable"
            ),
            "evidence": [
                "edge/src/util.py exposes verify_thresh_single and verify_thresh_multi parser controls.",
                "edge/src/engine.py hybrid verification triggers on either single-token or cumulative probability thresholds.",
            ],
            "limitations": [
                "This verifies NAV trigger implementation, not ablation or speedup values.",
            ],
        },
    ]
    measurement_limitations = [
        "The released artifact inspection does not recreate the reported cloud-edge hardware testbed.",
        "Paper table values are not counted as reproduced measurements.",
    ]
    measurement_claims = [
        {
            **binding,
            "status": "unavailable",
            "evidence": [
                "No independent CPU-only reproduction of this measurement is available in the released source-inspection artifact.",
            ],
            "limitations": measurement_limitations,
        }
        for binding in CLAIM_BINDINGS[2:]
    ]
    return source_claims + measurement_claims


def build_evidence_bundle() -> dict[str, object]:
    sources = _collect_source_files()
    summary = _implementation_summary(sources)
    file_hashes = [
        {
            "path": relative_path,
            "sha256": record["sha256"],
            "source": record["source"],
        }
        for relative_path, record in sorted(sources.items())
    ]

    return {
        "paper_id": PAPER_ID,
        "attempt_id": ATTEMPT_ID,
        "title": (
            "PipeSD: An Efficient Cloud-Edge Collaborative Pipeline Inference "
            "Framework with Speculative Decoding"
        ),
        "generated_at": _now_iso(),
        "upstream_revision": UPSTREAM_REVISION,
        "upstream_commit": UPSTREAM_COMMIT,
        "artifact_access": "pinned GitHub raw files",
        "estimated_api_cost_usd": 0.0,
        "claims": _claim_results(summary),
        "implementation_summary": summary,
        "file_hashes": file_hashes,
        "unreplicated_claims": [
            "1.16x-2.16x average TPT speedups over baselines",
            "14.3%-25.3% cloud-side energy reductions",
            "bandwidth-level speedup and ablation-result claims",
        ],
        "licensing": {
            "status": "unclear",
            "observation": "No explicit license file was identified in the pinned repository assessment.",
        },
    }


def write_evidence_bundle(output_path: str | Path = DEFAULT_BUNDLE_PATH) -> dict[str, object]:
    bundle = build_evidence_bundle()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return bundle


def load_evidence_bundle(path: str | Path = DEFAULT_BUNDLE_PATH) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def render_summary_markdown(bundle: dict[str, object]) -> str:
    claims = bundle["claims"]
    rows = "\n".join(
        f"- `{claim['status']}` `{claim['challenge_claim_sha256']}`: {claim['challenge_claim']}"
        for claim in claims
    )
    return (
        "# PipeSD Reproduction Evidence\n\n"
        f"Paper `{bundle['paper_id']}` is assessed from pinned upstream revision "
        f"`{bundle['upstream_revision']}`.\n\n"
        "This bundle verifies implementation-structure claims by inspecting "
        "released source files and marks cloud-edge measurement claims as "
        "unavailable unless independently recomputed. It does not reuse "
        "paper-reported throughput, energy, bandwidth, or ablation metrics as "
        "reproduced measurements.\n\n"
        f"{rows}"
    )
