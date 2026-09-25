from src.domain.recipes import queries as recipe_queries


class TestPlanCollectionTransfer:
    def test_recipes_equal_slots_writes_all_with_nothing_left_over(self) -> None:
        plan = recipe_queries.plan_collection_transfer(
            member_recipe_ids=[10, 20, 30, 40], slot_count=4,
        )

        assert plan.assignments == (
            recipe_queries.SlotAssignment(slot_index=1, recipe_id=10),
            recipe_queries.SlotAssignment(slot_index=2, recipe_id=20),
            recipe_queries.SlotAssignment(slot_index=3, recipe_id=30),
            recipe_queries.SlotAssignment(slot_index=4, recipe_id=40),
        )
        assert plan.dropped_recipe_ids == ()
        assert plan.untouched_slot_count == 0

    def test_fewer_recipes_than_slots_keeps_trailing_slots(self) -> None:
        plan = recipe_queries.plan_collection_transfer(
            member_recipe_ids=[10, 20], slot_count=7,
        )

        assert plan.assignments == (
            recipe_queries.SlotAssignment(slot_index=1, recipe_id=10),
            recipe_queries.SlotAssignment(slot_index=2, recipe_id=20),
        )
        assert plan.dropped_recipe_ids == ()
        assert plan.untouched_slot_count == 5

    def test_more_recipes_than_slots_drops_the_surplus(self) -> None:
        plan = recipe_queries.plan_collection_transfer(
            member_recipe_ids=[10, 20, 30, 40, 50], slot_count=4,
        )

        assert plan.assignments == (
            recipe_queries.SlotAssignment(slot_index=1, recipe_id=10),
            recipe_queries.SlotAssignment(slot_index=2, recipe_id=20),
            recipe_queries.SlotAssignment(slot_index=3, recipe_id=30),
            recipe_queries.SlotAssignment(slot_index=4, recipe_id=40),
        )
        assert plan.dropped_recipe_ids == (50,)
        assert plan.untouched_slot_count == 0

    def test_empty_collection_writes_nothing_and_keeps_every_slot(self) -> None:
        plan = recipe_queries.plan_collection_transfer(
            member_recipe_ids=[], slot_count=4,
        )

        assert plan.assignments == ()
        assert plan.dropped_recipe_ids == ()
        assert plan.untouched_slot_count == 4

    def test_camera_without_custom_slots_drops_every_recipe(self) -> None:
        plan = recipe_queries.plan_collection_transfer(
            member_recipe_ids=[10, 20], slot_count=0,
        )

        assert plan.assignments == ()
        assert plan.dropped_recipe_ids == (10, 20)
        assert plan.untouched_slot_count == 0
