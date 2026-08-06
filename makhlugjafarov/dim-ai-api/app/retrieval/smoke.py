import argparse
import json

from app.platform.config import Settings
from app.platform.embeddings import get_bge_m3_embedder
from app.retrieval.domain.models import RetrievalFilters
from app.retrieval.application.retrieve_context import retrieve_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local pgvector retrieval smoke query.")
    parser.add_argument(
        "--query",
        default="Səfəvilər dövləti haqqında nə bilirik?",
        help="Question to embed and search for.",
    )
    parser.add_argument("--subject", default="azerbaycan_tarixi")
    parser.add_argument("--grade", type=int, default=8)
    parser.add_argument("--language", default="az")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--database-url")
    args = parser.parse_args()

    database_url = args.database_url or Settings().database_url
    if not database_url:
        raise RuntimeError("DIM_AI_API_DATABASE_URL is required for retrieval smoke tests.")

    result = retrieve_context(
        database_url=database_url,
        query=args.query,
        embedder=get_bge_m3_embedder(),
        filters=RetrievalFilters(subject=args.subject, grade=args.grade, language=args.language),
        top_k=args.top_k,
    )

    print(
        json.dumps(
            {
                "query": result.query,
                "weak_context": result.weak_context,
                "filters_relaxed": result.filters_relaxed,
                "chunks": [
                    {
                        "score": round(chunk.score, 4),
                        "page_start": chunk.citation.page_start,
                        "page_end": chunk.citation.page_end,
                        "citation_label": chunk.citation.citation_label,
                        "preview": chunk.content[:240].replace("\n", " "),
                    }
                    for chunk in result.chunks
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
