"""재난 모듈 카탈로그 — disasters/*.json 로드 + 스키마 검증.

재난 추가 = JSON 한 개 추가(코드 변경 없음). 이게 '멀티재난 확장성'의 실체다.
검증은 가볍게: 필수 키·옵션 rubric 값·effects 타입만 본다(잘못된 설정은 일찍 죽인다).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DISASTER_DIR = Path(__file__).resolve().parents[1] / "disasters"
VALID_RUBRIC = {"correct", "partial", "wrong"}
VALID_DEPTH = {"playable", "scaffold"}
VALID_MODE = {"quiz", "sim"}


@lru_cache(maxsize=1)
def upcoming() -> list[dict]:
    """훈련 모듈 미구현 재난 유형(을지/안전한국훈련 체계 로드맵) — '준비 중' 표시용."""
    try:
        p = Path(__file__).resolve().parents[1] / "data" / "upcoming.json"
        return json.loads(p.read_text(encoding="utf-8")).get("upcoming", [])
    except Exception:  # noqa: BLE001
        return []


def _validate(d: dict, src: str) -> None:
    for k in ("id", "name", "depth"):
        if k not in d:
            raise ValueError(f"{src}: 필수 키 '{k}' 누락")
    if d["depth"] not in VALID_DEPTH:
        raise ValueError(f"{src}: depth는 {VALID_DEPTH} 중 하나여야 함")
    mode = d.get("mode", "quiz")
    if mode not in VALID_MODE:
        raise ValueError(f"{src}: mode는 {VALID_MODE} 중 하나여야 함")
    if mode == "sim":
        _validate_sim(d, src)
    else:
        _validate_quiz(d, src)


def _validate_quiz(d: dict, src: str) -> None:
    if "phases" not in d:
        raise ValueError(f"{src}: quiz 모드는 'phases' 필요")
    for ph in d["phases"]:
        for k in ("id", "inject", "question", "options"):
            if k not in ph:
                raise ValueError(f"{src}/{ph.get('id','?')}: phase 키 '{k}' 누락")
        if not ph["options"]:
            raise ValueError(f"{src}/{ph['id']}: 옵션이 비어 있음")
        for op in ph["options"]:
            if op.get("rubric") not in VALID_RUBRIC:
                raise ValueError(f"{src}/{ph['id']}/{op.get('id','?')}: rubric={op.get('rubric')} 부적합")
            if not isinstance(op.get("effects", {}), dict):
                raise ValueError(f"{src}/{ph['id']}/{op.get('id','?')}: effects는 dict")


def _validate_sim(d: dict, src: str) -> None:
    sim = d.get("sim")
    if not isinstance(sim, dict):
        raise ValueError(f"{src}: sim 모드는 'sim' 블록 필요")
    variants = sim.get("variants")
    if not variants:
        raise ValueError(f"{src}: sim 키 'variants' 누락/빈값")
    for v in variants:
        if not v.get("events"):
            raise ValueError(f"{src}/variant '{v.get('label','?')}': events 누락")
        _validate_sim_events(v["events"], src)


def _validate_sim_events(events: list, src: str) -> None:
    ids = set()
    for e in events:
        for k in ("id", "inject", "options", "trigger"):
            if k not in e:
                raise ValueError(f"{src}/event {e.get('id','?')}: 키 '{k}' 누락")
        ids.add(e["id"])
        rubrics = set()
        for op in e["options"]:
            if op.get("rubric") not in VALID_RUBRIC:
                raise ValueError(f"{src}/event {e['id']}/{op.get('id','?')}: rubric={op.get('rubric')} 부적합")
            if not isinstance(op.get("effects", {}), dict):
                raise ValueError(f"{src}/event {e['id']}/{op.get('id','?')}: effects는 dict")
            rubrics.add(op["rubric"])
        if "correct" not in rubrics:
            raise ValueError(f"{src}/event {e['id']}: 정답(correct) 옵션이 없음")


@lru_cache(maxsize=1)
def load_all() -> dict[str, dict]:
    """{id: 모듈} 사전. depth='playable' 먼저, 그다음 이름순(카탈로그 정렬용)."""
    out: dict[str, dict] = {}
    for p in sorted(DISASTER_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        _validate(d, p.name)
        out[d["id"]] = d
    return out


def get(disaster_id: str) -> dict:
    d = load_all().get(disaster_id)
    if not d:
        raise KeyError(f"unknown disaster {disaster_id}")
    return d


def _steps(d: dict) -> int:
    if d.get("mode") == "sim":
        return len(d["sim"]["variants"][0]["events"])
    return len(d.get("phases", []))


def summaries() -> list[dict]:
    """선택 화면용 요약 목록. playable 먼저."""
    items = [
        {"id": d["id"], "name": d["name"], "icon": d.get("icon", "⚠"),
         "depth": d["depth"], "mode": d.get("mode", "quiz"), "summary": d.get("summary", ""),
         "phases": _steps(d), "source_manuals": d.get("source_manuals", [])}
        for d in load_all().values()
    ]
    items.sort(key=lambda x: (x["depth"] != "playable", x["name"]))
    return items
