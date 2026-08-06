"""
Cache Service — disk-persistent cache using diskcache.
Stores per-session analysis results so they survive server restarts.
"""
import json
from pathlib import Path
from typing import Any
import diskcache

from config import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# ── Session state keys ──────────────────────────────────────────────────────
KEY_STATUS = "status"          # IngestStatusResponse dict
KEY_METADATA = "metadata"      # RepoMetadata dict
KEY_ASTS = "asts"              # list[FileAST] serialized
KEY_GRAPH = "graph"            # graph JSON (dep + call)
KEY_RISK = "risk"              # RiskResponse dict
KEY_OVERVIEW = "overview"      # OverviewResponse dict
KEY_FILE_CONTENTS = "files"    # path → content dict


class CacheService:
    def __init__(self):
        cache_dir = Path(settings.disk_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache = diskcache.Cache(str(cache_dir), size_limit=2 ** 30)  # 1 GB

    def _key(self, session_id: str, field: str) -> str:
        return f"{session_id}:{field}"

    def set(self, session_id: str, field: str, value: Any, ttl: int | None = None) -> None:
        k = self._key(session_id, field)
        if ttl:
            self._cache.set(k, value, expire=ttl)
        else:
            self._cache.set(k, value)

    def get(self, session_id: str, field: str, default: Any = None) -> Any:
        k = self._key(session_id, field)
        return self._cache.get(k, default=default)

    def exists(self, session_id: str, field: str) -> bool:
        return self._key(session_id, field) in self._cache

    def delete_session(self, session_id: str) -> None:
        """Remove all cached data for a session."""
        prefix = f"{session_id}:"
        keys_to_delete = [k for k in self._cache if isinstance(k, str) and k.startswith(prefix)]
        for k in keys_to_delete:
            del self._cache[k]
        logger.info(f"[{session_id}] Cache cleared ({len(keys_to_delete)} keys)")

    # ── Convenience helpers ──────────────────────────────────────────────────

    def set_status(self, session_id: str, status: dict) -> None:
        self.set(session_id, KEY_STATUS, status)

    def get_status(self, session_id: str) -> dict | None:
        return self.get(session_id, KEY_STATUS)

    def set_overview(self, session_id: str, overview: dict) -> None:
        self.set(session_id, KEY_OVERVIEW, overview)

    def get_overview(self, session_id: str) -> dict | None:
        return self.get(session_id, KEY_OVERVIEW)

    def set_graph(self, session_id: str, graph_data: dict) -> None:
        self.set(session_id, KEY_GRAPH, graph_data)

    def get_graph(self, session_id: str) -> dict | None:
        return self.get(session_id, KEY_GRAPH)

    def set_risk(self, session_id: str, risk_data: dict) -> None:
        self.set(session_id, KEY_RISK, risk_data)

    def get_risk(self, session_id: str) -> dict | None:
        return self.get(session_id, KEY_RISK)

    def set_file_contents(self, session_id: str, contents: dict[str, str]) -> None:
        self.set(session_id, KEY_FILE_CONTENTS, contents)

    def get_file_contents(self, session_id: str) -> dict[str, str]:
        return self.get(session_id, KEY_FILE_CONTENTS, {})

    def set_asts(self, session_id: str, asts_data: list[dict]) -> None:
        self.set(session_id, KEY_ASTS, asts_data)

    def get_asts(self, session_id: str) -> list[dict]:
        return self.get(session_id, KEY_ASTS, [])

    def list_sessions(self) -> list[str]:
        """Return all session IDs that have a status entry."""
        sessions = set()
        for k in self._cache:
            if isinstance(k, str) and ":" in k:
                sid = k.split(":")[0]
                sessions.add(sid)
        return sorted(sessions)


_cache_service: CacheService | None = None


def get_cache_service() -> CacheService:
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
