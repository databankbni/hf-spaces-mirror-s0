"""
Risk Agent — pure rule-based risk detection (no LLM tokens consumed).
Categories: circular deps, hardcoded secrets, oversized files,
            tight coupling, single points of failure.
"""
import asyncio
import uuid
from pathlib import Path

import networkx as nx

from services.graph_service import get_graph_service, RepoGraph
from services.cache_service import get_cache_service
from services.parser_service import FileAST
from utils.pattern_matcher import scan_file_for_secrets
from utils.logger import get_logger
from config import get_settings
from models.risk import RiskItem, RiskSummary, RiskResponse

logger = get_logger(__name__)
settings = get_settings()


class RiskAgent:
    def __init__(self):
        self.graph_svc = get_graph_service()
        self.cache     = get_cache_service()

    async def run(
        self,
        session_id: str,
        asts: list[FileAST],
        file_contents: dict[str, str],
    ) -> dict:
        logger.info(f"[{session_id}] RiskAgent: scanning {len(asts)} files")

        items: list[RiskItem] = []

        # Load graph from cache
        graph_data = self.cache.get_graph(session_id) or {}
        repo_graph = None
        if graph_data:
            repo_graph = self.graph_svc.from_json(graph_data)

        # Run all detectors concurrently
        results = await asyncio.gather(
            asyncio.to_thread(self._detect_circular_deps, repo_graph),
            asyncio.to_thread(self._detect_secrets, asts, file_contents),
            asyncio.to_thread(self._detect_oversized_files, asts),
            asyncio.to_thread(self._detect_tight_coupling, repo_graph),
            asyncio.to_thread(self._detect_spof, repo_graph),
        )

        for result_list in results:
            items.extend(result_list)

        # Score
        severity_weights = {"critical": 3.0, "high": 2.0, "medium": 1.0, "low": 0.3}
        raw_score = sum(severity_weights.get(i.severity, 0) for i in items)
        risk_score = round(min(10.0, raw_score / max(1, len(asts)) * 20), 1)

        summary = RiskSummary(
            critical=sum(1 for i in items if i.severity == "critical"),
            high=sum(1 for i in items if i.severity == "high"),
            medium=sum(1 for i in items if i.severity == "medium"),
            low=sum(1 for i in items if i.severity == "low"),
        )

        response = RiskResponse(
            session_id=session_id,
            total_risks=len(items),
            risk_score=risk_score,
            summary=summary,
            items=items,
            scanned_files=len(asts),
            secret_pattern_matches=summary.critical + summary.high,
        )

        self.cache.set_risk(session_id, response.model_dump())
        logger.info(f"[{session_id}] RiskAgent: {len(items)} risks found (score={risk_score}) ✓")
        return response.model_dump()

    # ── Detectors ─────────────────────────────────────────────────────────────

    def _detect_circular_deps(self, repo_graph: RepoGraph | None) -> list[RiskItem]:
        if not repo_graph:
            return []
        items = []
        try:
            cycles = list(nx.simple_cycles(repo_graph.dep_graph))
            for cycle in cycles[:10]:  # cap at 10 reported cycles
                items.append(RiskItem(
                    id=f"risk_circ_{uuid.uuid4().hex[:6]}",
                    category="circular_dependency",
                    severity="high",
                    title="Circular Dependency Detected",
                    description=(
                        f"A circular import chain exists: "
                        f"{' → '.join(cycle[:5])}{'...' if len(cycle) > 5 else ''} → {cycle[0]}"
                    ),
                    affected_files=cycle[:8],
                    suggestion=(
                        "Break the cycle by introducing an interface/abstract layer, "
                        "or moving shared logic into a separate module."
                    ),
                ))
        except nx.NetworkXNoCycle:
            pass
        except Exception as e:
            logger.warning(f"Circular dep detection error: {e}")
        return items

    def _detect_secrets(
        self, asts: list[FileAST], file_contents: dict[str, str]
    ) -> list[RiskItem]:
        items = []
        for ast in asts:
            content = file_contents.get(ast.path, "")
            if not content:
                continue
            matches = scan_file_for_secrets(ast.path, content)
            for m in matches:
                items.append(RiskItem(
                    id=f"risk_sec_{uuid.uuid4().hex[:6]}",
                    category="hardcoded_secret",
                    severity=m.severity,
                    title=f"Hardcoded {m.pattern_name}",
                    description=(
                        f"Pattern matching '{m.pattern_name}' found at line {m.line_number}. "
                        f"Snippet: `{m.line_content[:80]}`"
                    ),
                    affected_files=[ast.path],
                    suggestion=(
                        "Move secrets to environment variables. "
                        "Use python-dotenv, AWS Secrets Manager, or Vault."
                    ),
                    line_numbers=[m.line_number],
                ))
        return items

    def _detect_oversized_files(self, asts: list[FileAST]) -> list[RiskItem]:
        threshold = settings.oversized_file_threshold
        items = []
        for ast in asts:
            if ast.line_count > threshold:
                severity = "high" if ast.line_count > threshold * 3 else "medium"
                items.append(RiskItem(
                    id=f"risk_size_{uuid.uuid4().hex[:6]}",
                    category="oversized_file",
                    severity=severity,
                    title=f"Oversized File: {Path(ast.path).name}",
                    description=(
                        f"`{ast.path}` has {ast.line_count} lines "
                        f"(threshold: {threshold}). "
                        "Large files are harder to test, review, and maintain."
                    ),
                    affected_files=[ast.path],
                    suggestion=(
                        "Split into smaller, single-responsibility modules. "
                        "Apply the Single Responsibility Principle."
                    ),
                    metric_value=float(ast.line_count),
                ))
        return items

    def _detect_tight_coupling(self, repo_graph: RepoGraph | None) -> list[RiskItem]:
        if not repo_graph:
            return []
        threshold = settings.coupling_threshold
        items = []
        G = repo_graph.dep_graph
        for node in G.nodes():
            out_deg = G.out_degree(node)
            in_deg  = G.in_degree(node)
            if out_deg > threshold:
                items.append(RiskItem(
                    id=f"risk_coup_{uuid.uuid4().hex[:6]}",
                    category="tight_coupling",
                    severity="medium",
                    title=f"High Efferent Coupling: {Path(node).name}",
                    description=(
                        f"`{node}` imports {out_deg} other modules "
                        f"(threshold: {threshold}). "
                        "This makes it fragile and hard to test in isolation."
                    ),
                    affected_files=[node],
                    suggestion=(
                        "Apply Dependency Inversion — depend on abstractions, "
                        "not concrete implementations. Consider a facade pattern."
                    ),
                    metric_value=float(out_deg),
                ))
            if in_deg > threshold:
                items.append(RiskItem(
                    id=f"risk_coup_{uuid.uuid4().hex[:6]}",
                    category="tight_coupling",
                    severity="medium",
                    title=f"High Afferent Coupling: {Path(node).name}",
                    description=(
                        f"`{node}` is imported by {in_deg} modules "
                        f"(threshold: {threshold}). Changes here ripple everywhere."
                    ),
                    affected_files=[node],
                    suggestion=(
                        "Introduce a stable interface/protocol to decouple dependents."
                    ),
                    metric_value=float(in_deg),
                ))
        return items

    def _detect_spof(self, repo_graph: RepoGraph | None) -> list[RiskItem]:
        if not repo_graph:
            return []
        G = repo_graph.dep_graph
        if G.number_of_nodes() < 3:
            return []
        try:
            centrality = nx.betweenness_centrality(G, normalized=True)
        except Exception:
            return []

        top_threshold = 0.4  # top 40% betweenness = SPOF candidate
        items = []
        for node, score in centrality.items():
            if score >= top_threshold:
                items.append(RiskItem(
                    id=f"risk_spof_{uuid.uuid4().hex[:6]}",
                    category="single_point_of_failure",
                    severity="high",
                    title=f"Single Point of Failure: {Path(node).name}",
                    description=(
                        f"`{node}` sits on {score:.0%} of all shortest paths "
                        "in the dependency graph. Removing or breaking it would "
                        "cascade failures across many modules."
                    ),
                    affected_files=[node],
                    suggestion=(
                        "Add redundancy, introduce interface boundaries, "
                        "or split responsibilities across multiple modules."
                    ),
                    metric_value=round(score, 4),
                ))
        return items
