from pathlib import Path

import pytest
from PIL import Image as PILImage

from src.domain.recipes.cards import operations as card_operations
from src.domain.recipes.cards import templates as card_templates
from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestPreviewRecipeCardImage:
    def test_returns_the_output_path(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        output_path = tmp_path / "preview.jpg"
        result = card_operations.preview_recipe_card_image(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_path=output_path,
        )
        assert result == output_path

    def test_creates_jpeg_at_specified_path(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        output_path = tmp_path / "preview.jpg"
        card_operations.preview_recipe_card_image(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_path=output_path,
        )
        assert output_path.exists()

    def test_jpeg_has_correct_dimensions(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        output_path = tmp_path / "preview.jpg"
        card_operations.preview_recipe_card_image(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_path=output_path,
        )
        with PILImage.open(output_path) as img:
            assert img.size == card_templates.LONG_LABEL.output_size

    def test_successive_calls_overwrite_the_same_file(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        output_path = tmp_path / "preview.jpg"
        card_operations.preview_recipe_card_image(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_path=output_path,
        )
        card_operations.preview_recipe_card_image(
            recipe=recipe,
            template=card_templates.SHORT_LABEL,
            background_image=None,
            output_path=output_path,
        )
        assert output_path.exists()
        assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.django_db
class TestCreateRecipeCardImage:
    def test_returns_path_inside_output_dir(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        filepath = card_operations.create_recipe_card_image(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        assert filepath.parent == tmp_path

    def test_creates_jpeg_file(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        filepath = card_operations.create_recipe_card_image(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        assert filepath.exists()

    def test_jpeg_has_correct_dimensions(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        filepath = card_operations.create_recipe_card_image(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        with PILImage.open(filepath) as img:
            assert img.size == card_templates.LONG_LABEL.output_size

    def test_gradient_card_embeds_recipe_json_in_exif(self, tmp_path: Path) -> None:
        import piexif
        recipe = FujifilmRecipeFactory()
        filepath = card_operations.create_recipe_card_image(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        exif_data = piexif.load(str(filepath))
        user_comment = exif_data["Exif"].get(piexif.ExifIFD.UserComment, b"")
        assert b"film_simulation" in user_comment

    def test_each_call_produces_unique_filepath(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        filepath1 = card_operations.create_recipe_card_image(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        filepath2 = card_operations.create_recipe_card_image(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        assert filepath1 != filepath2
