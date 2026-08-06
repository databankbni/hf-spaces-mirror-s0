"""분기형 재난대응 시뮬레이션 엔진 (sim 모드) — '재난안전상황실' 상태머신.

자유도의 정체: 시나리오는 고정 대본이 아니라 **이벤트 그래프**다.
  · 각 이벤트는 trigger(발생 조건: 플래그·수위·상태·시각)를 가진다.
  · 선택은 상태·플래그를 바꾸고, 그 결과 **어떤 이벤트가 다음에 트리거되는지가 달라진다**.
    예) 지하차도를 통제 안 하면 flag(ignored_underpass) → '차량 고립 구조' 이벤트가 새로 발생.
        수위를 못 잡으면 water가 높아져 '반지하 침수' 이벤트가 터진다(잘하면 안 터짐).
  → 잘한 사람과 못한 사람이 다른 상황을 겪고, 다시 하면 다른 길이 나온다(자유도·리플레이성).

  · 매 결정마다 가장 우선순위 높은 '트리거된' 이벤트가 현재 상황이 된다.
  · 서버 무상태 — 프런트가 '결정 id 목록'을 보내면 처음부터 결정론 리플레이.
  · 채점 = 절차(이벤트별 표준조치) 50% + 결과(최종 피해) 50%.
"""
from __future__ import annotations

from . import catalog, core, region, ttx

RUBRIC_POINTS = {"correct": 100, "partial": 50, "wrong": 0}
MONITOR_KEYS = ["대피완료율", "통제율", "인명피해", "주민혼란", "재산피해", "구조"]
_MAX_STEPS = 24  # 무한루프 방지(분기 깊이 상한)


def _scenario(disaster_id: str, profile: dict | None) -> dict:
    d = region.localize(catalog.get(disaster_id), profile)
    if d.get("mode") != "sim":
        raise ValueError(f"{disaster_id}는 sim 모드가 아님")
    return d


def _fmt(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _danger(sim: dict, water: int) -> dict:
    for lv in sim["danger_levels"]:
        if water <= lv["max"]:
            return {"label": lv["label"], "color": lv["color"]}
    last = sim["danger_levels"][-1]
    return {"label": last["label"], "color": last["color"]}


def _monitor(state: dict) -> dict:
    return {k: state.get(k, 0) for k in MONITOR_KEYS}


def _cond_ok(cond: dict, state: dict, flags: set, water: int, clock: int) -> bool:
    if "flag" in cond and cond["flag"] not in flags:
        return False
    if "not_flag" in cond and cond["not_flag"] in flags:
        return False
    if "water_gte" in cond and not water >= cond["water_gte"]:
        return False
    if "clock_gte" in cond and not clock >= cond["clock_gte"]:
        return False
    for k, v in cond.get("state_gte", {}).items():
        if not state.get(k, 0) >= v:
            return False
    for k, v in cond.get("state_lt", {}).items():
        if not state.get(k, 0) < v:
            return False
    return True


def _triggered(ev: dict, state: dict, flags: set, water: int, clock: int) -> bool:
    tr = ev.get("trigger", {})
    if tr.get("always"):
        return True
    return all(_cond_ok(c, state, flags, water, clock) for c in tr.get("all", []))


def _variant(sim: dict, variant: int) -> tuple[int, dict]:
    """접속마다 다른 시나리오를 무작위 선택(variant). 결정론 유지(variant 고정 시 동일)."""
    vs = sim["variants"]
    idx = variant % len(vs)
    return idx, vs[idx]


def replay(disaster_id: str, choices: list[str], profile: dict | None = None, variant: int = 0) -> dict:
    """choices = 마주친 이벤트(분기 경로)에서 고른 옵션 id 목록. 결정론 리플레이.

    variant = 시나리오 변형(접속마다 무작위). 같은 (variant, choices)면 같은 경로·점수(테스트로 고정).
    """
    d = _scenario(disaster_id, profile)
    sim = d["sim"]
    vidx, v = _variant(sim, variant)
    events = v["events"]
    idx_of = {e["id"]: i for i, e in enumerate(events)}
    start = sim.get("clock_start_min", 180)
    per = sim.get("min_per_decision", 8)
    rise = sim.get("rise_per_decision", 12)

    water = v["water"]["start"]
    state = dict(sim["state0"])
    flags: set[str] = set()
    fired: set[str] = set()
    feed: list[dict] = []
    reviews: list[dict] = []
    clock = start
    current = None

    step = 0
    while step < _MAX_STEPS:
        cands = [e for e in events if e["id"] not in fired
                 and _triggered(e, state, flags, water, clock)]
        if not cands:
            break  # 더 트리거되는 상황 없음 → 상황 종료
        ev = max(cands, key=lambda e: (e.get("priority", 0), -idx_of[e["id"]]))
        feed.append({"clock": _fmt(clock), "text": ev["report"], "kind": "alert"})

        if step >= len(choices):  # 아직 결정 안 한 현재 상황
            current = {
                "idx": step, "clock": _fmt(clock),
                "water": water, "danger": _danger(sim, water),
                "deadline": _fmt(clock + ev.get("golden_min", 15)), "golden_min": ev.get("golden_min", 15),
                "monitor": _monitor(state), "feed": list(feed),
                "focal": {"id": ev["id"], "label": ev["label"], "inject": ev["inject"],
                          "options": [{"id": o["id"], "text": o["text"]} for o in ev["options"]]},
            }
            break

        cid = choices[step]
        opt = next((o for o in ev["options"] if o["id"] == cid), None)
        if opt is None:
            raise KeyError(f"{disaster_id}/{ev['id']}: 옵션 {cid} 없음")

        fired.add(ev["id"])
        state = core._apply(state, opt.get("effects", {}))
        water = max(0, water + opt.get("water_delta", 0))
        for f in opt.get("set_flags", []):
            flags.add(f)
        feed.append({"clock": _fmt(clock), "text": "▶ 결정: " + opt["text"], "kind": "decision"})
        if opt.get("feed"):
            feed.append({"clock": _fmt(clock), "text": opt["feed"], "kind": "radio"})

        std = next((o["text"] for o in ev["options"] if o["rubric"] == "correct"), "")
        reviews.append({"id": ev["id"], "label": ev["label"], "rubric": opt["rubric"],
                        "standard": std, "on_time": opt["rubric"] == "correct",
                        "escalated": opt["rubric"] == "wrong", "why": opt.get("why", "")})

        clock += per
        water = max(0, water + rise)
        step += 1

    finished = current is None
    pts = [RUBRIC_POINTS[r["rubric"]] for r in reviews]
    decision_score = round(sum(pts) / len(pts)) if pts else 0
    outcome_score = core._outcome_score(state)
    total = round(0.5 * decision_score + 0.5 * outcome_score) if finished else 0

    # 조합형 상황: 이벤트 그래프(채점)는 base 그대로, intro에만 강도·부가상황을 얹어 다양화.
    # ⚠시간은 시나리오 고유값(변형이 소유) — 무작위 시간을 얹지 않는다(본문과 모순 방지, TTX와 동일 원칙).
    comp = ttx._compose(variant, len(sim["variants"]))
    (sv_label, sv_note), (cx_label, cx_note) = comp["sev"], comp["ctx"]
    t_label = v.get("time_label", "")
    t_note = v.get("time_note", "")
    sit_pre = f"🕓 {t_label} · {sv_label}. {t_note} {sv_note}".strip() + (f" ⚠ {cx_note}" if cx_note else "")
    sit_label = f"{v.get('label', '')} · {sv_label}" + (f" · {cx_label}" if cx_label else "")

    return {
        "disaster": {"id": d["id"], "name": d["name"], "icon": d.get("icon", "⚠"),
                     "mode": "sim", "context": d.get("context", ""),
                     "source_manuals": d.get("source_manuals", [])},
        "intro": sit_pre + "\n\n" + v.get("intro", ""), "variant": variant, "variant_label": sit_label,
        "feed": feed,
        "state": state, "water": water, "danger": _danger(sim, water), "monitor": _monitor(state),
        "threats_review": reviews,
        "decision_score": decision_score,
        "outcome_score": outcome_score,
        "total": total,
        "grade": core.grade_of(total) if finished else None,
        "finished": finished,
        "current": current,
    }


def start(disaster_id: str, profile: dict | None = None, variant: int = 0) -> dict:
    """상황실 초기 상태 + 첫 상황. variant로 시나리오 변형을 무작위 선택."""
    d = _scenario(disaster_id, profile)
    r = replay(disaster_id, [], profile, variant)
    return {
        "id": d["id"], "name": d["name"], "icon": d.get("icon", "⚠"), "mode": "sim",
        "context": d.get("context", ""), "summary": d.get("summary", ""),
        "source_manuals": d.get("source_manuals", []),
        "data_sources": d.get("data_sources", []),
        "intro": r.get("intro", ""), "variant": r.get("variant", 0),
        "variant_label": r.get("variant_label", ""),
        "total_variants": len(d["sim"]["variants"]) * len(ttx._SEVERITY) * len(ttx._CONTEXT),
        "current": r["current"],
    }
