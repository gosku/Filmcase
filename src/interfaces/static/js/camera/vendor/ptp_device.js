/**
 * Errors and the device contract for browser-side PTP.
 *
 * Ports src/domain/camera/ptp_device.py. The Python module also declares a
 * PTPDevice Protocol; the equivalent here is the CameraDevice typedef below,
 * which JSDoc can check but nothing enforces at runtime.
 *
 * The vendor id deliberately does not live here. Python keeps it as a constant
 * because a browser page needed it and had no other source; this side is served
 * it in the client config, so hardcoding a second copy would undo that.
 */

/** Raised when the camera is not reachable or the transport fails. */
export class CameraConnectionError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "CameraConnectionError";
  }
}

/** Raised when the camera actively rejects a property write (non-zero rc). */
export class CameraWriteError extends Error {
  /**
   * @param {number} code PTP property code.
   * @param {string|number} value The value the camera refused.
   * @param {number} rc The response code it refused with.
   */
  constructor(code, value, rc) {
    super(
      `Camera rejected write of PTP property ${formatCode(code)} = ` +
        `${formatValue(value)} (rc=${formatRc(rc)})`
    );
    this.name = "CameraWriteError";
    this.code = code;
    this.value = value;
    this.rc = rc;
  }
}

/**
 * Format a PTP property code the way the Python side does: 0xD18C.
 *
 * Shared because these codes are meaningless in decimal, and a failure report
 * that a user pastes into an issue should be greppable against the Python logs.
 *
 * @param {number} code
 * @returns {string}
 */
export function formatCode(code) {
  return `0x${code.toString(16).toUpperCase().padStart(4, "0")}`;
}

/**
 * Format a response code as Python's `{rc:#x}` does: 0x2001 lowercase, no pad.
 *
 * @param {number} rc
 * @returns {string}
 */
export function formatRc(rc) {
  return `0x${rc.toString(16)}`;
}

/**
 * Format a written value the way Python's `!r` would, so the two implementations
 * report the same failure in the same words.
 *
 * @param {string|number} value
 * @returns {string}
 */
export function formatValue(value) {
  return typeof value === "string" ? `'${value}'` : String(value);
}

/**
 * The operations the domain layer needs from a camera.
 *
 * Mirrors the PTPDevice Protocol, with every method async because WebUSB is
 * promise-based. Two contracts carry over and are easy to get wrong:
 *
 *   - the setProperty* methods RETURN a response code, 0 for success. They do
 *     not throw on rejection. Turning a non-zero rc into a CameraWriteError is
 *     the job of the operations layer, which is also what decides whether to
 *     retry.
 *   - a transport failure, by contrast, throws CameraConnectionError.
 *
 * @typedef {object} CameraDevice
 * @property {() => Promise<void>} connect
 * @property {() => Promise<void>} disconnect
 * @property {() => Promise<number>} ping
 * @property {(code: number) => Promise<number>} getPropertyInt
 * @property {(code: number) => Promise<number>} getPropertyInt16
 * @property {(code: number) => Promise<string>} getPropertyString
 * @property {(code: number, value: number) => Promise<number>} setPropertyInt
 * @property {(code: number, value: number) => Promise<number>} setPropertyUint16
 * @property {(code: number, value: string) => Promise<number>} setPropertyString
 * @property {string} cameraName
 */
