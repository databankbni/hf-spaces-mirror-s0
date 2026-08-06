"""Time-causal residual price book for daily production drift correction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ResidualCorrection:
    side: str
    factor: float
    global_factor: float
    model_factor: float
    model_support: int
    model_mad: float | None
    fitted_through: str
    version: str = "v195_time_causal_residual_price_book_v1"


def _timestamp(value: Any) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is not None:
        parsed = parsed.tz_convert("Asia/Shanghai").tz_localize(None)
    return parsed.normalize()


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    if weights.sum() <= 0:
        return float(np.median(values))
    position = np.searchsorted(np.cumsum(weights), weights.sum() / 2.0)
    return float(values[min(position, len(values) - 1)])


class DailyResidualPriceBook:
    """Small, auditable T-1 correction layer over a Level-5 prediction.

    The correction never stores a target price.  It stores bounded ratios
    learned from earlier predictions versus confirmed outcomes.  Exact model
    ratios are heavily shrunk and a global factor handles short market drift.
    """

    def __init__(
        self,
        *,
        cutoff: Any,
        b2c_global_factor: float,
        b2c_model_rows: dict[int, tuple[float, int, float]],
    ) -> None:
        self.cutoff = _timestamp(cutoff)
        self.b2c_global_factor = float(b2c_global_factor)
        self.b2c_model_rows = b2c_model_rows

    @classmethod
    def load(cls, root: Path, *, cutoff: Any) -> "DailyResidualPriceBook":
        cutoff_day = _timestamp(cutoff)
        path = root / "results/traces/v194_355_b2c_30d_champion_trace.csv"
        columns = [
            "day",
            "actual_yuan",
            "champion_pred_yuan",
            "model_id",
            "model_id_int",
        ]
        available = set(pd.read_csv(path, nrows=0).columns)
        frame = pd.read_csv(
            path,
            usecols=[column for column in columns if column in available],
            low_memory=False,
        )
        frame["day"] = pd.to_datetime(frame["day"], errors="coerce").dt.normalize()
        frame["actual"] = pd.to_numeric(frame["actual_yuan"], errors="coerce")
        frame["predicted"] = pd.to_numeric(
            frame["champion_pred_yuan"], errors="coerce"
        )
        model_id = pd.to_numeric(
            frame["model_id_int"]
            if "model_id_int" in frame
            else pd.Series(np.nan, index=frame.index),
            errors="coerce",
        )
        if model_id.isna().all():
            model_id = pd.to_numeric(
                frame["model_id"]
                if "model_id" in frame
                else pd.Series(np.nan, index=frame.index),
                errors="coerce",
            )
        frame["model_id_numeric"] = model_id.fillna(0).astype(int)
        frame = frame.loc[
            frame["day"].lt(cutoff_day)
            & frame["actual"].between(3_000, 1_000_000)
            & frame["predicted"].between(3_000, 1_000_000)
        ].copy()
        frame["ratio"] = (frame["actual"] / frame["predicted"]).clip(0.50, 1.50)

        global_rows = frame.loc[
            frame["day"].ge(cutoff_day - pd.Timedelta(days=7))
        ].copy()
        if global_rows.empty:
            global_factor = 1.0
        else:
            low, high = global_rows["ratio"].quantile([0.01, 0.99])
            trimmed = global_rows.loc[global_rows["ratio"].between(low, high), "ratio"]
            global_factor = float(np.clip(trimmed.mean(), 0.98, 1.02))

        model_rows = frame.loc[
            frame["day"].ge(cutoff_day - pd.Timedelta(days=30))
            & frame["model_id_numeric"].gt(0)
        ].copy()
        learned: dict[int, tuple[float, int, float]] = {}
        for key, group in model_rows.groupby("model_id_numeric", sort=False):
            count = int(len(group))
            if count < 2:
                continue
            age = (cutoff_day - group["day"]).dt.days.clip(lower=1).to_numpy(dtype=float)
            weights = np.power(2.0, -(age / 30.0))
            values = group["ratio"].to_numpy(dtype=float)
            median = _weighted_median(values, weights)
            mad = float(np.median(np.abs(values - median)))
            if mad > 0.20:
                continue
            shrunk = 1.0 + (median - 1.0) * count / (count + 12.0)
            model_factor = float(np.clip(shrunk, 0.97, 1.03))
            learned[int(key)] = (model_factor, count, mad)
        return cls(
            cutoff=cutoff_day,
            b2c_global_factor=global_factor,
            b2c_model_rows=learned,
        )

    def correction(self, side: str, model_id: Any) -> ResidualCorrection:
        normalized_side = str(side).strip().upper()
        numeric = pd.to_numeric(model_id, errors="coerce")
        key = int(numeric) if pd.notna(numeric) else 0
        if normalized_side != "B2C":
            return ResidualCorrection(
                side=normalized_side,
                factor=1.0,
                global_factor=1.0,
                model_factor=1.0,
                model_support=0,
                model_mad=None,
                fitted_through=str((self.cutoff - pd.Timedelta(days=1)).date()),
            )
        model_factor, support, mad = self.b2c_model_rows.get(key, (1.0, 0, np.nan))
        factor = float(np.clip(self.b2c_global_factor * model_factor, 0.95, 1.05))
        return ResidualCorrection(
            side="B2C",
            factor=factor,
            global_factor=self.b2c_global_factor,
            model_factor=model_factor,
            model_support=support,
            model_mad=float(mad) if np.isfinite(mad) else None,
            fitted_through=str((self.cutoff - pd.Timedelta(days=1)).date()),
        )
