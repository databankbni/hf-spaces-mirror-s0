"""AI 평가관 — 훈련 결과를 표준행동요령에 비춰 강평(debrief). Claude + 규칙 폴백.

공모 부제 '최고의 재난안전 AI 프롬프트'의 본체. 두 원칙:
- 점수·정답 판정은 '엔진'이 한다(결정론). LLM은 그 판정을 근거로 코칭 문장만 만든다(날조 금지).
- 키 없거나 실패 시 규칙 폴백 → 데모는 0원으로도 항상 동작.
"""
from __future__ import annotations

import os
from pathlib import Path

MODEL = "claude-haiku-4-5-20251001"

DEBRIEF_TOOL = {
    "name": "emit_debrief",
    "description": "재난대응 도상훈련 결과를 표준행동요령에 비춰 강평한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "description": "한 줄 총평(등급 근거, 차분·실무적)"},
            "did_well": {"type": "array", "items": {"type": "string"}, "description": "잘한 결정 1~3개"},
            "missed": {"type": "array", "items": {"type": "string"}, "description": "놓친·틀린 결정과 그 여파 1~3개"},
            "coach": {"type": "string", "description": "다음 훈련을 위한 핵심 한 수(표준행동요령 인용)"},
        },
        "required": ["verdict", "did_well", "missed", "coach"],
    },
}

SYSTEM = """\
당신은 재난대응 도상훈련(TTX)의 AI 평가관이다. 다음을 반드시 지켜라.
- 점수·정답 판정은 이미 엔진이 끝냈다. 너는 그 판정(각 결정의 correct/partial/wrong과 근거)을
  바탕으로 '강평'만 한다. 점수를 바꾸거나 새 사실을 지어내지 않는다.
- 제공된 표준행동요령(매뉴얼명)과 결정 근거 안에서만 코칭한다. 없는 규정을 인용하지 않는다.
- 과장·질책 없이 차분하고 구체적으로. 한국어. 실제 재난담당공무원이 다음에 더 잘하도록.
"""


def _anthropic_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import tomllib
        for cand in (Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml",
                     Path(__file__).resolve().parents[2] / "jikigo" / ".streamlit" / "secrets.toml"):
            if cand.exists():
                k = tomllib.loads(cand.read_text(encoding="utf-8")).get("ANTHROPIC_API_KEY")
                if k:
                    return k
    except Exception:  # noqa: BLE001
        pass
    return None


def has_key() -> bool:
    return bool(_anthropic_key())


def _fallback(result: dict) -> dict:
    """규칙 폴백 — 엔진 판정을 그대로 문장화."""
    did, missed = [], []
    for t in result["timeline"]:
        c = t["chosen"]
        line = f"[{t['clock']}] {c['text']} — {c['why']}"
        (did if c["rubric"] == "correct" else missed).append(line)
    g = result.get("grade") or "진행 중"
    verdict = (f"총점 {result['total']}점({g}). 의사결정 {result['decision_score']} · "
               f"피해최소화 {result['outcome_score']}. 인명피해 지수 {result['state'].get('인명피해', 0)}.")
    coach = ("핵심은 골든타임 내 '인명 우선 선제 통제'입니다. 지켜보기·일괄소집 같은 소극 대응은 "
             "이미 침수가 시작된 뒤를 의미합니다." if missed else
             "전 단계에서 인명 우선 원칙과 우선순위를 정확히 지켰습니다.")
    return {"verdict": verdict, "did_well": did[:3], "missed": missed[:3], "coach": coach}


def debrief(result: dict, use_llm: bool = True) -> tuple[dict, str]:
    """(강평 dict, 엔진라벨). 라벨='claude:<model>' 또는 'fallback(rule)'."""
    if use_llm and has_key():
        try:
            return _with_claude(result), f"claude:{MODEL}"
        except Exception:  # noqa: BLE001
            pass
    return _fallback(result), "fallback(rule)"


def _sim_payload(result: dict) -> dict:
    return {
        "disaster": result["disaster"]["name"],
        "context": result["disaster"].get("context", ""),
        "source_manuals": result["disaster"].get("source_manuals", []),
        "scores": {"total": result["total"], "grade": result.get("grade"),
                   "decision": result["decision_score"], "outcome": result["outcome_score"]},
        "final_state": result["state"],
        "threats": [{"위협": t["label"], "판정": t["rubric"], "표준조치": t["standard"],
                     "적시여부": t["on_time"], "악화": t["escalated"]}
                    for t in result["threats_review"]],
    }


def _sim_fallback(result: dict) -> dict:
    did, missed = [], []
    for t in result["threats_review"]:
        if t["rubric"] == "correct":
            did.append(f"{t['label']} — 골든타임 내 표준조치({t['standard']})로 해결")
        elif t["rubric"] == "partial":
            missed.append(f"{t['label']} — 해결했으나 골든타임 경과(지연 대응)")
        else:
            missed.append(f"{t['label']} — 미해결로 악화. 표준조치는 '{t['standard']}'")
    g = result.get("grade") or "진행 중"
    verdict = (f"총점 {result['total']}점({g}). 의사결정 {result['decision_score']} · "
               f"피해최소화 {result['outcome_score']}. 인명피해 지수 {result['state'].get('인명피해', 0)}.")
    coach = ("핵심은 한정 인력을 '골든타임이 임박한 인명 위협' 순으로 배분하는 것입니다. "
             "수위·정전 복구 같은 자산 보호보다 지하·반지하·고립 등 인명 노출이 큰 위협이 항상 먼저입니다."
             if missed else
             "한정 인력으로 모든 위협을 골든타임 내 우선순위대로 처리했습니다. 표준 지휘 그대로입니다.")
    return {"verdict": verdict, "did_well": did[:4], "missed": missed[:4], "coach": coach}


def debrief_sim(result: dict, use_llm: bool = True) -> tuple[dict, str]:
    """sim(상태머신) 결과 강평. 점수·판정은 엔진 결정, LLM은 문장만."""
    if use_llm and has_key():
        try:
            return _with_claude(result, payload=_sim_payload(result)), f"claude:{MODEL}"
        except Exception:  # noqa: BLE001
            pass
    return _sim_fallback(result), "fallback(rule)"


def _with_claude(result: dict, payload: dict | None = None) -> dict:
    import json

    import anthropic

    if payload is None:
        payload = {
            "disaster": result["disaster"]["name"],
            "context": result["disaster"].get("context", ""),
            "source_manuals": result["disaster"].get("source_manuals", []),
            "scores": {"total": result["total"], "grade": result.get("grade"),
                       "decision": result["decision_score"], "outcome": result["outcome_score"]},
            "final_state": result["state"],
            "decisions": [{"clock": t["clock"], "chosen": t["chosen"]["text"],
                           "rubric": t["chosen"]["rubric"], "why": t["chosen"]["why"]}
                          for t in result["timeline"]],
        }
    client = anthropic.Anthropic(api_key=_anthropic_key())
    resp = client.messages.create(
        model=MODEL, max_tokens=900, system=SYSTEM,
        tools=[DEBRIEF_TOOL], tool_choice={"type": "tool", "name": "emit_debrief"},
        messages=[{"role": "user", "content":
                   "아래 훈련 결과(JSON)를 강평하라. 판정·점수는 그대로 두고 코칭만 한다.\n"
                   + json.dumps(payload, ensure_ascii=False)}],
    )
    block = next(b for b in resp.content if b.type == "tool_use")
    return dict(block.input)
