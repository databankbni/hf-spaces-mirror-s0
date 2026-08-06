from __future__ import annotations

import argparse
import json
import math
import shutil
import traceback
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler

from src.training.build_rag_features_two_source import build_rag_features_for_split
from src.training.evaluate_models_two_source import (
    PRICE_BINS,
    PRICE_LABELS,
    add_eval_columns,
    build_group_metrics,
    regression_metrics,
)
from src.training.experiment_scheduler import write_json
from src.training.feature_sets import (
    FORBIDDEN_FEATURES,
    TARGET_BY_TASK,
    VALID_FLAG_BY_TASK,
    available_feature_spec,
)
from src.training.human_review_rules_two_source import apply_human_review_rules
from src.training.model_zoo import candidate_specs, make_estimator


RANDOM_STATE = 42
TASKS = ["c2b", "b2c"]


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def md_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    if df is None or df.empty:
        return "_无数据_"
    if max_rows:
        df = df.head(max_rows)
    cols = list(df.columns)
    rows = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in df.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                if math.isnan(v):
                    vals.append("")
                elif abs(v) < 1:
                    vals.append(f"{v:.4f}")
                else:
                    vals.append(f"{v:.2f}")
            else:
                vals.append(str(v))
        rows.append("| " + " | ".join(vals) + " |")
    return "\n".join(rows)


def load_data(prepared_dir: Path) -> pd.DataFrame:
    csv_path = prepared_dir / "data/processed/pricing_model_training_single_sale_price_v5_reviewed.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"未找到单一销售价训练宽表: {csv_path}")
    df = pd.read_csv(csv_path)
    if "guide_price_missing_flag" not in df.columns:
        df["guide_price_missing_flag"] = df["guide_price_mid_wan"].isna().astype(int)
    if "sample_id" not in df.columns:
        df["sample_id"] = np.arange(len(df)).astype(str)
    for col in ["pricing_order_id", "source_record_id", "source_product_id"]:
        if col in df.columns:
            df[col] = df[col].astype(str)
    if "pricing_order_id" not in df.columns:
        df["pricing_order_id"] = df["sample_id"]
    df["price_bucket_c2b"] = pd.cut(pd.to_numeric(df.get("purchase_price"), errors="coerce"), PRICE_BINS, labels=PRICE_LABELS, include_lowest=True).astype(str)
    df["price_bucket_b2c"] = pd.cut(pd.to_numeric(df.get("sale_price"), errors="coerce"), PRICE_BINS, labels=PRICE_LABELS, include_lowest=True).astype(str)
    df["has_real_car_age"] = df.get("real_car_age_years").notna().astype(int) if "real_car_age_years" in df.columns else 0
    return df


def task_frame(df: pd.DataFrame, task: str) -> pd.DataFrame:
    target = TARGET_BY_TASK[task]
    valid_flag = VALID_FLAG_BY_TASK[task]
    out = df.copy()
    mask = out[target].notna() & (pd.to_numeric(out[target], errors="coerce") > 1000)
    if valid_flag in out.columns:
        mask &= out[valid_flag].fillna(0).astype(int).eq(1)
    if "price_outlier_flag" in out.columns:
        mask &= ~out["price_outlier_flag"].fillna(0).astype(int).eq(1)
    out = out.loc[mask].reset_index(drop=True)
    return out


def phase0_report(df: pd.DataFrame, output_root: Path) -> None:
    report_dir = ensure_dir(output_root / "reports")
    rows = []
    for task in TASKS:
        tdf = task_frame(df, task)
        rows.append({
            "task": task,
            "有效样本数": len(tdf),
            "目标字段": TARGET_BY_TASK[task],
            "价格均值": pd.to_numeric(tdf[TARGET_BY_TASK[task]], errors="coerce").mean(),
            "价格中位数": pd.to_numeric(tdf[TARGET_BY_TASK[task]], errors="coerce").median(),
        })
    fields = pd.DataFrame({
        "field": df.columns,
        "missing_rate": [df[c].isna().mean() for c in df.columns],
        "unique_count": [df[c].nunique(dropna=True) for c in df.columns],
        "dtype": [str(df[c].dtype) for c in df.columns],
    }).sort_values("missing_rate", ascending=False)
    fields.to_csv(output_root / "artifacts/model_results/phase0_field_profile.csv", index=False, encoding="utf-8-sig")
    text = [
        "# Phase 0 数据和特征检查",
        "",
        "本阶段只做字段、样本、缺失率和泄露字段检查，不训练重模型。",
        "",
        "## 有效样本数",
        md_table(pd.DataFrame(rows)),
        "",
        "## source_dataset 分布",
        md_table(df["source_dataset"].value_counts(dropna=False).reset_index().rename(columns={"source_dataset": "source_dataset", "count": "count"}), 20) if "source_dataset" in df.columns else "未找到 source_dataset",
        "",
        "## sale_price_source 分布",
        md_table(df["sale_price_source"].value_counts(dropna=False).reset_index().rename(columns={"sale_price_source": "sale_price_source", "count": "count"}), 20) if "sale_price_source" in df.columns else "未找到 sale_price_source",
        "",
        "## 关键字段覆盖率",
        md_table(pd.DataFrame([
            {"field": "age_for_training", "coverage": 1 - df.get("age_for_training", pd.Series(index=df.index)).isna().mean()},
            {"field": "real_car_age_years", "coverage": 1 - df.get("real_car_age_years", pd.Series(index=df.index)).isna().mean()},
            {"field": "guide_price_mid_wan", "coverage": 1 - df.get("guide_price_mid_wan", pd.Series(index=df.index)).isna().mean()},
        ])),
        "",
        "## 禁止进入训练的泄露字段",
        ", ".join(sorted(FORBIDDEN_FEATURES)),
        "",
        "## 缺失率最高字段 Top 30",
        md_table(fields.head(30)),
    ]
    (report_dir / "PHASE0_DATA_AND_FEATURE_CHECK_V5_REVIEWED.md").write_text("\n".join(text), encoding="utf-8")


def split_task(df: pd.DataFrame, task: str, output_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    target = TARGET_BY_TASK[task]
    id_col = "pricing_order_id"
    work = task_frame(df, task).copy()
    bucket = pd.cut(pd.to_numeric(work[target], errors="coerce"), PRICE_BINS, labels=PRICE_LABELS, include_lowest=True).astype(str)
    source = work["source_dataset"].fillna("unknown").astype(str) if "source_dataset" in work.columns else "unknown"
    strat = (bucket + "|" + source).astype(str)
    counts = strat.value_counts()
    strat = strat.where(strat.map(counts) >= 4, bucket)
    try:
        train_idx, temp_idx = train_test_split(work.index, test_size=0.30, random_state=RANDOM_STATE, stratify=strat)
        temp_strat = strat.loc[temp_idx]
        counts2 = temp_strat.value_counts()
        temp_strat = temp_strat.where(temp_strat.map(counts2) >= 2, bucket.loc[temp_idx])
        valid_idx, test_idx = train_test_split(temp_idx, test_size=0.50, random_state=RANDOM_STATE, stratify=temp_strat)
    except Exception:
        train_idx, temp_idx = train_test_split(work.index, test_size=0.30, random_state=RANDOM_STATE)
        valid_idx, test_idx = train_test_split(temp_idx, test_size=0.50, random_state=RANDOM_STATE)
    train, valid, test = work.loc[train_idx].reset_index(drop=True), work.loc[valid_idx].reset_index(drop=True), work.loc[test_idx].reset_index(drop=True)
    split_dir = ensure_dir(output_root / "artifacts/splits")
    train[[id_col]].to_csv(split_dir / f"{task}_train_ids.csv", index=False)
    valid[[id_col]].to_csv(split_dir / f"{task}_valid_ids.csv", index=False)
    test[[id_col]].to_csv(split_dir / f"{task}_test_ids.csv", index=False)
    return train, valid, test


def stratified_downsample(df: pd.DataFrame, target_col: str, n: int) -> pd.DataFrame:
    if len(df) <= n:
        return df.reset_index(drop=True)
    bucket = pd.cut(pd.to_numeric(df[target_col], errors="coerce"), PRICE_BINS, labels=PRICE_LABELS, include_lowest=True).astype(str)
    source = df["source_dataset"].fillna("unknown").astype(str) if "source_dataset" in df.columns else "unknown"
    key = bucket + "|" + source
    sampled = (
        df.assign(_key=key)
        .groupby("_key", group_keys=False)
        .apply(lambda x: x.sample(min(len(x), max(1, int(math.floor(len(x) / len(df) * n)))), random_state=RANDOM_STATE))
        .drop(columns=["_key"])
    )
    if len(sampled) >= n:
        return sampled.sample(n=n, random_state=RANDOM_STATE).reset_index(drop=True)
    remaining = df.drop(index=sampled.index, errors="ignore")
    if len(remaining) > 0:
        sampled = pd.concat([sampled, remaining.sample(n=min(n - len(sampled), len(remaining)), random_state=RANDOM_STATE)])
    return sampled.sample(n=min(n, len(sampled)), random_state=RANDOM_STATE).reset_index(drop=True)


def sample_splits(train: pd.DataFrame, valid: pd.DataFrame, test: pd.DataFrame, target_col: str, total_n: int):
    n_train = int(total_n * 0.70)
    n_valid = int(total_n * 0.15)
    n_test = total_n - n_train - n_valid
    return (
        stratified_downsample(train, target_col, n_train),
        stratified_downsample(valid, target_col, n_valid),
        stratified_downsample(test, target_col, n_test),
    )


def add_rag(train: pd.DataFrame, valid: pd.DataFrame, test: pd.DataFrame, task: str, output_root: Path, tag: str):
    target = TARGET_BY_TASK[task]
    cache_dir = ensure_dir(output_root / "artifacts/rag_features_v5")
    paths = [cache_dir / f"{task}_{tag}_{split}_rag.csv" for split in ["train", "valid", "test"]]
    if all(p.exists() for p in paths):
        return tuple(pd.concat([frame.reset_index(drop=True), pd.read_csv(path)], axis=1) for frame, path in zip([train, valid, test], paths))
    train_rag, valid_rag, test_rag = build_rag_features_for_split(train, valid, test, target)
    train_rag.to_csv(paths[0], index=False)
    valid_rag.to_csv(paths[1], index=False)
    test_rag.to_csv(paths[2], index=False)
    return (
        pd.concat([train.reset_index(drop=True), train_rag], axis=1),
        pd.concat([valid.reset_index(drop=True), valid_rag], axis=1),
        pd.concat([test.reset_index(drop=True), test_rag], axis=1),
    )


def make_preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    num_pipe = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler(with_mean=False))])
    cat_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="__missing__")),
        ("ordinal", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
    ])
    return ColumnTransformer(
        transformers=[
            ("num", num_pipe, numeric),
            ("cat", cat_pipe, categorical),
        ],
        remainder="drop",
    )


def fit_predict_model(model_name: str, feature_set: str, task: str, train: pd.DataFrame, valid: pd.DataFrame, test: pd.DataFrame, phase: str, output_root: Path):
    target = TARGET_BY_TASK[task]
    if model_name == "PureComparable_top5_median":
        fallback = float(train[target].median())
        valid_pred = pd.to_numeric(valid.get("rag_top5_median_price"), errors="coerce").fillna(valid.get("rag_top10_median_price")).fillna(fallback).to_numpy()
        test_pred = pd.to_numeric(test.get("rag_top5_median_price"), errors="coerce").fillna(test.get("rag_top10_median_price")).fillna(fallback).to_numpy()
        return None, valid_pred, test_pred, "pure_rag"

    spec = available_feature_spec(train.columns, feature_set, task)
    # v5: sale_price_source and audit/review fields are forbidden as model inputs.
    features = [c for c in spec.features if c != "sale_price_source" and not c.endswith("_reason_v5") and not c.endswith("_status_v5") and "audit" not in c and "review" not in c]
    spec = spec.__class__(spec.name, features, spec.missing, [c for c in spec.categorical if c in features], [c for c in spec.numeric if c in features])
    train_x = train[spec.features].copy()
    valid_x = valid[spec.features].copy()
    test_x = test[spec.features].copy()
    # 宽表来自两份数据源，同一分类列可能混有 float / str。显式转字符串，避免 OrdinalEncoder 报错。
    for c in spec.categorical:
        train_x[c] = train_x[c].where(train_x[c].notna(), "__missing__").astype(str)
        valid_x[c] = valid_x[c].where(valid_x[c].notna(), "__missing__").astype(str)
        test_x[c] = test_x[c].where(test_x[c].notna(), "__missing__").astype(str)
    preprocessor = make_preprocessor(spec.numeric, spec.categorical)
    estimator = make_estimator(model_name, phase=phase, random_state=RANDOM_STATE)
    pipe = Pipeline([("preprocessor", preprocessor), ("model", estimator)])
    y_train = np.log1p(pd.to_numeric(train[target], errors="coerce").to_numpy())
    pipe.fit(train_x, y_train)
    valid_pred = np.expm1(pipe.predict(valid_x))
    test_pred = np.expm1(pipe.predict(test_x))
    return pipe, valid_pred, test_pred, f"missing_features={spec.missing}"


def save_predictions(path: Path, df: pd.DataFrame, target: str, pred: np.ndarray, meta: dict) -> None:
    cols = [
        "pricing_order_id", "source_dataset", "sale_price_source", "brand", "series", "vehicle_model",
        "model_id", "city", "model_year", "age_for_training", "mileage_wan_km", "transfer_count",
        "guide_price_mid_wan", "guide_price_match_level", "guide_price_match_confidence",
        "rag_confidence", "rag_match_level", "rag_confidence_score", target,
    ]
    keep = [c for c in cols if c in df.columns]
    out = df[keep].copy()
    out["pred_price"] = pred
    out = add_eval_columns(out, target)
    for k, v in meta.items():
        out[k] = v
    ensure_dir(path.parent)
    out.to_csv(path, index=False, encoding="utf-8-sig")


def run_one(task: str, model_name: str, feature_set: str, phase: str, train: pd.DataFrame, valid: pd.DataFrame, test: pd.DataFrame, output_root: Path) -> dict:
    target = TARGET_BY_TASK[task]
    start = perf_counter()
    record = {
        "task": task,
        "model_name": model_name,
        "feature_set": feature_set,
        "phase": phase,
        "train_rows": len(train),
        "valid_rows": len(valid),
        "test_rows": len(test),
        "status": "running",
    }
    try:
        model, valid_pred, test_pred, notes = fit_predict_model(model_name, feature_set, task, train, valid, test, phase, output_root)
        metrics = regression_metrics(test[target], test_pred)
        valid_metrics = regression_metrics(valid[target], valid_pred)
        pred_dir = ensure_dir(output_root / "artifacts/predictions")
        safe_name = f"{task}_{phase}_{model_name}_{feature_set}".replace("/", "_")
        valid_path = pred_dir / f"{safe_name}_valid_predictions.csv"
        test_path = pred_dir / f"{safe_name}_test_predictions.csv"
        save_predictions(valid_path, valid, target, valid_pred, {"split": "valid", "model_name": model_name, "feature_set": feature_set})
        save_predictions(test_path, test, target, test_pred, {"split": "test", "model_name": model_name, "feature_set": feature_set})
        if model is not None and phase == "phase2":
            model_path = ensure_dir(output_root / "artifacts/models") / f"{task}_{model_name}_{feature_set}.pkl"
            joblib.dump(model, model_path)
            record["model_path"] = str(model_path)
        record.update(metrics)
        record.update({f"valid_{k}": v for k, v in valid_metrics.items()})
        record["predictions_path"] = str(test_path)
        record["valid_predictions_path"] = str(valid_path)
        record["notes"] = notes
        record["status"] = "completed"
    except Exception as exc:
        record["status"] = "failed"
        record["error_message"] = str(exc)
        record["traceback"] = traceback.format_exc(limit=6)
    record["duration_seconds"] = perf_counter() - start
    return record


def append_result(path: Path, record: dict) -> None:
    ensure_dir(path.parent)
    if path.exists():
        old = pd.read_csv(path)
        df = pd.concat([old, pd.DataFrame([record])], ignore_index=True)
    else:
        df = pd.DataFrame([record])
    df.to_csv(path, index=False, encoding="utf-8-sig")


def result_done(path: Path, task: str, model_name: str, feature_set: str, phase: str) -> bool:
    if not path.exists():
        return False
    df = pd.read_csv(path)
    return bool(((df.task == task) & (df.model_name == model_name) & (df.feature_set == feature_set) & (df.phase == phase) & (df.status == "completed")).any())


def run_phase1(splits: dict, output_root: Path, args) -> None:
    reports = ensure_dir(output_root / "reports")
    model_result_dir = ensure_dir(output_root / "artifacts/model_results")
    skipped = [s.__dict__ for s in candidate_specs() if s.skipped_reason]
    pd.DataFrame(skipped).to_csv(model_result_dir / "phase1_skipped_models_v5.csv", index=False, encoding="utf-8-sig")
    phase1_specs = [s for s in candidate_specs() if s.phase1 and not s.skipped_reason]
    for task in TASKS:
        result_path = model_result_dir / f"phase1_screening_{task}_v5.csv"
        target = TARGET_BY_TASK[task]
        train, valid, test = splits[task]
        total_n = args.sample_size_c2b if task == "c2b" else args.sample_size_b2c
        s_train, s_valid, s_test = sample_splits(train, valid, test, target, total_n)
        s_train_rag, s_valid_rag, s_test_rag = add_rag(s_train, s_valid, s_test, task, output_root, f"phase1_{total_n}")
        for spec in phase1_specs:
            feature_sets = ["F5"] if spec.family == "pure_rag" else ["F4_source", "F5"]
            for fs in feature_sets:
                if result_done(result_path, task, spec.name, fs, "phase1"):
                    continue
                train_use, valid_use, test_use = (s_train_rag, s_valid_rag, s_test_rag) if fs == "F5" else (s_train, s_valid, s_test)
                rec = run_one(task, spec.name, fs, "phase1", train_use, valid_use, test_use, output_root)
                append_result(result_path, rec)
    lines = ["# Phase 1 快速模型筛选报告", ""]
    for task in TASKS:
        path = model_result_dir / f"phase1_screening_{task}_v5.csv"
        df = pd.read_csv(path) if path.exists() else pd.DataFrame()
        ok = df[df["status"] == "completed"].sort_values("MAPE").head(15) if not df.empty else df
        lines += [f"## {task.upper()} Top 15", md_table(ok[["model_name", "feature_set", "MAPE", "MAE", "RMSE", "Median_APE", "P90_APE", "R2", "duration_seconds"]], 15), ""]
    lines += ["## 跳过模型", md_table(pd.DataFrame(skipped), 30)]
    (reports / "PHASE1_MODEL_SCREENING_REPORT_V5_REVIEWED.md").write_text("\n".join(lines), encoding="utf-8")


def select_phase2_models(output_root: Path, task: str, top_k: int = 6) -> list[str]:
    path = output_root / f"artifacts/model_results/phase1_screening_{task}_v5.csv"
    df = pd.read_csv(path)
    ok = df[df["status"] == "completed"].copy()
    base = [
        "LightGBM_L2",
        "LightGBM_L1",
        "XGBoost_squarederror",
        "CatBoost_RMSE",
        "Sklearn_HistGBR",
        "PureComparable_top5_median",
    ]
    top = ok.sort_values("MAPE")["model_name"].drop_duplicates().head(top_k).tolist()
    return list(dict.fromkeys(base + top))


def run_phase2(splits: dict, output_root: Path, args) -> None:
    model_result_dir = ensure_dir(output_root / "artifacts/model_results")
    for task in TASKS:
        result_path = model_result_dir / f"model_comparison_{task}_v5.csv"
        train, valid, test = splits[task]
        train_rag, valid_rag, test_rag = add_rag(train, valid, test, task, output_root, "phase2_full")
        selected = select_phase2_models(output_root, task, args.phase2_top_k)
        for model_name in selected:
            if model_name.startswith("LightGBM"):
                feature_sets = ["F0_proxy", "F0_real_age", "F1", "F2", "F3", "F4", "F4_source", "F5"]
            elif model_name in {"XGBoost_squarederror", "CatBoost_RMSE", "Sklearn_HistGBR"}:
                feature_sets = ["F0_real_age", "F4_source", "F5"]
            else:
                feature_sets = ["F5"]
            for fs in feature_sets:
                if result_done(result_path, task, model_name, fs, "phase2"):
                    continue
                train_use, valid_use, test_use = (train_rag, valid_rag, test_rag) if fs == "F5" else (train, valid, test)
                rec = run_one(task, model_name, fs, "phase2", train_use, valid_use, test_use, output_root)
                append_result(result_path, rec)
    lines = ["# Phase 2 Top 模型全量训练报告", ""]
    for task in TASKS:
        path = model_result_dir / f"model_comparison_{task}_v5.csv"
        df = pd.read_csv(path) if path.exists() else pd.DataFrame()
        ok = df[df["status"] == "completed"].sort_values("MAPE").head(20) if not df.empty else df
        lines += [f"## {task.upper()} 全量结果 Top 20", md_table(ok[["model_name", "feature_set", "MAPE", "MAE", "RMSE", "Median_APE", "P90_APE", "R2", "duration_seconds", "model_path"] if "model_path" in ok.columns else ok.columns], 20), ""]
    (output_root / "reports/MODEL_TRAINING_REPORT_V5_REVIEWED.md").write_text("\n".join(lines), encoding="utf-8")


def best_full(output_root: Path, task: str) -> pd.Series:
    path = output_root / f"artifacts/model_results/model_comparison_{task}_v5.csv"
    df = pd.read_csv(path)
    ok = df[df["status"] == "completed"].sort_values("MAPE")
    return ok.iloc[0]


def run_phase3(df: pd.DataFrame, splits: dict, output_root: Path, args) -> None:
    summary = []
    for task in TASKS:
        best = best_full(output_root, task)
        pred_path = Path(best["predictions_path"])
        valid_pred_path = Path(best["valid_predictions_path"])
        test_preds = pd.read_csv(pred_path)
        valid_preds = pd.read_csv(valid_pred_path)
        target = TARGET_BY_TASK[task]
        # Human review evaluation
        reviewed = apply_human_review_rules(test_preds, pred_col="pred_price")
        reviewed_path = output_root / f"artifacts/predictions/{task}_test_predictions_with_review.csv"
        ensure_dir(reviewed_path.parent)
        reviewed.to_csv(reviewed_path, index=False, encoding="utf-8-sig")
        auto = reviewed[~reviewed["need_human_review"]]
        manual = reviewed[reviewed["need_human_review"]]
        full_m = regression_metrics(reviewed["true_price"], reviewed["pred_price"])
        auto_m = regression_metrics(auto["true_price"], auto["pred_price"])
        manual_m = regression_metrics(manual["true_price"], manual["pred_price"])
        summary.append({"task": task, "experiment": "human_review", "base_model": best["model_name"], "feature_set": best["feature_set"], "coverage": len(auto) / len(reviewed), "MAPE": auto_m["MAPE"], "full_MAPE": full_m["MAPE"], "manual_MAPE": manual_m["MAPE"], "path": str(reviewed_path)})

        # Residual correction using valid residuals.
        try:
            from lightgbm import LGBMRegressor
            residual_features = ["pred_price", "rag_confidence_score", "model_sample_count", "age_for_training", "mileage_wan_km", "transfer_count"]
            residual_features = [c for c in residual_features if c in valid_preds.columns and c in test_preds.columns]
            valid_res = valid_preds["true_price"] - valid_preds["pred_price"]
            model = LGBMRegressor(n_estimators=400, learning_rate=0.04, num_leaves=31, random_state=RANDOM_STATE, verbose=-1)
            model.fit(valid_preds[residual_features].fillna(-1), valid_res)
            corr = model.predict(test_preds[residual_features].fillna(-1))
            clipped = np.clip(corr, -0.2 * test_preds["pred_price"], 0.2 * test_preds["pred_price"])
            residual_pred = test_preds["pred_price"] + clipped
            m = regression_metrics(test_preds["true_price"], residual_pred)
            residual_out = test_preds.copy()
            residual_out["pred_price"] = residual_pred
            residual_out.to_csv(output_root / f"artifacts/predictions/{task}_residual_corrected_predictions.csv", index=False, encoding="utf-8-sig")
            summary.append({"task": task, "experiment": "residual_correction", "base_model": best["model_name"], "feature_set": best["feature_set"], **m})
        except Exception as exc:
            summary.append({"task": task, "experiment": "residual_correction", "status": "failed", "error": str(exc)})

        # Ratio target on high-confidence guide-price subset.
        try:
            train, valid, test = splits[task]
            subset = {}
            for split_name, part in {"train": train, "valid": valid, "test": test}.items():
                mask = (part["guide_price_mid_wan"].notna()) & (pd.to_numeric(part["guide_price_match_confidence"], errors="coerce").fillna(0) >= 0.7) & (pd.to_numeric(part["guide_price_mid_wan"], errors="coerce") > 0)
                subset[split_name] = part.loc[mask].copy()
            if min(len(subset["train"]), len(subset["valid"]), len(subset["test"])) >= 50:
                fs = "F4_source"
                target_ratio = f"{task}_ratio_target"
                for part in subset.values():
                    part[target_ratio] = part[target] / (part["guide_price_mid_wan"] * 10000)
                from lightgbm import LGBMRegressor
                spec = available_feature_spec(subset["train"].columns, fs, task)
                pp = make_preprocessor(spec.numeric, spec.categorical)
                pipe = Pipeline([("preprocessor", pp), ("model", LGBMRegressor(n_estimators=800, learning_rate=0.04, num_leaves=31, random_state=RANDOM_STATE, verbose=-1))])
                train_x = subset["train"][spec.features].copy()
                test_x = subset["test"][spec.features].copy()
                for c in spec.categorical:
                    train_x[c] = train_x[c].where(train_x[c].notna(), "__missing__").astype(str)
                    test_x[c] = test_x[c].where(test_x[c].notna(), "__missing__").astype(str)
                pipe.fit(train_x, subset["train"][target_ratio])
                ratio_pred = pipe.predict(test_x)
                price_pred = ratio_pred * subset["test"]["guide_price_mid_wan"].to_numpy() * 10000
                m = regression_metrics(subset["test"][target], price_pred)
                summary.append({"task": task, "experiment": "ratio_target_high_conf_guide", "test_rows": len(subset["test"]), **m})
            else:
                summary.append({"task": task, "experiment": "ratio_target_high_conf_guide", "status": "skipped", "reason": "高置信指导价样本不足"})
        except Exception as exc:
            summary.append({"task": task, "experiment": "ratio_target_high_conf_guide", "status": "failed", "error": str(exc)})

    summary_df = pd.DataFrame(summary)
    out_path = output_root / "artifacts/model_results/special_experiments_summary.csv"
    ensure_dir(out_path.parent)
    summary_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    lines = ["# Phase 3 专项实验报告", "", md_table(summary_df, 50)]
    (output_root / "reports/PHASE3_SPECIAL_EXPERIMENTS_REPORT_V5_REVIEWED.md").write_text("\n".join(lines), encoding="utf-8")


def write_final_reports(output_root: Path) -> None:
    lines = ["# 最终模型选择报告", ""]
    best_rows = []
    for task in TASKS:
        full_path = output_root / f"artifacts/model_results/model_comparison_{task}_v5.csv"
        if not full_path.exists():
            continue
        df = pd.read_csv(full_path)
        ok = df[df["status"] == "completed"].sort_values("MAPE")
        if ok.empty:
            continue
        best = ok.iloc[0]
        best_rows.append(best)
        lines += [
            f"## {task.upper()} 最佳模型",
            md_table(ok[["model_name", "feature_set", "MAPE", "MAE", "RMSE", "Median_APE", "P90_APE", "R2", "duration_seconds"]].head(10)),
            "",
        ]
        if "model_path" in best and isinstance(best.get("model_path"), str) and Path(best["model_path"]).exists():
            dst = output_root / f"artifacts/models/{task}_best_model.pkl"
            shutil.copyfile(best["model_path"], dst)
            # 当前 pipeline 已包含 preprocessor，这里额外复制一份同名 preprocessor 占位，方便下游固定路径读取。
            shutil.copyfile(best["model_path"], output_root / f"artifacts/models/{task}_preprocessor.pkl")
    special = output_root / "artifacts/model_results/special_experiments_summary.csv"
    if special.exists():
        s = pd.read_csv(special)
        lines += ["## 专项实验摘要", md_table(s, 30), ""]
    lines += [
        "## 结论口径",
        "- Phase 1 是抽样筛选，不能作为最终指标。",
        "- Phase 2 是全量统一 split 结果，作为模型选择主口径。",
        "- LLM / Qwen / LoRA 不作为最终价格主模型，后续只建议用于字段抽取、解释和 badcase 归因。",
    ]
    (output_root / "reports/MODEL_TRAINING_REPORT_V5_REVIEWED.md").write_text("\n".join(lines), encoding="utf-8")
    (output_root / "reports/HUMAN_REVIEW_COVERAGE_ACCURACY_REPORT.md").write_text("\n".join([
        "# Human Review 评估报告",
        "",
        "详见 `artifacts/model_results/special_experiments_summary.csv` 中 `human_review` 行。",
        "",
        "当前规则会对可比样本低置信、指导价未匹配、低样本车型、极低/极高预测价、与可比样本或指导价偏离过大的样本触发人工复核。",
    ]), encoding="utf-8")
    (output_root / "reports/NEXT_DATA_IMPROVEMENT_PLAN_V5_REVIEWED.md").write_text("\n".join([
        "# 下一步数据补强计划",
        "",
        "1. 优先补 P0/P1 高频车型的新车指导价，当前 guide price 覆盖率仍偏低。",
        "2. 保留真实上牌时间，真实车龄比年款 proxy 更接近折旧逻辑。",
        "3. 对低样本车型补充车型库映射和人工复核标签。",
        "4. 补事故/水泡/火烧/调表等车况风险字段，当前训练数据缺强风险特征。",
        "5. 持续记录线上预测、人工最终价和用户反馈，用于后续 shadow mode 校准。",
    ]), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared-dir", default="/Users/bytedance/Downloads/used_car_pricing_single_sale_price_v5_low_price_aware_reviewed")
    parser.add_argument("--output-root", default=".")
    parser.add_argument("--phase", choices=["phase0", "phase1", "phase2", "phase3", "all"], default="all")
    parser.add_argument("--sample-size-c2b", type=int, default=15000)
    parser.add_argument("--sample-size-b2c", type=int, default=20000)
    parser.add_argument("--phase2-top-k", type=int, default=6)
    args = parser.parse_args()

    output_root = Path(args.output_root).resolve()
    ensure_dir(output_root / "reports")
    ensure_dir(output_root / "artifacts/model_results")
    df = load_data(Path(args.prepared_dir))

    if args.phase in {"phase0", "all"}:
        phase0_report(df, output_root)

    splits = {task: split_task(df, task, output_root) for task in TASKS}

    if args.phase in {"phase1", "all"}:
        run_phase1(splits, output_root, args)
    if args.phase in {"phase2", "all"}:
        run_phase2(splits, output_root, args)
    if args.phase in {"phase3", "all"}:
        run_phase3(df, splits, output_root, args)
    if args.phase == "all":
        write_final_reports(output_root)


if __name__ == "__main__":
    main()
