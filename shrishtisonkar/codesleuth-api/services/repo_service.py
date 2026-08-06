"""
Repo Service — clone GitHub repos, walk file trees, extract metadata.
"""
import os
import asyncio
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from git import Repo, GitCommandError, InvalidGitRepositoryError

from config import get_settings
from utils.logger import get_logger
from utils.language_detector import (
    detect_language, is_binary, is_code_file, build_language_breakdown
)

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class FileEntry:
    path: str            # relative path within repo
    abs_path: str
    language: str
    line_count: int
    size_bytes: int
    is_binary: bool


@dataclass
class RepoMetadata:
    repo_name: str
    repo_url: str
    branch: str
    clone_path: str
    files: list[FileEntry] = field(default_factory=list)
    total_lines: int = 0
    total_files: int = 0
    language_breakdown: dict[str, float] = field(default_factory=dict)
    contributors: int = 0
    last_commit: str | None = None
    readme_content: str | None = None
    entry_points: list[str] = field(default_factory=list)


IGNORE_DIRS = {
    ".git", ".github", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", ".nuxt", "coverage",
    ".cache", ".idea", ".vscode", "vendor", "target", "out",
}

ENTRY_POINT_NAMES = {
    "main.py", "app.py", "server.py", "index.py", "run.py",
    "main.js", "index.js", "app.js", "server.js",
    "main.ts", "index.ts", "app.ts",
    "main.go", "main.java", "Main.java",
    "main.rs", "main.cpp",
}


class RepoService:
    def get_clone_path(self, session_id: str) -> Path:
        return Path(settings.storage_path) / session_id / "repo"

    def _build_clone_url(self, repo_url: str, token: str | None) -> str:
        if token and "github.com" in repo_url:
            # inject token: https://TOKEN@github.com/org/repo.git
            return repo_url.replace("https://", f"https://{token}@")
        return repo_url

    def clone(self, session_id: str, repo_url: str, branch: str = "main",
              token: str | None = None) -> Path:
        clone_path = self.get_clone_path(session_id)
        clone_path.mkdir(parents=True, exist_ok=True)

        clone_url = self._build_clone_url(repo_url, token)
        logger.info(f"[{session_id}] Cloning {repo_url} → {clone_path}")

        def _redact(msg: str) -> str:
            """Strip the auth token from git error text so it never reaches
            logs or the status endpoint shown in the UI."""
            return msg.replace(token, "***") if token else msg

        try:
            try:
                Repo.clone_from(
                    clone_url,
                    str(clone_path),
                    branch=branch,
                    depth=1,          # shallow clone — fast
                    single_branch=True,
                )
            except GitCommandError as e:
                # Retry on the repo's default branch — the requested branch may
                # simply not exist (e.g. "main" vs "master"). Git error text
                # varies across versions, so don't try to string-match it.
                logger.warning(
                    f"[{session_id}] Clone with branch '{branch}' failed "
                    f"({_redact(str(e))[:200]}), retrying default branch"
                )
                # A failed attempt can leave a partial checkout behind
                shutil.rmtree(clone_path, ignore_errors=True)
                clone_path.mkdir(parents=True, exist_ok=True)
                Repo.clone_from(clone_url, str(clone_path), depth=1)
        except GitCommandError as e:
            raise RuntimeError(f"Git clone failed: {_redact(str(e))}") from None
        logger.info(f"[{session_id}] Clone complete ✓")
        return clone_path

    def walk_files(self, clone_path: Path) -> list[FileEntry]:
        """Walk the repo directory tree and collect all non-binary file entries."""
        entries: list[FileEntry] = []

        for root, dirs, files in os.walk(clone_path):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

            for filename in files:
                abs_path = Path(root) / filename
                rel_path = str(abs_path.relative_to(clone_path))

                if is_binary(abs_path):
                    continue

                try:
                    size = abs_path.stat().st_size
                    if size > 1_000_000:  # skip files >1MB
                        continue
                    content = abs_path.read_text(encoding="utf-8", errors="replace")
                    line_count = content.count("\n") + 1
                except Exception:
                    continue

                entries.append(FileEntry(
                    path=rel_path.replace("\\", "/"),
                    abs_path=str(abs_path),
                    language=detect_language(abs_path),
                    line_count=line_count,
                    size_bytes=size,
                    is_binary=False,
                ))
        return entries

    def extract_metadata(self, session_id: str, repo_url: str,
                         branch: str, clone_path: Path,
                         files: list[FileEntry]) -> RepoMetadata:
        repo_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
        file_paths = [f.path for f in files]
        total_lines = sum(f.line_count for f in files)

        # Git metadata
        contributors = 0
        last_commit = None
        try:
            repo = Repo(str(clone_path))
            contributors = len(set(c.author.email for c in repo.iter_commits(max_count=200)))
            last_commit = repo.head.commit.committed_datetime.isoformat()
        except Exception as e:
            logger.warning(f"[{session_id}] Git metadata error: {e}")

        # README
        readme_content = None
        for name in ("README.md", "README.rst", "README.txt", "readme.md"):
            readme_path = clone_path / name
            if readme_path.exists():
                readme_content = readme_path.read_text(errors="replace")[:1000]
                break

        # Entry points
        entry_points = [
            f.path for f in files
            if Path(f.path).name in ENTRY_POINT_NAMES
        ]

        return RepoMetadata(
            repo_name=repo_name,
            repo_url=repo_url,
            branch=branch,
            clone_path=str(clone_path),
            files=files,
            total_lines=total_lines,
            total_files=len(files),
            language_breakdown=build_language_breakdown(file_paths),
            contributors=contributors,
            last_commit=last_commit,
            readme_content=readme_content,
            entry_points=entry_points,
        )


def get_repo_service() -> RepoService:
    return RepoService()
