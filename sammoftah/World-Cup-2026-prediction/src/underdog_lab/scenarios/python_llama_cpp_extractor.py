from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path

from underdog_lab.config import MODEL_FILENAME, MODEL_PATH, MODEL_REPO
from underdog_lab.domain import MatchRecord
from underdog_lab.scenarios.prompts import build_messages
from underdog_lab.scenarios.schemas import ScenarioExtraction


class PythonLlamaCppExtractor:
    """In-process llama.cpp runtime for a local grammar-constrained GGUF."""

    name = "SmolLM2-360M via llama.cpp"

    def __init__(
        self,
        model_path: Path = MODEL_PATH,
        model_repo: str = MODEL_REPO,
        model_filename: str = MODEL_FILENAME,
    ) -> None:
        self.model_path = model_path
        self.model_repo = model_repo
        self.model_filename = model_filename
        self.grammar_path = Path(__file__).with_name("grammar.gbnf")

    @cached_property
    def llama(self):
        from huggingface_hub import hf_hub_download
        from llama_cpp import Llama

        path = self.model_path
        if not path.exists():
            downloaded = hf_hub_download(
                repo_id=self.model_repo,
                filename=self.model_filename,
            )
            path = Path(downloaded)
        return Llama(
            model_path=str(path),
            n_ctx=1536,
            n_threads=2,
            n_batch=128,
            verbose=False,
        )

    @cached_property
    def grammar(self):
        from llama_cpp import LlamaGrammar

        return LlamaGrammar.from_file(str(self.grammar_path))

    def extract(self, text: str, match: MatchRecord) -> ScenarioExtraction:
        response = self.llama.create_chat_completion(
            messages=build_messages(text, match),
            max_tokens=256,
            temperature=0.0,
            grammar=self.grammar,
        )
        payload = response["choices"][0]["message"]["content"].strip()
        json.loads(payload)
        return ScenarioExtraction.model_validate_json(payload)

    def warmup(self) -> None:
        """Download and load the model before the first interactive request."""
        _ = self.llama
        _ = self.grammar
