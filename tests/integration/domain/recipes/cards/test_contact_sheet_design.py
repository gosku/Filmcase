from pathlib import Path

import pytest
from PIL import Image as PILImage

from src.domain.recipes.cards import queries as card_queries
from src.domain.recipes.cards.designs import contact_sheet
from tests.factories import FujifilmRecipeFactory


def _photo(tmp_path: Path) -> object:
    path = tmp_path / "photo.jpg"
    PILImage.new("RGB", (900, 600), (120, 60, 40)).save(str(path), format="JPEG")

    class _Image:
        filepath = str(path)

    return _Image()


class TestContactSheetDesignMetadata:
    def test_template_name(self) -> None:
        assert contact_sheet.ContactSheetDesign().template_name == "contact_sheet"

    def test_output_size_is_portrait(self) -> None:
        assert contact_sheet.ContactSheetDesign().output_size == (1080, 1920)

    def test_requires_a_background_image(self) -> None:
        assert contact_sheet.ContactSheetDesign().requires_background_image is True


@pytest.mark.django_db
class TestContactSheetDesignRender:
    def test_renders_portrait_rgb_canvas(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Classic Chrome")

        rendered = contact_sheet.ContactSheetDesign().render(recipe=recipe, background_image=_photo(tmp_path))

        assert rendered.canvas.size == (1080, 1920)
        assert rendered.canvas.mode == "RGB"

    def test_qr_round_trips(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Velvia")

        rendered = contact_sheet.ContactSheetDesign().render(recipe=recipe, background_image=_photo(tmp_path))
        out = tmp_path / "card.jpg"
        rendered.canvas.save(str(out), format="JPEG", quality=92)

        decoded = card_queries.get_qr_recipe_from_image(image_path=str(out))
        assert decoded.film_simulation == "Velvia"

    def test_rows_lead_with_the_shared_summary_fields(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Classic Chrome")

        rows = contact_sheet.ContactSheetDesign()._rows(recipe)

        assert [label for label, _ in rows[:4]] == [
            "Film Simulation",
            "Sensors",
            "White Balance",
            "WB Shift",
        ]

    def test_bw_rows_include_tone_fields_and_omit_color(self, tmp_path: Path) -> None:
        from decimal import Decimal
        recipe = FujifilmRecipeFactory(
            film_simulation="Acros Yellow",
            monochromatic_color_warm_cool=Decimal("0"),
            monochromatic_color_magenta_green=Decimal("0"),
        )

        labels = [label for label, _ in contact_sheet.ContactSheetDesign()._rows(recipe)]

        assert "BW Warm/Cool" in labels
        assert "Color" not in labels

    def test_falls_back_to_gradient_without_photo(self) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Classic Chrome")

        rendered = contact_sheet.ContactSheetDesign().render(recipe=recipe, background_image=None)

        assert rendered.canvas.size == (1080, 1920)
        assert rendered.embed_exif is True
