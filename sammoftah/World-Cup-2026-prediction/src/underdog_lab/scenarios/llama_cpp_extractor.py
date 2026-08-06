from __future__ import annotations

import json
import subprocess
from pathlib import Path

from underdog_lab.config import LLAMA_CLI, MODEL_PATH
from underdog_lab.domain import MatchRecord
from underdog_lab.scenarios.prompts import build_prompt
from underdog_lab.scenarios.schemas import ScenarioExtraction


class LlamaCppExtractor:
    name = "llama.cpp"

    def __init__(
        self,
        model_path: Path = MODEL_PATH,
        executable: str = LLAMA_CLI,
        timeout_seconds: int = 45,
    ) -> None:
        self.model_path = model_path
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.grammar_path = Path(__file__).with_name("grammar.gbnf")

    def extract(self, text: str, match: MatchRecord) -> ScenarioExtraction:
        command = [
            self.executable,
            "-m",
            str(self.model_path),
            "--grammar-file",
            str(self.grammar_path),
            "-p",
            build_prompt(text, match),
            "-n",
            "512",
            "--temp",
            "0",
            "--no-display-prompt",
        ]
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        payload = self._extract_json(completed.stdout)
        return ScenarioExtraction.model_validate_json(payload)

    @staticmethod
    def _extract_json(output: str) -> str:
        start = output.find("{")
        end = output.rfind("}")
        if start < 0 or end < start:
            raise ValueError("llama.cpp output did not contain a JSON object.")
        payload = output[start : end + 1]
        json.loads(payload)
        return payload
