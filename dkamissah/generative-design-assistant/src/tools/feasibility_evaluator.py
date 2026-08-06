"""
Tool 4: Feasibility Evaluator + Report Generator

Scores each design alternative against the requirements,
ranks them, and generates a structured feasibility report.
"""

import os
import re
import json
import requests
from datetime import datetime
from pathlib import Path

import yaml
from loguru import logger


def load_config(path="configs/config.yaml"):
    with open(path) as f:
        raw = f.read()
    raw = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ""), raw)
    return yaml.safe_load(raw)


EVAL_PROMPT = """You are a senior engineering manager evaluating design alternatives.
Score and rank the following design alternatives against the requirements.
Provide a clear recommendation with justification.

REQUIREMENTS:
{requirements}

DESIGN ALTERNATIVES:
{alternatives}

Return a JSON object with:
- ranking: list of alternative IDs in order of recommendation (best first)
- recommended: ID of recommended alternative
- recommendation_rationale: 3-4 sentence justification
- scores: dict mapping alternative ID to overall score (0-100)
- risk_assessment: dict mapping alternative ID to risk level ("LOW"|"MEDIUM"|"HIGH")
- next_steps: list of 4-5 concrete next steps for the recommended alternative

Return ONLY valid JSON."""


class FeasibilityEvaluator:
    def __init__(self, config_path="configs/config.yaml"):
        cfg = load_config(config_path)
        self.hf_token     = os.environ.get("HF_TOKEN", "")
        self.hf_url       = cfg["llm"]["hf_url"]
        self.ollama_url   = cfg["llm"]["ollama_url"]
        self.ollama_model = cfg["llm"]["ollama_model"]
        self.max_tokens   = 768
        self.reports_dir  = cfg["outputs"]["reports_dir"]
        self.designs_dir  = cfg["outputs"]["designs_dir"]

    def _call_llm(self, prompt: str) -> str:
        if self.hf_token:
            headers = {"Authorization": f"Bearer {self.hf_token}"}
            payload = {
                "inputs": f"<s>[INST] {prompt} [/INST]",
                "parameters": {"max_new_tokens": self.max_tokens, "temperature": 0.2, "return_full_text": False}
            }
            resp = requests.post(self.hf_url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            result = resp.json()
            return result[0].get("generated_text", "") if isinstance(result, list) else str(result)
        else:
            payload = {
                "model": self.ollama_model, "prompt": prompt, "stream": False,
                "options": {"num_predict": self.max_tokens, "temperature": 0.2}
            }
            resp = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json()["response"]

    def evaluate(self, requirements: dict, alternatives: list) -> dict:
        """Score and rank design alternatives against requirements."""
        logger.info("Evaluating design alternatives...")

        prompt = EVAL_PROMPT.format(
            requirements=json.dumps(requirements, indent=2),
            alternatives=json.dumps(alternatives, indent=2)
        )

        try:
            raw = self._call_llm(prompt)
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            evaluation = json.loads(json_match.group() if json_match else raw.strip())
        except Exception as e:
            logger.warning(f"LLM evaluation failed: {e}. Using scoring fallback.")
            evaluation = self._fallback_evaluation(requirements, alternatives)

        logger.success(f"Recommended: Alternative {evaluation.get('recommended', 'B')}")
        return evaluation

    def _fallback_evaluation(self, requirements: dict, alternatives: list) -> dict:
        priority = requirements.get("priority", "performance")
        score_key = {
            "weight": "performance_score",
            "cost": "estimated_cost_index",
            "performance": "performance_score",
            "sustainability": "sustainability_score"
        }.get(priority, "performance_score")

        sorted_alts = sorted(
            alternatives,
            key=lambda x: x.get(score_key, 0),
            reverse=(score_key != "estimated_cost_index")
        )
        ranking = [a["id"] for a in sorted_alts]
        recommended = ranking[0] if ranking else "B"

        return {
            "ranking": ranking,
            "recommended": recommended,
            "recommendation_rationale": f"Alternative {recommended} best satisfies the {priority} priority based on scoring across key metrics.",
            "scores": {a["id"]: int(a.get("performance_score", 3) * 20) for a in alternatives},
            "risk_assessment": {a["id"]: a.get("feasibility", "MEDIUM") for a in alternatives},
            "next_steps": [
                "Initiate detailed CAD modelling of recommended concept.",
                "Perform FEA structural validation against load cases.",
                "Conduct DfM review with manufacturing team.",
                "Prepare prototype for physical validation testing.",
                "Submit for design review with programme team."
            ]
        }

    def generate_report(self, requirements: dict, knowledge: dict,
                         alternatives: list, evaluation: dict) -> dict:
        """Generate the full feasibility report."""
        timestamp    = datetime.now().isoformat()
        report_id    = f"GDA-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        recommended_id = evaluation.get("recommended", "B")
        recommended  = next((a for a in alternatives if a["id"] == recommended_id), alternatives[0])

        report = {
            "report_id":   report_id,
            "timestamp":   timestamp,
            "component":   requirements.get("component_name", "Engineering Component"),
            "requirements": requirements,
            "knowledge_sources": [v["title"] for v in knowledge.values()],
            "design_alternatives": alternatives,
            "evaluation":  evaluation,
            "recommended": recommended,
            "executive_summary": self._executive_summary(requirements, recommended, evaluation),
            "next_steps":  evaluation.get("next_steps", []),
        }

        # Save report
        Path(self.reports_dir).mkdir(parents=True, exist_ok=True)
        path = Path(self.reports_dir) / f"{report_id}.json"
        with open(path, "w") as f:
            json.dump(report, f, indent=2)

        # Save markdown
        md_path = Path(self.reports_dir) / f"{report_id}.md"
        with open(md_path, "w") as f:
            f.write(self._to_markdown(report))

        logger.success(f"Report saved: {path}")
        return report

    def _executive_summary(self, requirements: dict, recommended: dict,
                             evaluation: dict) -> str:
        component  = requirements.get("component_name", "component")
        rec_id     = recommended.get("id", "B")
        rec_name   = recommended.get("name", "recommended design")
        rationale  = evaluation.get("recommendation_rationale", "")
        priority   = requirements.get("priority", "performance")
        return (
            f"This feasibility study evaluated 3 design alternatives for the {component}. "
            f"Based on {priority} priority and engineering requirements analysis, "
            f"Alternative {rec_id} — {rec_name} — is recommended. "
            f"{rationale}"
        )

    def _to_markdown(self, report: dict) -> str:
        r   = report
        rec = r["recommended"]
        ev  = r["evaluation"]

        md = f"""# Generative Design Feasibility Report
**Report ID:** {r['report_id']}  
**Component:** {r['component']}  
**Generated:** {r['timestamp']}

---

## Executive Summary

{r['executive_summary']}

---

## Requirements Summary

| Field | Value |
|-------|-------|
| Component | {r['requirements'].get('component_name', '')} |
| Priority | {r['requirements'].get('priority', '')} |
| Design Space | {r['requirements'].get('design_space', '')} |

**Functional Requirements:**
{chr(10).join(f"- {req}" for req in r['requirements'].get('functional_requirements', []))}

**Performance Targets:**
{chr(10).join(f"- {k}: {v}" for k, v in r['requirements'].get('performance_targets', {}).items())}

**Constraints:**
{chr(10).join(f"- {c}" for c in r['requirements'].get('constraints', []))}

---

## Design Alternatives

"""
        for alt in r["design_alternatives"]:
            score = ev.get("scores", {}).get(alt["id"], "N/A")
            risk  = ev.get("risk_assessment", {}).get(alt["id"], "MEDIUM")
            rec_marker = " ⭐ RECOMMENDED" if alt["id"] == rec["id"] else ""
            md += f"""### Alternative {alt['id']}: {alt['name']}{rec_marker}

| Metric | Value |
|--------|-------|
| Material | {alt.get('material', '')} |
| Process | {alt.get('manufacturing_process', '')} |
| Est. Weight | {alt.get('estimated_weight_kg', '')} kg |
| Cost Index | {alt.get('estimated_cost_index', '')}/5 |
| Performance Score | {alt.get('performance_score', '')}/5 |
| Sustainability Score | {alt.get('sustainability_score', '')}/5 |
| Feasibility | {alt.get('feasibility', '')} |
| Overall Score | {score}/100 |
| Risk | {risk} |

**Concept:** {alt.get('concept', '')}

**Advantages:** {' · '.join(alt.get('advantages', []))}

**Disadvantages:** {' · '.join(alt.get('disadvantages', []))}

**Best for:** {alt.get('recommended_for', '')}

"""

        md += f"""---

## Evaluation & Recommendation

**Ranking:** {' > '.join(ev.get('ranking', []))}

**Recommendation:** Alternative {rec['id']} — {rec['name']}

{ev.get('recommendation_rationale', '')}

---

## Next Steps

"""
        for i, step in enumerate(r.get("next_steps", []), 1):
            md += f"{i}. {step}\n"

        md += f"""
---

## Knowledge Sources

{chr(10).join(f"- {s}" for s in r.get('knowledge_sources', []))}

---
*Generated by Generative Design Assistant v1.0*
"""
        return md
