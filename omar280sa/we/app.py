"""
app.py
------
The FastAPI server. Two routes only:

  GET  /        -> serves the upload page
  POST /upload   -> receives an image, compresses it, uploads it,
                    returns a JSON result

Temp files are always cleaned up, even if something goes wrong.
The server never crashes because one upload failed — every error is
caught and turned into a JSON response instead.
"""

import logging
import os
import uuid

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from compress import compress_image
from config import load_settings
from upload import upload_image

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

app = FastAPI(title="Personal Image Upload Service")

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

INDEX_PATH = os.path.join(BASE_DIR, "templates", "index.html")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    """
    Serve the single-page upload UI.

    The page has no server-side variables (no {{ }} placeholders), so it's
    served directly as a static file instead of through a template engine —
    one less moving part, and it sidesteps Jinja2/Starlette version-mismatch
    issues entirely.
    """
    return FileResponse(INDEX_PATH)


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    quality: int = Form(None),
    target_size: int = Form(None),
    max_width: int = Form(None),
):
    """
    Receive an image, compress it to WebP, upload it to Cloudinary,
    and return the result as JSON.

    Form fields (quality, target_size, max_width) are optional — if not
    provided, values from settings.json are used instead.
    """
    settings = load_settings()

    # Fall back to settings.json for anything the client didn't send.
    quality = quality if quality is not None else settings["quality"]
    target_size = target_size if target_size is not None else settings["target_size"]
    max_width = max_width if max_width is not None else settings["max_width"]

    # Clamp values to sane ranges so a bad slider value can't break anything.
    quality = max(1, min(100, quality))
    target_size = max(1, target_size)
    max_width = max(50, max_width)

    # Reject obviously-not-an-image uploads early based on content type.
    if not file.content_type or not file.content_type.startswith("image/"):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Uploaded file is not an image"},
        )

    # Use a random name so concurrent uploads never collide.
    job_id = uuid.uuid4().hex
    input_path = os.path.join(TEMP_DIR, f"{job_id}_input")
    output_path = os.path.join(TEMP_DIR, f"{job_id}_output.webp")

    try:
        # --- Save the upload to disk ---
        try:
            contents = await file.read()
            with open(input_path, "wb") as f:
                f.write(contents)
        except OSError as e:
            logger.error(f"Failed to save uploaded file: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Failed to save uploaded file"},
            )

        # --- Compress ---
        compress_result = compress_image(
            input_path=input_path,
            output_path=output_path,
            quality=quality,
            target_size_kb=target_size,
            max_width=max_width,
        )

        if not compress_result["success"]:
            return JSONResponse(status_code=400, content=compress_result)

        # --- Upload to Cloudinary ---
        upload_result = upload_image(output_path)

        if not upload_result["success"]:
            return JSONResponse(status_code=502, content=upload_result)

        # --- Success ---
        return {
            "success": True,
            "url": upload_result["url"],
            "provider": upload_result["provider"],
            "size_kb": compress_result["size_kb"],
        }

    except Exception as e:
        # Catch-all safety net: one bad upload must never take down the server.
        logger.exception(f"Unexpected error while processing upload: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Unexpected server error"},
        )

    finally:
        # Always clean up temp files, success or failure.
        for path in (input_path, output_path):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as e:
                    logger.warning(f"Could not delete temp file {path}: {e}")
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
