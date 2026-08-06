"""국민 모드 — 개인 시민 1인칭 생존 대응 체험.

기관 모드(시뮬·TTX)가 '재난대책본부 지휘'라면, 국민 모드는 '내 목숨을 지키는 결정'이다.
선택지 정답(verdict)은 행정안전부 국민행동요령에 근거하며, 채점은 결정론적 순수 로직(LLM 아님).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from engine import hazards, region

_HERE = Path(__file__).resolve().parent
_V = {"correct": 1.0, "partial": 0.5, "wrong": 0.0}
# 생존 위험 게이지(0=안전~100=치명) 변화량 — 옳은 선택은 낮추고, 위험한 선택은 급상승.
_DANGER = {"correct": -12, "partial": 14, "wrong": 34}
_START_DANGER = 22


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads((_HERE.parent / "data" / "citizen.json").read_text(encoding="utf-8"))


def available() -> list[str]:
    return [k for k in _data() if not k.startswith("_")]


def _variants(disaster: str) -> list:
    d = _data().get(disaster) or {}
    return d.get("variants") or []


def _clamp(x):
    return max(0, min(100, x))


def start(disaster: str, profile: dict | None, seed: int = 0) -> dict | None:
    """1인칭 시나리오(지역화). variants 중 seed로 하나 선택. verdict/fb 포함(즉시 피드백용)."""
    d = _data().get(disaster)
    vs = _variants(disaster)
    if not d or not vs:
        return None
    vi = seed % len(vs)
    v = vs[vi]

    def loc(t):
        return region.localize_text(t, profile)

    steps = [{"sit": loc(s["sit"]),
              "options": [{"t": loc(o["t"]), "v": o["v"], "fb": loc(o["fb"])} for o in s["options"]]}
             for s in v["steps"]]
    return {"disaster": disaster, "name": d["name"], "icon": d["icon"],
            "variant": vi, "variant_total": len(vs),
            "intro": loc(v["intro"]), "steps": steps,
            "start_danger": _START_DANGER, "danger_delta": _DANGER,
            "reality": hazards.reality_note(profile, disaster)}


def evaluate(disaster: str, choices: list, profile: dict | None, variant: int = 0) -> dict:
    """선택 → 국민행동요령 기준 결정론 채점 + 생존 위험 게이지 + 단계별 강평 + 실제 대응법."""
    d = _data().get(disaster)
    vs = _variants(disaster)
    if not d or not vs:
        return {"error": "unknown"}
    v = vs[variant % len(vs)]

    def loc(t):
        return region.localize_text(t, profile)

    steps = v["steps"]
    results, total, danger = [], 0.0, _START_DANGER
    for i, s in enumerate(steps):
        opts = s["options"]
        ci = choices[i] if (i < len(choices) and isinstance(choices[i], int) and 0 <= choices[i] < len(opts)) else -1
        chosen = opts[ci] if ci >= 0 else None
        vd = chosen["v"] if chosen else "wrong"
        total += _V.get(vd, 0.0)
        danger = _clamp(danger + _DANGER.get(vd, 34))
        correct = next((o for o in opts if o["v"] == "correct"), opts[0])
        results.append({"sit": loc(s["sit"]),
                        "chosen": loc(chosen["t"]) if chosen else "(무응답)",
                        "verdict": vd, "fb": loc(chosen["fb"]) if chosen else "",
                        "correct": loc(correct["t"]), "danger": danger})
    n = len(steps) or 1
    score = round(total / n * 100)
    grade = "A" if score >= 90 else "B" if score >= 70 else "C" if score >= 40 else "D"
    verdict = {
        "A": "훌륭합니다 — 국민행동요령대로 정확히 대응했습니다.",
        "B": "양호합니다 — 대체로 옳았으나 일부 아쉬운 선택이 있었습니다.",
        "C": "보완이 필요합니다 — 위험한 선택이 있었습니다. 행동요령을 익히세요.",
        "D": "위험합니다 — 실제였다면 큰 피해로 이어질 선택이었습니다. 꼭 복습하세요.",
    }[grade]
    outcome = ("생존", "안전하게 위기를 넘겼습니다.") if danger < 30 else \
              ("부상 위험", "가까스로 벗어났지만 위험했습니다.") if danger <= 60 else \
              ("사망 위기", "실제였다면 생존을 장담하기 어려운 상황이었습니다.")
    return {"disaster": disaster, "name": d["name"], "variant": variant % len(vs),
            "score": score, "grade": grade, "verdict": verdict,
            "final_danger": danger, "outcome": outcome[0], "outcome_desc": outcome[1],
            "results": results, "guideline": region.guideline(d.get("guideline") or disaster)}
