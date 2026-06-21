from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.data import models
from src.domain.images import events
from src.domain.recipes.cards import operations as card_operations


# Replaces transaction.atomic(durable=True) with a no-op so unit tests never
# touch the database connection.
@contextmanager
def _noop_atomic(*args, **kwargs):
    yield


_ATOMIC = patch("src.domain.recipes.cards.operations.transaction.atomic", _noop_atomic)


def _make_card_qs(card: object = None, missing: bool = False) -> MagicMock:
    qs = MagicMock()
    if missing:
        qs.get.side_effect = models.RecipeCard.DoesNotExist
    else:
        qs.get.return_value = card
    return qs


class TestRemoveRecipeCardNotFound:
    def test_raises_when_card_does_not_exist(self) -> None:
        qs = _make_card_qs(missing=True)
        with patch("src.domain.recipes.cards.operations.models.RecipeCard.objects", qs):
            with pytest.raises(card_operations.RecipeCardNotFoundError) as exc_info:
                card_operations.remove_recipe_card(card_id=42, remove_file=False)
        assert exc_info.value.card_id == 42

    def test_card_is_not_deleted_when_not_found(self) -> None:
        qs = _make_card_qs(missing=True)
        with patch("src.domain.recipes.cards.operations.models.RecipeCard.objects", qs):
            with pytest.raises(card_operations.RecipeCardNotFoundError):
                card_operations.remove_recipe_card(card_id=42, remove_file=False)
        qs.get.assert_called_once_with(pk=42)


class TestRemoveRecipeCardFileRemoval:
    def test_removes_file_when_remove_file_is_true(self, tmp_path: Path) -> None:
        filepath = tmp_path / "card.jpg"
        filepath.write_bytes(b"fake")
        card = MagicMock()
        card.pk = 1
        card.recipe_id = 10
        card.filepath = str(filepath)
        with _ATOMIC, patch(
            "src.domain.recipes.cards.operations.models.RecipeCard.objects", _make_card_qs(card=card)
        ):
            card_operations.remove_recipe_card(card_id=1, remove_file=True)
        assert not filepath.exists()

    def test_does_not_remove_file_when_remove_file_is_false(self, tmp_path: Path) -> None:
        filepath = tmp_path / "card.jpg"
        filepath.write_bytes(b"fake")
        card = MagicMock()
        card.pk = 1
        card.recipe_id = 10
        card.filepath = str(filepath)
        with _ATOMIC, patch(
            "src.domain.recipes.cards.operations.models.RecipeCard.objects", _make_card_qs(card=card)
        ):
            card_operations.remove_recipe_card(card_id=1, remove_file=False)
        assert filepath.exists()

    def test_does_not_raise_when_file_is_missing_and_remove_file_is_true(self, tmp_path: Path) -> None:
        filepath = tmp_path / "gone.jpg"
        card = MagicMock()
        card.pk = 1
        card.recipe_id = 10
        card.filepath = str(filepath)
        with _ATOMIC, patch(
            "src.domain.recipes.cards.operations.models.RecipeCard.objects", _make_card_qs(card=card)
        ):
            card_operations.remove_recipe_card(card_id=1, remove_file=True)


class TestRemoveRecipeCardEventPublishing:
    def test_publishes_recipe_card_removed_event(self, captured_logs: list[dict]) -> None:
        card = MagicMock()
        card.pk = 5
        card.recipe_id = 10
        card.filepath = "/some/path.jpg"
        with _ATOMIC, patch(
            "src.domain.recipes.cards.operations.models.RecipeCard.objects", _make_card_qs(card=card)
        ):
            card_operations.remove_recipe_card(card_id=5, remove_file=False)
        removed_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CARD_REMOVED]
        assert len(removed_events) == 1
        assert removed_events[0]["card_id"] == 5
        assert removed_events[0]["recipe_id"] == 10

    def test_no_event_published_when_card_not_found(self, captured_logs: list[dict]) -> None:
        with patch(
            "src.domain.recipes.cards.operations.models.RecipeCard.objects",
            _make_card_qs(missing=True),
        ):
            with pytest.raises(card_operations.RecipeCardNotFoundError):
                card_operations.remove_recipe_card(card_id=99, remove_file=False)
        removed_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CARD_REMOVED]
        assert len(removed_events) == 0
