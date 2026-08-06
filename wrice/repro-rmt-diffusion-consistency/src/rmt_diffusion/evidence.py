from __future__ import annotations

import numpy as np

from .denoiser import denoiser_anisotropy_profile, denoiser_variance_prediction
from .sampling import sample_covariance_sqrt_shrinkage, sampling_map_cross_split_variance
from .silverstein import denoiser_shrinkage, solve_kappa
from .spectrum import power_law_spectrum

UPSTREAM_REVISION = (
    "arxiv:2602.02908v2+arxiv-source-sha256:"
    "d315b147972a42b0672876faa771b7a27d759659ad2ffa49e44f68494d4f3f3d"
)
GENERATED_AT = "2026-07-29T02:30:00+00:00"

TARGET_CLAIMS = [
    "Finite-sample covariance effects renormalize the effective noise scale in the expected linear denoiser, causing overshrinkage of low-variance directions (Figure 2)",
    "The denoiser-variance theory predicts anisotropic, location-dependent cross-split deviations that decay with dataset size (Result 4.2)",
    "The sampling-map analysis gives deterministic-equivalence formulas for expectation and variance over full diffusion trajectories (Results 5.1 and 5.2)",
]


def _float(value: float) -> float:
    return float(np.asarray(value, dtype=np.float64))


def build_evidence() -> dict:
    eig = power_law_spectrum(d=64, exponent=1.3, floor=0.025)
    raw_noise = 0.12
    n_samples = 96
    kappa = solve_kappa(eig, raw_noise, n_samples)
    population = denoiser_shrinkage(eig, raw_noise)
    finite_sample = denoiser_shrinkage(eig, kappa)
    low_band = eig < 0.20

    denoiser_eig = power_law_spectrum(d=48, exponent=1.2, floor=0.03)
    denoiser_noise = 0.15
    denoiser_kappa = solve_kappa(denoiser_eig, denoiser_noise, 72)
    peak_index = int(np.argmin(np.abs(denoiser_eig - denoiser_kappa)))
    top_index = int(np.argmax(denoiser_eig))
    location = np.sqrt(denoiser_eig + denoiser_noise)
    profile = denoiser_anisotropy_profile(denoiser_eig, denoiser_noise, 72, location)
    peak_var = denoiser_variance_prediction(
        denoiser_eig, denoiser_noise, 72, peak_index, location
    )
    top_var = denoiser_variance_prediction(
        denoiser_eig, denoiser_noise, 72, top_index, location
    )
    large_n_var = denoiser_variance_prediction(
        denoiser_eig, denoiser_noise, 384, peak_index, location
    )

    sampling_eig = power_law_spectrum(d=32, exponent=1.1, floor=0.04)
    shrink = sample_covariance_sqrt_shrinkage(
        sampling_eig, n_samples=64, trials=80, seed=7
    )
    sampling_stats = sampling_map_cross_split_variance(
        sampling_eig, n_samples=64, trials=80, seed=9
    )

    return {
        "paper_id": "iPjuUQbkfl",
        "title": "A Random Matrix Perspective on the Consistency of Diffusion Models",
        "upstream_revision": UPSTREAM_REVISION,
        "generated_at": GENERATED_AT,
        "cpu_only": True,
        "commands": [
            "uv run --project submissions/a-random-matrix-perspective-on-the-consistency-of-diffusion-models python submissions/a-random-matrix-perspective-on-the-consistency-of-diffusion-models/generate_evidence.py",
            "uv run --project submissions/a-random-matrix-perspective-on-the-consistency-of-diffusion-models python -m pytest submissions/a-random-matrix-perspective-on-the-consistency-of-diffusion-models/tests -q",
        ],
        "target_claims": TARGET_CLAIMS,
        "claims": [
            {
                "claim": TARGET_CLAIMS[0],
                "verdict": "toy",
                "evidence": "A finite diagonal Gaussian spectrum reproduces the Silverstein noise renormalization and the resulting lower-band shrinkage in the optimal linear denoiser.",
                "metrics": {
                    "raw_noise_variance": raw_noise,
                    "renormalized_kappa": _float(kappa),
                    "kappa_minus_raw": _float(kappa - raw_noise),
                    "low_band_population_shrinkage": _float(population[low_band].mean()),
                    "low_band_finite_sample_shrinkage": _float(finite_sample[low_band].mean()),
                },
            },
            {
                "claim": TARGET_CLAIMS[1],
                "verdict": "toy",
                "evidence": "Result 4.2's factorized variance formula peaks near lambda ~= kappa and decays when n is increased on the same synthetic spectrum.",
                "metrics": {
                    "kappa": _float(denoiser_kappa),
                    "peak_eigenvalue": _float(denoiser_eig[peak_index]),
                    "top_eigenvalue": _float(denoiser_eig[top_index]),
                    "peak_direction_variance": _float(peak_var),
                    "top_direction_variance": _float(top_var),
                    "large_n_peak_variance": _float(large_n_var),
                    "profile_argmax_index": int(np.argmax(profile)),
                },
            },
            {
                "claim": TARGET_CLAIMS[2],
                "verdict": "toy",
                "evidence": "Empirical sample-covariance square-root maps overshrink low modes and independent split maps have positive same-seed disagreement that drops with larger n.",
                "metrics": {
                    "low_mode_empirical_sqrt_mean": _float(shrink[-8:].mean()),
                    "low_mode_population_sqrt_mean": _float(np.sqrt(sampling_eig[-8:]).mean()),
                    **sampling_stats,
                },
            },
        ],
        "limitations": [
            "No official executable repository was found in the pinned arXiv source or web search.",
            "The evidence targets the paper's linear/RMT theory claims on synthetic spectra, not the paper's UNet/DiT image experiments.",
        ],
    }
