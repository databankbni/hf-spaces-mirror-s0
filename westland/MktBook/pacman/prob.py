import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import numpy as np
from scipy import stats

app = dash.Dash(__name__)

FAMILIES = {
    "SU": "Johnson SU (Unbounded)",
    "SB": "Johnson SB (Bounded)",
    "SL": "Johnson SL (Log-Normal)",
}

app.layout = html.Div(
    style={"fontFamily": "Arial, sans-serif", "maxWidth": "960px", "margin": "0 auto", "padding": "24px"},
    children=[
        html.H1("Johnson Distribution Explorer", style={"textAlign": "center"}),
        html.P(
            "The Johnson system of distributions uses a transformation to normality. "
            "Every distribution is defined by four parameters: "
            "γ (shape), δ (shape), ξ (location), and λ (scale), plus a subfamily type.",
            style={"textAlign": "center", "color": "#555", "marginBottom": "24px"},
        ),

        # Family selector
        html.Div([
            html.Label("Johnson Family", style={"fontWeight": "bold"}),
            dcc.Dropdown(
                id="family-type",
                options=[{"label": v, "value": k} for k, v in FAMILIES.items()],
                value="SU",
                clearable=False,
            ),
        ], style={"marginBottom": "24px"}),

        # Four Johnson parameter sliders
        html.Div([
            html.Div([
                html.Label("γ  (gamma) — shape", style={"fontWeight": "bold"}),
                dcc.Slider(id="slider-gamma", min=-5, max=5, step=0.05, value=0,
                           marks={i: str(i) for i in range(-5, 6)},
                           tooltip={"placement": "bottom", "always_visible": True}),
            ], style={"marginBottom": "20px"}),

            html.Div([
                html.Label("δ  (delta) — shape  [must be > 0]", style={"fontWeight": "bold"}),
                dcc.Slider(id="slider-delta", min=0.1, max=5, step=0.05, value=1,
                           marks={i: str(i) for i in range(0, 6)},
                           tooltip={"placement": "bottom", "always_visible": True}),
            ], style={"marginBottom": "20px"}),

            html.Div([
                html.Label("ξ  (xi) — location", style={"fontWeight": "bold"}),
                dcc.Slider(id="slider-xi", min=-10, max=10, step=0.1, value=0,
                           marks={i: str(i) for i in range(-10, 11, 2)},
                           tooltip={"placement": "bottom", "always_visible": True}),
            ], style={"marginBottom": "20px"}),

            html.Div([
                html.Label("λ  (lambda) — scale  [must be > 0]", style={"fontWeight": "bold"}),
                dcc.Slider(id="slider-lambda", min=0.1, max=10, step=0.1, value=1,
                           marks={i: str(i) for i in range(0, 11)},
                           tooltip={"placement": "bottom", "always_visible": True}),
            ], style={"marginBottom": "20px"}),
        ]),

        # Sample size
        html.Div([
            html.Label("Sample Size", style={"fontWeight": "bold"}),
            dcc.Slider(id="slider-n", min=500, max=20000, step=500, value=5000,
                       marks={i: str(i) for i in range(0, 20001, 5000)},
                       tooltip={"placement": "bottom", "always_visible": True}),
        ], style={"marginBottom": "24px"}),

        # Graphs
        dcc.Graph(id="hist-graph", style={"height": "480px"}),
        dcc.Graph(id="cdf-graph", style={"height": "340px"}),

        # Stats summary
        html.Div(id="stats-box", style={
            "background": "#f4f4f4", "borderRadius": "8px",
            "padding": "16px", "marginTop": "12px", "fontFamily": "monospace",
        }),

        # Transformation description
        html.Div(id="transform-box", style={
            "background": "#eef2ff", "borderRadius": "8px",
            "padding": "16px", "marginTop": "12px", "fontSize": "14px",
        }),
    ],
)


TRANSFORMS = {
    "SU": "z = γ + δ · sinh⁻¹((x − ξ) / λ)  →  z ~ N(0,1)",
    "SB": "z = γ + δ · ln((x − ξ) / (ξ + λ − x))  →  z ~ N(0,1)",
    "SL": "z = γ + δ · ln((x − ξ) / λ)  →  z ~ N(0,1)",
}


def build_johnson(family, gamma, delta, xi, lam, n):
    """Build a Johnson distribution and return (samples, x, pdf, rv)."""
    n = int(n)
    if family == "SU":
        rv = stats.johnsonsu(gamma, delta, loc=xi, scale=lam)
    elif family == "SB":
        rv = stats.johnsonsb(gamma, delta, loc=xi, scale=lam)
    else:  # SL — log-normal parameterised the Johnson way
        rv = stats.lognorm(s=1 / delta, scale=lam * np.exp(-gamma / delta), loc=xi)

    samples = rv.rvs(size=n)
    lo, hi = rv.ppf(0.001), rv.ppf(0.999)
    x = np.linspace(lo, hi, 500)
    pdf = rv.pdf(x)
    cdf = rv.cdf(x)
    return samples, x, pdf, cdf, rv


@app.callback(
    [Output("hist-graph", "figure"),
     Output("cdf-graph", "figure"),
     Output("stats-box", "children"),
     Output("transform-box", "children")],
    [Input("family-type", "value"),
     Input("slider-gamma", "value"),
     Input("slider-delta", "value"),
     Input("slider-xi", "value"),
     Input("slider-lambda", "value"),
     Input("slider-n", "value")],
)
def update_graphs(family, gamma, delta, xi, lam, n):
    samples, x, pdf, cdf, rv = build_johnson(family, gamma, delta, xi, lam, n)

    # --- Histogram + PDF ---
    fig1 = go.Figure()
    fig1.add_trace(go.Histogram(
        x=samples, nbinsx=80, histnorm="probability density",
        marker_color="rgba(99, 110, 250, 0.45)", name="Samples",
    ))
    fig1.add_trace(go.Scatter(
        x=x, y=pdf, mode="lines",
        line=dict(color="rgba(239, 85, 59, 1)", width=3), name="PDF",
    ))
    title = f"Johnson {family}  |  γ={gamma}  δ={delta}  ξ={xi}  λ={lam}"
    fig1.update_layout(
        title=title, xaxis_title="x", yaxis_title="Density",
        template="plotly_white", legend=dict(x=0.82, y=0.98),
        margin=dict(t=50, b=40),
    )

    # --- CDF ---
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=x, y=cdf, mode="lines",
        line=dict(color="rgba(0, 150, 136, 1)", width=3), name="CDF",
    ))
    fig2.update_layout(
        title="Cumulative Distribution Function",
        xaxis_title="x", yaxis_title="F(x)",
        template="plotly_white", margin=dict(t=50, b=40),
    )

    # --- Stats ---
    mean, var, skew, kurt = rv.stats(moments="mvsk")
    stats_text = (
        f"Mean: {float(mean):.4f}   |   "
        f"Variance: {float(var):.4f}   |   "
        f"Std Dev: {float(np.sqrt(var)):.4f}   |   "
        f"Skewness: {float(skew):.4f}   |   "
        f"Kurtosis: {float(kurt):.4f}   |   "
        f"Samples: {int(n)}"
    )

    # --- Transformation formula ---
    transform = html.Div([
        html.Strong("Johnson transformation:  "),
        html.Span(TRANSFORMS[family]),
    ])

    return fig1, fig2, stats_text, transform


if __name__ == "__main__":
    print("Starting dashboard at http://127.0.0.1:8050")
    app.run(debug=True)
