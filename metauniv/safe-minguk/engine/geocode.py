"""도로명주소 지오코딩 — juso.go.kr 도로명주소 API.

법정동 매칭은 주소에 '시군구·동' 글자가 있어야 동작한다. 도로명주소(예: '양대기로길 89')는
그 글자가 없어 매칭이 안 되므로, 행정안전부 juso.go.kr 도로명주소 API로 시군구를 해석한다.

키: 무료 발급(https://www.juso.go.kr/addrlink/openApi/apiReqstMng.do).
   환경변수 JUSO_KEY 또는 .streamlit/secrets.toml의 [juso] confmKey / JUSO_KEY 로 설정.
키가 없으면 None을 반환해 기존 폴백(법정동 매칭/일반 시나리오)이 그대로 동작한다(0원 모드 유지).
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

API = "https://www.juso.go.kr/addrlink/addrLinkApi.do"


@lru_cache(maxsize=1)
def _key() -> str | None:
    k = os.environ.get("JUSO_KEY")
    if k:
        return k
    try:
        import tomllib
        for cand in (Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml",):
            if cand.exists():
                data = tomllib.loads(cand.read_text(encoding="utf-8"))
                k = data.get("JUSO_KEY") or data.get("juso", {}).get("confmKey")
                if k:
                    return k
    except Exception:  # noqa: BLE001
        pass
    return None


def has_key() -> bool:
    return bool(_key())


@lru_cache(maxsize=512)
def road_lookup(address: str) -> dict | None:
    """도로명주소 → {sido, sigungu, emd, road, jibun, full}. 키 없거나 실패 시 None."""
    key = _key()
    if not key or not address.strip():
        return None
    qs = urllib.parse.urlencode({
        "confmKey": key, "currentPage": 1, "countPerPage": 1,
        "keyword": address, "resultType": "json",
    })
    try:
        with urllib.request.urlopen(f"{API}?{qs}", timeout=6) as r:
            data = json.loads(r.read().decode("utf-8"))
        res = data.get("results", {})
        if res.get("common", {}).get("errorCode") != "0":
            return None
        juso = res.get("juso") or []
        if not juso:
            return None
        j = juso[0]
        return {
            "sido": j.get("siNm", ""), "sigungu": j.get("sggNm", ""),
            "emd": j.get("emdNm", ""), "road": j.get("rn", ""),
            "jibun": j.get("jibunAddr", ""), "full": j.get("roadAddr", ""),
        }
    except Exception:  # noqa: BLE001
        return None
