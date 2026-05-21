import attrs

from src.data import models
from src.domain.images import events, operations, queries


@attrs.frozen
class DeduplicationSummary:
    """
    Counts produced by a :func:`deduplicate_images` run.
    """

    hashed: int
    merged: int
    files_skipped: int


def deduplicate_images() -> DeduplicationSummary:
    """
    Backfill content hashes for legacy images and merge duplicate records.

    For every image with no content hash, the SHA-256 hash of its file is
    computed. If another image already holds that hash, the two are merged
    into the oldest record; otherwise the hash is backfilled. Images whose
    file is missing or unreadable are skipped. The operation is idempotent.
    """
    hashed = 0
    merged = 0
    files_skipped = 0

    for image_id in queries.get_unhashed_image_ids():
        image = models.Image.objects.filter(pk=image_id).first()
        if image is None:
            # Already merged away as a duplicate of an earlier row.
            continue
        if image.content_hash:
            # Already backfilled earlier in this run.
            continue
        try:
            content_hash = queries.compute_content_hash(image_path=image.filepath)
        except OSError:
            events.publish_event(
                event_type=events.IMAGE_DEDUP_FILE_MISSING,
                image_id=image.pk,
                filepath=image.filepath,
            )
            files_skipped += 1
            continue

        keeper = queries.find_image_by_content_hash(content_hash=content_hash)
        if keeper is None:
            image.set_content_hash(content_hash=content_hash)
            hashed += 1
        else:
            operations.merge_image_into(loser=image, keeper=keeper)
            merged += 1

    return DeduplicationSummary(hashed=hashed, merged=merged, files_skipped=files_skipped)
