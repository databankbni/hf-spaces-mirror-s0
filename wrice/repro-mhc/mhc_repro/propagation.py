"""Paired toy residual-matrix composition for propagation analysis."""

import torch

from .sinkhorn import sinkhorn_knopp_projection


def amax_gain_magnitudes(
    composite: torch.Tensor,
) -> dict[str, float]:
    """Compute the forward and backward absolute-max gain of a composite matrix."""
    return {
        "forward_amax": float(composite.abs().amax().item()),
        "backward_amax": float(composite.T.abs().amax().item()),
    }


def evaluate_toy_propagation(
    depths: tuple[int, ...] = (10, 50, 100),
    stream_counts: tuple[int, ...] = (2, 4, 8),
    seeds: tuple[int, ...] = (17, 42, 123),
    n_sinkhorn_iters: int = 100,
) -> list[dict[str, float | int | str]]:
    """Evaluate paired unconstrained vs projected matrix composition at varying depths.

    Each record contains paired raw/projected results from the same seeded logits.
    ``evidence_kind`` is always ``toy_random_matrix_propagation``.
    """
    requested_depths = tuple(sorted(set(depths)))
    if not requested_depths or requested_depths[0] < 1:
        raise ValueError("depths must contain positive integers")

    rows: list[dict[str, float | int | str]] = []
    for seed in seeds:
        for stream_count in stream_counts:
            generator = torch.Generator().manual_seed(seed)
            raw_composite = torch.eye(stream_count, dtype=torch.float64)
            projected_composite = torch.eye(stream_count, dtype=torch.float64)
            for depth in range(1, requested_depths[-1] + 1):
                logits = torch.randn(
                    stream_count,
                    stream_count,
                    dtype=torch.float64,
                    generator=generator,
                )
                raw_composite = logits @ raw_composite
                projected_composite = (
                    sinkhorn_knopp_projection(
                        logits,
                        n_iters=n_sinkhorn_iters,
                    )
                    @ projected_composite
                )
                if depth in requested_depths:
                    raw = amax_gain_magnitudes(raw_composite)
                    projected = amax_gain_magnitudes(projected_composite)
                    rows.append(
                        {
                            "seed": seed,
                            "stream_count": stream_count,
                            "depth": depth,
                            "evidence_kind": "toy_random_matrix_propagation",
                            "unconstrained_forward_amax": raw["forward_amax"],
                            "unconstrained_backward_amax": raw["backward_amax"],
                            "projected_forward_amax": projected["forward_amax"],
                            "projected_backward_amax": projected["backward_amax"],
                        }
                    )
    return rows


def evaluate_signal_propagation(
    depth: int = 30,
    K: int = 4,
    d_model: int = 16,
    n_steps: int = 20,
) -> dict:
    """Legacy backward compatibility shim; retained but excluded from evidence generation."""
    from .layers import (
        HyperConnectionLayer,
        ManifoldHyperConnectionLayer,
        StandardResidualLayer,
    )
    import torch.nn as nn

    results = {}

    torch.manual_seed(42)
    std_layers = nn.ModuleList([StandardResidualLayer(d_model) for _ in range(depth)])
    x_std = torch.randn(8, d_model, requires_grad=True)
    out_std = x_std
    for layer in std_layers:
        out_std = layer(out_std)
    loss_std = out_std.pow(2).mean()
    loss_std.backward()
    grad_norm_std = float(x_std.grad.norm().item())
    norm_ratio_std = float((out_std.norm() / (x_std.norm() + 1e-8)).item())

    results["standard_residual"] = {
        "depth": depth,
        "signal_norm_ratio": norm_ratio_std,
        "gradient_norm": grad_norm_std,
        "loss": float(loss_std.item()),
    }

    torch.manual_seed(42)
    hc_layers = nn.ModuleList(
        [HyperConnectionLayer(K=K, d_model=d_model) for _ in range(depth)]
    )
    x_hc = torch.randn(8, K, d_model, requires_grad=True)
    out_hc = x_hc
    for layer in hc_layers:
        out_hc = layer(out_hc)
    loss_hc = out_hc.pow(2).mean()
    loss_hc.backward()
    grad_norm_hc = float(x_hc.grad.norm().item())
    norm_ratio_hc = float((out_hc.norm() / (x_hc.norm() + 1e-8)).item())

    results["unconstrained_hc"] = {
        "depth": depth,
        "signal_norm_ratio": norm_ratio_hc,
        "gradient_norm": grad_norm_hc,
        "loss": float(loss_hc.item()),
    }

    torch.manual_seed(42)
    mhc_layers = nn.ModuleList(
        [
            ManifoldHyperConnectionLayer(K=K, d_model=d_model, n_sinkhorn_iters=20)
            for _ in range(depth)
        ]
    )
    x_mhc = torch.randn(8, K, d_model, requires_grad=True)
    out_mhc = x_mhc
    for layer in mhc_layers:
        out_mhc = layer(out_mhc)
    loss_mhc = out_mhc.pow(2).mean()
    loss_mhc.backward()
    grad_norm_mhc = float(x_mhc.grad.norm().item())
    norm_ratio_mhc = float((out_mhc.norm() / (x_mhc.norm() + 1e-8)).item())

    results["manifold_mhc"] = {
        "depth": depth,
        "signal_norm_ratio": norm_ratio_mhc,
        "gradient_norm": grad_norm_mhc,
        "loss": float(loss_mhc.item()),
    }

    return results
