from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import override_settings

from src.application.usecases.images import trigger_thumbnail_generation as uc
from src.domain.images.thumbnails.queries import thumbnail_cache_path
from tests.factories import ImageFactory

FIXTURE_IMAGE = Path(__file__).resolve().parents[3] / "fixtures" / "images" / "XS107114.JPG"
THUMBNAIL_WIDTH = 600

_WORKER = "src.application.usecases.images.trigger_thumbnail_generation.workertasks.is_celery_worker_available"
_BACKGROUND = "src.application.usecases.images.trigger_thumbnail_generation.background.run_in_background"


def _run_inline(func: Callable[..., object], /, **kwargs: object) -> None:
    func(**kwargs)


@pytest.mark.django_db
class TestTriggerThumbnailGeneration:
    @override_settings(USE_ASYNC_TASKS=True)
    def test_enqueues_and_reports_counts_in_async_mode(self, tmp_path) -> None:
        ImageFactory(filename="XS107114.JPG", filepath=str(FIXTURE_IMAGE))

        with patch(_WORKER, return_value=True), override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            summary = uc.trigger_thumbnail_generation()

        assert summary.ran_in_background is False
        assert summary.enqueued == 1
        assert summary.already_cached == 0

    @override_settings(USE_ASYNC_TASKS=False)
    def test_generates_cache_files_in_sync_mode(self, tmp_path) -> None:
        ImageFactory(filename="XS107114.JPG", filepath=str(FIXTURE_IMAGE))

        # Run the handed-off work inline so the assertion is deterministic rather
        # than racing a daemon thread.
        with patch(_BACKGROUND, side_effect=_run_inline), override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            summary = uc.trigger_thumbnail_generation()
            expected = thumbnail_cache_path(original_path=FIXTURE_IMAGE, width=THUMBNAIL_WIDTH)

        assert summary.ran_in_background is True
        assert expected.is_file()
