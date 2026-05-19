import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.data import models
from src.domain.images import events
from src.domain.recipes.cards import operations as card_operations


def _fake_card(*, pk: int, filepath: str) -> MagicMock:
    card = MagicMock(spec=models.RecipeCard)
    card.pk = pk
    card.filepath = filepath
    return card


class TestCreateRecipeCardsZip:
    def test_publishes_zip_created_event(
        self, tmp_path: Path, captured_logs: list[dict]
    ) -> None:
        source = tmp_path / "card_1.jpg"
        source.write_bytes(b"jpeg-bytes")
        card = _fake_card(pk=1, filepath=str(source))

        zip_path = card_operations.create_recipe_cards_zip(cards=[card])

        zip_events = [
            e for e in captured_logs
            if e.get("event_type") == events.RECIPE_CARDS_ZIP_CREATED
        ]
        assert len(zip_events) == 1
        assert zip_events[0]["card_count"] == 1
        assert zip_events[0]["zip_path"] == str(zip_path)

    def test_raises_when_card_file_missing(
        self, tmp_path: Path, captured_logs: list[dict]
    ) -> None:
        card = _fake_card(pk=42, filepath=str(tmp_path / "does_not_exist.jpg"))

        with pytest.raises(card_operations.RecipeCardFileMissingError) as exc_info:
            card_operations.create_recipe_cards_zip(cards=[card])

        assert exc_info.value.card_id == 42
        zip_events = [
            e for e in captured_logs
            if e.get("event_type") == events.RECIPE_CARDS_ZIP_CREATED
        ]
        assert len(zip_events) == 0

    def test_does_not_write_partial_zip_when_a_later_file_is_missing(
        self, tmp_path: Path
    ) -> None:
        present = tmp_path / "present.jpg"
        present.write_bytes(b"jpeg-bytes")
        cards = [
            _fake_card(pk=1, filepath=str(present)),
            _fake_card(pk=2, filepath=str(tmp_path / "missing.jpg")),
        ]
        tmp_dir = Path(tempfile.gettempdir())
        before = set(tmp_dir.glob("recipe_cards_*.zip"))

        with pytest.raises(card_operations.RecipeCardFileMissingError):
            card_operations.create_recipe_cards_zip(cards=cards)

        # Validation runs before any archive is opened, so no new zip exists.
        assert set(tmp_dir.glob("recipe_cards_*.zip")) == before
