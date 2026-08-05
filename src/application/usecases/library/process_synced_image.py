import structlog

from src.domain.images import events as image_events
from src.domain.images import operations as image_operations
from src.domain.images.queries import NoFilmSimulationError
from src.domain.library import operations as library_operations
from src.domain.library import queries as library_queries
from src.domain.recipes import validation as recipe_validation

logger = structlog.get_logger("application.library.process_synced_image")


def process_synced_image(*, image_path: str, sync_run_id: int) -> None:
    """
    Process a single image as part of sync run *sync_run_id* and record progress.

    Composes the pure image-processing operation with sync-run bookkeeping so the
    processing operation stays unaware of sync: files that cannot produce a recipe
    count as skipped, whether because they carry no Fujifilm metadata or because
    their EXIF fails recipe validation; unexpected failures are logged and counted
    as errors (the run continues); and successful imports count as processed. When
    every image in the run has a terminal outcome, the run is completed.

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
        image_events.publish_event(
            event_type=image_events.IMAGE_IMPORT_SKIPPED,
            image_path=image_path,
            reason=image_events.SKIP_REASON_NO_FILM_SIMULATION,
        )
    except recipe_validation.InvalidFujifilmRecipeData as exc:
        run.record_skipped()
        image_events.publish_event(
            event_type=image_events.IMAGE_IMPORT_SKIPPED,
            image_path=image_path,
            reason=image_events.SKIP_REASON_INVALID_RECIPE_DATA,
            recipe_field=exc.field,
        )
    except Exception:
        logger.exception("Failed to process image during sync")
        run.record_error()
    else:
        run.record_processed()

    run.refresh_from_db()
    if run.all_images_accounted_for():
        library_operations.complete_sync_run(run=run)
