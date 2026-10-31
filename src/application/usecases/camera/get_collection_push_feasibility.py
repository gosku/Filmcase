"""
Application-layer use case for the collection push modal.

Reads, in one connection, the camera model, its current slots, and whether the
collection could be pushed: shared white-balance conflicts, the fields the model
drops across the collection, and the recipes it cannot store at all. The modal
uses this to warn before the user pushes. A per-property body is always feasible
and drops nothing, so the modal renders exactly as before for it.
"""
from __future__ import annotations

import attrs

from src.domain.camera import device_config
from src.domain.camera import queries as camera_queries
from src.domain.camera import strategies
from src.domain.recipes import queries as recipe_queries

CollectionNotFound = recipe_queries.CollectionNotFound


@attrs.frozen
class UnrepresentableRecipe:
    """A collection recipe the model cannot store, named for the modal."""

    recipe_id: int
    field: str
    value: str


@attrs.frozen
class CollectionPushFeasibility:
    """The collection modal's read: current slots plus the push verdict."""

    camera_model: str
    slots: list[camera_queries.SlotState]
    ok: bool
    conflicts: tuple[str, ...]
    dropped_fields: tuple[str, ...]
    unrepresentable: tuple[UnrepresentableRecipe, ...]
    # Whether the whole collection must be pushed as one operation (a backup-blob
    # body edits one settings backup and restores once) rather than slot by slot.
    single_operation: bool


def get_collection_push_feasibility(
    *, collection_id: int, camera_model: str | None = None
) -> CollectionPushFeasibility:
    """
    Read the camera's slots and whether *collection_id* could be pushed to them.

    Args:
        collection_id: The collection to assess.
        camera_model:  The camera model, when the caller already learned it, so
                       the strategy can be resolved without rediscovering it. When
                       None, the model is read from the connected device.

    Raises:
        CollectionNotFound:    If no collection with that id exists.
        CameraConnectionError: If the camera is unreachable or a read fails.
        CameraWriteError:      If the camera rejects a slot cursor write.
    """
    collection = recipe_queries.get_collection_detail(collection_id=collection_id)
    device = device_config.get_device()
    device.connect()
    try:
        camera_model = camera_model or device.camera_name
        strategy = strategies.get_strategy(camera_model)
        single_operation = isinstance(strategy, strategies.BackupBlobStrategy)
        slot_count = camera_queries.custom_slot_count(camera_model)
        slots = strategy.read_slots(device, slot_count=slot_count)
        plan = recipe_queries.plan_collection_transfer(
            member_recipe_ids=[member.recipe_id for member in collection.members],
            slot_count=slot_count,
        )
        data_by_id = recipe_queries.recipe_data_by_ids(
            recipe_ids=[assignment.recipe_id for assignment in plan.assignments]
        )
        assignments = [
            (assignment.slot_index, data_by_id[assignment.recipe_id])
            for assignment in plan.assignments
        ]
        feasibility = strategy.collection_feasibility(device, assignments)
    finally:
        device.disconnect()

    recipe_id_by_slot = {assignment.slot_index: assignment.recipe_id for assignment in plan.assignments}
    unrepresentable = tuple(
        UnrepresentableRecipe(
            recipe_id=recipe_id_by_slot[item.slot_index],
            field=item.field,
            value=item.value,
        )
        for item in feasibility.unrepresentable
    )
    return CollectionPushFeasibility(
        camera_model=camera_model,
        slots=slots,
        ok=feasibility.ok,
        conflicts=feasibility.conflicts,
        dropped_fields=feasibility.dropped_fields,
        unrepresentable=unrepresentable,
        single_operation=single_operation,
    )
