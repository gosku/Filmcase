from unittest.mock import patch

from django.test import override_settings

from src.application.usecases.images import process_images as uc
from src.domain.images import events
from src.domain.images.queries import NoFilmSimulationError
from src.domain.recipes.validation import InvalidFujifilmRecipeData

_COLLECT = "src.application.usecases.images.process_images.queries.collect_image_paths"
_PROCESS = "src.application.usecases.images.process_images.operations.process_image"


def _skip_events(captured_logs: list[dict[str, object]]) -> list[dict[str, object]]:
    return [e for e in captured_logs if e.get("event_type") == events.IMAGE_IMPORT_SKIPPED]


class TestProcessImagesInFolder:
    def test_continues_after_an_image_that_fails_recipe_validation(self) -> None:
        paths = ["a.jpg", "bad.jpg", "c.jpg"]
        side_effect = [None, InvalidFujifilmRecipeData("color", None), None]

        with patch(_COLLECT, return_value=paths):
            with patch(_PROCESS, side_effect=side_effect) as mock_process:
                summary = uc._process_images_in_folder(folder="/photos")

        assert mock_process.call_count == 3
        assert summary.processed == 2
        assert summary.skipped == ("bad.jpg",)

    def test_continues_after_an_image_with_no_film_simulation(self) -> None:
        paths = ["a.jpg", "canon.jpg", "c.jpg"]
        side_effect = [None, NoFilmSimulationError("canon.jpg"), None]

        with patch(_COLLECT, return_value=paths):
            with patch(_PROCESS, side_effect=side_effect) as mock_process:
                summary = uc._process_images_in_folder(folder="/photos")

        assert mock_process.call_count == 3
        assert summary.processed == 2
        assert summary.skipped == ("canon.jpg",)

    def test_reports_processed_and_skipped_counts(self) -> None:
        paths = ["a.jpg", "canon.jpg", "bad.jpg"]
        side_effect = [
            None,
            NoFilmSimulationError("canon.jpg"),
            InvalidFujifilmRecipeData("color", None),
        ]

        with patch(_COLLECT, return_value=paths):
            with patch(_PROCESS, side_effect=side_effect):
                summary = uc._process_images_in_folder(folder="/photos")

        assert summary.total == 3
        assert summary.processed == 1
        assert summary.skipped == ("canon.jpg", "bad.jpg")

    def test_publishes_an_import_skipped_event_per_skipped_image(self, captured_logs) -> None:
        paths = ["canon.jpg", "bad.jpg"]
        side_effect = [
            NoFilmSimulationError("canon.jpg"),
            InvalidFujifilmRecipeData("color", None),
        ]

        with patch(_COLLECT, return_value=paths):
            with patch(_PROCESS, side_effect=side_effect):
                uc._process_images_in_folder(folder="/photos")

        skipped = _skip_events(captured_logs)
        assert len(skipped) == 2
        assert skipped[0]["image_path"] == "canon.jpg"
        assert skipped[0]["reason"] == events.SKIP_REASON_NO_FILM_SIMULATION
        assert skipped[1]["image_path"] == "bad.jpg"
        assert skipped[1]["reason"] == events.SKIP_REASON_INVALID_RECIPE_DATA
        assert skipped[1]["recipe_field"] == "color"

    def test_publishes_no_event_when_every_image_is_processed(self, captured_logs) -> None:
        with patch(_COLLECT, return_value=["a.jpg", "b.jpg"]):
            with patch(_PROCESS, return_value=None):
                summary = uc._process_images_in_folder(folder="/photos")

        assert summary.skipped == ()
        assert _skip_events(captured_logs) == []


class TestImportImagesFromFolder:
    def test_reports_only_the_enqueued_total_in_async_mode(self) -> None:
        with override_settings(USE_ASYNC_TASKS=True):
            with patch(_COLLECT, return_value=["a.jpg", "b.jpg"]):
                with patch("src.application.usecases.images.process_images.workertasks.enqueue_task"):
                    summary = uc.import_images_from_folder(folder="/photos")

        assert summary.total == 2
        assert summary.processed == 0
        assert summary.skipped == ()

    def test_reports_per_file_outcomes_in_sync_mode(self) -> None:
        side_effect = [None, InvalidFujifilmRecipeData("color", None)]

        with override_settings(USE_ASYNC_TASKS=False):
            with patch(_COLLECT, return_value=["a.jpg", "bad.jpg"]):
                with patch(_PROCESS, side_effect=side_effect):
                    summary = uc.import_images_from_folder(folder="/photos")

        assert summary.total == 2
        assert summary.processed == 1
        assert summary.skipped == ("bad.jpg",)
