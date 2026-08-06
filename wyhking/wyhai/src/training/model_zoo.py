from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelSpec:
    name: str
    family: str
    phase1: bool = True
    phase2: bool = False
    heavy: bool = False
    skipped_reason: str | None = None


def candidate_specs() -> list[ModelSpec]:
    return [
        ModelSpec("LightGBM_L2", "lightgbm", True, True),
        ModelSpec("LightGBM_L1", "lightgbm", True, True),
        ModelSpec("XGBoost_squarederror", "xgboost", True, True),
        ModelSpec("XGBoost_absoluteerror", "xgboost", True, False),
        ModelSpec("CatBoost_RMSE", "catboost", True, True),
        ModelSpec("CatBoost_MAE", "catboost", True, False),
        ModelSpec("Sklearn_HistGBR", "histgbr", True, True),
        ModelSpec("Sklearn_HistGBR_absolute_error", "histgbr", True, False),
        ModelSpec("RandomForest", "sklearn_tree", True, False),
        ModelSpec("ExtraTrees", "sklearn_tree", True, False),
        ModelSpec("Ridge", "linear", True, False),
        ModelSpec("ElasticNet", "linear", True, False),
        ModelSpec("Huber", "linear", True, False),
        ModelSpec("KNNRegressor", "knn", True, False),
        ModelSpec("PureComparable_top5_median", "pure_rag", True, False),
        ModelSpec("AutoGluon_Tabular_300s", "autogluon", False, False, True, "Phase 1 默认跳过：AutoGluon 已安装但训练耗时高，待 GBDT/树模型筛完后单独限时跑。"),
        ModelSpec("Torch_MLP_Embedding", "neural", False, False, True, "Phase 1 默认跳过：需要单独 GPU/多 seed 预算，本轮先做传统强基线。"),
        ModelSpec("WideDeep", "neural", False, False, True, "Phase 1 默认跳过：需要单独 GPU/多 seed 预算，本轮先做传统强基线。"),
        ModelSpec("TabPFNRegressor", "tabpfn", False, False, True, "Phase 1 默认跳过：TabPFN 对大样本/高基数字段成本高，仅保留为后续抽样 challenger。"),
        ModelSpec("H2O_AutoML", "h2o", False, False, True, "依赖未安装，按要求不自动安装大型依赖。"),
        ModelSpec("FLAML", "flaml", False, False, True, "依赖未安装，按要求不自动安装大型依赖。"),
        ModelSpec("NGBoost", "ngboost", False, False, True, "依赖未安装；区间能力本轮优先用 LightGBM quantile / conformal。"),
    ]


def make_estimator(name: str, phase: str = "phase1", random_state: int = 42) -> Any:
    if name.startswith("LightGBM"):
        from lightgbm import LGBMRegressor
        objective = "regression_l1" if name.endswith("_L1") else "regression"
        n_estimators = 900 if phase == "phase1" else 1800
        return LGBMRegressor(
            objective=objective,
            n_estimators=n_estimators,
            learning_rate=0.045,
            num_leaves=63,
            min_child_samples=50,
            subsample=0.88,
            colsample_bytree=0.86,
            reg_alpha=0.1,
            reg_lambda=8.0,
            random_state=random_state,
            n_jobs=-1,
            verbose=-1,
        )
    if name.startswith("XGBoost"):
        from xgboost import XGBRegressor
        objective = "reg:absoluteerror" if "absoluteerror" in name else "reg:squarederror"
        n_estimators = 900 if phase == "phase1" else 1800
        return XGBRegressor(
            objective=objective,
            n_estimators=n_estimators,
            learning_rate=0.045,
            max_depth=7,
            min_child_weight=5,
            subsample=0.88,
            colsample_bytree=0.86,
            reg_alpha=0.1,
            reg_lambda=8.0,
            tree_method="hist",
            random_state=random_state,
            n_jobs=-1,
        )
    if name.startswith("CatBoost"):
        from catboost import CatBoostRegressor
        loss = "MAE" if name.endswith("_MAE") else "RMSE"
        iterations = 800 if phase == "phase1" else 1600
        return CatBoostRegressor(
            loss_function=loss,
            iterations=iterations,
            learning_rate=0.05,
            depth=8,
            l2_leaf_reg=10,
            random_seed=random_state,
            verbose=False,
            allow_writing_files=False,
        )
    if name.startswith("Sklearn_HistGBR"):
        from sklearn.ensemble import HistGradientBoostingRegressor
        loss = "absolute_error" if "absolute" in name else "squared_error"
        return HistGradientBoostingRegressor(
            loss=loss,
            learning_rate=0.06,
            max_iter=550 if phase == "phase1" else 900,
            max_leaf_nodes=63,
            l2_regularization=0.1,
            early_stopping=True,
            random_state=random_state,
        )
    if name == "RandomForest":
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(
            n_estimators=180 if phase == "phase1" else 360,
            min_samples_leaf=3,
            max_features=0.8,
            random_state=random_state,
            n_jobs=-1,
        )
    if name == "ExtraTrees":
        from sklearn.ensemble import ExtraTreesRegressor
        return ExtraTreesRegressor(
            n_estimators=220 if phase == "phase1" else 420,
            min_samples_leaf=2,
            max_features=0.85,
            random_state=random_state,
            n_jobs=-1,
        )
    if name == "Ridge":
        from sklearn.linear_model import Ridge
        return Ridge(alpha=5.0, random_state=random_state)
    if name == "ElasticNet":
        from sklearn.linear_model import ElasticNet
        return ElasticNet(alpha=0.001, l1_ratio=0.15, random_state=random_state, max_iter=5000)
    if name == "Huber":
        from sklearn.linear_model import HuberRegressor
        return HuberRegressor(epsilon=1.35, alpha=0.0001, max_iter=300)
    if name == "KNNRegressor":
        from sklearn.neighbors import KNeighborsRegressor
        return KNeighborsRegressor(n_neighbors=20, weights="distance", n_jobs=-1)
    raise KeyError(f"未实现模型: {name}")

