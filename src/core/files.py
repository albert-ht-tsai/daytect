import os

from fastapi import HTTPException, UploadFile, status

from src.core.config import AVATAR_DIR, BASE_URL

_ALLOWED_AVATAR_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


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
