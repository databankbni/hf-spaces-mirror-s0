"""Run the 6 assignment analytical questions through the hybrid retriever."""

from __future__ import annotations

import textwrap

from src.retrieval.retriever import retrieve

ANALYTICAL_QUESTIONS = [
    "Why do users struggle to discover new music?",
    "What are the most common frustrations with recommendations?",
    "What listening behaviors are users trying to achieve?",
    "What causes users to repeatedly listen to the same content?",
    "Which user segments experience different discovery challenges?",
    "What unmet needs emerge consistently across reviews?",
]


def _truncate(text: str, width: int = 140) -> str:
    cleaned = " ".join((text or "").split())
    return textwrap.shorten(cleaned, width=width, placeholder="...")


def main() -> None:
    print("=" * 80)
    print("Phase 4 Retrieval Test — 6 Analytical Questions")
    print("Pipeline: Dense (BGE-small) + BM25 + RRF + ms-marco-MiniLM-L-6-v2")
    print("=" * 80)

    for question_number, question in enumerate(ANALYTICAL_QUESTIONS, start=1):
        print(f"\nQ{question_number}: {question}")
        print("-" * 80)
        results = retrieve(question, k=5)

        for rank, result in enumerate(results[:3], start=1):
            source = result.get("source", "unknown")
            similarity = result.get("similarity", 0.0)
            text = _truncate(result.get("text", ""))
            print(f"  {rank}. [{source}] similarity={similarity:.3f}")
            print(f"     {text}")

    print("\n" + "=" * 80)
    print("Phase 4 test complete.")


if __name__ == "__main__":
    main()
