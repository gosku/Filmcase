from src.domain.images import operations, queries


def process_images_in_folder(*, folder: str) -> tuple[int, list[str]]:
    """Process all JPG images in *folder*, skipping those without Fujifilm metadata.

    Returns:
        A tuple of (total_found, skipped_paths).
    """
    paths = queries.collect_image_paths(folder=folder)
    skipped = []
    for path in paths:
        try:
            operations.process_image(image_path=path)
        except operations.NoFilmSimulationError:
            skipped.append(path)
    return len(paths), skipped
