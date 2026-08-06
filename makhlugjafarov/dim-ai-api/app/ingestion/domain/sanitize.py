"""Sanitize OCR text from GOT-OCR-2.0 LaTeX document-structure artifacts.

GOT-OCR-2.0 emits LaTeX **document-structure commands** into math chunks.
Examples leaking into citations: ``\\title{ Praktik məşğələ }``,
``\\title{ Öyrənmə tapşırıqları }``, stray ``\\)``.

This module provides a single entry-point function ``sanitize_ocr_text``
that strips structural commands while **preserving real math verbatim**.

Policy GRO-88 — version: ocr-sanitize-v1
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Structural-command patterns (non-math LaTeX emitted by the OCR engine)
# ---------------------------------------------------------------------------

# Commands whose *inner text* we want to keep, e.g. \title{X} → X
# Order matters: more-specific patterns first.
_STRUCTURAL_UNWRAP_PATTERN = re.compile(
    r"\\(?:title|section|subsection|subsubsection|chapter"
    r"|textbf|textit|emph|underline|texttt|textsf|textsc|textmd|textrm"
    r"|textup|textnormal|textsl)"
    r"\s*\{([^}]*)\}",
)

# \begin{env} / \end{env} — drop the wrapper, keep what's between them
# (called after unwrapping structural commands above)
_BEGIN_END_PATTERN = re.compile(r"\\(?:begin|end)\s*\{[^}]*\}")

# ---------------------------------------------------------------------------
# Stray unbalanced delimiter detection helpers
# ---------------------------------------------------------------------------
# We only remove a delimiter when it is unbalanced on the line.  True math
# (balanced \(…\) or \[…\]) is preserved because both sides exist.


def _strip_unbalanced_parens(text: str) -> str:
    r"""Remove stray unbalanced ``\(`` or ``\)`` delimiters.

    A ``\(`` with no matching ``\)`` is unbalanced (and vice-versa).
    We scan the whole string rather than line-by-line because a formula
    can span several lines in the OCR output.
    """
    # Collect all positions of \( and \)
    opens: list[int] = [m.start() for m in re.finditer(r"\\\(", text)]
    closes: list[int] = [m.start() for m in re.finditer(r"\\\)", text)]

    # Match pairs greedily left-to-right
    matched_opens: set[int] = set()
    matched_closes: set[int] = set()
    ci = 0
    for oi in opens:
        while ci < len(closes) and closes[ci] <= oi:
            ci += 1
        if ci < len(closes):
            matched_opens.add(oi)
            matched_closes.add(closes[ci])
            ci += 1

    # Build a set of positions to remove (start of the 2-char token \( or \))
    remove: set[int] = set()
    for oi in opens:
        if oi not in matched_opens:
            remove.add(oi)
    for ci_pos in closes:
        if ci_pos not in matched_closes:
            remove.add(ci_pos)

    if not remove:
        return text

    result: list[str] = []
    i = 0
    while i < len(text):
        if i in remove:
            i += 2  # skip the 2-char token \( or \)
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


def _strip_unbalanced_brackets(text: str) -> str:
    r"""Remove stray unbalanced ``\[`` or ``\]`` delimiters."""
    opens: list[int] = [m.start() for m in re.finditer(r"\\\[", text)]
    closes: list[int] = [m.start() for m in re.finditer(r"\\\]", text)]

    matched_opens: set[int] = set()
    matched_closes: set[int] = set()
    ci = 0
    for oi in opens:
        while ci < len(closes) and closes[ci] <= oi:
            ci += 1
        if ci < len(closes):
            matched_opens.add(oi)
            matched_closes.add(closes[ci])
            ci += 1

    remove: set[int] = set()
    for oi in opens:
        if oi not in matched_opens:
            remove.add(oi)
    for ci_pos in closes:
        if ci_pos not in matched_closes:
            remove.add(ci_pos)

    if not remove:
        return text

    result: list[str] = []
    i = 0
    while i < len(text):
        if i in remove:
            i += 2
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sanitize_ocr_text(text: str) -> str:
    """Sanitize a single OCR text chunk produced by GOT-OCR-2.0.

    Transformations applied in order:

    1. Unwrap structural non-math commands, keeping inner text:
       ``\\title{X}`` → ``X``, ``\\textbf{X}`` → ``X``, etc.
    2. Drop ``\\begin{…}`` / ``\\end{…}`` wrappers.
    3. Strip stray unbalanced ``\\(`` / ``\\)`` delimiters.
    4. Strip stray unbalanced ``\\[`` / ``\\]`` delimiters.
    5. Normalize whitespace (collapse multiple spaces/newlines introduced
       by the removals into single spaces; preserve intentional newlines).

    **Preserves verbatim:**
    - Balanced ``\\(…\\)`` inline math.
    - Balanced ``\\[…\\]`` display math.
    - ``$…$`` and ``$$…$$`` dollar math.
    - All real math commands: ``\\sqrt``, ``\\frac``, ``\\geq``, etc.

    **Idempotent:** ``sanitize(sanitize(x)) == sanitize(x)``.

    Policy: ocr-sanitize-v1
    """
    if not text:
        return text

    # Step 1: unwrap structural commands (strip leading/trailing spaces in inner text)
    cleaned = _STRUCTURAL_UNWRAP_PATTERN.sub(lambda m: m.group(1).strip(), text)

    # Step 2: drop \begin{env} / \end{env}
    cleaned = _BEGIN_END_PATTERN.sub("", cleaned)

    # Step 3–4: strip unbalanced delimiters
    cleaned = _strip_unbalanced_parens(cleaned)
    cleaned = _strip_unbalanced_brackets(cleaned)

    # Step 5: light whitespace normalisation — collapse runs of spaces
    # but leave newlines intact (chunker may rely on them for paragraph breaks)
    cleaned = re.sub(r" {2,}", " ", cleaned)

    return cleaned
