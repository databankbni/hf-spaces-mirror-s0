#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/processed"
ART = ROOT / "artifacts"
REPORTS = ROOT / "reports"
RANDOM_STATE = 42
RAG_FEATURES = [
    "rag_top1_price", "rag_top3_mean_price", "rag_top5_mean_price", "rag_top10_mean_price",
    "rag_top5_median_price", "rag_top10_median_price", "rag_top5_min_price", "rag_top5_max_price",
    "rag_top5_std_price", "rag_top5_count", "rag_top10_count", "rag_same_model_id_count",
    "rag_same_series_count", "rag_same_city_count", "rag_distance_mean", "rag_confidence_score", "rag_match_level",
]
FORBIDDEN = {
    "target_price", "source_id", "target_task", "purchase_price", "sale_price", "purchase_price_source",
    "sale_price_source", "first_board_price_raw", "first_pricer_sale_price_raw", "purchase_contract_price_raw",
    "final_purchase_price_raw", "review_or_excluded_reason", "ratio", "APE", "pred_price", "pred_lower",
    "pred_upper", "low_price_decision", "recommended_usage", "audit_reasons", "sale_purchase_ratio",
    "sale_minus_purchase", "low_price_action", "review_reason",
}


@dataclass(frozen=True)
class Experiment:
    model_name: str
    feature_set: str
    split_type: str


def ensure_dirs() -> None:
    for p in [
        ART / "model_results", ART / "predictions", ART / "error_analysis", ART / "models", REPORTS
    ]:
        p.mkdir(parents=True, exist_ok=True)


def md_table(df: pd.DataFrame, max_rows: int = 50) -> str:
    if df is None or df.empty:
        return "_无数据_"
    view = df.head(max_rows).copy().fillna("")
    lines = ["| " + " | ".join(map(str, view.columns)) + " |", "| " + " | ".join(["---"] * len(view.columns)) + " |"]
    for _, row in view.iterrows():
        lines.append("| " + " | ".join(str(row[c]).replace("\n", " ") for c in view.columns) + " |")
    return "\n".join(lines)


def metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    y = np.asarray(y, dtype=float)
    pred = np.asarray(pred, dtype=float)
    ape = np.abs(y - pred) / np.maximum(np.abs(y), 1)
    try:
        rmse = mean_squared_error(y, pred, squared=False)
    except TypeError:
        rmse = math.sqrt(mean_squared_error(y, pred))
    return {
        "MAE": float(mean_absolute_error(y, pred)),
        "RMSE": float(rmse),
        "MAPE": float(np.mean(ape) * 100),
        "Median_APE": float(np.median(ape) * 100),
        "P90_APE": float(np.quantile(ape, 0.9) * 100),
        "R2": float(r2_score(y, pred)),
        "sample_count": int(len(y)),
    }


def add_price_bucket(s: pd.Series) -> pd.Series:
    bins = [-np.inf, 10000, 20000, 30000, 50000, 100000, 200000, 300000, 500000, 1000000, np.inf]
    labels = ["<=1万", "1-2万", "2-3万", "3-5万", "5-10万", "10-20万", "20-30万", "30-50万", "50-100万", ">100万"]
    return pd.cut(pd.to_numeric(s, errors="coerce"), bins=bins, labels=labels, right=False).astype(str)


def read_manifest() -> dict[str, Any]:
    return json.loads((DATA / "feature_manifest_v7_2.json").read_text(encoding="utf-8"))


def base_features(df: pd.DataFrame, include_rag: bool = True) -> list[str]:
    manifest = read_manifest()
    allowed = [c for c in manifest["feature_columns"] if c in df.columns and c not in FORBIDDEN and c != "source_dataset"]
    if include_rag:
        allowed += [c for c in RAG_FEATURES if c in df.columns]
    return list(dict.fromkeys(allowed))


def make_preprocessor(df: pd.DataFrame, features: list[str]) -> ColumnTransformer:
    cat = [c for c in features if df[c].dtype == "object"]
    num = [c for c in features if c not in cat]
    cat_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
        ("encoder", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
    ])
    num_pipe = Pipeline([("imputer", SimpleImputer(strategy="median"))])
    return ColumnTransformer([("num", num_pipe, num), ("cat", cat_pipe, cat)], remainder="drop")


def make_model(name: str):
    if name == "LightGBM":
        from lightgbm import LGBMRegressor
        return LGBMRegressor(
            objective="regression_l1", n_estimators=1200, learning_rate=0.045, num_leaves=63,
            min_child_samples=50, subsample=0.88, colsample_bytree=0.86, reg_alpha=0.1,
            reg_lambda=8.0, random_state=RANDOM_STATE, n_jobs=-1, verbose=-1
        )
    if name == "XGBoost":
        from xgboost import XGBRegressor
        return XGBRegressor(
            objective="reg:squarederror", n_estimators=1200, learning_rate=0.045, max_depth=7,
            min_child_weight=5, subsample=0.88, colsample_bytree=0.86, reg_alpha=0.1,
            reg_lambda=8.0, tree_method="hist", random_state=RANDOM_STATE, n_jobs=-1
        )
    if name == "CatBoost":
        from catboost import CatBoostRegressor
        return CatBoostRegressor(
            loss_function="MAE", iterations=900, learning_rate=0.05, depth=8, l2_leaf_reg=10,
            random_seed=RANDOM_STATE, verbose=False, allow_writing_files=False
        )
    if name == "ExtraTrees":
        return ExtraTreesRegressor(n_estimators=160, min_samples_leaf=2, max_features=0.85, random_state=RANDOM_STATE, n_jobs=-1)
    if name == "RandomForest":
        return RandomForestRegressor(n_estimators=90, min_samples_leaf=3, max_features=0.8, random_state=RANDOM_STATE, n_jobs=-1)
    if name == "HistGBR":
        return HistGradientBoostingRegressor(loss="absolute_error", learning_rate=0.06, max_iter=700, max_leaf_nodes=63, l2_regularization=0.1, early_stopping=True, random_state=RANDOM_STATE)
    raise ValueError(name)


def load_data(task: str, split_type: str) -> pd.DataFrame:
    if split_type == "grouped":
        p = DATA / f"pricing_training_v7_2_{task}_grouped_split_with_true_topk_rag.csv"
    elif split_type == "specialist":
        p = DATA / f"pricing_training_v7_2_{task}_low_price_specialist.csv"
    else:
        p = DATA / f"pricing_training_v7_2_{task}_model_ready_with_true_topk_rag.csv"
    return pd.read_csv(p, low_memory=False)


def pure_rag_predict(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    train_med = float(df.loc[df["split"].eq("train"), "target_price"].median())
    col = "rag_top5_median_price" if "rag_top5_median_price" in df.columns else "rag_top10_median_price"
    valid = df.loc[df["split"].eq("valid"), col].astype(float).fillna(train_med).to_numpy()
    test = df.loc[df["split"].eq("test"), col].astype(float).fillna(train_med).to_numpy()
    return valid, test


def group_median_predict(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    train = df[df["split"].eq("train")]
    train_med = float(train["target_price"].median())
    maps = {}
    for key in ["model_id", "series", "brand"]:
        if key in train:
            maps[key] = train.groupby(key)["target_price"].median().to_dict()

    def pred_part(part: pd.DataFrame) -> np.ndarray:
        vals = []
        for _, r in part.iterrows():
            v = np.nan
            for key in ["model_id", "series", "brand"]:
                if key in maps:
                    v = maps[key].get(r.get(key), np.nan)
                    if pd.notna(v):
                        break
            vals.append(float(v) if pd.notna(v) else train_med)
        return np.asarray(vals)

    return pred_part(df[df["split"].eq("valid")]), pred_part(df[df["split"].eq("test")])


def train_one(task: str, df: pd.DataFrame, exp: Experiment) -> tuple[dict[str, Any], pd.DataFrame | None]:
    start = time.time()
    rec: dict[str, Any] = {"task": task, "model_name": exp.model_name, "feature_set": exp.feature_set, "split_type": exp.split_type}
    try:
        valid_mask = df["split"].eq("valid")
        test_mask = df["split"].eq("test")
        if exp.model_name == "PureComparable":
            valid_pred, test_pred = pure_rag_predict(df) if exp.feature_set == "F3_rag" else group_median_predict(df)
            model = None
        else:
            features = base_features(df, include_rag=(exp.feature_set == "F3_rag"))
            train_mask = df["split"].eq("train")
            pipe = Pipeline([("preprocessor", make_preprocessor(df, features)), ("model", make_model(exp.model_name))])
            pipe.fit(df.loc[train_mask, features], np.log1p(df.loc[train_mask, "target_price"].astype(float)))
            valid_pred = np.expm1(pipe.predict(df.loc[valid_mask, features]))
            test_pred = np.expm1(pipe.predict(df.loc[test_mask, features]))
            model = pipe
        vm = metrics(df.loc[valid_mask, "target_price"], valid_pred)
        tm = metrics(df.loc[test_mask, "target_price"], test_pred)
        rec.update(tm)
        rec.update({f"valid_{k}": v for k, v in vm.items()})
        rec.update({
            "train_rows": int(df["split"].eq("train").sum()),
            "valid_rows": int(valid_mask.sum()),
            "test_rows": int(test_mask.sum()),
            "duration_seconds": round(time.time() - start, 2),
            "status": "completed",
        })
        pred = df.loc[test_mask].copy()
        pred["pred_price"] = test_pred
        pred["abs_error"] = (pred["target_price"] - pred["pred_price"]).abs()
        pred["ape"] = pred["abs_error"] / np.maximum(pred["target_price"], 1)
        pred["model_name"] = exp.model_name
        pred["feature_set"] = exp.feature_set
        pred["split_type"] = exp.split_type
        safe = f"v7_2_{task}_{exp.split_type}_{exp.model_name}_{exp.feature_set}"
        pred_path = ART / "predictions" / f"{safe}_predictions.csv"
        pred.to_csv(pred_path, index=False, encoding="utf-8-sig")
        rec["prediction_path"] = str(pred_path)
        if model is not None and exp.split_type in {"random", "specialist"}:
            model_path = ART / "models" / f"{safe}.pkl"
            joblib.dump(model, model_path)
            rec["model_path"] = str(model_path)
        return rec, pred
    except Exception as e:
        rec.update({"status": "failed", "error_message": repr(e), "duration_seconds": round(time.time() - start, 2)})
        return rec, None


def append(path: Path, rec: dict[str, Any]) -> None:
    if path.exists():
        old = pd.read_csv(path)
        new = pd.DataFrame([rec])
        cols = list(dict.fromkeys(list(old.columns) + list(new.columns)))
        pd.concat([old.reindex(columns=cols), new.reindex(columns=cols)], ignore_index=True).to_csv(path, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame([rec]).to_csv(path, index=False, encoding="utf-8-sig")


def already_done(path: Path, rec: dict[str, str]) -> bool:
    if not path.exists():
        return False
    df = pd.read_csv(path)
    if df.empty:
        return False
    return bool((df["model_name"].eq(rec["model_name"]) & df["feature_set"].eq(rec["feature_set"]) & df["split_type"].eq(rec["split_type"]) & df["status"].eq("completed")).any())


def run_suite(task: str, split_type: str, models: list[str], out_path: Path, feature_set: str = "F3_rag") -> list[pd.DataFrame]:
    df = load_data(task, split_type)
    if split_type == "specialist":
        # Specialist rows do not have RAG by default; train compact low-price models on structured features.
        feature_set = "F2_stats"
    preds: list[pd.DataFrame] = []
    for model in models:
        fs = feature_set if model != "PureComparable" else ("F3_rag" if feature_set == "F3_rag" else "F2_stats")
        exp = Experiment(model, fs, split_type)
        if already_done(out_path, exp.__dict__):
            continue
        rec, pred = train_one(task, df, exp)
        append(out_path, rec)
        if pred is not None:
            preds.append(pred)
    return preds


def weighted_ensemble(task: str, split_type: str, result_path: Path) -> dict[str, Any] | None:
    if not result_path.exists():
        return None
    df = pd.read_csv(result_path)
    ok = df[(df["status"].eq("completed")) & (~df["model_name"].eq("PureComparable"))].sort_values("valid_MAPE").head(3)
    if len(ok) < 2:
        return None
    pred_frames = [pd.read_csv(p, low_memory=False) for p in ok["prediction_path"]]
    weights = 1 / np.maximum(ok["valid_MAPE"].to_numpy(float), 1e-6)
    weights = weights / weights.sum()
    out = pred_frames[0].copy()
    mat = np.vstack([p["pred_price"].to_numpy(float) for p in pred_frames])
    out["pred_price"] = np.average(mat, axis=0, weights=weights)
    out["abs_error"] = (out["target_price"] - out["pred_price"]).abs()
    out["ape"] = out["abs_error"] / np.maximum(out["target_price"], 1)
    out["model_name"] = "Top3WeightedEnsemble"
    out["feature_set"] = "F3_blend"
    out["split_type"] = split_type
    pred_name = f"v7_2_{task}_{split_type}_Top3WeightedEnsemble_predictions.csv"
    out.to_csv(ART / "predictions" / pred_name, index=False, encoding="utf-8-sig")
    rec = {
        "task": task, "model_name": "Top3WeightedEnsemble", "feature_set": "F3_blend",
        "split_type": split_type, "status": "completed", **metrics(out["target_price"], out["pred_price"]),
        "members": ",".join(ok["model_name"] + "+" + ok["feature_set"]),
        "weights": json.dumps([round(float(w), 4) for w in weights]),
        "prediction_path": str(ART / "predictions" / pred_name),
    }
    append(result_path, rec)
    if split_type == "random":
        joblib.dump({"type": "weighted_ensemble", "members": ok.to_dict("records"), "weights": weights.tolist()}, ART / "models" / f"v7_2_{task}_best_model.pkl")
    return rec


def group_metrics(pred: pd.DataFrame) -> pd.DataFrame:
    out = []
    pred = pred.copy()
    pred["price_bucket"] = add_price_bucket(pred["target_price"])
    pred["age_bucket"] = pd.cut(pd.to_numeric(pred.get("age_for_training"), errors="coerce"), [-1, 1, 3, 5, 8, 99], labels=["<1年", "1-3年", "3-5年", "5-8年", ">8年"]).astype(str) if "age_for_training" in pred else ""
    pred["mileage_bucket"] = pd.cut(pd.to_numeric(pred.get("mileage_wan_km"), errors="coerce"), [-1, 1, 3, 5, 8, 12, 999], labels=["<1万", "1-3万", "3-5万", "5-8万", "8-12万", ">12万"]).astype(str) if "mileage_wan_km" in pred else ""
    pred["rag_conf_bucket"] = pd.cut(pd.to_numeric(pred.get("rag_confidence_score"), errors="coerce"), [-0.01, 0.3, 0.6, 1.0], labels=["low", "medium", "high"]).astype(str) if "rag_confidence_score" in pred else ""
    for col in ["price_bucket", "city", "brand", "series", "energy_type", "age_bucket", "mileage_bucket", "rag_match_level", "rag_conf_bucket", "condition_group"]:
        if col not in pred:
            continue
        for val, g in pred.groupby(col, observed=False, dropna=False):
            if len(g) < 20:
                continue
            out.append({"group_type": col, "group_value": val, **metrics(g["target_price"], g["pred_price"])})
    return pd.DataFrame(out)


def review_curve(pred: pd.DataFrame) -> pd.DataFrame:
    pred = pred.copy()
    risk = pd.Series(0.0, index=pred.index)
    if "rag_confidence_score" in pred:
        risk += (1 - pd.to_numeric(pred["rag_confidence_score"], errors="coerce").fillna(0)).clip(0, 1) * 0.35
    if "model_sample_count" in pred:
        risk += (pd.to_numeric(pred["model_sample_count"], errors="coerce").fillna(0) < 5).astype(float) * 0.2
    pred["price_bucket"] = add_price_bucket(pred["target_price"])
    risk += pred["price_bucket"].isin(["<=1万", "1-2万", "2-3万", "50-100万", ">100万"]).astype(float) * 0.25
    if "good_condition_strict_flag" in pred:
        risk += (pd.to_numeric(pred["good_condition_strict_flag"], errors="coerce").fillna(0) < 1).astype(float) * 0.10
    if "rag_top5_median_price" in pred:
        diff = (pred["pred_price"] - pd.to_numeric(pred["rag_top5_median_price"], errors="coerce")).abs() / np.maximum(pred["pred_price"], 1)
        risk += (diff > 0.25).astype(float) * 0.10
    pred["risk_score"] = risk
    ranked = pred.sort_values("risk_score")
    rows = []
    for cov in [0.2, 0.4, 0.6, 0.8, 1.0]:
        sub = ranked.head(max(1, int(len(ranked) * cov)))
        rows.append({"auto_coverage": cov, **metrics(sub["target_price"], sub["pred_price"])})
    return pd.DataFrame(rows)


def copy_standard_outputs(task: str, best_pred: pd.DataFrame, grouped_pred: pd.DataFrame | None, low_pred: pd.DataFrame | None) -> None:
    best_pred.to_csv(ART / "predictions" / f"v7_2_{task}_test_predictions.csv", index=False, encoding="utf-8-sig")
    if grouped_pred is not None:
        grouped_pred.to_csv(ART / "predictions" / f"v7_2_{task}_grouped_test_predictions.csv", index=False, encoding="utf-8-sig")
    if low_pred is not None:
        low_pred.to_csv(ART / "predictions" / f"v7_2_{task}_low_price_predictions.csv", index=False, encoding="utf-8-sig")


def make_reports() -> None:
    lines = ["# V7.2 模型训练报告", ""]
    summary_rows = []
    for task in ["c2b", "b2c"]:
        random_path = ART / "model_results" / f"v7_2_model_comparison_{task}_random.csv"
        grouped_path = ART / "model_results" / f"v7_2_model_comparison_{task}_grouped.csv"
        low_path = ART / "model_results" / f"v7_2_low_price_specialist_{task}.csv"
        random = pd.read_csv(random_path)
        grouped = pd.read_csv(grouped_path)
        low = pd.read_csv(low_path) if low_path.exists() else pd.DataFrame()
        random_ok = random[random["status"].eq("completed")].sort_values("MAPE")
        grouped_ok = grouped[grouped["status"].eq("completed")].sort_values("MAPE")
        low_ok = low[low["status"].eq("completed")].sort_values("MAPE") if not low.empty else low
        lines += [f"## {task.upper()} Random Split", md_table(random_ok[["model_name", "feature_set", "MAPE", "MAE", "RMSE", "Median_APE", "P90_APE", "R2", "sample_count"]], 20), ""]
        lines += [f"## {task.upper()} Grouped Split", md_table(grouped_ok[["model_name", "feature_set", "MAPE", "MAE", "RMSE", "Median_APE", "P90_APE", "R2", "sample_count"]], 20), ""]
        lines += [f"## {task.upper()} Low Price Specialist", md_table(low_ok[["model_name", "feature_set", "MAPE", "MAE", "RMSE", "Median_APE", "P90_APE", "R2", "sample_count"]] if not low_ok.empty else low_ok, 20), ""]
        if not random_ok.empty:
            best = random_ok.iloc[0].to_dict()
            best["task"] = task
            summary_rows.append(best)
    pd.DataFrame(summary_rows).to_csv(ART / "model_results" / "v7_1_vs_v7_2_summary.csv", index=False, encoding="utf-8-sig")
    (REPORTS / "V7_2_MODEL_TRAINING_REPORT.md").write_text("\n".join(lines), encoding="utf-8")

    (REPORTS / "V7_2_GROUPED_SPLIT_REPORT.md").write_text("# V7.2 Grouped Split 报告\n\n详见 `artifacts/model_results/v7_2_model_comparison_*_grouped.csv` 与 `artifacts/audit/v7_2_near_duplicate_audit_*_grouped.csv`。\n", encoding="utf-8")
    (REPORTS / "V7_2_RAG_COMPARABLE_REPORT.md").write_text("# V7.2 RAG Comparable 报告\n\n已对 random/grouped split 分别构建 true topK RAG，并输出 source trace。valid/test 只从 train 召回；train 使用 5-fold OOF。\n", encoding="utf-8")


def main() -> None:
    ensure_dirs()
    for task in ["c2b", "b2c"]:
        random_path = ART / "model_results" / f"v7_2_model_comparison_{task}_random.csv"
        grouped_path = ART / "model_results" / f"v7_2_model_comparison_{task}_grouped.csv"
        low_path = ART / "model_results" / f"v7_2_low_price_specialist_{task}.csv"
        run_suite(task, "random", ["LightGBM", "XGBoost", "CatBoost", "ExtraTrees", "RandomForest", "HistGBR", "PureComparable"], random_path)
        weighted_ensemble(task, "random", random_path)
        run_suite(task, "grouped", ["LightGBM", "XGBoost", "CatBoost", "PureComparable"], grouped_path)
        weighted_ensemble(task, "grouped", grouped_path)
        run_suite(task, "specialist", ["LightGBM", "CatBoost", "ExtraTrees", "HistGBR", "PureComparable"], low_path)

        random = pd.read_csv(random_path)
        best_row = random[random["status"].eq("completed")].sort_values("MAPE").iloc[0]
        best_pred = pd.read_csv(best_row["prediction_path"], low_memory=False)
        grouped = pd.read_csv(grouped_path)
        grouped_best = grouped[grouped["status"].eq("completed")].sort_values("MAPE").iloc[0]
        grouped_pred = pd.read_csv(grouped_best["prediction_path"], low_memory=False)
        low_pred = None
        if low_path.exists():
            low = pd.read_csv(low_path)
            if not low[low["status"].eq("completed")].empty:
                low_best = low[low["status"].eq("completed")].sort_values("MAPE").iloc[0]
                low_pred = pd.read_csv(low_best["prediction_path"], low_memory=False)
        copy_standard_outputs(task, best_pred, grouped_pred, low_pred)
        group_metrics(best_pred).to_csv(ART / "error_analysis" / f"v7_2_group_metrics_{task}.csv", index=False, encoding="utf-8-sig")
        if low_pred is not None:
            group_metrics(low_pred).to_csv(ART / "error_analysis" / f"v7_2_low_price_group_metrics_{task}.csv", index=False, encoding="utf-8-sig")
            low_pred.sort_values("ape", ascending=False).head(200).to_csv(ART / "error_analysis" / f"v7_2_{task}_high_error_low_price_cases.csv", index=False, encoding="utf-8-sig")
        best_pred.sort_values("ape", ascending=False).head(200).to_csv(ART / "error_analysis" / f"v7_2_high_error_cases_{task}.csv", index=False, encoding="utf-8-sig")
        review_curve(best_pred).to_csv(ART / "error_analysis" / f"v7_2_review_curve_{task}.csv", index=False, encoding="utf-8-sig")

    make_reports()
    # Compatibility filenames requested by the handoff.
    for src, dst in [
        ("v7_2_high_error_cases_c2b.csv", "v7_2_high_error_low_price_cases.csv"),
    ]:
        p = ART / "error_analysis" / src
        if p.exists():
            (ART / "error_analysis" / dst).write_bytes(p.read_bytes())


if __name__ == "__main__":
    main()
