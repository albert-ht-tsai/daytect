import os
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile, status

from src.core.config import ANALYSIS_IMAGE_DIR, AVATAR_DIR, BASE_URL

_ALLOWED_AVATAR_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

_ALLOWED_ANALYSIS_IMAGE_TYPES = _ALLOWED_AVATAR_TYPES


def save_avatar(file: UploadFile, prefix: str, entity_id: int) -> str:
    ext = _ALLOWED_AVATAR_TYPES.get(file.content_type)
    if ext is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "Avatar must be a JPEG, PNG, WEBP, or GIF image"},
        )

    os.makedirs(AVATAR_DIR, exist_ok=True)
    for stale_ext in _ALLOWED_AVATAR_TYPES.values():
        stale_path = os.path.join(AVATAR_DIR, f"{prefix}_{entity_id}.{stale_ext}")
        if os.path.exists(stale_path):
            os.remove(stale_path)

    filename = f"{prefix}_{entity_id}.{ext}"
    with open(os.path.join(AVATAR_DIR, filename), "wb") as out_file:
        out_file.write(file.file.read())

    return f"{BASE_URL}/avatar/{filename}"


def generate_pic_id() -> str:
    return "analysis_pic_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:-3]


def save_analysis_image(image_bytes: bytes, content_type: str | None, pic_id: str) -> str | None:
    """Persists an uploaded analysis image to disk. Returns None (without raising) for
    unrecognized content types, since the image is still analyzed even if not saved."""
    ext = _ALLOWED_ANALYSIS_IMAGE_TYPES.get(content_type)
    if ext is None:
        return None

    os.makedirs(ANALYSIS_IMAGE_DIR, exist_ok=True)
    filename = f"{pic_id}.{ext}"
    with open(os.path.join(ANALYSIS_IMAGE_DIR, filename), "wb") as out_file:
        out_file.write(image_bytes)

    return f"{BASE_URL}/analysis-images/{filename}"
