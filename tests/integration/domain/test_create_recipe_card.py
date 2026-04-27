from pathlib import Path

import pytest
from PIL import Image as PILImage

from src.domain.images import events
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


@pytest.mark.django_db
class TestCreateRecipeCard:
    def test_creates_recipe_card_record_in_db(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        card = card_operations.create_recipe_card(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        assert card.pk is not None
        assert card.recipe_id == recipe.pk

    def test_card_filepath_points_to_existing_file(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        card = card_operations.create_recipe_card(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        assert Path(card.filepath).exists()

    def test_no_background_image_sets_null_image_fk(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        card = card_operations.create_recipe_card(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        assert card.image_id is None

    def test_stores_template_name_on_card(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        card = card_operations.create_recipe_card(
            recipe=recipe,
            template=card_templates.SHORT_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        assert card.template == "short_label"


@pytest.mark.django_db
class TestCreateRecipeCardEventPublishing:
    def test_publishes_recipe_card_created_event(
        self, tmp_path: Path, captured_logs: list[dict]
    ) -> None:
        recipe = FujifilmRecipeFactory()
        card = card_operations.create_recipe_card(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        card_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_CARD_CREATED
        ]
        assert len(card_events) == 1
        assert card_events[0]["recipe_id"] == recipe.pk
        assert card_events[0]["card_id"] == card.pk

    def test_event_contains_template_name(
        self, tmp_path: Path, captured_logs: list[dict]
    ) -> None:
        recipe = FujifilmRecipeFactory()
        card_operations.create_recipe_card(
            recipe=recipe,
            template=card_templates.SHORT_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        card_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_CARD_CREATED
        ]
        assert card_events[0]["template"] == "short_label"


@pytest.mark.django_db
class TestRecipeCardLogo:
    def test_logo_white_background_appears_bottom_left(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        filepath = card_operations.create_recipe_card_image(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )
        with PILImage.open(filepath) as img:
            # Sample inside the left padding strip of the white logo pill.
            # This strip (x < _TEXT_PADDING) contains only the white background,
            # not the logo itself, so it is reliably white regardless of logo content.
            x = card_operations._TEXT_PADDING - card_operations._LOGO_PADDING // 2
            y = img.height - card_operations._TEXT_PADDING - card_operations._LOGO_PADDING
            r, g, b = img.getpixel((x, y))
        # The gradient background at this position is near-black (~30, 20, 70).
        assert r > 200 and g > 200 and b > 200
