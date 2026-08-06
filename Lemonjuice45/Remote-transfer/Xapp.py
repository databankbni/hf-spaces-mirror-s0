import gradio as gr
import subprocess
import os
import re
import tempfile
import shutil
from collections import deque

def process_transfer(direct_url, yt_url, quality, threads, remote_name):
    # Input validation
    if not direct_url.strip() and not yt_url.strip():
        yield "❌ Error: Please provide either a Direct Link or a Website Link.", ""
        return

    # Check for rclone config
    if not os.path.exists("rclone.conf"):
        yield "❌ Error: 'rclone.conf' not found! Please upload it to the root directory of this Space.", ""
        return

    # Setup rotating log queue to prevent memory overload in UI
    log_queue = deque(maxlen=25)
    def append_log(text):
        if text.strip():
            log_queue.append(text.strip())
        return "\n".join(log_queue)

    # 1. Create a temporary workspace
    temp_dir = tempfile.mkdtemp()
    yield append_log(f"📁 Created temp workspace: {temp_dir}"), ""

    # Determine which URL to use (Direct takes priority if both are filled)
    target_url = direct_url.strip() if direct_url.strip() else yt_url.strip()
    is_ytdlp = bool(yt_url.strip() and not direct_url.strip())

    # ================= DOWNLOAD PHASE =================
    yield append_log("⏳ Starting Download Phase..."), ""

    if not is_ytdlp:
        # Direct Download via Aria2c
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
        # Website Video Download via yt-dlp -> passing to aria2c
        format_map = {
            "Best video": "bestvideo+bestaudio/best",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]"
        }
        yt_format = format_map.get(quality, "best")
        
        # aria2c args passed through yt-dlp
        aria2c_args = f"aria2c:-x {int(threads)} -s {int(threads)} -j {int(threads)} --summary-interval=1"
        
        cmd = [
            "yt-dlp",
            "-f", yt_format,
            "--external-downloader", "aria2c",
            "--external-downloader-args", aria2c_args,
            "-P", temp_dir,
            target_url
        ]

    # Execute Download Command
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    for line in proc.stdout:
        # Yield line-by-line updates for live progress bar effect (Speed, ETA, %)
        yield append_log(line), ""
    proc.wait()

    if proc.returncode != 0:
        yield append_log("❌ Download failed! Please check the logs above."), ""
        shutil.rmtree(temp_dir)
        return

    # Verify downloaded files
    files = os.listdir(temp_dir)
    if not files:
        yield append_log("❌ No files were found in the temp directory after download."), ""
        shutil.rmtree(temp_dir)
        return

    yield append_log(f"✅ Download complete. Found {len(files)} file(s)."), ""

    # ================= UPLOAD PHASE =================
    upload_folder = "Remote_Transfers"
    yield append_log(f"⏳ Starting Upload Phase to {remote_name}:{upload_folder} ..."), ""

    # Rclone copy with --stats-one-line to keep logs clean and readable
    rclone_cmd = [
        "rclone", "copy", temp_dir, f"{remote_name}:{upload_folder}",
        "--stats", "1s", "--stats-one-line", "--config", "rclone.conf"
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
        # Use rclone link to generate a shareable link
        link_cmd = ["rclone", "link", f"{remote_name}:{upload_folder}/{f}", "--config", "rclone.conf"]
        link_proc = subprocess.run(link_cmd, capture_output=True, text=True)

        if link_proc.returncode == 0:
            share_link = link_proc.stdout.strip()
            
            # Extract Drive File ID to create a direct download link
            match = re.search(r'/d/([a-zA-Z0-9_-]+)', share_link) or re.search(r'id=([a-zA-Z0-9_-]+)', share_link)
            if match:
                file_id = match.group(1)
                direct_link = f"https://drive.google.com/uc?export=download&id={file_id}"
                final_links.append(f"📁 **{f}**\n📥 Direct Download: {direct_link}\n🔗 Standard Link: {share_link}")
            else:
                final_links.append(f"📁 **{f}**\n🔗 Link: {share_link}")
        else:
            final_links.append(f"📁 **{f}**\n❌ Failed to generate link.")

    # Cleanup temp workspace
    shutil.rmtree(temp_dir)
    links_str = "\n\n".join(final_links)
    
    yield append_log("🗑️ Temp files cleaned up. All tasks finished successfully! 🎉"), links_str


# ================= GRADIO UI =================
with gr.Blocks(title="Cloud Transfer Tool") as app:
    gr.Markdown(
        """
        # 🚀 Direct URL / Video to Google Drive
        High-speed transfer tool. Downloads files locally to this Space using **Aria2** or **yt-dlp**, then seamlessly pushes them to your Google Drive via **Rclone**.
        """
    )
    
    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("### 1. Choose Download Method")
            gr.Markdown("*Fill only **ONE** of the following boxes. Direct Link takes priority.*")
            direct_url = gr.Textbox(label="Direct Download Link (Aria2)", placeholder="https://example.com/file.zip")
            
            yt_url = gr.Textbox(label="Website Link (yt-dlp)", placeholder="https://youtube.com/watch?v=...")
            quality = gr.Dropdown(
                choices=["Best video", "1080p", "720p", "480p", "360p"], 
                value="Best video", 
                label="Video Quality (Only applies if using yt-dlp)"
            )

        with gr.Column(scale=1):
            gr.Markdown("### 2. Configuration")
            threads = gr.Slider(minimum=1, maximum=16, step=1, value=4, label="Download Threads (Aria2)")
            remote_name = gr.Textbox(label="Rclone Remote Name", value="gdrive", info="Must match the remote name in your rclone.conf file.")
            
            start_btn = gr.Button("🚀 Start Transfer", variant="primary")

    with gr.Row():
        # Live log output
        log_output = gr.Textbox(label="Live Progress (%, ETA, Speed)", lines=12, max_lines=15, interactive=False)

    with gr.Row():
        # Final copyable links - removed deprecated `show_copy_button` argument
        link_output = gr.Textbox(label="Google Drive Download Links", lines=5, interactive=False)

    # Connect UI elements to Python function
    start_btn.click(
        fn=process_transfer,
        inputs=[direct_url, yt_url, quality, threads, remote_name],
        outputs=[log_output, link_output]
    )

if __name__ == "__main__":
    app.launch()