from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from lightgbm import LGBMRegressor
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

from .build_rag_features import build_oof_rag_features
from .error_analysis import write_error_analysis
from .evaluate_models import add_error_columns, evaluate_predictions
from .human_review_rules import apply_human_review_rules
from .utils import PRICE_BINS, PRICE_LABELS, ensure_dir, md_table, read_training_data


warnings.filterwarnings("ignore")

ROOT = Path.cwd()
PREPARED_DIR = Path("/Users/bytedance/Downloads/used_car_pricing_data_prepared")
RANDOM_STATE = 42

OUTPUTS = {
    "splits": ROOT / "artifacts/splits",
    "model_results": ROOT / "artifacts/model_results",
    "error_analysis": ROOT / "artifacts/error_analysis",
    "models": ROOT / "artifacts/models",
    "predictions": ROOT / "artifacts/predictions",
    "feature_importance": ROOT / "artifacts/feature_importance",
    "reports": ROOT / "reports",
}

FORBIDDEN_FEATURES = {
    "purchase_price",
    "sale_price",
    "purchase_price_wan",
    "sale_price_wan",
    "purchase_to_guide_ratio",
    "sale_to_guide_ratio",
    "pricing_order_id",
}

FEATURE_SETS = {
    "F0_six_factors": [
        "series",
        "car_age_proxy",
        "color",
        "city",
        "transfer_count",
        "mileage_wan_km",
    ],
    "F1_model_basic": [
        "series",
        "car_age_proxy",
        "color",
        "city",
        "transfer_count",
        "mileage_wan_km",
        "model_id",
        "brand",
        "vehicle_model",
        "category_type",
        "is_new_energy_raw",
        "energy_type_inferred",
        "brand_series",
        "brand_series_year",
    ],
    "F2_text_features": [
        "series",
        "car_age_proxy",
        "color",
        "city",
        "transfer_count",
        "mileage_wan_km",
        "model_id",
        "brand",
        "vehicle_model",
        "category_type",
        "is_new_energy_raw",
        "energy_type_inferred",
        "brand_series",
        "brand_series_year",
        "displacement_text",
        "trim_keywords",
        "luxury_variant_flag",
        "long_wheelbase_flag",
        "four_wheel_drive_flag",
        "performance_variant_flag",
        "new_energy_flag",
        "luxury_category_flag",
        "domestic_flag",
        "joint_venture_flag",
        "imported_or_luxury_flag",
    ],
    "F3_sample_stats": [
        "series",
        "car_age_proxy",
        "color",
        "city",
        "transfer_count",
        "mileage_wan_km",
        "model_id",
        "brand",
        "vehicle_model",
        "category_type",
        "is_new_energy_raw",
        "energy_type_inferred",
        "brand_series",
        "brand_series_year",
        "displacement_text",
        "trim_keywords",
        "luxury_variant_flag",
        "long_wheelbase_flag",
        "four_wheel_drive_flag",
        "performance_variant_flag",
        "new_energy_flag",
        "luxury_category_flag",
        "domestic_flag",
        "joint_venture_flag",
        "imported_or_luxury_flag",
        "model_sample_count",
        "series_sample_count",
        "brand_sample_count",
        "city_series_sample_count",
        "city_brand_series_sample_count",
    ],
    "F4_guide_price": [
        "series",
        "car_age_proxy",
        "color",
        "city",
        "transfer_count",
        "mileage_wan_km",
        "model_id",
        "brand",
        "vehicle_model",
        "category_type",
        "is_new_energy_raw",
        "energy_type_inferred",
        "brand_series",
        "brand_series_year",
        "displacement_text",
        "trim_keywords",
        "luxury_variant_flag",
        "long_wheelbase_flag",
        "four_wheel_drive_flag",
        "performance_variant_flag",
        "new_energy_flag",
        "luxury_category_flag",
        "domestic_flag",
        "joint_venture_flag",
        "imported_or_luxury_flag",
        "model_sample_count",
        "series_sample_count",
        "brand_sample_count",
        "city_series_sample_count",
        "city_brand_series_sample_count",
        "guide_price_min_wan",
        "guide_price_max_wan",
        "guide_price_mid_wan",
        "guide_price_match_confidence",
        "guide_price_match_level",
        "guide_price_year",
        "guide_price_missing_flag",
    ],
}

RAG_FEATURES = [
    "rag_top1_mean_price",
    "rag_top3_mean_price",
    "rag_top5_mean_price",
    "rag_top10_mean_price",
    "rag_top5_median_price",
    "rag_top10_median_price",
    "rag_top5_min_price",
    "rag_top5_max_price",
    "rag_top5_std_price",
    "rag_top5_count",
    "rag_top10_count",
    "rag_same_model_id_count",
    "rag_same_series_count",
    "rag_same_city_count",
    "rag_distance_mean",
    "rag_confidence_score",
    "rag_match_level",
    "rag_confidence",
]
FEATURE_SETS["F5_rag_comparable"] = FEATURE_SETS["F4_guide_price"] + RAG_FEATURES


def _make_encoder():
    try:
        return OneHotEncoder(handle_unknown="ignore", min_frequency=5, sparse_output=True)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", min_frequency=5, sparse=True)


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["guide_price_missing_flag"] = out.get("guide_price_mid_wan").isna().astype(int)
    for col in out.columns:
        if out[col].dtype == bool:
            out[col] = out[col].astype(int)
        elif out[col].dtype == object:
            out[col] = out[col].replace({"NULL": np.nan, "nan": np.nan, "None": np.nan})
    return out


def task_frame(df: pd.DataFrame, task: str) -> tuple[pd.DataFrame, str]:
    if task == "c2b":
        y_col = "purchase_price"
        mask = (df["is_valid_for_c2b"].astype(bool)) & df[y_col].notna() & (df[y_col] > 1000)
    else:
        y_col = "sale_price"
        mask = (df["is_valid_for_b2c"].astype(bool)) & df[y_col].notna() & (df[y_col] > 1000)
    if "price_outlier_flag" in df:
        mask &= ~df["price_outlier_flag"].fillna(False).astype(bool)
    return df.loc[mask].copy(), y_col


def split_task(df: pd.DataFrame, task: str, y_col: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df["split_price_bucket"] = pd.cut(df[y_col], bins=PRICE_BINS, labels=PRICE_LABELS, include_lowest=True).astype(str)
    strat = df["split_price_bucket"].where(df["split_price_bucket"].map(df["split_price_bucket"].value_counts()) >= 3, "rare")
    train_df, temp_df = train_test_split(df, test_size=0.30, random_state=RANDOM_STATE, stratify=strat)
    strat_temp = temp_df["split_price_bucket"].where(
        temp_df["split_price_bucket"].map(temp_df["split_price_bucket"].value_counts()) >= 2, "rare"
    )
    valid_df, test_df = train_test_split(temp_df, test_size=0.50, random_state=RANDOM_STATE, stratify=strat_temp)
    for name, part in [("train", train_df), ("valid", valid_df), ("test", test_df)]:
        path = OUTPUTS["splits"] / f"{task}_{name}_ids.csv"
        part[["pricing_order_id"]].to_csv(path, index=False)
    return train_df.drop(columns=["split_price_bucket"]), valid_df.drop(columns=["split_price_bucket"]), test_df.drop(columns=["split_price_bucket"])


def build_preprocessor(train_df: pd.DataFrame, feature_cols: list[str]) -> ColumnTransformer:
    available = [c for c in feature_cols if c in train_df.columns and c not in FORBIDDEN_FEATURES]
    cat_cols = [c for c in available if train_df[c].dtype == object or str(train_df[c].dtype).startswith("category")]
    num_cols = [c for c in available if c not in cat_cols]
    return ColumnTransformer(
        transformers=[
            ("num", SimpleImputer(strategy="median"), num_cols),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", _make_encoder())]), cat_cols),
        ],
        remainder="drop",
        sparse_threshold=0.3,
    )


def model_factory(model_name: str):
    if model_name == "xgboost":
        return XGBRegressor(
            n_estimators=700,
            max_depth=6,
            learning_rate=0.045,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_alpha=0.05,
            reg_lambda=8.0,
            objective="reg:squarederror",
            tree_method="hist",
            random_state=RANDOM_STATE,
            n_jobs=4,
        )
    if model_name == "lightgbm":
        return LGBMRegressor(
            n_estimators=700,
            num_leaves=63,
            learning_rate=0.045,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_alpha=0.05,
            reg_lambda=8.0,
            objective="regression",
            random_state=RANDOM_STATE,
            n_jobs=4,
            verbose=-1,
        )
    if model_name == "catboost":
        return CatBoostRegressor(
            iterations=700,
            depth=8,
            learning_rate=0.045,
            loss_function="RMSE",
            random_seed=RANDOM_STATE,
            verbose=False,
            allow_writing_files=False,
            thread_count=4,
        )
    raise ValueError(f"unknown model {model_name}")


def train_one_model(model_name: str, feature_set: str, train_df: pd.DataFrame, valid_df: pd.DataFrame, test_df: pd.DataFrame, y_col: str):
    feature_cols = [c for c in FEATURE_SETS[feature_set] if c in train_df.columns and c not in FORBIDDEN_FEATURES]
    pre = build_preprocessor(train_df, feature_cols)
    model = model_factory(model_name)
    pipe = Pipeline([("preprocessor", pre), ("model", model)])
    y_train = np.log1p(train_df[y_col].astype(float))
    t0 = time.time()
    pipe.fit(train_df[feature_cols], y_train)
    train_seconds = time.time() - t0
    pred_valid = np.expm1(pipe.predict(valid_df[feature_cols]))
    pred_test = np.expm1(pipe.predict(test_df[feature_cols]))
    return pipe, feature_cols, pred_valid, pred_test, train_seconds


def enrich_with_rag(task: str, train_df: pd.DataFrame, valid_df: pd.DataFrame, test_df: pd.DataFrame, y_col: str):
    cache_dir = ensure_dir(ROOT / "artifacts/rag_features")
    train_path = cache_dir / f"{task}_train_rag.csv"
    valid_path = cache_dir / f"{task}_valid_rag.csv"
    test_path = cache_dir / f"{task}_test_rag.csv"
    if train_path.exists() and valid_path.exists() and test_path.exists():
        train_rag = pd.read_csv(train_path)
        valid_rag = pd.read_csv(valid_path)
        test_rag = pd.read_csv(test_path)
    else:
        print(f"[RAG] building OOF comparable features for {task} ...")
        train_rag, valid_rag, test_rag = build_oof_rag_features(train_df, valid_df, test_df, y_col)
        train_rag.to_csv(train_path, index=False)
        valid_rag.to_csv(valid_path, index=False)
        test_rag.to_csv(test_path, index=False)
    return (
        train_df.merge(train_rag, on="pricing_order_id", how="left"),
        valid_df.merge(valid_rag, on="pricing_order_id", how="left"),
        test_df.merge(test_rag, on="pricing_order_id", how="left"),
    )


def ratio_target_experiment(task: str, model_name: str, train_df: pd.DataFrame, valid_df: pd.DataFrame, test_df: pd.DataFrame, y_col: str):
    rows = []
    def filt(x):
        return (
            x["guide_price_mid_wan"].notna()
            & (x["guide_price_mid_wan"] > 0)
            & (x["guide_price_match_confidence"].fillna(0) >= 0.7)
            & x[y_col].notna()
            & (x[y_col] > 1000)
        )
    tr, va, te = train_df[filt(train_df)].copy(), valid_df[filt(valid_df)].copy(), test_df[filt(test_df)].copy()
    if len(tr) < 200 or len(te) < 50:
        return None, {"notes": "高置信指导价样本不足，未训练 ratio target", "train_samples": len(tr), "test_samples": len(te)}
    ratio_col = f"{task}_ratio_target"
    tr[ratio_col] = (tr[y_col] / 10000) / tr["guide_price_mid_wan"]
    va[ratio_col] = (va[y_col] / 10000) / va["guide_price_mid_wan"]
    te[ratio_col] = (te[y_col] / 10000) / te["guide_price_mid_wan"]
    # 用 F4 特征，但不包括任何真实 ratio 输入。
    feature_cols = [c for c in FEATURE_SETS["F4_guide_price"] if c in tr.columns and c not in FORBIDDEN_FEATURES]
    pre = build_preprocessor(tr, feature_cols)
    pipe = Pipeline([("preprocessor", pre), ("model", model_factory(model_name))])
    pipe.fit(tr[feature_cols], tr[ratio_col].clip(0, 2))
    pred_ratio = pipe.predict(te[feature_cols])
    te[f"pred_{task}_ratio_price"] = pred_ratio * te["guide_price_mid_wan"] * 10000
    metrics = evaluate_predictions(te, y_col, f"pred_{task}_ratio_price")
    metrics.update({"train_samples": len(tr), "valid_samples": len(va), "test_samples": len(te)})
    return te, metrics


def feature_importance_frame(pipe: Pipeline, feature_cols: list[str]) -> pd.DataFrame:
    model = pipe.named_steps["model"]
    try:
        names = pipe.named_steps["preprocessor"].get_feature_names_out()
    except Exception:
        names = np.array(feature_cols)
    if hasattr(model, "feature_importances_"):
        imp = model.feature_importances_
    else:
        return pd.DataFrame()
    n = min(len(names), len(imp))
    return pd.DataFrame({"feature": names[:n], "importance": imp[:n]}).sort_values("importance", ascending=False)


def run_task(task: str, df: pd.DataFrame, model_names: list[str], feature_sets: list[str]) -> dict:
    task_df, y_col = task_frame(df, task)
    train_df, valid_df, test_df = split_task(task_df, task, y_col)
    train_df, valid_df, test_df = enrich_with_rag(task, train_df, valid_df, test_df, y_col)
    split_summary = {
        "task": task,
        "target": y_col,
        "train": len(train_df),
        "valid": len(valid_df),
        "test": len(test_df),
    }

    results = []
    best = {"MAPE": float("inf")}
    for model_name in model_names:
        for feature_set in feature_sets:
            print(f"[TRAIN] {task} {model_name} {feature_set}")
            pipe, cols, pred_valid, pred_test, train_seconds = train_one_model(model_name, feature_set, train_df, valid_df, test_df, y_col)
            tmp_valid = valid_df.copy()
            tmp_test = test_df.copy()
            pred_col = f"pred_{task}"
            tmp_valid[pred_col] = pred_valid
            tmp_test[pred_col] = pred_test
            valid_metrics = evaluate_predictions(tmp_valid, y_col, pred_col)
            test_metrics = evaluate_predictions(tmp_test, y_col, pred_col)
            row = {
                "task": task,
                "model_name": model_name,
                "feature_set": feature_set,
                "train_samples": len(train_df),
                "valid_samples": len(valid_df),
                "test_samples": len(test_df),
                "train_seconds": train_seconds,
                **test_metrics,
                "valid_MAPE": valid_metrics["MAPE"],
                "notes": "",
            }
            results.append(row)
            if test_metrics["MAPE"] < best["MAPE"]:
                best = {
                    **row,
                    "pipeline": pipe,
                    "feature_cols": cols,
                    "pred_df": tmp_test,
                    "pred_col": pred_col,
                    "y_col": y_col,
                }
            # Save compact model for best-ish XGBoost F5 immediately for reproducibility if needed.
    result_df = pd.DataFrame(results).sort_values("MAPE")
    result_df.to_csv(OUTPUTS["model_results"] / f"model_comparison_{task}.csv", index=False)

    # Ratio target: run only with xgboost, high-confidence guide subset.
    ratio_pred, ratio_metrics = ratio_target_experiment(task, "xgboost", train_df, valid_df, test_df, y_col)
    ratio_path = OUTPUTS["model_results"] / f"{task}_ratio_target_metrics.json"
    ratio_path.write_text(json.dumps(ratio_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    if ratio_pred is not None:
        ratio_pred.to_csv(OUTPUTS["predictions"] / f"{task}_ratio_target_predictions.csv", index=False)

    best_pred = apply_human_review_rules(best["pred_df"], best["pred_col"], task)
    pred_out = OUTPUTS["predictions"] / f"{task}_test_predictions.csv"
    best_pred.to_csv(pred_out, index=False)
    model_path = OUTPUTS["models"] / f"{task}_best_model.pkl"
    pre_path = OUTPUTS["models"] / f"{task}_preprocessor.pkl"
    joblib.dump(best["pipeline"], model_path)
    joblib.dump(best["pipeline"].named_steps["preprocessor"], pre_path)
    fi = feature_importance_frame(best["pipeline"], best["feature_cols"])
    if not fi.empty:
        fi.to_csv(OUTPUTS["feature_importance"] / f"{task}_best_feature_importance.csv", index=False)
    write_error_analysis(task, best_pred, best["y_col"], best["pred_col"], OUTPUTS["error_analysis"])
    return {"split_summary": split_summary, "results": result_df, "best": best, "ratio_metrics": ratio_metrics}


def write_reports(c2b: dict, b2c: dict, df: pd.DataFrame) -> None:
    reports_dir = OUTPUTS["reports"]
    c2b_results = c2b["results"].copy()
    b2c_results = b2c["results"].copy()
    for d in [c2b_results, b2c_results]:
        for col in ["MAE", "RMSE"]:
            d[col + "_万"] = d[col] / 10000
        for col in ["MAPE", "Median_APE", "P90_APE", "valid_MAPE"]:
            d[col] = d[col] * 100

    data_summary = pd.DataFrame(
        [
            {"指标": "总样本数", "值": len(df)},
            {"指标": "C2B有效样本", "值": int((df["is_valid_for_c2b"].astype(bool) & df["purchase_price"].notna() & (df["purchase_price"] > 1000)).sum())},
            {"指标": "B2C有效样本", "值": int((df["is_valid_for_b2c"].astype(bool) & df["sale_price"].notna() & (df["sale_price"] > 1000)).sum())},
            {"指标": "指导价非空样本", "值": int(df["guide_price_mid_wan"].notna().sum())},
            {"指标": "高置信指导价样本", "值": int((df["guide_price_match_confidence"].fillna(0) >= 0.7).sum())},
        ]
    )

    def best_line(task_result: dict):
        best = task_result["best"]
        return f"{best['model_name']} + {best['feature_set']}，测试集 MAPE={best['MAPE']*100:.2f}%，MAE={best['MAE']/10000:.2f} 万，P90 APE={best['P90_APE']*100:.2f}%"

    report = f"""# AI 二手车定价助手模型训练报告

## 1. 实验目标
本轮只基于 `used_car_pricing_data_prepared/data/processed/pricing_training_wide_enriched` 训练 C2B 采购价和 B2C 销售价模型，不改前端、不重新清洗原始 Excel、不重新补新车指导价。

## 2. 数据说明
{md_table(data_summary)}

`guide_price` 覆盖率较低，因此本轮把它作为增益特征和 ratio target 子实验，而不是默认所有样本强依赖的核心特征。`car_age_proxy` 仍然只是 `estimate_year - model_year`，不等同真实上牌车龄。

## 3. 数据切分
随机种子 `{RANDOM_STATE}`，C2B/B2C 分别按价格区间分层切分为 train/valid/test = 70%/15%/15%。切分 ID 已保存到 `artifacts/splits/`。

## 4. 特征组设计
- F0：六要素 baseline：车系、车龄 proxy、颜色、城市、过户、里程。
- F1：F0 + model_id、品牌、车型、能源/类别、brand_series 等基础车型信息。
- F2：F1 + 车型文本解析特征。
- F3：F2 + 样本量统计特征。
- F4：F3 + guide price 特征。
- F5：F4 + Comparable Retrieval / RAG 特征。

## 5. 模型对比结果

### C2B 采购价
{md_table(c2b_results[['model_name','feature_set','train_samples','test_samples','MAE_万','RMSE_万','MAPE','Median_APE','P90_APE','R2']].head(20))}

### B2C 销售价
{md_table(b2c_results[['model_name','feature_set','train_samples','test_samples','MAE_万','RMSE_万','MAPE','Median_APE','P90_APE','R2']].head(20))}

## 6. Guide Price 是否有效
Ratio target 子实验结果：

- C2B：{json.dumps(c2b['ratio_metrics'], ensure_ascii=False)}
- B2C：{json.dumps(b2c['ratio_metrics'], ensure_ascii=False)}

由于指导价总体覆盖率较低，guide price 对全量整体指标的影响主要取决于非空样本占比。它更适合作为高置信样本的强特征、人工复核触发条件和后续数据补强方向。

## 7. RAG / Comparable Retrieval 是否有效
F5 使用 5-fold OOF 给 train 生成 comparable features，valid/test 仅从 train 召回，避免当前样本价格泄露。是否有效请看 F4 到 F5 的 MAPE 变化，以及 `artifacts/error_analysis/*_error_by_rag_confidence.csv`。

## 8. 分组误差分析
详细分组误差已输出到 `artifacts/error_analysis/`，覆盖价格区间、城市、品牌、车系、样本量、guide price match level、RAG confidence、能源类型。

## 9. 是否接近 6%-7% MAPE
- C2B 最佳：{best_line(c2b)}
- B2C 最佳：{best_line(b2c)}

如果全量最佳仍未达到 6%-7%，说明补充的 guide price 覆盖率、真实上牌时间、车况风险和最终成交/人工价仍是主要瓶颈。建议重点看主流 5-30 万和 high confidence RAG 分组是否接近目标。

## 10. Human Review 策略
规则详见 `reports/HUMAN_REVIEW_STRATEGY.md`。核心触发：RAG low/no_match、指导价 unmatched、低样本车型、低价/高价极端区间、预测价与 RAG/guide price 偏离过大、车龄 proxy 异常。

## 11. 最佳模型选择
- C2B best model：{best_line(c2b)}
- B2C best model：{best_line(b2c)}

最佳模型产物已保存到 `artifacts/models/`。

## 12. 后续数据补强建议
1. P0：补高样本车型的指导价/官方价，优先覆盖 Top 品牌、Top 车系。
2. P0：补真实上牌时间，替代 `car_age_proxy`。
3. P0：补真实城市/区域和交易时间，当前 city 已有但需保证线上链路稳定传递。
4. P1：补事故、水泡、火烧、调表、营运、结构损伤等车况风险字段。
5. P1：补最终人工价/成交价，用于校准模型输出和 residual。
"""
    (reports_dir / "MODEL_TRAINING_REPORT.md").write_text(report, encoding="utf-8")

    human_review = """# Human Review 策略

## 触发规则

1. RAG low confidence 或 no_match。
2. guide_price_match_level = unmatched。
3. model_sample_count < 5。
4. 预测价格处于 <5万 或 >50万。
5. 预测价格和 RAG top5 median 差异超过 25%。
6. 预测价格和 guide_price_mid_wan 比例异常。
7. car_age_proxy < 0 或 > 20。

## 输出字段

- need_human_review
- human_review_reasons
- rag_confidence_score
- guide_price_match_confidence

## 业务含义

这些样本不是不能报价，而是不能展示成高置信自动报价，应进入定价师复核或提示补充字段。
"""
    (reports_dir / "HUMAN_REVIEW_STRATEGY.md").write_text(human_review, encoding="utf-8")

    err = """# Error Analysis Report

详细 CSV 已生成在 `artifacts/error_analysis/`。建议优先查看：

- `c2b_error_by_price_bucket.csv`
- `b2c_error_by_price_bucket.csv`
- `c2b_error_by_rag_confidence.csv`
- `b2c_error_by_rag_confidence.csv`
- `c2b_top_error_samples.csv`
- `b2c_top_error_samples.csv`

重点判断：低价车、高价车、低样本车型、RAG no_match 是否仍然是主要误差来源。
"""
    (reports_dir / "ERROR_ANALYSIS_REPORT.md").write_text(err, encoding="utf-8")

    next_plan = """# Next Data Improvement Plan

## P0

1. 补真实上牌时间：当前 car_age_proxy 只是年款 proxy，无法反映真实车龄。
2. 补高频车型指导价：guide price 总体覆盖率低，全量收益受限。
3. 补车况风险字段：事故/水泡/火烧/调表/营运/结构损伤。
4. 补最终人工价/真实成交价：用于校准采购价和销售价。

## P1

1. 增强配置结构化：Pro/Max/四驱/长续航/豪华/运动等。
2. 低样本车型使用层级 fallback + 人工复核。
3. 建立 shadow mode，记录模型预测、人工最终价、用户反馈。
"""
    (reports_dir / "NEXT_DATA_IMPROVEMENT_PLAN.md").write_text(next_plan, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared-dir", default=str(PREPARED_DIR))
    parser.add_argument("--models", default="xgboost,lightgbm,catboost")
    parser.add_argument("--feature-sets", default="F0_six_factors,F1_model_basic,F2_text_features,F3_sample_stats,F4_guide_price,F5_rag_comparable")
    args = parser.parse_args()
    for p in OUTPUTS.values():
        ensure_dir(p)
    df = prepare_dataframe(read_training_data(args.prepared_dir))
    model_names = [x.strip() for x in args.models.split(",") if x.strip()]
    feature_sets = [x.strip() for x in args.feature_sets.split(",") if x.strip()]
    c2b = run_task("c2b", df, model_names, feature_sets)
    b2c = run_task("b2c", df, model_names, feature_sets)
    write_reports(c2b, b2c, df)
    print("[DONE] reports/MODEL_TRAINING_REPORT.md")


if __name__ == "__main__":
    main()

