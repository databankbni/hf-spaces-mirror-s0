"""
Onboarding Agent — generates a beginner-friendly guide for a new developer.
Deterministic; uses cached overview, graph, and risk data.
"""
from pathlib import Path
import networkx as nx

from services.graph_service import get_graph_service
from services.cache_service import get_cache_service
from models.onboarding import (
    OnboardingResponse, StartPoint, KeyModule, GlossaryItem
)
from utils.logger import get_logger

logger = get_logger(__name__)

GLOSSARY = [
    GlossaryItem(term="dependency graph", meaning="Shows which files import or depend on each other."),
    GlossaryItem(term="call graph", meaning="Shows how functions call each other at runtime."),
    GlossaryItem(term="flow trace", meaning="Tracks execution from one function/file to another, step by step."),
    GlossaryItem(term="risk score", meaning="A 0–10 measure of overall codebase health and security risk."),
    GlossaryItem(term="centrality", meaning="A metric for how 'central' a file is — high centrality means many files depend on it."),
    GlossaryItem(term="tight coupling", meaning="When a module heavily depends on many others, making changes risky."),
    GlossaryItem(term="entry point", meaning="The file or function where execution begins (e.g., main.py, index.ts)."),
]

LEARNING_PATH = [
    "Read the main app entrypoint to understand the overall wiring.",
    "Review route or controller files to understand request flow.",
    "Understand the service layer — where business logic lives.",
    "Inspect data access / repository layers.",
    "Study authentication and authorization flows.",
    "Ask targeted questions using 'Ask Repo' for deep dives.",
]

SUGGESTED_QUESTIONS = [
    "How does authentication work in this repo?",
    "Which files are most central to the application?",
    "Where is the main application entry point?",
    "What are the highest-risk files I should be careful editing?",
    "How does data flow from API requests to the database?",
]


def _label(path: str) -> str:
    return Path(path).name


def _module_name(path: str) -> str:
    parts = Path(path).parts
    if len(parts) > 1:
        return parts[1] if parts[0] in ("src", "app", ".") else parts[0]
    return parts[0]


class OnboardingAgent:
    def __init__(self):
        self.graph_svc = get_graph_service()
        self.cache = get_cache_service()

    def run(self, session_id: str) -> OnboardingResponse:
        logger.info(f"[{session_id}] OnboardingAgent: generating guide")

        overview_data = self.cache.get_overview(session_id) or {}
        graph_data = self.cache.get_graph(session_id) or {}
        risk_data = self.cache.get_risk(session_id) or {}
        asts_data = self.cache.get_asts(session_id) or []

        repo_name = overview_data.get("repo_name", "this repository")
        entry_points = overview_data.get("entry_points", [])
        readme_summary = overview_data.get("readme_summary", "")
        top_modules_raw = overview_data.get("top_modules", [])

        G_dep: nx.DiGraph = nx.DiGraph()
        if graph_data:
            repo_graph = self.graph_svc.from_json(graph_data)
            G_dep = repo_graph.dep_graph

        # ── Recommended start points ──────────────────────────────────────────
        start_points: list[StartPoint] = []

        # 1. Known entry points first
        for ep in entry_points[:2]:
            start_points.append(StartPoint(
                title=f"Start with '{_label(ep)}'",
                file=ep,
                reason="This is the main application entrypoint — it wires all modules together.",
            ))

        # 2. High in-degree files (many others depend on them)
        if G_dep.number_of_nodes() > 0:
            by_indegree = sorted(G_dep.nodes(), key=lambda n: G_dep.in_degree(n), reverse=True)
            for node in by_indegree[:3]:
                if node not in {sp.file for sp in start_points}:
                    start_points.append(StartPoint(
                        title=f"Understand '{_label(node)}'",
                        file=node,
                        reason=f"Used by {G_dep.in_degree(node)} other files — a core building block.",
                    ))
                    if len(start_points) >= 5:
                        break

        # ── Key modules ───────────────────────────────────────────────────────
        module_files: dict[str, list[str]] = {}
        for ast_d in asts_data:
            path = ast_d.get("path", "")
            mod = _module_name(path)
            module_files.setdefault(mod, []).append(path)

        key_modules: list[KeyModule] = []
        for mod_name in top_modules_raw[:6]:
            files_in_mod = module_files.get(mod_name, [])
            n = len(files_in_mod)
            summary = f"Contains {n} file(s). " if n else ""
            # check if risky
            risk_items = risk_data.get("items", [])
            mod_risks = [i for i in risk_items if any(mod_name in f for f in i.get("affected_files", []))]
            if mod_risks:
                summary += f"Has {len(mod_risks)} known risk(s). "
            summary += "Review this module early to understand its responsibilities."
            key_modules.append(KeyModule(name=mod_name, summary=summary.strip()))

        if not key_modules:
            for mod_name, files in list(module_files.items())[:5]:
                key_modules.append(KeyModule(
                    name=mod_name,
                    summary=f"Contains {len(files)} file(s). Explore to understand its responsibilities."
                ))

        # ── Overview text ─────────────────────────────────────────────────────
        total_files = overview_data.get("total_files", len(asts_data))
        total_funcs = overview_data.get("total_functions", 0)
        risk_score = overview_data.get("risk_score", 0)
        languages = overview_data.get("languages", {})
        primary_lang = max(languages, key=languages.get) if languages else "Mixed"

        overview = (
            f"'{repo_name}' is a {primary_lang} repository with {total_files} files "
            f"and {total_funcs} functions. "
        )
        if readme_summary:
            overview += readme_summary[:200] + " "
        overview += (
            f"Risk score: {risk_score:.1f}/10. "
            f"Key modules: {', '.join(top_modules_raw[:4]) or 'see graph'}."
        )

        return OnboardingResponse(
            session_id=session_id,
            repo_name=repo_name,
            overview=overview,
            recommended_start_points=start_points[:5],
            key_modules=key_modules[:6],
            learning_path=LEARNING_PATH,
            glossary=GLOSSARY,
            suggested_questions=SUGGESTED_QUESTIONS,
        )
