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
        # v=99 is outside the accepted set ({1, 2}) so the decoder reports
        # unsupported_version. The exact version is incidental -- we're
        # asserting the failure path publishes the reason verbatim.
        bad = _qr_file(tmp_path, json.dumps({"v": 99}), filename="unknown_schema.png")

        import_recipes_from_uploaded_qr_cards(files=[bad])

        failure_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_IMPORT_QR_CARD_FAILED
        ]
        assert len(failure_events) == 1
        assert failure_events[0]["filename"] == "unknown_schema.png"
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


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "v": 1,
        "film_simulation": "Provia",
        "grain_roughness": "Off",
        "d_range_priority": "Off",
        "white_balance": "Auto",
        "white_balance_red": 0,
        "white_balance_blue": 0,
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestImportRecipesFromUploadedQRCardsOutcomes:
    """
    Importing a card does not necessarily create a recipe: its settings may
    already match one. The result says which happened, so a bulk import can
    report what it did to the library.
    """

    def test_reports_a_new_recipe_as_created(self, tmp_path: Path) -> None:
        card = _qr_file(tmp_path, json.dumps(_payload(name="Kodachrome")), filename="card.png")

        result = import_recipes_from_uploaded_qr_cards(files=[card])

        assert result.created == result.imported
        assert result.updated == ()

    def test_reports_a_card_that_names_an_existing_recipe_as_updated(self, tmp_path: Path) -> None:
        nameless = _qr_file(tmp_path, json.dumps(_payload()), filename="nameless.png")
        import_recipes_from_uploaded_qr_cards(files=[nameless])

        named = _qr_file(tmp_path, json.dumps(_payload(name="Kodachrome")), filename="named.png")
        result = import_recipes_from_uploaded_qr_cards(files=[named])

        assert result.created == ()
        assert len(result.updated) == 1
        assert result.updated[0].name == "Kodachrome"
        assert models.FujifilmRecipe.objects.count() == 1

    def test_reports_a_card_matching_a_named_recipe_as_neither(self, tmp_path: Path) -> None:
        card = _qr_file(tmp_path, json.dumps(_payload(name="Kodachrome")), filename="card.png")
        import_recipes_from_uploaded_qr_cards(files=[card])

        result = import_recipes_from_uploaded_qr_cards(files=[card])

        assert len(result.imported) == 1
        assert result.created == ()
        assert result.updated == ()

    def test_a_card_with_an_illegal_value_fails_alone(self, tmp_path: Path) -> None:
        # A card exported by a library that knows a sensor this one doesn't.
        # It must not take the rest of the batch down with it.
        unknown_sensor = _qr_file(
            tmp_path,
            json.dumps(_payload(v=2, sensors=["X-Trans VI"])),
            filename="future.png",
        )
        good = uploaded_file_from_fixture("card_classic_chrome.jpg")

        result = import_recipes_from_uploaded_qr_cards(files=[unknown_sensor, good])

        assert result.failed == ("future.png",)
        assert len(result.imported) == 1
        assert result.imported[0].film_simulation == "Classic Chrome"

    def test_publishes_the_invalid_value_reason_for_a_card_that_fails_alone(
        self, tmp_path: Path, captured_logs
    ) -> None:
        too_long = _qr_file(
            tmp_path, json.dumps(_payload(name="x" * 26)), filename="long_name.png"
        )

        import_recipes_from_uploaded_qr_cards(files=[too_long])

        failure_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_IMPORT_QR_CARD_FAILED
        ]
        assert len(failure_events) == 1
        assert failure_events[0]["failure_reason"] == "invalid_field_value"
