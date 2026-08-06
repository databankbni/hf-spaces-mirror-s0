import os

from mcp.server.fastmcp import FastMCP
import chromadb

from rank_bm25 import BM25Okapi

# Starlette primitives for the mobile-app HTTP bridge (see custom routes below)
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

# host/port come from the hosting platform (e.g. Render/Railway set $PORT)
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

mcp = FastMCP("Golf Swing Coach", host=HOST, port=PORT)

# Connect to the ChromaDB we built
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heo_db")
chroma_client = chromadb.PersistentClient(path=_DB_PATH)
collection = chroma_client.get_collection("heo_tips")

# Build a BM25 keyword index alongside the vector index
all_data = collection.get()
all_docs = all_data["documents"]
all_ids = all_data["ids"]
all_metas = all_data["metadatas"]

tokenized_corpus = [doc.lower().split() for doc in all_docs]
bm25 = BM25Okapi(tokenized_corpus)
# Map casual/colloquial phrases to the terms Coach Birdie actually uses
SYNONYM_MAP = {
    "topping it": "thin contact",
    "hitting it thin": "thin contact",
    "hitting it fat": "fat shot",
    "chunking it": "fat shot",
    "losing my spine angle": "early extension",
    "standing up early": "early extension",
    "slicing": "open clubface",
    "hooking": "closed clubface",
    "casting": "early release",
}

def rewrite_query(query: str) -> str:
    q = query.lower()
    for casual, formal in SYNONYM_MAP.items():
        if casual in q:
            q = q.replace(casual, formal)
    return q

# --- Tool 1: Analyze the swing ---
@mcp.tool()
def analyze_swing(video_description: str) -> dict:
    """
    Accepts a description of a golf swing and returns detected faults.
    In the real version, this will accept an actual video file.
    """
    # Dummy logic for now — pretend we detected faults from the video
    detected_faults = ["early_extension", "chicken_wing"]

    return {
        "faults_detected": detected_faults,
        "confidence": "demo mode — real video analysis not yet active"
    }

def hybrid_search(query: str, k: int = 3):
    query = rewrite_query(query)

    # Vector search (existing ChromaDB)
    vector_results = collection.query(query_texts=[query], n_results=k * 3)
    vector_ids = vector_results["ids"][0]

    # Keyword search (BM25)
    bm25_scores = bm25.get_scores(query.lower().split())
    ranked_indices = sorted(range(len(bm25_scores)), key=lambda i: -bm25_scores[i])[:k * 3]
    bm25_ids = [all_ids[i] for i in ranked_indices]

    # Merge both rankings (Reciprocal Rank Fusion)
    scores = {}
    for rank, doc_id in enumerate(vector_ids):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (60 + rank)
    for rank, doc_id in enumerate(bm25_ids):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (60 + rank)

    top_ids = sorted(scores.items(), key=lambda x: -x[1])[:k]

    # Look up the actual text/metadata for the winning IDs
    id_to_index = {doc_id: i for i, doc_id in enumerate(all_ids)}
    final_results = []
    for doc_id, _ in top_ids:
        idx = id_to_index[doc_id]
        final_results.append({"tip": all_docs[idx], "meta": all_metas[idx]})

    return final_results

# --- Tool 2: Get coaching tip for a specific fault ---
@mcp.tool()
def get_coaching_tip(fault: str) -> dict:
    """
    Takes a fault or swing issue description and returns Coach Birdie's
    most relevant coaching tips from his video library.
    """
    results = hybrid_search(fault, k=3)

    tips = []
    for r in results:
        tips.append({
            "tip": r["tip"],
            "fault_category": r["meta"]["fault"],
            "source_video": r["meta"]["source_video"]
        })

    return {"tips": tips}

# ---------------------------------------------------------------------------
# Free, on-server swing analysis: MediaPipe Pose (Apache-2.0) + golf rules.
# No paid vision API — body landmarks are detected locally and a rule engine
# derives faults, a star scorecard, and plain-English coaching. The frontend
# response shape is unchanged.
# ---------------------------------------------------------------------------

# MediaPipe Pose landmark indices we use.
_LM = {
    "nose": 0,
    "l_shoulder": 11, "r_shoulder": 12,
    "l_elbow": 13, "r_elbow": 14,
    "l_wrist": 15, "r_wrist": 16,
    "l_hip": 23, "r_hip": 24,
    "l_knee": 25, "r_knee": 26,
    "l_ankle": 27, "r_ankle": 28,
}

_POSE = None  # lazy singleton so the model loads once per process


def _get_pose():
    global _POSE
    if _POSE is None:
        import mediapipe as _mp
        # BlazePose, 33-landmark model. model_complexity: 0=Lite, 1=Full,
        # 2=Heavy (most accurate landmark placement). Running Heavy here because
        # the Hugging Face Space has 16GB RAM -- plenty of headroom, unlike the
        # old 512MB tier where Heavy OOM'd.
        _POSE = _mp.solutions.pose.Pose(
            static_image_mode=True, model_complexity=2,
            enable_segmentation=False, min_detection_confidence=0.3,
        )
    return _POSE


def _landmarks_from_image(jpeg_bytes: bytes):
    """Detect one frame's pose.

    Returns a detection dict:
        {"img": {name:(x,y,vis)}, "world": {name:(x,y,z)}, "vis": mean_vis}
    or None if no body was found. `img` are normalized image coords (good for
    lateral drift), `world` are metric 3D coords (good for true joint angles).
    """
    import numpy as _np
    import cv2 as _cv2
    arr = _np.frombuffer(jpeg_bytes, dtype=_np.uint8)
    img = _cv2.imdecode(arr, _cv2.IMREAD_COLOR)
    if img is None:
        return None
    rgb = _cv2.cvtColor(img, _cv2.COLOR_BGR2RGB)
    res = _get_pose().process(rgb)
    if not res.pose_landmarks:
        return None
    lm = res.pose_landmarks.landmark
    img_lm, vis_sum = {}, 0.0
    for name, idx in _LM.items():
        p = lm[idx]
        img_lm[name] = (float(p.x), float(p.y), float(p.visibility))
        vis_sum += float(p.visibility)
    world_lm = None
    if getattr(res, "pose_world_landmarks", None):
        wl = res.pose_world_landmarks.landmark
        world_lm = {name: (float(wl[idx].x), float(wl[idx].y), float(wl[idx].z))
                    for name, idx in _LM.items()}
    return {"img": img_lm, "world": world_lm, "vis": vis_sum / len(_LM)}


def _best_detection(jpeg_candidates):
    """Run pose on several candidate frames, return (det, jpeg_bytes) for the
    one with the highest mean landmark visibility, or (None, first_jpeg)."""
    best_det, best_jpeg, best_vis = None, (jpeg_candidates[0] if jpeg_candidates else None), -1.0
    for jb in jpeg_candidates:
        det = _landmarks_from_image(jb)
        if det and det["vis"] > best_vis:
            best_vis, best_det, best_jpeg = det["vis"], det, jb
    return best_det, best_jpeg


# --- geometry helpers (pure, unit-testable) -------------------------------

def _mid(a, b):
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def _dist(a, b):
    import math
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _tilt_from_vertical(top, bottom):
    """Degrees the top->bottom segment leans from straight-up (0 = upright)."""
    import math
    dx = top[0] - bottom[0]
    dy = top[1] - bottom[1]  # image y grows downward
    return math.degrees(math.atan2(abs(dx), abs(dy) + 1e-9))


def _joint_angle(a, b, c):
    """Interior angle at b (degrees) for points a-b-c."""
    import math
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1 = math.hypot(*v1) + 1e-9
    n2 = math.hypot(*v2) + 1e-9
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def _tilt_from_vertical_3d(top, bottom):
    """Degrees the 3D top->bottom segment leans from vertical (0 = upright)."""
    import math
    dx = top[0] - bottom[0]
    dy = top[1] - bottom[1]
    dz = top[2] - bottom[2]
    horizontal = math.hypot(dx, dz)
    return math.degrees(math.atan2(horizontal, abs(dy) + 1e-9))


def _joint_angle_3d(a, b, c):
    """Interior angle at b (degrees) for 3D points a-b-c."""
    import math
    v1 = (a[0] - b[0], a[1] - b[1], a[2] - b[2])
    v2 = (c[0] - b[0], c[1] - b[1], c[2] - b[2])
    n1 = math.sqrt(sum(x * x for x in v1)) + 1e-9
    n2 = math.sqrt(sum(x * x for x in v2)) + 1e-9
    cos = max(-1.0, min(1.0, sum(p * q for p, q in zip(v1, v2)) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def _axis_turn_3d(a_det, b_det, lkey, rkey):
    """Rotation (deg) of a body segment (e.g. hips, shoulders) about the vertical
    axis between two frames, using 3D world landmarks. Camera-independent.
    Returns None if world landmarks are unavailable."""
    import math

    def world_of(d):
        return d.get("world") if isinstance(d, dict) and "world" in d else None

    wa, wb = world_of(a_det), world_of(b_det)
    if not (wa and wb):
        return None

    def horiz(w):
        L, R = w[lkey], w[rkey]
        return (R[0] - L[0], R[2] - L[2])  # drop vertical axis

    va, vb = horiz(wa), horiz(wb)
    na = math.hypot(*va) + 1e-9
    nb = math.hypot(*vb) + 1e-9
    cos = max(-1.0, min(1.0, (va[0] * vb[0] + va[1] * vb[1]) / (na * nb)))
    return math.degrees(math.acos(cos))


def _shoulder_turn(addr_det, top_det):
    """True shoulder rotation in degrees between address and top.

    Uses the horizontal component of the 3D shoulder line (camera-independent);
    falls back to the 2D apparent-width shrink (width ~= true_width * cos(turn))
    when world landmarks are unavailable. Returns (degrees, "3d"|"2d") or
    (None, None) if it cannot be computed.
    """
    import math

    def world_of(d):
        return d.get("world") if isinstance(d, dict) and "world" in d else None

    wa, wt = world_of(addr_det), world_of(top_det)
    if wa and wt:
        def horiz(w):
            L, R = w["l_shoulder"], w["r_shoulder"]
            return (R[0] - L[0], R[2] - L[2])  # drop vertical axis
        va, vt = horiz(wa), horiz(wt)
        na = math.hypot(*va) + 1e-9
        nt = math.hypot(*vt) + 1e-9
        cos = max(-1.0, min(1.0, (va[0] * vt[0] + va[1] * vt[1]) / (na * nt)))
        return math.degrees(math.acos(cos)), "3d"

    fa, ft = _features(addr_det), _features(top_det)
    if fa and ft and fa["sh_w"] > 1e-4:
        ratio = max(0.0, min(1.0, ft["sh_w"] / fa["sh_w"]))
        return math.degrees(math.acos(ratio)), "2d"
    return None, None


def _features(det):
    """Reliable 2D measurements from one frame's detection.

    Deliberately uses ONLY the normalized image landmarks (x, y, visibility),
    which MediaPipe estimates accurately. It does NOT use the 3D world-landmark
    depth, which is guessed from a single camera and is unreliable for absolute
    angles. Everything here is a position or a body-relative ratio, reported so
    the rule engine can stay qualitative rather than inventing precise degrees.
    """
    if not det:
        return None
    img = det["img"] if isinstance(det, dict) and "img" in det else det

    sh = _mid(img["l_shoulder"], img["r_shoulder"])
    hip = _mid(img["l_hip"], img["r_hip"])
    ank = _mid(img["l_ankle"], img["r_ankle"])
    torso = _dist(sh, hip)
    shw = _dist(img["l_shoulder"], img["r_shoulder"])  # apparent shoulder width
    keys = ["nose", "l_shoulder", "r_shoulder", "l_hip", "r_hip",
            "l_ankle", "r_ankle", "l_wrist", "r_wrist"]
    vis = sum(img[k][2] for k in keys) / len(keys)

    return {
        "nose_x": img["nose"][0], "nose_y": img["nose"][1],
        "sh_y": sh[1],
        "hip_x": hip[0], "hip_y": hip[1],
        "ank_y": ank[1],
        "hands_y": min(img["l_wrist"][1], img["r_wrist"][1]),  # smaller y = higher
        "torso": torso if torso > 1e-4 else 1e-4,
        "shw": shw if shw > 1e-4 else 1e-4,
        "vis": vis,
    }


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


_CONF = 0.55  # min mean landmark visibility before we trust a frame's numbers

_METRIC_ORDER = ["Setup & Posture", "Takeaway & Path", "Impact & Clubface", "Tempo & Balance"]


def _gemini_analyze_video(video_path: str) -> dict | None:
    """Send the actual swing clip to Gemini's vision model and ask for the same
    summary/metrics/faults shape _grade_swing() produces from pose landmarks.

    This is a genuine coach watching the video (path, tempo, sequencing, clubface)
    rather than the geometric heuristics below, which only ever read head sway,
    shoulder-turn foreshortening, and vertical rise. Returns None -- and the
    caller falls back to the free MediaPipe rule engine -- if GEMINI_API_KEY
    isn't set, the SDK isn't installed, or anything about the call fails.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        import json as _json
        import time as _time
        from google import genai
        from google.genai import types

        model = os.environ.get("GOLF_GEMINI_MODEL", "gemini-2.5-flash")
        client = genai.Client(api_key=api_key)
        uploaded = client.files.upload(file=video_path)
        try:
            for _ in range(30):
                uploaded = client.files.get(name=uploaded.name)
                if uploaded.state.name == "ACTIVE":
                    break
                if uploaded.state.name == "FAILED":
                    return None
                _time.sleep(1)
            else:
                return None

            prompt = (
                "You are Coach Birdie, a PGA-level golf coach reviewing a student's "
                "swing video. Watch the full clip closely -- backswing path, clubface, "
                "tempo, weight shift, posture, and impact position -- and return ONLY a "
                "JSON object with this exact shape:\n"
                '{"summary": str, "handedness": "right"|"left"|"unknown", '
                '"metrics": [4 objects, in this exact order and with these exact names -- '
                '"Setup & Posture", "Takeaway & Path", "Impact & Clubface", "Tempo & Balance" '
                '-- each {"name": str, "rating": int 1-5, "note": str (one specific '
                'sentence)}], "faults": [0-3 objects {"label": str (short fault name), '
                '"phase": "address"|"takeaway"|"top"|"impact"|"finish", '
                '"severity": "minor"|"moderate"|"major", "observation": str (1-2 '
                "sentences, specific to what you saw)}]}\n"
                "Be honest and specific -- reference what actually happens in THIS clip, "
                "not generic swing advice. If the swing looks solid, say so and return an "
                "empty faults list rather than inventing issues."
            )

            resp = client.models.generate_content(
                model=model,
                contents=[uploaded, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.4
                ),
            )

            text = (resp.text or "").strip()
            text = text.replace("```json", "").replace("```", "").strip()
            lo, hi = text.find("{"), text.rfind("}")
            if lo == -1 or hi == -1:
                return None
            data = _json.loads(text[lo:hi + 1])

            metrics = [m for m in (data.get("metrics") or []) if m.get("name") in _METRIC_ORDER]
            if len(metrics) != 4 or not str(data.get("summary", "")).strip():
                return None  # malformed response -- fall back to the free engine
            metrics.sort(key=lambda m: _METRIC_ORDER.index(m["name"]))
            for m in metrics:
                m["rating"] = max(0, min(5, int(m.get("rating") or 0)))

            faults = (data.get("faults") or [])[:3]
            frame_notes = {}
            for f in faults:
                ph = f.get("phase")
                if ph and ph not in frame_notes:
                    frame_notes[ph] = f.get("observation", "")

            return {
                "summary": str(data.get("summary", "")).strip(),
                "handedness": data.get("handedness", "unknown"),
                "metrics": metrics,
                "faults": faults,
                "frame_notes": frame_notes,
                "debug": {"engine": "gemini", "model": model},
            }
        finally:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass
    except Exception:
        return None


def _grade_swing(landmarks_by_phase: dict) -> dict:
    """Confidence-gated 2D rule engine.

    Reports ONLY signals that single-camera 2D pose measures reliably -- head
    movement and vertical body positions -- and only when the landmarks are
    high-confidence. Findings are qualitative (no fake-precise degrees). If a
    signal can't be measured confidently, the metric is returned neutral instead
    of guessing. Pure logic, unit-testable with synthetic keypoints.
    """
    phases = ["address", "takeaway", "top", "impact", "finish"]
    feat = {ph: _features(landmarks_by_phase.get(ph)) for ph in phases}
    detected = [ph for ph in phases if feat[ph]]

    debug = {}
    for ph in phases:
        if feat[ph]:
            g = feat[ph]
            debug[ph] = {"detected": True, "vis": round(g["vis"], 2),
                         "nose_x": round(g["nose_x"], 3), "nose_y": round(g["nose_y"], 3),
                         "sh_y": round(g["sh_y"], 3), "hip_y": round(g["hip_y"], 3),
                         "ank_y": round(g["ank_y"], 3), "hands_y": round(g["hands_y"], 3),
                         "torso": round(g["torso"], 3), "shw": round(g["shw"], 3)}
        else:
            debug[ph] = {"detected": False}

    _a0, _t0 = feat.get("address"), feat.get("top")
    debug["coil_ratio"] = (round(_t0["shw"] / _a0["shw"], 3)
                           if _a0 and _t0 and _a0["shw"] > 1e-3 else None)

    notes, metrics, faults = {}, [], []

    if not detected:
        for ph in phases:
            notes[ph] = "Couldn't clearly detect the body in this frame."
        for name in ["Setup & Posture", "Takeaway & Path",
                     "Impact & Clubface", "Tempo & Balance"]:
            metrics.append({"name": name, "rating": 0,
                            "note": "No body detected to measure."})
        summary = ("I couldn't pick out a clear body position in this video. "
                   "For the best read, film face-on or down-the-line, full body "
                   "in frame, good lighting, and a fairly steady camera.")
        return {"summary": summary, "handedness": "unknown",
                "metrics": metrics, "faults": faults, "frame_notes": notes,
                "debug": debug}

    def conf(x):
        return x is not None and x["vis"] >= _CONF

    a = feat.get("address")
    t = feat.get("top")
    i = feat.get("impact")
    fin = feat.get("finish")

    # ---- Tempo & Balance: head movement across the swing (most reliable 2D) ----
    head_move = None
    if conf(a):
        sway = lift = 0.0
        # Only through impact -- turning the head toward the target in the
        # follow-through is normal and shouldn't count as a fault.
        for ph in ["takeaway", "top", "impact"]:
            g = feat[ph]
            if conf(g):
                sway = max(sway, abs(g["nose_x"] - a["nose_x"]) / a["torso"])
                lift = max(lift, abs(g["nose_y"] - a["nose_y"]) / a["torso"])
                head_move = max(sway, lift)
    if head_move is not None:
        if head_move > 0.9:
            metrics.append({"name": "Tempo & Balance", "rating": 2,
                            "note": "Your head moves a lot during the swing."})
            faults.append({"label": "Head moves off the ball", "phase": "top",
                "severity": "moderate",
                "observation": "Your head drifts well away from where it started -- "
                               "a steadier head is one of the biggest consistency wins."})
        elif head_move > 0.5:
            metrics.append({"name": "Tempo & Balance", "rating": 3,
                            "note": "A bit of head movement during the swing."})
            faults.append({"label": "Some head movement", "phase": "top",
                "severity": "minor",
                "observation": "Your head drifts a little during the swing; keeping it "
                               "quieter will tighten up your strike."})
        else:
            metrics.append({"name": "Tempo & Balance", "rating": 5,
                            "note": "Head stays nice and steady over the ball."})
        notes["address"] = "Setup -- your head position here is the reference point."
    else:
        metrics.append({"name": "Tempo & Balance", "rating": 0,
                        "note": "Couldn't track the head reliably in this clip."})

    # ---- Takeaway & Path: shoulder coil (apparent shoulder-width shrink) ----
    # As the shoulders turn away from a face-on camera, the shoulder line
    # foreshortens and its apparent width shrinks (width ~= true_width *
    # cos(turn)). A small shrink => the body barely rotated = lifting the arms
    # instead of coiling. Calibrated against a real "not enough coil" swing.
    if conf(a) and conf(t):
        coil = t["shw"] / a["shw"]          # lower = more shoulder turn
        rel = (t["sh_y"] - t["hands_y"]) / a["torso"]  # hand height at the top
        if coil > 0.55:
            metrics.append({"name": "Takeaway & Path", "rating": 2,
                            "note": "Limited shoulder coil -- arms lift more than the body turns."})
            faults.append({"label": "Not enough shoulder coil", "phase": "top",
                "severity": "moderate",
                "observation": "Your shoulders don't turn far enough away from the target "
                               "on the backswing -- you're lifting your arms more than coiling "
                               "your body, which leaks power and consistency."})
        elif coil > 0.42:
            metrics.append({"name": "Takeaway & Path", "rating": 3,
                            "note": "Shoulder coil is a bit short of a full turn."})
            faults.append({"label": "Shoulder coil a bit short", "phase": "top",
                "severity": "minor",
                "observation": "A bigger shoulder turn -- getting your back more toward the "
                               "target -- would add easy distance."})
        else:
            metrics.append({"name": "Takeaway & Path", "rating": 5,
                            "note": "Good, full shoulder coil at the top."})
        if rel < -0.05 and coil <= 0.55:
            notes["top"] = "Decent turn, but the hands stay a little low at the top."
        else:
            notes["top"] = ("Full coil -- back turned nicely toward the target." if coil <= 0.42
                            else "Shoulders stop short of a full turn -- coil the body more.")
    else:
        metrics.append({"name": "Takeaway & Path", "rating": 0,
                        "note": "Couldn't see the top of the swing clearly."})

    # ---- Impact & Clubface: standing up / early extension (vertical rise) ----
    if conf(a) and conf(i):
        addr_gap = a["ank_y"] - a["hip_y"]      # hips above ankles at address
        imp_gap = i["ank_y"] - i["hip_y"]
        hip_rise = (imp_gap - addr_gap) / (abs(addr_gap) + 1e-4)
        head_rise = (a["nose_y"] - i["nose_y"]) / a["torso"]  # +ve = head higher
        standup = max(hip_rise, head_rise)
        if standup > 0.18:
            metrics.append({"name": "Impact & Clubface", "rating": 2,
                            "note": "You rise up out of your posture into the ball."})
            faults.append({"label": "Standing up through impact (early extension)",
                "phase": "impact", "severity": "moderate",
                "observation": "You come up out of your setup posture into the ball, which "
                               "is a common cause of thin/inconsistent strikes."})
        elif standup > 0.09:
            metrics.append({"name": "Impact & Clubface", "rating": 3,
                            "note": "Slight loss of posture through impact."})
            faults.append({"label": "Slight loss of posture at impact", "phase": "impact",
                "severity": "minor",
                "observation": "You come up a little through impact; staying down in your "
                               "posture longer will help."})
        else:
            metrics.append({"name": "Impact & Clubface", "rating": 5,
                            "note": "You hold your posture nicely into the ball."})
        notes["impact"] = ("Posture held through impact." if standup <= 0.09
                           else "You stand up a bit coming into the ball.")
    else:
        metrics.append({"name": "Impact & Clubface", "rating": 0,
                        "note": "Couldn't see impact clearly."})

    # ---- Setup & Posture: kept honest -- a single angle can't be read reliably ----
    if conf(a):
        metrics.append({"name": "Setup & Posture", "rating": 4,
            "note": "Setup looks balanced (a full posture read needs a down-the-line view)."})
        notes.setdefault("address", "Balanced-looking setup.")
    else:
        metrics.append({"name": "Setup & Posture", "rating": 0,
                        "note": "Couldn't see the setup clearly."})

    # canonical order for the app
    order = ["Setup & Posture", "Takeaway & Path", "Impact & Clubface", "Tempo & Balance"]
    metrics.sort(key=lambda m: order.index(m["name"]) if m["name"] in order else 99)

    notes.setdefault("takeaway", "Takeaway -- club starting back.")
    notes.setdefault("finish", "Finish position." if conf(fin) else "Finish not clearly visible.")

    # ---- summary ----
    parts = []
    if faults:
        parts.append("Here's what stood out: " + faults[0]["observation"])
    else:
        parts.append("Nothing major jumped out from the body positions I could track "
                     "clearly -- looks pretty solid.")
    parts.append("I only flag things I can see clearly; a steady down-the-line or face-on "
                 "clip in good light lets me read more of your swing.")
    summary = " ".join(parts)

    for ph in phases:
        if not feat[ph]:
            notes[ph] = "Body not clearly detected in this frame."

    faults = faults[:3]
    return {"summary": summary, "handedness": "unknown",
            "metrics": metrics, "faults": faults, "frame_notes": notes,
            "debug": debug}


# --- Tool 3: Analyze an actual swing VIDEO (runs entirely on the server) ---
@mcp.tool()
def analyze_swing_video(video_url: str = "", video_base64: str = "") -> dict:
    """
    Analyze a real golf swing VIDEO and return a structured coaching plan with
    Coach Birdie tips. Provide a public direct video_url (recommended for phones
    and other remote devices) or a base64-encoded video. The server extracts 5
    key frames (address -> finish), detects body landmarks with MediaPipe Pose,
    applies a golf rule engine to score the swing and flag faults, and matches
    Coach Birdie coaching tips to each fault. Runs fully on-server, no paid
    vision API and no local machine required.
    """
    import base64 as _b64
    import re as _re
    import subprocess as _sp
    import tempfile as _tmp
    import urllib.request as _url

    phases = ["address", "takeaway", "top", "impact", "finish"]
    max_bytes = int(os.environ.get("GOLF_MAX_VIDEO_MB", "60")) * 1024 * 1024

    try:
        import imageio_ffmpeg
    except Exception as e:  # pragma: no cover
        return {"error": f"Missing server dependency: {e}"}

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    with _tmp.TemporaryDirectory(prefix="golf-") as workdir:
        video_path = os.path.join(workdir, "swing.mp4")

        # 1) Acquire the video (base64 inline, or download from a direct URL)
        if video_base64:
            data = _b64.b64decode(video_base64)
            if len(data) > max_bytes:
                return {"error": f"Video exceeds {max_bytes // (1024 * 1024)}MB limit."}
            with open(video_path, "wb") as fh:
                fh.write(data)
        elif video_url.lower().startswith(("http://", "https://")):
            req = _url.Request(video_url, headers={"User-Agent": "golf-mcp/1.0"})
            with _url.urlopen(req, timeout=60) as resp:  # noqa: S310 (scheme validated)
                total = 0
                with open(video_path, "wb") as fh:
                    while True:
                        chunk = resp.read(1 << 16)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            return {"error": f"Video exceeds {max_bytes // (1024 * 1024)}MB limit."}
                        fh.write(chunk)
        else:
            return {"error": "Provide a direct http(s) video_url or video_base64."}

        # 2) Duration (parse ffmpeg stderr; imageio-ffmpeg ships no ffprobe)
        probe = _sp.run([ffmpeg, "-i", video_path], capture_output=True, text=True)
        m = _re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", probe.stderr)
        if not m:
            return {"error": "Could not read video duration (is this a valid video?)."}
        duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        if duration <= 0:
            return {"error": "Video has zero duration."}

        # 3) Locate impact via peak scene-change score
        scene = _sp.run(
            [ffmpeg, "-i", video_path,
             "-vf", "select='gt(scene,0)',metadata=print:file=-",
             "-an", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        best_t, best_s = None, -1.0
        for t_str, s_str in _re.findall(r"pts_time:([0-9.]+)[\s\S]*?scene_score=([0-9.]+)", scene.stderr):
            t, s = float(t_str), float(s_str)
            if s > best_s:
                best_s, best_t = s, t
        if best_t is not None and duration * 0.2 < best_t < duration * 0.9:
            impact = best_t
            times = [impact * 0.1, impact * 0.55, impact * 0.85, impact,
                     impact + (duration - impact) * 0.7]
        else:
            times = [((i + 0.5) / len(phases)) * duration for i in range(len(phases))]
        times = [max(0.05, min(duration - 0.05, t)) for t in times]

        # 4+5) Event-based frame selection. Densely sample the clip, detect pose
        # on every frame, then locate the real swing positions from the hand
        # trajectory -- hands highest = top of backswing, hands lowest after the
        # top = impact -- instead of trusting guessed timestamps. Every phase
        # frame is chosen from the actual motion, so the per-frame measurements
        # line up with what really happened in the swing.
        _seq = [0]

        def _extract_at(t):
            t = max(0.02, min(duration - 0.02, t))
            _seq[0] += 1
            out = os.path.join(workdir, f"f{_seq[0]}.jpg")
            _sp.run([ffmpeg, "-ss", f"{t:.3f}", "-i", video_path,
                     "-frames:v", "1", "-q:v", "2", "-y", out],
                    capture_output=True, text=True)
            try:
                with open(out, "rb") as fh:
                    return fh.read()
            except OSError:
                return None

        def _hands_y(det):
            im = det["img"]
            return min(im["l_wrist"][1], im["r_wrist"][1])  # smaller y = higher

        N = 24
        try:
            samples = []
            for k in range(N):
                st = duration * (k + 0.5) / N
                jb = _extract_at(st)
                if jb is None:
                    continue
                det = _landmarks_from_image(jb)
                samples.append({"t": st, "det": det, "jpeg": jb,
                                "hy": _hands_y(det) if det else None})
        except Exception as e:  # pragma: no cover
            return {"error": f"Pose engine failed: {e}"}

        detected = [s for s in samples if s["det"]]
        if detected:
            # Address-height baseline: the hands' resting height before the swing
            # starts (median of the early, low-hands portion of the clip).
            early_hy = sorted(s["hy"] for s in detected
                              if s["t"] <= max(duration * 0.35, detected[0]["t"]))
            base_y = early_hy[len(early_hy) // 2] if early_hy else detected[0]["hy"]

            # TOP = the FIRST prominent peak of hand height (first local minimum of
            # y after the backswing lifts the hands). Using the *first* peak avoids
            # grabbing the follow-through, where the hands also swing up high.
            top_s = None
            for j in range(1, len(detected) - 1):
                s = detected[j]
                if (s["hy"] < base_y - 0.06 and s["hy"] <= detected[j - 1]["hy"]
                        and s["hy"] < detected[j + 1]["hy"]):
                    top_s = s
                    break
            if top_s is None:  # no clear peak -> fall back to highest hands
                top_s = min(detected, key=lambda s: s["hy"])

            # ADDRESS = last low-hands frame before the top (start of the backswing).
            pre = [s for s in detected if s["t"] < top_s["t"] and s["hy"] > base_y - 0.05]
            addr_s = pre[-1] if pre else detected[0]

            # IMPACT = after the top, the first frame where the hands have dropped
            # back to ~address height (the ball), else the lowest-hands frame in the
            # first half of the downswing/through-swing.
            after = [s for s in detected if s["t"] > top_s["t"]]
            impact_s = None
            for s in after:
                if s["hy"] >= base_y - 0.08:
                    impact_s = s
                    break
            if impact_s is None and after:
                half = after[:max(1, len(after) // 2)]
                impact_s = max(half, key=lambda s: s["hy"])

            tk_t = (addr_s["t"] + top_s["t"]) / 2.0
            tak_s = min(detected, key=lambda s: abs(s["t"] - tk_t))
            fin_s = detected[-1]

            # Guard against degenerate collapses (poor detection).
            if top_s is addr_s:
                top_s = None
            if impact_s is not None and (impact_s is addr_s or impact_s is top_s):
                impact_s = None
            chosen = {"address": addr_s, "takeaway": tak_s, "top": top_s,
                      "impact": impact_s, "finish": fin_s}
        else:
            chosen = {ph: None for ph in phases}

        # Build display frames + landmarks. For an undetected phase, fall back to
        # the nearest sampled frame at the guessed time just for the image.
        frames = []
        landmarks_by_phase = {}
        for i, phase in enumerate(phases):
            s = chosen.get(phase)
            if s is not None:
                landmarks_by_phase[phase] = s["det"]
                disp_jpeg, disp_t = s["jpeg"], s["t"]
            else:
                landmarks_by_phase[phase] = None
                near = min(samples, key=lambda q: abs(q["t"] - times[i])) if samples else None
                disp_jpeg = near["jpeg"] if near else _extract_at(times[i])
                disp_t = times[i]
            frames.append({"phase": phase, "time": round(disp_t, 2),
                           "base64": _b64.b64encode(disp_jpeg).decode() if disp_jpeg else ""})

        # 6) Prefer Gemini's vision analysis of the actual video (richer, sees the
        # whole swing) when GEMINI_API_KEY is set; otherwise fall back to the free
        # on-server MediaPipe rule engine, exactly as before.
        analysis = _gemini_analyze_video(video_path) or _grade_swing(landmarks_by_phase)
        metrics = analysis["metrics"]
        frame_notes = analysis["frame_notes"]
        faults = analysis["faults"]

        severity_by_phase = {}
        for fault in faults:
            ph = fault.get("phase")
            if ph and ph not in severity_by_phase:
                severity_by_phase[ph] = fault.get("severity")

        # 6b) Attach Coach Birdie tips per fault (reuse the existing RAG search)
        plan_faults = []
        for fault in faults:
            label = fault.get("label", "")
            tips = []
            for r in hybrid_search(label, k=2):
                tips.append({
                    "tip": r["tip"],
                    "fault_category": r["meta"].get("fault"),
                    "source_video": r["meta"].get("source_video"),
                })
            entry = dict(fault)
            entry["proGolferHeoTips"] = tips
            plan_faults.append(entry)

        # 6c) Build annotated key frames (image + phase + severity + what-to-look-at note)
        frame_out = []
        for f in frames:
            ph = f["phase"]
            frame_out.append({
                "phase": ph,
                "time": f["time"],
                "base64": f["base64"],
                "note": str(frame_notes.get(ph, "")).strip(),
                "severity": severity_by_phase.get(ph),
            })

        return {
            "overall": "",
            "summary": analysis["summary"],
            "handedness": analysis.get("handedness", "unknown"),
            "metrics": metrics,
            "frames": frame_out,
            "faults": plan_faults,
            "debug": analysis.get("debug", {}),
        }


# ---------------------------------------------------------------------------
# HTTP bridge for the mobile app.
#
# FastMCP runs on a Starlette/uvicorn server. `@mcp.custom_route` registers
# plain REST routes on that SAME server and port, so the iPhone app can call
# /health and /analyze without speaking the MCP protocol. /analyze reuses the
# real analyze_swing_video() engine above — no duplicated logic, no mock.
# ---------------------------------------------------------------------------

def _to_app_response(result: dict) -> dict:
    """Flatten the rich analysis into the shape the mobile app expects,
    while still returning the full analysis under `analysis` for future use."""
    faults = [f.get("label", "") for f in result.get("faults", []) if f.get("label")]

    tips = []
    for f in result.get("faults", []):
        for t in f.get("proGolferHeoTips", []):
            tip_text = t.get("tip")
            if tip_text and tip_text not in tips:
                tips.append(tip_text)

    coaching_tip = result.get("overall", "").strip()
    if tips:
        joined = "\n\n".join(tips[:3])
        coaching_tip = (coaching_tip + "\n\n" + joined).strip() if coaching_tip else joined

    report = {
        "summary": (result.get("summary") or result.get("overall", "")).strip(),
        "handedness": result.get("handedness", "unknown"),
        "metrics": result.get("metrics", []),
        "frames": result.get("frames", []),
        "faults": [
            {k: f.get(k) for k in ("label", "phase", "severity", "observation")}
            for f in result.get("faults", [])
        ],
        "debug": result.get("debug", {}),
    }

    return {
        "faults": faults or ["No major faults detected"],
        "coaching_tip": coaching_tip or "Your swing looks solid — keep it up!",
        "report": report,
    }


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Health check for the mobile app's 'Test Connection' button."""
    return JSONResponse({
        "status": "ok",
        "service": "Golf Coach MCP",
        "version": "1.0.0",
    })


@mcp.custom_route("/analyze", methods=["POST"])
async def analyze(request: Request) -> JSONResponse:
    """
    Receive a swing video from the mobile app and run the real analysis.

    Accepts either:
      - multipart/form-data with a `video` file (what the iPhone app sends), or
      - JSON body with `video_url` (direct http(s) link) or `video_base64`.
    """
    import base64 as _b64
    import datetime as _dt

    video_base64 = ""
    video_url = ""

    try:
        ctype = request.headers.get("content-type", "")
        if "multipart/form-data" in ctype:
            form = await request.form()
            upload = form.get("video")
            if upload is None or not hasattr(upload, "read"):
                return JSONResponse(
                    {"success": False, "error": "No 'video' file found in upload."},
                    status_code=400,
                )
            data = await upload.read()
            video_base64 = _b64.b64encode(data).decode()
        else:
            body = await request.json()
            video_url = body.get("video_url", "")
            video_base64 = body.get("video_base64", "")

        if not video_base64 and not video_url:
            return JSONResponse(
                {"success": False, "error": "Provide a video file, video_url, or video_base64."},
                status_code=400,
            )

        # analyze_swing_video is synchronous and does CPU + network work; run it
        # off the event loop so the server stays responsive.
        result = await run_in_threadpool(
            analyze_swing_video, video_url=video_url, video_base64=video_base64
        )

        if isinstance(result, dict) and result.get("error"):
            return JSONResponse(
                {"success": False, "error": result["error"]},
                status_code=502,
            )

        payload = _to_app_response(result)
        payload["success"] = True
        payload["timestamp"] = _dt.datetime.now().isoformat()
        return JSONResponse(payload)

    except Exception as e:  # noqa: BLE001
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


@mcp.custom_route("/chat", methods=["POST"])
async def chat(request: Request) -> JSONResponse:
    """
    Conversational coaching for the mobile app's Chat tab.

    Body: { "message": str, "history": [{ "role": "user"|"assistant", "content": str }] }
    Returns: { "success": true, "reply": str, "sources": [str] }

    Retrieves the most relevant Coach Birdie tips (same RAG search the MCP tools
    use) and has Claude answer in Coach Birdie's voice, grounded in those tips.
    """
    try:
        import anthropic  # noqa: F401

        body = await request.json()
        message = (body.get("message") or "").strip()
        history = body.get("history") or []

        if not message:
            return JSONResponse(
                {"success": False, "error": "Empty message."}, status_code=400
            )
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return JSONResponse(
                {"success": False, "error": "ANTHROPIC_API_KEY is not set on the server."},
                status_code=500,
            )

        # 1) Retrieve relevant Coach Birdie tips (reuse the existing RAG search)
        tips = []
        for r in hybrid_search(message, k=6):
            tips.append({
                "tip": r["tip"],
                "fault": r["meta"].get("fault"),
                "source_video": r["meta"].get("source_video"),
            })
        context = "\n\n".join(
            "- " + t["tip"] + (f"  (covers: {t['fault']})" if t.get("fault") else "")
            for t in tips
        ) or "(no specific tips matched — use general golf coaching best practices)"

        system = (
            "You are Coach Birdie, a friendly but THOROUGH PGA-level golf coach. The "
            "golfer wants a comprehensive answer they can actually follow through on at "
            "the range — never generic one-liners. Structure every coaching reply with "
            "clear labeled parts on their own lines:\n"
            "DIAGNOSIS: one line naming the most likely root cause.\n"
            "WHY IT HAPPENS: 1-2 sentences on the mechanics behind it.\n"
            "FIXES: 2-3 numbered fixes, each with the exact setup, position, or move "
            "(be specific about grip, stance, club, body part, and direction).\n"
            "DRILL: one drill with 2-3 numbered steps they can do at the range.\n"
            "FEEL / CUE: one simple swing thought to take into each shot.\n"
            "Be specific and practical, not vague. Ground your advice in the Coach Birdie "
            "coaching tips below; if they don't fully cover it, use sound golf "
            "fundamentals and say so briefly. Avoid medical claims. Stay encouraging. "
            "Aim for a complete but tight answer (roughly 150-250 words).\n\n"
            "Relevant Coach Birdie tips:\n" + context
        )

        # 2) Build the message list from prior turns + the new question
        msgs = []
        for h in history[-8:]:
            role = h.get("role")
            content = (h.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                msgs.append({"role": role, "content": content})
        msgs.append({"role": "user", "content": message})

        model = os.environ.get("GOLF_CLAUDE_MODEL", "claude-sonnet-4-6")
        client = anthropic.Anthropic()
        resp = await run_in_threadpool(
            lambda: client.messages.create(
                model=model, max_tokens=1024, system=system, messages=msgs
            )
        )
        reply = "".join(b.text for b in resp.content if b.type == "text").strip()

        return JSONResponse({
            "success": True,
            "reply": reply or "Sorry, I didn't catch that — can you rephrase?",
            "sources": [t["source_video"] for t in tips if t.get("source_video")],
        })

    except Exception as e:  # noqa: BLE001
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


_DRILLS_CACHE = None


@mcp.custom_route("/drills", methods=["GET"])
async def drills(request: Request) -> JSONResponse:
    """
    Return practice drills for the mobile app, in two categories:
      with_club    -> drills that need a club/ball
      without_club -> bodyweight / mirror / no-equipment drills

    Drills are generated once (then cached in memory) by grounding Claude in the
    same Coach Birdie tip library the MCP tools use. Pass ?refresh=1 to rebuild.
    """
    global _DRILLS_CACHE
    try:
        import json as _json
        import anthropic  # noqa: F401

        refresh = request.query_params.get("refresh") == "1"
        if _DRILLS_CACHE is not None and not refresh:
            return JSONResponse(_DRILLS_CACHE)

        if not os.environ.get("ANTHROPIC_API_KEY"):
            return JSONResponse(
                {"success": False, "error": "ANTHROPIC_API_KEY is not set on the server."},
                status_code=500,
            )

        # 1) Gather grounding tips from Coach Birdie's library (RAG)
        queries = [
            "takeaway drill", "tempo drill", "impact position", "swing path",
            "putting stroke", "weight shift", "wrist hinge", "alignment setup",
            "chipping", "early extension",
        ]
        grounding, seen = [], set()
        for q in queries:
            for r in hybrid_search(q, k=2):
                t = r["tip"]
                if t and t not in seen:
                    seen.add(t)
                    grounding.append(t)
        context = "\n".join("- " + t for t in grounding[:22]) or "(none)"

        system = (
            "You are Coach Birdie. Create a practical set of practice drills, grounded in "
            "the coaching tips below. Respond with ONLY a JSON object of the form "
            '{"with_club": [...], "without_club": [...]}. Each list has 4-5 drills. '
            'Each drill is {"title": str, "focus": str (the fault or skill it improves, '
            '3-6 words), "steps": [str, str, str] (2-4 short imperative steps)}. '
            "with_club = needs a club and/or ball. without_club = bodyweight, mirror, "
            "or household-object drills with no club. Keep them safe and beginner-friendly.\n\n"
            "Coach Birdie tips:\n" + context
        )
        model = os.environ.get("GOLF_CLAUDE_MODEL", "claude-sonnet-4-6")
        client = anthropic.Anthropic()
        resp = await run_in_threadpool(
            lambda: client.messages.create(
                model=model,
                max_tokens=1800,
                system=system,
                messages=[{"role": "user", "content": "Generate the drills JSON."}],
            )
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        lo, hi = text.find("{"), text.rfind("}")
        if lo != -1 and hi != -1:
            text = text[lo:hi + 1]
        data = _json.loads(text)

        out = {"with_club": [], "without_club": [], "success": True}
        for cat in ("with_club", "without_club"):
            for i, d in enumerate(data.get(cat, []) or []):
                steps = d.get("steps") or []
                if isinstance(steps, str):
                    steps = [steps]
                out[cat].append({
                    "id": f"{cat}-{i}",
                    "title": d.get("title", "Drill"),
                    "category": cat,
                    "focus": d.get("focus", ""),
                    "steps": [str(s) for s in steps][:5],
                })

        _DRILLS_CACHE = out
        return JSONResponse(out)

    except Exception as e:  # noqa: BLE001
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


_PRO_SWING_CACHE = None


@mcp.custom_route("/pro_swing", methods=["GET"])
async def pro_swing(request: Request) -> JSONResponse:
    """
    Return a breakdown of Tommy Fleetwood's swing for the mobile app's
    "Pro's Swing" tab: why it's elite and how an amateur can emulate it.
    Generated once via Claude (grounded in Coach Birdie principles) and cached.
    """
    global _PRO_SWING_CACHE
    try:
        import json as _json
        import anthropic  # noqa: F401

        refresh = request.query_params.get("refresh") == "1"
        if _PRO_SWING_CACHE is not None and not refresh:
            return JSONResponse(_PRO_SWING_CACHE)

        if not os.environ.get("ANTHROPIC_API_KEY"):
            return JSONResponse(
                {"success": False, "error": "ANTHROPIC_API_KEY is not set on the server."},
                status_code=500,
            )

        grounding, seen = [], set()
        for q in ["tempo", "rotation", "takeaway", "balance and finish",
                  "hand path", "wrist hinge", "weight shift"]:
            for r in hybrid_search(q, k=2):
                t = r["tip"]
                if t and t not in seen:
                    seen.add(t)
                    grounding.append(t)
        context = "\n".join("- " + t for t in grounding[:18]) or "(none)"

        system = (
            "You are Coach Birdie. Break down Tommy Fleetwood's golf swing for an "
            "improving amateur. Respond with ONLY a JSON object: "
            '{"summary": str, "why_good": [{"title": str, "detail": str}], '
            '"how_to_emulate": [{"title": str, "detail": str}]}. '
            "why_good: 4-5 points on what makes his swing world-class (e.g. tempo, "
            "rotation, neutral hand path, balance), each with a specific, vivid detail. "
            "how_to_emulate: 4-5 points an amateur can actually copy, each a concrete "
            "action, feel, or mini-drill (1-2 sentences). Be specific and practical. "
            "Ground it in these Coach Birdie principles where relevant:\n" + context
        )
        model = os.environ.get("GOLF_CLAUDE_MODEL", "claude-sonnet-4-6")
        client = anthropic.Anthropic()
        resp = await run_in_threadpool(
            lambda: client.messages.create(
                model=model,
                max_tokens=1600,
                system=system,
                messages=[{"role": "user", "content": "Generate the Tommy Fleetwood JSON."}],
            )
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        lo, hi = text.find("{"), text.rfind("}")
        if lo != -1 and hi != -1:
            text = text[lo:hi + 1]
        data = _json.loads(text)

        def _clean(items):
            out = []
            for d in items or []:
                out.append({
                    "title": str(d.get("title", "")).strip(),
                    "detail": str(d.get("detail", "")).strip(),
                })
            return out

        out = {
            "success": True,
            "player": "Tommy Fleetwood",
            "summary": str(data.get("summary", "")).strip(),
            "why_good": _clean(data.get("why_good")),
            "how_to_emulate": _clean(data.get("how_to_emulate")),
        }
        _PRO_SWING_CACHE = out
        return JSONResponse(out)

    except Exception as e:  # noqa: BLE001
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


if __name__ == "__main__":
    # streamable-http exposes the MCP endpoint at /mcp so it can be added
    # as a remote/custom connector (e.g. from the Claude mobile app).
    # The /health and /analyze custom routes above are served on the same port.
    mcp.run(transport="streamable-http")
