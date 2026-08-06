# prompts.py
# All prompt builders for every AI feature in the platform.

# ─────────────────────────────────────────────────────────────────────────────
# Language registry
# Maps internal keys → display names and code-fence identifiers
# ─────────────────────────────────────────────────────────────────────────────

# key → (display name, markdown fence id)
SUPPORTED_LANGUAGES: dict[str, tuple[str, str]] = {
    "python":     ("Python",     "python"),
    "java":       ("Java",       "java"),
    "javascript": ("JavaScript", "javascript"),
    "typescript": ("TypeScript", "typescript"),
    "c":          ("C",          "c"),
    "cpp":        ("C++",        "cpp"),
    "csharp":     ("C#",         "csharp"),
    "go":         ("Go",         "go"),
    "rust":       ("Rust",       "rust"),
}

# Alias map: any UI display name → internal key
_ALIASES: dict[str, str] = {
    # canonical display names
    "python": "python", "java": "java", "javascript": "javascript",
    "typescript": "typescript", "c": "c", "c++": "cpp", "c#": "csharp",
    "go": "go", "rust": "rust",
    # common aliases
    "js": "javascript", "ts": "typescript", "golang": "go",
    "csharp": "csharp", "cpp": "cpp", "c plus plus": "cpp",
}


def resolve_language(name: str) -> tuple[str, str] | None:
    """
    Resolve a language name/alias to (display_name, fence_id).
    Returns None if the language is not supported.
    """
    key = _ALIASES.get(name.strip().lower())
    if key is None:
        return None
    return SUPPORTED_LANGUAGES[key]

# ─────────────────────────────────────────────────────────────────────────────
# Feature 1 — Code Explanation (original, preserved)
# ─────────────────────────────────────────────────────────────────────────────

def build_prompt(
    code: str,
    language: str,
    bug_detection: bool,
    complexity_analysis: bool,
    simple_mode: bool,
) -> str:
    """Builds the explanation prompt based on user feature toggles."""
    role_instruction = "You are an expert software engineer and coding mentor."
    if simple_mode:
        role_instruction += (
            " Use very simple language suitable for explaining concepts to a 10-year-old child."
        )

    complexity_section = (
        """# Complexity Analysis\n\nExplain:\n- Time Complexity\n- Space Complexity\n- Optimization Opportunities"""
        if complexity_analysis
        else """# Time Complexity\n\nMention complexity.\n\n# Space Complexity\n\nMention complexity."""
    )

    bug_section = (
        """# Bug Detection\n\nFind:\n- Logical errors\n- Edge cases\n- Missing validations\n- Security concerns"""
        if bug_detection
        else """# Potential Bugs\n\nMention any bugs or edge cases."""
    )

    resolved = resolve_language(language)
    fence = resolved[1] if resolved else language.lower().replace("#", "sharp").replace("+", "p")

    return f"""{role_instruction}

Analyze the {language} code below.

Return your response in markdown format with these exact sections.

# Summary

Explain what the code does in 2-3 sentences.

# Line-by-Line Explanation

Explain each major block of lines clearly. Use code references like `line N`.

{complexity_section}

# Improvements

Provide exactly 3 concrete improvements as numbered list items.

{bug_section}

Code:
```{fence}
{code}
```
"""


# ─────────────────────────────────────────────────────────────────────────────
# Feature 2 — Code Translator
# ─────────────────────────────────────────────────────────────────────────────

def build_translation_prompt(
    code: str,
    source_lang: str,
    target_lang: str,
) -> str:
    """
    Builds the code translation prompt.
    source_lang / target_lang are display names (e.g. "C#", "Go", "Rust").
    The correct markdown fence identifiers are resolved from the registry.
    """
    src = resolve_language(source_lang)
    tgt = resolve_language(target_lang)

    src_display  = src[0] if src else source_lang
    src_fence    = src[1] if src else source_lang.lower().replace("#", "sharp").replace("+", "p")
    tgt_display  = tgt[0] if tgt else target_lang
    tgt_fence    = tgt[1] if tgt else target_lang.lower().replace("#", "sharp").replace("+", "p")

    return f"""You are an expert polyglot software engineer. Your task is to translate source code accurately.

Translate the {src_display} code below into idiomatic, production-quality {tgt_display}.

Rules:
- Preserve ALL comments (translate comment text to English if needed)
- Preserve the original logic exactly — do not add or remove functionality
- Preserve function names, variable names, and overall structure
- Use idiomatic {tgt_display} patterns (e.g. goroutines in Go, pattern matching in Rust, interfaces in Java)
- If a concept has no direct equivalent, use the closest idiomatic approach and note it

Return your response in this EXACT markdown format. Use the exact section headings shown:

# Translated Code

```{tgt_fence}
<translated code here — complete, runnable, no placeholders>
```

# Translation Explanation

Explain the key translation decisions in 2–4 sentences.

# Key Differences

List 3–5 bullet points comparing {src_display} vs {tgt_display} for this specific code.

# Optimization Notes

List any {tgt_display}-specific optimizations applied, or idioms that could further improve the code.

Source {src_display} Code:
```{src_fence}
{code}
```
"""


# ─────────────────────────────────────────────────────────────────────────────
# Feature 3 — Complexity Analysis (structured output for dashboard)
# ─────────────────────────────────────────────────────────────────────────────

def build_complexity_prompt(code: str, language: str) -> str:
    """Builds a structured complexity analysis prompt for the visual dashboard."""
    resolved = resolve_language(language)
    fence = resolved[1] if resolved else language.lower().replace("#", "sharp").replace("+", "p")
    display = resolved[0] if resolved else language

    return f"""You are an expert algorithm analyst specializing in {display} code.

Analyze the {display} code below and determine its time and space complexity.

IMPORTANT: Fill in REAL complexity values (like O(n), O(n²), O(log n), O(1), O(n log n), O(2^n)).
Do NOT leave placeholder text like O(?). Replace every O(?) with the actual complexity.

Return your response in this EXACT markdown format:

# Complexity Report

## Time Complexity
**Overall:** <fill in e.g. O(n)>
**Best Case:** <fill in>
**Average Case:** <fill in>
**Worst Case:** <fill in>

## Space Complexity
**Overall:** <fill in e.g. O(n)>
**Auxiliary Space:** <fill in>
**Recursive Stack Depth:** <fill in or write N/A>

## Performance Bottlenecks
List up to 3 bottlenecks as bullet points. If none, write "None identified."

## Optimization Opportunities
List up to 3 concrete optimization suggestions as numbered items.

## Complexity Class
Classify as exactly one of: Constant, Logarithmic, Linear, Linearithmic, Quadratic, Exponential, Factorial

Code:
```{fence}
{code}
```
"""


# ─────────────────────────────────────────────────────────────────────────────
# (Flow feature removed)
# ─────────────────────────────────────────────────────────────────────────────
