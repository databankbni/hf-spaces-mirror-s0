"""Calibrate external asking prices into B2C transaction-price evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


SOURCES = ("dongchedi", "autohome", "guazi")
PRICE_BINS = (0, 30_000, 50_000, 80_000, 120_000, 200_000, 300_000, 2_000_000)


@dataclass(frozen=True)
class SourceCalibration:
    source: str
    global_transaction_to_listing_ratio: float
    price_band_ratios: dict[str, float]
    train_count: int
    temporal_validation_count: int
    temporal_validation_median_ape: float
    reliability_weight: float
    ratio_q10: float
    ratio_q50: float
    ratio_q90: float


@dataclass(frozen=True)
class ExternalMarketCalibration:
    version: str
    fitted_through: str
    shrinkage: float
    sources: dict[str, SourceCalibration]
    asking_price_is_transaction_target: bool = False
    source_vote_policy: str = "one calibrated point per source; inventory count never multiplies source votes"

    def to_dict(self) -> dict[str, Any]:
        output = asdict(self)
        output["sources"] = {
            source: asdict(calibration) for source, calibration in self.sources.items()
        }
        return output


def add_price_band(frame: pd.DataFrame, base_column: str) -> pd.DataFrame:
    out = frame.copy()
    base = pd.to_numeric(out[base_column], errors="coerce")
    out["v195_price_band"] = (
        pd.cut(base, PRICE_BINS, labels=False, include_lowest=True).fillna(-1).astype(int)
    )
    return out


def _source_rows(frame: pd.DataFrame, source: str, actual_column: str) -> pd.DataFrame:
    listing_column = f"{source}_median_yuan"
    if listing_column not in frame:
        return pd.DataFrame(columns=[actual_column, listing_column, "v195_price_band", "day"])
    selected = frame[[actual_column, listing_column, "v195_price_band", "day"]].copy()
    selected[actual_column] = pd.to_numeric(selected[actual_column], errors="coerce")
    selected[listing_column] = pd.to_numeric(selected[listing_column], errors="coerce")
    selected = selected.loc[
        selected[actual_column].between(3_000, 1_000_000)
        & selected[listing_column].between(3_000, 2_000_000)
    ].copy()
    selected["ratio"] = (
        selected[actual_column] / selected[listing_column]
    ).clip(0.65, 1.20)
    selected["day"] = pd.to_datetime(selected["day"], errors="coerce")
    return selected


def fit_external_market_calibration(
    frame: pd.DataFrame,
    *,
    base_column: str,
    actual_column: str,
    shrinkage: float = 20.0,
) -> ExternalMarketCalibration:
    prepared = add_price_band(frame, base_column)
    source_calibrations: dict[str, SourceCalibration] = {}
    for source in SOURCES:
        rows = _source_rows(prepared, source, actual_column)
        if rows.empty:
            source_calibrations[source] = SourceCalibration(
                source=source,
                global_transaction_to_listing_ratio=1.0,
                price_band_ratios={},
                train_count=0,
                temporal_validation_count=0,
                temporal_validation_median_ape=1.0,
                reliability_weight=0.0,
                ratio_q10=1.0,
                ratio_q50=1.0,
                ratio_q90=1.0,
            )
            continue
        global_ratio = float(rows["ratio"].median())
        stats = rows.groupby("v195_price_band")["ratio"].agg(["median", "count"])
        band_ratios: dict[str, float] = {}
        for band, stat in stats.iterrows():
            weight = float(stat["count"]) / (float(stat["count"]) + shrinkage)
            band_ratios[str(int(band))] = float(
                weight * float(stat["median"]) + (1.0 - weight) * global_ratio
            )

        ordered_days = sorted(rows["day"].dropna().dt.normalize().unique())
        if len(ordered_days) >= 4:
            validation_start = ordered_days[max(1, int(len(ordered_days) * 0.75))]
            early = rows.loc[rows["day"] < validation_start]
            validation = rows.loc[rows["day"] >= validation_start]
        else:
            early = rows
            validation = rows
        validation_ratio = float(early["ratio"].median()) if not early.empty else global_ratio
        validation_ape = (
            (
                validation[f"{source}_median_yuan"] * validation_ratio
                - validation[actual_column]
            ).abs()
            / validation[actual_column]
        )
        temporal_median_ape = float(validation_ape.median()) if not validation_ape.empty else 1.0
        support = len(validation) / (len(validation) + 50.0)
        reliability = float(support / max(temporal_median_ape, 0.03))
        source_calibrations[source] = SourceCalibration(
            source=source,
            global_transaction_to_listing_ratio=global_ratio,
            price_band_ratios=band_ratios,
            train_count=int(len(rows)),
            temporal_validation_count=int(len(validation)),
            temporal_validation_median_ape=temporal_median_ape,
            reliability_weight=reliability,
            ratio_q10=float(rows["ratio"].quantile(0.10)),
            ratio_q50=float(rows["ratio"].quantile(0.50)),
            ratio_q90=float(rows["ratio"].quantile(0.90)),
        )

    days = pd.to_datetime(prepared["day"], errors="coerce").dropna()
    return ExternalMarketCalibration(
        version="v195_external_listing_to_b2c_calibration_v1",
        fitted_through=str(days.max().date()) if not days.empty else "UNKNOWN",
        shrinkage=shrinkage,
        sources=source_calibrations,
    )


def _weighted_median(values: list[float], weights: list[float]) -> float:
    order = np.argsort(values)
    sorted_values = np.asarray(values, dtype=float)[order]
    sorted_weights = np.asarray(weights, dtype=float)[order]
    if sorted_weights.sum() <= 0:
        return float(np.median(sorted_values))
    position = np.searchsorted(np.cumsum(sorted_weights), sorted_weights.sum() / 2.0)
    return float(sorted_values[min(position, len(sorted_values) - 1)])


def calibrated_external_proxy(
    frame: pd.DataFrame,
    calibration: ExternalMarketCalibration,
    *,
    base_column: str,
) -> pd.DataFrame:
    prepared = add_price_band(frame, base_column)
    records: list[dict[str, Any]] = []
    for _, row in prepared.iterrows():
        points: list[float] = []
        weights: list[float] = []
        source_points: dict[str, float | None] = {}
        band = str(int(row["v195_price_band"]))
        for source in SOURCES:
            listing = pd.to_numeric(row.get(f"{source}_median_yuan"), errors="coerce")
            source_calibration = calibration.sources[source]
            if pd.isna(listing) or float(listing) <= 0 or source_calibration.train_count <= 0:
                source_points[source] = None
                continue
            ratio = source_calibration.price_band_ratios.get(
                band, source_calibration.global_transaction_to_listing_ratio
            )
            point = float(listing) * float(ratio)
            points.append(point)
            weights.append(source_calibration.reliability_weight)
            source_points[source] = point
        if points:
            proxy = _weighted_median(points, weights)
            dispersion = (
                (max(points) - min(points)) / float(np.median(points))
                if len(points) >= 2
                else np.nan
            )
        else:
            proxy = np.nan
            dispersion = np.nan
        confidence = (
            "HIGH"
            if len(points) >= 2 and np.isfinite(dispersion) and dispersion <= 0.18
            else "MEDIUM"
            if len(points) >= 1 and (not np.isfinite(dispersion) or dispersion <= 0.30)
            else "LOW"
        )
        records.append(
            {
                "external_b2c_proxy_yuan": proxy,
                "external_source_count": len(points),
                "external_source_dispersion": dispersion,
                "external_anchor_confidence": confidence,
                **{
                    f"{source}_calibrated_b2c_proxy_yuan": source_points[source]
                    for source in SOURCES
                },
            }
        )
    return pd.DataFrame(records, index=frame.index)

