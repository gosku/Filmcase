/**
 * Read every custom slot from the camera.
 *
 * Ports src/application/usecases/camera/get_camera_slots.py.
 *
 * The device is passed in rather than built here, which is the one structural
 * difference from the Python. There, device_config.get_device() reads a setting
 * and constructs an implementation; here the caller has already been through
 * the browser's device picker, and repeating that inside a use case would put a
 * permission dialog behind a function that reads slots.
 *
 * The reads are sequential and deliberately so. Each one depends on the slot
 * cursor written before it, so running them together would return four
 * readings of whichever slot the camera happened to land on.
 */

import { CameraConnectionError } from "../../vendor/ptp_device.js";
import { customSlotCount, makeSlotState } from "../../domain/queries.js";
import { setCursorWithRetry } from "../../domain/operations.js";
import {
  SLOT_PROGRESS,
  SLOT_RETRY,
  publishEvent,
  publishTrace,
} from "../../vendor/events.js";

/**
 * Call `fn` until it succeeds, retrying only transport failures.
 *
 * A CameraWriteError propagates immediately: the camera answered and refused,
 * so another identical request would be refused identically.
 *
 * @template T
 * @param {() => Promise<T>} fn
 * @param {{config: object, sleep: (seconds: number) => Promise<void>}} runtime
 * @returns {Promise<T>}
 */
async function _retry(fn, { config, sleep }, what) {
  const maxRetries = config.settings.CAMERA_MAX_RETRIES;
  const backoff = config.settings.CAMERA_RETRY_BACKOFF_S;
  let lastError = new CameraConnectionError("no retries attempted");
  for (let attempt = 1; attempt <= maxRetries; attempt += 1) {
    if (attempt > 1) {
      await sleep(backoff * 2 ** (attempt - 2));
    }
    try {
      return await fn();
    } catch (error) {
      if (!(error instanceof CameraConnectionError)) throw error;
      // This loop swallowed its attempts, which made the slot listing look like
      // it gave up first time when it had in fact tried three times. Of the
      // three retry loops it is the only one wrapping a whole slot operation,
      // so its attempts are the ones worth seeing.
      publishEvent({
        eventType: SLOT_RETRY,
        operation: what,
        attempt: `${attempt}/${maxRetries}`,
        error: error.message,
      });
      lastError = error;
    }
  }
  throw lastError;
}

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
  const { config, sleep } = runtime;
  const encodings = config.encodings;
  const slotCount = customSlotCount(device.cameraName, encodings);
  const nameCode = encodings.prop_slot_name;
  const filmSimCode = encodings.custom_slot_codes.FilmSimulation;

  publishTrace({ eventType: SLOT_PROGRESS, camera: device.cameraName, slots: slotCount });
  const states = [];
  for (let index = 1; index <= slotCount; index += 1) {
    publishTrace({ eventType: SLOT_PROGRESS, slot: `C${index}`, of: slotCount });
    if (index > 1) {
      await sleep(config.settings.CAMERA_INTER_SLOT_DELAY_S);
    }
    await setCursorWithRetry(device, index, runtime);
    // The camera needs a moment to settle on the new slot; reading too soon
    // returns the previous slot's values, which is worse than an error because
    // it looks like a correct answer.
    await sleep(config.settings.CAMERA_POST_CURSOR_DELAY_S);

    const name = await _retry(
      () => device.getPropertyString(nameCode),
      runtime,
      `C${index} name`
    );
    const filmSimPtp = await _retry(
      () => device.getPropertyInt(filmSimCode),
      runtime,
      `C${index} film simulation`
    );

    states.push(makeSlotState({ index, name, filmSimPtp }, encodings));
  }
  return states;
}
