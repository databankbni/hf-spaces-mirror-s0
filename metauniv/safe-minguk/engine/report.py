"""훈련 결과보고서 생성 — 훈련 결과를 공무원 실무 산출물(평가보고서)로 변환.

목적: 훈련이 게임 점수표로 끝나지 않고, 결과보고서·취약점 분석·사전교육 자료로 이어지게 한다.
설계:
  · 순수 함수 — 결과 데이터(sim.replay 결과 또는 ttx 단계별 평가)를 받아 {html, summary, weaknesses, next_training} 반환.
  · HTML은 인쇄 가능(자체완결 인라인 CSS). 문체는 게임 점수표가 아니라 '공무원 보고서' 어투.
  · 지역 재난안전데이터 브리핑·표준매뉴얼 채점·AI 평가관 강평을 한 문서로 묶는다.
"""
from __future__ import annotations

import html as _html

from . import eval_map

TITLE = "안전민국 AI 재난훈련 결과보고서"
_G5_COLOR = {"매우우수": "#0a7d43", "우수": "#1b6bb8", "보통": "#a9791b",
             "미흡": "#c0392b", "매우미흡": "#8a1c1c"}
_LV = {"full": "충실 반영", "partial": "부분 반영", "none": "미반영"}
_LV_COLOR = {"full": "#0a7d43", "partial": "#a9791b", "none": "#c0392b"}


def _e(x) -> str:
    return _html.escape(str(x if x is not None else ""))


def _next_training(disaster_name: str, region_label: str) -> list[str]:
    return [
        f"같은 지역({region_label})으로 다른 변형 시나리오를 재훈련해 대응 일관성을 점검",
        f"{disaster_name} 도상훈련(TTX)과 상황실 시뮬을 교차 실시해 서술·실시간 판단을 모두 훈련",
        "동일 엔진의 확장 모듈(지진·화학사고)로 다른 재난 유형 대응력 확대",
    ]


def _sim_weaknesses(result: dict) -> list[dict]:
    """sim 결과 → 미흡 대응요소 TOP 3(악화>지연 순)."""
    order = {"wrong": 0, "partial": 1}
    rows = [t for t in result.get("threats_review", []) if t.get("rubric") != "correct"]
    rows.sort(key=lambda t: order.get(t.get("rubric"), 2))
    out = []
    for t in rows[:3]:
        out.append({
            "label": t.get("label", ""),
            "why": ("골든타임 내 미해결로 상황이 악화됐습니다." if t.get("escalated")
                    else "대응은 했으나 골든타임을 넘겨 지연됐습니다."),
            "standard": t.get("standard", ""),
            "improve": f"다음 훈련에서는 '{t.get('standard','')}'을(를) 우선순위 앞단에 배치해야 합니다.",
        })
    return out


def _ttx_weaknesses(stages: list[dict]) -> list[dict]:
    """ttx 단계별 평가 → 미흡 대응요소 TOP 3(가중치 높은 미반영·부분 우선)."""
    cand = []
    for si, ev in enumerate(stages):
        for el in ev.get("elements", []):
            if el.get("level") == "full":
                continue
            cand.append({
                "label": el.get("desc", ""),
                "weight": el.get("weight", 0),
                "level": el.get("level", "none"),
                "why": ("표준 대응요소로 명시돼 있으나 답안에 반영되지 않았습니다."
                        if el.get("level") == "none" else "일부만 반영돼 보완이 필요합니다."),
                "improve": el.get("recommendation") or el.get("missing_action") or "",
            })
    # 미반영(none) 먼저, 그다음 가중치 큰 순
    cand.sort(key=lambda x: (x["level"] != "none", -x["weight"]))
    return cand[:3]


# P3 · 개선과제 도출(환류) — 안전한국훈련 평가지표 3-1. 미흡 대응요소를 '유형·담당·조치'로 구조화한
# 개선과제로 전환해 훈련이 실제 제도·시설·교육 개선으로 환류되게 한다. 분류는 키워드 기반(지어내지 않음).
_IMPROVE_RULES = [
    (("통제", "차단", "도로", "지하차도", "진입"), "시설·장비",
     "도로·교통 부서", "선제 통제 기준과 차단시설(진입차단기·통제라인)을 정비한다"),
    (("배수", "펌프", "정전", "전원", "한전", "저지대"), "시설·장비",
     "하천·방재시설 부서", "배수펌프장 비상전원과 이동식 펌프를 확보하고 정전 대비를 점검한다"),
    (("대피", "방송", "전파", "재난문자", "통반장", "주민", "취약"), "교육·훈련",
     "안전총괄 부서", "취약계층 대피 유도 절차와 주민 전파 체계를 반복 훈련한다"),
    (("유관", "협조", "공동", "소방", "경찰", "협력", "군"), "협업·체계",
     "재난상황실", "유관기관 공동대응 매뉴얼과 비상연락 체계를 정비한다"),
    (("본부", "가동", "보고", "지휘", "판단", "회의"), "제도·매뉴얼",
     "안전총괄 부서", "상황판단회의·대책본부 가동 기준을 명확화한다"),
]


def _classify_improve(text: str) -> tuple[str, str, str]:
    for kws, typ, dept, action in _IMPROVE_RULES:
        if any(k in text for k in kws):
            return typ, dept, action
    return "제도·매뉴얼", "안전총괄 부서", "표준행동매뉴얼을 반영해 재난대응 절차를 보완한다"


def _improvement_tasks(weaknesses: list[dict]) -> list[dict]:
    """미흡 대응요소 → 개선과제(환류). 유형·담당·조치·근거로 구조화, 중복 제거."""
    tasks, seen = [], set()
    for w in weaknesses:
        text = f"{w.get('label','')} {w.get('standard','') or w.get('improve','')}"
        typ, dept, action = _classify_improve(text)
        task = (w.get("improve") or "").strip() or action
        key = (typ, task)
        if key in seen:
            continue
        seen.add(key)
        tasks.append({"task": task, "type": typ, "dept": dept,
                      "basis": w.get("label", ""), "term": "차기 훈련 전까지"})
    return tasks


def _indicator_table(stages: list[dict]) -> tuple[str, list]:
    """단계별 평가지표 대조를 합쳐 '공식 평가지표별 획득 등급' 표 HTML + 원자료 반환."""
    merged = eval_map.merge([s.get("indicators", []) for s in stages])
    if not merged:
        return "", []
    rows = []
    for m in merged:
        col = _G5_COLOR.get(m["grade"], "#555")
        code = _e(m["code"].replace("-INMYEONG", "·인명").replace("-SUSEUP", "·수습"))
        miss = f"<br><span class='muted'>보완: {_e(' · '.join(m['missed']))}</span>" if m.get("missed") else ""
        rows.append(
            f"<tr><td class='ic'>{code}</td><td><b>{_e(m['title'])}</b>{miss}</td>"
            f"<td style='text-align:center'><span class='g5' style='background:{col}'>{_e(m['grade'])} {m['grade_score']}점</span></td>"
            f"<td class='muted'>{_e(m['grade_desc'])}</td></tr>")
    html = ("<table class='grid'><tr><th>지표</th><th>평가지표 항목</th><th>획득 등급</th><th>등급 기준</th></tr>"
            + "".join(rows) + "</table>")
    return html, merged


def _briefing_rows(briefing: dict) -> str:
    items = (briefing or {}).get("briefing_items", [])
    if not items:
        return "<tr><td colspan='3' class='muted'>해당 지역의 정밀 브리핑 데이터가 없어 일반 시나리오로 진행했습니다.</td></tr>"
    rows = []
    for it in items:
        src = it.get("source") or {}
        srctxt = f"{_e(src.get('name',''))} · {_e(src.get('provider',''))} · <b>{_e(src.get('status_label','데모 샘플'))}</b>" if src else "—"
        rows.append(
            f"<tr><td><b>{_e(it.get('title',''))}</b><br><span class='muted'>{_e(it.get('value',''))}</span></td>"
            f"<td>{_e(it.get('description',''))}</td><td class='src'>{srctxt}</td></tr>")
    return "".join(rows)


def _flags_line(briefing: dict) -> str:
    active = (briefing or {}).get("active_flags", [])
    if not active:
        return "일반 시나리오(지역 위험플래그 미확인)"
    return " · ".join(_e(a) for a in active)


def _ai_table_sim(result: dict) -> str:
    rows = []
    for t in result.get("threats_review", []):
        lv = "full" if t.get("rubric") == "correct" else ("partial" if t.get("rubric") == "partial" else "none")
        judge = {"full": "적절", "partial": "부분", "none": "미흡"}[lv]
        rows.append(
            f"<tr><td>{_e(t.get('label',''))}</td>"
            f"<td><span class='j' style='color:{_LV_COLOR[lv]}'>{judge}</span></td>"
            f"<td>{_e(t.get('why',''))}</td>"
            f"<td>{'' if lv=='full' else _e(t.get('standard',''))}</td></tr>")
    return "".join(rows) or "<tr><td colspan='4' class='muted'>기록 없음</td></tr>"


def _ai_table_ttx(stages: list[dict]) -> str:
    rows = []
    for si, ev in enumerate(stages):
        rows.append(f"<tr class='stg'><td colspan='5'>상황 {si+1} · {_e(ev.get('title',''))} "
                    f"— {_e(ev.get('score',0))}/100 ({_e(ev.get('grade',''))})</td></tr>")
        for el in ev.get("elements", []):
            lv = el.get("level", "none")
            rows.append(
                f"<tr><td>{_e(el.get('desc',''))} <span class='muted'>({_e(el.get('weight',0))}점)</span></td>"
                f"<td><span class='j' style='color:{_LV_COLOR.get(lv,'#555')}'>{_LV.get(lv,lv)}</span></td>"
                f"<td>{_e(el.get('reason',''))}</td>"
                f"<td>{_e(el.get('missing_action',''))}</td>"
                f"<td>{_e(el.get('recommendation',''))}</td></tr>")
    return "".join(rows)


def _region_reflection_block(stages: list[dict]) -> str:
    seen, items = set(), []
    for ev in stages:
        for r in (ev.get("region_reflection") or []):
            if r["flag"] in seen:
                continue
            seen.add(r["flag"])
            mark = "✔ 반영" if r.get("reflected") else "✘ 미반영"
            color = "#0a7d43" if r.get("reflected") else "#c0392b"
            items.append(f"<li><b style='color:{color}'>{mark}</b> {_e(r.get('label',''))} — {_e(r.get('advice',''))}</li>")
    if not items:
        return ""
    return ("<div class='sec'><h2>지역 재난안전데이터 반영도</h2>"
            "<p class='muted'>답안이 이 지역의 실제 위험요소(브리핑)를 반영했는지 점검한 결과입니다.</p>"
            f"<ul class='ref'>{''.join(items)}</ul></div>")


CSS = """
*{box-sizing:border-box} body{margin:0;background:#f4f6f9;color:#1a2230;
 font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;line-height:1.7;word-break:keep-all}
.doc{max-width:900px;margin:24px auto;background:#fff;padding:44px 48px;
 box-shadow:0 2px 18px rgba(0,0,0,.08);border-radius:4px}
.rpt-head{border-bottom:3px solid #1b3a6b;padding-bottom:16px;margin-bottom:8px}
.rpt-head .k{font-size:12px;color:#1b6bb8;font-weight:800;letter-spacing:.04em}
.rpt-head h1{font-size:25px;margin:6px 0 2px;font-weight:900;color:#12203a}
.rpt-head .pos{font-size:13px;color:#5a6577}
.meta{width:100%;border-collapse:collapse;margin:18px 0 6px;font-size:13.5px}
.meta td{border:1px solid #d7dee8;padding:8px 12px}
.meta td.h{background:#eef3f9;font-weight:700;width:130px;color:#33445e}
.sec{margin:26px 0}
.sec h2{font-size:16px;font-weight:800;color:#12203a;border-left:4px solid #1b6bb8;
 padding-left:10px;margin:0 0 10px}
.sec p{font-size:14px;margin:6px 0}
table.grid{width:100%;border-collapse:collapse;font-size:13px}
table.grid th{background:#1b3a6b;color:#fff;padding:9px 10px;text-align:left;font-weight:700}
table.grid td{border:1px solid #dbe2ec;padding:9px 10px;vertical-align:top}
table.grid tr.stg td{background:#eef3f9;font-weight:800;color:#22406e}
.j{font-weight:800}
.tag{display:inline-block;color:#fff;font-weight:800;font-size:11px;padding:3px 9px;border-radius:20px;white-space:nowrap}
.g5{display:inline-block;color:#fff;font-weight:900;font-size:12px;padding:3px 11px;border-radius:20px;white-space:nowrap}
td.ic{font-weight:800;color:#22406e;white-space:nowrap;font-size:12px}
.muted{color:#7b8698;font-size:12.5px}
.src{font-size:11.5px;color:#5a6577}
.scorebar{display:flex;gap:12px;margin:6px 0}
.scorebar .b{flex:1;border:1px solid #d7dee8;border-radius:8px;padding:14px;text-align:center}
.scorebar .b .n{font-size:28px;font-weight:900} .scorebar .b .l{font-size:12px;color:#5a6577}
.grade{display:inline-block;font-weight:900;padding:5px 16px;border-radius:20px;font-size:15px}
ul.wk{margin:6px 0;padding-left:0;list-style:none}
ul.wk li{border:1px solid #e6d3d3;background:#fbf4f4;border-radius:8px;padding:11px 14px;margin:8px 0}
ul.wk li b{color:#b23b3b} ul.wk li .imp{color:#22406e;font-weight:700;margin-top:3px;display:block}
ul.ref{padding-left:2px;list-style:none} ul.ref li{margin:6px 0;font-size:13.5px}
ol.nx{margin:6px 0;padding-left:20px} ol.nx li{margin:6px 0;font-size:13.5px}
.note{background:#eef3f9;border:1px solid #cdddef;border-radius:8px;padding:12px 15px;font-size:13px;color:#2a3d5c;margin-top:8px}
.foot{margin-top:30px;padding-top:14px;border-top:1px solid #dbe2ec;font-size:11.5px;color:#8390a3}
@media print{body{background:#fff}.doc{box-shadow:none;margin:0;max-width:none;padding:20px}.noprint{display:none}}
.pbtn{position:fixed;top:16px;right:16px;background:#1b6bb8;color:#fff;border:0;padding:10px 18px;
 border-radius:8px;font-weight:800;cursor:pointer;font-size:13px}
"""


def build(ctx: dict) -> dict:
    """훈련 결과보고서 생성.

    ctx = {
      mode: "sim"|"ttx",
      disaster: {name, icon, context, source_manuals[]},
      region: {label, org},
      when: "YYYY-MM-DD HH:MM" (표시용, 없으면 생략),
      briefing: safety_data.get_local_disaster_briefing 결과,
      sim: sim.replay 결과(mode=sim일 때),
      ttx: {stages:[평가...], summary:{avg, scores[]}} (mode=ttx일 때),
    }
    반환: {html, summary, weaknesses, next_training}
    """
    mode = ctx.get("mode", "sim")
    dz = ctx.get("disaster", {})
    reg = ctx.get("region", {})
    briefing = ctx.get("briefing", {})
    region_label = reg.get("label", "지역 미지정")
    org = reg.get("org", "")
    when = ctx.get("when", "")
    role = ctx.get("role", "")
    manuals = dz.get("source_manuals", [])
    mode_label = "상황실 시뮬레이션" if mode == "sim" else "도상훈련(TTX)"

    if mode == "sim":
        res = ctx.get("sim", {})
        dec, out, tot = res.get("decision_score", 0), res.get("outcome_score", 0), res.get("total", 0)
        grade = res.get("grade", "")
        state = res.get("state", {})
        weaknesses = _sim_weaknesses(res)
        ai_table = (
            "<table class='grid'><tr><th>표준 대응요소</th><th>AI 판정</th><th>판정 근거</th><th>표준 조치</th></tr>"
            + _ai_table_sim(res) + "</table>")
        scenario = (f"<p>초기 상황: {_e(res.get('intro') or dz.get('context',''))}</p>"
                    f"<p class='muted'>변형: {_e(res.get('variant_label',''))}</p>")
        result_metrics = (f"인명피해 {state.get('인명피해',0)} · 구조 {state.get('구조',0)} · "
                          f"주민혼란 {state.get('주민혼란',0)} · 재산피해 {state.get('재산피해',0)}")
        region_ref_block = ""
        indicator_html = ""
    else:
        tt = ctx.get("ttx", {})
        stages = tt.get("stages", [])
        summ = tt.get("summary", {})
        dec = out = 0
        tot = summ.get("avg", 0)
        grade = summ.get("grade", "")
        weaknesses = _ttx_weaknesses(stages)
        ai_table = (
            "<table class='grid'><tr><th>표준 대응요소</th><th>AI 판정</th><th>판정 근거</th>"
            "<th>누락된 행동</th><th>개선 권고</th></tr>" + _ai_table_ttx(stages) + "</table>")
        scenario = "".join(
            f"<p><b>상황 {i+1}.</b> {_e(s.get('title',''))} — 평가 {_e(s.get('score',0))}/100</p>"
            for i, s in enumerate(stages))
        result_metrics = f"{len(stages)}개 상황부여 평균 {tot}점 · 단계별 " + \
            " · ".join(f"{_e(s.get('score',0))}점" for s in stages)
        region_ref_block = _region_reflection_block(stages)
        indicator_html, _merged = _indicator_table(stages)

    gcolor = "#0a7d43" if tot >= 85 else "#1b6bb8" if tot >= 70 else "#a9791b" if tot >= 55 else "#c0392b"

    improvement_tasks = _improvement_tasks(weaknesses)   # P3 환류(3-1)

    # 종합 요약 문장(발표·계획서용)
    summary = (
        f"본 훈련은 {mode_label} 방식으로 {region_label}의 {dz.get('name','재난')} 상황을 가정해 실시했으며, "
        f"지역 재난안전데이터 브리핑({_flags_line(briefing)})을 반영해 시나리오를 구성했다. "
        f"행정안전부 표준매뉴얼 기준 종합 {tot}점({grade})으로 평가됐고, "
        f"미흡 대응요소 {len(weaknesses)}건에서 개선과제 {len(improvement_tasks)}건을 도출해 환류하였다.")

    weak_html = "".join(
        f"<li><b>{i+1}. {_e(w['label'])}</b> — {_e(w['why'])}"
        f"<span class='imp'>↳ 개선: {_e(w['improve'])}</span></li>"
        for i, w in enumerate(weaknesses)) or "<li class='muted'>미흡 대응요소가 없습니다. 표준매뉴얼대로 대응했습니다.</li>"

    _TYPE_COLOR = {"시설·장비": "#1b6bb8", "교육·훈련": "#0a7d43",
                   "협업·체계": "#8a4fc4", "제도·매뉴얼": "#a9791b"}
    improve_html = "".join(
        f"<tr><td><span class='tag' style='background:{_TYPE_COLOR.get(t['type'],'#5a6577')}'>{_e(t['type'])}</span></td>"
        f"<td>{_e(t['task'])}<br><span class='muted'>도출 근거: {_e(t['basis'])}</span></td>"
        f"<td>{_e(t['dept'])}</td><td>{_e(t['term'])}</td></tr>"
        for t in improvement_tasks) or (
        "<tr><td colspan='4' class='muted'>미흡 요소가 없어 별도 개선과제가 도출되지 않았습니다. 현 대응수준을 유지합니다.</td></tr>")

    next_tr = _next_training(dz.get("name", "재난"), region_label)
    next_html = "".join(f"<li>{_e(x)}</li>" for x in next_tr)
    scorecells = (f"<div class='b'><div class='n' style='color:#22406e'>{dec}</div><div class='l'>의사결정(절차)</div></div>"
                  f"<div class='b'><div class='n' style='color:#22406e'>{out}</div><div class='l'>피해 최소화(결과)</div></div>"
                  if mode == "sim" else "")

    intro_para = (
        f"본 훈련은 {_e(dz.get('name','재난'))} 상황을 가정하여, 대상 지역({_e(region_label)})의 위험요소와 "
        "대피 인프라를 기반으로 재난담당자의 초기 대응·상황전파·인명보호·현장통제 판단을 점검하기 위해 실시하였다.")

    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(TITLE)}</title><style>{CSS}</style></head><body>
<button class="pbtn noprint" onclick="window.print()">🖨 인쇄 / PDF 저장</button>
<div class="doc">
 <div class="rpt-head">
   <div class="k">안전민국 · AI 재난훈련 평가관</div>
   <h1>{_e(TITLE)}</h1>
   <div class="pos">지역 데이터 기반 재난 대응 도상훈련 평가보고서 · 행정안전부 표준매뉴얼 기준</div>
 </div>

 <p style="font-size:14px;margin:14px 0">{intro_para}</p>

 <div class="sec"><h2>1. 훈련 개요</h2>
   <table class="meta">
     <tr><td class="h">훈련명</td><td>{_e(dz.get('name',''))} 대응 {_e(mode_label)}</td>
         <td class="h">재난 유형</td><td>{_e(dz.get('icon',''))} {_e(dz.get('name',''))}</td></tr>
     <tr><td class="h">훈련 방식</td><td>{_e(mode_label)}</td>
         <td class="h">대상 지역</td><td>{_e(region_label)}</td></tr>
     <tr><td class="h">담당 기관</td><td>{_e(org)}</td>
         <td class="h">훈련 일시</td><td>{_e(when) or '실시간'}</td></tr>
     {(f'<tr><td class="h">참가자 역할</td><td colspan="3">{_e(role)} <span class="muted">(안전한국훈련 평가지표 2-3 다역할)</span></td></tr>') if role else ''}
   </table>
 </div>

 <div class="sec"><h2>2. 지역 재난안전데이터 브리핑</h2>
   <p class="muted">확인된 위험 플래그: {_flags_line(briefing)}</p>
   <table class="grid"><tr><th>데이터 항목</th><th>내용</th><th>데이터 출처 · 상태</th></tr>
   {_briefing_rows(briefing)}</table>
 </div>

 <div class="sec"><h2>3. 시나리오 요약</h2>{scenario}</div>

 <div class="sec"><h2>4. AI 평가관 분석 (표준 대응요소별)</h2>
   {ai_table}
   <div class="note">안전민국은 AI가 점수를 임의로 만들지 않습니다. AI는 사용자의 답변을 표준 대응요소별로 해석하고,
   점수 계산은 결정론적 채점 엔진이 수행합니다. 따라서 평가 결과의 재현성과 설명가능성을 확보합니다.</div>
 </div>

 {(f'''<div class="sec"><h2>5. 공식 평가지표별 획득 등급 대조</h2>
   <p class="muted">본 훈련 대응을 「2026년 재난대응 안전한국훈련 평가지표」(행정안전부)에 대조한 결과입니다.
   실제 안전한국훈련에서 어떤 지표로 몇 등급을 받게 될지 그대로 점검할 수 있습니다.</p>
   {indicator_html}</div>''') if indicator_html else ''}

 {region_ref_block}

 <div class="sec"><h2>6. 종합 점수 및 등급</h2>
   <div class="scorebar">{scorecells}
     <div class="b"><div class="n" style="color:{gcolor}">{tot}</div><div class="l">종합 점수</div></div>
   </div>
   <p style="text-align:center;margin:8px 0"><span class="grade" style="background:{gcolor};color:#fff">{_e(grade)}</span></p>
   <p class="muted">결과 지표: {result_metrics}</p>
 </div>

 <div class="sec"><h2>7. 미흡 대응요소 TOP 3</h2><ul class="wk">{weak_html}</ul></div>

 <div class="sec"><h2>8. 개선과제 도출 (환류)</h2>
   <p class="muted">훈련에서 확인된 미흡 요소를 유형별 개선과제로 전환한 결과입니다.
   훈련이 점수로 끝나지 않고 제도·시설·교육 개선으로 이어지도록 환류합니다(안전한국훈련 평가지표 3-1).</p>
   <table class="grid"><tr><th>유형</th><th>개선과제 · 도출 근거</th><th>담당(제안)</th><th>이행 기한</th></tr>
   {improve_html}</table>
 </div>

 <div class="sec"><h2>9. 다음 훈련 추천</h2><ol class="nx">{next_html}</ol></div>

 <div class="foot">채점 기준: {_e(' · '.join(manuals) or '행정안전부 위기관리 표준매뉴얼')}<br>
   본 보고서는 훈련용 의사결정 평가 결과이며, 실제 재난 대응 지시가 아닙니다. · 안전민국</div>
</div></body></html>"""

    return {
        "html": html,
        "summary": summary,
        "weaknesses": weaknesses,
        "improvement_tasks": improvement_tasks,
        "next_training": next_tr,
    }
