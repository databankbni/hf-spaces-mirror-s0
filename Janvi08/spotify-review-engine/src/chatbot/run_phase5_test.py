"""Phase 5 smoke test — RAG answer + theme clustering."""

from __future__ import annotations

import json
import logging
import textwrap

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from src.chatbot.rag import answer_question
from src.chatbot.themes import compute_themes

_SEP = "=" * 72
_SUB = "-" * 72


def _wrap(text: str, indent: int = 4) -> str:
    prefix = " " * indent
    return textwrap.fill(text, width=80, initial_indent=prefix, subsequent_indent=prefix)


def test_rag() -> None:
    print(_SEP)
    print("PHASE 5 TEST 1 — RAG answer_question()")
    print(_SEP)

    query = "Why do users struggle to discover new music?"
    print(f"\nQuery: {query}\n")

    result = answer_question(query, k=5)

    print(f"Backend: {result.get('backend', 'unknown')}\n")
    print("ANSWER:")
    print(_wrap(result["answer"]))

    print("\nSOURCES:")
    for i, src in enumerate(result["sources"], 1):
        score = src.get("score", 0.0)
        source = src.get("source", "?")
        date = src.get("date", "?")
        text = (src.get("text") or "")[:120].replace("\n", " ")
        print(f"  {i}. [{source}] {date} | score={score:.4f}")
        print(f"     {text}...")


def test_themes() -> None:
    print(f"\n{_SEP}")
    print("PHASE 5 TEST 2 — compute_themes()")
    print(_SEP)

    themes = compute_themes()

    print(f"\nTotal themes: {len(themes)}\n")
    for i, theme in enumerate(themes, 1):
        name = theme.get("theme_name", "?")
        count = theme.get("count", 0)
        print(f"{i}. {name!r}  ({count} chunks)")
        for q in theme.get("top_quotes", [])[:2]:
            src = q.get("source", "?")
            date = q.get("date", "?")
            text = (q.get("text") or "")[:120].replace("\n", " ")
            print(f"   [{src} {date}] {text}...")
        print()


def main() -> None:
    test_rag()
    test_themes()
    print(_SEP)
    print("Phase 5 test complete.")


if __name__ == "__main__":
    main()
