import os

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
ANALYSIS_IMAGE_DIR = os.path.join(UPLOAD_DIR, "analysis")
