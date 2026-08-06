# -*- coding: utf-8 -*-
"""
폐암 재발 계산기 로컬 서버
- deploy/ 폴더의 정적 파일(계산기) 서빙
- POST /api/ocr : 서버에 보관된 Claude API 키로 병리 사진 OCR을 대신 처리(프록시)
  => 접속자는 키 없이 OCR 사용 가능 (키는 클라이언트에 노출되지 않음)

[키 설정] 아래 중 하나
  1) 환경변수:  set ANTHROPIC_API_KEY=sk-ant-...   (Windows)  /  export ... (mac/linux)
  2) 같은 폴더에 apikey.txt 파일 생성 후 키만 한 줄 저장

[실행]  python server.py        (기본 포트 8000, 같은 와이파이의 다른 기기도 접속 가능)
        python server.py 8080   (포트 지정)
접속:   http://<이 PC의 IP>:8000/    (예: http://172.30.22.72:8000/)
"""
import os, sys, json, ssl, pathlib, urllib.request, math
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
WEBDIR = ROOT / "deploy"

# ---- XGBoost 예측 모델 로드 (없으면 예측 엔드포인트만 비활성, OCR/정적은 정상) ----
PRED = None
try:
    import numpy as _np, xgboost as _xgb
    _pm = ROOT / "calculator" / "predict_meta.json"
    if _pm.exists():
        _meta = json.loads(_pm.read_text(encoding="utf-8"))
        _boost = {}
        for _name in _meta["baselines"].keys():
            _f = ROOT / "models" / f"{_name}.json"
            if _f.exists():
                _b = _xgb.Booster(); _b.load_model(str(_f)); _boost[_name] = _b
        if _boost:
            PRED = {"meta": _meta, "boost": _boost, "np": _np, "xgb": _xgb}
except Exception as _e:
    PRED = None

def predict_curves(features):
    if PRED is None:
        return {"error": "예측 모델이 서버에 로드되지 않았습니다."}
    np = PRED["np"]; xgb = PRED["xgb"]; meta = PRED["meta"]
    F = meta["features"]; med = meta["medians"]
    # 학습 시 결측 처리(15_train_export_xgb.py)와 같은 규칙:
    #   grade 는 NaN 으로 남겨 XGBoost 가 default direction 을 배웠고, 나머지는 중앙값으로 채웠다.
    # 브라우저 getX()/xgbVec() 도 같은 규칙이라 온·오프라인 결과가 일치한다.
    # (JSON 에는 NaN 이 없어 브라우저는 grade 결측을 null 로 보낸다.)
    MISSING_OK = set(meta.get("missing_ok", ["grade"]))
    def val(k):
        v = features.get(k, None)
        try:
            if v is None or v == "":
                return float("nan") if k in MISSING_OK else med[k]
            return float(v)
        except Exception:
            return float("nan") if k in MISSING_OK else med[k]
    vec = np.array([[val(f) for f in F]], dtype=float)
    dm = xgb.DMatrix(vec, feature_names=F)
    out = {"overall": None, "sites": {}, "cindex": meta.get("cindex", {}),
           "site_modality": meta.get("site_modality", {}), "months": meta["months"]}

    def cs_risk(name):
        """원인특이 누적발생 근사 1-S(t) (%) 와 누적위험 H(t) 를 함께 반환."""
        margin = float(PRED["boost"][name].predict(dm, output_margin=True)[0])
        S0 = np.clip(np.array(meta["baselines"][name], dtype=float), 1e-12, 1.0)
        H = -np.log(S0) * math.exp(margin)
        return (1 - np.exp(-H)) * 100, H

    for name in PRED["boost"]:
        if name == "death":
            continue                      # 경쟁사건 — 부위 곡선이 아니다
        risk, _ = cs_risk(name)
        arr = [round(float(x), 3) for x in risk]
        if name == "overall": out["overall"] = arr
        else: out["sites"][name] = arr

    # ---- overall = 경쟁위험 CIF (사망을 경쟁사건으로) ----
    # CIF_r(t) = Σ_{u<=t} S(u-)·q_r(u),  S = exp(-H_r - H_d),  q_r(u) = 1-exp(-ΔH_r(u))
    # analysis/_cr.py `_cif_combine` 과 같은 추정량. 저기서는 증분이 실제 사건시점에 놓이지만
    # 여기서는 월 단위 격자이므로 구간 내를 지수(이산 Aalen–Johansen)로 집계한다. ΔH_r 를
    # 그대로 쓰면(직사각형 합) CIF가 원인특이 1-exp(-H_r) 를 넘을 수 있다. 이 형태는
    # H_d=0 일 때 1-exp(-H_r) 로 정확히 telescoping 된다. (브라우저 cifCurve 와 동일 식)
    if meta.get("competing_risk_overall") and "death" in PRED["boost"] and "overall" in PRED["boost"]:
        _, Hr = cs_risk("overall")
        _, Hd = cs_risk("death")
        S_prev = np.exp(-Hr[:-1] - Hd[:-1])          # S(u-)
        q_r = 1 - np.exp(-np.diff(Hr))               # 구간 내 재발 조건부확률
        cif = np.concatenate([[0.0], np.cumsum(S_prev * q_r)]) * 100
        out["overall"] = [round(float(x), 3) for x in cif]
        out["competing_risk_overall"] = True
    return out
# 포트: 명령행 인자 > 환경변수 PORT(클라우드 호스팅이 주입) > 8000
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8000))
MODEL = "claude-opus-4-8"   # 병리 리포트 사진 판독 정확도 우선

def get_key():
    k = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if k: return k
    f = ROOT / "apikey.txt"
    if f.exists(): return f.read_text(encoding="utf-8").strip()
    return ""

OCR_PROMPT = (
 "Extract structured fields from this lung cancer surgical pathology report image. "
 "Return ONLY a JSON object (use null if not found) with keys: "
 '{"total_size":number|null,"size_cm":number|null,"pT_ord":number|null,'
 '"node_N1":0|1|null,"node_N2":0|1|null,"vpi":0|1|null,"lymphatic_inv":0|1|null,'
 '"vascular_inv":0|1|null,"perineural_inv":0|1|null,"stas":0|1|null,'
 '"celltype":"adeno"|"ct_Mucinous adeno"|"ct_SqCC"|"ct_Others"|null}. '
 "Rules: total_size=total tumor size in cm; size_cm=invasive component size in cm "
 "(if no lepidic component, equals total). "
 "pT_ord: read the EXACT pT category written in the report and map: pTis/AIS=0, MIA=0.5, "
 "pT1a=1, pT1b=2, pT1c=3, pT2a=4, pT2b=5, pT3=6, pT4=7. "
 "Read the subcategory letter very carefully (distinguish 1a vs 1b vs 1c, 2a vs 2b). "
 "If pT is not explicitly stated, derive from invasive size: <=1cm=T1a(1), >1-2=T1b(2), "
 ">2-3=T1c(3), >3-4=T2a(4), >4-5=T2b(5), >5-7=T3(6), >7cm or local invasion=T4(7). "
 "node_N1=1 if any N1 (hilar/intrapulmonary) station positive else 0; "
 "node_N2=1 if any N2 (mediastinal) station positive else 0 (independent; N1- with N2+ = skip). "
 "vpi/lymphatic_inv/vascular_inv/perineural_inv/stas=1 if present/positive else 0. "
 'celltype: adenocarcinoma(non-mucinous)->"adeno", mucinous adenocarcinoma->"ct_Mucinous adeno", '
 'squamous cell carcinoma->"ct_SqCC", otherwise->"ct_Others". Output JSON only, no prose.'
)

def call_anthropic(media_type, data_b64):
    key = get_key()
    if not key:
        return {"error": "서버에 API 키가 설정되지 않았습니다 (ANTHROPIC_API_KEY 또는 apikey.txt)."}
    body = json.dumps({
        "model": MODEL, "max_tokens": 700,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data_b64}},
            {"type": "text", "text": OCR_PROMPT}]}]
    }).encode("utf-8")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": "Anthropic API 오류: " + e.read().decode("utf-8", "ignore")[:300]}
    except Exception as e:
        return {"error": "요청 실패: " + str(e)}
    try:
        txt = resp["content"][0]["text"].strip().replace("```json", "").replace("```", "")
        return {"fields": json.loads(txt)}
    except Exception:
        return {"error": "응답 파싱 실패", "raw": resp.get("content")}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(WEBDIR), **k)
    def log_message(self, *a): pass  # quiet
    def _json(self, result):
        out = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)
    def do_POST(self):
        path = self.path.rstrip("/")
        n = int(self.headers.get("content-length", 0))
        if path == "/api/predict":
            if n > 1*1024*1024: return self._json({"error": "payload too large"})
            try:
                payload = json.loads(self.rfile.read(n).decode("utf-8"))
                result = predict_curves(payload.get("features", {}))
            except Exception as e:
                result = {"error": str(e)}
            return self._json(result)
        if path != "/api/ocr":
            self.send_error(404); return
        if n > 20*1024*1024:
            self.send_error(413, "image too large"); return
        try:
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
            result = call_anthropic(payload.get("media_type", "image/jpeg"), payload.get("data", ""))
        except Exception as e:
            result = {"error": str(e)}
        out = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

if __name__ == "__main__":
    if not WEBDIR.exists():
        print("ERROR: deploy/ 폴더가 없습니다."); sys.exit(1)
    keyset = "설정됨" if get_key() else "없음(OCR 비활성)"
    predset = "로드됨(%d개 모델)" % len(PRED["boost"]) if PRED else "없음(내장 Cox 폴백)"
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"폐암 재발 계산기 서버 실행 중")
    print(f"  - 예측모델:  {predset}")
    print(f"  - 로컬:      http://localhost:{PORT}/")
    print(f"  - 같은 망:   http://<이 PC IP>:{PORT}/")
    print(f"  - API 키:    {keyset}")
    print("중지: Ctrl+C")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 중지")
