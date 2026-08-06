import gradio as gr
import subprocess
import os
import re
import time
import random
import tempfile
import json
import shutil
import urllib.parse

# ── Bot-avoidance: rotate user-agents ──────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def random_ua():
    return random.choice(USER_AGENTS)


def is_valid_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


# ── Progress parsers ────────────────────────────────────────────────────────
def parse_aria2_progress(line):
    m = re.search(r'\((\d+)%\).*?DL:([^\s]+)\s+ETA:([^\]]+)', line)
    if m:
        return int(m.group(1)), m.group(2), m.group(3)
    return None


def parse_rclone_progress(line):
    m = re.search(r'(\d+)%.*?([0-9.]+\s*[KMGTkmgt]?Bytes/s).*?ETA\s+([^\s,]+)', line)
    if m:
        return int(m.group(1)), m.group(2), m.group(3)
    return None


def fmt_elapsed(start_time):
    s = int(time.time() - start_time)
    return f"{s // 60:02d}:{s % 60:02d}"


# ── STEP 1: DOWNLOAD & DETECT AUDIO ──────────────────────────────────────────
def start_download(direct_url, threads, session_state):
    """session_state is a per-user dict (gr.State), not a global — safe for
    multiple concurrent users."""
    direct_url = (direct_url or "").strip()

    if not direct_url:
        yield (gr.update(value=0, label="Error"), "❌ Error: Please provide a Direct Link.",
               "—", "—", gr.update(choices=[]), session_state)
        return

    if not is_valid_url(direct_url):
        yield (gr.update(value=0, label="Error"), "❌ Error: Please provide a valid http(s) URL.",
               "—", "—", gr.update(choices=[]), session_state)
        return

    temp_dir = tempfile.mkdtemp()
    session_state = {"temp_dir": temp_dir, "downloaded_file": None}
    start_time = time.time()

    ua = random_ua()
    cmd = [
        "aria2c", "-x", str(int(threads)), "-s", str(int(threads)), "-j", "1",
        "--min-split-size=5M", "--summary-interval=1", "--console-log-level=notice",
        "--user-agent", ua, "-d", temp_dir, direct_url,
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 universal_newlines=True, bufsize=1)
    except FileNotFoundError:
        shutil.rmtree(temp_dir, ignore_errors=True)
        yield (gr.update(value=0, label="Error"), "❌ aria2c not found on this system.",
               "—", "—", gr.update(choices=[]), session_state)
        return

    pct, speed_str, eta_str = 0, "—", "—"
    for line in proc.stdout:
        parsed = parse_aria2_progress(line.rstrip())
        if parsed:
            pct, speed_str, eta_str = parsed
            pct = min(int(float(pct)), 99)
        yield (gr.update(value=pct, label=f"Download: {pct}% | ⏱ {fmt_elapsed(start_time)}"),
               f"📥 Downloading… {pct}%", speed_str, eta_str, gr.update(), session_state)

    proc.wait()

    if proc.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        yield (gr.update(value=0, label="Failed"), "❌ Download failed.",
               "—", "—", gr.update(choices=[]), session_state)
        return

    files = os.listdir(temp_dir)
    if not files:
        shutil.rmtree(temp_dir, ignore_errors=True)
        yield (gr.update(value=0, label="No files"), "❌ No files found after download.",
               "—", "—", gr.update(choices=[]), session_state)
        return

    downloaded_file = os.path.join(temp_dir, files[0])
    session_state["downloaded_file"] = downloaded_file

    # Detect audio tracks via ffprobe (no shell=True — safer + handles odd filenames)
    audio_options = []
    try:
        ffprobe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=index:stream_tags=language,title",
            "-select_streams", "a", "-of", "json", downloaded_file,
        ]
        result = subprocess.check_output(ffprobe_cmd, text=True)
        data = json.loads(result)
        for track in data.get("streams", []):
            idx = track.get("index")
            tags = track.get("tags", {})
            lang = tags.get("language", "unknown")
            title = tags.get("title", "No Title")
            audio_options.append(f"Track ID: {idx} [Lang: {lang} | {title}]")
    except Exception:
        audio_options = []

    if not audio_options:
        audio_options = ["No multiple audio tracks found (Default)"]

    yield (
        gr.update(value=100, label="Download complete ✅"),
        "✅ File downloaded. Now select an audio track below and click 'Process & Upload'!",
        "—", "—",
        gr.update(choices=audio_options, value=audio_options[0], interactive=True),
        session_state,
    )


# ── STEP 2: CUT AUDIO & UPLOAD VIA RCLONE ─────────────────────────────────────
def process_and_upload(selected_audio, remote_name, session_state):
    temp_dir = (session_state or {}).get("temp_dir")
    input_file = (session_state or {}).get("downloaded_file")
    remote_name = (remote_name or "").strip()

    if not temp_dir or not input_file or not os.path.exists(input_file):
        yield (gr.update(value=0, label="Error"), "❌ Session expired or file not found. Download again.",
               "", "—", "—")
        return

    if not remote_name:
        yield (gr.update(value=0, label="Error"), "❌ Please provide an rclone remote name.", "", "—", "—")
        return

    rclone_conf = "rclone.conf"
    if not os.path.exists(rclone_conf):
        yield (gr.update(value=0, label="Error"), "❌ 'rclone.conf' not found in root directory!", "", "—", "—")
        return

    start_time = time.time()

    try:
        # Parse selected track index (fallback: keep every audio stream, don't guess a bad map)
        track_map = None
        match = re.search(r'Track ID:\s*(\d+)', selected_audio or "")
        if match:
            track_map = f"0:{match.group(1)}"

        output_file = os.path.join(temp_dir, "processed_" + os.path.basename(input_file))

        if track_map:
            yield (gr.update(value=10, label="FFmpeg Processing..."),
                   "✂️ Cutting extra audio tracks (Lossless, subtitles kept)...", "", "—", "—")
            # -map 0:s? keeps ALL subtitle streams (the "?" makes it optional so
            # ffmpeg won't error out on files that have no subtitles at all).
            # -map 0:t? keeps any attachments (e.g. embedded fonts used by ASS/SSA subs).
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", input_file,
                "-map", "0:v:0",
                "-map", track_map,
                "-map", "0:s?",
                "-map", "0:t?",
                "-c", "copy",
                output_file,
            ]
            result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            if result.returncode == 0 and os.path.exists(output_file):
                os.remove(input_file)  # free space, keep only the trimmed file
            else:
                # ffmpeg failed — keep the original file instead of silently uploading
                # a "cut" file that doesn't exist
                output_file = input_file
                yield (gr.update(value=15, label="FFmpeg warning"),
                       "⚠️ Audio cut failed, uploading original file instead.", "", "—", "—")
        else:
            output_file = input_file  # no valid track selected — upload as-is

        # Rclone Upload
        upload_folder = "Remote_Transfers"
        yield (gr.update(value=20, label="Upload: 0%"),
               f"⏳ Uploading to {remote_name}:{upload_folder}…", "", "—", "—")

        rclone_cmd = [
            "rclone", "copy", temp_dir, f"{remote_name}:{upload_folder}",
            "--transfers", "32", "--checkers", "32", "--drive-chunk-size", "256M",
            "--buffer-size", "256M", "--multi-thread-streams", "8",
            "--stats", "1s", "--stats-one-line", "--config", rclone_conf,
        ]

        proc = subprocess.Popen(rclone_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 universal_newlines=True, bufsize=1)

        pct, speed_str, eta_str = 20, "—", "—"
        for line in proc.stdout:
            parsed = parse_rclone_progress(line.rstrip())
            if parsed:
                r_pct, speed_str, eta_str = parsed
                pct = 20 + int((r_pct / 100) * 79)  # scale rclone 0-100% into overall 20-99%
            yield (gr.update(value=pct, label=f"Uploading: {pct}% | ⏱ {fmt_elapsed(start_time)}"),
                   f"☁️ Uploading… {pct}%", "", speed_str, eta_str)

        proc.wait()

        if proc.returncode != 0:
            yield (gr.update(value=0, label="Upload failed"),
                   "❌ Upload failed. Check rclone.conf / remote name.", "", "—", "—")
            return

        # Share link generation
        yield (gr.update(value=100, label="Generating Links..."),
               "🔗 Generating direct share links…", "", "—", "—")

        final_links = []
        final_file_name = os.path.basename(output_file)
        link_cmd = ["rclone", "link", f"{remote_name}:{upload_folder}/{final_file_name}",
                    "--config", rclone_conf]
        link_proc = subprocess.run(link_cmd, capture_output=True, text=True)

        if link_proc.returncode == 0 and link_proc.stdout.strip():
            share_link = link_proc.stdout.strip()
            m = re.search(r'/d/([a-zA-Z0-9_-]+)', share_link) or re.search(r'id=([a-zA-Z0-9_-]+)', share_link)
            final_links.append(
                f"https://drive.google.com/uc?export=download&id={m.group(1)}" if m else share_link
            )
        else:
            final_links.append(f"❌ rclone link failed: {link_proc.stderr.strip()[:200]}")

        yield (
            gr.update(value=100, label=f"Done ✅ | Time: {fmt_elapsed(start_time)}"),
            "🎉 Success! Audio removed without re-encoding, subtitles kept.",
            "\n".join(final_links), "—", "—",
        )
    finally:
        # Always clean up, even if something raised above
        shutil.rmtree(temp_dir, ignore_errors=True)


# ── Gradio UI ───────────────────────────────────────────────────────────────
with gr.Blocks(title="Aria2 Audio Cutter & Cloud Uploader", theme=gr.themes.Soft()) as app:
    session_state = gr.State({"temp_dir": None, "downloaded_file": None})

    gr.Markdown("# 🚀 Aria2 Audio Cutter & G-Drive Uploader")
    gr.Markdown("Lossless Audio Cutter: Extra tracks stream out hone se video quality par 0% effect padega.")

    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("### 📥 Step 1: Download & Analyze")
            direct_url = gr.Textbox(label="Direct MKV Link", placeholder="https://example.com/movie.mkv")
            threads = gr.Slider(minimum=1, maximum=16, step=1, value=8, label="Download Threads")
            download_btn = gr.Button("📥 Start Download", variant="primary")

            gr.Markdown("### ✂️ Step 2: Audio Selection & Upload")
            audio_dropdown = gr.Dropdown(choices=[], label="Detected Audio Tracks", interactive=False,
                                          info="Download complete hone par yahan tracks dikhenge.")
            remote_name = gr.Textbox(label="Rclone Remote Name", value="gdrive")
            upload_btn = gr.Button("⚡ Process & Upload", variant="secondary")

    with gr.Row():
        progress_bar = gr.Slider(minimum=0, maximum=100, value=0, step=1, label="Progress Status", interactive=False)

    with gr.Row():
        speed_box = gr.Textbox(label="⚡ Speed", value="—", interactive=False)
        eta_box = gr.Textbox(label="⏳ ETA", value="—", interactive=False)
        status_box = gr.Textbox(label="📊 Status Message", value="", interactive=False)

    with gr.Row():
        link_output = gr.Textbox(label="📥 Google Drive Direct Public Link", lines=2, interactive=False,
                                  placeholder="Direct links will appear here…")

    download_btn.click(
        fn=start_download,
        inputs=[direct_url, threads, session_state],
        outputs=[progress_bar, status_box, speed_box, eta_box, audio_dropdown, session_state],
    )

    upload_btn.click(
        fn=process_and_upload,
        inputs=[audio_dropdown, remote_name, session_state],
        outputs=[progress_bar, status_box, link_output, speed_box, eta_box],
    )

if __name__ == "__main__":
    app.launch()
