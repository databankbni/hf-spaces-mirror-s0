from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.platform.embeddings import TextEmbedder
    from psycopg import Connection

class EmbeddingContractError(RuntimeError):
    """Raised when the database embedding contract does not match the application spec."""

def _assert_embedding_contract(connection: Connection, embedder: TextEmbedder) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select id, dimension, normalize_embeddings
            from public.embedding_models
            where id = %s
            """,
            (embedder.spec.id,),
        )
        row = cursor.fetchone()

    if not row:
        raise EmbeddingContractError(f"Embedding model {embedder.spec.id!r} is not seeded in Postgres")
    if row["dimension"] != embedder.spec.dimension:
        raise EmbeddingContractError(
            f"Postgres model dimension mismatch for {embedder.spec.id}: "
            f"expected {embedder.spec.dimension}, got {row['dimension']}"
        )
    if row["normalize_embeddings"] != embedder.spec.normalize_embeddings:
        raise EmbeddingContractError(f"Postgres normalization contract mismatch for {embedder.spec.id}")
