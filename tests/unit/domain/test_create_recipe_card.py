from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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
