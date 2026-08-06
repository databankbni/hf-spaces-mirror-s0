"""
Language detector — maps file extensions to language names.
"""
from pathlib import Path

EXTENSION_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
    ".h": "C/C++ Header",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".md": "Markdown",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sql": "SQL",
    ".tf": "Terraform",
    ".dockerfile": "Dockerfile",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".rar",
    ".pdf", ".doc", ".docx",
    ".pyc", ".pyo", ".class", ".exe", ".dll", ".so",
}

CODE_EXTENSIONS = set(EXTENSION_MAP.keys())


def detect_language(file_path: str | Path) -> str:
    ext = Path(file_path).suffix.lower()
    return EXTENSION_MAP.get(ext, "Unknown")


def is_binary(file_path: str | Path) -> bool:
    ext = Path(file_path).suffix.lower()
    return ext in BINARY_EXTENSIONS


def is_code_file(file_path: str | Path) -> bool:
    ext = Path(file_path).suffix.lower()
    return ext in CODE_EXTENSIONS


def build_language_breakdown(file_paths: list[str]) -> dict[str, float]:
    """Returns language → percentage breakdown."""
    counts: dict[str, int] = {}
    total = 0
    for fp in file_paths:
        lang = detect_language(fp)
        if lang != "Unknown":
            counts[lang] = counts.get(lang, 0) + 1
            total += 1
    if total == 0:
        return {}
    return {lang: round(count / total * 100, 1) for lang, count in
            sorted(counts.items(), key=lambda x: -x[1])}
