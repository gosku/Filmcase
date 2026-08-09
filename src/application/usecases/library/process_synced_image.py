import structlog

from src.application.usecases.library.finalize_sync_run import finalize_sync_run
from src.data import models
from src.domain.images import events as image_events
from src.domain.images import operations as image_operations
from src.domain.images.queries import NoFilmSimulationError
from src.domain.library import operations as library_operations
from src.domain.library import queries as library_queries
from src.domain.recipes import validation as recipe_validation

logger = structlog.get_logger("application.library.process_synced_image")

# Enough of an error to recognise it on the ignored-images page without letting a
# pathological message fill the column.
_DETAIL_MAX_LEN = 500


def process_synced_image(*, image_path: str, sync_run_id: int) -> None:
    """
    Process a single image as part of sync run *sync_run_id* and record progress.

    Composes the pure image-processing operation with sync-run bookkeeping so the
    processing operation stays unaware of sync: files that cannot produce a recipe
    count as skipped, whether because they carry no Fujifilm metadata or because
    their EXIF fails recipe validation; unexpected failures are logged and counted
    as errors (the run continues); and successful imports count as processed. When
    every image in the run has a terminal outcome, the run is completed.

    Every outcome other than success is also remembered against the file itself,
    so later syncs leave it alone until it changes on disk. Without that the file
    has no trace in the catalog at all and is rediscovered, and re-read, on every
    single sync.

    If the run no longer exists (its folder was removed while this work was
    queued), the call returns without processing.
    """
    try:
        run = library_queries.get_sync_run(run_id=sync_run_id)
    except library_queries.SyncRunNotFound:
        return

    try:
        image_operations.process_image(image_path=image_path)
    except NoFilmSimulationError:
        run.record_skipped()
        _ignore(
            run=run,
            image_path=image_path,
            reason=models.IgnoredImage.REASON_NO_FILM_SIMULATION,
            detail="",
        )
        image_events.publish_event(
            event_type=image_events.IMAGE_IMPORT_SKIPPED,
            image_path=image_path,
            reason=image_events.SKIP_REASON_NO_FILM_SIMULATION,
        )
    except recipe_validation.InvalidFujifilmRecipeData as exc:
        run.record_skipped()
        _ignore(
            run=run,
            image_path=image_path,
            reason=models.IgnoredImage.REASON_INVALID_RECIPE_DATA,
            detail=exc.field,
        )
        image_events.publish_event(
            event_type=image_events.IMAGE_IMPORT_SKIPPED,
            image_path=image_path,
            reason=image_events.SKIP_REASON_INVALID_RECIPE_DATA,
            recipe_field=exc.field,
        )
    except Exception as exc:
        logger.exception("Failed to process image during sync")
        run.record_error()
        _ignore(
            run=run,
            image_path=image_path,
            reason=models.IgnoredImage.REASON_ERROR,
            detail=f"{type(exc).__name__}: {exc}"[:_DETAIL_MAX_LEN],
        )
    else:
        run.record_processed()
        # A file that failed before and imports now must stop being ignored, or
        # the record outlives the truth and shows a photo that is in the gallery
        # as though it had been rejected.
        library_operations.forget_ignored_path(filepath=image_path)

    run.refresh_from_db()
    if run.all_images_accounted_for():
        finalize_sync_run(run=run)


def _ignore(*, run: models.SyncRun, image_path: str, reason: str, detail: str) -> None:
    """
    Remember that this file could not be imported, without letting that
    bookkeeping break the run.

    A file that disappeared between the scan and now cannot be stat'ed, and that
    is an ordinary race rather than a failure worth aborting for: the next sync
    will not find it either.
    """
    try:
        library_operations.record_ignored_image(
            folder=run.folder,
            filepath=image_path,
            reason=reason,
            detail=detail,
        )
    except OSError:
        logger.warning("Could not remember an ignored image", image_path=image_path)
