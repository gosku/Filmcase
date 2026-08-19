/**
 * Writing properties to a camera, with retries.
 *
 * Ports src/domain/camera/operations.py.
 *
 * The distinction this module turns on: a transport failure is retried, a
 * rejection is not. If the camera answered at all, it considered the request
 * and refused it, and asking three more times will not change its mind. If it
 * did not answer, the write may never have arrived, and trying again is the
 * whole point. The two leave by different exceptions because the push sequence
 * treats them differently: it abandons the recipe on one and carries on past
 * the other.
 */

import {
  CameraConnectionError,
  CameraWriteError,
  formatCode,
  formatRc,
  formatValue,
} from "../vendor/ptp_device.js";
import {
  PTP_WRITE_FAILED,
  PTP_WRITE_SUCCEEDED,
  publishEvent,
} from "../vendor/events.js";

/**
 * Write one property, retrying transport failures with exponential back-off.
 *
 * @param {import("../vendor/ptp_device.js").CameraDevice} device
 * @param {number} code PTP property code.
 * @param {string|number} value
 * @param {{config: object, sleep: (seconds: number) => Promise<void>}} runtime
 * @returns {Promise<void>}
 * @throws {CameraWriteError} The camera refused the write. It is still there.
 * @throws {CameraConnectionError} Every attempt failed to reach the camera.
 */
export async function setPropWithRetry(device, code, value, { config, sleep }) {
  const maxRetries = config.settings.CAMERA_MAX_RETRIES;
  const backoff = config.settings.CAMERA_RETRY_BACKOFF_S;
  const propHex = formatCode(code);
  const shownValue = formatValue(value);

  let connectionFailed = false;
  let writeRejected = false;
  let failedRc = 0;

  for (let attempt = 1; attempt <= maxRetries; attempt += 1) {
    if (attempt > 1) {
      // Attempts are 1-based here and 0-based in the transport, so the
      // exponent differs while the sequence does not: 0.15 s, then 0.30 s.
      await sleep(backoff * 2 ** (attempt - 2));
    }
    connectionFailed = false;

    let rc;
    try {
      rc =
        typeof value === "string"
          ? await device.setPropertyString(code, value)
          : await device.setPropertyInt(code, value);
    } catch (error) {
      if (!(error instanceof CameraConnectionError)) throw error;
      connectionFailed = true;
      publishEvent({
        eventType: PTP_WRITE_FAILED,
        description:
          `${propHex} = ${shownValue}: ${error.message} ` +
          `(attempt ${attempt}/${maxRetries})`,
      });
      continue;
    }

    if (rc !== 0) {
      writeRejected = true;
      failedRc = rc;
      publishEvent({
        eventType: PTP_WRITE_FAILED,
        description: `${propHex} = ${shownValue}: camera rejected write (rc=${formatRc(rc)})`,
      });
      break;
    }

    publishEvent({
      eventType: PTP_WRITE_SUCCEEDED,
      description: `${propHex} = ${shownValue}`,
    });
    return;
  }

  if (connectionFailed) {
    throw new CameraConnectionError(
      `Camera unreachable after ${maxRetries} attempts writing ${propHex} = ${shownValue}`
    );
  }
  if (writeRejected) {
    throw new CameraWriteError(code, value, failedRc);
  }
}

/**
 * Point the camera at a custom slot, retrying transport failures.
 *
 * Separate from setPropWithRetry because the cursor is a uint16 and that
 * function sends numbers as int32. Four bytes where the camera expects two is
 * not a value it will interpret, and nothing downstream would report it as the
 * cause: the write appears to be accepted and the recipe lands somewhere else.
 *
 * @param {import("../vendor/ptp_device.js").CameraDevice} device
 * @param {number} slotIndex 1-based slot number.
 * @param {{config: object, sleep: (seconds: number) => Promise<void>}} runtime
 * @returns {Promise<void>}
 * @throws {CameraWriteError} The camera refused to move the cursor.
 * @throws {CameraConnectionError} It could not be reached.
 */
export async function setCursorWithRetry(device, slotIndex, { config, sleep }) {
  const maxRetries = config.settings.CAMERA_MAX_RETRIES;
  const backoff = config.settings.CAMERA_RETRY_BACKOFF_S;
  const cursorCode = config.encodings.prop_slot_cursor;
  let lastError = new CameraConnectionError("no retries attempted");

  for (let attempt = 1; attempt <= maxRetries; attempt += 1) {
    if (attempt > 1) {
      await sleep(backoff * 2 ** (attempt - 2));
    }
    try {
      const rc = await device.setPropertyUint16(cursorCode, slotIndex);
      if (rc !== 0) {
        throw new CameraWriteError(cursorCode, slotIndex, rc);
      }
      publishEvent({
        eventType: PTP_WRITE_SUCCEEDED,
        description: `${formatCode(cursorCode)} = ${slotIndex}`,
      });
      return;
    } catch (error) {
      // A refusal is the camera's decision and asking again will not change it.
      if (error instanceof CameraWriteError) throw error;
      if (!(error instanceof CameraConnectionError)) throw error;
      publishEvent({
        eventType: PTP_WRITE_FAILED,
        description:
          `${formatCode(cursorCode)} = ${slotIndex}: ${error.message} ` +
          `(attempt ${attempt}/${maxRetries})`,
      });
      lastError = error;
    }
  }
  throw lastError;
}

/**
 * Read back each property that reported success and check it took.
 *
 * A write reporting success only means the camera accepted the request, not
 * that the value stuck; reading back is the only way to know. Returns the codes
 * that did not match, rather than throwing, because the caller wants the whole
 * list to show the user rather than the first disappointment.
 *
 * @param {import("../vendor/ptp_device.js").CameraDevice} device
 * @param {Array<[number, string|number]>} written
 * @param {{config: object, sleep: (seconds: number) => Promise<void>}} runtime
 * @returns {Promise<number[]>} Codes whose read-back did not match.
 */
export async function verifyWrittenProperties(device, written, { config, sleep }) {
  const mismatched = [];
  for (const [code, expected] of written) {
    await sleep(config.settings.CAMERA_PRE_WRITE_DELAY_S);
    try {
      let matches;
      let actual;
      if (typeof expected === "string") {
        actual = await device.getPropertyString(code);
        matches = actual === expected;
      } else {
        actual = await device.getPropertyInt(code);
        // Compared as sixteen bits: the camera returns a uint16 where the
        // value written was a signed int32, so -40 goes out as 0xFFFFFFD8 and
        // comes back as 0xFFD8. Comparing them whole would fail every negative.
        matches = (actual & 0xffff) === (expected & 0xffff);
      }
      if (!matches) {
        console.warn(
          `Verification failed for ${formatCode(code)}: wrote ${formatValue(expected)}, ` +
            `read back ${formatValue(actual)}`
        );
        mismatched.push(code);
      }
    } catch (error) {
      if (!(error instanceof CameraConnectionError)) throw error;
      console.warn(`Verification read failed for ${formatCode(code)} (camera error)`);
      mismatched.push(code);
    }
  }
  return mismatched;
}
