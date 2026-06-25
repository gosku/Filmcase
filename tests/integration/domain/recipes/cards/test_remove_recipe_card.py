from pathlib import Path

import pytest

from src.data import models
from src.domain.images import events
from src.domain.recipes.cards import operations as card_operations
from tests.factories import RecipeCardFactory


# transaction=True is required throughout: atomic(durable=True) inside
# remove_recipe_card raises RuntimeError if called within an outer transaction,
# which is how pytest-django wraps every regular @pytest.mark.django_db test.
@pytest.mark.django_db(transaction=True)
class TestRemoveRecipeCardPersistence:
    def test_deletes_recipe_card_from_db(self) -> None:
        card = RecipeCardFactory()
        card_operations.remove_recipe_card(card_id=card.pk, remove_file=False)
        assert not models.RecipeCard.objects.filter(pk=card.pk).exists()

    def test_removes_file_when_remove_file_is_true(self, tmp_path: Path) -> None:
        filepath = tmp_path / "card.jpg"
        filepath.write_bytes(b"fake_jpeg")
        card = RecipeCardFactory(filepath=str(filepath))
        card_operations.remove_recipe_card(card_id=card.pk, remove_file=True)
        assert not filepath.exists()

    def test_does_not_remove_file_when_remove_file_is_false(self, tmp_path: Path) -> None:
        filepath = tmp_path / "card.jpg"
        filepath.write_bytes(b"fake_jpeg")
        card = RecipeCardFactory(filepath=str(filepath))
        card_operations.remove_recipe_card(card_id=card.pk, remove_file=False)
        assert filepath.exists()

    def test_tolerates_missing_file_when_remove_file_is_true(self) -> None:
        card = RecipeCardFactory(filepath="/nonexistent/path/card.jpg")
        card_operations.remove_recipe_card(card_id=card.pk, remove_file=True)
        assert not models.RecipeCard.objects.filter(pk=card.pk).exists()

    def test_raises_recipe_card_not_found_for_missing_card(self) -> None:
        with pytest.raises(card_operations.RecipeCardNotFoundError) as exc_info:
            card_operations.remove_recipe_card(card_id=99999, remove_file=False)
        assert exc_info.value.card_id == 99999


@pytest.mark.django_db(transaction=True)
class TestRemoveRecipeCardEventPublishing:
    def test_publishes_event_with_correct_ids(self, captured_logs: list[dict]) -> None:
        card = RecipeCardFactory()
        card_operations.remove_recipe_card(card_id=card.pk, remove_file=False)
        removed_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CARD_REMOVED]
        assert len(removed_events) == 1
        assert removed_events[0]["card_id"] == card.pk
        assert removed_events[0]["recipe_id"] == card.recipe_id

    def test_event_includes_filepath(self, captured_logs: list[dict]) -> None:
        card = RecipeCardFactory(filepath="/some/path/card.jpg")
        card_operations.remove_recipe_card(card_id=card.pk, remove_file=False)
        removed_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CARD_REMOVED]
        assert removed_events[0]["filepath"] == "/some/path/card.jpg"

    def test_event_includes_remove_file_flag(self, captured_logs: list[dict]) -> None:
        card = RecipeCardFactory()
        card_operations.remove_recipe_card(card_id=card.pk, remove_file=True)
        removed_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CARD_REMOVED]
        assert removed_events[0]["remove_file"] is True

    def test_no_event_published_when_card_not_found(self, captured_logs: list[dict]) -> None:
        with pytest.raises(card_operations.RecipeCardNotFoundError):
            card_operations.remove_recipe_card(card_id=99999, remove_file=False)
        removed_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CARD_REMOVED]
        assert len(removed_events) == 0
