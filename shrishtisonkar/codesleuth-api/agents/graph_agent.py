"""
Graph Agent — builds and persists dependency + call graphs from parsed ASTs.
"""
import asyncio
from pathlib import Path

from services.graph_service import get_graph_service, RepoGraph
from services.cache_service import get_cache_service
from services.parser_service import FileAST
from models.graph import GraphNode, GraphEdge, GraphResponse
from utils.logger import get_logger

logger = get_logger(__name__)


def _ast_dict_to_obj(d: dict) -> FileAST:
    """Reconstruct a lightweight FileAST from cached dict."""
    from services.parser_service import FileAST, FunctionDef, ClassDef
    ast = FileAST(
        path=d["path"],
        language=d["language"],
        imports=d.get("imports", []),
        line_count=d.get("line_count", 0),
        complexity=d.get("complexity", 1.0),
    )
    ast.functions = [
        FunctionDef(
            name=f["name"],
            line_start=f["line_start"],
            line_end=f["line_end"],
            calls=f.get("calls", []),
            complexity=f.get("complexity", 1),
        )
        for f in d.get("functions", [])
    ]
    ast.classes = [
        ClassDef(
            name=c["name"],
            line_start=c["line_start"],
            line_end=c["line_end"],
            methods=c.get("methods", []),
            bases=c.get("bases", []),
        )
        for c in d.get("classes", [])
    ]
    return ast


class GraphAgent:
    def __init__(self):
        self.graph_svc = get_graph_service()
        self.cache     = get_cache_service()

    async def run(self, session_id: str, asts: list[FileAST]) -> dict:
        logger.info(f"[{session_id}] GraphAgent: building graphs for {len(asts)} files")

        repo_graph: RepoGraph = await asyncio.to_thread(
            self.graph_svc.build, asts
        )

        # Serialize + cache
        graph_data = self.graph_svc.to_json(repo_graph)
        self.cache.set_graph(session_id, graph_data)
        logger.info(f"[{session_id}] GraphAgent: graphs cached ✓")
        return graph_data

    def build_response(
        self,
        session_id: str,
        graph_type: str = "dependency",
        highlighted_nodes: list[str] | None = None,
    ) -> GraphResponse:
        """Convert cached graph JSON into a GraphResponse for the API.
        Enriches each node with heat/risk metadata for the Graph Heatmap feature.
        """
        import networkx as nx

        graph_data = self.cache.get_graph(session_id) or {}
        risk_data = self.cache.get_risk(session_id) or {}
        highlighted = set(highlighted_nodes or [])

        key = "dep_graph" if graph_type == "dependency" else "call_graph"
        g_data = graph_data.get(key, {"nodes": [], "links": []})

        # ── Build risk lookup (file → risk info) ──────────────────────────────
        severity_weight = {"critical": 3.0, "high": 2.0, "medium": 1.0, "low": 0.3}
        file_risk_score: dict[str, float] = {}
        file_risk_cats: dict[str, list[str]] = {}
        for item in risk_data.get("items", []):
            sw = severity_weight.get(item.get("severity", "low"), 0.3)
            cat = item.get("category", "")
            for fp in item.get("affected_files", []):
                file_risk_score[fp] = file_risk_score.get(fp, 0.0) + sw
                if cat and cat not in file_risk_cats.get(fp, []):
                    file_risk_cats.setdefault(fp, []).append(cat)

        # ── Rebuild nx graph to get centrality ────────────────────────────────
        G_nx: nx.DiGraph = nx.DiGraph()
        for lnk in g_data.get("links", []):
            G_nx.add_edge(str(lnk.get("source", "")), str(lnk.get("target", "")))
        centrality: dict[str, float] = {}
        if G_nx.number_of_nodes() > 1:
            try:
                centrality = nx.betweenness_centrality(G_nx, normalized=True)
            except Exception:
                centrality = {}

        # ── Max values for normalisation ──────────────────────────────────────
        max_risk = max(file_risk_score.values(), default=1.0)
        max_cent = max(centrality.values(), default=1.0)

        def _heat(nid: str) -> float:
            r = file_risk_score.get(nid, 0.0) / max(max_risk, 1.0)
            c = centrality.get(nid, 0.0) / max(max_cent, 1.0)
            return round(min(1.0, r * 0.6 + c * 0.4), 3)

        def _risk_level(h: float) -> str:
            if h >= 0.8:
                return "critical"
            if h >= 0.6:
                return "high"
            if h >= 0.35:
                return "medium"
            if h >= 0.1:
                return "low"
            return "safe"

        nodes: list[GraphNode] = []
        for n in g_data.get("nodes", []):
            nid = n.get("id", "")
            h = _heat(nid)
            crit_score = round((file_risk_score.get(nid, 0.0) * 0.5 + centrality.get(nid, 0.0) * 5.0), 2)
            nodes.append(GraphNode(
                id=nid,
                label=n.get("label", Path(nid).name if nid else nid),
                type=n.get("node_type", "file"),
                language=n.get("language", "Unknown"),
                lines=n.get("lines", 0),
                complexity=n.get("complexity", 0.0),
                highlighted=(nid in highlighted),
                risk_level=_risk_level(h),
                criticality_score=min(10.0, crit_score),
                heat_score=h,
                risk_categories=file_risk_cats.get(nid, []),
            ))

        edges: list[GraphEdge] = []
        for e in g_data.get("links", []):
            src = str(e.get("source", ""))
            tgt = str(e.get("target", ""))
            edges.append(GraphEdge(
                id=f"{src}→{tgt}",
                source=src,
                target=tgt,
                type=e.get("edge_type", "imports"),
                weight=e.get("weight", 1.0),
            ))

        return GraphResponse(
            session_id=session_id,
            graph_type=graph_type,
            nodes=nodes,
            edges=edges,
            stats={
                "nodes": len(nodes),
                "edges": len(edges),
            },
        )

    @classmethod
    def from_cache(cls, session_id: str) -> "GraphAgent":
        """Factory — loads ASTs from cache and returns a ready agent."""
        agent = cls()
        return agent
