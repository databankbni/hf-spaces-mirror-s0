"""Upload the current HALT-CoT folder to Hugging Face."""

from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import create_repo, upload_folder


DEFAULT_IGNORE = [
    ".git",
    ".git/*",
    ".pytest_cache",
    ".pytest_cache/*",
    "__pycache__",
    "**/__pycache__/*",
    "*.pyc",
    "*.egg-info",
    "*.egg-info/*",
    "build",
    "build/*",
    "dist",
    "dist/*",
    ".env",
    ".env.*",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish HALT-CoT to Hugging Face.")
    parser.add_argument("--repo-id", required=True, help="Example: username/halt-cot")
    parser.add_argument("--repo-type", choices=("space", "model", "dataset"), default="space")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--commit-message", default="Publish HALT-CoT")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]

    create_repo(
        repo_id=args.repo_id,
        repo_type=args.repo_type,
        private=args.private,
        exist_ok=True,
        space_sdk="gradio" if args.repo_type == "space" else None,
    )
    upload_folder(
        repo_id=args.repo_id,
        repo_type=args.repo_type,
        folder_path=str(project_root),
        path_in_repo=".",
        ignore_patterns=DEFAULT_IGNORE,
        commit_message=args.commit_message,
    )
    print(f"Uploaded {project_root} to {args.repo_type} repo {args.repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
