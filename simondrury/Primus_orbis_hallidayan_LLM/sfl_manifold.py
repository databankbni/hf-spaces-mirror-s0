#!/usr/bin/env python3
"""
sfl_manifold.py
Semiotic Path Geometry Engine.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List

DIM_NAMES = ["ideational", "field", "interpersonal", "tenor", "textual", "mode"]


def apply_sfl_composition_rule(delta: np.ndarray, field_stability_threshold: float = 0.15,
                                interpersonal_rise_threshold: float = 0.2,
                                textual_boost: float = 0.10) -> np.ndarray:
    """
    One explicit, inspectable Hallidayan composition rule.

    Rule: if interpersonal rises meaningfully while field stays stable,
    propagate that move into the textual dimension (the interpersonal
    move is being organized/cohered rather than just asserted).

    This does not replace the raw delta; it returns an adjusted delta
    that is then used for composition, so the effect is visible and
    auditable rather than baked silently into argmax labels.
    """
    ideational, field_val, interpersonal, tenor, textual, mode = delta
    adjusted = delta.copy()
    field_stable = abs(field_val) < field_stability_threshold
    interpersonal_rise = interpersonal > interpersonal_rise_threshold
    if interpersonal_rise and field_stable:
        adjusted[4] += textual_boost
    return adjusted


@dataclass
class StepGeometry:
    t: int
    label: str
    displacement: float
    curvature: float
    momentum: np.ndarray
    dominant_driver: str
    dominant_index: int
    delta_vector: np.ndarray
    dominant_metafunction: str = ""
    dominant_register: str = ""
    rule_applied: str = ""


@dataclass
class ManifoldAnalysis:
    lang: str
    steps: List[StepGeometry]
    path_loss: float
    lambda1: float
    lambda2: float


def compute_manifold(trajectory, lambda1: float = 0.5, lambda2: float = 0.5, alpha: float = 0.7) -> ManifoldAnalysis:
    states = [s.to_vector() for s in trajectory.states]
    deltas = [states[t] - states[t - 1] for t in range(1, len(states))]
    steps = []
    momentum = np.zeros(6)
    path_loss = 0.0
    for i, raw_delta in enumerate(deltas):
        t = i + 1
        delta = apply_sfl_composition_rule(raw_delta)
        rule_applied = "interpersonal->textual propagation" if not np.allclose(delta, raw_delta) else "none"
        disp = float(np.linalg.norm(delta))
        if i > 0:
            prev = deltas[i - 1]
            denom = np.linalg.norm(prev) * np.linalg.norm(delta) + 1e-9
            cos_angle = np.dot(prev, delta) / denom
            kappa = float(np.arccos(np.clip(cos_angle, -1.0, 1.0)))
        else:
            kappa = float("nan")
        momentum = alpha * delta + (1 - alpha) * momentum
        dom_idx = int(np.argmax(np.abs(delta)))
        dom_name = DIM_NAMES[dom_idx]
        mat = delta.reshape(3, 2)
        row_norms = np.linalg.norm(mat, axis=1)
        col_norms = np.linalg.norm(mat, axis=0)
        dom_metafunction = ["ideational", "interpersonal", "textual"][int(np.argmax(row_norms))]
        dom_register = ["field", "tenor", "mode"][int(np.argmax(col_norms))]
        kappa_term = 0.0 if np.isnan(kappa) else kappa ** 2
        path_loss += lambda1 * disp ** 2 + lambda2 * kappa_term
        steps.append(StepGeometry(
            t=t,
            label=trajectory.states[t].label,
            displacement=disp,
            curvature=kappa,
            momentum=momentum.copy(),
            dominant_driver=dom_name,
            dominant_index=dom_idx,
            delta_vector=delta.copy(),
            dominant_metafunction=dom_metafunction,
            dominant_register=dom_register,
            rule_applied=rule_applied,
        ))
    return ManifoldAnalysis(
        lang=trajectory.lang,
        steps=steps,
        path_loss=path_loss,
        lambda1=lambda1,
        lambda2=lambda2,
    )


def print_manifold(analysis: ManifoldAnalysis):
    print("\n=== Semiotic Manifold Analysis [" + analysis.lang + "] ===\n")
    for s in analysis.steps:
        kap = f"{s.curvature:.3f}" if not np.isnan(s.curvature) else "-"
        print(f"t={s.t} {s.label} disp={s.displacement:.3f} kappa={kap} driver={s.dominant_driver} "
              f"metafunction={s.dominant_metafunction} register={s.dominant_register} rule={s.rule_applied}")
    print("\n Semiotic Path Loss L_sp: " + f"{analysis.path_loss:.4f}")


if __name__ == "__main__":
    from sfl_matrix_engine import encode_en, encode_es
    for fn in [encode_en, encode_es]:
        traj = fn()
        analysis = compute_manifold(traj)
        print_manifold(analysis)
        print("=" * 60)
