"""Gradio app for the PIRD AI-text detector (Hugging Face Spaces).

Expects the trained checkpoint in ./pird_deploy (pird.pt + config.json) and the `pird/` package
present in the Space. Runs on CPU (free Spaces tier) — RoBERTa inference on one text is ~1-2s.

UI: full-width vintage-classic design with a light ("classic white") / dark ("classic black")
toggle. The verdict mirrors the web app — plain-language headline, a large probability, and a
HUMAN<->AI needle dial. The toggle flips Gradio's `dark` class and persists in localStorage.
"""
import math
import os

import gradio as gr

from pird.detectors.pird import PIRDDetector

CKPT = os.environ.get("PIRD_CKPT", "pird_deploy")
detector = PIRDDetector(CKPT)


# ---------- plain-language reading of the calibrated probability ----------
def _interpret(p: float):
    if p >= 0.98:
        return "Almost certainly AI-written", "ai"
    if p >= 0.80:
        return "Very likely AI-written", "ai"
    if p >= 0.55:
        return "Probably AI-written", "ai"
    if p > 0.45:
        return "Too close to call", "neutral"
    if p > 0.20:
        return "Probably human-written", "human"
    if p > 0.02:
        return "Very likely human-written", "human"
    return "Almost certainly human-written", "human"


def _explain(p: float):
    if 0.45 < p < 0.55:
        return "The evidence points both ways — treat this passage as unresolved."
    ai = p >= 0.55
    n = min(99, round((p if ai else 1 - p) * 100))
    return (f"Roughly {n} of every 100 passages with this score "
            f"turn out to be {'AI' if ai else 'human'}-written.")


# ---------- half-dial gauge (mirrors the web app's Gauge component) ----------
_CX, _CY, _R = 110, 100, 82


def _pt(f, r):
    theta = math.pi * (1 - f)
    return _CX + r * math.cos(theta), _CY - r * math.sin(theta)


def _arc(f1, f2, r):
    x1, y1 = _pt(f1, r)
    x2, y2 = _pt(f2, r)
    return f"M {x1:.2f} {y1:.2f} A {r} {r} 0 0 1 {x2:.2f} {y2:.2f}"


def _gauge(p, idle=False):
    ticks = ""
    for i in range(11):
        x1, y1 = _pt(i / 10, _R + 9)
        x2, y2 = _pt(i / 10, _R + 15)
        ticks += f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}'/>"
    angle = (p - 0.5) * 180
    dial_op = 0.35 if idle else 1.0
    ndl_op = 0.3 if idle else 1.0
    return f"""
<svg viewBox="0 0 220 128" class="gauge-svg" role="img" aria-label="Human to AI dial">
  <g fill="none" stroke-width="13" opacity="{dial_op}">
    <path d="{_arc(0.0, 0.44, _R)}" stroke="var(--human-color)"/>
    <path d="{_arc(0.455, 0.545, _R)}" stroke="var(--line)"/>
    <path d="{_arc(0.56, 1.0, _R)}" stroke="var(--ai-color)"/>
  </g>
  <g stroke="var(--ink-soft)" stroke-width="1" opacity="0.65">{ticks}</g>
  <text x="{_CX - _R - 2}" y="{_CY + 16}" text-anchor="middle" class="g-num">0</text>
  <text x="{_CX}" y="{_CY - _R - 20}" text-anchor="middle" class="g-num">50</text>
  <text x="{_CX + _R + 2}" y="{_CY + 16}" text-anchor="middle" class="g-num">100</text>
  <text x="{_CX - _R + 6}" y="{_CY + 27}" text-anchor="middle" class="g-end" fill="var(--human-color)">HUMAN</text>
  <text x="{_CX + _R - 6}" y="{_CY + 27}" text-anchor="middle" class="g-end" fill="var(--ai-color)">AI</text>
  <g class="g-needle" opacity="{ndl_op}" style="transform: rotate({angle:.1f}deg); transform-origin: {_CX}px {_CY}px;">
    <line x1="{_CX}" y1="{_CY}" x2="{_CX}" y2="{_CY - _R + 20}" stroke="var(--ink)" stroke-width="2.5" stroke-linecap="round"/>
    <circle cx="{_CX}" cy="{_CY}" r="5.5" fill="var(--ink)"/>
    <circle cx="{_CX}" cy="{_CY}" r="2" fill="var(--paper)"/>
  </g>
</svg>"""


def _panel(headline, side, pct_html, gauge_html, detail_html):
    return f"""
<div class="verdict {side}">
  <div class="v-eyebrow">The Verdict</div>
  <div class="v-rule"></div>
  <div class="v-head">{headline}</div>
  <div class="v-pct">{pct_html}</div>
  <div class="v-sub">probability of AI authorship</div>
  {gauge_html}
  <div class="v-detail">{detail_html}</div>
</div>"""


IDLE_HTML = _panel(
    "Awaiting a passage", "idle", "&mdash;", _gauge(0.5, idle=True),
    "Paste a passage and press Analyze — the needle swings toward Human or AI "
    "and the score is explained in plain words.",
)


def classify(text: str):
    text = (text or "").strip()
    n_words = len(text.split())
    if n_words < 20:
        need = 20 - n_words
        return _panel(
            "Not enough text", "idle", "&mdash;", _gauge(0.5, idle=True),
            f"Please paste at least 20 words for a reliable estimate"
            f"{f' — {need} more to go' if n_words else ''}.",
        )
    p = float(detector.predict_proba([text])[0])
    headline, side = _interpret(p)
    detail = (f"{_explain(p)}<br><span class='v-meta'>{n_words} words examined "
              f"&middot; calibrated</span>")
    return _panel(headline, side, f"{p * 100:.1f}%", _gauge(p), detail)


EXAMPLES = [
    ["The proposed framework leverages a robust architecture to efficiently process large-scale data, "
     "demonstrating significant improvements across all evaluated benchmarks and establishing a new "
     "state of the art for the task under consideration."],
    ["honestly i wasn't sure the trip was gonna happen at all — the flight got delayed twice, my bag "
     "nearly didn't make it, and then it rained the whole first day. but somehow it turned out great."],
]

HEADER = """
<div class="pird-header">
  <div class="pird-eyebrow">Paraphrase-Robust &middot; Cross-Domain &middot; Calibrated</div>
  <h1 class="pird-title">PIRD</h1>
  <div class="pird-rule"><span>&#10086;</span></div>
  <p class="pird-sub">Was it written by human hand, or by machine? Paste a passage of at least twenty
  words and receive a calibrated verdict — robust to paraphrase and disguise.</p>
</div>
"""

FOOTER = """
<div class="pird-footer">
  Research demonstration — predictions are probabilistic and not infallible.
  Do not use as sole evidence of misconduct.
</div>
"""

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,600;0,700;1,500&family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&display=swap');

/* ---------- vintage palettes ----------
   Gradio emits its dark-mode variables under `:root.dark, :root .dark` (specificity 0,2,0),
   so these overrides live on <body> with higher specificity to win in both modes. */
:root:not(.dark) body:not(.dark) {
  --paper: #f2ecdc;          /* aged ivory */
  --panel: #f9f5e8;
  --ink: #2b241a;
  --ink-soft: #6f6249;
  --line: #d5c8a5;
  --accent: #8c6a2f;         /* antique bronze */
  --accent-strong: #6b4e1c;
  --ai-color: #a03a24;       /* oxblood (CVD-validated pair) */
  --human-color: #2e6ba3;    /* prussian blue */
}
:root.dark body, :root body.dark {
  --paper: #12100e;          /* vintage black */
  --panel: #1b1714;
  --ink: #eae1ca;
  --ink-soft: #a2937a;
  --line: #3d352a;
  --accent: #c9a24b;         /* antique gold */
  --accent-strong: #e2bd66;
  --ai-color: #c65a33;
  --human-color: #4f8ac4;
}

/* ---------- map onto Gradio variables ---------- */
:root:not(.dark) body:not(.dark), :root.dark body, :root body.dark {
  --body-background-fill: var(--paper);
  --background-fill-primary: var(--panel);
  --background-fill-secondary: var(--paper);
  --block-background-fill: var(--panel);
  --block-border-color: var(--line);
  --border-color-primary: var(--line);
  --border-color-accent: var(--accent);
  --body-text-color: var(--ink);
  --body-text-color-subdued: var(--ink-soft);
  --block-label-text-color: var(--ink-soft);
  --block-title-text-color: var(--ink-soft);
  --block-info-text-color: var(--ink-soft);
  --input-background-fill: var(--panel);
  --input-background-fill-focus: var(--panel);
  --input-border-color: var(--line);
  --input-border-color-focus: var(--accent);
  --input-placeholder-color: var(--ink-soft);
  --color-accent: var(--accent);
  --color-accent-soft: rgba(140, 106, 47, 0.14);
  --link-text-color: var(--accent-strong);
  --link-text-color-hover: var(--accent);
  --link-text-color-visited: var(--accent-strong);
  --button-secondary-background-fill: transparent;
  --button-secondary-background-fill-hover: var(--color-accent-soft);
  --button-secondary-border-color: var(--line);
  --button-secondary-text-color: var(--ink);
  --stat-background-fill: linear-gradient(90deg, var(--accent), var(--accent-strong));
  --loader-color: var(--accent);
  --block-shadow: none;
  --shadow-drop: none;
  --shadow-drop-lg: none;
  --block-radius: 3px;
  --input-radius: 3px;
  --button-large-radius: 3px;
  --button-small-radius: 3px;
}
:root:not(.dark) body:not(.dark) {
  --button-primary-background-fill: #3a2f20;
  --button-primary-background-fill-hover: #241c11;
  --button-primary-border-color: #3a2f20;
  --button-primary-text-color: #f6f0dd;
}
:root.dark body, :root body.dark {
  --button-primary-background-fill: var(--accent);
  --button-primary-background-fill-hover: var(--accent-strong);
  --button-primary-border-color: var(--accent);
  --button-primary-text-color: #171310;
}

body { background: var(--paper) !important; }

/* ---------- FULL-WIDTH container ---------- */
.gradio-container {
  max-width: 100% !important;
  width: 100% !important;
  margin: 0 !important;
  padding: 0 clamp(1rem, 4vw, 4rem) 2rem !important;
  position: relative;
  font-family: 'EB Garamond', Georgia, 'Times New Roman', serif !important;
  font-size: 17px;
  background: var(--paper) !important;
  background-image:
    radial-gradient(ellipse at 50% -8%, rgba(140, 106, 47, 0.10), transparent 55%),
    radial-gradient(ellipse at 12% 108%, rgba(140, 106, 47, 0.05), transparent 50%) !important;
}
.gradio-container * { font-family: inherit; }
.main, .wrap, .contain, .fillable { max-width: 100% !important; }

/* ---------- header ---------- */
.pird-header { text-align: center; padding: 2.6rem 1rem 0.4rem; }
.pird-eyebrow {
  letter-spacing: 0.38em; text-transform: uppercase;
  font-size: 0.72rem; color: var(--ink-soft);
}
.pird-title {
  font-family: 'Playfair Display', Georgia, serif !important;
  font-size: 4rem; font-weight: 700; letter-spacing: 0.16em;
  margin: 0.4rem 0 0.1rem; padding-left: 0.16em;
  color: var(--ink);
}
.pird-rule {
  display: flex; align-items: center; gap: 0.9rem; justify-content: center;
  max-width: 440px; margin: 0.5rem auto 1.1rem; color: var(--accent); font-size: 1.15rem;
}
.pird-rule::before, .pird-rule::after { content: ''; flex: 1; border-top: 1px solid var(--line); }
.pird-sub {
  font-style: italic; color: var(--ink-soft);
  font-size: 1.15rem; line-height: 1.55; max-width: 620px; margin: 0 auto;
}

/* ---------- theme toggle ---------- */
#theme-toggle {
  position: absolute; top: 16px; left: 16px; z-index: 10;
  width: auto; min-width: 0; flex: none;
  border: 1px solid var(--line); border-radius: 999px;
  background: var(--panel); color: var(--ink-soft);
  padding: 0.34rem 1rem; font-size: 0.72rem;
  letter-spacing: 0.2em; text-transform: uppercase;
  box-shadow: none; cursor: pointer;
}
#theme-toggle:hover { color: var(--accent-strong); border-color: var(--accent); }

/* ---------- blocks & inputs ---------- */
.block { border-color: var(--line) !important; }
textarea {
  font-size: 1.08rem !important; line-height: 1.7 !important;
  color: var(--ink) !important;
}
label span, .block-label, .label-wrap span {
  letter-spacing: 0.16em; text-transform: uppercase; font-size: 0.72rem !important;
  color: var(--ink-soft) !important;
}

/* ---------- buttons ---------- */
button.primary, button.secondary, button.sm, button.lg {
  text-transform: uppercase; letter-spacing: 0.18em;
  font-size: 0.8rem !important; font-weight: 600;
  box-shadow: none !important;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

/* ---------- VERDICT panel (mirrors web app) ---------- */
.verdict {
  border: 1px solid var(--line);
  outline: 4px solid var(--panel); outline-offset: -8px;   /* double-frame look */
  background: var(--panel);
  padding: 1.6rem 1.4rem 1.9rem;
  text-align: center;
  min-height: 100%;
}
.v-eyebrow { letter-spacing: 0.3em; text-transform: uppercase; font-size: 0.68rem; color: var(--ink-soft); }
.v-rule { width: 64px; height: 1px; background: var(--line); margin: 0.6rem auto 1.1rem; }
.v-head {
  font-family: 'Playfair Display', Georgia, serif !important;
  font-size: 1.7rem; font-weight: 700; line-height: 1.15;
}
.verdict.ai    .v-head { color: var(--ai-color); }
.verdict.human .v-head { color: var(--human-color); }
.verdict.idle  .v-head, .verdict.neutral .v-head { color: var(--ink-soft); }
.v-pct {
  font-family: 'Playfair Display', Georgia, serif !important;
  font-size: 4.4rem; font-weight: 600; line-height: 1; color: var(--ink); margin-top: 0.7rem;
}
.verdict.idle .v-pct { color: var(--ink-soft); opacity: 0.5; }
.v-sub { letter-spacing: 0.22em; text-transform: uppercase; font-size: 0.66rem; color: var(--ink-soft); margin-top: 0.4rem; }
.v-detail { font-style: italic; font-size: 1.04rem; line-height: 1.5; color: var(--ink); max-width: 30rem; margin: 0.6rem auto 0; }
.v-meta { display: inline-block; margin-top: 0.7rem; font-style: normal; letter-spacing: 0.2em; text-transform: uppercase; font-size: 0.64rem; color: var(--ink-soft); }
.gauge-svg { width: 100%; max-width: 360px; margin: 1.1rem auto 0.4rem; display: block; }
.gauge-svg .g-num { font-size: 9px; letter-spacing: 0.1em; fill: var(--ink-soft); }
.gauge-svg .g-end { font-size: 10.5px; letter-spacing: 0.18em; }
.g-needle { transition: transform 0.9s cubic-bezier(0.22, 1, 0.36, 1); }

/* ---------- examples & footer ---------- */
.gallery-item, .examples { font-size: 0.95rem; }
button.gallery-item, .example {
  background: var(--panel) !important;
  color: var(--ink) !important;
  border: 1px solid var(--line) !important;
  border-radius: 3px !important;
  text-align: left;
}
button.gallery-item:hover, .example:hover {
  border-color: var(--accent) !important;
  background: var(--color-accent-soft) !important;
}
.pird-footer {
  text-align: center; color: var(--ink-soft);
  font-size: 0.88rem; font-style: italic;
  border-top: 3px double var(--line);
  margin-top: 2.2rem; padding: 1.3rem 0 0.6rem;
}
footer { display: none !important; }  /* hide "Built with Gradio" strip */
"""

INIT_THEME_JS = """
() => {
  const saved = localStorage.getItem('pird-theme');
  const dark = saved ? saved === 'dark'
                     : window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.classList.toggle('dark', dark);
  document.body.classList.toggle('dark', dark);
}
"""

TOGGLE_THEME_JS = """
() => {
  const dark = !document.body.classList.contains('dark');
  document.documentElement.classList.toggle('dark', dark);
  document.body.classList.toggle('dark', dark);
  localStorage.setItem('pird-theme', dark ? 'dark' : 'light');
}
"""

theme = gr.themes.Base(
    font=[gr.themes.GoogleFont("EB Garamond"), "Georgia", "serif"],
    font_mono=[gr.themes.GoogleFont("IBM Plex Mono"), "ui-monospace", "monospace"],
    radius_size=gr.themes.sizes.radius_none,
)

with gr.Blocks(theme=theme, css=CSS, js=INIT_THEME_JS,
               title="PIRD — Paraphrase-Robust AI-Text Detector") as demo:
    theme_btn = gr.Button("◐ light · dark", elem_id="theme-toggle", size="sm")
    gr.HTML(HEADER)

    with gr.Row(equal_height=True):
        with gr.Column(scale=6):
            text_in = gr.Textbox(
                lines=13, label="Passage under examination",
                placeholder="Paste a passage of at least 20 words…",
            )
            with gr.Row():
                clear_btn = gr.ClearButton(value="Clear", size="lg")
                analyze_btn = gr.Button("Analyze", variant="primary", size="lg")
            gr.Examples(EXAMPLES, inputs=text_in, label="Specimens to try")
        with gr.Column(scale=5):
            verdict_out = gr.HTML(value=IDLE_HTML)

    gr.HTML(FOOTER)

    clear_btn.add([text_in])
    analyze_btn.click(classify, text_in, verdict_out)
    text_in.submit(classify, text_in, verdict_out)
    theme_btn.click(None, None, None, js=TOGGLE_THEME_JS)

if __name__ == "__main__":
    favicon = "favicon.ico" if os.path.exists("favicon.ico") else None
    demo.launch(favicon_path=favicon)
