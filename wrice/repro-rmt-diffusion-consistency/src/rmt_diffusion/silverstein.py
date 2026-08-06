from __future__ import annotations

import numpy as np


def df1(eigenvalues: np.ndarray, value: float) -> float:
    eig = np.asarray(eigenvalues, dtype=np.float64)
    return float(np.sum(eig / (eig + value)))


def df2(eigenvalues: np.ndarray, value: float, other: float | None = None) -> float:
    eig = np.asarray(eigenvalues, dtype=np.float64)
    if other is None:
        other = value
    return float(np.sum(eig**2 / ((eig + value) * (eig + other))))


def solve_kappa(
    eigenvalues: np.ndarray,
    noise_variance: float,
    n_samples: int,
    *,
    tol: float = 1e-12,
    max_iter: int = 200,
) -> float:
    """Solve the Silverstein equation used by the paper for finite spectra."""
    eig = np.asarray(eigenvalues, dtype=np.float64)
    if np.any(eig < 0):
        raise ValueError("eigenvalues must be non-negative")
    if noise_variance <= 0:
        raise ValueError("noise_variance must be positive")
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    gamma = eig.size / float(n_samples)

    def residual(kappa: float) -> float:
        trace = float(np.mean(eig / (eig + kappa)))
        return kappa - noise_variance - gamma * kappa * trace

    lo = float(noise_variance)
    hi = max(lo * 2.0, lo + 1.0, float(np.max(eig)) + lo)
    while residual(hi) <= 0.0:
        hi *= 2.0
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        if residual(mid) <= 0.0:
            lo = mid
        else:
            hi = mid
        if hi - lo <= tol * max(1.0, hi):
            break
    return float(0.5 * (lo + hi))


def denoiser_shrinkage(eigenvalues: np.ndarray, noise_variance: float) -> np.ndarray:
    eig = np.asarray(eigenvalues, dtype=np.float64)
    return eig / (eig + float(noise_variance))
