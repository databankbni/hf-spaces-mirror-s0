"""Hugging Face Transformers backend for HALT-CoT."""

from __future__ import annotations

from dataclasses import fields, replace
import json
import os
from typing import Sequence

from .core import (
    AnswerCandidate,
    AnswerDistribution,
    EntropyHaltingController,
    HaltCoTConfig,
    HaltCoTResult,
    HaltCoTStep,
    answer_distribution_from_scores,
    format_reasoning,
    normalize_candidates,
)


HALT_COT_CONFIG_REPO = os.getenv("HALT_COT_CONFIG_REPO", "yass4/halt-cot")


def load_config_from_hub(
    repo_id: str = HALT_COT_CONFIG_REPO,
    *,
    filename: str = "config.json",
) -> HaltCoTConfig | None:
    """Fetch the published HALT-CoT defaults from the Hub.

    Downloading ``config.json`` through the Hub also lets Hugging Face count
    real usage of the method. Any failure (offline, missing repo, malformed
    file) returns ``None`` so callers fall back to the built-in defaults and a
    run is never blocked.
    """

    try:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(repo_id=repo_id, filename=filename)
        payload = json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return None

    values = payload.get("halt_cot", payload)
    if not isinstance(values, dict):
        return None

    defaults = HaltCoTConfig()
    tuple_fields = {
        f.name for f in fields(HaltCoTConfig)
        if isinstance(getattr(defaults, f.name), tuple)
    }
    kwargs = {}
    for field in fields(HaltCoTConfig):
        if field.name not in values:
            continue
        value = values[field.name]
        if field.name in tuple_fields and isinstance(value, list):
            value = tuple(value)
        kwargs[field.name] = value
    try:
        return HaltCoTConfig(**kwargs)
    except (TypeError, ValueError):
        return None


class TextStopCriteria:
    """Transformers stopping criterion that halts when generated text hits a marker."""

    def __init__(
        self,
        tokenizer,
        prompt_length: int,
        stop_strings: Sequence[str],
        min_new_tokens: int,
    ):
        from transformers import StoppingCriteria

        class _Criterion(StoppingCriteria):
            def __call__(inner_self, input_ids, scores, **kwargs) -> bool:
                new_len = input_ids.shape[-1] - prompt_length
                if new_len < min_new_tokens:
                    return False
                tail_start = max(prompt_length, input_ids.shape[-1] - 64)
                tail = tokenizer.decode(
                    input_ids[0, tail_start:],
                    skip_special_tokens=False,
                )
                return any(stop in tail for stop in stop_strings)

        self.criterion = _Criterion()


class HaltCoTForCausalLM:
    """Run HALT-CoT with any causal language model exposing next-token logits."""

    def __init__(self, model, tokenizer, config: HaltCoTConfig | None = None):
        self.model = model
        self.tokenizer = tokenizer
        self.config = config or HaltCoTConfig()

        if getattr(self.tokenizer, "pad_token_id", None) is None:
            eos_token = getattr(self.tokenizer, "eos_token", None)
            if eos_token is not None:
                self.tokenizer.pad_token = eos_token

    @classmethod
    def from_pretrained(
        cls,
        model_id: str,
        *,
        config: HaltCoTConfig | None = None,
        torch_dtype: str | None = "auto",
        device_map: str | None = None,
        trust_remote_code: bool = False,
        **kwargs,
    ) -> "HaltCoTForCausalLM":
        """Load a Transformers causal LM and tokenizer."""

        from transformers import AutoModelForCausalLM, AutoTokenizer

        if config is None:
            config = load_config_from_hub()

        tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            trust_remote_code=trust_remote_code,
        )

        model_kwargs = dict(kwargs)
        if torch_dtype is not None:
            model_kwargs["torch_dtype"] = torch_dtype
        if device_map is not None:
            model_kwargs["device_map"] = device_map
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            trust_remote_code=trust_remote_code,
            **model_kwargs,
        )
        if device_map is None:
            model.to(_default_device())
        model.eval()
        return cls(model=model, tokenizer=tokenizer, config=config)

    def run(
        self,
        question: str,
        candidates: Sequence[str | AnswerCandidate],
        config: HaltCoTConfig | None = None,
    ) -> HaltCoTResult:
        """Generate reasoning steps until answer entropy crosses the threshold."""

        run_config = config or self.config
        answer_candidates = normalize_candidates(candidates)
        controller = EntropyHaltingController(run_config)
        context = run_config.prompt_template.format(question=question)
        steps: list[HaltCoTStep] = []
        generated_tokens = 0
        last_distribution: AnswerDistribution | None = None

        for index in range(1, run_config.max_steps + 1):
            step_prompt = _ensure_trailing_newline(context) + run_config.step_prefix.format(step=index)
            step_text, token_count = self.generate_step(step_prompt, run_config)
            generated_tokens += token_count
            step_text = step_text.strip()
            context = f"{step_prompt}{step_text}\n"

            distribution = self.answer_distribution(
                context + run_config.answer_probe,
                answer_candidates,
                entropy_unit=run_config.entropy_unit,
            )
            last_distribution = distribution
            decision = controller.observe(distribution.entropy, index)

            steps.append(
                HaltCoTStep(
                    index=index,
                    text=step_text,
                    entropy=distribution.entropy,
                    prediction=distribution.prediction,
                    probabilities=distribution.probabilities,
                    halted=decision.should_halt,
                    generated_tokens=token_count,
                )
            )

            if decision.should_halt:
                return HaltCoTResult(
                    answer=distribution.prediction,
                    halted=True,
                    steps=tuple(steps),
                    reasoning=format_reasoning(steps),
                    generated_tokens=generated_tokens,
                )

        if last_distribution is None:
            raise RuntimeError("HALT-CoT run produced no steps")

        return HaltCoTResult(
            answer=last_distribution.prediction,
            halted=False,
            steps=tuple(steps),
            reasoning=format_reasoning(steps),
            generated_tokens=generated_tokens,
        )

    def generate_step(self, prompt: str, config: HaltCoTConfig) -> tuple[str, int]:
        """Generate one bounded reasoning step."""

        import torch
        from transformers import StoppingCriteriaList

        inputs = self._encode(prompt)
        prompt_length = inputs["input_ids"].shape[-1]
        stopping_criteria = None
        if config.step_stop_strings:
            stopping_criteria = StoppingCriteriaList(
                [
                    TextStopCriteria(
                        self.tokenizer,
                        prompt_length,
                        config.step_stop_strings,
                        config.step_min_new_tokens,
                    ).criterion
                ]
            )

        generation_kwargs = {
            "max_new_tokens": config.step_max_new_tokens,
            "do_sample": config.do_sample,
            "pad_token_id": self.tokenizer.pad_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
            "stopping_criteria": stopping_criteria,
        }
        if config.do_sample:
            generation_kwargs["temperature"] = max(config.temperature, 1e-6)
            generation_kwargs["top_p"] = config.top_p

        with torch.inference_mode():
            output_ids = self.model.generate(**inputs, **generation_kwargs)[0]

        new_ids = output_ids[prompt_length:]
        text = self.tokenizer.decode(new_ids, skip_special_tokens=True).lstrip()
        text = _truncate_at_first_stop(text, config.step_stop_strings)
        return text, int(new_ids.shape[-1])

    def answer_distribution(
        self,
        context: str,
        candidates: Sequence[AnswerCandidate],
        *,
        entropy_unit: str = "bits",
    ) -> AnswerDistribution:
        """Compute answer entropy from next-token logits over candidates."""

        import torch

        candidate_token_ids = first_token_ids_by_candidate(self.tokenizer, candidates)
        inputs = self._encode(context)
        with torch.inference_mode():
            logits = self.model(**inputs).logits[0, -1, :].float()

        scores: dict[str, float] = {}
        for candidate in candidates:
            token_ids = candidate_token_ids[candidate.label]
            token_logits = logits[token_ids]
            scores[candidate.label] = float(torch.logsumexp(token_logits, dim=0).item())

        return answer_distribution_from_scores(scores, entropy_unit=entropy_unit)

    def _encode(self, text: str):
        inputs = self.tokenizer(text, return_tensors="pt")
        return inputs.to(_model_device(self.model))


def first_token_ids_by_candidate(
    tokenizer,
    candidates: Sequence[AnswerCandidate],
) -> dict[str, list[int]]:
    """Map each candidate to first-token ids for its label and aliases."""

    mapping: dict[str, list[int]] = {}
    for candidate in candidates:
        token_ids: set[int] = set()
        for text in candidate.texts:
            for variant in _candidate_variants(text):
                encoded = tokenizer.encode(variant, add_special_tokens=False)
                if encoded:
                    token_ids.add(int(encoded[0]))
        if not token_ids:
            raise ValueError(f"Candidate {candidate.label!r} did not tokenize to any ids")
        mapping[candidate.label] = sorted(token_ids)
    return mapping


def with_config(base: HaltCoTConfig, **updates) -> HaltCoTConfig:
    """Return a modified config while preserving dataclass validation."""

    return replace(base, **updates)


def _candidate_variants(text: str) -> tuple[str, ...]:
    stripped = text.strip()
    variants = {stripped, f" {stripped}"}
    if stripped[:1].isalpha():
        variants.add(stripped.lower())
        variants.add(stripped.upper())
        variants.add(f" {stripped.lower()}")
        variants.add(f" {stripped.upper()}")
    return tuple(variant for variant in variants if variant)


def _truncate_at_first_stop(text: str, stop_strings: Sequence[str]) -> str:
    if not stop_strings:
        return text
    indexes = [text.find(stop) for stop in stop_strings if text.find(stop) >= 0]
    if not indexes:
        return text
    return text[: min(indexes)]


def _ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"


def _model_device(model):
    try:
        return next(model.parameters()).device
    except StopIteration:
        return _default_device()


def _default_device():
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")
