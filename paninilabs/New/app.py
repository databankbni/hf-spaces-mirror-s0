import os
import sqlite3
import uuid
import shutil
import wave
import gradio as gr

# Database and Audio directory locations
DB_FILE = "kannada_speech_data.db"
AUDIO_DIR = "recorded_audio"

def init_db():
    """Initializes the SQLite database and directory structure."""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audio_samples (
            id TEXT PRIMARY KEY,
            audio_path TEXT,
            prompt_text TEXT,
            speaker_id TEXT,
            gender TEXT,
            age INTEGER,
            district TEXT,
            dialect TEXT,
            duration_seconds REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# Initialize on startup
init_db()

# Pre-defined Kannada speech collection prompts
KANNADA_PROMPTS = [
    "ಒಂದು, ಎರಡು, ಮೂರು, ನಾಲ್ಕು, ಐದು, ಆರು, ಏಳು, ಎಂಟು, ಒಂಬತ್ತು, ಹತ್ತು.",
    "ದಯವಿಟ್ಟು ನಿಲ್ಲಿಸಿ, ಇಲ್ಲಿಗೆ ಬನ್ನಿ, ಅಲ್ಲಿ ಹೋಗಬೇಡಿ, ನಮಗೆ ಸಹಾಯ ಮಾಡಿ.",
    "ಎಲ್ಲರಿಗೂ ನಮಸ್ಕಾರ, ಇಂದಿನ ದಿನ ನಿಮಗೆ ಶುಭವಾಗಿರಲಿ.",
    "ನಿಮ್ಮ ಹೆಸರು ಏನು ಮತ್ತು ನೀವು ಎಲ್ಲಿಂದ ಬಂದಿದ್ದೀರಾ?",
    "ಬೆಂಗಳೂರಿನ ಹವಾಮಾನ ಇಂದು ತುಂಬಾ ತಂಪಾಗಿದೆ ಮತ್ತು ಮೋಡ ಕವಿದಿದೆ.",
    "ರೈತರು ನಮ್ಮ ದೇಶದ ಜೀವನಾಡಿ, ಅವರ ಶ್ರಮ ನಮಗೆಲ್ಲರಿಗೂ ಅನ್ನ ನೀಡುತ್ತದೆ.",
    "ಕನ್ನಡ ಸಾಹಿತ್ಯಕ್ಕೆ ಎಂಟು ಜ್ಞಾನಪೀಠ ಪ್ರಶಸ್ತಿಗಳು ಲಭಿಸಿವೆ ಎಂಬುದು ಹೆಮ್ಮೆಯ ವಿಷಯ.",
    "ಮಾಹಿತಿ ತಂತ್ರಜ್ಞಾನ ಕ್ಷೇತ್ರದ ಬೆಳವಣಿಗೆಯಿಂದ ಬೆಂಗಳೂರು ಜಾಗತಿಕ ಮಟ್ಟದಲ್ಲಿ ಗುರುತಿಸಿಕೊಂಡಿದೆ.",
    "ಕಡಲೆಕಾಯಿ ಕೆಂಪು ಕಡಲೆಕಾಯಿ, ಕಹಿಯಾದ ಕಹಿ ಕಡಲೆಕಾಯಿ ಅಲ್ಲ."
]

def save_sample(audio, prompt, speaker_id, gender, age, district, dialect):
    """Saves the recorded audio sample to disk and autosaves metadata in SQLite."""
    if audio is None:
        return "⚠️ Error: No audio recorded. Please record or upload an audio sample.", get_dataset_stats(), prepare_download_packages()
    
    # Determine the next incrementing sample ID starting from sample_01
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM audio_samples")
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        max_idx = 0
        for id_str in ids:
            if id_str.startswith("sample_"):
                try:
                    num = int(id_str.split("_")[1])
                    if num > max_idx:
                        max_idx = num
                except Exception:
                    pass
        next_idx = max_idx + 1
        sample_id = f"sample_{next_idx:02d}"
    except Exception:
        sample_id = f"sample_{str(uuid.uuid4())[:8]}"
    
    # Resolve temp audio file path from Gradio
    if isinstance(audio, str):
        temp_filepath = audio
    else:
        temp_filepath = audio.name if hasattr(audio, 'name') else str(audio)
        
    if not temp_filepath or not os.path.exists(temp_filepath):
        return "⚠️ Error: Temp audio file not found. Try recording again.", get_dataset_stats(), prepare_download_packages()
    
    # Save audio file under recorded_audio directory
    extension = os.path.splitext(temp_filepath)[1] or ".wav"
    dest_filename = f"{sample_id}{extension}"
    dest_path = os.path.join(AUDIO_DIR, dest_filename)
    
    shutil.copy(temp_filepath, dest_path)
    
    # Attempt to calculate WAV audio duration
    duration = -1.0
    try:
        with wave.open(dest_path, 'r') as f:
            frames = f.getnframes()
            rate = f.getframerate()
            duration = round(frames / float(rate), 2)
    except Exception:
        # Fallback for non-standard WAV/WebM container headers
        duration = 0.0
        
    # Persist metadata into local SQLite Database
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audio_samples 
            (id, audio_path, prompt_text, speaker_id, gender, age, district, dialect, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (sample_id, dest_path, prompt, speaker_id, gender, int(age) if age else None, district, dialect, duration))
        conn.commit()
        conn.close()
        
        return f"🎉 Success! Recording saved successfully.\n Saved As: {dest_path}\n Database Row: {sample_id} saved.", get_dataset_stats(), prepare_download_packages()
    except Exception as e:
        return f"❌ Database Error: {str(e)}", get_dataset_stats(), prepare_download_packages()

def get_dataset_stats():
    """Retrieves dynamic, real-time statistics of the SQLite database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM audio_samples")
        total_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT speaker_id) FROM audio_samples")
        unique_speakers = cursor.fetchone()[0]
        
        cursor.execute("SELECT gender, COUNT(*) FROM audio_samples GROUP BY gender")
        genders = [f"{row[0]} ({row[1]})" for row in cursor.fetchall()]
        gender_str = ", ".join(genders) if genders else "None"
        
        cursor.execute("SELECT SUM(duration_seconds) FROM audio_samples WHERE duration_seconds > 0")
        total_duration = cursor.fetchone()[0]
        total_duration = round(total_duration, 2) if total_duration else 0.0
        
        conn.close()
        return (
            f" Dataset Statistics:\n"
            f"• Total Saved Samples: {total_count}\n"
            f"• Unique Contributors: {unique_speakers}\n"
            f"• Cumulative Duration: {total_duration} seconds\n"
            f"• Gender Balance: {gender_str}"
        )
    except Exception as e:
        return f"⚠️ Error fetching stats: {str(e)}"

def prepare_download_packages():
    """Bundles SQLite DB and zips the audio folder on demand for researchers."""
    files_to_download = []
    
    # 1. Include the SQLite database
    if os.path.exists(DB_FILE):
        files_to_download.append(DB_FILE)
        
    # 2. Archive audio files into a ZIP
    zip_basename = "kannada_speech_dataset"
    zip_fullname = f"{zip_basename}.zip"
    
    if os.path.exists(AUDIO_DIR) and len(os.listdir(AUDIO_DIR)) > 0:
        # Create ZIP archive of the AUDIO_DIR
        shutil.make_archive(zip_basename, 'zip', AUDIO_DIR)
        files_to_download.append(zip_fullname)
        
    return files_to_download

# Apply a modern clean style theme
custom_theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="emerald",
    neutral_hue="slate"
)

# Render Gradio blocks
with gr.Blocks(theme=custom_theme, title="Kannada Speech Research Collector") as demo:
    gr.Markdown("""
    #  Kannada Speech Recognition Research Dataset Collector
    
    Help us build high-quality, open-source resources for Kannada Automatic Speech Recognition (ASR).
    This interface collects audio recordings along with critical linguistic demographics, automatically saving them in a structured local **SQLite database** and file repository.
    """)
    
    with gr.Tab(" Recording Studio"):
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("### Step 1: Select and Read the Prompt")
                prompt_dropdown = gr.Dropdown(
                    choices=KANNADA_PROMPTS,
                    value=KANNADA_PROMPTS[0],
                    label=" Select Kannada Prompt text",
                    interactive=True
                )
                
                # Large, readable text display in Kannada
                prompt_html = gr.HTML(
                    value=f"<div style='font-size: 26px; font-weight: bold; padding: 25px; line-height: 1.5; background-color: #f8fafc; border-radius: 12px; border: 2px solid #e2e8f0; text-align: center; color: #1e293b; margin: 15px 0;'>{KANNADA_PROMPTS[0]}</div>"
                )
                
                def update_display(selected_prompt):
                    return f"<div style='font-size: 26px; font-weight: bold; padding: 25px; line-height: 1.5; background-color: #f8fafc; border-radius: 12px; border: 2px solid #e2e8f0; text-align: center; color: #1e293b; margin: 15px 0;'>{selected_prompt}</div>"
                
                prompt_dropdown.change(fn=update_display, inputs=prompt_dropdown, outputs=prompt_html)
                
                gr.Markdown("### Step 2: Record Your Speech")
                audio_input = gr.Audio(
                    sources=["microphone"],
                    type="filepath",
                    label=" Audio Microphone Input"
                )
                
            with gr.Column(scale=1):
                gr.Markdown("###  Speaker Metadata (Demographics)")
                speaker_id = gr.Textbox(
                    label="Speaker ID / Nickname", 
                    value="anonymous_speaker", 
                    placeholder="e.g., speaker_kannada_01"
                )
                gender = gr.Radio(
                    choices=["Male", "Female","Prefer not to say"], 
                    label="Gender", 
                    value="Male"
                )
                age = gr.Number(
                    label="Age", 
                    value=25, 
                    precision=0
                )
                district = gr.Dropdown(
                    choices=[
                        "Bengaluru", "Mysuru", "Hubballi-Dharwad", "Mangaluru", 
                        "Belagavi", "Kalaburagi", "Shivamogga", "Tumakuru", 
                        "Davangere", "Ballari", "Udupi", "Chikkamagaluru", "Other"
                    ],
                    label="District / Region (for accent analysis)",
                    value="Bengaluru"
                )
                dialect = gr.Dropdown(
                    choices=[
                        "Standard Kannada", "Mysuru Kannada", "Mangaluru / Coastal Kannada", 
                        "Hubli-Dharwad / North Karnataka", "Kundapura Kannada", 
                        "Soliga / Tribal Dialects", "Arebhashe", "Other"
                    ],
                    label="Self-Identified Dialect",
                    value="Standard Kannada"
                )
                
        submit_btn = gr.Button(" Submit & Save Sample", variant="primary", size="lg")
        status_box = gr.Textbox(label="Submission Status", interactive=False)
        
    with gr.Tab(" Dataset Explorer & Downloader"):
        gr.Markdown("###  Download and Export Speech Dataset")
        
        with gr.Row():
            stats_output = gr.Textbox(
                value=get_dataset_stats(), 
                label="Active Dataset Metadata Stats", 
                interactive=False,
                lines=5
            )
        
        refresh_btn = gr.Button(" Refresh Database Statistics")
        refresh_btn.click(fn=get_dataset_stats, inputs=[], outputs=stats_output)
        
        gr.Markdown("""
        ### Download Files
        Generate and package the complete SQLite database file (`kannada_speech_data.db`) and all recorded voice sample audio files (`.wav` or `.webm`) packed into a single zip file.
        """)
        
        package_btn = gr.Button(" Prepare Data Package", variant="secondary")
        file_download_widget = gr.Files(label="Downloadable Packages")
        
        package_btn.click(fn=prepare_download_packages, inputs=[], outputs=file_download_widget)
        
        # Link submission to automatically update status, dataset stats, and download files
        submit_btn.click(
            fn=save_sample,
            inputs=[audio_input, prompt_dropdown, speaker_id, gender, age, district, dialect],
            outputs=[status_box, stats_output, file_download_widget]
        )

# Run app
if __name__ == "__main__":
    demo.launch()
