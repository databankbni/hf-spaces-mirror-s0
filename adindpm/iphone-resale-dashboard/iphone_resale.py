import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ===========================================================================
# VIZRO FRAMEWORK + DASH CUSTOMIZATION
# Strategi: Vizro digunakan sebagai foundation framework (server & app engine),
# kemudian layout-nya di-override sepenuhnya dengan custom layout Dash
# menggunakan vizro.Vizro().server untuk mempertahankan 100% UI yang sama.
# ===========================================================================

import vizro
from vizro import Vizro
Vizro._reset()
import vizro.models as vm
from dash import Dash, dcc, html, Input, Output, callback_context
import dash_bootstrap_components as dbc

# ===========================================================================
# VIZRO FRAMEWORK + DASH CUSTOMIZATION
# Strategi: Vizro digunakan sebagai foundation framework (server & app engine),
# kemudian layout-nya di-override sepenuhnya dengan custom layout Dash
# menggunakan vizro.Vizro().server untuk mempertahankan 100% UI yang sama.
# ===========================================================================

# %%
# Memuat data eksternal benchmark harga resale e-commerce iPhone USA tahun 2026
df_clean = pd.read_csv(
    "iphone_resale_clean.csv"
)

# ===========================================================================
# 1. PALET WARNA & URUTAN SESUAI UI MOCKUP
# ===========================================================================

WARNA_CUSTOM = {
    "Pro": "#17593A",
    "Standard": "#8EC4A7"
}

WARNA_KONDISI = {
    "New": "#17593A",
    "Open Box": "#0C783E",
    "Refurbished": "#0A9D45",
    "Second-hand": "#3CBF70",
    "Damaged": "#90CAA8"
}

WARNA_GENERASI = {
    "Latest (15+)": "#17593A",
    "Modern (13-14)": "#0A9D45",
    "Mid-Gen (11-12)": "#3CBF70",
    "Older (<11)": "#DCEFE4"
}

# ===========================================================================
# 2. HELPER FUNCTIONS UNTUK FORMAT CHART
# ===========================================================================

def format_storage_label(value):
    if pd.isna(value):
        return "Unknown"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)

    if value >= 1000 and value % 1000 == 0:
        tb = value / 1000
        return f"{int(tb)} TB" if tb.is_integer() else f"{tb:.1f} TB"
    return f"{int(value)} GB"


# ===========================================================================
# 3. GENERATOR FUNGSI GRAFIK
# ===========================================================================

def chart_model_price(df):
    model_df = (
        df.groupby(["model", "type"], as_index=False)["price"]
        .median()
    )

    # urutkan model berdasarkan median harga terbesar -> terkecil
    model_rank = (
        model_df.groupby("model", as_index=False)["price"]
        .median()
        .sort_values("price", ascending=False)
    )
    model_order = model_rank["model"].tolist()

    fig = px.bar(
        model_df,
        x="price",
        y="model",
        orientation="h",
        text=model_df["price"].map(lambda x: f"${x:,.0f}"),
        labels={
            "model": "Model iPhone",
            "price": "Median Harga (USD)",
            "type": "Tipe iPhone"
        },
        color_discrete_map=WARNA_CUSTOM,
        color="type",
        category_orders={
            "model": model_order
        }
    )

    fig.update_traces(textposition="outside", cliponaxis=False)

    fig.update_layout(
        margin=dict(b=40, t=50, l=20, r=20),
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.15,
            bgcolor="rgba(0,0,0,0)"
        ),
        font=dict(family="Inter, sans-serif", size=12, color="#111827")
    )

    fig.update_yaxes(
        automargin=True,
        tickfont=dict(size=10),
        categoryorder="array",
        categoryarray=model_order[::-1]
    )
    fig.update_xaxes(automargin=True, tickprefix="$", tickfont=dict(size=10))

    return fig


def chart_storage_impact(df):
    storage_df = df.copy()
    storage_df["storage_label"] = storage_df["storage"].apply(format_storage_label)

    storage_order = [
        format_storage_label(s)
        for s in sorted(storage_df["storage"].dropna().unique())
    ]

    agg = (
        storage_df.groupby(["storage", "storage_label", "type"], as_index=False)["price"]
        .median()
        .sort_values(["storage", "type"])
    )

    fig = px.bar(
        agg,
        x="storage_label",
        y="price",
        color="type",
        barmode="group",
        category_orders={"storage_label": storage_order},
        color_discrete_map=WARNA_CUSTOM,
        text=agg["price"].map(lambda x: f"${x:,.0f}"),
        labels={
            "storage_label": "Storage",
            "price": "Median Harga (USD)",
            "type": "Tipe iPhone"
        }
    )

    fig.update_layout(
        margin=dict(b=5, t=50, l=60, r=20),
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(0,0,0,0)"
        ),
        font=dict(family="Inter, sans-serif", size=12, color="#111827")
    )

    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_xaxes(automargin=True, tickfont=dict(size=9))
    fig.update_yaxes(automargin=True, tickfont=dict(size=9))
    return fig



def chart_heatmap_model_storage(df):
    storage_df = df.copy()
    storage_df["storage_label"] = storage_df["storage"].apply(format_storage_label)

    storage_order = [
        format_storage_label(s)
        for s in sorted(storage_df["storage"].dropna().unique())
    ]

    heatmap_df = (
        storage_df.groupby(["model", "storage_label"], as_index=False)["price"]
        .median()
    )

    pivot_heatmap = heatmap_df.pivot(
        index="model",
        columns="storage_label",
        values="price"
    ).reindex(columns=storage_order)

    fig = px.imshow(
        pivot_heatmap,
        text_auto=".0f",
        aspect="auto",
        color_continuous_scale=[
            "#C3E2CF",
            "#90CAA8",
            "#3CBF70",
            "#4FB778",
            "#0C783E"
        ],
        labels=dict(
            x="Storage",
            y="Model iPhone",
            color="Median (USD)"
        )
    )

    fig.update_traces(
        textfont=dict(size=9, color="#1F2937") 
    )

    fig.update_layout(
        margin=dict(l=20, r=20, t=35, b=20),
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=False,
        coloraxis_colorbar=dict(
            title="Median (USD)",
            thickness=14,
            len=0.78,
            x=1.1
        ),
        font=dict(family="Inter, sans-serif", size=12, color="#111827")
    )

    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=storage_order,
        automargin=True,
        tickfont=dict(size=10)
    )
    fig.update_yaxes(
        automargin=True,
        tickfont=dict(size=10)
    )

    return fig


def chart_condition_benchmark(df):
    fig = px.box(
        df,
        x="condition_group",
        y="price",
        color="condition_group",
        color_discrete_map=WARNA_KONDISI,
        labels={
            "condition_group": "Kondisi Kelompok",
            "price": "Harga (USD)"
        }
    )

    fig.update_layout(
        margin=dict(b=5, t=50, l=60, r=140),
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(0,0,0,0)"),
        font=dict(family="Inter, sans-serif", size=12, color="#111827")
    )

    fig.update_xaxes(automargin=True, tickfont=dict(size=9))
    fig.update_yaxes(automargin=True, tickfont=dict(size=9))

    return fig



def chart_generation_impact(df):
    fig = px.box(
        df,
        x="gen_group",
        y="price",
        color="gen_group",
        color_discrete_map=WARNA_GENERASI,
        labels={
            "gen_group": "Generasi",
            "price": "Harga (USD)"
        },
        category_orders={
            "gen_group": [
            "Mid-Gen (11-12)",
            "Modern (13-14)",
            "Latest (15+)"
            ]
        }
)

    fig.update_layout(
        margin=dict(b=5, t=50, l=60, r=140),
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(0,0,0,0)"),
        font=dict(family="Inter, sans-serif", size=12, color="#111827")
    )

    fig.update_xaxes(automargin=True, tickfont=dict(size=9))
    fig.update_yaxes(automargin=True, tickfont=dict(size=9))

    return fig


def chart_location_benchmark(df):
    top_states = (
        df["state_full"]
        .value_counts()
        .nlargest(10)
        .index
    )

    df_top_loc = df[df["state_full"].isin(top_states)].copy()

    agg = (
        df_top_loc.groupby(["state_full", "type"], as_index=False)["price"]
        .median()
    )

    fig = px.bar(
        agg,
        x="state_full",
        y="price",
        color="type",
        barmode="group",
        category_orders={"state_full": list(top_states)},
        color_discrete_map=WARNA_CUSTOM,
        text=agg["price"].map(lambda x: f"${x:,.0f}"),
        labels={
            "state_full": "Wilayah",
            "price": "Median Harga (USD)",
            "type": "Tipe iPhone"
        }
    )

    fig.update_layout(
        margin=dict(b=5, t=50, l=60, r=20),
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(0,0,0,0)"
        ),
        font=dict(family="Inter, sans-serif", size=12, color="#111827")
    )

    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_xaxes(automargin=True, tickfont=dict(size=10))
    fig.update_yaxes(automargin=True, tickfont=dict(size=9))
    return fig


def apply_figure_theme(fig, theme="light"):
    if theme == "dark":
        template = "plotly_dark"
        paper_bg = "rgba(0,0,0,0)"
        plot_bg = "rgba(0,0,0,0)"
        text_color = "#F4F7F5"
        grid_color = "rgba(255,255,255,0.08)"
        axis_color = "#D7E3DB"
        legend_font = "#F4F7F5"
    else:
        template = "plotly_white"
        paper_bg = "rgba(255,255,255,0)"
        plot_bg = "rgba(255,255,255,0)"
        text_color = "#111827"
        grid_color = "#E8EFEA"
        axis_color = "#294032"
        legend_font = "#111827"

    fig.update_layout(
        template=template,
        paper_bgcolor=paper_bg,
        plot_bgcolor=plot_bg,
        font=dict(family="Inter, sans-serif", size=12, color=text_color),
        legend=dict(font=dict(color=legend_font)),
    )
    fig.update_xaxes(
        gridcolor=grid_color,
        linecolor=axis_color,
        tickfont=dict(color=axis_color),
        title_font=dict(color=axis_color),
        zerolinecolor=grid_color,
    )
    fig.update_yaxes(
        gridcolor=grid_color,
        linecolor=axis_color,
        tickfont=dict(color=axis_color),
        title_font=dict(color=axis_color),
        zerolinecolor=grid_color,
    )
    return fig


CUSTOM_CSS = """
:root {
    --green-900: #17593A;
    --green-800: #1F6A47;
    --green-700: #2A7C55;
    --green-600: #3D8D67;
    --green-500: #5BA07F;
    --green-400: #8EC4A7;
    --green-300: #B7DCC4;
    --green-200: #DDF0E4;
    --green-100: #F1FAF4;
    --bg: #FFFFFF;
    --shell: #F9F9F9;
    --panel: #FFFFFF;
    --card: #FFFFFF;
    --card-strong: #17593A;
    --text: #111827;
    --muted: #6B7280;
    --border: #E5E7EB;
    --shadow: 0 10px 30px rgba(16, 24, 40, 0.06);
}

body, .dash-application {
    margin: 0 !important;
    background: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* ── VIZRO OVERRIDE: sembunyikan semua elemen UI bawaan Vizro ── */
#vizro-header,
#vizro-nav,
.vizro-page-header,
.nav-bar,
[data-dash-is-loading="true"] > .dash-spinner {
    display: none !important;
}

/* Biarkan Vizro container tetap full-screen */
#dashboard-container,
#vizro-page-0,
.page-main,
.vizro {
    padding: 0 !important;
    margin: 0 !important;
    max-width: none !important;
    background: transparent !important;
}

.theme-light {
    --bg: #FFFFFF;
    --shell: #F9F9F9;
    --panel: #FFFFFF;
    --card: #FFFFFF;
    --card-strong: #17593A;
    --text: #111827;
    --muted: #667085;
    --border: #E5E7EB;
    --shadow: 0 10px 30px rgba(16, 24, 40, 0.06);
    --chip-bg: #FFFFFF;
    --chip-text: #111827;
    --info-bg: #D1E7DD66;   
    --info-border: #E5E7EB;
}

.theme-dark {
    --bg: #0B1110;
    --shell: #111916;
    --panel: #13201B;
    --card: #14231E;
    --card-strong: #17593A;
    --text: #F4F7F5;
    --muted: #9EB1A6;
    --border: #21332B;
    --shadow: 0 12px 28px rgba(0, 0, 0, 0.28);
    --chip-bg: #182621;
    --chip-text: #F4F7F5;
    --info-bg: #1A2722;    
    --info-border: #21332B;
}

#app-root {
    min-height: 100vh;
    background: var(--bg);
    padding: 14px;
    box-sizing: border-box;
    zoom: 0.8;
}

.app-shell {
    min-height: calc(100vh - 28px);
    width: 100%;
    display: flex;
    flex-direction: row;
    flex-wrap: nowrap;
    gap: 16px;
    align-items: stretch;
    background: var(--shell);
    border-radius: 28px;
    padding: 16px;
    box-sizing: border-box;
}

.sidebar-panel {
    width: 280px;
    flex: 0 0 280px;
    min-width: 280px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 24px;
    box-shadow: var(--shadow);
    padding: 20px 18px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    gap: 18px;
    position: sticky;
    top: 14px;
    height: calc(120vh - 35px);
    overflow: auto;
}

.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 4px 20px;
    margin-bottom: 8px;
    border-bottom: 1px solid var(--border);
}

.sidebar-logo {
    width: 52px;
    height: 52px;
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, #17593A, #2A7C55);
    color: #FFFFFF;
    font-size: 22px;
    box-shadow: 0 10px 20px rgba(23, 89, 58, 0.18);
    flex-shrink: 0;
}

.sidebar-brand-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.brand-title {
    font-size: 18px;
    font-weight: 800;
    color: var(--text);
    line-height: 1.1;
}

.brand-subtitle {
    font-size: 12px;
    color: var(--muted);
    line-height: 1.2;
}

.filter-stack {
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-top: 2px;
}

.filter-item {
    display: flex;
    flex-direction: column;
    gap: 7px;
}

.filter-label {
    font-size: 12px;
    font-weight: 700;
    color: var(--text);
    margin: 0;
}

.reset-btn {
    width: 100%; 
    box-sizing: border-box;
    margin-top: 12px;
    background: #FEF2F2;
    border: 1px solid #FCA5A5; 
    color: #DC2626; 
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    padding: 10px 16px;
    border-radius: 10px; 
    transition: all 0.2s ease;
    display: flex;
    justify-content: center;
    align-items: center;
}

/* Efek animasi saat mouse diarahkan ke tombol */
.reset-btn:hover {
    background: #FEE2E2; 
    border-color: #F87171;
    transform: translateY(-1px); /* Efek tombol sedikit terangkat */
    box-shadow: 0 4px 12px rgba(220, 38, 38, 0.1);
}

.reset-btn:active {
    transform: translateY(0); /* Efek saat ditekan */
}

.dashboard-panel {
    flex: 1;
    min-width: 0;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 24px;
    box-shadow: var(--shadow);
    padding: 22px 22px 24px;
    box-sizing: border-box;
    overflow: hidden;
}

.topbar {
    display: flex;
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    margin-bottom: 18px;
}

.dashboard-heading {
    margin: 0;
    font-size: 34px;
    line-height: 1.08;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: var(--text);
}

.dashboard-subtitle {
    margin: 6px 0 0 0;
    font-size: 13px;
    color: var(--muted);
}

.dashboard-info {
    display: flex;
    align-items: center;
    gap: 12px;
    background-color: var(--info-bg);
    border: 1px solid var(--info-border);
    border-radius: 8px;
    padding: 14px 16px;
    margin-bottom: 24px;
}

.info-icon {
    color: var(--muted);
    font-size: 16px;
}

.info-text {
    color: var(--muted);
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
}

.theme-toggle-container {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
}

.theme-chip {
    border: 1px solid var(--border);
    background: var(--chip-bg);
    color: var(--chip-text);
    border-radius: 999px;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    transition: transform 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.theme-chip:hover {
    transform: translateY(-1px);
}

.theme-chip.active {
    background: var(--green-900);
    border-color: var(--green-900);
    color: #FFFFFF;
}

.kpi-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 18px;
    margin-bottom: 18px;
    min-width: 0;
}

.kpi-card {
    background: var(--card-strong);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 18px;
    padding: 16px 16px;
    box-shadow: 0 12px 28px rgba(23, 89, 58, 0.18);
    color: #FFFFFF;
    min-height: 118px;
    position: relative;
    overflow: hidden;
}

.kpi-card::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(255,255,255,0.08), rgba(255,255,255,0));
    pointer-events: none;
}

.kpi-card-content {
    display: flex;
    align-items: center;
    gap: 16px;
    height: 100%;
}

.kpi-text {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 6px;
    padding-bottom: 12px;
}

.kpi-icon-box {
    width: 52px;
    height: 52px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.14);
}

.kpi-icon {
    font-size: 24px;
    color: white;
}

.kpi-label {
    font-size: 11px;
    font-weight: 600;
    color: rgba(255,255,255,0.82);
    margin-bottom: 4px;
}

.kpi-value {
    font-size: 28px;
    font-weight: 600;
    line-height: 1.05;
    color: #FFFFFF;
}

.chart-grid-2 {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
    margin-bottom: 18px;
    min-width: 0;
}

.chart-card-full {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 18px 18px 14px;
    min-height: 420px;
    min-width: 0;
    box-shadow: 0 6px 18px rgba(16, 24, 40, 0.04);
    overflow: hidden;
    margin-bottom: 20px;
}

.chart-header {
    margin-bottom: 10px;
}

.chart-title {
    font-size: 13px;
    font-weight: 800;
    color: var(--text);
}

.chart-desc {
    font-size: 11px;
    color: var(--muted);
    margin-top: 4px;
}

.responsive-heatmap {
    height: 360px !important;
}

/* =========================================
   ACCORDION & RESPONSIVE MEDIA QUERIES
   ========================================= */

/* Default Desktop: Tombol menu disembunyikan */
.filter-summary {
    display: none;
}
.filter-wrapper {
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-top: -8px;
}

.filter-wrapper.show-mobile {
    display: flex !important;
}

/* Paksa filter selalu muncul di Desktop walau atribut <details> tertutup */
@media (min-width: 1025px) {
    .filter-container:not([open]) .filter-wrapper {
        display: flex !important;
    }
}

/* =========================================
   TAMBAHAN CSS LOGO MOBILE
   ========================================= */
.mobile-logo { display: none; } /* Pastikan logo ganda hilang di Desktop */
.topbar-left { display: flex; align-items: center; gap: 16px; }

/* --- UKURAN TABLET (1024px) --- */
@media (max-width: 1024px) {
    /* Pindah Logo ke Judul */
    .mobile-logo { display: flex; width: 44px; height: 44px; font-size: 18px; flex-shrink: 0; }
    .sidebar-brand > .sidebar-logo { display: none; } /* Hilangkan logo lama */
    .sidebar-brand { border-bottom: none; padding-bottom: 0; }

    .app-shell { flex-direction: column; gap: 16px; }
    .sidebar-panel { width: 100%; min-width: 0; flex: none; position: relative; top: auto; height: auto; overflow: visible; padding: 20px; }
    .filter-summary { display: flex; justify-content: space-between; align-items: center; background: var(--card-strong); color: #FFFFFF; padding: 12px 18px; border-radius: 12px; font-size: 14px; font-weight: 700; cursor: pointer; list-style: none; box-shadow: 0 4px 12px rgba(23, 89, 58, 0.15); }
    .filter-summary::-webkit-details-marker { display: none; }
    .toggle-icon { transition: transform 0.3s ease; }
    .filter-container[open] .toggle-icon { transform: rotate(180deg); }
    .filter-wrapper { display: none; padding-top: 18px; gap: 14px; }
    .filter-stack { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
    .reset-btn { grid-column: 1 / -1; }
    .dashboard-panel { width: 100%; min-width: 0; }
    .kpi-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .chart-grid-2 { grid-template-columns: 1fr; }
}

/* --- UKURAN HP (768px) */
@media (max-width: 768px) {
    #app-root { padding: 4px; zoom: 1 !important; }
    .app-shell { padding: 8px; gap: 12px; display: flex; flex-direction: column; background: transparent; }
    .sidebar-panel, .dashboard-panel { display: contents; }

    /* ORDER 1: Topbar */
    .topbar { 
        order: 1; background: var(--panel); border-radius: 16px; padding: 14px 12px; margin-bottom: 0; 
        border: 1px solid var(--border); flex-wrap: nowrap !important; align-items: center; gap: 8px;
    }
    .topbar-left { gap: 10px; } 
    .mobile-logo { width: 38px; height: 38px; font-size: 16px; border-radius: 12px; }
    .dashboard-heading { font-size: 15px !important; line-height: 1.2; }
    .theme-toggle-container { flex-shrink: 0; }

    /* ORDER 2 & 3: Info & KPI Card */
    .dashboard-info { order: 2; margin-bottom: 0; }
    .kpi-row { order: 3; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)) !important; gap: 10px; margin-bottom: 0; }
    .kpi-card { padding: 12px 10px; min-height: 90px; border-radius: 14px;}
    .kpi-icon-box { width: 34px; height: 34px; border-radius: 8px;}
    .kpi-icon { font-size: 16px; }
    .kpi-text { padding-bottom: 0; gap: 4px;}
    .kpi-label { font-size: 9.5px; line-height: 1.1; margin-bottom: 2px;}
    .kpi-value { font-size: 20px; }

    /* ORDER 4 & 5: MERGE TITLE DAN KOTAK FILTER */
    .sidebar-brand { 
        order: 4; 
        background: var(--panel); 
        border: 1px solid var(--border); 
        border-bottom: none; 
        border-radius: 16px 16px 0 0; 
        padding: 14px 14px 4px 14px; 
        /* SIHIR CSS: Menarik kotak di bawahnya ke atas agar celah gap 12px tertutup */
        margin-bottom: -12px !important; 
        z-index: 2;
    }
    .sidebar-brand > .sidebar-logo { display: none; }

    .filter-container { 
        order: 5; 
        background: var(--panel); 
        border: 1px solid var(--border); 
        border-top: none; 
        border-radius: 0 0 16px 16px; 
        padding: 4px 14px 14px 14px; 
        margin-bottom: 0; 
    }
    .filter-stack { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px;}
    
    /* ORDER 6: Semua Grafik */
    .chart-grid-2, .chart-card-full { 
        order: 6; gap: 12px; margin-bottom: 12px !important;
        padding: 12px 4px 8px !important; border-radius: 16px; 
    }
    .chart-header {
        padding-left: 12px;
        padding-right: 12px;
    }
    .responsive-heatmap {
        height: 500px !important;
    }
}

/* --- HP LAYAR SANGAT KECIL (<480px) --- */
@media (max-width: 480px) {
    .filter-stack { grid-template-columns: minmax(0, 1fr); }
    .dashboard-heading { font-size: 14px !important; }
}

/* Tombol Reset saat mati (resmi dinonaktifkan HTML) */
.reset-btn:disabled {
    background: transparent !important;
    border: 1px dashed var(--muted) !important;
    color: var(--muted) !important;
    opacity: 0.5;
    cursor: not-allowed;
    animation: none;
}

/* Tombol Reset saat menyala */
.reset-btn.active-filter {
    background: #FEF2F2 !important;
    border: 1px solid #DC2626 !important;
    color: #DC2626 !important;
    font-weight: 800 !important;
    animation: pulse-red 1.5s infinite; 
}

@keyframes pulse-red {
    0% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.4); }
    70% { box-shadow: 0 0 0 8px rgba(220, 38, 38, 0); }
    100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); }
}



"""


# ===========================================================================
# 4. VIZRO APP SETUP
# ===========================================================================
# Vizro.build() menginisialisasi Vizro framework (Dash server + assets pipeline
# + Vizro CSS/JS). Kita ambil .server (Flask) dan .layout dari sini,
# lalu replace .layout dengan custom layout kita — sehingga 100% UI kita
# berjalan di atas Vizro engine, bukan Dash biasa.
# ===========================================================================

# Buat Vizro dashboard minimal sebagai "container" untuk framework-nya
vizro_dashboard = vm.Dashboard(theme="vizro_light", pages=[vm.Page(
    title="iPhone Resale Benchmark",
    components=[
        vm.Card(text=" ") 
    ]
)])
vizro_app = Vizro().build(vizro_dashboard)

# Ambil Dash app yang dibangun oleh Vizro
app = vizro_app.dash

# Inject CSS kustom kita ke dalam index HTML Vizro
# (Vizro sudah punya index_string bawaan; kita extend dengan style tag)
original_index = app.index_string
app.index_string = original_index.replace(
    "</head>",
    "<style>" + CUSTOM_CSS + "</style>\n</head>"
).replace(
    "Bootstrap Icons",
    "Bootstrap Icons"
)

# Tambahkan Bootstrap Icons CDN 
app.index_string = app.index_string.replace(
    "{%css%}",
    """{%css%}
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">"""
)

# ===========================================================================
# 5. KPI METRICS 
# ===========================================================================

median_price = round(df_clean["price"].median(), 0)

top_model = (
    df_clean.groupby("model")["price"]
    .median()
    .sort_values(ascending=False)
    .index[0]
)

top_condition = (
    df_clean.groupby("condition_group")["price"]
    .median()
    .idxmax()
)

top_storage = (
    df_clean.groupby("storage")["price"]
    .median()
    .idxmax()
)

# ===========================================================================
# 6. DROPDOWN OPTION HELPERS
# ===========================================================================

def _storage_options():
    return [
        {"label": "Semua Kapasitas", "value": "all"}
    ] + [
        {"label": f"{int(s)}GB" if s < 1000 else f"{int(s/1000)}TB", "value": s}
        for s in sorted(df_clean["storage"].dropna().unique())
    ]

def _model_options():
    return [{"label": "Semua Model", "value": "all"}] + [
        {"label": m, "value": m}
        for m in sorted(df_clean["model"].dropna().unique())
    ]

def _condition_options():
    return [{"label": "Semua Kondisi", "value": "all"}] + [
        {"label": c, "value": c}
        for c in sorted(df_clean["condition_group"].dropna().unique())
    ]

def _generation_options():
    return [{"label": "Semua Generasi", "value": "all"}] + [
        {"label": g, "value": g}
        for g in sorted(df_clean["gen_group"].dropna().unique())
    ]

def _state_options():
    return [{"label": "Semua Wilayah", "value": "all"}] + [
        {"label": s, "value": s}
        for s in sorted(df_clean["state_full"].dropna().unique())
    ]

# ===========================================================================
# 7. CUSTOM LAYOUT
# ===========================================================================

app.layout = html.Div(
    id="app-root",
    className="theme-light",
    children=[
        dcc.Store(id="theme-store", data="light"),

        html.Div(className="app-shell", children=[
            html.Div(className="sidebar-panel", children=[
                html.Div(className="sidebar-brand", children=[
                    html.Div(className="sidebar-logo", children=[
                        html.I(className="bi bi-graph-up-arrow")
                    ]),
                    html.Div(className="sidebar-brand-text", children=[
                        html.Div("Filter Dashboard", className="brand-title"),
                        html.Div("Pilih filter sesuai kebutuhan", className="brand-subtitle"),
                    ]),
                ]),

                html.Div(
                    className="filter-container",
                    children=[
                        # Tombol Menu (Hanya Muncul di HP/Tablet)
                        html.Div(
                            id="btn-mobile-menu", 
                            className="filter-summary", 
                            n_clicks=0, 
                            children=[
                                html.Span(children=[
                                    html.I(className="bi bi-funnel-fill", style={"marginRight": "8px"}),
                                    "Filter"
                                ]),
                                html.I(id="icon-mobile-menu", className="bi bi-chevron-down toggle-icon")
                            ]
                        ),
                        
                        # Isi Filter
                        html.Div(
                            id="mobile-filter-wrapper", 
                            className="filter-wrapper", 
                            children=[
                                html.Div(className="filter-stack", children=[
                                    html.Div(className="filter-item", children=[
                                        html.Div("Model", className="filter-label"),
                                        dcc.Dropdown(
                                            id="drop-model",
                                            options=_model_options(),
                                            value="all",
                                            clearable=False,
                                        ),
                                    ]),
                                    html.Div(className="filter-item", children=[
                                        html.Div("Kapasitas Penyimpanan", className="filter-label"),
                                        dcc.Dropdown(
                                            id="drop-storage",
                                            options=_storage_options(),
                                            value="all",
                                            clearable=False,
                                        ),
                                    ]),
                                    html.Div(className="filter-item", children=[
                                        html.Div("Kondisi", className="filter-label"),
                                        dcc.Dropdown(
                                            id="drop-condition",
                                            options=_condition_options(),
                                            value="all",
                                            clearable=False,
                                        ),
                                    ]),
                                    html.Div(className="filter-item", children=[
                                        html.Div("Generasi", className="filter-label"),
                                        dcc.Dropdown(
                                            id="drop-gen",
                                            options=_generation_options(),
                                            value="all",
                                            clearable=False,
                                        ),
                                    ]),
                                    html.Div(className="filter-item", children=[
                                        html.Div("Wilayah", className="filter-label"),
                                        dcc.Dropdown(
                                            id="drop-state",
                                            options=_state_options(),
                                            value="all",
                                            clearable=False,
                                        ),
                                    ]),
                                ]),
                                html.Button("Reset Filter", id="btn-reset-filters", className="reset-btn"),
                            ]
                        )
                    ]
                ),
            ]),
            

            html.Div(className="dashboard-panel", children=[
                html.Div(className="topbar", children=[
                    
                    html.Div(className="topbar-left", children=[
                        
                        html.Div(className="sidebar-logo mobile-logo", children=[
                            html.I(className="bi bi-graph-up-arrow")
                        ]),
                        html.H1("Dashboard iPhone Resale Benchmark", className="dashboard-heading"),
                    ]),
                
                    html.Div(className="theme-toggle-container", children=[
                        html.Button("Light", id="btn-light", className="theme-chip active"),
                        html.Button("Dark", id="btn-dark", className="theme-chip"),
                    ]),
                ]),

            html.Div(
                    className="dashboard-info",
                    children=[
                        html.I(className="bi bi-info-circle-fill info-icon"),
                        html.Span(
                            "Dashboard ini menyajikan benchmark harga resale iPhone dari 1.893 data e-commerce yang telah dibersihkan. Gunakan filter yang tersedia untuk membandingkan harga berdasarkan model, kapasitas penyimpanan, kondisi, generasi, dan wilayah.",
                            className="info-text",
                        ),
                    ],
                ),

                # ROW 1 — KPI Cards
                html.Div(className="kpi-row", children=[
                    html.Div(className="kpi-card", children=[
                        html.Div(className="kpi-card-content", children=[
                            html.Div(
                                html.I(className="bi bi-cash-stack kpi-icon"),
                                className="kpi-icon-box"
                            ),
                            html.Div(className="kpi-text", children=[
                                html.Div("Median Harga Resale", className="kpi-label"),
                                html.Div(f"${median_price:,.0f}", className="kpi-value"),
                            ])
                        ])
                    ]),

                    html.Div(className="kpi-card", children=[
                        html.Div(className="kpi-card-content", children=[
                            html.Div(
                                html.I(className="bi bi-phone kpi-icon"),
                                className="kpi-icon-box"
                            ),
                            html.Div(className="kpi-text", children=[
                                html.Div("Model dengan Harga Tertinggi", className="kpi-label"),
                                html.Div(top_model, className="kpi-value"),
                            ])
                        ])
                    ]),

                    html.Div(className="kpi-card", children=[
                        html.Div(className="kpi-card-content", children=[
                            html.Div(
                                html.I(className="bi bi-shield kpi-icon"),
                                className="kpi-icon-box"
                            ),
                            html.Div(className="kpi-text", children=[
                                html.Div("Kondisi dengan Harga Tertinggi", className="kpi-label"),
                                html.Div(top_condition, className="kpi-value"),
                            ])
                        ])
                    ]),

                    html.Div(className="kpi-card", children=[
                        html.Div(className="kpi-card-content", children=[
                            html.Div(
                                html.I(className="bi bi-memory kpi-icon"),
                                className="kpi-icon-box"
                            ),
                            html.Div(className="kpi-text", children=[
                                html.Div("Kapasitas Penyimpanan dengan Harga Tertinggi", className="kpi-label"),
                                html.Div(f"{top_storage} GB", className="kpi-value"),
                            ])
                        ])
                    ]),
                ]),

                # ROW 2 — Model & Storage Charts
                html.Div(className="chart-grid-2", children=[
                    html.Div(className="chart-card-full", children=[
                        html.Div([
                            html.Div("Perbandingan Median Harga Resale berdasarkan Model", className="chart-title"),
                            html.Div("Menampilkan median harga resale setiap model iPhone yang dikelompokkan berdasarkan tipe perangkat.", className="chart-desc")
                        ], className="chart-header"),
                        dcc.Graph(
                            id="graph-model",
                            config={"displayModeBar": True, "displaylogo": False, "responsive": True},
                            style={"height": "360px"}
                        ),
                    ]),

                    html.Div(className="chart-card-full", children=[
                        html.Div([
                            html.Div("Perbandingan Median Harga Resale berdasarkan Kapasitas Penyimpanan", className="chart-title"),
                            html.Div("Menampilkan median harga resale berdasarkan kapasitas penyimpanan yang dikelompokkan berdasarkan tipe perangkat.", className="chart-desc")
                        ], className="chart-header"),
                        dcc.Graph(
                            id="graph-storage",
                            config={"displayModeBar": True, "displaylogo": False, "responsive": True},
                            style={"height": "360px"}
                        ),
                    ])
                ]),

                # ROW 3 — Heatmap Full Width
                html.Div(className="chart-card-full", children=[
                    html.Div([
                        html.Div("Perbandingan Median Harga Resale berdasarkan Model dan Kapasitas Penyimpanan", className="chart-title"),
                        html.Div("Menampilkan median harga resale berdasarkan kombinasi model iPhone dan kapasitas penyimpanan, dengan warna yang semakin gelap menunjukkan harga yang semakin tinggi.", className="chart-desc")
                    ], className="chart-header"),
                    dcc.Graph(
                        id="graph-heatmap",
                        config={"displayModeBar": True, "displaylogo": False, "responsive": True},
                        className="responsive-heatmap"
                    ),
                ]),

                # ROW 4 — Condition & Generation Charts
                html.Div(className="chart-grid-2", children=[
                    html.Div(className="chart-card-full", children=[
                        html.Div([
                            html.Div("Perbandingan Median Harga Resale berdasarkan Kondisi", className="chart-title"),
                            html.Div("Menampilkan sebaran harga resale berdasarkan kondisi produk.", className="chart-desc")
                        ], className="chart-header"),
                        dcc.Graph(
                            id="graph-condition",
                            config={"displayModeBar": True, "displaylogo": False, "responsive": True},
                            style={"height": "360px"}
                        ),
                    ]),

                    html.Div(className="chart-card-full", children=[
                        html.Div([
                            html.Div("Perbandingan Median Harga Resale berdasarkan Generasi", className="chart-title"),
                            html.Div("Menampilkan sebaran harga resale berdasarkan generasi iPhone.", className="chart-desc")
                        ], className="chart-header"),
                        dcc.Graph(
                            id="graph-generation",
                            config={"displayModeBar": True, "displaylogo": False, "responsive": True},
                            style={"height": "360px"}
                        ),
                    ])
                ]),

                # ROW 5 — Location Full Width
                html.Div(className="chart-card-full", children=[
                    html.Div([
                        html.Div("Perbandingan Median Harga Resale berdasarkan Wilayah", className="chart-title"),
                        html.Div("Menampilkan median harga resale berdasarkan wilayah penjualan.", className="chart-desc")
                    ], className="chart-header"),
                    dcc.Graph(
                        id="graph-location",
                        config={"displayModeBar": True, "displaylogo": False, "responsive": True},
                        style={"height": "360px"}
                    ),
                ]),
            ]),
        ]),
    ]
)

# ===========================================================================
# 8. CALLBACKS 
# ===========================================================================

@app.callback(
    Output("theme-store", "data"),
    Input("btn-light", "n_clicks"),
    Input("btn-dark", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_theme(n_light, n_dark):
    if not callback_context.triggered:
        return "light"
    triggered = callback_context.triggered[0]["prop_id"].split(".")[0]
    if triggered == "btn-dark":
        return "dark"
    return "light"


@app.callback(
    Output("app-root", "className"),
    Input("theme-store", "data"),
)
def sync_theme_class(theme):
    return f"theme-{theme}"


@app.callback(
    Output("btn-light", "className"),
    Output("btn-dark", "className"),
    Input("theme-store", "data"),
)
def sync_theme_buttons(theme):
    return (
        "theme-chip active" if theme == "light" else "theme-chip",
        "theme-chip active" if theme == "dark" else "theme-chip",
    )


@app.callback(
    Output("graph-model", "figure"),
    Output("graph-condition", "figure"),
    Output("graph-heatmap", "figure"),
    Output("graph-storage", "figure"),
    Output("graph-generation", "figure"),
    Output("graph-location", "figure"),
    Input("drop-model", "value"),
    Input("drop-storage", "value"),
    Input("drop-condition", "value"),
    Input("drop-gen", "value"),
    Input("drop-state", "value"),
    Input("theme-store", "data"),
)
def update_dashboard_charts(mdl, stg, cnd, gn, stt, theme):
    dff = df_clean.copy()

    if mdl != "all":
        dff = dff[dff["model"] == mdl]
    if stg != "all":
        dff = dff[dff["storage"] == stg]
    if cnd != "all":
        dff = dff[dff["condition_group"] == cnd]
    if gn != "all":
        dff = dff[dff["gen_group"] == gn]
    if stt != "all":
        dff = dff[dff["state_full"] == stt]

    model_fig      = apply_figure_theme(chart_model_price(dff), theme)
    condition_fig  = apply_figure_theme(chart_condition_benchmark(dff), theme)
    heatmap_fig    = apply_figure_theme(chart_heatmap_model_storage(dff), theme)
    storage_fig    = apply_figure_theme(chart_storage_impact(dff), theme)
    generation_fig = apply_figure_theme(chart_generation_impact(dff), theme)
    location_fig   = apply_figure_theme(chart_location_benchmark(dff), theme)

    return (
        model_fig,
        condition_fig,
        heatmap_fig,
        storage_fig,
        generation_fig,
        location_fig,
    )


@app.callback(
    Output("drop-model", "value"),
    Output("drop-storage", "value"),
    Output("drop-condition", "value"),
    Output("drop-gen", "value"),
    Output("drop-state", "value"),
    Input("btn-reset-filters", "n_clicks"),
    prevent_initial_call=True,
)
def execute_reset_filters(n_clicks):
    # Ketika tombol diklik, kembalikan semua value dropdown ke "all"
    if n_clicks:
        return "all", "all", "all", "all", "all"
    
    # Mencegah error saat pertama kali web dimuat
    from dash import no_update
    return no_update, no_update, no_update, no_update, no_update


@app.callback(
    Output("mobile-filter-wrapper", "className"),
    Output("icon-mobile-menu", "className"),
    Input("btn-mobile-menu", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_mobile_menu(n_clicks):
    if n_clicks is None:
        n_clicks = 0
        
    if n_clicks % 2 != 0:
        return "filter-wrapper show-mobile", "bi bi-chevron-up toggle-icon"

    return "filter-wrapper", "bi bi-chevron-down toggle-icon"

@app.callback(
    Output("btn-reset-filters", "disabled"),
    Output("btn-reset-filters", "children"),
    Output("btn-reset-filters", "className"),
    Input("drop-model", "value"),
    Input("drop-storage", "value"),
    Input("drop-condition", "value"),
    Input("drop-gen", "value"),
    Input("drop-state", "value"),
)
def update_filter_indicator(mdl, stg, cnd, gn, stt):
    # Mengecek apakah ada setidaknya 1 filter yang aktif
    is_filtered = any(v != "all" for v in [mdl, stg, cnd, gn, stt])
    
    # JIKA ADA FILTER AKTIF:
    if is_filtered:
        return (
            False,                                  # 1. Disabled = False (Tombol bisa diklik)
            "Reset Filter",                 # 2. Teks tombol berubah
            "reset-btn active-filter"               # 3. Tombol jadi merah menyala
        )
    
    # JIKA TIDAK ADA FILTER AKTIF (Kondisi Awal):
    return (
        True,                                       # 1. Disabled = True (Tombol dimatikan)
        "Reset Filter",                             # 2. Teks tombol normal
        "reset-btn"                                 # 3. Class normal (CSS :disabled otomatis jalan)
    )
    
# ===========================================================================
# 9. RUN
# ===========================================================================
server = app.server

if __name__ == "__main__":
   
    vizro_app.run(port=8062)