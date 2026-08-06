"""공통 유틸 — 입력 안전화·간단 로깅. 보안(XSS 차단)·복원력의 단일 지점.

원칙: 사용자 자유입력(주소·기관명·컨셉 등)은 화면에 되비추기 전에 반드시 안전화한다.
프런트가 innerHTML로 렌더하므로, HTML 특수문자(<,>,")를 제거해 태그 주입을 원천 차단한다.
"""
from __future__ import annotations

import logging
import re

_HTML_CHARS = re.compile(r'[<>"\x00-\x08\x0b\x0c\x0e-\x1f]')


def sanitize_text(s: str | None, maxlen: int = 200) -> str:
    """사용자 자유입력 안전화 — HTML 특수문자·제어문자 제거 + 길이 제한.

    한글 주소·기관명엔 <,>,"가 쓰이지 않으므로 제거해도 무해하며, XSS·레이아웃 깨짐을 원천 차단한다.
    """
    s = (s or "").strip()
    if len(s) > maxlen:
        s = s[:maxlen]
    return _HTML_CHARS.sub("", s)


def get_logger(name: str = "safeminguk") -> logging.Logger:
    """관측성용 최소 로거(핸들러 중복 방지). 요청·오류를 한 줄로 남긴다."""
    lg = logging.getLogger(name)
    if not lg.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s"))
        lg.addHandler(h)
        lg.setLevel(logging.INFO)
        lg.propagate = False
    return lg
