from __future__ import annotations

import time
from typing import Any

import httpx

from app.eval.domain.metrics import EvalQuestion, EvalResult, check_answer


def evaluate_question(
    q: EvalQuestion,
    api_url: str,
    top_k: int,
    client: httpx.Client,
    byok_key: str | None = None,
    byok_model: str | None = None,
) -> EvalResult:
    payload: dict[str, Any] = {
        "question": q.question,
        "history": [],
        "locale": q.language,
        "filters": {
            "subject": q.subject,
            "grade": q.grade,
            "limit": top_k,
        },
    }
    # GRO-89: include BYOK generation block when key/model are provided
    if byok_key and byok_model:
        m = byok_model.lower()
        if m.startswith("gemini"):
            provider = "google"
        elif m.startswith("gpt-") or m.startswith("o1") or m.startswith("o3"):
            provider = "openai"
        else:
            provider = "anthropic"
        payload["generation"] = {
            "provider": provider,
            "model": byok_model,
            "api_key": byok_key,
        }
    t0 = time.perf_counter()
    
    retries = 5
    backoff = 2
    for attempt in range(retries):
        try:
            resp = client.post(f"{api_url}/api/query", json=payload, timeout=120.0)
            if resp.status_code in (429, 503, 504, 500):
                retry_after = resp.headers.get("Retry-After")
                wait_time = int(retry_after) if retry_after and retry_after.isdigit() else backoff
                print(f"[{q.id}] Server error {resp.status_code}, backing off {wait_time}s...")
                time.sleep(wait_time)
                backoff *= 2
                continue
            resp.raise_for_status()
            body = resp.json()
            latency_ms = (time.perf_counter() - t0) * 1000
            raw_answer = body.get("answer") or ""
            # GRO-89: grade the answer when expected_answer is set
            answer_correct: bool | None = None
            if q.expected_answer and raw_answer:
                answer_correct = check_answer(raw_answer, q.expected_answer)
            return EvalResult(
                question_id=q.id,
                question=q.question,
                latency_ms=round(latency_ms, 1),
                confidence=body.get("confidence"),
                citations=body.get("citations", []),
                answer_snippet=raw_answer[:120],
                answer_correct=answer_correct,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[{q.id}] Query failed: {exc}")
            time.sleep(backoff)
            backoff *= 2

    latency_ms = (time.perf_counter() - t0) * 1000
    return EvalResult(
        question_id=q.id,
        question=q.question,
        latency_ms=round(latency_ms, 1),
        confidence=None,
        citations=[],
        answer_snippet="",
        error=f"Failed after {retries} retries",
    )
