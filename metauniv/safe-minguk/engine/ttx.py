"""도상훈련(TTX) 엔진 — 을지연습·안전한국훈련 방식의 '서술형' 대응 평가.

상황실 시뮬(객관식·실시간)과 다른 파트:
  · 상황을 부여하고(inject), 참가자가 대응조치를 **자유서술**로 작성한다(실제 도상훈련 방식).
  · AI 평가관이 행안부 표준매뉴얼의 '표준 대응요소(elements)'와 대조해 각 요소의 반영도를 판정한다.
  · 점수는 엔진이 계산한다(요소 weight × 반영도). LLM은 '판정·강평'만(날조 금지). 키 없으면 키워드 폴백.

데이터: data/ttx_<disaster>.json (상황부여 단계 + 단계별 평가요소·모범답안).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import core, eval_map, hazards, llm, region, safety_data

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_LEVEL_VAL = {"full": 1.0, "partial": 0.5, "none": 0.0}


@lru_cache(maxsize=8)
def _load(disaster_id: str) -> dict:
    p = DATA_DIR / f"ttx_{disaster_id}.json"
    if not p.exists():
        raise KeyError(f"도상훈련 시나리오 없음: {disaster_id}")
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _examples_all() -> dict:
    p = DATA_DIR / "ttx_examples.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _examples(disaster_id: str, variant: int, stage: int) -> list:
    return _examples_all().get(disaster_id, {}).get(str(variant), {}).get(str(stage), [])


def available(disaster_id: str) -> bool:
    return (DATA_DIR / f"ttx_{disaster_id}.json").exists()


# ── 돌발 불시메시지(2-1-4) ───────────────────────────────────────
@lru_cache(maxsize=1)
def _surprise_pool() -> list[dict]:
    p = DATA_DIR / "ttx_surprise.json"
    return json.loads(p.read_text(encoding="utf-8")).get("pool", []) if p.exists() else []


def _pick_surprise(seed: int) -> dict | None:
    pool = _surprise_pool()
    return pool[seed % len(pool)] if pool else None


def surprise(disaster_id: str, profile: dict | None = None, seed: int = 0) -> dict | None:
    """훈련 중 부여할 돌발 불시메시지(공개 정보만). 평가요소는 숨긴다. seed로 순환 선택."""
    s = _pick_surprise(seed)
    if not s:
        return None
    prof = profile or region.resolve(None)
    real = hazards.scenario_tokens(prof)
    if real:
        prof = {**prof, "tokens": {**prof.get("tokens", {}), **real}}
    L = lambda t: region.localize_text(t, prof)  # noqa: E731
    return {"id": s["id"], "title": s["title"], "icon": s.get("icon", "⚡"),
            "inject": L(s["inject"]), "task": s["task"], "seed": seed,
            "total": len(_surprise_pool())}


def surprise_eval(disaster_id: str, answer: str, profile: dict | None = None,
                  use_llm: bool = True, seed: int = 0, role: str | None = None) -> dict:
    """돌발 불시메시지 답안을 평가(2-1-4 중심). 채점 코어·공식 지표 대조를 본 훈련과 동일하게 적용."""
    s = _pick_surprise(seed)
    if not s:
        return {"score": 0, "elements": [], "indicators": [], "grade5": eval_map.grade5(0)}
    prof = profile or region.resolve(None)
    real = hazards.scenario_tokens(prof)
    if real:
        prof = {**prof, "tokens": {**prof.get("tokens", {}), **real}}
    L = lambda t: region.localize_text(t, prof)  # noqa: E731
    elements = s["elements"]

    coverage = detail = strengths = missed = coach = engine = None
    if use_llm and answer.strip() and llm.has_key():
        try:
            st = {"inject": L(s["inject"]), "task": s["task"], "elements": elements}
            coverage, detail, strengths, missed, coach = _with_claude(st, answer, L)
            engine = f"claude:{llm.MODEL}"
        except Exception:  # noqa: BLE001
            coverage = None
    if coverage is None:
        coverage, detail = _fallback_coverage(elements, answer)
        engine = "fallback(keyword)"

    score = _score_from_coverage(elements, coverage)
    bykey = {d["key"]: d for d in detail}
    elem_out = []
    for e in elements:
        level = coverage.get(e["key"], "none")
        d = bykey.get(e["key"], {})
        ma = d.get("missing_action") or (L(e.get("missing_action", "")) if level != "full" else "")
        rec = d.get("recommendation") or (L(e.get("recommendation", "")) if level != "full" else "현 수준 유지")
        elem_out.append({"key": e["key"], "desc": L(e["desc"]), "근거": e.get("근거", ""),
                         "weight": e["weight"], "level": level, "reason": d.get("reason", ""),
                         "missing_action": ma, "recommendation": rec,
                         "indicator": eval_map.indicator_of(e["key"])})
    if strengths is None:
        strengths = [L(e["desc"]) for e in elements if coverage.get(e["key"]) == "full"]
        missed = [L(e["desc"]) for e in elements if coverage.get(e["key"]) in (None, "none", "partial")]
        covered_n = sum(1 for e in elements if coverage.get(e["key"]) == "full")
        coach = (f"돌발상황 대응요소 {len(elements)}개 중 {covered_n}개를 반영했습니다. "
                 "불시 상황일수록 인명·우선순위 판단을 먼저 정리하는 연습을 권합니다."
                 if covered_n < len(elements) else "돌발상황에도 침착하게 우선순위대로 대응했습니다.")
    r = _role(role)
    return {
        "surprise": True, "title": s["title"], "icon": s.get("icon", "⚡"),
        "score": score, "grade": core.grade_of(score), "grade5": eval_map.grade5(score), "max": 100,
        "elements": elem_out, "strengths": strengths[:5], "missed": missed[:5],
        "coach": coach, "model_answer": L(s.get("model_answer", "")), "engine": engine,
        "role_note": {"label": r["label"], "focus": r["focus"]},
        "indicators": eval_map.build(elem_out),
    }


def _variants(s: dict) -> list[dict]:
    """변형 목록. 구버전(stages 직접)도 단일 변형으로 감싼다."""
    if "variants" in s:
        return s["variants"]
    return [{"label": "기본", "stages": s["stages"]}]


def _pick(s: dict, variant: int) -> tuple[int, dict]:
    vs = _variants(s)
    idx = variant % len(vs)
    return idx, vs[idx]


# ── 조합형 상황 컴포저 ────────────────────────────────────────
# ⚠ 시간대는 조합하지 않는다. 각 기본 시나리오는 '자기 고유 시각'을 갖는다(V0=새벽·V1=만조저녁·
# V3=점심 다중이용·V4=야간). 예전엔 무작위 시간을 덧씌워 '새벽 03:40인데 본문은 점심시간' 같은
# 모순이 났다 → 시간은 시나리오 소유, 조합기는 강도(severity)·부가상황(context)만 얹는다(둘 다 시각과
# 무관한 additive 요소). 표준 대응요소(채점)는 그대로 → 상황만 다양해지고 채점 불변(테스트 고정).
# 강도 = '기상 배경'(특보 단계)만 바꾼다. 본문의 국지 상황(급속침수·고립 등)과 충돌하지 않도록,
# 초기/후기 같은 '진행 단계'가 아니라 어느 국면에도 얹히는 기상특보 수준으로 서술한다.
_SEVERITY = [
    ("호우주의보 발효", "현재 호우주의보가 발효 중입니다. 추가 악화 가능성을 염두에 두고 판단하십시오."),
    ("호우경보 격상", "호우경보로 격상돼 비상단계 상향과 자원 추가 투입 판단이 필요합니다."),
    ("태풍특보 동반", "태풍특보가 겹쳐 강풍·2차 위험까지 함께 관리해야 하는 복합 상황입니다."),
]
# 부가상황은 어느 시나리오·어느 시각에도 모순 없이 얹히는 운영상 복잡성만(정전 등 시나리오 고유요소는 제외).
_CONTEXT = [
    ("", ""),
    ("유관기관 회선 폭주", "119·유관기관 통신이 몰려 상황전파 우선순위 판단이 필요합니다."),
    ("인접 시군 동시 상황", "인접 시군에서도 동시다발 신고가 접수돼 자원·공조 조정이 필요합니다."),
    ("담당 인력 절반 비번", "가용 인력이 절반이라 조치 우선순위와 인력 배분이 특히 중요합니다."),
]


def _compose(variant: int, base_n: int) -> dict:
    """variant → (기본변형, 강도, 부가상황) 조합. 시간은 시나리오 고유값이라 조합하지 않는다."""
    b = variant % base_n
    sv = (variant // base_n) % len(_SEVERITY)
    cx = (variant // (base_n * len(_SEVERITY))) % len(_CONTEXT)
    return {"base": b, "sev": _SEVERITY[sv], "ctx": _CONTEXT[cx]}


def total_situations(disaster_id: str) -> int:
    base_n = len(_variants(_load(disaster_id)))
    return base_n * len(_SEVERITY) * len(_CONTEXT)


# P2 · 상황판단회의(안전한국훈련 평가지표 2-1-2) — 재난대책본부가 상황부여 후 대응방침을
# 토의·결정하는 표준 단계. 상황부여 → [상황판단회의 안건 판단] → 대응조치 작성 흐름을 만든다.
# 안건 5종은 재난 표준행동매뉴얼 '상황판단회의 운영'의 실제 판단 항목(지어내지 않음).
_MEETING_AGENDA = [
    "현 상황·피해 규모 평가 — 어디까지, 얼마나 위험한가",
    "대응 목표와 우선순위 결정 — 인명 보호 최우선",
    "가용 자원·즉시 조치 확인 — 인력·장비·배수펌프·대피소",
    "유관기관 협조 사항 — 소방·경찰·한전·군 등 공동대응",
    "주민 전파·대피 방침 — 재난문자·마을방송·통반장 가가호호",
]


# P4 · 다역할(안전한국훈련 평가지표 2-3) — 도상훈련은 지휘책임자·통제관·부서가 함께 참여한다.
# 참가자가 역할을 선택하면 책무(duty)와 중점(focus)이 바뀐다. 채점 요소는 불변(모든 표준요소 평가) —
# 역할은 '관점·중점'을 주는 자문 정보이며 점수를 바꾸지 않는다(정직: 요소 가중치 조작 없음).
_ROLES = [
    {"key": "commander", "label": "지휘책임자(본부장)",
     "duty": "재난안전대책본부를 총괄 지휘하고 비상단계 상향·대외 발표를 결정한다.",
     "focus": "대책본부 가동과 대응 우선순위 결정을 가장 먼저 챙기세요."},
    {"key": "controller", "label": "통제관(상황실장)",
     "duty": "상황 전파·유관기관 협조·동원자원 통제를 총괄한다.",
     "focus": "재난문자·유관기관 공동대응 등 상황 전파를 우선하세요."},
    {"key": "ops", "label": "상황총괄반",
     "duty": "상황 판단·기록·보고와 부서 간 조정을 맡는다.",
     "focus": "상황판단회의 안건을 빠짐없이 기록·보고하세요."},
    {"key": "field", "label": "현장대응반",
     "duty": "통제·대피·구조 등 현장 조치를 직접 수행한다.",
     "focus": "지하차도 통제·취약계층 대피 등 현장 인명보호를 우선하세요."},
]
_DEFAULT_ROLE = "ops"


def _role(role_key: str | None) -> dict:
    for r in _ROLES:
        if r["key"] == (role_key or _DEFAULT_ROLE):
            return r
    return next(r for r in _ROLES if r["key"] == _DEFAULT_ROLE)


def _meeting(stage_title: str) -> dict:
    """상황부여 단계마다 소집되는 상황판단회의 안건(표준 5항목). 첫 항목만 현 단계로 앵커."""
    anchor = (stage_title or "").split("  ")[-1].strip() or "현 국면"
    agenda = [f"현 상황·피해 규모 평가 — {anchor} 국면에서 어디까지 위험한가"] + _MEETING_AGENDA[1:]
    return {
        "title": "상황판단회의",
        "intro": "재난안전대책본부 상황판단회의를 소집합니다. 아래 안건을 판단한 뒤, 그 결정에 따른 대응조치를 작성하십시오.",
        "agenda": agenda,
        "basis": "안전한국훈련 평가지표 2-1-2 · 재난 표준행동매뉴얼 「상황판단회의 운영」",
    }


def start(disaster_id: str, profile: dict | None = None, variant: int = 0,
          role: str | None = None) -> dict:
    """상황부여 단계(공개 정보만) — 평가요소·모범답안은 숨긴다.

    variant로 (기본변형 × 시간대 × 강도 × 부가상황)을 조합해 매번 다른 상황을 부여한다.
    표준 대응요소·채점은 기본변형 그대로 → 상황만 다양해지고 채점 불변(테스트 고정).
    role(P4·2-3)은 참가자 역할(책무·중점)을 정한다 — 관점만 바뀌고 채점은 불변.
    """
    s = _load(disaster_id)
    base_n = len(_variants(s))
    comp = _compose(variant, base_n)
    idx, v = comp["base"], _variants(s)[comp["base"]]

    # P1 · 시나리오 충실성(평가지표 1-1-4): 일반 토큰({underpass}/{river}/{lowland})을 그 시군구의
    # 실제 인명피해우려 지점명으로 치환. 실지점 없으면 일반명 폴백(지어내지 않음). 큐레이션은 보존.
    prof = profile or region.resolve(None)
    real = hazards.scenario_tokens(prof)
    if real:
        prof = {**prof, "tokens": {**prof.get("tokens", {}), **real}}
    L = lambda t: region.localize_text(t, prof)  # noqa: E731

    (sv_label, sv_note), (cx_label, cx_note) = comp["sev"], comp["ctx"]
    t_label = v.get("time_label", "")   # 시각은 시나리오 고유값(무작위 아님) — 본문과 모순 없음
    t_note = v.get("time_note", "")
    preamble = f"🕓 {t_label} · {sv_label}. {t_note} {sv_note}".strip()
    if cx_note:
        preamble += f" ⚠ 부가 상황: {cx_note}"
    # 상황 도입부에 '이 지역 실제 침수 이력·하천범람 우려지점'(침수흔적도·인명피해우려지역 실데이터) 삽입
    rnote = hazards.reality_note(prof, disaster_id)
    if rnote:
        preamble += f"\n📊 실측 데이터: {rnote}."
    situation_label = f"{v.get('label', '')} · {sv_label}" + (f" · {cx_label}" if cx_label else "")

    stages = []
    for si, st in enumerate(v["stages"]):
        inject = L(st["inject"])
        if si == 0:   # 첫 상황부여에 조합 상황 프리앰블을 얹는다
            inject = preamble + "\n\n" + inject
        stages.append({
            "no": st["no"], "clock": st.get("clock", ""), "title": st["title"],
            "inject": inject, "task": st["task"],
            "meeting": _meeting(st["title"]),   # P2 상황판단회의(2-1-2)
            "examples": [{"label": ex["label"], "answer": L(ex["answer"])}
                         for ex in _examples(disaster_id, idx, si)],
        })

    sel_role = _role(role)                       # P4 다역할(2-3)
    resources = hazards.mob_resources(prof)      # P5 동원자원 체크리스트(2-2-4)
    # 공식 시나리오 5요건(1-1-3) 충족 배지 — 이 시나리오가 왜 '매우우수(5점)' 요건인지 가시화
    sev_extreme = sv_label in ("호우경보 격상", "태풍특보 동반")
    scenario_reqs = [
        {"key": "극한환경", "label": "최악의 상황조건(극한환경)", "met": True,
         "note": f"급속 침수·정전·고립 등 극한 상황" + (f" · {sv_label}" if sev_extreme else "")},
        {"key": "과거사례", "label": "과거사례·사실기반 현실성", "met": bool(rnote),
         "note": (rnote[:60] + "…") if rnote else "이 시군구 실 침수이력 미개방(일반 시나리오)"},
        {"key": "불확실성", "label": "불확실성 요소(돌발변수)", "met": True,
         "note": "훈련 중 돌발 불시메시지(통신두절·유언비어 등) 부여"},
        {"key": "임무협업", "label": "임무·협업절차의 구체성", "met": True,
         "note": "표준 대응요소·상황판단회의 안건·동원자원 명시"},
        {"key": "목표연계", "label": "훈련목표와의 연계성", "met": True,
         "note": "행안부 표준매뉴얼 기준 채점=검증할 핵심역량(훈련목표)"},
    ]

    return {
        "id": s["id"], "name": s["name"], "icon": s.get("icon", "📝"),
        "title": s["title"], "role": L(s.get("role", "")), "intro": s.get("intro", ""),
        "source_manuals": s.get("source_manuals", []),
        "variant": variant, "variant_label": situation_label,
        "total_variants": total_situations(disaster_id),
        "total_stages": len(v["stages"]), "stages": stages,
        "roles": _ROLES, "selected_role": sel_role,   # P4
        "resources": resources,                        # P5
        "surprise": surprise(disaster_id, prof, seed=variant),  # 2-1-4 돌발 불시메시지
        "scenario_reqs": scenario_reqs,                # 1-1-3 시나리오 5요건 충족
    }


def _score_from_coverage(elements: list[dict], coverage: dict[str, str]) -> int:
    """요소 weight × 반영도(full/partial/none) → 0~100."""
    total_w = sum(e["weight"] for e in elements) or 1
    got = sum(e["weight"] * _LEVEL_VAL.get(coverage.get(e["key"], "none"), 0.0) for e in elements)
    return round(got / total_w * 100)


def _fallback_coverage(elements: list[dict], answer: str) -> tuple[dict, list]:
    """키워드 매칭 폴백 — 표준요소 키워드가 답안에 있으면 반영으로 본다."""
    cov, detail = {}, []
    for e in elements:
        hits = [k for k in e.get("keywords", []) if k in answer]
        level = "full" if len(hits) >= 2 else "partial" if len(hits) == 1 else "none"
        cov[e["key"]] = level
        detail.append({"key": e["key"], "level": level,
                       "reason": f"관련 키워드 {len(hits)}개 감지" if hits else "관련 서술 미확인"})
    return cov, detail


def score_elements(elements: list[dict], answer: str, title: str = "",
                   model_answer: str = "", use_llm: bool = True,
                   inject: str = "", task: str = "") -> dict:
    """표준 대응요소 목록 + 자유서술 답안 → 채점·강평 결과(dict).

    ttx.evaluate와 AI 생성 시나리오 평가가 공유하는 채점 코어.
    · 점수는 항상 결정론 엔진(_score_from_coverage)이 계산 — LLM은 판정·강평 문장만.
    · 키 없으면 키워드 매칭 폴백으로 동일 구조 출력(0원).
    elements[i] = {key, desc, weight, keywords[], 근거?, missing_action?, recommendation?}
    """
    coverage = detail = strengths = missed = coach = engine = None
    if use_llm and answer.strip() and llm.has_key():
        try:
            stage = {"inject": inject, "task": task, "elements": elements}
            coverage, detail, strengths, missed, coach = _with_claude(stage, answer, lambda t: t)
            engine = f"claude:{llm.MODEL}"
        except Exception:  # noqa: BLE001
            coverage = None
    if coverage is None:
        coverage, detail = _fallback_coverage(elements, answer)
        engine = "fallback(keyword)"

    score = _score_from_coverage(elements, coverage)
    bykey = {d["key"]: d for d in detail}
    elem_out = []
    for e in elements:
        level = coverage.get(e["key"], "none")
        d = bykey.get(e["key"], {})
        ma = d.get("missing_action") or (e.get("missing_action", "") if level != "full" else "")
        rec = d.get("recommendation") or (e.get("recommendation", "") if level != "full" else "현 수준 유지")
        elem_out.append({
            "key": e["key"], "desc": e["desc"], "근거": e.get("근거", ""),
            "weight": e["weight"], "level": level, "reason": d.get("reason", ""),
            "missing_action": ma, "recommendation": rec,
            "indicator": eval_map.indicator_of(e["key"]),
        })
    if strengths is None:
        strengths = [e["desc"] for e in elements if coverage.get(e["key"]) == "full"]
        missed = [e["desc"] for e in elements if coverage.get(e["key"]) in (None, "none", "partial")]
        covered = sum(1 for e in elements if coverage.get(e["key"]) == "full")
        coach = (f"표준 대응요소 {len(elements)}개 중 {covered}개를 충실히 반영했습니다. "
                 "누락 요소(특히 인명 관련)를 우선순위 앞단에 넣는 연습을 권합니다."
                 if covered < len(elements) else "표준 대응요소를 빠짐없이 우선순위대로 반영했습니다.")
    return {
        "title": title, "score": score, "grade": core.grade_of(score),
        "grade5": eval_map.grade5(score), "max": 100,
        "elements": elem_out, "strengths": strengths[:5], "missed": missed[:5],
        "coach": coach, "model_answer": model_answer, "engine": engine,
        "indicators": eval_map.build(elem_out),
    }


def evaluate(disaster_id: str, stage_idx: int, answer: str,
             profile: dict | None = None, use_llm: bool = True, variant: int = 0,
             briefing: dict | None = None, role: str | None = None) -> dict:
    """참가자 자유서술 답안을 표준 대응요소와 대조해 채점·강평.

    briefing = safety_data.get_local_disaster_briefing(profile) 결과(선택).
      주면 반환에 region_reflection(지역 재난안전데이터 위험요소 반영도)이 추가된다.
      채점 점수(score)는 표준요소 채점만으로 결정 — 지역 반영은 자문 정보이며 점수를 바꾸지 않는다.
    role(P4·2-3): 역할별 중점 자문(role_note)을 덧붙인다. 점수는 역할과 무관(불변).
    """
    s = _load(disaster_id)
    _, v = _pick(s, variant)
    st = v["stages"][stage_idx]
    elements = st["elements"]
    # 상황부여(start)와 동일한 실지점 토큰을 써 모범답안·요소설명이 참가자가 본 지점명과 일치하도록
    prof = profile or region.resolve(None)
    real = hazards.scenario_tokens(prof)
    if real:
        prof = {**prof, "tokens": {**prof.get("tokens", {}), **real}}
    L = lambda t: region.localize_text(t, prof)  # noqa: E731

    coverage, detail, strengths, missed, coach, engine = None, None, None, None, None, None
    if use_llm and answer.strip() and llm.has_key():
        try:
            coverage, detail, strengths, missed, coach = _with_claude(st, answer, L)
            engine = f"claude:{llm.MODEL}"
        except Exception:  # noqa: BLE001
            coverage = None
    if coverage is None:
        coverage, detail = _fallback_coverage(elements, answer)
        engine = "fallback(keyword)"

    score = _score_from_coverage(elements, coverage)
    bykey = {d["key"]: d for d in detail}
    elem_out = []
    for e in elements:
        level = coverage.get(e["key"], "none")
        d = bykey.get(e["key"], {})
        # 누락행동·개선권고: LLM 판정 우선, 없으면 표준요소 JSON의 값(폴백도 항상 채워짐)
        ma = d.get("missing_action") or (L(e.get("missing_action", "")) if level != "full" else "")
        rec = d.get("recommendation") or (L(e.get("recommendation", "")) if level != "full"
                                          else "현 수준 유지")
        elem_out.append({
            "key": e["key"], "desc": L(e["desc"]), "근거": e.get("근거", ""),
            "weight": e["weight"], "level": level,
            "reason": d.get("reason", ""),
            "missing_action": ma, "recommendation": rec,
            "indicator": eval_map.indicator_of(e["key"]),   # 공식 평가지표 코드
        })
    if strengths is None:
        strengths = [L(e["desc"]) for e in elements if coverage.get(e["key"]) == "full"]
        missed = [L(e["desc"]) for e in elements if coverage.get(e["key"]) in (None, "none", "partial")]
        covered_n = sum(1 for e in elements if coverage.get(e["key"]) == "full")
        coach = (f"표준 대응요소 {len(elements)}개 중 {covered_n}개를 충실히 반영했습니다. "
                 "누락 요소(특히 인명 관련)를 우선순위 앞단에 넣는 연습을 권합니다."
                 if covered_n < len(elements) else "표준 대응요소를 빠짐없이 우선순위대로 반영했습니다.")

    region_ref = None
    if briefing:
        region_ref = safety_data.region_reflection(briefing.get("risk_flags", {}), answer)

    r = _role(role)
    role_note = {"label": r["label"], "focus": r["focus"]}
    indicators = eval_map.build(elem_out)     # 공식 평가지표별 획득 등급 대조

    return {
        "stage": stage_idx, "title": st["title"], "score": score,
        "grade": core.grade_of(score), "grade5": eval_map.grade5(score), "max": 100,
        "elements": elem_out, "strengths": strengths[:5], "missed": missed[:5],
        "coach": coach, "model_answer": L(st.get("model_answer", "")),
        "engine": engine,
        "region_reflection": region_ref,
        "role_note": role_note,   # P4 역할 관점(점수 불변)
        "indicators": indicators,  # 공식 평가지표 대조
    }


_EVAL_TOOL = {
    "name": "emit_ttx_eval",
    "description": "도상훈련 서술 답안을 표준 대응요소와 대조해 반영도를 판정한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "coverage": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "level": {"type": "string", "enum": ["full", "partial", "none"]},
                    "reason": {"type": "string", "description": "판정 근거 한 줄"},
                    "missing_action": {"type": "string", "description": "이 요소에서 답안이 놓친 구체 행동(full이면 빈 문자열)"},
                    "recommendation": {"type": "string", "description": "이 요소 개선 권고 한 줄(표준매뉴얼 근거)"},
                },
                "required": ["key", "level", "reason"]}},
            "strengths": {"type": "array", "items": {"type": "string"}, "description": "잘 반영한 점 1~3"},
            "missed": {"type": "array", "items": {"type": "string"}, "description": "놓친·약한 점 1~3"},
            "coach": {"type": "string", "description": "핵심 한 수(표준매뉴얼 인용)"},
        },
        "required": ["coverage", "strengths", "missed", "coach"],
    },
}

_SYSTEM = """\
당신은 재난대응 도상훈련(TTX)의 AI 평가관이다.
- 참가자의 자유서술 답안을, 제공된 '표준 대응요소' 각각에 대해 full(충실 반영)/partial(부분)/none(누락)으로 판정한다.
- 제공된 표준 대응요소 안에서만 판단한다. 없는 규정을 지어내지 않는다.
- 차분하고 구체적으로, 한국어로. 실제 재난담당공무원이 다음에 더 잘하도록 강평한다.
"""


def _with_claude(stage: dict, answer: str, L):
    import anthropic

    elements = [{"key": e["key"], "표준요소": L(e["desc"]), "근거": e.get("근거", "")}
                for e in stage["elements"]]
    payload = {
        "상황부여": L(stage["inject"]), "지시": stage["task"],
        "표준_대응요소": elements, "참가자_답안": answer,
    }
    client = anthropic.Anthropic(api_key=llm._anthropic_key())
    resp = client.messages.create(
        model=llm.MODEL, max_tokens=1100, system=_SYSTEM,
        tools=[_EVAL_TOOL], tool_choice={"type": "tool", "name": "emit_ttx_eval"},
        messages=[{"role": "user", "content":
                   "아래 도상훈련 답안을 표준 대응요소별로 판정·강평하라.\n"
                   + json.dumps(payload, ensure_ascii=False)}],
    )
    blk = next(b for b in resp.content if b.type == "tool_use")
    data = dict(blk.input)
    coverage = {c["key"]: c["level"] for c in data["coverage"]}
    detail = [{"key": c["key"], "level": c["level"], "reason": c.get("reason", ""),
               "missing_action": c.get("missing_action", ""),
               "recommendation": c.get("recommendation", "")}
              for c in data["coverage"]]
    return coverage, detail, data.get("strengths", []), data.get("missed", []), data.get("coach", "")
