"""
Tool 3: Design Alternative Generator

Uses the LLM + retrieved engineering knowledge to generate
3 distinct design alternatives with trade-off analysis.
"""

import os
import re
import json
import requests
import yaml
from loguru import logger


def load_config(path="configs/config.yaml"):
    with open(path) as f:
        raw = f.read()
    raw = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ""), raw)
    return yaml.safe_load(raw)


DESIGN_PROMPT = """You are a senior automotive design engineer at BMW Group.
Based on the engineering requirements and knowledge context below, generate exactly 3 distinct design alternatives.

REQUIREMENTS:
{requirements}

ENGINEERING KNOWLEDGE CONTEXT:
{context}

Generate 3 design alternatives as a JSON array. Each alternative must have:
- id: "A", "B", or "C"
- name: short descriptive name
- concept: 2-3 sentence description of the design approach
- material: primary material and grade
- manufacturing_process: primary manufacturing method
- estimated_weight_kg: numerical estimate
- estimated_cost_index: 1 (lowest) to 5 (highest)
- performance_score: 1 (lowest) to 5 (highest) vs. requirements
- sustainability_score: 1 (lowest) to 5 (highest)
- advantages: list of 3 key advantages
- disadvantages: list of 2 key disadvantages
- feasibility: "HIGH" | "MEDIUM" | "LOW"
- recommended_for: what scenario this alternative is best suited for

Return ONLY a valid JSON array. No explanation outside the JSON."""


class DesignGenerator:
    def __init__(self, config_path="configs/config.yaml"):
        cfg = load_config(config_path)
        self.hf_token     = os.environ.get("HF_TOKEN", "")
        self.hf_url       = cfg["llm"]["hf_url"]
        self.ollama_url   = cfg["llm"]["ollama_url"]
        self.ollama_model = cfg["llm"]["ollama_model"]
        self.max_tokens   = cfg["llm"]["max_tokens"]
        self.n_alternatives = cfg["agent"]["design_alternatives"]

    def _call_llm(self, prompt: str) -> str:
        if self.hf_token:
            return self._call_hf(prompt)
        return self._call_ollama(prompt)

    def _call_hf(self, prompt: str) -> str:
        headers = {"Authorization": f"Bearer {self.hf_token}"}
        payload = {
            "inputs": f"<s>[INST] {prompt} [/INST]",
            "parameters": {"max_new_tokens": self.max_tokens, "temperature": 0.4, "return_full_text": False}
        }
        resp = requests.post(self.hf_url, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        result = resp.json()
        return result[0].get("generated_text", "") if isinstance(result, list) else str(result)

    def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": self.max_tokens, "temperature": 0.4}
        }
        resp = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["response"]

    def generate(self, requirements: dict, knowledge_context: str) -> list:
        """Generate design alternatives based on requirements and knowledge."""
        logger.info("Generating design alternatives...")

        req_str = json.dumps(requirements, indent=2)
        prompt  = DESIGN_PROMPT.format(
            requirements=req_str,
            context=knowledge_context
        )

        try:
            raw = self._call_llm(prompt)
            json_match = re.search(r'\[.*\]', raw, re.DOTALL)
            if json_match:
                alternatives = json.loads(json_match.group())
            else:
                alternatives = json.loads(raw.strip())

            if not isinstance(alternatives, list):
                alternatives = [alternatives]

        except Exception as e:
            logger.warning(f"LLM generation failed: {e}. Using fallback designs.")
            alternatives = self._fallback_designs(requirements)

        logger.success(f"Generated {len(alternatives)} design alternatives")
        return alternatives[:self.n_alternatives]

    def _fallback_designs(self, requirements: dict) -> list:
        """Fallback designs when LLM is unavailable."""
        component = requirements.get("component_name", "Component")
        priority  = requirements.get("priority", "performance")

        return [
            {
                "id": "A", "name": f"Steel-Based {component}",
                "concept": f"Conventional high-strength steel design optimised for {priority}. Uses press-forming and resistance spot welding for cost-effective manufacture.",
                "material": "DP800 High-Strength Steel",
                "manufacturing_process": "Press forming + resistance spot welding",
                "estimated_weight_kg": 3.5, "estimated_cost_index": 2,
                "performance_score": 3, "sustainability_score": 3, "feasibility": "HIGH",
                "advantages": ["Low tooling cost", "Proven manufacturing process", "Good crashworthiness"],
                "disadvantages": ["Higher weight than alternatives", "Corrosion risk without coating"],
                "recommended_for": "Cost-sensitive programmes with volume > 50,000 units/year"
            },
            {
                "id": "B", "name": f"Aluminium-Intensive {component}",
                "concept": "Multi-extrusion aluminium design with self-piercing rivet joining. 35% weight saving vs. steel baseline.",
                "material": "6061-T6 Aluminium Alloy",
                "manufacturing_process": "Extrusion + SPR joining",
                "estimated_weight_kg": 2.3, "estimated_cost_index": 3,
                "performance_score": 4, "sustainability_score": 4, "feasibility": "HIGH",
                "advantages": ["Significant weight saving", "High recyclability", "Corrosion resistant"],
                "disadvantages": ["Higher material cost", "Joining complexity vs. steel"],
                "recommended_for": "Programmes prioritising weight reduction and sustainability"
            },
            {
                "id": "C", "name": f"Topology-Optimised AM {component}",
                "concept": "LPBF metal AM component with topology-optimised geometry. Maximum performance-to-weight ratio.",
                "material": "AlSi10Mg (AM Grade)",
                "manufacturing_process": "Laser Powder Bed Fusion (LPBF)",
                "estimated_weight_kg": 1.4, "estimated_cost_index": 5,
                "performance_score": 5, "sustainability_score": 3, "feasibility": "MEDIUM",
                "advantages": ["Maximum weight optimisation", "Complex geometry freedom", "Integrated functions"],
                "disadvantages": ["High unit cost", "Limited volume scalability"],
                "recommended_for": "Low-volume, high-performance applications (motorsport, AMG, M variants)"
            }
        ]