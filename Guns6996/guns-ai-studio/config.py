import os
from pathlib import Path
# =========================================================
# BACKEND DEFAULTS
# =========================================================

DEFAULT_STEPS = 28
DEFAULT_SEED = 0

DEFAULT_CFG = 5.5
DEFAULT_STRENGTH = 0.35
DEFAULT_FACE_BLEND = 0.95

DEFAULT_LORA_SCALE = 0.80
DEFAULT_REFERENCE_LORA_SCALE = 0.35
DEFAULT_AI_LORA_SCALE = 0.25

DEFAULT_IP_STEPS = 30
DEFAULT_IP_STRENGTH = 0.70

DEFAULT_VIDEO_FPS = 24
DEFAULT_VIDEO_FRAMES = 121
DEFAULT_DECODE_TIMESTEP = 0.05
DEFAULT_DECODE_NOISE_SCALE = 0.015
# API Keys
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
Fal_KEY = os.getenv("Fal_Key")
CIVITAI_KEY = os.getenv("Civitai_Key")
RUNPOD_BASE = "https://api.runpod.ai/v2"

# Ensure outputs directory exists
Path("outputs").mkdir(exist_ok=True)

# Model Defaults
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024
DEFAULT_IMAGE_MODEL = "black-forest-labs/FLUX.1-dev"
DEFAULT_LORA_MODEL = "black-forest-labs/flux-dev-lora"
LORA_URL = "https://huggingface.co/spaces/Guns6996/guns-lora-app/resolve/main/flux-lora.safetensors"

DEFAULT_NEGATIVE = (
    "blurry, low quality, cartoon, anime, CGI, 3d render, digital painting, "
    "smooth plastic skin, perfect porcelain skin, doll skin, wax skin, plastic skin, overprocessed face, beauty filter, glamour makeup, "
    "thick eyebrows, blocky eyebrows, painted eyebrows, sharp eyebrows, black lipstick, "
    "dark lipstick, heavy lipstick, oversized lips, oversized eyes, distorted face, "
    "duplicate face, bad anatomy, extra fingers, malformed hands, octane render, unreal engine, "
    "subsurface scattering, ambient occlusion, perfectly symmetrical, airbrushed"
)

css = """
body, .gradio-container {
    max-width: 100% !important;
    overflow-x: hidden !important;
}
.tab-nav {
    justify-content: center !important;
    overflow-x: auto !important;
    white-space: nowrap !important;
}
.tab-nav button {
    min-width: fit-content !important;
}
button {
    background: linear-gradient(135deg, #8b3dff, #d946ef) !important;
    color: white !important;
    border-radius: 14px !important;
    font-weight: bold !important;
}
"""
lora_names = []
custom_css = """
body {
    background-color: #000000 !important;
}
.gradio-container {
    background-color: #000000 !important;
}
footer {visibility: hidden} 
.gr-button-primary {
    background: linear-gradient(45deg, #6b21a8, #a855f7) !important; 
    border: none !important;
    color: white !important;
    font-weight: bold !important;
}
.gr-button-primary:hover {
    box-shadow: 0px 0px 15px #a855f7 !important;
}
"""
