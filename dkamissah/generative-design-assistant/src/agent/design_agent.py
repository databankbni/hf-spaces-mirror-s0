"""
Generative Design Assistant — Main Agent

Orchestrates 4 tools in sequence to analyse engineering requirements
and generate design alternatives with feasibility assessment:

1. parse_requirements    — extract structured specs from free text
2. retrieve_knowledge    — query engineering standards knowledge base
3. generate_designs      — produce 3 design alternatives via LLM
4. evaluate_and_report   — score, rank, and generate feasibility report

Usage:
    from src.agent.design_agent import DesignAgent
    agent = DesignAgent()
    result = agent.run("Design a lightweight suspension bracket for a BEV...")
"""

import os
import re
import time
import yaml
from loguru import logger

import mlflow
from src.tools.requirements_parser import RequirementsParser
from src.tools.knowledge_retriever import KnowledgeRetriever
from src.tools.design_generator import DesignGenerator
from src.tools.feasibility_evaluator import FeasibilityEvaluator


def load_config(path="configs/config.yaml"):
    with open(path) as f:
        raw = f.read()
    raw = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ""), raw)
    return yaml.safe_load(raw)


class DesignAgent:
    """
    LangChain-style agent for generative engineering design.

    Follows a structured reasoning chain:
    Parse Requirements → Retrieve Knowledge → Generate Designs → Evaluate & Report
    """

    def __init__(self, config_path="configs/config.yaml"):
        self.cfg = load_config(config_path)
        logger.info("Initialising DesignAgent...")
        self.parser    = RequirementsParser(config_path)
        self.retriever = KnowledgeRetriever(config_path)
        self.generator = DesignGenerator(config_path)
        self.evaluator = FeasibilityEvaluator(config_path)
        logger.success("DesignAgent ready — 4 tools loaded")

    def run(self, requirements_text: str, verbose: bool = True,
             track: bool = True) -> dict:
        """
        Run the full generative design pipeline.

        Args:
            requirements_text: Free-text engineering requirements
            verbose:           Log each step
            track:             Log run to MLflow

        Returns:
            Full result with requirements, alternatives, evaluation, and report
        """
        t0 = time.time()
        logger.info(f"\n{'='*60}")
        logger.info("DesignAgent.run()")
        logger.info(f"{'='*60}")

        # ── Step 1: Parse Requirements ──────────────────────────────────
        logger.info("STEP 1: Parsing requirements")
        requirements = self.parser.parse(requirements_text)
        if verbose:
            logger.info(f"  Component: {requirements['component_name']}")
            logger.info(f"  Priority: {requirements['priority']}")
            logger.info(f"  Functional requirements: {len(requirements['functional_requirements'])}")

        # ── Step 2: Retrieve Knowledge ──────────────────────────────────
        logger.info("STEP 2: Retrieving engineering knowledge")
        knowledge = self.retriever.retrieve_for_requirements(requirements)
        context   = self.retriever.format_context(knowledge)
        if verbose:
            logger.info(f"  Knowledge sources retrieved: {len(knowledge)}")

        # ── Step 3: Generate Designs ────────────────────────────────────
        logger.info("STEP 3: Generating design alternatives")
        alternatives = self.generator.generate(requirements, context)
        if verbose:
            for alt in alternatives:
                logger.info(f"  Alt {alt['id']}: {alt['name']} — {alt.get('material', '')} — {alt.get('estimated_weight_kg', '')}kg")

        # ── Step 4: Evaluate & Report ───────────────────────────────────
        logger.info("STEP 4: Evaluating and generating report")
        evaluation = self.evaluator.evaluate(requirements, alternatives)
        report     = self.evaluator.generate_report(requirements, knowledge, alternatives, evaluation)

        total_ms = int((time.time() - t0) * 1000)
        logger.success(f"Pipeline complete in {total_ms}ms")
        logger.success(f"Recommended: Alternative {evaluation.get('recommended', 'B')}")

        result = {
            "requirements":  requirements,
            "knowledge":     knowledge,
            "alternatives":  alternatives,
            "evaluation":    evaluation,
            "report":        report,
            "pipeline_ms":   total_ms,
            "steps_completed": 4,
        }

        if track:
            try:
                mlflow.set_tracking_uri(self.cfg["mlflow"]["tracking_uri"])
                mlflow.set_experiment(self.cfg["mlflow"]["experiment_name"])
                with mlflow.start_run(run_name="design_run"):
                    # Parameters
                    mlflow.log_params({
                        "component":       requirements.get("component_name", "unknown"),
                        "priority":        requirements.get("priority", "unknown"),
                        "n_alternatives":  len(alternatives),
                        "recommended":     evaluation.get("recommended", "unknown"),
                        "embedding_model": self.cfg["embeddings"]["model"],
                        "llm_model":       self.cfg["llm"].get("hf_model", self.cfg["llm"].get("ollama_model", "")),
                        "top_k":           self.cfg["retrieval"]["top_k"],
                    })
                    # Metrics
                    scores = evaluation.get("scores", {})
                    for alt_id, score in scores.items():
                        mlflow.log_metric(f"score_alt_{alt_id}", float(score))
                    mlflow.log_metric("pipeline_ms", total_ms)
                    mlflow.log_metric("n_knowledge_sources", len(knowledge))
                    # Artifact
                    import json
                    import tempfile
                    import os
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                        json.dump(result["report"], f, indent=2)
                        tmp = f.name
                    mlflow.log_artifact(tmp, "report")
                    os.unlink(tmp)
                logger.info("MLflow run logged")
            except Exception as e:
                logger.warning(f"MLflow logging failed (non-critical): {e}")

        return result