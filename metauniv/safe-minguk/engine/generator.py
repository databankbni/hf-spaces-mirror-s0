"""AI 맞춤 시나리오 생성기 — 기관 성격 + 재난 + 컨셉 → 그 기관에 맞춘 TTX 시나리오.

공모 부제 "최고의 재난안전 AI 프롬프트를 찾아서"의 정면 구현:
  사용자가 "○○연구원 / 화재"처럼 적으면 → 연구기관(연구장비·화학약품·실험실)을
  반영한 상황부여와 표준 대응요소를 생성하고, 기존 채점 엔진(ttx.score_elements)으로 훈련한다.

설계:
  · LLM 경로 — Claude 구조화 출력(tool use)으로 시나리오를 스키마에 맞춰 생성(키 있을 때).
  · 규칙 폴백 — 키 없으면 기관 유형×재난 템플릿을 조합해 초안 생성(0원 데모 유지, 정직 표기).
  · 생성된 시나리오는 disasters/*.json과 동일한 elements 스키마 → 결정론 채점 엔진이 그대로 채점.
  · 점수는 절대 LLM이 만들지 않는다(생성=상황·요소, 채점=엔진). 정직성 핵심 불변.
"""
from __future__ import annotations

import json
import re

from . import llm

# ── 기관 유형 프로파일: 텍스트 키워드 → 자산·취약군·특화 대응요소 ──
HAZARD_PROFILES = [
    (("연구원", "연구소", "연구기관", "실험실", "실험"),
     {"label": "연구기관", "assets": "연구장비·실험실·화학약품·고압가스",
      "vuln": "실험실 내 연구원·야간 소수 인원",
      "elem": {"key": "lab_hazmat", "desc": "실험실 화학약품·고압가스 등 위험물질 파악 및 유출·폭발 2차위험 차단",
               "keywords": ["화학", "약품", "가스", "실험실", "유출", "MSDS", "위험물"],
               "근거": "연구시설 특성상 유해화학물질·고압가스 2차재난 위험",
               "missing_action": "실험실 위험물질(가연·독성·고압가스) 위치 파악과 차단 조치가 누락됨",
               "recommendation": "MSDS 기반 위험물질 목록으로 화기·전원 차단과 유출 대비를 초동에 포함"}}),
    (("병원", "의료", "요양", "보건소"),
     {"label": "의료·요양시설", "assets": "입원·거동불편 환자, 의료가스, 전원 의존 장비",
      "vuln": "자력 대피 불가 환자·고령자",
      "elem": {"key": "patient_evac", "desc": "거동불편 환자·전원의존 장비 환자의 우선 대피·이송 계획",
               "keywords": ["환자", "거동", "이송", "병상", "산소", "의료진", "우선대피"],
               "근거": "의료·요양시설은 자력대피 불가군이 다수",
               "missing_action": "거동불편·전원의존 환자의 우선 대피·이송 계획이 누락됨",
               "recommendation": "병상·중환자 우선순위와 이송 수단·수용 병원을 사전 지정"}}),
    (("학교", "대학", "유치원", "어린이집"),
     {"label": "교육시설", "assets": "다수 학생·교직원, 급식·실습실",
      "vuln": "저연령·다수 밀집 인원",
      "elem": {"key": "student_evac", "desc": "학생 인원 확인(점호)·질서 있는 대피 유도 및 학부모 연락체계",
               "keywords": ["학생", "점호", "인원확인", "대피유도", "학부모", "교직원"],
               "근거": "다수 밀집·저연령으로 인원확인과 질서 대피가 관건",
               "missing_action": "학생 인원 점호·질서 대피 유도가 누락됨",
               "recommendation": "학급별 인솔·집결지 점호·학부모 통지 체계를 초동에 가동"}}),
    (("공장", "제조", "산업단지", "플랜트", "발전"),
     {"label": "산업·제조시설", "assets": "생산설비·유해물질·고온고압 공정",
      "vuln": "공정 작업자·협력업체 인원",
      "elem": {"key": "process_shutdown", "desc": "위험공정 비상정지·유해물질 차단 및 작업자 대피",
               "keywords": ["공정", "정지", "차단", "설비", "유해물질", "작업자", "비상정지"],
               "근거": "제조공정 특성상 비상정지·유해물질 차단이 2차재난 좌우",
               "missing_action": "위험공정 비상정지·유해물질 차단 조치가 누락됨",
               "recommendation": "공정 비상정지 절차와 밸브·전원 차단을 초동 우선순위로 배치"}}),
    (("관공서", "청사", "시청", "구청", "센터", "공공기관"),
     {"label": "공공청사", "assets": "민원인·직원, 전산실·중요기록물",
      "vuln": "불특정 다수 민원인",
      "elem": {"key": "visitor_evac", "desc": "불특정 민원인 안내·대피 유도 및 중요기록·전산 보호",
               "keywords": ["민원인", "안내", "대피유도", "기록물", "전산", "직원"],
               "근거": "공공청사는 불특정 다수 민원인 안전과 기록물 보호가 병행",
               "missing_action": "민원인 대피 유도 및 중요기록·전산 보호가 누락됨",
               "recommendation": "층별 안내인력으로 민원인 대피를 유도하고 전산실 보호를 병행"}}),
]
_DEFAULT_PROFILE = {"label": "일반 기관·시설", "assets": "상주 인원·주요 설비",
                    "vuln": "상주 인원", "elem": None}

# ── 재난 유형 템플릿: 키워드 → 라벨·아이콘·공통 표준 대응요소·모범답안 ──
_COMMON = [
    {"key": "situation", "desc": "초기 상황 판단·비상연락 및 재난문자·유관기관 전파",
     "weight": 20, "keywords": ["119", "신고", "전파", "비상", "재난문자", "보고", "상황실"],
     "근거": "위기관리 표준매뉴얼 초동 상황전파", "missing_action": "초기 상황전파·비상연락 체계 가동이 누락됨",
     "recommendation": "119 신고·내부 비상연락·유관기관 전파를 동시에 초동에 가동"},
    {"key": "life_safety", "desc": "인명 우선 보호 — 재실자 대피·인원 확인·구조 요청",
     "weight": 30, "keywords": ["대피", "인명", "인원확인", "구조", "대피로", "피난"],
     "근거": "인명보호 최우선 원칙", "missing_action": "재실자 대피·인원 확인 등 인명보호 조치가 누락됨",
     "recommendation": "대피 유도·인원 점검·미확인자 구조 요청을 최우선으로 배치"},
    {"key": "scene_control", "desc": "현장 통제·2차 피해 차단(접근통제·위험요소 제거)",
     "weight": 20, "keywords": ["통제", "차단", "접근", "2차", "확산", "격리"],
     "근거": "2차 재난 차단", "missing_action": "현장 통제·2차 피해 차단 조치가 누락됨",
     "recommendation": "위험구역 접근통제와 확산 차단을 초동에 병행"},
    {"key": "report_coord", "desc": "상황 보고·기록 및 유관기관(소방·경찰·지자체) 공조 요청",
     "weight": 15, "keywords": ["보고", "기록", "소방", "경찰", "공조", "지원요청", "협조"],
     "근거": "지휘체계·유관기관 공조", "missing_action": "상황 보고·유관기관 공조 요청이 누락됨",
     "recommendation": "지휘부 보고와 소방·경찰·지자체 공조를 명시적으로 요청"},
]
DISASTER_TEMPLATES = {
    "화재": {"label": "화재", "icon": "🔥", "hazard": "화재·연기 확산",
             "inject": "{org} 건물에서 화재가 발생했습니다. {assets} 주변으로 연기가 확산 중이며 재실자 일부가 미대피 상태입니다.",
             "model": "① 119 신고·비상방송·재난문자 전파 ② 재실자 대피 유도·인원 점호·미확인자 구조요청 "
                      "③ 방화문 폐쇄·전원/가스 차단으로 확산·2차폭발 차단 ④ 소방 도착 시 위험물·구조 위치 인계·지휘부 보고"},
    "화학": {"label": "화학사고", "icon": "🧪", "hazard": "유해화학물질 누출",
             "inject": "{org}에서 화학물질 누출이 발생했습니다. {assets} 인근으로 유해가스가 퍼지고 있습니다.",
             "model": "① 누출물질 확인(MSDS)·119신고·경보전파 ② 풍상측 대피·실내대피 판단·인원확인 "
                      "③ 밸브차단·확산방지·오염구역 접근통제 ④ 화학구조대·환경당국 공조·상황보고"},
    "지진": {"label": "지진", "icon": "🏚️", "hazard": "건물 손상·여진",
             "inject": "규모 있는 지진으로 {org} 건물이 흔들렸습니다. 일부 구조물 손상과 낙하물이 발생했습니다.",
             "model": "① 흔들림 중 낙하물 대비·진정 후 대피·인원확인 ② 가스·전기 차단으로 2차재난 차단 "
                      "③ 붕괴위험 구역 접근통제·부상자 응급 ④ 여진 대비 개활지 집결·상황보고·유관기관 공조"},
    "침수": {"label": "도시침수", "icon": "🌊", "hazard": "침수·정전",
             "inject": "집중호우로 {org} 일대가 침수되고 있습니다. 지하공간·저층부 침수와 정전이 우려됩니다.",
             "model": "① 지하·저지대 통제·재실자 상층 대피·인원확인 ② 전기·기계실 차단으로 감전·2차피해 방지 "
                      "③ 배수·모래주머니 등 침수 저지·접근통제 ④ 상황보고·지자체/소방 공조"},
    "정전": {"label": "정전·설비장애", "icon": "🔌", "hazard": "전원 상실",
             "inject": "{org}에 광역 정전이 발생했습니다. {assets}의 전원 의존 설비가 정지 위험에 있습니다.",
             "model": "① 비상발전·UPS 가동·중요설비 우선 전원 확보 ② 승강기 갇힘·암전 구역 인명확인 "
                      "③ 전원의존 위험설비 안전정지·2차피해 차단 ④ 한전·유관기관 공조·복구·상황보고"},
    "인파": {"label": "다중밀집 인파사고", "icon": "👥", "hazard": "밀집·압사 위험",
             "inject": "{org} 행사장에 인파가 급격히 몰려 밀집도가 위험 수준입니다. 압사·전도 위험이 커지고 있습니다.",
             "model": "① 유입 차단·일방통행 유도·밀집구역 분산 ② 방송으로 진정·대피로 안내·인원흐름 통제 "
                      "③ 전도·부상자 즉시 구조·응급의료 ④ 경찰·소방 공조·상황보고"},
}
_DISASTER_ALIASES = {"불": "화재", "가스": "화학", "누출": "화학", "약품": "화학", "홍수": "침수",
                     "호우": "침수", "폭우": "침수", "단전": "정전", "압사": "인파", "군중": "인파"}


def _match_profile(institution: str) -> dict:
    t = (institution or "").lower()
    for keys, prof in HAZARD_PROFILES:
        if any(k.lower() in t for k in keys):
            return prof
    return _DEFAULT_PROFILE


def _match_disaster(text: str) -> str:
    for k in DISASTER_TEMPLATES:
        if k in text:
            return k
    for alias, k in _DISASTER_ALIASES.items():
        if alias in text:
            return k
    return "화재"


def _rule_scenario(institution: str, disaster_text: str, concept: str) -> dict:
    """규칙 기반 초안 — 기관 프로파일 × 재난 템플릿 조합(0원, 키 불필요)."""
    org = (institution or "우리 기관").strip()
    prof = _match_profile(institution)
    dkey = _match_disaster((disaster_text or "") + " " + (concept or ""))
    tpl = DISASTER_TEMPLATES[dkey]

    elements = [dict(e) for e in _COMMON]
    if prof.get("elem"):
        e = dict(prof["elem"]); e["weight"] = 15
        elements.insert(2, e)   # 인명보호 다음에 기관 특화 요소
    # weight 정규화(합 100 근처로)
    total = sum(e["weight"] for e in elements)
    for e in elements:
        e["weight"] = round(e["weight"] * 100 / total)

    concept_note = f" 특히 '{concept.strip()}' 상황을 가정합니다." if concept and concept.strip() else ""
    inject = tpl["inject"].format(org=org, assets=prof["assets"]) + concept_note
    return {
        "source": "rule",
        "title": f"{org} {tpl['label']} 대응",
        "icon": tpl["icon"],
        "role": f"당신은 {org}의 재난안전 상황총괄 담당입니다.",
        "disaster_label": tpl["label"],
        "profile_label": prof["label"],
        "stage": {
            "title": f"{tpl['label']} 초기 대응",
            "clock": "발생 직후",
            "inject": inject,
            "task": "재난안전 담당자로서 초기 대응방안을 우선순위대로 서술하세요(상황전파·인명보호·현장통제·공조).",
            "elements": elements,
            "model_answer": tpl["model"],
        },
    }


# ── LLM 생성(Claude 구조화 출력) ──────────────────────────────
_GEN_TOOL = {
    "name": "emit_scenario",
    "description": "기관 성격·재난·컨셉에 맞춘 재난대응 도상훈련(TTX) 시나리오와 표준 대응요소를 생성한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "훈련명(기관+재난)"},
            "icon": {"type": "string", "description": "재난 이모지 1개"},
            "role": {"type": "string", "description": "참가자 역할(그 기관 담당)"},
            "disaster_label": {"type": "string"},
            "profile_label": {"type": "string", "description": "기관 유형 요약"},
            "stage": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "inject": {"type": "string", "description": "구체적 상황부여(그 기관의 자산·취약군 반영, 3~5문장)"},
                    "task": {"type": "string", "description": "참가자에게 주는 지시"},
                    "model_answer": {"type": "string", "description": "표준매뉴얼 기준 모범 대응(번호 매겨 4개 내외)"},
                    "elements": {
                        "type": "array", "description": "표준 대응요소 4~6개",
                        "items": {"type": "object", "properties": {
                            "key": {"type": "string"},
                            "desc": {"type": "string", "description": "표준 대응요소 설명"},
                            "weight": {"type": "integer", "description": "배점(합 100 권장). 인명보호 최고배점"},
                            "keywords": {"type": "array", "items": {"type": "string"},
                                         "description": "이 요소 반영을 판정할 핵심 키워드 3~6"},
                            "근거": {"type": "string", "description": "표준매뉴얼상 근거 한 줄"},
                            "missing_action": {"type": "string"},
                            "recommendation": {"type": "string"},
                        }, "required": ["key", "desc", "weight", "keywords"]},
                    },
                },
                "required": ["title", "inject", "task", "elements", "model_answer"],
            },
        },
        "required": ["title", "role", "stage"],
    },
}
_GEN_SYSTEM = """\
당신은 재난대응 도상훈련(TTX) 시나리오 설계자다.
- 입력된 기관의 성격(자산·취약군·업무 특성)과 재난 유형·컨셉을 반영해 현실적인 상황부여를 만든다.
- 표준 대응요소는 행정안전부 위기관리 표준매뉴얼의 정신(초기전파·인명보호 최우선·현장통제·2차피해차단·유관기관 공조)을 따른다.
- 없는 규정·수치를 지어내지 않는다. 인명보호 요소에 최고 배점을 둔다. 한국어로.
"""


def _llm_scenario(institution: str, disaster_text: str, concept: str) -> dict | None:
    try:
        import anthropic
        payload = {"기관": institution, "재난": disaster_text, "컨셉": concept or "(지정 없음)"}
        client = anthropic.Anthropic(api_key=llm._anthropic_key())
        resp = client.messages.create(
            model=llm.MODEL, max_tokens=1600, system=_GEN_SYSTEM,
            tools=[_GEN_TOOL], tool_choice={"type": "tool", "name": "emit_scenario"},
            messages=[{"role": "user", "content":
                       "아래 조건에 맞춘 TTX 시나리오를 생성하라.\n" + json.dumps(payload, ensure_ascii=False)}],
        )
        blk = next(b for b in resp.content if b.type == "tool_use")
        data = dict(blk.input)
        st = data.get("stage", {})
        if not st.get("elements"):
            return None
        for i, e in enumerate(st["elements"]):
            e.setdefault("key", f"e{i}")
            e.setdefault("weight", 100 // len(st["elements"]))
            e.setdefault("keywords", [])
        data["source"] = "ai"
        data.setdefault("icon", "⚠")
        st.setdefault("clock", "발생 직후")
        return data
    except Exception:  # noqa: BLE001
        return None


def generate(institution: str, disaster_text: str, concept: str = "", use_llm: bool = True) -> dict:
    """기관·재난·컨셉 → 맞춤 TTX 시나리오. 키 있으면 AI 생성, 없으면 규칙 초안."""
    if use_llm and llm.has_key():
        sc = _llm_scenario(institution, disaster_text, concept)
        if sc:
            return sc
    return _rule_scenario(institution, disaster_text, concept)
