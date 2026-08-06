import os

from flask import Flask, render_template, jsonify, url_for

import queue_manager
from blueprints.silence_cutter import (
    bp as silence_cutter_bp,
    register_error_handlers as register_silence_cutter_errors,
    get_job_brief as sc_job_brief,
)
from blueprints.transcript import bp as transcript_bp, get_job_brief as tr_job_brief
from blueprints.video_downloader import bp as video_downloader_bp, get_job_brief as vd_job_brief

app = Flask(__name__)

# The larger of the two tools' upload limits applies at the WSGI level;
# each blueprint still enforces its own (smaller) limit where relevant.
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024 * 1024  # 12 GB

# Flask's default static-file response sends Cache-Control: no-cache, which
# forces a network round trip (even if it's just a cheap 304) on every single
# asset, on every page navigation. That's invisible on localhost (~0ms
# loopback) but adds up to real, noticeable delay on a hosted deployment —
# this is what made clicking between nav tabs feel slow only once published.
# SEND_FILE_MAX_AGE_DEFAULT lets the browser skip the round trip entirely for
# a while; static_url() below appends a content-based version so a future
# deploy's changed files still bust the old cached copy immediately.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24 * 365  # 1 year

_static_versions = {}


@app.template_global()
def static_url(filename):
    if filename not in _static_versions:
        path = os.path.join(app.static_folder, filename)
        try:
            _static_versions[filename] = str(int(os.path.getmtime(path)))
        except OSError:
            _static_versions[filename] = "0"
    return url_for("static", filename=filename, v=_static_versions[filename])


app.register_blueprint(silence_cutter_bp)
app.register_blueprint(transcript_bp)
app.register_blueprint(video_downloader_bp)
register_silence_cutter_errors(app)

TOOL_LABELS = {
    "silence-cutter": "Silence Cutter",
    "transcript": "Transcript",
    "video-downloader": "Video Downloader",
}
JOB_BRIEF_FNS = {
    "silence-cutter": sc_job_brief,
    "transcript": tr_job_brief,
    "video-downloader": vd_job_brief,
}


@app.route("/")
def home():
    return render_template("home.html", active_tool="home")


@app.route("/queue")
def queue_page():
    return render_template("queue.html", active_tool="queue")


@app.route("/api/queue-overview")
def queue_overview():
    current, pending = queue_manager.snapshot()

    current_out = None
    if current:
        brief = JOB_BRIEF_FNS[current["tool"]](current["job_id"])
        if brief:  # job could have vanished (e.g. deleted right as it became current)
            current_out = {**current, **brief, "tool_label": TOOL_LABELS[current["tool"]]}

    pending_out = [
        {**e, "position": i + 1, "tool_label": TOOL_LABELS[e["tool"]]}
        for i, e in enumerate(pending)
    ]

    return jsonify({"current": current_out, "pending": pending_out})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "7860"))
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
