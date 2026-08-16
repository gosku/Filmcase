import os
from collections.abc import Sequence
from pathlib import Path

import attrs
from django import conf
from django.db import transaction

from src.data import models
from src.domain.images import events, queries
from src.domain.images.queries import NoFilmSimulationError as NoFilmSimulationError
from src.domain.images.thumbnails import operations as thumbnail_operations
from src.domain.recipes import operations as recipe_operations


@attrs.frozen
class InvalidImageRatingError(Exception):
    """
    Raised when a rating value is outside the allowed range [0, IMAGE_MAX_RATING].
    """

    rating: int


@attrs.frozen
class UnableToRateImage(Exception):
    """
    Raised when an image cannot be rated for any reason.
    """

    image_path: str


def set_image_rating(*, image: models.Image, rating: int) -> None:
    """
    Set the rating of *image* to *rating*.

    Raises:
        InvalidImageRatingError: If *rating* is negative or exceeds
            settings.IMAGE_MAX_RATING.
    """
    if rating < 0 or rating > conf.settings.IMAGE_MAX_RATING:
        raise InvalidImageRatingError(rating)
    image.set_rating(rating)
    events.publish_event(
        event_type=events.IMAGE_RATING_SET,
        image_id=image.pk,
        rating=rating,
    )


def set_images_rating(*, image_ids: Sequence[int], rating: int) -> int:
    """
    Set the rating of every image in *image_ids* to *rating* in a single bulk update.

    Publishes one IMAGE_RATING_SET event per image that is actually updated;
    ids that do not exist are skipped and get no event. Returns the number of
    images updated.

    Raises:
        InvalidImageRatingError: If *rating* is negative or exceeds
            settings.IMAGE_MAX_RATING.
    """
    if rating < 0 or rating > conf.settings.IMAGE_MAX_RATING:
        raise InvalidImageRatingError(rating)

    with transaction.atomic():
        images = models.Image.objects.filter(pk__in=image_ids)
        updated_ids = list(images.values_list("pk", flat=True))
        images.update(rating=rating)

    for image_id in updated_ids:
        events.publish_event(
            event_type=events.IMAGE_RATING_SET,
            image_id=image_id,
            rating=rating,
        )

    return len(updated_ids)


def rate_image(*, image_path: str, rating: int) -> models.Image:
    """
    Find the Image for *image_path* and set its rating.

    Does not create a new DB record if the image is not found.

    Raises:
        UnableToRateImage: If the image cannot be found, the match is
            ambiguous, or the rating value is invalid.
    """
    try:
        image = queries.find_image_for_path(image_path=image_path)
    except (queries.ImageNotFound, queries.AmbiguousImageMatch) as exc:
        raise UnableToRateImage(image_path) from exc
    try:
        set_image_rating(image=image, rating=rating)
    except InvalidImageRatingError as exc:
        raise UnableToRateImage(image_path) from exc
    return image


def toggle_image_favorite(*, image_id: int) -> bool:
    """
    Toggle the is_favorite flag for the image with the given *image_id*.

    Returns the new value of is_favorite after toggling.
    """
    image = models.Image.objects.get(pk=image_id)
    image.is_favorite = not image.is_favorite
    image.save(update_fields=["is_favorite"])
    return image.is_favorite


def relocate_image(*, image: models.Image, new_path: str) -> bool:
    """
    Point *image* at *new_path* when the file it recorded has disappeared.

    An import that matches an existing record by content hash is either a move or
    a copy, and the two are told apart by the old file: if it is gone, the same
    bytes have simply been renamed or moved and the record must follow so that
    its rating, favourite flag and album membership survive. If the old file is
    still there, this is a second copy of the same photo and the record is left
    where it is.

    Never touches either file on disk. Returns True if the record was moved.
    """
    if new_path == image.filepath:
        return False
    if os.path.lexists(image.filepath):
        return False

    # filepath is unique. A legacy record already sitting at the new path would
    # collide, and raising inside the caller's transaction would poison it, so
    # check first rather than catching IntegrityError.
    if models.Image.objects.filter(filepath=new_path).exclude(pk=image.pk).exists():
        return False

    old_path = image.filepath
    image.set_location(filepath=new_path, filename=os.path.basename(new_path))
    events.publish_event(
        event_type=events.IMAGE_FILE_RELOCATED,
        image_id=image.pk,
        old_filepath=old_path,
        new_filepath=new_path,
    )
    return True


@transaction.atomic(durable=True)
def remove_image(*, image: models.Image, reason: str) -> None:
    """
    Remove *image* from the catalog because its file is gone or its library
    folder was removed.

    Removes the catalog entry only: the image file on disk is never touched.

    Recipe-card and cover-image references are set to null by the schema and are
    deliberately not repointed. A card is a self-contained rendered JPEG that
    outlives its source image, and a recipe with no explicit cover already falls
    back to its most-used image. The image's FujifilmExif row is deleted if this
    leaves it orphaned. The FujifilmRecipe is never touched, because recipes are
    shared and worth keeping even with no images left.
    """
    image_id = image.pk
    filepath = image.filepath
    exif_id = image.fujifilm_exif_id

    image.delete()

    if exif_id is not None and not models.Image.objects.filter(fujifilm_exif_id=exif_id).exists():
        models.FujifilmExif.objects.filter(pk=exif_id).delete()

    # Durable, so the row is committed before the cache files go: a rollback must
    # never leave a record pointing at thumbnails that have been unlinked.
    thumbnail_operations.delete_cached_thumbnails(original_path=Path(filepath))

    events.publish_event(
        event_type=events.IMAGE_REMOVED,
        image_id=image_id,
        filepath=filepath,
        reason=reason,
    )


@transaction.atomic()
def process_image(*, image_path: str) -> models.Image:
    """
    Read EXIF data from *image_path* and persist it to the database.

    Images are deduplicated by a SHA-256 hash of their file bytes: the same
    photo stored under several paths resolves to a single record. A legacy
    record imported before hashing existed is matched by its filepath (or, if
    the file has moved, by its EXIF identity) and has its hash backfilled.

    A matched record keeps its EXIF, recipe and user data, but follows its file:
    if the path it recorded no longer exists, the file has been renamed or moved
    and the record is repointed at *image_path*. See relocate_image.

    A FujifilmExif record is looked up or created for the image's EXIF field
    combination and linked via the recipe FK.

    Raises:
        NoFilmSimulationError: If the image has no film simulation EXIF data.
        InvalidFujifilmRecipeData: If the image's EXIF cannot produce a valid
            recipe. Nothing is persisted: the whole call is one transaction.
    """
    metadata = queries.read_image_exif(image_path=image_path)

    if metadata.camera_make.upper() != "FUJIFILM":
        raise NoFilmSimulationError(image_path)
    filename = os.path.basename(image_path)

    # Convert date string to timezone-aware datetime
    date_taken = queries.parse_exif_date(value=metadata.date_taken) if metadata.date_taken else None

    exif_fields = attrs.asdict(metadata)
    exif_fields.pop("date_taken")
    recipe_fields = {field: exif_fields.pop(field) for field in models.RECIPE_FIELDS}

    fujifilm_exif = models.FujifilmExif.get_or_create(**recipe_fields)

    fujifilm_recipe, _ = recipe_operations.get_or_create_recipe_from_metadata(metadata=metadata)

    content_hash = queries.compute_content_hash(image_path=image_path)
    existing = queries.find_existing_image_for_import(
        content_hash=content_hash,
        filepath=image_path,
        exif=metadata,
        taken_at=date_taken,
        filename=filename,
    )

    if existing is None:
        image = models.Image.create(
            filepath=image_path,
            filename=filename,
            taken_at=date_taken,
            content_hash=content_hash,
            fujifilm_exif=fujifilm_exif,
            fujifilm_recipe=fujifilm_recipe,
            **exif_fields,
        )
        created = True
    else:
        image = existing
        created = False
        # A row found by its hash is already complete; never override its EXIF or
        # recipe. An un-hashed legacy row only gets its content hash backfilled,
        # the data we did not store before.
        if existing.content_hash == "":
            existing.set_content_hash(content_hash=content_hash)
        # The path is the exception: a record whose file has moved follows it, so
        # a rename or a move keeps the same row rather than stranding it on a
        # path that no longer exists.
        relocate_image(image=existing, new_path=image_path)

    events.publish_event(
        event_type=events.RECIPE_IMAGE_CREATED if created else events.RECIPE_IMAGE_UPDATED,
        image_id=image.pk,
        filename=filename,
        film_simulation=fujifilm_exif.film_simulation,
        taken_at=date_taken.isoformat() if date_taken else "",
    )
    return image


@transaction.atomic()
def merge_image_into(*, loser: models.Image, keeper: models.Image) -> None:
    """
    Merge *loser* into *keeper* and delete *loser*.

    The keeper gains album membership if either copy had it and keeps the
    higher rating. Recipe-card and cover-image references are repointed to the
    keeper before *loser* is deleted (both FKs are SET_NULL, so deleting first
    would discard them). The loser's FujifilmExif row is deleted if the merge
    leaves it orphaned. The FujifilmRecipe is never touched — a recipe may
    exist without any image.
    """
    if loser.in_album and not keeper.in_album:
        keeper.set_as_in_album()
    if loser.rating > keeper.rating:
        keeper.set_rating(loser.rating)

    models.RecipeCard.objects.filter(image=loser).update(image=keeper)
    models.FujifilmRecipe.objects.filter(cover_image=loser).update(cover_image=keeper)

    exif_id = loser.fujifilm_exif_id
    loser.delete()

    if exif_id is not None and not models.Image.objects.filter(fujifilm_exif_id=exif_id).exists():
        models.FujifilmExif.objects.filter(pk=exif_id).delete()
