"""
Sala AI - Product Tagger
Tags a user query with the most relevant product name, reusing the
existing product vector store (no extra embedding cost - same
Chroma store used for chat responses).
"""

import logging
from chatbot import rag  # import the module (not a specific variable) to always get the live store

log = logging.getLogger("SalaAI")


def tag_product(query: str) -> str | None:
    """
    Returns the name of the most relevant product for this query, or None
    if no product store is loaded yet or nothing matches closely.
    """
    if not query or not query.strip():
        return None

    try:
        if rag._product_store is None:
            return None

        # Just need the single closest product here, so a plain similarity
        # search (k=1) is enough - no need for MMR diversity like the main
        # chat retrieval uses.
        docs = rag._product_store.similarity_search(query, k=1)
        if not docs:
            return None

        top = docs[0]
        return top.metadata.get("name")
    except Exception as e:
        log.error(f"Product tagging error: {e}")
        return None