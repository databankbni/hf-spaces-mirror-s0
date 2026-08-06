import gradio as gr
import subprocess
import os
import re
import time
import random
import tempfile
import json
import shutil

# ── Bot-avoidance: rotate user-agents ──────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

def random_ua():
    return random.choice(USER_AGENTS)

# Global temporary session state to store paths between download and upload steps
SESSION_DATA = {"temp_dir": None, "downloaded_file": None}

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

# ── STEP 1: DOWNLOAD & DETECT AUDIO ──────────────────────────────────────────
def start_download(direct_url, threads):
    if not direct_url.strip():
        return (gr.update(value=0, label="Error"), "❌ Error: Please provide a Direct Link.", "—", "—", gr.update(choices=[]))
    
    # Create persistent temp directory for session
    SESSION_DATA["temp_dir"] = tempfile.mkdtemp()
    temp_dir = SESSION_DATA["temp_dir"]
    start_time = time.time()
    
    def elapsed():
        s = int(time.time() - start_time)
        return f"{s//60:02d}:{s%60:02d}"

    ua = random_ua()
    cmd = [
        "aria2c", "-x", str(int(threads)), "-s", str(int(threads)), "-j", "1",
        "--min-split-size=5M", "--summary-interval=1", "--console-log-level=notice",
        "--user-agent", ua, "-d", temp_dir, direct_url
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1)
    
    pct, speed_str, eta_str = 0, "—", "—"
    for line in proc.stdout:
        parsed = parse_aria2_progress(line.rstrip())
        if parsed:
            pct, speed_str, eta_str = parsed
            pct = min(int(float(pct)), 99)
        yield (gr.update(value=pct, label=f"Download: {pct}% | ⏱ {elapsed()}"), f"📥 Downloading… {pct}%", speed_str, eta_str, gr.update())

    proc.wait()

    if proc.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        yield (gr.update(value=0, label="Failed"), "❌ Download failed.", "—", "—", gr.update(choices=[]))
        return

    files = os.listdir(temp_dir)
    if not files:
        yield (gr.update(value=0, label="No files"), "❌ No files found after download.", "—", "—", gr.update(choices=[]))
        return

    SESSION_DATA["downloaded_file"] = os.path.join(temp_dir, files[0])
    input_file = SESSION_DATA["downloaded_file"]

    # Detect Audios via FFprobe
    ffprobe_cmd = f'ffprobe -v error -show_entries stream=index:tags=language,title -select_streams a -of json "{input_file}"'
    try:
        result = subprocess.check_output(ffprobe_cmd, shell=True).decode('utf-8')
        data = json.loads(result)
        audio_options = []
        if 'streams' in data:
            for track in data['streams']:
                idx = track.get('index')
                lang = track.get('tags', {}).get('language', 'unknown')
                title = track.get('tags', {}).get('title', 'No Title')
                audio_options.append(f"Track ID: {idx} [Lang: {lang} | {title}]")
        
        if not audio_options:
            audio_options = ["No multiple audio tracks found (Default)"]
    except Exception as e:
        audio_options = ["Error reading audio tracks, copying all."]

    yield (
        gr.update(value=100, label="Download complete ✅"),
        f"✅ File downloaded. Now select an audio track below and click 'Process & Upload'!",
        "—", "—",
        gr.update(choices=audio_options, value=audio_options[0] if audio_options else None, interactive=True)
    )

# ── STEP 2: CUT AUDIO & UPLOAD VIA RCLONE ─────────────────────────────────────
def process_and_upload(selected_audio, remote_name):
    temp_dir = SESSION_DATA.get("temp_dir")
    input_file = SESSION_DATA.get("downloaded_file")

    if not temp_dir or not input_file or not os.path.exists(input_file):
        yield (gr.update(value=0, label="Error"), "❌ Session expired or file not found. Download again.", "", "—", "—")
        return

    if not os.path.exists("rclone.conf"):
        yield (gr.update(value=0, label="Error"), "❌ 'rclone.conf' not found in root directory!", "", "—", "—")
        return

    start_time = time.time()
    def elapsed():
        s = int(time.time() - start_time)
        return f"{s//60:02d}:{s%60:02d}"

    # Parse selected track ID
    track_id = "0:a:0"  # default fallback
    match = re.search(r'Track ID:\s*(\d+)', selected_audio)
    if match:
        track_id = match.group(1)

    # 1. Lossless FFmpeg Stream Copying
    yield (gr.update(value=10, label="FFmpeg Processing..."), "✂️ Cutting extra audio tracks (Lossless)...", "", "—", "—")
    output_file = os.path.join(temp_dir, "processed_" + os.path.basename(input_file))
    
    ffmpeg_cmd = f'ffmpeg -y -i "{input_file}" -map 0:v:0 -map 0:{track_id} -c copy "{output_file}"'
    os.system(ffmpeg_cmd)
    
    # Remove original file to save space before uploading
    if os.path.exists(output_file):
        os.remove(input_file)
    else:
        output_file = input_file # fallback if ffmpeg fails

    # 2. Rclone Upload
    upload_folder = "Remote_Transfers"
    yield (gr.update(value=20, label="Upload: 0%"), f"⏳ Uploading to {remote_name}:{upload_folder}…", "", "—", "—")

    rclone_cmd = [
        "rclone", "copy", temp_dir, f"{remote_name}:{upload_folder}",
        "--transfers", "32", "--checkers", "32", "--drive-chunk-size", "256M",
        "--buffer-size", "256M", "--multi-thread-streams", "8",
        "--stats", "1s", "--stats-one-line", "--config", "rclone.conf",
    ]

    proc = subprocess.Popen(rclone_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1)

    pct, speed_str, eta_str = 20, "—", "—"
    for line in proc.stdout:
        parsed = parse_rclone_progress(line.rstrip())
        if parsed:
            r_pct, speed_str, eta_str = parsed
            pct = 20 + int((r_pct / 100) * 79) # Scale rclone 0-100% to overall 20-99%
        yield (gr.update(value=pct, label=f"Uploading: {pct}% | ⏱ {elapsed()}"), f"☁️ Uploading… {pct}%", "", speed_str, eta_str)

    proc.wait()

    if proc.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        yield (gr.update(value=0, label="Upload failed"), "❌ Upload failed. Check rclone.conf / remote name.", "", "—", "—")
        return

    # 3. Share Link Generation
    yield (gr.update(value=100, label="Generating Links..."), "🔗 Generating direct share links…", "", "—", "—")
    final_links = []
    final_file_name = os.path.basename(output_file)
    
    link_cmd = ["rclone", "link", f"{remote_name}:{upload_folder}/{final_file_name}", "--config", "rclone.conf"]
    link_proc = subprocess.run(link_cmd, capture_output=True, text=True)
    
    if link_proc.returncode == 0:
        share_link = link_proc.stdout.strip()
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', share_link) or re.search(r'id=([a-zA-Z0-9_-]+)', share_link)
        if match:
            file_id = match.group(1)
            final_links.append(f"https://drive.google.com/uc?export=download&id={file_id}")
        else:
            final_links.append(share_link)
    else:
        final_links.append(f"❌ rclone link failed.")

    shutil.rmtree(temp_dir, ignore_errors=True)
    yield (
        gr.update(value=100, label=f"Done ✅ | Time: {elapsed()}"),
        f"🎉 Success! Audio removed without re-encoding.",
        "\n".join(final_links), "—", "—"
    )

# ── Gradio UI ───────────────────────────────────────────────────────────────
with gr.Blocks(title="Aria2 Audio Cutter & Cloud Uploader", theme=gr.themes.Soft()) as app:
    gr.Markdown("# 🚀 Aria2 Audio Cutter & G-Drive Uploader")
    gr.Markdown("Lossless Audio Cutter: Extra tracks stream out hone se video quality par 0% effect padega.")

    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("### 📥 Step 1: Download & Analyze")
            direct_url = gr.Textbox(label="Direct MKV Link", placeholder="https://example.com/movie.mkv")
            threads = gr.Slider(minimum=1, maximum=16, step=1, value=8, label="Download Threads")
            download_btn = gr.Button("📥 Start Download", variant="primary")
            
            gr.Markdown("### ✂️ Step 2: Audio Selection & Upload")
            audio_dropdown = gr.Dropdown(choices=[], label="Detected Audio Tracks", interactive=False, info="Download complete hone par yahan tracks dikhenge.")
            remote_name = gr.Textbox(label="Rclone Remote Name", value="gdrive")
            upload_btn = gr.Button("⚡ Process & Upload", variant="secondary")

    with gr.Row():
        progress_bar = gr.Slider(minimum=0, maximum=100, value=0, step=1, label="Progress Status", interactive=False)

    with gr.Row():
        speed_box = gr.Textbox(label="⚡ Speed", value="—", interactive=False)
        eta_box = gr.Textbox(label="⏳ ETA", value="—", interactive=False)
        status_box = gr.Textbox(label="📊 Status Message", value="", interactive=False)

    with gr.Row():
        link_output = gr.Textbox(label="📥 Google Drive Direct Public Link", lines=2, interactive=False, placeholder="Direct links will appear here…")

    # Click Events mapping
    download_btn.click(
        fn=start_download,
        inputs=[direct_url, threads],
        outputs=[progress_bar, status_box, speed_box, eta_box, audio_dropdown]
    )

    upload_btn.click(
        fn=process_and_upload,
        inputs=[audio_dropdown, remote_name],
        outputs=[progress_bar, status_box, link_output, speed_box, eta_box]
    )

if __name__ == "__main__":
    app.launch()
