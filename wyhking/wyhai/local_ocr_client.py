#!/usr/bin/env python3
"""Local offline OCR client based on RapidOCR."""

import os
import tempfile


class LocalOcrError(RuntimeError):
    """Raised when local OCR is unavailable or fails."""


_OCR_ENGINE = None


def get_local_ocr_config() -> dict:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        available = True
    except Exception:
        available = False
    return {
        "provider": "rapidocr",
        "model": "rapidocr_onnxruntime",
        "available": available,
        "offline": True,
    }


def _get_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:
        raise LocalOcrError(
            "本地 OCR 依赖未安装。请安装 rapidocr_onnxruntime 后再试。"
        ) from exc

    _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def _normalize_ocr_result(result) -> list:
    if result is None:
        return []
    # RapidOCR 1.x returns (ocr_result, elapsed), while some versions may
    # return the OCR result directly.
    if isinstance(result, tuple) and result:
        result = result[0]
    if not result:
        return []

    lines = []
    for item in result:
        text = ""
        score = None
        box = None
        if isinstance(item, (list, tuple)):
            if len(item) >= 2:
                box = item[0]
                text = str(item[1] or "").strip()
            if len(item) >= 3:
                score = item[2]
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("DetectedText") or "").strip()
            score = item.get("score") or item.get("confidence")
            box = item.get("box") or item.get("polygon")
        else:
            text = str(item).strip()

        if text:
            lines.append({
                "text": text,
                "confidence": score,
                "polygon": box,
            })
    return lines


def recognize_image_bytes(image_bytes: bytes, filename: str = "") -> dict:
    if not image_bytes:
        raise LocalOcrError("图片内容为空。")

    suffix = os.path.splitext(filename or "")[1].lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        suffix = ".png"

    engine = _get_engine()
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_file.write(image_bytes)
            temp_path = temp_file.name

        result = engine(temp_path)
        lines = _normalize_ocr_result(result)
        full_text = "\n".join(line["text"] for line in lines).strip()
        return {
            "text": full_text,
            "lines": lines,
            "engine": "rapidocr",
            "model": "rapidocr_onnxruntime",
            "filename": filename,
        }
    except LocalOcrError:
        raise
    except Exception as exc:
        raise LocalOcrError(f"本地 OCR 识别失败：{exc}") from exc
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass
