"""
Explain Agent — multi-level explanation of a file or function.
Modes: intern (analogy-driven) | engineer (technical) | architect (system design).
"""
from pathlib import Path

from services.index_service import get_index_service
from services.llm_service import get_llm_service
from services.cache_service import get_cache_service
from services.graph_service import get_graph_service
from models.explain import ExplainResponse
from utils.logger import get_logger

logger = get_logger(__name__)

EXPLAIN_PROMPTS = {
    "intern": (
        "Explain this code to a brand-new developer using simple language and analogies. "
        "Avoid jargon. Cover: What does it do? Why does it exist? How does it work in plain English?"
    ),
    "engineer": (
        "Provide a technical explanation covering: purpose, key algorithms/patterns used, "
        "inputs/outputs, important edge cases, and any performance considerations."
    ),
    "architect": (
        "Analyse this from a software architecture perspective: "
        "its role in the overall system, design patterns applied, coupling/cohesion assessment, "
        "scalability implications, and any architectural concerns or improvement opportunities."
    ),
}


class ExplainAgent:
    def __init__(self):
        self.indexer   = get_index_service()
        self.grok      = get_llm_service()
        self.cache     = get_cache_service()
        self.graph_svc = get_graph_service()

    async def run(
        self,
        session_id: str,
        target: str,      # file path or "file.py::function_name"
        mode: str = "engineer",
    ) -> ExplainResponse:

        logger.info(f"[{session_id}] ExplainAgent: target='{target}' mode={mode}")

        # Resolve file path and optional function name
        if "::" in target:
            file_path, func_name = target.split("::", 1)
        else:
            file_path, func_name = target, None

        # ── 1. Retrieve relevant chunks ───────────────────────────────────────
        search_query = f"{Path(file_path).stem} {func_name or ''} implementation"
        chunks = self.indexer.search(session_id, search_query, top_k=4)

        # filter to same file preferentially
        file_chunks = [c for c in chunks if c.file_path == file_path]
        context_chunks = file_chunks if file_chunks else chunks

        if not context_chunks:
            return self._fallback_response(session_id, target, mode)

        # ── 2. Build code context ─────────────────────────────────────────────
        code_context = "\n\n".join(
            f"```{c.language.lower()}\n{c.content}\n```"
            for c in context_chunks
        )

        # ── 3. Build prompt ───────────────────────────────────────────────────
        mode_instruction = EXPLAIN_PROMPTS.get(mode, EXPLAIN_PROMPTS["engineer"])
        focus = f"the function `{func_name}`" if func_name else f"the file `{file_path}`"

        prompt = (
            f"{mode_instruction}\n\n"
            f"Focus specifically on {focus}.\n\n"
            f"## Code\n\n{code_context}\n\n"
            f"## Your Explanation\n\n"
            f"Provide:\n"
            f"1. **Summary** (1 sentence)\n"
            f"2. **Detailed Explanation** (3-5 paragraphs)\n"
            f"3. **Key Concepts** (bullet list of 3-5 items)\n"
        )

        answer, _ = await self.grok.chat_with_mode(
            user_prompt=prompt,
            mode=mode,
            temperature=0.3,
            max_tokens=1500,
        )

        # Parse out sections
        summary, explanation, key_concepts = self._parse_explanation(answer)

        # ── 4. Graph-derived dependency info ──────────────────────────────────
        graph_data = self.cache.get_graph(session_id) or {}
        dependencies: list[str] = []
        dependents: list[str] = []

        if graph_data:
            try:
                import networkx as nx
                repo_graph = self.graph_svc.from_json(graph_data)
                G = repo_graph.dep_graph
                if file_path in G:
                    dependencies = list(G.successors(file_path))[:10]
                    dependents   = list(G.predecessors(file_path))[:10]
            except Exception:
                pass

        # ── 5. AST-derived file stats ─────────────────────────────────────────
        asts = self.cache.get_asts(session_id)
        line_count = 0
        complexity  = 0.0
        language    = "Unknown"
        for ast in asts:
            if ast.get("path") == file_path:
                line_count = ast.get("line_count", 0)
                complexity  = ast.get("complexity", 0.0)
                language    = ast.get("language", "Unknown")
                break

        return ExplainResponse(
            session_id=session_id,
            target=target,
            mode=mode,
            title=Path(file_path).name + (f" → {func_name}" if func_name else ""),
            summary=summary,
            explanation=explanation,
            key_concepts=key_concepts,
            dependencies=dependencies,
            dependents=dependents,
            complexity_score=round(min(10.0, complexity * 1.5), 1),
            line_count=line_count,
            language=language,
        )

    def _parse_explanation(self, text: str) -> tuple[str, str, list[str]]:
        """Best-effort parse of the LLM's structured response."""
        lines = text.strip().splitlines()
        summary = ""
        explanation_lines: list[str] = []
        key_concepts: list[str] = []

        section = None
        for line in lines:
            stripped = line.strip()
            if "**Summary**" in stripped or stripped.startswith("1."):
                section = "summary"
                content = stripped.split("**")[-1].strip().lstrip(".")
                if content:
                    summary = content
            elif "**Detailed" in stripped or stripped.startswith("2."):
                section = "explanation"
            elif "**Key Concepts**" in stripped or stripped.startswith("3."):
                section = "concepts"
            elif section == "summary" and stripped and not summary:
                summary = stripped
            elif section == "explanation" and stripped:
                explanation_lines.append(stripped)
            elif section == "concepts" and stripped.startswith(("-", "*", "•", "·")):
                key_concepts.append(stripped.lstrip("-*•· ").strip())

        # Fallback: first line = summary, rest = explanation
        if not summary and lines:
            summary = lines[0].strip()
        if not explanation_lines:
            explanation_lines = lines[1:] if len(lines) > 1 else ["See the code above."]

        return summary, "\n".join(explanation_lines), key_concepts[:6]

    def _fallback_response(
        self, session_id: str, target: str, mode: str
    ) -> ExplainResponse:
        return ExplainResponse(
            session_id=session_id,
            target=target,
            mode=mode,
            title=Path(target.split("::")[0]).name,
            summary="Could not find indexed content for this target.",
            explanation="Please ensure the repository has been fully ingested before requesting explanations.",
            key_concepts=[],
            dependencies=[],
            dependents=[],
            complexity_score=0.0,
            line_count=0,
            language="Unknown",
        )
