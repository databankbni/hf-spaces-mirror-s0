import os
import io
import base64
from PIL import Image
import numpy as np
import gradio as gr
from huggingface_hub import InferenceClient
from fastapi import FastAPI, Body, Request
from fastapi.responses import JSONResponse

# =========================================================
# Hugging Face Inference Client (existing text-to-image / upscale)
# =========================================================
token = os.environ.get("HF_TOKEN", None)
client = InferenceClient(token=token)


def generate_image_fn(prompt):
    """
    Generates a high-quality image from a text prompt.
    Uses Stability AI's Stable Diffusion XL model, which is free and public.
    """
    if not prompt or not prompt.strip():
        raise gr.Error("الرجاء إدخال نص أولاً / Please enter a prompt first!")

    try:
        # High quality text-to-image model
        model_id = "stabilityai/stable-diffusion-xl-base-1.0"
        image = client.text_to_image(prompt, model=model_id)
        return image
    except Exception as e:
        try:
            # Fallback to an alternative fast model if busy
            model_id = "runwayml/stable-diffusion-v1-5"
            image = client.text_to_image(prompt, model=model_id)
            return image
        except Exception as e2:
            raise gr.Error(f"Error during generation: {str(e2)}")


def upscale_image_fn(image, upscale_factor=2.0):
    """
    Upscales an image and enhances its details with AI.
    1. Resizes with high-quality Lanczos interpolation.
    2. Runs a low-strength image-to-image pass to reconstruct textures and add sharpness.
    """
    if image is None:
        raise gr.Error("الرجاء تحميل صورة أولاً / Please upload an image first!")

    try:
        # Step 1: Physical upscale using high quality lanczos filters
        width, height = image.size
        new_width = int(width * float(upscale_factor))
        new_height = int(height * float(upscale_factor))
        upscaled_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Step 2: AI Enhancer Pass to re-render sharp pixel-level details
        try:
            enhancer_prompt = "extremely detailed, 4k, ultra-sharp focus, clean textures, masterfully rendered"

            # Keep dimensions reasonable for API stability to prevent timeout
            max_api_dim = 1024
            if upscaled_image.width > max_api_dim or upscaled_image.height > max_api_dim:
                api_input = upscaled_image.copy()
                api_input.thumbnail((max_api_dim, max_api_dim), Image.Resampling.LANCZOS)
            else:
                api_input = upscaled_image

            # Image-to-image pass with low strength (0.15) to sharpen details without altering structure
            enhanced_image = client.image_to_image(
                image=api_input,
                prompt=enhancer_prompt,
                strength=0.15,
                model="stabilityai/stable-diffusion-xl-base-1.0"
            )

            # Restore to requested upscaled size if it was resized down for the API
            if enhanced_image.size != upscaled_image.size:
                enhanced_image = enhanced_image.resize(upscaled_image.size, Image.Resampling.LANCZOS)

            return enhanced_image
        except Exception as api_err:
            # Fallback to pure high-quality LANCZOS upscaled if the serverless API is overloaded/unreachable
            print(f"AI detail enhancer bypass: {api_err}")
            return upscaled_image

    except Exception as e:
        raise gr.Error(f"Error during upscaling: {str(e)}")


# =========================================================
# NEW: Local AI tools (Real-ESRGAN, GFPGAN, rembg, LaMa)
# All models are loaded lazily (only on first actual use) to keep
# server startup fast and memory usage low on the free CPU Space.
# =========================================================

_realesrgan_model = None
_gfpgan_model = None
_rembg_session = None
_lama_model = None


def get_realesrgan():
    """
    Lazy-load the Real-ESRGAN upsampler (general x4 model).
    NOTE: Real-ESRGAN is notably slow on CPU (no GPU acceleration).
    A single 1024x1024 image can take from several seconds up to
    ~1 minute depending on Space load. `tile=256` below keeps memory
    bounded but does not change this fundamental CPU speed limit.
    """
    global _realesrgan_model
    if _realesrgan_model is None:
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer

        weights_path = "/code/weights/RealESRGAN_x4plus.pth"
        model_arch = RRDBNet(
            num_in_ch=3, num_out_ch=3, num_feat=64,
            num_block=23, num_grow_ch=32, scale=4
        )
        _realesrgan_model = RealESRGANer(
            scale=4,
            model_path=weights_path,
            model=model_arch,
            tile=256,          # tiling keeps RAM usage bounded on CPU
            tile_pad=10,
            pre_pad=0,
            half=False,        # half precision is not supported on CPU
            device="cpu",
        )
    return _realesrgan_model


def get_gfpgan():
    """Lazy-load the GFPGAN face-restoration model."""
    global _gfpgan_model
    if _gfpgan_model is None:
        from gfpgan import GFPGANer

        weights_path = "/code/weights/GFPGANv1.4.pth"
        _gfpgan_model = GFPGANer(
            model_path=weights_path,
            upscale=1,          # we only restore faces here; use Real-ESRGAN separately to upscale
            arch="clean",
            channel_multiplier=2,
            bg_upsampler=None,  # avoid loading Real-ESRGAN as background upsampler to save RAM
        )
    return _gfpgan_model


def get_rembg_session():
    """Lazy-load the rembg (u2net) background-removal session."""
    global _rembg_session
    if _rembg_session is None:
        from rembg import new_session
        _rembg_session = new_session("u2net")
    return _rembg_session


def get_lama():
    """Lazy-load the LaMa inpainting model."""
    global _lama_model
    if _lama_model is None:
        from simple_lama_inpainting import SimpleLama
        _lama_model = SimpleLama()
    return _lama_model


def decode_base64_image(image_data: str) -> Image.Image:
    """Decode a base64 (optionally data-URL prefixed) string into a PIL RGB image."""
    if "," in image_data:
        image_data = image_data.split(",")[1]
    decoded = base64.b64decode(image_data)
    img = Image.open(io.BytesIO(decoded))
    return img.convert("RGB")


def decode_base64_mask(mask_data: str, size) -> Image.Image:
    """Decode a base64 mask into a single-channel (L) PIL image resized to `size`."""
    if "," in mask_data:
        mask_data = mask_data.split(",")[1]
    decoded = base64.b64decode(mask_data)
    mask = Image.open(io.BytesIO(decoded)).convert("L")
    if mask.size != size:
        mask = mask.resize(size, Image.Resampling.NEAREST)
    return mask


def build_rect_mask(size, rect) -> Image.Image:
    """
    Build a white-rectangle-on-black mask from a simple rect dict:
    {"x": int, "y": int, "width": int, "height": int}
    Coordinates are in pixels relative to the original image.
    """
    width, height = size
    mask = Image.new("L", size, 0)
    x = max(0, min(int(rect.get("x", 0)), width))
    y = max(0, min(int(rect.get("y", 0)), height))
    w = max(1, int(rect.get("width", 0)))
    h = max(1, int(rect.get("height", 0)))
    x2 = max(0, min(x + w, width))
    y2 = max(0, min(y + h, height))
    for py in range(y, y2):
        for px in range(x, x2):
            mask.putpixel((px, py), 255)
    return mask


def image_to_base64_png(img: Image.Image) -> str:
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"


def realesrgan_upscale_fn(image: Image.Image, outscale: float = 4.0) -> Image.Image:
    upsampler = get_realesrgan()
    img_np = np.array(image)  # RGB
    # RealESRGANer expects BGR (it internally does the conversion via cv2 convention)
    img_bgr = img_np[:, :, ::-1]
    output, _ = upsampler.enhance(img_bgr, outscale=outscale)
    output_rgb = output[:, :, ::-1]
    return Image.fromarray(output_rgb)


def gfpgan_restore_fn(image: Image.Image) -> Image.Image:
    restorer = get_gfpgan()
    img_np = np.array(image)
    img_bgr = img_np[:, :, ::-1]
    _, _, restored_bgr = restorer.enhance(
        img_bgr, has_aligned=False, only_center_face=False, paste_back=True
    )
    restored_rgb = restored_bgr[:, :, ::-1]
    return Image.fromarray(restored_rgb)


def remove_background_fn(image: Image.Image) -> Image.Image:
    from rembg import remove
    session = get_rembg_session()
    result = remove(image, session=session)  # returns RGBA PIL image
    return result


def inpaint_fn(image: Image.Image, mask: Image.Image) -> Image.Image:
    lama = get_lama()
    result = lama(image, mask)
    return result


# =========================================================
# Gradio UI (existing tabs preserved, new tabs added)
# =========================================================
with gr.Blocks(title="AI Image Hub", css="footer {visibility: hidden}") as demo:
    gr.Markdown("# 🎨 SCRIPT PUBLIC - AI Image Generator & Super-Resolution Upscaler")
    gr.Markdown("This Hugging Face Space is connected to your web application to serve high-fidelity AI requests securely.")

    with gr.Tab("✨ Text to Image / توليد الصور"):
        with gr.Row():
            with gr.Column():
                prompt_input = gr.Textbox(label="Prompt / الوصف", placeholder="Describe your image...", lines=3)
                generate_btn = gr.Button("Create Image / توليد صورة ✨", variant="primary")
            with gr.Column():
                image_output = gr.Image(label="Result / النتيجة", type="pil")
        generate_btn.click(fn=generate_image_fn, inputs=[prompt_input], outputs=[image_output])

    with gr.Tab("🔬 Enhance & Upscale / تكبير وتحسين الصور"):
        with gr.Row():
            with gr.Column():
                upload_input = gr.Image(label="Upload / تحميل صورة", type="pil")
                factor_slider = gr.Slider(minimum=1.5, maximum=4.0, value=2.0, step=0.5, label="Upscale Factor / معامل التكبير")
                upscale_btn = gr.Button("Enhance Quality / تكبير وتحسين ⚡", variant="primary")
            with gr.Column():
                upscale_output = gr.Image(label="Result / النتيجة", type="pil")
        upscale_btn.click(fn=upscale_image_fn, inputs=[upload_input, factor_slider], outputs=[upscale_output])

    with gr.Tab("🧬 Real-ESRGAN Upscale / تكبير حقيقي بالذكاء الاصطناعي"):
        with gr.Row():
            with gr.Column():
                re_input = gr.Image(label="Upload / تحميل صورة", type="pil")
                re_scale = gr.Slider(minimum=2, maximum=4, value=4, step=1, label="Outscale")
                re_btn = gr.Button("Run Real-ESRGAN ⚡", variant="primary")
            with gr.Column():
                re_output = gr.Image(label="Result / النتيجة", type="pil")
        re_btn.click(fn=realesrgan_upscale_fn, inputs=[re_input, re_scale], outputs=[re_output])

    with gr.Tab("🙂 Face Restore (GFPGAN) / ترميم الوجوه"):
        with gr.Row():
            with gr.Column():
                gf_input = gr.Image(label="Upload / تحميل صورة", type="pil")
                gf_btn = gr.Button("Restore Faces ⚡", variant="primary")
            with gr.Column():
                gf_output = gr.Image(label="Result / النتيجة", type="pil")
        gf_btn.click(fn=gfpgan_restore_fn, inputs=[gf_input], outputs=[gf_output])

    with gr.Tab("✂️ Remove Background / إزالة الخلفية"):
        with gr.Row():
            with gr.Column():
                rb_input = gr.Image(label="Upload / تحميل صورة", type="pil")
                rb_btn = gr.Button("Remove Background ⚡", variant="primary")
            with gr.Column():
                rb_output = gr.Image(label="Result / النتيجة", type="pil")
        rb_btn.click(fn=remove_background_fn, inputs=[rb_input], outputs=[rb_output])

# Create FastAPI application
app = FastAPI()


# =========================================================
# Shared auth helper (same Bearer-token scheme as the original app)
# =========================================================
def check_auth(request: Request):
    """
    Returns None if authorized, or a JSONResponse with the appropriate
    error if not. Callers should `return` the result if it's not None.
    """
    expected_token = os.getenv("HF_TOKEN", "").strip()
    if not expected_token:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Server Error: HF_TOKEN is not configured in Space secrets/environment variables."}
        )

    auth_header = request.headers.get("Authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Unauthorized: Missing or invalid Authorization header"}
        )
    token_part = auth_header.replace("Bearer ", "").strip()
    if token_part != expected_token:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Unauthorized: Invalid access token"}
        )
    return None


# =========================================================
# Existing endpoints (unchanged)
# =========================================================
@app.post("/api/generate")
async def api_generate(request: Request, payload: dict = Body(...)):
    auth_error = check_auth(request)
    if auth_error:
        return auth_error

    prompt = payload.get("prompt", "")
    if not prompt:
        return JSONResponse(status_code=400, content={"success": False, "error": "Prompt is required"})
    try:
        img = generate_image_fn(prompt)
        return {"success": True, "image": image_to_base64_png(img)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/upscale")
async def api_upscale(request: Request, payload: dict = Body(...)):
    auth_error = check_auth(request)
    if auth_error:
        return auth_error

    image_data = payload.get("image", "")
    upscale_factor = float(payload.get("upscale_factor", 2.0))
    if not image_data:
        return JSONResponse(status_code=400, content={"success": False, "error": "Image data is required"})

    try:
        img = decode_base64_image(image_data)
        upscaled_img = upscale_image_fn(img, upscale_factor)
        return {"success": True, "image": image_to_base64_png(upscaled_img)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =========================================================
# NEW endpoints: local AI tools
# All accept: { "image": "data:image/png;base64,...", ... }
# All return: { "success": true, "image": "data:image/png;base64,..." }
# =========================================================

@app.post("/api/upscale-realesrgan")
async def api_upscale_realesrgan(request: Request, payload: dict = Body(...)):
    """
    Real super-resolution upscaling with Real-ESRGAN (runs fully offline,
    no external inference API needed).
    Body: { "image": "<base64>", "outscale": 4 }
    """
    auth_error = check_auth(request)
    if auth_error:
        return auth_error

    image_data = payload.get("image", "")
    outscale = float(payload.get("outscale", 4.0))
    if not image_data:
        return JSONResponse(status_code=400, content={"success": False, "error": "Image data is required"})

    try:
        img = decode_base64_image(image_data)
        result = realesrgan_upscale_fn(img, outscale)
        return {"success": True, "image": image_to_base64_png(result)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/restore-face")
async def api_restore_face(request: Request, payload: dict = Body(...)):
    """
    Face restoration / enhancement with GFPGAN.
    Body: { "image": "<base64>" }
    """
    auth_error = check_auth(request)
    if auth_error:
        return auth_error

    image_data = payload.get("image", "")
    if not image_data:
        return JSONResponse(status_code=400, content={"success": False, "error": "Image data is required"})

    try:
        img = decode_base64_image(image_data)
        result = gfpgan_restore_fn(img)
        return {"success": True, "image": image_to_base64_png(result)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/remove-bg")
async def api_remove_bg(request: Request, payload: dict = Body(...)):
    """
    Background removal with rembg. Returns a transparent PNG (RGBA).
    Body: { "image": "<base64>" }
    """
    auth_error = check_auth(request)
    if auth_error:
        return auth_error

    image_data = payload.get("image", "")
    if not image_data:
        return JSONResponse(status_code=400, content={"success": False, "error": "Image data is required"})

    try:
        img = decode_base64_image(image_data)
        result = remove_background_fn(img)  # RGBA
        return {"success": True, "image": image_to_base64_png(result)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/inpaint")
async def api_inpaint(request: Request, payload: dict = Body(...)):
    """
    Object removal / cleanup with LaMa.
    Body: {
      "image": "<base64>",
      "mask": "<base64>"          # optional: white=remove area, black=keep
      "rect": {"x":0,"y":0,"width":100,"height":100}   # optional fallback if no mask given
    }
    At least one of "mask" or "rect" must be provided.
    """
    auth_error = check_auth(request)
    if auth_error:
        return auth_error

    image_data = payload.get("image", "")
    mask_data = payload.get("mask")
    rect = payload.get("rect")

    if not image_data:
        return JSONResponse(status_code=400, content={"success": False, "error": "Image data is required"})
    if not mask_data and not rect:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Either 'mask' (base64 image) or 'rect' ({x,y,width,height}) is required"}
        )

    try:
        img = decode_base64_image(image_data)

        if mask_data:
            mask = decode_base64_mask(mask_data, img.size)
        else:
            mask = build_rect_mask(img.size, rect)

        result = inpaint_fn(img, mask)
        return {"success": True, "image": image_to_base64_png(result)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# Mount Gradio app to the root path of FastAPI
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
