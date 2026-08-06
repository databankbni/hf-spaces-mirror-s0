import os
import glob
import json
import time
import uuid
import threading
import subprocess

from flask import Blueprint, request, jsonify, render_template, send_file, abort

import queue_manager
from . import downloader

bp = Blueprint("video_downloader", __name__, url_prefix="/video-downloader")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("VIDEO_DOWNLOADER_DATA_DIR")
if not DATA_DIR:
    DATA_DIR = "/data/video-downloader" if os.path.isdir("/data") else os.path.join(BASE_DIR, "..", "..", "data", "video_downloader")
DOWNLOAD_DIR = os.path.join(DATA_DIR, "downloads")
JOBS_DB_PATH = os.path.join(DATA_DIR, "jobs_db.json")


def ensure_data_dirs():
    """Recreate the data subdirectories if they're missing. Called at import
    and again at the start of every job -- storage on some deploy targets
    (e.g. Hugging Face Spaces' free tier) is ephemeral, and the app
    otherwise only created these once at process startup, so anything that
    removed a subdirectory afterwards would make every subsequent write fail
    with ENOENT."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)


ensure_data_dirs()

# A job that fails (transient network error, yt-dlp hiccup) gets retried
# automatically up to this many times before it's shown as a hard error.
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "2"))

# Finished job files older than this get swept by the cleanup loop so disk
# doesn't fill up with downloads nobody came back for.
MAX_FILE_AGE_HOURS = float(os.environ.get("MAX_FILE_AGE_HOURS", "24"))
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", "1800"))

MODE_VIDEO = "video"
MODE_AUDIO = "audio"

# ---------------------------------------------------------------------------
# Job registry (in-memory + lightweight disk persistence so a restart
# doesn't wipe the job list). Cross-tool single-concurrency is enforced by
# queue_manager, not here.
# ---------------------------------------------------------------------------
STATUS_QUEUED = "queued"
STATUS_DOWNLOADING = "downloading"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"

ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_DOWNLOADING)
ACTIVE_PROCESSING_STATUSES = (STATUS_DOWNLOADING,)

jobs = {}
jobs_lock = threading.Lock()

# job_id -> subprocess.Popen for the yt-dlp process currently running, so a
# cancel request can terminate it immediately instead of waiting it out.
active_processes = {}
active_processes_lock = threading.Lock()

# job_ids with a pending cancel request, checked between yt-dlp output lines.
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
    return {"status": job.get("status"), "progress": job.get("progress", 0), "filename": job.get("title")}


def update_job_if_status(job_id, expected_statuses, **fields):
    """Atomically check-then-update so two racing callers can't both act on
    the same status read (e.g. cancel racing the worker's dequeue). Returns
    the pre-update job dict on success, else None."""
    if isinstance(expected_statuses, str):
        expected_statuses = (expected_statuses,)
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None or job["status"] not in expected_statuses:
            return None
        snapshot = dict(job)
        jobs[job_id].update(fields)
        _save_jobs_locked()
        return snapshot


# ---------------------------------------------------------------------------
# yt-dlp download subprocess
# ---------------------------------------------------------------------------
def subprocess_error_tail(text):
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return "\n".join(lines[-5:]) or "Proses keluar tanpa pesan error."


def run_download(job_id, cmd, dest_template):
    """Run the yt-dlp download/convert command, streaming progress into the
    job record. Returns the final output file path, or None if cancelled
    mid-run. Raises downloader.VideoFetchError on failure."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    with active_processes_lock:
        active_processes[job_id] = proc
    tail_lines = []
    cancelled_mid = False
    try:
        for line in proc.stdout:
            tail_lines.append(line)
            if len(tail_lines) > 40:
                tail_lines.pop(0)
            if is_cancel_requested(job_id):
                cancelled_mid = True
                proc.terminate()
                break
            pct = downloader.parse_progress_percent(line)
            if pct is not None:
                update_job(job_id, progress=int(pct), phase="fetching")
            elif downloader.is_processing_line(line):
                update_job(job_id, phase="processing")
        proc.wait()
    finally:
        with active_processes_lock:
            active_processes.pop(job_id, None)

    if cancelled_mid or is_cancel_requested(job_id):
        return None
    if proc.returncode != 0:
        raise downloader.classify_error("".join(tail_lines))

    candidates = sorted(
        p for p in glob.glob(dest_template.replace("%(ext)s", "*"))
        if not p.endswith(".part") and not p.endswith(".ytdl")
    )
    return candidates[0] if candidates else None


def run_ffmpeg(job_id, cmd):
    """Run a plain ffmpeg command (not yt-dlp) to completion, registering it
    so cancel can terminate it. Returns (returncode, stderr_text)."""
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    with active_processes_lock:
        active_processes[job_id] = proc
    try:
        _, stderr = proc.communicate()
    finally:
        with active_processes_lock:
            active_processes.pop(job_id, None)
    return proc.returncode, stderr or ""


def _cleanup_glob(pattern):
    for path in glob.glob(pattern):
        try:
            os.remove(path)
        except OSError:
            pass


def finalize_cancelled(job_id, extra_cleanup=None):
    if extra_cleanup:
        extra_cleanup()
    clear_cancel(job_id)
    update_job(job_id, status=STATUS_CANCELLED, progress=0, phase=None, error=None)


# ---------------------------------------------------------------------------
# The pipeline: acquire the file via yt-dlp (video or audio-to-mp3), then
# mark done. Resumable -- if output_path is already set and the file still
# exists (e.g. a retry after a later transient step), the download is
# skipped, though in practice this single-stage pipeline rarely needs that.
# ---------------------------------------------------------------------------
def process_job(job_id):
    ensure_data_dirs()
    job = get_job(job_id)
    if job is None:
        return
    if is_cancel_requested(job_id):
        finalize_cancelled(job_id)
        return

    if not job.get("output_path") or not os.path.exists(job["output_path"]):
        update_job(job_id, status=STATUS_DOWNLOADING, progress=0, phase="fetching")
        dest_template = os.path.join(DOWNLOAD_DIR, f"{job_id}.%(ext)s")
        if job["mode"] == MODE_AUDIO:
            cmd = downloader.build_audio_download_command(job["url"], dest_template)
        else:
            cmd = downloader.build_video_download_command(job["url"], job.get("height"), dest_template)

        result_path = run_download(job_id, cmd, dest_template)
        if is_cancel_requested(job_id):
            finalize_cancelled(job_id, lambda: _cleanup_glob(os.path.join(DOWNLOAD_DIR, f"{job_id}*")))
            return
        if not result_path:
            raise downloader.VideoFetchError("yt-dlp selesai tapi file hasil unduhan tidak ditemukan.")

        # Some sources (Instagram in particular) only expose VP9/AV1 video
        # DASH streams -- no H.264 alternative exists to prefer in the
        # format selector at all. yt-dlp's --merge-output-format just picks
        # a container, it doesn't transcode, so the result plays fine in
        # browsers/VLC but not in QuickTime/iOS. Re-encode only when the
        # actual codec turns out to need it.
        if job["mode"] == MODE_VIDEO:
            codec = downloader.probe_video_codec(result_path)
            if downloader.needs_transcode(codec):
                update_job(job_id, phase="processing")
                transcoded_path = result_path.rsplit(".", 1)[0] + "_h264.mp4"
                returncode, stderr = run_ffmpeg(job_id, downloader.build_transcode_command(result_path, transcoded_path))
                if is_cancel_requested(job_id):
                    finalize_cancelled(job_id, lambda: _cleanup_glob(os.path.join(DOWNLOAD_DIR, f"{job_id}*")))
                    return
                if returncode != 0 or not os.path.exists(transcoded_path):
                    raise downloader.VideoFetchError(f"Gagal mengonversi video ke format kompatibel: {subprocess_error_tail(stderr)}")
                os.remove(result_path)
                result_path = transcoded_path

        ext = result_path.rsplit(".", 1)[-1]
        output_filename = downloader.build_output_filename(job["title"], job["mode"], job.get("resolution_label"), ext)
        update_job(job_id, output_path=result_path, output_filename=output_filename)

    clear_cancel(job_id)
    update_job(job_id, status=STATUS_DONE, progress=100, phase=None, error=None)


# ---------------------------------------------------------------------------
# queue_manager wiring
# ---------------------------------------------------------------------------
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
            phase=None,
            retries=retries + 1,
            error=f"Percobaan {retries + 1} gagal ({exc}) — mencoba lagi otomatis...",
        )
        queue_manager.submit("video-downloader", job_id, job.get("title"), _build_run_fn(job_id))
    else:
        clear_cancel(job_id)
        update_job(job_id, status=STATUS_ERROR, error=str(exc))


def _build_run_fn(job_id):
    """Builds the closure queue_manager runs once it's this job's turn.

    Atomically claims the job iff it's still queued (via update_job_if_status)
    so a cancel/delete/duplicate-ticket race lands as a harmless no-op --
    mirrors the pattern used by the other tools' blueprints.
    """
    def _run():
        claimed = update_job_if_status(job_id, STATUS_QUEUED)
        if not claimed:
            return
        try:
            process_job(job_id)
        except Exception as e:
            handle_job_failure(job_id, e)
    return _run


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
            # The process died mid-download (crash/restart). Every job here
            # is URL-sourced, so it can always be re-downloaded from scratch.
            retries = job.get("retries", 0)
            if retries < MAX_RETRIES:
                job["status"] = STATUS_QUEUED
                job["progress"] = 0
                job["phase"] = None
                job["retries"] = retries + 1
                job["error"] = "Server sempat berhenti — sedang diunduh ulang secara otomatis."
                queue_manager.submit("video-downloader", job_id, job.get("title"), _build_run_fn(job_id))
            else:
                job["status"] = STATUS_ERROR
                job["error"] = "Proses berulang kali terhenti. Coba lagi."
        jobs[job_id] = job


# ---------------------------------------------------------------------------
# Auto-cleanup: sweep finished/failed jobs (and their files) once they're
# older than MAX_FILE_AGE_HOURS, so disk usage doesn't grow unbounded.
# ---------------------------------------------------------------------------
def cleanup_old_jobs():
    cutoff = time.time() - MAX_FILE_AGE_HOURS * 3600
    with jobs_lock:
        stale_ids = [
            jid for jid, j in jobs.items()
            if j["status"] not in ACTIVE_STATUSES and j.get("created_at", 0) < cutoff
        ]
    for jid in stale_ids:
        _cleanup_glob(os.path.join(DOWNLOAD_DIR, f"{jid}*"))
        with jobs_lock:
            jobs.pop(jid, None)
    if stale_ids:
        with jobs_lock:
            _save_jobs_locked()


def cleanup_loop():
    while True:
        time.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            cleanup_old_jobs()
        except Exception as e:
            print(f"[video-downloader cleanup] error: {e}")


threading.Thread(target=cleanup_loop, daemon=True).start()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def new_job_record(job_id, url, platform, mode, height, resolution_label, title, thumbnail, duration):
    return {
        "job_id": job_id,
        "url": url,
        "platform": platform,
        "mode": mode,
        "height": height,
        "resolution_label": resolution_label,
        "title": title,
        "thumbnail": thumbnail,
        "duration": duration,
        "status": STATUS_QUEUED,
        "progress": 0,
        "phase": None,
        "created_at": time.time(),
        "retries": 0,
        "error": None,
        "output_path": None,
        "output_filename": None,
    }


@bp.route("/")
def index():
    return render_template("video_downloader/index.html", active_tool="video-downloader")


@bp.route("/api/metadata", methods=["POST"])
def metadata():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Link video kosong."}), 400
    try:
        meta = downloader.fetch_metadata(url)
    except downloader.VideoFetchError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(meta)


@bp.route("/api/download", methods=["POST"])
def start_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    mode = data.get("mode")
    title = (data.get("title") or "video").strip()
    thumbnail = data.get("thumbnail")
    duration = data.get("duration")

    if not url:
        return jsonify({"error": "Link video kosong."}), 400
    if mode not in (MODE_VIDEO, MODE_AUDIO):
        return jsonify({"error": "Format tidak valid."}), 400

    try:
        platform = downloader.validate_url(url)
    except downloader.VideoFetchError as e:
        return jsonify({"error": str(e)}), 400

    height = None
    resolution_label = None
    if mode == MODE_VIDEO and data.get("height") is not None:
        try:
            height = int(data.get("height"))
        except (TypeError, ValueError):
            return jsonify({"error": "Resolusi tidak valid."}), 400
        resolution_label = (data.get("resolution_label") or "").strip() or None

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = new_job_record(job_id, url, platform, mode, height, resolution_label, title, thumbnail, duration)
        _save_jobs_locked()

    queue_manager.submit("video-downloader", job_id, title, _build_run_fn(job_id))
    position = queue_manager.position_of("video-downloader", job_id) or 0
    return jsonify({"job_id": job_id, "queue_position": position})


@bp.route("/api/status/<job_id>")
def status(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "Job tidak ditemukan."}), 404

    position = queue_manager.position_of("video-downloader", job_id) or 0
    current, _pending = queue_manager.snapshot()
    currently_processing = None
    if current and not (current["tool"] == "video-downloader" and current["job_id"] == job_id):
        tool_label = {"silence-cutter": "Silence Cutter", "transcript": "Transcript", "video-downloader": "Video Downloader"}.get(current["tool"], current["tool"])
        currently_processing = f'{current["filename"]} ({tool_label})'

    return jsonify({
        "job_id": job_id,
        "title": job["title"],
        "platform": job.get("platform"),
        "mode": job["mode"],
        "height": job.get("height"),
        "resolution_label": job.get("resolution_label"),
        "status": job["status"],
        "progress": job.get("progress", 0),
        "phase": job.get("phase"),
        "error": job.get("error"),
        "retries": job.get("retries", 0),
        "queue_position": position,
        "currently_processing": currently_processing,
        "output_filename": job.get("output_filename"),
    })


@bp.route("/api/download-file/<job_id>")
def download_file(job_id):
    job = get_job(job_id)
    if job is None:
        abort(404)
    if job["status"] != STATUS_DONE or not job.get("output_path") or not os.path.exists(job["output_path"]):
        abort(404)
    return send_file(job["output_path"], as_attachment=True, download_name=job["output_filename"])


@bp.route("/api/jobs")
def list_jobs():
    with jobs_lock:
        items = sorted(jobs.values(), key=lambda j: j["created_at"], reverse=True)
        return jsonify([
            {
                "job_id": j["job_id"],
                "title": j["title"],
                "mode": j["mode"],
                "resolution_label": j.get("resolution_label"),
                "status": j["status"],
                "progress": j.get("progress", 0),
                "phase": j.get("phase"),
                "error": j.get("error"),
                "retries": j.get("retries", 0),
                "output_filename": j.get("output_filename"),
            }
            for j in items
        ])


@bp.route("/api/job/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "Job tidak ditemukan."}), 404
    if job["status"] not in ACTIVE_STATUSES:
        return jsonify({"error": "Job ini sudah tidak berjalan."}), 409

    request_cancel(job_id)
    # Atomically flip QUEUED -> CANCELLED so this can't race the worker's own
    # atomic claim in _build_run_fn.
    claimed = update_job_if_status(job_id, STATUS_QUEUED, status=STATUS_CANCELLED, progress=0)
    if claimed:
        clear_cancel(job_id)
    else:
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

    clear_cancel(job_id)
    update_job(job_id, status=STATUS_QUEUED, progress=0, phase=None, error=None, retries=0)
    queue_manager.submit("video-downloader", job_id, job["title"], _build_run_fn(job_id))
    return jsonify({"ok": True})


@bp.route("/api/job/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "Job tidak ditemukan."}), 404
    if job["status"] in ACTIVE_STATUSES:
        return jsonify({"error": "Tidak bisa menghapus job yang masih diproses."}), 409

    _cleanup_glob(os.path.join(DOWNLOAD_DIR, f"{job_id}*"))
    with jobs_lock:
        jobs.pop(job_id, None)
        _save_jobs_locked()

    return jsonify({"ok": True})


cleanup_old_jobs()
# Runs at import time -- must come after _build_run_fn is defined above (it's
# used inside _load_jobs' crash-requeue path) and after `import queue_manager`
# at the top of this file (its worker thread must already be running).
_load_jobs()
