import numpy as np

from rmt_diffusion.denoiser import denoiser_variance_prediction
from rmt_diffusion.evidence import build_evidence
from rmt_diffusion.sampling import (
    sample_covariance_sqrt_shrinkage,
    sampling_map_cross_split_variance,
)
from rmt_diffusion.silverstein import denoiser_shrinkage, solve_kappa
from rmt_diffusion.spectrum import power_law_spectrum


def test_kappa_exceeds_raw_noise_and_increases_overshrinkage():
    eig = power_law_spectrum(d=64, exponent=1.4, floor=0.02)
    raw = 0.12
    kappa = solve_kappa(eig, raw, n_samples=96)
    assert kappa > raw

    population = denoiser_shrinkage(eig, raw)
    finite_sample = denoiser_shrinkage(eig, kappa)
    low_band = eig < 0.2
    assert finite_sample[low_band].mean() < population[low_band].mean()


def test_denoiser_variance_is_anisotropic_and_decays_with_dataset_size():
    eig = power_law_spectrum(d=48, exponent=1.2, floor=0.03)
    raw = 0.15
    kappa = solve_kappa(eig, raw, n_samples=72)
    peak_index = int(np.argmin(np.abs(eig - kappa)))
    top_index = int(np.argmax(eig))
    location = np.sqrt(eig + raw)

    peak = denoiser_variance_prediction(eig, raw, 72, peak_index, location)
    top = denoiser_variance_prediction(eig, raw, 72, top_index, location)
    assert peak > top

    small_n = denoiser_variance_prediction(eig, raw, 72, peak_index, location)
    large_n = denoiser_variance_prediction(eig, raw, 384, peak_index, location)
    assert large_n < small_n * 0.35


def test_sampling_map_shrinks_low_modes_and_has_positive_split_variance():
    eig = power_law_spectrum(d=32, exponent=1.1, floor=0.04)
    shrink = sample_covariance_sqrt_shrinkage(eig, n_samples=64, trials=80, seed=7)
    assert shrink[-8:].mean() < np.sqrt(eig[-8:]).mean()

    stats = sampling_map_cross_split_variance(eig, n_samples=64, trials=80, seed=9)
    assert stats["cross_split_mse"] > 0.0
    assert stats["larger_n_cross_split_mse"] < stats["cross_split_mse"]


def test_evidence_bundle_maps_all_target_claims_to_metrics():
    bundle = build_evidence()
    assert bundle["upstream_revision"].startswith("arxiv:2602.02908v2")
    assert len(bundle["target_claims"]) == 3
    statuses = {claim["verdict"] for claim in bundle["claims"]}
    assert statuses <= {"verified", "toy", "inconclusive", "falsified"}
    assert all(claim["metrics"] for claim in bundle["claims"])


def test_evidence_bundle_is_deterministic():
    assert build_evidence() == build_evidence()
