# app.py — Codle AI Platform
#
# Security: HF_TOKEN is loaded exclusively from the environment via utils.py.
# No secrets are accepted from the UI, passed through Gradio state,
# or exposed in frontend JS/HTML/console output.

import sys
import os
import re as _re
import json
import logging
import datetime
import gradio as gr
from dotenv import load_dotenv

from prompts import (
    build_prompt,
    build_translation_prompt,
    build_complexity_prompt,
    resolve_language,
    SUPPORTED_LANGUAGES,
)
from utils import (
    generate_explanation,
    generate_translation,
    generate_complexity_analysis,
)

# ─── Startup ──────────────────────────────────────────────────────────────────
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _validate_config() -> None:
    if not os.getenv("HF_TOKEN", "").strip():
        logger.error("HF_TOKEN is not set. Add it to .env and restart.")
        sys.exit("Startup aborted: API configuration missing. Set HF_TOKEN in .env.")


_validate_config()

# ─── Asset loaders ────────────────────────────────────────────────────────────

def _read_asset(filename: str, fallback: str = "") -> str:
    path = os.path.join(os.path.dirname(__file__), "assets", filename)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return fallback


CSS    = _read_asset("styles.css")
JS_SRC = _read_asset("codle.js")

# ─── Language → starter template mapping ──────────────────────────────────────
# display_name → (codemirror_language_id, starter_code)
LANG_TEMPLATES: dict[str, tuple[str, str]] = {
    "Python": ("python", """\
def factorial(n):
    # Base case
    if n == 0:
        return 1
    # Recursive case
    return n * factorial(n - 1)
"""),
    "JavaScript": ("javascript", """\
// Recursive factorial
function factorial(n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}
"""),
    "TypeScript": ("javascript", """\
// Recursive factorial with TypeScript types
function factorial(n: number): number {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}
"""),
    "Java": ("java", """\
public class Main {
    // Recursive factorial
    static int factorial(int n) {
        if (n <= 1) return 1;
        return n * factorial(n - 1);
    }
}
"""),
    "C++": ("cpp", """\
#include <iostream>
// Recursive factorial
int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}
"""),
    "C": ("c", """\
#include <stdio.h>
/* Recursive factorial */
int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}
"""),
    "Go": ("go", """\
package main

// factorial computes n! recursively
func factorial(n int) int {
    if n <= 1 {
        return 1
    }
    return n * factorial(n-1)
}
"""),
    "C#": ("csharp", """\
public class Program {
    // Recursive factorial
    static int Factorial(int n) {
        if (n <= 1) return 1;
        return n * Factorial(n - 1);
    }
}
"""),
    "Rust": ("rust", """\
// Recursive factorial
fn factorial(n: u64) -> u64 {
    if n <= 1 { 1 } else { n * factorial(n - 1) }
}
"""),
}

ALL_LANGUAGES = list(LANG_TEMPLATES.keys())  # keeps insertion order

def _cm_lang(display: str) -> str | None:
    lang = LANG_TEMPLATES.get(display, ("python", ""))[0]
    supported = {
        "python", "c", "cpp", "markdown", "latex", "json", "html", "css", 
        "javascript", "jinja2", "typescript", "yaml", "dockerfile", "shell", "r", "sql"
    }
    return lang if lang in supported else None


def _template(display: str) -> str:
    return LANG_TEMPLATES.get(display, ("python", "# Start coding here\n"))[1]

def switch_language(lang: str):
    """Swap both syntax-highlight mode and starter template when dropdown changes."""
    return gr.update(language=_cm_lang(lang), value=_template(lang))

# ─── Language detector ────────────────────────────────────────────────────────
# Ordered rules — more specific languages first to avoid misclassification.
_LANG_PATTERNS: list[tuple[_re.Pattern, str]] = [
    (_re.compile(r'\bpublic\s+class\b|\bSystem\.out\.println\b|\bimport\s+java\.', _re.M), "Java"),
    (_re.compile(r'\busing\s+System\b|\bConsole\.Write|\bnamespace\s+\w+\s*[{;]|\bpublic\s+static\s+void\s+Main\b', _re.M), "C#"),
    (_re.compile(r'\bpackage\s+main\b|\bfmt\.Print|\bfunc\s+main\s*\(\)', _re.M), "Go"),
    (_re.compile(r'\bfn\s+\w+\s*\(|\blet\s+mut\b|\bprintln!\s*\(|\bimpl\b', _re.M), "Rust"),
    (_re.compile(r':\s*(string|number|boolean|void|any)\b|interface\s+\w+\s*\{', _re.M), "TypeScript"),
    (_re.compile(r'\bconst\s+\w+\s*=|\bfunction\s+\w+\s*\(|\bconsole\.log\b', _re.M), "JavaScript"),
    (_re.compile(r'#include\s*<[a-z_]+>\s*\n.*(?:std::|cout|cin|vector\s*<)', _re.M | _re.S), "C++"),
    (_re.compile(r'#include\s*<(?:stdio|stdlib|string)\.h>|\bprintf\s*\(|\bscanf\s*\(', _re.M), "C"),
    (_re.compile(r'^\s*def\s+\w+\s*\(|^\s*class\s+\w+\s*:|^\s*import\s+\w+|^\s*from\s+\w+\s+import', _re.M), "Python"),
]

def detect_language(code: str) -> str | None:
    """Heuristic language detection. Returns display name or None."""
    if not code or not code.strip():
        return None
    for pattern, lang in _LANG_PATTERNS:
        if pattern.search(code):
            return lang
    return None

# ─── Controller: Code Explanation ─────────────────────────────────────────────

def explain_code(
    code: str, language: str,
    bug_detection: bool, complexity_analysis: bool, simple_mode: bool,
) -> str:
    if not code or not code.strip():
        return "### ⚠️ Please enter or select some code to analyze."
    resolved = resolve_language(language)
    if not resolved:
        return f"### ⚠️ Language **{language}** is not supported. Please select a supported language."
    prompt = build_prompt(code, language, bug_detection, complexity_analysis, simple_mode)
    try:
        return generate_explanation(prompt)
    except RuntimeError as e:
        return f"### ❌ {e}"
    except Exception:
        logger.exception("Unexpected error in explain_code.")
        return "### ❌ An unexpected error occurred. Please try again later."


def save_report(text: str):
    _bad = ("Results will appear here", "⚠️", "❌", "No report")
    if not text or any(b in text for b in _bad):
        return gr.update(value=None, visible=False)
    filename = "codle_explanation_report.md"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(text)
        return gr.update(value=filename, visible=True)
    except Exception:
        logger.exception("Error saving report.")
        return gr.update(value=None, visible=False)


def export_json(explanation: str, language: str, code: str):
    _bad = ("Results will appear here", "⚠️", "❌")
    if not explanation or any(b in explanation for b in _bad):
        return gr.update(value=None, visible=False)
    data = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "language": language,
        "code_length": len(code),
        "explanation": explanation,
    }
    filename = "codle_report.json"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return gr.update(value=filename, visible=True)
    except Exception:
        logger.exception("Error saving JSON report.")
        return gr.update(value=None, visible=False)


def clear_all():
    return (
        "",
        "### AI Explanation\n\nResults will appear here.",
        gr.update(value=None, visible=False),
        gr.update(value=None, visible=False),
    )

# ─── Controller: Code Translator ──────────────────────────────────────────────

def translate_code(code: str, source_lang: str, target_lang: str):
    if not code or not code.strip():
        return "### ⚠️ Please enter code to translate.", "", "", ""
    if source_lang == target_lang:
        return "### ℹ️ Source and target languages are the same.", "", "", ""

    src_resolved = resolve_language(source_lang)
    tgt_resolved = resolve_language(target_lang)

    if not src_resolved:
        return f"### ⚠️ Source language **{source_lang}** is not supported.", "", "", ""
    if not tgt_resolved:
        return f"### ⚠️ Target language **{target_lang}** is not supported.", "", "", ""

    prompt = build_translation_prompt(code, source_lang, target_lang)
    try:
        result      = generate_translation(prompt)
        translated  = _extract_section(result, "Translated Code",        next_header="Translation Explanation")
        explanation = _extract_section(result, "Translation Explanation", next_header="Key Differences")
        differences = _extract_section(result, "Key Differences",         next_header="Optimization Notes")
        opt_notes   = _extract_section(result, "Optimization Notes")
        return translated or result, explanation, differences, opt_notes
    except RuntimeError as e:
        return f"### ❌ {e}", "", "", ""
    except Exception:
        logger.exception("Unexpected error in translate_code.")
        return "### ❌ An unexpected error occurred.", "", "", ""


def _extract_section(text: str, header: str, next_header: str = None) -> str:
    """Extract a markdown section by heading. Falls back to plain search."""
    pattern = rf"#{1,3}\s+{_re.escape(header)}\s*\n(.*?)"
    end_pat = rf"#{1,3}\s+{_re.escape(next_header)}" if next_header else r"$"
    match = _re.search(pattern + end_pat, text, _re.DOTALL | _re.IGNORECASE)
    if match:
        return match.group(1).strip()
    idx = text.lower().find(header.lower())
    if idx != -1:
        chunk = text[idx + len(header):].strip()
        if next_header:
            nidx = chunk.lower().find(next_header.lower())
            if nidx != -1:
                chunk = chunk[:nidx].strip()
        return chunk[:1200]
    return ""

# ─── Controller: Complexity Analysis ──────────────────────────────────────────

def analyze_complexity(code: str, language: str):
    if not code or not code.strip():
        return "*Enter code and click Analyze Complexity.*", _complexity_dashboard_html(None)

    resolved = resolve_language(language)
    if not resolved:
        return (
            f"### ⚠️ Language **{language}** is not supported for complexity analysis.",
            _complexity_dashboard_html(None),
        )

    # Non-blocking mismatch warning
    detected = detect_language(code)
    warn = ""
    if detected and detected != language:
        warn = (
            f"> ⚠️ **Language mismatch:** code looks like **{detected}** "
            f"but **{language}** is selected. Results may be inaccurate.\n\n"
        )

    prompt = build_complexity_prompt(code, language)
    try:
        result         = generate_complexity_analysis(prompt)
        dashboard_html = _build_complexity_dashboard(result)
        return warn + result, dashboard_html
    except RuntimeError as e:
        return f"### ❌ {e}", _complexity_dashboard_html(None)
    except Exception:
        logger.exception("Unexpected error in analyze_complexity.")
        return "### ❌ An unexpected error occurred.", _complexity_dashboard_html(None)


def _build_complexity_dashboard(report: str) -> str:
    """Parse LLM complexity report → HTML badge cards + chart."""
    def extract(pattern, text, default="—"):
        m = _re.search(pattern, text, _re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            # Strip markdown bold formatting and backticks
            val = val.strip("*").strip("`").strip()
            return val
        return default

    # Split report into Time and Space sections to prevent overall cross-matching
    time_sec = ""
    space_sec = ""
    parts = _re.split(r"##\s*Space Complexity", report, flags=_re.IGNORECASE)
    if len(parts) > 1:
        time_sec = parts[0]
        space_sec = parts[1]
    else:
        time_sec = report
        space_sec = report

    # Extract raw values
    time_overall  = extract(r"Overall:\s*([^\n]+)", time_sec)
    time_worst    = extract(r"Worst Case:\s*([^\n]+)", time_sec)
    time_avg      = extract(r"Average Case:\s*([^\n]+)", time_sec)
    space_overall = extract(r"Overall:\s*([^\n]+)", space_sec)
    
    # Try multiple class match patterns
    complexity_cls = extract(r"Complexity Class:\s*([^\n]+)", report, "Unknown")
    if complexity_cls == "Unknown":
        complexity_cls = extract(r"##\s*Complexity Class\s*\n([^\n]+)", report, "Unknown")

    # Clean raw values from HTML characters (like <, >) and LaTeX delimiters
    def clean_val(v: str) -> str:
        v = v.replace("<", "").replace(">", "").replace("\\(", "").replace("\\)", "").replace("$", "")
        v = v.strip()
        if v.startswith("(") and v.endswith(")"):
            v = v[1:-1].strip()
        return v

    time_overall   = clean_val(time_overall)
    time_worst     = clean_val(time_worst)
    time_avg       = clean_val(time_avg)
    space_overall  = clean_val(space_overall)
    complexity_cls = clean_val(complexity_cls)

    # Class maps for visual styling and highlights
    cls_map = {
        "constant": "class-constant",   "logarithmic": "class-log",
        "linearithmic": "class-linearithmic", "linear": "class-linear",
        "quadratic": "class-quadratic", "exponential": "class-exponential",
    }
    curve_map = {
        "constant": "O(1)",      "logarithmic": "O(log n)",
        "linearithmic": "O(n log n)", "linear": "O(n)",
        "quadratic": "O(n\u00b2)", "exponential": "O(2^n)",
    }
    
    cls_key = complexity_cls.lower().strip()
    css_cls  = next((v for k, v in cls_map.items()  if k in cls_key), "")
    highlight = curve_map.get(next((k for k in curve_map if k in cls_key), ""), "")

    return _complexity_dashboard_html({
        "time_overall": time_overall,
        "time_worst":   time_worst,
        "time_avg":     time_avg,
        "space":        space_overall,
        "cls":          complexity_cls,
        "css_cls":      css_cls,
        "highlight":    highlight,
    })



def _complexity_dashboard_html(data) -> str:
    if not data:
        return '<div class="cx-placeholder">Run complexity analysis to see the dashboard.</div>'

    hl_js = f'"{data["highlight"]}"' if data.get("highlight") else "null"

    return f"""
<div id="complexity-dashboard">
  <div class="complexity-card {data['css_cls']}">
    <span class="badge-O">{data['time_overall']}</span>
    <span class="badge-label">Time Overall</span>
  </div>
  <div class="complexity-card {data['css_cls']}">
    <span class="badge-O">{data['time_worst']}</span>
    <span class="badge-label">Worst Case</span>
  </div>
  <div class="complexity-card {data['css_cls']}">
    <span class="badge-O">{data['time_avg']}</span>
    <span class="badge-label">Average Case</span>
  </div>
  <div class="complexity-card">
    <span class="badge-O" style="color:#22d3ee">{data['space']}</span>
    <span class="badge-label">Space Overall</span>
  </div>
  <div class="complexity-card">
    <span class="badge-O" style="font-size:0.88rem;color:#a78bfa">{data['cls']}</span>
    <span class="badge-label">Class</span>
  </div>
</div>
<div id="complexity-chart-wrap">
  <canvas id="complexity-chart"></canvas>
</div>
<script>
(function(){{
  var HL={hl_js}, tries=0;
  function draw(){{
    var cv=document.getElementById("complexity-chart");
    var wr=document.getElementById("complexity-chart-wrap");
    if(!cv||!wr){{if(++tries<30)setTimeout(draw,200);return;}}
    if(!window.Codle||!Codle.ComplexityChart){{if(++tries<30)setTimeout(draw,200);return;}}
    wr.classList.add("has-chart");
    requestAnimationFrame(function(){{
      cv.width=wr.clientWidth||600; cv.height=wr.clientHeight||240;
      try{{Codle.ComplexityChart.animateDraw(cv,HL);}}
      catch(e){{console.warn("Chart draw failed:",e);}}
    }});
  }}
  draw();
}})();
</script>"""

# ─── HTML helpers ─────────────────────────────────────────────────────────────

def _header_html() -> str:
    svg = """<svg width="30" height="30" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="1" y="1" width="30" height="30" rx="8" stroke="#818cf8" stroke-width="1.5"/>
      <path d="M9 12 L14 16 L9 20" stroke="#818cf8" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M17 20 L23 20" stroke="#818cf8" stroke-width="1.8" stroke-linecap="round"/>
    </svg>"""
    return f"""
<canvas id="codle-particles"></canvas>
<div id="codle-header">
  <div id="codle-logo-wrap" style="background:transparent;border:none;box-shadow:none;
    width:34px;height:34px;animation:none;overflow:visible;display:flex;align-items:center;">
    {svg}
  </div>
  <span id="codle-title" style="font-size:1.05rem;font-weight:700;letter-spacing:1.5px;
    color:#c7d2fe;text-transform:uppercase;">CODLE AI</span>
</div>"""

def _kbd_strip_html() -> str:
    return """<div id="codle-kbd-strip">
  <span><kbd>Ctrl+Enter</kbd> Analyze</span>
  <span><kbd>Ctrl+K</kbd> Clear</span>
  <span><kbd>Ctrl+S</kbd> Save report</span>
  <span><kbd>Ctrl+Shift+C</kbd> Copy</span>
  <span><kbd>Ctrl+/</kbd> Command palette</span>
</div>"""

# ─── Example snippets ─────────────────────────────────────────────────────────

PYTHON_EX = """\
def factorial(n):
    if n < 0:
        raise ValueError("Factorial undefined for negatives")
    if n == 0 or n == 1:
        return 1
    return n * factorial(n - 1)"""

JS_EX = """\
async function fetchUserData(userId) {
    try {
        const response = await fetch(`https://api.example.com/users/${userId}`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error("Failed:", error);
        return null;
    }
}"""

CPP_EX = """\
#include <vector>
#include <algorithm>
void bubbleSort(std::vector<int>& arr) {
    int n = arr.size();
    for (int i = 0; i < n - 1; ++i)
        for (int j = 0; j < n - i - 1; ++j)
            if (arr[j] > arr[j+1])
                std::swap(arr[j], arr[j+1]);
}"""

JAVA_EX = """\
public class BinarySearch {
    static int binarySearch(int[] arr, int target) {
        int low = 0, high = arr.length - 1;
        while (low <= high) {
            int mid = low + (high - low) / 2;
            if (arr[mid] == target) return mid;
            else if (arr[mid] < target) low = mid + 1;
            else high = mid - 1;
        }
        return -1;
    }
}"""

GO_EX = """\
package main

func binarySearch(arr []int, target int) int {
    low, high := 0, len(arr)-1
    for low <= high {
        mid := low + (high-low)/2
        if arr[mid] == target {
            return mid
        } else if arr[mid] < target {
            low = mid + 1
        } else {
            high = mid - 1
        }
    }
    return -1
}"""

RUST_EX = """\
fn fibonacci(n: u64) -> u64 {
    match n {
        0 => 0,
        1 => 1,
        _ => fibonacci(n - 1) + fibonacci(n - 2),
    }
}"""

# ─── Gradio theme ──────────────────────────────────────────────────────────────
theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="slate",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("Fira Code"), "monospace"],
)

# ─── Gradio UI ────────────────────────────────────────────────────────────────

with gr.Blocks(
    title="Codle AI",
    theme=theme,
    css=CSS,
    head=f"<script>{JS_SRC}</script>",
) as demo:

    gr.HTML(_header_html())

    with gr.Tabs():

        # ══════════════════════════════════════════════════════════════════════
        # TAB 1 — Explain
        # ══════════════════════════════════════════════════════════════════════
        with gr.TabItem("🔍 Explain"):
            with gr.Row(equal_height=False):

                # Left — inputs
                with gr.Column(scale=5, min_width=300, elem_classes="glass-card"):
                    gr.HTML('<div class="section-label">Configuration</div>')

                    language = gr.Dropdown(
                        choices=ALL_LANGUAGES, value="Python",
                        label="Programming Language",
                        info="Changing language loads a starter template.",
                    )
                    code_input = gr.Code(
                        label="Code Editor",
                        language="python",
                        lines=22,
                        value=PYTHON_EX,
                        elem_classes="code-editor-wrap",
                    )

                    gr.HTML('<div class="section-label" style="margin-top:14px">Analysis Options</div>')
                    with gr.Row():
                        bug_detection = gr.Checkbox(
                            label="🐛 Bug Detector", value=True,
                            info="Logical errors, edge cases, security issues.",
                        )
                        complexity_analysis = gr.Checkbox(
                            label="📈 Complexity Analyzer", value=True,
                            info="Time & space complexity breakdown.",
                        )
                    simple_mode = gr.Checkbox(
                        label="👶 Explain Like I'm 10",
                        value=False,
                        info="Ultra-simple language for absolute beginners.",
                    )

                    with gr.Row():
                        explain_btn = gr.Button("🚀 Analyze Code", variant="primary", elem_classes="btn-primary")
                        clear_btn   = gr.Button("🗑 Clear",         elem_classes="btn-glass btn-clear")

                    gr.HTML(_kbd_strip_html())

                # Right — output
                with gr.Column(scale=7, min_width=360, elem_classes="glass-card"):
                    gr.HTML('<div class="section-label">AI Mentorship Report</div>')

                    output = gr.Markdown(
                        value="### AI Explanation\n\nResults will appear here.",
                        elem_classes="output-panel",
                    )

                    with gr.Row():
                        copy_btn          = gr.Button("📋 Copy",       elem_id="copy_btn",          elem_classes="btn-glass")
                        download_md_btn   = gr.Button("📥 Markdown",   elem_classes="btn-glass btn-download-md")
                        download_json_btn = gr.Button("📊 JSON",       elem_classes="btn-glass btn-download-json")

                    with gr.Row():
                        file_output      = gr.File(label="Markdown Report", visible=False)
                        json_file_output = gr.File(label="JSON Report",     visible=False)

            gr.Markdown("---\n### 💡 Code Templates")
            gr.Examples(
                examples=[
                    [PYTHON_EX, "Python"],
                    [JS_EX,     "JavaScript"],
                    [CPP_EX,    "C++"],
                    [JAVA_EX,   "Java"],
                    [GO_EX,     "Go"],
                    [RUST_EX,   "Rust"],
                ],
                inputs=[code_input, language],
            )

        # ══════════════════════════════════════════════════════════════════════
        # TAB 2 — Translate
        # ══════════════════════════════════════════════════════════════════════
        with gr.TabItem("🔄 Translate"):
            with gr.Row():
                with gr.Column(scale=1, elem_classes="glass-card"):
                    gr.HTML('<div class="section-label">Source</div>')
                    src_lang = gr.Dropdown(
                        choices=ALL_LANGUAGES, value="Python",
                        label="Source Language",
                    )
                    src_code = gr.Code(
                        label="Source Code",
                        language="python",
                        lines=20,
                        value=PYTHON_EX,
                        elem_classes="code-editor-wrap",
                    )

                with gr.Column(scale=1, elem_classes="glass-card"):
                    gr.HTML('<div class="section-label">Target</div>')
                    tgt_lang = gr.Dropdown(
                        choices=ALL_LANGUAGES, value="JavaScript",
                        label="Target Language",
                    )
                    translate_btn = gr.Button(
                        "⚡ Translate Code", variant="primary", elem_classes="btn-primary",
                    )
                    gr.Markdown(
                        "_All 9 languages supported. Selects a starter template on dropdown change._",
                    )

            with gr.Tabs():
                with gr.TabItem("📄 Converted Code"):
                    translated_output = gr.Markdown(
                        value="*Translation will appear here.*",
                        elem_classes="output-panel",
                    )
                with gr.TabItem("💬 Explanation"):
                    translation_explanation = gr.Markdown(
                        value="*Explanation will appear here.*",
                        elem_classes="output-panel",
                    )
                with gr.TabItem("🔀 Key Differences"):
                    translation_diff = gr.Markdown(
                        value="*Differences will appear here.*",
                        elem_classes="output-panel",
                    )
                with gr.TabItem("⚡ Optimization Notes"):
                    translation_opts = gr.Markdown(
                        value="*Optimization notes will appear here.*",
                        elem_classes="output-panel",
                    )

        # ══════════════════════════════════════════════════════════════════════
        # TAB 3 — Complexity
        # ══════════════════════════════════════════════════════════════════════
        with gr.TabItem("📈 Complexity"):
            with gr.Row():
                with gr.Column(scale=4, min_width=280, elem_classes="glass-card"):
                    gr.HTML('<div class="section-label">Code Input</div>')
                    cx_lang = gr.Dropdown(
                        choices=ALL_LANGUAGES, value="Python",
                        label="Language",
                    )
                    cx_code = gr.Code(
                        label="Code to Analyze",
                        language="python",
                        lines=20,
                        value=PYTHON_EX,
                        elem_classes="code-editor-wrap",
                    )
                    cx_btn = gr.Button(
                        "📊 Analyze Complexity", variant="primary", elem_classes="btn-primary",
                    )

                with gr.Column(scale=6, elem_classes="glass-card"):
                    gr.HTML('<div class="section-label">Complexity Dashboard</div>')
                    cx_dashboard = gr.HTML(value=_complexity_dashboard_html(None))
                    gr.HTML('<div class="section-label" style="margin-top:18px">Full Report</div>')
                    cx_output = gr.Markdown(
                        value="*Complexity analysis will appear here.*",
                        elem_classes="output-panel",
                    )

    # ─── Event bindings ───────────────────────────────────────────────────────

    # Tab 1 — Explain
    language.change(switch_language, inputs=language, outputs=code_input)

    explain_btn.click(
        explain_code,
        inputs=[code_input, language, bug_detection, complexity_analysis, simple_mode],
        outputs=output,
    )
    clear_btn.click(
        clear_all,
        outputs=[code_input, output, file_output, json_file_output],
    )
    copy_btn.click(
        fn=None, inputs=[output], outputs=None,
        js="""(text) => {
            if (!text || text.includes("Results will appear here") || text.includes("Please enter")) {
                Codle && Codle.Toast.info("No report to copy yet.");
                return;
            }
            navigator.clipboard.writeText(text)
                .then(() => Codle && Codle.Toast.success("Report copied!"))
                .catch(() => Codle && Codle.Toast.error("Clipboard access denied."));
        }""",
    )
    download_md_btn.click(save_report, inputs=output, outputs=file_output)
    download_json_btn.click(
        export_json,
        inputs=[output, language, code_input],
        outputs=json_file_output,
    )

    # Tab 2 — Translate
    # Source language change: swap syntax + template in source editor
    src_lang.change(switch_language, inputs=src_lang, outputs=src_code)

    translate_btn.click(
        translate_code,
        inputs=[src_code, src_lang, tgt_lang],
        outputs=[translated_output, translation_explanation, translation_diff, translation_opts],
    )

    # Tab 3 — Complexity
    cx_lang.change(switch_language, inputs=cx_lang, outputs=cx_code)

    cx_btn.click(
        analyze_complexity,
        inputs=[cx_code, cx_lang],
        outputs=[cx_output, cx_dashboard],
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
    )
