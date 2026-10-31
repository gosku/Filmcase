"""
Application-layer use case for pushing a whole collection to a camera.

Collection push is one operation, not a loop of single-recipe pushes: a
backup-blob body (X-T2) must resolve the shared white balance across every
recipe and restore the settings backup once. The per-model write algorithm lives
in the strategy; this use case resolves the collection's recipes and their slot
assignments, then delegates.
"""
from __future__ import annotations

from src.domain.camera import device_config
from src.domain.camera import queries as camera_queries
from src.domain.camera import strategies
from src.domain.recipes import queries as recipe_queries

# Re-exported so the view imports the push errors from the use case. See the
# push_recipe use case for what each means.
RecipeWriteError = strategies.RecipeWriteError
BackupValidationError = strategies.BackupValidationError
PushNotFeasibleError = strategies.PushNotFeasibleError
RecipeNotRepresentable = strategies.RecipeNotRepresentable
CollectionNotFound = recipe_queries.CollectionNotFound


def push_collection_to_camera(*, collection_id: int, camera_model: str | None = None) -> None:
    """
    Push a collection's recipes to the camera's custom slots in one operation.

    The recipes map onto the slots in order (first recipe to slot 1); when the
    collection has more recipes than the camera has slots, the trailing recipes
    are not written. A per-property body writes each slot in turn; a backup-blob
    body (X-T2) edits one settings backup with every assignment and restores it
    once.

    Args:
        collection_id: The collection to push.
        camera_model:  The camera model, when the caller already learned it, so
                       the strategy can be resolved without rediscovering it. When
                       None, the model is read from the connected device.

    Raises:
        CollectionNotFound:     If no collection with that id exists.
        RecipeNotRepresentable: If a recipe holds a value the model cannot store;
                                nothing is written.
        BackupValidationError:  (backup-blob) If the settings backup does not
                                validate, so editing it would be unsafe.
        PushNotFeasibleError:   (backup-blob) If a recipe's white balance would
                                retune a kept slot's shared white balance.
        RecipeWriteError:       If a write failed or did not verify.
        CameraConnectionError:  If the camera becomes unreachable.
        CameraWriteError:       If the camera rejects a critical write.
    """
    collection = recipe_queries.get_collection_detail(collection_id=collection_id)
    device = device_config.get_device()
    device.connect()
    try:
        camera_model = camera_model or device.camera_name
        strategy = strategies.get_strategy(camera_model)
        slot_count = camera_queries.custom_slot_count(camera_model)
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
        strategy.push_collection(device, assignments)
    finally:
        device.disconnect()
