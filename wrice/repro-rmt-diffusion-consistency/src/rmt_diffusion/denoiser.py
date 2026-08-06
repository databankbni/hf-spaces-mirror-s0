from __future__ import annotations

import numpy as np

from .silverstein import df2, solve_kappa


def diamond(eigenvalues: np.ndarray, kappa: float, vector: np.ndarray) -> float:
    eig = np.asarray(eigenvalues, dtype=np.float64)
    vec = np.asarray(vector, dtype=np.float64)
    weights = eig / (eig + kappa) ** 2
    return float(np.sum(vec**2 * weights))


def denoiser_variance_prediction(
    eigenvalues: np.ndarray,
    noise_variance: float,
    n_samples: int,
    probe_index: int,
    location: np.ndarray,
) -> float:
    eig = np.asarray(eigenvalues, dtype=np.float64)
    if not 0 <= probe_index < eig.size:
        raise IndexError("probe_index out of bounds")
    kappa = solve_kappa(eig, noise_variance, n_samples)
    probe = np.zeros_like(eig)
    probe[probe_index] = 1.0
    denominator = float(n_samples) - df2(eig, kappa)
    if denominator <= 0:
        raise ValueError("n_samples must exceed df2(kappa)")
    return (kappa**2 / denominator) * diamond(eig, kappa, probe) * diamond(
        eig, kappa, location
    )


def denoiser_anisotropy_profile(
    eigenvalues: np.ndarray, noise_variance: float, n_samples: int, location: np.ndarray
) -> np.ndarray:
    eig = np.asarray(eigenvalues, dtype=np.float64)
    return np.array(
        [
            denoiser_variance_prediction(eig, noise_variance, n_samples, idx, location)
            for idx in range(eig.size)
        ],
        dtype=np.float64,
    )
