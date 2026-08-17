from pathlib import Path
from typing import Any

from celery import shared_task
from django.conf import settings

from src.application.usecases.library.finalize_sync_run import finalize_sync_run_by_id
from src.application.usecases.library.process_synced_image import process_synced_image
from src.domain.images import events, operations
from src.domain.images.thumbnails import operations as thumbnail_operations
from src.domain.recipes import validation as recipe_validation
from src.services import workertasks

_SYNC_PROCESS_IMAGE_TASK = "src.interfaces.tasks.sync_process_image_task"


@shared_task(name="domain.process_image", bind=True, queue=settings.PROCESS_IMAGE_QUEUE)
def process_image_task(self: Any, /, *, image_path: str, **kwargs: object) -> str:
    """
    Celery task that processes a single image and stores its recipe in DB.
    """
    events.publish_event(
        event_type=events.TASK_IMAGE_STARTED,
        image_path=image_path,
        task_id=self.request.id,
    )
    try:
        recipe = operations.process_image(image_path=image_path)
    except operations.NoFilmSimulationError:
        events.publish_event(
            event_type=events.IMAGE_IMPORT_SKIPPED,
            image_path=image_path,
            reason=events.SKIP_REASON_NO_FILM_SIMULATION,
        )
        return f"Skipped {image_path} (no film simulation)"
    except recipe_validation.InvalidFujifilmRecipeData as exc:
        events.publish_event(
            event_type=events.IMAGE_IMPORT_SKIPPED,
            image_path=image_path,
            reason=events.SKIP_REASON_INVALID_RECIPE_DATA,
            recipe_field=exc.field,
        )
        return f"Skipped {image_path} (invalid recipe data)"
    events.publish_event(
        event_type=events.TASK_IMAGE_COMPLETED,
        image_path=image_path,
        task_id=self.request.id,
        image_id=recipe.pk,
    )
    return f"Processed {recipe.filename}"


@shared_task(name="library.sync_process_image", bind=True, queue=settings.PROCESS_IMAGE_QUEUE)
def sync_process_image_task(
    self: Any,
    /,
    *,
    image_path: str,
    sync_run_id: int,
    **kwargs: object,
) -> str:
    """
    Celery task that processes one image for a library sync run and reports
    progress against the run.

    One image per message is what makes a sync parallel: any free worker can take
    any image, a slow file delays only itself, and a failure retries one file
    rather than a hundred.
    """
    process_synced_image(image_path=image_path, sync_run_id=sync_run_id)
    return f"Processed {image_path} for sync run {sync_run_id}"


def _dispatch_image_batch(*, image_paths: list[str], sync_run_id: int) -> str:
    workertasks.enqueue_tasks(
        task_name=_SYNC_PROCESS_IMAGE_TASK,
        kwargs_list=[
            {"image_path": image_path, "sync_run_id": sync_run_id}
            for image_path in image_paths
        ],
        queue=settings.PROCESS_IMAGE_QUEUE,
    )
    return f"Dispatched {len(image_paths)} image(s) for sync run {sync_run_id}"


@shared_task(name="library.sync_dispatch_image_batch", bind=True, queue=settings.PROCESS_IMAGE_QUEUE)
def sync_dispatch_image_batch_task(
    self: Any,
    /,
    *,
    image_paths: list[str],
    sync_run_id: int,
    **kwargs: object,
) -> str:
    """
    Celery task that publishes one per-image task for each path in its batch.

    Dispatch happens in two levels because publishing is synchronous: whoever
    starts a sync cannot return until the last message is out, so publishing one
    message per file there would block startup on a large import. Batching the
    first level keeps that cheap, and doing the second level here spreads the
    publishing across workers instead of concentrating it in the starter.

    The batch is a unit of dispatch only. It is deliberately not a unit of work:
    processing a batch inside one task would cap parallelism at the number of
    batches and leave a larger worker pool idle.
    """
    return _dispatch_image_batch(image_paths=image_paths, sync_run_id=sync_run_id)


@shared_task(name="library.sync_process_image_batch", bind=True, queue=settings.PROCESS_IMAGE_QUEUE)
def sync_process_image_batch_task(
    self: Any,
    /,
    *,
    image_paths: list[str],
    sync_run_id: int,
    **kwargs: object,
) -> str:
    """
    Retained under its old name so messages published before the fan-out change
    still resolve to a task, rather than failing the run they belong to.

    It dispatches rather than processes, so an in-flight batch ends up handled the
    same way as a new one. Safe to delete once no such messages can remain.
    """
    return _dispatch_image_batch(image_paths=image_paths, sync_run_id=sync_run_id)


@shared_task(name="library.finalize_sync_run", bind=True, queue=settings.PROCESS_IMAGE_QUEUE)
def finalize_sync_run_task(self: Any, /, *, sync_run_id: int, **kwargs: object) -> str:
    """
    Celery task that finishes a sync run that had no images to process.

    A run with images is finished by whichever of them is handled last, so this
    exists for the case with none: photos were only deleted. Without it that work
    would run wherever the sync was started, which for a startup sync means
    walking the whole tree again before the server is reachable.
    """
    finalize_sync_run_by_id(sync_run_id=sync_run_id)
    return f"Finalized sync run {sync_run_id}"


@shared_task(name="domain.generate_thumbnail", bind=True, queue=settings.PROCESS_IMAGE_QUEUE)
def generate_thumbnail_task(self: Any, /, *, filepath: str, width: int, **kwargs: object) -> str:
    """
    Celery task that generates a thumbnail for a single image file.
    """
    thumbnail_operations.generate_thumbnail(original_path=Path(filepath), width=width)
    return f"Generated thumbnail for {Path(filepath).name}"
