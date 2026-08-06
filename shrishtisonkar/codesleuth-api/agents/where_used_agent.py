"""
Where-Used Agent — finds all callers / importers of a target file, module, or function.
Uses incoming edges from the cached dependency and call graphs.
"""
from pathlib import Path
import networkx as nx

from services.graph_service import get_graph_service
from services.cache_service import get_cache_service
from models.where_used import WhereUsedResponse, UsedByItem
from utils.logger import get_logger

logger = get_logger(__name__)


def _label(node_id: str) -> str:
    return Path(node_id).name if "/" in node_id or "\\" in node_id else node_id.split("::")[-1]


class WhereUsedAgent:
    def __init__(self):
        self.graph_svc = get_graph_service()
        self.cache = get_cache_service()

    def run(self, session_id: str, target: str, target_type: str) -> WhereUsedResponse:
        logger.info(f"[{session_id}] WhereUsedAgent: finding usages of '{target}'")

        graph_data = self.cache.get_graph(session_id) or {}
        risk_data = self.cache.get_risk(session_id) or {}

        G_dep: nx.DiGraph = nx.DiGraph()
        G_call: nx.DiGraph = nx.DiGraph()
        if graph_data:
            repo_graph = self.graph_svc.from_json(graph_data)
            G_dep = repo_graph.dep_graph
            G_call = repo_graph.call_graph

        used_by: list[UsedByItem] = []
        graph_highlights: list[str] = [target]

        # ── Dependency-graph incoming edges ───────────────────────────────────
        resolved_dep = self._resolve(G_dep, target)
        if resolved_dep:
            for pred in G_dep.predecessors(resolved_dep):
                edge_data = G_dep.edges.get((pred, resolved_dep), {})
                relation = edge_data.get("edge_type", "imports")
                used_by.append(UsedByItem(id=pred, label=_label(pred), relation=relation))
                graph_highlights.append(pred)

        # ── Call-graph incoming edges ─────────────────────────────────────────
        call_matches = [n for n in G_call.nodes() if target in n]
        for cm in call_matches:
            for pred in G_call.predecessors(cm):
                file_part = pred.split("::")[0] if "::" in pred else pred
                if file_part not in {u.id for u in used_by}:
                    used_by.append(UsedByItem(id=file_part, label=_label(file_part), relation="calls"))
                    graph_highlights.append(file_part)

        # Deduplicate
        seen: set[str] = set()
        deduped: list[UsedByItem] = []
        for item in used_by:
            if item.id not in seen:
                seen.add(item.id)
                deduped.append(item)
        used_by = deduped[:20]
        graph_highlights = list(dict.fromkeys(graph_highlights))[:25]

        # ── Related flows from risk data ──────────────────────────────────────
        related_flows: list[str] = []
        for item in risk_data.get("items", []):
            if target in item.get("affected_files", []):
                cat = item.get("category", "")
                flow_name = cat.replace("_", " ").title() + " Risk Flow"
                if flow_name not in related_flows:
                    related_flows.append(flow_name)

        # ── Summary ───────────────────────────────────────────────────────────
        n = len(used_by)
        if n == 0:
            summary = f"'{_label(target)}' does not appear to be used by any other file in the analysed codebase."
        elif n == 1:
            summary = f"'{_label(target)}' is used by 1 file: {used_by[0].label}."
        else:
            callers = ", ".join(u.label for u in used_by[:3])
            summary = (
                f"'{_label(target)}' is used by {n} file(s). "
                f"Main callers: {callers}{'…' if n > 3 else ''}."
            )

        return WhereUsedResponse(
            target=target,
            target_type=target_type,
            used_by=used_by,
            related_flows=related_flows,
            graph_highlights=graph_highlights,
            summary=summary,
        )

    def _resolve(self, G: nx.DiGraph, target: str) -> str | None:
        if target in G:
            return target
        tl = target.lower()
        candidates = [n for n in G.nodes() if tl in n.lower()]
        if candidates:
            return candidates[0]
        return None
