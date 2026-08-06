"""Build deterministic, scope-limited evidence for paper mDhyxu8WRb."""

import argparse
import csv
import json
import math
import platform
from pathlib import Path

import torch

from .ablation import run_dimensional_ablations
from .propagation import evaluate_toy_propagation
from .sinkhorn import projection_diagnostics, sinkhorn_knopp_projection

PAPER_ID = "mDhyxu8WRb"
ATTEMPT_ID = "3d164e18-39ef-416e-b986-96b5a5d4e12d"
UPSTREAM_REVISION = (
    "arxiv:2512.24880v2+"
    "github:tokenbender/mHC-manifold-constrained-hyper-connections@"
    "ad20d0d8db4d6fc7e8d9b148281167141da20d47"
)
LIVE_CLAIMS = (
    (
        "claim-1",
        "mHC constrains hyper-connection residual mappings by projecting them "
        "onto a manifold to preserve stability relative to unconstrained HC "
        "(Figure 1, Section 4.1).",
        "bdf296450b900b06ca2efbc1ffe702d9547371e3d847e6a31c71d977e0bfa052",
    ),
    (
        "claim-2",
        "HC component ablations test the roles of pre, post, and residual "
        "mappings while maintaining dimensional consistency with fixed "
        "mappings (Table 1).",
        "fa35812d9e1626bcfe1702f946f3926128f6012071af6ef378e0241e30881823",
    ),
    (
        "claim-3",
        "Training and propagation analyses show unconstrained HC has larger "
        "loss gaps, gradient norms, and residual propagation instability than "
        "mHC (Figure 2, Figure 3, Figure 5, Figure 7).",
        "15537486e4923b51864ce7b52999581519cde779ca9e03eda2ad93117abc9735",
    ),
    (
        "claim-4",
        "The paper introduces kernel fusion, recomputing, and "
        "communication-overlap infrastructure to reduce mHC system overhead "
        "(Section 4.3, Table 2, Table 3, Figure 4).",
        "2fd1e3570d1437de16597b0b942dc8d2f4a0045e84fd066bf01da44a86c86959",
    ),
    (
        "claim-5",
        "At 27B scale, mHC outperforms the baseline and surpasses HC on most "
        "zero-shot and few-shot downstream benchmarks (Table 4).",
        "f67e1f1f781f58d9e6c928002254a5dda7d94078db32408893971d6985094a02",
    ),
)


def _claim(
    index: int,
    *,
    status: str,
    evidence_kind: str,
    observation: str,
    limitation: str,
    metrics: dict[str, object] | None = None,
) -> dict[str, object]:
    claim_id, text, digest = LIVE_CLAIMS[index]
    result: dict[str, object] = {
        "claim_id": claim_id,
        "text": text,
        "challenge_claim_sha256": digest,
        "status": status,
        "evidence_kind": evidence_kind,
        "observation": observation,
        "limitation": limitation,
    }
    if metrics is not None:
        result["metrics"] = metrics
    return result


def _reject_nonfinite(value: object, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite float at {path}: {value!r}")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_nonfinite(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_nonfinite(child, f"{path}[{index}]")


def build_evidence(n_sinkhorn_iters: int = 100) -> dict[str, object]:
    """Compute the complete five-claim evidence bundle on deterministic CPU inputs."""
    generator = torch.Generator().manual_seed(42)
    logits = torch.randn(4, 4, dtype=torch.float64, generator=generator)
    projected = sinkhorn_knopp_projection(logits, n_iters=n_sinkhorn_iters)
    projection = projection_diagnostics(projected)

    ablations = run_dimensional_ablations(
        stream_counts=(2, 4, 8),
        hidden_dims=(8, 16, 32),
        seeds=(17, 42, 123),
        n_samples=8,
        n_sinkhorn_iters=n_sinkhorn_iters,
    )
    toy_propagation = evaluate_toy_propagation(
        depths=(10, 50, 100),
        stream_counts=(2, 4, 8),
        seeds=(17, 42, 123),
        n_sinkhorn_iters=n_sinkhorn_iters,
    )
    valid_shapes = sum(bool(row["output_shape_valid"]) for row in ablations)

    claims = [
        _claim(
            0,
            status="partial",
            evidence_kind="computed_projection_invariant",
            observation=(
                "A seeded 4x4 CPU projection was nonnegative and doubly "
                "stochastic; its measured spectral norm was "
                f"{projection['spectral_norm']:.12g}."
            ),
            limitation=(
                "This verifies the implemented projection invariant on one "
                "synthetic matrix, not trained-model stability relative to HC."
            ),
            metrics=projection,
        ),
        _claim(
            1,
            status="partial",
            evidence_kind="toy_dimensional_ablation",
            observation=(
                f"{valid_shapes} of {len(ablations)} seeded synthetic-tensor "
                "rows preserved their expected output shape across eight "
                "mapping variants."
            ),
            limitation=(
                "This tests dimensional consistency only; it does not "
                "reproduce Table 1 task quality or trained component ablations."
            ),
            metrics={
                "rows": len(ablations),
                "valid_shape_rows": valid_shapes,
                "stream_counts": [2, 4, 8],
                "hidden_dims": [8, 16, 32],
                "variants": 8,
            },
        ),
        _claim(
            2,
            status="partial",
            evidence_kind="toy_random_matrix_propagation",
            observation=(
                f"Computed {len(toy_propagation)} paired seeded raw/projected "
                "residual-matrix compositions at depths 10, 50, and 100."
            ),
            limitation=(
                "This tests only a toy residual-propagation mechanism; it does "
                "not reproduce loss gaps, trained gradient norms, or the "
                "paper's model-scale figures."
            ),
            metrics={
                "rows": len(toy_propagation),
                "depths": [10, 50, 100],
                "stream_counts": [2, 4, 8],
                "seeds": [17, 42, 123],
            },
        ),
        _claim(
            3,
            status="unavailable",
            evidence_kind="unavailable",
            observation="No kernel or system measurement was produced.",
            limitation=(
                "No kernel fusion, recomputing, communication-overlap, or "
                "system-overhead benchmark was run."
            ),
        ),
        _claim(
            4,
            status="unavailable",
            evidence_kind="unavailable",
            observation="No model-scale or downstream measurement was produced.",
            limitation="No 27B training or downstream benchmark was run.",
        ),
    ]
    bundle: dict[str, object] = {
        "schema_version": "1.0.0",
        "paper_id": PAPER_ID,
        "attempt_id": ATTEMPT_ID,
        "title": "mHC: Manifold-Constrained Hyper-Connections",
        "upstream_revision": UPSTREAM_REVISION,
        "provenance": {
            "python_version": platform.python_version(),
            "pytorch_version": torch.__version__,
            "device": "cpu",
            "seeds": [17, 42, 123],
            "projection_seed": 42,
            "stream_counts": [2, 4, 8],
            "hidden_dims": [8, 16, 32],
            "depths": [10, 50, 100],
            "sinkhorn_iterations": n_sinkhorn_iters,
            "command": (
                "uv run python -m mhc_repro.cli --output-json evidence.json "
                "--output-csv summary.csv --n-iters 100"
            ),
            "source_revision": UPSTREAM_REVISION,
            "api_cost_usd": 0.0,
        },
        "claims": claims,
        "dimensional_ablations": ablations,
        "toy_propagation": toy_propagation,
        "summary": {
            "claim_statuses": {
                claim["claim_id"]: claim["status"] for claim in claims
            },
            "all_claims_verified": False,
        },
    }
    _reject_nonfinite(bundle)
    return bundle


def write_evidence(
    bundle: dict[str, object],
    output_json: str | Path,
    output_csv: str | Path,
) -> None:
    """Write strict, deterministic JSON and a five-row claim summary."""
    _reject_nonfinite(bundle)
    json_path = Path(output_json)
    csv_path = Path(output_csv)
    json_path.write_text(
        json.dumps(bundle, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ["claim_id", "status", "evidence_kind", "observation", "limitation"]
        )
        for claim in bundle["claims"]:
            writer.writerow(
                [
                    claim["claim_id"],
                    claim["status"],
                    claim["evidence_kind"],
                    claim["observation"],
                    claim["limitation"],
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the scoped mHC CPU audit.")
    parser.add_argument("--output-json", default="evidence.json")
    parser.add_argument("--output-csv", default="summary.csv")
    parser.add_argument("--n-iters", type=int, default=100)
    args = parser.parse_args()

    write_evidence(
        build_evidence(n_sinkhorn_iters=args.n_iters),
        args.output_json,
        args.output_csv,
    )
    print(f"Evidence written to {args.output_json} and {args.output_csv}")


if __name__ == "__main__":
    main()
