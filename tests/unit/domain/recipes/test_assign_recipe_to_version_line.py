from unittest.mock import MagicMock, patch

import pytest

from src.data import models
from src.domain.images import events
from src.domain.recipes import operations

_MODULE = "src.domain.recipes.operations"


def _make_group_objects(*, missing=False, group=None, max_position=1):
    mock_objects = MagicMock()
    if missing:
        mock_objects.get.side_effect = models.RecipeGroup.DoesNotExist
    else:
        mock_objects.get.return_value = group
    return mock_objects


def _make_member_objects(*, max_position=1):
    mock_objects = MagicMock()
    mock_objects.filter.return_value.aggregate.return_value = {"max_position": max_position}
    return mock_objects


class TestAddRecipeToVersionLineEvent:
    def test_publishes_event_when_assigned_to_new_group(self, captured_logs) -> None:
        recipe = MagicMock(pk=42)
        mock_group = MagicMock(pk=10)
        mock_member = MagicMock(position=1)

        with (
            patch("django.db.transaction.Atomic.__enter__", return_value=None),
            patch("django.db.transaction.Atomic.__exit__", return_value=False),
            patch(f"{_MODULE}.models.RecipeGroup.new_version_line", return_value=mock_group),
            patch(f"{_MODULE}.models.RecipeGroupMember.new", return_value=mock_member),
        ):
            operations.add_recipe_to_version_line(recipe=recipe, group_id=None)

        version_line_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_ADDED_TO_VERSION_LINE
        ]
        assert len(version_line_events) == 1
        assert version_line_events[0]["recipe_id"] == 42
        assert version_line_events[0]["group_id"] == mock_group.pk
        assert version_line_events[0]["position"] == mock_member.position

    def test_publishes_event_when_appended_to_existing_group(self, captured_logs) -> None:
        recipe = MagicMock(pk=42)
        mock_group = MagicMock(pk=10)
        mock_member = MagicMock(position=2)

        with (
            patch("django.db.transaction.Atomic.__enter__", return_value=None),
            patch("django.db.transaction.Atomic.__exit__", return_value=False),
            patch(f"{_MODULE}.models.RecipeGroup.objects", _make_group_objects(group=mock_group)),
            patch(f"{_MODULE}.models.RecipeGroupMember.objects", _make_member_objects()),
            patch(f"{_MODULE}.models.RecipeGroupMember.new", return_value=mock_member),
        ):
            operations.add_recipe_to_version_line(recipe=recipe, group_id=10)

        version_line_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_ADDED_TO_VERSION_LINE
        ]
        assert len(version_line_events) == 1
        assert version_line_events[0]["recipe_id"] == 42
        assert version_line_events[0]["group_id"] == mock_group.pk
        assert version_line_events[0]["position"] == mock_member.position

    def test_no_event_when_group_not_found(self, captured_logs) -> None:
        recipe = MagicMock(pk=42)

        with (
            patch("django.db.transaction.Atomic.__enter__", return_value=None),
            patch("django.db.transaction.Atomic.__exit__", return_value=False),
            patch(f"{_MODULE}.models.RecipeGroup.objects", _make_group_objects(missing=True)),
            pytest.raises(operations.VersionLineGroupNotFoundError),
        ):
            operations.add_recipe_to_version_line(recipe=recipe, group_id=99)

        version_line_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_ADDED_TO_VERSION_LINE
        ]
        assert len(version_line_events) == 0
