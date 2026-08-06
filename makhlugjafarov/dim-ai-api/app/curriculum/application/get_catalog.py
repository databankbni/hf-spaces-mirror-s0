"""Orchestrator for the catalog read — the list the Home screen renders.

The entry point before any navigation: the mobile app asks "what can I study?"
and gets every ingested book with enough metadata to draw a card and decide
whether to offer an outline (browsable course) or only ``/query`` (ask-only).
Thin by design — connect, read, return — with all assembly in the infrastructure
query and the shape in the domain model.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from app.curriculum.domain.models import CatalogEntry, TopicSliceError
from app.curriculum.infrastructure.postgres_curriculum_reader import fetch_catalog

_DB_CONNECT_TIMEOUT_SECONDS = 5


def get_catalog(*, database_url: str) -> list[CatalogEntry]:
    """Return all non-archived books with their node/chunk counts.

    Raises :class:`~app.curriculum.domain.models.TopicSliceError` on a database
    connection failure (mapped to 503 by the route), matching the other reads.
    """
    try:
        connection_cm = psycopg.connect(
            database_url, row_factory=dict_row, connect_timeout=_DB_CONNECT_TIMEOUT_SECONDS
        )
    except psycopg.OperationalError as exc:
        raise TopicSliceError(f"database connection failed: {exc.__class__.__name__}") from exc

    with connection_cm as connection:
        return fetch_catalog(connection)
