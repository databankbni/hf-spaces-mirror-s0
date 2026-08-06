from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression


class BetaCalibrator:
    def __init__(self):
        self.model = LogisticRegression(C=1.0, max_iter=1000)

    @staticmethod
    def transform(probability: np.ndarray) -> np.ndarray:
        clipped = np.clip(probability, 1e-6, 1 - 1e-6)
        return np.column_stack([np.log(clipped), np.log1p(-clipped)])

    def fit(self, probability: np.ndarray, target: np.ndarray) -> "BetaCalibrator":
        self.model.fit(self.transform(probability), target)
        return self

    def predict(self, probability: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(self.transform(probability))[:, 1]
