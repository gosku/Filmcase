import hashlib
import mimetypes
from pathlib import Path

from django.conf import settings


def thumbnail_cache_path(*, original_path: Path, width: int) -> Path:
    """Return the cache file path for a thumbnail of *original_path* at *width* px."""
    key = hashlib.md5(f"{original_path}:{width}".encode()).hexdigest()
    return Path(settings.THUMBNAIL_CACHE_DIR) / f"{key}{original_path.suffix}"


def thumbnail_content_type(*, cache_path: Path) -> str:
    """Return the MIME type for *cache_path*, defaulting to ``image/jpeg``."""
    content_type, _ = mimetypes.guess_type(cache_path.name)
    return content_type or "image/jpeg"
