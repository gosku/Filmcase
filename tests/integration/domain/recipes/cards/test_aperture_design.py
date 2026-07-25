from pathlib import Path

import pytest
from PIL import Image as PILImage
from PIL import ImageStat

from src.domain.recipes.cards import queries as card_queries
from src.domain.recipes.cards.designs import aperture
from tests.factories import FujifilmRecipeFactory


def _photo(tmp_path: Path) -> str:
    # A plain on-disk photo path the design can open as the hero / blurred background.
    path = tmp_path / "photo.jpg"
    PILImage.new("RGB", (900, 600), (120, 60, 40)).save(str(path), format="JPEG")
    return str(path)


class TestApertureDesignMetadata:
    def test_template_name(self) -> None:
        assert aperture.ApertureDesign().template_name == "aperture"

    def test_output_size_is_portrait(self) -> None:
        assert aperture.ApertureDesign().output_size == (1080, 1920)

    def test_requires_a_background_image(self) -> None:
        assert aperture.ApertureDesign().requires_background_image is True


@pytest.mark.django_db
class TestApertureDesignRender:
    def test_renders_portrait_rgb_jpeg_canvas(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory(name="Portra", film_simulation="Classic Chrome")

        rendered = aperture.ApertureDesign().render(recipe=recipe, background_photo_path=_photo(tmp_path))

        assert rendered.canvas.size == (1080, 1920)
        assert rendered.canvas.mode == "RGB"

    def test_qr_round_trips(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Classic Chrome")

        rendered = aperture.ApertureDesign().render(recipe=recipe, background_photo_path=_photo(tmp_path))
        out = tmp_path / "card.jpg"
        rendered.canvas.save(str(out), format="JPEG", quality=92)

        decoded = card_queries.get_qr_recipe_from_image(image_path=str(out))
        assert decoded.film_simulation == "Classic Chrome"

    def test_eyebrow_marks_bw_recipe(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Acros Yellow")

        assert "B&W" in aperture.ApertureDesign()._eyebrow_text(recipe)

    def test_falls_back_to_gradient_without_photo(self) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Classic Chrome")

        rendered = aperture.ApertureDesign().render(recipe=recipe, background_photo_path=None)

        assert rendered.canvas.size == (1080, 1920)
        assert rendered.embed_exif is True

    def test_bottom_scrim_opacity_is_configurable(self, tmp_path: Path, settings: object) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Classic Chrome")
        photo = _photo(tmp_path)
        # A bottom-corner strip shows the background scrim directly (no panels).
        corner = (0, 1800, 90, 1880)

        settings.RECIPE_CARD_APERTURE_SCRIM_BOTTOM_OPACITY = 80  # type: ignore[attr-defined]
        dark = aperture.ApertureDesign().render(recipe=recipe, background_photo_path=photo).canvas.crop(corner)
        settings.RECIPE_CARD_APERTURE_SCRIM_BOTTOM_OPACITY = 10  # type: ignore[attr-defined]
        light = aperture.ApertureDesign().render(recipe=recipe, background_photo_path=photo).canvas.crop(corner)

        dark_brightness = ImageStat.Stat(dark.convert("L")).mean[0]
        light_brightness = ImageStat.Stat(light.convert("L")).mean[0]
        assert light_brightness > dark_brightness
