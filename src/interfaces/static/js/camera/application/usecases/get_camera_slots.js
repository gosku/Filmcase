/**
 * Read every custom slot from the camera.
 *
 * Ports src/application/usecases/camera/get_camera_slots.py. Resolves the per-
 * model strategy and delegates the read to it; the read algorithm, including
 * its retry behaviour, lives in the strategy.
 *
 * The device is passed in rather than built here, which is the one structural
 * difference from the Python. There, device_config.get_device() reads a setting
 * and constructs an implementation; here the caller has already been through
 * the browser's device picker, and repeating that inside a use case would put a
 * permission dialog behind a function that reads slots.
 */

import { customSlotCount } from "../../domain/queries.js";
import { getStrategy } from "../../domain/strategies.js";

/**
 * Read every custom slot the camera model offers, with optional push feasibility.
 *
 * Mirrors src/application/usecases/camera/get_camera_slots.py: the slots come
 * back empty for a model with no custom slots, or one the served config does not
 * know. When a target recipe is given, the read also reports whether that recipe
 * could be pushed into each slot and which of its fields the model would drop,
 * so the picker can grey out conflicting slots and warn before a push; without
 * one, `feasibility` is empty and `droppedFields` is `[]`.
 *
 * @param {import("../../vendor/ptp_device.js").CameraDevice} device Connected.
 * @param {{config: object, sleep: (seconds: number) => Promise<void>}} runtime
 * @param {object} [options]
 * @param {object|null} [options.recipe] A recipe to assess feasibility against.
 * @returns {Promise<{slots: Array<{index: number, name: string, filmSimPtp: number, filmSimName: string}>, feasibility: Array<{slotIndex: number, feasible: boolean, reason: string}>, droppedFields: string[]}>}
 */
export async function getCameraSlots(device, runtime, { recipe = null } = {}) {
  const strategy = getStrategy(device.cameraName, runtime.config);
  const slotCount = customSlotCount(device.cameraName, runtime.config.encodings);
  const slots = await strategy.readSlots(device, { slotCount, runtime });
  if (!recipe) {
    return { slots, feasibility: [], droppedFields: [] };
  }
  const plan = await strategy.planFeasibility(device, recipe, { slotCount, runtime });
  return { slots, feasibility: plan.slots, droppedFields: plan.droppedFields };
}
