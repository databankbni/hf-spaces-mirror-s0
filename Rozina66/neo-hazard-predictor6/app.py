import gradio as gr
import joblib
import numpy as np

model = joblib.load("model.pkl")
scaler = joblib.load("scaler.pkl")


def predict(min_diameter, max_diameter, relative_velocity, miss_distance, absolute_magnitude):
    X = [[min_diameter, max_diameter, relative_velocity, miss_distance, absolute_magnitude]]
    X_scaled = scaler.transform(X)
    prediction = int(model.predict(X_scaled)[0])

    proba = None
    if hasattr(model, "predict_proba"):
        try:
            proba = float(model.predict_proba(X_scaled)[0][1])
        except Exception:
            proba = None

    is_hazard = prediction == 1
    pct = round(proba * 100, 1) if proba is not None else None

    if is_hazard:
        verdict, sub = "Hazardous", "This object is classified as potentially hazardous"
        accent, glow = "#ff5f6d", "rgba(255,95,109,0.35)"
        icon = "⚠"
    else:
        verdict, sub = "Not hazardous", "This object is classified as safe"
        accent, glow = "#4ade80", "rgba(74,222,128,0.35)"
        icon = "✓"

    bar_html = ""
    if pct is not None:
        bar_html = f"""
        <div style="margin-top:18px;">
          <div style="display:flex;justify-content:space-between;font-size:13px;color:#9ca3c9;margin-bottom:6px;">
            <span>Hazard probability</span><span>{pct}%</span>
          </div>
          <div style="width:100%;height:10px;border-radius:6px;background:rgba(255,255,255,0.08);overflow:hidden;">
            <div style="width:{pct}%;height:100%;border-radius:6px;background:{accent};box-shadow:0 0 12px {glow};"></div>
          </div>
        </div>
        """

    return f"""
    <div style="border:1px solid {accent}55;background:radial-gradient(circle at top left, {glow}, rgba(15,17,35,0.6));
                border-radius:16px;padding:26px 28px;text-align:left;box-shadow:0 0 30px {glow};">
      <div style="display:flex;align-items:center;gap:14px;">
        <div style="width:46px;height:46px;border-radius:50%;background:{accent}22;border:1px solid {accent};
                    display:flex;align-items:center;justify-content:center;font-size:22px;color:{accent};">{icon}</div>
        <div>
          <div style="font-size:20px;font-weight:600;color:{accent};">{verdict}</div>
          <div style="font-size:13px;color:#9ca3c9;">{sub}</div>
        </div>
      </div>
      {bar_html}
    </div>
    """


space_css = """
.gradio-container {
    background: radial-gradient(ellipse at top, #1b1e3d 0%, #0a0c1b 60%, #05060f 100%) !important;
    background-attachment: fixed !important;
}
.gradio-container::before {
    content: "";
    position: fixed;
    inset: 0;
    background-image:
        radial-gradient(1.5px 1.5px at 20px 30px, #ffffff55, transparent),
        radial-gradient(1.5px 1.5px at 120px 90px, #ffffff33, transparent),
        radial-gradient(1px 1px at 200px 40px, #ffffff44, transparent),
        radial-gradient(1.5px 1.5px at 300px 150px, #ffffff33, transparent),
        radial-gradient(1px 1px at 400px 60px, #ffffff55, transparent),
        radial-gradient(1.5px 1.5px at 480px 200px, #ffffff33, transparent);
    background-repeat: repeat;
    background-size: 500px 300px;
    opacity: 0.6;
    pointer-events: none;
    z-index: 0;
}
#hero {
    text-align: center;
    padding: 28px 10px 6px 10px;
}
#hero h1 {
    font-size: 30px;
    font-weight: 700;
    background: linear-gradient(90deg, #7dd3fc, #a78bfa, #f472b6);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    margin-bottom: 6px;
}
#hero p {
    color: #9ca3c9;
    font-size: 14px;
}
#badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 16px;
    border-radius: 999px;
    border: 1px solid #7dd3fc55;
    background: #7dd3fc11;
    color: #7dd3fc;
    font-size: 12px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 14px;
}
.panel {
    background: rgba(20, 22, 45, 0.65) !important;
    border: 1px solid rgba(125, 211, 252, 0.15) !important;
    border-radius: 16px !important;
    backdrop-filter: blur(6px);
}
footer {visibility: hidden}
"""

theme = gr.themes.Base(
    primary_hue="sky",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "sans-serif"],
).set(
    body_background_fill="#05060f",
    block_background_fill="rgba(20, 22, 45, 0.65)",
    block_border_color="rgba(125, 211, 252, 0.15)",
    block_label_text_color="#9ca3c9",
    block_title_text_color="#e5e7ff",
    input_background_fill="rgba(255,255,255,0.04)",
    body_text_color="#e5e7ff",
    button_primary_background_fill="linear-gradient(90deg, #7dd3fc, #a78bfa)",
    button_primary_text_color="#05060f",
)

with gr.Blocks(theme=theme, css=space_css, title="NEO Hazard Predictor") as demo:
    gr.HTML(
        """
        <div id="hero">
          <div id="badge">🛰️ Near-Earth Object Watch</div>
          <h1>NEO Hazard Predictor</h1>
          <p>Estimate whether a near-Earth asteroid poses a potential impact hazard</p>
        </div>
        """
    )

    with gr.Row():
        with gr.Column(scale=1, elem_classes="panel"):
            gr.Markdown("### Orbital parameters")
            min_diameter = gr.Number(label="Min diameter (km)", value=0.2)
            max_diameter = gr.Number(label="Max diameter (km)", value=0.5)
            relative_velocity = gr.Number(label="Relative velocity (km/h)", value=45000)
            miss_distance = gr.Number(label="Miss distance (km)", value=5000000)
            absolute_magnitude = gr.Number(label="Absolute magnitude (H)", value=20.0)
            predict_btn = gr.Button("Analyze object", variant="primary")

        with gr.Column(scale=1):
            gr.Markdown("### Prediction")
            output = gr.HTML(
                """
                <div style="border:1px dashed rgba(125,211,252,0.3);border-radius:16px;padding:30px;text-align:center;color:#9ca3c9;">
                  Enter orbital parameters and click <b>Analyze object</b> to see the result
                </div>
                """
            )

    gr.Examples(
        examples=[
            [0.12, 0.27, 38000, 6800000, 21.4],
            [0.9, 2.1, 68000, 450000, 17.8],
        ],
        inputs=[min_diameter, max_diameter, relative_velocity, miss_distance, absolute_magnitude],
        label="Try an example",
    )

    gr.HTML(
        """
        <p style="text-align:center;color:#5f6480;font-size:12px;margin-top:20px;">
          Built with Gradio · Model trained on NASA NEO data · For educational purposes only
        </p>
        """
    )

    predict_btn.click(
        fn=predict,
        inputs=[min_diameter, max_diameter, relative_velocity, miss_distance, absolute_magnitude],
        outputs=output,
    )

demo.launch()