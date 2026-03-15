from src.data.models import Image
from src.domain.images import operations


def reprocess_kelvin_images() -> tuple[int, list[str]]:
    """Reprocess all images whose white balance EXIF value is Kelvin.

    Returns:
        A tuple of (total_found, skipped_paths).
    """
    images = Image.objects.with_kelvin_white_balance().select_related("fujifilm_exif")
    paths = [image.filepath for image in images]
    skipped = []
    for path in paths:
        try:
            operations.process_image(image_path=path)
        except operations.NoFilmSimulationError:
            skipped.append(path)
    return len(paths), skipped
