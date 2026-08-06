#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit, train_test_split


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/processed"
REPORTS = ROOT / "reports"
AUDIT = ROOT / "artifacts/audit"
V71_SOURCE = Path("/Users/bytedance/Downloads/v7_1_codex_train_package/data/processed")
LOW_REVIEW = Path("/tmp/v7_2_low_price_work/low_review")
if not (LOW_REVIEW / "data/processed").exists():
    LOW_REVIEW = Path("/Users/bytedance/Downloads/low_price_review_v7_2")

RANDOM_STATE = 42
TASKS = ["c2b", "b2c"]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def price_bucket(s: pd.Series) -> pd.Series:
    bins = [-np.inf, 10000, 20000, 30000, 50000, 100000, 200000, 300000, 500000, 1000000, np.inf]
    labels = ["<=1万", "1-2万", "2-3万", "3-5万", "5-10万", "10-20万", "20-30万", "30-50万", "50-100万", ">100万"]
    return pd.cut(pd.to_numeric(s, errors="coerce"), bins=bins, labels=labels, right=False).astype(str)


def stable_random_split(df: pd.DataFrame) -> pd.Series:
    tmp = df.copy()
    tmp["_strata"] = price_bucket(tmp["target_price"]) + "_" + tmp.get("source_dataset", "").astype(str)
    vc = tmp["_strata"].value_counts()
    tmp.loc[~tmp["_strata"].isin(vc[vc >= 3].index), "_strata"] = "other"
    idx = np.arange(len(tmp))
    train_idx, hold_idx = train_test_split(
        idx,
        test_size=0.30,
        random_state=RANDOM_STATE,
        stratify=tmp["_strata"] if tmp["_strata"].nunique() > 1 else None,
    )
    hold = tmp.iloc[hold_idx].copy()
    hold_strata = hold["_strata"]
    vc2 = hold_strata.value_counts()
    strat2 = hold_strata.where(hold_strata.isin(vc2[vc2 >= 2].index), "other")
    valid_local, test_local = train_test_split(
        np.arange(len(hold)),
        test_size=0.50,
        random_state=RANDOM_STATE,
        stratify=strat2 if strat2.nunique() > 1 else None,
    )
    split = pd.Series(index=tmp.index, dtype=object)
    split.iloc[train_idx] = "train"
    split.iloc[hold_idx[valid_local]] = "valid"
    split.iloc[hold_idx[test_local]] = "test"
    return split


def grouped_split(df: pd.DataFrame) -> pd.Series:
    def col(name: str, default: str = "") -> pd.Series:
        return df[name].astype(str) if name in df else pd.Series(default, index=df.index)

    mileage = pd.to_numeric(df.get("mileage_wan_km", 0), errors="coerce").fillna(0)
    mileage_bucket = (mileage * 10).round().astype(int).astype(str)
    group = (
        col("model_id") + "|" + col("series_id") + "|" + col("brand") + "|" + col("series") + "|"
        + col("vehicle_model") + "|" + col("model_year") + "|" + col("first_license_year") + "|"
        + col("city") + "|" + col("color") + "|" + mileage_bucket + "|" + col("transfer_count") + "|"
        + col("energy_type") + "|" + col("condition_group")
    )
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=RANDOM_STATE)
    idx = np.arange(len(df))
    train_idx, hold_idx = next(splitter.split(idx, groups=group))
    hold_group = group.iloc[hold_idx]
    splitter2 = GroupShuffleSplit(n_splits=1, test_size=0.50, random_state=RANDOM_STATE)
    valid_local, test_local = next(splitter2.split(np.arange(len(hold_idx)), groups=hold_group))
    split = pd.Series(index=df.index, dtype=object)
    split.iloc[train_idx] = "train"
    split.iloc[hold_idx[valid_local]] = "valid"
    split.iloc[hold_idx[test_local]] = "test"
    return split


def normalize_low_rows(df: pd.DataFrame, task: str, base_cols: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for c in base_cols:
        out[c] = df[c] if c in df else np.nan
    out["target_task"] = task
    out["target_price"] = pd.to_numeric(df.get("target_value"), errors="coerce")
    if "first_license_year" not in out or out["first_license_year"].isna().all():
        out["first_license_year"] = pd.to_datetime(df.get("first_license_date"), errors="coerce").dt.year
    if "mileage_km" in out:
        out["mileage_km"] = pd.to_numeric(out["mileage_wan_km"], errors="coerce") * 10000
    out["estimate_year"] = out.get("estimate_year", 2026).fillna(2026)
    out["brand_series"] = out.get("brand_series").fillna(out["brand"].astype(str) + "_" + out["series"].astype(str))
    out["brand_series_year"] = out.get("brand_series_year").fillna(out["brand_series"].astype(str) + "_" + out["model_year"].astype(str))
    inferred_new_energy = pd.Series(
        np.where(out.get("energy_type", "").astype(str).str.contains("新能源|纯电|增程|混动", na=False), "是", "否"),
        index=out.index,
    )
    out["is_new_energy"] = out.get("is_new_energy").fillna(inferred_new_energy)
    condition_rating = out["condition_rating"] if "condition_rating" in out else pd.Series("", index=out.index)
    out["condition_group"] = out.get("condition_group").fillna(
        pd.Series(np.where(condition_rating.astype(str).isin(["A", "B"]), "good_strict", "non_strict_or_unknown"), index=out.index)
    )
    out["good_condition_strict_flag"] = out.get("good_condition_strict_flag").fillna((out["condition_group"] == "good_strict").astype(int))
    risk_any = out["risk_any"] if "risk_any" in out else pd.Series(0, index=out.index)
    out["good_condition_loose_flag"] = out.get("good_condition_loose_flag").fillna((risk_any.fillna(0).astype(float) <= 0).astype(int))
    for c in [
        "luxury_variant_flag", "long_wheelbase_flag", "four_wheel_drive_flag", "performance_variant_flag",
        "new_energy_flag", "luxury_category_flag", "domestic_flag", "joint_venture_flag", "imported_or_luxury_flag",
    ]:
        out[c] = pd.to_numeric(out.get(c), errors="coerce").fillna(0).astype(int)
    out["age_source"] = out.get("age_source").fillna("low_price_review_v7_2")
    out["split"] = np.nan
    return out[base_cols]


def refresh_count_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for key, col in [
        ("model_id", "model_sample_count"),
        ("series", "series_sample_count"),
        ("brand", "brand_sample_count"),
        ("brand_series", "brand_series_sample_count"),
    ]:
        if key in df:
            df[col] = df[key].map(df[key].value_counts()).fillna(0).astype(int)
    if {"city", "brand_series"}.issubset(df.columns):
        combo = df["city"].astype(str) + "_" + df["brand_series"].astype(str)
        df["city_brand_series_sample_count"] = combo.map(combo.value_counts()).fillna(0).astype(int)
    return df


def load_low(task: str, kind: str) -> pd.DataFrame:
    p = LOW_REVIEW / "data/processed" / f"{task}_low_price_{kind}_candidates_v7_2.csv"
    return read_csv(p) if p.exists() else pd.DataFrame()


def write_split_audit(df: pd.DataFrame, task: str, suffix: str) -> None:
    rows = []
    for sp, g in df.groupby("split"):
        rows.append({
            "task": task,
            "split_type": suffix,
            "split": sp,
            "rows": len(g),
            "target_min": g["target_price"].min(),
            "target_median": g["target_price"].median(),
            "target_max": g["target_price"].max(),
            "source_counts": json.dumps(g.get("source_dataset", pd.Series()).value_counts().to_dict(), ensure_ascii=False),
        })
    pd.DataFrame(rows).to_csv(AUDIT / f"v7_2_split_distribution_{task}_{suffix}.csv", index=False, encoding="utf-8-sig")


def near_duplicate_audit(df: pd.DataFrame, task: str, suffix: str) -> pd.DataFrame:
    key_cols = [c for c in [
        "model_id", "series_id", "brand", "series", "vehicle_model", "model_year", "first_license_year",
        "city", "color", "mileage_km", "transfer_count", "energy_type", "condition_group",
    ] if c in df]
    train = df[df["split"].eq("train")].copy()
    other = df[~df["split"].eq("train")].copy()
    if not key_cols or train.empty or other.empty:
        return pd.DataFrame()
    train_key = train[key_cols].astype(str).agg("|".join, axis=1)
    other_key = other[key_cols].astype(str).agg("|".join, axis=1)
    train_targets = train.groupby(train_key)["target_price"].agg(list).to_dict()
    rows = []
    for idx, k in zip(other.index, other_key):
        targets = train_targets.get(k, [])
        y = float(other.at[idx, "target_price"])
        rows.append({
            "source_dataset": other.at[idx, "source_dataset"],
            "source_id": other.at[idx, "source_id"],
            "split": other.at[idx, "split"],
            "has_train_exact_key": bool(targets),
            "same_target_price": any(abs(float(t) - y) < 1e-9 for t in targets),
            "target_diff_le_1000": any(abs(float(t) - y) <= 1000 for t in targets),
            "target_diff_le_1pct": any(abs(float(t) - y) / max(y, 1) <= 0.01 for t in targets),
            "target_price": y,
        })
    out = pd.DataFrame(rows)
    out.to_csv(AUDIT / f"v7_2_near_duplicate_audit_{task}_{suffix}.csv", index=False, encoding="utf-8-sig")
    return out


def main() -> None:
    for p in [DATA, REPORTS, AUDIT]:
        p.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((DATA / "feature_manifest_v7_1.json").read_text(encoding="utf-8"))
    summary: dict[str, object] = {"version": "v7.2_low_price_addback", "tasks": {}}
    all_manual, all_dirty = [], []

    for task in TASKS:
        base_path = V71_SOURCE / f"pricing_training_v7_1_{task}_model_ready_base.csv"
        base = read_csv(base_path)
        safe = load_low(task, "safe_addback")
        specialist = load_low(task, "specialist")
        manual_path = LOW_REVIEW / "artifacts/audit" / f"{task}_low_price_manual_review_required_v7_2.csv"
        dirty_path = LOW_REVIEW / "artifacts/audit" / f"{task}_low_price_exclude_dirty_v7_2.csv"
        manual = read_csv(manual_path) if manual_path.exists() else pd.DataFrame()
        dirty = read_csv(dirty_path) if dirty_path.exists() else pd.DataFrame()
        all_manual.append(manual)
        all_dirty.append(dirty)

        safe_norm = normalize_low_rows(safe, task, list(base.columns)) if not safe.empty else base.iloc[0:0].copy()
        spec_norm = normalize_low_rows(pd.concat([safe, specialist], ignore_index=True), task, list(base.columns)) if not specialist.empty or not safe.empty else base.iloc[0:0].copy()

        main = pd.concat([base, safe_norm], ignore_index=True)
        main = main.drop_duplicates(["source_dataset", "source_id"], keep="first")
        main = main[pd.to_numeric(main["target_price"], errors="coerce") > 1000].copy()
        main = refresh_count_features(main)
        main["split"] = stable_random_split(main).values
        grouped = main.copy()
        grouped["split"] = grouped_split(grouped).values

        spec = spec_norm.drop_duplicates(["source_dataset", "source_id"], keep="first")
        spec = spec[pd.to_numeric(spec["target_price"], errors="coerce").between(1001, 30000, inclusive="both")].copy()
        spec = refresh_count_features(spec)
        spec["split"] = stable_random_split(spec).values if len(spec) >= 10 else "train"

        main.to_csv(DATA / f"pricing_training_v7_2_{task}_model_ready_base.csv", index=False, encoding="utf-8-sig")
        grouped.to_csv(DATA / f"pricing_training_v7_2_{task}_grouped_split_base.csv", index=False, encoding="utf-8-sig")
        safe_norm.to_csv(DATA / f"pricing_training_v7_2_{task}_low_price_addback.csv", index=False, encoding="utf-8-sig")
        spec.to_csv(DATA / f"pricing_training_v7_2_{task}_low_price_specialist.csv", index=False, encoding="utf-8-sig")
        write_split_audit(main, task, "random")
        write_split_audit(grouped, task, "grouped")
        near_duplicate_audit(main, task, "random")
        near_duplicate_audit(grouped, task, "grouped")

        summary["tasks"][task] = {
            "v7_1_base_rows": len(base),
            "safe_addback_rows": len(safe_norm),
            "specialist_total_rows": len(spec),
            "main_rows": len(main),
            "grouped_rows": len(grouped),
            "manual_review_rows": len(manual),
            "dirty_excluded_rows": len(dirty),
            "random_split_counts": main["split"].value_counts().to_dict(),
            "grouped_split_counts": grouped["split"].value_counts().to_dict(),
        }

    if all_manual:
        pd.concat(all_manual, ignore_index=True).to_csv(DATA / "pricing_training_v7_2_low_price_manual_review_queue.csv", index=False, encoding="utf-8-sig")
        pd.concat(all_manual, ignore_index=True).to_csv(AUDIT / "v7_2_low_price_manual_review_queue.csv", index=False, encoding="utf-8-sig")
    if all_dirty:
        pd.concat(all_dirty, ignore_index=True).to_csv(DATA / "pricing_training_v7_2_low_price_excluded_dirty.csv", index=False, encoding="utf-8-sig")
        pd.concat(all_dirty, ignore_index=True).to_csv(AUDIT / "v7_2_low_price_excluded_dirty.csv", index=False, encoding="utf-8-sig")

    manifest["version"] = "v7.2_low_price_addback"
    manifest["low_price_policy"] = "trusted low-price rows are added to v7.2 main model; specialist candidates are kept for low-price specialist only"
    (DATA / "feature_manifest_v7_2.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "v7_2_training_package_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (AUDIT / "v7_2_low_price_addback_audit.csv").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# V7.2 低价样本回加数据构建报告", "", "## 字段映射", "- `target_value` -> `target_price`", "- `low_price_decision` -> 审核决策字段，仅用于数据选择，不进入训练特征", "- `recommended_usage` / `audit_reasons` -> 审计说明，不进入训练特征", "", "## 汇总", "```json", json.dumps(summary, ensure_ascii=False, indent=2), "```"]
    (REPORTS / "V7_2_LOW_PRICE_REVIEW_AND_ADDBACK_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
