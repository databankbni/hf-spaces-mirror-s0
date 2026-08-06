"""주소(지역) → 과거 재해 통계 — 행정안전부 통계연보 오픈API(data.go.kr 1741000) 실연동.

승인·엔드포인트 확정 완료(2026-07-02):
  · 지역별 이재민 발생   : /DisasterVictimsOccurRegion/getDisasterVictimsOccurRegionList (JSON)
  · 지역별 자연재해 복구비 : /RegionDisasterRecoveryCosts/getRegionDisasterRecoveryCosts (XML)
  · 자연재난 시도별-원인별 피해 : /NaturalDisasterDamageCause/getNaturalDisasterDamageCause (XML)

⚠ 1741000 계열은 활용신청 '허용 IP' 설정이 필수(*.*.*.* 권장). 미설정 시 403(plain 'Forbidden').
정직 원칙(CLAUDE.md): 403·실패 시 status='pending' + 사유(수치 날조 금지). 성공 시 원본 수치 그대로.
키: DATA_GO_KR_KEY(env→secrets).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

try:
    import requests
except ImportError:  # noqa
    requests = None  # type: ignore

BASE = "https://apis.data.go.kr/1741000"
EP = {
    "victims": (f"{BASE}/DisasterVictimsOccurRegion/getDisasterVictimsOccurRegionList", "json"),
    "recovery": (f"{BASE}/RegionDisasterRecoveryCosts/getRegionDisasterRecoveryCosts", "xml"),
    "damage": (f"{BASE}/NaturalDisasterDamageCause/getNaturalDisasterDamageCause", "xml"),
}
SOURCES = [
    {"id": "15077971", "name": "지역별 이재민 발생", "url": "https://www.data.go.kr/data/15077971/openapi.do"},
    {"id": "15107322", "name": "지역별 자연재해 복구비", "url": "https://www.data.go.kr/data/15107322/openapi.do"},
    {"id": "15107569", "name": "자연재난 시도별·원인별 피해", "url": "https://www.data.go.kr/data/15107569/openapi.do"},
]
# 시도 라벨 → (이재민 응답의 영문 컬럼 접두, 피해/복구비 응답의 지역 축약명)
_REGION = {
    "서울특별시": ("seoul", "서울"), "부산광역시": ("busan", "부산"), "대구광역시": ("daegu", "대구"),
    "인천광역시": ("incheon", "인천"), "광주광역시": ("gwangju", "광주"), "대전광역시": ("daejeon", "대전"),
    "울산광역시": ("ulsan", "울산"), "세종특별자치시": ("sejong", "세종"), "경기도": ("gyeonggi", "경기"),
    "강원특별자치도": ("gangwon", "강원"), "강원도": ("gangwon", "강원"),
    "충청북도": ("chungbuk", "충북"), "충청남도": ("chungnam", "충남"),
    "전북특별자치도": ("jeonbuk", "전북"), "전라북도": ("jeonbuk", "전북"), "전라남도": ("jeonnam", "전남"),
    "경상북도": ("gyeongbuk", "경북"), "경상남도": ("gyeongnam", "경남"), "제주특별자치도": ("jeju", "제주"),
}
# 피해 원인 필드 접두 → 한글명 (damage API 실제 필드 기준)
_CAUSE = [("typhoon_hevy_rain", "태풍·호우"), ("airflow_hevy_wind", "풍랑·강풍"),
          ("typhoon", "태풍"), ("hevy_rain", "호우"), ("hevy_snow", "대설"), ("hevy_wind", "강풍"),
          ("fall_lightn", "낙뢰"), ("cld_wave", "한파"), ("earthqk", "지진"), ("ht_wave", "폭염")]
_MON_EP = f"{BASE}/NaturalDisasterMonthlyFacility/getNaturalDisasterMonthlyFacility"


def _api_key() -> str | None:
    key = os.environ.get("DATA_GO_KR_KEY")
    if key:
        return key
    here = Path(__file__).resolve()
    for p in (here.parents[1] / ".streamlit" / "secrets.toml",
              here.parents[2] / "jikigo" / ".streamlit" / "secrets.toml"):
        try:
            import tomllib
            if p.exists():
                v = tomllib.loads(p.read_text(encoding="utf-8")).get("DATA_GO_KR_KEY")
                if v:
                    return v
        except Exception:  # noqa: BLE001
            pass
    return None


def _pending(profile, reason):
    return {"status": "pending", "region": (profile or {}).get("label", "지역 미지정"),
            "sido": (profile or {}).get("sido", ""), "items": [], "sources": SOURCES, "note": reason}


def _get(url: str, params: dict, timeout: float):
    if requests is None:
        return None
    try:
        r = requests.get(url, params=params, timeout=timeout)
        return r if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


def _i(x) -> int:
    m = re.sub(r"[^\d\-]", "", str(x or ""))
    try:
        return int(m) if m not in ("", "-") else 0
    except ValueError:
        return 0


def _victims_rows(key, timeout):
    r = _get(EP["victims"][0], {"serviceKey": key, "pageNo": "1", "numOfRows": "500", "type": "json"}, timeout)
    if not r:
        return None
    try:
        j = r.json()
        blk = next(x for x in j["DisasterVictimsOccurRegion"] if "row" in x)
        return blk["row"]
    except Exception:  # noqa: BLE001
        return None


def _xml_rows(url, key, timeout):
    r = _get(url, {"serviceKey": key, "pageNo": "1", "numOfRows": "500"}, timeout)
    if not r:
        return None
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)
        return [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("row")]
    except Exception:  # noqa: BLE001
        return None


_cache: dict[str, dict] = {}   # 시도별 캐시(통계는 연 1회 갱신 → 세션 유지)


def get_region_history(profile: dict | None, timeout: float = 8.0) -> dict:
    """지역(시도) → 과거 재해 통계(이재민·인명피해·주요원인·기간). 실패 시 pending(날조 없음).

    금액(재산피해·복구비)은 통계연보 원단위 확정 전까지 제외한다(추정 금지).
    """
    key = _api_key()
    if not key or requests is None:
        return _pending(profile, "인증키 미설정 — 활용신청·키 등록 후 연동됩니다.")
    sido = (profile or {}).get("sido", "")
    eng, short = _REGION.get(sido, (None, None))
    if not eng:
        return _pending(profile, "시도 단위 통계라 이 주소는 매칭되지 않습니다(큐레이션 외 지역).")
    hit = _cache.get(sido)
    if hit:
        return {**hit, "region": (profile or {}).get("label", "")}

    victims = _victims_rows(key, timeout)
    damage = _xml_rows(EP["damage"][0], key, timeout)
    if victims is None and damage is None:
        return _pending(profile, "API 접근 거부(403 등) — 활용신청 '허용 IP'를 *.*.*.*로 설정하면 연동됩니다.")

    items, years = [], set()
    # 1) 누적 이재민 (해당 시도 컬럼, 연간 '총' 행 합)
    if victims:
        col = f"l{eng}_prsnum"
        cum = sum(_i(r.get(col)) for r in victims if r.get("disst_occu") == "총")
        for r in victims:
            if r.get("bas_yy"):
                years.add(r["bas_yy"])
        items.append({"label": "누적 이재민", "value": f"{cum:,}명"})
    # 2) 누적 인명피해 + 주요 재해 원인 (해당 시도 행)
    if damage:
        drs = [r for r in damage if r.get("regi") == short]
        life = sum(_i(r.get("life_tot")) for r in drs)
        for r in drs:
            if r.get("wrttimeid"):
                years.add(r["wrttimeid"])
        cause_sum = {}
        for r in drs:
            for pref, ko in _CAUSE:
                v = _i(r.get(f"{pref}_prop"))
                if v:
                    cause_sum[ko] = cause_sum.get(ko, 0) + v
        items.append({"label": "누적 인명피해", "value": f"{life:,}명"})
        if cause_sum:
            top = max(cause_sum, key=cause_sum.get)
            items.append({"label": "주요 재해 원인", "value": top})
    if years:
        ys = sorted(years)
        items.append({"label": "조회 기간", "value": f"{ys[0]}~{ys[-1]} ({len(ys)}개년)"})

    if not items:
        return _pending(profile, "응답은 받았으나 해당 지역 데이터가 없습니다.")
    result = {"status": "live", "region": (profile or {}).get("label", ""), "sido": sido,
              "items": items, "sources": SOURCES,
              "note": "행정안전부 통계연보 실데이터 (시도 단위 · 금액은 원단위 확정 후 추가)"}
    _cache[sido] = result
    return result


_dash_cache: dict = {}


def get_dashboard(profile, timeout: float = 8.0) -> dict:
    """대시보드 통합 통계 — 요약·연도별 시계열·유형 비중(실%)·이달 발생비중.

    · 연도별/유형: NaturalDisasterDamageCause (지역 regi × 연도 × 원인, 재산피해 prop 상대규모)
    · 이달 발생비중: NaturalDisasterMonthlyFacility (전국 월별 피해총액 → 현재 월 비중)
    금액 절대값은 원단위 미확정 → '상대 규모'로만 사용(절대 수치 표기 안 함, 추정 금지).
    """
    key = _api_key()
    sido = (profile or {}).get("sido", "")
    eng, short = _REGION.get(sido, (None, None))
    out = {"status": "pending", "region": (profile or {}).get("label", ""), "sido": sido,
           "summary": [], "yearly": [], "cause_rank": [], "month": {}, "sources": SOURCES,
           "note": "행안부 통계연보 활용신청·허용IP(*.*.*.*) 후 연동됩니다."}
    if not key or requests is None:
        return out
    if not eng:
        out["note"] = "시도 단위 통계라 이 주소는 매칭되지 않습니다(큐레이션 외)."
        return out
    if sido in _dash_cache:
        return {**_dash_cache[sido], "region": (profile or {}).get("label", "")}

    victims = _victims_rows(key, timeout)
    damage = _xml_rows(EP["damage"][0], key, timeout)
    monthly = _xml_rows(_MON_EP, key, timeout)
    if victims is None and damage is None and monthly is None:
        out["note"] = "API 접근 거부(403) — 활용신청 '허용 IP'를 *.*.*.*로 설정하면 연동됩니다."
        return out

    out["status"] = "live"
    out["note"] = "행정안전부 통계연보 실데이터"
    years = set()

    vic_year: dict[str, int] = {}   # 연도별 이재민(명) — 확정 단위, 막대 값으로 사용
    if victims:
        col = f"l{eng}_prsnum"
        cum = 0
        for r in victims:
            yy = r.get("bas_yy")
            years.add(yy)
            if r.get("disst_occu") == "총" and yy:
                v = _i(r.get(col))
                cum += v
                vic_year[yy] = vic_year.get(yy, 0) + v
        out["summary"].append({"label": "누적 이재민", "value": f"{cum:,}명"})

    cause_year: dict[str, str] = {}   # 연도 → 그 해 최다 재해 원인(막대 색)
    if damage:
        drs = [r for r in damage if r.get("regi") == short]
        cause_tot, life = {}, 0
        for r in drs:
            yy = r.get("wrttimeid")
            years.add(yy)
            life += _i(r.get("life_tot"))
            top, topv = "", 0
            for pref, ko in _CAUSE:
                v = _i(r.get(f"{pref}_prop"))
                cause_tot[ko] = cause_tot.get(ko, 0) + v
                if v > topv:
                    top, topv = ko, v
            if yy:
                cause_year[yy] = top
        out["summary"].append({"label": "누적 인명피해", "value": f"{life:,}명"})
        tot = sum(cause_tot.values()) or 1
        rank = sorted(((k, v) for k, v in cause_tot.items() if v > 0), key=lambda x: -x[1])[:5]
        out["cause_rank"] = [{"name": k, "pct": round(v / tot * 100)} for k, v in rank]
        if rank:
            out["summary"].append({"label": "반복 피해 유형", "value": rank[0][0]})

    # 연도별 막대 = 이재민 있는 모든 해(누적 이재민과 정합) · 색 = 그 해 최다 원인.
    all_years = sorted(y for y in (set(vic_year) | set(cause_year)) if y)
    out["yearly"] = [{"y": y, "vic": vic_year.get(y, 0), "top": cause_year.get(y, "")} for y in all_years]

    if monthly:
        import datetime as _dt
        mo = _dt.datetime.now().month
        msum = {m: 0 for m in range(1, 13)}
        for r in monthly:
            dt = r.get("dt", "")
            if dt.isdigit() and 1 <= int(dt) <= 12:
                msum[int(dt)] += _i(r.get("damage_amount_tot"))
        total = sum(msum.values()) or 1
        peak = max(msum, key=msum.get)
        out["month"] = {"m": mo, "share": round(msum[mo] / total * 100),
                        "peak": peak, "peak_share": round(msum[peak] / total * 100)}

    if years:
        ys = sorted(y for y in years if y)
        out["summary"].append({"label": "조회 기간", "value": f"{ys[0]}~{ys[-1]}"})

    _dash_cache[sido] = out
    return out
