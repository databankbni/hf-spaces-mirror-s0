from typing import Callable, List, Optional, Tuple

import gradio as gr
import matplotlib.pyplot as plt
import pandas as pd

from src.data_loader import DataLoader
from src.leaderboard import Leaderboard
from src.plotter import Plotter
from src.radar_plotter import RadarPlotter
from src.styling import dataframe_to_html, get_academic_css
from src.utils import clean_metric_names, get_metric_choices

plt.switch_backend("Agg")


DEFAULT_METRIC = "EWMScore"


def build_track_tab(
    results_dir: str,
    metric_choices: Optional[List[str]] = None,
    enable_radar: bool = True,
    metric_display_map: Optional[dict] = None,
    description: Optional[str] = None,
) -> Tuple[Callable, list]:
    """Build one leaderboard tab and return its loader callback and outputs."""
    data_loader = DataLoader(results_dir=results_dir)
    leaderboard = Leaderboard(data_loader)
    plotter = Plotter(data_loader)
    radar_plotter = RadarPlotter(data_loader)

    metric_choices = metric_choices or get_metric_choices()
    metric_display_map = metric_display_map or {}
    display_to_internal = {
        display_name: internal_name
        for internal_name, display_name in metric_display_map.items()
    }
    display_metric_choices = [
        metric_display_map.get(metric, metric) for metric in metric_choices
    ]
    default_internal_metric = metric_choices[0] if metric_choices else DEFAULT_METRIC
    default_display_metric = (
        display_metric_choices[0] if display_metric_choices else DEFAULT_METRIC
    )

    if description:
        gr.Markdown(description)

    def to_internal_metric(metric_name: str) -> str:
        return display_to_internal.get(metric_name, metric_name)

    def to_internal_metrics(metric_names: List[str]) -> List[str]:
        return [to_internal_metric(metric_name) for metric_name in metric_names]

    def build_radar_df(table_df: pd.DataFrame) -> pd.DataFrame:
        displayed_models = table_df["Model"].tolist() if not table_df.empty else []
        if not displayed_models or data_loader.df_all is None:
            return pd.DataFrame()
        return data_loader.df_all[
            data_loader.df_all["Model"].isin(displayed_models)
        ].copy()

    def reload_data():
        message = data_loader.reload_data()
        if data_loader.df_all is None or data_loader.df_all.empty:
            placeholder = (
                "<div class='placeholder'>No data available. "
                "Please add result files.</div>"
            )
            base_returns = (
                message,
                gr.update(choices=["All"], value="All", interactive=True),
                gr.update(choices=["All"], value="All", interactive=True),
                placeholder,
            )
            if enable_radar:
                figure, axis = plt.subplots(figsize=(6, 3))
                axis.text(0.5, 0.5, message, ha="center", va="center")
                axis.axis("off")
                return base_returns + (figure,)
            return base_returns

        selected_metrics = [
            metric for metric in metric_choices if metric != default_internal_metric
        ]
        table_df = leaderboard.update_leaderboard(
            metric=default_internal_metric,
            top_k=100,
            model_filter="",
            open_source_filter="All",
            year_filter="All",
            sort_mode="Auto",
            selected_metrics=selected_metrics,
        )
        base_returns = (
            message,
            gr.update(
                choices=data_loader.get_open_source_choices(),
                value="All",
                interactive=True,
            ),
            gr.update(
                choices=data_loader.get_year_choices(),
                value="All",
                interactive=True,
            ),
            dataframe_to_html(table_df, column_label_map=metric_display_map),
        )
        if enable_radar:
            return base_returns + (
                radar_plotter.create_radar_chart(build_radar_df(table_df)),
            )
        return base_returns

    def update_leaderboard_wrapper(
        metric,
        top_k,
        model_filter,
        open_source_filter,
        year_filter,
        sort_mode,
        selected_metrics,
    ):
        clean_metric = to_internal_metric(clean_metric_names([metric])[0])
        clean_selected_metrics = to_internal_metrics(
            clean_metric_names(selected_metrics)
        )
        table_df = leaderboard.update_leaderboard(
            clean_metric,
            top_k,
            model_filter,
            open_source_filter,
            year_filter,
            sort_mode,
            clean_selected_metrics,
        )
        html = dataframe_to_html(table_df, column_label_map=metric_display_map)
        if enable_radar:
            return html, radar_plotter.create_radar_chart(
                build_radar_df(table_df)
            )
        return html

    def create_comparison_plot_wrapper(
        model_filter,
        open_source_filter,
        year_filter,
        selected_plot_metric,
        plot_sort_mode,
    ):
        display_metric = clean_metric_names([selected_plot_metric])[0]
        return plotter.create_comparison_plot(
            model_filter,
            open_source_filter,
            year_filter,
            to_internal_metric(display_metric),
            plot_sort_mode,
            display_metric_name=display_metric,
        )

    status_box = gr.Markdown("Loading results...")
    with gr.Row():
        with gr.Column(scale=2):
            metric_dropdown = gr.Dropdown(
                label="Primary Ranking Metric",
                choices=display_metric_choices,
                value=default_display_metric,
                interactive=True,
            )
        with gr.Column(scale=1):
            sort_mode_radio = gr.Radio(
                label="Sort Order",
                choices=[
                    "Auto",
                    "Ascending (low to high)",
                    "Descending (high to low)",
                ],
                value="Auto",
                interactive=True,
            )
            topk_slider = gr.Slider(
                label="Display Top-K Models",
                minimum=3,
                maximum=100,
                value=min(40, max(3, len(metric_choices) * 10)),
                step=1,
                interactive=True,
            )

    metrics_select = gr.CheckboxGroup(
        label="Additional Metrics to Display",
        choices=[
            metric
            for metric in display_metric_choices
            if metric != default_display_metric
        ],
        value=[
            metric
            for metric in display_metric_choices
            if metric != default_display_metric
        ],
        interactive=True,
    )

    with gr.Row():
        model_filter_box = gr.Textbox(
            label="Filter by Model Name",
            placeholder="Enter a partial model name",
            interactive=True,
        )
        open_source_dropdown = gr.Dropdown(
            label="Filter by Open Source",
            choices=["All"],
            value="All",
            interactive=True,
        )
        year_dropdown = gr.Dropdown(
            label="Filter by Year",
            choices=["All"],
            value="All",
            interactive=True,
        )

    with gr.Row():
        reload_button = gr.Button("Reload Data", variant="secondary", size="sm")
        update_button = gr.Button(
            "Update Leaderboard", variant="primary", size="sm"
        )

    leaderboard_html = gr.HTML(
        value="<div class='placeholder'>Leaderboard will appear here.</div>"
    )
    radar_plot = (
        gr.Plot(label="Dimension Radar Chart", format="png")
        if enable_radar
        else None
    )

    with gr.Row():
        with gr.Column(scale=2):
            plot_metric_radio = gr.Radio(
                label="Metric for Comparison Plot",
                choices=display_metric_choices,
                value=default_display_metric,
                interactive=True,
            )
        with gr.Column(scale=1):
            plot_sort_radio = gr.Radio(
                label="Plot Sort Order",
                choices=[
                    "Ascending (low to high)",
                    "Descending (high to low)",
                ],
                value="Descending (high to low)",
                interactive=True,
            )
            plot_update_button = gr.Button(
                "Generate Comparison Plot", variant="primary", size="sm"
            )

    comparison_plot = gr.Plot(
        label="Model Comparison Visualization", format="png"
    )
    outputs = [
        status_box,
        open_source_dropdown,
        year_dropdown,
        leaderboard_html,
    ] + ([radar_plot] if enable_radar else [])

    reload_button.click(fn=reload_data, inputs=[], outputs=outputs)
    update_button.click(
        fn=update_leaderboard_wrapper,
        inputs=[
            metric_dropdown,
            topk_slider,
            model_filter_box,
            open_source_dropdown,
            year_dropdown,
            sort_mode_radio,
            metrics_select,
        ],
        outputs=[leaderboard_html] + ([radar_plot] if enable_radar else []),
    )
    plot_update_button.click(
        fn=create_comparison_plot_wrapper,
        inputs=[
            model_filter_box,
            open_source_dropdown,
            year_dropdown,
            plot_metric_radio,
            plot_sort_radio,
        ],
        outputs=[comparison_plot],
    )
    return reload_data, outputs


with gr.Blocks(css=get_academic_css()) as demo:
    gr.HTML(
        """
        <section class="wa-hero">
          <div class="wa-kicker">WORLD MODEL BENCHMARK</div>
          <h1>WorldArena 2.0</h1>
          <p>Extending Embodied World Model Benchmarking on Modality, Functionality and Platform</p>
          <div class="wa-axis">
            <span class="wa-purple">Modality</span>
            <span class="wa-green">Functionality</span>
            <span class="wa-blue">Platform</span>
          </div>
        </section>
        <section class="wa-intro">
          <strong>WorldArena 2.0 Leaderboard</strong> evaluates embodied world
          models across simulator video quality, interactive RL environments,
          visuo-tactile manipulation, and real-robot action planning.
        </section>
        """
    )

    with gr.Tabs():
        with gr.Tab("Track 1 - Simulator Video Quality"):
            track1_reload, track1_outputs = build_track_tab(
                "./worldarena-results(track1)",
                metric_display_map={
                    "EWMScore": "EWMScore-P (Difficulty/OOD Adjusted)"
                },
                description=(
                    "**Track 1:** Simulator video-quality evaluation using the "
                    "WorldArena perceptual metrics, including the benchmark's "
                    "difficulty and out-of-distribution corrections."
                ),
            )

        with gr.Tab("Track 2 - World Model as RL Environment"):
            track2_reload, track2_outputs = build_track_tab(
                "./worldarena-results(track2)",
                metric_choices=[
                    "RL Environment",
                    "RL Environment(Click Bell)",
                    "RL Environment(Adjust Bottle)",
                ],
                enable_radar=False,
                description=(
                    "**Track 2:** Success rates of policies trained inside each "
                    "world-model environment on Click Bell and Adjust Bottle. "
                    "The paper's proxy-based reward results are used."
                ),
            )

        with gr.Tab("Track 3 - Real Robot"):
            with gr.Tabs():
                with gr.Tab("Track 3.1 - WAM + VT-WAM"):
                    track31_reload, track31_outputs = build_track_tab(
                        "./worldarena-results(track3.1)",
                        metric_choices=[
                            "Visuo-Tactile Success Rate",
                            "Visuo-Tactile(Insert HDMI)",
                            "Visuo-Tactile(Lift Bottle)",
                        ],
                        enable_radar=False,
                        description=(
                            "**Track 3.1:** Visuo-tactile evaluation on the "
                            "UniVTAC simulator using Insert HDMI and Lift Bottle."
                        ),
                    )
                with gr.Tab("Track 3.2 - Real Action Planner"):
                    track32_reload, track32_outputs = build_track_tab(
                        "./worldarena-results(track3.2)",
                        metric_choices=[
                            "Real Action Planner",
                            "Real Action Planner(Wipe Table)",
                            "Real Action Planner(Pour Water)",
                        ],
                        enable_radar=False,
                        description=(
                            "**Track 3.2:** Real-robot action-planning success "
                            "rates on Wipe Table and Pour Water."
                        ),
                    )

    demo.load(fn=track1_reload, inputs=[], outputs=track1_outputs)
    demo.load(fn=track2_reload, inputs=[], outputs=track2_outputs)
    demo.load(fn=track31_reload, inputs=[], outputs=track31_outputs)
    demo.load(fn=track32_reload, inputs=[], outputs=track32_outputs)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
