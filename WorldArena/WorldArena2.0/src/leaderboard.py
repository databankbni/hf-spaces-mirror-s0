from typing import Dict, List, Literal, Optional

import pandas as pd


class Leaderboard:
    def __init__(self, data_loader):
        self.data_loader = data_loader
        self.metric_better: Dict[str, Literal["min", "max"]] = {
            metric: "max" for metric in self.data_loader.BASIC_METRICS
        }
        for dimension in self.data_loader.DIMENSION_MAP:
            self.metric_better[dimension] = "max"
        self.metric_better["EWMScore"] = "max"
        self.dimension_metrics = list(self.data_loader.DIMENSION_MAP)

    def update_leaderboard(
        self,
        metric: str,
        top_k: int,
        model_filter: str,
        open_source_filter: str,
        year_filter: str,
        sort_mode: str,
        selected_metrics: Optional[List[str]],
    ) -> pd.DataFrame:
        if self.data_loader.df_all is None:
            return pd.DataFrame()
        df = self.data_loader.df_all.copy()
        if df.empty:
            return pd.DataFrame()

        if model_filter and model_filter.strip():
            df = df[
                df["Model"].str.contains(model_filter, case=False, na=False)
            ]
        if open_source_filter and open_source_filter != "All":
            df = df[df["open_source"] == open_source_filter]
        if year_filter and year_filter != "All":
            df = df[df["year"] == year_filter]
        if metric not in df.columns:
            return pd.DataFrame()

        if sort_mode == "Auto":
            ascending = self.metric_better.get(metric, "max") == "min"
        else:
            ascending = sort_mode.startswith("Ascending")

        df_sorted = (
            df.dropna(subset=[metric])
            .sort_values(metric, ascending=ascending)
            .copy()
        )
        df_sorted["Rank"] = range(1, len(df_sorted) + 1)
        df_top = df_sorted.head(top_k).copy()

        selected_metrics = selected_metrics or []
        fixed_cols = ["Model", metric, "Rank"]
        columns = fixed_cols + [
            selected
            for selected in selected_metrics
            if selected not in fixed_cols and selected in df_top.columns
        ]
        table_df = df_top[columns].copy()
        for column in table_df.columns:
            if column != "Model":
                table_df[column] = table_df[column].apply(
                    lambda value: f"{value:.2f}"
                    if pd.notna(value)
                    else "N/A"
                )
        return self._add_styling_to_dataframe(table_df)

    @staticmethod
    def _add_styling_to_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        styled_df = df.copy()
        numeric_cols = [
            column for column in df.columns if column not in ["Model", "Rank"]
        ]
        for column in numeric_cols:
            numeric_values = pd.to_numeric(df[column], errors="coerce")
            valid_values = numeric_values.dropna()
            if valid_values.empty:
                continue
            max_idx = valid_values.idxmax()
            styled_df.loc[max_idx, column] = f"**{df.loc[max_idx, column]}**"
            if len(valid_values) >= 2:
                second_idx = valid_values.nlargest(2).index[-1]
                styled_df.loc[second_idx, column] = (
                    f"<u>{df.loc[second_idx, column]}</u>"
                )

        if "Rank" in styled_df.columns:
            styled_df["Rank"] = styled_df["Rank"].apply(
                lambda value: str(int(float(value)))
                if value != "N/A" and not pd.isna(value)
                else "N/A"
            )
        return styled_df
