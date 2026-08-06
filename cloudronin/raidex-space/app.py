"""Raidex: an open Responsible AI index for frontier models (HuggingFace Space).

Reads model evaluations from the raidex-results dataset and renders a leaderboard,
the capability-vs-RAI "gap" visual, model cards, and a submit form that queues new
evaluations into the raidex-requests dataset.

Storage is abstracted behind a local/HF switch (RAIDEX_DATA_SOURCE): development
reads local dataset folders (or a bundled seed/), production reads/writes the HF
Hub. Only load_results / get_pending / get_completed / submit_eval touch storage.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import gradio as gr
import pandas as pd
import plotly.graph_objects as go

from check_integrity import developer_for  # canonical model -> developer (single source of truth)

HERE = Path(__file__).resolve().parent
DATA_SOURCE = os.environ.get("RAIDEX_DATA_SOURCE", "local").lower()
RESULTS_REPO = "cloudronin/raidex-results"
REQUESTS_REPO = "cloudronin/raidex-requests"
SEED_DIR = HERE / "seed"
SIB_RESULTS = HERE.parent / "raidex-results"
SIB_REQUESTS = HERE.parent / "raidex-requests"

TOTAL_BENCHMARKS = 9
BENCHMARKS = [
    {"id": "bbq", "label": "BBQ", "dim": "fairness_bias", "tier": "A"},
    {"id": "wmdp", "label": "WMDP", "dim": "security", "tier": "A"},
    {"id": "simpleqa", "label": "SimpleQA", "dim": "factuality", "tier": "A"},
    {"id": "strongreject", "label": "StrongREJECT", "dim": "security", "tier": "A"},
    {"id": "ethics", "label": "ETHICS", "dim": "machine_ethics", "tier": "A"},
    {"id": "xstest", "label": "XSTest", "dim": "safety", "tier": "A"},
    {"id": "sycophancy", "label": "Sycophancy", "dim": "sycophancy", "tier": "A"},
    {"id": "advglue", "label": "AdvGLUE", "dim": "robustness", "tier": "B"},
    {"id": "confaide", "label": "ConfAIde", "dim": "privacy", "tier": "B"},
]
BENCH_LABELS = [b["label"] for b in BENCHMARKS]
DIMENSION_ORDER = ["safety", "fairness_bias", "factuality", "security",
                   "robustness", "privacy", "machine_ethics", "sycophancy"]
DIM_LABEL = {"safety": "Safety", "fairness_bias": "Fairness & Bias", "factuality": "Factuality",
             "security": "Security", "robustness": "Robustness", "privacy": "Privacy",
             "machine_ethics": "Machine Ethics", "sycophancy": "Sycophancy"}
ACTIVE_DIMS = ["safety", "fairness_bias", "factuality", "security", "machine_ethics", "sycophancy"]
BADGE_LEGEND = ("🟣 Full RAI Profile (9/9)  |  🔵 Independently Evaluated  |  "
                "🟡 Self-Reported Only  |  ⚪ Partial Coverage")
MODEL_ID_RE = re.compile(r"^[a-z0-9_\-]+/[A-Za-z0-9._:\-]+$")

CITATION_TEXT = """@misc{raidex2026,
  title  = {Raidex: An Open Responsible AI Index for Frontier Models},
  author = {Vettrivel, Vishnu},
  year   = {2026},
  url    = {https://raidex.ai}
}"""


def _read_text(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text()
    except Exception:
        return fallback


CAP = json.loads(_read_text(HERE / "data" / "capability_benchmarks.json",
                            '{"benchmarks": [], "models": {}}'))
CAP_SCORES = json.loads(_read_text(HERE / "data" / "capability_scores.json", "{}")).get("scores", {})
KEY_FINDINGS_MD = _read_text(HERE / "findings.md", "_Key findings will appear here after evaluation runs._")
METHODOLOGY_MD = _read_text(HERE / "METHODOLOGY.md", "METHODOLOGY.md not found.")


# ----------------------------------------------------------------------------
# Storage layer: the ONLY place that branches on local vs HF.
# ----------------------------------------------------------------------------
# Cache snapshot paths per repo for a TTL. app.load fires load_results() on every (SSR)
# render and the scheduler adds more, so WITHOUT this the Space re-runs snapshot_download on
# every request (a download loop that pins the app and fails its health check, stuck
# "restarting forever"). Re-pull at most every RAIDEX_SNAPSHOT_TTL seconds.
_SNAP_CACHE: dict = {}
_SNAP_TTL = float(os.environ.get("RAIDEX_SNAPSHOT_TTL", "300"))


def _hf_snapshot(repo: str) -> str:
    from huggingface_hub import snapshot_download
    hit = _SNAP_CACHE.get(repo)
    now = time.time()
    if hit and (now - hit[1]) < _SNAP_TTL:
        return hit[0]
    path = snapshot_download(repo_id=repo, repo_type="dataset")
    _SNAP_CACHE[repo] = (path, now)
    return path


def _results_dir() -> str:
    if DATA_SOURCE == "hf":
        try:
            return _hf_snapshot(RESULTS_REPO)
        except Exception as e:  # fall back to local/seed so the app still renders
            print("[raidex] HF results snapshot failed, using local/seed:", e)
    for cand in [os.environ.get("RAIDEX_RESULTS_DIR"), str(SIB_RESULTS), str(SEED_DIR)]:
        if cand and os.path.isdir(cand) and any(Path(cand).glob("*.json")):
            return cand
    return str(SEED_DIR)


def _requests_dir() -> str:
    if DATA_SOURCE == "hf":
        try:
            return _hf_snapshot(REQUESTS_REPO)
        except Exception as e:
            print("[raidex] HF requests snapshot failed:", e)
    for cand in [os.environ.get("RAIDEX_REQUESTS_DIR"), str(SIB_REQUESTS)]:
        if cand and os.path.isdir(cand):
            return cand
    return str(SIB_REQUESTS)


def _write_request(filename: str, obj: dict) -> None:
    if DATA_SOURCE == "hf":
        from huggingface_hub import HfApi
        tmp = Path(tempfile.gettempdir()) / filename
        tmp.write_text(json.dumps(obj, indent=2))
        HfApi().upload_file(path_or_fileobj=str(tmp), path_in_repo=filename,
                            repo_id=REQUESTS_REPO, repo_type="dataset",
                            token=os.environ.get("HF_TOKEN"))
        return
    d = os.environ.get("RAIDEX_REQUESTS_DIR") or str(SIB_REQUESTS)
    os.makedirs(d, exist_ok=True)
    (Path(d) / filename).write_text(json.dumps(obj, indent=2))


# ----------------------------------------------------------------------------
# Load + transform
# ----------------------------------------------------------------------------
def _iter_result_docs(dir_path: str):
    for f in sorted(Path(dir_path).glob("*.json")):
        try:
            doc = json.loads(f.read_text())
        except Exception:
            continue
        if isinstance(doc, dict) and "config" in doc and "results" in doc:
            yield doc


def load_results() -> pd.DataFrame:
    rows = []
    for doc in _iter_result_docs(_results_dir()):
        cfg, comp, res = doc.get("config", {}), doc.get("composite", {}), doc.get("results", {})
        name = cfg.get("model_name") or cfg.get("model_id", "?")
        row = {
            "Badge": comp.get("badge_emoji", "⚪"),
            "Model": name,
            # Developer is DERIVED from the model name (single source of truth in
            # check_integrity.developer_for), NOT the serving provider stored in the JSON.
            # SambaNova/HF-hosted models were otherwise mis-attributed to their host.
            "Developer": developer_for(name) or "?",
            "RAI Score": comp.get("rai_score"),
            "Coverage": comp.get("rai_coverage", ""),
            "_model_id": cfg.get("model_id", ""),
            "_tiers": set(),
            "_sources": set(),
        }
        for b in BENCHMARKS:
            r = res.get(b["id"]) or {}
            norm = r.get("normalized")
            if norm is not None and not r.get("error"):
                row[b["label"]] = round(norm * 100, 1)
                row["_tiers"].add(b["tier"])
                row["_sources"].add(r.get("eval_source", ""))
            else:
                row[b["label"]] = None
        for dim in DIMENSION_ORDER:
            row["dim_" + dim] = comp.get("dimension_scores", {}).get(dim)
        rows.append(row)
    df = pd.DataFrame(rows)
    if not df.empty:
        # RAI descending, then Model name ascending so ties (e.g. gpt-4o / gemini both 69.2)
        # rank deterministically; Rank is then derived from this order, the single source.
        df = df.sort_values(["RAI Score", "Model"], ascending=[False, True],
                            na_position="last").reset_index(drop=True)
        df.insert(0, "Rank", range(1, len(df) + 1))
    return df


LEADERBOARD = load_results()
DISPLAY_COLS = ["Rank", "Badge", "Model", "Developer", "RAI Score", "Coverage"] + BENCH_LABELS


def _display(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=DISPLAY_COLS)
    out = df[[c for c in DISPLAY_COLS if c in df.columns]].copy()
    # Display only: pad every score to one decimal (69 -> 69.0); missing -> em dash.
    # Never written back to the source data the integrity gate reads.
    for c in ["RAI Score"] + BENCH_LABELS:
        if c in out.columns:
            out[c] = out[c].map(lambda v: f"{float(v):.1f}" if pd.notna(v) else "")
    return out


def refresh():
    global LEADERBOARD
    LEADERBOARD = load_results()
    return _display(LEADERBOARD)


def refresh_all():
    """Reload results and push fresh values to every results-driven component, so a
    newly-evaluated model flows through everywhere: the leaderboard table, the
    Capability-vs-RAI scatter, the Model Card and Radar dropdown choices, and the
    pending/completed queues, on each page load and on Refresh. (The Gap heatmaps
    are sourced reference data, not submission-driven, so they intentionally stay
    static.) Output order must match the wired component list at the end of the app."""
    global LEADERBOARD
    LEADERBOARD = load_results()
    choices = model_choices()
    return (_display(LEADERBOARD), build_capability_vs_rai_scatter(),
            gr.update(choices=choices), gr.update(choices=choices),
            get_pending(), get_completed())


def filter_leaderboard(search: str, tiers):
    df = LEADERBOARD
    if df is None or df.empty:
        return _display(df)
    mask = pd.Series(True, index=df.index)
    if search:
        s = search.lower()
        mask &= (df["Model"].str.lower().str.contains(s, na=False)
                 | df["Developer"].str.lower().str.contains(s, na=False))
    sel = {t.split()[-1] for t in tiers} if tiers else {"A"}
    mask &= df["_tiers"].apply(lambda ts: bool(set(ts) & sel) if ts else False)
    return _display(df[mask])


def model_choices():
    if LEADERBOARD is None or LEADERBOARD.empty:
        return []
    return list(LEADERBOARD["Model"])


# ----------------------------------------------------------------------------
# Charts
# ----------------------------------------------------------------------------
GREEN = [[0.0, "#0b3d2e"], [1.0, "#16a34a"]]
RED = [[0.0, "#3d0b0b"], [1.0, "#dc2626"]]
_FONT = "Inter, ui-sans-serif, system-ui, -apple-system, sans-serif"
# Charts sit on a transparent background over the page, which can be light OR dark (gradio
# follows the system theme). Use a mid-slate text and low-opacity gridlines that read on both.
# A fixed dark text (#334155) was invisible in dark mode.
_FG = "#94a3b8"
_GRID = "rgba(148,163,184,0.25)"
_LAYOUT = dict(autosize=True, height=560, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
               font=dict(size=14, family=_FONT, color=_FG),
               title_font=dict(size=16, family=_FONT), title_x=0.02, title_xanchor="left",
               margin=dict(l=160, r=110, t=72, b=120))


def _empty_fig(title: str):
    fig = go.Figure()
    fig.update_layout(title=title, **_LAYOUT)
    fig.add_annotation(text="No data yet", showarrow=False, font=dict(size=24, color="#888"))
    return fig


def build_capability_heatmap():
    """Which capability benchmarks each frontier developer self-reports (sourced grid)."""
    benches = CAP.get("capability_benchmarks", [])
    models = list(CAP.get("models", {}).keys())
    if not benches or not models:
        return _empty_fig("Capability benchmarks")
    z = [CAP["models"][m].get("capability", []) for m in models]
    fig = go.Figure(go.Heatmap(z=z, x=benches, y=models, colorscale=GREEN,
                               showscale=True, xgap=3, ygap=3, zmin=0, zmax=1,
                               colorbar=dict(tickvals=[0, 1], ticktext=["not reported", "reported"],
                                             len=0.55, thickness=16, outlinewidth=0, ticks="")))
    fig.update_layout(title="<b>Capability benchmarks: widely self-reported</b>", **_LAYOUT)
    fig.update_xaxes(tickangle=-40)
    return fig


def build_rai_heatmap():
    """Which RAI benchmarks each frontier developer self-reports (sourced grid): sparse.
    This is reporting, not Raidex's coverage: our leaderboard is what fills the gap."""
    benches = CAP.get("rai_benchmarks", [])
    models = list(CAP.get("models", {}).keys())
    if not benches or not models:
        return _empty_fig("RAI benchmarks")
    z = [CAP["models"][m].get("rai", []) for m in models]
    fig = go.Figure(go.Heatmap(z=z, x=benches, y=models, colorscale=RED,
                               showscale=True, xgap=3, ygap=3, zmin=0, zmax=1,
                               colorbar=dict(tickvals=[0, 1], ticktext=["not reported", "reported"],
                                             len=0.55, thickness=16, outlinewidth=0, ticks="")))
    fig.update_layout(title="<b>RAI benchmarks: rarely self-reported</b>", **_LAYOUT)
    fig.update_xaxes(tickangle=-40)
    return fig


def build_radar(models):
    fig = go.Figure()
    if LEADERBOARD is None or LEADERBOARD.empty or not models:
        fig.update_layout(title="Select models to compare")
        return fig
    for m in models:
        sub = LEADERBOARD[LEADERBOARD["Model"] == m]
        if sub.empty:
            continue
        row = sub.iloc[0]
        r = [row.get("dim_" + d) or 0 for d in ACTIVE_DIMS]
        fig.add_trace(go.Scatterpolar(r=r + [r[0]],
                                      theta=[DIM_LABEL[d] for d in ACTIVE_DIMS] + [DIM_LABEL[ACTIVE_DIMS[0]]],
                                      fill="toself", name=m))
    fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(visible=True, range=[0, 100])),
                      title="Per-dimension comparison", height=520,
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(family=_FONT, color=_FG))
    return fig


# Open-weight classifier (name-substring match), shared by the scatter colouring and the
# hero stats so the "open models are competitive" finding is counted the same way in both.
_OPEN_KEYS = ("llama", "deepseek", "qwen", "gemma", "gpt-oss", "glm", "mixtral", "olmo",
              "minimax", "phi", "kimi", "moonshot", "mimo", "nemotron", "mistral", "inkling")


def _is_open(nm):
    return any(k in (nm or "").lower() for k in _OPEN_KEYS)


def build_capability_vs_rai_scatter():
    """Capability (Artificial Analysis Intelligence Index) vs RAI Score: the core
    'does capability predict responsibility?' view. Replaces the coverage scatter,
    which goes flat once every model reaches 9/9. Capability is sourced + static
    (data/capability_scores.json); RAI reads live from the leaderboard, so the plot
    self-updates as runs land."""
    df = LEADERBOARD
    if df is None or df.empty or not CAP_SCORES:
        return _empty_fig("Capability vs RAI Score")
    pts = []
    for _, row in df.iterrows():
        cap = CAP_SCORES.get(row["Model"])
        rai = row.get("RAI Score")
        if cap is not None and rai is not None and not pd.isna(rai):
            complete = str(row.get("Coverage", "")).strip() == f"{TOTAL_BENCHMARKS}/{TOTAL_BENCHMARKS}"
            pts.append((row["Model"], float(cap), float(rai), complete))
    if not pts:
        return _empty_fig("Capability vs RAI Score")
    xs = [p[1] for p in pts]
    ys = [p[2] for p in pts]
    n = len(pts)
    # Trim long ids so labels are narrower (fewer collisions).
    def _short(nm):
        return (nm.replace("Meta-Llama-3.3-70B-Instruct", "Llama-3.3-70B")
                  .replace("Qwen3-235B-A22B-Instruct-2507", "Qwen3-235B")
                  .replace("-20251001", ""))
    # De-collide labels: point each label in the direction AWAY from its nearby neighbours'
    # centroid, so clustered points (gpt-4o / gemini / llama, gemma-3 / gpt-4o-mini) splay
    # apart in different directions instead of stacking on top-center.
    import math
    xr = (max(xs) - min(xs)) or 1.0
    yr = (max(ys) - min(ys)) or 1.0
    _SECT = [(22.5, "middle right"), (67.5, "top right"), (112.5, "top center"),
             (157.5, "top left"), (202.5, "middle left"), (247.5, "bottom left"),
             (292.5, "bottom center"), (337.5, "bottom right")]
    def _label_pos(i):
        nb = [j for j in range(n) if j != i
              and abs(xs[i] - xs[j]) / xr < 0.14 and abs(ys[i] - ys[j]) / yr < 0.11]
        if not nb:
            return "top center"
        cx = sum(xs[j] for j in nb) / len(nb)
        cy = sum(ys[j] for j in nb) / len(nb)
        a = math.degrees(math.atan2((ys[i] - cy) / yr, (xs[i] - cx) / xr)) % 360
        return next((p for hi, p in _SECT if a < hi), "middle right")
    pos_by_i = {i: _label_pos(i) for i in range(n)}
    # Colour by weight availability (module-level _is_open) so the "open models are
    # competitive" finding is visible.
    # Complete-coverage points (9/9) are coloured by weight and drive the trend fit; partial
    # points are shown but excluded from the fit, because their RAI omits a benchmark and the
    # missingness is capability-correlated (the most-gated models cannot be scored on WMDP),
    # which would bias the slope upward.
    comp_i = [i for i in range(n) if pts[i][3]]
    part_i = [i for i in range(n) if not pts[i][3]]
    fig = go.Figure()
    for label, color, idxs in [
            ("Closed-weight", "#4f46e5", [i for i in comp_i if not _is_open(pts[i][0])]),
            ("Open-weight", "#ea580c", [i for i in comp_i if _is_open(pts[i][0])])]:
        if idxs:
            fig.add_trace(go.Scatter(
                x=[xs[i] for i in idxs], y=[ys[i] for i in idxs],
                mode="markers+text", text=[_short(pts[i][0]) for i in idxs],
                textposition=[pos_by_i[i] for i in idxs], textfont=dict(size=11),
                name=label, marker=dict(size=13, color=color)))
    if part_i:
        fig.add_trace(go.Scatter(
            x=[xs[i] for i in part_i], y=[ys[i] for i in part_i],
            mode="markers+text", text=[_short(pts[i][0]) for i in part_i],
            textposition=[pos_by_i[i] for i in part_i], textfont=dict(size=11, color="#9ca3af"),
            name="Partial coverage (not fitted)",
            marker=dict(size=12, color="rgba(0,0,0,0)", symbol="diamond",
                        line=dict(width=1.6, color="#9ca3af"))))
    rtxt = ""
    xs_c = [xs[i] for i in comp_i]
    ys_c = [ys[i] for i in comp_i]
    if len(xs_c) >= 3 and len(set(xs_c)) > 1:
        import numpy as np
        m, b = np.polyfit(xs_c, ys_c, 1)
        xl = [min(xs_c), max(xs_c)]
        fig.add_trace(go.Scatter(x=xl, y=[m * x + b for x in xl], mode="lines",
                                 line=dict(dash="dash", color="#9ca3af"), showlegend=False, hoverinfo="skip"))
        r = float(np.corrcoef(xs_c, ys_c)[0, 1])
        if r == r:
            # Bootstrap 95% CI (2000 resamples, seeded) over the complete-coverage subset so a
            # new r reads with its uncertainty — the scatter is the finding, not the estimate.
            ax, ay = np.asarray(xs_c), np.asarray(ys_c)
            nc = len(ax)
            rng = np.random.default_rng(0)
            boot = []
            for _ in range(2000):
                idx = rng.integers(0, nc, nc)
                bx, by = ax[idx], ay[idx]
                if len(set(bx)) > 1 and len(set(by)) > 1:
                    boot.append(np.corrcoef(bx, by)[0, 1])
            if boot:
                lo, hi = np.percentile(boot, [2.5, 97.5])
                rtxt = f"Pearson r = {r:.2f}, 95% CI [{lo:.2f}, {hi:.2f}], n = {nc} (9/9 only)"
            else:
                rtxt = f"Pearson r = {r:.2f}, n = {nc} (9/9 only)"
    # Pad the x-range so edge labels (e.g. the rightmost model) aren't clipped.
    pad = (max(xs) - min(xs)) * 0.18 or 5
    fig.update_xaxes(range=[min(xs) - pad, max(xs) + pad])
    # Pearson r in the TITLE (not an in-plot box) so it can't collide with a corner label.
    title = "Capability vs Responsibility" + (f"  ({rtxt})" if rtxt else "")
    fig.update_layout(title=title,
                      xaxis_title="Capability  (Artificial Analysis Intelligence Index v4.1, 2026-07)",
                      yaxis_title="RAI Score", height=560, autosize=True,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(size=14, family=_FONT, color=_FG),
                      title_font=dict(size=18, family=_FONT), title_x=0.0, title_xanchor="left",
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0),
                      margin=dict(l=70, r=60, t=92, b=120))
    fig.update_xaxes(gridcolor=_GRID, zeroline=False)
    fig.update_yaxes(gridcolor=_GRID, zeroline=False)
    # Short coverage note, dropped well below the x-axis title to avoid overlapping it.
    fig.add_annotation(text=f"{len(pts)} models on the capability index; trend fitted over the {len(comp_i)} with full 9/9 coverage (partial-coverage points shown but excluded). RAI is live from the leaderboard",
                       xref="paper", yref="paper", x=0, y=-0.22, showarrow=False,
                       font=dict(size=11, color="#888"), align="left")
    return fig


def build_model_radar(model: str):
    fig = go.Figure()
    if LEADERBOARD is None or LEADERBOARD.empty or not model:
        return fig
    sub = LEADERBOARD[LEADERBOARD["Model"] == model]
    if sub.empty:
        return fig
    row = sub.iloc[0]
    r = [row.get("dim_" + d) or 0 for d in ACTIVE_DIMS]
    theta = [DIM_LABEL[d] for d in ACTIVE_DIMS]
    mean = [LEADERBOARD["dim_" + d].dropna().mean() if "dim_" + d in LEADERBOARD else 0 for d in ACTIVE_DIMS]
    mean = [0 if pd.isna(x) else x for x in mean]
    fig.add_trace(go.Scatterpolar(r=r + [r[0]], theta=theta + [theta[0]], fill="toself", name=model))
    fig.add_trace(go.Scatterpolar(r=mean + [mean[0]], theta=theta + [theta[0]], name="Roster mean"))
    fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(visible=True, range=[0, 100])),
                      height=480, title=f"{model} vs roster mean",
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(family=_FONT, color=_FG))
    return fig


def model_card(model: str):
    if not model or LEADERBOARD is None or LEADERBOARD.empty:
        return "Select a model.", go.Figure(), pd.DataFrame(), ""
    sub = LEADERBOARD[LEADERBOARD["Model"] == model]
    if sub.empty:
        return "Model not found.", go.Figure(), pd.DataFrame(), ""
    row = sub.iloc[0]
    summary = (f"### {row['Badge']} {model}\n"
               f"- **Developer:** {row['Developer']}\n"
               f"- **RAI Score:** {row['RAI Score']}\n"
               f"- **Coverage:** {row['Coverage']}\n"
               f"- **Model ID:** `{row['_model_id']}`")
    tbl = pd.DataFrame({"Benchmark": BENCH_LABELS,
                        "Normalized (0-100)": [row.get(b["label"]) for b in BENCHMARKS]})
    cap_note = ("*Capability-vs-RAI rank comparison appears once capability data is populated.*")
    return summary, build_model_radar(model), tbl, cap_note


# ----------------------------------------------------------------------------
# Submit + queue views
# ----------------------------------------------------------------------------
def _queue_df(status_filter=None):
    rows = []
    try:
        for f in sorted(Path(_requests_dir()).glob("*.json")):
            try:
                req = json.loads(f.read_text())
            except Exception:
                continue
            if "model_id" not in req:
                continue
            if status_filter and req.get("status") != status_filter:
                continue
            rows.append({"Model ID": req.get("model_id"), "Tier": req.get("tier"),
                         "Status": req.get("status"), "Submitted": req.get("submitted_at", "")})
    except Exception:
        pass
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Model ID", "Tier", "Status", "Submitted"])


def get_pending():
    return _queue_df("pending")


def get_completed():
    return _queue_df("completed")


def validate_model_id(model_id: str) -> bool:
    return bool(model_id and MODEL_ID_RE.match(model_id.strip()))


def submit_eval(model_id: str, tier: str):
    model_id = (model_id or "").strip()
    if not validate_model_id(model_id):
        return "❌ Invalid model ID. Use litellm format `provider/model_name`, e.g. `openai/gpt-5.2`."
    benches = [b["id"] for b in BENCHMARKS]
    tier_code = "A+B" if tier.startswith("A+B") else "A"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    obj = {"model_id": model_id, "submitted_by": os.environ.get("USER", "anonymous"),
           "submitted_at": ts, "tier": tier_code, "status": "pending", "benchmarks": benches}
    fname = model_id.replace("/", "__") + "__" + ts.replace(":", "").replace("-", "") + ".json"
    try:
        _write_request(fname, obj)
    except Exception as e:
        return f"❌ Could not queue evaluation: {e}"
    return (f"✅ Queued **{model_id}** for Tier {tier_code} ({len(benches)} benchmarks). "
            "Results appear on the leaderboard within ~30 min of completion.")


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
THEME = gr.themes.Soft(
    primary_hue="indigo",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("IBM Plex Mono"), "ui-monospace", "monospace"],
)
CSS = """
.hero-stats { display:flex; gap:1.75rem; flex-wrap:wrap; margin:.4rem 0 1.25rem; align-items:baseline; }
.hero-stats .stat { font-size:1rem; color:var(--body-text-color-subdued); }
.hero-stats .stat b { color:var(--primary-600); font-size:1.25rem; font-weight:700; }
#board-table table td { font-family:var(--font-mono); font-size:.85rem; }
"""


def _hero_stats_html():
    """Live RAI spread and capability range for the hero, both derived from LEADERBOARD and
    CAP_SCORES (the range is max/min capability, currently about twelvefold). Display only:
    never written back to the data the integrity gate reads."""
    rai = (LEADERBOARD["RAI Score"].dropna()
           if LEADERBOARD is not None and not LEADERBOARD.empty else pd.Series(dtype=float))
    spread = (rai.max() - rai.min()) if not rai.empty else 0
    caps = [CAP_SCORES[m] for m in (list(LEADERBOARD["Model"])
            if LEADERBOARD is not None and not LEADERBOARD.empty else []) if m in CAP_SCORES]
    ratio = (max(caps) / min(caps)) if caps and min(caps) > 0 else 0
    rng = f" vs a <b>{ratio:.0f}&times;</b> capability range" if ratio >= 2 else ""
    s1 = (f"<span class='stat'><b>{spread:.0f}-point</b> RAI spread{rng}</span>" if spread else "")
    # Dynamic Pearson r over the complete-coverage (9/9) capability-RAI join, matching the
    # scatter's fit exactly (partial-coverage models are excluded so the estimate is not
    # inflated by capability-correlated missingness).
    import numpy as np
    xy = []
    if LEADERBOARD is not None and not LEADERBOARD.empty:
        for m, v, cov in zip(LEADERBOARD["Model"], LEADERBOARD["RAI Score"], LEADERBOARD["Coverage"]):
            if m in CAP_SCORES and pd.notna(v) and str(cov).strip() == f"{TOTAL_BENCHMARKS}/{TOTAL_BENCHMARKS}":
                xy.append((CAP_SCORES[m], v))
    s2 = ""
    if len(xy) >= 3 and len({a for a, _ in xy}) > 1:
        rr = float(np.corrcoef([a for a, _ in xy], [b for _, b in xy])[0, 1])
        s2 = f"<span class='stat'>capability barely predicts RAI (<b>r &asymp; {rr:.2f}</b>)</span>"
    # Dynamic: leaderboard rank of the highest-scoring open-weight model.
    s3 = ""
    if LEADERBOARD is not None and not LEADERBOARD.empty:
        for i, m in enumerate(LEADERBOARD.sort_values("RAI Score", ascending=False)["Model"], 1):
            if _is_open(m):
                s3 = f"<span class='stat'>top open-weight model is <b>#{i}</b></span>"
                break
    return "<div class='hero-stats'>" + s1 + s2 + s3 + "</div>"


HERO_STATS = _hero_stats_html()

with gr.Blocks(title="Raidex", theme=THEME, css=CSS) as app:
    gr.Markdown("# Raidex\n**An open Responsible AI index for frontier models.** "
                "[raidex.ai](https://raidex.ai)")

    # ---- Hero: the finding and the scatter lead; the board is evidence, in the tab below ----
    gr.Markdown("## Capability doesn't predict responsibility")
    gr.Markdown("_Every score is independently evaluated by Raidex, not self-reported._")
    gr.HTML(HERO_STATS)
    cap_scatter = gr.Plot(value=build_capability_vs_rai_scatter())

    with gr.Tabs() as tabs:
        # ---- Main page: leaderboard + the gap + coverage, all in one ----
        with gr.Tab("Findings", id="leaderboard"):
            # 1. The finding: prose, demoted from the hero to first in-tab section
            gr.Markdown("## Key Findings")
            gr.Markdown(KEY_FINDINGS_MD)

            # 2. The board: supporting evidence; search + tier filter sit with the table
            gr.Markdown("## The board")
            gr.Markdown("Frontier models ranked by **RAI Score**, the unweighted mean of their normalized "
                        "scores across 8 open Responsible-AI benchmarks (0 to 100). Raidex runs every benchmark "
                        "itself, so none of these numbers are self-reported. Search by name or filter by tier. "
                        "The badge shows how many of the 8 benchmarks were run.")
            with gr.Row():
                search = gr.Textbox(placeholder="Search models...", show_label=False, scale=3)
                tier_filter = gr.CheckboxGroup(["Tier A", "Tier B", "Tier C"], value=["Tier A", "Tier B"],
                                               label="Benchmark tiers", scale=2)
            table = gr.Dataframe(value=_display(LEADERBOARD), interactive=False, wrap=True,
                                 elem_id="board-table")
            refresh_btn = gr.Button("Refresh", scale=0)
            gr.Markdown(BADGE_LEGEND)
            search.change(filter_leaderboard, [search, tier_filter], table)
            tier_filter.change(filter_leaderboard, [search, tier_filter], table)

            # 3. The Gap: supporting context (sourced reporting grid)
            gr.Markdown("## The Gap")
            gr.Markdown("Why Raidex exists. Frontier developers report **capability** benchmarks almost "
                        "universally (top, green) but **Responsible-AI** benchmarks rarely (bottom, red). "
                        "Each row is a flagship model; each cell marks whether that developer publicly reports "
                        "that benchmark. The sparse red grid is the reporting gap Raidex fills.")
            gr.Plot(value=build_capability_heatmap())
            gr.Plot(value=build_rai_heatmap())
            gr.Markdown("*Frontier developers report capability benchmarks consistently but "
                        "rarely report RAI benchmarks. Raidex runs all 8 anyway.*")

            # 4. Methodology teaser: last
            gr.Markdown("## Methodology")
            gr.Markdown("The RAI Score is a defined index: an unweighted mean of normalized open-benchmark "
                        "scores across safety, fairness, factuality, security, machine ethics, robustness, "
                        "and privacy. Scores are generative and judge-based and sampled, so read them within "
                        "Raidex rather than against canonical loglikelihood leaderboards.")
            method_btn = gr.Button("Read the full methodology →", scale=0)

        with gr.Tab("Model Card", id="modelcard"):
            picker = gr.Dropdown(label="Select model", choices=model_choices())
            with gr.Row():
                with gr.Column(scale=1):
                    m_summary = gr.Markdown()
                with gr.Column(scale=2):
                    m_radar = gr.Plot()
            m_table = gr.Dataframe(interactive=False)
            m_cap = gr.Markdown()
            picker.change(model_card, picker, [m_summary, m_radar, m_table, m_cap])

        with gr.Tab("Radar", id="radar"):
            r_select = gr.Dropdown(multiselect=True, label="Compare models", choices=model_choices())
            r_plot = gr.Plot(value=build_radar([]))
            r_select.change(build_radar, r_select, r_plot)

        with gr.Tab("Submit", id="submit"):
            gr.Markdown("### Evaluate a model on RAI benchmarks")
            gr.Markdown("Model ID uses litellm format: `provider/model_name` "
                        "(e.g. `openai/gpt-5.2`, `anthropic/claude-opus-4-8`, `gemini/gemini-2.5-flash`)")
            s_model = gr.Textbox(label="Model ID", placeholder="openai/gpt-5.2")
            s_tier = gr.Radio(["A (6 benchmarks)", "A+B (8 benchmarks)"],
                              value="A+B (8 benchmarks)", label="Evaluation tier")
            s_btn = gr.Button("Submit for evaluation", variant="primary")
            s_msg = gr.Markdown()
            gr.Markdown("---")
            with gr.Accordion("Pending evaluations", open=False):
                pending_tbl = gr.Dataframe(value=get_pending(), interactive=False)
            with gr.Accordion("Completed evaluations", open=False):
                completed_tbl = gr.Dataframe(value=get_completed(), interactive=False)

        with gr.Tab("Methodology", id="methodology"):
            gr.Markdown(METHODOLOGY_MD)

    with gr.Accordion("Citation", open=False):
        gr.Textbox(value=CITATION_TEXT, lines=8, show_label=False)
    gr.Markdown("---")
    with gr.Row():
        gr.Markdown("[GitHub](https://github.com/cloudronin/raidex) | Built by Vishnu Vettrivel")
        footer_method_btn = gr.Button("Methodology", scale=0)

    # Markdown links can't target Gradio tabs, so route the methodology links through tab selection.
    method_btn.click(lambda: gr.Tabs(selected="methodology"), None, tabs)
    footer_method_btn.click(lambda: gr.Tabs(selected="methodology"), None, tabs)

    # Results-driven refresh, wired here (after every component exists). Page load and
    # the Refresh button repopulate the leaderboard table, the Capability-vs-RAI
    # scatter, the Model Card + Radar dropdown choices, and the queue tables, so a
    # newly-submitted/evaluated model shows up everywhere without a restart.
    _refresh_outs = [table, cap_scatter, picker, r_select, pending_tbl, completed_tbl]
    refresh_btn.click(refresh_all, None, _refresh_outs)
    s_btn.click(submit_eval, [s_model, s_tier], s_msg).then(
        lambda: (get_pending(), get_completed()), None, [pending_tbl, completed_tbl])
    # NO app.load(refresh_all) here on purpose: it re-ran load_results()/snapshot_download on
    # EVERY (SSR) render, and under HF's SSR worker that re-downloaded the dataset on every
    # request (a loop that pinned the app and failed its health check, stuck restarting).
    # Every component already initialises from the startup LEADERBOARD; freshness comes from
    # the 🔄 Refresh button and the 30-min scheduler.


# Auto-refresh at MODULE level: HF launches the `app` object directly and never runs the
# __main__ block below, so a scheduler started there would never fire on the Space. Reload
# results every 30 min so newly-evaluated models appear without a manual Refresh. Guarded so
# a hot-reload double-import can't stack schedulers or take the app down.
def _start_auto_refresh():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        sched = BackgroundScheduler(daemon=True)
        sched.add_job(refresh, "interval", seconds=1800)
        sched.start()
        return sched
    except Exception as e:
        print("[raidex] auto-refresh scheduler not started:", e)
        return None


_AUTO_REFRESH = _start_auto_refresh()


if __name__ == "__main__":
    # Local runs only: HF ignores this block and launches `app` itself (SSR is controlled on
    # the Space via the GRADIO_SSR_MODE env var). ssr_mode=False keeps local single-process.
    app.queue(default_concurrency_limit=40).launch(ssr_mode=False)
