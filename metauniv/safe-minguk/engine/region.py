"""지역화 엔진 — 주소 → 지역 프로파일 → 시나리오 지역 치환 + 재난 위험도 추천.

핵심 아이디어(의료 가상환자 시뮬의 '케이스 = 템플릿 × 환자'를 재난에 적용):
    훈련 케이스 = (재난 시나리오 템플릿) × (그 주소의 지역 데이터)
같은 침수 템플릿이라도 관악구면 도림천·신림동 반지하로, 청주면 미호강·오송 지하차도로
지역화된다. 지역 프로파일은 data/regions.json(재해이력·위험지구 기반 큐레이션)에서 온다.

정직성: risk·tokens는 정밀 예측이 아니라 '훈련 우선순위·시나리오 변수'다. 실제 대응법(국민행동요령)은
data/guidelines.json의 공개 독트린으로 별도 제공한다.
"""
from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path

from . import geocode
from .util import sanitize_text

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_TOKEN_RE = re.compile(r"\{([a-zA-Z_]+)\}")


def _juso_relevant(addr: str, j: dict) -> bool:
    """juso 결과가 입력과 실제로 관련 있는지 검증.

    juso API는 자모·오타 같은 비주소 입력도 퍼지 매칭해 엉뚱한 시군구를 돌려준다(예 'ㅁㄴㅇㄹ'→관악구).
    입력의 2글자 이상 연속(한글·숫자)이 결과 주소에 실제로 등장할 때만 신뢰한다 → '없는 지역' 오매칭 차단.
    """
    hay = " ".join(str(j.get(k, "")) for k in ("full", "jibun", "sido", "sigungu", "emd", "road"))
    a = re.sub(r"[^가-힣0-9]", "", addr or "")   # 한글·숫자만(자모·영문·기호 제거)
    if len(a) < 2:
        return False
    return any(a[i:i + 2] in hay for i in range(len(a) - 1))


@lru_cache(maxsize=1)
def _regions() -> dict:
    return json.loads((DATA_DIR / "regions.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _guidelines() -> dict:
    return json.loads((DATA_DIR / "guidelines.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _admin() -> dict:
    """전국 시군구·읍면동 매칭 테이블(법정동코드 기반). 없으면 빈 테이블."""
    p = DATA_DIR / "admin_kr.json"
    if not p.exists():
        return {"govs": [], "emd": {}}
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _orgs() -> list:
    """기관 사전 — orgs.json(수기 시드) + orgs_auto.json(데이터셋 자동 적재)을 병합."""
    out: list = []
    for fn in ("orgs.json", "orgs_auto.json"):
        p = DATA_DIR / fn
        if p.exists():
            out += json.loads(p.read_text(encoding="utf-8")).get("orgs", [])
    return out


def _match_org(addr: str, base_tokens: dict) -> dict | None:
    for o in _orgs():
        if any(a in addr for a in o["aliases"]):
            return {
                "key": "org", "sido": o["sido"], "sigungu": o["sigungu"],
                "label": o["label"], "org": o["org"],
                "tags": ["기관 사전 매칭"],
                "note": f"기관 사전에서 '{o['org']}'을(를) 인식했습니다. 관할 지자체({o['sigungu']}) 기준으로 시나리오를 맞춥니다.",
                "risk": _regions()["default"]["risk"],
                "tokens": {**base_tokens, **o.get("tokens", {}), "org": o["org"]},
                "matched": True, "input": addr,
            }
    return None


# 시도 약칭 → 정식명(주소에 시도가 있으면 동명이군구 모호성 해소)
_SIDO_ABBR = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도",
}


def _detect_sido(addr: str) -> str | None:
    for abbr, full in _SIDO_ABBR.items():
        if abbr in addr or full in addr:
            return full
    return None


def _gov_in(gov: str, addr: str) -> bool:
    """지자체명이 주소에 '단어 경계'로 등장하는지 — 앞글자가 한글이면 더 큰 단어의 일부로 보고 제외.
    예: '북구'는 '부산 북구'(O)엔 매칭하되 '천안 서북구'의 '서북구'(X)엔 매칭하지 않는다."""
    i = addr.find(gov)
    while i != -1:
        before = addr[i - 1] if i > 0 else ""
        if not ("가" <= before <= "힣"):
            return True
        i = addr.find(gov, i + 1)
    return False


def _match_admin(addr: str) -> dict | None:
    """전국 법정동 테이블에서 주소 → 관할 지자체(시군구) 매칭."""
    ad = _admin()
    if not ad["govs"]:
        return None
    a = addr.strip()
    # 세종특별자치시 = 단층제(시군구 없음) — '세종·세종시·세종특별자치시'만 인정('세종대로' 등 도로명 제외)
    if a == "세종" or a.startswith("세종시") or a.startswith("세종특별자치시") or a.startswith("세종 "):
        for g in ad["govs"]:
            if g["sido"] == "세종특별자치시":
                return g
    sido = _detect_sido(addr)
    cands = [g for g in ad["govs"] if _gov_in(g["gov"], addr)]
    if sido:
        cands = [g for g in cands if g["sido"] == sido] or cands
    if not cands:  # 시군구명이 없으면 하위 지명(구·읍면동)으로 역추적
        for k in sorted(ad["emd"], key=len, reverse=True):
            if k in addr:
                labels = ad["emd"][k]
                if sido:
                    labels = [x for x in labels if x.startswith(sido)] or labels
                cands = [g for g in ad["govs"] if g["label"] == labels[0]]
                break
    if not cands:
        return None
    return max(cands, key=lambda x: len(x["gov"]))  # 가장 구체적인 매칭


# 시·도 대표 좌표(실측 도청/광역 중심) — 시군구 정밀 좌표 미보유 시 광역 지도 폴백.
_SIDO_GEO = {
    "서울특별시": (37.5665, 126.9780), "부산광역시": (35.1796, 129.0756),
    "대구광역시": (35.8714, 128.6014), "인천광역시": (37.4563, 126.7052),
    "광주광역시": (35.1595, 126.8526), "대전광역시": (36.3504, 127.3845),
    "울산광역시": (35.5384, 129.3114), "세종특별자치시": (36.4800, 127.2890),
    "경기도": (37.4138, 127.5183), "강원특별자치도": (37.8228, 128.1555), "강원도": (37.8228, 128.1555),
    "충청북도": (36.6357, 127.4917), "충청남도": (36.5184, 126.8000),
    "전북특별자치도": (35.7175, 127.1530), "전라북도": (35.7175, 127.1530),
    "전라남도": (34.8679, 126.9910), "경상북도": (36.4919, 128.8889),
    "경상남도": (35.4606, 128.2132), "제주특별자치도": (33.4890, 126.4983),
}


def _fin(d: dict) -> dict:
    """프로파일에 지도용 좌표(lat/lon)와 정밀도(geo)를 채운다.

    큐레이션(정밀 좌표 보유)=point / 그 외=시도 대표좌표 폴백=sido / 좌표 없으면 None.
    """
    if d.get("lat") is not None and d.get("lon") is not None:
        d.setdefault("geo", "point")
    else:
        c = _SIDO_GEO.get(d.get("sido", ""))
        if c:
            d["lat"], d["lon"], d["geo"] = c[0], c[1], "sido"
        else:
            d.setdefault("lat", None); d.setdefault("lon", None); d.setdefault("geo", None)
    return d


def resolve(address: str | None) -> dict:
    """주소 문자열 → 지역 프로파일. 매칭 실패·미입력 시 기본 프로파일.

    반환 프로파일의 tokens는 기본값과 병합되어 모든 변수가 항상 채워진다(브레이스 잔류 방지).
    label = 사용자에게 보여줄 지역명, matched = 큐레이션 매칭 여부.
    lat/lon/geo = 지역 프로필 지도용(point=정밀, sido=시도 폴백).
    """
    reg = _regions()
    default = reg["default"]
    base_tokens = default["tokens"]
    addr = sanitize_text(address, 100)   # 화면에 되비쳐지는 라벨의 XSS·태그주입 원천 차단

    if addr:
        org = _match_org(addr, base_tokens)   # 기관 사전 우선(도로명·기관명 인식)
        if org:
            return _fin(org)
        for r in reg["regions"]:
            if any(kw in addr for kw in r["match"]):
                org = f"{r['sigungu']} 재난안전대책본부"
                return _fin({
                    "key": r["key"], "sido": r["sido"], "sigungu": r["sigungu"],
                    "label": f"{r['sido']} {r['sigungu']}", "org": org,
                    "tags": r["tags"], "note": r["note"], "risk": r["risk"],
                    "lat": r.get("lat"), "lon": r.get("lon"),
                    "tokens": {**base_tokens, **r["tokens"], "org": org},
                    "matched": True, "input": addr,
                })

    # 전국 법정동 테이블 매칭(큐레이션 외 임의 주소) — 관할 지자체·기관명은 실제, 세부 위험은 일반
    if addr:
        g = _match_admin(addr)
        if g:
            org = f"{g['gov']} 재난안전대책본부"
            label = g["gov"] if g["sido"] == g["gov"] else g["label"]
            return _fin({
                "key": "admin", "sido": g["sido"], "sigungu": g["gov"],
                "label": label, "org": org,
                "tags": ["전국 행정구역 매칭"],
                "note": "법정동코드 기반으로 관할 지자체를 매칭했습니다. 세부 위험지점은 일반 시나리오로 진행합니다(지역 위험데이터 연동 시 정밀화).",
                "risk": default["risk"],
                "tokens": {**base_tokens, "region": g["gov"], "org": org},
                "matched": True, "input": addr,
            })

        # 도로명주소·시 단위 지명(시군구 글자 없음) → juso.go.kr API로 해석(키 설정 시).
        # ⚠juso는 비주소 입력도 퍼지 매칭하므로 결과가 입력과 관련 있을 때만 신뢰(_juso_relevant).
        j = geocode.road_lookup(addr)
        if j and j.get("sigungu") and _juso_relevant(addr, j):
            gov, sido = j["sigungu"], j["sido"]
            org = f"{gov} 재난안전대책본부"
            return _fin({
                "key": "juso", "sido": sido, "sigungu": gov,
                "label": f"{sido} {gov}".strip(), "org": org,
                "tags": ["도로명주소 매칭(juso)"],
                "note": f"도로명주소를 juso API로 해석했습니다(관할 {gov}). 세부 위험은 일반 시나리오로 진행합니다.",
                "risk": default["risk"],
                "tokens": {**base_tokens, "region": gov, "org": org},
                "matched": True, "input": addr,
            })

    # 미매칭 — 입력 지역명을 그대로 살려 일반 시나리오로
    tokens = dict(base_tokens)
    region_name = addr[:20] if addr else "우리 지역"
    if addr:
        tokens["region"] = region_name
    org = f"{region_name} 관할 재난안전대책본부"
    tokens["org"] = org
    return _fin({
        "key": "default", "sido": default["sido"], "sigungu": default["sigungu"],
        "label": (addr or "지역 미지정"), "org": org,
        "tags": default["tags"], "note": default["note"], "risk": default["risk"],
        "tokens": tokens, "matched": False, "input": addr,
    })


def _sub(text: str, tokens: dict) -> str:
    return _TOKEN_RE.sub(lambda m: tokens.get(m.group(1), m.group(0)), text)


def localize_text(text: str, profile: dict | None) -> str:
    """단일 문자열의 {token}을 지역 변수로 치환(도상훈련 등 임의 텍스트용)."""
    return _sub(text, (profile or resolve(None))["tokens"])


def localize(disaster: dict, profile: dict | None) -> dict:
    """시나리오 텍스트의 {token}을 지역 변수로 치환한 사본을 돌려준다(채점에는 영향 없음)."""
    tokens = (profile or resolve(None))["tokens"]
    d = copy.deepcopy(disaster)
    if "context" in d:
        d["context"] = _sub(d["context"], tokens)
    # quiz 모드
    for ph in d.get("phases", []):
        for k in ("inject", "question"):
            if k in ph:
                ph[k] = _sub(ph[k], tokens)
        for op in ph.get("options", []):
            for k in ("text", "why"):
                if k in op:
                    op[k] = _sub(op[k], tokens)
    # sim 모드
    sim = d.get("sim")
    if isinstance(sim, dict):
        for v in sim.get("variants", []):
            if "intro" in v:
                v["intro"] = _sub(v["intro"], tokens)
            for e in v.get("events", []):
                for k in ("label", "report", "inject"):
                    if k in e:
                        e[k] = _sub(e[k], tokens)
                for op in e.get("options", []):
                    for k in ("text", "why", "feed"):
                        if k in op:
                            op[k] = _sub(op[k], tokens)
    return d


def rank_disasters(summaries: list[dict], profile: dict) -> list[dict]:
    """카탈로그 요약에 지역 위험도(relevance)를 붙여 정렬. playable 우선, 그다음 위험도순."""
    risk = profile.get("risk", {})
    out = []
    for s in summaries:
        rel = risk.get(s["id"], 0.4)
        out.append({**s, "relevance": round(rel, 2),
                    "recommended": s["depth"] == "playable" and rel >= 0.6})
    out.sort(key=lambda x: (x["depth"] != "playable", -x["relevance"], x["name"]))
    return out


def guideline(disaster_id: str) -> dict | None:
    """재난유형별 '실제 대응법'(국민행동요령). 없으면 None."""
    g = _guidelines().get(disaster_id)
    return dict(g) if isinstance(g, dict) else None
