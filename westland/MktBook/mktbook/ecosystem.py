"""
Ecosystem A/B assignment helpers for Workout #5.

The authoritative source of a bot's ecosystem is a machine-written tag
injected at the very start of behavior_rules whenever the student saves
the bot form.  The tag format is:

    ECO_OVERRIDE=A
    <rest of student's rules text>

All text-based heuristics (per-pane voting) are used only as a fallback
when no override tag is present (e.g. bots created before this feature).
"""

_TAG_A = "ECO_OVERRIDE=A"
_TAG_B = "ECO_OVERRIDE=B"


def inject_ecosystem_tag(behavior_rules: str, ecosystem: str) -> str:
    """Prepend (or replace) the override tag in behavior_rules."""
    stripped = strip_ecosystem_tag(behavior_rules)
    tag = _TAG_A if ecosystem.upper() == "A" else _TAG_B
    return f"{tag}\n{stripped}" if stripped else tag


def strip_ecosystem_tag(behavior_rules: str) -> str:
    """Return behavior_rules with the override tag line removed (for display)."""
    lines = (behavior_rules or "").split("\n")
    filtered = [l for l in lines if not l.strip().upper().startswith("ECO_OVERRIDE=")]
    return "\n".join(filtered).strip()


def read_ecosystem_tag(behavior_rules: str) -> str | None:
    """Return 'A', 'B', or None if no tag is present."""
    for line in (behavior_rules or "").split("\n"):
        upper = line.strip().upper()
        if upper.startswith("ECO_OVERRIDE="):
            val = upper[len("ECO_OVERRIDE="):]
            if val in ("A", "B"):
                return val
    return None


def _pane_votes(field: str, letter: str, other: str) -> bool:
    """A pane votes for `letter` only if it mentions that ecosystem but not the other."""
    names = (f"ecosystem {letter}", f"eco {letter}")
    rival = (f"ecosystem {other}", f"eco {other}")
    return any(n in field for n in names) and not any(rv in field for rv in rival)


def detect_ecosystem(bot) -> str:
    """Return 'Ecosystem A' or 'Ecosystem B' for a bot.

    Priority:
    1. Explicit override tag in behavior_rules (set via the ecosystem selector).
    2. Per-pane voting across personality / objective / behavior_rules.
    3. Default: Ecosystem B.
    """
    tag = read_ecosystem_tag(bot.behavior_rules or "")
    if tag:
        return f"Ecosystem {tag}"

    p = (bot.personality or "").lower()
    o = (bot.objective or "").lower()
    r = strip_ecosystem_tag(bot.behavior_rules or "").lower()

    votes_a = _pane_votes(p, "a", "b") or _pane_votes(o, "a", "b") or _pane_votes(r, "a", "b")
    votes_b = _pane_votes(p, "b", "a") or _pane_votes(o, "b", "a") or _pane_votes(r, "b", "a")

    if votes_a and not votes_b:
        return "Ecosystem A"
    return "Ecosystem B"
