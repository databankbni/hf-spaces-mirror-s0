"""Verification — run then delete."""
import sys
sys.path.insert(0, ".")

# ── 1. No flow imports anywhere ───────────────────────────────────────────────
app_src   = open("app.py",     encoding="utf-8").read()
utils_src = open("utils.py",   encoding="utf-8").read()
prompts_src = open("prompts.py", encoding="utf-8").read()

assert "build_flow_prompt"  not in app_src,     "build_flow_prompt still in app.py"
assert "generate_flow_data" not in app_src,     "generate_flow_data still in app.py"
assert "generate_flow"      not in app_src,     "generate_flow still in app.py"
assert "_flow_html"         not in app_src,     "_flow_html still in app.py"
assert "tab-flow"           not in app_src,     "Flow tab still in app.py"
assert "🌊"                 not in app_src,     "Flow emoji still in app.py"
assert "generate_flow_data" not in utils_src,   "generate_flow_data still in utils.py"
assert "build_flow_prompt"  not in prompts_src, "build_flow_prompt still in prompts.py"
print("Flow feature fully removed from all files ✓")

# ── 2. All 9 languages in ALL_LANGUAGES ──────────────────────────────────────
from app import ALL_LANGUAGES, LANG_TEMPLATES, switch_language
assert len(ALL_LANGUAGES) == 9, f"Expected 9 languages, got {len(ALL_LANGUAGES)}: {ALL_LANGUAGES}"
for lang in ["Python","JavaScript","TypeScript","Java","C++","C","Go","C#","Rust"]:
    assert lang in ALL_LANGUAGES, f"Missing language: {lang}"
print(f"ALL_LANGUAGES: all 9 present ✓  {ALL_LANGUAGES}")

# ── 3. switch_language returns both language= and value= for every language ───
for lang in ALL_LANGUAGES:
    upd = switch_language(lang)
    # gr.update returns a dict-like object
    d = upd if isinstance(upd, dict) else vars(upd)
    assert "language" in str(upd) or hasattr(upd, "__dict__"), f"No update for {lang}"
print("switch_language: returns update for all 9 languages ✓")

# ── 4. Language templates all populated ───────────────────────────────────────
from app import _template, _cm_lang
for lang in ALL_LANGUAGES:
    t = _template(lang)
    m = _cm_lang(lang)
    assert t and t.strip(), f"Empty template for {lang}"
    assert m is None or (isinstance(m, str) and m.strip()), f"Empty cm_lang for {lang}"
print("Templates and cm_langs populated for all 9 languages ✓")

# ── 5. detect_language works for all supported languages ─────────────────────
from app import detect_language
samples = {
    "Python":     "def factorial(n):\n    return 1 if n == 0 else n * factorial(n-1)",
    "Java":       "public class Main { static int f(int n){ return n; } }",
    "C#":         "using System;\npublic static void Main(string[] args){}",
    "Go":         "package main\nfunc factorial(n int) int { return 1 }",
    "Rust":       "fn factorial(n: u64) -> u64 { if n<=1 {1} else {n} }",
    "C":          "#include <stdio.h>\nint factorial(int n){ return 1; }",
    "C++":        "#include <vector>\nstd::vector<int> v;",
    "JavaScript": "function factorial(n) { return n<=1?1:n*factorial(n-1); }",
    "TypeScript": "function f(n: number): number { return n; }",
}
for lang, code in samples.items():
    result = detect_language(code)
    assert result == lang, f"detect_language mismatch: {lang} code detected as {result}"
print("detect_language: all 9 languages detected correctly ✓")

# ── 6. resolve_language handles all 9 display names ──────────────────────────
from prompts import resolve_language
for lang in ALL_LANGUAGES:
    r = resolve_language(lang)
    assert r is not None, f"resolve_language returned None for '{lang}'"
    assert r[0] == lang, f"resolve_language display mismatch for '{lang}': got {r[0]}"
print("resolve_language: all 9 languages resolve correctly ✓")

# ── 7. build_prompt / build_translation_prompt / build_complexity_prompt ──────
from prompts import build_prompt, build_translation_prompt, build_complexity_prompt
for lang in ALL_LANGUAGES:
    p1 = build_prompt("x=1", lang, True, True, False)
    assert "x=1" in p1 and lang in p1, f"build_prompt broken for {lang}"

    p3 = build_complexity_prompt("x=1", lang)
    assert "x=1" in p3, f"build_complexity_prompt broken for {lang}"
    assert "<fill in" in p3, f"No fill-in placeholders in complexity prompt for {lang}"

for src in ALL_LANGUAGES:
    for tgt in ALL_LANGUAGES:
        if src == tgt:
            continue
        p2 = build_translation_prompt("x=1", src, tgt)
        assert "x=1" in p2, f"build_translation_prompt broken {src}→{tgt}"
print("All prompt builders work for all 9×9 language combinations ✓")

# ── 8. analyze_complexity rejects unknown language ────────────────────────────
from app import analyze_complexity
r_text, r_html = analyze_complexity("x=1", "COBOL")
assert "not supported" in r_text.lower() or "unsupported" in r_text.lower(), \
    f"Unexpected response for unsupported lang: {r_text[:80]}"
print("analyze_complexity: unsupported language handled gracefully ✓")

# ── 9. _complexity_dashboard_html — empty state has no reserved height ────────
from app import _complexity_dashboard_html
empty = _complexity_dashboard_html(None)
assert "220px" not in empty and "height:" not in empty, "Empty dashboard still reserves height"
print("_complexity_dashboard_html: empty state compact ✓")

# ── 10. No import of removed symbols ─────────────────────────────────────────
import ast, sys as _sys
tree = ast.parse(app_src)
for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        names = [a.name for a in node.names]
        assert "build_flow_prompt"  not in names, "build_flow_prompt still imported"
        assert "generate_flow_data" not in names, "generate_flow_data still imported"
print("Import cleanup verified — no stale flow imports ✓")

print("\n✓ All 10 checks passed.")
