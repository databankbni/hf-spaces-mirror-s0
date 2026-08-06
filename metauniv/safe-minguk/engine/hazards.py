"""주소(시군구) → 실제 위험지점(하천·지하차도·저지대·침수흔적·대피소 등).

두 소스:
  1) 큐레이션 지역(관악·강남·청주·포항·경주·해운대) = regions.json의 지역 특정 토큰
     (도림천·오송 궁평2지하차도 등, 재해연보·인명피해우려·침수흔적 기반 실지명) → 지금 즉시 표출.
  2) 그 외 전국 시군구 = 공유플랫폼 위험지점 API(인명피해우려 15139667·침수흔적도 15150694 등).
     ⚠활용신청 + 허용IP(*.*.*.*) 필요 → 승인 전에는 status='pending'(지어내지 않음).
     승인 후 `_LIVE_SPECS`의 endpoint/필드만 채우면 전국 자동 점등("소켓 먼저").

정직 원칙(CLAUDE.md): 미승인·실패 시 pending. 큐레이션은 'curated' 라벨로 근거 명시.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

try:
    import requests
except ImportError:  # 오프라인 방어
    requests = None  # type: ignore

_HERE = Path(__file__).resolve().parent

# 토큰 키 → (표출 라벨, 아이콘, 재난 연관) : 시나리오에 끼우는 지역 위험지점과 동일 소스
_TYPES = [
    ("underpass", "지하차도", "🚧", "침수 시 통제 대상"),
    ("river", "하천", "🌊", "범람 감시"),
    ("lowland", "저지대", "🏘️", "침수 취약 주거"),
    ("pump", "빗물펌프장", "💧", "배수 핵심시설"),
    ("riverside", "둔치주차장", "🅿️", "차량 고립 위험"),
    ("oldtown", "노후상가", "🏚️", "지진·붕괴 취약"),
    ("shelter", "대피소", "🏫", "이재민 수용"),
]

_SOURCES = [
    {"id": "15139667", "name": "인명피해우려지역", "url": "https://www.data.go.kr/data/15139667/openapi.do"},
    {"id": "15150694", "name": "침수흔적도", "url": "https://www.data.go.kr/data/15150694/openapi.do"},
    {"id": "15139679", "name": "지역재해위험지구", "url": "https://www.data.go.kr/data/15139679/openapi.do"},
    {"id": "DSSP-IF-10943", "name": "지진옥외대피소(공유플랫폼)", "url": "https://www.safetydata.go.kr/"},
    {"id": "15016405", "name": "재해연보(큐레이션 근거)", "url": "https://www.data.go.kr/data/15016405/fileData.do"},
]


@lru_cache(maxsize=1)
def _shelter_index() -> dict:
    """지진옥외대피소 번들(safetydata 하베스트, 시군구 인덱싱) — 전국 11,187곳."""
    import json
    try:
        d = json.loads((_HERE.parent / "data" / "shelters_eqk.json").read_text(encoding="utf-8"))
        return d.get("by", {})
    except Exception:  # noqa: BLE001
        return {}


def _cap(x) -> int:
    try:
        return int(x.get("cap") or 0)
    except (TypeError, ValueError):
        return 0


@lru_cache(maxsize=1)
def _points_index() -> dict:
    """인명피해우려지역 번들(시군구명 인덱싱) — 실제 지구명·지정사유·좌표."""
    try:
        return json.loads((_HERE.parent / "data" / "hazard_points.json").read_text(encoding="utf-8")).get("by", {})
    except Exception:  # noqa: BLE001
        return {}


@lru_cache(maxsize=1)
def _rivers_index() -> dict:
    """시군구별 대표 하천명(공개 지리정보 시드). {river} 토큰을 실제 하천명으로 치환하는 데 쓴다.
    전국하천표준데이터(15139206) 승인 시 이 시드를 대체·확장(소켓)."""
    try:
        return json.loads((_HERE.parent / "data" / "rivers_by_sgg.json").read_text(encoding="utf-8")).get("by", {})
    except Exception:  # noqa: BLE001
        return {}


@lru_cache(maxsize=1)
def _flood_index() -> dict:
    """침수흔적도 번들(시군구명) — 실제 과거 침수 재해명·연도."""
    try:
        return json.loads((_HERE.parent / "data" / "flood_history.json").read_text(encoding="utf-8")).get("by", {})
    except Exception:  # noqa: BLE001
        return {}


def _classify(reason: str) -> tuple[str, str]:
    r = reason or ""
    if "하천" in r or "범람" in r or "하상" in r or "제방" in r:
        return "하천·범람", "🌊"
    if "지하" in r or "차도" in r or "보차도" in r:
        return "지하공간", "🚧"
    if "급경사" in r or "산사태" in r or "사면" in r or "낙석" in r:
        return "급경사·산사태", "⛰️"
    if "급류" in r or "계곡" in r or "세월교" in r or "징검다리" in r:
        return "급류·계곡", "💧"
    if "저지대" in r or "침수" in r:
        return "침수우려", "🏘️"
    return "인명피해우려", "⚠️"


def _sgg_key(profile: dict) -> str:
    return f"{(profile or {}).get('sido', '')} {(profile or {}).get('sigungu', '')}".strip()


def _idx_get(index: dict, profile: dict):
    """시군구 키로 실데이터 조회. 구 단위('충청남도 천안시 동남구')가 미스면 시 단위('충청남도 천안시')로
    폴백한다 — 인명피해우려·침수흔적·대피소 번들이 시(市) 단위로 인덱싱돼 있어 구 단위 주소가 어긋나던 버그 해결."""
    key = _sgg_key(profile)
    if key in index:
        return index[key], key
    sgg = (profile or {}).get("sigungu", "")
    if " " in sgg:   # '천안시 동남구' → '천안시'
        parent = f"{(profile or {}).get('sido', '')} {sgg.split(' ')[0]}".strip()
        if parent in index:
            return index[parent], parent
    return None, key


def _live_points(profile: dict, limit: int = 8) -> list[dict]:
    raw = _idx_get(_points_index(), profile)[0] or []
    out = []
    for x in raw[:limit]:
        typ, icon = _classify(x.get("r", ""))
        out.append({"type": typ, "name": x.get("n", ""), "role": (x.get("r") or "")[:30],
                    "icon": icon, "lat": x.get("la"), "lon": x.get("lo")})
    return out


def _flood_history(profile: dict) -> dict | None:
    f = _idx_get(_flood_index(), profile)[0]
    if not f:
        return None
    # 침수 심도는 이상치(면적 오입력 등)가 있어 0.1~10m만 신뢰 표기, 그 외 숨김.
    evs = []
    for e in f.get("events", []):
        d = e.get("depth")
        evs.append({"yr": e.get("yr"), "nm": e.get("nm"),
                    "depth": (d if isinstance(d, (int, float)) and 0.1 <= d <= 10 else None)})
    return {"events": evs, "count": f.get("count", 0)}


def _token_slot(name: str, reason: str) -> str | None:
    """인명피해우려 지점을 시나리오 토큰 슬롯(underpass/river/lowland)에 배정.

    ⛔물리적 형태가 이름/사유로 명확할 때만 배정한다(reason만으로는 교차오염 → 지하차도 슬롯에
    엉뚱한 지구명이 들어가는 것을 막는다). 애매하면 None → 호출측이 일반명 폴백을 유지(지어내지 않음).
    """
    n = name or ""
    r = reason or ""
    if any(h in n for h in ("지하차도", "지하보도", "지하도", "굴다리", "언더패스", "철길밑")):
        return "underpass"
    if any(h in n for h in ("제방", "둔치", "하상", "수변")) or n.endswith("천") or n.endswith("강"):
        return "river"
    if n.endswith("교") and any(k in r for k in ("하천", "범람")):
        return "river"
    if any(h in n for h in ("저지대", "반지하")):
        return "lowland"
    if any(h in n for h in ("지구", "마을", "단지")) and "침수" in r:
        return "lowland"
    return None


def scenario_tokens(profile: dict) -> dict:
    """시군구의 실데이터 → 시나리오 토큰 오버라이드(river/underpass/lowland/pump/shelter).

    실데이터에서만 채운다(지어내지 않음). 이미 지역특정(큐레이션) 값이 있으면 보존(default 일반값일 때만 교체).
      · river     = 인명피해우려 하천형 지점 → 없으면 대표 하천명 시드(rivers_by_sgg) → 없으면 폴백
      · underpass = 인명피해우려 지하공간형 지점
      · lowland   = 인명피해우려 침수 저지대 지점
      · pump      = 인명피해우려 지점명 중 펌프장/배수시설
      · shelter   = 지진옥외대피소(수용인원 최다) 실명
    호출측(ttx/sim)은 채워진 슬롯만 실명으로 치환하고, 빈 슬롯은 일반명 폴백을 유지한다.
    """
    prof = profile or {}
    raw = _idx_get(_points_index(), prof)[0] or []
    tokens = prof.get("tokens", {})
    default = _default_tokens()
    picks: dict[str, str] = {}

    def _free(slot: str) -> bool:   # 큐레이션 등 실지명이 이미 있으면 건드리지 않는다
        return tokens.get(slot) in (None, "", default.get(slot))

    # 1) 인명피해우려 지점 → 형태가 명확한 슬롯(underpass/river/lowland)
    for x in raw:
        name = (x.get("n") or "").strip()
        if not name:
            continue
        slot = _token_slot(name, x.get("r") or "")
        if slot and slot not in picks and _free(slot):
            picks[slot] = name
        if "pump" not in picks and _free("pump") and any(k in name for k in ("펌프", "배수")):
            picks["pump"] = name

    # 2) river 슬롯이 비면 대표 하천명 시드로(실제 하천명)
    if "river" not in picks and _free("river"):
        rv = _idx_get(_rivers_index(), prof)[0] or []
        if rv:
            picks["river"] = rv[0]

    # 3) shelter = 실제 지진옥외대피소(수용 최다)
    if _free("shelter"):
        sh, _n = _shelters_for(prof, 1)
        if sh and sh[0].get("name"):
            picks["shelter"] = sh[0]["name"]

    # 4) riverside(둔치주차장)는 실제 하천명과 연계 — "○○천변 둔치주차장"
    if "river" in picks and _free("riverside"):
        picks["riverside"] = f"{picks['river']}변 둔치주차장"

    return picks


def _josa(word: str, has_batchim: str, no_batchim: str) -> str:
    """한글 받침 유무에 맞는 조사 선택(은/는·이/가·으로/로 등). 숫자·영문 끝은 받침형 기본."""
    ch = (word or "")[-1:] or ""
    if "가" <= ch <= "힣":
        return has_batchim if (ord(ch) - 0xAC00) % 28 else no_batchim
    return has_batchim


def reality_note(profile: dict, disaster: str) -> str:
    """시나리오에 주입할 '이 지역 실제 데이터' 한 줄(침수 이력 + 하천범람 우려지점). 없으면 빈 문자열."""
    if disaster not in ("flood",):
        return ""
    sgg = (profile or {}).get("sigungu", "") or "이 지역"
    sgg = sgg.split(" ")[0] if " " in sgg else sgg   # 데이터가 시 단위 → 라벨도 시 단위(구 표기 지양)
    parts = []
    f = _idx_get(_flood_index(), profile)[0]
    if f and f.get("events"):
        e = f["events"][0]
        nm = e.get("nm") or ""
        parts.append(f"{sgg}{_josa(sgg, '은', '는')} 실제로 {e.get('yr')}년 '{nm}'{_josa(nm, '으로', '로')} 침수된 이력이 있습니다")
    pts = _idx_get(_points_index(), profile)[0] or []
    riverine = [p for p in pts if any(k in (p.get("r") or "") for k in ("하천", "범람", "하상"))]
    if riverine:
        parts.append(f"인근 '{riverine[0]['n']}' 일대가 하천범람 인명피해우려지역으로 지정돼 있습니다")
    elif pts:   # 하천형 지점이 없으면 그 지역의 대표 인명피해우려 지점이라도 실명으로 든다
        parts.append(f"'{pts[0]['n']}' 등이 인명피해우려지역으로 지정된 지역입니다")
    return " · ".join(parts)


def _shelters_for(profile: dict, limit: int = 6) -> tuple[list[dict], int]:
    """해당 시군구의 지진옥외대피소(수용인원 상위 N) + 총 개수."""
    sido = (profile or {}).get("sido", "")
    sgg = (profile or {}).get("sigungu", "")
    if not sido or not sgg:
        return [], 0
    lst = _idx_get(_shelter_index(), profile)[0] or []
    top = sorted(lst, key=_cap, reverse=True)[:limit]
    return ([{"name": x.get("n", ""), "lat": x.get("la"), "lon": x.get("lo"), "cap": _cap(x)}
             for x in top], len(lst))


def mob_resources(profile: dict, shelter_limit: int = 3, pump_limit: int = 4) -> dict:
    """P5 · 동원 가능 자원 체크리스트(안전한국훈련 평가지표 2-2-4).

    시설·장비는 실데이터에서만(대피소=지진옥외대피소 번들, 펌프장=인명피해우려 지점명).
    인력·협약기관은 재난안전대책본부 편성 표준(공개 독트린) — 실데이터 아님을 라벨로 정직 표기.
    실 시설이 없으면 해당 항목은 빈 리스트(지어내지 않음).
    """
    prof = profile or {}
    shelters, stotal = _shelters_for(prof, shelter_limit)
    pumps: list[str] = []
    for x in (_idx_get(_points_index(), prof)[0] or []):
        n = (x.get("n") or "").strip()
        if n and any(k in n for k in ("펌프", "배수")) and n not in pumps:
            pumps.append(n)
        if len(pumps) >= pump_limit:
            break
    return {
        "shelters": shelters, "shelter_total": stotal,   # 실데이터
        "pumps": pumps,                                    # 실데이터(있을 때만)
        "personnel": ["재난안전대책본부 비상근무 인력", "읍·면·동 통·이장 및 통반장", "자율방재단·의용소방대"],
        "agencies": ["소방서(119)", "경찰서(112)", "한국전력(정전·감전 위험)", "군부대·유관기관(인력·장비 지원)"],
        "personnel_source": "재난안전대책본부 편성 표준(공개)",
        "agencies_source": "재난대응 유관기관 표준 협조체계(공개)",
    }


@lru_cache(maxsize=1)
def _default_tokens() -> dict:
    """regions.json의 default tokens(일반 지명) — 이것과 다르면 '지역 특정(실지명)'으로 판단."""
    import json
    try:
        d = json.loads((_HERE.parent / "data" / "regions.json").read_text(encoding="utf-8"))
        return d.get("default", {}).get("tokens", {})
    except Exception:  # noqa: BLE001
        return {}


def _api_key() -> str | None:
    key = os.environ.get("DATA_GO_KR_KEY")
    if key:
        return key
    for p in (_HERE.parent / ".streamlit" / "secrets.toml",
              _HERE.parents[1] / "jikigo" / ".streamlit" / "secrets.toml"):
        try:
            import tomllib
            if p.exists():
                v = tomllib.loads(p.read_text(encoding="utf-8")).get("DATA_GO_KR_KEY")
                if v:
                    return v
        except Exception:  # noqa: BLE001
            pass
    return None


def _curated_points(profile: dict) -> list[dict]:
    """큐레이션 토큰 중 '지역 특정' 값만 실제 위험지점으로 추출(일반 기본값은 제외)."""
    tokens = (profile or {}).get("tokens", {})
    default = _default_tokens()
    pts = []
    for tk, label, icon, role in _TYPES:
        v = tokens.get(tk)
        if v and v != default.get(tk):
            pts.append({"type": label, "name": v, "icon": icon, "role": role})
    return pts


# ── 라이브(공유플랫폼) 소켓 — 활용신청 승인 후 endpoint/필드만 채우면 점등 ────────────
# 표준 구조(공유플랫폼 포인트 API): 시도·시군구 + 지점명 + 위경도. 승인 후 실측으로 확정한다.
_LIVE_SPECS: list[dict] = [
    # 예) {"key":"인명피해우려","endpoint":"https://www.safetydata.go.kr/V2/api/DSSP-IF-XXXXX",
    #      "icon":"⚠️","role":"인명피해 우려",
    #      "fields":{"sigungu":"sgg_nm","name":"plc_nm","lat":"lat","lon":"lot"}},
]


def _fetch_live(sido: str, sigungu: str, key: str, timeout: float) -> list[dict] | None:
    """공유플랫폼 위험지점 API에서 해당 시군구 지점 조회. 미설정/실패 시 None(→pending)."""
    if not _LIVE_SPECS or requests is None or not key:
        return None
    out: list[dict] = []
    for spec in _LIVE_SPECS:
        try:
            r = requests.get(spec["endpoint"], params={
                "serviceKey": key, "pageNo": "1", "numOfRows": "100", "returnType": "json",
            }, timeout=timeout)
            if r.status_code != 200:
                continue
            rows = _rows_of(r.json())
            f = spec["fields"]
            for row in rows:
                if sigungu and sigungu not in str(row.get(f["sigungu"], "")):
                    continue
                out.append({"type": spec["key"], "name": row.get(f["name"], ""),
                            "lat": _num(row.get(f["lat"])), "lon": _num(row.get(f["lon"])),
                            "icon": spec.get("icon", "⚠️"), "role": spec.get("role", "")})
        except Exception:  # noqa: BLE001
            continue
    return out or None


def _rows_of(j):
    # 공유플랫폼 응답 형태는 승인 후 실측으로 확정(body.items 등). 방어적 추출.
    if isinstance(j, dict):
        for k in ("body", "data", "items", "response"):
            v = j.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                for kk in ("items", "item", "data"):
                    if isinstance(v.get(kk), list):
                        return v[kk]
    return []


def _num(x):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return None


def get_hazards(profile: dict | None, timeout: float = 6.0) -> dict:
    """주소(시군구) → 실제 위험지점. 큐레이션=즉시, 그 외=라이브(승인 후) 또는 pending."""
    prof = profile or {}
    shelters, shelter_total = _shelters_for(prof)   # 지진옥외대피소(전국 실데이터)
    flood = _flood_history(prof)                     # 실제 과거 침수 이력
    base = {"region": prof.get("label", ""), "sido": prof.get("sido", ""),
            "sigungu": prof.get("sigungu", ""), "sources": _SOURCES,
            "shelters": shelters, "shelter_total": shelter_total, "flood": flood}

    live = _live_points(prof)                        # 인명피해우려지역 실데이터(전국 184 시군구)
    if live:
        return {**base, "status": "live", "points": live,
                "hist": prof.get("note", ""), "tags": prof.get("tags", []),
                "note": "행안부 공유플랫폼 인명피해우려지역·침수흔적도 실연동."}

    pts = _curated_points(prof)
    if pts:
        return {**base, "status": "curated", "points": pts,
                "hist": prof.get("note", ""), "tags": prof.get("tags", []),
                "note": "이 지역 대표 위험지점 — 재해연보·인명피해우려지역 기반 큐레이션."}

    return {**base, "status": "pending", "points": [],
            "hist": "", "tags": prof.get("tags", []),
            "note": "이 시군구는 인명피해우려지역 지정 데이터가 없어(또는 미매칭) 일반 시나리오로 진행합니다."}
