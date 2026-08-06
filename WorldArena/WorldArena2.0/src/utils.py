from typing import List

from .data_loader import DIMENSION_METRICS, METRIC_CHOICES


def get_metric_choices() -> List[str]:
    basic_metrics = [
        metric
        for metric in METRIC_CHOICES
        if metric not in DIMENSION_METRICS and metric != "EWMScore"
    ]
    dimension_order = [
        "Visual Quality",
        "Motion Quality",
        "Content Consistency",
        "Physics Adherence",
        "3D Accuracy",
        "Controllability",
    ]
    dimension_choices = [
        f"[Dimension] {dimension}"
        for dimension in dimension_order
        if dimension in DIMENSION_METRICS
    ]
    return ["EWMScore"] + dimension_choices + sorted(basic_metrics)


def clean_metric_names(metrics: List[str]) -> List[str]:
    return [metric.replace("[Dimension] ", "") for metric in metrics]
