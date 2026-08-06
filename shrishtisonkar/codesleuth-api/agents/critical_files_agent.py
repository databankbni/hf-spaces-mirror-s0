"""
Critical Files Agent — ranks files by combined criticality score.
Combines risk severity, graph centrality, degree, and oversized-file heuristics.
"""
from pathlib import Path
import networkx as nx

from services.graph_service import get_graph_service
from services.cache_service import get_cache_service
from models.critical_files import CriticalFileItem, CriticalFilesResponse
from utils.logger import get_logger

logger = get_logger(__name__)


def _label(path: str) -> str:
    return Path(path).name


def _risk_level(score: float) -> str:
    if score >= 8.0:
        return "critical"
    if score >= 6.0:
        return "high"
    if score >= 3.5:
        return "medium"
    return "low"


class CriticalFilesAgent:
    def __init__(self):
        self.graph_svc = get_graph_service()
        self.cache = get_cache_service()

    def run(self, session_id: str, top_n: int = 10) -> CriticalFilesResponse:
        logger.info(f"[{session_id}] CriticalFilesAgent: computing top {top_n} critical files")

        graph_data = self.cache.get_graph(session_id) or {}
        risk_data = self.cache.get_risk(session_id) or {}
        asts_data = self.cache.get_asts(session_id) or []

        G: nx.DiGraph = nx.DiGraph()
        if graph_data:
            repo_graph = self.graph_svc.from_json(graph_data)
            G = repo_graph.dep_graph

        # ── Build per-file risk map ───────────────────────────────────────────
        severity_weight = {"critical": 3.0, "high": 2.0, "medium": 1.0, "low": 0.3}
        file_risk_score: dict[str, float] = {}
        file_risk_categories: dict[str, set] = {}
        file_reasons: dict[str, list] = {}

        for item in risk_data.get("items", []):
            sev_w = severity_weight.get(item.get("severity", "low"), 0.3)
            cat = item.get("category", "")
            for fp in item.get("affected_files", []):
                file_risk_score[fp] = file_risk_score.get(fp, 0.0) + sev_w
                file_risk_categories.setdefault(fp, set()).add(cat)
                title = item.get("title", "Risk detected")
                reasons = file_reasons.setdefault(fp, [])
                if title not in reasons:
                    reasons.append(title)

        # ── Centrality ────────────────────────────────────────────────────────
        centrality: dict[str, float] = {}
        if G.number_of_nodes() > 1:
            try:
                centrality = nx.betweenness_centrality(G, normalized=True)
            except Exception:
                centrality = {}

        # ── AST line counts ───────────────────────────────────────────────────
        LINE_THRESHOLD = 300
        file_lines: dict[str, int] = {a["path"]: a.get("line_count", 0) for a in asts_data}

        # ── Score every known file ────────────────────────────────────────────
        all_files: set[str] = set(G.nodes()) | set(file_risk_score.keys())
        scored: list[tuple[float, str]] = []

        for fp in all_files:
            risk_s = min(file_risk_score.get(fp, 0.0), 6.0)
            cent_s = centrality.get(fp, 0.0) * 5.0
            in_deg = G.in_degree(fp) if fp in G else 0
            out_deg = G.out_degree(fp) if fp in G else 0
            degree_s = min((in_deg + out_deg) * 0.15, 3.0)
            lines = file_lines.get(fp, 0)
            size_s = 1.5 if lines > LINE_THRESHOLD * 3 else (0.7 if lines > LINE_THRESHOLD else 0.0)

            total = round(min(10.0, risk_s + cent_s + degree_s + size_s), 2)
            scored.append((total, fp))

        scored.sort(reverse=True)
        top = scored[:top_n]

        items: list[CriticalFileItem] = []
        for score, fp in top:
            reasons = file_reasons.get(fp, [])
            if not reasons:
                in_deg = G.in_degree(fp) if fp in G else 0
                out_deg = G.out_degree(fp) if fp in G else 0
                if in_deg > 2:
                    reasons.append(f"Imported by {in_deg} files")
                if out_deg > 2:
                    reasons.append(f"Imports {out_deg} modules")
                c = centrality.get(fp, 0.0)
                if c > 0.3:
                    reasons.append("High betweenness centrality — bridge node")
                if file_lines.get(fp, 0) > LINE_THRESHOLD:
                    reasons.append(f"Large file ({file_lines[fp]} lines)")
                reasons = reasons or ["Frequently referenced in the codebase"]

            cats = list(file_risk_categories.get(fp, set()))
            items.append(CriticalFileItem(
                file_path=fp,
                file_name=_label(fp),
                criticality_score=score,
                risk_level=_risk_level(score),
                reasons=reasons[:4],
                risk_categories=cats,
                impact_score=round(score * 0.9, 2),
            ))

        return CriticalFilesResponse(session_id=session_id, items=items)
