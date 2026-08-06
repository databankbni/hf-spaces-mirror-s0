"""Sinkhorn-Knopp algorithm for manifold projection onto the Birkhoff polytope."""

import torch


def sinkhorn_knopp_projection(
    logits: torch.Tensor,
    n_iters: int = 100,
    eps: float = 1e-12,
) -> torch.Tensor:
    """
    Project raw square matrices / logits onto the Birkhoff polytope of doubly stochastic matrices.

    Args:
        logits: Tensor of shape (..., K, K)
        n_iters: Number of row-column normalization iterations
        eps: Small constant to avoid division by zero

    Returns:
        Doubly stochastic matrix M of shape (..., K, K) where row sums = 1, col sums = 1, M >= 0.
    """
    if logits.ndim < 2 or logits.shape[-1] != logits.shape[-2]:
        raise ValueError("logits must contain square matrices")
    if n_iters < 1:
        raise ValueError("n_iters must be positive")
    if eps <= 0:
        raise ValueError("eps must be positive")

    matrix = torch.exp(logits - logits.amax(dim=(-2, -1), keepdim=True))
    for _ in range(n_iters):
        matrix = matrix / matrix.sum(dim=-1, keepdim=True).clamp_min(eps)
        matrix = matrix / matrix.sum(dim=-2, keepdim=True).clamp_min(eps)
    return matrix


def projection_diagnostics(
    matrix: torch.Tensor,
    atol: float = 1e-6,
) -> dict[str, float | bool]:
    """Compute diagnostic metrics for a doubly stochastic matrix."""
    row_error = (matrix.sum(dim=-1) - 1.0).abs().max()
    column_error = (matrix.sum(dim=-2) - 1.0).abs().max()
    spectral_norm = torch.linalg.matrix_norm(matrix, ord=2).max()
    nonnegative = bool(torch.all(matrix >= 0).item())
    return {
        "nonnegative": nonnegative,
        "max_row_error": float(row_error.item()),
        "max_column_error": float(column_error.item()),
        "spectral_norm": float(spectral_norm.item()),
        "is_doubly_stochastic": (
            nonnegative
            and row_error.item() <= atol
            and column_error.item() <= atol
        ),
    }


def is_doubly_stochastic(matrix: torch.Tensor, atol: float = 1e-4) -> bool:
    """Verify if a matrix (or batch of matrices) is doubly stochastic."""
    return bool(projection_diagnostics(matrix, atol)["is_doubly_stochastic"])
