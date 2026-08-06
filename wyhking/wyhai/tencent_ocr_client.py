#!/usr/bin/env python3
"""Tencent Cloud OCR client using TC3-HMAC-SHA256 signing."""

import base64
import datetime as _dt
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request


class TencentOcrError(RuntimeError):
    """Raised when Tencent Cloud OCR is not configured or returns an error."""


_LOCAL_CONFIG_CACHE = None
_LOCAL_CONFIG_SOURCE = ""


def _module_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _candidate_config_paths() -> list:
    paths = []
    explicit_path = os.environ.get("TENCENT_OCR_CONFIG")
    if explicit_path:
        paths.append(explicit_path)
    for root in {_module_dir(), os.getcwd()}:
        paths.extend([
            os.path.join(root, "tencent_ocr_config.json"),
            os.path.join(root, ".env"),
        ])
    seen = set()
    ordered = []
    for path in paths:
        if path and path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def _load_local_config() -> dict:
    global _LOCAL_CONFIG_CACHE, _LOCAL_CONFIG_SOURCE
    if _LOCAL_CONFIG_CACHE is not None:
        return _LOCAL_CONFIG_CACHE

    _LOCAL_CONFIG_CACHE = {}
    _LOCAL_CONFIG_SOURCE = ""
    for path in _candidate_config_paths():
        if not os.path.isfile(path):
            continue
        try:
            if path.endswith(".json"):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    _LOCAL_CONFIG_CACHE = {str(k): str(v).strip() for k, v in data.items() if v is not None}
                    _LOCAL_CONFIG_SOURCE = path
                    return _LOCAL_CONFIG_CACHE
            else:
                data = {}
                with open(path, "r", encoding="utf-8") as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        data[key.strip()] = value.strip().strip('"').strip("'")
                if data:
                    _LOCAL_CONFIG_CACHE = data
                    _LOCAL_CONFIG_SOURCE = path
                    return _LOCAL_CONFIG_CACHE
        except Exception:
            continue
    return _LOCAL_CONFIG_CACHE


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or _load_local_config().get(name) or default).strip()


def _setting(names: list, default: str = "") -> str:
    for name in names:
        value = _env(name)
        if value:
            return value
    return default


def get_tencent_ocr_config() -> dict:
    """Return the effective Tencent OCR configuration without exposing secrets."""
    secret_id = _setting(["TENCENTCLOUD_SECRET_ID", "TENCENT_SECRET_ID", "secret_id"])
    secret_key = _setting(["TENCENTCLOUD_SECRET_KEY", "TENCENT_SECRET_KEY", "secret_key"])
    return {
        "configured": bool(secret_id and secret_key),
        "endpoint": _setting(["TENCENTCLOUD_OCR_ENDPOINT", "endpoint"], "ocr.tencentcloudapi.com"),
        "action": _setting(["TENCENTCLOUD_OCR_ACTION", "action"], "GeneralAccurateOCR"),
        "version": _setting(["TENCENTCLOUD_OCR_VERSION", "version"], "2018-11-19"),
        "region": _setting(["TENCENTCLOUD_OCR_REGION", "region"], ""),
        "config_source": _LOCAL_CONFIG_SOURCE,
        "has_secret_id": bool(secret_id),
        "has_secret_key": bool(secret_key),
    }


def _build_headers(payload: str, action: str, version: str, endpoint: str, region: str) -> dict:
    secret_id = _setting(["TENCENTCLOUD_SECRET_ID", "TENCENT_SECRET_ID", "secret_id"])
    secret_key = _setting(["TENCENTCLOUD_SECRET_KEY", "TENCENT_SECRET_KEY", "secret_key"])
    if not secret_id or not secret_key:
        raise TencentOcrError(
            "腾讯云 OCR 未配置密钥。请设置 TENCENTCLOUD_SECRET_ID 和 TENCENTCLOUD_SECRET_KEY。"
        )

    service = "ocr"
    algorithm = "TC3-HMAC-SHA256"
    timestamp = int(time.time())
    date = _dt.datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")

    http_request_method = "POST"
    canonical_uri = "/"
    canonical_querystring = ""
    canonical_headers = (
        f"content-type:application/json; charset=utf-8\n"
        f"host:{endpoint}\n"
        f"x-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    hashed_request_payload = _sha256_hex(payload.encode("utf-8"))
    canonical_request = "\n".join([
        http_request_method,
        canonical_uri,
        canonical_querystring,
        canonical_headers,
        signed_headers,
        hashed_request_payload,
    ])

    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = "\n".join([
        algorithm,
        str(timestamp),
        credential_scope,
        _sha256_hex(canonical_request.encode("utf-8")),
    ])

    secret_date = _hmac_sha256(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _hmac_sha256(secret_date, service)
    secret_signing = _hmac_sha256(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"{algorithm} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json; charset=utf-8",
        "Host": endpoint,
        "X-TC-Action": action,
        "X-TC-Version": version,
        "X-TC-Timestamp": str(timestamp),
    }
    if region:
        headers["X-TC-Region"] = region
    return headers


def recognize_image_bytes(image_bytes: bytes, filename: str = "") -> dict:
    """Run Tencent Cloud OCR and return normalized text lines."""
    if not image_bytes:
        raise TencentOcrError("图片内容为空。")

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    if len(encoded) > 10 * 1024 * 1024:
        raise TencentOcrError("图片过大，Base64 后不能超过 10MB。请压缩后再上传。")

    config = get_tencent_ocr_config()
    action = config["action"]
    version = config["version"]
    endpoint = config["endpoint"]
    region = config["region"]

    payload = json.dumps({
        "ImageBase64": encoded,
        "ConfigID": "OCR",
        "EnableDetectText": True,
    }, ensure_ascii=False, separators=(",", ":"))
    headers = _build_headers(payload, action, version, endpoint, region)
    request = urllib.request.Request(
        f"https://{endpoint}",
        data=payload.encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise TencentOcrError(f"腾讯云 OCR 请求失败：HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise TencentOcrError(f"腾讯云 OCR 网络请求失败：{exc.reason}") from exc

    try:
        payload_obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TencentOcrError(f"腾讯云 OCR 返回了无法解析的响应：{raw[:300]}") from exc

    response = payload_obj.get("Response") or {}
    if "Error" in response:
        error = response["Error"]
        code = error.get("Code", "Unknown")
        message = error.get("Message", "")
        raise TencentOcrError(f"腾讯云 OCR 识别失败：{code} {message}".strip())

    detections = response.get("TextDetections") or []
    lines = []
    for item in detections:
        text = str(item.get("DetectedText") or "").strip()
        if text:
            lines.append({
                "text": text,
                "confidence": item.get("Confidence"),
                "polygon": item.get("Polygon") or item.get("ItemPolygon"),
            })

    full_text = "\n".join(line["text"] for line in lines).strip()
    return {
        "text": full_text,
        "lines": lines,
        "engine": "tencentcloud",
        "model": action,
        "request_id": response.get("RequestId", ""),
        "angle": response.get("Angle"),
        "filename": filename,
    }
