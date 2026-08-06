"""
Flask web app: chunked upload -> background extraction -> progress polling -> download.

Why chunked upload + background job:
- Render free tier has limited memory/CPU and request timeouts.
- A 200MB single-shot upload can time out or hang the browser with no feedback.
- Splitting into chunks lets the client show a real upload progress bar,
  and processing happens in a background thread so the HTTP request returns instantly.
"""

from __future__ import annotations

import shutil
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, abort

from core import extract_mhtml_to_zip, ExtractionError

import os

BASE_DIR = Path(__file__).resolve().parent
# DATA_DIR overridable via env var: HF Spaces containers may run as a non-root
# user, so we keep data inside the app's own writable directory by default.
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
for d in (UPLOAD_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB hard limit
CHUNK_JOB_TTL_SECONDS = 60 * 60  # cleanup files after 1 hour

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # each chunk request must stay small (~5MB chunks expected)

jobs_lock = threading.Lock()
jobs: dict[str, dict] = {}
# job structure:
# {
#   "id", "filename", "total_chunks", "received_chunks": set(),
#   "upload_path": Path, "status": "uploading"|"queued"|"processing"|"done"|"error",
#   "percent": int, "stage": str, "message": str,
#   "zip_path": Path|None, "manifest": dict|None, "error": str|None,
#   "created_at": float,
# }


def new_job_id() -> str:
    return uuid.uuid4().hex


def cleanup_old_jobs():
    now = time.time()
    with jobs_lock:
        stale = [jid for jid, j in jobs.items() if now - j["created_at"] > CHUNK_JOB_TTL_SECONDS]
        for jid in stale:
            j = jobs.pop(jid)
            for p in (j.get("upload_path"), j.get("zip_path")):
                try:
                    if p and Path(p).exists():
                        Path(p).unlink()
                except Exception:
                    pass


@app.route("/")
def home():
    return render_template("index.html", max_size_mb=MAX_FILE_SIZE // (1024 * 1024))


@app.route("/api/upload/init", methods=["POST"])
def upload_init():
    cleanup_old_jobs()
    data = request.get_json(force=True)
    filename = (data.get("filename") or "chapter.mhtml").strip()
    total_size = int(data.get("total_size") or 0)
    total_chunks = int(data.get("total_chunks") or 0)

    if total_size <= 0 or total_chunks <= 0:
        return jsonify({"error": "بيانات الرفع غير صالحة."}), 400
    if total_size > MAX_FILE_SIZE:
        return jsonify({"error": f"حجم الملف يتجاوز الحد المسموح ({MAX_FILE_SIZE // (1024*1024)}MB)."}), 413
    if not filename.lower().endswith((".mhtml", ".mht")):
        return jsonify({"error": "الامتداد يجب أن يكون .mhtml أو .mht"}), 400

    job_id = new_job_id()
    upload_path = UPLOAD_DIR / f"{job_id}.part"
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "filename": filename,
            "total_chunks": total_chunks,
            "received_chunks": set(),
            "upload_path": upload_path,
            "status": "uploading",
            "percent": 0,
            "stage": "uploading",
            "message": "بانتظار رفع الأجزاء...",
            "zip_path": None,
            "manifest": None,
            "error": None,
            "created_at": time.time(),
        }
    # pre-allocate empty file
    upload_path.touch()
    return jsonify({"job_id": job_id})


@app.route("/api/upload/chunk", methods=["POST"])
def upload_chunk():
    job_id = request.form.get("job_id")
    chunk_index = request.form.get("chunk_index")
    file = request.files.get("chunk")

    if not job_id or chunk_index is None or file is None:
        return jsonify({"error": "طلب رفع غير مكتمل."}), 400

    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "جلسة الرفع غير موجودة أو انتهت صلاحيتها."}), 404

    chunk_index = int(chunk_index)
    chunk_bytes = file.read()

    # chunks may arrive out of order; write at the correct byte offset
    offset = chunk_index * 5 * 1024 * 1024  # must match CHUNK_SIZE on the client (5MB)
    with open(job["upload_path"], "r+b") as f:
        f.seek(offset)
        f.write(chunk_bytes)

    with jobs_lock:
        job["received_chunks"].add(chunk_index)
        received = len(job["received_chunks"])
        total = job["total_chunks"]
        job["percent"] = int(received / total * 100)
        job["message"] = f"تم رفع {received}/{total} جزء"

    return jsonify({"received": received, "total": total})


@app.route("/api/upload/complete", methods=["POST"])
def upload_complete():
    data = request.get_json(force=True)
    job_id = data.get("job_id")
    base_name = (data.get("base_name") or "").strip() or None

    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "جلسة الرفع غير موجودة."}), 404
        if len(job["received_chunks"]) != job["total_chunks"]:
            return jsonify({"error": "لم يتم استلام كل الأجزاء بعد."}), 400
        job["status"] = "queued"
        job["stage"] = "queued"
        job["percent"] = 0
        job["message"] = "بانتظار بدء المعالجة..."

    thread = threading.Thread(target=run_extraction, args=(job_id, base_name), daemon=True)
    thread.start()
    return jsonify({"ok": True})


def run_extraction(job_id: str, base_name: str | None):
    with jobs_lock:
        job = jobs[job_id]
        job["status"] = "processing"

    def progress_cb(stage: str, percent: int, message: str):
        with jobs_lock:
            j = jobs.get(job_id)
            if not j:
                return
            j["stage"] = stage
            j["percent"] = percent
            j["message"] = message

    upload_path: Path = jobs[job_id]["upload_path"]
    renamed_path = upload_path.with_suffix(Path(jobs[job_id]["filename"]).suffix or ".mhtml")
    try:
        shutil.move(str(upload_path), str(renamed_path))
    except Exception:
        renamed_path = upload_path  # fallback, keep original

    zip_path = OUTPUT_DIR / f"{job_id}.zip"
    try:
        manifest = extract_mhtml_to_zip(renamed_path, zip_path, base_name=base_name, cb=progress_cb)
        with jobs_lock:
            job = jobs[job_id]
            job["status"] = "done"
            job["zip_path"] = zip_path
            job["manifest"] = manifest
            job["percent"] = 100
            job["message"] = "تم الاستخراج بنجاح."
    except ExtractionError as e:
        with jobs_lock:
            job = jobs[job_id]
            job["status"] = "error"
            job["error"] = str(e)
            job["message"] = str(e)
    except Exception as e:
        with jobs_lock:
            job = jobs[job_id]
            job["status"] = "error"
            job["error"] = f"خطأ غير متوقع: {e}"
            job["message"] = job["error"]
    finally:
        try:
            if renamed_path.exists():
                renamed_path.unlink()
        except Exception:
            pass


@app.route("/api/status/<job_id>")
def status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "غير موجود"}), 404
        return jsonify({
            "status": job["status"],
            "stage": job["stage"],
            "percent": job["percent"],
            "message": job["message"],
            "manifest": job["manifest"],
            "error": job["error"],
        })


@app.route("/api/download/<job_id>")
def download(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job["status"] != "done" or not job["zip_path"] or not Path(job["zip_path"]).exists():
        abort(404)
    download_name = Path(job["filename"]).stem + ".zip"
    return send_file(job["zip_path"], as_attachment=True, download_name=download_name)


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "حجم البيانات المرسلة أكبر من المسموح."}), 413


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))


# ═══════════════════════════════════════════════════════════════
# Rename Images in ZIP — routes
# ═══════════════════════════════════════════════════════════════

from renamer import rename_zip_images, RenamerError

RENAME_UPLOAD_DIR = DATA_DIR / "rename_uploads"
RENAME_OUTPUT_DIR = DATA_DIR / "rename_outputs"
for _d in (RENAME_UPLOAD_DIR, RENAME_OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

rename_jobs_lock = threading.Lock()
rename_jobs: dict[str, dict] = {}


def cleanup_old_rename_jobs():
    now = time.time()
    with rename_jobs_lock:
        stale = [jid for jid, j in rename_jobs.items() if now - j["created_at"] > CHUNK_JOB_TTL_SECONDS]
        for jid in stale:
            j = rename_jobs.pop(jid)
            for p in (j.get("upload_path"), j.get("zip_path")):
                try:
                    if p and Path(p).exists():
                        Path(p).unlink()
                except Exception:
                    pass


@app.route("/api/rename/init", methods=["POST"])
def rename_init():
    cleanup_old_rename_jobs()
    data = request.get_json(force=True)
    filename = (data.get("filename") or "images.zip").strip()
    total_size = int(data.get("total_size") or 0)
    total_chunks = int(data.get("total_chunks") or 0)

    if total_size <= 0 or total_chunks <= 0:
        return jsonify({"error": "بيانات الرفع غير صالحة."}), 400
    if total_size > MAX_FILE_SIZE:
        return jsonify({"error": f"حجم الملف يتجاوز الحد المسموح ({MAX_FILE_SIZE // (1024*1024)}MB)."}), 413
    if not filename.lower().endswith(".zip"):
        return jsonify({"error": "يجب أن يكون الملف بامتداد .zip"}), 400

    job_id = new_job_id()
    upload_path = RENAME_UPLOAD_DIR / f"{job_id}.zip"
    upload_path.touch()

    with rename_jobs_lock:
        rename_jobs[job_id] = {
            "id": job_id,
            "filename": filename,
            "total_chunks": total_chunks,
            "received_chunks": set(),
            "upload_path": upload_path,
            "status": "uploading",
            "percent": 0,
            "stage": "uploading",
            "message": "بانتظار رفع الأجزاء...",
            "zip_path": None,
            "manifest": None,
            "error": None,
            "created_at": time.time(),
        }
    return jsonify({"job_id": job_id})


@app.route("/api/rename/chunk", methods=["POST"])
def rename_chunk():
    job_id = request.form.get("job_id")
    chunk_index = request.form.get("chunk_index")
    file = request.files.get("chunk")

    if not job_id or chunk_index is None or file is None:
        return jsonify({"error": "طلب رفع غير مكتمل."}), 400

    with rename_jobs_lock:
        job = rename_jobs.get(job_id)
    if not job:
        return jsonify({"error": "جلسة الرفع غير موجودة أو انتهت صلاحيتها."}), 404

    chunk_index = int(chunk_index)
    chunk_bytes = file.read()
    offset = chunk_index * 5 * 1024 * 1024

    with open(job["upload_path"], "r+b") as f:
        f.seek(offset)
        f.write(chunk_bytes)

    with rename_jobs_lock:
        job["received_chunks"].add(chunk_index)
        received = len(job["received_chunks"])
        total = job["total_chunks"]
        job["percent"] = int(received / total * 100)
        job["message"] = f"تم رفع {received}/{total} جزء"

    return jsonify({"received": received, "total": total})


@app.route("/api/rename/complete", methods=["POST"])
def rename_complete():
    data = request.get_json(force=True)
    job_id = data.get("job_id")

    with rename_jobs_lock:
        job = rename_jobs.get(job_id)
        if not job:
            return jsonify({"error": "جلسة الرفع غير موجودة."}), 404
        if len(job["received_chunks"]) != job["total_chunks"]:
            return jsonify({"error": "لم يتم استلام كل الأجزاء بعد."}), 400
        job["status"] = "queued"
        job["stage"] = "queued"
        job["percent"] = 0
        job["message"] = "بانتظار بدء المعالجة..."

    thread = threading.Thread(target=run_rename, args=(job_id,), daemon=True)
    thread.start()
    return jsonify({"ok": True})


def run_rename(job_id: str):
    with rename_jobs_lock:
        job = rename_jobs[job_id]
        job["status"] = "processing"

    def progress_cb(stage: str, percent: int, message: str):
        with rename_jobs_lock:
            j = rename_jobs.get(job_id)
            if j:
                j["stage"] = stage
                j["percent"] = percent
                j["message"] = message

    upload_path: Path = rename_jobs[job_id]["upload_path"]
    zip_path = RENAME_OUTPUT_DIR / f"{job_id}_renamed.zip"

    try:
        manifest = rename_zip_images(upload_path, zip_path, cb=progress_cb)
        with rename_jobs_lock:
            job = rename_jobs[job_id]
            job["status"] = "done"
            job["zip_path"] = zip_path
            job["manifest"] = manifest
            job["percent"] = 100
            job["message"] = "تمت إعادة الترتيب بنجاح."
    except RenamerError as e:
        with rename_jobs_lock:
            job = rename_jobs[job_id]
            job["status"] = "error"
            job["error"] = str(e)
            job["message"] = str(e)
    except Exception as e:
        with rename_jobs_lock:
            job = rename_jobs[job_id]
            job["status"] = "error"
            job["error"] = f"خطأ غير متوقع: {e}"
            job["message"] = job["error"]
    finally:
        try:
            if upload_path.exists():
                upload_path.unlink()
        except Exception:
            pass


@app.route("/api/rename/status/<job_id>")
def rename_status(job_id: str):
    with rename_jobs_lock:
        job = rename_jobs.get(job_id)
        if not job:
            return jsonify({"error": "غير موجود"}), 404
        return jsonify({
            "status": job["status"],
            "stage": job["stage"],
            "percent": job["percent"],
            "message": job["message"],
            "manifest": job["manifest"],
            "error": job["error"],
        })


@app.route("/api/rename/download/<job_id>")
def rename_download(job_id: str):
    with rename_jobs_lock:
        job = rename_jobs.get(job_id)
    if not job or job["status"] != "done" or not job["zip_path"] or not Path(job["zip_path"]).exists():
        abort(404)
    original_stem = Path(job["filename"]).stem
    download_name = f"{original_stem}_renamed.zip"
    return send_file(job["zip_path"], as_attachment=True, download_name=download_name)
