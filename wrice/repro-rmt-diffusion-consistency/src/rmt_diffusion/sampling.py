from __future__ import annotations

import numpy as np

from .spectrum import sample_covariance, symmetric_matrix_sqrt


def sample_covariance_sqrt_shrinkage(
    eigenvalues: np.ndarray, n_samples: int, trials: int, seed: int
) -> np.ndarray:
    """Estimate E[u_i^T sample_cov^{1/2} u_i] in the population eigenbasis."""
    eig = np.asarray(eigenvalues, dtype=np.float64)
    rng = np.random.default_rng(seed)
    accum = np.zeros_like(eig)
    for _ in range(trials):
        cov = sample_covariance(eig, n_samples, rng)
        sqrt_cov = symmetric_matrix_sqrt(cov)
        accum += np.diag(sqrt_cov)
    return accum / float(trials)


def _cross_split_mse(eigenvalues: np.ndarray, n_samples: int, trials: int, rng: np.random.Generator) -> float:
    eig = np.asarray(eigenvalues, dtype=np.float64)
    mses = []
    for _ in range(trials):
        seed_vector = rng.standard_normal(eig.size)
        left = symmetric_matrix_sqrt(sample_covariance(eig, n_samples, rng)) @ seed_vector
        right = symmetric_matrix_sqrt(sample_covariance(eig, n_samples, rng)) @ seed_vector
        mses.append(float(np.mean((left - right) ** 2)))
    return float(np.mean(mses))


def sampling_map_cross_split_variance(
    eigenvalues: np.ndarray, n_samples: int, trials: int, seed: int
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    base = _cross_split_mse(eigenvalues, n_samples, trials, rng)
    larger = _cross_split_mse(eigenvalues, n_samples * 4, trials, rng)
    return {
        "cross_split_mse": base,
        "larger_n_cross_split_mse": larger,
        "n_samples": float(n_samples),
        "larger_n_samples": float(n_samples * 4),
    }
