import glob
import json
import os
from typing import List, Optional

import numpy as np
import pandas as pd


BASIC_METRICS = [
    "Image Quality",
    "Aesthetic Quality",
    "JEPA Similarity",
    "Dynamic Degree",
    "Flow Score",
    "Motion Smoothness",
    "Subject Consistency",
    "Background Consistency",
    "Photometric Consistency",
    "Interaction Quality",
    "Trajectory Accuracy",
    "Depth Accuracy",
    "Perspectivity",
    "Instruction Following",
    "Semantic Alignment",
]

DIMENSION_MAP = {
    "Visual Quality": ["Image Quality", "Aesthetic Quality", "JEPA Similarity"],
    "Motion Quality": ["Dynamic Degree", "Flow Score", "Motion Smoothness"],
    "Content Consistency": [
        "Subject Consistency",
        "Background Consistency",
        "Photometric Consistency",
    ],
    "Physics Adherence": ["Interaction Quality", "Trajectory Accuracy"],
    "3D Accuracy": ["Depth Accuracy", "Perspectivity"],
    "Controllability": [
        "Instruction Following",
        "Semantic Alignment",
    ],
}

ALL_METRICS = BASIC_METRICS + list(DIMENSION_MAP) + ["EWMScore"]
DIMENSION_METRICS = list(DIMENSION_MAP)
METRIC_CHOICES = sorted(ALL_METRICS)

TASK_AGGREGATES = {
    "Data Engine": "Data Engine(",
    "Action Planner": "Action Planner(",
    "RL Environment": "RL Environment(",
    "Visuo-Tactile Success Rate": "Visuo-Tactile(",
    "Real Action Planner": "Real Action Planner(",
}


class DataLoader:
    def __init__(self, results_dir: str = "./worldarena-results"):
        self.results_dir = results_dir
        self.df_all: Optional[pd.DataFrame] = None
        self.BASIC_METRICS = BASIC_METRICS
        self.DIMENSION_MAP = DIMENSION_MAP
        self.DIMENSION_METRICS = DIMENSION_METRICS
        self.ALL_METRICS = ALL_METRICS
        self.METRIC_CHOICES = METRIC_CHOICES

    def load_results(self) -> pd.DataFrame:
        rows = []
        file_patterns = ("*.json", "*.xlsx", "*.csv")
        all_files = [
            path
            for pattern in file_patterns
            for path in sorted(glob.glob(os.path.join(self.results_dir, pattern)))
        ]

        for file_path in all_files:
            model_name = os.path.splitext(os.path.basename(file_path))[0]
            if file_path.endswith(".json"):
                row = self._load_json_file(file_path, model_name)
            else:
                row = self._load_table_file(file_path, model_name)
            if row:
                rows.append(row)

        df = pd.DataFrame(rows)
        return self._process_data(df) if not df.empty else df

    def _load_json_file(self, file_path: str, model_name: str) -> dict:
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            row = {
                "Model": data.get("Model", model_name),
                "open_source": data.get(
                    "open source", data.get("open_source", "unknown")
                ),
                "year": data.get("year", data.get("date", "unknown")),
            }

            def extract_values(data_dict, prefix=""):
                for key, value in data_dict.items():
                    metric_name = f"{prefix}{key}" if prefix else key
                    if isinstance(value, dict):
                        extract_values(value, f"{metric_name}_")
                    elif isinstance(value, (int, float)):
                        row[metric_name] = value

            extract_values(data.get("Metrics", {}))
            return row
        except Exception as exc:
            print(f"Error loading JSON file {file_path}: {exc}")
            return {}

    def _load_table_file(self, file_path: str, model_name: str) -> dict:
        try:
            if file_path.endswith(".xlsx"):
                table = pd.read_excel(file_path)
            else:
                table = pd.read_csv(file_path)

            row = {"Model": model_name, "open_source": "unknown", "year": "unknown"}
            for metadata_key in ("open source", "open_source"):
                if metadata_key in table.columns:
                    row["open_source"] = table[metadata_key].iloc[0]
                    break
            for metadata_key in ("year", "date"):
                if metadata_key in table.columns:
                    row["year"] = table[metadata_key].iloc[0]
                    break

            aliases = {
                metric: [
                    metric,
                    metric.lower().replace(" ", "_"),
                    metric.replace(" ", "_"),
                ]
                for metric in BASIC_METRICS
            }
            aliases["Image Quality"].append("imaging_quality")
            aliases["JEPA Similarity"].append("JEPA_normalized")

            for metric, candidates in aliases.items():
                matching = next(
                    (candidate for candidate in candidates if candidate in table.columns),
                    None,
                )
                row[metric] = (
                    round(table[matching].mean(), 4) if matching else np.nan
                )
            return row
        except Exception as exc:
            print(f"Error loading table file {file_path}: {exc}")
            return {}

    @staticmethod
    def _normalize_metadata(df: pd.DataFrame) -> pd.DataFrame:
        if "open_source" in df.columns:
            source_map = {
                "yes": "Open-source",
                "open-source": "Open-source",
                "opensource": "Open-source",
                "true": "Open-source",
                "1": "Open-source",
                "no": "Closed-source",
                "closed-source": "Closed-source",
                "closedsource": "Closed-source",
                "false": "Closed-source",
                "0": "Closed-source",
            }
            df["open_source"] = (
                df["open_source"].astype(str).str.lower().map(source_map).fillna(
                    df["open_source"].astype(str).str.lower()
                )
            )
        if "year" in df.columns:
            df["year"] = df["year"].astype(str).str.extract(r"(\d{4})")[0]
        return df

    @staticmethod
    def _to_percentage(series: pd.Series) -> pd.Series:
        values = pd.to_numeric(series, errors="coerce")
        valid = values.dropna()
        if not valid.empty and valid.min() >= 0 and valid.max() <= 1:
            values = values * 100
        values = values.mask(values < 0, 0)
        return values.round(2)

    def _process_task_success_data(self, df: pd.DataFrame) -> pd.DataFrame:
        aggregate_columns = {}
        task_cols = []
        for aggregate_name, prefix in TASK_AGGREGATES.items():
            matching_cols = [
                column for column in df.columns if column.startswith(prefix)
            ]
            if matching_cols:
                aggregate_columns[aggregate_name] = matching_cols
                task_cols.extend(matching_cols)

        for column in task_cols:
            df[column] = self._to_percentage(df[column])

        for aggregate_name, columns in aggregate_columns.items():
            df[aggregate_name] = df[columns].mean(axis=1, skipna=True).round(2)

        aggregate_cols = list(aggregate_columns)
        df["EWMScore"] = df[aggregate_cols].mean(axis=1, skipna=True).round(2)
        df = self._normalize_metadata(df).dropna(subset=["EWMScore"])

        meta_cols = ["Model", "open_source", "year"]
        return df[meta_cols + aggregate_cols + ["EWMScore"] + task_cols]

    def _process_policy_evaluator_data(self, df: pd.DataFrame) -> pd.DataFrame:
        df["Policy Evaluator"] = self._to_percentage(df["Policy Evaluator"])
        df = self._normalize_metadata(df).dropna(subset=["Policy Evaluator"])
        return df[["Model", "open_source", "year", "Policy Evaluator"]]

    def _process_video_quality_data(self, df: pd.DataFrame) -> pd.DataFrame:
        for metric in BASIC_METRICS:
            if metric not in df.columns:
                df[metric] = np.nan
            else:
                df[metric] = self._to_percentage(df[metric])

        for dimension, sub_metrics in DIMENSION_MAP.items():
            df[dimension] = df[sub_metrics].mean(axis=1, skipna=True).round(2)

        df["EWMScore"] = df[BASIC_METRICS].mean(axis=1, skipna=True).round(2)
        df = self._normalize_metadata(df)
        df = df.dropna(subset=["EWMScore"])
        meta_cols = ["Model", "open_source", "year"]
        metric_cols = BASIC_METRICS + list(DIMENSION_MAP) + ["EWMScore"]
        return df[meta_cols + metric_cols]

    def _process_data(self, df: pd.DataFrame) -> pd.DataFrame:
        metric_cols = [
            column
            for column in df.columns
            if column not in ["Model", "open_source", "year"]
        ]
        if any(
            column.startswith(prefix)
            for column in metric_cols
            for prefix in TASK_AGGREGATES.values()
        ):
            return self._process_task_success_data(df)
        if "Policy Evaluator" in metric_cols and not any(
            metric in metric_cols for metric in BASIC_METRICS
        ):
            return self._process_policy_evaluator_data(df)
        return self._process_video_quality_data(df)

    def reload_data(self) -> str:
        self.df_all = self.load_results()
        if self.df_all is None or self.df_all.empty:
            return (
                f"No JSON or table files found in {self.results_dir}. "
                "Please upload some results."
            )
        return f"Loaded {len(self.df_all)} models from {self.results_dir}"

    def get_open_source_choices(self) -> List[str]:
        if self.df_all is None or "open_source" not in self.df_all.columns:
            return ["All"]
        choices = sorted(
            str(value)
            for value in self.df_all["open_source"].dropna().unique()
            if value != ""
        )
        return ["All"] + choices

    def get_year_choices(self) -> List[str]:
        if self.df_all is None or "year" not in self.df_all.columns:
            return ["All"]
        years = sorted(
            (
                str(value)
                for value in self.df_all["year"].dropna().unique()
                if value != ""
            ),
            reverse=True,
        )
        return ["All"] + years
