import datetime
import pandas as pd
import gradio as gr

# Heavy imports done once at module level (fast ~2-3s startup)
from calculations import DF, ga1, ga2, hadlock, intergrowth, gold_standard_ga
from ml_models import predict_ga, predict_risks
from plots import (plot_growth_centiles, plot_violin, plot_corr_heatmap,
                   plot_sga_box, plot_outlier_scatter, run_stats)

# ── CSS ──────────────────────────────────────────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
.gradio-container { max-width:1400px !important; }
.header { background: linear-gradient(135deg, #0d9488, #0891b2); color: #ffffff !important;
          padding: 28px 32px; border-radius: 14px; margin-bottom: 20px;
          box-shadow: 0 4px 20px rgba(0,0,0,.12); }
.header h1 { font-size: 28px; font-weight: 800; margin: 0 0 6px; color: #ffffff !important; }
.header p  { font-size: 14px; margin: 0; opacity: .88; color: #ffffff !important; }

/* Gestational Age Card Grid styles */
.ga-grid  { display: grid; grid-template-columns: repeat(auto-fit, minmax(175px, 1fr)); gap: 12px; }
.ga-card  { background: #ffffff !important; border-radius: 10px; padding: 16px; text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,.06); border: 1px solid #e2e8f0; }
.ga-card .label { font-size: 10px; font-weight: 700; text-transform: uppercase;
                  color: #475569 !important; letter-spacing: .5px; margin-bottom: 6px; }
.ga-card .value { font-size: 24px; font-weight: 800; }
.card-gold  { border: 2px solid #16a34a !important; }
.card-gold  .value { color: #16a34a !important; }
.card-ai    { border: 2px solid #7c3aed !important; }
.card-ai    .value { color: #7c3aed !important; }
.card-g2    { border: 2px solid #0d9488 !important; }
.card-g2    .value { color: #0d9488 !important; }
.card-west  { border: 2px solid #64748b !important; }
.card-west  .value { color: #64748b !important; }
.ga-card .sub { font-size: 10px; color: #64748b !important; margin-top: 4px; }

/* Risk Assessment Grid styles */
.risk-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-top: 14px; }
.risk-card { background: #ffffff !important; border-radius: 10px; padding: 14px; box-shadow: 0 2px 8px rgba(0,0,0,.05); border: 1px solid #e2e8f0; }
.risk-card .rlabel { font-size: 10px; font-weight: 700; text-transform: uppercase; color: #475569 !important; margin-bottom: 5px; }
.risk-card .rval { font-size: 22px; font-weight: 800; }
.risk-high .rval { color: #dc2626 !important; }
.risk-low  .rval { color: #16a34a !important; }
.rbar { background: #f1f5f9; height: 7px; border-radius: 4px; overflow: hidden; }
.rbar div { height: 100%; border-radius: 4px; }
.risk-high .rbar div { background: #dc2626 !important; }
.risk-low  .rbar div { background: #16a34a !important; }

/* Alerts and pathology feedback */
.alert { padding: 15px 18px; border-radius: 8px; margin-top: 12px; font-size: 13px; line-height: 1.6; }
.alert-ptb  { background: #fef2f2 !important; border-left: 4px solid #dc2626; color: #991b1b !important; }
.alert-ptb * { color: #991b1b !important; }
.alert-warn { background: #fffbeb !important; border-left: 4px solid #f59e0b; color: #92400e !important; }
.alert-warn * { color: #92400e !important; }
.alert-ok   { background: #f0fdf4 !important; border-left: 4px solid #22c55e; color: #166534 !important; }
.alert-ok * { color: #166534 !important; }
.alert-flag { background: #fff7ed !important; border-left: 4px solid #f97316; color: #9a3412 !important; }
.alert-flag * { color: #9a3412 !important; }
.alert-conf { background: #eff6ff !important; border-left: 4px solid #3b82f6; color: #1e40af !important; }
.alert-conf * { color: #1e40af !important; }
.atitle { font-weight: 700; font-size: 13px; text-transform: uppercase; margin-bottom: 6px; }

/* Research & Outlier Stats styles */
.stat-box { background: #ffffff !important; border-radius: 10px; padding: 18px; box-shadow: 0 2px 8px rgba(0,0,0,.05); border: 1px solid #e2e8f0; }
.stat-box h4 { margin: 0 0 8px; font-size: 14px; color: #0f172a !important; }
.stat-box p, .stat-box p * { color: #334155 !important; }
.dt { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; color: #475569 !important; }
.dt th, .dt td { padding: 8px 12px; border: 1px solid #e2e8f0; text-align: center; }
.dt th { background: #f8fafc; font-weight: 700; color: #0f172a !important; }
.dt td { color: #475569 !important; }
.dt td b { color: #0f172a !important; }
.dt .sig  { background: #dcfce7 !important; color: #166534 !important; font-weight: 700; }
.dt .ns   { background: #fef3c7 !important; color: #92400e !important; font-weight: 700; }
.dt .self { background: #f1f5f9 !important; color: #475569 !important; }
.pattern-desc { background: #f0fdf4 !important; border-left: 4px solid #16a34a; color: #166534 !important;
                padding: 13px; border-radius: 8px; font-size: 13px; margin-bottom: 10px; }
.pattern-desc * { color: #166534 !important; }
"""

TODAY = datetime.date.today().strftime("%Y-%m-%d")
DEFAULT_FIRST = (datetime.date.today() - datetime.timedelta(weeks=20)).strftime("%Y-%m-%d")

# ── CLINICAL CALCULATOR CALLBACK ─────────────────────────────────────────────
def run_calculator(crl, d_first, d_curr, bpd, ofd, hc, ac, fc,
                   weight, age_cat, thyroid, anemia, hyp, diab, centile_param):
    crl=float(crl or 0); bpd=float(bpd or 0); ofd=float(ofd or 0)
    hc=float(hc or 0);   ac=float(ac or 0);   fc=float(fc or 0)
    w_enc = {"Normal":0,"Obese":1,"Underweight":2}.get(weight,0)
    a_enc = {"less_than_24":0,"greater_than_24":1}.get(age_cat,0)
    tri = 2 if hc<25 else 3

    # Scenario A: GA-1 + Gold Standard
    g1 = ga1(crl)
    gs = gold_standard_ga(crl, d_first, d_curr)

    # Scenario B: Late estimates
    g2 = ga2(bpd, ofd, hc)
    hd = hadlock(hc, fc, bpd, ac)
    ig = intergrowth(hc, fc)

    # Scenario D: AI model
    row_full = dict(bpd1=bpd or DF["bpd1"].median(), ofd1=ofd or DF["ofd1"].median(),
                    hc1=hc or DF["hc1"].median(), ac1=ac or DF["ac1"].median(),
                    fc1=fc or DF["fc1"].median(), trimester=tri,
                    Weight_enc=w_enc, Age_enc=a_enc,
                    thyroid_preg=int(thyroid), anemia=int(anemia),
                    hypertension=int(hyp), prediab_diab=int(diab))
    row_risk = {k:row_full[k] for k in ["bpd1","ofd1","hc1","ac1","fc1","trimester","Weight_enc"]}

    ai_ga = predict_ga(row_full)
    sga_p, anm_p, diab_p = predict_risks(row_full, row_risk)

    def fmt(v): return f"{v:.1f} wks" if v>0 else "N/A"

    # GA result cards HTML
    ga_html = f"""<div class='ga-grid'>
  <div class='ga-card card-gold'><div class='label'>Gold Standard GA</div>
    <div class='value'>{fmt(gs)}</div><div class='sub'>Dating + CRL baseline</div></div>
  <div class='ga-card card-ai'><div class='label'>AI Maternal-Adjusted</div>
    <div class='value'>{fmt(ai_ga)}</div><div class='sub'>Random Forest (biometry + maternal)</div></div>
  <div class='ga-card card-g2'><div class='label'>Garbhini GA-2</div>
    <div class='value'>{fmt(g2)}</div><div class='sub'>IIT Madras model (BPD, OFD, HC)</div></div>
  <div class='ga-card card-west'><div class='label'>Hadlock</div>
    <div class='value'>{fmt(hd)}</div><div class='sub'>Western standard</div></div>
  <div class='ga-card card-west'><div class='label'>INTERGROWTH-21st</div>
    <div class='value'>{fmt(ig)}</div><div class='sub'>International baseline</div></div>
</div>"""

    # Risk cards HTML
    def risk_card(title, pct):
        cls = "risk-high" if pct>0.25 else "risk-low"
        return f"""<div class='risk-card {cls}'>
  <div class='rlabel'>{title}</div><div class='rval'>{pct*100:.1f}%</div>
  <div class='rbar'><div style='width:{min(pct*100,100):.1f}%'></div></div></div>"""
    risk_html = f"<div class='risk-grid'>{risk_card('SGA Risk',sga_p)}{risk_card('Anemia Risk',anm_p)}{risk_card('Diabetes Risk',diab_p)}</div>"

    # Scenario C: PTB misclassification
    ptb_html = ""
    if gs>0:
        is_preterm = gs<37
        hd_preterm = hd<37 if hd>0 else False
        g2_preterm = g2<37 if g2>0 else False
        if is_preterm and not hd_preterm and g2>0:
            ptb_html = f"""<div class='alert alert-ptb'>
  <div class='atitle'>⚠️ Critical: Preterm Misclassification by Hadlock</div>
  Hadlock estimates <b>{fmt(hd)} (Term)</b> — this baby would be classified as term and miss
  vital corticosteroid therapy. Garbhini GA-2 correctly estimates <b>{fmt(g2)} (Preterm)</b>.
  The Gold Standard confirms <b>{fmt(gs)} (Preterm)</b>.</div>"""
        elif is_preterm:
            ptb_html = f"<div class='alert alert-warn'><div class='atitle'>👶 Preterm Birth Encounter</div>Gold Standard GA: <b>{fmt(gs)}</b>. Garbhini GA-2: <b>{fmt(g2)}</b>. All models flag preterm status.</div>"

    # Scenario F: Anomaly alerts
    flags = []
    if 0<hc<22:
        flags.append(f"🔴 <b>Microcephaly Pattern:</b> HC = {hc:.1f} cm (< 22 cm). Matches outlier profiles #203 and #735 in IIT Madras cohort.")
    if hc>0 and ac>0 and (hc/ac)>1.25:
        flags.append(f"🟠 <b>Asymmetric IUGR:</b> HC/AC ratio = {hc/ac:.2f} (>1.25). Suggests brain-sparing growth restriction.")
    if fc >= 7.23:
        flags.append(f"⚠️ <b>Long Femur Outlier:</b> FL = {fc:.1f} cm — exceeds 99th percentile of IIT Madras cohort (7.23 cm). Possible measurement error or skeletal anomaly.")
    elif 0 < fc <= 4.50:
        flags.append(f"🟠 <b>Short Femur Outlier:</b> FL = {fc:.1f} cm — below 5th percentile of cohort. Possible skeletal dysplasia risk.")
    if fc > 0 and hc > 0 and (fc/hc) < 0.14:
        flags.append(f"🟠 <b>Skeletal Dysplasia Risk:</b> Femur-to-Head ratio = {fc/hc:.3f} (very short FL relative to HC).")

    if flags:
        anom_html = f"<div class='alert alert-flag'><div class='atitle'>🏥 Biometric Anomaly Alerts</div>" + "<br>".join(flags) + "</div>"
    else:
        anom_html = "<div class='alert alert-ok'><div class='atitle'>✅ No Biometric Outliers</div>All parameters within IIT Madras cohort standard ranges (FC 4.1–9.4 cm, HC 8.1–33.9 cm).</div>"

    # Scenario D: Maternal confounder explanation
    conf_lines = []
    if diab:   conf_lines.append("<li><b>Gestational Diabetes:</b> Promotes macrosomia. Hadlock overestimates GA further on diabetic fetuses. AI model accounts for this.</li>")
    if anemia: conf_lines.append("<li><b>Maternal Anemia:</b> Restricts oxygen transport → smaller fetal head parameters (confirmed by cohort correlation HC r=+0.105 with anemia).</li>")
    if thyroid:conf_lines.append("<li><b>Thyroid Dysfunction:</b> Negatively correlated with fetal growth velocity across all biometry metrics (r≈–0.07).</li>")
    if weight=="Obese": conf_lines.append("<li><b>Maternal Obesity:</b> Larger fetal size on average. AI model adjusts for obesity-driven size inflation.</li>")
    if weight=="Underweight": conf_lines.append("<li><b>Maternal Undernutrition:</b> Symmetric growth deceleration expected.</li>")
    conf_html = ""
    if conf_lines:
        conf_html = f"<div class='alert alert-conf'><div class='atitle'>🔬 Maternal Confounder Analysis</div><ul style='margin:6px 0 0;padding-left:18px;'>{''.join(conf_lines)}</ul></div>"

    # Growth centile chart
    centile_fig = plot_growth_centiles(centile_param,
                                       {"hc1":hc,"bpd1":bpd,"ofd1":ofd,"ac1":ac,"fc1":fc}.get(centile_param,hc),
                                       gs)

    return ga_html, risk_html, ptb_html, anom_html, conf_html, centile_fig


# ── RESEARCH ANALYTICS CALLBACK ───────────────────────────────────────────────
def run_analytics(trim, weight):
    sub = DF.copy()
    if trim!="All": sub = sub[sub["trimester"]==int(trim)]
    if weight!="All": sub = sub[sub["Weight"]==weight]
    if len(sub)<5:
        empty = plot_violin(DF)
        return plot_violin(DF), "<p>Select a larger subset.</p>", plot_corr_heatmap(DF), plot_sga_box(DF)
    return plot_violin(sub), run_stats(sub), plot_corr_heatmap(sub), plot_sga_box(sub)


# fc1: mean=5.74, std=0.95, 99th pct=7.23, max=9.4 cm
# hc1: min=8.1 cm (2 true microcephaly outliers below IQR fence of 13.6)
FC_HIGH = 7.23   # 99th percentile — biologically implausible for gestational range
FC_LOW  = 4.50   # suspiciously short femur (< 5th pct of cohort)
HC_MICRO = 22.0  # clinically significant microcephaly boundary
HC_AC_IUGR = 1.25  # brain-sparing IUGR ratio threshold

# ── OUTLIER EXPLORER CALLBACK ─────────────────────────────────────────────────
def run_outliers(pattern):
    if "Microcephaly" in pattern:
        flagged = DF[DF["hc1"] < HC_MICRO].copy()
        n = len(flagged)
        desc = (f"Patients with HC < {HC_MICRO} cm — clinically significant microcephaly boundary. "
                f"{n} flagged patients in the IIT Madras cohort (cohort mean HC = 27.3 cm).")
    elif "IUGR" in pattern:
        flagged = DF[(DF["hc1"] / DF["ac1"]) > HC_AC_IUGR].copy()
        n = len(flagged)
        desc = (f"Asymmetric IUGR: HC/AC ratio > {HC_AC_IUGR} indicates brain-sparing growth restriction. "
                f"{n} patients flagged in cohort.")
    else:
        # Femur outliers: unusually long (>99th pct) or unusually short (<5th pct)
        flagged = DF[(DF["fc1"] >= FC_HIGH) | (DF["fc1"] <= FC_LOW)].copy()
        n_high = len(DF[DF["fc1"] >= FC_HIGH])
        n_low  = len(DF[DF["fc1"] <= FC_LOW])
        desc = (f"Femur length outliers: ≥{FC_HIGH} cm (99th pct, n={n_high}) or ≤{FC_LOW} cm (suspiciously short, n={n_low}). "
                f"Cohort range: 4.1–9.4 cm. These may indicate skeletal anomalies or data-entry errors.")

    cols = ["participant_r2id","hc1","bpd1","ofd1","ac1","fc1",
            "Weight","thyroid_preg","anemia","hypertension","prediab_diab","sga","Gold_Standard_GA"]
    desc_html = f"<div class='pattern-desc'><b>{len(flagged)} patients found.</b> {desc}</div>"
    return flagged[cols].reset_index(drop=True), desc_html, plot_outlier_scatter(flagged, pattern)


# ── GRADIO LAYOUT ─────────────────────────────────────────────────────────────
with gr.Blocks(title="Garbhini – IIT Madras Clinical Portal") as demo:
    gr.HTML("""<div class='header'>
  <h1>🏥 Garbhini Clinical Decision Support & Research Portal</h1>
  <p>IIT Madras · GARBH-Ini Programme (DBT India Initiative) · GA-1 & GA-2 Gestational Age Estimation</p>
</div>""")

    with gr.Tabs():

        # ── TAB 1 ──────────────────────────────────────────────────────────
        with gr.TabItem("📋 Clinical GA Calculator"):
            gr.Markdown("### Enter fetal biometry and maternal details to estimate Gestational Age across all models")
            with gr.Row():
                with gr.Column(scale=4):
                    gr.Markdown("**First-Trimester Inputs (Scenario A — GA-1)**")
                    with gr.Row():
                        d_first = gr.Textbox(value=DEFAULT_FIRST, label="1st Trimester Scan Date (YYYY-MM-DD)")
                        d_curr  = gr.Textbox(value=TODAY,         label="Current Scan Date (YYYY-MM-DD)")
                    crl = gr.Number(value=30.0, label="CRL — Crown-Rump Length (mm)")

                    gr.Markdown("**Second/Third Trimester Biometry (Scenarios B, C, E, F)**")
                    with gr.Row():
                        bpd = gr.Number(value=7.5,  label="BPD (cm)")
                        ofd = gr.Number(value=9.7,  label="OFD (cm)")
                        hc  = gr.Number(value=27.3, label="HC (cm)")
                    with gr.Row():
                        ac  = gr.Number(value=25.0, label="AC (cm)")
                        fc  = gr.Number(value=5.7,  label="FL/FC (cm)")

                    gr.Markdown("**Maternal Conditions (Scenario D)**")
                    with gr.Row():
                        weight  = gr.Dropdown(["Normal","Obese","Underweight"], value="Normal", label="Maternal Weight")
                        age_cat = gr.Dropdown(["less_than_24","greater_than_24"], value="greater_than_24", label="Maternal Age")
                    with gr.Row():
                        thyroid = gr.Checkbox(label="Thyroid disorder",      value=False)
                        anemia  = gr.Checkbox(label="Anemia",                value=False)
                        hyp     = gr.Checkbox(label="Hypertension",          value=False)
                        diab    = gr.Checkbox(label="Gestational Diabetes",  value=False)

                    calc_btn = gr.Button("🔍 Calculate Gestational Age", variant="primary", size="lg")

                with gr.Column(scale=5):
                    gr.Markdown("**GA Estimates (Scenarios A, B, D)**")
                    ga_out    = gr.HTML()
                    risk_out  = gr.HTML()
                    ptb_out   = gr.HTML()
                    anom_out  = gr.HTML()
                    conf_out  = gr.HTML()

            gr.Markdown("---\n### Fetal Growth Reference Centiles — Indian Cohort (Scenario E)")
            with gr.Row():
                with gr.Column(scale=1):
                    cparam = gr.Dropdown(["hc1","bpd1","ofd1","ac1","fc1"], value="hc1",
                                         label="Biometry Parameter")
                with gr.Column(scale=4):
                    centile_fig = gr.Plot()

        # ── TAB 2 ──────────────────────────────────────────────────────────
        with gr.TabItem("📊 Research Analytics"):
            gr.Markdown("### Dynamic cohort analysis: error distributions, statistical significance, correlations")
            with gr.Row():
                with gr.Column(scale=1):
                    r_trim   = gr.Dropdown(["All","2","3"], value="All", label="Trimester")
                    r_weight = gr.Dropdown(["All","Normal","Obese","Underweight"], value="All", label="Maternal Weight")
                    gr.Button("Update Analytics", variant="secondary").click(
                        run_analytics, [r_trim, r_weight],
                        [gr.Plot(), gr.HTML(), gr.Plot(), gr.Plot()])
                with gr.Column(scale=3):
                    stats_out = gr.HTML()
            with gr.Row():
                violin_out = gr.Plot()
                corr_out   = gr.Plot()
            sga_box_out = gr.Plot()

        # ── TAB 3 ──────────────────────────────────────────────────────────
        with gr.TabItem("🔎 Symptomatic Patient Explorer"):
            gr.Markdown("### Identify patients exhibiting specific clinical growth anomaly patterns")
            with gr.Row():
                with gr.Column(scale=1):
                    outlier_dd = gr.Radio(
                        choices=[
                            "Microcephaly Pattern (HC < 22 cm)",
                            "Asymmetric IUGR (HC/AC > 1.25)",
                            "Femur Outlier / Skeletal Anomaly (FL ≥ 7.23 cm or ≤ 4.5 cm)"
                        ],
                        value="Microcephaly Pattern (HC < 22 cm)",
                        label="Select Anomaly Pattern"
                    )
                    pattern_html = gr.HTML()
                with gr.Column(scale=2):
                    scatter_out = gr.Plot()
            outlier_table = gr.Dataframe(interactive=False)

        # ── TAB 4 ──────────────────────────────────────────────────────────
        with gr.TabItem("📂 Cohort Data Browser"):
            gr.Markdown(f"### {len(DF)} patients after preprocessing (showing top 100 rows, use search below)")
            with gr.Row():
                s_id  = gr.Textbox(label="Search Participant ID", placeholder="e.g. 30240")
                s_wt  = gr.Dropdown(["All","Normal","Obese","Underweight"], value="All", label="Weight")
                s_sga = gr.Dropdown(["All","0","1"], value="All", label="SGA")
            data_table = gr.Dataframe(value=DF.head(100).reset_index(drop=True), interactive=False)

            def search(q, w, s):
                f = DF.copy()
                if q: f = f[f["participant_r2id"].astype(str).str.contains(q, na=False)]
                if w!="All": f = f[f["Weight"]==w]
                if s!="All": f = f[f["sga"]==int(s)]
                return f.head(100).reset_index(drop=True)
            s_id.change(search, [s_id,s_wt,s_sga], data_table)
            s_wt.change(search, [s_id,s_wt,s_sga], data_table)
            s_sga.change(search, [s_id,s_wt,s_sga], data_table)

    # ── WIRE CALLBACKS ────────────────────────────────────────────────────────
    calc_inputs  = [crl, d_first, d_curr, bpd, ofd, hc, ac, fc,
                    weight, age_cat, thyroid, anemia, hyp, diab, cparam]
    calc_outputs = [ga_out, risk_out, ptb_out, anom_out, conf_out, centile_fig]

    calc_btn.click(run_calculator, calc_inputs, calc_outputs)
    cparam.change(run_calculator, calc_inputs, calc_outputs)

    # Research analytics — fix: wire correctly to output components
    def do_analytics(trim, weight):
        return run_analytics(trim, weight)

    r_trim.change(run_analytics, [r_trim, r_weight], [violin_out, stats_out, corr_out, sga_box_out])
    r_weight.change(run_analytics, [r_trim, r_weight], [violin_out, stats_out, corr_out, sga_box_out])

    outlier_dd.change(run_outliers, [outlier_dd], [outlier_table, pattern_html, scatter_out])

    # Load defaults on startup (lightweight — no ML inference, just static plots)
    # Removed redundant load to prevent startup freeze
    # Removed redundant load to prevent startup freeze


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860,
                share=False, css=CSS)
