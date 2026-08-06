import asyncio
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import unicodedata
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import state

router = APIRouter(tags=["media"])

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg", ".opus"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}

IMAGE_INPUT_MAX_BYTES = int(os.getenv("MEDIA_IMAGE_INPUT_MAX_BYTES", str(10 * 1024 * 1024)))
IMAGE_OUTPUT_MAX_BYTES = int(os.getenv("MEDIA_IMAGE_OUTPUT_MAX_BYTES", str(1 * 1024 * 1024)))
AUDIO_OUTPUT_MAX_BYTES = int(os.getenv("MEDIA_AUDIO_OUTPUT_MAX_BYTES", str(30 * 1024 * 1024)))
VIDEO_OUTPUT_MAX_BYTES = int(os.getenv("MEDIA_VIDEO_OUTPUT_MAX_BYTES", str(100 * 1024 * 1024)))
SIGNED_URL_TTL_SECONDS = int(os.getenv("MEDIA_SIGNED_URL_TTL_SECONDS", "3600"))
TRANSFER_TTL_SECONDS = int(os.getenv("MEDIA_TRANSFER_TTL_SECONDS", "3600"))
MEDIA_TTL_HOURS = int(os.getenv("MEDIA_TTL_HOURS", "24"))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("MEDIA_CLEANUP_INTERVAL_SECONDS", "3600"))

_cleanup_task: asyncio.Task | None = None


class PrepareDownloadRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class TransferAckRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    bytes_written: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    dest_path: str = Field(min_length=1, max_length=512)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_database() -> None:
    if not state.db_pool:
        raise HTTPException(status_code=503, detail="PostgreSQL is required for media operations")


def _safe_title(value: str) -> str:
    title = unicodedata.normalize("NFC", (value or "").strip())
    title = " ".join(title.split())
    if not title:
        raise HTTPException(status_code=400, detail="Media title is required")
    if len(title) > 160:
        raise HTTPException(status_code=400, detail="Media title is too long")
    return title


def _safe_stem(value: str) -> str:
    value = unicodedata.normalize("NFC", value.strip())
    if not value or value in {".", ".."} or "/" in value or "\\" in value or ".." in value:
        raise HTTPException(status_code=400, detail="Invalid filename")
    stem = Path(value).stem
    clean = "".join("_" if ord(ch) < 32 or ch in '<>:"/\\|?*' else ch for ch in stem)
    clean = re.sub(r"\s+", " ", clean).strip(" ._-")
    if not clean:
        clean = "media"
    return clean[:96].rstrip(" .") or "media"


def _search_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).casefold()
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^\w]+", " ", without_marks, flags=re.UNICODE).split())


def _media_type_for_extension(extension: str) -> str:
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    raise HTTPException(status_code=400, detail=f"Unsupported media extension: {extension or '(none)'}")


def _input_limit(media_type: str) -> int:
    if media_type == "image":
        return IMAGE_INPUT_MAX_BYTES
    return AUDIO_OUTPUT_MAX_BYTES if media_type == "audio" else VIDEO_OUTPUT_MAX_BYTES


def _output_limit(media_type: str) -> int:
    return {
        "image": IMAGE_OUTPUT_MAX_BYTES,
        "audio": AUDIO_OUTPUT_MAX_BYTES,
        "video": VIDEO_OUTPUT_MAX_BYTES,
    }[media_type]


def _output_extension(media_type: str) -> str:
    return {"image": ".png", "audio": ".mp3", "video": ".avi"}[media_type]


def _destination_path(media_type: str, filename: str) -> str:
    folder = {"image": "images", "audio": "music", "video": "videos"}[media_type]
    return f"/sdcard/{folder}/{filename}"


def _s3_client():
    bucket = os.getenv("R2_BUCKET", os.getenv("S3_BUCKET", "")).strip()
    access_key = os.getenv("R2_ACCESS_KEY_ID", os.getenv("S3_ACCESS_KEY_ID", "")).strip()
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY", os.getenv("S3_SECRET_ACCESS_KEY", "")).strip()
    endpoint = os.getenv("R2_ENDPOINT_URL", os.getenv("S3_ENDPOINT_URL", "")).strip()
    if not bucket or not access_key or not secret_key or not endpoint:
        raise HTTPException(status_code=503, detail="Cloudflare R2 environment is not configured")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.getenv("R2_REGION", "auto"),
        config=Config(signature_version="s3v4"),
    )
    return client, bucket


async def init_store() -> None:
    if not state.db_pool:
        state.logger.error("[MEDIA] PostgreSQL unavailable; media feature is disabled")
        return
    async with state.db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS media_files (
                media_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_key TEXT NOT NULL,
                size BIGINT NOT NULL,
                sha256 TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        for statement in (
            "ALTER TABLE media_files ADD COLUMN IF NOT EXISTS title TEXT",
            "ALTER TABLE media_files ADD COLUMN IF NOT EXISTS search_title TEXT",
            "ALTER TABLE media_files ADD COLUMN IF NOT EXISTS dest_filename TEXT",
            "ALTER TABLE media_files ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'ready'",
            "ALTER TABLE media_files ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ",
            "ALTER TABLE media_files ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ",
            "ALTER TABLE media_files ADD COLUMN IF NOT EXISTS error TEXT",
        ):
            await conn.execute(statement)
        await conn.execute("""
            UPDATE media_files
            SET title = COALESCE(title, original_name),
                search_title = COALESCE(search_title, LOWER(original_name)),
                dest_filename = COALESCE(dest_filename, original_name),
                expires_at = COALESCE(expires_at, created_at + ($1 * INTERVAL '1 hour'))
            WHERE title IS NULL OR search_title IS NULL OR dest_filename IS NULL OR expires_at IS NULL
        """, MEDIA_TTL_HOURS)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS media_transfers (
                transfer_id TEXT PRIMARY KEY,
                media_id TEXT NOT NULL REFERENCES media_files(media_id),
                token_hash TEXT NOT NULL,
                dest_path TEXT NOT NULL,
                expected_size BIGINT NOT NULL,
                expected_sha256 TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'prepared',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL,
                ack_at TIMESTAMPTZ,
                bytes_written BIGINT,
                error TEXT
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_media_search ON media_files(search_title)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_media_cleanup ON media_files(status, expires_at)")
    state.logger.info("[MEDIA] PostgreSQL media tables are ready")


async def start_cleanup() -> None:
    global _cleanup_task
    if not state.db_pool or _cleanup_task:
        return
    await cleanup_expired_media()
    _cleanup_task = asyncio.create_task(_cleanup_loop(), name="media-r2-cleanup")


async def stop_cleanup() -> None:
    global _cleanup_task
    task, _cleanup_task = _cleanup_task, None
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            await cleanup_expired_media()
        except Exception:
            state.logger.exception("[MEDIA] Periodic cleanup failed")


async def _copy_upload(upload: UploadFile, destination: Path, limit: int) -> int:
    total = 0
    with destination.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                raise HTTPException(status_code=413, detail=f"Input exceeds {limit} bytes")
            output.write(chunk)
    if total == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return total


def _run_json_command(command: list[str], label: str) -> dict[str, Any]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=422, detail=f"{label} timed out") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f"{label} failed")[-1200:]
        raise HTTPException(status_code=422, detail=f"{label} failed: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"{label} returned invalid JSON") from exc


async def _probe(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise HTTPException(status_code=503, detail="ffprobe is required")
    return await asyncio.to_thread(
        _run_json_command,
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        "ffprobe",
    )


def _verify_input_probe(probe: dict[str, Any], media_type: str) -> None:
    streams = probe.get("streams") or []
    video_streams = [item for item in streams if item.get("codec_type") == "video"]
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    format_name = str((probe.get("format") or {}).get("format_name", ""))
    still_image = any(name in format_name for name in ("image2", "png_pipe", "jpeg_pipe"))
    decoded_image = any(
        item.get("codec_name") in {"png", "mjpeg"}
        and int(item.get("width", 0)) > 0
        and int(item.get("height", 0)) > 0
        for item in video_streams
    )
    decoded_video = any(int(item.get("width", 0)) > 0 and int(item.get("height", 0)) > 0 for item in video_streams)
    valid = (
        media_type == "image" and still_image and decoded_image
        or media_type == "audio" and bool(audio_streams) and not video_streams
        or media_type == "video" and decoded_video and not still_image
    )
    if not valid:
        raise HTTPException(status_code=400, detail="File content does not match its media extension")


def _run_ffmpeg(command: list[str]) -> None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=422, detail="ffmpeg conversion timed out") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "ffmpeg failed")[-1200:]
        raise HTTPException(status_code=422, detail=f"ffmpeg conversion failed: {detail}")


async def _normalize_media(source: Path, destination: Path, media_type: str, title: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(status_code=503, detail="ffmpeg is required")
    command = [ffmpeg, "-y", "-i", str(source)]
    if media_type == "image":
        command += ["-vf", "scale=240:320:force_original_aspect_ratio=decrease", "-frames:v", "1"]
    elif media_type == "audio":
        command += ["-vn", "-c:a", "libmp3lame", "-b:a", "128k", "-metadata", f"title={title}"]
    else:
        command += [
            "-vf", "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2",
            "-r", "15", "-c:v", "mjpeg", "-q:v", "5",
            "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1",
        ]
    command.append(str(destination))
    await asyncio.to_thread(_run_ffmpeg, command)


def _verify_output_probe(probe: dict[str, Any], media_type: str) -> None:
    streams = probe.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if media_type == "image":
        valid = video and video.get("codec_name") == "png" and int(video.get("width", 0)) <= 240 and int(video.get("height", 0)) <= 320
    elif media_type == "audio":
        valid = audio and audio.get("codec_name") == "mp3" and not video
    else:
        valid = video and video.get("codec_name") == "mjpeg" and int(video.get("width", 0)) == 320 and int(video.get("height", 0)) == 240
        if audio:
            valid = valid and audio.get("codec_name") == "pcm_s16le" and int(audio.get("sample_rate", 0)) == 16000 and int(audio.get("channels", 0)) == 1
    if not valid:
        raise HTTPException(status_code=422, detail="Normalized media does not match the SD playback format")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as media_file:
        for chunk in iter(lambda: media_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _upload_object(path: Path, key: str) -> None:
    client, bucket = _s3_client()
    await asyncio.to_thread(
        client.upload_file,
        str(path),
        bucket,
        key,
        ExtraArgs={"ContentType": mimetypes.guess_type(path.name)[0] or "application/octet-stream"},
    )


async def _delete_object(key: str) -> None:
    client, bucket = _s3_client()
    await asyncio.to_thread(client.delete_object, Bucket=bucket, Key=key)


def _signed_url(key: str) -> str:
    client, bucket = _s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=SIGNED_URL_TTL_SECONDS,
    )


def _format_row(row: Any) -> dict[str, Any]:
    result = dict(row)
    for key, value in list(result.items()):
        if isinstance(value, datetime):
            result[key] = value.isoformat()
    return result


def _resolve_candidates(rows: list[Any], query: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    key = _search_key(query)
    formatted = [_format_row(row) for row in rows]
    exact = [row for row in formatted if row.get("search_title") == key]
    matches = exact or [row for row in formatted if key in str(row.get("search_title", ""))]
    if not matches and formatted:
        matches = formatted
    if len(matches) == 1:
        return matches[0], []
    return None, [
        {"media_id": row["media_id"], "title": row["title"], "type": row["type"]}
        for row in matches[:10]
    ]


def _validate_ack(row: Any, payload: TransferAckRequest) -> None:
    supplied_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(supplied_hash, row["token_hash"]):
        raise HTTPException(status_code=403, detail="Invalid ACK token")
    if payload.bytes_written != row["expected_size"]:
        raise HTTPException(status_code=409, detail="ACK size does not match expected size")
    if not hmac.compare_digest(payload.sha256.lower(), row["expected_sha256"].lower()):
        raise HTTPException(status_code=409, detail="ACK SHA-256 does not match expected hash")
    if payload.dest_path != row["dest_path"]:
        raise HTTPException(status_code=409, detail="ACK destination path does not match ticket")


@router.post("/api/admin/media/upload")
async def upload_media(file: UploadFile = File(...), title: str | None = Form(default=None)) -> dict[str, Any]:
    _require_database()
    original_name = unicodedata.normalize("NFC", file.filename or "")
    if not original_name or "/" in original_name or "\\" in original_name:
        raise HTTPException(status_code=400, detail="Invalid upload filename")
    extension = Path(original_name).suffix.lower()
    media_type = _media_type_for_extension(extension)
    media_id = str(uuid.uuid4())
    resolved_title = _safe_title(title or Path(original_name).stem)
    output_name = f"{_safe_stem(resolved_title)}-{media_id[:8]}{_output_extension(media_type)}"
    object_key = f"media/{media_id}/{output_name}"
    uploaded = False

    try:
        with tempfile.TemporaryDirectory(prefix="media-upload-") as temp_directory:
            temp = Path(temp_directory)
            source = temp / f"source{extension}"
            output = temp / output_name
            await _copy_upload(file, source, _input_limit(media_type))
            input_probe = await _probe(source)
            _verify_input_probe(input_probe, media_type)
            await _normalize_media(source, output, media_type, resolved_title)
            output_size = output.stat().st_size
            if output_size <= 0 or output_size > _output_limit(media_type):
                raise HTTPException(status_code=413, detail=f"Normalized output exceeds {_output_limit(media_type)} bytes")
            output_probe = await _probe(output)
            _verify_output_probe(output_probe, media_type)
            digest = await asyncio.to_thread(_sha256_file, output)
            await _upload_object(output, object_key)
            uploaded = True

        created_at = _now()
        expires_at = created_at + timedelta(hours=MEDIA_TTL_HOURS)
        async with state.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO media_files
                    (media_id, title, search_title, type, original_name, stored_key, dest_filename,
                     size, sha256, status, created_at, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'ready', $10, $11)
                RETURNING *
            """, media_id, resolved_title, _search_key(resolved_title), media_type, original_name,
                object_key, output_name, output_size, digest, created_at, expires_at)
        return {"success": True, "media": _format_row(row)}
    except Exception:
        if uploaded:
            with suppress(Exception):
                await _delete_object(object_key)
        raise
    finally:
        await file.close()


@router.get("/api/admin/media")
async def list_media() -> dict[str, Any]:
    _require_database()
    async with state.db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM media_files ORDER BY created_at DESC")
    return {"media": [_format_row(row) for row in rows]}


@router.delete("/api/admin/media/{media_id}")
async def delete_media(media_id: str) -> dict[str, Any]:
    _require_database()
    async with state.db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM media_files WHERE media_id = $1", media_id)
    if not row:
        raise HTTPException(status_code=404, detail="Media not found")
    if row["status"] not in {"consumed", "expired"}:
        try:
            await _delete_object(row["stored_key"])
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to delete R2 object: {exc}") from exc
    async with state.db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM media_transfers WHERE media_id = $1", media_id)
            await conn.execute("DELETE FROM media_files WHERE media_id = $1", media_id)
    return {"success": True, "media_id": media_id}


@router.post("/api/media/prepare-download")
async def prepare_download(payload: PrepareDownloadRequest) -> dict[str, Any]:
    _require_database()
    state.logger.info(f"[MEDIA] Nhận yêu cầu chuẩn bị tải (prepare-download) cho query: '{payload.query}'")
    public_base_url = os.getenv("MEDIA_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not public_base_url:
        state.logger.error("[MEDIA] MEDIA_PUBLIC_BASE_URL chưa được cấu hình!")
        raise HTTPException(status_code=503, detail="MEDIA_PUBLIC_BASE_URL is required")
    query_key = _search_key(payload.query)
    if not query_key:
        raise HTTPException(status_code=400, detail="Query is empty after normalization")

    type_filter = None
    if query_key in ("image", "anh", "hinh anh", "hinh", "photo"):
        type_filter = "image"
    elif query_key in ("audio", "music", "nhac", "am thanh", "song"):
        type_filter = "audio"
    elif query_key in ("video", "vid", "phim", "clip", "movie"):
        type_filter = "video"

    async with state.db_pool.acquire() as conn:
        if type_filter:
            rows = await conn.fetch("""
                SELECT * FROM media_files
                WHERE status = 'ready' AND expires_at > NOW()
                  AND (type = $2 OR search_title = $1 OR search_title LIKE '%' || $1 || '%')
                ORDER BY created_at DESC
                LIMIT 20
            """, query_key, type_filter)
        else:
            rows = await conn.fetch("""
                SELECT * FROM media_files
                WHERE status = 'ready' AND expires_at > NOW()
                  AND (search_title = $1 OR search_title LIKE '%' || $1 || '%')
                ORDER BY created_at DESC
                LIMIT 20
            """, query_key)
    media, candidates = _resolve_candidates(list(rows), payload.query)
    if not media:
        if candidates:
            state.logger.warning(f"[MEDIA] Từ khóa '{payload.query}' bị trùng lặp giữa các kết quả: {[c['title'] for c in candidates]}")
            return {"success": False, "error": "ambiguous", "candidates": candidates}
        state.logger.warning(f"[MEDIA] Không tìm thấy media phù hợp cho từ khóa: '{payload.query}'")
        return {"success": False, "error": "not_found", "query": payload.query}

    transfer_id = str(uuid.uuid4())
    ack_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(ack_token.encode("utf-8")).hexdigest()
    dest_path = _destination_path(media["type"], media["dest_filename"])
    expires_at = _now() + timedelta(seconds=TRANSFER_TTL_SECONDS)
    async with state.db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO media_transfers
                (transfer_id, media_id, token_hash, dest_path, expected_size, expected_sha256, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, transfer_id, media["media_id"], token_hash, dest_path, media["size"], media["sha256"], expires_at)

    state.logger.info(
        f"[MEDIA] Khởi tạo ticket tải thành công! "
        f"Media: '{media['title']}' ({media['type']}) | "
        f"Kích thước: {media['size']} bytes | "
        f"Đường dẫn đích trên SD Card: '{dest_path}' | "
        f"Transfer ID: {transfer_id}"
    )

    arguments = {
        "url": _signed_url(media["stored_key"]),
        "dest_path": dest_path,
        "expected_size": media["size"],
        "sha256": media["sha256"],
        "transfer_id": transfer_id,
        "ack_url": f"{public_base_url}/api/media/transfers/{transfer_id}/ack",
        "ack_token": ack_token,
    }
    return {
        "success": True,
        "media": {"media_id": media["media_id"], "title": media["title"], "type": media["type"]},
        "required_next_call": "self.sdcard.download_file",
        "arguments": arguments,
        "expires_at": expires_at.isoformat(),
    }


@router.post("/api/media/transfers/{transfer_id}/ack")
async def acknowledge_transfer(transfer_id: str, payload: TransferAckRequest) -> dict[str, Any]:
    _require_database()
    state.logger.info(f"[MEDIA] Nhận ACK từ ESP32 cho Transfer ID: {transfer_id}")
    async with state.db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT t.*, m.stored_key, m.status AS media_status
            FROM media_transfers t
            JOIN media_files m ON m.media_id = t.media_id
            WHERE t.transfer_id = $1
        """, transfer_id)
    if not row:
        state.logger.error(f"[MEDIA] Không tìm thấy ticket tải (Transfer ID: {transfer_id}) trong database.")
        raise HTTPException(status_code=404, detail="Transfer not found")
    if row["status"] == "success":
        state.logger.info(f"[MEDIA] ACK bị trùng lặp (đã xác thực thành công trước đó) cho Transfer ID: {transfer_id}")
        return {"success": True, "idempotent": True, "transfer_id": transfer_id}
    if row["expires_at"] <= _now():
        state.logger.error(f"[MEDIA] Ticket tải Transfer ID: {transfer_id} đã hết hạn vào {row['expires_at'].isoformat()}.")
        raise HTTPException(status_code=410, detail="Transfer ticket expired")

    try:
        _validate_ack(row, payload)
    except HTTPException as exc:
        state.logger.error(f"[MEDIA] Xác thực ACK lỗi: {exc.detail}")
        raise exc

    try:
        await _delete_object(row["stored_key"])
    except Exception as exc:
        state.logger.exception(f"[MEDIA] Xác thực file thành công nhưng dọn dẹp R2 object thất bại: {exc}")
        async with state.db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE media_transfers SET status = 'cleanup_pending', error = $2 WHERE transfer_id = $1", transfer_id, str(exc))
                await conn.execute("UPDATE media_files SET status = 'cleanup_pending', error = $2 WHERE media_id = $1", row["media_id"], str(exc))
        raise HTTPException(status_code=502, detail="File verified but R2 cleanup failed; ACK may be retried") from exc

    async with state.db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""
                UPDATE media_transfers
                SET status = 'success', ack_at = NOW(), bytes_written = $2, error = NULL
                WHERE transfer_id = $1
            """, transfer_id, payload.bytes_written)
            await conn.execute("""
                UPDATE media_files SET status = 'consumed', consumed_at = NOW(), error = NULL
                WHERE media_id = $1
            """, row["media_id"])

    state.logger.info(
        f"🎉 [MEDIA] ESP32 tải file và xác thực thành công! "
        f"Đường dẫn đích: '{payload.dest_path}' | "
        f"Kích thước đã ghi: {payload.bytes_written} bytes. "
        f"Đã xoá file nguồn trên R2 Cloud để tối ưu bộ nhớ."
    )
    return {"success": True, "idempotent": False, "transfer_id": transfer_id}


async def cleanup_expired_media() -> dict[str, int]:
    if not state.db_pool:
        return {"deleted": 0, "pending": 0}
    async with state.db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT media_id, stored_key FROM media_files
            WHERE status = 'cleanup_pending' OR (status = 'ready' AND expires_at <= NOW())
            ORDER BY expires_at ASC NULLS FIRST
        """)
        await conn.execute("UPDATE media_transfers SET status = 'expired' WHERE status = 'prepared' AND expires_at <= NOW()")
    deleted = 0
    pending = 0
    for row in rows:
        try:
            await _delete_object(row["stored_key"])
        except Exception as exc:
            pending += 1
            async with state.db_pool.acquire() as conn:
                await conn.execute("UPDATE media_files SET status = 'cleanup_pending', error = $2 WHERE media_id = $1", row["media_id"], str(exc))
            continue
        deleted += 1
        async with state.db_pool.acquire() as conn:
            await conn.execute("UPDATE media_files SET status = 'expired', error = NULL WHERE media_id = $1", row["media_id"])
    if deleted or pending:
        state.logger.info("[MEDIA] Cleanup complete: deleted=%d pending=%d", deleted, pending)
    return {"deleted": deleted, "pending": pending}
