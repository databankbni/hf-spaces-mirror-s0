"""
upload.py
---------
Uploads a compressed image file to Cloudinary.

Tries each configured account in order. If one fails (bad credentials,
quota exceeded, network hiccup, etc.), it automatically moves on to the
next account. Returns which account succeeded.

No classes, no retries-with-backoff complexity — just a simple loop.
"""

import logging

import cloudinary
import cloudinary.uploader

from config import CLOUDINARY_ACCOUNTS

logger = logging.getLogger("upload")


def upload_image(file_path: str) -> dict:
    """
    Upload a file to Cloudinary, trying each account in order until one
    succeeds.

    Args:
        file_path: path to the local file to upload.

    Returns:
        dict with success flag, and on success: url + provider name.
        On failure: an error message listing what was tried.
    """
    if not CLOUDINARY_ACCOUNTS:
        return {
            "success": False,
            "error": "No Cloudinary accounts configured on the server.",
        }

    errors = []

    for account in CLOUDINARY_ACCOUNTS:
        try:
            # Configure the SDK for this specific account before each
            # upload attempt. cloudinary's config is global/module-level,
            # so we just re-point it each time we try a new account.
            cloudinary.config(
                cloud_name=account["cloud_name"],
                api_key=account["api_key"],
                api_secret=account["api_secret"],
            )

            result = cloudinary.uploader.upload(file_path, resource_type="image")
            url = result.get("secure_url")

            if not url:
                raise ValueError("Cloudinary response had no secure_url")

            logger.info(f"Upload succeeded via {account['name']}")
            return {
                "success": True,
                "url": url,
                "provider": account["name"],
            }

        except Exception as e:
            # Any failure (bad creds, quota, network) -> log and try next account.
            logger.warning(f"Upload failed on {account['name']}: {e}")
            errors.append(f"{account['name']}: {e}")
            continue

    # All accounts failed.
    logger.error("All Cloudinary accounts failed to upload the image")
    return {
        "success": False,
        "error": "All Cloudinary accounts failed. Details: " + " | ".join(errors),
    }
