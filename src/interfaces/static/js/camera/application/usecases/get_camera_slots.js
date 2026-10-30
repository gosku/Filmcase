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
 * Read every custom slot the camera model offers.
 *
 * Returns an empty list for a model with no custom slots, or one the server
 * does not know: offering slots that may not exist would invite a write into
 * nothing.
 *
 * @param {import("../../vendor/ptp_device.js").CameraDevice} device Connected.
 * @param {{config: object, sleep: (seconds: number) => Promise<void>}} runtime
 * @returns {Promise<Array<{index: number, name: string, filmSimPtp: number, filmSimName: string}>>}
 */
export async function getCameraSlots(device, runtime) {
  const strategy = getStrategy(device.cameraName);
  const slotCount = customSlotCount(device.cameraName, runtime.config.encodings);
  return strategy.readSlots(device, { slotCount, runtime });
}
