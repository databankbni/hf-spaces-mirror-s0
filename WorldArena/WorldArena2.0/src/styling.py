from typing import Dict, Optional

import pandas as pd

from .data_loader import DIMENSION_METRICS


def dataframe_to_html(
    df: pd.DataFrame,
    column_label_map: Optional[Dict[str, str]] = None,
) -> str:
    if df.empty:
        return "<div class='no-data'>No data available</div>"

    column_label_map = column_label_map or {}
    headers = df.columns.tolist()
    html = """
    <div class="academic-table-container">
      <table class="academic-table"><thead><tr>
    """

    for header in headers:
        display_header = column_label_map.get(header, header)
        if header == "Model":
            css_class = "model-header"
        elif header == "EWMScore":
            css_class = "primary-metric"
        elif header == "Rank":
            css_class = "rank-header"
        elif header in DIMENSION_METRICS:
            css_class = "dimension-metric-header"
        else:
            css_class = ""
        html += f'<th class="{css_class}">{display_header}</th>'

    html += "</tr></thead><tbody>"
    for row_index, (_, row) in enumerate(df.iterrows()):
        html += f'<tr class="{"even-row" if row_index % 2 == 0 else "odd-row"}">'
        for column in headers:
            value = str(row[column])
            if column == "Model":
                css_class = "model-cell"
            elif column == "EWMScore":
                css_class = "primary-metric-cell"
            elif column == "Rank":
                css_class = "rank-cell"
            elif column in DIMENSION_METRICS:
                css_class = "dimension-metric-cell"
            else:
                css_class = "regular-cell"

            if "**" in value:
                value = value.replace("**", "")
                css_class += " best-score"
                value = f'{value}<span class="score-trophy">🏆</span>'
            elif "<u>" in value:
                value = value.replace("<u>", "").replace("</u>", "")
                css_class += " second-best"
            html += f'<td class="{css_class}">{value}</td>'
        html += "</tr>"

    return html + "</tbody></table></div>"


def get_academic_css() -> str:
    return """
    @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@300;400;500;600;700;800;900&display=swap');

    :root {
      --wa-green: #B8D9A8;
      --wa-green-dark: #719663;
      --wa-green-light: #EEF7EA;
      --wa-purple: #B5A8E5;
      --wa-blue: #8EC5E8;
      --wa-text: #253238;
      --wa-muted: #5b6670;
      --wa-border: rgba(37, 50, 56, 0.12);
      --wa-card: rgba(255, 255, 255, 0.82);
      --wa-shadow: 0 18px 45px rgba(35, 54, 34, 0.12);
    }

    body, .gradio-container {
      font-family: "Rubik", sans-serif !important;
      color: var(--wa-text);
      background: radial-gradient(circle at top, #EEF7EA 0%, #DCEFD2 35%, #F7FAF5 100%) !important;
      min-height: 100vh;
    }

    body {
      display: flex;
      justify-content: center;
    }

    .gradio-container {
      width: min(1440px, calc(100vw - 40px)) !important;
      max-width: 1440px !important;
      margin: 0 auto !important;
      padding: 28px !important;
    }

    .gradio-container > .main,
    .gradio-container .contain {
      width: 100% !important;
      max-width: none !important;
      margin-left: auto !important;
      margin-right: auto !important;
    }

    .wa-hero {
      text-align: center;
      padding: 54px 28px 38px;
      margin-bottom: 20px;
      border: 1px solid var(--wa-border);
      border-radius: 32px;
      background: rgba(255, 255, 255, 0.72);
      backdrop-filter: blur(16px);
      box-shadow: var(--wa-shadow);
    }

    .wa-kicker {
      color: var(--wa-green-dark);
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.18em;
      margin-bottom: 12px;
    }

    .wa-hero h1 {
      margin: 0;
      color: var(--wa-text);
      font-size: clamp(3rem, 8vw, 5.2rem);
      font-weight: 800;
      letter-spacing: -0.055em;
      line-height: 1;
    }

    .wa-hero p {
      max-width: 860px;
      margin: 20px auto 24px;
      color: var(--wa-muted);
      font-size: 1.2rem;
      line-height: 1.6;
    }

    .wa-axis {
      display: flex;
      justify-content: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .wa-axis span {
      padding: 8px 16px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.07em;
      text-transform: uppercase;
    }

    .wa-purple { background: rgba(181,168,229,.25); color: #5e4c8d; }
    .wa-green { background: rgba(184,217,168,.32); color: #416234; }
    .wa-blue { background: rgba(142,197,232,.28); color: #2c6283; }

    .wa-intro {
      padding: 24px 28px;
      margin-bottom: 22px;
      border: 1px solid rgba(141,178,126,.22);
      border-radius: 28px;
      background: linear-gradient(135deg, rgba(255,255,255,.94), rgba(238,247,234,.82));
      color: #2e3f47;
      font-size: 1.02rem;
      line-height: 1.8;
    }

    .tabs {
      border: 1px solid var(--wa-border) !important;
      border-radius: 28px !important;
      background: var(--wa-card) !important;
      box-shadow: var(--wa-shadow);
      padding: 14px !important;
      overflow: hidden;
    }

    .tab-nav {
      gap: 8px !important;
      border-bottom: 0 !important;
    }

    .tab-nav button {
      border-radius: 999px !important;
      padding: 10px 18px !important;
      color: var(--wa-muted) !important;
      font-weight: 600 !important;
    }

    .tab-nav button.selected {
      background: rgba(184,217,168,.35) !important;
      color: #284526 !important;
      border-color: rgba(113,150,99,.25) !important;
    }

    .block, .form {
      border-color: var(--wa-border) !important;
      border-radius: 20px !important;
      background: rgba(255,255,255,.7) !important;
    }

    button.primary {
      border: 0 !important;
      border-radius: 999px !important;
      background: var(--wa-green-dark) !important;
      color: white !important;
      font-weight: 700 !important;
    }

    button.secondary {
      border: 1px solid var(--wa-border) !important;
      border-radius: 999px !important;
      background: rgba(255,255,255,.9) !important;
      color: var(--wa-text) !important;
    }

    .academic-table-container {
      overflow-x: auto;
      margin: 20px 0;
      border: 1px solid var(--wa-border);
      border-radius: 22px;
      background: rgba(255,255,255,.7);
      box-shadow: 0 12px 30px rgba(35,54,34,.08);
    }

    .academic-table {
      width: 100%;
      min-width: 800px;
      border-collapse: collapse;
      font-family: "Rubik", sans-serif;
      font-size: 13px;
    }

    .academic-table th {
      position: sticky;
      top: 0;
      z-index: 2;
      padding: 14px 12px;
      border-bottom: 1px solid rgba(37,50,56,.16);
      background: rgba(184,217,168,.34);
      color: #294327;
      font-weight: 700;
      text-align: center;
      white-space: nowrap;
    }

    .academic-table th.dimension-metric-header {
      background: rgba(181,168,229,.22);
      color: #5e4c8d;
    }

    .academic-table th.primary-metric {
      background: rgba(142,197,232,.28);
      color: #285f7f;
    }

    .academic-table td {
      padding: 12px 10px;
      border-bottom: 1px solid rgba(37,50,56,.08);
      color: var(--wa-text);
      text-align: center;
    }

    .academic-table tr:nth-child(even) td { background: rgba(238,247,234,.42); }
    .academic-table tr:hover td { background: rgba(184,217,168,.2); }
    .academic-table .model-cell { text-align: left; font-weight: 650; }
    .academic-table .primary-metric-cell { color: #285f7f; font-weight: 700; }
    .academic-table .dimension-metric-cell { color: #5e4c8d; font-weight: 600; }
    .academic-table .rank-cell { color: var(--wa-muted); font-weight: 700; }
    .academic-table .best-score {
      color: #12b85a;
      background: #eaf8f1 !important;
      font-weight: 800;
    }

    .academic-table .score-trophy {
      display: inline-block;
      margin-left: 8px;
      font-size: 0.8em;
      vertical-align: 0.05em;
    }

    .academic-table .second-best {
      color: #f29a00;
      background: #fff9e9 !important;
      font-weight: 700;
      text-decoration: underline;
      text-decoration-thickness: 1.5px;
      text-underline-offset: 2px;
    }

    .placeholder, .no-data {
      padding: 34px;
      border: 1px dashed rgba(113,150,99,.4);
      border-radius: 20px;
      background: rgba(238,247,234,.55);
      color: var(--wa-muted);
      text-align: center;
    }

    @media (max-width: 768px) {
      .gradio-container {
        width: 100% !important;
        padding: 14px !important;
      }
      .wa-hero { padding: 40px 18px 30px; border-radius: 24px; }
      .wa-hero p { font-size: 1rem; }
      .tabs { border-radius: 22px !important; padding: 8px !important; }
    }
    """
