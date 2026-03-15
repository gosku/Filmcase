from pathlib import Path

from PIL import Image as PILImage, ImageOps

from src.domain.images.thumbnails.queries import thumbnail_cache_path


def generate_thumbnail(*, original_path: Path, width: int) -> Path:
    """Resize *original_path* to *width* px wide, applying EXIF orientation, and
    save to the thumbnail cache.  Returns the cache path.  Skips generation if
    a cached file already exists."""
    cache_path = thumbnail_cache_path(original_path=original_path, width=width)
    if cache_path.is_file():
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with PILImage.open(original_path) as img:
        fmt = img.format or "JPEG"
        img = ImageOps.exif_transpose(img)
        if img.width > width:
            new_height = int(img.height * width / img.width)
            img = img.resize((width, new_height), PILImage.Resampling.LANCZOS)
        img.save(cache_path, format=fmt)
    return cache_path
