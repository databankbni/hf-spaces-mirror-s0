
"""
Multi-user YOLO detection service (FastAPI) — hardened build.

Lifecycle
─────────
POST /start  { "userId": "42" }  →  Spring Boot calls this when a user enables AI.
POST /stop   { "userId": "42" }  →  Spring Boot calls this when a user disables AI.

For every active user the service:
  1. Polls Spring Boot for detection settings   (which categories are enabled).
  2. Polls Spring Boot for assigned cameras      (RTSP stream names / IDs).
  3. Spawns one OpenCV-capture + YOLO thread per camera.
  4. POSTs detection payloads back to Spring Boot on every detection hit.

Robustness changes vs. the previous build (see inline comments marked HARDENED):
  - All YOLO / dlib calls are globally serialized. Concurrent forward passes on
    shared torch/ultralytics model objects across camera threads is what was
    causing native heap corruption -> silent segfault -> container restart
    every ~10 min. This was the actual root cause of "it stops detecting".
  - The serialization is done via a timed Semaphore (not a plain Lock), so on a
    small CPU a busy camera just SKIPS a frame instead of piling up a queue.
    Each camera also backs off its own polling interval adaptively when it's
    starved, and recovers when load drops. This is what makes it usable on a
    4-vCPU box without falling over.
  - Per-frame processing is wrapped so ONE bad frame / bad box / OCR hiccup
    never kills the camera's connection — it's logged and skipped, next frame
    processes normally.
  - Background poll loops (settings/discovery) can no longer die silently on
    an unexpected exception (e.g. malformed JSON) — they log and keep polling.
  - Stream-staleness detection: if a camera's reader thread is alive but hasn't
    produced a new frame in STREAM_STALE_TIMEOUT seconds (frozen RTSP session),
    it's torn down and reconnected instead of hanging forever.
  - A watchdog thread periodically logs thread counts + per-camera activity so
    "it just stopped" becomes a concrete timestamped log line instead of a
    mystery.
  - threading.excepthook is set so ANY uncaught thread exception is actually
    logged (previously it would just vanish to stderr and the thread would
    quietly die).
"""
import os

# ─────────────────────────────────────────────────────────────────────────────
# HARDENED: CPU thread limits — MUST be set before importing torch / ultralytics.
# Since all inference is serialized (see _infer_sema below), only ONE forward
# pass ever runs at a time, so it's fine — even desirable — to let that single
# pass use more than 1 thread. Tune INFER_THREADS to roughly (vCPUs - 1) so a
# core is always free for RTSP/FFmpeg decode, OCR, and the FastAPI event loop.
# On a 4-vCPU box, "2" is a reasonable default.
# ─────────────────────────────────────────────────────────────────────────────
_INFER_THREADS = os.getenv("INFER_THREADS", "2")
os.environ.setdefault("OMP_NUM_THREADS", _INFER_THREADS)
os.environ.setdefault("MKL_NUM_THREADS", _INFER_THREADS)
os.environ.setdefault("OPENBLAS_NUM_THREADS", _INFER_THREADS)
os.environ.setdefault("NUMEXPR_NUM_THREADS", _INFER_THREADS)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"

import gc
import sys
import traceback
import cv2
cv2.setNumThreads(1)  # OpenCV image ops (resize/CLAHE/color convert) stay single-threaded; torch handles the heavy math

import re
import base64
import threading
import time
import logging
import requests
import numpy as np
import face_recognition
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import torch
torch.set_num_threads(int(_INFER_THREADS))
torch.set_num_interop_threads(1)

from ultralytics import YOLO

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG via env or config for deeper traces
    format="%(asctime)s [%(levelname)s] %(threadName)s — %(message)s",
)
logger = logging.getLogger(__name__)


# HARDENED: without this, an uncaught exception in ANY background thread
# (settings poll, discovery, camera loop, frame-buffer reader) just prints to
# stderr and the thread dies silently — no log line, no alert, nothing.
def _thread_excepthook(args):
    tb = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    name = args.thread.name if args.thread else "unknown"
    logger.error("UNCAUGHT exception in thread '%s':\n%s", name, tb)


threading.excepthook = _thread_excepthook

# ── Config (all tuneable via environment) ────────────────────────────────────
MEDIAMTX_HOST          = os.getenv("MEDIAMTX_HOST",          "host.docker.internal")
MEDIAMTX_PORT          = int(os.getenv("MEDIAMTX_PORT",      "8554"))
SPRING_BASE_URL        = os.getenv("SPRING_BASE_URL",        "http://host.docker.internal:8081")
CONF_THRESHOLD         = float(os.getenv("CONF_THRESHOLD",   "0.4"))
SNAPSHOT_EVERY         = int(os.getenv("SNAPSHOT_EVERY",     "30"))   # frames between snapshots
MODEL_PATH             = os.getenv("MODEL_PATH",             "yolov8n.pt")
WEAPON_MODEL_PATH      = os.getenv("WEAPON_MODEL_PATH",      "weapon.pt")
WEAPON_CONF_THRESHOLD  = float(os.getenv("WEAPON_CONF_THRESHOLD", "0.5"))
PLATE_MODEL_PATH       = os.getenv("PLATE_MODEL_PATH",       "plate.pt")
PLATE_CONF_THRESHOLD   = float(os.getenv("PLATE_CONF_THRESHOLD", "0.45"))
PLATE_CROP_PAD         = float(os.getenv("PLATE_CROP_PAD",       "0.08"))
OCR_CONF_THRESHOLD     = float(os.getenv("OCR_CONF_THRESHOLD",   "0.20"))
RECONNECT_DELAY        = int(os.getenv("RECONNECT_DELAY",     "5"))
SETTINGS_POLL_INTERVAL = int(os.getenv("SETTINGS_POLL_INTERVAL", "15"))
CAMERA_POLL_INTERVAL   = int(os.getenv("CAMERA_POLL_INTERVAL",   "30"))
INFER_EVERY_N_SEC      = float(os.getenv("INFER_EVERY_N_SEC", "0.5"))  # baseline YOLO cadence per camera

# HARDENED: new tunables for robustness / low-CPU operation
INFER_SEMA_TIMEOUT     = float(os.getenv("INFER_SEMA_TIMEOUT", "2.0"))   # max wait for the inference slot before skipping a frame
FACE_SEMA_TIMEOUT      = float(os.getenv("FACE_SEMA_TIMEOUT",  "1.0"))   # max wait for the face-recognition slot
MAX_INFER_INTERVAL     = float(os.getenv("MAX_INFER_INTERVAL", "5.0"))   # adaptive per-camera backoff ceiling
STREAM_STALE_TIMEOUT   = float(os.getenv("STREAM_STALE_TIMEOUT", "20"))  # no new frame in this long -> force reconnect
GC_EVERY_N_FRAMES      = int(os.getenv("GC_EVERY_N_FRAMES", "100"))
WATCHDOG_INTERVAL      = int(os.getenv("WATCHDOG_INTERVAL", "30"))
POST_EXECUTOR_WORKERS  = int(os.getenv("POST_EXECUTOR_WORKERS", "10"))

# HARDENED: camera-fleet scaling — only ONLINE cameras get a capture thread.
# Without this, "assigned" simply meant "spawn a thread and let it fail/retry
# forever", which is how 50-camera deployments end up with 40 threads stuck
# in a reconnect loop against cameras that are known-offline in Spring Boot.
OFFLINE_GRACE_PERIOD   = float(os.getenv("OFFLINE_GRACE_PERIOD", "60"))  # camera must be OFFLINE this long before its thread is torn down
CAMERA_STATUS_BATCH    = int(os.getenv("CAMERA_STATUS_BATCH", "100"))    # cameras per /api/cameras/status call

post_executor = ThreadPoolExecutor(max_workers=POST_EXECUTOR_WORKERS)
DETECTION_URL = f"{SPRING_BASE_URL}/api/detections"
CAMERA_STATUS_URL = f"{SPRING_BASE_URL}/api/detections/status"

S3_BUCKET = os.getenv("S3_BUCKET", "cstvms-recordings")
S3_REGION = os.getenv("S3_REGION", "ap-south-1")

# ── COCO class / category / severity maps ────────────────────────────────────
CATEGORY_CLASS_MAP: dict[str, list[int]] = {
    "PERSON":  [0],
    "VEHICLE": [2, 3, 5, 7],
    "ANPR":    [2, 3, 5, 7],
    "WEAPON":  [],            # no COCO weapon class; placeholder for custom models
}

SEVERITY_MAP   = {"PERSON": "LOW", "VEHICLE": "LOW", "ANPR": "MEDIUM", "WEAPON": "CRITICAL", "BLACKLISTED": "CRITICAL"}
SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

# ── HARDENED: shared HTTP session with connection pooling + retries ─────────
# Every camera thread was doing its own `requests.get/post` with no pooling
# and no retry — one flaky network blip = one silently dropped payload.
_http_session = requests.Session()
try:
    from urllib3.util.retry import Retry
    _retry = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=[502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
    )
    _adapter = requests.adapters.HTTPAdapter(max_retries=_retry, pool_connections=20, pool_maxsize=20)
    _http_session.mount("http://", _adapter)
    _http_session.mount("https://", _adapter)
except Exception:
    logger.warning("Could not configure HTTP retry adapter — falling back to a plain session.", exc_info=True)


# ── Shared YOLO model (loaded once) ──────────────────────────────────────────
_model: YOLO | None = None
_model_lock = threading.Lock()


def get_model() -> YOLO:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                logger.info("Loading General YOLO model: %s", MODEL_PATH)
                _model = YOLO(MODEL_PATH)
                logger.info("General YOLO model loaded successfully.")
    return _model


# ── Weapon model (lazy-loaded, separate from the general COCO model) ─────────
_weapon_model: YOLO | None = None
_weapon_model_lock = threading.Lock()


def get_weapon_model() -> YOLO | None:
    """Lazy-load weapon.pt once; returns None if the file is missing."""
    global _weapon_model
    if _weapon_model is None:
        with _weapon_model_lock:
            if _weapon_model is None:
                if not os.path.exists(WEAPON_MODEL_PATH):
                    logger.warning("[WEAPON] Weapon model not found at path: '%s' — cwd is '%s'. Weapon detection disabled.", WEAPON_MODEL_PATH, os.getcwd())
                    return None
                try:
                    logger.info("Loading weapon model: %s", WEAPON_MODEL_PATH)
                    _weapon_model = YOLO(WEAPON_MODEL_PATH)
                    logger.info("Weapon model loaded successfully.")
                except Exception:
                    logger.error("[WEAPON] Failed to load weapon model — weapon detection disabled.", exc_info=True)
                    return None
    return _weapon_model


# ── Plate detection model (lazy-loaded, for ANPR) ────────────────────────────
_plate_model: YOLO | None = None
_plate_model_lock = threading.Lock()


def get_plate_model() -> YOLO | None:
    """Lazy-load plate.pt once; returns None if the file is missing."""
    global _plate_model
    if _plate_model is None:
        with _plate_model_lock:
            if _plate_model is None:
                if not os.path.exists(PLATE_MODEL_PATH):
                    logger.warning("[ANPR] Plate model not found at '%s' — ANPR will emit plain VEHICLE detections.", PLATE_MODEL_PATH)
                    return None
                try:
                    logger.info("Loading plate model: %s", PLATE_MODEL_PATH)
                    _plate_model = YOLO(PLATE_MODEL_PATH)
                    logger.info("Plate model loaded successfully.")
                except Exception:
                    logger.error("[ANPR] Failed to load plate model — ANPR disabled.", exc_info=True)
                    return None
    return _plate_model


# ── RapidOCR (lazy, CPU, loaded once) ────────────────────────────────────────
_ocr_reader = None
_ocr_lock   = threading.Lock()


def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        with _ocr_lock:
            if _ocr_reader is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                    logger.info("[ANPR] Initialising RapidOCR (CPU) — first call only...")
                    _ocr_reader = RapidOCR()
                    logger.info("[ANPR] RapidOCR ready.")
                except ImportError:
                    logger.error("[ANPR] rapidocr_onnxruntime not installed — OCR unavailable.")
                    _ocr_reader = None
                except Exception:
                    logger.error("[ANPR] Failed to initialise RapidOCR — OCR unavailable.", exc_info=True)
                    _ocr_reader = None
    return _ocr_reader


# ─────────────────────────────────────────────────────────────────────────────
# HARDENED: global inference / face-recognition serialization
#
# This is the fix for the recurring container restart. ultralytics/torch
# forward passes and dlib's face_recognition calls are NOT safe to run
# concurrently against shared model objects on CPU — doing so caused native
# heap corruption (an uncatchable segfault, not a Python exception), which is
# why nothing ever showed up in the logs before the process just vanished.
#
# Semaphore (not Lock) is used deliberately: on a small CPU, if a camera can't
# get the slot within the timeout, it just skips that frame rather than
# blocking indefinitely and letting a backlog build up.
# ─────────────────────────────────────────────────────────────────────────────
_infer_sema = threading.Semaphore(1)   # serializes ALL YOLO forward passes (general / weapon / plate)
_face_sema  = threading.Semaphore(1)   # serializes ALL dlib / face_recognition calls


def _safe_yolo_infer(model: YOLO, image, timeout: float = INFER_SEMA_TIMEOUT, **kwargs):
    """
    Thread-safe wrapper around any YOLO(...) forward pass.
    Returns the ultralytics Results list on success, or None if the inference
    slot couldn't be acquired in time (camera should skip this frame) or if
    the model call itself raised (logged, frame skipped).
    """
    if not _infer_sema.acquire(timeout=timeout):
        return None
    try:
        with torch.inference_mode():
            return model(image, verbose=False, **kwargs)
    except Exception:
        logger.error("YOLO inference call failed — skipping this frame.", exc_info=True)
        return None
    finally:
        _infer_sema.release()


def _safe_face_locations(rgb_image, timeout: float = FACE_SEMA_TIMEOUT) -> list:
    if not _face_sema.acquire(timeout=timeout):
        return []
    try:
        return face_recognition.face_locations(rgb_image)
    except Exception:
        logger.error("face_recognition.face_locations failed — skipping face check.", exc_info=True)
        return []
    finally:
        _face_sema.release()


def _safe_face_encodings(rgb_image, locations, timeout: float = FACE_SEMA_TIMEOUT) -> list:
    if not _face_sema.acquire(timeout=timeout):
        return []
    try:
        return face_recognition.face_encodings(rgb_image, locations)
    except Exception:
        logger.error("face_recognition.face_encodings failed — skipping face check.", exc_info=True)
        return []
    finally:
        _face_sema.release()


# ── Indian plate regex + OCR helpers ─────────────────────────────────────────
_IN_PLATE_RE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$")


def _clean_plate_text(raw: str) -> str:
    """Upper-case, strip separators, fix common OCR substitutions."""
    cleaned = re.sub(r"[\s\-\.]", "", raw.upper())
    return (
        cleaned
        .replace("O", "0").replace("I", "1").replace("Q", "0")
        .replace("S", "5").replace("B", "8")
    )


def _preprocess_for_ocr(crop: np.ndarray) -> np.ndarray:
    """Upscale + sharpen + CLAHE — improves OCR hit rate on small plate crops."""
    h, w = crop.shape[:2]
    target_w = 300
    if w < target_w and w > 0:
        scale = target_w / w
        crop = cv2.resize(crop, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    gray    = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (0, 0), 2)
    sharp   = cv2.addWeighted(gray, 2.0, blurred, -1.0, 0)
    clahe   = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(sharp)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)


def _parse_rapid_result(result) -> tuple[str, float]:
    """Extract highest-confidence text block from RapidOCR output."""
    if not result or not result[0]:
        return "", 0.0
    best_text, best_conf = "", 0.0
    for item in result[0]:
        if len(item) < 3:
            continue
        text, conf = item[1], float(item[2])
        if conf > best_conf:
            best_text, best_conf = text, conf
    return best_text, best_conf


def _safe_ocr_call(ocr, image) -> tuple[str, float]:
    """HARDENED: RapidOCR can raise on odd crops (zero-size, wrong dtype, etc).
    Never let that propagate and kill the camera loop."""
    try:
        result, _ = ocr(image)
        return _parse_rapid_result((result, None))
    except Exception:
        logger.debug("[ANPR] OCR call raised an exception — treating as no text found.", exc_info=True)
        return "", 0.0


def _run_anpr_on_vehicle_crop(frame: np.ndarray, vx1: int, vy1: int, vx2: int, vy2: int) -> str | None:
    """
    Given a vehicle bounding box from the COCO model, run the plate YOLO model
    on that crop, then OCR any detected plate region.
    """
    plate_model = get_plate_model()
    if plate_model is None:
        return None

    ocr = _get_ocr_reader()
    if ocr is None:
        return None

    fh, fw = frame.shape[:2]

    # ── Slightly expand the vehicle crop so a plate near the edge isn't clipped
    pad = 10
    cx1 = max(0, vx1 - pad)
    cy1 = max(0, vy1 - pad)
    cx2 = min(fw, vx2 + pad)
    cy2 = min(fh, vy2 + pad)
    vehicle_crop = frame[cy1:cy2, cx1:cx2]

    if vehicle_crop.size == 0:
        logger.debug("[ANPR] Vehicle crop size is 0. Skipping.")
        return None

    plate_results_list = _safe_yolo_infer(plate_model, vehicle_crop, conf=PLATE_CONF_THRESHOLD)
    if plate_results_list is None:
        return None
    plate_results = plate_results_list[0]
    if not plate_results.boxes:
        logger.debug("[ANPR] No plate detected in vehicle crop.")
        return None

    try:
        # ── Pick the highest-confidence plate box ────────────────────────────
        best_conf_box = max(plate_results.boxes, key=lambda b: float(b.conf[0]))
        px1, py1, px2, py2 = [float(v) for v in best_conf_box.xyxy[0]]

        # ── Crop plate with padding ──────────────────────────────────────────
        ch, cw = vehicle_crop.shape[:2]
        pp = PLATE_CROP_PAD
        ppx = (px2 - px1) * pp
        ppy = (py2 - py1) * pp
        rx1 = max(0, int(px1 - ppx))
        ry1 = max(0, int(py1 - ppy))
        rx2 = min(cw, int(px2 + ppx))
        ry2 = min(ch, int(py2 + ppy))
        plate_crop = vehicle_crop[ry1:ry2, rx1:rx2]
    except Exception:
        logger.debug("[ANPR] Failed to compute/crop plate region.", exc_info=True)
        return None

    if plate_crop.size == 0:
        logger.debug("[ANPR] Plate crop size is 0 after padding. Skipping.")
        return None

    # ── OCR — try pre-processed first, fall back to raw colour ──────────────
    try:
        processed = _preprocess_for_ocr(plate_crop)
    except Exception:
        logger.debug("[ANPR] Pre-processing failed, using raw crop.", exc_info=True)
        processed = plate_crop

    text, conf = _safe_ocr_call(ocr, processed)

    if conf < OCR_CONF_THRESHOLD:
        logger.debug("[ANPR] Pre-processed OCR conf %.2f too low, falling back to raw.", conf)
        text, conf = _safe_ocr_call(ocr, plate_crop)

    if conf < OCR_CONF_THRESHOLD or not text:
        logger.debug("[ANPR] Final OCR conf %.2f below threshold %.2f, or no text found.", conf, OCR_CONF_THRESHOLD)
        return None

    cleaned = _clean_plate_text(text)
    logger.debug("[ANPR] Plate detected successfully: raw='%s', cleaned='%s', conf=%.2f", text, cleaned, conf)
    return cleaned if cleaned else None


# ─────────────────────────────────────────────────────────────────────────────
# LatestFrameBuffer — decouples RTSP reading from YOLO inference
# ─────────────────────────────────────────────────────────────────────────────

class LatestFrameBuffer:
    def __init__(self, rtsp_url: str):
        self.rtsp_url = rtsp_url
        logger.debug("Initialising video capture for %s", rtsp_url)
        self._cap      = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        self._cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10_000)
        self._cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10_000)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._frame: object     = None
        self._lock              = threading.Lock()
        self._stop_event        = threading.Event()
        self._opened             = self._cap.isOpened()
        self._error: str | None = None
        # HARDENED: track when we last got a frame so callers can detect a
        # frozen-but-still-"open" stream (reader thread alive, no new data).
        self._last_frame_time   = time.monotonic()

        self._reader = threading.Thread(
            target=self._read_loop,
            daemon=True,
            name=f"framebuf-{rtsp_url[-20:]}",
        )

    def start(self):
        if self._opened:
            logger.info("Starting frame reader thread: %s", self._reader.name)
            self._reader.start()
        else:
            logger.error("Failed to open video capture for %s", self.rtsp_url)
        return self

    def is_opened(self) -> bool:
        return self._opened

    def get(self):
        with self._lock:
            if self._frame is None:
                return False, None
            f = self._frame.copy()
            self._frame = None
            return True, f

    def is_running(self) -> bool:
        return self._reader.is_alive()

    def time_since_last_frame(self) -> float:
        with self._lock:
            return time.monotonic() - self._last_frame_time

    def stop(self):
        logger.info("Stopping frame buffer: %s", self._reader.name)
        self._stop_event.set()
        if self._reader.is_alive():
            self._reader.join(timeout=3)
        try:
            self._cap.release()
        except Exception:
            logger.debug("Error releasing VideoCapture for %s", self.rtsp_url, exc_info=True)
        logger.debug("Released video capture for %s", self.rtsp_url)

    def _read_loop(self):
        logger.debug("Entered read loop for %s", self._reader.name)
        consecutive_errors = 0
        while not self._stop_event.is_set():
            try:
                ret, frame = self._cap.read()
            except Exception:
                # HARDENED: cv2/FFmpeg can throw on a corrupt stream instead of
                # just returning False — don't let that kill the thread silently.
                logger.warning("Exception while reading frame in %s.", self._reader.name, exc_info=True)
                ret, frame = False, None

            if not ret or frame is None:
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    self._error = "stream ended or repeated frame read failures"
                    logger.warning("Repeated read failures in %s. Exiting read loop for reconnect.", self._reader.name)
                    break
                time.sleep(0.05)
                continue

            consecutive_errors = 0
            with self._lock:
                self._frame = frame
                self._last_frame_time = time.monotonic()


# ─────────────────────────────────────────────────────────────────────────────
# HARDENED: per-camera activity tracking, used by the watchdog and /status
# ─────────────────────────────────────────────────────────────────────────────
_camera_last_activity: dict[tuple[str, str], float] = {}
_activity_lock = threading.Lock()


def _fetch_camera_statuses(names: list[str], token:str) -> dict[str, str]:
    """
    Calls Spring Boot's POST /api/cameras/status with a batch of camera names
    and returns {name: "ACTIVE"|"INACTIVE"}.

    HARDENED: fail-open. On any network/parse error this returns {} rather
    than raising, and callers treat a missing entry as "unknown -> assume
    online" (see _discover_cameras). Otherwise a transient blip on this one
    endpoint would look identical to "every camera just went offline" and
    tear down the whole fleet's capture threads at once.
    """
    if not names:
        return {}
    statuses: dict[str, str] = {}
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        for i in range(0, len(names), CAMERA_STATUS_BATCH):
            chunk = names[i:i + CAMERA_STATUS_BATCH]
            resp = _http_session.post(CAMERA_STATUS_URL, json=chunk, headers=headers, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                logger.error("Camera status response was not a JSON object — ignoring this batch.")
                continue
            statuses.update(data)
    except (requests.RequestException, ValueError) as e:
        logger.error("Cannot fetch/parse camera statuses from Spring Boot: %s", e)
        return {}
    return statuses


def _touch_activity(user_id: str, camera_id: str):
    with _activity_lock:
        _camera_last_activity[(user_id, camera_id)] = time.monotonic()


def _clear_activity(user_id: str, camera_id: str):
    with _activity_lock:
        _camera_last_activity.pop((user_id, camera_id), None)


# ─────────────────────────────────────────────────────────────────────────────
# Per-user state
# ─────────────────────────────────────────────────────────────────────────────

class UserSession:
    def __init__(self, user_id: str, token:str):
        self.user_id   = user_id
        self.token = token # Store the token
        self._lock     = threading.RLock()
        self._active   = True

        # Detection filter state
        self._active_classes:    set[int] = set()
        self._active_categories: set[str] = set()

        # Blacklist State
        self._blacklist_enabled = False
        self._last_blacklist_fetch_time = 0.0
        self._known_face_encodings = []
        self._known_face_names = []

        self._camera_threads: dict[str, threading.Thread] = {}
        # HARDENED: tracks how long each still-assigned camera has been
        # reported OFFLINE by Spring Boot, so a brief flap doesn't tear the
        # thread down — only a sustained outage (>= OFFLINE_GRACE_PERIOD) does.
        self._camera_offline_since: dict[str, float] = {}

        self._settings_thread  = threading.Thread(
            target=self._settings_poll_loop,
            daemon=True,
            name=f"settings-{user_id}",
        )
        self._discovery_thread = threading.Thread(
            target=self._camera_discovery_loop,
            daemon=True,
            name=f"discovery-{user_id}",
        )

    def start(self):
        logger.info("[user=%s] Session starting. Initialising discovery and settings polling.", self.user_id)
        self._fetch_settings()
        self._settings_thread.start()
        self._discovery_thread.start()

    def stop(self):
        logger.info("[user=%s] Session stopping. Terminating all tasks.", self.user_id)
        with self._lock:
            self._active = False
            camera_ids = list(self._camera_threads.keys())
            self._camera_threads.clear()
        for cam in camera_ids:
            _clear_activity(self.user_id, cam)

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    # ── Settings polling ──────────────────────────────────────────────────────
    def _settings_poll_loop(self):
        logger.debug("[user=%s] Settings polling thread started.", self.user_id)
        while self.is_active:
            try:
                self._fetch_settings()
            except Exception:
                # HARDENED: this loop must never die — an uncaught exception
                # here previously meant settings silently stopped refreshing
                # forever (thread dies, no error visible anywhere).
                logger.error("[user=%s] Unexpected error in settings poll loop.", self.user_id, exc_info=True)
            time.sleep(SETTINGS_POLL_INTERVAL)

    def _fetch_settings(self):
        url = f"{SPRING_BASE_URL}/api/detection-settings/{self.user_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            logger.debug("[user=%s] Fetching detection settings from Spring Boot: %s", self.user_id, url)
            resp = _http_session.get(url, headers=headers, timeout=5)
            resp.raise_for_status()
            cfg = resp.json()
            logger.debug("[user=%s] Received settings: %s", self.user_id, cfg)
        except (requests.RequestException, ValueError) as e:
            logger.error("[user=%s] Cannot fetch/parse settings from Spring Boot: %s", self.user_id, e)
            return

        if not isinstance(cfg, dict):
            logger.error("[user=%s] Settings response was not a JSON object — ignoring.", self.user_id)
            return

        classes:    set[int] = set()
        categories: set[str] = set()

        flag_map = {
            "personEnabled":  "PERSON",
            "vehicleEnabled": "VEHICLE",
            "anprEnabled":    "ANPR",
            "weaponEnabled":  "WEAPON",
        }

        for flag, category in flag_map.items():
            if cfg.get(flag):
                categories.add(category)
                if category in CATEGORY_CLASS_MAP:
                    classes.update(CATEGORY_CLASS_MAP[category])

        with self._lock:
            if self._active_categories != categories:
                logger.info("[user=%s] Detection categories updated: %s -> %s", self.user_id, self._active_categories, categories)

            self._active_classes    = classes
            self._active_categories = categories

            # Check if blacklist was toggled on
            was_blacklist_enabled = self._blacklist_enabled
            self._blacklist_enabled = bool(cfg.get("blacklistEnabled", False))

            if self._blacklist_enabled != was_blacklist_enabled:
                logger.info("[user=%s] Blacklist enabled status changed: %s -> %s", self.user_id, was_blacklist_enabled, self._blacklist_enabled)

            # Fetch faces if newly enabled, or if it's enabled but we have no cached encodings
            if self._blacklist_enabled:
                now = time.time()
                if not was_blacklist_enabled or (now - self._last_blacklist_fetch_time > 600):
                    self._last_blacklist_fetch_time = now
                    logger.debug("[user=%s] Triggering background fetch of blacklisted faces.", self.user_id)
                    threading.Thread(target=self._load_blacklisted_faces, daemon=True,
                                      name=f"blacklist-{self.user_id}").start()

    def _load_blacklisted_faces(self):
        url = f"{SPRING_BASE_URL}/api/blacklist/{self.user_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        logger.info("[user=%s] Fetching blacklist details from %s", self.user_id, url)
        try:
            resp = _http_session.get(url, headers=headers, timeout=5)
            resp.raise_for_status()
            people = resp.json()
            if not isinstance(people, list):
                logger.error("[user=%s] Blacklist response was not a JSON list — ignoring.", self.user_id)
                return
            logger.info("[user=%s] Spring Boot returned %d records from the blacklist database.", self.user_id, len(people))

            encodings = []
            names = []

            for person in people:
                if not isinstance(person, dict):
                    continue
                person_name = person.get("name", "Unknown")
                try:
                    photo_key = person.get("photoKey")
                    if not photo_key:
                        logger.warning("[user=%s] Blacklist: Missing 'photoKey' for %s", self.user_id, person_name)
                        continue

                    photo_url = person.get("photoUrl")
                    if not photo_url:
                        logger.warning("[user=%s] Blacklist: Missing 'photoUrl' for %s", self.user_id, person_name)
                        continue

                    logger.debug("[user=%s] Downloading S3 image for %s...", self.user_id, person_name)
                    img_resp = _http_session.get(photo_url, timeout=10)
                    img_resp.raise_for_status()

                    np_arr = np.frombuffer(img_resp.content, np.uint8)
                    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                    if img is not None:
                        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        face_locs = _safe_face_locations(rgb_img)

                        if face_locs:
                            encs = _safe_face_encodings(rgb_img, face_locs)
                            if encs:
                                encodings.append(encs[0])
                                names.append(person_name)
                                logger.debug("[user=%s] Successfully extracted face encoding for %s", self.user_id, person_name)
                        else:
                            logger.warning("[user=%s] Blacklist: No face found in S3 image for %s", self.user_id, person_name)
                    else:
                        logger.warning("[user=%s] Blacklist: Failed to decode image bytes for %s", self.user_id, person_name)

                except Exception as e:
                    logger.error("[user=%s] Failed to process face for %s: %s", self.user_id, person_name, e, exc_info=True)

            with self._lock:
                self._known_face_encodings = encodings
                self._known_face_names = names
            logger.info("[user=%s] Successfully loaded %d blacklisted face encodings into memory.", self.user_id, len(names))

        except (requests.RequestException, ValueError) as e:
            logger.error("[user=%s] Cannot fetch blacklist records: %s", self.user_id, e)
        except Exception:
            logger.error("[user=%s] Unexpected error while loading blacklisted faces.", self.user_id, exc_info=True)

    def get_active_filters(self) -> tuple[set[int], set[str]]:
        with self._lock:
            return set(self._active_classes), set(self._active_categories)

    # ── Camera discovery ──────────────────────────────────────────────────────
    def _camera_discovery_loop(self):
        logger.debug("[user=%s] Camera discovery thread started.", self.user_id)
        while self.is_active:
            try:
                self._discover_cameras()
            except Exception:
                # HARDENED: same reasoning as settings poll loop.
                logger.error("[user=%s] Unexpected error in camera discovery loop.", self.user_id, exc_info=True)
            time.sleep(CAMERA_POLL_INTERVAL)

    def _discover_cameras(self):
        url = f"{SPRING_BASE_URL}/api/cameras/active-names/{self.user_id}"
        
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            logger.debug("[user=%s] Polling active cameras...", self.user_id)
            resp = _http_session.get(url, headers=headers, timeout=5)
            resp.raise_for_status()
            raw = resp.json()
            if not isinstance(raw, list):
                logger.error("[user=%s] Active-cameras response was not a JSON list — ignoring.", self.user_id)
                return
            names: list[str] = [n.strip() for n in raw if isinstance(n, str) and n.strip()]
            logger.debug("[user=%s] Discovered cameras: %s", self.user_id, names)
        except (requests.RequestException, ValueError, TypeError) as e:
            logger.error("[user=%s] Cannot fetch/parse cameras from Spring Boot: %s", self.user_id, e)
            return

        # HARDENED: resolve ONLINE/OFFLINE for every assigned camera before
        # touching any threads. Only ONLINE cameras get spawned; a camera can
        # be "assigned" to a user (50 cameras) while only a fraction of those
        # are actually reachable at any given moment (10 online) — we should
        # only ever be running capture threads for the latter.
        statuses = _fetch_camera_statuses(names, self.token)
        online_names: set[str] = set()
        for n in names:
            status = statuses.get(n)
            if status is None:
                # Status endpoint didn't return this camera (or the whole
                # call failed -> statuses == {}). Fail OPEN: treat as online
                # rather than silently dropping a camera because the status
                # service hiccupped.
                online_names.add(n)
            elif status.strip().upper() == "ACTIVE":
                online_names.add(n)

        with self._lock:
            if not self._active:
                return

            now = time.monotonic()

            # ── Spawn threads for online, not-yet-running cameras ───────────
            for cam in online_names:
                existing = self._camera_threads.get(cam)
                if existing is not None and existing.is_alive():
                    self._camera_offline_since.pop(cam, None)  # confirmed online again, clear any grace timer
                    continue
                logger.info("[user=%s] Spawning new capture thread for online camera: %s", self.user_id, cam)
                t = threading.Thread(
                    target=self._run_camera_loop,
                    args=(cam,),
                    daemon=True,
                    name=f"cam-{self.user_id}-{cam}",
                )
                self._camera_threads[cam] = t
                self._camera_offline_since.pop(cam, None)
                t.start()
                time.sleep(2.0)  # stagger camera startup to avoid a thundering herd on the network/model load

            # ── Cameras fully unassigned from this user -> stop immediately ──
            unassigned = set(self._camera_threads.keys()) - set(names)
            for cam in unassigned:
                logger.info("[user=%s] Camera '%s' removed from assignment. Thread will terminate.", self.user_id, cam)
                del self._camera_threads[cam]
                self._camera_offline_since.pop(cam, None)
                _clear_activity(self.user_id, cam)

            # ── Cameras still assigned but currently OFFLINE -> grace period,
            #    then stop. Avoids killing a thread over a few seconds' flap
            #    while still enforcing "offline for 1 min+ -> out of YOLO".
            assigned_but_offline = (set(names) - online_names) & set(self._camera_threads.keys())
            for cam in assigned_but_offline:
                since = self._camera_offline_since.setdefault(cam, now)
                offline_for = now - since
                if offline_for >= OFFLINE_GRACE_PERIOD:
                    logger.info(
                        "[user=%s] Camera '%s' has been OFFLINE for %.0fs (>= %.0fs grace) — stopping capture thread.",
                        self.user_id, cam, offline_for, OFFLINE_GRACE_PERIOD,
                    )
                    del self._camera_threads[cam]
                    self._camera_offline_since.pop(cam, None)
                    _clear_activity(self.user_id, cam)
                else:
                    logger.debug(
                        "[user=%s] Camera '%s' reported OFFLINE for %.0fs (< %.0fs grace) — keeping thread alive.",
                        self.user_id, cam, offline_for, OFFLINE_GRACE_PERIOD,
                    )

    # ── Camera processing ─────────────────────────────────────────────────────
    def _run_camera_loop(self, camera_id: str):
        logger.info("[user=%s][cam=%s] Entering camera processing loop.", self.user_id, camera_id)
        while self.is_active:
            with self._lock:
                if camera_id not in self._camera_threads:
                    logger.info("[user=%s][cam=%s] Camera unassigned. Exiting thread loop.", self.user_id, camera_id)
                    return

            try:
                self._process_camera(camera_id)
            except Exception:
                logger.error("[user=%s][cam=%s] Unexpected error in camera loop.", self.user_id, camera_id, exc_info=True)

            if not self.is_active:
                return

            with self._lock:
                if camera_id not in self._camera_threads:
                    return

            logger.info("[user=%s][cam=%s] Reconnecting in %ds...", self.user_id, camera_id, RECONNECT_DELAY)
            time.sleep(RECONNECT_DELAY)

    def _process_camera(self, camera_id: str):
        rtsp_url = f"rtsp://{MEDIAMTX_HOST}:{MEDIAMTX_PORT}/{camera_id}?token={self.token}"

        logger.info("[user=%s][cam=%s] Starting stream buffer from %s", self.user_id, camera_id, rtsp_url)
        buf = LatestFrameBuffer(rtsp_url).start()

        if not buf.is_opened():
            logger.error("[user=%s][cam=%s] Buffer failed to open stream. Aborting process.", self.user_id, camera_id)
            buf.stop()
            return

        model             = get_model()
        frame_count       = 0
        last_infer_time   = 0.0
        adaptive_interval = INFER_EVERY_N_SEC  # HARDENED: per-camera adaptive backoff under CPU pressure

        try:
            logger.info("[user=%s][cam=%s] Connected to stream successfully. Inference started.", self.user_id, camera_id)
            while self.is_active:
                if not buf.is_running():
                    logger.warning("[user=%s][cam=%s] Buffer thread died. Ending inference loop.", self.user_id, camera_id)
                    break

                # HARDENED: frozen-stream detection — reader thread alive but no new frames.
                if buf.time_since_last_frame() > STREAM_STALE_TIMEOUT:
                    logger.warning(
                        "[user=%s][cam=%s] No new frame in over %.0fs — stream appears stalled, forcing reconnect.",
                        self.user_id, camera_id, STREAM_STALE_TIMEOUT,
                    )
                    break

                with self._lock:
                    if camera_id not in self._camera_threads:
                        logger.info("[user=%s][cam=%s] Processing aborted; camera no longer assigned.", self.user_id, camera_id)
                        return

                general_results = None
                weapon_results  = None
                frame           = None

                # HARDENED: the entire per-frame body is isolated. Any unexpected
                # error here (bad box math, OCR edge case, malformed frame, etc.)
                # is logged and the loop moves on to the next frame — it no
                # longer tears down the whole camera connection.
                try:
                    ret, frame = buf.get()
                    if not ret or frame is None or frame.size == 0:
                        time.sleep(0.01)
                        continue

                    now = time.monotonic()
                    if now - last_infer_time < adaptive_interval:
                        time.sleep(0.005)
                        continue
                    last_infer_time = now

                    frame_count += 1
                    allowed_classes, active_categories = self.get_active_filters()

                    if not allowed_classes and "WEAPON" not in active_categories:
                        continue

                    inference_attempted = False
                    inference_skipped   = False

                    # ── Pass 1: general COCO model (PERSON / VEHICLE / ANPR) ──
                    if allowed_classes:
                        inference_attempted = True
                        general_results = _safe_yolo_infer(
                            model, frame, timeout=INFER_SEMA_TIMEOUT,
                            conf=CONF_THRESHOLD, classes=list(allowed_classes),
                        )
                        if general_results is None:
                            inference_skipped = True

                    # ── Pass 2: weapon model ───────────────────────────────────
                    if "WEAPON" in active_categories:
                        wm = get_weapon_model()
                        if wm is not None:
                            inference_attempted = True
                            weapon_results = _safe_yolo_infer(wm, frame, timeout=INFER_SEMA_TIMEOUT, conf=WEAPON_CONF_THRESHOLD)
                            if weapon_results is None:
                                inference_skipped = True

                    # HARDENED: adaptive backoff — if the shared inference slot
                    # was too busy to serve this camera, back off its cadence;
                    # recover gradually once it starts getting served promptly.
                    if inference_attempted:
                        if inference_skipped:
                            adaptive_interval = min(adaptive_interval * 1.5, MAX_INFER_INTERVAL)
                        else:
                            adaptive_interval = max(INFER_EVERY_N_SEC, adaptive_interval * 0.9)

                    has_general = general_results is not None and general_results[0].boxes
                    has_weapon  = weapon_results  is not None and weapon_results[0].boxes

                    if has_general or has_weapon:
                        payload = _build_payload(
                            camera_id=camera_id,
                            user_id=self.user_id,
                            general_results=general_results,
                            weapon_results=weapon_results,
                            frame=frame,
                            frame_count=frame_count,
                            allowed_classes=allowed_classes,
                            session=self,
                        )

                        if payload:
                            logger.debug("[user=%s][cam=%s] Detection payload built with %d items.", self.user_id, camera_id, len(payload["detections"]))
                            post_executor.submit(_post_payload, payload, self.token)

                    _touch_activity(self.user_id, camera_id)

                except Exception:
                    logger.error(
                        "[user=%s][cam=%s] Error while processing a frame — skipping it, camera stays connected.",
                        self.user_id, camera_id, exc_info=True,
                    )
                finally:
                    # Drop references promptly so gc can reclaim the frame/results.
                    del frame
                    del general_results
                    del weapon_results

                if frame_count and frame_count % GC_EVERY_N_FRAMES == 0:
                    gc.collect()
        finally:
            logger.info("[user=%s][cam=%s] Cleaning up camera buffer.", self.user_id, camera_id)
            buf.stop()
            _clear_activity(self.user_id, camera_id)


# ─────────────────────────────────────────────────────────────────────────────
# Detection helpers
# ─────────────────────────────────────────────────────────────────────────────

def _classify_category(cls_id: int) -> str | None:
    for category, ids in CATEGORY_CLASS_MAP.items():
        if cls_id in ids:
            return category
    return None


def _severity_for_categories(categories: set[str]) -> str:
    best = "LOW"
    for cat in categories:
        sev = SEVERITY_MAP.get(cat, "LOW")
        if SEVERITY_ORDER.index(sev) > SEVERITY_ORDER.index(best):
            best = sev
    return best


def _frame_to_base64(frame) -> str | None:
    try:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return None
        return base64.b64encode(buf).decode("utf-8")
    except Exception:
        logger.error("Failed to encode snapshot to base64.", exc_info=True)
        return None


def _build_payload(
    camera_id: str,
    user_id: str,
    general_results,
    weapon_results,
    frame,
    frame_count: int,
    allowed_classes: set[int],
    session: UserSession,
) -> dict | None:
    detections: list[dict] = []
    categories_seen: set[str] = set()
    h, w = frame.shape[:2]

    with session._lock:
        is_blacklist_active = session._blacklist_enabled
        known_encodings     = list(session._known_face_encodings)
        known_names         = list(session._known_face_names)
        anpr_enabled        = "ANPR" in session._active_categories

    # ── General COCO detections (PERSON / VEHICLE / ANPR) ────────────────────
    if general_results is not None and general_results[0].boxes:
        for box in general_results[0].boxes:
            # HARDENED: one malformed box should never drop the rest of the frame's detections.
            try:
                cls_id = int(box.cls[0])
                if cls_id not in allowed_classes:
                    continue
                category = _classify_category(cls_id)
                if category is None:
                    continue

                base_label = general_results[0].names[cls_id]
                label      = base_label
                conf       = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                IS_VEHICLE_CLASS = cls_id in (2, 3, 5, 7)
                plate_text: str | None = None

                if IS_VEHICLE_CLASS and anpr_enabled:
                    plate_text = _run_anpr_on_vehicle_crop(frame, x1, y1, x2, y2)

                if IS_VEHICLE_CLASS:
                    if plate_text:
                        category = "ANPR"
                        label    = f"{base_label} - {plate_text}"
                    else:
                        category = "VEHICLE"
                        label    = base_label

                # ── Face Recognition Injection (PERSON only) ─────────────────
                if category == "PERSON" and is_blacklist_active and known_encodings:
                    crop_y1 = max(0, y1 - 20)
                    crop_y2 = min(h, y2 + 20)
                    crop_x1 = max(0, x1 - 20)
                    crop_x2 = min(w, x2 + 20)
                    crop = frame[crop_y1:crop_y2, crop_x1:crop_x2]

                    if crop.size != 0:
                        rgb_crop       = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                        face_locations = _safe_face_locations(rgb_crop)

                        if face_locations:
                            face_encodings_list = _safe_face_encodings(rgb_crop, face_locations)
                            for face_encoding in face_encodings_list:
                                try:
                                    matches = face_recognition.compare_faces(known_encodings, face_encoding)
                                except Exception:
                                    logger.error("face_recognition.compare_faces failed.", exc_info=True)
                                    continue
                                if True in matches:
                                    first_match_index = matches.index(True)
                                    name     = known_names[first_match_index]
                                    category = "BLACKLISTED"
                                    label    = f"PERSON - {name}"
                                    logger.warning("[user=%s][cam=%s] Blacklisted person detected: %s (conf: %.2f)", user_id, camera_id, name, conf)
                                    break
                        else:
                            logger.debug("[user=%s] Blacklist match attempted but no face found in person crop.", user_id)

                detection_entry: dict = {
                    "label":       label,
                    "category":    category,
                    "confidence":  round(conf, 4),
                    "x":           x1,
                    "y":           y1,
                    "width":       x2 - x1,
                    "height":      y2 - y1,
                    "frameWidth":  w,
                    "frameHeight": h,
                }
                if plate_text:
                    detection_entry["plateText"] = plate_text

                detections.append(detection_entry)
                categories_seen.add(category)

            except Exception:
                logger.error("[user=%s][cam=%s] Failed to process a general detection box — skipping it.", user_id, camera_id, exc_info=True)
                continue

    # ── Weapon model detections ───────────────────────────────────────────────
    if weapon_results is not None and weapon_results[0].boxes:
        for box in weapon_results[0].boxes:
            try:
                cls_id = int(box.cls[0])
                label  = weapon_results[0].names[cls_id]
                conf   = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                logger.warning("[user=%s][cam=%s] Weapon detected: %s (conf: %.2f)", user_id, camera_id, label, conf)

                detections.append({
                    "label":       label,
                    "category":    "WEAPON",
                    "confidence":  round(conf, 4),
                    "x":           x1,
                    "y":           y1,
                    "width":       x2 - x1,
                    "height":      y2 - y1,
                    "frameWidth":  w,
                    "frameHeight": h,
                })
                categories_seen.add("WEAPON")
            except Exception:
                logger.error("[user=%s][cam=%s] Failed to process a weapon detection box — skipping it.", user_id, camera_id, exc_info=True)
                continue

    if not detections:
        return None

    snapshot = _frame_to_base64(frame) if frame_count % SNAPSHOT_EVERY == 0 else None
    if snapshot:
        logger.debug("[user=%s][cam=%s] Attached snapshot to payload (frame count %d).", user_id, camera_id, frame_count)

    return {
        "cameraId":   camera_id,
        "userId":     user_id,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "severity":   _severity_for_categories(categories_seen),
        "detections": detections,
        "snapshot":   snapshot,
    }


def _post_payload(payload: dict, token:str):
    cam_id  = payload.get("cameraId")
    user_id = payload.get("userId")
    
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = _http_session.post(DETECTION_URL, json=payload, headers=headers, timeout=3)
        if resp.ok:
            logger.debug("Successfully POSTed payload to Spring Boot for cam=%s, user=%s", cam_id, user_id)
        else:
            logger.warning(
                "Spring Boot returned status %s during payload POST for camera=%s user=%s",
                resp.status_code, cam_id, user_id,
            )
    except requests.RequestException as e:
        logger.error("Failed to POST detection payload to Spring Boot for cam=%s: %s", cam_id, e)
    except Exception:
        logger.error("Unexpected error while POSTing detection payload for cam=%s.", cam_id, exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Global session registry
# ─────────────────────────────────────────────────────────────────────────────

_sessions: dict[str, UserSession] = {}
_sessions_lock = threading.Lock()


def _get_session(user_id: str) -> UserSession | None:
    with _sessions_lock:
        return _sessions.get(user_id)


def _start_session(user_id: str, token: str) -> str:
    logger.debug("Handling start session request for user: %s", user_id)
    with _sessions_lock:
        if user_id in _sessions and _sessions[user_id].is_active:
            # Update token in case it refreshed
            _sessions[user_id].token = token 
            return "already_running"
        session = UserSession(user_id, token)
        _sessions[user_id] = session
    session.start()
    return "started"


def _stop_session(user_id: str) -> str:
    logger.debug("Handling stop session request for user: %s", user_id)
    with _sessions_lock:
        session = _sessions.pop(user_id, None)
    if session is None:
        logger.warning("Attempted to stop session for user %s, but no active session was found.", user_id)
        return "not_found"
    session.stop()
    return "stopped"


# ─────────────────────────────────────────────────────────────────────────────
# HARDENED: watchdog — turns "it just stopped" into a concrete log line
# ─────────────────────────────────────────────────────────────────────────────

def _watchdog_loop():
    logger.info("[watchdog] started, interval=%ss", WATCHDOG_INTERVAL)
    while True:
        try:
            time.sleep(WATCHDOG_INTERVAL)
            with _sessions_lock:
                session_count = len(_sessions)
            logger.info(
                "[watchdog] active_sessions=%d active_threads=%d",
                session_count, threading.active_count(),
            )
            now = time.monotonic()
            with _activity_lock:
                stale = [
                    key for key, ts in _camera_last_activity.items()
                    if now - ts > STREAM_STALE_TIMEOUT * 3
                ]
            for user_id, camera_id in stale:
                logger.warning(
                    "[watchdog] camera '%s' (user=%s) has produced no activity in over %.0fs — check the stream.",
                    camera_id, user_id, STREAM_STALE_TIMEOUT * 3,
                )
        except Exception:
            logger.error("[watchdog] unexpected error in watchdog loop.", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI application
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Service starting up. Pre-loading models...")
    try:
        get_model()  # this one is mandatory — fail startup loudly if it can't load
    except Exception:
        logger.critical("Failed to load the general YOLO model — service cannot start.", exc_info=True)
        raise
    get_weapon_model()   # optional — logs + disables itself if missing/broken
    get_plate_model()    # optional — logs + disables itself if missing/broken
    logger.info("Service is ready.")

    threading.Thread(target=_watchdog_loop, daemon=True, name="watchdog").start()

    yield

    logger.info("Shutting down — stopping all active sessions.")
    with _sessions_lock:
        ids = list(_sessions.keys())
    for uid in ids:
        try:
            _stop_session(uid)
        except Exception:
            logger.error("Error stopping session for user %s during shutdown.", uid, exc_info=True)
    post_executor.shutdown(wait=False, cancel_futures=False)
    logger.info("Shutdown complete.")


app = FastAPI(
    title="VMS YOLO & Face Detection Service",
    description="API-driven multi-user detection orchestrated by Spring Boot.",
    version="2.1.0-hardened",
    lifespan=lifespan,
)

# ── Request / response schemas ────────────────────────────────────────────────

class UserRequest(BaseModel):
    userId: str
    token: str


class StatusResponse(BaseModel):
    userId: str
    status: str
    message: str


class SessionInfo(BaseModel):
    userId:        str
    activeCameras: list[str]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/start", response_model=StatusResponse, summary="Start detection for a user")
def start_detection(req: UserRequest):
    logger.info("Received POST /start request for userId: '%s'", req.userId)
    if not req.userId or not req.userId.strip():
        logger.error("POST /start rejected: userId was blank.")
        raise HTTPException(status_code=400, detail="userId must not be blank.")

    try:
        result = _start_session(req.userId.strip(), req.token)
    except Exception:
        logger.error("Unexpected error starting session for userId '%s'.", req.userId, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start detection session.")

    if result == "already_running":
        return StatusResponse(
            userId=req.userId,
            status="already_running",
            message=f"Detection is already running for user {req.userId}.",
        )

    logger.info("Successfully started detection for userId: '%s'", req.userId)
    return StatusResponse(
        userId=req.userId,
        status="started",
        message=f"Detection started for user {req.userId}.",
    )


@app.post("/stop", response_model=StatusResponse, summary="Stop detection for a user")
def stop_detection(req: UserRequest):
    logger.info("Received POST /stop request for userId: '%s'", req.userId)
    if not req.userId or not req.userId.strip():
        logger.error("POST /stop rejected: userId was blank.")
        raise HTTPException(status_code=400, detail="userId must not be blank.")

    try:
        result = _stop_session(req.userId.strip())
    except Exception:
        logger.error("Unexpected error stopping session for userId '%s'.", req.userId, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to stop detection session.")

    if result == "not_found":
        return StatusResponse(
            userId=req.userId,
            status="not_found",
            message=f"No active detection session found for user {req.userId}.",
        )

    logger.info("Successfully stopped detection for userId: '%s'", req.userId)
    return StatusResponse(
        userId=req.userId,
        status="stopped",
        message=f"Detection stopped for user {req.userId}.",
    )


@app.get("/status", response_model=list[SessionInfo], summary="List all active user sessions")
def get_status():
    logger.debug("Received GET /status request.")
    with _sessions_lock:
        sessions = list(_sessions.values())

    result = []
    for s in sessions:
        if not s.is_active:
            continue
        with s._lock:
            cameras = [cam for cam, t in s._camera_threads.items() if t.is_alive()]
        result.append(SessionInfo(userId=s.user_id, activeCameras=cameras))

    logger.debug("Returning status for %d active sessions.", len(result))
    return result


@app.get("/health", summary="Health check")
def health():
    logger.debug("Received GET /health request.")
    with _sessions_lock:
        session_count = len(_sessions)
    return {
        "status": "ok",
        "activeSessions": session_count,
        "activeThreads": threading.active_count(),
    }
