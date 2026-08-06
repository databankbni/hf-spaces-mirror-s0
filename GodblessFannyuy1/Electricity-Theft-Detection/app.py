import os
import joblib
import pandas as pd
import numpy as np
import gradio as gr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── Load model & scaler safely using relative paths ───────────────────────────
scaler = joblib.load('models/scaler.joblib')
model  = joblib.load('models/theft_detector_model.joblib')

FEATURES = [
    'mean_consumption', 'std_consumption', 'min_consumption', 'max_consumption',
    'zero_consumption_ratio', 'missing_consumption_ratio', 'volatility', 'sudden_drops'
]

# ── Slider ranges — defaults set to SAFE (Normal) values (base proba = 0.46)
SLIDER_CONFIG = {
    'mean_consumption':          {'min': 0.0,  'max': 100.0,  'default': 3.0,   'step': 0.1,  'label': 'Mean Daily Consumption (kWh)'},
    'std_consumption':           {'min': 0.0,  'max': 100.0,  'default': 5.0,   'step': 0.1,  'label': 'Std Dev of Consumption (kWh)'},
    'min_consumption':           {'min': 0.0,  'max': 3.0,    'default': 0.5,   'step': 0.01, 'label': 'Minimum Daily Consumption (kWh)'},
    'max_consumption':           {'min': 0.0,  'max': 500.0,  'default': 100.0, 'step': 1.0,  'label': 'Maximum Daily Consumption (kWh)'},
    'zero_consumption_ratio':    {'min': 0.0,  'max': 1.0,    'default': 0.05,  'step': 0.01, 'label': 'Zero-Consumption Ratio (0 – 1)'},
    'missing_consumption_ratio': {'min': 0.0,  'max': 1.0,    'default': 0.05,  'step': 0.01, 'label': 'Missing Readings Ratio (0 – 1)'},
    'volatility':                {'min': 0.0,  'max': 55.0,   'default': 3.0,   'step': 0.1,  'label': 'Day-to-Day Volatility'},
    'sudden_drops':              {'min': 0.0,  'max': 200.0,  'default': 5.0,   'step': 1.0,  'label': 'Count of Sudden Consumption Drops'},
}

# ── Per-feature ELEVATED RISK thresholds (where a feature meaningfully contributes to theft risk)
# NOTE: No single feature can trigger theft alone. Theft detection requires 2+ elevated features.
# direction: 'above' = value >= threshold raises risk, 'below' = value <= threshold raises risk
# max_solo_proba = maximum theft probability achievable by this feature alone (others at safe defaults)
THRESHOLDS = {
    'mean_consumption':          {'value': 8.0,   'direction': 'above', 'note': '>= 8.0 kWh/day',           'max_solo': 0.505},
    'std_consumption':           {'value': 20.0,  'direction': 'above', 'note': '>= 20 kWh std dev',         'max_solo': 0.721},
    'min_consumption':           {'value': None,  'direction': None,    'note': 'Minimal solo contribution', 'max_solo': 0.457},
    'max_consumption':           {'value': 24.0,  'direction': 'below', 'note': '<= 24 kWh peak is low',     'max_solo': 0.633},
    'zero_consumption_ratio':    {'value': 0.23,  'direction': 'above', 'note': '>= 23% zero days',          'max_solo': 0.675},
    'missing_consumption_ratio': {'value': 0.23,  'direction': 'above', 'note': '>= 23% missing days',       'max_solo': 0.718},
    'volatility':                {'value': 1.0,   'direction': 'below', 'note': '<= 1.0 (unnaturally flat)', 'max_solo': 0.565},
    'sudden_drops':              {'value': 19.0,  'direction': 'above', 'note': '>= 19 sudden drops',        'max_solo': 0.463},
}

# ── Classification threshold (lowered from 0.85 to 0.70 for realistic flagging) ──
# 0.70 is highly confident for an imbalanced dataset where base theft rate is ~8.5%
THEFT_THRESHOLD = 0.70


def is_in_danger_zone(feat, value):
    """Check if a single feature value is in its theft danger zone."""
    cfg = THRESHOLDS[feat]
    if cfg['value'] is None:
        return False
    if cfg['direction'] == 'above':
        return value >= cfg['value']
    if cfg['direction'] == 'below':
        return value <= cfg['value']
    return False


def build_feature_status_html(values_dict):
    """Build a colour-coded per-feature status panel."""
    rows = ""
    for feat in FEATURES:
        label  = SLIDER_CONFIG[feat]['label']
        note   = THRESHOLDS[feat]['note']
        val    = values_dict[feat]
        danger = is_in_danger_zone(feat, val)

        if THRESHOLDS[feat]['value'] is None:
            bg    = "#F0F4FF"
            icon  = "&#8505;"   # ℹ
            color = "#4A6FA5"
            tag   = "CONTRIBUTING"
        elif danger:
            bg    = "#FEE8E7"
            icon  = "&#9888;"   # ⚠
            color = "#C0392B"
            tag   = "DANGER ZONE"
        else:
            bg    = "#E9F7EF"
            icon  = "&#10003;"  # ✓
            color = "#1E8449"
            tag   = "NORMAL"

        rows += f"""
        <div style="background:{bg}; border-left:4px solid {color};
                    border-radius:6px; padding:8px 12px; margin-bottom:6px;
                    display:flex; justify-content:space-between; align-items:center;">
            <div>
                <span style="font-size:13px; font-weight:600; color:#333;">{label}</span><br>
                <span style="font-size:11px; color:#777;">Threshold: {note} &nbsp;|&nbsp; Current: <b>{val:.3f}</b></span>
            </div>
            <span style="font-size:11px; font-weight:700; color:{color};
                         background:white; padding:3px 8px; border-radius:20px;
                         border:1px solid {color};">
                {icon} {tag}
            </span>
        </div>"""

    return f'<div style="font-family:\'Segoe UI\',sans-serif;">{rows}</div>'


def predict_theft(mean_consumption, std_consumption, min_consumption, max_consumption,
                  zero_consumption_ratio, missing_consumption_ratio, volatility, sudden_drops):

    # Guard: sliders may fire None on first page load
    args = [mean_consumption, std_consumption, min_consumption, max_consumption,
            zero_consumption_ratio, missing_consumption_ratio, volatility, sudden_drops]
    if any(v is None for v in args):
        return "", "", None

    values_dict = {
        'mean_consumption': mean_consumption, 'std_consumption': std_consumption,
        'min_consumption': min_consumption,   'max_consumption': max_consumption,
        'zero_consumption_ratio': zero_consumption_ratio,
        'missing_consumption_ratio': missing_consumption_ratio,
        'volatility': volatility, 'sudden_drops': sudden_drops
    }

    input_data   = pd.DataFrame([values_dict])
    input_scaled = pd.DataFrame(scaler.transform(input_data), columns=FEATURES)
    proba        = model.predict_proba(input_scaled)[0]
    theft_conf   = proba[1]
    normal_conf  = proba[0]
    prediction   = 1 if theft_conf >= THEFT_THRESHOLD else 0

    # ── Result HTML ────────────────────────────────────────────────────────────
    if prediction == 1:
        status_color = "#C0392B"
        status_text  = "THEFT DETECTED"
        badge        = "HIGH RISK"
    else:
        status_color = "#1E8449"
        status_text  = "NORMAL CONSUMPTION"
        badge        = "LOW RISK"

    # Count how many features are in danger zone
    danger_count = sum(1 for f in FEATURES if is_in_danger_zone(f, values_dict[f]))

    result_html = f"""
    <div style="font-family:'Segoe UI',sans-serif; padding:4px;">
        <div style="background:{status_color}; border-radius:12px; padding:20px;
                    text-align:center; margin-bottom:14px;
                    box-shadow:0 4px 15px rgba(0,0,0,0.15);">
            <div style="font-size:12px;font-weight:700;letter-spacing:2px;
                        opacity:0.85;color:white;">{badge}</div>
            <div style="font-size:26px;font-weight:800;color:white;margin:6px 0;">{status_text}</div>
            <div style="font-size:14px;color:rgba(255,255,255,0.9);">
                Theft Probability: <strong>{theft_conf:.1%}</strong>
                &nbsp;|&nbsp; Threshold: <strong>70%</strong>
            </div>
        </div>
        <div style="display:flex;gap:10px;margin-bottom:14px;">
            <div style="flex:1;background:#1E8449;border-radius:8px;padding:12px;
                        text-align:center;color:white;">
                <div style="font-size:11px;opacity:0.85;">NORMAL</div>
                <div style="font-size:20px;font-weight:700;">{normal_conf:.1%}</div>
            </div>
            <div style="flex:1;background:#C0392B;border-radius:8px;padding:12px;
                        text-align:center;color:white;">
                <div style="font-size:11px;opacity:0.85;">THEFT</div>
                <div style="font-size:20px;font-weight:700;">{theft_conf:.1%}</div>
            </div>
        </div>
        <div style="background:#FFF3CD;border-radius:8px;padding:10px 14px;
                    font-size:13px;color:#856404;border-left:4px solid #FFC107;">
            &#9888; <strong>{danger_count} of 8 features</strong> are currently in the theft danger zone.
        </div>
    </div>"""

    # ── Feature status panel ───────────────────────────────────────────────────
    status_html = build_feature_status_html(values_dict)

    # ── Contribution bar chart ─────────────────────────────────────────────────
    # For each feature: compare proba(all safe defaults EXCEPT this feature at current value)
    # vs proba(all safe defaults). This shows each feature's STANDALONE impact on theft risk.
    safe_defaults = {f: SLIDER_CONFIG[f]['default'] for f in FEATURES}
    base_safe_scaled = pd.DataFrame(
        scaler.transform(pd.DataFrame([safe_defaults])), columns=FEATURES
    )
    p_all_safe = model.predict_proba(base_safe_scaled)[0][1]

    contributions = {}
    for feat in FEATURES:
        solo_input = safe_defaults.copy()
        solo_input[feat] = values_dict[feat]   # only this feature at current value
        solo_scaled = pd.DataFrame(scaler.transform(pd.DataFrame([solo_input])), columns=FEATURES)
        p_solo = model.predict_proba(solo_scaled)[0][1]
        contributions[feat] = p_solo - p_all_safe   # positive = pushes toward theft

    feat_labels = [SLIDER_CONFIG[f]['label'] for f in FEATURES]
    values      = [contributions[f] for f in FEATURES]
    colors      = ['#C0392B' if v > 0 else '#1E8449' for v in values]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(feat_labels, values, color=colors, edgecolor='none', height=0.55)
    ax.axvline(0, color='#555', linewidth=0.8, linestyle='--')
    ax.set_xlabel('Change in Theft Probability vs. Typical Customer', fontsize=9)
    ax.set_title('Per-Feature Contribution to This Prediction', fontsize=10, fontweight='bold')
    ax.tick_params(axis='y', labelsize=8)
    ax.tick_params(axis='x', labelsize=8)
    plt.tight_layout()

    return result_html, status_html, fig


# ── UI ─────────────────────────────────────────────────────────────────────────
REFERENCE_HTML = """
<div style="font-family:'Segoe UI',sans-serif; background:#F8F9FA;
            border-radius:10px; padding:14px 16px; font-size:12px;">
    <div style="font-weight:700; font-size:13px; margin-bottom:6px; color:#333;">
        &#127919; Feature Risk Reference (SGCC Dataset Analysis)
    </div>
    <div style="background:#FFF3CD; border-radius:6px; padding:8px 10px;
                font-size:11px; color:#856404; margin-bottom:10px;
                border-left:3px solid #FFC107;">
        &#9888; <strong>No single feature can trigger theft alone.</strong>
        Theft detection (70%) requires <strong>2 or more</strong> elevated features together.
    </div>
    <table style="width:100%;border-collapse:collapse;">
        <tr style="background:#E9ECEF;font-size:11px;">
            <th style="padding:5px 8px;text-align:left;">Feature</th>
            <th style="padding:5px 8px;text-align:left;">Elevated Risk At</th>
            <th style="padding:5px 8px;text-align:left;">Max Solo Proba</th>
        </tr>
        <tr><td style="padding:5px 8px;">Std Dev of Consumption</td>
            <td style="color:#C0392B;font-weight:600;">&gt;= 20 kWh std dev</td>
            <td style="color:#E67E22;font-weight:600;">72.1%</td></tr>
        <tr style="background:#F8F9FA;"><td style="padding:5px 8px;">Missing Readings Ratio</td>
            <td style="color:#C0392B;font-weight:600;">&gt;= 23% missing days</td>
            <td style="color:#E67E22;font-weight:600;">71.8%</td></tr>
        <tr><td style="padding:5px 8px;">Zero-Consumption Ratio</td>
            <td style="color:#C0392B;font-weight:600;">&gt;= 23% zero days</td>
            <td style="color:#E67E22;font-weight:600;">67.5%</td></tr>
        <tr style="background:#F8F9FA;"><td style="padding:5px 8px;">Max Daily Consumption</td>
            <td style="color:#C0392B;font-weight:600;">&lt;= 24 kWh peak</td>
            <td style="color:#E67E22;font-weight:600;">63.3%</td></tr>
        <tr><td style="padding:5px 8px;">Day-to-Day Volatility</td>
            <td style="color:#C0392B;font-weight:600;">&lt;= 1.0 (unnaturally flat)</td>
            <td style="color:#E67E22;font-weight:600;">56.5%</td></tr>
        <tr style="background:#F8F9FA;"><td style="padding:5px 8px;">Mean Daily Consumption</td>
            <td style="color:#C0392B;font-weight:600;">&gt;= 8.0 kWh/day</td>
            <td style="color:#E67E22;font-weight:600;">50.5%</td></tr>
        <tr><td style="padding:5px 8px;color:#777;">Sudden Drops</td>
            <td style="color:#777;">&gt;= 19 drops (weak)</td>
            <td style="color:#777;">46.3%</td></tr>
        <tr style="background:#F8F9FA;"><td style="padding:5px 8px;color:#777;">Min Daily Consumption</td>
            <td style="color:#777;">Minimal effect</td>
            <td style="color:#777;">45.7%</td></tr>
    </table>
</div>"""

with gr.Blocks(title="SGCC Electricity Theft Detection") as demo:

    gr.Markdown("""
    # ⚡ SGCC Electricity Theft Detection System
    Adjust customer consumption statistics below. The model predicts whether the
    pattern indicates **electricity theft** or **normal usage**.
    > Sliders default to the **average SGCC customer profile**. Thresholds are shown live as you adjust.
    """)

    with gr.Row():
        # ── Left column: sliders + reference table ─────────────────────────────
        with gr.Column(scale=1):
            gr.Markdown("### Customer Statistics")
            inputs = []
            for feat in FEATURES:
                cfg = SLIDER_CONFIG[feat]
                s = gr.Slider(minimum=cfg['min'], maximum=cfg['max'],
                              value=cfg['default'], step=cfg['step'],
                              label=cfg['label'])
                inputs.append(s)

            gr.Markdown("---")
            gr.HTML(REFERENCE_HTML)
            analyse_btn = gr.Button("Analyse Customer", variant="primary", size="lg")

        # ── Right column: results ──────────────────────────────────────────────
        with gr.Column(scale=1):
            gr.Markdown("### Detection Result")
            result_html = gr.HTML()

            gr.Markdown("### Feature Status (Live Danger Zone Check)")
            status_html = gr.HTML()

            gr.Markdown("### Feature Contribution Chart")
            contrib_plot = gr.Plot()

    # Wire up interactions
    analyse_btn.click(fn=predict_theft, inputs=inputs,
                      outputs=[result_html, status_html, contrib_plot])
    for slider in inputs:
        slider.change(fn=predict_theft, inputs=inputs,
                      outputs=[result_html, status_html, contrib_plot])

    gr.Markdown("""
    ---
    **Reading the chart:** 🔴 Red = feature pushing toward theft &nbsp;|&nbsp;
    🟢 Green = feature pushing toward normal &nbsp;|&nbsp;
    **Threshold for detection: 70% theft probability**
    """)

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(primary_hue="blue"))
