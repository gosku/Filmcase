import attrs
from django.conf import settings

from src.domain.images import events, operations, queries
from src.domain.recipes import validation as recipe_validation
from src.services import workertasks


@attrs.frozen
class FolderImportSummary:
    """
    Counts produced by an :func:`import_images_from_folder` run.

    ``skipped`` holds the files that cannot produce a recipe. It is always empty
    in async mode, where each file's outcome is only known inside the worker.
    """

    total: int
    processed: int = 0
    skipped: tuple[str, ...] = ()


def import_images_from_folder(*, folder: str) -> FolderImportSummary:
    """
    Process all JPG images in *folder*, dispatching async or sync based on settings.
    """
    if settings.USE_ASYNC_TASKS:
        return FolderImportSummary(total=_enqueue_images_in_folder(folder=folder))
    return _process_images_in_folder(folder=folder)


def _enqueue_images_in_folder(*, folder: str) -> int:
    """
    Enqueue a Celery task for every JPG image found under *folder*.

    Returns the total number of tasks enqueued.
    """
    paths = queries.collect_image_paths(folder=folder)
    for path in paths:
        workertasks.enqueue_task(
            task_name="src.interfaces.tasks.process_image_task",
            kwargs={"image_path": path},
            queue=settings.PROCESS_IMAGE_QUEUE,
        )
        events.publish_event(event_type=events.TASK_IMAGE_ENQUEUED, image_path=path)
    return len(paths)


def _process_images_in_folder(*, folder: str) -> FolderImportSummary:
    """
    Process all JPG images in *folder* sequentially, one file at a time.

    A file that carries no Fujifilm metadata, or whose EXIF cannot produce a
    valid recipe, is recorded as skipped so it never aborts the rest of the run.
    """
    paths = queries.collect_image_paths(folder=folder)
    processed = 0
    skipped: list[str] = []
    for path in paths:
        try:
            operations.process_image(image_path=path)
        except operations.NoFilmSimulationError:
            skipped.append(path)
            events.publish_event(
                event_type=events.IMAGE_IMPORT_SKIPPED,
                image_path=path,
                reason=events.SKIP_REASON_NO_FILM_SIMULATION,
            )
        except recipe_validation.InvalidFujifilmRecipeData as exc:
            skipped.append(path)
            events.publish_event(
                event_type=events.IMAGE_IMPORT_SKIPPED,
                image_path=path,
                reason=events.SKIP_REASON_INVALID_RECIPE_DATA,
                recipe_field=exc.field,
            )
        else:
            processed += 1
    return FolderImportSummary(
        total=len(paths),
        processed=processed,
        skipped=tuple(skipped),
    )
