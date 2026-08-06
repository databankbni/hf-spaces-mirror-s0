import gradio as gr
import requests
import os
import time
import json
from urllib.parse import urlparse, parse_qs

# Suno API key
SUNO_KEY = os.environ.get("SunoKey", "")
if not SUNO_KEY:
    print("⚠️ SunoKey not set!")

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
            
            if status == "SUCCESS":
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
            elif model in ["V4_5", "V4_5PLUS", "V4_5ALL", "V5", "V5_5"] and len(lyrics_text) > 5000:
                lyrics_text = lyrics_text[:5000]
                yield f"⚠️ Lyrics truncated to 5000 characters for {model} model\n\n"
            
            request_data["prompt"] = lyrics_text
        else:
            request_data["prompt"] = ""
        
        # Apply style length limits
        if model == "V4" and len(style) > 200:
            style = style[:200]
            yield f"⚠️ Style truncated to 200 characters for V4 model\n\n"
        elif model in ["V4_5", "V4_5PLUS", "V4_5ALL", "V5", "V5_5"] and len(style) > 1000:
            style = style[:1000]
            yield f"⚠️ Style truncated to 1000 characters for {model} model\n\n"
        
        # Apply title length limits
        if model in ["V4", "V4_5ALL"] and len(title) > 80:
            title = title[:80]
            yield f"⚠️ Title truncated to 80 characters for {model} model\n\n"
        elif model in ["V4_5", "V4_5PLUS", "V5", "V5_5"] and len(title) > 100:
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
            yield f"**⏳ Status:** Generation started\n"
            yield f"**📞 Callback:** https://1hit.no/callback.php\n\n"
            yield "**What happens now:**\n"
            yield "1. Suno AI generates your song (1-3 minutes)\n"
            yield "2. You'll get a callback notification\n"
            yield "3. Use the Task ID above to check status manually\n\n"
            yield "---\n\n"
            yield f"## 🔍 Check Status Manually\n\n"
            yield f"Use this Task ID: `{task_id}`\n\n"
            yield "**To check status:**\n"
            yield "1. Copy the Task ID above\n"
            yield "2. Go to 'Check Any Task' tab\n"
            yield "3. Paste and click 'Check Status'\n"
            yield "4. Or wait for callback notification\n\n"
            yield "**Generation time:**\n"
            yield "- 30-60 seconds for stream URL\n"
            yield "- 2-3 minutes for download URL\n"
            
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
    
    # We'll use a hidden component to track initial load
    initial_load_done = gr.State(value=False)

    with gr.TabItem("Audio Link"):
        gr.HTML("""
                  <p>29 may 2026 - Thanks. This project ends on 1st June, or takes a summer pause. Maybe back in august? In new form? :)</p>
             

        
                    <p>03 may 2026 - New m3u of covers. :)</p>
                 <a href="https://www.1hit.no/cover/backup.php?generate_m3u=1" target="_blank">1hit.no - New m3u of covers with less errors.</a>
                 
                  
                <p>03 apr 2026 - Message about some problems with the Covers Space. :)</p>
                 <a href=" https://www.1hit.no/cover/mp3s/5794911bbd260281327424ee3f9c9d90_2.mp3" target="_blank">1hit.no Message about some problems with Covers.</a>
                 
                 <p>29 mar 2026 Suno AI launched Version 5.5 (internal model name: chirp-fenix) on March 26, 2026</p>
        
                 <p>27 mar 2026 - Made an example on how to include lib in games etc... :)</p>
                 <a href="https://1hit.no/demo/hola.html" target="_blank">1hit.no Suno - playlist demo.</a>
                 <p>(: -------------- :)</p>
                 <a href="https://1hit.no/demo/roll5.html" target="_blank">1hit.no Suno - playlist demo.</a>
                 
                 
               
                <p>12 mar 2026 - I tried putting up 45 minutes of music on youtube via twitch. :)</p>
                 <a href=" https://1hit.no/youtube/?v=BLjpwZwfKWY" target="_blank">1hit.no Suno - music on youtube created here.</a>
       
                <p>20 feb 2026 - WOW! We are features on two mockup radio stations. :)</p>
                 <p>(: -------------- :)</p>
                <a href="https://1hit.no/1radio.m3u" target="_blank">1hit radio - Chat GPT is host</a>
                <a href="https://1hit.no/onlineradio.m3u" target="_blank">1hit radio - Deepseek is host</a>
                <p>(: -------------- :)</p>
        
                <p>Hey gangster kids, plis clean up the site for me, you are making a mess!</p>
                <a href=" https://1hit.no/gen/audio3/images/patchfix.php" target="_blank">Open 1hit Image Cleanup</a>

                <p>Click below to open the last new audio page:</p>
                <a href="https://1hit.no/gen/audio3/mp3/" target="_blank">Open 1hit Audio</a>
                <p>Click below to open the somwhat new audio page:</p>
                <a href="https://1hit.no/gen/audio2/mp3/" target="_blank">Open 1hit Audio</a>
                <p>Click below to open the old audio page:</p>
                <a href="https://1hit.no/gen/audio/mp3/" target="_blank">Open big old 1hit Audio</a>

                <p>01 aug 2026 - New feature - Minimal m3u file download.</p>
                <a href="https://1hit.no/gen/audio3/xm3u.php" target="_blank">Get complete m3u.file of music lib - with titles and duration</a>
                
                <p>16 apr 2026 - New feature - Minimal m3u file download.</p>
                <a href="https://1hit.no/gen/audio2/xm3u.php" target="_blank">Get complete m3u.file of music lib - with titles and duration</a>
                
                 <p>Tested with VLC</p>
                 <p>11 feb 2026 - New feature - Minimal m3u file download.</p>
                <a href="https://1hit.no/gen/xm3u.php" target="_blank">Get complete m3u.file of music lib - with titles and duration</a>
               
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
                    label="Song Title",
                    placeholder="My Awesome Song",
                    value="",
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
                        choices=["V5_5","V5", "V4_5PLUS", "V4_5ALL", "V4_5", "V4"],
                        value="V5_5",
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
                
                **Tips:**
                - V4_5ALL: Best overall quality
                - V5: Latest model
                - Instrumental: No vocals, just music
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
        3. **Enter Song Title**
        4. **Choose Model** (V4_5ALL recommended)
        5. **Click "Generate Song"**
        
        ### 🔍 Check Any Task Tab
        1. **Paste any Suno Task ID**
        2. **Click "Check Status"**
        3. **View results and download links**
        
        **Quick URL Access:**
        - Visit with `?taskid=YOUR_TASK_ID` in the URL
        - Automatically switches to Check tab
        - Shows task status immediately
        
        Example:
        ```
        https://1hit.no/gen/view.php?task_id=fa3529d5cbaa93427ee4451976ed5c4b
        ```
        
        ### ⏱️ What to Expect
        
        **After generating:**
        - You'll get a **Task ID** immediately
        - Generation takes **1-3 minutes**
        - **Callback** sent to https://1hit.no/gen/cb.php
        - Use Task ID to **check status manually**
        
        **Task IDs come from:**
        - Song Generator (this app)
        - Vocal Separator (other app)
        - Any Suno API request
        
        ### 🎵 Getting Your Songs
        
        1. **Stream URL:** Ready in 30-60 seconds
        2. **Download URL:** Ready in 2-3 minutes
        3. **Both appear in status check**
        4. **Audio player** included for streaming
        
        ### 🔧 Troubleshooting
        
        **Task not found?**
        - Wait a few minutes
        - Check callback logs at https://1hit.no/gen/view.php
        - Ensure Task ID is correct
        
        **No audio links?**
        - Wait 2-3 minutes
        - Check status again
        - Generation may have failed
        """)
    
    with gr.Tab("📚 Less Instructions", id="less_instructions_tab"):
        gr.Markdown("""
        ## 📖 How to Use This App
        
        ### 🎶 Generate Song Tab
        1. **Enter Lyrics** (or leave empty for instrumental)
        2. **Set Music Style** (e.g., "Pop", "Rock", "Jazz")
        3. **Enter Song Title**
        4. **Choose Model**
        5. **Click "Generate Song"**
        
        ### 🔍 Check Any Task via URL
        Add `?taskid=YOUR_TASK_ID` to the URL
        
        Example:
        ```
         https://1hit.no/gen/view.php?task_id=fa3529d5cbaa93427ee4451976ed5c4b
        ```
        
        ### 📞 Callback Status
        https://1hit.no/gen/view.php
        
        **No audio links?**
        - Wait 2-3 minutes
        - Check status again
        - Generation may have failed
        """)
    
    gr.Markdown("---")
    gr.Markdown(
        """
        <div style="text-align: center; padding: 20px;">
            <p>Powered by <a href="https://suno.ai" target="_blank">Suno AI</a> • 
            <a href="https://sunoapi.org" target="_blank">Suno API Docs</a></p>
            <p><small>Create custom songs by providing lyrics and music style</small></p>
        </div>
        """,
        elem_id="footer"
    )
    
    # Event handlers for Generate Song tab
    def clear_all():
        return "", "Pop", "Generated Song", False, "V4_5ALL", "### Ready to generate!\n\nEnter lyrics and settings, then click 'Generate Song'"
    
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
    print("🚀 Starting Suno Song Generator")
    print(f"🔑 SunoKey: {'✅ Set' if SUNO_KEY else '❌ Not set'}")
    print("🌐 Open your browser to: http://localhost:7860")
    print("🔗 Use URL parameter: http://localhost:7860?taskid=YOUR_TASK_ID")
    
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)