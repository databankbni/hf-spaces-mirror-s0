from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from collections import defaultdict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_PATH = ROOT / "data" / "intent_training" / "global_intent_examples.jsonl"
PROTOTYPES_PATH = ROOT / "data" / "intent_training" / "global_intent_semantic_prototypes.jsonl"


class IntentExampleMatcherV2:
    """Local semantic fallback trained from reviewed business utterances.

    Character n-grams are deliberately used because Chinese internal-business
    messages are short and often contain typos, missing spaces, abbreviations,
    or mixed Latin model names. This layer proposes an intent only; pricing
    readiness and required-field validation remain owned by the state machine.
    """

    def __init__(self, examples_path: Path = EXAMPLES_PATH) -> None:
        self.examples_path = Path(examples_path)
        self.rows: list[dict[str, Any]] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None
        self._load()

    def _load(self) -> None:
        rows = []
        paths = [self.examples_path]
        if self.examples_path == EXAMPLES_PATH:
            paths.append(PROTOTYPES_PATH)
        for path in paths:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("message") and row.get("selectedBusinessModule") and row.get("expected"):
                    rows.append(row)
        if not rows:
            return
        self.rows = rows
        self.vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(2, 4),
            min_df=1,
            sublinear_tf=True,
            norm="l2",
        )
        self.matrix = self.vectorizer.fit_transform([str(row["message"]) for row in rows])

    def match(
        self,
        message: str,
        selected_module: str,
        *,
        min_score: float = 0.54,
    ) -> Dict[str, Any]:
        if not self.rows or self.vectorizer is None or self.matrix is None:
            return {}
        query = self.vectorizer.transform([str(message or "")])
        scores = linear_kernel(query, self.matrix).ravel()
        candidates = [
            (float(score), index, self.rows[index])
            for index, score in enumerate(scores)
            if self.rows[index].get("selectedBusinessModule") == selected_module
        ]
        if not candidates:
            return {}
        candidates.sort(key=lambda item: item[0], reverse=True)
        top_score, _, top_row = candidates[0]
        if top_score < min_score:
            return {}
        top_intent = (top_row.get("expected") or {}).get("internal_intent")
        supporting = [
            {
                "score": round(score, 4),
                "message": row.get("message"),
                "internal_intent": (row.get("expected") or {}).get("internal_intent"),
                "example_id": row.get("example_id"),
            }
            for score, _, row in candidates[:5]
            if (row.get("expected") or {}).get("internal_intent") == top_intent
        ]
        runner_up = next(
            (
                score
                for score, _, row in candidates[1:]
                if (row.get("expected") or {}).get("internal_intent") != top_intent
            ),
            0.0,
        )
        margin = top_score - float(runner_up)
        if margin < 0.035 and top_score < 0.72:
            return {}
        return {
            "score": round(top_score, 4),
            "margin": round(margin, 4),
            "row": top_row,
            "expected": top_row.get("expected") or {},
            "supporting_examples": supporting,
        }

    def route_across_modules(
        self,
        message: str,
        selected_module: str,
        *,
        min_score: float = 0.50,
    ) -> Dict[str, Any]:
        """Return a cross-module semantic route proposal.

        The normal ``match`` method only compares examples inside the current
        module, which is useful for local fallback but weak for an enterprise
        assistant: users can ask for a report while the pricing tab is active,
        or paste a vehicle while reading a report.  This method scores all
        reviewed utterances, applies only a tiny current-module prior, and
        returns enough diagnostics for the state machine to either accept the
        route or ask a clarification question.
        """
        if not self.rows or self.vectorizer is None or self.matrix is None:
            return {}
        query = self.vectorizer.transform([str(message or "")])
        scores = linear_kernel(query, self.matrix).ravel()
        candidates = []
        for index, score in enumerate(scores):
            row = self.rows[index]
            module = row.get("selectedBusinessModule")
            if not module:
                continue
            adjusted = float(score) + (0.018 if module == selected_module else 0.0)
            candidates.append((adjusted, float(score), index, row))
        if not candidates:
            return {}
        candidates.sort(key=lambda item: item[0], reverse=True)
        top_adjusted, top_raw, _, top_row = candidates[0]
        if top_adjusted < min_score:
            return {}

        top_module = top_row.get("selectedBusinessModule")
        top_expected = top_row.get("expected") or {}
        top_intent = top_expected.get("internal_intent")
        module_best: dict[str, float] = defaultdict(float)
        intent_best: dict[tuple[str, str], float] = defaultdict(float)
        for adjusted, _raw, _index, row in candidates:
            module = row.get("selectedBusinessModule") or ""
            expected = row.get("expected") or {}
            intent = expected.get("internal_intent") or ""
            module_best[module] = max(module_best[module], adjusted)
            intent_best[(module, intent)] = max(intent_best[(module, intent)], adjusted)

        runner_module_score = max(
            (score for module, score in module_best.items() if module != top_module),
            default=0.0,
        )
        runner_intent_score = max(
            (
                score
                for (module, intent), score in intent_best.items()
                if module != top_module or intent != top_intent
            ),
            default=0.0,
        )
        supporting = [
            {
                "score": round(raw, 4),
                "adjusted_score": round(adjusted, 4),
                "message": row.get("message"),
                "selectedBusinessModule": row.get("selectedBusinessModule"),
                "internal_intent": (row.get("expected") or {}).get("internal_intent"),
                "example_id": row.get("example_id"),
            }
            for adjusted, raw, _index, row in candidates[:8]
            if row.get("selectedBusinessModule") == top_module
        ]
        module_margin = top_adjusted - float(runner_module_score)
        intent_margin = top_adjusted - float(runner_intent_score)
        needs_clarification = module_margin < 0.025 and top_adjusted < 0.70
        return {
            "score": round(top_adjusted, 4),
            "raw_score": round(top_raw, 4),
            "module_margin": round(module_margin, 4),
            "intent_margin": round(intent_margin, 4),
            "selected_module": top_module,
            "expected": top_expected,
            "row": top_row,
            "supporting_examples": supporting[:5],
            "needs_clarification": needs_clarification,
            "module_scores": {
                module: round(score, 4)
                for module, score in sorted(module_best.items(), key=lambda item: item[1], reverse=True)
            },
        }
