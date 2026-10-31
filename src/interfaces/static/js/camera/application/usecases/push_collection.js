/**
 * Push a whole collection to the camera as one operation.
 *
 * Ports src/application/usecases/camera/push_collection.py. Resolves the per-
 * model strategy and delegates: a per-property body writes each slot in turn, a
 * backup-blob body (X-T2) edits one settings backup and restores it once. The
 * device is passed in already connected; disconnecting is the caller's job.
 */

import { getStrategy } from "../../domain/strategies.js";

// Re-exported so the interfaces layer imports the push errors from the use case.
export {
  BackupValidationError,
  PushNotFeasibleError,
  RecipeNotRepresentable,
  RecipeWriteError,
} from "../../domain/strategies.js";

/**
 * Write every (slotIndex, recipe) assignment to the camera in one operation.
 *
 * @param {import("../../vendor/ptp_device.js").CameraDevice} device Connected.
 * @param {Array<[number, object]>} assignments 1-based slot index, recipe data.
 * @param {object} options
 * @param {{config: object, sleep: (seconds: number) => Promise<void>}} options.runtime
 * @returns {Promise<void>}
 */
export async function pushCollectionToCamera(device, assignments, { runtime }) {
  const strategy = getStrategy(device.cameraName, runtime.config);
  return strategy.pushCollection(device, assignments, { runtime });
}
