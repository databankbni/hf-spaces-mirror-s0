import os
import glob
import json
import time
import uuid
import threading
import subprocess

from flask import Blueprint, request, jsonify, render_template, send_file, abort
from werkzeug.utils import secure_filename

import queue_manager
from blueprints.video_downloader import downloader as vd_downloader

bp = Blueprint("transcript", __name__, url_prefix="/transcript")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("TRANSCRIPT_DATA_DIR", os.path.join(BASE_DIR, "..", "..", "data", "transcript"))
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
JOBS_DB_PATH = os.path.join(DATA_DIR, "jobs_db.json")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv"}
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "1024"))

WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "medium")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "id") or None

# A job that fails (or is interrupted by a server restart) gets retried
# automatically up to this many times before it's shown as a hard error.
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "2"))

# ---------------------------------------------------------------------------
# Job registry (in-memory + lightweight disk persistence so a restart
# doesn't wipe the job list the browser still has in localStorage)
# ---------------------------------------------------------------------------
STATUS_QUEUED = "queued"
STATUS_EXTRACTING = "extracting_audio"
STATUS_DOWNLOADING = "downloading_audio"
STATUS_TRANSCRIBING = "transcribing"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"

ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_EXTRACTING, STATUS_DOWNLOADING, STATUS_TRANSCRIBING)

jobs = {}
jobs_lock = threading.Lock()

# job_id -> subprocess.Popen for the ffmpeg step currently running, so a
# cancel request can terminate it immediately instead of waiting it out.
active_processes = {}
active_processes_lock = threading.Lock()

# job_ids with a pending cancel request. Checked at each cooperative
# checkpoint (after ffmpeg exits, between transcription segments).
cancel_flags = set()
cancel_lock = threading.Lock()


def request_cancel(job_id):
    with cancel_lock:
        cancel_flags.add(job_id)


def is_cancel_requested(job_id):
    with cancel_lock:
        return job_id in cancel_flags


def clear_cancel(job_id):
    with cancel_lock:
        cancel_flags.discard(job_id)


def _load_jobs():
    if not os.path.exists(JOBS_DB_PATH):
        return
    try:
        with open(JOBS_DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    for job_id, job in data.items():
        if job.get("status") in ACTIVE_STATUSES:
            # The process died mid-job (crash/restart/OOM). An uploaded
            # video still on disk, or a URL-sourced job (always re-
            # downloadable from scratch), can be requeued instead of
            # failing outright — this is what stops long-unattended jobs
            # from just "erroring themselves" after the user has walked away.
            retries = job.get("retries", 0)
            is_url_job = job.get("source") == "url"
            resumable = is_url_job or (bool(job.get("video_path")) and os.path.exists(job["video_path"]))
            if resumable and retries < MAX_RETRIES:
                job["status"] = STATUS_QUEUED
                job["progress"] = 0
                job["retries"] = retries + 1
                job["error"] = "Server sempat berhenti — video sedang diproses ulang secara otomatis."
                queue_manager.submit("transcript", job_id, job.get("filename"), _build_run_fn(job_id))
            else:
                job["status"] = STATUS_ERROR
                job["error"] = (
                    "File video sudah tidak ada lagi. Silakan upload ulang."
                    if not resumable
                    else "Proses berulang kali terhenti. Coba lagi atau upload ulang."
                )
        jobs[job_id] = job


def _save_jobs_locked():
    try:
        with open(JOBS_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(jobs, f)
    except Exception:
        pass


def update_job(job_id, **fields):
    with jobs_lock:
        if job_id not in jobs:
            return
        jobs[job_id].update(fields)
        _save_jobs_locked()


def get_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        return dict(job) if job else None


def get_job_brief(job_id):
    job = get_job(job_id)
    if not job:
        return None
    return {"status": job.get("status"), "progress": job.get("progress", 0), "filename": job.get("filename")}


# _load_jobs() is called at the bottom of this file, once _build_run_fn (which
# it needs) has been defined — see the comment there for why the ordering matters.

# ---------------------------------------------------------------------------
# Whisper model — loaded once, reused for every job
# ---------------------------------------------------------------------------
_model = None
_model_lock = threading.Lock()


def get_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            _model = WhisperModel(
                WHISPER_MODEL_SIZE,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
            )
        return _model


# ---------------------------------------------------------------------------
# Processing helpers
# ---------------------------------------------------------------------------
def extract_audio(job_id, video_path, audio_path):
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    with active_processes_lock:
        active_processes[job_id] = proc
    _, stderr = proc.communicate()
    with active_processes_lock:
        active_processes.pop(job_id, None)

    if is_cancel_requested(job_id):
        return  # caller checks the cancel flag and finalizes; don't raise
    if proc.returncode != 0 or not os.path.exists(audio_path):
        lines = [line for line in (stderr or "").splitlines() if line.strip()]
        tail = "\n".join(lines[-5:]) or "ffmpeg keluar tanpa pesan error."
        raise RuntimeError(f"ffmpeg gagal mengekstrak audio: {tail}")


def download_audio(job_id, url, dest_template):
    """Download the best audio stream straight to mp3 via yt-dlp for a
    URL-sourced job -- skips a redundant ffmpeg pass since yt-dlp's -x/
    --audio-format postprocessor already produces what faster-whisper needs.
    Streams progress and honors cancellation the same way extract_audio()
    does for ffmpeg, reusing the same active_processes/cancel machinery so
    a cancel mid-download terminates the yt-dlp process too."""
    cmd = vd_downloader.build_audio_download_command(url, dest_template)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    with active_processes_lock:
        active_processes[job_id] = proc
    tail_lines = []
    try:
        for line in proc.stdout:
            tail_lines.append(line)
            if len(tail_lines) > 40:
                tail_lines.pop(0)
            if is_cancel_requested(job_id):
                proc.terminate()
                break
            pct = vd_downloader.parse_progress_percent(line)
            if pct is not None:
                update_job(job_id, progress=int(pct))
        proc.wait()
    finally:
        with active_processes_lock:
            active_processes.pop(job_id, None)

    if is_cancel_requested(job_id):
        return None
    if proc.returncode != 0:
        raise vd_downloader.classify_error("".join(tail_lines))

    candidates = sorted(
        p for p in glob.glob(dest_template.replace("%(ext)s", "*"))
        if not p.endswith(".part") and not p.endswith(".ytdl")
    )
    return candidates[0] if candidates else None


def format_timestamp_srt(seconds):
    ms_total = int(round(seconds * 1000))
    hours, rem = divmod(ms_total, 3600000)
    minutes, rem = divmod(rem, 60000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def format_timestamp_short(seconds):
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def build_srt(segments):
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{format_timestamp_srt(seg['start'])} --> {format_timestamp_srt(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


def build_txt(segments):
    lines = []
    for seg in segments:
        start = format_timestamp_short(seg["start"])
        end = format_timestamp_short(seg["end"])
        lines.append(f"[{start} - {end}] {seg['text']}")
    return "\n".join(lines)


def _cleanup_glob(pattern):
    for path in glob.glob(pattern):
        try:
            os.remove(path)
        except OSError:
            pass


def finalize_cancelled(job_id, audio_path, extra_cleanup=None):
    if audio_path and os.path.exists(audio_path):
        os.remove(audio_path)
    if extra_cleanup:
        extra_cleanup()
    clear_cancel(job_id)
    update_job(job_id, status=STATUS_CANCELLED, progress=0, error=None)


def process_job(job_id):
    job = get_job(job_id)
    if job is None:
        return
    is_url_job = job.get("source") == "url"

    if is_cancel_requested(job_id):
        finalize_cancelled(job_id, None)
        return

    if is_url_job:
        update_job(job_id, status=STATUS_DOWNLOADING, progress=0)
        dest_template = os.path.join(OUTPUT_DIR, f"{job_id}_src.%(ext)s")
        audio_path = download_audio(job_id, job["url"], dest_template)
        if is_cancel_requested(job_id):
            finalize_cancelled(job_id, None, lambda: _cleanup_glob(os.path.join(OUTPUT_DIR, f"{job_id}_src.*")))
            return
        if not audio_path:
            raise RuntimeError("yt-dlp selesai tapi file audio hasil unduhan tidak ditemukan.")
    else:
        video_path = job["video_path"]
        audio_path = os.path.join(OUTPUT_DIR, f"{job_id}.wav")
        update_job(job_id, status=STATUS_EXTRACTING, progress=0)
        extract_audio(job_id, video_path, audio_path)
        if is_cancel_requested(job_id):
            finalize_cancelled(job_id, audio_path)
            return

    update_job(job_id, status=STATUS_TRANSCRIBING, progress=0)
    model = get_model()
    seg_gen, info = model.transcribe(
        audio_path,
        language=WHISPER_LANGUAGE,
        vad_filter=True,
        beam_size=5,
    )

    segments = []
    duration = info.duration or 0
    for seg in seg_gen:
        if is_cancel_requested(job_id):
            finalize_cancelled(job_id, audio_path)
            return
        text = seg.text.strip()
        if not text:
            continue
        segments.append({"start": seg.start, "end": seg.end, "text": text})
        progress = int(min(99, (seg.end / duration) * 100)) if duration else 0
        update_job(job_id, progress=progress, segments_done=len(segments))

    result = {"segments": segments, "language": info.language, "duration": duration}
    result_path = os.path.join(OUTPUT_DIR, f"{job_id}.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    srt_path = os.path.join(OUTPUT_DIR, f"{job_id}.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(build_srt(segments))

    txt_path = os.path.join(OUTPUT_DIR, f"{job_id}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(build_txt(segments))

    if os.path.exists(audio_path):
        os.remove(audio_path)

    update_job(
        job_id,
        status=STATUS_DONE,
        progress=100,
        error=None,
        result_path=result_path,
        srt_path=srt_path,
        txt_path=txt_path,
        language=info.language,
        duration=duration,
    )


def handle_job_failure(job_id, exc):
    job = get_job(job_id)
    if job is None:
        return
    retries = job.get("retries", 0)
    if retries < MAX_RETRIES and not is_cancel_requested(job_id):
        update_job(
            job_id,
            status=STATUS_QUEUED,
            progress=0,
            retries=retries + 1,
            error=f"Percobaan {retries + 1} gagal ({exc}) — mencoba lagi otomatis...",
        )
        queue_manager.submit("transcript", job_id, job.get("filename"), _build_run_fn(job_id))
    else:
        clear_cancel(job_id)
        update_job(job_id, status=STATUS_ERROR, error=str(exc))


def _build_run_fn(job_id):
    """Builds the closure queue_manager runs once it's this job's turn.

    Re-checks job state at call time (not at submit time) so a job that was
    cancelled/deleted/already-handled while still queued becomes a cheap
    no-op instead of doing real work — this also makes a duplicate ticket
    (e.g. a retry racing an auto-retry) harmless, since only the first one
    to actually run will still see status == STATUS_QUEUED.
    """
    def _run():
        job = get_job(job_id)
        if job is None or job["status"] != STATUS_QUEUED:
            return
        try:
            process_job(job_id)
        except Exception as e:
            handle_job_failure(job_id, e)
    return _run


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_EXTENSIONS


@bp.route("/")
def index():
    return render_template("transcript/index.html", active_tool="transcript")


@bp.route("/api/upload", methods=["POST"])
def upload():
    if "video" not in request.files:
        return jsonify({"error": "Tidak ada file video."}), 400
    file = request.files["video"]
    if file.filename == "":
        return jsonify({"error": "Nama file kosong."}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Format tidak didukung. Gunakan MP4, MOV, atau MKV."}), 400

    job_id = uuid.uuid4().hex
    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower()
    video_path = os.path.join(UPLOAD_DIR, f"{job_id}.{ext}")
    # Bump the copy buffer past Werkzeug's 16 KB default — multipart uploads
    # already spooled to a temp file get one extra full read+write pass here,
    # and a bigger buffer noticeably cuts syscall overhead for large videos.
    file.save(video_path, buffer_size=1024 * 1024)

    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "filename": filename,
            "source": "upload",
            "video_path": video_path,
            "status": STATUS_QUEUED,
            "progress": 0,
            "created_at": time.time(),
            "retries": 0,
            "error": None,
        }
        _save_jobs_locked()

    queue_manager.submit("transcript", job_id, filename, _build_run_fn(job_id))
    position = queue_manager.position_of("transcript", job_id) or 0
    return jsonify({"job_id": job_id, "queue_position": position})


@bp.route("/api/from-url", methods=["POST"])
def from_url():
    """Start a transcript job sourced from a YouTube/TikTok/Instagram link
    instead of an upload. Metadata (title/thumbnail/platform) is expected to
    have already been fetched client-side via the Video Downloader's
    /video-downloader/api/metadata endpoint for the preview step -- this
    route just re-validates the URL and queues the download+transcribe job."""
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Link video kosong."}), 400
    try:
        platform = vd_downloader.validate_url(url)
    except vd_downloader.VideoFetchError as e:
        return jsonify({"error": str(e)}), 400

    title = (data.get("title") or "video").strip() or "video"

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "filename": title,
            "source": "url",
            "url": url,
            "platform": platform,
            "video_path": None,
            "status": STATUS_QUEUED,
            "progress": 0,
            "created_at": time.time(),
            "retries": 0,
            "error": None,
        }
        _save_jobs_locked()

    queue_manager.submit("transcript", job_id, title, _build_run_fn(job_id))
    position = queue_manager.position_of("transcript", job_id) or 0
    return jsonify({"job_id": job_id, "queue_position": position})


@bp.route("/api/status/<job_id>")
def status(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "Job tidak ditemukan."}), 404

    position = queue_manager.position_of("transcript", job_id) or 0
    current, _pending = queue_manager.snapshot()
    currently_processing = None
    if current and not (current["tool"] == "transcript" and current["job_id"] == job_id):
        tool_label = {"silence-cutter": "Silence Cutter", "transcript": "Transcript", "video-downloader": "Video Downloader"}.get(current["tool"], current["tool"])
        currently_processing = f'{current["filename"]} ({tool_label})'

    return jsonify({
        "job_id": job_id,
        "filename": job["filename"],
        "status": job["status"],
        "progress": job.get("progress", 0),
        "error": job.get("error"),
        "retries": job.get("retries", 0),
        "queue_position": position,
        "currently_processing": currently_processing,
    })


@bp.route("/api/result/<job_id>")
def result(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "Job tidak ditemukan."}), 404
    if job["status"] != STATUS_DONE:
        return jsonify({"error": "Transkrip belum selesai."}), 409
    with open(job["result_path"], "r", encoding="utf-8") as f:
        data = json.load(f)
    data["filename"] = job["filename"]
    return jsonify(data)


@bp.route("/api/download/<job_id>/<fmt>")
def download(job_id, fmt):
    job = get_job(job_id)
    if job is None:
        abort(404)
    if job["status"] != STATUS_DONE:
        abort(409)
    if fmt not in ("srt", "txt"):
        abort(400)
    path = job["srt_path"] if fmt == "srt" else job["txt_path"]
    base_name = os.path.splitext(job["filename"])[0]
    return send_file(path, as_attachment=True, download_name=f"{base_name}.{fmt}")


@bp.route("/api/jobs")
def list_jobs():
    with jobs_lock:
        items = sorted(jobs.values(), key=lambda j: j["created_at"], reverse=True)
        return jsonify([
            {
                "job_id": j["job_id"],
                "filename": j["filename"],
                "status": j["status"],
                "progress": j.get("progress", 0),
                "error": j.get("error"),
                "retries": j.get("retries", 0),
            }
            for j in items
        ])


@bp.route("/api/job/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "Job tidak ditemukan."}), 404
    if job["status"] in (STATUS_DONE, STATUS_ERROR, STATUS_CANCELLED):
        return jsonify({"error": "Job ini sudah tidak berjalan."}), 409

    request_cancel(job_id)
    if job["status"] == STATUS_QUEUED:
        # Not picked up by the worker yet — cancel immediately.
        update_job(job_id, status=STATUS_CANCELLED, progress=0)
        clear_cancel(job_id)
    else:
        # Actively running: kill the ffmpeg step if that's what's running.
        # The transcription loop notices the flag at the next segment.
        with active_processes_lock:
            proc = active_processes.get(job_id)
        if proc and proc.poll() is None:
            proc.terminate()

    return jsonify({"ok": True})


@bp.route("/api/job/<job_id>/retry", methods=["POST"])
def retry_job(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "Job tidak ditemukan."}), 404
    if job["status"] not in (STATUS_ERROR, STATUS_CANCELLED):
        return jsonify({"error": "Job ini masih berjalan."}), 409
    if job.get("source") != "url" and (not job.get("video_path") or not os.path.exists(job["video_path"])):
        return jsonify({"error": "File video sudah tidak ada. Silakan upload ulang."}), 410

    clear_cancel(job_id)
    update_job(job_id, status=STATUS_QUEUED, progress=0, error=None, retries=0)
    queue_manager.submit("transcript", job_id, job["filename"], _build_run_fn(job_id))
    return jsonify({"ok": True})


@bp.route("/api/job/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "Job tidak ditemukan."}), 404
    if job["status"] in ACTIVE_STATUSES:
        return jsonify({"error": "Tidak bisa menghapus job yang masih diproses."}), 409

    for key in ("video_path", "result_path", "srt_path", "txt_path"):
        path = job.get(key)
        if path and os.path.exists(path):
            os.remove(path)
    _cleanup_glob(os.path.join(OUTPUT_DIR, f"{job_id}.wav"))
    _cleanup_glob(os.path.join(OUTPUT_DIR, f"{job_id}_src.*"))

    with jobs_lock:
        jobs.pop(job_id, None)
        _save_jobs_locked()

    return jsonify({"ok": True})


def _preload_model():
    try:
        get_model()  # preload once at startup so the first real job doesn't wait for it
    except Exception as e:
        print(f"[transcript] gagal preload model, akan dicoba lagi per-job: {e}")


threading.Thread(target=_preload_model, daemon=True).start()

# Runs at import time — must come after _build_run_fn is defined above (it's
# used inside _load_jobs' crash-requeue path) and after `import queue_manager`
# at the top of this file (its worker thread must already be running).
_load_jobs()
