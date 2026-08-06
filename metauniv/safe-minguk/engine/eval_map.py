"""공식 평가지표 대조 — TTX 표준 대응요소를 「2026 안전한국훈련 평가지표」에 매핑하고
5단계 등급(매우우수~매우미흡)으로 환산한다.

핵심: 채점 점수는 그대로(ttx 엔진), 여기서는 그 결과를 '공식 지표별 획득 등급'으로 재구성만 한다.
훈련자가 실제 안전한국훈련에서 어떤 지표로 몇 등급을 받을지 그대로 연습·확인할 수 있게 한다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_LEVELVAL = {"full": 1.0, "partial": 0.5, "none": 0.0}

# 표준 대응요소 key → 공식 평가지표 코드(시군구 재난대응 기준)
INDICATOR_OF = {
    # 2-1-1 상황 접수·보고·전파
    "상황전파": "2-1-1", "대국민소통": "2-1-1",
    # 2-1-2 상황판단회의·비상기구 가동
    "대책본부": "2-1-2",
    # 2-1-3 재난상황 문제해결(현장 통제·응급조치)
    "선제통제": "2-1-3", "진입차단": "2-1-3", "하천통제": "2-1-3", "제방감시": "2-1-3",
    "주차장통제": "2-1-3", "배수복구": "2-1-3", "배수양수": "2-1-3", "응급복구": "2-1-3",
    "2차안전": "2-1-3", "감전차단": "2-1-3", "전원배수": "2-1-3",
    # 2-2 인명피해 최소화
    "반지하대피": "2-2-INMYEONG", "저지대대피": "2-2-INMYEONG", "대피유도": "2-2-INMYEONG",
    "구조우선": "2-2-INMYEONG", "인명구조": "2-2-INMYEONG", "구조대피": "2-2-INMYEONG",
    "구조수색": "2-2-INMYEONG", "승강기갇힘": "2-2-INMYEONG", "취약계층": "2-2-INMYEONG",
    # 수습·구호
    "대피소운영": "2-2-SUSEUP", "대피소구호": "2-2-SUSEUP",
    # 2-1-4 불시 돌발메시지 처리(돌발 불시메시지 요소)
    "대체통신확보": "2-1-4", "불시우선순위": "2-1-4", "수기기록보고": "2-1-1",
    "사실확인": "2-1-4", "공식정정발표": "2-1-1", "혼란차단": "2-2-INMYEONG",
    "대체자원확보": "2-2-SUSEUP", "자원재배분": "2-1-4", "인명보완조치": "2-2-INMYEONG",
    "구조자원증원": "2-2-INMYEONG", "중증도분류": "2-1-4", "임시대피유도": "2-2-INMYEONG",
    # AI 생성 시나리오(generator) 요소 → 공식 지표
    "situation": "2-1-1", "report_coord": "2-1-1",
    "life_safety": "2-2-INMYEONG", "patient_evac": "2-2-INMYEONG",
    "student_evac": "2-2-INMYEONG", "visitor_evac": "2-2-INMYEONG",
    "scene_control": "2-1-3", "lab_hazmat": "2-1-3", "process_shutdown": "2-1-3",
}


@lru_cache(maxsize=1)
def criteria() -> dict:
    try:
        return json.loads((DATA_DIR / "eval_criteria.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"grade_bands": [], "indicators": {}}


def grade5(score: int) -> dict:
    """0~100 점수 → 공식 5단계 등급(매우우수5~매우미흡1)."""
    for b in criteria().get("grade_bands", []):
        if score >= b.get("min", 0):
            return {"grade": b["g"], "score": b["score"]}
    return {"grade": "매우미흡", "score": 1}


def indicator_of(key: str) -> str | None:
    return INDICATOR_OF.get(key)


def build(elements: list[dict]) -> list[dict]:
    """채점된 대응요소 목록 → 공식 평가지표별 획득 등급 대조.

    elements[i] = {key, desc, weight, level(full/partial/none)}
    반환: [{code, title, score, grade, grade_score, items[], grade_desc, covered[], missed[]}] (지표코드순)
    """
    ind = criteria().get("indicators", {})
    groups: dict[str, list] = {}
    for e in elements:
        code = INDICATOR_OF.get(e.get("key", ""))
        if code:
            groups.setdefault(code, []).append(e)
    out = []
    for code, els in groups.items():
        tw = sum(e.get("weight", 0) for e in els) or 1
        got = sum(e.get("weight", 0) * _LEVELVAL.get(e.get("level", "none"), 0.0) for e in els)
        s = round(got / tw * 100)
        g = grade5(s)
        info = ind.get(code, {})
        out.append({
            "code": code, "title": info.get("title", code),
            "score": s, "grade": g["grade"], "grade_score": g["score"],
            "items": info.get("items", []),
            "grade_desc": info.get("grades", {}).get(g["grade"], ""),
            "covered": [e.get("desc", "") for e in els if e.get("level") == "full"],
            "missed": [e.get("desc", "") for e in els if e.get("level") != "full"],
        })
    out.sort(key=lambda x: x["code"])
    return out


def merge(reports: list[list[dict]]) -> list[dict]:
    """여러 단계의 지표 대조를 합쳐 지표별 최종 등급(획득 점수 가중 평균)으로 통합.

    결과보고서용 — 단계별 대조표를 한 장의 '평가지표별 획득 등급'으로.
    """
    acc: dict[str, dict] = {}
    for rep in reports:
        for r in rep:
            a = acc.setdefault(r["code"], {"code": r["code"], "title": r["title"],
                                          "items": r["items"], "_ss": 0, "_n": 0,
                                          "covered": [], "missed": []})
            a["_ss"] += r["score"]; a["_n"] += 1
            a["covered"] += r["covered"]; a["missed"] += r["missed"]
    out = []
    ind = criteria().get("indicators", {})
    for code, a in acc.items():
        s = round(a["_ss"] / a["_n"]) if a["_n"] else 0
        g = grade5(s)
        out.append({"code": code, "title": a["title"], "score": s,
                    "grade": g["grade"], "grade_score": g["score"],
                    "items": a["items"],
                    "grade_desc": ind.get(code, {}).get("grades", {}).get(g["grade"], ""),
                    "covered": sorted(set(a["covered"])),
                    "missed": sorted(set(x for x in a["missed"] if x not in a["covered"]))})
    out.sort(key=lambda x: x["code"])
    return out
