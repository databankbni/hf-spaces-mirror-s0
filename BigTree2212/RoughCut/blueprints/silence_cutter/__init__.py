import os
import re
import time
import uuid
import threading
import traceback

from flask import Blueprint, request, jsonify, render_template, send_file, abort

import queue_manager
from .processor import process_video, get_duration, JobCancelled

bp = Blueprint("silence_cutter", __name__, url_prefix="/silence-cutter")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("SILENCE_CUTTER_DATA_DIR")
if not DATA_DIR:
    # If this Space has the persistent storage add-on enabled, Hugging Face mounts
    # it at /data — use it so large uploads/outputs land on the durable disk you're
    # paying for instead of the container's small ephemeral filesystem.
    DATA_DIR = "/data/silence-cutter" if os.path.isdir("/data") else os.path.join(BASE_DIR, "..", "..", "data", "silence_cutter")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Shared-hosting safety limits (tune these for your server's specs) ---
MAX_UPLOAD_BYTES = 12 * 1024 * 1024 * 1024    # 12 GB per file
OUTPUT_TTL_SECONDS = 2 * 60 * 60               # delete finished files after 2h

# In-memory job store. Fine for a small team sharing one instance.
# Cross-tool single-concurrency is enforced by queue_manager, not here.
JOBS = {}
JOBS_LOCK = threading.Lock()

# One cancel flag per in-flight job; the background thread checks it while
# waiting for the processing slot and between ffmpeg polls, so a cancel
# request can interrupt a queued or running job quickly.
CANCEL_EVENTS = {}
CANCEL_EVENTS_LOCK = threading.Lock()


def set_job(job_id, **kwargs):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(kwargs)


def _cleanup_cancelled(job_id, input_path):
    set_job(job_id, status="cancelled")
    with CANCEL_EVENTS_LOCK:
        CANCEL_EVENTS.pop(job_id, None)
    try:
        os.remove(input_path)
    except OSError:
        pass


def run_job(job_id, input_path, output_path, params, cancel_event):
    # queue_manager only invokes this once it's this job's turn, so no need
    # to wait for a processing slot here — just handle the case where the
    # job was cancelled while it was still sitting in the queue.
    if cancel_event.is_set():
        _cleanup_cancelled(job_id, input_path)
        return

    try:
        try:
            set_job(job_id, status="detecting", progress=20)
            original_duration = get_duration(input_path, cancel_event=cancel_event)
            set_job(job_id, status="cutting", progress=45, original_duration=original_duration)

            stats = process_video(
                input_path,
                output_path,
                silence_db=params["silence_db"],
                min_silence_duration=params["min_silence_duration"],
                margin_before=params["margin_before"],
                margin_after=params["margin_after"],
                min_keep_duration=params["keep_talk_duration"],
                merge_gap=params["merge_gap"],
                cancel_event=cancel_event,
            )

            set_job(job_id, status="done", progress=100, stats=stats, finished_at=time.time())
        except JobCancelled:
            set_job(job_id, status="cancelled")
            try:
                os.remove(output_path)
            except OSError:
                pass
        except Exception as e:
            traceback.print_exc()
            set_job(job_id, status="error", error=str(e))
    finally:
        with CANCEL_EVENTS_LOCK:
            CANCEL_EVENTS.pop(job_id, None)
        try:
            os.remove(input_path)
        except OSError:
            pass


def cleanup_loop():
    """Background sweep: delete old output files so shared disk doesn't fill up."""
    while True:
        time.sleep(600)
        now = time.time()
        with JOBS_LOCK:
            stale_ids = [
                jid for jid, job in JOBS.items()
                if job.get("status") == "done"
                and now - job.get("finished_at", now) > OUTPUT_TTL_SECONDS
            ]
        for jid in stale_ids:
            with JOBS_LOCK:
                job = JOBS.pop(jid, None)
            if job:
                try:
                    os.remove(job["output_path"])
                except OSError:
                    pass


threading.Thread(target=cleanup_loop, daemon=True).start()


def register_error_handlers(app):
    @app.errorhandler(413)
    def too_large(e):
        max_gb = MAX_UPLOAD_BYTES / (1024 ** 3)
        return jsonify({"error": f"File terlalu besar. Maksimal {max_gb:.1f} GB."}), 413


@bp.route("/")
def index():
    return render_template(
        "silence_cutter/index.html",
        max_upload_gb=round(MAX_UPLOAD_BYTES / (1024 ** 3), 1),
        active_tool="silence-cutter",
    )


def _clamped_ms(form, key, lo, hi, default_ms):
    """Reads a millisecond field from the form, clamps it, returns seconds."""
    try:
        value = float(request.form.get(key, default_ms))
    except (TypeError, ValueError):
        value = default_ms
    return max(lo, min(hi, value)) / 1000


@bp.route("/api/upload", methods=["POST"])
def upload():
    file = request.files.get("video")
    if not file or file.filename == "":
        return jsonify({"error": "No file provided"}), 400

    try:
        silence_db = float(request.form.get("silence_db", -30))
    except (TypeError, ValueError):
        silence_db = -30
    silence_db = max(-60, min(-10, silence_db))

    min_silence_duration = _clamped_ms(request.form, "remove_silence_ms", 20, 5000, 350)
    keep_talk_duration = _clamped_ms(request.form, "keep_talk_ms", 20, 5000, 250)
    margin_before = _clamped_ms(request.form, "margin_before_ms", 0, 2000, 220)
    margin_after = _clamped_ms(request.form, "margin_after_ms", 0, 2000, 100)
    merge_gap = (
        _clamped_ms(request.form, "merge_gap_ms", 0, 2000, 120)
        if request.form.get("merge_gap_enabled") == "1"
        else 0.0
    )

    job_id = uuid.uuid4().hex
    ext = os.path.splitext(file.filename)[1] or ".mp4"
    input_path = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")
    output_path = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
    # Bump the copy buffer past Werkzeug's 16 KB default — multipart uploads
    # already spooled to a temp file get one extra full read+write pass here,
    # and a bigger buffer noticeably cuts syscall overhead for large videos.
    file.save(input_path, buffer_size=1024 * 1024)

    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "queued",
            "progress": 5,
            "output_path": output_path,
            "original_filename": file.filename,
        }

    params = {
        "silence_db": silence_db,
        "min_silence_duration": min_silence_duration,
        "keep_talk_duration": keep_talk_duration,
        "margin_before": margin_before,
        "margin_after": margin_after,
        "merge_gap": merge_gap,
    }
    cancel_event = threading.Event()
    with CANCEL_EVENTS_LOCK:
        CANCEL_EVENTS[job_id] = cancel_event

    queue_manager.submit(
        "silence-cutter", job_id, file.filename,
        lambda: run_job(job_id, input_path, output_path, params, cancel_event),
    )

    return jsonify({"job_id": job_id})


@bp.route("/api/status/<job_id>")
def status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "unknown job"}), 404
    return jsonify({
        "status": job.get("status"),
        "progress": job.get("progress"),
        "stats": job.get("stats"),
        "error": job.get("error"),
        "original_filename": job.get("original_filename"),
        "queue_position": queue_manager.position_of("silence-cutter", job_id),
    })


@bp.route("/api/cancel/<job_id>", methods=["POST"])
def cancel_job(job_id):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        abort(404)

    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job tidak ditemukan."}), 404
    if job.get("status") not in ("queued", "detecting", "cutting"):
        return jsonify({"error": "Job tidak sedang berjalan."}), 409

    with CANCEL_EVENTS_LOCK:
        event = CANCEL_EVENTS.get(job_id)
    if not event:
        return jsonify({"error": "Job tidak ditemukan."}), 404

    event.set()
    # Still queued (not yet this job's turn) — flip status immediately so the
    # UI doesn't keep showing "queued" until the worker eventually reaches it.
    # A job that's actively running still needs run_job's own cleanup path to
    # set the final "cancelled" status once ffmpeg has actually stopped.
    with JOBS_LOCK:
        if job_id in JOBS and JOBS[job_id].get("status") == "queued":
            JOBS[job_id]["status"] = "cancelled"

    return jsonify({"cancelling": True})


@bp.route("/api/jobs")
def list_jobs():
    with JOBS_LOCK:
        jobs = [
            {
                "job_id": jid,
                "status": job.get("status"),
                "progress": job.get("progress"),
                "original_filename": job.get("original_filename"),
                "stats": job.get("stats"),
            }
            for jid, job in JOBS.items()
        ]
    return jsonify({"jobs": jobs})


def get_job_brief(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        return {
            "status": job.get("status"),
            "progress": job.get("progress"),
            "filename": job.get("original_filename"),
        }


@bp.route("/api/download/<job_id>")
def download(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job and job.get("status") == "done":
        base = os.path.splitext(job.get("original_filename", "video"))[0]
        return send_file(job["output_path"], as_attachment=True, download_name=f"{base}_cut.mp4")

    # Fall back to the rendered file on disk: the in-memory job record can be
    # gone (worker restart) even though the output was already produced.
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        abort(404)
    output_path = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
    if os.path.isfile(output_path):
        return send_file(output_path, as_attachment=True, download_name=f"{job_id}_cut.mp4")

    abort(404)


@bp.route("/api/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        abort(404)

    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job and job.get("status") not in ("done", "error", "cancelled"):
            return jsonify({"error": "Job masih diproses, tidak bisa dihapus."}), 409
        job = JOBS.pop(job_id, None)

    output_path = job["output_path"] if job else os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
    try:
        os.remove(output_path)
    except OSError:
        pass

    return jsonify({"deleted": True})
