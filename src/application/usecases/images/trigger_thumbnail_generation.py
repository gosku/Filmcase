import attrs

from django.conf import settings

from src.application.usecases.images.generate_thumbnails import generate_thumbnails_for_all_images
from src.domain.settings import queries as settings_queries
from src.services import background, workertasks


@attrs.frozen
class CeleryWorkerUnavailable(Exception):
    """
    Raised when USE_ASYNC_TASKS is True but no Celery worker is reachable.
    """


@attrs.frozen
class ThumbnailRunSummary:
    """
    Outcome of triggering a whole-collection thumbnail run from a web request.

    ``ran_in_background`` is True in sync mode, where the run is handed to a
    background thread and the counts are therefore not known when the request
    returns. In async mode it is False and the counts are populated: ``enqueued``
    is how many thumbnails were queued for generation and ``already_cached`` how
    many were skipped because a cache file already exists, summed across widths.
    """

    ran_in_background: bool
    enqueued: int
    already_cached: int


def _generate_for_all_widths() -> None:
    for width in settings_queries.get_thumbnail_widths():
        generate_thumbnails_for_all_images(width=width)


def trigger_thumbnail_generation() -> ThumbnailRunSummary:
    """
    Pre-generate thumbnails for the whole collection at every configured width.

    Fire-and-forget: the disk cache is the single source of truth, so a repeat
    run simply skips everything already cached and nothing is tracked per
    thumbnail.

    In async mode the worker is checked before any work is queued, so nothing is
    enqueued when nothing can process it, and the returned summary carries the
    per-width counts. In sync mode the run is handed to a background thread so the
    request never blocks on the whole library, and the summary reports only that
    the run started.

    :raises CeleryWorkerUnavailable: If USE_ASYNC_TASKS is True and no Celery
        worker responds; no thumbnails are enqueued in that case.
    """
    if settings.USE_ASYNC_TASKS:
        if not workertasks.is_celery_worker_available():
            raise CeleryWorkerUnavailable()

        enqueued = already_cached = 0
        for width in settings_queries.get_thumbnail_widths():
            result = generate_thumbnails_for_all_images(width=width)
            enqueued += result.enqueued
            already_cached += result.already_cached
        return ThumbnailRunSummary(
            ran_in_background=False,
            enqueued=enqueued,
            already_cached=already_cached,
        )

    background.run_in_background(_generate_for_all_widths)
    return ThumbnailRunSummary(ran_in_background=True, enqueued=0, already_cached=0)
