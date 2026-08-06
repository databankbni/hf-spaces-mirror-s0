import math

import pytest

from mhc_repro.propagation import evaluate_toy_propagation


def test_toy_propagation_is_paired_bounded_and_explicitly_toy():
    rows = evaluate_toy_propagation(
        depths=(10, 50),
        stream_counts=(2, 4),
        seeds=(17, 42),
        n_sinkhorn_iters=100,
    )

    assert len(rows) == 2 * 2 * 2
    assert all(row["evidence_kind"] == "toy_random_matrix_propagation" for row in rows)
    assert all(math.isfinite(value) for row in rows for value in (
        row["projected_forward_amax"],
        row["projected_backward_amax"],
    ))
    for row in rows:
        # Projected doubly-stochastic composition converges to 1/K;
        # bound is <= 1.0 (the spectral-norm guarantee).
        assert row["projected_forward_amax"] <= 1.0 + 1e-5
        assert row["projected_backward_amax"] <= 1.0 + 1e-5


def test_toy_propagation_rejects_nonpositive_depths():
    with pytest.raises(ValueError, match="positive"):
        evaluate_toy_propagation(depths=(0,))
