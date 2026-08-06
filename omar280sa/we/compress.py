"""
compress.py
-----------
Takes an input image path, converts it to WebP, resizes it if it's
too wide, and reduces quality step-by-step until it's close to the
target size (or quality bottoms out at 20).

One function, no classes. Simple in, simple out.
"""

import logging
import os

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger("compress")

MIN_QUALITY = 20
QUALITY_STEP = 5


def compress_image(input_path: str, output_path: str, quality: int,
                    target_size_kb: int, max_width: int) -> dict:
    """
    Compress an image into WebP format.

    Args:
        input_path: path to the original uploaded file.
        output_path: where to write the compressed .webp file.
        quality: starting quality (1-100), from user/settings.
        target_size_kb: desired max size in KB. We stop reducing quality
                         once we're at or under this.
        max_width: if the image is wider than this, it gets downscaled
                    (aspect ratio preserved). Never upscaled.

    Returns:
        dict with success flag, output path, final size in KB, and the
        quality level that was actually used.
    """
    try:
        image = Image.open(input_path)
        image.load()  # force-read now so a corrupt file fails here, not later
    except (UnidentifiedImageError, OSError) as e:
        logger.error(f"Could not open image '{input_path}': {e}")
        return {"success": False, "error": "Invalid or unreadable image file"}

    # Convert to RGB. WebP doesn't need alpha handling headaches, and
    # Pillow can't save CMYK/P mode images straight to WebP reliably.
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")

    # Resize only if it's wider than max_width. Never resize up.
    if image.width > max_width:
        ratio = max_width / float(image.width)
        new_height = int(image.height * ratio)
        image = image.resize((max_width, new_height), Image.LANCZOS)
        logger.info(f"Resized image to {max_width}x{new_height}")

    target_bytes = target_size_kb * 1024
    current_quality = quality
    final_size_kb = None

    # Step quality down until we're under the target size, or we hit the floor.
    # We always keep the *last successfully saved* file at output_path, so
    # even if we never reach the target we still return the smallest we got.
    while True:
        image.save(output_path, format="WEBP", quality=current_quality)
        current_size = os.path.getsize(output_path)
        final_size_kb = round(current_size / 1024, 1)

        logger.info(f"Tried quality={current_quality} -> {final_size_kb} KB")

        if current_size <= target_bytes:
            break  # good enough, stop here

        if current_quality <= MIN_QUALITY:
            logger.warning(
                f"Reached minimum quality ({MIN_QUALITY}) but still "
                f"{final_size_kb} KB (target was {target_size_kb} KB)"
            )
            break  # can't shrink further, return what we have

        current_quality -= QUALITY_STEP
        current_quality = max(current_quality, MIN_QUALITY)

    return {
        "success": True,
        "output_path": output_path,
        "size_kb": final_size_kb,
        "quality_used": current_quality,
        "width": image.width,
        "height": image.height,
    }
