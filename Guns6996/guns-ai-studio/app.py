
import gradio as gr
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

# Modular UI imports
from ui.image_tab import build_image_tab
from ui.img2img_tab import build_img2img_tab
from ui.lora_tab import build_lora_tab
from ui.identity_lock import build_identity_lock_tab
from ui.video_tab import build_video_tab
from ui.face_video_tab import build_face_video_tab
from ui.face_swap_video import build_face_swap_video_tab

# Logic imports
from config import *
from image_utils import *
from face_engine import *
from providers import *
from pipelines import *
from engines.video._engine import generate_video_with_provider, toggle_model_id

import replicate
import requests

# Define a default empty string for CSS if it's not defined in config
custom_css = "" 
try:
    custom_css = css # Try to use the one from config
except NameError:
    pass

with gr.Blocks(
    title="Guns AI Studio", 
    css=custom_css,
) as demo:
    gr.Markdown("# ✨ Guns AI Studio ✨")

    with gr.Tabs():
        with gr.Tab("🖼️ Image Generation"): 
            build_image_tab()
            
        with gr.Tab("🎨 Image Editing"): 
            build_img2img_tab()
            
        with gr.Tab("🧬 LoRA"): 
            build_lora_tab()
            
        with gr.Tab("🔒 Identity Lock"): 
            build_identity_lock_tab()
            
        with gr.Tab("🎭 Face Tools"): 
            build_face_video_tab()
            build_face_swap_video_tab()
            
        with gr.Tab("🎬 Video"): 
            build_video_tab()

if __name__ == "__main__":
    # REMOVED ssr_mode=False to allow Tabs to render correctly
    demo.launch(
        server_name="0.0.0.0", 
        server_port=7860
    )
