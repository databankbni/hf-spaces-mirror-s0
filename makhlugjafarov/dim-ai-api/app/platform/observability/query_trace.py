"""Query Trace event payload."""

from dataclasses import dataclass, asdict, field
import logging

logger = logging.getLogger("dim.query")

@dataclass
class QueryTrace:
    """Structured event payload for RAG query timings and details."""
    question: str
    retrieve_ms: int
    pack_ms: int
    generate_ms: int
    total_ms: int
    top_score: float
    chunk_ids: list[str]
    tier_conflict: bool
    confidence: float | None
    provider: str | None
    model: str | None
    weak_context: bool
    user_id: str | None = None  # JWT-derived caller identity (None = anonymous)
    # GRO-217 (S2): context-packing outcomes, so a trimmed or dropped in-slice
    # chunk is never a silent event. `truncated` rolls up "the top-k slice did not
    # reach the model intact"; the id lists say exactly which chunks and how.
    context_truncated: bool = False
    truncated_chunk_ids: list[str] = field(default_factory=list)
    dropped_chunk_ids: list[str] = field(default_factory=list)

    def emit(self) -> None:
        """Emit the trace to the ``dim.query`` logger.

        Observability must never break the request: a failure here (e.g. a
        non-serializable field or a logging-handler error) must not destroy an
        already-generated answer. So the emit is best-effort — any exception is
        swallowed and itself logged, never propagated to the caller.

        Secret redaction is enforced by the platform JsonFormatter, which applies
        ``redact_secrets`` to the whole payload (message + merged ``extra``).
        """
        try:
            logger.info(
                f"Query trace: {self.total_ms}ms (r={self.retrieve_ms} p={self.pack_ms} g={self.generate_ms})",
                extra={"query_trace": asdict(self)},
            )
        except Exception:  # noqa: BLE001 — observability must not break the request
            logger.warning("query_trace emit failed", exc_info=True)
