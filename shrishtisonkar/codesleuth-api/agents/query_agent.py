"""
Query Agent — grounded retrieval + Grok reasoning for natural language Q&A.
Returns answer, source attributions, and highlighted graph node IDs.
"""
from services.index_service import get_index_service
from services.llm_service import get_llm_service
from services.cache_service import get_cache_service
from models.query import QueryRequest, QueryResponse, SourceChunk
from utils.logger import get_logger

logger = get_logger(__name__)

MODE_PREFIXES = {
    "intern":    "Explain this as if talking to a junior developer who is new to the codebase.",
    "engineer":  "Provide a precise technical answer with code-level details.",
    "architect": (
        "Provide a system-design perspective — discuss patterns, tradeoffs, "
        "scalability implications, and architectural significance."
    ),
}


class QueryAgent:
    def __init__(self):
        self.indexer  = get_index_service()
        self.grok     = get_llm_service()
        self.cache    = get_cache_service()

    async def run(self, request: QueryRequest) -> QueryResponse:
        session_id = request.session_id
        question   = request.question
        mode       = request.mode
        top_k      = request.max_context_chunks

        logger.info(f"[{session_id}] QueryAgent: '{question[:60]}' mode={mode}")

        # ── 1. Semantic retrieval ─────────────────────────────────────────────
        chunks = self.indexer.search(session_id, question, top_k=top_k)

        if not chunks:
            return QueryResponse(
                answer=(
                    "I could not find relevant code in the indexed repository "
                    "to answer your question. Please try rephrasing."
                ),
                sources=[],
                highlighted_nodes=[],
                confidence=0.0,
                mode=mode,
            )

        # ── 2. Build grounded prompt ──────────────────────────────────────────
        context_blocks = []
        for i, chunk in enumerate(chunks, 1):
            context_blocks.append(
                f"### Source {i}: `{chunk.file_path}` (lines {chunk.line_start}–{chunk.line_end})\n"
                f"```{chunk.language.lower()}\n{chunk.content}\n```"
            )
        context = "\n\n".join(context_blocks)

        mode_prefix = MODE_PREFIXES.get(mode, MODE_PREFIXES["engineer"])
        prompt = (
            f"{mode_prefix}\n\n"
            f"You are analysing the repository that was provided. "
            f"Using ONLY the source code excerpts below, answer the question. "
            f"If the answer cannot be determined from the provided sources, say so.\n\n"
            f"## Relevant Code\n\n{context}\n\n"
            f"## Question\n\n{question}\n\n"
            f"## Answer"
        )

        # ── 3. Grok inference ─────────────────────────────────────────────────
        answer, tokens_used = await self.grok.chat_with_mode(
            user_prompt=prompt,
            mode=mode,
            temperature=0.2,
            max_tokens=1024,
        )

        # ── 4. Build response ─────────────────────────────────────────────────
        source_chunks = [
            SourceChunk(
                file_path=c.file_path,
                content_snippet=c.content[:200].replace("\n", " "),
                relevance_score=c.relevance_score,
            )
            for c in chunks
        ]

        # highlighted_nodes = unique file paths from sources (graph node IDs)
        highlighted_nodes = list(dict.fromkeys(c.file_path for c in chunks))

        # confidence = average relevance of top chunks
        confidence = round(sum(c.relevance_score for c in chunks) / len(chunks), 3)

        logger.info(
            f"[{session_id}] QueryAgent: answered ({tokens_used} tokens, "
            f"confidence={confidence}, highlights={len(highlighted_nodes)})"
        )

        return QueryResponse(
            answer=answer,
            sources=source_chunks,
            highlighted_nodes=highlighted_nodes,
            confidence=confidence,
            mode=mode,
            tokens_used=tokens_used,
        )
