#!/usr/bin/env python3
"""
sfl_matrix_engine.py
SFL Meaning-Matrix Engine -- pilot implementation.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List

DIMENSIONS = ["ideational", "field", "interpersonal", "tenor", "textual", "mode"]


@dataclass
class MeaningMatrix:
    values: np.ndarray  # shape (3, 2)
    label: str = ""

    @classmethod
    def from_values(cls, ideational, field, interpersonal, tenor, textual, mode, label=""):
        v = np.array([[ideational, field], [interpersonal, tenor], [textual, mode]], dtype=float)
        return cls(values=v, label=label)

    def to_matrix_2x3(self) -> np.ndarray:
        return self.values.T

    def to_vector(self) -> np.ndarray:
        return self.values.flatten()

    def __add__(self, delta):
        combined = np.clip(self.values + delta.values, -1.0, 1.0)
        return MeaningMatrix(values=combined, label=self.label)

    def display(self):
        r = self.values
        lines = [
            "MeaningMatrix(" + self.label + ")",
            "  [ ideational: " + f"{r[0,0]:+.2f}" + "  field: " + f"{r[0,1]:+.2f}" + "  ]",
            "  [ interpersonal: " + f"{r[1,0]:+.2f}" + "  tenor: " + f"{r[1,1]:+.2f}" + "  ]",
            "  [ textual: " + f"{r[2,0]:+.2f}" + "  mode: " + f"{r[2,1]:+.2f}" + "  ]",
        ]
        return "\n".join(lines)

    def display_2x3(self):
        t = self.to_matrix_2x3()
        lines = [
            "MeaningMatrix 2x3 (" + self.label + ")",
            "  [ ideational: " + f"{t[0,0]:+.2f}" + "  interpersonal: " + f"{t[0,1]:+.2f}" + "  textual: " + f"{t[0,2]:+.2f}" + "  ]",
            "  [ field: " + f"{t[1,0]:+.2f}" + "  tenor: " + f"{t[1,1]:+.2f}" + "  mode: " + f"{t[1,2]:+.2f}" + "  ]",
        ]
        return "\n".join(lines)


@dataclass
class MeaningTrajectory:
    lang: str
    M0: MeaningMatrix
    deltas: List[MeaningMatrix] = field(default_factory=list)

    def __post_init__(self):
        self._states = [self.M0]

    def add_delta(self, delta: MeaningMatrix):
        self.deltas.append(delta)
        new_state = self._states[-1] + delta
        new_state.label = delta.label
        self._states.append(new_state)

    @property
    def states(self) -> List[MeaningMatrix]:
        return self._states

    @property
    def final_state(self):
        return self._states[-1]

    def print_trajectory(self):
        print("\n=== Trajectory [" + self.lang + "] ===")
        for i, s in enumerate(self._states):
            tag = "M0" if i == 0 else "M" + str(i) + " (after delta" + str(i) + ")"
            print("\n " + tag + ":")
            print(" " + s.display())
            print(" " + s.display_2x3())


def encode_en() -> MeaningTrajectory:
    """hey why dont you print hello world for me please thank you"""
    traj = MeaningTrajectory(lang="EN", M0=MeaningMatrix.from_values(
        -0.7, -0.5, +0.8, +0.9, +0.6, -0.6, label="hey"))
    traj.add_delta(MeaningMatrix.from_values(+0.1, +0.2, +0.1, 0.0, +0.2, 0.0, label="why dont you"))
    traj.add_delta(MeaningMatrix.from_values(+0.9, +0.9, +0.1, -0.1, +0.3, 0.0, label="print hello world"))
    traj.add_delta(MeaningMatrix.from_values(+0.1, 0.0, -0.1, +0.1, +0.1, 0.0, label="for me"))
    traj.add_delta(MeaningMatrix.from_values(-0.3, 0.0, +0.1, +0.2, -0.2, 0.0, label="please thank you"))
    return traj


def encode_en_test_rule() -> MeaningTrajectory:
    """
    TEST-ONLY trajectory, not a real pilot utterance.
    Purpose: verify apply_sfl_composition_rule() in sfl_manifold.py actually
    fires. Segment 2 is constructed so interpersonal rises by +0.30 (> 0.2
    threshold) while field only moves by +0.05 (< 0.15 threshold), which
    should trigger interpersonal->textual propagation.
    This function is not wired into the app.py UI; it exists only to be
    called directly (e.g. from a Python shell or a dedicated test) to
    inspect sfl_manifold output for a step where the rule is expected to fire.
    """
    traj = MeaningTrajectory(lang="EN-TEST", M0=MeaningMatrix.from_values(
        -0.2, 0.4, 0.2, 0.3, 0.2, 0.0, label="baseline"))
    traj.add_delta(MeaningMatrix.from_values(0.0, +0.05, +0.30, +0.05, 0.0, 0.0, label="interpersonal rise, field stable"))
    return traj


def encode_es() -> MeaningTrajectory:
    """buenos dias, hoy es viernes. Esto es CNN. Hoy es un dia importante para mi y para muchos."""
    traj = MeaningTrajectory(lang="ES", M0=MeaningMatrix.from_values(
        -0.6, -0.3, +0.8, +0.7, +0.7, +0.4, label="buenos dias"))
    traj.add_delta(MeaningMatrix.from_values(+0.4, +0.2, 0.0, 0.0, +0.2, 0.0, label="hoy es viernes"))
    traj.add_delta(MeaningMatrix.from_values(+0.5, +0.8, +0.2, -0.3, +0.1, +0.3, label="Esto es CNN"))
    traj.add_delta(MeaningMatrix.from_values(+0.2, -0.1, -0.1, +0.3, +0.1, -0.1, label="dia importante para mi"))
    traj.add_delta(MeaningMatrix.from_values(+0.2, +0.1, +0.1, +0.2, 0.0, 0.0, label="y para muchos"))
    return traj


def realize(traj: MeaningTrajectory) -> str:
    m = traj.final_state.values
    field_v = m[0, 1]
    mode = m[2, 1]
    if traj.lang == "EN" and field_v > 0.5 and mode < 0:
        return "Hello, World!"
    if traj.lang == "ES" and field_v > 0.7 and mode > 0.5:
        return "Buenos dias. Hoy es un dia importante para todos. Seguimos en CNN."
    return "[realization: no candidate matched]"


if __name__ == "__main__":
    for encode_fn in [encode_en, encode_es]:
        t = encode_fn()
        t.print_trajectory()
        print("\n Realization [" + t.lang + "]: " + realize(t))
        print()

    from sfl_manifold import compute_manifold, print_manifold
    test_traj = encode_en_test_rule()
    test_traj.print_trajectory()
    analysis = compute_manifold(test_traj)
    print_manifold(analysis)
