from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def write_ablation_report(report: dict[str, Any], output_dir: str | Path = "results/evals") -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "selection_strategy_ablation_report.json"
    md_path = out_dir / "selection_strategy_ablation_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# AI懂车价选品模块策略对照回测")
    lines.append("")
    lines.append(f"- 生成时间：{report.get('generated_at') or datetime.now().isoformat()}")
    lines.append(f"- 业务数据：{report.get('data_sources', {}).get('business_90d_csv', '')}")
    lines.append(f"- 政策/新车事件：{report.get('data_sources', {}).get('policy_new_car_xlsx', '')}")
    lines.append(f"- 排行榜信号：{report.get('data_sources', {}).get('ranking_signals_csv', '')}")
    lines.append("")
    lines.append("## 结论")
    final = report.get("final_recommendation") or {}
    lines.append(f"- 建议 P0 策略：**{final.get('strategy_name')}**")
    lines.append(f"- 综合分：{final.get('strategy_score')}")
    lines.append(f"- 使用信号：{', '.join(final.get('used_signals') or [])}")
    lines.append(f"- 原因：{final.get('reason')}")
    for warning in final.get("warnings") or []:
        lines.append(f"- 风险提示：{warning}")
    optional = report.get("optional_best_strategy") or {}
    if optional:
        lines.append(
            f"- 可选观测最优：{optional.get('strategy_name')}，综合分 {optional.get('strategy_score')}。"
            "若高于 P0 推荐，说明新增弱信号更适合解释层而非主决策层。"
        )
    lines.append("")
    lines.append("## 为什么不能只看均值")
    lines.append(
        "只看平均利润、平均成交周期和转化率会鼓励系统只挑极少数最稳车源。"
        "例如全量 100 台总利润 100 万、均利 1 万；策略只选 10 台均利 2 万，"
        "总利润也只有 20 万。均值翻倍并不代表业务更好，所以本报告同时看选中率、"
        "总利润、利润保留率和单位处理效率。"
    )
    lines.append("")
    lines.append("## Baseline")
    baseline = report.get("baseline_all") or {}
    for key in (
        "baseline_candidate_count",
        "baseline_acquired_count",
        "baseline_sold_count",
        "baseline_total_profit",
        "baseline_avg_profit",
        "baseline_avg_days_to_sell",
        "baseline_acquisition_conversion_rate",
        "baseline_sales_conversion_rate",
    ):
        lines.append(f"- {key}: {baseline.get(key)}")
    lines.append("")
    lines.append("## 策略对比")
    lines.append(
        "| 策略 | 信号 | 选中率 | 总利润 | 利润保留率 | 均利 | 成交周期 | 实际收车转化率(90d) | 上架售出率(45d) | 综合分 | 推荐硬指标 | 规模约束 |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")
    for item in report.get("strategy_results") or []:
        if item.get("strategy_name") == "baseline_all":
            continue
        metrics = item.get("metrics") or {}
        lines.append(
            "| {name} | {signals} | {selection_rate} | {total_profit} | {retention} | {avg_profit} | {days} | {acq} | {sale} | {score} | {hard} | {scale} |".format(
                name=item.get("strategy_name"),
                signals=",".join(item.get("used_signals") or []),
                selection_rate=metrics.get("selection_rate"),
                total_profit=metrics.get("selected_total_profit"),
                retention=metrics.get("profit_retention_rate"),
                avg_profit=metrics.get("avg_profit"),
                days=metrics.get("avg_days_to_sell"),
                acq=metrics.get("acquisition_conversion_rate"),
                sale=metrics.get("sales_conversion_rate"),
                score=item.get("strategy_score"),
                hard="PASS" if item.get("recommend_pass", {}).get("all_pass") else "FAIL",
                scale="PASS" if item.get("scale_pass", {}).get("all_pass") else "FAIL",
            )
        )
    lines.append("")
    lines.append("## 避免组")
    lines.append("| 策略 | 避免率 | 候选数 | 均利 | 成交周期 | 实际收车转化率(90d) | 上架售出率(45d) | 四项指标 | 覆盖约束 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|---|")
    for item in report.get("strategy_results") or []:
        if item.get("strategy_name") == "baseline_all":
            continue
        metrics = item.get("avoid_metrics") or {}
        lines.append(
            "| {name} | {avoid_rate} | {count} | {avg_profit} | {days} | {acq} | {sale} | {hard} | {scale} |".format(
                name=item.get("strategy_name"),
                avoid_rate=metrics.get("avoid_rate"),
                count=metrics.get("avoid_candidate_count"),
                avg_profit=metrics.get("avg_profit"),
                days=metrics.get("avg_days_to_sell"),
                acq=metrics.get("acquisition_conversion_rate"),
                sale=metrics.get("sales_conversion_rate"),
                hard="PASS" if item.get("avoid_pass", {}).get("all_pass") else "FAIL",
                scale="PASS" if item.get("avoid_scale_pass", {}).get("all_pass") else "FAIL",
            )
        )
    lines.append("避免组按独立策略风险分选取；四项全反向交集只作为命中率审计参照，不参与替代策略排序。")
    lines.append("")
    lines.append("## DSI / 排行榜增益")
    for key in ("dsi_increment", "ranking_increment"):
        inc = report.get(key) or {}
        lines.append(
            f"- {key}: 分数增量 {inc.get('strategy_score_delta')}, "
            f"均利增量 {inc.get('avg_profit_delta')}, "
            f"利润保留增量 {inc.get('profit_retention_delta')}, "
            f"是否正增益 {inc.get('is_positive')}"
        )
    lines.append("")
    lines.append("## Top-K 同容量评估")
    lines.append("无原始人工排序基线，本轮按 prompt 允许口径使用全量 baseline 均值做同容量参照。")
    for item in report.get("strategy_results") or []:
        if item.get("strategy_name") == "baseline_all":
            continue
        lines.append(f"### {item.get('strategy_name')}")
        for name, metrics in (item.get("topk_evaluation") or {}).items():
            lines.append(
                f"- {name}: total_profit={metrics.get('total_profit')}, "
                f"avg_profit={metrics.get('avg_profit')}, "
                f"acq={metrics.get('acquisition_conversion_rate')}, "
                f"sale={metrics.get('sales_conversion_rate')}, "
                f"days={metrics.get('avg_days_to_sell')}"
            )
    lines.append("")
    lines.append("## 错误分析")
    for title, rows in (report.get("error_analysis") or {}).items():
        lines.append(f"### {title}")
        if not rows:
            lines.append("- 暂无明显样本。")
            continue
        for row in rows[:10]:
            lines.append(
                f"- {row.get('city')} {row.get('brand')} {row.get('series')}: "
                f"均利={row.get('avg_profit')}, 周期={row.get('avg_days_to_sell')}, "
                f"选中数={row.get('candidate_count')}, 售出={row.get('sold_count')}"
            )
    return "\n".join(lines) + "\n"
