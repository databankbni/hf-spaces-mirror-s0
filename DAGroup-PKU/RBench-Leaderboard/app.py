import gradio as gr
import pandas as pd
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
GPT_LEADERBOARD_PATH = BASE_DIR / "leaderboard.json"
QWEN_LEADERBOARD_PATH = BASE_DIR / "leaderboard_qwen.json"

EVALUATORS = ["GPT", "Qwen"]


# =========================
# Model Groups
# =========================

GROUPS = {
    "Open-source": [
        "Kandinsky-WM-1.0",
        "LingBot-Video",
        "Cosmos3-Nano",
        "Cosmos3-Super",
        "Cosmos 2.5",
        "Wan2.2_A14B",
        "HunyuanVideo 1.5",
        "LongCat-Video",
        "Wan2.1_14B",
        "LTX-2",
        "Wan2.2_5B",
        "SkyReels",
        "LTX-Video",
        "FramePack",
        "HunyuanVideo",
        "CogVideoX_5B",
    ],
    "Commercial": [
        "Wan 2.6",
        "Seedance 1.5 pro",
        "Wan 2.5",
        "Hailuo v2",
        "Veo 3",
        "Seedance 1.0",
        "Kling 2.6 pro",
        "Sora v2 Pro#",
        "Sora v1",
    ],
    "Robotics-specific": [
        "DreamGen(gr1)",
        "DreamGen(droid)",
        "Vidar",
        "UnifoLM-WMA-0",
    ],
}

GROUP_ALIASES = {
    "All": None,
    "Open Source": "Open-source",
    "Commercial": "Commercial",
    "Robotics-specific": "Robotics-specific",
}


# =========================
# Columns
# =========================

TASK_COLUMNS = [
    "Common Manipulation",
    "Long-horizon Planning",
    "Multi-entity Collaboration",
    "Spatial Relationship",
    "Visual Reasoning",
]

ROBOT_COLUMNS = [
    "Single Arm",
    "Dual Arm",
    "Quadruped Robot",
    "Humanoid Robot",
]

SORT_COLUMNS = (
    ["avg"] +
    TASK_COLUMNS +
    ROBOT_COLUMNS
)

REQUIRED_COLUMNS = ["model", "avg"] + TASK_COLUMNS + ROBOT_COLUMNS


# =========================
# Table Display Config
# =========================

COLUMN_WIDTHS = [
    260,  # MODELS
    90,   # RANK
    90,   # AVG.
    190,
    190,
    220,
    190,
    170,
    130,
    120,
    170,
    150,
]


# =========================
# Table Functions
# =========================

def add_rank(df):
    """
    Add RANK based on avg within the current displayed dataframe.

    For All:
        rank is computed over all models.

    For a specific model group:
        rank is computed only within that group.
    """
    df = df.copy()

    df["RANK"] = (
        df["avg"]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    cols = list(df.columns)

    if "RANK" in cols:
        cols.remove("RANK")

    if "model" in cols:
        model_idx = cols.index("model")
        cols.insert(model_idx + 1, "RANK")
    else:
        cols.insert(0, "RANK")

    return df[cols]


def filter_by_group(df, group_name):
    """
    Filter models by selected group.
    """
    group_key = GROUP_ALIASES.get(group_name, None)

    if group_key is None:
        return df

    model_list = GROUPS.get(group_key, [])
    df = df[df["model"].isin(model_list)].copy()

    return df


def load_table(sort_by="avg", group_name="All", evaluator="GPT"):
    if evaluator == "Qwen":
        df = pd.read_json(QWEN_LEADERBOARD_PATH)
    else:
        df = pd.read_json(GPT_LEADERBOARD_PATH)

    # 1. Filter by selected group first
    #    This makes RANK group-specific when group_name is not All.
    df = filter_by_group(df, group_name)

    # 2. Add rank after filtering
    #    All: global rank
    #    Open Source / Commercial / Robotics-specific: rank inside that group
    df = add_rank(df)

    # 3. Sort
    if sort_by not in df.columns:
        sort_by = "avg"

    df = df.sort_values(by=sort_by, ascending=False)

    return df


def reorder_columns(df, highlight_col):
    """
    Move highlight_col to the position after avg.
    """
    cols = list(df.columns)

    if highlight_col not in cols or highlight_col == "avg":
        return df

    cols.remove(highlight_col)

    if "avg" in cols:
        avg_idx = cols.index("avg")
        cols.insert(avg_idx + 1, highlight_col)
    else:
        cols.insert(0, highlight_col)

    return df[cols]


def rename_display_columns(df):
    """
    Rename columns only for display.
    Do not change leaderboard.json field names.
    """
    return df.rename(
        columns={
            "model": "MODELS",
            "avg": "AVG.",
        }
    )


def get_display_highlight_col(sort_by):
    """
    Map internal sort column name to display column name.
    """
    if sort_by == "avg":
        return "AVG."
    if sort_by == "model":
        return "MODELS"
    return sort_by


def highlight_column(df, col_name):
    """
    Format numeric columns and highlight selected metric column.
    """
    numeric_cols = df.select_dtypes(include=["float", "float64", "int"]).columns
    float_cols = [col for col in numeric_cols if col != "RANK"]

    format_dict = {col: "{:.3f}" for col in float_cols}

    if "RANK" in df.columns:
        format_dict["RANK"] = "{:d}"

    styler = df.style.format(format_dict)

    # Do not use set_table_styles for column width here.
    # gr.DataFrame may override pandas Styler table width.
    # Keep Styler only for highlighting.
    if col_name in df.columns:
        styler = styler.apply(
            lambda x: [
                "background-color: #E8F5E9" if x.name == col_name else ""
                for _ in x
            ],
            axis=0,
        )

    return styler


def update_leaderboard_table(evaluator, group_name, sort_by):
    df = load_table(
        sort_by=sort_by,
        group_name=group_name,
        evaluator=evaluator,
    )
    df = reorder_columns(df, sort_by)

    df = rename_display_columns(df)

    display_highlight_col = get_display_highlight_col(sort_by)
    styled_df = highlight_column(df, display_highlight_col)

    return styled_df


# =========================
# Submission
# =========================

def submit_json(file_obj):
    if file_obj is None:
        return {"error": "Please upload a JSON file."}

    try:
        with open(file_obj.name, "r") as f:
            data = json.load(f)
    except Exception as e:
        return {"error": f"Invalid JSON file: {e}"}

    if not isinstance(data, list):
        return {"error": "JSON must be a list of model results."}

    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            return {"error": f"Entry {i} is not a JSON object."}

        missing = [k for k in REQUIRED_COLUMNS if k not in entry]
        if missing:
            return {"error": f"Entry {i} missing fields: {missing}"}

    try:
        df_old = pd.read_json(GPT_LEADERBOARD_PATH)
    except Exception:
        df_old = pd.DataFrame(columns=REQUIRED_COLUMNS)

    df_new = pd.DataFrame(data)

    df_merged = (
        pd.concat([df_old, df_new])
        .drop_duplicates(subset="model", keep="last")
        .reset_index(drop=True)
    )

    df_merged.to_json(GPT_LEADERBOARD_PATH, orient="records", indent=2)

    return {
        "status": "success",
        "num_models_added": len(df_new),
        "models": df_new["model"].tolist(),
    }


# =========================
# Gradio App
# =========================

with gr.Blocks() as demo:

    gr.Markdown(
        """
        # RBench Leaderboard 🏆
        
        Welcome to the **RBench Leaderboard**, a benchmark designed for evaluating **robot-oriented image-to-video (I2V) generation models**.
        
        RBench evaluates model performance across **four robot embodiments** and **five task categories**, covering a wide range of embodied interaction scenarios.  
        The benchmark is built upon a curated test set of **650 image–text pairs**, each specifying a target robotic behavior conditioned on both visual and textual inputs.
        
        By jointly assessing task-level correctness and visual quality under diverse robotic settings, RBench provides a standardized and reproducible protocol for comparing I2V models in embodied intelligence research.
        
        ---
        """
    )

    gr.Markdown(
        """
        **Links:**  
        [GitHub](https://github.com/DAGroup-PKU/ReVidgen/) |
        [Arxiv](https://arxiv.org/abs/2601.15282) |
        [Home Page](https://dagroup-pku.github.io/ReVidgen.github.io/) |
        [RBench](https://huggingface.co/datasets/DAGroup-PKU/RBench/) |
        [RoVid-X](https://huggingface.co/datasets/DAGroup-PKU/RoVid-X/) |
        [RBench-Leaderboard](https://huggingface.co/spaces/DAGroup-PKU/RBench-Leaderboard/)
        """
    )

    gr.Markdown(
        """
        📊 **This leaderboard reports the performance of image-to-video models evaluated on RBench across four robot embodiments and five task categories.**
        """
    )

    with gr.Tab("Leaderboard"):

        with gr.Row():
            evaluator = gr.Dropdown(
                choices=EVALUATORS,
                value="GPT",
                label="Evaluator",
            )

            group_filter = gr.Dropdown(
                choices=list(GROUP_ALIASES.keys()),
                value="All",
                label="Model Group (Open Source, Commercial, Robotics-specific)",
            )

            sort_col = gr.Dropdown(
                choices=SORT_COLUMNS,
                value="avg",
                label="Sort by (Higher is Better)",
            )

        init_df = load_table(sort_by="avg", group_name="All", evaluator="GPT")
        init_df = reorder_columns(init_df, "avg")
        init_df = rename_display_columns(init_df)
        init_styled = highlight_column(init_df, "AVG.")

        table = gr.DataFrame(
            value=init_styled,
            interactive=False,
            wrap=False,
            label="Model Performance",
            column_widths=COLUMN_WIDTHS,
        )

        evaluator.change(
            fn=update_leaderboard_table,
            inputs=[evaluator, group_filter, sort_col],
            outputs=table,
        )

        group_filter.change(
            fn=update_leaderboard_table,
            inputs=[evaluator, group_filter, sort_col],
            outputs=table,
        )

        sort_col.change(
            fn=update_leaderboard_table,
            inputs=[evaluator, group_filter, sort_col],
            outputs=table,
        )

    with gr.Tab("Submit Your Model"):
        gr.Markdown(
            """
            ### Submit Evaluation Results

            This section is currently under construction.
            """
        )


demo.launch(ssr_mode=False)
