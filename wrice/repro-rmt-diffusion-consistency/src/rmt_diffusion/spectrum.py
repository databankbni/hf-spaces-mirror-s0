from __future__ import annotations

import numpy as np


def power_law_spectrum(d: int, exponent: float = 1.2, floor: float = 0.02) -> np.ndarray:
    """Return a descending synthetic image-like covariance spectrum."""
    if d <= 0:
        raise ValueError("d must be positive")
    ranks = np.arange(1, d + 1, dtype=np.float64)
    eig = ranks ** (-float(exponent))
    eig = eig / eig[0]
    return eig + float(floor)


def sample_covariance(eigenvalues: np.ndarray, n_samples: int, rng: np.random.Generator) -> np.ndarray:
    eig = np.asarray(eigenvalues, dtype=np.float64)
    if n_samples <= 1:
        raise ValueError("n_samples must exceed one")
    z = rng.standard_normal((n_samples, eig.size))
    x = z * np.sqrt(eig)
    x = x - x.mean(axis=0, keepdims=True)
    return (x.T @ x) / float(n_samples - 1)


def symmetric_matrix_sqrt(matrix: np.ndarray) -> np.ndarray:
    vals, vecs = np.linalg.eigh((matrix + matrix.T) * 0.5)
    vals = np.clip(vals, 0.0, None)
    return (vecs * np.sqrt(vals)) @ vecs.T
