"""Versioned, effective-dated manual override registry for v195."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd

from .v195_price_book_schema import (
    EvaluationMode,
    compact,
    condition_bucket,
    normalize_color,
    stable_hash,
    text,
    transfer_bucket,
)


OVERRIDE_COLUMNS = [
    "override_id",
    "approval_status",
    "override_type",
    "key_level",
    "canonical_key",
    "brand",
    "series",
    "model_id",
    "model_year",
    "trim_normalized",
    "city",
    "mileage_bucket",
    "registration_bucket",
    "transfer_count_bucket",
    "color_bucket",
    "condition_grade",
    "reference_registration_date",
    "reference_mileage_km",
    "registration_adjustment_pct_per_month",
    "mileage_adjustment_pct_per_1000km",
    "max_local_adjustment_pct",
    "suggested_listing_price",
    "listing_price_low",
    "listing_price_high",
    "expected_b2c_transaction_price",
    "b2c_transaction_low",
    "b2c_transaction_high",
    "max_c2b_acquisition_price",
    "suggested_first_offer",
    "expected_final_acquisition_price",
    "final_acquisition_low",
    "final_acquisition_high",
    "suggested_acquisition_price",
    "delta_yuan",
    "floor_yuan",
    "cap_yuan",
    "confidence",
    "reason",
    "source_basis",
    "evidence_refs",
    "effective_from",
    "effective_to",
    "approved_at",
    "data_cutoff",
    "ttl_days",
    "owner",
    "reviewer",
    "version",
    "created_at",
    "updated_at",
]


PRICE_FIELDS = [
    "suggested_listing_price",
    "listing_price_low",
    "listing_price_high",
    "expected_b2c_transaction_price",
    "b2c_transaction_low",
    "b2c_transaction_high",
    "max_c2b_acquisition_price",
    "suggested_first_offer",
    "expected_final_acquisition_price",
    "final_acquisition_low",
    "final_acquisition_high",
    "suggested_acquisition_price",
]

SEVEN_ELEMENT_OVERRIDE_TYPES = {"REPLACE", "INTERVAL_REPLACE"}

NORMALIZED_COLORS = {
    "WHITE",
    "BLACK",
    "GRAY",
    "SILVER",
    "RED",
    "BLUE",
    "GREEN",
    "YELLOW",
    "ORANGE",
    "BROWN",
    "PURPLE",
    "GOLD",
    "UNKNOWN",
}


def seven_element_canonical_key(
    *,
    model_id: Any,
    model_year: Any,
    registration_bucket: Any,
    mileage_bucket: Any,
    city: Any,
    transfer_count_bucket: Any,
    color_bucket: Any,
    condition_grade: Any,
) -> str:
    """Build the exact Level-0 key used by the production price book."""

    model_number = pd.to_numeric(model_id, errors="coerce")
    year_number = pd.to_numeric(model_year, errors="coerce")
    if pd.isna(model_number) or int(model_number) <= 0:
        raise ValueError("model_id must be a positive standard-trim id")
    if pd.isna(year_number) or int(year_number) < 1900:
        raise ValueError("model_year must be a valid year")
    registration = text(registration_bucket).upper()
    if not pd.Series([registration]).str.fullmatch(r"(?:19|20)\d{2}Q[1-4]").iloc[0]:
        raise ValueError("registration_bucket must use YYYYQ1..YYYYQ4")
    mileage = text(mileage_bucket).upper()
    if not pd.Series([mileage]).str.fullmatch(r"\d+_\d+").iloc[0]:
        raise ValueError("mileage_bucket must use lower_upper kilometres")
    lower, upper = (int(value) for value in mileage.split("_", 1))
    if lower < 0 or upper <= lower:
        raise ValueError("mileage_bucket upper bound must exceed lower bound")
    city_key = compact(city) or "UNKNOWN"
    transfer_raw = text(transfer_count_bucket).upper()
    transfer_key = (
        transfer_raw
        if transfer_raw in {"0", "1", "2", "3_PLUS", "UNKNOWN"}
        else transfer_bucket(transfer_count_bucket)
    )
    color_raw = text(color_bucket).upper()
    color_key = color_raw if color_raw in NORMALIZED_COLORS else normalize_color(color_bucket)
    condition_key = condition_bucket(condition_grade)
    raw = "|".join(
        [
            str(int(model_number)),
            str(int(year_number)),
            registration,
            f"{lower}_{upper}",
            city_key,
            transfer_key,
            color_key,
            condition_key,
        ]
    )
    return stable_hash([0, raw], "book")


def compile_seven_element_overrides(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate operator rows and compile their exact production keys.

    The compiler never approves a row.  Approval status, reviewer and dates
    must already be supplied by the business workflow.
    """

    out = frame.reindex(columns=OVERRIDE_COLUMNS).copy()
    errors: list[str] = []
    compiled_keys: list[str] = []
    generated_ids: list[str] = []
    now = pd.Timestamp.now(tz="UTC")
    for position, row in out.iterrows():
        try:
            key_level = int(pd.to_numeric(row.get("key_level"), errors="coerce"))
            if key_level == -1:
                key = text(row.get("canonical_key"))
                if not re.fullmatch(r"exact7_[0-9a-f]{24}", key):
                    raise ValueError(
                        "unbucketed exact seven-element overrides require an exact7 fingerprint"
                    )
            elif key_level == 0:
                key = seven_element_canonical_key(
                    model_id=row["model_id"],
                    model_year=row["model_year"],
                    registration_bucket=row["registration_bucket"],
                    mileage_bucket=row["mileage_bucket"],
                    city=row["city"],
                    transfer_count_bucket=row["transfer_count_bucket"],
                    color_bucket=row["color_bucket"],
                    condition_grade=row["condition_grade"],
                )
            else:
                raise ValueError("seven-element overrides must use key_level=-1 or key_level=0")
            status = text(row.get("approval_status")).upper()
            if status not in {"PENDING", "APPROVED", "REJECTED", "EXPIRED"}:
                raise ValueError("approval_status must be PENDING/APPROVED/REJECTED/EXPIRED")
            override_type = text(row.get("override_type")).upper()
            if override_type not in SEVEN_ELEMENT_OVERRIDE_TYPES:
                raise ValueError(
                    "seven-element override_type must be REPLACE or INTERVAL_REPLACE"
                )
            b2c = pd.to_numeric(row.get("expected_b2c_transaction_price"), errors="coerce")
            c2b = pd.to_numeric(row.get("expected_final_acquisition_price"), errors="coerce")
            if pd.isna(b2c) and pd.isna(c2b):
                raise ValueError("at least one B2C or C2B replacement price is required")
            for field in PRICE_FIELDS:
                value = pd.to_numeric(row.get(field), errors="coerce")
                if pd.notna(value) and float(value) <= 0:
                    raise ValueError(f"{field} must be positive")
            if pd.notna(b2c) and pd.notna(c2b) and float(b2c) < float(c2b):
                raise ValueError("expected B2C transaction price cannot be below C2B")
            listing = pd.to_numeric(row.get("suggested_listing_price"), errors="coerce")
            max_c2b = pd.to_numeric(row.get("max_c2b_acquisition_price"), errors="coerce")
            first_offer = pd.to_numeric(row.get("suggested_first_offer"), errors="coerce")
            if pd.notna(listing) and pd.notna(b2c) and float(listing) < float(b2c):
                raise ValueError("suggested listing price cannot be below expected B2C")
            if pd.notna(max_c2b) and pd.notna(b2c) and float(max_c2b) > float(b2c):
                raise ValueError("maximum C2B price cannot exceed expected B2C")
            if pd.notna(max_c2b) and pd.notna(c2b) and float(max_c2b) < float(c2b):
                raise ValueError("maximum C2B price cannot be below expected final C2B")
            if pd.notna(first_offer) and pd.notna(c2b) and float(first_offer) > float(c2b):
                raise ValueError("first C2B offer cannot exceed expected final C2B")
            for low_field, point_field, high_field in (
                ("b2c_transaction_low", "expected_b2c_transaction_price", "b2c_transaction_high"),
                ("final_acquisition_low", "expected_final_acquisition_price", "final_acquisition_high"),
                ("listing_price_low", "suggested_listing_price", "listing_price_high"),
            ):
                low = pd.to_numeric(row.get(low_field), errors="coerce")
                point = pd.to_numeric(row.get(point_field), errors="coerce")
                high = pd.to_numeric(row.get(high_field), errors="coerce")
                if pd.notna(low) and pd.notna(point) and float(low) > float(point):
                    raise ValueError(f"{low_field} cannot exceed {point_field}")
                if pd.notna(point) and pd.notna(high) and float(point) > float(high):
                    raise ValueError(f"{point_field} cannot exceed {high_field}")
            if status == "APPROVED":
                if not text(row.get("reviewer")):
                    raise ValueError("approved override requires reviewer")
                for field in ("effective_from", "effective_to", "approved_at", "data_cutoff"):
                    if pd.isna(pd.to_datetime(row.get(field), errors="coerce", utc=True)):
                        raise ValueError(f"approved override requires valid {field}")
                start = pd.to_datetime(row["effective_from"], utc=True)
                end = pd.to_datetime(row["effective_to"], utc=True)
                if end <= start:
                    raise ValueError("effective_to must be after effective_from")
                reference_registration = pd.to_datetime(
                    row.get("reference_registration_date"), errors="coerce"
                )
                reference_mileage = pd.to_numeric(
                    row.get("reference_mileage_km"), errors="coerce"
                )
                registration_rate = pd.to_numeric(
                    row.get("registration_adjustment_pct_per_month"), errors="coerce"
                )
                mileage_rate = pd.to_numeric(
                    row.get("mileage_adjustment_pct_per_1000km"), errors="coerce"
                )
                adjustment_cap = pd.to_numeric(
                    row.get("max_local_adjustment_pct"), errors="coerce"
                )
                if pd.isna(reference_registration):
                    raise ValueError("approved override requires reference_registration_date")
                if pd.isna(reference_mileage) or float(reference_mileage) < 0:
                    raise ValueError("approved override requires non-negative reference_mileage_km")
                if pd.isna(registration_rate) or not 0 <= float(registration_rate) <= 0.03:
                    raise ValueError(
                        "registration adjustment must be between 0 and 3% per month"
                    )
                if pd.isna(mileage_rate) or not 0 <= float(mileage_rate) <= 0.03:
                    raise ValueError(
                        "mileage adjustment must be between 0 and 3% per 1000km"
                    )
                if pd.isna(adjustment_cap) or not 0 < float(adjustment_cap) <= 0.30:
                    raise ValueError("max local adjustment must be between 0 and 30%")
            compiled_keys.append(key)
            existing_id = text(row.get("override_id"))
            generated_ids.append(
                existing_id
                or stable_hash([key, row.get("version"), row.get("effective_from")], "override")
            )
            errors.append("")
        except (TypeError, ValueError) as exc:
            compiled_keys.append("")
            generated_ids.append(text(row.get("override_id")))
            errors.append(f"row {position}: {exc}")
    if any(errors):
        raise ValueError("; ".join(error for error in errors if error))
    out["canonical_key"] = compiled_keys
    out["override_id"] = generated_ids
    out["key_level"] = pd.to_numeric(out["key_level"], errors="raise").astype(int)
    out["updated_at"] = out["updated_at"].where(out["updated_at"].notna(), now.isoformat())
    out["created_at"] = out["created_at"].where(out["created_at"].notna(), now.isoformat())
    return out


@dataclass(frozen=True)
class OverrideMatch:
    override_id: str
    override_type: str
    key_level: int
    canonical_key: str
    version: str
    reason: str
    values: dict[str, float]
    delta_yuan: float | None = None
    floor_yuan: float | None = None
    cap_yuan: float | None = None
    reference_registration_date: str = ""
    reference_mileage_km: float | None = None
    registration_adjustment_pct_per_month: float | None = None
    mileage_adjustment_pct_per_1000km: float | None = None
    max_local_adjustment_pct: float | None = None


def empty_override_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=OVERRIDE_COLUMNS)


def write_override_templates(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    template = directory / "manual_price_book_template.csv"
    reviewed = directory / "manual_price_book_reviewed.csv"
    active = directory / "manual_price_book_active.csv"
    fixture = directory / "approved_override_fixture.csv"
    empty_override_frame().to_csv(template, index=False, encoding="utf-8-sig")
    if not reviewed.exists():
        empty_override_frame().to_csv(reviewed, index=False, encoding="utf-8-sig")
    active_is_empty = not active.exists()
    if active.exists():
        try:
            active_is_empty = pd.read_csv(active, low_memory=False).empty
        except pd.errors.EmptyDataError:
            active_is_empty = True
    if active_is_empty:
        empty_override_frame().to_csv(active, index=False, encoding="utf-8-sig")
    fixture_rows = empty_override_frame()
    fixture_rows.loc[0, OVERRIDE_COLUMNS] = [pd.NA] * len(OVERRIDE_COLUMNS)
    fixture_rows.loc[0, [
        "override_id",
        "approval_status",
        "override_type",
        "key_level",
        "canonical_key",
        "expected_b2c_transaction_price",
        "effective_from",
        "effective_to",
        "approved_at",
        "ttl_days",
        "owner",
        "reviewer",
        "version",
        "reason",
    ]] = [
        "FIXTURE_EXPIRED_001",
        "APPROVED",
        "REPLACE",
        0,
        "fixture-only-key",
        100_000,
        "2026-01-01T00:00:00+08:00",
        "2026-01-02T00:00:00+08:00",
        "2025-12-31T00:00:00+08:00",
        1,
        "TEST_FIXTURE",
        "TEST_REVIEWER",
        "fixture-v1",
        "Expired fixture used only by tests; never loaded from active registry.",
    ]
    fixture_rows.to_csv(fixture, index=False, encoding="utf-8-sig")
    return {
        "template": template,
        "reviewed": reviewed,
        "active": active,
        "fixture": fixture,
    }


def _as_utc(value: Any) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("Asia/Shanghai")
    return parsed.tz_convert("UTC")


def eligible_overrides(
    frame: pd.DataFrame,
    *,
    as_of: Any,
    mode: EvaluationMode,
) -> pd.DataFrame:
    if frame.empty:
        return empty_override_frame()
    out = frame.reindex(columns=OVERRIDE_COLUMNS).copy()
    as_of_timestamp = _as_utc(as_of)
    effective_from = pd.to_datetime(out["effective_from"], errors="coerce", utc=True)
    effective_to = pd.to_datetime(out["effective_to"], errors="coerce", utc=True)
    approved_at = pd.to_datetime(out["approved_at"], errors="coerce", utc=True)
    status = out["approval_status"].fillna("").astype(str).str.upper().eq("APPROVED")
    active = (
        status
        & effective_from.notna()
        & effective_from.le(as_of_timestamp)
        & effective_to.notna()
        & effective_to.ge(as_of_timestamp)
        & approved_at.notna()
        & approved_at.le(as_of_timestamp)
    )
    if mode == EvaluationMode.CLEAN_ROLLING_EVAL:
        data_cutoff = pd.to_datetime(out["data_cutoff"], errors="coerce", utc=True)
        active &= data_cutoff.notna() & data_cutoff.le(as_of_timestamp)
    out = out.loc[active].copy()
    out["key_level"] = pd.to_numeric(out["key_level"], errors="coerce").fillna(99).astype(int)
    return out.sort_values(
        ["key_level", "effective_from", "updated_at"],
        ascending=[True, False, False],
        kind="stable",
    )


class ManualOverrideRegistry:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame.copy()

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        as_of: Any,
        mode: EvaluationMode,
    ) -> "ManualOverrideRegistry":
        frame = pd.read_csv(path, low_memory=False) if path.exists() else empty_override_frame()
        return cls(eligible_overrides(frame, as_of=as_of, mode=mode))

    def match(self, keys_by_level: dict[int, str]) -> OverrideMatch | None:
        for level in sorted(keys_by_level):
            key = text(keys_by_level[level])
            if not key:
                continue
            matches = self.frame.loc[
                self.frame["key_level"].eq(level)
                & self.frame["canonical_key"].fillna("").astype(str).eq(key)
            ]
            if matches.empty:
                continue
            row = matches.iloc[0]
            values = {
                field: float(row[field])
                for field in PRICE_FIELDS
                if pd.notna(pd.to_numeric(row[field], errors="coerce"))
            }
            return OverrideMatch(
                override_id=text(row["override_id"]),
                override_type=text(row["override_type"]).upper(),
                key_level=int(row["key_level"]),
                canonical_key=key,
                version=text(row["version"]),
                reason=text(row["reason"]),
                values=values,
                delta_yuan=_optional_float(row.get("delta_yuan")),
                floor_yuan=_optional_float(row.get("floor_yuan")),
                cap_yuan=_optional_float(row.get("cap_yuan")),
                reference_registration_date=text(row.get("reference_registration_date")),
                reference_mileage_km=_optional_float(row.get("reference_mileage_km")),
                registration_adjustment_pct_per_month=_optional_float(
                    row.get("registration_adjustment_pct_per_month")
                ),
                mileage_adjustment_pct_per_1000km=_optional_float(
                    row.get("mileage_adjustment_pct_per_1000km")
                ),
                max_local_adjustment_pct=_optional_float(
                    row.get("max_local_adjustment_pct")
                ),
            )
        return None


def _optional_float(value: Any) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return float(parsed) if pd.notna(parsed) else None


def apply_override_value(
    base: float,
    *,
    override_type: str,
    replacement: float | None = None,
    delta_yuan: float | None = None,
    floor_yuan: float | None = None,
    cap_yuan: float | None = None,
) -> float:
    output = float(base)
    kind = override_type.upper()
    if kind in {"REPLACE", "INTERVAL_REPLACE", "HIERARCHY_REPAIR"} and replacement is not None:
        output = float(replacement)
    elif kind == "DELTA" and delta_yuan is not None:
        output += float(delta_yuan)
    elif kind == "FLOOR" and floor_yuan is not None:
        output = max(output, float(floor_yuan))
    elif kind == "CAP" and cap_yuan is not None:
        output = min(output, float(cap_yuan))
    return float(output) if np.isfinite(output) else float(base)


def local_reference_adjustment(
    match: OverrideMatch,
    *,
    registration_date: Any,
    mileage_km: Any,
) -> tuple[float, dict[str, float]]:
    """Adjust a reviewed reference vehicle to the query's exact age and mileage."""

    reference_date = pd.to_datetime(match.reference_registration_date, errors="coerce")
    query_date = pd.to_datetime(registration_date, errors="coerce")
    reference_mileage = match.reference_mileage_km
    query_mileage = pd.to_numeric(mileage_km, errors="coerce")
    month_rate = match.registration_adjustment_pct_per_month
    mileage_rate = match.mileage_adjustment_pct_per_1000km
    cap = match.max_local_adjustment_pct
    if (
        pd.isna(reference_date)
        or pd.isna(query_date)
        or reference_mileage is None
        or pd.isna(query_mileage)
        or month_rate is None
        or mileage_rate is None
        or cap is None
    ):
        return 1.0, {
            "registration_adjustment_pct": 0.0,
            "mileage_adjustment_pct": 0.0,
            "local_adjustment_pct": 0.0,
        }
    registration_component = (
        (query_date - reference_date).total_seconds() / (86_400.0 * 30.4375)
    ) * float(month_rate)
    mileage_component = (
        (float(reference_mileage) - float(query_mileage)) / 1_000.0
    ) * float(mileage_rate)
    total = float(np.clip(registration_component + mileage_component, -float(cap), float(cap)))
    return 1.0 + total, {
        "registration_adjustment_pct": float(registration_component),
        "mileage_adjustment_pct": float(mileage_component),
        "local_adjustment_pct": total,
    }
