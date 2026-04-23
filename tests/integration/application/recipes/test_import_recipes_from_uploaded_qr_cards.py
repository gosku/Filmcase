import json
from pathlib import Path

import pytest
import qrcode  # type: ignore[import-untyped]

from src.application.usecases.recipes.import_recipes_from_uploaded_qr_cards import (
    import_recipes_from_uploaded_qr_cards,
)
from src.data import models
from src.domain.images import events
from src.domain.recipes.dataclasses import ImportRecipesResult, UploadedFile

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "recipe_cards"
NON_CARD_IMAGE_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "images"
)


def uploaded_file_from_fixture(filename: str, *, fixtures_dir: Path = FIXTURES_DIR) -> UploadedFile:
    path = fixtures_dir / filename
    return UploadedFile(name=filename, content=path.read_bytes())


def _qr_file(tmp_path: Path, payload_str: str, *, filename: str = "qr.png") -> UploadedFile:
    img = qrcode.make(payload_str, box_size=10)
    img_path = tmp_path / filename
    img.save(img_path)
    return UploadedFile(name=filename, content=img_path.read_bytes())


@pytest.mark.django_db
class TestImportRecipesFromUploadedQRCards:
    def test_imports_recipe_from_single_card(self) -> None:
        files = [uploaded_file_from_fixture("card_classic_chrome.jpg")]

        result = import_recipes_from_uploaded_qr_cards(files=files)

        assert len(result.imported) == 1
        assert isinstance(result.imported[0], models.FujifilmRecipe)
        assert result.imported[0].film_simulation == "Classic Chrome"
        assert result.failed == ()

    def test_imports_recipes_from_multiple_cards(self) -> None:
        files = [
            uploaded_file_from_fixture("card_classic_chrome.jpg"),
            uploaded_file_from_fixture("card_acros.jpg"),
        ]

        result = import_recipes_from_uploaded_qr_cards(files=files)

        assert len(result.imported) == 2
        assert {r.film_simulation for r in result.imported} == {"Classic Chrome", "Acros STD"}
        assert result.failed == ()

    def test_deduplicates_identical_cards(self) -> None:
        files = [
            uploaded_file_from_fixture("card_classic_chrome.jpg"),
            uploaded_file_from_fixture("card_classic_chrome.jpg"),
        ]

        result = import_recipes_from_uploaded_qr_cards(files=files)

        assert len(result.imported) == 2
        assert result.imported[0].pk == result.imported[1].pk
        assert models.FujifilmRecipe.objects.count() == 1

    def test_records_failure_for_image_without_qr(self) -> None:
        non_card = uploaded_file_from_fixture("XS107114.JPG", fixtures_dir=NON_CARD_IMAGE_DIR)

        result = import_recipes_from_uploaded_qr_cards(files=[non_card])

        assert result.imported == ()
        assert result.failed == ("XS107114.JPG",)

    def test_publishes_qr_not_found_event_when_image_has_no_qr(self, captured_logs) -> None:
        non_card = uploaded_file_from_fixture("XS107114.JPG", fixtures_dir=NON_CARD_IMAGE_DIR)

        import_recipes_from_uploaded_qr_cards(files=[non_card])

        failure_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_IMPORT_QR_CARD_FAILED
        ]
        assert len(failure_events) == 1
        assert failure_events[0]["filename"] == "XS107114.JPG"
        assert failure_events[0]["failure_reason"] == "qr_not_found"

    def test_records_failure_for_invalid_qr_payload(self, tmp_path: Path) -> None:
        bad = _qr_file(tmp_path, json.dumps({"v": 1, "wrong_key": "wrong"}), filename="bad.png")

        result = import_recipes_from_uploaded_qr_cards(files=[bad])

        assert result.imported == ()
        assert result.failed == ("bad.png",)

    def test_publishes_invalid_payload_event_with_reason(self, tmp_path: Path, captured_logs) -> None:
        bad = _qr_file(tmp_path, json.dumps({"v": 2}), filename="old_schema.png")

        import_recipes_from_uploaded_qr_cards(files=[bad])

        failure_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_IMPORT_QR_CARD_FAILED
        ]
        assert len(failure_events) == 1
        assert failure_events[0]["filename"] == "old_schema.png"
        assert failure_events[0]["failure_reason"] == "unsupported_version"

    def test_continues_after_failure_and_processes_remaining_files(self) -> None:
        non_card = uploaded_file_from_fixture("XS107114.JPG", fixtures_dir=NON_CARD_IMAGE_DIR)
        card = uploaded_file_from_fixture("card_classic_chrome.jpg")

        result = import_recipes_from_uploaded_qr_cards(files=[non_card, card])

        assert len(result.imported) == 1
        assert result.failed == ("XS107114.JPG",)

    def test_temp_file_is_deleted_after_success(self, monkeypatch) -> None:
        created_paths: list[str] = []

        original_unlink = __import__("os").unlink

        def tracking_unlink(path: str) -> None:
            created_paths.append(path)
            original_unlink(path)

        monkeypatch.setattr(
            "src.application.usecases.recipes.import_recipes_from_uploaded_qr_cards.os.unlink",
            tracking_unlink,
        )

        files = [uploaded_file_from_fixture("card_classic_chrome.jpg")]
        import_recipes_from_uploaded_qr_cards(files=files)

        assert len(created_paths) == 1
        assert not Path(created_paths[0]).exists()

    def test_temp_file_is_deleted_after_failure(self, monkeypatch) -> None:
        created_paths: list[str] = []

        original_unlink = __import__("os").unlink

        def tracking_unlink(path: str) -> None:
            created_paths.append(path)
            original_unlink(path)

        monkeypatch.setattr(
            "src.application.usecases.recipes.import_recipes_from_uploaded_qr_cards.os.unlink",
            tracking_unlink,
        )

        files = [UploadedFile(name="bad.jpg", content=b"\xff\xd8\xff\xd9")]
        import_recipes_from_uploaded_qr_cards(files=files)

        assert len(created_paths) == 1
        assert not Path(created_paths[0]).exists()

    def test_empty_file_list_returns_empty_result(self) -> None:
        result = import_recipes_from_uploaded_qr_cards(files=[])

        assert result == ImportRecipesResult(imported=(), failed=())
