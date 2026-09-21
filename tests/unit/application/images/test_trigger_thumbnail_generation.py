from unittest.mock import patch

import pytest
from django.test import override_settings

from src.application.usecases.images import trigger_thumbnail_generation as uc
from src.application.usecases.images.generate_thumbnails import ThumbnailGenerationResult

_WORKER = "src.application.usecases.images.trigger_thumbnail_generation.workertasks.is_celery_worker_available"
_GENERATE = "src.application.usecases.images.trigger_thumbnail_generation.generate_thumbnails_for_all_images"
_WIDTHS = "src.application.usecases.images.trigger_thumbnail_generation.settings_queries.get_thumbnail_widths"
_BACKGROUND = "src.application.usecases.images.trigger_thumbnail_generation.background.run_in_background"


class TestTriggerThumbnailGeneration:
    @override_settings(USE_ASYNC_TASKS=True)
    def test_raises_when_no_worker_is_available_in_async_mode(self) -> None:
        with patch(_WORKER, return_value=False), patch(_GENERATE) as mock_generate:
            with pytest.raises(uc.CeleryWorkerUnavailable):
                uc.trigger_thumbnail_generation()

        mock_generate.assert_not_called()

    @override_settings(USE_ASYNC_TASKS=True)
    def test_aggregates_counts_across_widths_in_async_mode(self) -> None:
        results = [
            ThumbnailGenerationResult(enqueued=3, already_cached=1, missing_paths=()),
            ThumbnailGenerationResult(enqueued=2, already_cached=4, missing_paths=()),
        ]

        with (
            patch(_WORKER, return_value=True),
            patch(_WIDTHS, return_value=(600, 1200)),
            patch(_GENERATE, side_effect=results) as mock_generate,
        ):
            summary = uc.trigger_thumbnail_generation()

        assert mock_generate.call_count == 2
        assert summary.ran_in_background is False
        assert summary.enqueued == 5
        assert summary.already_cached == 5

    @override_settings(USE_ASYNC_TASKS=False)
    def test_hands_the_run_to_a_background_thread_in_sync_mode(self) -> None:
        with patch(_BACKGROUND) as mock_background, patch(_GENERATE) as mock_generate:
            summary = uc.trigger_thumbnail_generation()

        mock_background.assert_called_once_with(uc._generate_for_all_widths)
        mock_generate.assert_not_called()
        assert summary.ran_in_background is True
        assert summary.enqueued == 0
        assert summary.already_cached == 0
