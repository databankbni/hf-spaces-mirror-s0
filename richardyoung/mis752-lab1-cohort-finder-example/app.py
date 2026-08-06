# MIS 752 Lab 1 -- Cohort Finder (the easier artifact).
#
# A privacy-safe patient search: the filters query the vault, but what the user
# ever SEES is the de-identified (released) view. Pure pandas + Gradio -- no GPU,
# no API keys, no LLM. Runs unchanged in Google Colab and on a free HuggingFace
# Space (CPU basic). Loads lab1_cohort.csv, which is fully synthetic (Synthea)
# data, so it is safe to ship publicly.
import os

import pandas as pd
import gradio as gr

CSV = "lab1_cohort.csv"
GREEN, AMBER = "#12b76a", "#f79009"


def banner(text, color):
    return ("<div style='background:%s;color:white;padding:12px 16px;border-radius:10px;"
            "font-size:16px;font-weight:700'>%s</div>" % (color, text))


def load_cohort(path=CSV):
    if not os.path.exists(path):
        raise FileNotFoundError(
            path + " not found. In Colab: run the Export cell first. "
            "In a Space: upload lab1_cohort.csv next to app.py.")
    df = pd.read_csv(path)
    # de-identify at load: the finder only ever DISPLAYS the released view
    lo = (df["age"] // 10) * 10
    df["AGE_BAND"] = lo.astype(str) + "-" + (lo + 9).astype(str)
    df["ZIP3"] = df["zip"].astype(str).str.replace("[^0-9]", "", regex=True).str.zfill(5).str[:3]
    return df


def build_app(df):
    df = df.reset_index(drop=True)
    show_cols = ["AGE_BAND", "gender", "race", "ZIP3", "n_conditions",
                 "n_encounters", "total_billed"]

    def search(gender, min_age, min_cond, zip3):
        # the query runs on the vault (exact age); the RESULTS show only the released view
        mask = (df["age"] >= int(min_age)) & (df["n_conditions"] >= int(min_cond))
        if gender != "Any":
            mask &= df["gender"].astype(str).str.upper().str.startswith(gender)
        zip3 = (zip3 or "").strip()
        if zip3:
            mask &= df["ZIP3"].str.startswith(zip3[:3])
        hits = df.loc[mask]
        tail = ""
        if "the_patient" in hits and bool(hits["the_patient"].any()):
            tail = " - includes your representative patient"
        msg = banner("%d matching patients (de-identified view)%s" % (len(hits), tail),
                     GREEN if len(hits) else AMBER)
        table = hits[show_cols].head(50).rename(columns={"gender": "GENDER", "race": "RACE"})
        return msg, table

    with gr.Blocks(title="MIS 752 Cohort Finder") as demo:
        gr.Markdown("# Cohort Finder\n**MIS 752 Lab 1** - ask for a cohort, get back only "
                    "de-identified records. All data is synthetic (Synthea).")
        with gr.Row():
            gender = gr.Dropdown(["Any", "F", "M"], value="Any", label="Gender")
            min_age = gr.Slider(0, 100, value=65, step=1, label="Minimum age")
            min_cond = gr.Slider(0, 15, value=1, step=1, label="Minimum number of conditions")
            zip3 = gr.Textbox(placeholder="e.g. 891", label="ZIP prefix (optional)")
        out_banner = gr.HTML()
        out_table = gr.Dataframe(label="Matching patients (first 50)", interactive=False)
        for c in (gender, min_age, min_cond, zip3):
            c.change(search, [gender, min_age, min_cond, zip3], [out_banner, out_table])
        demo.load(search, [gender, min_age, min_cond, zip3], [out_banner, out_table])
    return demo


if __name__ == "__main__":
    demo = build_app(load_cohort())
    demo.launch()
