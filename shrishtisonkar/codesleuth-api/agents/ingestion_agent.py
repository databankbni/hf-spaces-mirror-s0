"""
Ingestion Agent — clone repo, parse all files, build vector index.
"""
import asyncio
from pathlib import Path
from typing import Callable, Any

from services.repo_service import get_repo_service, RepoMetadata
from services.parser_service import get_parser_service, FileAST
from services.index_service import get_index_service
from services.cache_service import get_cache_service
from utils.logger import get_logger

logger = get_logger(__name__)


class IngestionAgent:
    def __init__(self):
        self.repo    = get_repo_service()
        self.parser  = get_parser_service()
        self.indexer = get_index_service()
        self.cache   = get_cache_service()

    async def run(
        self,
        session_id: str,
        repo_url: str,
        branch: str = "main",
        token: str | None = None,
        on_progress: Callable | None = None,
    ) -> tuple[RepoMetadata, list[FileAST], dict[str, str]]:

        def _progress(pct: int, status: str):
            if on_progress:
                on_progress(pct, status)

        # ── 1. Clone ─────────────────────────────────────────────────────────
        _progress(5, "cloning")
        clone_path = await asyncio.to_thread(
            self.repo.clone, session_id, repo_url, branch, token
        )

        # ── 2. Walk file tree ────────────────────────────────────────────────
        _progress(20, "parsing")
        files = await asyncio.to_thread(self.repo.walk_files, clone_path)
        logger.info(f"[{session_id}] Found {len(files)} files")

        # ── 3. Read file contents ────────────────────────────────────────────
        file_contents: dict[str, str] = {}
        for f in files:
            try:
                file_contents[f.path] = Path(f.abs_path).read_text(
                    encoding="utf-8", errors="replace"
                )
            except Exception:
                file_contents[f.path] = ""

        # ── 4. Parse ASTs ────────────────────────────────────────────────────
        _progress(35, "parsing")
        asts: list[FileAST] = []
        for file_entry in files:
            ast = await asyncio.to_thread(self.parser.parse_file, file_entry)
            asts.append(ast)

        logger.info(f"[{session_id}] Parsed {len(asts)} ASTs")

        # ── 5. Build metadata ────────────────────────────────────────────────
        metadata = await asyncio.to_thread(
            self.repo.extract_metadata,
            session_id, repo_url, branch, clone_path, files
        )

        # ── 6. Vector index ──────────────────────────────────────────────────
        _progress(50, "indexing")
        chunk_count = await asyncio.to_thread(
            self.indexer.index_session, session_id, asts, file_contents
        )
        logger.info(f"[{session_id}] Indexed {chunk_count} chunks ✓")

        # ── 7. Persist to cache ──────────────────────────────────────────────
        asts_data = [
            {
                "path": a.path,
                "language": a.language,
                "imports": a.imports,
                "line_count": a.line_count,
                "complexity": a.complexity,
                "functions": [
                    {"name": f.name, "line_start": f.line_start,
                     "line_end": f.line_end, "calls": f.calls,
                     "complexity": f.complexity}
                    for f in a.functions
                ],
                "classes": [
                    {"name": c.name, "line_start": c.line_start,
                     "line_end": c.line_end, "methods": c.methods,
                     "bases": c.bases}
                    for c in a.classes
                ],
            }
            for a in asts
        ]
        self.cache.set_asts(session_id, asts_data)
        self.cache.set_file_contents(session_id, file_contents)

        _progress(58, "building_graph")
        return metadata, asts, file_contents
