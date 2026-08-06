"""
Impact Agent — analyses blast radius when a file/module/node changes.
Uses the cached dependency and call graphs; no LLM tokens required.
"""
from pathlib import Path
import networkx as nx

from services.graph_service import get_graph_service
from services.cache_service import get_cache_service
from models.impact import ImpactResponse, AffectedFile
from utils.logger import get_logger

logger = get_logger(__name__)

# ── helpers ───────────────────────────────────────────────────────────────────

def _label(node_id: str) -> str:
    return Path(node_id).name if "/" in node_id or "\\" in node_id else node_id.split("::")[-1]


def _module_from_path(path: str) -> str:
    parts = Path(path).parts
    return parts[1] if len(parts) > 1 else parts[0]


class ImpactAgent:
    def __init__(self):
        self.graph_svc = get_graph_service()
        self.cache = get_cache_service()

    def run(self, session_id: str, target: str, target_type: str) -> ImpactResponse:
        logger.info(f"[{session_id}] ImpactAgent: analysing '{target}'")

        graph_data = self.cache.get_graph(session_id) or {}
        risk_data = self.cache.get_risk(session_id) or {}

        G_dep: nx.DiGraph = nx.DiGraph()
        G_call: nx.DiGraph = nx.DiGraph()
        if graph_data:
            repo_graph = self.graph_svc.from_json(graph_data)
            G_dep = repo_graph.dep_graph
            G_call = repo_graph.call_graph

        # ── Resolve target node in dep graph ──────────────────────────────────
        resolved = self._resolve(G_dep, target)
        if resolved is None:
            resolved = self._resolve(G_call, target)

        affected_files: list[AffectedFile] = []
        affected_modules: set[str] = set()
        graph_highlights: list[str] = [target]

        if resolved and resolved in G_dep:
            # Downstream (files that import target)
            for node in nx.descendants(G_dep, resolved):
                reason = "downstream dependency"
                in_edges = list(G_dep.predecessors(node))
                if resolved in in_edges:
                    reason = "directly imports target"
                affected_files.append(AffectedFile(id=node, label=_label(node), reason=reason))
                graph_highlights.append(node)
                affected_modules.add(_module_from_path(node))

            # Immediate importers (upstream coupling)
            for pred in G_dep.predecessors(resolved):
                if pred not in {f.id for f in affected_files}:
                    affected_files.append(AffectedFile(id=pred, label=_label(pred), reason="imports target"))
                    graph_highlights.append(pred)
                    affected_modules.add(_module_from_path(pred))

        # ── Call graph contributions ──────────────────────────────────────────
        call_matches = [n for n in G_call.nodes() if target in n]
        for cm in call_matches:
            for node in nx.descendants(G_call, cm):
                file_part = node.split("::")[0] if "::" in node else node
                if file_part not in {f.id for f in affected_files}:
                    affected_files.append(
                        AffectedFile(id=file_part, label=_label(file_part), reason="called by target")
                    )
                    graph_highlights.append(file_part)
                    affected_modules.add(_module_from_path(file_part))

        # Deduplicate
        seen: set[str] = set()
        deduped: list[AffectedFile] = []
        for af in affected_files:
            if af.id not in seen:
                seen.add(af.id)
                deduped.append(af)
        affected_files = deduped[:20]
        graph_highlights = list(dict.fromkeys(graph_highlights))[:25]

        # ── Affected flows (from risk items' affected_files) ──────────────────
        affected_flows: list[str] = []
        risk_items = risk_data.get("items", [])
        for item in risk_items:
            if target in item.get("affected_files", []):
                cat = item.get("category", "unknown")
                affected_flows.append(cat.replace("_", " ").title() + " Flow")
        affected_flows = list(dict.fromkeys(affected_flows))

        # ── Compute impact score ──────────────────────────────────────────────
        n_affected = len(affected_files)
        centrality_score = 0.0
        if resolved and resolved in G_dep and G_dep.number_of_nodes() > 1:
            try:
                c = nx.betweenness_centrality(G_dep, normalized=True)
                centrality_score = c.get(resolved, 0.0)
            except Exception:
                centrality_score = 0.0

        risk_boost = sum(
            3.0 if i.get("severity") == "critical" else
            2.0 if i.get("severity") == "high" else
            1.0 if i.get("severity") == "medium" else 0.3
            for i in risk_items
            if target in i.get("affected_files", [])
        )

        raw = (n_affected * 0.4) + (centrality_score * 5.0) + risk_boost
        impact_score = round(min(10.0, raw), 1)
        confidence = round(min(0.95, 0.5 + centrality_score * 0.4 + min(n_affected, 10) * 0.03), 2)

        # ── Summary ───────────────────────────────────────────────────────────
        module_str = ", ".join(sorted(affected_modules)[:4]) or "unknown"
        summary = (
            f"Changes to '{_label(target)}' may propagate to {n_affected} file(s) "
            f"across {len(affected_modules)} module(s) ({module_str}). "
        )
        if centrality_score > 0.3:
            summary += "This node is a critical bridge in the dependency graph. "
        if affected_flows:
            summary += f"Affected flows: {', '.join(affected_flows[:3])}."

        return ImpactResponse(
            target=target,
            target_type=target_type,
            impact_score=impact_score,
            summary=summary,
            affected_files=affected_files,
            affected_modules=sorted(affected_modules),
            affected_flows=affected_flows,
            graph_highlights=graph_highlights,
            confidence=confidence,
        )

    def _resolve(self, G: nx.DiGraph, target: str) -> str | None:
        if target in G:
            return target
        tl = target.lower()
        candidates = [n for n in G.nodes() if tl in n.lower()]
        if candidates:
            roots = [n for n in candidates if G.in_degree(n) == 0]
            return roots[0] if roots else candidates[0]
        return None
