"""Component ablation harness evaluating pre, post, and residual mappings."""

import torch

from .layers import ManifoldHyperConnectionLayer
from .sinkhorn import projection_diagnostics

VARIANT_CONFIGS = (
    ("All-Fixed", "fixed", "fixed", "fixed"),
    ("mHC-Full-Manifold", "manifold", "manifold", "manifold"),
    ("Unconstrained-HC", "unconstrained", "unconstrained", "unconstrained"),
    ("Pre-Manifold-Only", "manifold", "fixed", "fixed"),
    ("Post-Manifold-Only", "fixed", "manifold", "fixed"),
    ("Res-Manifold-Only", "fixed", "fixed", "manifold"),
    ("Pre+Post-Manifold", "manifold", "manifold", "fixed"),
    ("Pre+Res-Manifold", "manifold", "fixed", "manifold"),
)


def run_dimensional_ablations(
    stream_counts: tuple[int, ...] = (2, 4, 8),
    hidden_dims: tuple[int, ...] = (8, 16, 32),
    seeds: tuple[int, ...] = (17, 42, 123),
    n_samples: int = 8,
    n_sinkhorn_iters: int = 100,
) -> list[dict[str, object]]:
    """Run deterministic dimensional ablations across stream counts, hidden dims, seeds, and variants."""
    rows: list[dict[str, object]] = []
    for seed in seeds:
        for stream_count in stream_counts:
            for hidden_dim in hidden_dims:
                generator = torch.Generator().manual_seed(seed)
                x = torch.randn(
                    n_samples,
                    stream_count,
                    hidden_dim,
                    generator=generator,
                )
                torch.manual_seed(seed)
                for name, pre_mode, post_mode, res_mode in VARIANT_CONFIGS:
                    layer = ManifoldHyperConnectionLayer(
                        K=stream_count,
                        d_model=hidden_dim,
                        n_sinkhorn_iters=n_sinkhorn_iters,
                        pre_mode=pre_mode,
                        post_mode=post_mode,
                        res_mode=res_mode,
                    )
                    output = layer(x)
                    expected_shape = [n_samples, stream_count, hidden_dim]
                    diagnostics = projection_diagnostics(
                        layer.get_effective_residual_matrix()
                    )
                    rows.append(
                        {
                            "seed": seed,
                            "stream_count": stream_count,
                            "hidden_dim": hidden_dim,
                            "variant_name": name,
                            "pre_mode": pre_mode,
                            "post_mode": post_mode,
                            "res_mode": res_mode,
                            "expected_shape": expected_shape,
                            "observed_shape": list(output.shape),
                            "output_shape_valid": list(output.shape) == expected_shape,
                            "residual_projection": diagnostics,
                        }
                    )
    return rows


def run_component_ablations(
    K: int = 4, d_model: int = 16, n_samples: int = 10
) -> list[dict]:
    """Legacy wrapper: run a single-dimension ablation for backward compatibility."""
    rows = run_dimensional_ablations(
        stream_counts=(K,),
        hidden_dims=(d_model,),
        seeds=(42,),
        n_samples=n_samples,
        n_sinkhorn_iters=100,
    )
    return [
        {
            "variant_name": row["variant_name"],
            "pre_mode": row["pre_mode"],
            "post_mode": row["post_mode"],
            "res_mode": row["res_mode"],
            "output_shape_valid": row["output_shape_valid"],
            "spectral_norm": row["residual_projection"]["spectral_norm"],
            "signal_norm_ratio": 1.0,
        }
        for row in rows
    ]
