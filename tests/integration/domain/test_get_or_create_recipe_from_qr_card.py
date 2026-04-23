import json
from pathlib import Path

import pytest
import qrcode  # type: ignore[import-untyped]

from src.data import models
from src.domain.images import events
from src.domain.recipes import operations as recipe_operations
from src.domain.recipes.cards import queries as card_queries

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "recipe_cards"
CLASSIC_CHROME_CARD = str(FIXTURES_DIR / "card_classic_chrome.jpg")
ACROS_CARD = str(FIXTURES_DIR / "card_acros.jpg")
NON_CARD_IMAGE = str(
    Path(__file__).resolve().parent.parent.parent / "fixtures" / "images" / "XS107114.JPG"
)


def _write_qr(tmp_path: Path, payload_str: str) -> str:
    img = qrcode.make(payload_str, box_size=10)
    path = tmp_path / "qr.png"
    img.save(path)
    return str(path)


@pytest.mark.django_db
class TestGetOrCreateRecipeFromQRCard:
    def test_creates_recipe_from_colour_card_fixture(self) -> None:
        recipe = recipe_operations.get_or_create_recipe_from_qr_card(filepath=CLASSIC_CHROME_CARD)

        assert isinstance(recipe, models.FujifilmRecipe)
        assert recipe.pk is not None
        assert recipe.film_simulation == "Classic Chrome"
        assert recipe.white_balance == "Daylight"
        assert recipe.white_balance_red == 2
        assert recipe.white_balance_blue == -1
        assert recipe.color_chrome_effect == "Strong"

    def test_creates_recipe_from_monochromatic_card_fixture(self) -> None:
        recipe = recipe_operations.get_or_create_recipe_from_qr_card(filepath=ACROS_CARD)

        assert recipe.film_simulation == "Acros STD"
        # grain_size falls back to "Off" when grain_roughness is "Off" and the
        # payload omits it.
        assert recipe.grain_roughness == "Off"
        assert recipe.grain_size == "Off"
        # Colour-only fields default to "" when the payload omits them.
        assert recipe.color_chrome_effect == ""
        assert recipe.color is None
        # Monochrome fields round-trip back to Decimal.
        assert recipe.monochromatic_color_warm_cool is not None
        assert float(recipe.monochromatic_color_warm_cool) == -2.0

    def test_publishes_recipe_created_event_on_first_import(self, captured_logs) -> None:
        recipe = recipe_operations.get_or_create_recipe_from_qr_card(filepath=CLASSIC_CHROME_CARD)

        created_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CREATED]
        assert len(created_events) == 1
        assert created_events[0]["recipe_id"] == recipe.pk
        assert created_events[0]["film_simulation"] == "Classic Chrome"

    def test_returns_existing_recipe_on_reimport(self, captured_logs) -> None:
        first = recipe_operations.get_or_create_recipe_from_qr_card(filepath=CLASSIC_CHROME_CARD)
        captured_logs.clear()

        second = recipe_operations.get_or_create_recipe_from_qr_card(filepath=CLASSIC_CHROME_CARD)

        assert second.pk == first.pk
        assert models.FujifilmRecipe.objects.count() == 1
        # Dedup path must not re-publish RECIPE_CREATED.
        created_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CREATED]
        assert created_events == []

    def test_saves_name_from_payload_on_first_create(self, tmp_path: Path) -> None:
        payload = {
            "v": 1,
            "name": "Shared Recipe",
            "film_simulation": "Provia",
            "grain_roughness": "Off",
            "d_range_priority": "Off",
            "white_balance": "Auto",
            "white_balance_red": 3,
            "white_balance_blue": 3,
        }
        card = _write_qr(tmp_path, json.dumps(payload))

        recipe = recipe_operations.get_or_create_recipe_from_qr_card(filepath=card)

        assert recipe.name == "Shared Recipe"

    def test_preserves_existing_name_on_dedup(self, tmp_path: Path) -> None:
        # Base payload has no name; the existing recipe will be created nameless.
        base_payload = {
            "v": 1,
            "film_simulation": "Provia",
            "grain_roughness": "Off",
            "d_range_priority": "Off",
            "white_balance": "Auto",
            "white_balance_red": 4,
            "white_balance_blue": 4,
        }
        first = recipe_operations.get_or_create_recipe_from_qr_card(
            filepath=_write_qr(tmp_path, json.dumps(base_payload)),
        )
        first.name = "Locally Named"
        first.save(update_fields=["name"])

        # A second import with the same settings but a different name in the
        # payload must not overwrite the existing name — uniqueness is
        # settings-only, and the existing name wins on dedup.
        second = recipe_operations.get_or_create_recipe_from_qr_card(
            filepath=_write_qr(tmp_path, json.dumps({**base_payload, "name": "Remote Name"})),
        )

        assert second.pk == first.pk
        second.refresh_from_db()
        assert second.name == "Locally Named"

    def test_raises_qr_not_found_for_image_without_qr(self) -> None:
        with pytest.raises(card_queries.QRCodeNotFoundError):
            recipe_operations.get_or_create_recipe_from_qr_card(filepath=NON_CARD_IMAGE)

    def test_raises_invalid_payload_for_bad_qr_content(self, tmp_path: Path) -> None:
        # A QR that decodes but doesn't carry a valid recipe payload.
        bad_qr = _write_qr(tmp_path, json.dumps({"v": 1, "wrong_key": "wrong"}))

        with pytest.raises(card_queries.InvalidQRRecipePayloadError):
            recipe_operations.get_or_create_recipe_from_qr_card(filepath=bad_qr)
