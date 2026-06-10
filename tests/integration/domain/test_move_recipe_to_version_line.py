import pytest

from src.data import models
from src.domain.images import events
from src.domain.recipes.operations import (
    CannotMoveToSameGroupError,
    InvalidVersionLinePositionError,
    VersionLineGroupNotFoundError,
    move_recipe_to_version_line,
)
from src.domain.recipes.queries import RecipeNotInVersionLineError
from tests.factories import FujifilmRecipeFactory, RecipeGroupFactory, RecipeGroupMemberFactory


def _positions(group: models.RecipeGroup) -> list[int]:
    return list(
        models.RecipeGroupMember.objects.filter(group=group)
        .order_by("position")
        .values_list("position", flat=True)
    )


def _recipe_ids_ordered(group: models.RecipeGroup) -> list[int]:
    return list(
        models.RecipeGroupMember.objects.filter(group=group)
        .order_by("position")
        .values_list("recipe_id", flat=True)
    )


@pytest.mark.django_db
class TestMoveRecipeToVersionLine:

    # ── Source group membership ───────────────────────────────────────────────

    def test_removes_recipe_from_source_group(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        recipe_y = FujifilmRecipeFactory()
        recipe_z = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        RecipeGroupMemberFactory(group=source, recipe=recipe_y, position=2)
        RecipeGroupMemberFactory(group=source, recipe=recipe_z, position=3)
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)
        RecipeGroupMemberFactory(group=dest, recipe=recipe_b, position=2)

        move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk)

        assert recipe_x.pk not in _recipe_ids_ordered(source)

    def test_shifts_source_positions_down_after_removal(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        recipe_y = FujifilmRecipeFactory()
        recipe_z = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        RecipeGroupMemberFactory(group=source, recipe=recipe_y, position=2)
        RecipeGroupMemberFactory(group=source, recipe=recipe_z, position=3)
        recipe_a = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)

        move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk)

        assert _recipe_ids_ordered(source) == [recipe_y.pk, recipe_z.pk]
        assert _positions(source) == [1, 2]

    def test_does_not_shift_source_members_before_the_removed_position(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        recipe_y = FujifilmRecipeFactory()
        recipe_z = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        RecipeGroupMemberFactory(group=source, recipe=recipe_y, position=2)
        RecipeGroupMemberFactory(group=source, recipe=recipe_z, position=3)
        recipe_a = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)

        move_recipe_to_version_line(recipe_id=recipe_z.pk, destination_group_id=dest.pk)

        assert _recipe_ids_ordered(source) == [recipe_x.pk, recipe_y.pk]
        assert _positions(source) == [1, 2]

    # ── Source group deletion ─────────────────────────────────────────────────

    def test_deletes_source_group_when_it_becomes_empty(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        recipe_a = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)

        move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk)

        assert not models.RecipeGroup.objects.filter(pk=source.pk).exists()

    def test_does_not_delete_source_group_when_members_remain(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        recipe_y = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        RecipeGroupMemberFactory(group=source, recipe=recipe_y, position=2)
        recipe_a = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)

        move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk)

        assert models.RecipeGroup.objects.filter(pk=source.pk).exists()

    # ── Destination group insertion ───────────────────────────────────────────

    def test_appends_to_destination_by_default(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)
        RecipeGroupMemberFactory(group=dest, recipe=recipe_b, position=2)

        move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk)

        assert _recipe_ids_ordered(dest) == [recipe_a.pk, recipe_b.pk, recipe_x.pk]
        assert _positions(dest) == [1, 2, 3]

    def test_inserts_at_given_position_and_shifts_others_up(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)
        RecipeGroupMemberFactory(group=dest, recipe=recipe_b, position=2)

        move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk, position=2)

        assert _recipe_ids_ordered(dest) == [recipe_a.pk, recipe_x.pk, recipe_b.pk]
        assert _positions(dest) == [1, 2, 3]

    def test_inserts_at_first_position(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)
        RecipeGroupMemberFactory(group=dest, recipe=recipe_b, position=2)

        move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk, position=1)

        assert _recipe_ids_ordered(dest) == [recipe_x.pk, recipe_a.pk, recipe_b.pk]
        assert _positions(dest) == [1, 2, 3]

    def test_recipe_ends_up_in_destination_group(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        recipe_a = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)

        move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk)

        assert models.RecipeGroupMember.objects.filter(
            recipe_id=recipe_x.pk,
            group=dest,
        ).exists()

    # ── Event publishing ──────────────────────────────────────────────────────

    def test_publishes_version_line_updated_event(self, captured_logs: list[dict]) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)
        RecipeGroupMemberFactory(group=dest, recipe=recipe_b, position=2)

        move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk)

        version_line_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_VERSION_LINE_UPDATED
        ]
        assert len(version_line_events) == 1
        event = version_line_events[0]
        assert event["recipe_id"] == recipe_x.pk
        assert event["source_group_id"] == source.pk
        assert event["destination_group_id"] == dest.pk
        assert event["position"] == 3

    def test_published_event_reflects_explicit_position(self, captured_logs: list[dict]) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        recipe_a = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)

        move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk, position=1)

        event = next(
            e for e in captured_logs if e.get("event_type") == events.RECIPE_VERSION_LINE_UPDATED
        )
        assert event["position"] == 1

    # ── Error cases ───────────────────────────────────────────────────────────

    def test_raises_when_recipe_not_in_version_line(self) -> None:
        recipe = FujifilmRecipeFactory()
        dest = RecipeGroupFactory()
        recipe_a = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)

        with pytest.raises(RecipeNotInVersionLineError) as exc_info:
            move_recipe_to_version_line(recipe_id=recipe.pk, destination_group_id=dest.pk)

        assert exc_info.value.recipe_id == recipe.pk

    def test_raises_when_destination_group_not_found(self) -> None:
        source = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)

        with pytest.raises(VersionLineGroupNotFoundError) as exc_info:
            move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=99999)

        assert exc_info.value.group_id == 99999

    def test_raises_when_destination_is_a_family_group(self) -> None:
        source = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        family_group = RecipeGroupFactory(group_type=models.RecipeGroup.GROUP_TYPE_FAMILY)

        with pytest.raises(VersionLineGroupNotFoundError):
            move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=family_group.pk)

    def test_raises_when_source_and_destination_are_the_same_group(self) -> None:
        source = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        recipe_y = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        RecipeGroupMemberFactory(group=source, recipe=recipe_y, position=2)

        with pytest.raises(CannotMoveToSameGroupError) as exc_info:
            move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=source.pk)

        assert exc_info.value.group_id == source.pk

    def test_raises_when_position_exceeds_destination_size_plus_one(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        recipe_a = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)

        with pytest.raises(InvalidVersionLinePositionError) as exc_info:
            move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk, position=5)

        assert exc_info.value.position == 5
        assert exc_info.value.max_position == 2

    def test_raises_when_position_is_zero(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        recipe_a = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)

        with pytest.raises(InvalidVersionLinePositionError):
            move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk, position=0)
