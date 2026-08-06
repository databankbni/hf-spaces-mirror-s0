"""
GNSS Guardian — GPS Jamming & Spoofing Detection
Detect -> Locate -> Retrieve Similar Cases -> Generate Threat Report -> Alert
"""
import os
import json
import urllib.request
import urllib.parse
import urllib.error
import socket
from datetime import datetime, timezone

import gradio as gr
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import tensorflow as tf

# ── Load model & scaler ──────────────────────────────────────────
model = tf.keras.models.load_model('gnss_cnn_model.keras')

with open('gnss_scaler_meta.json') as f:
    meta = json.load(f)

MEAN   = np.array(meta['mean_'],  dtype=np.float32)
SCALE  = np.array(meta['scale_'], dtype=np.float32)
WINDOW = meta['window_size']
CLASSES = {0: 'Normal', 1: 'Jamming', 2: 'Spoofing'}
COLORS  = {0: '#2ecc71', 1: '#e74c3c', 2: '#3498db'}
REQUIRED_COLS = ['cn0_mean', 'cn0_std', 'agc_level',
                 'sv_count', 'pos_variance', 'delta_pseudorange']

AGC_THRESHOLD = meta['agc_jamming_threshold']
SV_IDX        = meta['sv_count_feature_idx']
AGC_IDX       = meta['agc_feature_idx']

EXAMPLES = [
    [42.0, 1.5, -85.0, 10.0, 0.5,  0.1],
    [12.0, 6.5, -61.0,  1.0, 9.0,  3.5],
    [49.5, 2.0, -83.5,  8.0, 18.0, 9.2],
]

# ── Space theme CSS ──────────────────────────────────────────────
SPACE_CSS = """
.gradio-container {
    background:
        radial-gradient(1px 1px at 25px 45px, #fff, transparent),
        radial-gradient(1px 1px at 150px 105px, #cfe3ff, transparent),
        radial-gradient(2px 2px at 290px 60px, #fff, transparent),
        radial-gradient(1px 1px at 420px 160px, #aac6ff, transparent),
        radial-gradient(1.5px 1.5px at 560px 30px, #fff, transparent),
        radial-gradient(1px 1px at 640px 130px, #e0ecff, transparent),
        radial-gradient(2px 2px at 780px 80px, #fff, transparent),
        linear-gradient(180deg, #05060f 0%, #0a0f24 45%, #10173a 100%) !important;
    background-repeat: repeat !important;
    background-size: 800px 200px, 800px 200px, 800px 200px, 800px 200px,
                     800px 200px, 800px 200px, 800px 200px, 100% 100% !important;
}
#guardian-header {
    text-align: center;
    padding: 18px 0 4px 0;
}
#guardian-header h1 {
    background: linear-gradient(90deg, #6ec3ff, #a78bfa, #6ec3ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.2em;
    letter-spacing: 1px;
}
.tab-nav button { font-weight: 600 !important; }

/* ── Readability: force light text on the dark space background ── */
.gradio-container, .gradio-container * {
    color: #e8ecf8;
}
.gradio-container .prose, .gradio-container .prose *,
.gradio-container .md, .gradio-container .md * {
    color: #e8ecf8 !important;
}
.gradio-container label, .gradio-container .label-wrap,
.gradio-container span, .gradio-container p,
.gradio-container h1, .gradio-container h2,
.gradio-container h3, .gradio-container h4 {
    color: #e8ecf8 !important;
}
.gradio-container table, .gradio-container th, .gradio-container td {
    color: #e8ecf8 !important;
    border-color: #3a4468 !important;
}
.gradio-container input, .gradio-container textarea, .gradio-container select {
    color: #f2f5ff !important;
    background: #141b38 !important;
}
.gradio-container .tab-nav button {
    color: #c7d2f0 !important;
}
.gradio-container .tab-nav button.selected {
    color: #ffffff !important;
}
/* inline code chips: dark chip + bright text (was light-on-light) */
.gradio-container code,
.gradio-container .prose code,
.gradio-container .md code {
    background: #1e2a52 !important;
    color: #7ec8ff !important;
    border: 1px solid #35427a !important;
    border-radius: 4px !important;
    padding: 1px 6px !important;
}
.gradio-container pre, .gradio-container pre code {
    background: #10173a !important;
    color: #d7e3ff !important;
}
/* tab buttons: bright enough to read when unselected */
.gradio-container .tab-nav button,
.gradio-container button[role="tab"] {
    color: #aebcf0 !important;
    opacity: 1 !important;
}
.gradio-container .tab-nav button.selected,
.gradio-container button[role="tab"][aria-selected="true"] {
    color: #ffffff !important;
    border-color: #7ec8ff !important;
}
/* file upload component: readable filename + labels */
.gradio-container .file-preview, .gradio-container .file-preview *,
.gradio-container .wrap, .gradio-container .or,
.gradio-container .icon-wrap svg {
    color: #dbe4ff !important;
}
.gradio-container a, .gradio-container a * {
    color: #7ec8ff !important;
}
/* secondary/dim text bumped up */
.gradio-container .secondary-wrap, .gradio-container .info,
.gradio-container small, .gradio-container .text-gray-500 {
    color: #b8c4e8 !important;
}

/* ── Kill ALL light backgrounds: dark bg + light text everywhere ── */

/* Examples table (Quick Starters) — rows were white with light text */
.gradio-container table,
.gradio-container thead, .gradio-container tbody,
.gradio-container tr, .gradio-container th, .gradio-container td {
    background: #141b38 !important;
    color: #e8ecf8 !important;
    border-color: #35427a !important;
}
.gradio-container thead th, .gradio-container tr:hover td {
    background: #1e2a52 !important;
    color: #ffffff !important;
}

/* Dataframe component cells */
.gradio-container .table-wrap, .gradio-container .cell-wrap,
.gradio-container .dataframe, .gradio-container .dataframe * {
    background: #141b38 !important;
    color: #e8ecf8 !important;
}

/* Component labels / chips ("Confidence Score", "Feature Profile", "Examples") */
.gradio-container .label, .gradio-container label > span,
.gradio-container .plot-container label,
.gradio-container div[data-testid="block-label"],
.gradio-container div[data-testid="block-label"] * {
    background: #1e2a52 !important;
    color: #dbe4ff !important;
    border-color: #35427a !important;
}

/* Slider number boxes + all inputs */
.gradio-container input[type="number"],
.gradio-container input[type="text"],
.gradio-container textarea {
    background: #141b38 !important;
    color: #ffffff !important;
    border-color: #35427a !important;
}

/* Secondary buttons (Download: Normal, etc.) */
.gradio-container button.secondary,
.gradio-container .secondary {
    background: #1e2a52 !important;
    color: #dbe4ff !important;
    border-color: #35427a !important;
}

/* File upload drop-zone */
.gradio-container .upload-container, .gradio-container .file-preview,
.gradio-container div[data-testid="file"] {
    background: #10173a !important;
    color: #dbe4ff !important;
}

/* Checkbox row */
.gradio-container input[type="checkbox"] + span,
.gradio-container .checkbox-label {
    color: #e8ecf8 !important;
}
/* Make the checkbox itself clearly visible + show checked state */
.gradio-container input[type="checkbox"] {
    appearance: none !important;
    -webkit-appearance: none !important;
    width: 20px !important; height: 20px !important;
    border: 2px solid #6ec3ff !important;
    border-radius: 5px !important;
    background: #0d1230 !important;
    cursor: pointer !important;
    position: relative !important;
    vertical-align: middle !important;
    flex: none !important;
}
.gradio-container input[type="checkbox"]:checked {
    background: #6ec3ff !important;
    border-color: #6ec3ff !important;
}
.gradio-container input[type="checkbox"]:checked::after {
    content: '✓' !important;
    position: absolute !important;
    top: -2px !important; left: 3px !important;
    color: #08101f !important;
    font-size: 15px !important;
    font-weight: 900 !important;
}

/* Any leftover white/light utility backgrounds */
.gradio-container .bg-white, .gradio-container [class*="bg-gray-1"],
.gradio-container [class*="bg-gray-2"], .gradio-container [class*="bg-slate-1"] {
    background: #141b38 !important;
}
/* keep gradient title working */
#guardian-header h1 {
    -webkit-text-fill-color: transparent !important;
}
/* blocks/panels: translucent dark cards so plots and controls stay readable */
.gradio-container .block, .gradio-container .form,
.gradio-container .panel {
    background: rgba(13, 18, 42, 0.72) !important;
    border-color: #2c3660 !important;
}

/* ═══════════════ DEEP SPACE SCENE ═══════════════ */

@keyframes twinkle {
    0%, 100% { opacity: 0.9; }
    50%      { opacity: 0.25; }
}
.space-decor { position: fixed; pointer-events: none; z-index: 0; }

.star-layer-a, .star-layer-b {
    top: 0; left: 0; width: 100%; height: 100%;
}
.star-layer-a {
    background:
        radial-gradient(1.5px 1.5px at 12% 22%, #fff, transparent),
        radial-gradient(2px 2px at 33% 68%, #dbe9ff, transparent),
        radial-gradient(1px 1px at 55% 15%, #fff, transparent),
        radial-gradient(2px 2px at 71% 43%, #ffe9c4, transparent),
        radial-gradient(1.5px 1.5px at 88% 76%, #fff, transparent),
        radial-gradient(1px 1px at 44% 89%, #cfe3ff, transparent);
    animation: twinkle 3.5s ease-in-out infinite;
}
.star-layer-b {
    background:
        radial-gradient(1px 1px at 8% 55%, #fff, transparent),
        radial-gradient(2px 2px at 25% 35%, #ffd9e8, transparent),
        radial-gradient(1.5px 1.5px at 62% 82%, #fff, transparent),
        radial-gradient(1px 1px at 79% 12%, #d0f0ff, transparent),
        radial-gradient(2px 2px at 93% 48%, #fff, transparent);
    animation: twinkle 5s ease-in-out 1.2s infinite;
}

/* ringed gas giant — top right */
.planet-saturn {
    top: 90px; right: 4%;
    width: 110px; height: 110px; border-radius: 50%;
    background: radial-gradient(circle at 32% 30%,
        #ffd9a0 0%, #e8a960 35%, #a96b35 70%, #5c3418 100%);
    box-shadow: 0 0 45px rgba(255, 190, 110, 0.35),
                inset -18px -14px 40px rgba(0,0,0,0.55);
    animation: planet-drift 26s ease-in-out infinite;
}
.planet-saturn::before {
    content: '';
    position: absolute; top: 50%; left: 50%;
    width: 210px; height: 54px;
    border: 7px solid rgba(230, 195, 140, 0.55);
    border-radius: 50%;
    transform: translate(-50%, -50%) rotateX(72deg) rotate(-16deg);
    box-shadow: 0 0 18px rgba(255, 210, 150, 0.25);
}
@keyframes planet-drift {
    0%, 100% { transform: translateY(0px); }
    50%      { transform: translateY(-18px); }
}

/* blue ice planet — mid left */
.planet-blue {
    top: 46%; left: 2.5%;
    width: 70px; height: 70px; border-radius: 50%;
    background: radial-gradient(circle at 35% 30%,
        #bfe6ff 0%, #55a8e8 40%, #1d5fa8 75%, #0a2c5c 100%);
    box-shadow: 0 0 34px rgba(90, 170, 255, 0.4),
                inset -12px -10px 26px rgba(0,0,0,0.5);
    animation: planet-drift 20s ease-in-out 3s infinite;
}

/* small red planet — bottom right */
.planet-red {
    bottom: 12%; right: 7%;
    width: 44px; height: 44px; border-radius: 50%;
    background: radial-gradient(circle at 38% 32%,
        #ffb59a 0%, #e06a45 45%, #93321c 80%, #4a1408 100%);
    box-shadow: 0 0 22px rgba(255, 120, 80, 0.35),
                inset -8px -7px 16px rgba(0,0,0,0.55);
    animation: planet-drift 17s ease-in-out 1.5s infinite;
}

/* Earth glimpse — bottom left horizon */
.planet-earth {
    bottom: -130px; left: -110px;
    width: 320px; height: 320px; border-radius: 50%;
    background: radial-gradient(circle at 42% 30%,
        #9fd8ff 0%, #3f96d8 30%, #1a6ab8 55%, #0b3a78 78%, #041c40 100%);
    box-shadow: 0 0 90px rgba(80, 160, 255, 0.45),
                inset -30px -25px 80px rgba(0,0,0,0.6);
    opacity: 0.85;
}
.planet-earth::after {
    content: '';
    position: absolute; inset: -14px;
    border-radius: 50%;
    border: 3px solid rgba(140, 210, 255, 0.28);
    filter: blur(3px);
}

/* orbiting satellite crossing the screen */
@keyframes sat-orbit {
    0%   { transform: translate(-8vw, 22vh)  rotate(-18deg); }
    45%  { transform: translate(48vw, 6vh)   rotate(8deg); }
    100% { transform: translate(108vw, 18vh) rotate(24deg); }
}
.flying-sat {
    top: 0; left: 0;
    font-size: 34px;
    filter: drop-shadow(0 0 10px rgba(140, 200, 255, 0.8));
    animation: sat-orbit 38s linear infinite;
}

/* second, smaller satellite the other way */
@keyframes sat-orbit-2 {
    0%   { transform: translate(105vw, 62vh) rotate(200deg) scale(0.6); }
    100% { transform: translate(-10vw, 40vh) rotate(140deg) scale(0.6); }
}
.flying-sat-2 {
    top: 0; left: 0;
    font-size: 30px;
    opacity: 0.75;
    animation: sat-orbit-2 55s linear 8s infinite;
}

/* shooting star */
@keyframes shoot {
    0%   { transform: translate(110vw, -40px) rotate(-35deg); opacity: 0; }
    3%   { opacity: 1; }
    12%  { transform: translate(55vw, 32vh) rotate(-35deg); opacity: 0; }
    100% { opacity: 0; }
}
.shooting-star {
    top: 0; left: 0;
    width: 130px; height: 2px;
    background: linear-gradient(90deg, transparent, #fff 60%, #aee3ff);
    border-radius: 2px;
    animation: shoot 14s ease-in 4s infinite;
}

/* content sits above the scenery */
.gradio-container > * { position: relative; z-index: 1; }
"""

SPACE_DECOR_HTML = """
<div class="space-decor star-layer-a"></div>
<div class="space-decor star-layer-b"></div>
<div class="space-decor planet-saturn"></div>
<div class="space-decor planet-blue"></div>
<div class="space-decor planet-red"></div>
<div class="space-decor planet-earth"></div>
<div class="space-decor flying-sat">🛰️</div>
<div class="space-decor flying-sat-2">🛰️</div>
<div class="space-decor shooting-star"></div>
"""

HEADER_MD = """
<div id="guardian-header">

# 🛰️ GNSS GUARDIAN

**GPS Jamming & Spoofing Detection · Direction Finding · AI Threat Reports**

*Detect → Locate → Retrieve Similar Cases → Report → Alert · Powered by 1D-CNN + Edge AI*

</div>
"""


# ── Core helpers ─────────────────────────────────────────────────

def scale_features(raw, calib_offset=None):
    adjusted = raw - calib_offset if calib_offset is not None else raw
    return (adjusted - MEAN) / SCALE


def emergency_fallback(sv_count, agc):
    if sv_count == 0.0:
        if agc > AGC_THRESHOLD:
            return 1, 'Jamming [FALLBACK]', 1.0
        return -1, 'Unknown [Zero-Sat]', 1.0
    return None, None, None


# Normal-class reference: the feature centroid the model considers "Normal".
# Auto-calibration maps a device's clean baseline onto THIS point (not the
# global scaler mean, which is a blend of all 3 classes and leans toward
# attacks). Loaded from the demo_normal sample of the training distribution.
try:
    NORMAL_MEAN = pd.read_csv('demo_normal.csv')[REQUIRED_COLS].mean().values.astype(np.float32)
except Exception:
    NORMAL_MEAN = MEAN.copy()


def compute_calibration(df: pd.DataFrame, n_baseline: int = 30):
    """First n_baseline rows = the device's clean baseline. We shift them onto
    the Normal-class centroid so real clean data lands in the Normal region and
    only genuine deviations move toward the attack clusters."""
    baseline = df[REQUIRED_COLS].head(n_baseline).mean().values.astype(np.float32)
    offset = baseline - NORMAL_MEAN
    return offset, baseline


# ── Known-episode library (Similar-Case Retrieval) ───────────────
# Each episode: representative feature vector + human description.
# NOTE: feature-space retrieval for now; will be swapped for the
# text-embedding model (MiniLM / bge / e5) once Part 3 evaluation picks a winner.

EPISODE_LIBRARY = [
    # label, features [cn0_mean, cn0_std, agc, sv, pos_var, d_pr], description
    (0, [42.5, 1.2, -85.2, 11, 0.4, 0.1],
     "Open-sky pedestrian walk, clear conditions. Strong stable C/N0 around 42 dB-Hz, "
     "11 satellites tracked, quiet AGC noise floor. Textbook clean GNSS environment."),
    (0, [38.0, 2.8, -84.5, 8, 1.2, 0.4],
     "Urban canyon drive. Mild multipath raises C/N0 variance and drops 2-3 satellites "
     "behind buildings, but AGC stays at thermal noise floor - no interference present."),
    (0, [35.5, 3.5, -84.0, 6, 2.0, 0.6],
     "Dense foliage hiking trail. Attenuated signals and reduced satellite count from "
     "canopy blockage. Benign degradation - AGC unchanged, no coherent anomaly."),
    (1, [15.0, 6.0, -60.0, 2, 8.0, 3.0],
     "Wideband chirp jammer near a logistics depot. AGC climbed 25 dB as the receiver "
     "fought rising noise floor; C/N0 collapsed below 18 dB-Hz and lock lost on most SVs."),
    (1, [8.0, 7.5, -55.0, 0, 0.0, 0.0],
     "High-power barrage jamming - total denial. Zero satellites tracked, AGC saturated "
     "30 dB above baseline. Classic truck-mounted PPD (personal privacy device) signature."),
    (1, [22.0, 5.0, -68.0, 4, 6.0, 2.2],
     "Intermittent pulsed jammer at airport perimeter. Partial degradation: half the "
     "constellation lost, AGC oscillating, C/N0 dips synchronized with pulse duty cycle."),
    (2, [49.0, 2.2, -83.0, 9, 16.0, 8.5],
     "Meaconing/replay spoofing at a harbor. Counterfeit signals arrive stronger than "
     "authentic ones (C/N0 ~49 dB-Hz - suspiciously high), position solution dragged "
     "800 m off the pier while AGC stayed near normal."),
    (2, [47.5, 3.0, -82.5, 8, 22.0, 11.0],
     "Drone-hijack spoofing attack. Elevated uniform C/N0 across all channels, sudden "
     "pseudorange jumps of ~10 m, and position variance spike during the capture phase."),
    (2, [50.5, 1.8, -84.0, 10, 12.0, 6.0],
     "GPS time-spoofing against a power-grid substation receiver. Signals slightly "
     "over-powered and abnormally uniform; position stable but clock solution walked off."),
]

_LIB_FEATS  = np.array([e[1] for e in EPISODE_LIBRARY], dtype=np.float32)
_LIB_SCALED = (_LIB_FEATS - MEAN) / SCALE


def retrieve_similar_cases(raw_features, top_k=3):
    """Cosine similarity in standardized feature space -> top-k known episodes."""
    q = (np.asarray(raw_features, dtype=np.float32) - MEAN) / SCALE
    qn = q / (np.linalg.norm(q) + 1e-9)
    ln = _LIB_SCALED / (np.linalg.norm(_LIB_SCALED, axis=1, keepdims=True) + 1e-9)
    sims = ln @ qn
    order = np.argsort(sims)[::-1][:top_k]
    results = []
    for idx in order:
        label, feats, desc = EPISODE_LIBRARY[idx]
        results.append({'label': CLASSES[label], 'similarity': float(sims[idx]),
                        'description': desc})
    return results


# ── Threat report generator (GenAI part - template engine now,
#    small HF LLM slot-in later) ──────────────────────────────────

MITIGATIONS = {
    0: ["No action required. Continue routine monitoring.",
        "Keep logging enabled to maintain a healthy device baseline."],
    1: ["Switch to a multi-constellation / multi-frequency receiver if available (L5/E5a is harder to jam).",
        "Fall back to inertial navigation (IMU dead-reckoning) until AGC returns to baseline.",
        "Report the interference location and time to the national spectrum regulator.",
        "If direction estimate is available, physically survey that bearing for a jamming device."],
    2: ["Cross-check position against an independent source (Wi-Fi/cell positioning, IMU).",
        "Reject satellites with abnormally uniform or elevated C/N0 from the PVT solution.",
        "Enable OSNMA / authentication-capable signals if the receiver supports them.",
        "Treat current position/time outputs as untrusted until signals renormalize."],
}


def generate_threat_report(results_df, calib_note="", direction_info=None,
                           similar_cases=None):
    n_total = len(results_df)
    counts  = results_df['predicted_class'].value_counts()
    n_jam   = int(counts.get(1, 0))
    n_spoof = int(counts.get(2, 0))
    n_norm  = int(counts.get(0, 0))
    n_attack = n_jam + n_spoof

    # A real attack is sustained. Require it to cover a meaningful share of the
    # trace before declaring an attack verdict, so a few scattered false
    # positives on a clean signal still read as NO THREAT.
    attack_rate = n_attack / n_total if n_total else 0.0
    if attack_rate < 0.35:
        verdict, dominant = "NO THREAT DETECTED", 0
    elif n_jam >= n_spoof:
        verdict, dominant = "JAMMING ATTACK", 1
    else:
        verdict, dominant = "SPOOFING ATTACK", 2

    attacks = results_df[results_df['predicted_class'] != 0]
    first_idx = int(attacks['sample_idx'].iloc[0]) if n_attack else None
    avg_conf  = float(results_df['confidence'].mean())
    atk_conf  = float(attacks['confidence'].mean()) if n_attack else None

    agc_series = results_df['agc_level'].values
    cn0_series = results_df['cn0_mean'].values
    agc_delta  = float(agc_series.max() - np.median(agc_series[:min(30, n_total)]))
    cn0_delta  = float(np.median(cn0_series[:min(30, n_total)]) - cn0_series.min())

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    sev = {0: '🟢 LOW', 1: '🔴 CRITICAL', 2: '🟠 HIGH'}[dominant]

    lines = [
        f"# 📋 GNSS THREAT REPORT",
        f"**Generated:** {now}  |  **Severity:** {sev}",
        f"",
        f"## Verdict: {verdict}",
        f"",
        f"## 1. What Happened",
        f"Analyzed **{n_total} signal epochs**: {n_norm} normal, "
        f"{n_jam} jamming, {n_spoof} spoofing.",
    ]
    if n_attack:
        lines += [
            f"First anomaly at epoch **{first_idx}** "
            f"(~{first_idx} seconds into the recording). "
            f"Attack persisted across **{n_attack/n_total*100:.0f}%** of the trace.",
        ]
    lines += [
        f"",
        f"## 2. Confidence",
        f"Mean model confidence: **{avg_conf*100:.1f}%**"
        + (f" (attack epochs: **{atk_conf*100:.1f}%**)" if n_attack else ""),
        f"",
        f"## 3. Anomaly Explanation",
    ]
    if dominant == 1:
        lines += [
            f"- AGC rose **{agc_delta:+.1f} dB** above baseline — the receiver amplified "
            f"against a rising noise floor, the physical fingerprint of jamming.",
            f"- C/N0 dropped **{cn0_delta:.1f} dB-Hz** from baseline as noise buried the satellites.",
            f"- Satellite count minimum: **{int(results_df['sv_count'].min())}**.",
        ]
    elif dominant == 2:
        lines += [
            f"- C/N0 became abnormally strong/uniform — counterfeit signals typically "
            f"overpower authentic ones (peak {cn0_series.max():.1f} dB-Hz).",
            f"- AGC stayed near baseline ({agc_delta:+.1f} dB) — spoofing adds structured "
            f"signal, not noise, so the noise floor barely moves.",
            f"- Position/pseudorange discontinuities indicate a capture-and-drag phase.",
        ]
    else:
        lines += [
            f"- AGC stable ({agc_delta:+.1f} dB from baseline), C/N0 within normal spread.",
            f"- No coherent interference signature found.",
        ]

    if direction_info:
        lines += [f"", f"## 4. Interference Direction",
                  f"Estimated bearing to source: **{direction_info['bearing']:.0f}° "
                  f"({direction_info['compass']})** "
                  f"(directionality strength: {direction_info['strength']:.0%})."]

    if similar_cases:
        lines += [f"", f"## 5. Most Similar Known Episodes"]
        for i, c in enumerate(similar_cases, 1):
            lines += [f"{i}. **[{c['label']}]** (similarity {c['similarity']:.2f}) — "
                      f"{c['description']}"]

    lines += [f"", f"## 6. Recommended Actions"]
    lines += [f"- {m}" for m in MITIGATIONS[dominant]]
    if calib_note:
        lines += [f"", f"---", f"*Auto-calibration was applied to this analysis.*"]
    return "\n".join(lines), verdict, dominant


# ── Telegram alert (chat-app bonus) ──────────────────────────────

# HF Spaces (and many cloud hosts) have broken IPv6: Python tries the AAAA
# record first, the TLS handshake hangs, and you get an SSL timeout. Forcing
# getaddrinfo to return only IPv4 addresses fixes the outbound connection.
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_only_getaddrinfo(*args, **kwargs):
    responses = _orig_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET] or responses


def _telegram_share_link(report_text):
    """Browser-side delivery: a t.me link the USER clicks. Works even when the
    Space itself cannot reach Telegram (blocked outbound) because it uses the
    user's own device/network. Opens Telegram with the report ready to send."""
    plain = report_text.replace('#', '').replace('**', '').replace('`', '').strip()
    plain = plain[:1500]   # keep the URL within safe length limits
    text  = urllib.parse.quote(plain)
    return f"https://t.me/share/url?url=%20&text={text}"


def send_telegram_alert(report_text):
    # Guard: no report yet -> nothing to send
    if not report_text or not report_text.strip():
        return ("⚠️ No report to send yet. Go to the **CSV Analysis** tab, run an "
                "analysis first, then come back and send — the report is generated there.")

    # Free HF Spaces block outbound connections to Telegram, so a server-side
    # send just hangs for ~20s and fails. We skip it entirely and hand back an
    # instant browser link — it uses the user's own device to deliver, and it's
    # immediate (no network call from the Space).
    link = _telegram_share_link(report_text)
    return (
        f"### 👉 [📲 Send the report via Telegram]({link})\n\n"
        f"Click the link — Telegram opens on **your** device with the report "
        f"ready. Pick a chat (your bot, a group, or Saved Messages) and hit send."
    )


# ── GNSSLogger parser ─────────────────────────────────────────────

def parse_gnsslogger(filepath: str) -> pd.DataFrame:
    """Convert a Google GNSSLogger .txt file into the model's CSV format."""
    epoch_data = {}

    with open(filepath, 'r', errors='replace') as f:
        lines = f.readlines()

    col_map    = {}
    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.lstrip('# ').strip()
        if stripped.startswith('Raw,') and 'Svid' in stripped:
            header_parts = stripped.split(',')
            col_map = {name.strip(): idx for idx, name in enumerate(header_parts)}
            header_idx = i
            break

    if header_idx is None or not col_map:
        raise ValueError(
            "This does not look like a GNSSLogger file.\n"
            "Make sure you export from the GNSSLogger app as a .txt file\n"
            "and that it contains 'Raw,' measurement lines."
        )

    required_gnss_cols = ['Svid', 'Cn0DbHz', 'TimeNanos', 'ReceivedSvTimeNanos']
    missing = [c for c in required_gnss_cols if c not in col_map]
    if missing:
        raise ValueError(f"GNSSLogger file missing expected columns: {missing}")

    agc_col = 'AgcDb' if 'AgcDb' in col_map else None
    # Doppler range-rate: the receiver's own clean range-rate estimate.
    # We build delta_pseudorange from its temporal jitter (see below).
    prr_col = ('PseudorangeRateMetersPerSecond'
               if 'PseudorangeRateMetersPerSecond' in col_map else None)

    for line in lines:
        if not line.startswith('Raw,'):
            continue
        parts = line.strip().split(',')
        try:
            svid       = int(parts[col_map['Svid']])
            cn0        = float(parts[col_map['Cn0DbHz']])
            time_ns    = int(parts[col_map['TimeNanos']])
            pr_ns      = int(parts[col_map['ReceivedSvTimeNanos']])
            agc        = float(parts[col_map[agc_col]]) if agc_col and parts[col_map[agc_col]] else -85.0
            prr        = (float(parts[col_map[prr_col]])
                          if prr_col and parts[col_map[prr_col]] else None)
        except (ValueError, IndexError):
            continue

        epoch_key = time_ns // 1_000_000_000

        if epoch_key not in epoch_data:
            epoch_data[epoch_key] = {'cn0': [], 'agc': [], 'pr': {}, 'prr': {}}

        epoch_data[epoch_key]['cn0'].append(cn0)
        epoch_data[epoch_key]['agc'].append(agc)
        epoch_data[epoch_key]['pr'][svid] = pr_ns
        if prr is not None:
            epoch_data[epoch_key]['prr'][svid] = prr

    if not epoch_data:
        raise ValueError("No valid Raw measurement lines found in the file.")

    rows      = []
    prev_prr  = {}    # PseudorangeRate one epoch back
    prev2_prr = {}    # two epochs back

    DPR_CLIP     = 20.0             # m/s — matches synthetic training range
    POSVAR_CLIP  = 40.0

    for key in sorted(epoch_data.keys()):
        ep       = epoch_data[key]
        cn0_vals = ep['cn0']
        agc_vals = [a for a in ep['agc'] if a != -85.0]

        cn0_mean = float(np.mean(cn0_vals))          if cn0_vals else 0.0
        cn0_std  = float(np.std(cn0_vals))           if len(cn0_vals) > 1 else 0.0
        agc_mean = float(np.mean(agc_vals))          if agc_vals else -85.0
        sv_count = len(cn0_vals)

        # delta_pseudorange = temporal JITTER of the Doppler range-rate.
        # Raw pseudorange changes hundreds of m/s every second just from normal
        # satellite motion, so differencing it directly is useless. Instead we
        # take the second difference of PseudorangeRateMetersPerSecond per
        # satellite:  |prr[t] - 2*prr[t-1] + prr[t-2]|.  Smooth orbital motion
        # cancels out -> ~0 for a clean signal, spikes on the sudden jumps that
        # a spoofing capture produces. Averaged over satellites, clipped for
        # satellite appear/disappear edge cases.
        jitters = []
        for svid, prr in ep['prr'].items():
            if svid in prev_prr and svid in prev2_prr:
                second_diff = abs(prr - 2.0 * prev_prr[svid] + prev2_prr[svid])
                jitters.append(min(second_diff, DPR_CLIP))
        prev2_prr = prev_prr
        prev_prr  = ep['prr'].copy()

        delta_pr  = float(np.mean(jitters)) if jitters else 0.0
        delta_pr  = min(delta_pr, DPR_CLIP)
        pos_var   = min(cn0_std * delta_pr * 0.10, POSVAR_CLIP) if delta_pr > 0 else 0.0

        rows.append({
            'cn0_mean'          : round(cn0_mean, 3),
            'cn0_std'           : round(cn0_std,  3),
            'agc_level'         : round(agc_mean, 3),
            'sv_count'          : float(sv_count),
            'pos_variance'      : round(pos_var,  3),
            'delta_pseudorange' : round(delta_pr, 3),
        })

    return pd.DataFrame(rows)


# ── Direction Finder (per-satellite azimuth analysis) ─────────────

def parse_gnss_status(filepath: str):
    """
    Parse GNSSLogger 'Status' lines -> per-epoch {svid: (azimuth, cn0)}.
    Status lines carry each satellite's azimuth/elevation + C/N0, which lets
    us estimate the interference bearing: satellites in the jammer's direction
    lose more signal.
    """
    with open(filepath, 'r', errors='replace') as f:
        lines = f.readlines()

    col_map = {}
    for line in lines:
        stripped = line.lstrip('# ').strip()
        if stripped.startswith('Status,') and 'AzimuthDegrees' in stripped:
            col_map = {n.strip(): i for i, n in enumerate(stripped.split(','))}
            break
    if not col_map:
        return None

    cn0_key = 'Cn0DbHz' if 'Cn0DbHz' in col_map else None
    if cn0_key is None or 'AzimuthDegrees' not in col_map or 'Svid' not in col_map:
        return None
    time_key = ('UnixTimeMillis' if 'UnixTimeMillis' in col_map
                else 'ElapsedRealtimeMillis' if 'ElapsedRealtimeMillis' in col_map
                else None)

    epochs = {}
    for line in lines:
        if not line.startswith('Status,'):
            continue
        parts = line.strip().split(',')
        try:
            svid = int(parts[col_map['Svid']])
            az   = float(parts[col_map['AzimuthDegrees']])
            cn0  = float(parts[col_map[cn0_key]])
            t    = int(parts[col_map[time_key]]) // 1000 if time_key else 0
        except (ValueError, IndexError):
            continue
        if cn0 <= 0:
            continue
        epochs.setdefault(t, {})[svid] = (az, cn0)
    return epochs if epochs else None


def estimate_jammer_bearing(status_epochs, n_baseline=30):
    """
    Weighted circular mean of per-satellite C/N0 degradation.
    Baseline = first n_baseline epochs. drop_i = baseline_cn0_i - current_cn0_i.
    Bearing vector = sum(drop_i * [sin(az_i), cos(az_i)]).
    Returns (bearing_deg, strength 0-1, per-azimuth drop profile).
    """
    keys = sorted(status_epochs.keys())
    if len(keys) < n_baseline + 5:
        return None

    baseline = {}
    for k in keys[:n_baseline]:
        for svid, (az, cn0) in status_epochs[k].items():
            baseline.setdefault(svid, []).append(cn0)
    baseline = {s: float(np.mean(v)) for s, v in baseline.items()}

    x_sum, y_sum, drop_total, n_obs = 0.0, 0.0, 0.0, 0
    az_bins = np.zeros(12)   # 30-degree sectors for the polar profile
    bin_cnt = np.zeros(12)

    for k in keys[n_baseline:]:
        for svid, (az, cn0) in status_epochs[k].items():
            if svid not in baseline:
                continue
            drop = baseline[svid] - cn0
            if drop <= 0:
                drop = 0.0
            rad = np.deg2rad(az)
            x_sum += drop * np.sin(rad)
            y_sum += drop * np.cos(rad)
            drop_total += drop
            n_obs += 1
            b = int(az // 30) % 12
            az_bins[b] += drop
            bin_cnt[b] += 1

    if n_obs == 0 or drop_total < 1.0:
        return None

    bearing = float(np.rad2deg(np.arctan2(x_sum, y_sum))) % 360
    # strength: resultant length / total drop -> 1.0 = perfectly directional
    strength = float(np.hypot(x_sum, y_sum) / (drop_total + 1e-9))
    profile  = np.divide(az_bins, np.maximum(bin_cnt, 1))
    return bearing, strength, profile


COMPASS_PTS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
               'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']

def bearing_to_compass(deg):
    return COMPASS_PTS[int((deg + 11.25) // 22.5) % 16]


def make_compass_plot(bearing, strength, profile):
    fig = plt.figure(figsize=(7, 7))
    fig.patch.set_facecolor('#0a0f24')
    ax = fig.add_subplot(111, projection='polar')
    ax.set_facecolor('#0d0d1a')
    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)

    theta = np.deg2rad(np.arange(15, 375, 30))
    norm  = profile / (profile.max() + 1e-9)
    bars  = ax.bar(theta, norm, width=np.deg2rad(28), bottom=0.0,
                   color='#e67e22', alpha=0.55, edgecolor='#f39c12')

    ax.annotate('', xy=(np.deg2rad(bearing), 1.05), xytext=(0, 0),
                arrowprops=dict(facecolor='#e74c3c', edgecolor='white',
                                width=4, headwidth=14))
    ax.set_ylim(0, 1.15)
    ax.set_yticklabels([])
    ax.set_xticks(np.deg2rad([0, 45, 90, 135, 180, 225, 270, 315]))
    ax.set_xticklabels(['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'],
                       color='white', fontsize=12)
    ax.set_title(f'Estimated Interference Bearing: {bearing:.0f}° '
                 f'({bearing_to_compass(bearing)})\n'
                 f'Directionality strength: {strength:.0%}',
                 color='white', fontsize=13, fontweight='bold', pad=20)
    ax.grid(color='#333', alpha=0.5)
    return fig


def find_direction(file):
    """Direction Finder tab handler — needs the original GNSSLogger .txt."""
    if file is None:
        return "Upload a GNSSLogger .txt file first.", None
    try:
        status_epochs = parse_gnss_status(file.name)
    except Exception as e:
        return f"Could not read file: {e}", None

    if status_epochs is None:
        return ("No usable `Status` lines found in this file.\n\n"
                "In GNSSLogger, enable **GnssStatus** logging (Settings tab) "
                "before recording — Status lines carry each satellite's "
                "azimuth, which is what direction-finding needs."), None

    result = estimate_jammer_bearing(status_epochs)
    if result is None:
        return ("**No directional interference detected.** ✅\n\n"
                "Per-satellite signal drops are negligible or uniformly spread — "
                "there is no consistent bearing pointing at an interference source. "
                "This is expected for clean recordings."), None

    bearing, strength, profile = result
    compass = bearing_to_compass(bearing)
    verdict = "strong directional signature" if strength > 0.5 else \
              "moderate directional signature" if strength > 0.25 else \
              "weak directional signature (interpret with caution)"
    msg = (f"### 🧭 Interference source estimated at **{bearing:.0f}° ({compass})**\n\n"
           f"- Directionality strength: **{strength:.0%}** — {verdict}\n"
           f"- Method: satellites located toward the interference source lose more C/N0 "
           f"than satellites away from it. We compute a degradation-weighted circular "
           f"mean over all satellite azimuths (baseline = first 30 s).\n"
           f"- ⚠️ Single-receiver bearing is approximate (±30°). For a fix, take a second "
           f"recording from a different location and triangulate.")
    return msg, make_compass_plot(bearing, strength, profile)


# ── Demo CSV generators ───────────────────────────────────────────

def _make_demo(scenario: str) -> str:
    """Serve the real demo CSVs (sampled from the exact training distribution,
    so they classify correctly with the deployed model). Falls back gracefully
    if a bundled file is missing. `mixed` is built by stitching real segments."""
    demo_files = {
        'normal'  : 'demo_normal.csv',
        'jamming' : 'demo_jamming.csv',
        'spoofing': 'demo_spoofing.csv',
    }

    def _load(name):
        return pd.read_csv(demo_files[name])[REQUIRED_COLS]

    if scenario in demo_files and os.path.exists(demo_files[scenario]):
        df = _load(scenario)
    elif scenario == 'mixed':
        # Normal -> Jamming -> Normal -> Spoofing, from real rows
        segs = []
        for name in ['normal', 'jamming', 'normal', 'spoofing']:
            if os.path.exists(demo_files[name]):
                segs.append(_load(name).sample(frac=1, random_state=7).head(30))
        df = (pd.concat(segs, ignore_index=True) if segs
              else pd.DataFrame(columns=REQUIRED_COLS))
    else:
        # Should not happen if the demo CSVs are uploaded alongside app.py.
        df = pd.DataFrame(columns=REQUIRED_COLS)

    path = f'/tmp/demo_{scenario}.csv'
    df.to_csv(path, index=False)
    return path


def demo_normal():  return _make_demo('normal')
def demo_jamming(): return _make_demo('jamming')
def demo_spoofing(): return _make_demo('spoofing')
def demo_mixed():   return _make_demo('mixed')


# ── GNSSLogger upload handler ─────────────────────────────────────

def convert_gnsslogger(file):
    if file is None:
        return "No file uploaded.", None
    try:
        fpath = file.name if hasattr(file, 'name') else str(file)
        df = parse_gnsslogger(fpath)
    except ValueError as e:
        return f"❌ {e}", None
    except Exception as e:
        import traceback
        return (f"❌ Unexpected error: `{type(e).__name__}: {e}`\n\n"
                f"```\n{traceback.format_exc()[-800:]}\n```"), None

    if len(df) < WINDOW:
        return (f"File parsed OK ({len(df)} epochs) but need at least "
                f"{WINDOW} for inference. Walk around longer next time.", None)

    path = '/tmp/gnsslogger_converted.csv'
    df.to_csv(path, index=False)
    msg = (f"Converted {len(df)} epochs from GNSSLogger file.\n\n"
           f"Avg C/N0={df['cn0_mean'].mean():.1f} dB-Hz  |  "
           f"Avg AGC={df['agc_level'].mean():.1f} dBm  |  "
           f"Avg SV={df['sv_count'].mean():.1f}\n\n"
           f"File ready — click **Analyze CSV** in the CSV Analysis tab.")
    return msg, path


# ── Manual mode plots ─────────────────────────────────────────────

def make_gauge(class_id, confidence, label):
    fig, ax = plt.subplots(figsize=(7, 3.2))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')
    heights = [0.05, 0.05, 0.05]
    if 0 <= class_id <= 2:
        heights[class_id] = confidence
    bars = ax.bar(['Normal', 'Jamming', 'Spoofing'], heights,
                  color=[COLORS[i] for i in range(3)],
                  width=0.5, edgecolor='white', linewidth=0.8)
    if 0 <= class_id <= 2:
        bars[class_id].set_linewidth(2.5)
        ax.text(class_id, confidence + 0.04, f'{confidence*100:.1f}%',
                ha='center', color='white', fontsize=13, fontweight='bold')
    ax.set_ylim(0, 1.15)
    ax.set_ylabel('Confidence', color='white', fontsize=12)
    ax.set_title(f'Prediction: {label}', color='white', fontsize=14, fontweight='bold')
    ax.tick_params(colors='white')
    for sp in ax.spines.values():
        sp.set_edgecolor('#444')
    plt.tight_layout()
    return fig


def make_feature_bar(raw):
    features = ['C/N0 mean', 'C/N0 std', 'AGC', 'SV count', 'Pos var', 'Delta PR']
    ranges   = [(0, 55), (0, 10), (-95, -55), (0, 14), (0, 40), (0, 20)]
    normed   = np.clip([(raw[i] - ranges[i][0]) / (ranges[i][1] - ranges[i][0])
                        for i in range(6)], 0, 1)
    fig, ax  = plt.subplots(figsize=(7, 3.2))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')
    ax.bar(range(6), normed, color='#3498db', alpha=0.8, edgecolor='white', linewidth=0.7)
    ax.set_xticks(range(6))
    ax.set_xticklabels(features, color='white', fontsize=9)
    ax.set_ylim(0, 1.2)
    ax.set_ylabel('Normalised Value', color='white', fontsize=11)
    ax.set_title('Input Feature Profile', color='white', fontsize=13, fontweight='bold')
    ax.tick_params(colors='white')
    for sp in ax.spines.values():
        sp.set_edgecolor('#444')
    plt.tight_layout()
    return fig


def predict_manual(cn0_mean, cn0_std, agc_level, sv_count, pos_var, delta_pr):
    raw = np.array([cn0_mean, cn0_std, agc_level, sv_count,
                    pos_var, delta_pr], dtype=np.float32)
    fb_id, fb_label, fb_conf = emergency_fallback(sv_count, agc_level)
    if fb_label:
        disp = 1 if fb_id == 1 else 0
        return (fb_label, make_gauge(disp, fb_conf, fb_label),
                make_feature_bar(raw),
                f"**Emergency Fallback triggered** - SV=0, AGC={agc_level:.1f} dBm",
                _similar_cases_md(raw))
    scaled = scale_features(raw)
    window = np.tile(scaled, (WINDOW, 1))[np.newaxis]
    probs  = model.predict(window, verbose=0)[0]
    cls_id = int(np.argmax(probs))
    conf   = float(probs[cls_id])
    label  = CLASSES[cls_id]
    details = {
        0: f"Signal clean. C/N0={cn0_mean:.1f} dB-Hz, AGC={agc_level:.1f} dBm, {int(sv_count)} satellites.",
        1: f"Jamming detected. AGC={agc_level:.1f} dBm elevated. SV count={int(sv_count)}.",
        2: f"Spoofing detected. C/N0={cn0_mean:.1f} dB-Hz abnormal. delta_PR={delta_pr:.1f} m jump.",
    }
    return (label, make_gauge(cls_id, conf, label), make_feature_bar(raw),
            details.get(cls_id, ''), _similar_cases_md(raw))


def _similar_cases_md(raw):
    cases = retrieve_similar_cases(raw)
    md = ["### 🔍 Most similar known episodes"]
    for i, c in enumerate(cases, 1):
        md.append(f"{i}. **[{c['label']}]** (sim {c['similarity']:.2f}) — {c['description']}")
    return "\n\n".join(md)


# ── Timeline plot ─────────────────────────────────────────────────

def make_timeline(results_df):
    color_map = {0: '#2ecc71', 1: '#e74c3c', 2: '#3498db'}
    label_map = {0: 'Normal',  1: 'Jamming', 2: 'Spoofing'}
    ids   = results_df['predicted_class'].values
    confs = results_df['confidence'].values
    x     = np.arange(len(results_df))

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    fig.patch.set_facecolor('#1a1a2e')

    ax1 = axes[0]
    ax1.set_facecolor('#0d0d1a')
    ax1.plot(x, results_df['cn0_mean'].values, color='#f1c40f', lw=1.5, label='C/N0 mean')
    for i in x:
        ax1.axvspan(i-0.5, i+0.5, alpha=0.15, color=color_map.get(int(ids[i]), 'gray'))
    ax1.set_ylabel('C/N0 (dB-Hz)', color='white')
    ax1.set_title('GNSS Signal Timeline - CSV Analysis',
                  color='white', fontsize=14, fontweight='bold')
    ax1.tick_params(colors='white')
    ax1.legend(loc='upper right', fontsize=9)
    for sp in ax1.spines.values(): sp.set_edgecolor('#444')

    ax2 = axes[1]
    ax2.set_facecolor('#0d0d1a')
    ax2.plot(x, results_df['agc_level'].values, color='#e67e22', lw=1.5, label='AGC level')
    ax2.axhline(AGC_THRESHOLD, color='#e74c3c', linestyle='--', lw=1.2,
                label=f'Threshold ({AGC_THRESHOLD} dBm)')
    for i in x:
        ax2.axvspan(i-0.5, i+0.5, alpha=0.15, color=color_map.get(int(ids[i]), 'gray'))
    ax2.set_ylabel('AGC (dBm)', color='white')
    ax2.tick_params(colors='white')
    ax2.legend(loc='upper right', fontsize=9)
    for sp in ax2.spines.values(): sp.set_edgecolor('#444')

    ax3 = axes[2]
    ax3.set_facecolor('#0d0d1a')
    ax3.bar(x, confs, color=[color_map.get(int(c), 'gray') for c in ids],
            alpha=0.85, width=0.8)
    ax3.set_ylim(0, 1.1)
    ax3.set_ylabel('Confidence', color='white')
    ax3.set_xlabel('Sample Index', color='white')
    ax3.tick_params(colors='white')
    patches = [mpatches.Patch(color=c, label=label_map[k]) for k, c in color_map.items()]
    ax3.legend(handles=patches, loc='upper right', fontsize=9)
    for sp in ax3.spines.values(): sp.set_edgecolor('#444')

    plt.tight_layout(h_pad=0.8)
    return fig


# ── CSV inference engine ──────────────────────────────────────────

def run_inference_on_df(df: pd.DataFrame, calib_offset=None):
    raw_matrix  = df[REQUIRED_COLS].values.astype(np.float32)
    predictions = []

    for i in range(len(raw_matrix)):
        start  = max(0, i - WINDOW + 1)
        window = raw_matrix[start: i + 1]
        if len(window) < WINDOW:
            pad    = np.tile(window[0], (WINDOW - len(window), 1))
            window = np.vstack([pad, window])

        raw_row = raw_matrix[i]
        fb_id, fb_label, fb_conf = emergency_fallback(raw_row[SV_IDX], raw_row[AGC_IDX])
        if fb_label:
            cls_id, conf, tier = (1 if fb_id == 1 else 0), fb_conf, 'FALLBACK'
        else:
            scaled = scale_features(window, calib_offset)
            probs  = model.predict(scaled[np.newaxis], verbose=0)[0]
            cls_id = int(np.argmax(probs))
            conf   = float(probs[cls_id])
            tier   = 'CNN'

        predictions.append({
            'sample_idx'     : i,
            'cn0_mean'       : round(float(raw_row[0]), 2),
            'agc_level'      : round(float(raw_row[2]), 2),
            'sv_count'       : int(raw_row[3]),
            'predicted_class': cls_id,
            'label'          : CLASSES[cls_id],
            'confidence'     : round(conf, 4),
            'tier'           : tier,
        })

    return _smooth_predictions(pd.DataFrame(predictions))


def _smooth_predictions(pred_df):
    """Temporal smoothing: a genuine attack persists for many seconds, so an
    isolated epoch that disagrees with its neighbours is a false alarm. Replace
    each label with the majority vote over a small centred window."""
    if len(pred_df) >= 5:
        cls = pred_df['predicted_class'].tolist()
        smoothed = cls.copy()
        half = 3   # 7-wide window
        for i in range(len(cls)):
            lo, hi = max(0, i - half), min(len(cls), i + half + 1)
            votes = cls[lo:hi]
            smoothed[i] = max(set(votes), key=votes.count)
        pred_df['predicted_class'] = smoothed
        pred_df['label'] = pred_df['predicted_class'].map(CLASSES)
    return pred_df


def run_physics_detector(df: pd.DataFrame):
    """Robust detector for REAL device data. The CNN is trained on synthetic
    data and generalises poorly to a real phone, so for real recordings we
    classify by physical deviation from the device's own clean baseline (the
    first 30 rows). This is scale-independent and far more reliable on real GPS.

    - Jamming: AGC rises sharply above baseline AND C/N0 drops (or satellites lost)
    - Spoofing: pseudorange jitter / position variance spikes well above baseline
    - Normal: no significant physical deviation
    """
    raw = df[REQUIRED_COLS].values.astype(np.float32)
    b   = raw[:30]
    b_cn0, b_agc      = b[:, 0].mean(), b[:, 2].mean()
    b_pv,  b_dpr      = b[:, 4].mean(), b[:, 5].mean()
    s_cn0 = max(b[:, 0].std(), 1.0)
    s_agc = max(b[:, 2].std(), 1.0)
    s_pv  = max(b[:, 4].std(), 0.3)
    s_dpr = max(b[:, 5].std(), 0.3)

    rows = []
    for i, r in enumerate(raw):
        cn0, cn0_std, agc, sv, pv, dpr = r
        agc_rise = agc - b_agc
        jam = (agc_rise > max(6.0, 3 * s_agc)) and \
              (cn0 < b_cn0 - max(4.0, 3 * s_cn0) or sv <= 2)
        spoof = (dpr > b_dpr + max(6.0, 6 * s_dpr)) or \
                (pv > b_pv + max(6.0, 6 * s_pv))
        cls_id = 1 if jam else (2 if spoof else 0)
        # confidence ~ how far past the trigger, capped
        if cls_id == 1:
            conf = min(1.0, 0.6 + agc_rise / 30.0)
        elif cls_id == 2:
            conf = min(1.0, 0.6 + (dpr - b_dpr) / 15.0)
        else:
            conf = min(1.0, 0.75 + (b_agc + 6 - agc) / 40.0)
        rows.append({
            'sample_idx': i, 'cn0_mean': round(float(cn0), 2),
            'agc_level': round(float(agc), 2), 'sv_count': int(sv),
            'predicted_class': cls_id, 'label': CLASSES[cls_id],
            'confidence': round(float(max(0.5, conf)), 4), 'tier': 'PHYSICS',
        })
    return _smooth_predictions(pd.DataFrame(rows))


def build_outputs(results_df):
    n_total  = len(results_df)
    attacks  = results_df[results_df['predicted_class'] != 0]
    n_attack = len(attacks)

    if n_attack == 0:
        status = f"**No attacks detected** across {n_total} samples. Signal is clean."
    else:
        jam   = (results_df['predicted_class'] == 1).sum()
        spoof = (results_df['predicted_class'] == 2).sum()
        first = attacks['sample_idx'].iloc[0]
        status = (f"**{n_attack} attack samples** out of {n_total} total\n\n"
                  f"- Jamming: **{jam}** | Spoofing: **{spoof}**\n"
                  f"- First attack at sample index: **{first}**\n"
                  f"- Attack rate: **{n_attack/n_total*100:.1f}%**")

    label_map = {0: 'Normal', 1: 'Jamming', 2: 'Spoofing'}
    counts    = results_df['predicted_class'].value_counts().rename(label_map)
    summary   = pd.DataFrame({
        'Class'     : counts.index,
        'Count'     : counts.values,
        'Percentage': (counts.values / n_total * 100).round(1)
    }).reset_index(drop=True)

    out_path = '/tmp/gnss_results.csv'
    results_df.to_csv(out_path, index=False)
    return status, make_timeline(results_df), summary, out_path


def process_csv(file, use_calibration=True):
    """Full pipeline: classify -> retrieve similar cases -> generate report."""
    empty = (None,) * 6
    if file is None:
        return ("No file uploaded.",) + empty[:5]
    try:
        df = pd.read_csv(file.name)
    except Exception as e:
        return (f"Could not read file: {e}",) + empty[:5]

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        return ((f"CSV missing columns: {missing}\n\n"
                 f"If this is a GNSSLogger .txt file, use the **GNSSLogger** tab first "
                 f"to convert it."),) + empty[:5]

    df = df[REQUIRED_COLS].dropna().reset_index(drop=True)
    if len(df) < WINDOW:
        return (f"Need at least {WINDOW} rows. File has {len(df)}.",) + empty[:5]

    calib_note = ""

    if use_calibration and len(df) >= 30:
        # REAL-DEVICE MODE: the CNN is trained on synthetic data and generalises
        # poorly to a real phone, so we use the baseline-relative physics
        # detector, which reads real deviations from the device's own clean start.
        baseline = df[REQUIRED_COLS].head(30).mean().values
        results_df = run_physics_detector(df)
        calib_note = (
            f"\n\n---\n**Real-device mode** — classified by physical deviation from "
            f"your device's own baseline (first 30 rows), not the synthetic model.\n\n"
            f"Device baseline: C/N0 **{baseline[0]:.1f}** dB-Hz · "
            f"AGC **{baseline[2]:.1f}** dBm · SV **{baseline[3]:.0f}**. "
            f"Jamming = AGC spikes above this; Spoofing = pseudorange jumps above this."
        )
    else:
        # DEMO MODE: synthetic CSVs are already at the training scale -> use CNN.
        results_df = run_inference_on_df(df, None)

    status, timeline, summary, out_path = build_outputs(results_df)

    # Retrieve similar cases using the mean attack profile (or overall mean)
    attacks = results_df[results_df['predicted_class'] != 0]
    if len(attacks):
        ref_rows = df.iloc[attacks['sample_idx'].values]
    else:
        ref_rows = df
    mean_profile = ref_rows[REQUIRED_COLS].mean().values
    similar = retrieve_similar_cases(mean_profile)

    report_md, verdict, _ = generate_threat_report(
        results_df, calib_note, direction_info=None, similar_cases=similar)

    return status + calib_note, timeline, summary, out_path, report_md, report_md


# ── Gradio UI ────────────────────────────────────────────────────
with gr.Blocks(theme=gr.themes.Base(primary_hue='indigo', neutral_hue='slate'),
               css=SPACE_CSS, title='GNSS Guardian') as demo:

    gr.HTML(SPACE_DECOR_HTML)
    gr.Markdown(HEADER_MD)

    # holds the latest generated report for the Telegram button
    report_state = gr.State("")

    with gr.Tabs():

        # ── TAB 1: Manual ────────────────────────────────────────
        with gr.TabItem('🎛️ Manual Mode'):
            gr.Markdown("Enter GNSS receiver measurements and click **Detect Attack**.")
            with gr.Row():
                with gr.Column(scale=1):
                    cn0_mean  = gr.Slider(0,   60,  value=42.0, step=0.5,  label='C/N0 Mean (dB-Hz)')
                    cn0_std   = gr.Slider(0,   10,  value=1.5,  step=0.1,  label='C/N0 Std (dB-Hz)')
                    agc_level = gr.Slider(-95, -55, value=-85.0, step=0.5, label='AGC Level (dBm)')
                    sv_count  = gr.Slider(0,   14,  value=10,   step=1,    label='Satellite Count')
                    pos_var   = gr.Slider(0,   40,  value=0.5,  step=0.5,  label='Position Variance (m^2)')
                    delta_pr  = gr.Slider(0,   20,  value=0.1,  step=0.1,  label='Delta Pseudorange (m)')
                    btn_manual = gr.Button('🚨 Detect Attack', variant='primary', size='lg')
                with gr.Column(scale=2):
                    label_out  = gr.Textbox(label='Classification', interactive=False)
                    gauge_plot = gr.Plot(label='Confidence Score')
                    radar_plot = gr.Plot(label='Feature Profile')
                    explain    = gr.Markdown()
                    similar_md = gr.Markdown()

            gr.Markdown("### ⚡ Quick Starters — click to load an example")
            gr.Examples(
                examples=EXAMPLES,
                inputs=[cn0_mean, cn0_std, agc_level, sv_count, pos_var, delta_pr],
                outputs=[label_out, gauge_plot, radar_plot, explain, similar_md],
                fn=predict_manual, run_on_click=True,
            )
            btn_manual.click(
                fn=predict_manual,
                inputs=[cn0_mean, cn0_std, agc_level, sv_count, pos_var, delta_pr],
                outputs=[label_out, gauge_plot, radar_plot, explain, similar_md]
            )

        # ── TAB 2: Demo CSV Scenarios ────────────────────────────
        with gr.TabItem('🧪 Demo Scenarios'):
            gr.Markdown("""
            ### Pre-built demo scenarios
            Download any scenario as a CSV, then switch to **CSV Analysis** to run it.

            | Scenario | Description |
            |----------|-------------|
            | Normal | 100 clean signal samples |
            | Jamming | 30 normal → 70 jamming with AGC ramp |
            | Spoofing | 30 normal → 70 spoofing with C/N0 elevation |
            | Mixed | Normal → Jamming → Normal → Spoofing |
            """)

            with gr.Row():
                btn_norm  = gr.Button('Download: Normal',   variant='secondary')
                btn_jam   = gr.Button('Download: Jamming',  variant='secondary')
                btn_spoof = gr.Button('Download: Spoofing', variant='secondary')
                btn_mix   = gr.Button('Download: Mixed',    variant='secondary')

            demo_file = gr.File(label='Downloaded Demo CSV — upload this in CSV Analysis tab',
                                interactive=False)

            btn_norm.click(fn=demo_normal,   outputs=demo_file)
            btn_jam.click( fn=demo_jamming,  outputs=demo_file)
            btn_spoof.click(fn=demo_spoofing, outputs=demo_file)
            btn_mix.click( fn=demo_mixed,    outputs=demo_file)

        # ── TAB 3: GNSSLogger (real data) ────────────────────────
        with gr.TabItem('📱 GNSSLogger (Real GPS)'):
            gr.Markdown("""
            ### Upload real GPS data from your phone

            **How to record real GPS data:**

            1. Install **GNSSLogger** from Google on your Android phone
               (search "GNSSLogger" on Play Store — by Google LLC)
            2. Go outside, press **Start Logging**, walk for 2+ minutes
            3. Press **Stop**, share the **.txt file** to your computer
            4. Upload it here — the app converts it automatically

            **What GNSSLogger records:**
            - `Cn0DbHz` — signal quality per satellite (our C/N0)
            - `AgcDb` — hardware noise floor (our AGC)
            - `ReceivedSvTimeNanos` — timing for pseudorange calculation
            """)

            gnss_file  = gr.File(label='Upload GNSSLogger .txt file',
                                 file_types=['.txt', '.log'])
            convert_btn = gr.Button('Convert to CSV', variant='primary')

            with gr.Row():
                convert_status = gr.Markdown()
                converted_file = gr.File(
                    label='Converted CSV — upload this in CSV Analysis tab',
                    interactive=False
                )

            convert_btn.click(
                fn=convert_gnsslogger,
                inputs=gnss_file,
                outputs=[convert_status, converted_file]
            )

        # ── TAB 4: CSV Analysis ──────────────────────────────────
        with gr.TabItem('📊 CSV Analysis'):
            gr.Markdown("""
            ### Analyze any CSV file

            Upload a CSV from the **Demo Scenarios** tab or the **GNSSLogger** tab.
            Analysis now also generates a full **Threat Report** (see Threat Report tab).

            **Required columns:**
            `cn0_mean` | `cn0_std` | `agc_level` | `sv_count` | `pos_variance` | `delta_pseudorange`
            """)

            csv_input   = gr.File(label='Upload CSV', file_types=['.csv'])
            calib_check = gr.Checkbox(
                value=False,
                label='Auto-Calibrate — turn ON for real GNSSLogger recordings',
                info='Maps the first 30 rows (assumed clean) onto the Normal profile, so real '
                     'phone data classifies correctly. Leave OFF for the demo CSVs (they are '
                     'already at the training scale).'
            )
            analyze_btn = gr.Button('🔬 Analyze', variant='primary', size='lg')
            status_out  = gr.Markdown()
            timeline_plot = gr.Plot(label='Signal Timeline')

            with gr.Row():
                summary_tbl = gr.Dataframe(
                    label='Attack Summary',
                    headers=['Class', 'Count', 'Percentage'],
                    interactive=False
                )
                results_dl = gr.File(label='Download Full Results CSV')

        # ── TAB 5: Direction Finder ──────────────────────────────
        with gr.TabItem('🧭 Direction Finder'):
            gr.Markdown("""
            ### Where is the interference coming from?

            Upload the **original GNSSLogger .txt file** (not the converted CSV — we need
            each satellite's sky position).

            **How it works:** every satellite sits at a known azimuth in the sky.
            A ground-based jammer degrades satellites **in its direction** more than
            satellites behind you. We measure each satellite's C/N0 drop relative to the
            first 30 seconds, then compute a degradation-weighted compass bearing.

            ⚠️ Requires **GnssStatus** logging enabled in the GNSSLogger app settings.
            """)

            dir_file = gr.File(label='Upload GNSSLogger .txt file',
                               file_types=['.txt', '.log'])
            dir_btn  = gr.Button('🧭 Estimate Direction', variant='primary', size='lg')
            dir_out  = gr.Markdown()
            dir_plot = gr.Plot(label='Interference Compass')

            dir_btn.click(fn=find_direction, inputs=dir_file,
                          outputs=[dir_out, dir_plot])

        # ── TAB 6: Threat Report + Telegram ──────────────────────
        with gr.TabItem('📋 Threat Report'):
            gr.Markdown("""
            ### AI-generated incident report

            Run an analysis in the **CSV Analysis** tab first — the report is generated
            automatically and appears here: verdict, confidence, anomaly explanation,
            similar known episodes, and recommended mitigations.
            """)

            report_out = gr.Markdown(value="*No report yet — analyze a CSV first.*")

            gr.Markdown("---")
            gr.Markdown("### 📱 Send alert to Telegram")
            tg_btn    = gr.Button('🚀 Send Report to Telegram', variant='secondary')
            tg_status = gr.Markdown()

            tg_btn.click(fn=send_telegram_alert, inputs=report_state,
                         outputs=tg_status)

    # CSV Analysis wiring (after all components exist)
    analyze_btn.click(
        fn=process_csv,
        inputs=[csv_input, calib_check],
        outputs=[status_out, timeline_plot, summary_tbl, results_dl,
                 report_out, report_state]
    )

    gr.Markdown(
        "<div style='text-align:center; opacity:0.6; padding:10px'>"
        "🛰️ GNSS Guardian · Introduction to Data Science Final Project · "
        "1D-CNN + Edge AI + Auto-Calibration</div>"
    )

demo.launch()
