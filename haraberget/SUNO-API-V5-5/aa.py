import gradio as gr
import requests
import os
import time
import json
import hashlib
import hmac
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import tempfile

# Suno API key
SUNO_KEY = os.environ.get("SunoKey", "")
# Secret key for ownership proofs
SECRET_SALT = "Salt"  # You might want to make this configurable

if not SUNO_KEY:
    print("⚠️ SunoKey not set!")

def generate_ownership_proof(task_id, title, music_id=None):
    """
    Generate a SHA256 hash proof using task_id as seed
    """
    proof_data = {
        "task_id": task_id,
        "title": title,
        "music_id": music_id,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    proof_string = json.dumps(proof_data, sort_keys=True)
    
    signature = hmac.new(
        SECRET_SALT.encode('utf-8'),
        proof_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return {
        "proof": signature,
        "data": proof_data,
        "version": "1.0"
    }

def create_simple_receipt(task_id, title):
    """
    Create a simple JSON receipt with task ID and title
    """
    proof = generate_ownership_proof(task_id, title)
    
    receipt = {
        "receipt_type": "song_ownership_proof",
        "generated": datetime.now().isoformat(),
        "task_id": task_id,
        "title": title,
        "proof": proof,
        "check_url": f"https://1hit.no/gen/view.php?taskid={task_id}"
    }
    
    return receipt

def create_html_receipt(receipt):
    """
    Create a simple HTML viewer for the receipt
    """
    task_id = receipt['task_id']
    title = receipt['title']
    proof = receipt['proof']
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Song Receipt - {title}</title>
    <style>
        body {{ font-family: Arial; max-width: 800px; margin: 40px auto; padding: 20px; }}
        .receipt {{ border: 2px solid #333; padding: 20px; border-radius: 10px; }}
        .proof {{ background: #f0f0f0; padding: 10px; word-break: break-all; font-family: monospace; }}
        h1 {{ color: #2c3e50; }}
        .button {{ background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="receipt">
        <h1>🎵 Song Ownership Receipt</h1>
        <p><strong>Generated:</strong> {receipt['generated']}</p>
        <p><strong>Title:</strong> {title}</p>
        <p><strong>Task ID:</strong> <code>{task_id}</code></p>
        
        <h3>🔐 Proof</h3>
        <div class="proof">
            <strong>Hash:</strong> {proof['proof']}<br>
            <strong>Signed Data:</strong> {json.dumps(proof['data'])}
        </div>
        
        <p><strong>Check Status:</strong> <a href="{receipt['check_url']}">{receipt['check_url']}</a></p>
        
        <p><small>Save this receipt to prove you created this song request.</small></p>
    </div>
</body>
</html>"""
    
    return html

def get_task_info(task_id):
    """Manually check any Suno task status"""
    if not task_id:
        return "❌ Please enter a Task ID"
    
    try:
        resp = requests.get(
            "https://api.sunoapi.org/api/v1/generate/record-info",
            headers={"Authorization": f"Bearer {SUNO_KEY}"},
            params={"taskId": task_id},
            timeout=30
        )
        
        if resp.status_code != 200:
            return f"❌ HTTP Error {resp.status_code}\n\n{resp.text}"
        
        data = resp.json()
        
        # Format the response for display
        output = f"## 🔍 Task Status: `{task_id}`\n\n"
        
        if data.get("code") == 200:
            task_data = data.get("data", {})
            status = task_data.get("status", "UNKNOWN")
            
            output += f"**Status:** {status}\n"
            output += f"**Task ID:** `{task_data.get('taskId', 'N/A')}`\n"
            output += f"**Music ID:** `{task_data.get('musicId', 'N/A')}`\n"
            output += f"**Created:** {task_data.get('createTime', 'N/A')}\n"
            
            if status == "SUCCESS" or status == "TEXT_SUCCESS":
                response_data = task_data.get("response", {})
                
                # Try to parse response (could be string or dict)
                if isinstance(response_data, str):
                    try:
                        response_data = json.loads(response_data)
                    except:
                        output += f"\n**Raw Response:**\n```\n{response_data}\n```\n"
                        response_data = {}
                
                # Check for song data
                songs = []
                if isinstance(response_data, dict):
                    songs = response_data.get("sunoData", [])
                    if not songs:
                        songs = response_data.get("data", [])
                elif isinstance(response_data, list):
                    songs = response_data
                
                if songs:
                    output += f"\n## 🎵 Generated Songs ({len(songs)})\n\n"
                    
                    for i, song in enumerate(songs, 1):
                        if isinstance(song, dict):
                            output += f"### Song {i}\n"
                            output += f"**Title:** {song.get('title', 'Untitled')}\n"
                            output += f"**ID:** `{song.get('id', 'N/A')}`\n"
                            
                            # Audio URLs
                            audio_url = song.get('audioUrl') or song.get('audio_url')
                            stream_url = song.get('streamUrl') or song.get('stream_url')
                            download_url = song.get('downloadUrl') or song.get('download_url')
                            
                            if audio_url:
                                output += f"**Audio:** [Play]({audio_url}) | [Download]({audio_url})\n"
                            elif stream_url:
                                output += f"**Stream:** [Play]({stream_url})\n"
                            
                            if download_url:
                                output += f"**Download:** [MP3]({download_url})\n"
                            
                            # Audio player
                            play_url = audio_url or stream_url
                            if play_url:
                                output += f"""\n<audio controls style="width: 100%; margin: 10px 0;">
                                    <source src="{play_url}" type="audio/mpeg">
                                    Your browser does not support audio.
                                </audio>\n"""
                            
                            output += f"**Prompt:** {song.get('prompt', 'N/A')[:100]}...\n"
                            output += f"**Duration:** {song.get('duration', 'N/A')}s\n"
                            output += f"**Created:** {song.get('createTime', 'N/A')}\n\n"
                            output += "---\n\n"
                else:
                    output += "\n**No song data found in response.**\n"
                    
            elif status == "FAILED":
                error_msg = task_data.get("errorMessage", "Unknown error")
                output += f"\n**Error:** {error_msg}\n"
            
            elif status in ["PENDING", "PROCESSING", "RUNNING"]:
                output += f"\n**Task is still processing...**\n"
                output += f"Check again in 30 seconds.\n"
            
            else:
                output += f"\n**Unknown status:** {status}\n"
        
        else:
            output += f"**API Error:** {data.get('msg', 'Unknown')}\n"
        
        # Show raw JSON for debugging
        output += "\n## 📋 Raw Response\n"
        output += f"```json\n{json.dumps(data, indent=2)}\n```"
        
        return output
        
    except Exception as e:
        return f"❌ Error checking task: {str(e)}"

def generate_song_from_text(lyrics_text, style, title, instrumental, model):
    """Generate a song from lyrics text"""
    if not SUNO_KEY:
        yield "❌ Error: SunoKey not configured in environment variables"
        return
    
    if not lyrics_text.strip() and not instrumental:
        yield "❌ Error: Please provide lyrics or select instrumental"
        return
    
    if not style.strip():
        yield "❌ Error: Please provide a music style"
        return
    
    if not title.strip():
        yield "❌ Error: Please provide a song title"
        return
    
    try:
        # Prepare request data
        request_data = {
            "customMode": True,
            "instrumental": instrumental,
            "model": model,
            "callBackUrl": "https://1hit.no/gen/cb.php",
            "style": style,
            "title": title,
        }
        
        if not instrumental:
            # Apply character limits
            if model == "V4" and len(lyrics_text) > 3000:
                lyrics_text = lyrics_text[:3000]
                yield f"⚠️ Lyrics truncated to 3000 characters for V4 model\n\n"
            elif model in ["V4_5", "V4_5PLUS", "V4_5ALL", "V5"] and len(lyrics_text) > 5000:
                lyrics_text = lyrics_text[:5000]
                yield f"⚠️ Lyrics truncated to 5000 characters for {model} model\n\n"
            
            request_data["prompt"] = lyrics_text
        else:
            request_data["prompt"] = ""
        
        # Apply style length limits
        if model == "V4" and len(style) > 200:
            style = style[:200]
            yield f"⚠️ Style truncated to 200 characters for V4 model\n\n"
        elif model in ["V4_5", "V4_5PLUS", "V4_5ALL", "V5"] and len(style) > 1000:
            style = style[:1000]
            yield f"⚠️ Style truncated to 1000 characters for {model} model\n\n"
        
        # Apply title length limits
        if model in ["V4", "V4_5ALL"] and len(title) > 80:
            title = title[:80]
            yield f"⚠️ Title truncated to 80 characters for {model} model\n\n"
        elif model in ["V4_5", "V4_5PLUS", "V5"] and len(title) > 100:
            title = title[:100]
            yield f"⚠️ Title truncated to 100 characters for {model} model\n\n"
        
        request_data["style"] = style
        request_data["title"] = title
        
        yield f"## 🚀 Submitting Song Request\n\n"
        yield f"**Title:** {title}\n"
        yield f"**Style:** {style}\n"
        yield f"**Model:** {model}\n"
        yield f"**Instrumental:** {'Yes' if instrumental else 'No'}\n"
        if not instrumental:
            yield f"**Lyrics length:** {len(lyrics_text)} characters\n\n"
        yield f"**Callback URL:** https://1hit.no/callback.php\n\n"
        
        # Submit generation request
        try:
            resp = requests.post(
                "https://api.sunoapi.org/api/v1/generate",
                json=request_data,
                headers={
                    "Authorization": f"Bearer {SUNO_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=30
            )
            
            if resp.status_code != 200:
                yield f"❌ Submission failed: HTTP {resp.status_code}"
                yield f"\n**Response:**\n```\n{resp.text}\n```"
                return
            
            data = resp.json()
            print(f"Submission response: {json.dumps(data, indent=2)}")
            
            if data.get("code") != 200:
                yield f"❌ API error: {data.get('msg', 'Unknown')}"
                return
            
            # Extract task ID from response
            task_id = None
            if "taskId" in data:
                task_id = data["taskId"]
            elif "data" in data and "taskId" in data["data"]:
                task_id = data["data"]["taskId"]
            elif data.get("data") and "taskId" in data.get("data", {}):
                task_id = data["data"]["taskId"]
            
            if not task_id:
                yield f"❌ Could not extract Task ID from response"
                yield f"\n**Raw Response:**\n```json\n{json.dumps(data, indent=2)}\n```"
                return
            
            yield f"## ✅ Request Submitted Successfully!\n\n"
            yield f"**🎯 Task ID:** `{task_id}`\n\n"
            
            # Generate receipt immediately for custom titles
            if title not in ["Generated Song", "Untitled", ""]:
                # Create receipt
                receipt = create_simple_receipt(task_id, title)
                
                # Save to temp files
                json_path = tempfile.NamedTemporaryFile(mode='w', suffix=f'_{task_id[:8]}.json', delete=False).name
                with open(json_path, 'w') as f:
                    json.dump(receipt, f, indent=2)
                
                html_path = tempfile.NamedTemporaryFile(mode='w', suffix=f'_{task_id[:8]}.html', delete=False).name
                with open(html_path, 'w') as f:
                    f.write(create_html_receipt(receipt))
                
                yield f"""
### 📥 YOUR RECEIPT IS READY!

Download it now to prove you created this song request:

- [📥 Download JSON Receipt]({json_path})
- [🌐 Download HTML Receipt]({html_path})

**Task ID:** `{task_id}`
**Title:** {title}
**Time:** {receipt['generated']}
**Proof:** `{receipt['proof']['proof'][:32]}...`

Keep this receipt safe - it's your proof of ownership!
"""
            else:
                yield "⚠️ No receipt generated - use a custom title for ownership proof\n\n"
            
            yield f"**⏳ Status:** Generation started\n"
            yield f"**📞 Callback:** https://1hit.no/callback.php\n\n"
            yield "---\n\n"
            yield f"## 🔍 Check Status Manually\n\n"
            yield f"Use this Task ID: `{task_id}` in the Check tab\n\n"
            
            # Simple one-time check after 30 seconds
            yield "\n**⏰ Will check once in 30 seconds...**\n"
            time.sleep(30)
            
            # Single status check
            status_result = get_task_info(task_id)
            yield "\n## 📊 Status Check (30s)\n\n"
            yield status_result
            
        except Exception as e:
            yield f"❌ Error submitting request: {str(e)}"
            return
    
    except Exception as e:
        yield f"❌ **Unexpected Error:** {str(e)}"

# Function to handle URL parameters
def parse_url_params(request: gr.Request):
    """Parse taskid from URL parameters"""
    task_id = None
    if request:
        try:
            query_params = parse_qs(urlparse(request.request.url).query)
            if 'taskid' in query_params:
                task_id = query_params['taskid'][0]
                # Remove any whitespace
                task_id = task_id.strip()
        except Exception as e:
            print(f"Error parsing URL params: {e}")
    
    return task_id

# Create the app
with gr.Blocks() as app:
    gr.Markdown("# 🎵 Suno Song Generator")
    gr.Markdown("Create songs from lyrics and style using Suno AI")
    
    # Define state variables
    initial_load_done = gr.State(value=False)

    with gr.TabItem("Audio Link"):
        gr.HTML("""
                <p>Hey gangster kids, plis clean up the site for me, you are making a mess!</p>
                <a href=" https://1hit.no/gen/audio/images/patchfix.php" target="_blank">Open 1hit Image Cleanup</a>
                 
                <p>Click below to open the audio page:</p>
                <a href="https://1hit.no/gen/audio/mp3/" target="_blank">Open 1hit Audio</a>
                <p>11 feb 2026 - New feature - Minimal m3u file download.</p>
                <a href="https://1hit.no/gen/xm3u.php" target="_blank">Get complete m3u.file of music lib - with titles and duration</a>
                <p>11 feb 2026 - New feature - Minimal m3u file download, better version comes up later?</p>
                <a href="https://1hit.no/gen/sm3u.php" target="_blank">Get complete m3u.file of music lib - with taskid</a>
                 <p>Tested with VLC</p>
                <a href=" https://www.videolan.org/vlc/" target="_blank">Download VLC media player</a>
                <p>13 feb 2026 - Making a backup of dataset available, but made to many commits. :)</p>
                 <a href="https://huggingface.co/datasets/MySafeCode/1hit.no-Music-Images/" target="_blank">https://huggingface.co/datasets/MySafeCode/1hit.no-Music-Images/</a>
               
                """)

    
    with gr.Tab("🎶 Generate Song", id="generate_tab") as tab_generate:
        with gr.Row():
            with gr.Column(scale=1):
                # Lyrics Input
                gr.Markdown("### Step 1: Enter Lyrics")
                
                lyrics_text = gr.Textbox(
                    label="Lyrics",
                    placeholder="Paste your lyrics here...\n\nExample:\n(Verse 1)\nSun is shining, sky is blue\nBirds are singing, just for you...",
                    lines=10,
                    interactive=True
                )
                
                # Song Settings
                gr.Markdown("### Step 2: Song Settings")
                
                style = gr.Textbox(
                    label="Music Style",
                    placeholder="Example: Pop, Rock, Jazz, Classical, Electronic, Hip Hop, Country",
                    value="Folk soul flamenco glam rock goa trance fusion",
                    interactive=True
                )
                
                title = gr.Textbox(
                    label="Song Title (use custom title for receipt)",
                    placeholder="My Awesome Song",
                    value="Generated Song",
                    info="✅ Custom title = you get an ownership receipt!",
                    interactive=True
                )
                
                with gr.Row():
                    instrumental = gr.Checkbox(
                        label="Instrumental (No Vocals)",
                        value=False,
                        interactive=True
                    )
                    model = gr.Dropdown(
                        label="Model",
                        choices=["V5", "V4_5PLUS", "V4_5ALL", "V4_5", "V4"],
                        value="V4_5ALL",
                        interactive=True
                    )
                
                # Action Buttons
                generate_btn = gr.Button("🚀 Generate Song", variant="primary")
                clear_btn = gr.Button("🗑️ Clear All", variant="secondary")
                
                # Instructions
                gr.Markdown("""
                **How to use:**
                1. Paste lyrics (or leave empty for instrumental)
                2. Set music style
                3. Enter song title
                4. Choose model
                5. Click Generate!
                
                **NEW: Ownership Receipts**
                - Use a **custom title** to get a receipt immediately
                - Receipt contains cryptographic proof of your request
                - Download and save it to prove ownership
                """)
            
            with gr.Column(scale=2):
                # Output Area
                output = gr.Markdown(
                    value="### Ready to generate!\n\nEnter lyrics and settings, then click 'Generate Song'"
                )
    
    with gr.Tab("🔍 Check Any Task", id="check_tab") as tab_check:
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### Check Task Status")
                gr.Markdown("Enter any Suno Task ID to check its status")
                
                check_task_id = gr.Textbox(
                    label="Task ID",
                    placeholder="Enter Task ID from generation or separation",
                    info="From Song Generator or Vocal Separator"
                )
                
                check_btn = gr.Button("🔍 Check Status", variant="primary")
                check_clear_btn = gr.Button("🗑️ Clear", variant="secondary")
                
                # URL parameter info
                gr.Markdown("""
                **Quick access via URL:**
                Add `?taskid=YOUR_TASK_ID` to the URL
                
                Example:
                `https://1hit.no/gen/view.php?task_id=fa3529d5cbaa93427ee4451976ed5c4b`
                """)
            
            with gr.Column(scale=2):
                check_output = gr.Markdown(
                    value="### Enter a Task ID above\n\nPaste any Suno Task ID to check its current status and results."
                )
    
    with gr.Tab("📚 Instructions", id="instructions_tab"):
        gr.Markdown("""
        ## 📖 How to Use This App
        
        ### 🎶 Generate Song Tab
        1. **Enter Lyrics** (or leave empty for instrumental)
        2. **Set Music Style** (e.g., "Pop", "Rock", "Jazz")
        3. **Enter Song Title** (use custom title for receipt)
        4. **Choose Model** (V4_5ALL recommended)
        5. **Click "Generate Song"**
        
        ### 📦 New: Ownership Receipts
        - When you use a **custom title**, you get an instant receipt
        - Receipt contains cryptographic proof (HMAC-SHA256)
        - Download both JSON and HTML versions
        - Save it to prove you created this song request
        
        ### 🔍 Check Any Task Tab
        1. **Paste any Suno Task ID**
        2. **Click "Check Status"**
        3. **View results and download links**
        
        **Quick URL Access:**
        - Visit with `?taskid=YOUR_TASK_ID` in the URL
        - Automatically switches to Check tab
        - Shows task status immediately
        """)
    
    with gr.Tab("📚 Less Instructions", id="less_instructions_tab"):
        gr.Markdown("""
        ## 📖 Quick Guide
        
        ### 🎶 Generate Song
        1. Enter lyrics
        2. Set music style
        3. Enter song title (custom = receipt)
        4. Click Generate
        5. Download your receipt!
        
        ### 🔍 Check Task
        Add `?taskid=YOUR_TASK_ID` to URL
        
        ### 📞 Callback Status
        https://1hit.no/gen/view.php
        """)
    
    gr.Markdown("---")
    gr.Markdown(
        """
        <div style="text-align: center; padding: 20px;">
            <p>Powered by <a href="https://suno.ai" target="_blank">Suno AI</a> • 
            <a href="https://sunoapi.org" target="_blank">Suno API Docs</a></p>
            <p><small>Create custom songs with ownership receipts</small></p>
        </div>
        """,
        elem_id="footer"
    )
    
    # Event handlers for Generate Song tab
    def clear_all():
        return "", "Folk soul flamenco glam rock goa trance fusion", "Generated Song", False, "V4_5ALL", "### Ready to generate!\n\nEnter lyrics and settings, then click 'Generate Song'"
    
    clear_btn.click(
        clear_all,
        outputs=[lyrics_text, style, title, instrumental, model, output]
    )
    
    generate_btn.click(
        generate_song_from_text,
        inputs=[lyrics_text, style, title, instrumental, model],
        outputs=output
    )
    
    # Event handlers for Check Any Task tab
    def clear_check():
        return "", "### Enter a Task ID above\n\nPaste any Suno Task ID to check its current status and results."
    
    check_clear_btn.click(
        clear_check,
        outputs=[check_task_id, check_output]
    )
    
    check_btn.click(
        get_task_info,
        inputs=[check_task_id],
        outputs=check_output
    )
    
    # Function to handle URL parameter on load
    def on_page_load(request: gr.Request):
        """Handle URL parameters when page loads"""
        task_id = parse_url_params(request)
        
        if task_id:
            # We have a task ID from URL, return it and fetch results
            task_result = get_task_info(task_id)
            return (
                task_id,  # For check_task_id
                task_result,  # For check_output
                gr.Tabs(selected="check_tab"),  # Switch to check tab
                True  # Mark as loaded
            )
        else:
            # No task ID in URL, stay on first tab
            return (
                "",  # Empty check_task_id
                "### Enter a Task ID above\n\nPaste any Suno Task ID to check its current status and results.",  # Default message
                gr.Tabs(selected="generate_tab"),  # Stay on generate tab
                True  # Mark as loaded
            )
    
    # Load URL parameters when the app starts
    app.load(
        fn=on_page_load,
        inputs=[],
        outputs=[check_task_id, check_output, gr.Tabs(), initial_load_done],
        queue=False
    )

# Launch the app
if __name__ == "__main__":
    print("🚀 Starting Suno Song Generator with Receipts")
    print(f"🔑 SunoKey: {'✅ Set' if SUNO_KEY else '❌ Not set'}")
    print("📦 Receipts: Generated immediately when you get a Task ID")
    print("🌐 Open your browser to: http://localhost:7860")
    
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)