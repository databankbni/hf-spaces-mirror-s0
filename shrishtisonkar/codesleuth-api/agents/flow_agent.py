"""
Flow Agent — DFS/BFS traversal of the call graph from an entry point.
Returns an ordered execution path for the Execution Flow Visualizer.
"""
import asyncio
from pathlib import Path
from collections import deque

import networkx as nx

from services.graph_service import get_graph_service
from services.cache_service import get_cache_service
from models.flow import FlowNode, FlowEdge, FlowResponse
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_DEPTH = 8
MAX_NODES = 60


class FlowAgent:
    def __init__(self):
        self.graph_svc = get_graph_service()
        self.cache     = get_cache_service()

    async def run(self, session_id: str, entry_point: str) -> FlowResponse:
        graph_data = self.cache.get_graph(session_id)
        if not graph_data:
            return self._empty_response(session_id, entry_point, "Graph not yet built")

        repo_graph = await asyncio.to_thread(self.graph_svc.from_json, graph_data)
        G = repo_graph.call_graph

        # Find best matching start node
        start_node = self._resolve_entry(G, entry_point)
        if start_node is None:
            # Fall back to dependency graph traversal (file level)
            G = repo_graph.dep_graph
            start_node = self._resolve_entry(G, entry_point)

        if start_node is None:
            return self._empty_response(session_id, entry_point, f"Entry point '{entry_point}' not found")

        # BFS traversal
        visited: dict[str, int] = {}  # node → depth
        queue = deque([(start_node, 0)])
        edges_seen: set[tuple] = set()
        flow_nodes: list[FlowNode] = []
        flow_edges: list[FlowEdge] = []

        while queue and len(flow_nodes) < MAX_NODES:
            node, depth = queue.popleft()
            if node in visited or depth > MAX_DEPTH:
                continue
            visited[node] = depth

            node_data = G.nodes.get(node, {})
            file_path  = node_data.get("file_path", node)
            label      = node_data.get("label", Path(node).name)
            line_start = node_data.get("line_start")
            line_end   = node_data.get("line_end")

            # Separate "file::function" → function_name
            func_name = None
            if "::" in node:
                _, func_name = node.rsplit("::", 1)

            flow_nodes.append(FlowNode(
                id=node,
                label=label,
                file_path=file_path,
                function_name=func_name,
                line_start=line_start,
                line_end=line_end,
                depth=depth,
                node_type="entrypoint" if depth == 0 else "function",
            ))

            for neighbor in G.successors(node):
                edge_key = (node, neighbor)
                if edge_key not in edges_seen:
                    edges_seen.add(edge_key)
                    edge_data = G.edges.get(edge_key, {})
                    is_recursive = neighbor == node or (neighbor in visited)
                    flow_edges.append(FlowEdge(
                        source=node,
                        target=neighbor,
                        call_type="recursive" if is_recursive else "direct",
                    ))
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))

        # Detect cycles
        has_cycles = False
        cycle_nodes: list[str] = []
        try:
            cycle = nx.find_cycle(G.subgraph(list(visited.keys())))
            has_cycles = True
            cycle_nodes = list({u for u, v, *_ in cycle} | {v for u, v, *_ in cycle})
        except nx.NetworkXNoCycle:
            pass

        return FlowResponse(
            session_id=session_id,
            entry_point=entry_point,
            nodes=flow_nodes,
            edges=flow_edges,
            total_steps=len(flow_nodes),
            max_depth=max(visited.values()) if visited else 0,
            has_cycles=has_cycles,
            cycle_nodes=cycle_nodes,
        )

    def _resolve_entry(self, G: nx.DiGraph, entry_point: str) -> str | None:
        """Find the best matching node for the given entry_point string."""
        if entry_point in G:
            return entry_point
        # Partial match — find node whose label / path contains the entry_point
        ep_lower = entry_point.lower()
        candidates = [
            n for n in G.nodes()
            if ep_lower in n.lower()
        ]
        if candidates:
            # Prefer nodes with no in-edges (true entry points)
            roots = [n for n in candidates if G.in_degree(n) == 0]
            return roots[0] if roots else candidates[0]
        return None

    def _empty_response(self, session_id: str, entry_point: str, msg: str) -> FlowResponse:
        logger.warning(f"[{session_id}] FlowAgent: {msg}")
        return FlowResponse(
            session_id=session_id,
            entry_point=entry_point,
            nodes=[],
            edges=[],
            total_steps=0,
            max_depth=0,
            has_cycles=False,
            cycle_nodes=[],
        )
