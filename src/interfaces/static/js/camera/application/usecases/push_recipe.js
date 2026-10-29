/**
 * Write a recipe into one of the camera's custom slots.
 *
 * Ports src/application/usecases/camera/push_recipe.py. Resolves the per-model
 * strategy and delegates the write to it; the write algorithm lives in the
 * strategy.
 *
 * The device is passed in already connected; disconnecting is the caller's job,
 * as it is the caller that obtained the device from the browser in the first
 * place.
 */

import { getStrategy } from "../../domain/strategies.js";

// Re-exported so the interfaces layer keeps importing the exception from the
// use case. It is raised by the strategy (domain), where the push algorithm now
// lives.
export { RecipeWriteError } from "../../domain/strategies.js";

/**
 * Write a recipe to a custom slot.
 *
 * @param {import("../../vendor/ptp_device.js").CameraDevice} device Connected.
 * @param {object} recipe A recipe in FujifilmRecipeData shape.
 * @param {object} options
 * @param {number} options.slotIndex 1-based slot number.
 * @param {{config: object, sleep: (seconds: number) => Promise<void>}} options.runtime
 * @returns {Promise<void>}
 * @throws {RecipeValidationError} The recipe holds a value the camera cannot take.
 * @throws {CameraConnectionError} The camera stopped answering mid-sequence.
 * @throws {CameraWriteError} The camera refused the slot cursor.
 * @throws {RecipeWriteError} Some properties did not write or verify.
 */
export async function pushRecipeToCamera(device, recipe, { slotIndex, runtime }) {
  const strategy = getStrategy(device.cameraName);
  return strategy.pushRecipe(device, recipe, { slotIndex, runtime });
}
