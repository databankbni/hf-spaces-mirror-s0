"""
Tool 1: Requirements Parser

Extracts structured engineering requirements from free-text input
using the LLM. Identifies functional requirements, performance targets,
constraints, and interface requirements.
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


PARSE_PROMPT = """Extract structured engineering requirements from the following text.
Return a JSON object with these fields:
- component_name: name of the component/system
- functional_requirements: list of what it must do
- performance_targets: dict of measurable targets (e.g. {{"max_weight_kg": 2.5, "min_strength_mpa": 400}})
- constraints: list of hard constraints (material, process, cost, regulatory)
- interface_requirements: list of how it connects to other systems
- design_space: description of available volume/space
- priority: "weight" | "cost" | "performance" | "sustainability"

Return ONLY valid JSON. No explanation.

Requirements text:
{requirements_text}"""


class RequirementsParser:
    def __init__(self, config_path="configs/config.yaml"):
        cfg = load_config(config_path)
        self.hf_token  = os.environ.get("HF_TOKEN", "")
        self.hf_url    = cfg["llm"]["hf_url"]
        self.ollama_url = cfg["llm"]["ollama_url"]
        self.ollama_model = cfg["llm"]["ollama_model"]
        self.max_tokens = cfg["llm"]["max_tokens"]

    def _call_llm(self, prompt: str) -> str:
        if self.hf_token:
            return self._call_hf(prompt)
        return self._call_ollama(prompt)

    def _call_hf(self, prompt: str) -> str:
        headers = {"Authorization": f"Bearer {self.hf_token}"}
        payload = {
            "inputs": f"<s>[INST] {prompt} [/INST]",
            "parameters": {"max_new_tokens": 512, "temperature": 0.1, "return_full_text": False}
        }
        resp = requests.post(self.hf_url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        return result[0].get("generated_text", "") if isinstance(result, list) else str(result)

    def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 512, "temperature": 0.1}
        }
        resp = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["response"]

    def parse(self, requirements_text: str) -> dict:
        """Parse free-text requirements into structured format."""
        logger.info("Parsing requirements...")
        prompt = PARSE_PROMPT.format(requirements_text=requirements_text)

        try:
            raw = self._call_llm(prompt)
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
            else:
                parsed = json.loads(raw.strip())
        except Exception as e:
            logger.warning(f"LLM parsing failed: {e}. Using fallback extraction.")
            parsed = self._fallback_parse(requirements_text)

        # Ensure all required fields exist
        defaults = {
            "component_name": "Engineering Component",
            "functional_requirements": [],
            "performance_targets": {},
            "constraints": [],
            "interface_requirements": [],
            "design_space": "Not specified",
            "priority": "performance"
        }
        for k, v in defaults.items():
            if k not in parsed:
                parsed[k] = v

        logger.success(f"Parsed requirements: {parsed['component_name']}")
        return parsed

    def _fallback_parse(self, text: str) -> dict:
        """Rule-based fallback when LLM fails."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return {
            "component_name":        lines[0] if lines else "Component",
            "functional_requirements": list(lines[1:4]),
            "performance_targets":   {},
            "constraints":           [],
            "interface_requirements": [],
            "design_space":          "Not specified",
            "priority":              "performance"
        }