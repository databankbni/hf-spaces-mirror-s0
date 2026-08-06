import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from scipy.stats import kruskal
import scikit_posthocs as sp
from calculations import DF

LAYOUT = dict(paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
              margin=dict(l=40, r=40, t=60, b=40),
              font=dict(family="Inter, sans-serif", size=12, color="#1e293b"))

GRID = dict(showgrid=True, gridwidth=1, gridcolor="#f1f5f9",
            title_font=dict(color="#334155"), tickfont=dict(color="#64748b"))

def plot_growth_centiles(param, patient_val, patient_ga):
    labels = {"hc1":"Head Circumference (cm)","bpd1":"Biparietal Diameter (cm)",
               "ofd1":"OFD (cm)","ac1":"Abdominal Circumference (cm)","fc1":"Femur Length (cm)"}
    ylabel = labels.get(param, param)
    tmp = DF.copy()
    tmp["ga_wk"] = tmp["Gold_Standard_GA"].round().astype(int)
    tmp = tmp[(tmp["ga_wk"]>=18)&(tmp["ga_wk"]<=38)]
    grp = tmp.groupby("ga_wk")[param].agg(
        p10=lambda x: np.percentile(x,10),
        p50=lambda x: np.percentile(x,50),
        p90=lambda x: np.percentile(x,90)).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=grp["ga_wk"], y=grp["p90"], name="90th %ile",
        line=dict(color="#5eead4", width=1.5, dash="dash"), fill=None))
    fig.add_trace(go.Scatter(x=grp["ga_wk"], y=grp["p10"], name="10th %ile",
        line=dict(color="#5eead4", width=1.5, dash="dash"),
        fill="tonexty", fillcolor="rgba(94,234,212,0.08)"))
    fig.add_trace(go.Scatter(x=grp["ga_wk"], y=grp["p50"], name="Cohort Median",
        line=dict(color="#0d9488", width=2.5)))
    if float(patient_val)>0 and float(patient_ga)>0:
        fig.add_trace(go.Scatter(x=[float(patient_ga)], y=[float(patient_val)],
            mode="markers", name="This Patient",
            marker=dict(color="#ef4444", size=13, line=dict(color="white",width=2))))
    fig.update_layout(title=f"Indian Cohort Growth Centiles — {ylabel}", **LAYOUT,
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right"))
    fig.update_xaxes(title="Gestational Age (weeks)", range=[18,38], **GRID)
    fig.update_yaxes(title=ylabel, **GRID)
    return fig

def plot_violin(sub_df):
    long = sub_df[["Error_GA2","Error_Hadlock","Error_INTERGROWTH"]].rename(
        columns={"Error_GA2":"Garbhini GA-2","Error_Hadlock":"Hadlock",
                 "Error_INTERGROWTH":"INTERGROWTH-21st"}
    ).melt(var_name="Model", value_name="Error (weeks)")
    colors = {"Garbhini GA-2":"#0d9488","Hadlock":"#64748b","INTERGROWTH-21st":"#6366f1"}
    fig = px.violin(long, x="Model", y="Error (weeks)", color="Model",
        box=True, points=False, color_discrete_map=colors,
        title=f"GA Estimation Error Distribution (n={len(sub_df)})")
    fig.add_hline(y=0, line_dash="dash", line_color="#ef4444", line_width=1.5)
    # Median dots
    for i, m in enumerate(["Garbhini GA-2","Hadlock","INTERGROWTH-21st"]):
        med = long[long["Model"]==m]["Error (weeks)"].median()
        fig.add_trace(go.Scatter(x=[m], y=[med], mode="markers",
            marker=dict(color="#ef4444", size=10, line=dict(color="white",width=1.5)),
            showlegend=False, name=f"{m} median"))
    fig.update_layout(**LAYOUT, showlegend=False)
    fig.update_yaxes(**GRID)
    return fig

def plot_corr_heatmap(sub_df):
    bio = ["hc1","bpd1","ofd1","ac1","fc1"]
    mat = ["thyroid_preg","anemia","hypertension","prediab_diab","sga"]
    corr = sub_df[bio+mat].corr().loc[bio, mat]
    fig = px.imshow(corr, color_continuous_scale="RdBu", range_color=[-0.4,0.4],
        x=["Thyroid","Anemia","Hypertension","Diabetes","SGA"],
        y=["HC","BPD","OFD","AC","FL"],
        title="Fetal Biometry ↔ Maternal Risk Correlations", zmin=-0.4, zmax=0.4)
    fig.update_layout(**LAYOUT)
    return fig

def plot_sga_box(sub_df):
    tmp = sub_df.copy()
    tmp["SGA Status"] = tmp["sga"].map({0:"Normal",1:"SGA Fetus"})
    fig = px.box(tmp, x="SGA Status", y="hc1", color="SGA Status",
        color_discrete_map={"Normal":"#0d9488","SGA Fetus":"#ef4444"},
        title="Head Circumference: SGA vs Normal Fetus",
        labels={"hc1":"Head Circumference (cm)"})
    fig.update_layout(**LAYOUT, showlegend=False)
    fig.update_yaxes(**GRID)
    return fig

def plot_outlier_scatter(flagged_df, pattern=""):
    """Pattern-specific scatter: each anomaly gets its clinically relevant axes."""
    fig = go.Figure()

    if "Microcephaly" in pattern:
        # HC vs Gold Standard GA — shows how HC falls short for gestational age
        fig.add_trace(go.Scatter(
            x=DF["Gold_Standard_GA"], y=DF["hc1"], mode="markers",
            marker=dict(color="rgba(100,116,139,0.18)", size=5), name="Cohort"))
        if len(flagged_df) > 0:
            fig.add_trace(go.Scatter(
                x=flagged_df["Gold_Standard_GA"], y=flagged_df["hc1"], mode="markers",
                marker=dict(color="#ef4444", size=12, line=dict(color="white", width=1.5)),
                name="Flagged: HC < 22 cm"))
        # Reference line at HC = 22 cm
        fig.add_hline(y=22, line_dash="dash", line_color="#ef4444", line_width=1.5,
                      annotation_text="Microcephaly threshold (22 cm)",
                      annotation_position="top left")
        fig.update_layout(title="Head Circumference vs Gestational Age — Microcephaly Pattern",
                          **LAYOUT, legend=dict(orientation="h", y=1.02))
        fig.update_xaxes(title="Gestational Age (weeks)", **GRID)
        fig.update_yaxes(title="Head Circumference (cm)", **GRID)

    elif "IUGR" in pattern:
        # HC vs AC — the defining ratio for asymmetric IUGR
        fig.add_trace(go.Scatter(
            x=DF["ac1"], y=DF["hc1"], mode="markers",
            marker=dict(color="rgba(100,116,139,0.18)", size=5), name="Cohort"))
        if len(flagged_df) > 0:
            fig.add_trace(go.Scatter(
                x=flagged_df["ac1"], y=flagged_df["hc1"], mode="markers",
                marker=dict(color="#f97316", size=12, line=dict(color="white", width=1.5)),
                name="Flagged: HC/AC > 1.25"))
        # Diagonal reference line for HC/AC = 1.25
        ac_range = np.linspace(DF["ac1"].min(), DF["ac1"].max(), 100)
        fig.add_trace(go.Scatter(
            x=ac_range, y=ac_range * 1.25, mode="lines",
            line=dict(color="#f97316", dash="dash", width=1.5),
            name="HC/AC = 1.25 threshold"))
        fig.update_layout(title="HC vs AC Space — Asymmetric IUGR Pattern",
                          **LAYOUT, legend=dict(orientation="h", y=1.02))
        fig.update_xaxes(title="Abdominal Circumference (cm)", **GRID)
        fig.update_yaxes(title="Head Circumference (cm)", **GRID)

    else:
        # Femur Outlier — HC vs FL is the clinically relevant space
        fig.add_trace(go.Scatter(
            x=DF["hc1"], y=DF["fc1"], mode="markers",
            marker=dict(color="rgba(100,116,139,0.18)", size=5), name="Cohort"))
        if len(flagged_df) > 0:
            fig.add_trace(go.Scatter(
                x=flagged_df["hc1"], y=flagged_df["fc1"], mode="markers",
                marker=dict(color="#ef4444", size=12, line=dict(color="white", width=1.5)),
                name="Flagged Outliers"))
        # Threshold lines
        fig.add_hline(y=7.23, line_dash="dash", line_color="#ef4444", line_width=1.5,
                      annotation_text="99th pct (7.23 cm)", annotation_position="top left")
        fig.add_hline(y=4.50, line_dash="dash", line_color="#f97316", line_width=1.5,
                      annotation_text="Short femur threshold (4.5 cm)", annotation_position="bottom right")
        fig.update_layout(title="HC vs FL Space — Femur Length Outlier Map",
                          **LAYOUT, legend=dict(orientation="h", y=1.02))
        fig.update_xaxes(title="Head Circumference (cm)", **GRID)
        fig.update_yaxes(title="Femur Length (cm)", **GRID)

    return fig

def run_stats(sub_df):
    cols = ["Error_INTERGROWTH","Error_Hadlock","Error_GA2"]
    groups = [sub_df[c].dropna() for c in cols]
    try:
        H, p = kruskal(*groups)
        # Optimize performance: Sub-sample to 400 rows if cohort is too large.
        # This keeps rank-sum test mathematically stable and fast, avoiding blocking the main event loop.
        stats_df = sub_df
        if len(sub_df) > 400:
            stats_df = sub_df.sample(400, random_state=42)
            
        long = stats_df[cols].rename(columns={
            "Error_GA2":"Garbhini GA-2","Error_Hadlock":"Hadlock",
            "Error_INTERGROWTH":"INTERGROWTH-21st"
        }).melt(var_name="Model", value_name="Error")
        dunn = sp.posthoc_dunn(long, val_col="Error", group_col="Model", p_adjust="bonferroni")
        models = ["Garbhini GA-2","Hadlock","INTERGROWTH-21st"]
        rows = ""
        for r in models:
            cells = f"<td><b>{r}</b></td>"
            for c in models:
                v = 1.0 if r==c else dunn.loc[r,c]
                cls = "self" if r==c else ("sig" if v<0.05 else "ns")
                cells += f"<td class='{cls}'>{v:.2e}</td>"
            rows += f"<tr>{cells}</tr>"
        sig_word = "✅ Statistically significant" if p<0.05 else "⚪ Not significant"
        return f"""
<div class='stat-box'>
  <h4>Kruskal–Wallis Test</h4>
  <p>H = {H:.3f} &nbsp;|&nbsp; p = <b>{p:.2e}</b> &nbsp;→&nbsp; {sig_word} (α=0.05)</p>
  <h4>Dunn's Post-hoc (Bonferroni-adjusted p-values)</h4>
  <table class='dt'>
    <thead><tr><th>Model</th>{''.join(f'<th>{m}</th>' for m in models)}</tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <p style='font-size:11px;color:#888;margin-top:6px'>Green = significant difference (p&lt;0.05)</p>
</div>"""
    except Exception as e:
        return f"<p>Stats error: {e}</p>"
