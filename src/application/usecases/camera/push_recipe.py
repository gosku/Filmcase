"""
Application-layer use case for pushing a recipe to a Fujifilm camera.

Orchestrates the connection lifecycle and resolves the per-model strategy that
performs the write.  The write algorithm itself lives in the strategy.
"""
from __future__ import annotations

from src.data import models
from src.domain.camera import device_config
from src.domain.camera import strategies
from src.domain.recipes import queries as recipe_queries

# Re-exported so callers keep importing the exception from the use case.  It is
# raised by the strategy (domain), where the push algorithm now lives.
RecipeWriteError = strategies.RecipeWriteError


def push_recipe_to_camera(
    recipe: models.FujifilmRecipe,
    *,
    slot_index: int,
    known_model: str | None = None,
) -> None:
    """
    Push a film simulation recipe to a custom C-slot on the connected camera.

    The device is obtained from device_config (settings.PTP_DEVICE).
    Connection and disconnection are managed internally; the model-specific write
    is delegated to the resolved strategy.

    Args:
        recipe:      The recipe to write.  ``recipe.name`` must be a non-blank
                     string of at most 25 ASCII characters.
        slot_index:  1-based custom slot number (e.g. 1 for C1).
        known_model: The camera model, when the caller already learned it, so the
                     strategy can be resolved without rediscovering it.  When
                     None, the model is read from the connected device.

    Raises:
        RecipeValidationError: If any recipe field (including name) is invalid.
        CameraConnectionError: If the camera becomes unreachable during the
                               write sequence.
        CameraWriteError:      If the camera rejects a critical write.
        RecipeWriteError:      If one or more properties failed to write or verify.
                               ``exc.failed_properties`` lists the property names.
    """
    recipe_data = recipe_queries.recipe_from_db(recipe=recipe)
    device = device_config.get_device()
    device.connect()
    try:
        camera_name = known_model or device.camera_name
        strategy = strategies.get_strategy(camera_name)
        strategy.push_recipe(device, recipe_data, slot_index=slot_index)
    finally:
        device.disconnect()
