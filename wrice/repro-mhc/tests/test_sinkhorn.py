import pytest
import torch

from mhc_repro.sinkhorn import (
    projection_diagnostics,
    sinkhorn_knopp_projection,
)


@pytest.mark.parametrize("stream_count", [2, 4, 8])
def test_projection_diagnostics_hold_across_stream_counts(stream_count):
    generator = torch.Generator().manual_seed(42 + stream_count)
    logits = torch.randn(
        3, stream_count, stream_count, dtype=torch.float64, generator=generator
    )
    projected = sinkhorn_knopp_projection(logits)
    diagnostics = projection_diagnostics(projected)

    assert diagnostics["nonnegative"] is True
    assert diagnostics["max_row_error"] <= 1e-6
    assert diagnostics["max_column_error"] <= 1e-6
    assert diagnostics["spectral_norm"] <= 1.0 + 1e-6
    assert diagnostics["is_doubly_stochastic"] is True


@pytest.mark.parametrize(
    ("logits", "n_iters", "message"),
    [
        (torch.randn(2, 3), 100, "square"),
        (torch.randn(2, 2), 0, "positive"),
    ],
)
def test_projection_rejects_invalid_inputs(logits, n_iters, message):
    with pytest.raises(ValueError, match=message):
        sinkhorn_knopp_projection(logits, n_iters=n_iters)
