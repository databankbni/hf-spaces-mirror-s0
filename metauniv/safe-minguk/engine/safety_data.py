"""지역 재난안전데이터 브리핑 엔진 — 주소(지역 프로파일) → 실제/연동예정 재난안전데이터 브리핑.

설계 원칙:
  · 순수 함수 — profile(region.resolve 결과)을 받아 {risk_flags, briefing_items, sources}를 반환.
    sim·ttx·report 어디서나 재사용한다.
  · 정직성 — 각 데이터는 status(connected/integration_ready/demo_sample)로 라벨링된다.
    실제 API 연동이 없으면 demo_sample을 반환하되 '실데이터처럼' 표시하지 않는다.
  · 결정론 — 같은 지역이면 같은 브리핑(테스트로 고정). 채점 엔진과 분리되어 점수를 바꾸지 않는다.

데이터: data/local_disaster_briefing.json(지역별 위험플래그·브리핑) + data/safety_sources.json(출처 카탈로그).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# 위험 플래그 → 시나리오·평가에 주는 의미(사람이 읽는 라벨). 채점 자체는 바꾸지 않는다.
FLAG_LABELS = {
    "flood_history": "과거 침수 이력",
    "near_underpass": "인근 침수우려 지하차도",
    "low_lying": "저지대 주거지",
    "semi_basement": "반지하 밀집",
    "shelter_available": "인근 대피소 확보",
}


@lru_cache(maxsize=1)
def _briefings() -> dict:
    p = DATA_DIR / "local_disaster_briefing.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"default": {}}


@lru_cache(maxsize=1)
def _sources() -> dict:
    """{id: source} 사전."""
    p = DATA_DIR / "safety_sources.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {s["id"]: s for s in data.get("sources", [])}


def source(source_id: str) -> dict | None:
    """출처 메타데이터 조회(데이터명·제공기관·활용방식·상태·기준일)."""
    s = _sources().get(source_id)
    return dict(s) if s else None


def all_sources() -> list[dict]:
    return [dict(s) for s in _sources().values()]


def _region_key(profile: dict | None) -> str:
    """프로파일 → 브리핑 조회 키. 큐레이션 지역(key)만 정밀 브리핑, 그 외 default."""
    if not profile:
        return "default"
    key = profile.get("key", "default")
    return key if key in _briefings() else "default"


def risk_flags(profile: dict | None) -> dict:
    """지역 위험 플래그(사전통제·반지하 등 강조에 사용). 미매칭 지역은 default."""
    b = _briefings().get(_region_key(profile), _briefings().get("default", {}))
    return dict(b.get("risk_flags", {}))


def get_local_disaster_briefing(profile: dict | None) -> dict:
    """주소(지역 프로파일) → 재난안전데이터 브리핑.

    반환:
      region            : 표시용 지역 라벨
      region_key        : 브리핑 조회 키(default = 일반 시나리오)
      matched           : 큐레이션 정밀 브리핑 여부
      risk_flags        : {flood_history, near_underpass, ...}
      active_flags      : True인 플래그의 사람 읽기용 라벨 목록
      briefing_items    : 각 항목에 출처(source) 메타데이터를 인라인으로 붙인 목록
      sources           : 이 브리핑에 쓰인 출처 카탈로그(중복 제거)
    """
    key = _region_key(profile)
    b = _briefings().get(key, _briefings().get("default", {}))
    flags = dict(b.get("risk_flags", {}))

    items, used_ids = [], []
    for it in b.get("briefing", []):
        sid = it.get("source_id")
        src = source(sid) if sid else None
        if sid and sid not in used_ids:
            used_ids.append(sid)
        items.append({
            "type": it.get("type", ""),
            "title": it.get("title", ""),
            "value": it.get("value", ""),
            "description": it.get("description", ""),
            "source_id": sid,
            "source": {
                "name": src["name"] if src else "",
                "provider": src["provider"] if src else "",
                "usage": src["usage"] if src else "",
                "status": src["status"] if src else "demo_sample",
                "status_label": src["status_label"] if src else "데모 샘플",
                "last_checked": src["last_checked"] if src else "",
            } if src else None,
        })

    active = [FLAG_LABELS[k] for k, v in flags.items() if v and k in FLAG_LABELS]
    if isinstance(flags.get("weather_warning"), str) and flags["weather_warning"] != "none":
        active.append(_warning_label(flags["weather_warning"]))

    return {
        "region": (profile or {}).get("label", "지역 미지정"),
        "region_key": key,
        "matched": key != "default",
        "risk_flags": flags,
        "active_flags": active,
        "briefing_items": items,
        "sources": [source(sid) for sid in used_ids if source(sid)],
    }


_WARN = {
    "heavy_rain_watch": "호우 주의보",
    "heavy_rain_warning": "호우 경보",
    "typhoon": "태풍 특보",
    "none": "특보 없음",
}


def _warning_label(code: str) -> str:
    return _WARN.get(code, code)


def scenario_note(flags: dict) -> str:
    """위험 플래그 → 시나리오 도입부에 붙일 '데이터 근거' 한 문장.

    데이터가 시나리오 강조에 어떻게 반영되는지 심사위원이 즉시 이해하도록 만든다.
    (채점에는 영향 없음 — 표현·우선순위 강조용)
    """
    reasons = []
    if flags.get("flood_history"):
        reasons.append("과거 침수 이력")
    if flags.get("near_underpass"):
        reasons.append("지하차도 침수 위험요소")
    if flags.get("semi_basement"):
        reasons.append("반지하 밀집")
    elif flags.get("low_lying"):
        reasons.append("저지대 주거지")
    warn = flags.get("weather_warning")
    head = f"{_warning_label(warn)} 발효 상황에서 " if isinstance(warn, str) and warn not in ("none", None) else ""
    if not reasons:
        return f"{head}입력한 주소의 지역 브리핑을 반영해 시나리오를 구성했습니다.".strip()
    body = "·".join(reasons)
    return (f"{head}입력한 주소의 지역 브리핑 결과 {body}이(가) 확인되어, "
            "초기 대응에서 사전통제·선제대피 판단이 특히 중요합니다.")


# 답안이 지역 위험요소를 반영했는지 판정할 때 쓰는 플래그별 키워드
_FLAG_KEYWORDS = {
    "flood_history": ["침수", "저지대", "이력", "상습"],
    "near_underpass": ["지하차도", "지하", "통제", "진입", "차단"],
    "low_lying": ["저지대", "지하", "선제", "대피"],
    "semi_basement": ["반지하", "지하", "대피", "방송"],
    "shelter_available": ["대피소", "수용", "이재민", "개방"],
}

_FLAG_ADVICE = {
    "flood_history": "과거 침수 이력 지역인 만큼 사전통제·선제대피 판단을 앞단에 두어야 합니다.",
    "near_underpass": "인근 지하차도 침수 위험이 있어 강우특보 시 선제 통제·진입 차단을 명시해야 합니다.",
    "low_lying": "저지대 주거지 특성상 지하·저층 선제 대피를 우선 검토해야 합니다.",
    "semi_basement": "반지하 밀집 지역이므로 반지하 세대 선제 대피 방송·유도를 반드시 포함해야 합니다.",
    "shelter_available": "인근 지정 대피소 개방·이재민 수용 안내를 대응에 포함하면 좋습니다.",
}


def region_reflection(flags: dict, answer: str) -> list[dict]:
    """참가자 답안이 '지역 재난안전데이터 위험요소'를 반영했는지 판정(가점 아님, 자문 정보).

    각 활성 플래그에 대해 관련 키워드가 답안에 있으면 reflected, 없으면 missing.
    채점 점수(_score_from_coverage)와 분리 — 표준요소 채점을 훼손하지 않는다.
    """
    out = []
    a = answer or ""
    for k, on in flags.items():
        if not on or k not in _FLAG_KEYWORDS:
            continue
        hits = [w for w in _FLAG_KEYWORDS[k] if w in a]
        out.append({
            "flag": k,
            "label": FLAG_LABELS.get(k, k),
            "reflected": bool(hits),
            "advice": _FLAG_ADVICE.get(k, ""),
        })
    return out
