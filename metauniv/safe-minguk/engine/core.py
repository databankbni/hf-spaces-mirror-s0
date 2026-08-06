"""훈련 세션 코어 — 결정론 리플레이 + 채점. 순수 로직 → 단위테스트로 고정.

설계: 서버는 상태를 들고 있지 않는다. 프런트가 '선택한 옵션 id 목록'을 보내면
엔진이 처음부터 다시 재생(replay)해 현재 상태·점수·피드백을 돌려준다.
→ 멱등·재현 가능·테스트 쉬움(같은 입력=같은 결과).

채점 = 절차(의사결정 품질) 50% + 결과(최종 피해 상태) 50%.
도상훈련 평가가 '표준행동요령 준수'와 '피해 최소화'를 함께 보는 것을 반영.
"""
from __future__ import annotations

from . import catalog, region

RUBRIC_POINTS = {"correct": 100, "partial": 50, "wrong": 0}
# 상태변수 방향: True=높을수록 좋음, False=낮을수록 좋음
HIGHER_BETTER = {"대피완료율": True, "통제율": True,
                 "인명피해": False, "재산피해": False, "주민혼란": False}
CLAMP_0_100 = {"대피완료율", "통제율"}


def _apply(state: dict, effects: dict) -> dict:
    s = dict(state)
    for k, dv in effects.items():
        s[k] = s.get(k, 0) + dv
        if k in CLAMP_0_100:
            s[k] = max(0, min(100, s[k]))
        elif k != "골든타임_잔여분":
            s[k] = max(0, s[k])
    return s


def _outcome_score(state: dict) -> int:
    """최종 상태 → 0~100. 인명피해를 가장 무겁게 본다."""
    penalty = state.get("인명피해", 0) * 2.0 + state.get("재산피해", 0) * 0.6 \
        + state.get("주민혼란", 0) * 0.4
    return max(0, min(100, round(100 - penalty)))


def grade_of(score: int) -> str:
    return ("A · 우수" if score >= 85 else "B · 양호" if score >= 70
            else "C · 보통" if score >= 55 else "D · 대응 미흡")


def replay(disaster_id: str, choices: list[str], profile: dict | None = None) -> dict:
    """choices = 각 phase에서 고른 option id 목록(순서=phase 순서).

    profile = 지역 프로파일(region.resolve 결과). 주면 시나리오 텍스트가 지역화된다
    (채점은 텍스트와 무관하므로 점수·불변식은 동일 — 테스트로 고정).

    반환: {disaster, timeline[], state, decision_score, outcome_score,
           total, grade, finished, next_phase}
    """
    d = region.localize(catalog.get(disaster_id), profile)
    phases = d["phases"]
    state = dict(d.get("state", {}))
    timeline, dec_points = [], []

    for i, ch in enumerate(choices):
        if i >= len(phases):
            break
        ph = phases[i]
        op = next((o for o in ph["options"] if o["id"] == ch), None)
        if op is None:
            raise KeyError(f"{disaster_id}/{ph['id']}: 옵션 {ch} 없음")
        before = state
        state = _apply(state, op.get("effects", {}))
        dec_points.append(RUBRIC_POINTS[op["rubric"]])
        timeline.append({
            "phase_id": ph["id"], "clock": ph.get("clock", ""),
            "inject": ph["inject"], "question": ph["question"],
            "chosen": {"id": op["id"], "text": op["text"], "rubric": op["rubric"], "why": op["why"]},
            "state_after": state, "state_before": before,
        })

    finished = len(choices) >= len(phases)
    next_phase = None if finished else _phase_public(phases[len(choices)])
    decision_score = round(sum(dec_points) / len(dec_points)) if dec_points else 0
    outcome_score = _outcome_score(state)
    total = round(0.5 * decision_score + 0.5 * outcome_score) if dec_points else 0

    return {
        "disaster": {"id": d["id"], "name": d["name"], "icon": d.get("icon", "⚠"),
                     "context": d.get("context", ""), "depth": d["depth"],
                     "source_manuals": d.get("source_manuals", []),
                     "consequence": d.get("consequence", "rule_state")},
        "total_phases": len(phases),
        "timeline": timeline,
        "state": state,
        "decision_score": decision_score,
        "outcome_score": outcome_score,
        "total": total,
        "grade": grade_of(total) if finished else None,
        "finished": finished,
        "next_phase": next_phase,
    }


def _phase_public(ph: dict) -> dict:
    """훈련생에게 보여줄 phase(정답 rubric·effects 숨김 — 커닝 방지)."""
    return {
        "id": ph["id"], "clock": ph.get("clock", ""),
        "inject": ph["inject"], "question": ph["question"],
        "golden_time_min": ph.get("golden_time_min"),
        "options": [{"id": o["id"], "text": o["text"]} for o in ph["options"]],
    }


def first_phase(disaster_id: str, profile: dict | None = None) -> dict:
    d = region.localize(catalog.get(disaster_id), profile)
    return _phase_public(d["phases"][0])
