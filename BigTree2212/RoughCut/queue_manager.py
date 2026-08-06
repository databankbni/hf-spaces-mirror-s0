"""Single global work queue shared by every tool blueprint.

Only one job (regardless of which tool submitted it) runs at a time — both
ffmpeg re-encoding and whisper transcription are CPU-heavy, and running them
concurrently would oversubscribe the shared host. Each tool keeps its own
job registry; this module only owns cross-tool ordering.
"""
import threading
import queue
import time
import traceback

_lock = threading.Lock()
_pending = []       # FIFO list of dicts: {"tool", "job_id", "filename", "submitted_at"}
_current = None     # dict of the ticket currently executing, or None
_task_queue = queue.Queue()


def submit(tool, job_id, filename, run_fn):
    """Enqueue run_fn to execute once every earlier ticket has finished.

    No-ops if (tool, job_id) is already current or already pending, so a
    retry/crash-requeue call site can call this again without risking the
    same job running twice back-to-back.
    """
    with _lock:
        if _current and _current["tool"] == tool and _current["job_id"] == job_id:
            return
        if any(e["tool"] == tool and e["job_id"] == job_id for e in _pending):
            return
        entry = {"tool": tool, "job_id": job_id, "filename": filename, "submitted_at": time.time()}
        _pending.append(entry)
    _task_queue.put((entry, run_fn))


def position_of(tool, job_id):
    """0 = currently running, 1+ = queue position, None = not tracked."""
    with _lock:
        if _current and _current["tool"] == tool and _current["job_id"] == job_id:
            return 0
        for i, e in enumerate(_pending):
            if e["tool"] == tool and e["job_id"] == job_id:
                return i + 1
    return None


def snapshot():
    """Returns (current, pending) as plain-data copies safe to hand to callers."""
    with _lock:
        current = dict(_current) if _current else None
        pending = [dict(e) for e in _pending]
    return current, pending


def _worker_loop():
    global _current
    while True:
        entry, run_fn = _task_queue.get()
        with _lock:
            _pending[:] = [
                e for e in _pending
                if not (e["tool"] == entry["tool"] and e["job_id"] == entry["job_id"])
            ]
            _current = entry
        try:
            run_fn()
        except Exception:
            # Every run_fn is expected to catch its own errors and record them
            # on its own job — this is a last-resort net so one broken ticket
            # can never take down processing for every job after it.
            traceback.print_exc()
            print(f"[queue_manager] run_fn crashed for {entry['tool']}/{entry['job_id']}")
        finally:
            with _lock:
                _current = None
            _task_queue.task_done()


threading.Thread(target=_worker_loop, daemon=True).start()
