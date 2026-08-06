"""세이프드릴 — AI 멀티재난 대응 훈련 시뮬레이터 (FastAPI 백엔드 + 단일 페이지 UI).

흐름: 주소 입력 → 지역 맞춤 재난 추천 → 상황 대응(도상훈련) → AI 강평 + 실제 대응법(국민행동요령)

라우트:
  GET  /                    단일 페이지
  GET  /api/resolve?address=...   주소 → 지역 프로파일 + 위험도순 재난 추천
  GET  /api/start?disaster=&address=   지역화된 브리핑 + 첫 상황
  POST /api/run             {disaster, choices[], address} → 리플레이·점수, 종료 시 강평+행동요령
  GET  /api/guideline?disaster=...    재난유형별 국민행동요령(실제 대응법)

실행:  python -m uvicorn app:app --port 8610   (재난훈련_시뮬레이터 폴더에서)
"""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine import catalog, citizen, core, disaster_stats, generator, hazards, live_data, llm, region, report, safety_data, sim, ttx
from engine.util import get_logger, sanitize_text

VERSION = "1.0"
app = FastAPI(title="안전민국 — 국민과 기관이 함께 연습하는 AI 재난안전 훈련 플랫폼", version=VERSION)
_log = get_logger()

_STATIC = Path(__file__).resolve().parent / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


# ── 보안·복원력·관측성 미들웨어 ────────────────────────────────────
@app.middleware("http")
async def _harden(request: Request, call_next):
    """보안 헤더 부착 + 요청 로깅 + 예외 시 스택 노출 없이 우아하게 실패(복원력)."""
    t0 = time.perf_counter()
    try:
        resp = await call_next(request)
    except Exception as e:  # noqa: BLE001  — 엔진 예외가 스택트레이스로 새어나가지 않게
        _log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500,
                            content={"error": "서버 처리 중 문제가 발생했습니다.", "detail": type(e).__name__})
    ms = (time.perf_counter() - t0) * 1000
    if request.url.path.startswith("/api/"):
        _log.info("%s %s -> %s (%.0fms)", request.method, request.url.path, resp.status_code, ms)
    # 최소 보안 헤더(정적 SPA·공모전 배포 기준)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


@app.get("/health")
@app.get("/api/health")
def health():
    """관측성·keep-alive용 헬스체크 — 배포 감시·HF Space 잠자기 방지(cron-job.org 10분 GET)에 사용.

    가벼운 응답만(외부 API 호출 없음) — 잠자기 방지 트래픽으로 컨테이너만 깨운다.
    /health·/api/health 둘 다 응답(경로 혼동 방지).
    """
    return {"status": "ok", "version": VERSION,
            "llm": "on" if llm.has_key() else "rule-fallback",
            "disasters": len(catalog.summaries())}


class RunReq(BaseModel):
    disaster: str
    choices: list[str] = []
    address: str = ""
    use_llm: bool = True


class SimRunReq(BaseModel):
    disaster: str
    choices: list[str] = []
    address: str = ""
    variant: int = 0
    use_llm: bool = True


class CitizenReq(BaseModel):
    disaster: str
    choices: list[int] = []
    address: str = ""
    variant: int = 0


class TtxEvalReq(BaseModel):
    disaster: str
    stage: int = 0
    answer: str = ""
    address: str = ""
    variant: int = 0
    use_llm: bool = True
    role: str = ""


@app.get("/api/resolve")
def api_resolve(address: str = ""):
    prof = region.resolve(address)
    # 주소를 입력했는데 실제 지역으로 매칭되지 않으면(오타·없는 지역) 대시보드로 넘기지 않고 반려.
    # 실시간 기상·신호등 등 엉뚱한 데이터가 붙는 것을 원천 차단(빈 주소=의도된 둘러보기는 예외).
    if address.strip() and not prof["matched"]:
        return JSONResponse({"unresolved": True, "input": address.strip(),
                             "region": {"label": prof["label"], "matched": False}})
    disasters = region.rank_disasters(catalog.summaries(), prof)
    for x in disasters:
        x["ttx"] = ttx.available(x["id"])
    briefing = safety_data.get_local_disaster_briefing(prof)
    return JSONResponse({
        "region": {"label": prof["label"], "sido": prof["sido"], "sigungu": prof["sigungu"],
                   "tags": prof["tags"], "note": prof["note"], "matched": prof["matched"],
                   "lat": prof.get("lat"), "lon": prof.get("lon"), "geo": prof.get("geo")},
        "disasters": disasters,
        "briefing": briefing,
        "live": live_data.get_live_status(prof),
        "dash": disaster_stats.get_dashboard(prof),
        "hazards": hazards.get_hazards(prof),
        "citizen": citizen.available(),
        "upcoming": catalog.upcoming(),
    })


@app.get("/api/start")
def api_start(disaster: str, address: str = "", variant: int = 0):
    prof = region.resolve(address)
    d = catalog.get(disaster)
    if d.get("mode") == "sim":
        out = sim.start(disaster, prof, variant=variant)
        out["depth"] = d["depth"]
        out["region"] = prof["label"]
        out["region_matched"] = prof["matched"]
        return JSONResponse(out)
    d = region.localize(d, prof)
    return JSONResponse({
        "id": d["id"], "name": d["name"], "icon": d.get("icon", "⚠"),
        "context": d.get("context", ""), "depth": d["depth"], "mode": "quiz",
        "summary": d.get("summary", ""),
        "source_manuals": d.get("source_manuals", []),
        "data_sources": d.get("data_sources", []),
        "region": prof["label"], "region_matched": prof["matched"],
        "total_phases": len(d["phases"]),
        "first_phase": core.first_phase(disaster, prof),
    })


@app.post("/api/run")
def api_run(req: RunReq):
    prof = region.resolve(req.address)
    result = core.replay(req.disaster, req.choices, prof)
    result["region"] = prof["label"]
    if result["finished"]:
        debrief, engine = llm.debrief(result, use_llm=req.use_llm)
        result["debrief"] = debrief
        result["debrief_engine"] = engine
        result["guideline"] = region.guideline(req.disaster)
    return JSONResponse(result)


@app.post("/api/sim_run")
def api_sim_run(req: SimRunReq):
    prof = region.resolve(req.address)
    result = sim.replay(req.disaster, req.choices, prof, variant=req.variant)
    result["region"] = prof["label"]
    if result["finished"]:
        debrief, engine = llm.debrief_sim(result, use_llm=req.use_llm)
        result["debrief"] = debrief
        result["debrief_engine"] = engine
        result["guideline"] = region.guideline(req.disaster)
    return JSONResponse(result)


@app.get("/api/guideline")
def api_guideline(disaster: str):
    return JSONResponse(region.guideline(disaster) or {})


@app.get("/api/citizen_start")
def api_citizen_start(disaster: str = "", address: str = "", seed: int = 0):
    prof = region.resolve(address)
    return JSONResponse(citizen.start(disaster, prof, seed=seed) or {"error": "no_scenario"})


@app.post("/api/citizen_run")
def api_citizen_run(req: CitizenReq):
    prof = region.resolve(req.address)
    return JSONResponse(citizen.evaluate(req.disaster, req.choices, prof, variant=req.variant))


@app.get("/api/ttx_start")
def api_ttx_start(disaster: str, address: str = "", variant: int = 0, role: str = ""):
    prof = region.resolve(address)
    out = ttx.start(disaster, prof, variant=variant, role=role or None)
    out["region"] = prof["label"]
    out["org"] = prof.get("org", "")
    out["region_matched"] = prof["matched"]
    return JSONResponse(out)


@app.post("/api/ttx_eval")
def api_ttx_eval(req: TtxEvalReq):
    prof = region.resolve(req.address)
    briefing = safety_data.get_local_disaster_briefing(prof)
    return JSONResponse(ttx.evaluate(req.disaster, req.stage, req.answer, prof,
                                     use_llm=req.use_llm, variant=req.variant,
                                     briefing=briefing, role=req.role or None))


@app.post("/api/ttx_surprise_eval")
def api_ttx_surprise_eval(req: TtxEvalReq):
    """돌발 불시메시지(2-1-4) 답안 평가. variant를 돌발 선택 seed로 사용."""
    prof = region.resolve(req.address)
    return JSONResponse(ttx.surprise_eval(req.disaster, req.answer, prof,
                                          use_llm=req.use_llm, seed=req.variant,
                                          role=req.role or None))


class ReportReq(BaseModel):
    mode: str = "ttx"          # "ttx" | "sim"
    disaster: str
    address: str = ""
    variant: int = 0
    when: str = ""
    stages: list[dict] = []    # ttx: 단계별 evaluate 결과 목록
    sim: dict = {}             # sim: sim.replay 결과
    role: str = ""             # ttx: 참가자 역할(P4)


@app.post("/api/report", response_class=HTMLResponse)
def api_report(req: ReportReq):
    """훈련 결과 → 공무원 실무 산출물(평가보고서) HTML. 인쇄/PDF 저장 가능."""
    prof = region.resolve(req.address)
    d = catalog.get(req.disaster)
    briefing = safety_data.get_local_disaster_briefing(prof)
    ctx = {
        "mode": req.mode,
        "disaster": {"name": d.get("name", ""), "icon": d.get("icon", "⚠"),
                     "context": d.get("context", ""),
                     "source_manuals": d.get("source_manuals", [])},
        "region": {"label": prof["label"], "org": prof.get("org", "")},
        "when": req.when,
        "briefing": briefing,
        "role": ttx._role(req.role or None)["label"] if req.mode == "ttx" else "",
    }
    if req.mode == "ttx":
        stages = req.stages or []
        scores = [s.get("score", 0) for s in stages]
        avg = round(sum(scores) / len(scores)) if scores else 0
        ctx["ttx"] = {"stages": stages,
                      "summary": {"avg": avg, "scores": scores, "grade": core.grade_of(avg)}}
    else:
        ctx["sim"] = req.sim
    return HTMLResponse(report.build(ctx)["html"])


class GenReq(BaseModel):
    institution: str = ""
    disaster: str = ""
    concept: str = ""
    use_llm: bool = True


class GenEvalReq(BaseModel):
    elements: list[dict] = []
    answer: str = ""
    title: str = ""
    model_answer: str = ""
    inject: str = ""
    task: str = ""
    use_llm: bool = True


@app.post("/api/generate")
def api_generate(req: GenReq):
    """기관 성격 + 재난 + 컨셉 → 맞춤 TTX 시나리오(AI 생성 또는 규칙 초안).

    ⚠사용자 자유입력이 시나리오 텍스트로 되비쳐지므로 안전화(HTML 태그 주입·XSS 차단)한다.
    """
    inst = sanitize_text(req.institution, 120)
    dis = sanitize_text(req.disaster, 40)
    con = sanitize_text(req.concept, 160)
    sc = generator.generate(inst, dis, con, use_llm=req.use_llm)
    sc["ai_available"] = llm.has_key()
    return JSONResponse(sc)


@app.post("/api/generate_eval")
def api_generate_eval(req: GenEvalReq):
    """생성 시나리오의 표준 대응요소 + 답안 → 결정론 채점·강평(엔진 공유)."""
    return JSONResponse(ttx.score_elements(
        req.elements, req.answer, title=req.title, model_answer=req.model_answer,
        use_llm=req.use_llm, inject=req.inject, task=req.task))


@app.get("/", response_class=HTMLResponse)
def index():
    """단일 페이지 — 정적 파일 서빙(HTML/CSS/JS는 static/으로 분리, app.py=백엔드 전용)."""
    return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))
