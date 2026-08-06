import gradio as gr
import subprocess
import os
import re
import tempfile
import shutil
from collections import deque

def process_transfer(direct_url, yt_url, quality, threads, remote_name):
    if not direct_url.strip() and not yt_url.strip():
        yield "❌ Error: Please provide either a Direct Link or a Website Link.", ""
        return

    if not os.path.exists("rclone.conf"):
        yield "❌ Error: 'rclone.conf' not found! Please upload it to the root directory of this Space.", ""
        return

    log_queue = deque(maxlen=25)
    def append_log(text):
        if text.strip():
            log_queue.append(text.strip())
        return "\n".join(log_queue)

    temp_dir = tempfile.mkdtemp()
    yield append_log(f"📁 Created temp workspace: {temp_dir}"), ""

    target_url = direct_url.strip() if direct_url.strip() else yt_url.strip()
    is_ytdlp = bool(yt_url.strip() and not direct_url.strip())

    # ================= DOWNLOAD PHASE =================
    yield append_log("⏳ Starting Download Phase..."), ""

    if not is_ytdlp:
        cmd = [
            "aria2c",
            "-x", str(int(threads)),
            "-s", str(int(threads)),
            "-j", str(int(threads)),
            "--summary-interval=1",
            "--console-log-level=notice",
            "-d", temp_dir,
            target_url
        ]
    else:
        format_map = {
            "Best video": "bestvideo+bestaudio/best",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]"
        }
        yt_format = format_map.get(quality, "best")
        aria2c_args = f"aria2c:-x {int(threads)} -s {int(threads)} -j {int(threads)} --summary-interval=1"
        cmd = [
            "yt-dlp",
            "-f", yt_format,
            "--external-downloader", "aria2c",
            "--external-downloader-args", aria2c_args,
            "-P", temp_dir,
            target_url
        ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    for line in proc.stdout:
        yield append_log(line), ""
    proc.wait()

    if proc.returncode != 0:
        yield append_log("❌ Download failed! Please check the logs above."), ""
        shutil.rmtree(temp_dir)
        return

    files = os.listdir(temp_dir)
    if not files:
        yield append_log("❌ No files found in temp directory after download."), ""
        shutil.rmtree(temp_dir)
        return

    yield append_log(f"✅ Download complete. Found {len(files)} file(s)."), ""

    # ================= UPLOAD PHASE =================
    upload_folder = "Remote_Transfers"
    yield append_log(f"⏳ Starting Upload Phase to {remote_name}:{upload_folder} ..."), ""

    rclone_cmd = [
        "rclone", "copy", temp_dir, f"{remote_name}:{upload_folder}",
        "--stats", "1s",
        "--stats-one-line",
        "--config", "rclone.conf",
        "--transfers", "16",
        "--checkers", "16",
        "--drive-chunk-size", "256M",
        "--drive-upload-cutoff", "256M",
        "--buffer-size", "256M",
        "--drive-acknowledge-abuse",
        "--ignore-checksum",
    ]

    proc = subprocess.Popen(rclone_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    for line in proc.stdout:
        yield append_log(line), ""
    proc.wait()

    if proc.returncode != 0:
        yield append_log("❌ Upload failed! Please check the logs above."), ""
        shutil.rmtree(temp_dir)
        return

    yield append_log("✅ Upload complete! Generating direct links..."), ""

    # ================= LINK GENERATION =================
    final_links = []
    for f in files:
        link_cmd = ["rclone", "link", f"{remote_name}:{upload_folder}/{f}", "--config", "rclone.conf"]
        link_proc = subprocess.run(link_cmd, capture_output=True, text=True)

        if link_proc.returncode == 0:
            share_link = link_proc.stdout.strip()
            match = re.search(r'/d/([a-zA-Z0-9_-]+)', share_link) or re.search(r'id=([a-zA-Z0-9_-]+)', share_link)
            if match:
                file_id = match.group(1)
                direct_link = f"https://drive.google.com/uc?export=download&id={file_id}"
                final_links.append(direct_link)
            else:
                final_links.append(f"❌ Could not extract direct link for: {f}")
        else:
            final_links.append(f"❌ Failed to generate link for: {f}")

    shutil.rmtree(temp_dir)
    links_str = "\n".join(final_links)
    yield append_log("🗑️ Temp files cleaned up. All done! 🎉"), links_str


def copy_link(link):
    if not link.strip():
        return gr.update(value="📋 Copy Link", variant="secondary")
    return gr.update(value="✅ Copied!", variant="primary")


# ================= GRADIO UI =================
with gr.Blocks(title="Cloud Transfer Tool", theme=gr.themes.Soft()) as app:
    gr.Markdown(
        """
        # 🚀 Direct URL / Video → Google Drive
        Downloads via **Aria2** or **yt-dlp**, then uploads to your Google Drive at maximum speed via **Rclone**.
        """
    )

    with gr.Row():
        # ---- Left Column: Input ----
        with gr.Column(scale=2):
            gr.Markdown("### 📥 Download Source")
            gr.Markdown("*Fill only **one** box. Direct Link takes priority if both are filled.*")

            direct_url = gr.Textbox(
                label="Direct Download Link (Aria2)",
                placeholder="https://example.com/file.zip"
            )
            yt_url = gr.Textbox(
                label="Website / YouTube Link (yt-dlp)",
                placeholder="https://youtube.com/watch?v=..."
            )
            quality = gr.Dropdown(
                choices=["Best video", "1080p", "720p", "480p", "360p"],
                value="Best video",
                label="Video Quality  (yt-dlp only)"
            )

        # ---- Right Column: Config ----
        with gr.Column(scale=1):
            gr.Markdown("### ⚙️ Configuration")
            threads = gr.Slider(
                minimum=1, maximum=16, step=1, value=8,
                label="Download Threads (Aria2)"
            )
            remote_name = gr.Textbox(
                label="Rclone Remote Name",
                value="gdrive",
                info="Must match the remote name in your rclone.conf file."
            )
            start_btn = gr.Button("🚀 Start Transfer", variant="primary", size="lg")

    # ---- Logs ----
    with gr.Row():
        log_output = gr.Textbox(
            label="📊 Live Progress  (Speed · ETA · %)",
            lines=12,
            max_lines=15,
            interactive=False
        )

    # ---- Output Link ----
    with gr.Row():
        with gr.Column():
            link_output = gr.Textbox(
                label="📥 Google Drive Direct Download Link",
                lines=3,
                interactive=False,
                placeholder="Your direct download link will appear here after transfer..."
            )
            copy_btn = gr.Button("📋 Copy Link", variant="secondary")

    # Copy to clipboard via JS
    copy_btn.click(
        fn=None,
        inputs=[link_output],
        outputs=[],
        js="(link) => { navigator.clipboard.writeText(link); }"
    )
    copy_btn.click(
        fn=copy_link,
        inputs=[link_output],
        outputs=[copy_btn]
    )

    start_btn.click(
        fn=process_transfer,
        inputs=[direct_url, yt_url, quality, threads, remote_name],
        outputs=[log_output, link_output]
    )

if __name__ == "__main__":
    app.launch()