"""
Pattern matcher — regex patterns for risk detection (secrets, API keys, etc.)
"""
import re
from dataclasses import dataclass


@dataclass
class PatternMatch:
    pattern_name: str
    line_number: int
    line_content: str
    severity: str


# ── Secret / credential patterns ──────────────────────────────────────────────
SECRET_PATTERNS: list[tuple[str, str, str]] = [
    # (name, regex, severity)
    ("AWS Access Key",        r"AKIA[0-9A-Z]{16}",                         "critical"),
    ("AWS Secret Key",        r"(?i)aws.{0,20}secret.{0,20}['\"][0-9a-zA-Z/+]{40}['\"]", "critical"),
    ("Generic API Key",       r"(?i)(api[_-]?key|apikey)\s*=\s*['\"][a-zA-Z0-9_\-]{16,}['\"]", "high"),
    ("Generic Token",         r"(?i)(token|secret|password|passwd|pwd)\s*=\s*['\"][^'\"]{8,}['\"]", "high"),
    ("GitHub Token",          r"ghp_[a-zA-Z0-9]{36}",                      "critical"),
    ("Private Key Header",    r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----", "critical"),
    # Require a long token-shaped value — bare "Bearer " + short word is
    # almost always docs or a header-building snippet, not a real secret
    ("Bearer Token",          r"(?i)bearer\s+[a-zA-Z0-9\-._~+/]{25,}=*",   "medium"),
    ("Database URL",          r"(?i)(mysql|postgres|mongodb|redis):\/\/[^@\s]+@", "critical"),
    ("Hardcoded Password",    r"(?i)password\s*=\s*['\"][^'\"]{4,}['\"]",   "high"),
    ("Slack Webhook",         r"https://hooks\.slack\.com/services/[A-Z0-9/]+", "medium"),
    ("Google API Key",        r"AIza[0-9A-Za-z\-_]{35}",                   "critical"),
    ("SendGrid API Key",      r"SG\.[a-zA-Z0-9\-_]{22}\.[a-zA-Z0-9\-_]{43}", "critical"),
    ("Stripe Secret Key",     r"sk_live_[0-9a-zA-Z]{24,}",                 "critical"),
    ("JWT Secret",            r"(?i)jwt[_-]?secret\s*=\s*['\"][^'\"]{8,}['\"]", "high"),
]

# ── Code smell patterns ────────────────────────────────────────────────────────
TODO_PATTERN = re.compile(r"(?i)\b(TODO|FIXME|HACK|XXX|BUG)\b")
PRINT_DEBUG_PATTERN = re.compile(r"\bprint\s*\(|console\.log\s*\(|System\.out\.print")


# Values that indicate a placeholder / template rather than a live secret
_PLACEHOLDER_RE = re.compile(
    r"(?i)("
    r"your[-_ ]?(api[-_ ]?key|token|secret|password)|"
    r"example|placeholder|changeme|change[-_ ]me|dummy|sample|redacted|"
    r"<[^>]+>|\$\{[^}]*\}|\{\{[^}]*\}\}|%\([^)]*\)s|"          # template vars
    r"os\.environ|process\.env|getenv|env\(|secrets\.|config\."  # env lookups
    r")"
)


def scan_file_for_secrets(file_path: str, content: str) -> list[PatternMatch]:
    """Scan file content for hardcoded secrets and credentials."""
    matches: list[PatternMatch] = []
    lines = content.splitlines()
    for line_num, line in enumerate(lines, start=1):
        # Skip obvious placeholders/templates and env-var lookups — flagging
        # them buries the real findings in noise
        if _PLACEHOLDER_RE.search(line):
            continue
        for name, pattern, severity in SECRET_PATTERNS:
            if re.search(pattern, line):
                matches.append(PatternMatch(
                    pattern_name=name,
                    line_number=line_num,
                    line_content=line.strip()[:120],  # truncate long lines
                    severity=severity,
                ))
    return matches


def count_todos(content: str) -> int:
    return len(TODO_PATTERN.findall(content))


def count_debug_prints(content: str) -> int:
    return len(PRINT_DEBUG_PATTERN.findall(content))
