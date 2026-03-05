"""
cloudinary_service.py – Cloudinary upload/delete helpers for violation evidence.
Falls back gracefully if Cloudinary is not configured.
"""

import os
import io
from dotenv import load_dotenv

load_dotenv()

_configured = False

def configure_cloudinary():
    """Initialize Cloudinary from environment variables."""
    global _configured
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key = os.getenv("CLOUDINARY_API_KEY")
    api_secret = os.getenv("CLOUDINARY_API_SECRET")

    if not all([cloud_name, api_key, api_secret]):
        print("[Cloudinary] Not configured — evidence images will not be uploaded")
        return

    try:
        import cloudinary
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True
        )
        _configured = True
        print(f"[Cloudinary] Configured for cloud: {cloud_name}")
    except ImportError:
        print("[Cloudinary] cloudinary package not installed — pip install cloudinary")


def upload_violation_image(jpeg_bytes: bytes, camera_id: str, violation_type: str) -> dict:
    """
    Upload a violation evidence JPEG to Cloudinary.
    Returns { secure_url, public_id } or empty dict if not configured.
    """
    if not _configured:
        return {}

    import cloudinary.uploader

    folder = f"violations/{camera_id}"
    result = cloudinary.uploader.upload(
        io.BytesIO(jpeg_bytes),
        folder=folder,
        resource_type="image",
        format="jpg",
        transformation=[
            {"width": 800, "crop": "limit"},
            {"quality": "auto:good"}
        ]
    )
    return {
        "secure_url": result.get("secure_url", ""),
        "public_id": result.get("public_id", "")
    }


def upload_video(video_path: str, camera_id: str) -> dict:
    """
    Upload annotated output video to Cloudinary.
    Returns { secure_url, public_id } or empty dict if not configured.
    """
    if not _configured:
        return {}

    import cloudinary.uploader

    folder = f"videos/{camera_id}"
    result = cloudinary.uploader.upload(
        video_path,
        folder=folder,
        resource_type="video",
    )
    return {
        "secure_url": result.get("secure_url", ""),
        "public_id": result.get("public_id", "")
    }


def delete_image(public_id: str):
    """Delete an image from Cloudinary by public_id."""
    if not _configured or not public_id:
        return

    import cloudinary.uploader
    try:
        cloudinary.uploader.destroy(public_id)
    except Exception as e:
        print(f"[Cloudinary] Failed to delete {public_id}: {e}")
