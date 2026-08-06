#!/usr/bin/env python3
"""
Flask后端服务 - Qwen LoRA + ReAct推理定价
"""
import os
import sys
import io
import wave
import json
import csv
import subprocess
import tempfile
import re
import uuid
import gzip
import base64
import mimetypes
import time
import hashlib
import threading
import queue
import urllib.parse
import urllib.request
import secrets
from difflib import SequenceMatcher
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, send_from_directory, send_file, Response, redirect, stream_with_context, session
from flask_cors import CORS
from werkzeug.security import check_password_hash

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_ROOT = os.path.join(APP_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)


def _load_runtime_env_file(path: str) -> None:
    """Load local KEY=VALUE overrides without requiring python-dotenv.

    This is intentionally tiny and conservative because the file is used for
    workstation-only secrets such as search provider keys. Values already
    present in the process environment win over the local file.
    """
    if not path or not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        return


_load_runtime_env_file(os.path.join(APP_ROOT, "runtime", "local_secrets.env"))


def _env_truthy(name: str, default: str = "") -> bool:
    return (os.environ.get(name, default) or "").strip().lower() in {"1", "true", "yes", "on"}


def _active_pricing_model_version() -> str:
    return (os.environ.get("PRICING_MODEL_VERSION") or "v194").strip()


DEPLOY_LITE_MODE = _env_truthy("DEPLOY_LITE_MODE")
HOSTED_FAST_PRICING = _env_truthy("HOSTED_FAST_PRICING")
ASR_DISABLED = (os.environ.get("ASR_PROVIDER") or "").strip().lower() in {"disabled", "off", "none"}

def _resolve_runtime_dir():
    candidates = []
    meipass_dir = getattr(sys, "_MEIPASS", None)
    if meipass_dir:
        candidates.append(meipass_dir)
    candidates.append(os.path.dirname(os.path.abspath(__file__)))
    for path in candidates:
        if path and os.path.isdir(path):
            return path
    return os.path.dirname(os.path.abspath(__file__))


def _resolve_resource_dir():
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.extend([
            os.environ.get("APP_RESOURCE_DIR"),
            os.path.normpath(os.path.join(exe_dir, "..", "Resources")),
            os.path.normpath(os.path.join(exe_dir, "..", "Frameworks")),
        ])
    candidates.extend([
        getattr(sys, "_MEIPASS", None),
        os.path.dirname(os.path.abspath(__file__)),
    ])
    for path in candidates:
        if path and os.path.isdir(path):
            return path
    return os.path.dirname(os.path.abspath(__file__))


def _find_support_dir(name: str):
    seen = set()
    roots = [
        os.path.dirname(os.path.abspath(__file__)),
        os.getcwd(),
    ]
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        roots.extend([exe_dir, os.path.dirname(exe_dir), os.path.dirname(os.path.dirname(exe_dir))])

    for root in roots:
        current = os.path.abspath(root)
        for _ in range(7):
            candidate = os.path.join(current, name)
            if candidate not in seen:
                seen.add(candidate)
                if os.path.isdir(candidate):
                    return candidate
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    return None


def _find_support_file(name: str):
    seen = set()
    roots = [
        os.path.dirname(os.path.abspath(__file__)),
        os.getcwd(),
    ]
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        roots.extend([exe_dir, os.path.dirname(exe_dir), os.path.dirname(os.path.dirname(exe_dir))])

    for root in roots:
        current = os.path.abspath(root)
        for _ in range(7):
            candidate = os.path.join(current, name)
            if candidate not in seen:
                seen.add(candidate)
                if os.path.isfile(candidate):
                    return candidate
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    return None


RUNTIME_DIR = _resolve_runtime_dir()
PROJECT_DIR = _resolve_resource_dir()
VENDOR_DIR = _find_support_dir(".vendor") or os.path.join(RUNTIME_DIR, ".vendor")

if os.path.isdir(VENDOR_DIR) and VENDOR_DIR not in sys.path:
    sys.path.insert(0, VENDOR_DIR)
if RUNTIME_DIR not in sys.path:
    sys.path.insert(0, RUNTIME_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

try:
    from data_processor import RealCarListing, df_to_listings, DataCleaner
except Exception as exc:
    _DATA_PROCESSOR_IMPORT_ERROR = exc

    class RealCarListing:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise RuntimeError(f"data_processor unavailable: {_DATA_PROCESSOR_IMPORT_ERROR}")

    def df_to_listings(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError(f"data_processor unavailable: {_DATA_PROCESSOR_IMPORT_ERROR}")

    class DataCleaner:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise RuntimeError(f"data_processor unavailable: {_DATA_PROCESSOR_IMPORT_ERROR}")

try:
    from demo_llm_real import RealCarRAGRetriever
except Exception as exc:
    _DEMO_LLM_IMPORT_ERROR = exc

    class RealCarRAGRetriever:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise RuntimeError(f"demo_llm_real unavailable: {_DEMO_LLM_IMPORT_ERROR}")

try:
    from local_ocr_client import (
        LocalOcrError,
        get_local_ocr_config,
        recognize_image_bytes as recognize_image_bytes_local,
    )
except Exception as exc:
    _LOCAL_OCR_IMPORT_ERROR = exc

    class LocalOcrError(RuntimeError):  # type: ignore[no-redef]
        pass

    def get_local_ocr_config():  # type: ignore[no-redef]
        return {"available": False, "error": str(_LOCAL_OCR_IMPORT_ERROR)}

    def recognize_image_bytes_local(*args, **kwargs):  # type: ignore[no-redef]
        raise LocalOcrError(f"local OCR unavailable: {_LOCAL_OCR_IMPORT_ERROR}")

try:
    from tencent_ocr_client import (
        TencentOcrError,
        get_tencent_ocr_config,
        recognize_image_bytes,
    )
except Exception as exc:
    _TENCENT_OCR_IMPORT_ERROR = exc

    class TencentOcrError(RuntimeError):  # type: ignore[no-redef]
        pass

    def get_tencent_ocr_config():  # type: ignore[no-redef]
        return {"available": False, "error": str(_TENCENT_OCR_IMPORT_ERROR)}

    def recognize_image_bytes(*args, **kwargs):  # type: ignore[no-redef]
        raise TencentOcrError(f"tencent OCR unavailable: {_TENCENT_OCR_IMPORT_ERROR}")


app = Flask(__name__)
app.secret_key = os.environ.get("INTERNAL_SESSION_SECRET") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("SPACE_ID")),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)
_CAR_DATA_GZIP_CACHE = {"mtime": None, "payload": None}
_CAR_MODEL_SEARCH_CACHE = {"cache_key": None, "records": None, "brands": None}

_DEFAULT_INTERNAL_ACCOUNTS = {
    "dcar_internal": {
        "password_hash": "pbkdf2:sha256:600000$dglVDnGFiSmITo2u$aaf5382c4213976650794da12b2ec367a742d27f9aba457ea09cc651fc251b5c",
        "role": "internal_tester",
        "label": "组内内测",
        "can_view_feedback": False,
    },
    "dcar_business": {
        "password_hash": "pbkdf2:sha256:600000$DHCEASyu7keLMqT2$d8a5ad61d7ccd7e6ccc1f2433ecd90879f819e4ed8097a6bb9f2b21d2479bdea",
        "role": "business_expert",
        "label": "业务专家",
        "can_view_feedback": False,
    },
    "dcar_dealer_ops": {
        "password_hash": "pbkdf2:sha256:600000$lP062EmGDSyVTbj2$54f341d1b2815a839d5f56370c32207f5d128e37cf2d3d90df9725fd6cbb2400",
        "role": "dealer_operations",
        "label": "一线商家运营",
        "can_view_feedback": False,
    },
    "dcar_product": {
        "password_hash": "pbkdf2:sha256:600000$LMX52m3qVZmrhDRq$35009f2bb59b552a9fb64ca100eebe7be79a4c0528d349461dd77d3ecacd837d",
        "role": "product_reviewer",
        "label": "产品",
        "can_view_feedback": False,
    },
    "dcar_risk_review": {
        "password_hash": "pbkdf2:sha256:600000$kdMWwW3jv8fzG9Jl$194acad8bb323e9faa9917c97dd2a4ee97cb009be59aaba72fcb99f1076d1930",
        "role": "management_risk_reviewer",
        "label": "管理及风险评审",
        "can_view_feedback": False,
    },
    "dcar_owner": {
        "password_hash": "pbkdf2:sha256:600000$gzGwUyuIv8hMfEyw$26ef43fbd03754ca3eae99bb05cefa6067d3adcf54748682f115a36e2e607d05",
        "role": "owner_admin",
        "label": "管理员",
        "can_view_feedback": True,
    },
}


def _load_internal_accounts():
    """Load role-aware gray-test accounts without exposing passwords to clients."""
    accounts = {username: dict(config) for username, config in _DEFAULT_INTERNAL_ACCOUNTS.items()}
    raw = (os.environ.get("INTERNAL_AUTH_ACCOUNTS_JSON") or "").strip()
    if raw:
        try:
            configured = json.loads(raw)
            if isinstance(configured, dict):
                for username, config in configured.items():
                    if isinstance(config, dict) and config.get("password_hash"):
                        accounts[str(username).strip()] = {
                            "password_hash": str(config.get("password_hash")),
                            "role": str(config.get("role") or "internal_tester"),
                            "label": str(config.get("label") or username),
                            "can_view_feedback": bool(config.get("can_view_feedback", False)),
                        }
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    # Preserve compatibility with the original single-account deployment.
    legacy_username = (os.environ.get("INTERNAL_AUTH_USERNAME") or "").strip()
    legacy_hash = (os.environ.get("INTERNAL_AUTH_PASSWORD_HASH") or "").strip()
    if legacy_username and legacy_hash:
        existing = accounts.get(legacy_username) or {}
        accounts[legacy_username] = {
            "password_hash": legacy_hash,
            "role": str(existing.get("role") or "internal_tester"),
            "label": str(existing.get("label") or "组内内测"),
            "can_view_feedback": bool(existing.get("can_view_feedback", False)),
        }
    return accounts


_INTERNAL_AUTH_ACCOUNTS = _load_internal_accounts()


def _internal_auth_enabled() -> bool:
    explicit = os.environ.get("INTERNAL_AUTH_ENABLED")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    # This application is currently an internal gray-test product.  Keep the
    # login boundary enabled locally as well as on hosted deployments so the
    # logout action cannot immediately fall back into an unprotected app.
    # Developers can still opt out explicitly with INTERNAL_AUTH_ENABLED=0.
    return True


def _current_internal_username() -> str:
    return str(session.get("internal_username") or "local_developer")


def _current_internal_account():
    if not _internal_auth_enabled():
        return {
            "username": _current_internal_username(),
            "role": "owner_admin",
            "label": "本地开发者",
            "can_view_feedback": True,
        }
    return {
        "username": _current_internal_username(),
        "role": str(session.get("internal_role") or "internal_tester"),
        "label": str(session.get("internal_account_label") or "组内内测"),
        "can_view_feedback": session.get("internal_can_view_feedback") is True,
    }


def _is_feedback_admin_request() -> bool:
    path = request.path.rstrip("/") or "/"
    if path in {"/agent/feedback", "/feedback-admin"}:
        return True
    admin_api_prefixes = (
        "/api/internal-feedback/",
        "/api/feedback/",
        "/api/reflections/",
        "/api/eval-cases/",
    )
    return any(request.path.startswith(prefix) for prefix in admin_api_prefixes)


@app.before_request
def enforce_internal_api_session():
    """Protect every business API on hosted gray-test deployments."""
    if not _internal_auth_enabled():
        return None
    if request.path.startswith("/api/"):
        public_paths = {"/api/auth/status", "/api/auth/login", "/api/version"}
        if request.path not in public_paths and session.get("internal_authenticated") is not True:
            return jsonify({"success": False, "error": "authentication_required"}), 401
    if _is_feedback_admin_request() and session.get("internal_authenticated") is True:
        if session.get("internal_can_view_feedback") is not True:
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "feedback_admin_required"}), 403
            return redirect("/agent?feedback_forbidden=1", code=302)
    return None


@app.after_request
def add_no_cache_headers(response):
    """首页不缓存，较大的静态数据文件允许缓存，避免每次刷新都重新下载车型库。"""
    if request.path in {"/car_data_slim.js", "/pricing_assistant_mock.js"}:
        response.headers["Cache-Control"] = "public, max-age=3600"
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
    elif request.path == "/" or request.path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response
CORS(app)


@app.route('/api/auth/status', methods=['GET'])
def internal_auth_status():
    enabled = _internal_auth_enabled()
    authenticated = (not enabled) or session.get("internal_authenticated") is True
    account = _current_internal_account() if authenticated else {}
    return jsonify({
        "success": True,
        "data": {
            "enabled": enabled,
            "authenticated": authenticated,
            "username": account.get("username", ""),
            "role": account.get("role", ""),
            "label": account.get("label", ""),
            "can_view_feedback": bool(account.get("can_view_feedback", False)),
        },
    })


@app.route('/api/auth/login', methods=['POST'])
def internal_auth_login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    account = _INTERNAL_AUTH_ACCOUNTS.get(username)
    if not account or not check_password_hash(str(account.get("password_hash") or ""), password):
        time.sleep(0.25)
        return jsonify({"success": False, "error": "账号或密码错误"}), 401
    session.clear()
    session.permanent = True
    session["internal_authenticated"] = True
    session["internal_username"] = username
    session["internal_role"] = str(account.get("role") or "internal_tester")
    session["internal_account_label"] = str(account.get("label") or username)
    session["internal_can_view_feedback"] = bool(account.get("can_view_feedback", False))
    session["internal_login_at"] = datetime.now(timezone.utc).isoformat()
    return jsonify({
        "success": True,
        "data": {
            "authenticated": True,
            "username": username,
            "role": session["internal_role"],
            "label": session["internal_account_label"],
            "can_view_feedback": session["internal_can_view_feedback"],
        },
    })


@app.route('/api/auth/logout', methods=['POST'])
def internal_auth_logout():
    session.clear()
    return jsonify({"success": True, "data": {"authenticated": False}})

retriever = None
is_initialized = False
_asr_pipeline = None
_asr_model_name = None
_asr_provider = None
price_car_react = None
init_qwen_model = None
_call_llm = None
use_finetuned_model = None
use_base_model = None
REASONING_MODEL_AVAILABLE = False


def _load_react_pricing():
    """Lazy-load legacy ReAct/Qwen code only for old chat/pricing paths.

    The v192.10 production pricing path must not import react_pricing before
    the historical comparable engine, because that dependency combination can
    trigger a native library segmentation fault in the local Python runtime.
    """
    global price_car_react, init_qwen_model, _call_llm
    global use_finetuned_model, use_base_model, REASONING_MODEL_AVAILABLE
    if price_car_react is not None:
        rp = _load_react_pricing()
        return rp
    import react_pricing as rp

    price_car_react = rp.price_car_react
    init_qwen_model = rp.init_qwen_model
    _call_llm = rp._call_llm
    use_finetuned_model = rp.use_finetuned_model
    use_base_model = rp.use_base_model
    REASONING_MODEL_AVAILABLE = rp.REASONING_MODEL_AVAILABLE
    return rp


class _SenseVoiceHelperProxy:
    def __init__(self, model_name: str, helper_script: str):
        self.model_name = model_name
        self.helper_script = helper_script
        self.proc = None

    def _python_candidates(self):
        candidates = [
            os.environ.get("SENSEVOICE_HELPER_PYTHON"),
            "/usr/bin/python3",
            sys.executable if sys.executable.endswith("python3") or sys.executable.endswith("python") else None,
        ]
        return [item for item in candidates if item and os.path.exists(item)]

    def _read_json_line(self):
        if self.proc is None or self.proc.stdout is None:
            raise RuntimeError("SenseVoice helper 未启动")

        while True:
            line = self.proc.stdout.readline()
            if not line:
                stderr_text = ""
                if self.proc.stderr is not None:
                    stderr_text = self.proc.stderr.read().strip()
                raise RuntimeError(f"SenseVoice helper 已退出。{stderr_text}".strip())
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    def _ensure_process(self):
        if self.proc is not None and self.proc.poll() is None:
            return

        python_cmd = next(iter(self._python_candidates()), None)
        if not python_cmd:
            raise RuntimeError("未找到可用的 Python 解释器来启动 SenseVoice helper。")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["SENSEVOICE_MODEL_PATH"] = self.model_name
        self.proc = subprocess.Popen(
            [python_cmd, self.helper_script, "--server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=_project_root(),
            env=env,
        )

        ready_payload = self._read_json_line()
        if not ready_payload.get("ready"):
            raise RuntimeError(ready_payload.get("error") or "SenseVoice helper 启动失败。")

    def generate(self, input: str, cache=None, language: str = "auto", use_itn: bool = True):
        self._ensure_process()
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("SenseVoice helper 不可用。")

        payload = {
            "input": input,
            "language": language,
            "use_itn": use_itn,
        }
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        response = self._read_json_line()
        if not response.get("success"):
            raise RuntimeError(response.get("error") or "SenseVoice helper 识别失败。")
        return response.get("result")


def init_backend():
    """初始化后端：加载数据、初始化模型、构建RAG"""
    global retriever, is_initialized
    
    if is_initialized:
        return
    
    print("=" * 80)
    print("  初始化定价后端...")
    print("=" * 80)
    
    data_path = os.path.join(PROJECT_DIR, "data", "最近六月定价最终价格单.xlsx")
    csv_data_path = os.path.join(PROJECT_DIR, "data", "最近六月定价最终价格单.csv")
    
    print("\n✅ 使用ReAct推理机制进行车况评分预测")
    
    # 加载参考车源数据
    if os.path.exists(data_path):
        df = pd.read_excel(data_path)
    elif os.path.exists(csv_data_path):
        df = pd.read_csv(csv_data_path)
    else:
        raise FileNotFoundError(f"未找到定价数据文件：{data_path} 或 {csv_data_path}")
    df['车源创建时间'] = pd.to_datetime(df['车源创建时间'])
    
    min_time = df['车源创建时间'].min()
    max_time = df['车源创建时间'].max()
    total_days = (max_time - min_time).days
    mid_time = min_time + timedelta(days=total_days / 2)
    
    df_train = df[df['车源创建时间'] <= mid_time].copy()
    
    df_train['purchase_price'] = df_train['采购价格'] / 10000
    df_train['sale_price'] = df_train['销售价格'] / 10000
    df_train['c2b_price'] = df_train['purchase_price']
    df_train['b2c_price'] = df_train['sale_price']
    
    cleaner = DataCleaner(verbose=False)
    df_train = cleaner.normalize_columns(df_train)
    df_train = cleaner.drop_invalid_prices(df_train)
    
    if 'inspection_score' in df_train.columns:
        df_train = df_train[df_train['inspection_score'] > 0]
    
    df_train = df_train[df_train['b2c_price'] >= 1]
    
    train_listings = df_to_listings(df_train)
    retriever = RealCarRAGRetriever(train_listings, min_months=0, max_months=0)
    
    print(f"[RAG] 加载 {len(train_listings)} 条参考记录")
    
    if DEPLOY_LITE_MODE or HOSTED_FAST_PRICING:
        print("\n[部署] 跳过本地 Qwen 大模型加载，使用数据检索/规则快速估价。")
    else:
        print("\n初始化Qwen模型...")
        _load_react_pricing()
        init_qwen_model()
    
    is_initialized = True
    print("\n✅ 后端初始化完成！")
    print("=" * 80)


def _project_root():
    return PROJECT_DIR


def _load_pcm_wav(audio_bytes: bytes):
    """读取前端上传的 PCM WAV 音频，返回 float32 单声道数组。"""
    import numpy as np

    with wave.open(io.BytesIO(audio_bytes), 'rb') as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        frames = wav_file.readframes(frame_count)

    if sample_width != 2:
        raise ValueError(f"仅支持16-bit PCM WAV，当前位深: {sample_width * 8}bit")

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    return audio, sample_rate


def _extract_text_from_asr_result(result):
    """兼容 SenseVoice / Whisper 不同返回结构，尽量抽取文本。"""
    def _clean_text(text: str) -> str:
        text = re.sub(r"<\|[^|]+?\|>", "", text)
        return re.sub(r"\s+", " ", text).strip()

    if result is None:
        return ""

    if isinstance(result, str):
        return _clean_text(result)

    if isinstance(result, dict):
        for key in ('text', 'result', 'sentence_info'):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return _clean_text(value)
            if isinstance(value, list):
                texts = []
                for item in value:
                    text = _extract_text_from_asr_result(item)
                    if text:
                        texts.append(text)
                if texts:
                    return " ".join(texts).strip()

        # 兜底：把 dict 里的字符串字段拼起来
        texts = [str(v).strip() for v in result.values() if isinstance(v, str) and str(v).strip()]
        return " ".join(texts).strip()

    if isinstance(result, list):
        texts = []
        for item in result:
            text = _extract_text_from_asr_result(item)
            if text:
                texts.append(text)
        return " ".join(texts).strip()

    return _clean_text(str(result))


def _load_sensevoice_model():
    """优先加载 SenseVoice。"""
    local_model_dir = os.path.join(PROJECT_DIR, ".asr_models", "SenseVoiceSmall")
    model_name = (
        os.environ.get('SENSEVOICE_MODEL_PATH')
        or (local_model_dir if os.path.isdir(local_model_dir) else None)
        or os.environ.get('ASR_MODEL_PATH')
        or os.environ.get('SENSEVOICE_MODEL_ID')
        or 'iic/SenseVoiceSmall'
    )

    try:
        import torch
        from funasr import AutoModel
        import funasr.models.sense_voice.model  # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            "SenseVoice 依赖未安装。请在打包/运行环境中提供 funasr（以及它依赖的 modelscope）。"
        ) from exc

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    try:
        model = AutoModel(
            model=model_name,
            trust_remote_code=False,
            device=device,
            disable_update=True,
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        helper_script = (
            os.environ.get("SENSEVOICE_HELPER_PATH")
            or _find_support_file("sensevoice_asr_helper.py")
        )
        if helper_script:
            print(f"[ASR] 直接加载 SenseVoice 失败，改用 helper: {helper_script}")
            return _SenseVoiceHelperProxy(model_name, helper_script), model_name, 'sensevoice'
        raise RuntimeError(
            f"SenseVoice 模型加载失败：{model_name}。"
            "如果你希望离线使用，请把本地 SenseVoice 模型目录写入 SENSEVOICE_MODEL_PATH。"
        ) from exc

    print(f"[ASR] 已加载 SenseVoice 模型: {model_name}")
    return model, model_name, 'sensevoice'


def _load_whisper_model():
    """Whisper 兜底。"""
    model_name = (
        os.environ.get('WHISPER_MODEL_PATH')
        or os.environ.get('ASR_MODEL_PATH')
        or os.environ.get('WHISPER_MODEL_ID')
        or 'openai/whisper-small'
    )

    try:
        import torch
        from transformers import pipeline
    except Exception as exc:
        raise RuntimeError(
            "Whisper 依赖未就绪，无法加载 transformers/torch。"
        ) from exc

    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    device = 0 if torch.cuda.is_available() else -1

    try:
        model = pipeline(
            task="automatic-speech-recognition",
            model=model_name,
            torch_dtype=torch_dtype,
            device=device,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Whisper 模型加载失败：{model_name}。"
            "如果你希望离线使用，请把本地 Whisper 模型目录写入 WHISPER_MODEL_PATH 或 ASR_MODEL_PATH。"
        ) from exc

    print(f"[ASR] 已加载 Whisper 模型: {model_name}")
    return model, model_name, 'whisper'


def _get_asr_backend():
    """懒加载 ASR 后端：默认仅启用 SenseVoice，必要时才允许回退 Whisper。"""
    global _asr_pipeline, _asr_model_name, _asr_provider

    if _asr_pipeline is not None:
        return _asr_pipeline, _asr_model_name, _asr_provider

    preferred_provider = (os.environ.get('ASR_PROVIDER') or 'sensevoice').strip().lower()
    allow_fallback = (os.environ.get('ASR_ALLOW_FALLBACK') or '').strip().lower() in {'1', 'true', 'yes'}
    if preferred_provider == 'whisper':
        loaders = [_load_whisper_model]
        if allow_fallback:
            loaders.append(_load_sensevoice_model)
    else:
        loaders = [_load_sensevoice_model]
        if allow_fallback:
            loaders.append(_load_whisper_model)

    last_error = None
    for loader in loaders:
        try:
            _asr_pipeline, _asr_model_name, _asr_provider = loader()
            return _asr_pipeline, _asr_model_name, _asr_provider
        except Exception as exc:
            last_error = exc
            print(f"[ASR] {loader.__name__} 加载失败: {exc}")

    raise RuntimeError(
        "没有可用的 ASR 后端。"
        "当前配置要求优先使用 SenseVoice。"
        "如果你确实需要回退 Whisper，请显式设置 ASR_ALLOW_FALLBACK=1。"
    ) from last_error


@app.route('/', methods=['GET'])
def serve_index():
    """桌面 App 首页：通过 localhost 提供前端，保证麦克风能力可用。"""
    if _env_truthy("DEFAULT_TO_AGENT_UI"):
        return redirect("/agent", code=302)
    return send_from_directory(_project_root(), "AI定价助手_优化版_Qwen_ReAct.html")


def _agent_ui_dist_dir():
    return os.path.join(_project_root(), "frontend", "agent-ui", "dist")


@app.route('/agent', methods=['GET'])
@app.route('/agent/', methods=['GET'])
@app.route('/agent/selection-lab', methods=['GET'])
@app.route('/agent/selection-lab/', methods=['GET'])
@app.route('/agent/feedback', methods=['GET'])
@app.route('/agent/feedback/', methods=['GET'])
def serve_agent_ui():
    """Enterprise Agent modular UI.  The legacy single HTML remains at / for rollback."""
    dist_dir = _agent_ui_dist_dir()
    index_path = os.path.join(dist_dir, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(dist_dir, "index.html")
    return jsonify(
        {
            "success": False,
            "error": "Agent UI has not been built. Run: cd frontend/agent-ui && npm install && npm run build",
        }
    ), 503


@app.route('/agent/assets/<path:filename>', methods=['GET'])
def serve_agent_ui_assets(filename):
    """Static assets generated by Vite for the modular Agent UI."""
    dist_dir = _agent_ui_dist_dir()
    assets_dir = os.path.join(dist_dir, "assets")
    return send_from_directory(assets_dir, filename)


@app.route('/car_data_slim.js', methods=['GET'])
def serve_car_data():
    js_path = os.path.join(_project_root(), "car_data_slim.js")
    accepts_gzip = "gzip" in (request.headers.get("Accept-Encoding") or "").lower()
    if accepts_gzip and os.path.exists(js_path):
        mtime = os.path.getmtime(js_path)
        if _CAR_DATA_GZIP_CACHE["mtime"] != mtime or not _CAR_DATA_GZIP_CACHE["payload"]:
            with open(js_path, "rb") as f:
                _CAR_DATA_GZIP_CACHE["payload"] = gzip.compress(f.read(), compresslevel=6)
            _CAR_DATA_GZIP_CACHE["mtime"] = mtime
        payload = _CAR_DATA_GZIP_CACHE["payload"]
        if payload:
            response = Response(payload, mimetype="application/javascript")
            response.headers["Content-Encoding"] = "gzip"
            response.headers["Vary"] = "Accept-Encoding"
            response.headers["Content-Length"] = str(len(payload))
            return response
    if os.path.exists(js_path):
        return send_from_directory(_project_root(), "car_data_slim.js")
    return "", 404


def _normalize_car_search_text(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"[，。！？、；：:,.()\[\]【】（）\s]+", "", text)
    return text


def _extract_config_codes(value):
    text = str(value or "").lower()
    codes = set()
    for pattern in (
        r"(?<!\d)(?:[1-9]\d{2})(?:li|i|e|d)?(?!\d)",
        r"(?<![a-z0-9])(?:c|e|s|glc|gle|gls|cls)\s*\d{2,3}(?![a-z0-9])",
        r"(?<![a-z0-9])a\d(?:l)?(?![a-z0-9])",
    ):
        for match in re.finditer(pattern, text, flags=re.I):
            codes.add(re.sub(r"\s+", "", match.group(0).lower()))
    return codes


def _extract_search_year(value):
    match = re.search(r"((?:19|20)\d{2}|[12]\d)\s*(?:款|年)?", str(value or ""))
    if not match:
        return ""
    year = match.group(1)
    return f"20{year}" if len(year) == 2 else year


def _strip_search_year(value):
    text = str(value or "")
    # Only remove a real year clue.  The previous global pattern also removed
    # the "25" inside "525Li", which made full queries such as
    # "2025款 宝马5系 525Li M运动套装" fail while the shorter "525" worked.
    text = re.sub(r"^\s*((?:19|20)\d{2}|[12]\d)\s*(?:款|年)?\s*", " ", text, count=1)
    text = re.sub(r"((?:19|20)\d{2}|[12]\d)\s*(?:款|年)\s*", " ", text, count=1)
    return text


def _car_data_source_path():
    csv_path = os.path.join(PROJECT_DIR, "data", "最近六月定价最终价格单.csv")
    xlsx_path = os.path.join(PROJECT_DIR, "data", "最近六月定价最终价格单.xlsx")
    if os.path.exists(csv_path):
        return csv_path
    if os.path.exists(xlsx_path):
        return xlsx_path
    return ""


def _vehicle_catalog_source_path():
    """v7 车型库补充源：覆盖 2024 款宝马3系等旧 Excel 不完整的车型。"""
    catalog_path = os.path.join(PROJECT_DIR, "results", "vehicle_catalog", "vehicle_model.csv")
    return catalog_path if os.path.exists(catalog_path) else ""


def _vehicle_catalog_fast_index_path():
    """Prebuilt compact search index used by production cold starts."""
    return os.path.join(PROJECT_DIR, "data", "runtime", "vehicle_catalog_search_index.json.gz")


def _vehicle_catalog_fast_index_archive_path():
    """Text-safe copy for hosts whose Git remote rejects binary assets."""
    return f"{_vehicle_catalog_fast_index_path()}.b64"


def _autohome_spec_catalog_path():
    """Full current Autohome spec catalog; used server-side only."""
    path = os.path.join(PROJECT_DIR, "data", "runtime", "autohome_vehicle_spec_catalog.json.gz")
    return path if os.path.exists(path) else ""


def _static_kb_catalog_path():
    path = os.path.join(PROJECT_DIR, "data", "knowledge", "current_vehicle_model_knowledge_base.csv")
    return path if os.path.exists(path) else ""


def _safe_model_search_text(value):
    text = "" if value is None or pd.isna(value) else str(value).strip()
    return "" if text.lower() in {"nan", "none", "null", "missing"} else text


def _append_car_search_record(records, seen, row):
    brand = _safe_model_search_text(row.get("brand") or row.get("品牌"))
    series = _safe_model_search_text(row.get("series") or row.get("车系"))
    model_year = _safe_model_search_text(row.get("model_year") or row.get("年款"))
    model = _safe_model_search_text(row.get("model_name") or row.get("车型"))
    model_id = _safe_model_search_text(row.get("model_id") or row.get("车型ID"))

    if re.fullmatch(r"\d+\.0", model_year):
        model_year = model_year[:-2]
    if re.fullmatch(r"\d+\.0", model_id):
        model_id = model_id[:-2]
    if not brand or not series or not model_year:
        return

    brand_series = series if series.startswith(brand) else f"{brand}{series}"
    title = f"{model_year}款 {brand_series} {model}".strip()
    # 旧 Excel 里偶尔存在同一车型ID落在错误年款的脏行；按“年款+车型ID”
    # 去重，避免阻止 v7 标准车型库里的真实 2024/2025 款记录进入搜索。
    dedupe_key = f"{model_year}:{model_id}" if model_id else title
    if dedupe_key in seen:
        return
    seen.add(dedupe_key)

    mileage = row.get("median_mileage_wan")
    if mileage is None or pd.isna(mileage):
        mileage = row.get("里程")
    try:
        mileage_text = f"{float(mileage):.1f}" if mileage is not None and pd.notna(mileage) else "5.0"
    except (TypeError, ValueError):
        mileage_text = "5.0"

    transfer = row.get("过户次数")
    transfer_text = str(transfer if transfer is not None and pd.notna(transfer) else "1")
    if transfer_text.endswith(".0"):
        transfer_text = transfer_text[:-2]

    record_id = model_id or _normalize_car_search_text(title)
    records.append({
        "id": record_id,
        "title": title,
        "brand": brand,
        "series": series,
        "model_year": model_year,
        "model": model,
        # Standard model candidates must not invent first-license time.
        # Registration date is one of the six pricing elements and must come
        # from user input or the month picker; otherwise the form can pollute
        # the model name with values like “,-06上牌”.
        "regDate": "",
        "mileage": mileage_text,
        "transfer": transfer_text,
        "color": _safe_model_search_text(row.get("车身颜色")) or "白色",
        "city": "北京",
    })


def _append_kb_search_record(records, seen, row):
    brand = _safe_model_search_text(row.get("canonical_brand") or row.get("brand_name"))
    series = _safe_model_search_text(row.get("canonical_series") or row.get("series_name"))
    model_year = _safe_model_search_text(row.get("model_year") or row.get("year"))
    model = _safe_model_search_text(row.get("trim_name") or row.get("canonical_model") or row.get("model_name"))
    record_id = _safe_model_search_text(row.get("knowledge_record_id"))
    if re.fullmatch(r"\d+\.0", model_year):
        model_year = model_year[:-2]
    if brand.endswith("汽车") and len(brand) > 2:
        brand = brand[:-2]
    if not brand or not series or not model_year or not model:
        return
    mapped = {
        "brand": brand,
        "series": series,
        "model_year": model_year,
        "model_name": model,
        "model_id": record_id or "",
    }
    _append_car_search_record(records, seen, mapped)


def _load_car_model_search_records():
    """后端缓存车型库搜索索引，避免前端每次打开表格加载完整 JS 车型库。"""
    source_path = _car_data_source_path()
    catalog_path = _vehicle_catalog_source_path()
    fast_index_path = _vehicle_catalog_fast_index_path()
    fast_index_archive_path = _vehicle_catalog_fast_index_archive_path()
    fast_index_source_path = fast_index_path if os.path.exists(fast_index_path) else fast_index_archive_path
    autohome_spec_path = _autohome_spec_catalog_path()
    static_kb_path = _static_kb_catalog_path()
    if not source_path and not catalog_path and not autohome_spec_path and not static_kb_path and not os.path.exists(fast_index_source_path):
        return [], []

    cache_key = (
        fast_index_source_path,
        os.path.getmtime(fast_index_source_path) if os.path.exists(fast_index_source_path) else None,
        source_path,
        os.path.getmtime(source_path) if source_path else None,
        catalog_path,
        os.path.getmtime(catalog_path) if catalog_path else None,
        autohome_spec_path,
        os.path.getmtime(autohome_spec_path) if autohome_spec_path else None,
        static_kb_path,
        os.path.getmtime(static_kb_path) if static_kb_path else None,
    )
    if (
        _CAR_MODEL_SEARCH_CACHE.get("records") is not None
        and _CAR_MODEL_SEARCH_CACHE.get("cache_key") == cache_key
    ):
        return _CAR_MODEL_SEARCH_CACHE["records"], _CAR_MODEL_SEARCH_CACHE["brands"]

    records = []
    seen = set()

    if os.path.exists(fast_index_source_path):
        try:
            if fast_index_source_path.endswith(".b64"):
                packed = base64.b64decode(Path(fast_index_source_path).read_text(encoding="ascii"))
                fast_records = json.loads(gzip.decompress(packed).decode("utf-8"))
            else:
                with gzip.open(fast_index_source_path, "rt", encoding="utf-8") as handle:
                    fast_records = json.load(handle)
            for item in fast_records if isinstance(fast_records, list) else []:
                if not isinstance(item, dict):
                    continue
                key = f"{item.get('model_year')}:{item.get('id') or _normalize_car_search_text(item.get('title'))}"
                if key in seen:
                    continue
                seen.add(key)
                item["regDate"] = ""
                records.append(item)
            print(f"[车型库] 已从压缩索引读取 {len(records)} 个标准车型搜索项")
            if records:
                brands = sorted({item["brand"] for item in records if item.get("brand")}, key=len, reverse=True)
                _CAR_MODEL_SEARCH_CACHE.update({"cache_key": cache_key, "records": records, "brands": brands})
                print(f"[车型库] 已缓存 {len(records)} 个标准车型搜索项，来源: {os.path.basename(fast_index_source_path)}")
                return records, brands
        except (OSError, ValueError, TypeError) as exc:
            print(f"[车型库] 压缩索引读取失败，回退 CSV: {exc}")

    if source_path:
        if source_path.endswith(".csv"):
            df = pd.read_csv(source_path, usecols=lambda c: c in {"品牌", "车系", "年款", "车型", "车型ID", "车身颜色", "过户次数", "里程"})
        else:
            df = pd.read_excel(source_path, usecols=lambda c: c in {"品牌", "车系", "年款", "车型", "车型ID", "车身颜色", "过户次数", "里程"})
        for _, row in df.iterrows():
            _append_car_search_record(records, seen, row)

    if catalog_path:
        catalog_cols = {"brand", "series", "model_year", "model_name", "model_id", "median_mileage_wan"}
        catalog_df = pd.read_csv(catalog_path, usecols=lambda c: c in catalog_cols)
        for _, row in catalog_df.iterrows():
            _append_car_search_record(records, seen, row)

    if autohome_spec_path:
        try:
            with gzip.open(autohome_spec_path, "rt", encoding="utf-8") as handle:
                spec_rows = json.load(handle)
            for row in spec_rows if isinstance(spec_rows, list) else []:
                _append_car_search_record(records, seen, row)
        except (OSError, ValueError, TypeError) as exc:
            print(f"[车型库] 汽车之家车型目录读取失败: {exc}")

    if static_kb_path:
        try:
            kb_cols = {"knowledge_record_id", "canonical_brand", "canonical_series", "canonical_model", "model_year", "trim_name"}
            kb_df = pd.read_csv(static_kb_path, usecols=lambda c: c in kb_cols)
            for _, row in kb_df.iterrows():
                _append_kb_search_record(records, seen, row)
        except Exception as exc:
            print(f"[车型库] 静态车型知识库读取失败: {exc}")

    brands = sorted({item["brand"] for item in records if item.get("brand")}, key=len, reverse=True)
    _CAR_MODEL_SEARCH_CACHE.update({"cache_key": cache_key, "records": records, "brands": brands})
    source_names = [os.path.basename(p) for p in (fast_index_path, source_path, catalog_path, autohome_spec_path, static_kb_path) if p and os.path.exists(p)]
    print(f"[车型库] 已缓存 {len(records)} 个标准车型搜索项，来源: {', '.join(source_names)}")
    return records, brands


def _extract_search_brand(query, brands):
    normalized_query = _normalize_car_search_text(query)
    for brand in brands:
        if brand and _normalize_car_search_text(brand) in normalized_query:
            return brand
    return ""


@app.route('/api/car-models/search', methods=['GET'])
def search_car_models():
    """轻量车型搜索接口：前端只拿候选结果，不再加载整份车型库导致页面卡死。"""
    query = (request.args.get("q") or "").strip()
    try:
        limit = max(1, min(int(request.args.get("limit") or 50), 100))
    except ValueError:
        limit = 50

    records, brands = _load_car_model_search_records()
    normalized_query = _normalize_car_search_text(query)
    explicit_year = _extract_search_year(query)
    brand = _extract_search_brand(query, brands)
    series_query = _normalize_car_search_text(_strip_search_year(query).replace(brand, ""))
    query_config_codes = _extract_config_codes(query)

    scored = []
    for item in records:
        if brand and item.get("brand") != brand:
            continue
        if explicit_year and str(item.get("model_year")) != explicit_year:
            continue

        title_key = _normalize_car_search_text(item.get("title"))
        brand_key = _normalize_car_search_text(item.get("brand"))
        series_key = _normalize_car_search_text(item.get("series"))
        brand_series_key = _normalize_car_search_text(f"{item.get('brand', '')}{item.get('series', '')}")
        model_key = _normalize_car_search_text(item.get("model"))
        haystack = f"{title_key} {brand_key} {series_key} {brand_series_key} {model_key}"
        item_config_codes = _extract_config_codes(f"{item.get('title', '')} {item.get('model', '')}")
        series_matched = bool(
            series_query
            and (
                series_query in series_key
                or series_query in brand_series_key
                or series_query in title_key
                or series_query in model_key
            )
        )
        fuzzy_ratio = 0.0
        if series_query and not series_matched:
            fuzzy_ratio = max(
                SequenceMatcher(None, series_query, f"{series_key}{model_key}").ratio(),
                SequenceMatcher(None, series_query, title_key).ratio(),
            )
            if fuzzy_ratio >= 0.58:
                series_matched = True
        # If the user typed a concrete series clue such as "宝马3系", do not
        # let brand/year-only matches return 宝马1系/5系/X1 as standard models.
        if series_query and len(series_query) >= 2 and not series_matched:
            continue
        if query_config_codes and (not item_config_codes or query_config_codes.isdisjoint(item_config_codes)):
            continue

        score = 0
        if not normalized_query:
            score = 1
        if brand:
            score += 100
        if explicit_year:
            score += 80
        if normalized_query and title_key.startswith(normalized_query):
            score += 90 + len(normalized_query)
        if normalized_query and normalized_query in title_key:
            score += 70 + len(normalized_query)
        if normalized_query and normalized_query in brand_series_key:
            score += 60
        if series_matched:
            score += 55 + len(series_query)
            if fuzzy_ratio:
                score += int(45 * fuzzy_ratio)
        if normalized_query and normalized_query in haystack:
            score += 20
        query_core = series_query or normalized_query
        raw_model_text = str(item.get("model") or item.get("title") or "")
        if query_core:
            # Configuration clues such as “C63” must prefer AMG C 63 over
            # GLC 63, even when the latter is newer.  Use the raw text before
            # compaction so model-family letters remain meaningful.
            compact_core = _normalize_car_search_text(query_core)
            if compact_core == "c63":
                if re.search(r"(^|[^A-Za-z0-9])C\s*63([^A-Za-z0-9]|$)", raw_model_text, flags=re.I):
                    score += 180
                if re.search(r"GLC\s*63|GLE\s*63|GLS\s*63", raw_model_text, flags=re.I):
                    score -= 80
            if compact_core and compact_core == model_key:
                score += 120
            elif compact_core and model_key.startswith(compact_core):
                score += 90
        if query_config_codes and item_config_codes and not query_config_codes.isdisjoint(item_config_codes):
            score += 140
        if brand and not series_query:
            try:
                score += int(item.get("model_year") or 0) / 10000
            except ValueError:
                pass

        if score > 0:
            scored.append((score, item))

    # A user can remember the registration year as the model year (for
    # example "20年 Model Y").  Do not pretend a non-existent 2020款 exists,
    # but also do not make a popular series look missing.  When the exact
    # year has no trim, return the nearest real model years for that series.
    year_fallback = False
    fallback_years = []
    if explicit_year and series_query and not scored:
        target_year = int(explicit_year)
        fallback_candidates = []
        for item in records:
            if brand and item.get("brand") != brand:
                continue
            series_key = _normalize_car_search_text(item.get("series"))
            brand_series_key = _normalize_car_search_text(f"{item.get('brand', '')}{item.get('series', '')}")
            title_key = _normalize_car_search_text(item.get("title"))
            model_key = _normalize_car_search_text(item.get("model"))
            if not any(series_query in key for key in (series_key, brand_series_key, title_key, model_key)):
                continue
            item_config_codes = _extract_config_codes(f"{item.get('title', '')} {item.get('model', '')}")
            if query_config_codes and (not item_config_codes or query_config_codes.isdisjoint(item_config_codes)):
                continue
            try:
                item_year = int(item.get("model_year") or 0)
            except (TypeError, ValueError):
                continue
            fallback_candidates.append((abs(item_year - target_year), item_year, item))
        if fallback_candidates:
            nearest_distance = min(candidate[0] for candidate in fallback_candidates)
            nearest_candidates = [candidate for candidate in fallback_candidates if candidate[0] == nearest_distance]
            fallback_years = sorted({str(candidate[1]) for candidate in nearest_candidates})
            scored.extend((200, candidate[2]) for candidate in nearest_candidates)
        year_fallback = bool(scored)

    scored.sort(key=lambda pair: (-pair[0], -int(pair[1].get("model_year") or 0), pair[1].get("title") or ""))
    deduped_items = []
    seen_titles = set()
    for _, item in scored:
        title_key = _normalize_car_search_text(item.get("title"))
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        deduped_items.append(item)
    return jsonify({
        "success": True,
        "query": query,
        "matchedBrand": brand,
        "matchedYear": explicit_year,
        "yearFallback": year_fallback,
        "yearFallbackMessage": (
            f"未找到{explicit_year}款，已显示最接近的真实年款：{'/'.join(fallback_years)}款"
            if year_fallback else ""
        ),
        "items": deduped_items[:limit],
        "total": len(deduped_items),
        "source": "server_cached_csv",
    })


@app.route('/pricing_assistant_mock.js', methods=['GET'])
def serve_pricing_assistant_mock():
    js_path = os.path.join(_project_root(), "pricing_assistant_mock.js")
    if os.path.exists(js_path):
        return send_from_directory(_project_root(), "pricing_assistant_mock.js")
    return "", 404


def _feedback_dir():
    path = os.environ.get("FEEDBACK_DIR") or os.path.join(_project_root(), "feedback_records")
    os.makedirs(path, exist_ok=True)
    return path


def _feedback_jsonl_path():
    return os.path.join(_feedback_dir(), "assistant_feedback.jsonl")


def _trace_jsonl_path():
    return os.path.join(_feedback_dir(), "assistant_trace.jsonl")


def _eval_candidates_jsonl_path():
    path = os.path.join(_project_root(), "eval")
    os.makedirs(path, exist_ok=True)
    return os.path.join(path, "feedback_eval_candidates.jsonl")


def _now_bj():
    return datetime.now(timezone(timedelta(hours=8)))


def _now_bj_iso():
    return _now_bj().isoformat(timespec="seconds")


def generate_trace_id():
    return f"trace_{_now_bj().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:10]}"


def append_jsonl(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _mask_sensitive_text(text):
    text = str(text or "")
    text = re.sub(r"(?<!\d)(1[3-9]\d{2})\d{4}(\d{4})(?!\d)", r"\1****\2", text)
    text = re.sub(
        r"([京沪津渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z])([A-Z0-9]{3,5})([A-Z0-9挂学警港澳])",
        r"\1****\3",
        text,
    )
    text = re.sub(r"(sk-[A-Za-z0-9_\-]{8,}|hf_[A-Za-z0-9_\-]{8,}|AKID[A-Za-z0-9_\-]{8,})", "[已脱敏密钥]", text)
    return text


def sanitize_for_log(value, max_text_len=1200, depth=0):
    if depth > 4:
        return "[已截断]"
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        text = _mask_sensitive_text(value)
        return text[:max_text_len] + ("..." if len(text) > max_text_len else "")
    if isinstance(value, list):
        return [sanitize_for_log(item, max_text_len=max_text_len, depth=depth + 1) for item in value[:20]]
    if isinstance(value, dict):
        sanitized = {}
        for key, item in list(value.items())[:60]:
            key_text = str(key)
            if any(secret_key in key_text.lower() for secret_key in ["key", "token", "secret", "password", "cookie"]):
                sanitized[key_text] = "[已脱敏]"
            else:
                sanitized[key_text] = sanitize_for_log(item, max_text_len=max_text_len, depth=depth + 1)
        return sanitized
    return sanitize_for_log(str(value), max_text_len=max_text_len, depth=depth + 1)


def compact_ref_cars(ref_cars, limit=5):
    compacted = []
    for ref in (ref_cars or [])[:limit]:
        if hasattr(ref, "__dict__"):
            ref = ref.__dict__
        if not isinstance(ref, dict):
            continue
        compacted.append(sanitize_for_log({
            "brand": ref.get("brand"),
            "series": ref.get("series"),
            "model": ref.get("model"),
            "title": ref.get("title") or ref.get("model_name"),
            "model_year": ref.get("model_year"),
            "mileage": ref.get("mileage"),
            "transfer_count": ref.get("transfer_count"),
            "color": ref.get("color"),
            "city": ref.get("city"),
            "c2b_price": ref.get("c2b_price"),
            "b2c_price": ref.get("b2c_price"),
            "inspection_score": ref.get("inspection_score"),
        }, max_text_len=300))
    return compacted


def write_assistant_trace(record):
    try:
        base = {
            "traceId": record.get("traceId") or generate_trace_id(),
            "serverCreatedAt": _now_bj_iso(),
        }
        base.update(sanitize_for_log(record, max_text_len=1600))
        append_jsonl(_trace_jsonl_path(), base)
        return base["traceId"]
    except Exception as exc:
        print(f"⚠️ trace 写入失败，不影响主流程: {exc}")
        return record.get("traceId")


def _read_jsonl_records(path, limit=500):
    if not os.path.exists(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    records.sort(key=lambda item: item.get("serverCreatedAt") or item.get("createdAt") or "", reverse=True)
    if limit:
        return records[: int(limit)]
    return records


def _read_feedback_records(limit=500):
    return _read_jsonl_records(_feedback_jsonl_path(), limit=limit)


def _read_trace_records(limit=0):
    return _read_jsonl_records(_trace_jsonl_path(), limit=limit)


def _find_trace_by_id(trace_id):
    if not trace_id:
        return None
    for trace in _read_trace_records(limit=0):
        if trace.get("traceId") == trace_id:
            return trace
    return None


def _find_feedback_by_id(feedback_id):
    for record in _read_feedback_records(limit=0):
        if record.get("feedbackId") == feedback_id:
            return record
    return None


def _rewrite_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _count_by(records, key):
    counts = {}
    for record in records:
        value = record.get(key) or "-"
        counts[value] = counts.get(value, 0) + 1
    return [{"name": key, "value": value, "count": count} for value, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)]


def _parse_iso_date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
        return parsed
    except Exception:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d")
        except Exception:
            return None


def _filter_feedback_records(records, args):
    filtered = []
    start_date = _parse_iso_date(args.get("startDate"))
    end_date = _parse_iso_date(args.get("endDate"))
    for record in records:
        ok = True
        if (record.get("feedbackKind") or "explicit") == "implicit":
            continue
        for key in ["answerType", "errorType", "businessIntent", "rootIntent", "workflow", "promptVersion"]:
            expected = args.get(key)
            if expected and str(record.get(key) or "") != expected:
                ok = False
                break
        rating = args.get("rating")
        if ok and rating and str(record.get("rating") or "") != str(rating):
            ok = False
        created_at = _parse_iso_date(record.get("serverCreatedAt") or record.get("createdAt"))
        if ok and start_date and created_at and created_at < start_date:
            ok = False
        if ok and end_date and created_at and created_at > end_date + timedelta(days=1):
            ok = False
        if ok:
            filtered.append(record)
    return filtered


ERROR_TYPES = {
    "INTENT_WRONG",
    "PRICE_UNREASONABLE",
    "EVIDENCE_WRONG",
    "MISSING_CONTEXT",
    "ANSWER_NOT_ACTIONABLE",
    "FORMAT_BAD",
    "OTHER",
}


def _workflow_from_intent(root_intent="", diag_sub_intent=""):
    diag = diag_sub_intent or ""
    if diag == "price_reason":
        return "price_explanation"
    if diag == "market_competitor":
        return "market_competitor_chat"
    if root_intent == "valuation":
        return "media_pricing"
    if root_intent == "adjust":
        return "supplement_condition"
    if root_intent == "fallback":
        return "fallback_chat"
    return "chat"


def _extract_pricing_snapshot(source):
    source = source or {}
    pricing = source.get("pricingResult") or {}
    if not pricing and source.get("data"):
        pricing = source.get("data") or {}
    ref_cars = pricing.get("ref_cars") or pricing.get("refCars") or []
    return {
        "c2bPrice": pricing.get("c2bPrice") or pricing.get("c2b_price"),
        "b2cPrice": pricing.get("b2cPrice") or pricing.get("b2c_price"),
        "c2bRange": pricing.get("c2bRange") or [pricing.get("c2b_low"), pricing.get("c2b_high")],
        "b2cRange": pricing.get("b2cRange") or [pricing.get("b2c_low"), pricing.get("b2c_high")],
        "targetC2B": pricing.get("targetC2B") or pricing.get("c2bPrice") or pricing.get("c2b_price"),
        "targetB2C": pricing.get("targetB2C") or pricing.get("b2cPrice") or pricing.get("b2c_price"),
        "conditionScore": pricing.get("condition_score") or pricing.get("conditionScore"),
        "refCount": pricing.get("ref_count") or pricing.get("refCount") or len(ref_cars),
        "refB2cMean": pricing.get("ref_b2c_mean") or pricing.get("refB2cMean"),
    }


def build_ai_judge_prompt(feedback, trace):
    return sanitize_for_log({
        "task": "判断用户反馈对应的主要问题类型，输出结构化 JSON。",
        "feedback": feedback,
        "trace": trace,
    }, max_text_len=1000)


def mock_ai_judge(feedback, trace):
    error_type = feedback.get("errorType")
    business_intent = feedback.get("businessIntent") or (trace or {}).get("businessIntent")
    corrected_intent = feedback.get("correctedIntent")
    if error_type in ERROR_TYPES:
        primary = error_type
    elif corrected_intent and business_intent and corrected_intent != business_intent:
        primary = "INTENT_WRONG"
    elif int(feedback.get("rating") or 0) <= 2:
        primary = "OTHER"
    else:
        primary = None
    return {
        "isBadCase": bool(primary),
        "primaryErrorType": primary,
        "secondaryErrorType": None,
        "judgeScore": 0.3 if primary else 0.8,
        "reason": "基于用户评分、点选问题类型和纠正意图做规则判断，未调用外部模型。",
        "suggestedFix": "若为低分样本，建议加入反馈评测集并人工补充 expectedIntent/referenceAnswer。",
    }


def judge_feedback_case(feedback, trace):
    if _env_truthy("ENABLE_AI_JUDGE", default=False):
        # 预留：后续可在这里接已有 LLM client。当前默认不调用任何外部模型。
        return mock_ai_judge(feedback, trace)
    return mock_ai_judge(feedback, trace)


@app.route('/api/feedback', methods=['POST'])
def submit_feedback_record():
    """记录所有用户的回答评分反馈，JSONL 落盘，便于 demo 后台查看和导出。"""
    try:
        payload = request.get_json(silent=True) or {}
        trace = _find_trace_by_id(payload.get("traceId") or payload.get("trace_id"))
        trace_pricing = _extract_pricing_snapshot(trace or {})
        error_type = payload.get("errorType") or ""
        if error_type and error_type not in ERROR_TYPES:
            error_type = "OTHER"
        feedback_kind = payload.get("feedbackKind") or "explicit"
        if feedback_kind == "implicit":
            return jsonify({"success": True, "data": {"ignored": True, "reason": "implicit feedback disabled"}})
        record = {
            "schemaVersion": "feedback_v2",
            "feedbackId": str(uuid.uuid4()),
            "serverCreatedAt": _now_bj_iso(),
            "clientCreatedAt": payload.get("createdAt"),
            "feedbackKind": "explicit",
            "feedbackValue": "",
            "messageId": payload.get("messageId"),
            "traceId": payload.get("traceId") or payload.get("trace_id") or "",
            "sourceApi": payload.get("sourceApi") or (trace or {}).get("api") or "",
            "answerType": payload.get("answerType") or (trace or {}).get("answerType") or "chat",
            "businessIntent": payload.get("businessIntent") or (trace or {}).get("businessIntent") or "",
            "rootIntent": payload.get("rootIntent") or (trace or {}).get("rootIntent") or "",
            "diagSubIntent": payload.get("diagSubIntent") or (trace or {}).get("diagSubIntent") or "",
            "workflow": payload.get("workflow") or (trace or {}).get("workflow") or "",
            "modelName": payload.get("modelName") or (trace or {}).get("modelName") or "",
            "promptVersion": payload.get("promptVersion") or (trace or {}).get("promptVersion") or "",
            "errorType": error_type,
            "correctedIntent": payload.get("correctedIntent") or "",
            "pricingErrorType": payload.get("pricingErrorType") or "",
            "aiSuggestedPrice": payload.get("aiSuggestedPrice"),
            "aiC2bPrice": payload.get("aiC2bPrice") or trace_pricing.get("c2bPrice"),
            "aiB2cPrice": payload.get("aiB2cPrice") or trace_pricing.get("b2cPrice"),
            "aiPriceLow": payload.get("aiPriceLow"),
            "aiPriceHigh": payload.get("aiPriceHigh"),
            "userFinalPrice": payload.get("userFinalPrice"),
            "vehicleFingerprint": payload.get("vehicle_fingerprint") or payload.get("vehicleFingerprint") or "",
            "vehicleSlots": payload.get("vehicle_slots") or payload.get("vehicleSlots") or {},
            "systemPurchasePrice": payload.get("system_purchase_price") or payload.get("systemPurchasePrice"),
            "userAdjustedPurchasePrice": payload.get("user_adjusted_purchase_price") or payload.get("userAdjustedPurchasePrice"),
            "systemSalePrice": payload.get("system_sale_price") or payload.get("systemSalePrice"),
            "userAdjustedSalePrice": payload.get("user_adjusted_sale_price") or payload.get("userAdjustedSalePrice"),
            "actualPurchasePrice": payload.get("actual_purchase_price") or payload.get("actualPurchasePrice"),
            "actualSalePrice": payload.get("actual_sale_price") or payload.get("actualSalePrice"),
            "grossProfit": payload.get("gross_profit") or payload.get("grossProfit") or payload.get("estimated_profit") or payload.get("estimatedProfit"),
            "calculatorSnapshot": payload.get("calculator_snapshot") or payload.get("calculatorSnapshot") or {},
            "acceptedByCustomer": payload.get("accepted_by_customer") if "accepted_by_customer" in payload else payload.get("acceptedByCustomer"),
            "freeText": payload.get("free_text") or payload.get("freeText") or payload.get("comment") or "",
            "refCount": payload.get("refCount") or trace_pricing.get("refCount"),
            "hasRetrievedContext": payload.get("hasRetrievedContext") if payload.get("hasRetrievedContext") is not None else bool((trace or {}).get("retrievedContext")),
            "rating": payload.get("rating"),
            "selectedTags": payload.get("selectedTags") or payload.get("tags") or [],
            "customFeedback": payload.get("customFeedback") or payload.get("comment") or "",
            "username": _current_internal_username(),
            "userQuestion": payload.get("userQuestion") or "",
            "assistantAnswer": payload.get("assistantAnswer") or "",
            "pageUrl": payload.get("pageUrl") or "",
            "sessionId": payload.get("sessionId") or "",
            "userAgent": payload.get("userAgent") or request.headers.get("User-Agent", ""),
            "clientIp": request.headers.get("X-Forwarded-For", request.remote_addr) or "",
        }
        record = sanitize_for_log(record, max_text_len=3000)
        append_jsonl(_feedback_jsonl_path(), record)
        reflexion_data = {}
        try:
            from services.reflexion.feedback_schema import FeedbackRecord
            from services.reflexion.reflection_generator import generate_reflection
            from services.reflexion.reflection_store import ReflectionStore

            report_snapshot = payload.get("reportSnapshot") or payload.get("report_snapshot") or {}
            final_result = payload.get("finalResult") or payload.get("final_result") or {}
            feedback_record = FeedbackRecord.from_payload(
                payload,
                fallback_id=record["feedbackId"],
                created_at=record["serverCreatedAt"],
                trace=trace or {},
            )
            store = ReflectionStore()
            store.save_feedback(feedback_record)
            reflection = generate_reflection(
                feedback_record,
                task_state=trace or {},
                final_result=final_result if isinstance(final_result, dict) else {},
                report_snapshot=report_snapshot if isinstance(report_snapshot, dict) else {},
            )
            store.save_reflection(reflection)
            reflexion_data = {
                "feedback_id": feedback_record.feedback_id,
                "reflection_id": reflection.reflection_id,
                "reflection_preview": reflection.next_time_instruction,
            }
        except Exception as reflexion_exc:
            print(f"⚠️ 反馈记忆写入失败，不影响旧反馈记录: {reflexion_exc}")
            reflexion_data = {"reflection_error": str(reflexion_exc)}
        return jsonify({
            "success": True,
            "ok": True,
            "data": {"feedbackId": record["feedbackId"], **reflexion_data},
            **reflexion_data,
        })
    except Exception as e:
        print(f"❌ 反馈记录失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/feedback/list', methods=['GET'])
def list_feedback_records():
    try:
        limit = int(request.args.get("limit", "500"))
        records = _filter_feedback_records(_read_feedback_records(limit=0), request.args)
        if limit:
            records = records[:limit]
        reflexion_records = []
        try:
            from services.reflexion.reflection_store import ReflectionStore
            reflexion_records = ReflectionStore().list_feedback(dict(request.args), limit=limit)
        except Exception:
            reflexion_records = []
        return jsonify({"success": True, "data": {"total": len(records), "records": records, "reflexion_records": reflexion_records}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/reflections/list', methods=['GET'])
def list_reflection_records():
    try:
        from services.reflexion.reflection_store import ReflectionStore
        limit = int(request.args.get("limit", "500"))
        records = ReflectionStore().list_reflections(dict(request.args), limit=limit)
        return jsonify({"success": True, "data": {"total": len(records), "records": records}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/reflections/<reflection_id>/disable', methods=['POST'])
def disable_reflection_record(reflection_id):
    try:
        from services.reflexion.reflection_store import ReflectionStore
        disabled = ReflectionStore().disable_reflection(reflection_id)
        status = 200 if disabled else 404
        return jsonify({"success": disabled, "ok": disabled, "data": {"reflection_id": reflection_id, "disabled": disabled}}), status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/pricing/customer-script/regenerate', methods=['POST'])
def regenerate_pricing_customer_script():
    try:
        payload = request.get_json(silent=True) or {}
        vehicle_title = str(payload.get("vehicle_title") or "这台车")
        purchase_price = float(payload.get("current_purchase_price") or payload.get("purchase_price") or 0)
        sale_price = float(payload.get("current_sale_price") or payload.get("sale_price") or 0)
        gross_profit = float(payload.get("gross_profit") or 0)
        gross_rate = float(payload.get("gross_profit_rate") or 0)
        market_note = str(payload.get("market_note") or "")
        fallback = _safe_customer_script(
            vehicle_title=vehicle_title,
            purchase_price=purchase_price,
            sale_price=sale_price,
            gross_profit=gross_profit,
            gross_rate=gross_rate,
            market_note=market_note,
        )
        text = fallback
        source = "fallback_rule"
        try:
            from services.llm_client import Qwen3LocalClient, extract_json_object
            client = Qwen3LocalClient()
            if client.config_snapshot().get("api_key_configured") or os.environ.get("LLM_BASE_URL"):
                prompt = (
                    "你是一线二手车收车顾问。基于当前利润方案生成一段对客沟通话术。"
                    "不要出现模型、算法、置信度、中位价、样本区间、追价上限、内部上限、数据库。"
                    "不要暴露售车价和内部毛利，只能讲检测、整备、再卖周期和可申请空间。"
                    "输出 JSON：{\"text\":\"\"}"
                )
                result = client.structured_extract(prompt, sanitize_for_log(payload, max_text_len=900))
                parsed = extract_json_object(result.content) if result.ok else None
                candidate = str((parsed or {}).get("text") or "").strip()
                if candidate:
                    text = candidate
                    source = "llm_provider"
        except Exception:
            text = fallback
            source = "fallback_rule"
        text = _sanitize_customer_script_text(text)
        text = _replace_exact_price_with_public_wording(text, purchase_price)
        return jsonify({"success": True, "data": {"text": text, "source": source}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _safe_customer_script(*, vehicle_title, purchase_price, sale_price, gross_profit, gross_rate, market_note):
    talk_price = _soft_wan_price(purchase_price)
    margin_note = "后面再卖还有一定空间" if gross_profit > 0 and gross_rate >= 0.06 else "后面再卖空间不大，所以前面报价不能太冒进"
    return (
        f"哥，这台{vehicle_title}我看了，基础条件可以继续聊。"
        f"但我们收车不能只看网上挂价，后面还要看检测、整备和再卖周期，{margin_note}。"
        f"我建议先按{talk_price}沟通，车况要是检测出来确实好、手续也清楚，再给您争取一个更合适的价。"
        "咱们先把检测约了，车况确认清楚后再把最终价定下来。"
    )


def _soft_wan_price(value):
    try:
        number = float(value)
    except Exception:
        return "这个价"
    if number <= 0:
        return "这个价"
    wan = number / 10000 if number > 1000 else number
    integer = int(wan)
    decimal = round(wan - integer, 4)
    if decimal >= 0.65:
        return f"{integer}万多"
    if decimal >= 0.2:
        return f"{integer}万出头"
    return f"{integer}万左右"


def _sanitize_customer_script_text(text):
    value = str(text or "")
    for word in ("中位价", "价格区间", "最高样本", "追价上限", "内部上限", "置信度", "模型", "算法", "RAG", "workflow", "trace", "数据库", "我们系统算出来"):
        value = value.replace(word, "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _replace_exact_price_with_public_wording(text, purchase_price):
    value = str(text or "")
    try:
        price = float(purchase_price)
    except Exception:
        return value
    if price <= 0:
        return value
    wan = price / 10000 if price > 1000 else price
    public_price = _soft_wan_price(price)
    exact_patterns = {
        f"{wan:.2f}万元",
        f"{wan:.1f}万元",
        f"{wan:g}万元",
        f"{wan:.2f}万",
        f"{wan:.1f}万",
        f"{wan:g}万",
        f"{wan:.2f} 万",
        f"{wan:.1f} 万",
    }
    for exact in sorted(exact_patterns, key=len, reverse=True):
        value = value.replace(exact, public_price)
    return value


@app.route('/api/feedback/summary', methods=['GET'])
def feedback_summary():
    try:
        records = _filter_feedback_records(_read_feedback_records(limit=0), request.args)
        explicit = records
        ratings = [float(r.get("rating")) for r in explicit if r.get("rating") not in (None, "")]
        low = [r for r in explicit if r.get("rating") not in (None, "") and float(r.get("rating") or 0) <= 3]
        data = {
            "total": len(explicit),
            "explicitCount": len(explicit),
            "implicitCount": 0,
            "lowRatingCount": len(low),
            "avgRating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "lowRatingRate": round(len(low) / len(explicit), 4) if explicit else 0,
            "byErrorType": _count_by(explicit, "errorType"),
            "byAnswerType": _count_by(explicit, "answerType"),
            "byBusinessIntent": _count_by(explicit, "businessIntent"),
            "byWorkflow": _count_by(explicit, "workflow"),
            "byPromptVersion": _count_by(explicit, "promptVersion"),
        }
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/feedback/detail/<feedback_id>', methods=['GET'])
def feedback_detail(feedback_id):
    try:
        feedback = _find_feedback_by_id(feedback_id)
        if not feedback:
            return jsonify({"success": False, "error": "feedback not found"}), 404
        trace = _find_trace_by_id(feedback.get("traceId"))
        return jsonify({"success": True, "data": {"feedback": feedback, "trace": trace, "judge": judge_feedback_case(feedback, trace)}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/feedback/delete', methods=['POST'])
def delete_feedback_record():
    """删除指定反馈，主要用于清理误点/测试反馈。"""
    try:
        payload = request.get_json(silent=True) or {}
        feedback_id = payload.get("feedbackId")
        purge_implicit = bool(payload.get("purgeImplicit"))
        records = _read_feedback_records(limit=0)
        if purge_implicit:
            kept = [r for r in records if (r.get("feedbackKind") or "explicit") != "implicit"]
        elif feedback_id:
            kept = [r for r in records if r.get("feedbackId") != feedback_id]
        else:
            return jsonify({"success": False, "error": "feedbackId required"}), 400
        deleted = len(records) - len(kept)
        _rewrite_jsonl(_feedback_jsonl_path(), kept)
        return jsonify({"success": True, "data": {"deleted": deleted}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/eval-cases/from-feedback', methods=['POST'])
def add_eval_case_from_feedback():
    try:
        payload = request.get_json(silent=True) or {}
        feedback_id = payload.get("feedbackId")
        feedback = _find_feedback_by_id(feedback_id)
        if not feedback:
            return jsonify({"success": False, "error": "feedback not found"}), 404
        if feedback.get("feedbackKind") == "implicit":
            return jsonify({"success": False, "error": "implicit feedback cannot be added by default"}), 400
        path = _eval_candidates_jsonl_path()
        existing = _read_jsonl_records(path, limit=0)
        if any(item.get("sourceFeedbackId") == feedback_id for item in existing):
            return jsonify({"success": True, "data": {"status": "already_exists"}})
        trace = _find_trace_by_id(feedback.get("traceId")) or {}
        case = {
            "caseId": f"feedback_case_{_now_bj().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}",
            "sourceFeedbackId": feedback_id,
            "sourceTraceId": feedback.get("traceId") or "",
            "createdAt": _now_bj_iso(),
            "userQuery": feedback.get("userQuestion") or trace.get("userQuery") or "",
            "assistantAnswer": feedback.get("assistantAnswer") or trace.get("answerPreview") or "",
            "answerType": feedback.get("answerType") or trace.get("answerType") or "",
            "businessIntent": feedback.get("businessIntent") or trace.get("businessIntent") or "",
            "rootIntent": feedback.get("rootIntent") or trace.get("rootIntent") or "",
            "diagSubIntent": feedback.get("diagSubIntent") or trace.get("diagSubIntent") or "",
            "workflow": feedback.get("workflow") or trace.get("workflow") or "",
            "correctedIntent": feedback.get("correctedIntent") or "",
            "errorType": feedback.get("errorType") or "",
            "selectedTags": feedback.get("selectedTags") or [],
            "customFeedback": feedback.get("customFeedback") or "",
            "pricingResult": trace.get("pricingResult") or {},
            "retrievedContext": trace.get("retrievedContext") or {},
            "expectedIntent": "",
            "expectedWorkflow": "",
            "referenceAnswer": "",
            "status": "pending",
        }
        append_jsonl(path, sanitize_for_log(case, max_text_len=3000))
        return jsonify({"success": True, "data": {"status": "created", "caseId": case["caseId"]}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/eval-cases/list', methods=['GET'])
def list_feedback_eval_cases():
    try:
        limit = int(request.args.get("limit", "500"))
        records = _read_jsonl_records(_eval_candidates_jsonl_path(), limit=limit)
        return jsonify({"success": True, "data": {"total": len(records), "records": records}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/feedback/export', methods=['GET'])
def export_reflexion_feedback_records():
    try:
        from services.reflexion.reflection_store import ReflectionStore
        fmt = str(request.args.get("format") or "jsonl").lower()
        store = ReflectionStore()
        if fmt == "csv":
            csv_text = store.export_feedback_csv()
            return Response(
                "\ufeff" + csv_text,
                mimetype="text/csv; charset=utf-8",
                headers={"Content-Disposition": "attachment; filename=reflexion_feedback.csv"},
            )
        return Response(
            store.export_feedback_jsonl(),
            mimetype="application/x-ndjson; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=reflexion_feedback.jsonl"},
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/feedback/export.csv', methods=['GET'])
def export_feedback_records():
    records = _read_feedback_records(limit=0)
    output = io.StringIO()
    fieldnames = [
        "serverCreatedAt", "feedbackId", "traceId", "username",
        "answerType", "rating", "errorType", "correctedIntent", "selectedTags",
        "businessIntent", "rootIntent", "diagSubIntent", "workflow", "modelName", "promptVersion",
        "customFeedback", "userQuestion", "assistantAnswer", "pageUrl", "sessionId", "clientIp"
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for record in records:
        row = {key: record.get(key, "") for key in fieldnames}
        row["selectedTags"] = "、".join(record.get("selectedTags") or [])
        writer.writerow(row)
    csv_text = output.getvalue()
    return Response(
        "\ufeff" + csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=assistant_feedback.csv"},
    )


@app.route('/feedback-admin', methods=['GET'])
def feedback_admin_page():
    """反馈后台：查看用户显式反馈、trace、错误类型，并沉淀评测样本。"""
    html = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI懂车价反馈后台</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 text-slate-900">
  <main class="max-w-[1600px] mx-auto p-6">
    <header class="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-6">
      <div>
        <div class="text-sm font-black text-blue-600 tracking-widest">FEEDBACK ADMIN</div>
        <h1 class="text-3xl font-black mt-1">AI懂车价反馈记录</h1>
        <p class="text-slate-500 mt-2">查看用户评分、问题类型、trace 链路，并把坏例加入评测集。</p>
      </div>
      <a class="px-4 py-2 rounded-xl bg-blue-600 text-white font-black" href="/api/feedback/export.csv">导出 CSV</a>
    </header>
    <section id="summary" class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5"></section>
    <section class="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 mb-5">
      <div class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 text-sm">
        <input id="filter-startDate" type="date" class="border rounded-xl px-3 py-2" />
        <input id="filter-endDate" type="date" class="border rounded-xl px-3 py-2" />
        <select id="filter-rating" class="border rounded-xl px-3 py-2"><option value="">评分</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select>
        <select id="filter-answerType" class="border rounded-xl px-3 py-2"><option value="">回答类型</option></select>
        <select id="filter-errorType" class="border rounded-xl px-3 py-2"><option value="">问题类型</option></select>
        <select id="filter-businessIntent" class="border rounded-xl px-3 py-2"><option value="">业务意图</option></select>
        <select id="filter-workflow" class="border rounded-xl px-3 py-2"><option value="">workflow</option></select>
        <select id="filter-promptVersion" class="border rounded-xl px-3 py-2"><option value="">promptVersion</option></select>
      </div>
      <div class="mt-3 flex gap-2">
        <button onclick="loadFeedback()" class="px-4 py-2 rounded-xl bg-slate-900 text-white font-black">筛选</button>
        <button onclick="resetFilters()" class="px-4 py-2 rounded-xl bg-slate-100 text-slate-700 font-black">重置</button>
      </div>
    </section>
    <section class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="overflow-auto">
        <table class="min-w-full text-sm">
          <thead class="bg-slate-50 text-slate-500">
            <tr>
              <th class="text-left px-4 py-3">时间</th>
              <th class="text-left px-4 py-3">traceId</th>
              <th class="text-left px-4 py-3">answerType</th>
              <th class="text-left px-4 py-3">评分</th>
              <th class="text-left px-4 py-3">errorType</th>
              <th class="text-left px-4 py-3">businessIntent</th>
              <th class="text-left px-4 py-3">rootIntent</th>
              <th class="text-left px-4 py-3">workflow</th>
              <th class="text-left px-4 py-3">promptVersion</th>
              <th class="text-left px-4 py-3">modelName</th>
              <th class="text-left px-4 py-3">用户问题</th>
              <th class="text-left px-4 py-3">AI回答</th>
              <th class="text-left px-4 py-3">用户反馈内容</th>
              <th class="text-left px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody id="rows" class="divide-y divide-slate-100"></tbody>
        </table>
      </div>
    </section>
  </main>
  <div id="detail-modal" class="hidden fixed inset-0 bg-slate-950/40 backdrop-blur-sm z-50 p-6 overflow-auto">
    <div class="max-w-5xl mx-auto bg-white rounded-3xl shadow-2xl border border-slate-200 p-6">
      <div class="flex justify-between items-start gap-4 mb-4">
        <h2 class="text-2xl font-black">反馈详情</h2>
        <button onclick="closeDetail()" class="px-3 py-2 rounded-xl bg-slate-100 font-black">关闭</button>
      </div>
      <pre id="detail-content" class="whitespace-pre-wrap text-sm bg-slate-50 rounded-2xl p-4 overflow-auto max-h-[70vh]"></pre>
    </div>
  </div>
  <script>
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
    const truncate = (v, n=80) => { const s = String(v ?? ''); return s.length > n ? s.slice(0, n) + '…' : s; };
    const filterIds = ['startDate','endDate','rating','answerType','errorType','businessIntent','workflow','promptVersion'];
    function buildQuery() {
      const params = new URLSearchParams({ limit: '1000' });
      filterIds.forEach(id => {
        const value = document.getElementById('filter-' + id)?.value;
        if (value) params.set(id, value);
      });
      return params.toString();
    }
    function fillSelect(id, values) {
      const el = document.getElementById('filter-' + id);
      if (!el || el.dataset.ready) return;
      values.filter(Boolean).sort().forEach(v => el.insertAdjacentHTML('beforeend', `<option value="${esc(v)}">${esc(v)}</option>`));
      el.dataset.ready = '1';
    }
    function resetFilters() {
      filterIds.forEach(id => { const el = document.getElementById('filter-' + id); if (el) el.value = ''; });
      loadFeedback();
    }
    function loadFeedback() {
      Promise.all([
        fetch('/api/feedback/list?' + buildQuery()).then(r => r.json()),
        fetch('/api/feedback/summary?' + buildQuery()).then(r => r.json())
      ]).then(([res, summaryRes]) => {
      const records = res?.data?.records || [];
      fillSelect('answerType', [...new Set(records.map(r => r.answerType))]);
      fillSelect('errorType', [...new Set(records.map(r => r.errorType))]);
      fillSelect('businessIntent', [...new Set(records.map(r => r.businessIntent))]);
      fillSelect('workflow', [...new Set(records.map(r => r.workflow))]);
      fillSelect('promptVersion', [...new Set(records.map(r => r.promptVersion))]);
      const summary = summaryRes?.data || {};
      document.getElementById('summary').innerHTML = [
        ['总反馈数', summary.total ?? records.length],
        ['显式反馈', summary.explicitCount ?? '-'],
        ['平均评分', summary.avgRating ?? '--'],
        ['低分率', summary.lowRatingRate !== undefined ? `${Math.round(summary.lowRatingRate * 100)}%` : '--'],
      ].map(([k,v]) => `<div class="bg-white rounded-2xl border border-slate-200 p-4"><div class="text-slate-500 text-sm">${k}</div><div class="text-2xl font-black mt-1">${v}</div></div>`).join('');
      document.getElementById('rows').innerHTML = records.map(r => `
        <tr class="align-top">
          <td class="px-4 py-3 whitespace-nowrap text-slate-500">${esc((r.serverCreatedAt || '').replace('T',' ').slice(0,19))}</td>
          <td class="px-4 py-3 whitespace-nowrap font-mono text-xs">${esc(truncate(r.traceId, 18) || '-')}</td>
          <td class="px-4 py-3 whitespace-nowrap font-bold">${esc(r.answerType || '-')}</td>
          <td class="px-4 py-3 whitespace-nowrap font-black text-amber-500">${r.rating ? esc(r.rating) + ' 星' : '-'}</td>
          <td class="px-4 py-3 whitespace-nowrap">${esc(r.errorType || '-')}</td>
          <td class="px-4 py-3 whitespace-nowrap">${esc(r.businessIntent || '-')}</td>
          <td class="px-4 py-3 whitespace-nowrap">${esc(r.rootIntent || '-')}</td>
          <td class="px-4 py-3 whitespace-nowrap">${esc(r.workflow || '-')}</td>
          <td class="px-4 py-3 whitespace-nowrap">${esc(r.promptVersion || '-')}</td>
          <td class="px-4 py-3 whitespace-nowrap">${esc(r.modelName || '-')}</td>
          <td class="px-4 py-3 min-w-[240px]">${esc(truncate(r.userQuestion, 100))}</td>
          <td class="px-4 py-3 min-w-[240px]">${esc(truncate(r.assistantAnswer, 100))}</td>
          <td class="px-4 py-3 min-w-[240px]">${esc(truncate(r.customFeedback, 120) || '-')}</td>
          <td class="px-4 py-3 whitespace-nowrap">
            <button onclick="openDetail('${esc(r.feedbackId)}')" class="px-3 py-1.5 rounded-lg bg-slate-100 font-bold mr-2">详情</button>
            <button onclick="addEvalCase('${esc(r.feedbackId)}')" class="px-3 py-1.5 rounded-lg bg-blue-600 text-white font-bold">加入评测集</button>
          </td>
        </tr>
      `).join('');
      });
    }
    function openDetail(id) {
      fetch('/api/feedback/detail/' + encodeURIComponent(id)).then(r => r.json()).then(res => {
        document.getElementById('detail-content').textContent = JSON.stringify(res.data || res, null, 2);
        document.getElementById('detail-modal').classList.remove('hidden');
      });
    }
    function closeDetail() { document.getElementById('detail-modal').classList.add('hidden'); }
    function addEvalCase(id) {
      fetch('/api/eval-cases/from-feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedbackId: id })
      }).then(r => r.json()).then(res => alert(res?.data?.status === 'already_exists' ? '已存在' : (res.success ? '已加入评测集' : (res.error || '加入失败'))));
    }
    loadFeedback();
  </script>
</body>
</html>
"""
    return Response(html, mimetype="text/html; charset=utf-8")


@app.route('/api/asr', methods=['POST'])
def speech_to_text():
    """语音识别 API：接收前端录音的 WAV，返回转写文本。"""
    try:
        if ASR_DISABLED:
            return jsonify({
                'success': False,
                'error': '当前免费部署版未启用后端语音识别。可在 Space 环境中开启 SenseVoice ASR 后使用。'
            }), 503

        audio_file = request.files.get('audio')
        if audio_file is None:
            return jsonify({'success': False, 'error': '缺少音频文件'}), 400

        audio_bytes = audio_file.read()
        if not audio_bytes:
            return jsonify({'success': False, 'error': '音频内容为空'}), 400

        audio_array, sample_rate = _load_pcm_wav(audio_bytes)
        asr_backend, model_name, provider = _get_asr_backend()

        if provider == 'sensevoice':
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                temp_wav.write(audio_bytes)
                temp_wav_path = temp_wav.name

            try:
                result = asr_backend.generate(
                    input=temp_wav_path,
                    cache={},
                    language="auto",
                    use_itn=True,
                )
            finally:
                try:
                    os.remove(temp_wav_path)
                except OSError:
                    pass
        else:
            result = asr_backend(
                {"array": audio_array, "sampling_rate": sample_rate},
                generate_kwargs={"language": "zh", "task": "transcribe"},
            )

        text = _extract_text_from_asr_result(result)
        if not text:
            raise RuntimeError(f"ASR 未返回可用文本，原始结果: {json.dumps(result, ensure_ascii=False, default=str)[:500]}")

        return jsonify({
            'success': True,
            'data': {
                'text': text,
                'engine': provider,
                'model': model_name,
            }
        })
    except Exception as e:
        print(f"❌ 语音识别失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/asr/status', methods=['GET'])
def asr_status():
    """查看当前 ASR 后端状态，便于排查打包后的实际生效情况。"""
    try:
        if ASR_DISABLED:
            return jsonify({
                'success': True,
                'data': {
                    'provider': 'disabled',
                    'model': '',
                    'note': '当前免费部署版未启用后端语音识别。'
                }
            })

        _, model_name, provider = _get_asr_backend()
        return jsonify({
            'success': True,
            'data': {
                'provider': provider,
                'model': model_name,
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/ocr', methods=['POST'])
def image_to_text():
    """OCR API：默认使用本地 RapidOCR，必要时可切换腾讯云 OCR。"""
    try:
        image_file = request.files.get('image') or request.files.get('file')
        if image_file is None:
            return jsonify({'success': False, 'error': '缺少图片文件'}), 400

        image_bytes = image_file.read()
        if not image_bytes:
            return jsonify({'success': False, 'error': '图片内容为空'}), 400

        provider = (os.environ.get('OCR_PROVIDER') or 'local').strip().lower()
        if provider in {'tencent', 'tencentcloud', 'cloud'}:
            result = recognize_image_bytes(image_bytes, filename=image_file.filename or '')
        else:
            result = recognize_image_bytes_local(image_bytes, filename=image_file.filename or '')

        if not result.get('text'):
            return jsonify({'success': False, 'error': '图片中未识别到可用文字'}), 422

        return jsonify({
            'success': True,
            'data': result
        })
    except TencentOcrError as e:
        print(f"❌ OCR 识别失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    except LocalOcrError as e:
        print(f"❌ 本地 OCR 识别失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    except Exception as e:
        print(f"❌ OCR 识别异常: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/ocr/status', methods=['GET'])
def ocr_status():
    """查看 OCR 配置状态，不返回密钥内容。"""
    return jsonify({
        'success': True,
        'data': {
            'provider': (os.environ.get('OCR_PROVIDER') or 'local').strip().lower(),
            'local': get_local_ocr_config(),
            'tencentcloud': get_tencent_ocr_config(),
        }
    })


def _fast_price_from_refs(car: RealCarListing, refs):
    """公网演示快速估价：基于相似样本和核心字段修正，避免免费 CPU 长时间阻塞。"""
    valid_refs = [ref for ref, _ in (refs or []) if getattr(ref, 'b2c_price', None) and getattr(ref, 'c2b_price', None)]
    if len(valid_refs) < 3:
        return None

    def _avg(values):
        values = [float(v) for v in values if v is not None]
        return sum(values) / max(len(values), 1)

    ref_c2b_mean = _avg([ref.c2b_price for ref in valid_refs])
    ref_b2c_mean = _avg([ref.b2c_price for ref in valid_refs])
    ref_mileage_mean = _avg([ref.mileage for ref in valid_refs])
    ref_transfer_mean = _avg([ref.transfer_count for ref in valid_refs])
    ref_year_mean = _avg([ref.model_year for ref in valid_refs])

    mileage_adjust = (ref_mileage_mean - float(car.mileage or 0)) * 0.18
    transfer_adjust = (ref_transfer_mean - float(car.transfer_count or 0)) * 0.25
    year_adjust = (float(car.model_year or 2020) - ref_year_mean) * 0.55
    color_adjust = -0.15 if car.color and car.color not in {"白色", "黑色", "灰色", "银色", "白", "黑", "灰", "银"} else 0.0
    total_adjust = mileage_adjust + transfer_adjust + year_adjust + color_adjust

    b2c_price = max(0.5, ref_b2c_mean + total_adjust)
    c2b_price = max(0.3, min(ref_c2b_mean + total_adjust * 0.85, b2c_price * 0.92))

    ref_cars = []
    for ref in valid_refs[:5]:
        ref_cars.append({
            'brand': getattr(ref, 'brand', ''),
            'series': getattr(ref, 'series', ''),
            'model_year': getattr(ref, 'model_year', ''),
            'mileage': getattr(ref, 'mileage', 0),
            'transfer_count': getattr(ref, 'transfer_count', 0),
            'b2c_price': getattr(ref, 'b2c_price', 0),
            'c2b_price': getattr(ref, 'c2b_price', 0),
            'inspection_score': getattr(ref, 'inspection_score', 0),
        })

    reason = (
        f"基于相似成交样本估算：参考{len(valid_refs)}辆同类车，"
        f"B2C均价{ref_b2c_mean:.2f}万，C2B均价{ref_c2b_mean:.2f}万；"
        f"按里程、过户、年款、颜色做规则修正后生成区间。"
    )

    return {
        'c2bPrice': round(c2b_price, 2),
        'b2cPrice': round(b2c_price, 2),
        'reason': reason,
        'c2b_low': round(c2b_price * 0.95, 2),
        'c2b_high': round(c2b_price * 1.05, 2),
        'b2c_low': round(b2c_price * 0.95, 2),
        'b2c_high': round(b2c_price * 1.05, 2),
        'condition_desc': '基于相似样本与核心字段生成估价',
        'ref_count': len(valid_refs),
        'ref_b2c_mean': round(ref_b2c_mean, 2),
        'ref_cars': ref_cars,
        'pricing_engine': 'sample_rule_fast',
    }


def _lite_price_from_refs(car: RealCarListing, refs):
    return _fast_price_from_refs(car, refs)


def _safe_year(value):
    """Extract a four-digit year from loose frontend input."""
    if value is None:
        return None
    text = str(value).strip()
    match = re.search(r'(19|20)\d{2}', text)
    if not match:
        short_match = re.search(r'(?<!\d)(\d{2})\s*年', text)
        if short_match:
            year = int(short_match.group(1))
            return 2000 + year if year <= 40 else 1900 + year
    if not match:
        return None
    try:
        return int(match.group(0))
    except Exception:
        return None


def _pricing_model_year_from_input(model_year, vehicle_model_year, reg_year):
    """Return a safe integer year for RealCarListing, never raising on loose date text."""
    return (
        _safe_year(vehicle_model_year)
        or _safe_year(model_year)
        or reg_year
        or datetime.now().year
    )


def _vehicle_year_consistency(model_year, reg_year):
    """Model-year is a sales label and may legitimately lead registration by one year."""
    vehicle_year = _safe_year(model_year)
    registration_year = _safe_year(reg_year)
    if not vehicle_year or not registration_year:
        return {"valid": True, "warning": "", "reason": "YEAR_NOT_COMPARABLE"}
    lead = vehicle_year - registration_year
    if lead <= 0:
        return {"valid": True, "warning": "", "reason": "MODEL_YEAR_NOT_AFTER_REGISTRATION"}
    if lead == 1:
        return {
            "valid": True,
            "warning": f"{vehicle_year}款于{registration_year}年上牌属于常见跨年款，已按车型年款继续报价。",
            "reason": "ONE_YEAR_AHEAD_MODEL_YEAR_ALLOWED",
        }
    return {
        "valid": True,
        "warning": f"车型标注为{vehicle_year}款、首次上牌为{registration_year}年，跨度较大；系统仍报价并降低证据置信度。",
        "reason": "MODEL_YEAR_REGISTRATION_GAP_REVIEW",
    }


@app.route('/api/price', methods=['POST'])
def get_price():
    """定价API端点"""
    trace_id = generate_trace_id()
    started_at = datetime.utcnow()
    car_data = {}
    try:
        car_data = request.json or {}
        
        brand = car_data.get('brand', '')
        series = car_data.get('series', '')
        model = car_data.get('model') or car_data.get('modelName') or car_data.get('standardModelName') or ''
        model_year = str(car_data.get('model_year') or car_data.get('modelYear') or '')
        vehicle_model_year = car_data.get('vehicle_model_year') or car_data.get('vehicleModelYear') or ''
        reg_date = (
            car_data.get('reg_date')
            or car_data.get('regDate')
            or car_data.get('firstLicenseDate')
            or ''
        )
        mileage = float(car_data.get('mileage', car_data.get('mileage_wan_km', 0)) or 0)
        transfer_count = int(car_data.get('transfer', car_data.get('transferCount', car_data.get('transfer_count', 0))) or 0)
        color = car_data.get('color', '')
        city = car_data.get('city', '')
        is_custom_model = bool(car_data.get('is_custom_model', False))

        reg_year = _safe_year(reg_date) or _safe_year(model_year)
        vehicle_year = _safe_year(vehicle_model_year) or _safe_year(f'{model}')
        if not reg_year:
            error_message = '缺少上牌时间，暂不生成报价。请补充上牌年份/月后再生成专业报价报告。'
            write_assistant_trace({
                "traceId": trace_id,
                "api": "/api/price",
                "sessionId": car_data.get("sessionId") or "",
                "messageId": car_data.get("messageId") or "",
                "businessIntent": car_data.get("businessIntent") or "MEDIA_PRICING",
                "userQuery": f"{brand}{series}{model}",
                "rootIntent": "valuation",
                "workflow": "media_pricing",
                "answerType": "media_pricing",
                "modelName": "required-field-validator",
                "promptVersion": "price_v1",
                "useFinetuned": False,
                "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                "pricingResult": _extract_pricing_snapshot({}),
                "retrievedContext": {"refCars": []},
                "answerPreview": "缺少上牌时间，未生成报价。",
                "error": error_message,
            })
            return jsonify({
                'success': False,
                'error': error_message,
                'traceId': trace_id
            }), 422
        year_consistency = _vehicle_year_consistency(vehicle_year, reg_year)
        if year_consistency.get("warning"):
            car_data["year_consistency_warning"] = year_consistency["warning"]
            car_data["year_consistency_reason"] = year_consistency["reason"]

        pricing_model_year = _pricing_model_year_from_input(model_year, vehicle_model_year, reg_year)

        active_pricing_version = _active_pricing_model_version()
        if is_custom_model and active_pricing_version != "v194":
            error_message = f'{brand}{series} 当前没有匹配到车型库标准车型，请从车型库下拉列表选择标准车型后再生成报价。'
            write_assistant_trace({
                "traceId": trace_id,
                "api": "/api/price",
                "sessionId": car_data.get("sessionId") or "",
                "messageId": car_data.get("messageId") or "",
                "businessIntent": car_data.get("businessIntent") or "MEDIA_PRICING",
                "userQuery": f"{brand}{series}{model}",
                "rootIntent": "valuation",
                "workflow": "media_pricing",
                "answerType": "media_pricing",
                "modelName": "model-library-validator",
                "promptVersion": "price_v1",
                "useFinetuned": False,
                "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                "pricingResult": _extract_pricing_snapshot({}),
                "retrievedContext": {"refCars": []},
                "answerPreview": "车型库未匹配，未生成报价。",
                "error": error_message,
            })
            return jsonify({
                'success': False,
                'error': error_message,
                'traceId': trace_id
            }), 422

        if active_pricing_version in {"v159_latest_trusted_cluster", "v159"}:
            try:
                from v159_serving_engine import predict_v159_price

                v159_payload = dict(car_data)
                v159_payload.update({
                    "request_id": trace_id,
                    "modelYear": vehicle_year or pricing_model_year,
                    "model_year": vehicle_year or pricing_model_year,
                    "regDate": reg_date,
                    "reg_date": reg_date,
                    "mileage": mileage,
                    "transferCount": transfer_count,
                    "transfer": transfer_count,
                    "color": color,
                    "city": city,
                })
                v159_data = predict_v159_price(v159_payload)
                v159_data["traceId"] = trace_id
                write_assistant_trace({
                    "traceId": trace_id,
                    "api": "/api/price",
                    "sessionId": car_data.get("sessionId") or "",
                    "messageId": car_data.get("messageId") or "",
                    "businessIntent": car_data.get("businessIntent") or "MEDIA_PRICING",
                    "userQuery": f"{brand}{series}{model} {reg_date} {mileage}万公里 {city}",
                    "rootIntent": "valuation",
                    "workflow": "media_pricing_v159_latest_trusted_cluster",
                    "answerType": "media_pricing",
                    "modelName": v159_data.get("modelName") or "v159_latest_trusted_cluster",
                    "promptVersion": "price_v159_latest_trusted_cluster",
                    "useFinetuned": False,
                    "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                    "pricingResult": _extract_pricing_snapshot({"data": v159_data}),
                    "retrievedContext": {"refCars": compact_ref_cars(v159_data.get("ref_cars") or [])},
                    "answerPreview": v159_data.get("reason") or "v159最新可信成交簇报价完成",
                    "error": None,
                })
                return jsonify({'success': True, 'data': v159_data, 'traceId': trace_id})
            except Exception as exc:
                print(f"[v159_pricing] failed: {exc}")
                if not _env_truthy("PRICING_MODEL_FALLBACK_OLD", "1"):
                    write_assistant_trace({
                        "traceId": trace_id,
                        "api": "/api/price",
                        "sessionId": car_data.get("sessionId") or "",
                        "messageId": car_data.get("messageId") or "",
                        "businessIntent": car_data.get("businessIntent") or "MEDIA_PRICING",
                        "userQuery": f"{brand}{series}{model} {reg_date} {mileage}万公里 {city}",
                        "rootIntent": "valuation",
                        "workflow": "media_pricing_v159_latest_trusted_cluster",
                        "answerType": "media_pricing",
                        "modelName": "v159_latest_trusted_cluster",
                        "promptVersion": "price_v159_latest_trusted_cluster",
                        "useFinetuned": False,
                        "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                        "pricingResult": _extract_pricing_snapshot({}),
                        "retrievedContext": {"refCars": []},
                        "answerPreview": "v159模型加载或预测失败。",
                        "error": str(exc),
                    })
                    return jsonify({
                        'success': False,
                        'error': f'v159估价策略暂不可用：{exc}',
                        'traceId': trace_id
                    }), 503

        if active_pricing_version in {"v194", "v193_1", "v193", "v192_16", "v192_15", "v192_14", "v192_11", "v192_10", "v192_9", "v192_8", "v7_layered_2026"}:
            try:
                layered_payload = dict(car_data)
                layered_payload.update({
                    "request_id": trace_id,
                    "modelYear": vehicle_year or pricing_model_year,
                    "model_year": vehicle_year or pricing_model_year,
                    "regDate": reg_date,
                    "reg_date": reg_date,
                    "mileage": mileage,
                    "transferCount": transfer_count,
                    "transfer": transfer_count,
                    "color": color,
                    "city": city,
                })

                def lazy_legacy_predict_layered_price(payload):
                    from v7_pricing_engine import predict_layered_price

                    return predict_layered_price(payload)

                if active_pricing_version == "v194":
                    from services.v194_quote_service import (
                        quote_with_v194_service,
                    )

                    v7_data = quote_with_v194_service(
                        layered_payload,
                        lazy_legacy_predict_layered_price,
                    )
                    trace_workflow = "media_pricing_v194_production_evidence"
                    trace_model_name = (
                        v7_data.get("modelName")
                        or "v194-production-evidence-warehouse-asof-retrieval"
                    )
                    trace_prompt_version = "price_v194"
                    answer_preview = (
                        v7_data.get("reason")
                        or "v194严格历史C2B证据仓库、as-of召回和可复算证据链生成成功"
                    )
                elif active_pricing_version == "v193_1":
                    from services.v193_1_quote_service import (
                        quote_with_v1931_service,
                    )

                    v7_data = quote_with_v1931_service(
                        layered_payload,
                        lazy_legacy_predict_layered_price,
                    )
                    trace_workflow = "media_pricing_v193_1_qwen_semantic_ab"
                    trace_model_name = (
                        v7_data.get("modelName")
                        or "v193.1-qwen-plus-semantic-ab"
                    )
                    trace_prompt_version = "price_v193_1"
                    answer_preview = (
                        v7_data.get("reason")
                        or "v193.1 qwen-plus语义A/B层和Trust Gate生成成功"
                    )
                elif active_pricing_version == "v193":
                    from services.v193_quote_service import (
                        quote_with_v193_service,
                    )

                    v7_data = quote_with_v193_service(
                        layered_payload,
                        lazy_legacy_predict_layered_price,
                    )
                    trace_workflow = "media_pricing_v193_qwen_semantic"
                    trace_model_name = (
                        v7_data.get("modelName")
                        or "v193-qwen-semantic-evidence-layer"
                    )
                    trace_prompt_version = "price_v193"
                    answer_preview = (
                        v7_data.get("reason")
                        or "v193语义证据层、候选关系、Trust Gate和可解释证据卡生成成功"
                    )
                elif active_pricing_version == "v192_16":
                    from services.v192_16_quote_service import (
                        quote_with_v19216_service,
                    )

                    v7_data = quote_with_v19216_service(
                        layered_payload,
                        lazy_legacy_predict_layered_price,
                    )
                    trace_workflow = "media_pricing_v192_16"
                    trace_model_name = (
                        v7_data.get("modelName")
                        or "v192.16-confidence-calibrated-runtime"
                    )
                    trace_prompt_version = "price_v192_16"
                    answer_preview = (
                        v7_data.get("reason")
                        or "v192.16置信度校准、残差策略和真实证据链生成成功"
                    )
                elif active_pricing_version == "v192_15":
                    from services.v192_15_quote_service import (
                        quote_with_v19215_service,
                    )

                    v7_data = quote_with_v19215_service(
                        layered_payload,
                        lazy_legacy_predict_layered_price,
                    )
                    trace_workflow = "media_pricing_v192_15"
                    trace_model_name = (
                        v7_data.get("modelName")
                        or "v192.15-real-runnable-full-runtime"
                    )
                    trace_prompt_version = "price_v192_15"
                    answer_preview = (
                        v7_data.get("reason")
                        or "v192.15真实可运行全车型语义报价与证据链生成成功"
                    )
                elif active_pricing_version == "v192_14":
                    from services.v192_14_quote_service import (
                        quote_with_v19214_service,
                    )

                    v7_data = quote_with_v19214_service(
                        layered_payload,
                        lazy_legacy_predict_layered_price,
                    )
                    trace_workflow = "media_pricing_v192_14"
                    trace_model_name = (
                        v7_data.get("modelName")
                        or "v192.14-full-semantic-runtime"
                    )
                    trace_prompt_version = "price_v192_14"
                    answer_preview = (
                        v7_data.get("reason")
                        or "v192.14全车型语义报价与证据链生成成功"
                    )
                elif active_pricing_version == "v192_11":
                    from services.v192_11_quote_service import (
                        quote_with_v19211_service,
                    )

                    v7_data = quote_with_v19211_service(
                        layered_payload,
                        lazy_legacy_predict_layered_price,
                    )
                    trace_workflow = "media_pricing_v192_11"
                    trace_model_name = (
                        v7_data.get("modelName")
                        or "v192.11-real-runtime-pricing-engine"
                    )
                    trace_prompt_version = "price_v192_11"
                    answer_preview = (
                        v7_data.get("reason")
                        or "v192.11真实报价与证据链生成成功"
                    )
                elif active_pricing_version == "v192_10":
                    from services.v192_10_quote_service import (
                        quote_with_v19210_service,
                    )

                    v7_data = quote_with_v19210_service(
                        layered_payload,
                        lazy_legacy_predict_layered_price,
                    )
                    trace_workflow = "media_pricing_v192_10"
                    trace_model_name = (
                        v7_data.get("modelName")
                        or "v192.10-real-deployment-pricing-engine"
                    )
                    trace_prompt_version = "price_v192_10"
                    answer_preview = (
                        v7_data.get("reason")
                        or "v192.10真实报价与证据链生成成功"
                    )
                elif active_pricing_version == "v192_9":
                    from services.v192_9_quote_service import (
                        quote_with_v1929_service,
                    )

                    v7_data = quote_with_v1929_service(
                        layered_payload,
                        lazy_legacy_predict_layered_price,
                    )
                    trace_workflow = "media_pricing_v192_9"
                    trace_model_name = (
                        v7_data.get("modelName")
                        or "v192.9-complete-pricing-evidence-engine"
                    )
                    trace_prompt_version = "price_v192_9"
                    answer_preview = (
                        v7_data.get("reason")
                        or "v192.9完整报价与证据链生成成功"
                    )
                else:
                    from services.v192_8_quote_service import (
                        quote_with_v1928_service,
                    )

                    v7_data = quote_with_v1928_service(
                        layered_payload,
                        lazy_legacy_predict_layered_price,
                    )
                    trace_workflow = "media_pricing_v192_8"
                    trace_model_name = (
                        v7_data.get("modelName")
                        or "v192.8-complete-pricing-evidence-engine"
                    )
                    trace_prompt_version = "price_v192_8"
                    answer_preview = (
                        v7_data.get("reason")
                        or "v192.8完整报价与证据链生成成功"
                    )
                v7_data["traceId"] = trace_id

                write_assistant_trace({
                    "traceId": trace_id,
                    "api": "/api/price",
                    "sessionId": car_data.get("sessionId") or "",
                    "messageId": car_data.get("messageId") or "",
                    "businessIntent": car_data.get("businessIntent") or "MEDIA_PRICING",
                    "userQuery": f"{brand}{series}{model} {reg_date} {mileage}万公里 {city}",
                    "rootIntent": "valuation",
                    "workflow": trace_workflow,
                    "answerType": "media_pricing",
                    "modelName": trace_model_name,
                    "promptVersion": trace_prompt_version,
                    "useFinetuned": False,
                    "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                    "pricingResult": _extract_pricing_snapshot({"data": v7_data}),
                    "retrievedContext": {"refCars": compact_ref_cars(v7_data.get("ref_cars") or [])},
                    "answerPreview": answer_preview,
                    "error": None,
                })
                return jsonify({'success': True, 'data': v7_data, 'traceId': trace_id})
            except Exception as exc:
                print(f"[v192_pricing] failed: {exc}")
                if not _env_truthy("PRICING_MODEL_FALLBACK_OLD", "1"):
                    write_assistant_trace({
                        "traceId": trace_id,
                        "api": "/api/price",
                        "sessionId": car_data.get("sessionId") or "",
                        "messageId": car_data.get("messageId") or "",
                        "businessIntent": car_data.get("businessIntent") or "MEDIA_PRICING",
                        "userQuery": f"{brand}{series}{model} {reg_date} {mileage}万公里 {city}",
                        "rootIntent": "valuation",
                        "workflow": (
                            "media_pricing_v194_production_evidence"
                            if active_pricing_version == "v194"
                            else "media_pricing_v192_14"
                            if active_pricing_version == "v192_14"
                            else "media_pricing_v192_11"
                            if active_pricing_version == "v192_11"
                            else "media_pricing_v192_10"
                            if active_pricing_version == "v192_10"
                            else "media_pricing_v192_9"
                            if active_pricing_version == "v192_9"
                            else "media_pricing_v192_8"
                        ),
                        "answerType": "media_pricing",
                        "modelName": (
                            "v194-production-evidence-warehouse-asof-retrieval"
                            if active_pricing_version == "v194"
                            else "v192.14-full-semantic-runtime"
                            if active_pricing_version == "v192_14"
                            else "v192.11-real-runtime-pricing-engine"
                            if active_pricing_version == "v192_11"
                            else "v192.10-real-deployment-pricing-engine"
                            if active_pricing_version == "v192_10"
                            else "v192.9-complete-pricing-evidence-engine"
                            if active_pricing_version == "v192_9"
                            else "v192.8-complete-pricing-evidence-engine"
                        ),
                        "promptVersion": (
                            "price_v194"
                            if active_pricing_version == "v194"
                            else "price_v192_14"
                            if active_pricing_version == "v192_14"
                            else "price_v192_11"
                            if active_pricing_version == "v192_11"
                            else "price_v192_10"
                            if active_pricing_version == "v192_10"
                            else "price_v192_9"
                            if active_pricing_version == "v192_9"
                            else "price_v192_8"
                        ),
                        "useFinetuned": False,
                        "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                        "pricingResult": _extract_pricing_snapshot({}),
                        "retrievedContext": {"refCars": []},
                        "answerPreview": "v7模型加载或预测失败。",
                        "error": str(exc),
                    })
                    return jsonify({
                        'success': False,
                        'error': f'新版估价模型暂不可用：{exc}',
                        'traceId': trace_id
                    }), 503
                print("[v192_pricing] falling back to old online pricing path")

        if DEPLOY_LITE_MODE or HOSTED_FAST_PRICING:
            init_backend()
            car = RealCarListing(
                brand=brand,
                series=series,
                model=model,
                model_year=pricing_model_year,
                mileage=mileage,
                transfer_count=transfer_count,
                color=color,
                inspection_score=80.0,
                inspection_grade="B",
                c2b_price=0.0,
                b2c_price=0.0
            )
            refs = retriever.retrieve(car, top_k=5) if retriever is not None else []
            fast_data = _fast_price_from_refs(car, refs)
            if not fast_data:
                error_message = f'{brand}{series or model} 同类成交样本不足，暂不生成自动报价。请补充具体配置/年款或选择车型库标准车型。'
                write_assistant_trace({
                    "traceId": trace_id,
                    "api": "/api/price",
                    "sessionId": car_data.get("sessionId") or "",
                    "messageId": car_data.get("messageId") or "",
                    "businessIntent": car_data.get("businessIntent") or "MEDIA_PRICING",
                    "userQuery": f"{brand}{series}{model} {reg_date} {mileage}万公里 {city}",
                    "rootIntent": "valuation",
                    "workflow": "media_pricing",
                    "answerType": "media_pricing",
                    "modelName": "hosted-fast-pricing" if HOSTED_FAST_PRICING else "lite-rule",
                    "promptVersion": "price_v1",
                    "useFinetuned": False,
                    "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                    "pricingResult": _extract_pricing_snapshot({}),
                    "retrievedContext": {"refCars": compact_ref_cars(refs)},
                    "answerPreview": "同类样本不足，未生成报价。",
                    "error": error_message,
                })
                return jsonify({
                    'success': False,
                    'error': error_message,
                    'traceId': trace_id
                }), 422
            write_assistant_trace({
                "traceId": trace_id,
                "api": "/api/price",
                "sessionId": car_data.get("sessionId") or "",
                "messageId": car_data.get("messageId") or "",
                "businessIntent": car_data.get("businessIntent") or "MEDIA_PRICING",
                "userQuery": f"{brand}{series}{model} {reg_date} {mileage}万公里 {city}",
                "rootIntent": "valuation",
                "workflow": "media_pricing",
                "answerType": "media_pricing",
                "modelName": "hosted-fast-pricing" if HOSTED_FAST_PRICING else "lite-rule",
                "promptVersion": "price_v1",
                "useFinetuned": False,
                "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                "pricingResult": _extract_pricing_snapshot({"data": fast_data}),
                "retrievedContext": {"refCars": compact_ref_cars(fast_data.get("ref_cars") or refs)},
                "answerPreview": fast_data.get("reason") or "快速估价成功",
                "error": None,
            })
            return jsonify({'success': True, 'data': fast_data, 'traceId': trace_id})

        init_backend()

        # 上次定价数据（用于参数修改时的单调性约束）
        previous_b2c = car_data.get('previous_b2c_price')   # float or None
        previous_mileage = car_data.get('previous_mileage') # float or None
        previous_transfer = car_data.get('previous_transfer') # int or None
        previous_model_year = car_data.get('previous_model_year') # int or None

        # 计算车龄
        current_year = datetime.now().year
        car_age = current_year - pricing_model_year
        
        # 使用默认评分（仅为了兼容RealCarListing结构）
        inspection_score = 80.0
        
        car = RealCarListing(
            brand=brand,
            series=series,
            model=model,
            model_year=pricing_model_year,
            mileage=mileage,
            transfer_count=transfer_count,
            color=color,
            inspection_score=inspection_score,
            inspection_grade="B",
            c2b_price=0.0,
            b2c_price=0.0
        )
        
        result = price_car_react(
            car,
            retriever,
            max_steps=1,
            use_qwen_direct=False,
            use_self_reflection=False,
            use_qwen_as_baseline=True,
            verbose=True,
            previous_mileage=float(previous_mileage) if previous_mileage is not None else None,
            previous_transfer=int(previous_transfer) if previous_transfer is not None else None,
            previous_b2c=float(previous_b2c) if previous_b2c is not None else None,
        )
        
        # 参数修改单调性约束：条件改善→价格不能下降，条件变差→价格不能上升
        if previous_b2c and previous_b2c > 0:
            def _simple_score(ml, tr, my):
                current_year = datetime.now().year
                age_year = _safe_year(my) or max(2000, current_year - 6)
                age = current_year - age_year
                ml_score = max(0.0, 100 - (float(ml) / 20) * 100)
                age_score = max(0.0, 100 - (age / 15) * 100)
                tr_score = max(0.0, 100 - (float(tr) / 5) * 100)
                return ml_score * 0.5 + age_score * 0.35 + tr_score * 0.15

            new_score = _simple_score(mileage, transfer_count, model_year)
            if previous_mileage is not None and previous_transfer is not None:
                prev_score = _simple_score(
                    previous_mileage, previous_transfer,
                    previous_model_year if previous_model_year else model_year
                )
                score_diff = new_score - prev_score
                print(f"[单调性] 车况分 旧={prev_score:.1f} → 新={new_score:.1f}，差={score_diff:+.1f}")
                print(f"[单调性] 价格 旧B2C={previous_b2c:.2f}万 → 新B2C={result.b2c_price:.2f}万")

                # 每1分车况差异对应约0.5%的价格变化，最小变动0.3%
                adj_ratio = max(abs(score_diff) * 0.005, 0.003)

                adjusted = False
                if score_diff > 0.5:
                    min_new_price = round(previous_b2c * (1 + adj_ratio), 2)
                    if result.b2c_price < min_new_price:
                        print(f"[单调性] ⚠️ 车况变好(+{score_diff:.1f}分)，价格须上涨：{result.b2c_price:.2f} → {min_new_price:.2f}")
                        result.b2c_price = min_new_price
                        result.c2b_price = round(min_new_price / 1.08, 2)
                        adjusted = True
                elif score_diff < -0.5:
                    max_new_price = round(previous_b2c * (1 - adj_ratio), 2)
                    if result.b2c_price > max_new_price:
                        print(f"[单调性] ⚠️ 车况变差({score_diff:.1f}分)，价格须下降：{result.b2c_price:.2f} → {max_new_price:.2f}")
                        result.b2c_price = max_new_price
                        result.c2b_price = round(max_new_price / 1.08, 2)
                        adjusted = True

                # 同步更新 pricing_reason 里的最终定价区块
                if adjusted and hasattr(result, 'pricing_reason') and result.pricing_reason:
                    import re as _re
                    result.pricing_reason = _re.sub(
                        r'### 🎯 最终定价[\s\S]*',
                        f'### 🎯 最终定价\n- **B2C售价：{result.b2c_price:.2f}万**\n'
                        f'- **C2B收车价：{result.c2b_price:.2f}万**\n'
                        f'- ⚠️ **参数修改单调性修正**：车况变化{score_diff:+.1f}分，价格已同步调整',
                        result.pricing_reason
                    )

        # 从react结果中获取更多信息
        ref_count = 0
        avg_ref_score = 0
        ref_b2c_mean = 0
        ref_cars = []  # 参考车源详情列表

        if hasattr(result, 'raw_steps') and result.raw_steps:
            if 'refs' in result.raw_steps:
                refs = result.raw_steps['refs']
                ref_count = len(refs)
                if ref_count > 0:
                    valid_refs = [r[0] for r in refs if hasattr(r[0], 'b2c_price') and r[0].b2c_price]
                    avg_ref_score = sum(r.inspection_score for r in valid_refs if hasattr(r, 'inspection_score')) / max(len(valid_refs), 1)
                    ref_b2c_mean = sum(r.b2c_price for r in valid_refs) / max(len(valid_refs), 1)
                    for r in valid_refs:
                        ref_cars.append({
                            'brand': getattr(r, 'brand', ''),
                            'series': getattr(r, 'series', ''),
                            'model_year': getattr(r, 'model_year', ''),
                            'mileage': getattr(r, 'mileage', 0),
                            'transfer_count': getattr(r, 'transfer_count', 0),
                            'b2c_price': getattr(r, 'b2c_price', 0),
                            'c2b_price': getattr(r, 'c2b_price', 0),
                            'inspection_score': getattr(r, 'inspection_score', 0),
                        })

        if ref_count < 3:
            error_message = f'{brand}{series} 同类成交样本不足，暂不生成自动报价。请补充具体配置/年款或转人工复核。'
            write_assistant_trace({
                "traceId": trace_id,
                "api": "/api/price",
                "sessionId": car_data.get("sessionId") or "",
                "messageId": car_data.get("messageId") or "",
                "businessIntent": car_data.get("businessIntent") or "MEDIA_PRICING",
                "userQuery": f"{brand}{series}{model} {reg_date} {mileage}万公里 {city}",
                "rootIntent": "valuation",
                "workflow": "media_pricing",
                "answerType": "media_pricing",
                "modelName": "Qwen2.5-3B-LoRA",
                "promptVersion": "price_v1",
                "useFinetuned": True,
                "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                "pricingResult": _extract_pricing_snapshot({}),
                "retrievedContext": {"refCars": compact_ref_cars(ref_cars)},
                "answerPreview": "参考样本不足，未生成报价。",
                "error": error_message,
            })
            return jsonify({
                'success': False,
                'error': error_message,
                'traceId': trace_id
            }), 422
        
        # 生成车辆状态描述
        condition_desc = ""
        if car_age <= 3 and mileage <= 5 and transfer_count <= 1:
            condition_desc = "车辆状态优秀，市场竞争力强"
        elif car_age <= 5 and mileage <= 8 and transfer_count <= 2:
            condition_desc = "车辆状态良好，市场表现稳定"
        elif car_age <= 8 and mileage <= 15 and transfer_count <= 3:
            condition_desc = "车辆状态一般，需要适当调整定价"
        else:
            condition_desc = "车况风险较高，建议人工复核后再确定报价"
        
        data = {
            'c2bPrice': result.c2b_price,
            'b2cPrice': result.b2c_price,
            'reason': result.pricing_reason,
            'c2b_low': result.c2b_price * 0.95,
            'c2b_high': result.c2b_price * 1.05,
            'b2c_low': result.b2c_price * 0.95,
            'b2c_high': result.b2c_price * 1.05,
            'condition_desc': condition_desc,
            'ref_count': ref_count,
            'ref_b2c_mean': ref_b2c_mean,
            'ref_cars': ref_cars,
        }
        
        response = {
            'success': True,
            'data': data,
            'traceId': trace_id
        }
        write_assistant_trace({
            "traceId": trace_id,
            "api": "/api/price",
            "sessionId": car_data.get("sessionId") or "",
            "messageId": car_data.get("messageId") or "",
            "businessIntent": car_data.get("businessIntent") or "MEDIA_PRICING",
            "userQuery": f"{brand}{series}{model} {reg_date} {mileage}万公里 {city}",
            "rootIntent": "valuation",
            "workflow": "media_pricing",
            "answerType": "media_pricing",
            "modelName": "Qwen2.5-3B-LoRA",
            "promptVersion": "price_v1",
            "useFinetuned": True,
            "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
            "pricingResult": _extract_pricing_snapshot({"data": data}),
            "retrievedContext": {"refCars": compact_ref_cars(ref_cars)},
            "answerPreview": data.get("reason") or data.get("condition_desc") or "估价成功",
            "error": None,
        })
        
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ 定价失败: {e}")
        import traceback
        traceback.print_exc()
        write_assistant_trace({
            "traceId": trace_id,
            "api": "/api/price",
            "sessionId": (car_data or {}).get("sessionId") or "",
            "messageId": (car_data or {}).get("messageId") or "",
            "businessIntent": (car_data or {}).get("businessIntent") or "MEDIA_PRICING",
            "userQuery": car_data,
            "rootIntent": "valuation",
            "workflow": "media_pricing",
            "answerType": "media_pricing",
            "modelName": "Qwen2.5-3B-LoRA" if not (DEPLOY_LITE_MODE or HOSTED_FAST_PRICING) else "lite-rule",
            "promptVersion": "price_v1",
            "useFinetuned": not (DEPLOY_LITE_MODE or HOSTED_FAST_PRICING),
            "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
            "pricingResult": _extract_pricing_snapshot({}),
            "retrievedContext": {"refCars": []},
            "answerPreview": "",
            "error": str(e),
        })
        
        return jsonify({
            'success': False,
            'error': str(e),
            'traceId': trace_id
        }), 500


@app.route('/api/price-v2', methods=['POST'])
def get_price_v2():
    """Pricing Model V2 实验接口。

    该接口用于并行验证新底层估价模型，不替换现有 /api/price。
    如果模型包或依赖缺失，直接返回明确错误，避免静默回退到旧规则或 mock。
    """
    trace_id = generate_trace_id()
    started_at = datetime.utcnow()
    payload = request.json or {}
    try:
        from pricing_model_v2.inference import predict_price

        result = predict_price(payload)
        data = {
            "c2bPrice": result.get("c2bPrice"),
            "b2cPrice": result.get("b2cPrice"),
            "c2b_low": (result.get("c2bRange") or [None, None])[0],
            "c2b_high": (result.get("c2bRange") or [None, None])[1],
            "b2c_low": (result.get("b2cRange") or [None, None])[0],
            "b2c_high": (result.get("b2cRange") or [None, None])[1],
            "confidence": result.get("confidence"),
            "needHumanReview": result.get("needHumanReview"),
            "humanReviewReasons": result.get("humanReviewReasons") or [],
            "modelVersion": result.get("modelVersion"),
            "featureVersion": result.get("featureVersion"),
            "calibrationVersion": result.get("calibrationVersion"),
            "pricingEngineVersion": result.get("pricingEngineVersion"),
            "inferenceModel": result.get("inferenceModel"),
        }
        write_assistant_trace({
            "traceId": trace_id,
            "api": "/api/price-v2",
            "sessionId": payload.get("sessionId") or "",
            "messageId": payload.get("messageId") or "",
            "businessIntent": payload.get("businessIntent") or "MEDIA_PRICING",
            "userQuery": payload,
            "rootIntent": "valuation",
            "workflow": "media_pricing_v2",
            "answerType": "media_pricing",
            "modelName": result.get("modelVersion") or "pricing_model_v2",
            "promptVersion": "price_v2",
            "useFinetuned": False,
            "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
            "pricingResult": _extract_pricing_snapshot({"data": data}),
            "retrievedContext": {"refCars": []},
            "answerPreview": f"C2B {data.get('c2bPrice')}万，B2C {data.get('b2cPrice')}万",
            "error": None,
        })
        return jsonify({"success": True, "data": data, "raw": result, "traceId": trace_id})
    except Exception as e:
        write_assistant_trace({
            "traceId": trace_id,
            "api": "/api/price-v2",
            "sessionId": payload.get("sessionId") or "",
            "messageId": payload.get("messageId") or "",
            "businessIntent": payload.get("businessIntent") or "MEDIA_PRICING",
            "userQuery": payload,
            "rootIntent": "valuation",
            "workflow": "media_pricing_v2",
            "answerType": "media_pricing",
            "modelName": "pricing_model_v2",
            "promptVersion": "price_v2",
            "useFinetuned": False,
            "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
            "pricingResult": _extract_pricing_snapshot({}),
            "retrievedContext": {"refCars": []},
            "answerPreview": "",
            "error": str(e),
        })
        return jsonify({
            "success": False,
            "error": f"Pricing Model V2 推理失败：{e}",
            "traceId": trace_id,
        }), 500


@app.route('/api/vehicle-catalog/normalize', methods=['POST'])
def normalize_vehicle_model_api():
    """车型库标准化匹配接口。"""
    try:
        from v7_pricing_engine import normalize_vehicle

        payload = request.json or {}
        result = normalize_vehicle(payload)
        return jsonify({
            "success": True,
            "data": {
                "standard_vehicle": {
                    "brand_id": result.get("brand_id", ""),
                    "brand_name": result.get("brand_name", ""),
                    "series_id": result.get("series_id", ""),
                    "series_name": result.get("series_name", ""),
                    "model_id": result.get("model_id", ""),
                    "model_name": result.get("model_name", ""),
                    "model_year": result.get("model_year"),
                    "match_confidence": result.get("match_confidence", 0.0),
                    "match_method": result.get("match_method", ""),
                    "match_reason": result.get("match_reason", ""),
                    "need_manual_confirm": result.get("need_manual_confirm", True),
                    "candidates": result.get("candidates", [])
                }
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"车型标准化失败: {str(e)}"
        }), 500


def _interaction_active_pricing_callable(payload):
    """Call the active production pricing engine for interaction turns.

    The chat flow must not use the legacy v7 engine as its first-class path,
    otherwise the report/evidence card diverges from /api/price.
    """
    layered_payload = dict(payload or {})
    layered_payload.setdefault("request_id", generate_trace_id())
    active_pricing_version = _active_pricing_model_version()

    def lazy_legacy_predict_layered_price(inner_payload):
        from v7_pricing_engine import predict_layered_price

        return predict_layered_price(inner_payload)

    if active_pricing_version == "v194":
        from services.v194_quote_service import quote_with_v194_service

        return quote_with_v194_service(layered_payload, lazy_legacy_predict_layered_price)
    if active_pricing_version == "v193_1":
        from services.v193_1_quote_service import quote_with_v1931_service

        return quote_with_v1931_service(layered_payload, lazy_legacy_predict_layered_price)
    if active_pricing_version == "v193":
        from services.v193_quote_service import quote_with_v193_service

        return quote_with_v193_service(layered_payload, lazy_legacy_predict_layered_price)
    if active_pricing_version == "v192_16":
        from services.v192_16_quote_service import quote_with_v19216_service

        return quote_with_v19216_service(layered_payload, lazy_legacy_predict_layered_price)
    if active_pricing_version == "v192_15":
        from services.v192_15_quote_service import quote_with_v19215_service

        return quote_with_v19215_service(layered_payload, lazy_legacy_predict_layered_price)
    if active_pricing_version == "v192_14":
        from services.v192_14_quote_service import quote_with_v19214_service

        return quote_with_v19214_service(layered_payload, lazy_legacy_predict_layered_price)
    if active_pricing_version == "v192_11":
        from services.v192_11_quote_service import quote_with_v19211_service

        return quote_with_v19211_service(layered_payload, lazy_legacy_predict_layered_price)
    if active_pricing_version == "v192_10":
        from services.v192_10_quote_service import quote_with_v19210_service

        return quote_with_v19210_service(layered_payload, lazy_legacy_predict_layered_price)
    if active_pricing_version == "v192_9":
        from services.v192_9_quote_service import quote_with_v1929_service

        return quote_with_v1929_service(layered_payload, lazy_legacy_predict_layered_price)
    if active_pricing_version == "v192_8":
        from services.v192_8_quote_service import quote_with_v1928_service

        return quote_with_v1928_service(layered_payload, lazy_legacy_predict_layered_price)
    return lazy_legacy_predict_layered_price(layered_payload)


_INTERACTION_SERVICE_SINGLETON = None
_INTERACTION_SERVICE_LOCK = threading.Lock()


def _get_interaction_service():
    global _INTERACTION_SERVICE_SINGLETON
    if _INTERACTION_SERVICE_SINGLETON is None:
        with _INTERACTION_SERVICE_LOCK:
            if _INTERACTION_SERVICE_SINGLETON is None:
                from services.interaction_service import InteractionService

                _INTERACTION_SERVICE_SINGLETON = InteractionService(
                    pricing_callable=_interaction_active_pricing_callable
                )
    return _INTERACTION_SERVICE_SINGLETON


def _record_internal_interaction(payload: dict, result: dict, username: str) -> None:
    """Persist the exact question, prior context and grounded answer for later feedback."""
    from services.internal_feedback_store import get_internal_feedback_store

    nested_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    module = (
        nested_payload.get("ui_module")
        or payload.get("module")
        or payload.get("selectedBusinessModule")
        or result.get("module")
        or "unknown"
    )
    request_context = {
        "selected_city": payload.get("selected_city"),
        "module": module,
        "filters": nested_payload,
        "client_state": payload.get("client_state") or {},
    }
    response_context = {
        "reply": result.get("reply") or {"text": result.get("text")},
        "intent": result.get("intent_v2") or result.get("intent") or {},
        "task_plan": result.get("task_plan") or {},
        "task_execution": result.get("task_execution") or [],
        "final_result": result.get("final_result") or {},
        "pricing": result.get("pricing") or {},
        "market_agent_card": result.get("market_agent_card") or {},
        "selection_result": result.get("selection_result") or {},
    }
    get_internal_feedback_store().record_interaction(
        # The stream task id is the id rendered by the UI. Persist feedback
        # against that exact id even when an upstream workflow emits another id.
        turn_id=str(payload.get("_stream_task_id") or result.get("turn_id") or result.get("task_id") or ""),
        session_id=str(result.get("session_id") or payload.get("session_id") or payload.get("sessionId") or ""),
        username=username,
        module=str(module),
        user_question=str(payload.get("message") or ""),
        request_context=request_context,
        response_context=response_context,
        release_version=os.environ.get("APP_RELEASE_VERSION") or _active_pricing_model_version(),
    )


@app.route('/api/internal-feedback', methods=['POST'])
def internal_feedback_submit():
    try:
        from services.internal_feedback_store import get_internal_feedback_store

        payload = request.get_json(silent=True) or {}
        result = get_internal_feedback_store().add_feedback(
            turn_id=str(payload.get("turn_id") or ""),
            username=_current_internal_username(),
            rating=int(payload.get("rating", 0)),
            comment=str(payload.get("comment") or ""),
            tags=payload.get("tags") or [],
            simulation_run_id=str(payload.get("simulation_run_id") or ""),
        )
        return jsonify({"success": True, "data": result})
    except KeyError:
        return jsonify({"success": False, "error": "找不到本次任务，请刷新后重新提交反馈"}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"feedback_submit_failed: {exc}"}), 500


@app.route('/api/internal-feedback/stats', methods=['GET'])
def internal_feedback_stats():
    from services.internal_feedback_store import get_internal_feedback_store

    return jsonify({"success": True, "data": get_internal_feedback_store().stats()})


@app.route('/api/internal-feedback/records', methods=['GET'])
def internal_feedback_records():
    from services.internal_feedback_store import get_internal_feedback_store

    rating_arg = request.args.get("rating")
    data = get_internal_feedback_store().records(
        limit=int(request.args.get("limit") or 100),
        offset=int(request.args.get("offset") or 0),
        module=str(request.args.get("module") or ""),
        rating=int(rating_arg) if rating_arg not in (None, "") else None,
        simulation_run_id=str(request.args.get("simulation_run_id") or ""),
    )
    return jsonify({"success": True, "data": data})


@app.route('/api/internal-feedback/export.csv', methods=['GET'])
def internal_feedback_export():
    from services.internal_feedback_store import get_internal_feedback_store

    csv_text = get_internal_feedback_store().export_csv()
    return Response(
        "\ufeff" + csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=AI_dongchejia_feedback.csv"},
    )


@app.route('/api/interaction/turn', methods=['POST'])
def interaction_turn():
    """Unified backend-owned AI interaction turn.

    New default entry for intent recognition, slot extraction, quick tags,
    pricing request construction and grounded replies.  The route keeps
    /api/price unchanged and calls the same v7 pricing engine only after the
    builder verifies required fields.
    """
    try:
        payload = request.json or {}
        from services.interaction_service import _json_safe_snapshot

        service = _get_interaction_service()
        result = service.process_turn(payload)
        safe_result = _json_safe_snapshot(result)
        _record_internal_interaction(payload, safe_result, _current_internal_username())
        return jsonify({"success": True, "data": safe_result, "traceId": safe_result.get("turn_id")})
    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": f"interaction_turn_failed: {exc}",
                "debug": {"fallback_used": True, "fallback_reason": str(exc)},
            }
        ), 500


@app.route('/api/interaction/turn/stream', methods=['POST'])
def interaction_turn_stream():
    """Stream real Agent lifecycle events as NDJSON.

    Business execution runs once in a worker thread.  The HTTP response flushes
    intent, backend-owned planning and actual tool start/completion events while
    that same turn is executing; the authoritative full result is emitted last.
    """

    payload = dict(request.json or {})
    task_id = str(payload.get("_stream_task_id") or uuid.uuid4())
    payload["_stream_task_id"] = task_id
    request_username = _current_internal_username()
    events: "queue.Queue[dict | object]" = queue.Queue()
    finished = object()

    def publish(event):
        if isinstance(event, dict):
            events.put(event)

    def run_turn():
        try:
            from services.interaction_service import _json_safe_snapshot

            service = _get_interaction_service()
            result = service.process_turn(payload, event_sink=publish)
            safe_result = _json_safe_snapshot(result)
            _record_internal_interaction(payload, safe_result, request_username)
            events.put(
                {
                    "event_type": "turn.completed",
                    "task_id": task_id,
                    "module": (payload.get("payload") or {}).get("ui_module") or payload.get("module"),
                    "at": datetime.now().isoformat(timespec="milliseconds"),
                    "response": safe_result,
                }
            )
        except Exception as exc:
            events.put(
                {
                    "event_type": "turn.failed",
                    "task_id": task_id,
                    "at": datetime.now().isoformat(timespec="milliseconds"),
                    "error": f"interaction_turn_failed: {exc}",
                }
            )
        finally:
            events.put(finished)

    def generate():
        sequence = 0

        def line(event):
            nonlocal sequence
            sequence += 1
            body = {"sequence": sequence, **event}
            return json.dumps(body, ensure_ascii=False, allow_nan=False, default=str) + "\n"

        yield line(
            {
                "event_type": "turn.accepted",
                "task_id": task_id,
                "module": (payload.get("payload") or {}).get("ui_module") or payload.get("module"),
                "at": datetime.now().isoformat(timespec="milliseconds"),
                "agent_intro": "收到请求，正在识别业务意图。",
            }
        )
        worker = threading.Thread(target=run_turn, name=f"agent-turn-{task_id[:8]}", daemon=True)
        worker.start()
        while True:
            try:
                event = events.get(timeout=12)
            except queue.Empty:
                yield line(
                    {
                        "event_type": "heartbeat",
                        "task_id": task_id,
                        "at": datetime.now().isoformat(timespec="milliseconds"),
                    }
                )
                continue
            if event is finished:
                break
            yield line(event)

    response = Response(stream_with_context(generate()), mimetype="application/x-ndjson")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@app.route('/api/reports/selection.xlsx', methods=['POST'])
def export_selection_excel_report():
    """Export the current grounded selection result as an auditable workbook."""
    try:
        from services.agent_excel_report_service import build_selection_report

        output, filename = build_selection_report(request.json or {})
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            max_age=0,
        )
    except Exception as exc:
        return jsonify({"success": False, "error": f"selection_report_export_failed: {exc}"}), 500


@app.route('/api/reports/pricing.xlsx', methods=['POST'])
def export_pricing_excel_report():
    """Export the current pricing decision, price ladder and evidence as XLSX."""
    try:
        from services.agent_excel_report_service import build_pricing_report

        output, filename = build_pricing_report(request.json or {})
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            max_age=0,
        )
    except Exception as exc:
        return jsonify({"success": False, "error": f"pricing_report_export_failed: {exc}"}), 500


@app.route('/api/reports/pricing.pdf', methods=['POST'])
def export_pricing_pdf_report():
    """Export the current pricing decision, evidence and profit calculation as PDF."""
    try:
        from services.pricing_pdf_report_service import build_pricing_pdf_report

        output, filename = build_pricing_pdf_report(request.json or {})
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf',
            max_age=0,
        )
    except Exception as exc:
        return jsonify({"success": False, "error": f"pricing_report_pdf_export_failed: {exc}"}), 500


@app.route('/api/intent/v2', methods=['POST'])
def intent_v2_classify():
    """Debuggable deterministic intent endpoint shared by all three modules."""
    try:
        payload = request.json or {}
        from services.enterprise_agent_graph_v2 import EnterpriseAgentGraphV2

        selected_module = (
            payload.get("selectedBusinessModule")
            or payload.get("module")
            or "media_pricing"
        )
        client_state = payload.get("client_state") or {}
        preflight = EnterpriseAgentGraphV2().run_preflight(
            message=payload.get("message") or "",
            selected_module=selected_module,
            client_state=client_state,
            session_id=payload.get("session_id") or payload.get("sessionId") or "intent-v2-debug",
        )
        return jsonify(
            {
                "success": True,
                "data": preflight["intent_result"],
                "guard": preflight["guarded_result"],
                "enterprise_agent_graph": preflight,
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": f"intent_v2_failed: {exc}"}), 500


@app.route('/api/agent/graph/spec', methods=['GET'])
def agent_graph_spec():
    """Expose the production Agent graph contract for audits and frontend QA."""
    try:
        from services.enterprise_agent_graph_v2 import GRAPH_VERSION

        return jsonify(
            {
                "success": True,
                "data": {
                    "graph_version": GRAPH_VERSION,
                    "framework": "LangGraph StateGraph + MemorySaver checkpoint",
                    "nodes": [
                        "normalize_context",
                        "classify_intent",
                        "guard_module",
                        "build_task_contract",
                        "build_tool_plan",
                        "validate_state_policy",
                    ],
                    "modules": ["daily_report", "market_state", "media_pricing"],
                    "tool_boundaries": {
                        "pricing_tool": "只允许 media_pricing + pricing_quote + 字段完整时调用",
                        "daily_report_tool": "只允许 daily_report 模块调用，禁止触发估价",
                        "market_state_tool": "只允许 market_state 模块调用，禁止触发估价",
                        "price_explanation": "只读取 quote_id/current_pricing_result，不重新估价",
                    },
                    "state_contracts": [
                        "裸品牌/新车源不能继承上一辆车的车系、年款、价格",
                        "日报/行情/调价任务不得覆盖 current_pricing_result",
                        "价格解释和候选证据必须引用当前或显式历史报价",
                        "前端和未来App只消费统一Agent API，不嵌入业务定价逻辑",
                    ],
                    "client_contract": {
                        "web": "React/TypeScript compatible",
                        "mobile_app": "same Agent API, same task_contract/tool_plan/evidence_card",
                        "business_logic_location": "backend_agent_and_pricing_services",
                    },
                },
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": f"agent_graph_spec_failed: {exc}"}), 500


@app.route('/api/market-state/opportunities', methods=['POST'])
def market_state_opportunities():
    """Deterministic city-series market opportunity endpoint."""
    try:
        payload = request.json or {}
        from services.market_opportunity_service import build_market_opportunity_response

        result = build_market_opportunity_response(
            query_text=payload.get("query_text") or payload.get("message") or "",
            selected_city=payload.get("selected_city") or payload.get("city") or "全国",
            client_state=payload.get("client_state") or {},
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": f"market_state_opportunities_failed: {exc}",
            }
        ), 500


@app.route('/api/selection/analyze', methods=['POST'])
def selection_analyze():
    """Selection module endpoint backed by safe city-series market data."""
    try:
        payload = request.json or {}
        from services.selection_strategy_service import build_selection_strategy_response

        result = build_selection_strategy_response(
            query_text=payload.get("query_text") or payload.get("message") or "",
            selected_city=payload.get("selected_city") or payload.get("city") or "全国",
            client_state=payload.get("client_state") or {},
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return jsonify({"success": False, "error": f"selection_analyze_failed: {exc}"}), 500


@app.route('/api/selection/strategy-ablation/report', methods=['GET', 'POST'])
def selection_strategy_ablation_report():
    """Internal strategy lab endpoint; not shown in the field selection card."""
    try:
        force = False
        if request.method == "POST":
            payload = request.json or {}
            force = bool(payload.get("force"))
        else:
            force = str(request.args.get("force") or "").strip().lower() in {"1", "true", "yes"}
        from services.selection_analyze_service import get_selection_strategy_lab_report

        return jsonify({"success": True, "data": get_selection_strategy_lab_report(force=force)})
    except Exception as exc:
        return jsonify({"success": False, "error": f"selection_strategy_ablation_report_failed: {exc}"}), 500


@app.route('/api/market/analyze', methods=['POST'])
def market_analyze():
    """Market report endpoint backed by safe model-year / city-series data."""
    try:
        payload = request.json or {}
        from services.market_report_service import build_market_report_response

        result = build_market_report_response(
            query_text=payload.get("query_text") or payload.get("message") or "",
            selected_city=payload.get("selected_city") or payload.get("city") or "全国",
            client_state=payload.get("client_state") or {},
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return jsonify({"success": False, "error": f"market_analyze_failed: {exc}"}), 500


@app.route('/api/market-state/cities', methods=['GET'])
def market_state_cities():
    """Expose only cities present in the calibrated city-series dataset."""
    from services.business_market_workbook_loader import get_business_market_loader

    loader = get_business_market_loader()
    return jsonify(
        {
            "success": True,
            "cities": loader.cities,
            "available": loader.available,
            "source": loader.metadata.get("source_file"),
        }
    )


@app.route('/api/workbench/status-summary', methods=['GET'])
def workbench_status_summary():
    """Small deterministic status payload for the premium Agent workbench."""
    root = Path(_project_root())
    ranking_dir = root / "data/external/dongchedi_rankings/current"
    ranking_manifest = ranking_dir / "crawl_manifest.json"
    ranking_signals = ranking_dir / "normalized_ranking_signals.csv"
    ranking_jobs = ranking_dir / "crawl_jobs.json"
    ranking_summary = {
        "available": ranking_signals.exists(),
        "signal_rows": _count_csv_rows(ranking_signals),
        "completed_jobs": 0,
        "total_jobs": 0,
        "source_file": str(ranking_signals),
        "updated_at": _file_updated_at(ranking_signals),
    }
    try:
        if ranking_manifest.exists():
            manifest = json.loads(ranking_manifest.read_text(encoding="utf-8"))
            jobs = manifest.get("jobs") if isinstance(manifest, dict) else {}
            if isinstance(jobs, dict):
                ranking_summary["completed_jobs"] = sum(
                    1 for item in jobs.values()
                    if isinstance(item, dict) and item.get("status") == "success"
                )
            ranking_summary["updated_at"] = manifest.get("updated_at") or ranking_summary["updated_at"]
        if ranking_jobs.exists():
            job_payload = json.loads(ranking_jobs.read_text(encoding="utf-8"))
            if isinstance(job_payload, list):
                ranking_summary["total_jobs"] = len(job_payload)
    except Exception:
        pass

    try:
        from services.business_market_workbook_loader import get_business_market_loader

        loader = get_business_market_loader()
        market_summary = {
            "available": loader.available,
            "source_file": loader.metadata.get("source_file"),
            "city_series_row_count": loader.metadata.get("city_series_row_count"),
            "model_year_row_count": loader.metadata.get("model_year_row_count"),
            "city_count": loader.metadata.get("city_count"),
            "series_count": loader.metadata.get("series_count"),
            "online_safe": loader.metadata.get("online_safe"),
        }
    except Exception as exc:
        market_summary = {"available": False, "error": str(exc)}

    try:
        from services.dongchedi_official_photo_service import get_dongchedi_official_photo_service

        photos_summary = get_dongchedi_official_photo_service().summary()
    except Exception as exc:
        photos_summary = {"available": False, "error": str(exc)}

    try:
        daily_summary = _build_daily_report_summary(root)
    except Exception as exc:
        daily_summary = {"available": False, "error": str(exc)}

    try:
        from services.llm_client import Qwen3LocalClient

        llm_snapshot = Qwen3LocalClient().config_snapshot()
        llm_summary = {
            "provider": llm_snapshot.get("provider"),
            "model": llm_snapshot.get("model"),
            "fallback_model": llm_snapshot.get("fallback_model"),
            "free_only": llm_snapshot.get("free_only"),
            "api_key_configured": llm_snapshot.get("api_key_configured"),
        }
    except Exception as exc:
        llm_summary = {"api_key_configured": False, "error": str(exc)}

    return jsonify(
        {
            "success": True,
            "data": {
                "updated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                "market": market_summary,
                "ranking": ranking_summary,
                "photos": photos_summary,
                "daily_report": daily_summary,
                "llm": llm_summary,
            },
        }
    )


@app.route('/api/vehicle/photo', methods=['GET'])
def vehicle_photo_lookup():
    """Lookup an official DCD cover photo by brand/series without crawling."""
    brand = request.args.get("brand") or ""
    series = request.args.get("series") or request.args.get("series_name") or ""
    try:
        from services.dongchedi_official_photo_service import get_dongchedi_official_photo_service

        photo = get_dongchedi_official_photo_service().find_series_photo(brand=brand, series=series)
        return jsonify({"success": True, "data": photo or {}, "available": bool(photo)})
    except Exception as exc:
        return jsonify({"success": False, "error": f"vehicle_photo_lookup_failed: {exc}"}), 500


@app.route('/api/vehicle/photo-proxy', methods=['GET'])
def vehicle_photo_proxy():
    """Proxy and cache DCD official vehicle images so the UI does not depend on hotlink rendering."""
    url = urllib.parse.unquote((request.args.get("url") or "").strip())
    parsed = urllib.parse.urlparse(url)
    allowed_hosts = {"p3-dcd.byteimg.com", "p9-dcd.byteimg.com"}
    if parsed.scheme != "https" or parsed.netloc not in allowed_hosts:
        return jsonify({"success": False, "error": "unsupported_photo_url"}), 400
    cache_dir = Path(APP_ROOT) / "data/external/dongchedi_official_photos/current/image_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.jpg"
    if not cache_path.exists() or cache_path.stat().st_size <= 0:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                "Referer": "https://www.dongchedi.com/",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                if not str(content_type).lower().startswith("image/"):
                    return jsonify({"success": False, "error": "photo_response_not_image"}), 502
                data = resp.read(4_000_000)
            if not data:
                return jsonify({"success": False, "error": "empty_photo_response"}), 502
            tmp_path = cache_path.with_suffix(".tmp")
            tmp_path.write_bytes(data)
            tmp_path.replace(cache_path)
        except Exception as exc:
            return jsonify({"success": False, "error": f"photo_proxy_fetch_failed: {exc}"}), 502
    return send_file(cache_path, mimetype="image/jpeg", max_age=86400)


def _count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as handle:
        return max(0, sum(1 for _ in handle) - 1)


def _file_updated_at(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime, timezone(timedelta(hours=8))).isoformat()


def _build_daily_report_summary(root: Path) -> dict:
    rows: dict[str, dict] = {}
    for directory in (root / "outputs", root / "uploaded_reports"):
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            filename = path.name[:-4] if path.name.endswith(".b64") else path.name
            if not filename.startswith("daily_report_"):
                continue
            if not filename.lower().endswith((".pdf", ".html", ".md", ".xlsx")):
                continue
            date_match = re.search(r"(\d{4}-\d{2}-\d{2}|yesterday)", filename)
            report_date = date_match.group(1) if date_match else "unknown"
            rows.setdefault(report_date, {"date": report_date, "updated_at": _file_updated_at(path)})
    reports = sorted(rows.values(), key=lambda item: item["date"], reverse=True)
    latest = reports[0] if reports else {}
    return {
        "available": bool(reports),
        "latest_date": latest.get("date"),
        "report_count": len(reports),
        "updated_at": latest.get("updated_at"),
    }


@app.route('/api/chat', methods=['POST'])
def chat():
    """二手车定价相关问答API端点"""
    trace_id = generate_trace_id()
    started_at = datetime.utcnow()
    chat_data = {}
    message = ""
    pricing_context = {}
    try:
        chat_data = request.json or {}
        message = chat_data.get('message', '').strip()
        pricing_context = chat_data.get('pricingContext', {})
        session_id = chat_data.get("sessionId") or ""
        message_id = chat_data.get("messageId") or ""
        business_intent = chat_data.get("businessIntent") or ""

        def _chat_response(answer, root_intent="chat", diag_sub_intent="", workflow="fallback_chat", status_code=200, success=True, error=None, model_name=None, use_finetuned=False):
            data = {"answer": answer, "traceId": trace_id}
            trace_pricing_context = pricing_context.get("pricingResult") if isinstance(pricing_context, dict) else {}
            trace_ref_cars = (trace_pricing_context or {}).get("ref_cars") or []
            write_assistant_trace({
                "traceId": trace_id,
                "api": "/api/chat",
                "sessionId": session_id,
                "messageId": message_id,
                "userQuery": message,
                "businessIntent": business_intent,
                "rootIntent": root_intent,
                "diagSubIntent": diag_sub_intent,
                "workflow": workflow,
                "answerType": "chat",
                "modelName": model_name or ("lite-rule" if DEPLOY_LITE_MODE else "Qwen2.5-chat"),
                "promptVersion": "chat_v1",
                "useFinetuned": use_finetuned,
                "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                "pricingResult": _extract_pricing_snapshot({"data": trace_pricing_context or {}}),
                "retrievedContext": {"refCars": compact_ref_cars(trace_ref_cars)},
                "answerPreview": answer or "",
                "error": error,
            })
            body = {"success": success, "data": data, "traceId": trace_id} if success else {"success": False, "error": error or "", "traceId": trace_id}
            return jsonify(body), status_code
        
        if not message:
            return _chat_response("", root_intent="fallback", workflow="fallback_chat", status_code=400, success=False, error="请输入问题")

        print(f"\n[聊天] 收到问题: {message}")

        is_pricing_explain_question = any(kw in message for kw in [
            '不准', '不太准', '不准确', '估高', '估低', '高了', '低了',
            '太高', '太低', '偏高', '偏低', '贵了', '便宜了', '不合理',
            '不是很准', '没那么准', '不够准', '不太对', '不对', '有偏差',
            '偏差大', '不靠谱', '价格不对', '估价不对', '报价不对',
            '这个价格不准', '这个报价不准', '你这个价格', '你这个报价',
            '报价有问题', '价格有问题', '估价有问题', '价格哪里来的',
            '影响因素', '价格影响因素', '影响价格', '影响报价', '影响估价',
            '定价因素', '估价因素', '报价因素', '因素分析', '哪些因素',
            '受什么影响', '怎么影响价格',
            '为什么', '原因', '怎么估', '定价逻辑', '价格逻辑'
        ])
        has_pricing_context = bool(
            pricing_context
            and (pricing_context.get('carData') or pricing_context.get('pricingResult'))
        )
        is_context_followup = has_pricing_context and any(kw in message for kw in [
            '怎么', '咋', '如何', '为什么', '为啥', '原因', '建议', '怎么办',
            '调', '调整', '改', '优化', '提升', '提高', '升级', '配置',
            '补充', '完善', '竞争力', '卖点', '话术', '客户', '车商'
        ])

        if is_pricing_explain_question and has_pricing_context and _env_truthy("INTERACTION_CHAT_GENERATOR_ENABLED", "1"):
            try:
                from services.response_generator import ResponseGenerator

                pr = pricing_context.get("pricingResult") or {}
                cd = pricing_context.get("carData") or {}
                answer = ResponseGenerator().generate(
                    user_message=message,
                    intent={"type": "EXPLAIN_PRICE", "task": "UNKNOWN", "confidence": 0.95, "source": "rule"},
                    slots={
                        "brand": cd.get("brand"),
                        "series": cd.get("series"),
                        "model_year": cd.get("model_year"),
                        "city": cd.get("city"),
                        "color": cd.get("color"),
                        "mileage_wan_km": cd.get("mileage"),
                        "transfer_count": cd.get("transfer"),
                    },
                    vehicle_match=pr.get("standard_vehicle") or {},
                    missing_fields=[],
                    quick_tags=[],
                    pricing={"current_pricing_result": pr, "price_result": pr},
                    warnings=[],
                    fallback_used=False,
                    fallback_reason="",
                )["text"]
                return _chat_response(answer, root_intent="chat", diag_sub_intent="price_reason", workflow="price_explanation", model_name="qwen3-response-generator")
            except Exception as exc:
                print(f"[interaction_chat] response generator failed, legacy fallback: {exc}")

        # ── 主题无关检测：与二手车/定价无关的问题直接返回兜底话术 ──
        _car_keywords = [
            '车', '定价', '估价', '收车', '售价', '价格', '里程', '过户',
            '车况', '车型', '品牌', '年款', '发动机', '变速箱', '事故',
            'C2B', 'B2C', '市场', '竞争力', '参考', '话术', '砍价',
            '成色', '公里', '万', '报价', '评估', '保值', '残值',
            '车源', '收车价', '二手', '新车', '卖车', '买车',
            '估高', '估低', '高了', '低了', '偏高', '偏低', '太高', '太低',
            '有点高', '有点低', '有些高', '有些低', '稍高', '稍低',
            '贵了', '便宜', '偏贵', '合理', '准确', '靠谱', '竞争',
            '觉得', '感觉', '我认为', '我感觉', '我觉得', '认为',
            '偏贵', '便宜了', '贵了点', '低了点',
            '不是很准', '没那么准', '不够准', '不太对', '不对', '有偏差',
            '偏差大', '不靠谱', '价格不对', '估价不对', '报价不对',
            '影响因素', '价格影响因素', '影响价格', '影响报价', '影响估价',
            '定价因素', '估价因素', '报价因素', '因素分析', '哪些因素',
            '受什么影响', '怎么影响价格',
            '配置', '升级', '优化', '调整', '提升', '提高', '竞品',
            '卖点', '建议', '客户', '成交', '解释', '依据',
        ]
        _FALLBACK_RESPONSE = (
            "抱歉，我是一名专注于二手车估值的AI专业助手。目前我只能回答与车辆估值、定价等相关的问题。"
            "您可以直接告诉我车源信息，我将为您生成专业报告。"
        )
        if not any(kw in message for kw in _car_keywords) and not is_context_followup:
            print(f"[聊天] 问题与二手车无关，返回兜底话术")
            return _chat_response(_FALLBACK_RESPONSE, root_intent="fallback", diag_sub_intent="out_of_scope", workflow="fallback_chat")

        def _fmt_wan(value):
            try:
                return f"{float(value):.2f}万"
            except Exception:
                return "暂无"

        def _safe_float(value, default=None):
            try:
                if value in (None, ''):
                    return default
                return float(value)
            except Exception:
                return default

        def _safe_int(value, default=None):
            try:
                if value in (None, ''):
                    return default
                return int(float(value))
            except Exception:
                return default

        def _build_pricing_factor_context(car_data, pricing_result):
            car_data = car_data or {}
            pricing_result = pricing_result or {}
            ref_cars = pricing_result.get('ref_cars') or []
            current_mileage = _safe_float(car_data.get('mileage'))
            current_transfer = _safe_int(car_data.get('transfer'))
            current_year = _safe_int(str(car_data.get('regDate', '')).split('-')[0])
            b2c = _safe_float(pricing_result.get('b2cPrice'))
            c2b = _safe_float(pricing_result.get('c2bPrice'))
            ref_mean = _safe_float(pricing_result.get('ref_b2c_mean'))

            facts = [
                f"当前车型: {car_data.get('title', '未知')}",
                f"当前车辆: 上牌/年款={car_data.get('regDate') or '未知'}，里程={car_data.get('mileage') or '未知'}万公里，过户={car_data.get('transfer') if car_data.get('transfer') not in (None, '') else '未知'}次，颜色={car_data.get('color') or '未知'}，城市={car_data.get('city') or '未知'}",
                f"当前报价: C2B={_fmt_wan(c2b)}，B2C={_fmt_wan(b2c)}，车况描述={pricing_result.get('condition_desc') or '未知'}",
            ]
            if ref_mean and b2c:
                gap = b2c - ref_mean
                gap_pct = gap / ref_mean * 100
                facts.append(f"同类样本B2C均价={_fmt_wan(ref_mean)}，当前B2C相对样本均价差额={gap:+.2f}万，差异={gap_pct:+.1f}%")

            valid_refs = []
            for ref in ref_cars:
                mileage = _safe_float(ref.get('mileage'))
                transfer = _safe_int(ref.get('transfer_count'))
                year = _safe_int(ref.get('model_year'))
                price = _safe_float(ref.get('b2c_price'))
                if price is not None:
                    valid_refs.append({
                        'year': year,
                        'mileage': mileage,
                        'transfer': transfer,
                        'price': price,
                    })

            if valid_refs:
                prices = [r['price'] for r in valid_refs if r['price'] is not None]
                mileages = [r['mileage'] for r in valid_refs if r['mileage'] is not None]
                transfers = [r['transfer'] for r in valid_refs if r['transfer'] is not None]
                years = [r['year'] for r in valid_refs if r['year'] is not None]

                def _linear_slope(xs, ys):
                    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
                    if len(pairs) < 2:
                        return None
                    x_vals = [p[0] for p in pairs]
                    y_vals = [p[1] for p in pairs]
                    x_mean = sum(x_vals) / len(x_vals)
                    y_mean = sum(y_vals) / len(y_vals)
                    denom = sum((x - x_mean) ** 2 for x in x_vals)
                    if denom <= 1e-9:
                        return None
                    return sum((x - x_mean) * (y - y_mean) for x, y in pairs) / denom

                def _impact_sentence(name, delta, impact, unit, positive_better=False):
                    if delta is None:
                        return ""
                    if abs(delta) < 0.05:
                        return f"{name}与参考样本基本一致，估算对价格影响约0.00万"
                    if impact is None or abs(impact) < 0.03:
                        direction = "高于" if delta > 0 else "低于"
                        return f"{name}{direction}样本平均{abs(delta):.1f}{unit}，但样本相关性显示估算影响接近0.00万"
                    effect = "抬高" if impact > 0 else "拉低"
                    direction = "高于" if delta > 0 else "低于"
                    better_hint = ""
                    if positive_better:
                        better_hint = "，该差异对价格偏正向" if impact > 0 else "，该差异对价格偏负向"
                    return f"{name}{direction}样本平均{abs(delta):.1f}{unit}{better_hint}，按样本相关性估算{effect}约{abs(impact):.2f}万"

                if years:
                    same_year = sum(1 for y in years if current_year is not None and y == current_year)
                    facts.append(f"参考样本年款范围={min(years)}-{max(years)}，同年款样本={same_year}辆")
                if mileages:
                    avg_mileage = sum(mileages) / len(mileages)
                    facts.append(f"参考样本里程范围={min(mileages):.1f}-{max(mileages):.1f}万公里，平均={avg_mileage:.1f}万公里")
                    if current_mileage is not None:
                        mileage_delta = current_mileage - avg_mileage
                        facts.append(f"当前里程比参考样本平均里程差={mileage_delta:+.1f}万公里")
                        mileage_slope = _linear_slope(mileages, prices)
                        mileage_impact = mileage_slope * mileage_delta if mileage_slope is not None else None
                        facts.append(f"里程影响估算: {_impact_sentence('里程', mileage_delta, mileage_impact, '万公里')}")
                if transfers:
                    avg_transfer = sum(transfers) / len(transfers)
                    facts.append(f"参考样本过户范围={min(transfers)}-{max(transfers)}次，平均={avg_transfer:.1f}次")
                    if current_transfer is not None:
                        transfer_delta = current_transfer - avg_transfer
                        if abs(transfer_delta) < 0.05:
                            facts.append(f"当前过户={current_transfer}次，与参考样本平均过户{avg_transfer:.1f}次基本一致，差值=0次")
                        else:
                            facts.append(f"当前过户比参考样本平均过户差={transfer_delta:+.1f}次")
                        transfer_slope = _linear_slope(transfers, prices)
                        transfer_impact = transfer_slope * transfer_delta if transfer_slope is not None else None
                        facts.append(f"过户影响估算: {_impact_sentence('过户次数', transfer_delta, transfer_impact, '次')}")
                if prices:
                    facts.append(f"参考样本售价范围={min(prices):.2f}-{max(prices):.2f}万")
                if years and current_year is not None:
                    avg_year = sum(years) / len(years)
                    year_delta = current_year - avg_year
                    year_slope = _linear_slope(years, prices)
                    year_impact = year_slope * year_delta if year_slope is not None else None
                    facts.append(f"年款影响估算: {_impact_sentence('年款', year_delta, year_impact, '年', positive_better=True)}")

                lower_mileage_prices = [
                    r['price'] for r in valid_refs
                    if current_mileage is not None and r['mileage'] is not None and r['mileage'] <= current_mileage and r['price'] is not None
                ]
                higher_mileage_prices = [
                    r['price'] for r in valid_refs
                    if current_mileage is not None and r['mileage'] is not None and r['mileage'] > current_mileage and r['price'] is not None
                ]
                if lower_mileage_prices and higher_mileage_prices:
                    lower_avg = sum(lower_mileage_prices) / len(lower_mileage_prices)
                    higher_avg = sum(higher_mileage_prices) / len(higher_mileage_prices)
                    facts.append(f"样本粗分组: 里程不高于当前车的均价={lower_avg:.2f}万，里程高于当前车的均价={higher_avg:.2f}万；这是相关性对比，不是单一因果系数")

            return "\n".join(f"- {item}" for item in facts)

        def _build_grounded_pricing_answer(car_data, pricing_result):
            """Create a data-grounded answer first, then let the LLM polish it."""
            car_data = car_data or {}
            pricing_result = pricing_result or {}
            ref_cars = pricing_result.get('ref_cars') or []
            b2c = _safe_float(pricing_result.get('b2cPrice'))
            c2b = _safe_float(pricing_result.get('c2bPrice'))
            ref_mean = _safe_float(pricing_result.get('ref_b2c_mean'))
            current_mileage = _safe_float(car_data.get('mileage'))
            current_transfer = _safe_int(car_data.get('transfer'))
            current_year = _safe_int(str(car_data.get('regDate', '')).split('-')[0])
            car_title = car_data.get('title') or car_data.get('rawModelText') or '这台车'
            ref_count = pricing_result.get('ref_count') or len(ref_cars)

            valid_refs = []
            for ref in ref_cars:
                mileage = _safe_float(ref.get('mileage'))
                transfer = _safe_int(ref.get('transfer_count'))
                year = _safe_int(ref.get('model_year'))
                price = _safe_float(ref.get('b2c_price'))
                if price is not None:
                    valid_refs.append({
                        'year': year,
                        'mileage': mileage,
                        'transfer': transfer,
                        'price': price,
                    })

            def _linear_slope(xs, ys):
                pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
                if len(pairs) < 2:
                    return None
                x_vals = [p[0] for p in pairs]
                y_vals = [p[1] for p in pairs]
                x_mean = sum(x_vals) / len(x_vals)
                y_mean = sum(y_vals) / len(y_vals)
                denom = sum((x - x_mean) ** 2 for x in x_vals)
                if denom <= 1e-9:
                    return None
                return sum((x - x_mean) * (y - y_mean) for x, y in pairs) / denom

            def _impact_phrase(name, current, avg, delta, impact, unit):
                if delta is None:
                    return ""
                if name == "上牌年份":
                    if abs(delta) < 0.05:
                        return f"上牌年份{int(current)}年，与同类样本平均上牌年份基本一致，对价格影响约0.00万"
                    compare = "更新" if delta > 0 else "更早"
                    if impact is None or abs(impact) < 0.03:
                        return f"上牌年份{int(current)}年，比同类样本平均{compare}{abs(delta):.1f}年，样本单项估算接近0.00万"
                    effect = "抬高" if impact > 0 else "拉低"
                    return f"上牌年份{int(current)}年，比同类样本平均{compare}{abs(delta):.1f}年，按参考样本相关性估算{effect}价格约{abs(impact):.2f}万"
                if abs(delta) < 0.05:
                    return f"{name}{current:g}{unit}，与同类样本平均{avg:.1f}{unit}基本一致，对价格影响约0.00万"
                compare = "高于" if delta > 0 else "低于"
                if impact is None or abs(impact) < 0.03:
                    business_direction = "拉低" if (name == "里程" and delta > 0) or (name == "过户" and delta > 0) else "抬高"
                    return f"{name}{current:g}{unit}，{compare}同类样本平均{abs(delta):.1f}{unit}，样本单项估算接近0.00万；按业务方向属于{business_direction}因素，但本次幅度很小"
                effect = "抬高" if impact > 0 else "拉低"
                return f"{name}{current:g}{unit}，{compare}同类样本平均{abs(delta):.1f}{unit}，按参考样本相关性估算{effect}价格约{abs(impact):.2f}万"

            sample_lines = []
            factor_lines = []
            action_lines = []
            caution_lines = []
            prices = []
            mileages = []
            transfers = []
            years = []

            if b2c is not None and ref_mean:
                gap = b2c - ref_mean
                gap_pct = gap / ref_mean * 100
                gap_direction = "高于" if gap > 0 else "低于"
                sample_lines.append(
                    f"当前售车参考价约{b2c:.2f}万，同类样本B2C均价约{ref_mean:.2f}万，"
                    f"{gap_direction}样本均价{abs(gap):.2f}万（{abs(gap_pct):.1f}%）。"
                )
            elif b2c is not None:
                sample_lines.append(f"当前售车参考价约{b2c:.2f}万，但本次没有拿到足够稳定的样本均价。")
            if c2b is not None:
                sample_lines.append(f"当前收车参考价约{c2b:.2f}万。")

            if valid_refs:
                prices = [r['price'] for r in valid_refs if r['price'] is not None]
                mileages = [r['mileage'] for r in valid_refs if r['mileage'] is not None]
                transfers = [r['transfer'] for r in valid_refs if r['transfer'] is not None]
                years = [r['year'] for r in valid_refs if r['year'] is not None]

                if prices:
                    sample_lines.append(
                        f"本次可比样本{len(valid_refs)}条，样本售价区间约{min(prices):.2f}-{max(prices):.2f}万。"
                    )

                if current_mileage is not None and mileages and prices:
                    avg_mileage = sum(mileages) / len(mileages)
                    mileage_delta = current_mileage - avg_mileage
                    mileage_slope = _linear_slope(mileages, prices)
                    mileage_impact = mileage_slope * mileage_delta if mileage_slope is not None else None
                    factor_lines.append(_impact_phrase("里程", current_mileage, avg_mileage, mileage_delta, mileage_impact, "万公里"))

                if current_transfer is not None and transfers and prices:
                    avg_transfer = sum(transfers) / len(transfers)
                    transfer_delta = current_transfer - avg_transfer
                    transfer_slope = _linear_slope(transfers, prices)
                    transfer_impact = transfer_slope * transfer_delta if transfer_slope is not None else None
                    factor_lines.append(_impact_phrase("过户", current_transfer, avg_transfer, transfer_delta, transfer_impact, "次"))

                if current_year is not None and years and prices:
                    avg_year = sum(years) / len(years)
                    year_delta = current_year - avg_year
                    year_slope = _linear_slope(years, prices)
                    year_impact = year_slope * year_delta if year_slope is not None else None
                    factor_lines.append(_impact_phrase("上牌年份", current_year, avg_year, year_delta, year_impact, "年"))

            if car_data.get('city'):
                factor_lines.append(f"城市为{car_data.get('city')}，会通过本地供需和同城样本价格修正最终报价。")
            if car_data.get('color'):
                factor_lines.append(f"颜色为{car_data.get('color')}，通常是弱影响项，除非属于明显冷门色或车况喷漆异常。")

            factor_lines = [p for p in factor_lines if p]

            condition_desc = pricing_result.get('condition_desc')
            if condition_desc:
                factor_lines.append(f"车况结论为“{condition_desc}”，它参与最终综合修正，不是让用户去改变已发生事实。")

            if not sample_lines and not factor_lines:
                return ""

            if not car_data.get('modelId') and car_data.get('rawModelText'):
                caution_lines.append("车型还只是线索，建议先从车型库选择标准车型，否则价格容易被相近车型带偏。")
            if not ref_count or int(ref_count or 0) < 3:
                caution_lines.append("同类样本不足，建议补充标准车型或转人工复核后再给强结论。")
            action_lines.extend([
                "如果您认为市场价不一致，可以补充一条同款车源价格，我会按新参考重新解释。",
                "如果参数有误，可以直接说“里程改成2万公里”“城市改成上海”“车型改成某某配置”，我会先同步参数再重新生成。"
            ])

            sample_text = "\n".join(f"- {line}" for line in sample_lines) or "- 暂无稳定样本均价，本次只能给弱结论。"
            factor_text = "\n".join(f"- {line}" for line in factor_lines) or "- 当前上下文缺少可拆解的样本字段，建议先重新生成完整报价报告。"
            caution_text = ("\n".join(f"- {line}" for line in caution_lines) + "\n") if caution_lines else ""
            action_text = "\n".join(f"- {line}" for line in action_lines)
            caution_section = f"3. 需要先注意的风险：\n{caution_text}\n" if caution_lines else ""
            action_index = "4" if caution_lines else "3"

            return (
                f"您觉得价格不准，不能只看一个参考价，要拆成“样本对比 + 单项因素 + 下一步核对”。\n\n"
                f"1. 当前报价和样本怎么比：\n{sample_text}\n\n"
                f"2. 哪些因素在拉高/拉低价格：\n{factor_text}\n\n"
                f"{caution_section}"
                f"{action_index}. 下一步怎么让报价更准：\n{action_text}\n\n"
                "说明：上面单项金额是基于参考样本的相关性估算，最终报价还会叠加车型配置、城市供需和模型综合修正，各项金额不能简单相加。"
            )

        def _clean_llm_answer(text):
            import re as _re
            cleaned = (text or '').replace('**', '').replace('###', '').strip()
            cleaned = _re.sub(r'\n+\s*\d+[\.、]\s*', ' ', cleaned)
            cleaned = _re.sub(r'\s*\n+\s*', ' ', cleaned)
            cleaned = cleaned.replace('可能会', '会').replace('可能对', '对').replace('可能', '')
            cleaned = cleaned.replace('多0次', '基本一致').replace('高出0.0次', '基本一致').replace('低于0.0次', '基本一致')
            cleaned = _re.sub(r'过户[^。；，]*高于样本平均[^。；，]*，但过户[^。；。]*基本一致', '过户次数与参考样本基本一致，估算对价格影响约0.00万', cleaned)
            return _re.sub(r'\s{2,}', ' ', cleaned).strip()

        def _llm_pricing_answer_failed_guardrails(text):
            text = text or ''
            bad_patterns = [
                '多0次', '多0.0次', '高出0次', '高出0.0次',
                '降低过户次数', '减少过户次数', '减少已发生里程', '降低已发生过户',
                '可能会影响', '可能影响', '可能对价格',
                '这也对价格产生影响', '也对价格产生影响',
                '共同导致了价格的轻微下降', '共同导致价格下降',
            ]
            if any(p in text for p in bad_patterns):
                return True
            if '基本一致' in text and '影响约0.00万' in text and ('产生影响' in text or '会影响价格' in text):
                return True
            return False

        is_factor_explain_question = has_pricing_context and (
            is_pricing_explain_question or any(kw in message for kw in [
                '车况', '影响因素', '价格影响因素', '影响价格', '影响报价', '影响估价',
                '影响我这台车价格', '怎么影响', '怎么影响价格', '价格怎么来的', '为什么这个价',
                '定价因素', '估价因素', '报价因素', '因素分析', '哪些因素', '受什么影响',
                '定价原因', '定价依据', '估价逻辑', '价格原因', '价格不是很准',
                '估价不是很准', '报价不是很准', '价格有偏差', '估价有偏差'
            ])
        )

        def _direct_followup_answer():
            car_data = pricing_context.get('carData') if pricing_context else {}
            pricing_result = pricing_context.get('pricingResult') if pricing_context else {}
            car_title = (car_data or {}).get('title') or '这台车'
            c2b = (pricing_result or {}).get('c2bPrice')
            b2c = (pricing_result or {}).get('b2cPrice')
            ref_mean = (pricing_result or {}).get('ref_b2c_mean')
            ref_count = (pricing_result or {}).get('ref_count', 0)
            ref_cars = (pricing_result or {}).get('ref_cars') or []

            if (car_data or {}).get('is_custom_model') or (
                (car_data or {}).get('rawModelText') and not (car_data or {}).get('modelId') and not (pricing_result or {}).get('b2cPrice')
            ):
                raw_model = (car_data or {}).get('rawModelText') or car_title
                return (
                    f"{raw_model} 当前没有匹配到车型库里的标准车型，我不会直接强行报价。"
                    "请先从车型库选择标准车型；如果库里确实没有，就建议转人工复核后再给价格，避免用相近车型套价造成明显偏差。"
                )

            if any(kw in message for kw in ['保养记录', '维保记录', '维修保养', '4S记录', '4s记录', '出险记录']):
                return (
                    f"查{car_title}的保养记录，优先走三条路：1. 让卖家提供4S店/品牌App里的维保截图或PDF，核对车架号、日期、公里数；"
                    "2. 带行驶证或车架号去对应品牌4S店查询授权记录；3. 用第三方报告查维保和出险，但只能做辅助。"
                    "重点看公里数是否连续、是否有大修/事故维修、保养间隔是否异常。"
                )

            if any(kw in message for kw in ['竞品', '行情', '竞争力', '同类', '参考车源', '类似']):
                if ref_mean and b2c:
                    diff = float(b2c) - float(ref_mean)
                    diff_pct = diff / float(ref_mean) * 100 if float(ref_mean) else 0
                    direction = "高于" if diff > 0 else "低于"
                    strength = "竞争力偏弱，需要靠车况/配置亮点支撑" if diff_pct > 5 else (
                        "价格有竞争力，但要确认车况是否支撑" if diff_pct < -5 else "基本处在同类样本中位附近"
                    )
                    sample_range = ""
                    prices = [_safe_float(r.get('b2c_price')) for r in ref_cars if _safe_float(r.get('b2c_price')) is not None]
                    if prices:
                        sample_range = f"；参考样本价格区间约{min(prices):.2f}-{max(prices):.2f}万"
                    return (
                        f"这台车当前B2C估价{float(b2c):.2f}万，同类样本均价{float(ref_mean):.2f}万，"
                        f"{direction}均价{abs(diff):.2f}万（{abs(diff_pct):.1f}%）{sample_range}。"
                        f"所以当前判断是：{strength}。竞争力主要看同年款/相近配置、里程、过户和城市样本差异，不建议只凭车型名判断。"
                    )
                return "要判断竞品/行情竞争力，需要先有当前报价和同类样本均价；请先生成报价或补充当前车源信息，我再按同年款、相近配置、里程、过户和城市样本对比。"

            if is_pricing_explain_question and not is_factor_explain_question:
                current_year = str((car_data or {}).get('regDate', '')).split('-')[0] if (car_data or {}).get('regDate') else ''
                current_mileage = (car_data or {}).get('mileage')
                current_transfer = (car_data or {}).get('transfer')
                current_color = (car_data or {}).get('color')
                current_city = (car_data or {}).get('city')
                sample_detail = ""
                if ref_cars:
                    years = [str(r.get('model_year')) for r in ref_cars if r.get('model_year')]
                    mileages = [float(r.get('mileage')) for r in ref_cars if r.get('mileage') is not None]
                    transfers = [int(r.get('transfer_count')) for r in ref_cars if r.get('transfer_count') is not None]
                    prices = [float(r.get('b2c_price')) for r in ref_cars if r.get('b2c_price')]
                    same_year_count = sum(1 for y in years if current_year and y == current_year)
                    parts = []
                    if years:
                        parts.append(f"参考车源年款集中在{min(years)}-{max(years)}款，同年款{same_year_count}辆")
                    if mileages:
                        parts.append(f"里程约{min(mileages):.1f}-{max(mileages):.1f}万公里")
                    if transfers:
                        parts.append(f"过户多在{min(transfers)}-{max(transfers)}次")
                    if prices:
                        parts.append(f"参考售价约{min(prices):.2f}-{max(prices):.2f}万")
                    sample_detail = "；".join(parts)
                if ref_mean and b2c:
                    diff_pct = (float(b2c) - float(ref_mean)) / float(ref_mean) * 100
                    direction = "高于" if diff_pct > 0 else "低于"
                    return (
                        f"这次定价不是单看车型名，而是先找同品牌/同车系/配置相近的成交样本，再按年款、里程、过户、城市和车况做修正。"
                        f"当前车是{current_year}款、{current_mileage}万公里、过户{current_transfer}次、{current_color or '未知颜色'}、{current_city or '未知城市'}；"
                        f"样本均价约{_fmt_wan(ref_mean)}，本次B2C估价约{_fmt_wan(b2c)}，{direction}样本均价{abs(diff_pct):.1f}%（样本{ref_count}辆）。"
                        f"{sample_detail or '颜色一般是弱影响项，主要影响来自配置、年款、里程、过户和车况。'}"
                    )
                return (
                    f"这次定价逻辑是：先按{car_title}匹配同品牌/同车系/配置相近车源，再按年款、里程、过户、城市和车况做加减价。"
                    "颜色通常是弱影响项，除非是冷门色或事故喷漆；真正拉开价格的是配置差异、年份新旧、里程高低、过户次数和同城供需。"
                )

            if any(kw in message for kw in ['升级配置', '提高配置', '怎么调整配置', '怎么改配置', '配置怎么']):
                return (
                    "配置不能靠话术“升级”，报价只认真实配置。正确做法是先确认标准车型，再补充真实选装或高配项，"
                    "例如辅助驾驶、全景天窗、座椅通风加热、音响、轮毂、原厂选装包等。"
                    "如果只是后改装，通常不能按原厂高配加价，最多作为卖点说明。"
                )

            return None

        direct_answer = _direct_followup_answer()
        if direct_answer:
            print(f"[聊天] 命中直答策略: {direct_answer[:80]}...")
            return _chat_response(direct_answer, root_intent="chat", diag_sub_intent="price_reason", workflow="price_explanation")

        if is_factor_explain_question:
            car_data = pricing_context.get('carData') if pricing_context else {}
            pricing_result = pricing_context.get('pricingResult') if pricing_context else {}
            grounded_answer = _build_grounded_pricing_answer(car_data, pricing_result)
            if grounded_answer:
                print(f"[聊天] 命中结构化估价解释: {grounded_answer[:80]}...")
                return _chat_response(grounded_answer, root_intent="chat", diag_sub_intent="price_reason", workflow="price_explanation")
            return _chat_response(
                    (
                        "要分析这辆车价格的影响因素，需要先拿到当前报价报告里的车型、上牌时间、里程、过户、城市、颜色和同类样本价格。"
                        "请先生成一次报价报告；报告生成后再问“价格影响因素”或“为什么这个价格”，我会按同类样本均价、里程差异、年款、过户次数、城市供需和车况逐项解释。"
                    ),
                    root_intent="chat",
                    diag_sub_intent="price_reason",
                    workflow="price_explanation",
            )

        if DEPLOY_LITE_MODE:
            car_data = pricing_context.get('carData') if pricing_context else {}
            pricing_result = pricing_context.get('pricingResult') if pricing_context else {}
            grounded_answer = _build_grounded_pricing_answer(car_data, pricing_result)
            fallback_answer = (
                grounded_answer
                or _direct_followup_answer()
                or (
                    "当前线上环境没有拿到可解释的完整估价上下文，无法直接解释这个价格。"
                    "请先生成一次报价报告，或补充车型、上牌、里程、过户、颜色、城市等信息后再追问。"
                )
            )
            return _chat_response(fallback_answer, root_intent="chat", diag_sub_intent="price_reason", workflow="price_explanation", model_name="lite-rule")

        init_backend()

        # 检查推理模型是否就绪
        import react_pricing as rp
        if not rp.REASONING_MODEL_AVAILABLE:
            return _chat_response("", root_intent="chat", workflow="fallback_chat", status_code=503, success=False, error="模型正在初始化中，请先完成一次定价后再使用聊天功能")

        if is_factor_explain_question:
            car_data = pricing_context.get('carData') if pricing_context else {}
            pricing_result = pricing_context.get('pricingResult') if pricing_context else {}
            factor_context = _build_pricing_factor_context(car_data, pricing_result)
            grounded_answer = _build_grounded_pricing_answer(car_data, pricing_result)
            factor_prompt = f"""你是二手车估值解释专家。请基于下面结构化数据回答用户追问，不要泛泛讲二手车常识。

结构化数据：
{factor_context}

必须遵守的数据结论：
{grounded_answer or '暂无可量化数据结论，只能基于已有车辆信息解释。'}

用户追问：{message}

回答要求：
1. 只解释定价原因，不给用户改车建议。
2. 以B2C估价和同类样本B2C均价做对比；不要把C2B收车价当成当前售价。
3. 必须优先使用“必须遵守的数据结论”和“里程影响估算/过户影响估算/年款影响估算”里的方向和金额，明确说拉低或抬高约多少万；不要只说“可能影响”。
4. 如果某项差值接近0或结构化数据写“影响约0.00万”，必须说“基本无影响”，禁止说它产生明显影响。
5. 不能把“价格高于/低于样本均价”本身当作原因，必须说明背后的因素，例如里程更高/更低、过户更多/更少、年款更新/更旧、车况描述、城市样本差异。
6. 如果说里程/过户/年款影响价格，只能说“已经发生的因素如何影响”，禁止建议减少已发生里程、降低已发生过户次数、虚假升级配置。
7. 禁止得出与“必须遵守的数据结论”相反的结论；例如过户差值为0就只能说基本无影响。
8. 禁止使用“可能、也许、大概”这类模糊词；只输出一段中文，不要编号，不要Markdown，不要重复同一句；最多3句话，120-180字。"""
            response = _clean_llm_answer(_call_llm(factor_prompt, temperature=0.1, max_tokens=320, use_finetuned=False))
            if grounded_answer and _llm_pricing_answer_failed_guardrails(response):
                response = grounded_answer
            return _chat_response(response, root_intent="chat", diag_sub_intent="price_reason", workflow="price_explanation", model_name="Qwen2.5-chat", use_finetuned=False)

        # 构建上下文信息
        context_parts = []
        
        if pricing_context and pricing_context.get('carData'):
            car_data = pricing_context['carData']
            context_parts.append("## 最近的车辆信息")
            context_parts.append(f"车型: {car_data.get('title', '未知')}")
            if car_data.get('regDate'):
                context_parts.append(f"上牌时间: {car_data.get('regDate')}")
            if car_data.get('mileage'):
                context_parts.append(f"里程: {car_data.get('mileage')} 万公里")
            if car_data.get('transfer'):
                context_parts.append(f"过户次数: {car_data.get('transfer')} 次")
            if car_data.get('color'):
                context_parts.append(f"颜色: {car_data.get('color')}")
            if car_data.get('city'):
                context_parts.append(f"城市: {car_data.get('city')}")
        
        if pricing_context and pricing_context.get('pricingResult'):
            pricing_result = pricing_context['pricingResult']
            context_parts.append("\n## 最近的定价结果")
            if pricing_result.get('c2bPrice'):
                context_parts.append(f"C2B收车价: {pricing_result['c2bPrice']:.2f} 万")
            if pricing_result.get('b2cPrice'):
                context_parts.append(f"B2C售价: {pricing_result['b2cPrice']:.2f} 万")
            if pricing_result.get('condition_desc'):
                context_parts.append(f"车辆状态: {pricing_result['condition_desc']}")

            # 市场竞争力分析
            b2c = pricing_result.get('b2cPrice', 0)
            ref_mean = pricing_result.get('ref_b2c_mean', 0)
            ref_count_val = pricing_result.get('ref_count', 0)
            if b2c and ref_mean and ref_count_val:
                diff_pct = (b2c - ref_mean) / ref_mean * 100
                direction = "高于" if diff_pct > 0 else "低于"
                context_parts.append(
                    f"\n## 市场参考数据（{ref_count_val}辆同类成交车）"
                )
                context_parts.append(f"同类车B2C均价: {ref_mean:.2f} 万")
                context_parts.append(
                    f"当前定价{direction}市场均价 {abs(diff_pct):.1f}%，"
                    f"{'价格偏高，竞争力偏弱' if diff_pct > 5 else ('价格偏低，竞争力较强' if diff_pct < -5 else '价格处于市场中位，竞争力适中')}"
                )

            # 参考车源明细
            ref_cars = pricing_result.get('ref_cars', [])
            if ref_cars:
                context_parts.append("\n## 参考车源明细")
                for i, rc in enumerate(ref_cars[:5], 1):
                    context_parts.append(
                        f"{i}. {rc.get('brand','')}{rc.get('series','')} {rc.get('model_year','')}款 "
                        f"| 里程{rc.get('mileage',0):.1f}万km "
                        f"| 过户{rc.get('transfer_count',0)}次 "
                        f"| B2C={rc.get('b2c_price',0):.2f}万"
                    )
        
        # 构建问答prompt
        context_str = "\n".join(context_parts) if context_parts else "无最近定价信息"
        
        prompt = f"""你是资深二手车收购顾问，有10年收车经验，熟悉收车话术、砍价技巧、客户心理，能结合市场数据给出具体建议。

{context_str}

用户问题：{message}

要求：
1. 只回答用户当前追问，不要扩展成完整评估报告，不要列无关检查清单。
2. 如果用户问怎么查某项，就给具体操作步骤；如果用户质疑价格，要解释定价背后的样本和因素：同年款/相近配置/里程/过户/城市/颜色/车况如何影响价格，不要只让用户检查输入。
3. 禁止建议用户减少已发生里程、降低已发生过户次数、虚假升级配置；只能解释这些因素已经如何影响价格。
4. 不要使用Markdown加粗符号，不要说"我无法"或"我不知道"。
5. 字数80-150字："""

        response = _call_llm(prompt, temperature=0.7, max_tokens=600, use_finetuned=False)

        # 检测拒答/无效响应，替换为兜底话术
        _refusal_patterns = [
            '我无法', '我不能', '我不知道', '无法回答', '无法提供',
            '超出我的', '我没有能力', '对不起，我', '抱歉，我无法',
            '我是AI', '作为AI', '我只是一个',
        ]
        _is_refusal = (
            not response
            or len(response.strip()) < 10
            or any(p in response for p in _refusal_patterns)
        )
        if _is_refusal:
            if is_pricing_explain_question or is_context_followup:
                response = (
                    "这次估价主要由同类成交车源、车型年款、里程、过户次数、车况和所在城市共同决定。"
                    "如果想让报价更准，不建议虚假“升级配置”，而是先校准真实车型配置，补充是否高配、选装、"
                    "事故/喷漆、保养记录、内饰外观、轮胎和机电状态。我会按补充后的真实信息重新计算。"
                )
            else:
                response = _FALLBACK_RESPONSE
        
        print(f"[聊天] 回答: {response[:100]}...")
        
        return _chat_response(response, root_intent="chat", diag_sub_intent="chat_business_guidance", workflow="fallback_chat", model_name="Qwen2.5-chat", use_finetuned=False)
        
    except Exception as e:
        print(f"❌ 问答失败: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            write_assistant_trace({
                "traceId": trace_id,
                "api": "/api/chat",
                "sessionId": (chat_data or {}).get("sessionId") or "",
                "messageId": (chat_data or {}).get("messageId") or "",
                "userQuery": message,
                "businessIntent": (chat_data or {}).get("businessIntent") or "",
                "rootIntent": "chat",
                "workflow": "fallback_chat",
                "answerType": "chat",
                "modelName": "Qwen2.5-chat",
                "promptVersion": "chat_v1",
                "useFinetuned": False,
                "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                "pricingResult": _extract_pricing_snapshot({}),
                "retrievedContext": {"refCars": []},
                "answerPreview": "",
                "error": str(e),
            })
        except Exception:
            pass
        return jsonify({
            'success': False,
            'error': str(e),
            'traceId': trace_id
        }), 500


@app.route('/api/intent', methods=['POST'])
def detect_intent():
    """意图识别API：用0.5B模型快速分类意图（单字母输出），chat回答由前端再调/api/chat"""
    trace_id = generate_trace_id()
    started_at = datetime.utcnow()
    data = {}
    message = ""
    try:
        data = request.json or {}
        message = data.get('message', '').strip()
        pricing_context = data.get('pricingContext', {})

        def _intent_response(intent_data, model_name="rule+Qwen-intent", source="rule", status_code=200):
            intent_data = intent_data or {}
            intent_data["traceId"] = trace_id
            root = intent_data.get("root_intent") or intent_data.get("intent") or ""
            diag = intent_data.get("diag_sub_intent") or ""
            write_assistant_trace({
                "traceId": trace_id,
                "api": "/api/intent",
                "sessionId": data.get("sessionId") or "",
                "messageId": data.get("messageId") or "",
                "userQuery": message,
                "businessIntent": data.get("businessIntent") or "",
                "rootIntent": root,
                "diagSubIntent": diag,
                "intentConfidence": intent_data.get("confidence") or intent_data.get("intentConfidence") or 0,
                "intentSource": intent_data.get("intentSource") or source,
                "workflow": _workflow_from_intent(root, diag),
                "answerType": "intent",
                "modelName": model_name,
                "promptVersion": "intent_v1",
                "useFinetuned": False,
                "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                "pricingResult": _extract_pricing_snapshot({}),
                "retrievedContext": {"refCars": []},
                "answerPreview": "",
                "error": None,
            })
            return jsonify({'success': True, 'data': intent_data}), status_code

        if not message:
            write_assistant_trace({
                "traceId": trace_id,
                "api": "/api/intent",
                "userQuery": "",
                "workflow": "fallback_chat",
                "answerType": "intent",
                "modelName": "rule+Qwen-intent",
                "promptVersion": "intent_v1",
                "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
                "error": "消息为空",
            })
            return jsonify({'success': False, 'error': '消息为空', 'traceId': trace_id}), 400

        if _env_truthy("INTERACTION_INTENT_SERVICE_ENABLED", "1"):
            try:
                from services.interaction_service import InteractionService

                unified = InteractionService(pricing_callable=None).process_turn(
                    {
                        "session_id": data.get("sessionId") or "",
                        "message": message,
                        "event_type": "user_message",
                        "client_state": {
                            "current_slots": {},
                            "current_pricing_result": pricing_context.get("pricingResult") if isinstance(pricing_context, dict) else {},
                        },
                        "disable_pricing": True,
                    }
                )
                canonical_type = unified.get("intent", {}).get("type", "")
                legacy_intent_map = {
                    "SELL_CAR_VALUATION_INTENT": "valuation",
                    "VEHICLE_INFO_ADD": "valuation",
                    "VEHICLE_INFO_UPDATE": "valuation",
                    "VEHICLE_CONFIRM": "valuation",
                    "PRICE_QUOTE_REQUEST": "valuation",
                    "PRICE_ESTIMATE": "valuation",
                    "SELL_CAR_PRICE": "valuation",
                    "BOTH_PRICE": "valuation",
                    "BUY_CAR_INTENT": "chat",
                    "PRICE_ADJUSTMENT_INTENT": "adjust",
                    "DAILY_REPORT_READ_INTENT": "chat",
                    "REPORT_DETAIL_QUESTION": "chat",
                    "PRICE_EXPLANATION_REQUEST": "chat",
                    "CANDIDATE_EVIDENCE_REQUEST": "chat",
                    "WHY_LOW_CONFIDENCE": "chat",
                    "HISTORY_QUOTE_REFERENCE": "chat",
                    "EXPLAIN_PRICE": "chat",
                    "FEEDBACK_PRICE_TOO_HIGH": "chat",
                    "FEEDBACK_PRICE_TOO_LOW": "chat",
                    "FEEDBACK_INACCURATE": "chat",
                    "OUT_OF_SCOPE": "fallback",
                    "UNKNOWN_OR_INCOMPLETE": "fallback",
                }
                mapped = {
                    "intent": legacy_intent_map.get(canonical_type, "fallback"),
                    "canonical_intent": canonical_type,
                    "intent_schema_version": "intent_router_v2_stateful",
                    "mode": "all",
                    "response": "",
                    "should_clarify": bool(unified.get("missing_fields")),
                    "diag_sub_intent": canonical_type.lower(),
                    "confidence": unified.get("intent", {}).get("confidence", 0),
                    "root_intent": canonical_type,
                    "vehicle_state_hash": unified.get("vehicle_state_hash", ""),
                    "quote_lifecycle": unified.get("quote_lifecycle", {}),
                }
                return _intent_response(mapped, model_name=unified.get("debug", {}).get("llm_model") or "qwen3-interaction-service", source=unified.get("intent", {}).get("source", "interaction_service"))
            except Exception as exc:
                print(f"[interaction_intent] unified service failed, legacy fallback: {exc}")

        # 构建简短上下文，先交给产品硬规则路由；硬规则解决报价缺字段、补充车况、
        # 覆盖城市/颜色等高风险路径，避免被通用 chat 规则提前截走。
        context_parts = []
        if pricing_context.get('carData'):
            cd = pricing_context['carData']
            context_parts.append(f"{cd.get('title','')}, 里程{cd.get('mileage','')}万km")
        if pricing_context.get('pricingResult'):
            pr = pricing_context['pricingResult']
            if pr.get('b2cPrice'):
                context_parts.append(f"已定价B2C={pr['b2cPrice']:.1f}万")
        context_str = "；".join(context_parts) or "无"

        # 价格质疑/追问必须优先硬路由，不能交给通用模型先判。
        # 这类表达通常是对刚生成报价的追问，误判成普通 chat 会导致回答泛化甚至 undefined。
        pricing_explain_keywords = [
            '不准', '不太准', '不准确', '估高', '估低', '高了', '低了',
            '太高', '太低', '偏高', '偏低', '贵了', '便宜了', '不合理',
            '不是很准', '没那么准', '不够准', '不太对', '不对', '有偏差',
            '偏差大', '不靠谱', '价格不对', '估价不对', '报价不对',
            '这个价格不准', '这个报价不准', '你这个价格', '你这个报价',
            '报价有问题', '价格有问题', '估价有问题', '价格哪里来的',
            '影响因素', '价格影响因素', '影响价格', '影响报价', '影响估价',
            '定价因素', '估价因素', '报价因素', '因素分析', '哪些因素',
            '受什么影响', '怎么影响价格',
            '为什么', '原因', '怎么估', '定价逻辑', '价格逻辑'
        ]
        has_pricing_context = bool(
            pricing_context
            and (pricing_context.get('carData') or pricing_context.get('pricingResult'))
        )
        contextual_followup_keywords = [
            '怎么', '咋', '如何', '为什么', '为啥', '原因', '建议', '怎么办',
            '调', '调整', '改', '优化', '提升', '提高', '升级', '配置',
            '补充', '完善', '竞争力', '卖点', '话术', '客户', '车商'
        ]
        if any(kw in message for kw in pricing_explain_keywords) or (
            has_pricing_context and any(kw in message for kw in contextual_followup_keywords)
        ):
            return _intent_response(
                {
                    'intent': 'chat',
                    'mode': 'all',
                    'response': '',
                    'should_clarify': False,
                    'diag_sub_intent': 'price_reason'
                },
                model_name="rule-intent",
                source="hard_rule",
            )

        import react_pricing as rp
        first_pass = rp.classify_intent(message, context_str)
        if first_pass.get('intent') != 'keyword_fallback':
            print(f"[意图识别] {message!r} → {first_pass['intent']} ({first_pass.get('diag_sub_intent','')})")
            return _intent_response(first_pass, model_name="rule-intent", source="react_pricing_rule")

        init_backend()

        if not rp.INTENT_MODEL_AVAILABLE:
            return _intent_response({'intent': 'keyword_fallback', 'should_clarify': False, 'diag_sub_intent': 'unknown'}, model_name="keyword-fallback", source="fallback")

        result = rp.classify_intent(message, context_str)
        print(f"[意图识别] {message!r} → {result['intent']} ({result.get('diag_sub_intent','')})")

        return _intent_response(result, model_name="Qwen2.5-0.5B-intent", source="intent_model")

    except Exception as e:
        print(f"❌ 意图识别失败: {e}")
        import traceback
        traceback.print_exc()
        write_assistant_trace({
            "traceId": trace_id,
            "api": "/api/intent",
            "userQuery": message,
            "workflow": "fallback_chat",
            "answerType": "intent",
            "modelName": "rule+Qwen-intent",
            "promptVersion": "intent_v1",
            "latencyMs": int((datetime.utcnow() - started_at).total_seconds() * 1000),
            "error": str(e),
        })
        return jsonify({'success': False, 'error': str(e), 'traceId': trace_id}), 500


@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    try:
        if _active_pricing_model_version() == "v194":
            from services.v194_quote_service import get_version_payload
        elif _active_pricing_model_version() == "v193_1":
            from services.v193_1_quote_service import get_version_payload
        elif _active_pricing_model_version() == "v193":
            from services.v193_quote_service import get_version_payload
        elif _active_pricing_model_version() == "v192_16":
            from services.v192_16_quote_service import get_version_payload
        elif _active_pricing_model_version() == "v192_15":
            from services.v192_15_quote_service import get_version_payload
        elif _active_pricing_model_version() == "v192_14":
            from services.v192_14_quote_service import get_version_payload
        elif _active_pricing_model_version() == "v192_9":
            from services.v192_9_quote_service import get_version_payload
        elif _active_pricing_model_version() == "v192_10":
            from services.v192_10_quote_service import get_version_payload
        else:
            from services.v192_11_quote_service import get_version_payload

        version = get_version_payload()
    except Exception:
        version = {"pricing_engine_version": "unknown"}
    return jsonify({
        'status': 'ok',
        'initialized': is_initialized,
        'pricing_engine_version': version.get("pricing_engine_version"),
        'production_entrypoint': 'app.py',
    })


@app.route('/api/version', methods=['GET'])
def api_version():
    """生产定价版本信息。"""
    if _active_pricing_model_version() == "v194":
        from services.v194_quote_service import get_version_payload
    elif _active_pricing_model_version() == "v193_1":
        from services.v193_1_quote_service import get_version_payload
    elif _active_pricing_model_version() == "v193":
        from services.v193_quote_service import get_version_payload
    elif _active_pricing_model_version() == "v192_16":
        from services.v192_16_quote_service import get_version_payload
    elif _active_pricing_model_version() == "v192_15":
        from services.v192_15_quote_service import get_version_payload
    elif _active_pricing_model_version() == "v192_14":
        from services.v192_14_quote_service import get_version_payload
    elif _active_pricing_model_version() == "v192_9":
        from services.v192_9_quote_service import get_version_payload
    elif _active_pricing_model_version() == "v192_10":
        from services.v192_10_quote_service import get_version_payload
    else:
        from services.v192_11_quote_service import get_version_payload

    return jsonify(get_version_payload())


@app.route('/api/llm/status', methods=['GET'])
def api_llm_status():
    """LLM runtime status for enterprise intent fallback and controlled QA.

    This endpoint intentionally returns no credentials.  A healthy LLM is
    optional for pricing safety but required for ChatGPT-like open expression
    handling beyond deterministic business rules.
    """
    try:
        from services.llm_client import Qwen3LocalClient

        status = Qwen3LocalClient().health_check()
        return jsonify({"success": True, "data": status}), 200 if status.get("ok") else 503
    except Exception as exc:
        return jsonify({
            "success": False,
            "data": {
                "ok": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "recommended_enterprise_model": "Qwen/Qwen3-235B-A22B-Instruct-2507",
                "recommended_single_node_model": "Qwen/Qwen3-32B",
            },
        }), 503


@app.route('/api/search/status', methods=['GET'])
def api_search_status():
    """Enterprise web search gateway status without exposing credentials."""
    try:
        from usedcar_pricing.v193_2_search_client import OpenSearchClient, SEARCH_CLIENT_VERSION
        from services.enterprise_general_answer_service import EnterpriseGeneralAnswerService

        client = OpenSearchClient()
        provider_chain = client.provider_chain()
        configured = {
            "tavily": bool(os.environ.get("TAVILY_API_KEY")),
            "exa": bool(os.environ.get("EXA_API_KEY")),
            "brave": bool(os.environ.get("BRAVE_SEARCH_API_KEY")),
            "bing": bool(os.environ.get("BING_SEARCH_API_KEY") or os.environ.get("AZURE_BING_SEARCH_KEY")),
            "serpapi": bool(os.environ.get("SERPAPI_API_KEY")),
            "searxng": bool(os.environ.get("SEARXNG_BASE_URL")),
            "duckduckgo_html": (os.environ.get("WEB_SEARCH_ALLOW_DDG") or "").strip().lower() in {"1", "true", "yes", "on"},
        }
        return jsonify({
            "success": True,
            "data": {
                "ok": True,
                "search_client_version": SEARCH_CLIENT_VERSION,
                "search_provider": client.provider,
                "provider_chain": provider_chain,
                "provider_configured": configured,
                "qa_web_search_enabled": EnterpriseGeneralAnswerService._web_search_enabled(),
                "allowed_for_general_qa": True,
                "allowed_for_external_evidence_extraction": True,
                "allowed_to_directly_affect_price": False,
                "allowed_to_enter_pricing_baseline_without_schema_validation": False,
            },
        })
    except Exception as exc:
        return jsonify({
            "success": False,
            "data": {
                "ok": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "allowed_to_directly_affect_price": False,
            },
        }), 503


@app.route('/ready', methods=['GET'])
def ready():
    """部署就绪检查：模型/索引/SQLite/API入口。"""
    if _active_pricing_model_version() == "v194":
        from services.v194_quote_service import v194_readiness_check

        status = v194_readiness_check(force=_env_truthy("V194_READY_FORCE"))
    elif _active_pricing_model_version() == "v193_1":
        from services.v193_1_quote_service import v1931_readiness_check

        status = v1931_readiness_check(force=_env_truthy("V193_1_READY_FORCE"))
    elif _active_pricing_model_version() == "v193":
        from services.v193_quote_service import v193_readiness_check

        status = v193_readiness_check(force=_env_truthy("V193_READY_FORCE"))
    elif _active_pricing_model_version() == "v192_16":
        from services.v192_16_quote_service import v19216_readiness_check

        status = v19216_readiness_check(force=_env_truthy("V19216_READY_FORCE"))
    elif _active_pricing_model_version() == "v192_15":
        from services.v192_15_quote_service import v19215_readiness_check

        status = v19215_readiness_check(force=_env_truthy("V19215_READY_FORCE"))
    elif _active_pricing_model_version() == "v192_14":
        from services.v192_14_quote_service import v19214_readiness_check

        status = v19214_readiness_check(force=_env_truthy("V19214_READY_FORCE"))
    elif _active_pricing_model_version() == "v192_9":
        from services.v192_9_quote_service import v1929_readiness_check

        status = v1929_readiness_check(
            load_engine=_env_truthy("V1929_READY_LOAD_ENGINE")
        )
    elif _active_pricing_model_version() == "v192_10":
        from services.v192_10_quote_service import v19210_readiness_check

        status = v19210_readiness_check(force=_env_truthy("V19210_READY_FORCE"))
    else:
        from services.v192_11_quote_service import v19211_readiness_check

        status = v19211_readiness_check(force=_env_truthy("V19211_READY_FORCE"))
    return jsonify(status), 200 if status.get("ready") else 503


@app.route('/api/industry-daily-report', methods=['POST'])
def api_industry_daily_report():
    """汽车行业日报由运营上传/预生成，前端用户不再触发在线生成。"""
    if os.environ.get("ALLOW_INDUSTRY_REPORT_GENERATE") != "1":
        return jsonify({"success": False, "error": "汽车行业日报由运营上传，当前不支持用户在线生成。"}), 403
    try:
        payload = request.get_json(silent=True) or {}
        from industry_daily_report import generate_industry_daily_report

        result = generate_industry_daily_report(
            date=payload.get("date") or "yesterday",
            output=payload.get("output") or "outputs/daily_report_yesterday.pdf",
            start_date=payload.get("startDate") or payload.get("start_date"),
            end_date=payload.get("endDate") or payload.get("end_date"),
            yiche_screenshot=payload.get("yicheScreenshot") or payload.get("yiche_screenshot"),
            autohome_listings=payload.get("autohomeListings") or payload.get("autohome_listings"),
            guazi_listings=payload.get("guaziListings") or payload.get("guazi_listings"),
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/industry-daily-report/list', methods=['GET'])
def api_industry_daily_report_list():
    """列出运营已上传的汽车行业日报产物，供价格管理模块展示。"""
    outputs_dir = os.path.join(_project_root(), "outputs")
    uploaded_dir = os.path.join(_project_root(), "uploaded_reports")
    rows = {}

    def add_report_files(storage_dir):
        if not os.path.isdir(storage_dir):
            return
        for stored_filename in sorted(os.listdir(storage_dir), reverse=True):
            filename = stored_filename[:-4] if stored_filename.endswith(".b64") else stored_filename
            if not filename.startswith("daily_report_"):
                continue
            if not filename.lower().endswith((".pdf", ".html", ".md", ".xlsx")):
                continue
            date_match = re.search(r"(\d{4}-\d{2}-\d{2}|yesterday)", filename)
            report_date = date_match.group(1) if date_match else "unknown"
            entry = rows.setdefault(report_date, {"date": report_date, "files": {}})
            ext = filename.rsplit(".", 1)[-1].lower()
            kind = "sources_xlsx" if filename.startswith("daily_report_sources_") else ext
            path = os.path.join(storage_dir, stored_filename)
            entry["files"][kind] = {
                "filename": filename,
                "url": f"/api/industry-daily-report/file/{filename}",
                "size": os.path.getsize(path),
                "updatedAt": datetime.fromtimestamp(os.path.getmtime(path), timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
            }

    add_report_files(outputs_dir)
    add_report_files(uploaded_dir)

    reports = sorted(rows.values(), key=lambda item: item["date"], reverse=True)
    requested_date = str(request.args.get("date") or "").strip()
    if requested_date:
        exact_reports = [item for item in reports if item.get("date") == requested_date]
        return jsonify({
            "success": True,
            "reports": exact_reports,
            "requested_date": requested_date,
            "exact_match": bool(exact_reports),
            "available_dates": [item.get("date") for item in reports if item.get("date") != "unknown"],
        })
    return jsonify({"success": True, "reports": reports, "requested_date": None, "exact_match": None})


@app.route('/api/industry-daily-report/content', methods=['GET'])
def api_industry_daily_report_content():
    """Return extracted, source-bound report sections for Agent cards and Q&A."""
    report_date = str(request.args.get("date") or "").strip()
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", report_date):
        return jsonify({"success": False, "error": "date must be YYYY-MM-DD"}), 400
    from services.daily_report_content_service import DailyReportContentService

    payload = DailyReportContentService(Path(_project_root())).card_payload(report_date)
    if payload is None:
        return jsonify({"success": False, "error": "日报原文不存在或无法抽取", "report_date": report_date}), 404
    return jsonify({"success": True, "content": payload})


@app.route('/api/industry-daily-report/file/<path:filename>', methods=['GET'])
def api_industry_daily_report_file(filename):
    """下载/预览日报文件，只允许访问 outputs 或 uploaded_reports 下的日报产物。"""
    if "/" in filename or "\\" in filename or not filename.startswith("daily_report_"):
        return jsonify({"success": False, "error": "非法文件名"}), 400
    outputs_dir = os.path.join(_project_root(), "outputs")
    uploaded_dir = os.path.join(_project_root(), "uploaded_reports")
    full_path = os.path.abspath(os.path.join(outputs_dir, filename))
    if full_path.startswith(os.path.abspath(outputs_dir) + os.sep) and os.path.isfile(full_path):
        return send_from_directory(outputs_dir, filename, as_attachment=False)

    uploaded_plain_path = os.path.abspath(os.path.join(uploaded_dir, filename))
    if uploaded_plain_path.startswith(os.path.abspath(uploaded_dir) + os.sep) and os.path.isfile(uploaded_plain_path):
        return send_from_directory(uploaded_dir, filename, as_attachment=False)

    uploaded_b64_path = os.path.abspath(os.path.join(uploaded_dir, filename + ".b64"))
    if uploaded_b64_path.startswith(os.path.abspath(uploaded_dir) + os.sep) and os.path.isfile(uploaded_b64_path):
        with open(uploaded_b64_path, "rb") as f:
            payload = base64.b64decode(f.read())
        mimetype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return Response(
            payload,
            mimetype=mimetype,
            headers={"Content-Disposition": f'inline; filename="{filename}"'}
        )

    return jsonify({"success": False, "error": "文件不存在"}), 404


@app.route('/api/market-report/file/<path:filename>', methods=['GET'])
def api_market_report_file(filename):
    """预览离线生成的全国行情 PDF，只允许 national_market_ 安全产物。"""
    if (
        "/" in filename
        or "\\" in filename
        or not filename.startswith("national_market_")
        or not filename.lower().endswith(".pdf")
    ):
        return jsonify({"success": False, "error": "非法文件名"}), 400
    uploaded_dir = os.path.join(_project_root(), "uploaded_reports")
    plain_path = os.path.abspath(os.path.join(uploaded_dir, filename))
    if plain_path.startswith(os.path.abspath(uploaded_dir) + os.sep) and os.path.isfile(plain_path):
        return send_from_directory(uploaded_dir, filename, as_attachment=False)
    b64_path = plain_path + ".b64"
    if b64_path.startswith(os.path.abspath(uploaded_dir) + os.sep) and os.path.isfile(b64_path):
        with open(b64_path, "rb") as handle:
            payload = base64.b64decode(handle.read())
        return Response(payload, mimetype="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})
    return jsonify({"success": False, "error": "文件不存在"}), 404


def _preload_active_pricing_service() -> None:
    """Warm heavy pricing artifacts before accepting the first user request."""
    if not _env_truthy("PRICING_PRELOAD_SERVICE", "1"):
        return
    active_version = _active_pricing_model_version()
    if active_version != "v194":
        return
    started = time.perf_counter()
    print("[pricing] 预热 v194 估价服务...")
    try:
        from services.v194_quote_service import get_service, warm_fast_serving_assets

        if _env_truthy("DEPLOY_LITE_MODE"):
            summary = warm_fast_serving_assets()
            if summary.get("errors"):
                print(f"[pricing] 轻量估价资产部分预热失败: {summary['errors']}")
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            print(f"[pricing] 轻量估价资产预热完成: {elapsed_ms}ms, {summary.get('warmed')}")
            return

        service = get_service(force_reload=False)
        warm_quote_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        warm_payloads = [
            {
                "request_id": "startup_warmup_c2b",
                "pricing_task": "c2b_purchase",
                "brand": "红旗",
                "series": "红旗HS5",
                "model_year": "2019",
                "trim": "2.0T 智联旗享四驱版",
                "model": "2.0T 智联旗享四驱版",
                "reg_date": "2021-08-27",
                "mileage_wan_km": 2.11,
                "transfer_count": 0,
                "city": "武汉",
                "color": "其他",
                "energy_type": "燃油车",
                "inspection_grade": "A",
                "inspection_score": 90,
                "quote_time": warm_quote_time,
            },
            {
                "request_id": "startup_warmup_b2c",
                "pricing_task": "b2c_sale",
                "brand": "特斯拉",
                "series": "Model 3",
                "model_year": "2022",
                "trim": "后轮驱动版",
                "model": "后轮驱动版",
                "reg_date": "2023-06-01",
                "mileage_wan_km": 2.81,
                "transfer_count": 0,
                "city": "深圳",
                "color": "黑色",
                "energy_type": "纯电动",
                "inspection_grade": "B",
                "inspection_score": 88,
                "b2c_listing_price_yuan": 145000,
                "quote_time": warm_quote_time,
            },
        ]
        for payload in warm_payloads:
            service.quote(payload)
    except Exception as exc:
        print(f"[pricing] v194 估价服务预热失败，将在首个请求时重试: {exc}")
        return
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    print(f"[pricing] v194 估价服务预热完成: {elapsed_ms}ms")


def _start_background_pricing_preload() -> None:
    if not _env_truthy("PRICING_BACKGROUND_PRELOAD", "0"):
        return
    thread = threading.Thread(
        target=_preload_active_pricing_service,
        name="pricing-fast-assets-preload",
        daemon=True,
    )
    thread.start()


def _preload_selection_service() -> None:
    """Warm shared selection datasets and ranking indexes for the first tester."""
    if not _env_truthy("SELECTION_PRELOAD_SERVICE", "1"):
        return
    started = time.perf_counter()
    print("[selection] 预热选品行情、经营指标与排行榜索引...")
    try:
        from services.selection_tools_service import SelectionToolsService

        service = SelectionToolsService()
        warm_scopes = (
            ("全国", "推荐值得收的车"),
            ("北京", "推荐值得收的车"),
            ("重庆", "推荐值得收的车"),
            ("合肥", "推荐值得收的车"),
            ("武汉", "推荐值得收的车"),
        )
        for city, query in warm_scopes:
            service.run(query, city, {})
    except Exception as exc:
        print(f"[selection] 选品预热失败，将在首个请求时重试: {exc}")
        return
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    print(f"[selection] 选品预热完成: {elapsed_ms}ms")


def _start_background_selection_preload() -> None:
    if not _env_truthy("SELECTION_BACKGROUND_PRELOAD", "1"):
        return
    thread = threading.Thread(
        target=_preload_selection_service,
        name="selection-datasets-preload",
        daemon=True,
    )
    thread.start()


if __name__ != "__main__":
    _start_background_pricing_preload()
    _start_background_selection_preload()


if __name__ == '__main__':
    host = os.environ.get('APP_HOST', '127.0.0.1')
    port = int(os.environ.get('APP_PORT', '5001'))
    ssl_mode = (os.environ.get('APP_SSL') or '').strip().lower()
    ssl_context = 'adhoc' if ssl_mode in {'1', 'true', 'yes', 'adhoc'} else None
    scheme = 'https' if ssl_context else 'http'

    print("启动定价服务...")
    _preload_active_pricing_service()
    _start_background_selection_preload()
    print(f"访问地址: {scheme}://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}/")
    if host == '0.0.0.0':
        print("局域网演示模式已开启：请使用本机局域网 IP 访问。")
        print("语音识别需要 HTTPS；如浏览器提示证书风险，演示环境中选择继续访问即可。")
    app.run(host=host, port=port, debug=False, ssl_context=ssl_context)
