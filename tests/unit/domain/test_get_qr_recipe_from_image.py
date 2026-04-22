import json
from pathlib import Path

import pytest
import qrcode  # type: ignore[import-untyped]

from src.domain.recipes.cards import dataclasses as card_dataclasses
from src.domain.recipes.cards import queries as card_queries

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "recipe_cards"
NON_CARD_IMAGE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "images" / "XS107114.JPG"


def _valid_payload() -> dict[str, object]:
    """A minimal valid QR payload: only the required fields."""
    return {
        "v": 1,
        "film_simulation": "Provia",
        "grain_roughness": "Off",
        "d_range_priority": "Off",
        "white_balance": "Auto",
        "white_balance_red": 0,
        "white_balance_blue": 0,
    }


def _write_qr(tmp_path: Path, payload_str: str, *, filename: str = "qr.png") -> str:
    # box_size=10 keeps the QR large enough for cv2.QRCodeDetector even before
    # the detector's crop+upscale fallback kicks in.
    img = qrcode.make(payload_str, box_size=10)
    path = tmp_path / filename
    img.save(path)
    return str(path)


class TestGetQRRecipeFromImage:
    def test_decodes_colour_card_fixture(self) -> None:
        path = str(FIXTURES_DIR / "card_classic_chrome.jpg")

        result = card_queries.get_qr_recipe_from_image(image_path=path)

        assert isinstance(result, card_dataclasses.QRFujifilmRecipe)
        assert result.v == 1
        assert result.film_simulation == "Classic Chrome"
        assert result.white_balance == "Daylight"
        assert result.white_balance_red == 2
        assert result.white_balance_blue == -1
        assert result.color_chrome_effect == "Strong"
        assert result.color == 0
        assert result.grain_size == "Small"
        # Monochrome fields are omitted for a colour film simulation.
        assert result.monochromatic_color_warm_cool is None
        assert result.monochromatic_color_magenta_green is None

    def test_decodes_monochromatic_card_fixture(self) -> None:
        path = str(FIXTURES_DIR / "card_acros.jpg")

        result = card_queries.get_qr_recipe_from_image(image_path=path)

        assert isinstance(result, card_dataclasses.QRFujifilmRecipe)
        assert result.film_simulation == "Acros STD"
        assert result.grain_roughness == "Off"
        # grain_size is omitted when grain_roughness == "Off".
        assert result.grain_size is None
        # Colour fields are omitted for a monochromatic film simulation.
        assert result.color is None
        assert result.color_chrome_effect is None
        assert result.color_chrome_fx_blue is None
        assert result.monochromatic_color_warm_cool == -2
        assert result.monochromatic_color_magenta_green == 1.5

    def test_parses_name_when_payload_includes_it(self, tmp_path: Path) -> None:
        payload = _valid_payload()
        payload["name"] = "My Summer Recipe"
        path = _write_qr(tmp_path, json.dumps(payload))

        result = card_queries.get_qr_recipe_from_image(image_path=path)

        assert result.name == "My Summer Recipe"

    def test_leaves_name_as_none_when_payload_omits_it(self, tmp_path: Path) -> None:
        path = _write_qr(tmp_path, json.dumps(_valid_payload()))

        result = card_queries.get_qr_recipe_from_image(image_path=path)

        assert result.name is None

    def test_raises_qr_not_found_for_missing_file(self) -> None:
        with pytest.raises(card_queries.QRCodeNotFoundError) as exc_info:
            card_queries.get_qr_recipe_from_image(image_path="/tmp/does_not_exist_abc123.jpg")
        assert exc_info.value.image_path == "/tmp/does_not_exist_abc123.jpg"

    def test_raises_qr_not_found_for_image_without_qr(self) -> None:
        path = str(NON_CARD_IMAGE)

        with pytest.raises(card_queries.QRCodeNotFoundError):
            card_queries.get_qr_recipe_from_image(image_path=path)

    def test_raises_invalid_json_when_qr_contains_non_json_text(self, tmp_path: Path) -> None:
        path = _write_qr(tmp_path, "hello world, not json")

        with pytest.raises(card_queries.InvalidQRRecipePayloadError) as exc_info:
            card_queries.get_qr_recipe_from_image(image_path=path)
        assert exc_info.value.reason == "invalid_json"

    def test_raises_invalid_json_when_qr_content_is_not_an_object(self, tmp_path: Path) -> None:
        path = _write_qr(tmp_path, json.dumps([1, 2, 3]))

        with pytest.raises(card_queries.InvalidQRRecipePayloadError) as exc_info:
            card_queries.get_qr_recipe_from_image(image_path=path)
        assert exc_info.value.reason == "invalid_json"

    def test_raises_unsupported_version_when_v_is_missing(self, tmp_path: Path) -> None:
        payload = _valid_payload()
        del payload["v"]
        path = _write_qr(tmp_path, json.dumps(payload))

        with pytest.raises(card_queries.InvalidQRRecipePayloadError) as exc_info:
            card_queries.get_qr_recipe_from_image(image_path=path)
        assert exc_info.value.reason == "unsupported_version"

    def test_raises_unsupported_version_when_v_is_not_one(self, tmp_path: Path) -> None:
        payload = _valid_payload()
        payload["v"] = 2
        path = _write_qr(tmp_path, json.dumps(payload))

        with pytest.raises(card_queries.InvalidQRRecipePayloadError) as exc_info:
            card_queries.get_qr_recipe_from_image(image_path=path)
        assert exc_info.value.reason == "unsupported_version"

    def test_raises_unknown_fields_when_payload_has_unexpected_key(self, tmp_path: Path) -> None:
        payload = _valid_payload()
        payload["bogus_key"] = "anything"
        path = _write_qr(tmp_path, json.dumps(payload))

        with pytest.raises(card_queries.InvalidQRRecipePayloadError) as exc_info:
            card_queries.get_qr_recipe_from_image(image_path=path)
        assert exc_info.value.reason == "unknown_fields"

    def test_raises_type_mismatch_when_int_field_has_string_value(self, tmp_path: Path) -> None:
        payload = _valid_payload()
        payload["white_balance_red"] = "not-an-int"
        path = _write_qr(tmp_path, json.dumps(payload))

        with pytest.raises(card_queries.InvalidQRRecipePayloadError) as exc_info:
            card_queries.get_qr_recipe_from_image(image_path=path)
        assert exc_info.value.reason == "type_mismatch"

    def test_raises_type_mismatch_when_required_field_is_missing(self, tmp_path: Path) -> None:
        payload = _valid_payload()
        del payload["film_simulation"]
        path = _write_qr(tmp_path, json.dumps(payload))

        with pytest.raises(card_queries.InvalidQRRecipePayloadError) as exc_info:
            card_queries.get_qr_recipe_from_image(image_path=path)
        assert exc_info.value.reason == "type_mismatch"
