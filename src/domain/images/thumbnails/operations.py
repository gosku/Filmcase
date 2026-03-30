from pathlib import Path

from PIL import Image as PILImage

from src.domain.images.thumbnails import queries as thumbnail_queries

# Maps EXIF Orientation tag values to PIL transpose operations.
# Orientation tag = 0x0112.  Value 1 means "normal" (no-op).
_EXIF_ORIENTATION_TAG = 0x0112
_ORIENTATION_TO_TRANSPOSE = {
    2: PILImage.Transpose.FLIP_LEFT_RIGHT,
    3: PILImage.Transpose.ROTATE_180,
    4: PILImage.Transpose.FLIP_TOP_BOTTOM,
    5: PILImage.Transpose.TRANSPOSE,
    6: PILImage.Transpose.ROTATE_270,
    7: PILImage.Transpose.TRANSVERSE,
    8: PILImage.Transpose.ROTATE_90,
}


def generate_thumbnail(*, original_path: Path, width: int) -> Path:
    """Resize *original_path* to *width* px wide, applying EXIF orientation, and
    save to the thumbnail cache.  Returns the cache path.  Skips generation if
    a cached file already exists."""
    cache_path = thumbnail_queries.thumbnail_cache_path(original_path=original_path, width=width)
    if cache_path.is_file():
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with PILImage.open(original_path) as img:
        fmt = img.format or "JPEG"

        # Read orientation from the EXIF header before any pixel data is
        # decoded.  getexif() only parses the APP1 segment, which Pillow
        # already read during open().
        orientation = img.getexif().get(_EXIF_ORIENTATION_TAG, 1)

        # Tell the JPEG decoder to downsample natively.  Must be called before
        # .load() to take effect.  Using the exact target dimensions lets the
        # decoder pick the largest possible DCT scale factor (1/2, 1/4, 1/8)
        # that still satisfies both width and height, maximising the speedup.
        if fmt == "JPEG" and img.width > width:
            target_height = int(width * img.height / img.width)
            img.draft("RGB", (width, target_height))

        # Decode pixels at the (reduced) draft resolution.
        img.load()

        # Apply EXIF orientation manually — avoids a second .load() call that
        # ImageOps.exif_transpose() would trigger internally.
        transpose_method = _ORIENTATION_TO_TRANSPOSE.get(orientation)
        if transpose_method is not None:
            img = img.transpose(transpose_method)

        if img.width > width:
            new_height = int(img.height * width / img.width)
            img = img.resize((width, new_height), PILImage.Resampling.LANCZOS)

        img.save(cache_path, format=fmt)
    return cache_path
