"""실시간 재난안전 현황 — 기상청 단기예보·기상특보 + 에어코리아 대기질 → 종합 위험 신호등.

설계 원칙(CLAUDE.md §10 데이터·API):
  · 외부 의존 = 타임아웃·예외·명시적 폴백. 키 없거나 실패하면 sample로 떨어지되 '실데이터인 척' 안 한다.
  · 각 지표는 source('live'|'sample')를 달고 온다 → UI가 실연동/데모를 정직하게 라벨링.
  · 결정론 분리: 신호등 계산(_signal_of)은 순수 함수 → 단위테스트로 고정. 네트워크와 무관.
  · TTL 캐시(5분)로 같은 지역 반복 조회 시 API 재호출을 줄인다(레이트리밋·지연 완화).

인증키: env DATA_GO_KR_KEY → 시뮬레이터 secrets → 지키GO(jikigo) secrets 순.
  (기상청 단기예보·기상특보는 이 키로 라이브 확인. 에어코리아는 서비스별 활용신청이 필요해
   미등록이면 403 → sample 폴백하고 '연동 예정'으로 표기한다.)
"""
from __future__ import annotations

import datetime as _dt
import os
import time
from pathlib import Path

try:
    import requests
except ImportError:  # 오프라인/미설치 방어 — 항상 sample로 동작
    requests = None  # type: ignore

_HERE = Path(__file__).resolve().parent
KMA_FCST = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
KMA_WARN = "https://apis.data.go.kr/1360000/WthrWrnInfoService/getWthrWrnMsg"
AIR_URL = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"

# 시도 대표 지점 기상청 격자(nx,ny) + 에어코리아 sidoName. 시군구 정밀좌표 연동 전까지 '시도 대표'로 정직 표기.
SIDO = {
    "서울특별시": (60, 127, "서울"), "부산광역시": (98, 76, "부산"), "대구광역시": (89, 90, "대구"),
    "인천광역시": (55, 124, "인천"), "광주광역시": (58, 74, "광주"), "대전광역시": (67, 100, "대전"),
    "울산광역시": (102, 84, "울산"), "세종특별자치시": (66, 103, "세종"),
    "경기도": (60, 120, "경기"), "강원특별자치도": (73, 134, "강원"), "강원도": (73, 134, "강원"),
    "충청북도": (69, 107, "충북"), "충청남도": (68, 100, "충남"),
    "전북특별자치도": (63, 89, "전북"), "전라북도": (63, 89, "전북"), "전라남도": (51, 67, "전남"),
    "경상북도": (89, 91, "경북"), "경상남도": (91, 77, "경남"), "제주특별자치도": (52, 38, "제주"),
}
_DEFAULT = (60, 127, "서울")

_PTY = {0: "없음", 1: "비", 2: "비/눈", 3: "눈", 4: "소나기", 5: "빗방울", 6: "빗방울/눈날림", 7: "눈날림"}
_AIR_GRADE = {1: "좋음", 2: "보통", 3: "나쁨", 4: "매우나쁨"}

_cache: dict[tuple, tuple[float, dict]] = {}
_TTL = 300.0  # 5분


# ── 인증키 ────────────────────────────────────────────────────
def _api_key() -> str | None:
    key = os.environ.get("DATA_GO_KR_KEY")
    if key:
        return key
    for p in (_HERE.parents[0] / ".streamlit" / "secrets.toml",
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


def has_key() -> bool:
    return _api_key() is not None


def _grid(profile: dict | None) -> tuple[int, int, str]:
    return SIDO.get((profile or {}).get("sido", ""), _DEFAULT)


# ── 기상청 단기예보 ───────────────────────────────────────────
def _base_datetime(now: _dt.datetime) -> tuple[str, str]:
    slots = [23, 20, 17, 14, 11, 8, 5, 2]
    cur = now - _dt.timedelta(minutes=45)
    for h in slots:
        if cur.hour >= h:
            return cur.strftime("%Y%m%d"), f"{h:02d}00"
    prev = now - _dt.timedelta(days=1)
    return prev.strftime("%Y%m%d"), "2300"


def _get_json(url: str, params: dict, timeout: float, tries: int = 2):
    """GET+JSON, resultCode 00 검증, 실패 시 1회 재시도. 성공 시 j, 실패 시 None."""
    if requests is None:
        return None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            j = r.json()
            if j.get("response", {}).get("header", {}).get("resultCode") == "00":
                return j
        except Exception:  # noqa: BLE001
            pass
    return None


def _fetch_weather(nx: int, ny: int, key: str, timeout: float) -> dict | None:
    base_date, base_time = _base_datetime(_dt.datetime.now())
    j = _get_json(KMA_FCST, {
        "serviceKey": key, "dataType": "JSON", "numOfRows": "1000", "pageNo": "1",
        "base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny,
    }, timeout)
    return _parse_weather(j) if j else None


def _parse_weather(j: dict) -> dict | None:
    try:
        items = j["response"]["body"]["items"]["item"]
    except (KeyError, TypeError):
        return None
    day = min(it["fcstDate"] for it in items)
    today = [it for it in items if it["fcstDate"] == day]

    def vals(cat):
        return [it["fcstValue"] for it in today if it["category"] == cat]

    def fnum(xs, default, agg=max):
        nums = []
        for x in xs:
            try:
                nums.append(float(x))
            except (TypeError, ValueError):
                pass
        return agg(nums) if nums else default

    return {
        "pop": int(fnum(vals("POP"), 0)),
        "pty": next((int(v) for v in vals("PTY")), 0),
        "tmp_max": round(fnum(vals("TMX") or vals("TMP"), 22.0)),
        "tmp_min": round(fnum(vals("TMN") or vals("TMP"), 14.0, agg=min)),
        "wsd": round(fnum(vals("WSD"), 2.0), 1),
    }


# ── 기상특보 ──────────────────────────────────────────────────
_DIS = [("호우", "호우"), ("홍수", "홍수"), ("태풍", "태풍"), ("강풍", "강풍"),
        ("풍랑", "풍랑"), ("폭염", "폭염"), ("한파", "한파"), ("대설", "대설"), ("건조", "건조")]


def _fetch_warnings(key: str, timeout: float) -> dict | None:
    """전국(stnId 108) 최근 5일 통보문 → 현재 발효 특보 요약. 실패 시 None."""
    today = _dt.date.today()
    j = _get_json(KMA_WARN, {
        "serviceKey": key, "dataType": "JSON", "pageNo": "1", "numOfRows": "20", "stnId": "108",
        "fromTmFc": (today - _dt.timedelta(days=5)).strftime("%Y%m%d"),
        "toTmFc": today.strftime("%Y%m%d"),
    }, timeout)
    return _parse_warnings(j) if j else None


def _parse_warnings(j: dict) -> dict:
    try:
        items = j["response"]["body"]["items"]["item"]
    except (KeyError, TypeError):
        return {"active": [], "top_level": ""}
    if isinstance(items, dict):
        items = [items]
    best: dict[str, tuple[int, str]] = {}   # 재난키 -> (tmSeq, t1)
    for it in items:
        t1 = (it.get("t1") or "").strip()
        try:
            seq = int(it.get("tmSeq") or 0)
        except (TypeError, ValueError):
            seq = 0
        key = next((k for w, k in _DIS if w in t1), None)
        if key and (key not in best or seq > best[key][0]):
            best[key] = (seq, t1)
    active = []
    top = ""
    for key, (_seq, t1) in best.items():
        if "해제" in t1:
            continue
        level = "경보" if "경보" in t1 else ("주의보" if "주의보" in t1 else "")
        active.append({"kind": key, "level": level})
        if level == "경보":
            top = "경보"
        elif level == "주의보" and top != "경보":
            top = "주의보"
    return {"active": active, "top_level": top}


# ── 에어코리아 대기질 ─────────────────────────────────────────
def _fetch_air(sido_name: str, key: str, timeout: float) -> dict | None:
    if requests is None:
        return None
    try:
        r = requests.get(AIR_URL, params={
            "serviceKey": key, "returnType": "json", "numOfRows": "100", "pageNo": "1",
            "sidoName": sido_name, "ver": "1.3",
        }, timeout=timeout)
        r.raise_for_status()
        j = r.json()
        items = j.get("response", {}).get("body", {}).get("items")
        if not items:
            return None
        pick = next((it for it in items if it.get("pm25Grade")), items[0])

        def g(k):
            try:
                return int(pick.get(k))
            except (TypeError, ValueError):
                return None

        return {"pm10_grade": g("pm10Grade"), "pm25_grade": g("pm25Grade"),
                "pm10_value": pick.get("pm10Value"), "pm25_value": pick.get("pm25Value")}
    except Exception:  # noqa: BLE001
        return None


# ── 종합 신호등(순수 함수, 테스트 고정) ───────────────────────
def _signal_of(weather: dict | None, warnings: dict | None, air: dict | None) -> dict:
    """기상특보·강수·대기질을 합쳐 green/yellow/red. 인명 위험 상향 편향(경보=즉시 red)."""
    reasons, level = [], "green"

    def bump(to, why):
        nonlocal level
        order = {"green": 0, "yellow": 1, "red": 2}
        if order[to] > order[level]:
            level = to
        reasons.append(why)

    top = (warnings or {}).get("top_level", "")
    if top == "경보":
        bump("red", "기상특보 경보 발효")
    elif top == "주의보":
        bump("yellow", "기상특보 주의보 발효")

    if weather:
        pty = weather.get("pty", 0)
        pop = weather.get("pop", 0)
        if pty in (1, 2, 4, 5, 6):          # 비/소나기 계열 현재 강수
            bump("yellow", f"현재 강수({_PTY.get(pty, '강수')})")
        if pop >= 70:
            bump("yellow", f"높은 강수확률 {pop}%")

    if air:
        g = air.get("pm25_grade") or air.get("pm10_grade")
        if g == 4:
            bump("red", "미세먼지 매우나쁨")
        elif g == 3:
            bump("yellow", "미세먼지 나쁨")

    label = {"green": "안정 · 평시 대비", "yellow": "주의 · 상황 예의주시",
             "red": "경계 · 즉시 대응태세"}[level]
    # 종합 위험지수(0~100) — 기상특보·강수·미세먼지 합성. 게이지 표시용(규칙 기반, 임의 아님).
    base = {"green": 30, "yellow": 60, "red": 82}[level]
    real = [r for r in reasons if "없음" not in r]
    score = min(96, base + min(4 * max(0, len(real) - 1), 12))
    return {"level": level, "label": label, "score": score,
            "reasons": reasons or ["특이 위험요소 없음(평시)"]}


# ── 재난 유형별 신호등(순수 함수) ─────────────────────────────
def _warn_level(warnings: dict | None, kinds: tuple) -> str:
    """kinds 중 발효 특보의 최고 레벨('경보'>'주의보'>'')."""
    lv = ""
    for a in (warnings or {}).get("active", []):
        if a.get("kind") in kinds:
            if a.get("level") == "경보":
                return "경보"
            if a.get("level") == "주의보":
                lv = "주의보"
    return lv


def disaster_board(weather: dict | None, warnings: dict | None, air: dict | None,
                   profile: dict | None, month: int) -> list[dict]:
    """재난 유형별 신호등 — 기상청 실시간(기온·강수·풍속·특보) + 지역 상시 위험도 종합.

    순수 함수(네트워크 무관, 테스트 고정). green(안전)/yellow(주의)/red(경계).
    지진은 예보 불가 → 지역 상시 위험도 기준으로 정직 표기.
    """
    risk = (profile or {}).get("risk", {}) or {}
    w = weather or {}
    pty, pop = w.get("pty", 0), w.get("pop", 0)
    tmax, tmin, wsd = w.get("tmp_max", 22), w.get("tmp_min", 14), w.get("wsd", 2.0)
    raining = pty in (1, 2, 4, 5, 6)
    snowing = pty in (3, 7)
    board: list[dict] = []

    def add(did, name, icon, level, reason):
        board.append({"id": did, "name": name, "icon": icon, "level": level, "reason": reason})

    wf = _warn_level(warnings, ("호우", "홍수", "태풍"))
    if wf == "경보":
        add("flood", "침수·호우", "🌊", "red", "호우·태풍 경보 발효")
    elif wf == "주의보" or pop >= 60 or raining:
        add("flood", "침수·호우", "🌊", "yellow",
            (wf + " 발효") if wf else (f"강수확률 {pop}%" if pop >= 60 else f"현재 {_PTY.get(pty, '강수')}"))
    else:
        add("flood", "침수·호우", "🌊", "green", "특보·강수 없음")

    ww = _warn_level(warnings, ("강풍", "태풍", "풍랑"))
    if ww == "경보":
        add("wind", "강풍·태풍", "🌪️", "red", "강풍·태풍 경보 발효")
    elif ww == "주의보" or wsd >= 9:
        add("wind", "강풍·태풍", "🌪️", "yellow", (ww + " 발효") if ww else f"풍속 {wsd}m/s")
    else:
        add("wind", "강풍·태풍", "🌪️", "green", "특보 없음")

    if 5 <= month <= 9:            # 폭염철
        wh = _warn_level(warnings, ("폭염",))
        if wh == "경보" or tmax >= 35:
            add("heat", "폭염·열사", "🔥", "red", (wh + " 발효") if wh else f"최고 {tmax}°C")
        elif wh == "주의보" or tmax >= 33:
            add("heat", "폭염·열사", "🔥", "yellow", (wh + " 발효") if wh else f"최고 {tmax}°C")
        else:
            add("heat", "폭염·열사", "🔥", "green", f"최고 {tmax}°C")
    elif month >= 11 or month <= 3:   # 한파·대설철
        wc = _warn_level(warnings, ("한파", "대설"))
        if wc == "경보" or tmin <= -12:
            add("cold", "한파·대설", "❄️", "red", (wc + " 발효") if wc else f"최저 {tmin}°C")
        elif wc == "주의보" or tmin <= -9 or snowing:
            add("cold", "한파·대설", "❄️", "yellow", (wc + " 발효") if wc else ("강설" if snowing else f"최저 {tmin}°C"))
        else:
            add("cold", "한파·대설", "❄️", "green", f"최저 {tmin}°C")

    ls = risk.get("landslide", 0.3)
    if wf == "경보" and ls >= 0.4:
        add("landslide", "산사태", "⛰️", "red", "호우경보+위험지형")
    elif (raining or wf) and ls >= 0.4:
        add("landslide", "산사태", "⛰️", "yellow", "강수+급경사 지역")
    else:
        add("landslide", "산사태", "⛰️", "green", "징후 없음")

    eq = risk.get("earthquake", 0.4)
    if eq >= 0.8:
        add("earthquake", "지진", "🏚️", "yellow", "지역 상시 위험 높음(예보 불가)")
    else:
        add("earthquake", "지진", "🏚️", "green", "상시 대비(예보 불가)")

    g = (air or {}).get("pm25_grade") or (air or {}).get("pm10_grade")
    if g == 4:
        add("dust", "미세먼지", "🌫️", "red", "매우나쁨")
    elif g == 3:
        add("dust", "미세먼지", "🌫️", "yellow", "나쁨")
    else:
        add("dust", "미세먼지", "🌫️", "green", "보통 이하")

    return board


# ── 공개 API ──────────────────────────────────────────────────
def get_live_status(profile: dict | None, timeout: float = 10.0) -> dict:
    """주소(지역 프로파일) → 실시간 현황 카드 + 종합 신호등.

    반환: {region, grid_note, as_of, signal, cards[], any_live}
      cards[i] = {key, icon, label, value, sub, source('live'|'sample'), status_label}
    캐시: 저장값의 만료시각(expiry)까지 재사용. 실연동 성공은 오래(5분), 키가 있는데 실패는
    짧게(20초) 캐시해 일시적 API 지연 후 스스로 실데이터로 회복한다.
    """
    nx, ny, sido_name = _grid(profile)
    ck = (nx, ny, sido_name)
    now = time.time()
    hit = _cache.get(ck)
    if hit and now < hit[0]:
        return {**hit[1], "region": (profile or {}).get("label", "지역 미지정")}

    key = _api_key()
    weather = _fetch_weather(nx, ny, key, timeout) if key else None
    warnings = _fetch_warnings(key, timeout) if key else None
    air = _fetch_air(sido_name, key, timeout) if key else None

    w_src = "live" if weather else "sample"
    warn_src = "live" if warnings is not None else "sample"
    air_src = "live" if air else "sample"

    weather = weather or {"pop": 30, "pty": 0, "tmp_max": 26, "tmp_min": 18, "wsd": 2.0}
    warnings = warnings if warnings is not None else {"active": [], "top_level": ""}
    air = air or {"pm10_grade": 2, "pm25_grade": 2, "pm10_value": "35", "pm25_value": "18"}

    signal = _signal_of(weather if w_src == "live" else None,
                        warnings if warn_src == "live" else None,
                        air if air_src == "live" else None)

    def lab(src):
        return "실연동" if src == "live" else "데모 샘플"

    warn_txt = " · ".join(f"{a['kind']}{a['level']}" for a in warnings["active"]) or "발효 특보 없음"
    cards = [
        {"key": "temp", "icon": "🌡", "label": "기온", "value": f"{weather['tmp_min']}~{weather['tmp_max']}°C",
         "sub": "오늘 최저~최고", "source": w_src, "status_label": lab(w_src)},
        {"key": "rain", "icon": "🌧", "label": "강수", "value": f"{_PTY.get(weather['pty'], '없음')} · {weather['pop']}%",
         "sub": "형태 · 강수확률", "source": w_src, "status_label": lab(w_src)},
        {"key": "wind", "icon": "💨", "label": "풍속", "value": f"{weather['wsd']} m/s",
         "sub": "예보 풍속", "source": w_src, "status_label": lab(w_src)},
        {"key": "warn", "icon": "⚠", "label": "기상특보", "value": warn_txt,
         "sub": "전국 발효 현황(기상청)", "source": warn_src, "status_label": lab(warn_src)},
        {"key": "air", "icon": "🌫", "label": "미세먼지",
         "value": f"PM2.5 {_AIR_GRADE.get(air.get('pm25_grade'), '-')} · PM10 {_AIR_GRADE.get(air.get('pm10_grade'), '-')}",
         "sub": ("에어코리아 실시간" if air_src == "live" else "에어코리아(활용신청 시 실연동)"),
         "source": air_src, "status_label": (lab(air_src) if air_src == "live" else "연동 예정")},
    ]

    _now = _dt.datetime.now()
    as_of = _now.strftime("%m/%d %H:%M")
    board = disaster_board(weather, warnings, air, profile, _now.month)
    result = {
        "grid_note": f"{sido_name} 대표 관측지점 기준(시군구 정밀좌표 연동 시 상세화)",
        "as_of": as_of, "signal": signal, "cards": cards, "board": board,
        "board_live": any(c["source"] == "live" for c in cards),
        "any_live": any(c["source"] == "live" for c in cards),
        "has_key": key is not None,
    }
    # 키가 있는데 날씨·특보가 라이브로 안 왔으면 일시 실패 → 짧게 캐시해 곧 재시도(자가 회복)
    weather_ok = w_src == "live" and warn_src == "live"
    ttl = _TTL if (key is None or weather_ok) else 20.0
    _cache[ck] = (now + ttl, result)
    return {**result, "region": (profile or {}).get("label", "지역 미지정")}
