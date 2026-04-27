from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image as PILImage

from src.data import models
from src.domain.images import events
from src.domain.recipes.cards import operations as card_operations
from src.domain.recipes.cards import templates as card_templates


def _make_fake_card(recipe_pk: int) -> MagicMock:
    card = MagicMock(spec=models.RecipeCard)
    card.pk = 99
    card.recipe_id = recipe_pk
    return card


class TestCreateRecipeCardEventPublishing:
    def test_publishes_recipe_card_created_event(
        self, tmp_path: Path, captured_logs: list[dict]
    ) -> None:
        recipe = MagicMock()
        recipe.pk = 7

        fake_card = _make_fake_card(recipe.pk)

        with (
            patch.object(
                card_operations,
                "create_recipe_card_image",
                return_value=tmp_path / "card.jpg",
            ),
            patch.object(models.RecipeCard, "create", return_value=fake_card),
        ):
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
        assert card_events[0]["recipe_id"] == 7
        assert card_events[0]["card_id"] == card.pk

    def test_event_contains_template_name(
        self, tmp_path: Path, captured_logs: list[dict]
    ) -> None:
        recipe = MagicMock()
        recipe.pk = 1

        fake_card = _make_fake_card(recipe.pk)

        with (
            patch.object(
                card_operations,
                "create_recipe_card_image",
                return_value=tmp_path / "card.jpg",
            ),
            patch.object(models.RecipeCard, "create", return_value=fake_card),
        ):
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

    def test_does_not_publish_event_if_image_creation_fails(
        self, tmp_path: Path, captured_logs: list[dict]
    ) -> None:
        recipe = MagicMock()
        recipe.pk = 3

        with patch.object(
            card_operations,
            "create_recipe_card_image",
            side_effect=OSError("disk full"),
        ):
            with pytest.raises(OSError):
                card_operations.create_recipe_card(
                    recipe=recipe,
                    template=card_templates.LONG_LABEL,
                    background_image=None,
                    output_dir=tmp_path,
                )

        card_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_CARD_CREATED
        ]
        assert len(card_events) == 0


class TestComposeCardTitle:
    def _generate_card(self, recipe: MagicMock, tmp_path: Path) -> Path:
        output_path = tmp_path / "card.jpg"
        with (
            patch.object(card_operations, "_LOGO_PATH", tmp_path / "no_logo.png"),
            patch.object(card_operations.card_queries, "get_recipe_cover_lines", return_value=()),
            patch.object(card_operations.card_queries, "get_recipe_as_json", return_value='{"v":1}'),
        ):
            card_operations.preview_recipe_card_image(
                recipe=recipe,
                template=card_templates.LONG_LABEL,
                background_image=None,
                output_path=output_path,
            )
        return output_path

    def _max_brightness_in_title_region(self, filepath: Path) -> int:
        p = card_operations._TEXT_PADDING
        with PILImage.open(filepath) as img:
            region = img.crop((p, p, p + 300, p + card_operations._TITLE_LINE_HEIGHT))
        return region.getextrema()[0][1]  # max R value in the region

    def test_title_is_rendered_when_recipe_has_name(self, tmp_path: Path) -> None:
        recipe = MagicMock()
        recipe.name = "My Recipe"
        recipe.pk = 1

        filepath = self._generate_card(recipe, tmp_path)

        # White text on a near-black gradient; max R in the title region must be bright.
        assert self._max_brightness_in_title_region(filepath) > 200

    def test_title_is_not_rendered_when_name_is_empty(self, tmp_path: Path) -> None:
        recipe = MagicMock()
        recipe.name = ""
        recipe.pk = 1

        filepath = self._generate_card(recipe, tmp_path)

        # Gradient at top-left is ~(18, 51, 64); no text means no bright pixels.
        assert self._max_brightness_in_title_region(filepath) < 100


class TestComposeCardLogoFallback:
    def test_missing_logo_file_does_not_raise(self, tmp_path: Path) -> None:
        recipe = MagicMock()
        recipe.name = ""
        recipe.pk = 1

        with (
            patch.object(card_operations, "_LOGO_PATH", tmp_path / "no_logo.png"),
            patch.object(card_operations.card_queries, "get_recipe_cover_lines", return_value=()),
            patch.object(card_operations.card_queries, "get_recipe_as_json", return_value='{"v":1}'),
        ):
            output_path = tmp_path / "card.jpg"
            result = card_operations.preview_recipe_card_image(
                recipe=recipe,
                template=card_templates.LONG_LABEL,
                background_image=None,
                output_path=output_path,
            )

        assert result == output_path
        assert output_path.exists()


