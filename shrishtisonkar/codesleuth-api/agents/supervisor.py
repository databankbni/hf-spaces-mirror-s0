"""
Supervisor Agent — orchestrates the full analysis pipeline.
Coordinates: Ingestion → Graph → Risk → Flow (parallel after ingestion).
"""
import asyncio
import uuid
from pathlib import Path

from services.cache_service import get_cache_service
from agents.ingestion_agent import IngestionAgent
from agents.graph_agent import GraphAgent
from agents.risk_agent import RiskAgent
from agents.flow_agent import FlowAgent
from utils.logger import get_logger

logger = get_logger(__name__)


def _status(session_id: str, status: str, progress: int, **extra) -> dict:
    return {"session_id": session_id, "status": status, "progress": progress, **extra}


class SupervisorAgent:
    def __init__(self):
        self.cache = get_cache_service()
        self.ingestion = IngestionAgent()
        self.graph    = GraphAgent()
        self.risk     = RiskAgent()
        self.flow     = FlowAgent()

    async def run(
        self,
        session_id: str,
        repo_url: str,
        branch: str = "main",
        token: str | None = None,
    ) -> None:
        """
        Full pipeline — runs asynchronously in background.
        Status is written to cache at every step so the client can poll.
        """
        logger.info(f"[{session_id}] Supervisor starting pipeline for {repo_url}")

        try:
            # ── Step 1: Ingest (clone + parse + index) ────────────────────────
            self.cache.set_status(session_id, _status(
                session_id, "cloning", 5,
                error=None, repo_name=None,
            ))

            # Simple progress callback — repo_name not available until after
            def _on_progress(pct: int, status_str: str) -> None:
                self.cache.set_status(session_id, _status(
                    session_id, status_str, pct, error=None, repo_name=None,
                ))

            metadata, asts, file_contents = await self.ingestion.run(
                session_id, repo_url, branch, token,
                on_progress=_on_progress,
            )

            self.cache.set_status(session_id, _status(
                session_id, "building_graph", 60,
                repo_name=metadata.repo_name,
                error=None,
                language_breakdown=metadata.language_breakdown,
                total_files=metadata.total_files,
                total_lines=metadata.total_lines,
            ))

            # ── Step 2: Graph, then Risk ──────────────────────────────────────
            # RiskAgent's circular-dependency / coupling / SPOF detectors read
            # the graph from cache, so the graph must be fully built and cached
            # before risk detection starts — running them in parallel made
            # those detectors silently no-op.
            repo_graph = await self.graph.run(session_id, asts)

            self.cache.set_status(session_id, _status(
                session_id, "detecting_risks", 80,
                repo_name=metadata.repo_name,
                error=None,
                language_breakdown=metadata.language_breakdown,
                total_files=metadata.total_files,
                total_lines=metadata.total_lines,
            ))
            risk_response = await self.risk.run(session_id, asts, file_contents)

            # Build overview (needs graph + risk results)
            overview = self._build_overview(session_id, metadata, asts, risk_response)
            self.cache.set_overview(session_id, overview)

            # ── Step 3: Mark ready ────────────────────────────────────────────
            self.cache.set_status(session_id, _status(
                session_id, "ready", 100,
                repo_name=metadata.repo_name,
                error=None,
                language_breakdown=metadata.language_breakdown,
                total_files=metadata.total_files,
                total_lines=metadata.total_lines,
            ))
            logger.info(f"[{session_id}] Pipeline complete ✓")

        except Exception as exc:
            logger.error(f"[{session_id}] Pipeline failed: {exc}", exc_info=True)
            self.cache.set_status(session_id, {
                "session_id": session_id,
                "status": "error",
                "progress": 0,
                "error": str(exc),
                "repo_name": None,
            })

    def _build_overview(self, session_id, metadata, asts, risk_response) -> dict:
        total_functions = sum(len(a.functions) for a in asts)
        total_classes   = sum(len(a.classes)   for a in asts)
        avg_complexity  = (
            sum(a.complexity for a in asts) / len(asts) if asts else 0.0
        )
        # Normalise complexity to 0-10
        complexity_score = min(10.0, round(avg_complexity * 1.5, 1))

        return {
            "session_id": session_id,
            "repo_name": metadata.repo_name,
            "repo_url": metadata.repo_url,
            "branch": metadata.branch,
            "total_files": metadata.total_files,
            "total_lines": metadata.total_lines,
            "total_functions": total_functions,
            "total_classes": total_classes,
            "languages": metadata.language_breakdown,
            "top_modules": self._top_modules(metadata),
            "complexity_score": complexity_score,
            "risk_score": risk_response.get("risk_score", 0.0),
            "contributors": metadata.contributors,
            "last_commit": metadata.last_commit,
            "entry_points": metadata.entry_points,
            "readme_summary": (metadata.readme_content or "")[:300] or None,
        }

    def _top_modules(self, metadata) -> list[str]:
        """Return top-level directory names or key filenames."""
        dirs: dict[str, int] = {}
        for f in metadata.files:
            top = f.path.split("/")[0]
            dirs[top] = dirs.get(top, 0) + 1
        return [k for k, _ in sorted(dirs.items(), key=lambda x: -x[1])[:8]]


def create_session_id() -> str:
    return uuid.uuid4().hex
