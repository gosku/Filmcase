/**
 * In-memory camera device for unit tests.
 *
 * A port of tests/fakes.py:FakePTPDevice, knob for knob, so a test written
 * against one reads the same against the other.
 *
 * All three setProperty* variants write to a single shared store keyed by
 * property code, and the getProperty* variants read from it, so a
 * write-then-read round trip works with no configuration. That matters for the
 * verification path, which is exactly such a round trip.
 *
 * One knob has no Python counterpart: setFailuresBeforeSuccess, for a property
 * that fails a few times and then works. The Python fake raises for a code
 * forever, which cannot express the case the retry loops exist for.
 */

import { CameraConnectionError } from "../../../src/interfaces/static/js/camera/vendor/ptp_device.js";

export class FakePTPDevice {
  /**
   * @param {object} [options]
   * @param {Record<number, number>} [options.intValues] Initial integer store.
   * @param {Record<number, string>} [options.stringValues] Initial string store.
   * @param {string} [options.cameraName]
   * @param {boolean} [options.pingFails] ping() returns -1 instead of 0.
   * @param {Record<number, Error>} [options.getErrors] Code to error thrown on read.
   * @param {Error} [options.defaultGetError] Thrown for any read not in getErrors.
   * @param {Error} [options.defaultIntGetError] Thrown for any integer read; string
   *   reads still work, which is how the verification phase is made to fail
   *   while the slot-name read succeeds.
   * @param {Record<number, number>} [options.intReadOverrides] Code to value always
   *   returned, whatever was written. Models the camera normalising a value.
   * @param {Record<number, string>} [options.strReadOverrides] As above, for strings.
   * @param {Record<number, Error>} [options.setErrors] Code to error thrown on write.
   * @param {Record<number, number>} [options.setRejectionCodes] Code to non-zero
   *   response code. The store is left untouched, as a real refusal leaves it.
   * @param {Record<number, number>} [options.setFailuresBeforeSuccess] Code to a
   *   count of transport failures to raise before the write goes through.
   */
  constructor({
    intValues = {},
    stringValues = {},
    cameraName = "X-S10",
    pingFails = false,
    getErrors = {},
    defaultGetError = null,
    defaultIntGetError = null,
    intReadOverrides = {},
    strReadOverrides = {},
    setErrors = {},
    setRejectionCodes = {},
    setFailuresBeforeSuccess = {},
  } = {}) {
    this._intStore = { ...intValues };
    this._strStore = { ...stringValues };
    this._cameraName = cameraName;
    this._pingFails = pingFails;
    this._getErrors = { ...getErrors };
    this._defaultGetError = defaultGetError;
    this._defaultIntGetError = defaultIntGetError;
    this._intReadOverrides = { ...intReadOverrides };
    this._strReadOverrides = { ...strReadOverrides };
    this._setErrors = { ...setErrors };
    this._setRejectionCodes = { ...setRejectionCodes };
    this._setFailuresLeft = { ...setFailuresBeforeSuccess };

    /** Every write attempted, in order, including ones that failed. */
    this.writes = [];
    /** Every read attempted, in order. */
    this.reads = [];
    /** Lifecycle calls, so a test can assert the device was released. */
    this.calls = [];
  }

  get cameraName() {
    return this._cameraName;
  }

  async connect() {
    this.calls.push("connect");
  }

  async disconnect() {
    this.calls.push("disconnect");
  }

  async ping() {
    return this._pingFails ? -1 : 0;
  }

  // --- reads --------------------------------------------------------------

  _checkGet(code, isInt) {
    if (code in this._getErrors) throw this._getErrors[code];
    if (isInt && this._defaultIntGetError) throw this._defaultIntGetError;
    if (this._defaultGetError) throw this._defaultGetError;
  }

  async getPropertyInt(code) {
    this.reads.push(code);
    this._checkGet(code, true);
    if (code in this._intReadOverrides) return this._intReadOverrides[code];
    return code in this._intStore ? this._intStore[code] : 0;
  }

  async getPropertyInt16(code) {
    const raw = await this.getPropertyInt(code);
    const v = raw & 0xffff;
    return v >= 32768 ? v - 65536 : v;
  }

  async getPropertyString(code) {
    this.reads.push(code);
    this._checkGet(code, false);
    if (code in this._strReadOverrides) return this._strReadOverrides[code];
    return code in this._strStore ? this._strStore[code] : "";
  }

  // --- writes -------------------------------------------------------------

  _beforeSet(code, value) {
    this.writes.push([code, value]);
    if (this._setFailuresLeft[code] > 0) {
      this._setFailuresLeft[code] -= 1;
      throw new CameraConnectionError(`transport failure writing ${code}`);
    }
    if (code in this._setErrors) throw this._setErrors[code];
  }

  async setPropertyInt(code, value) {
    this._beforeSet(code, value);
    if (code in this._setRejectionCodes) return this._setRejectionCodes[code];
    this._intStore[code] = value;
    return 0;
  }

  async setPropertyUint16(code, value) {
    this._beforeSet(code, value);
    if (code in this._setRejectionCodes) return this._setRejectionCodes[code];
    this._intStore[code] = value & 0xffff;
    return 0;
  }

  async setPropertyString(code, value) {
    this._beforeSet(code, value);
    if (code in this._setRejectionCodes) return this._setRejectionCodes[code];
    this._strStore[code] = value;
    return 0;
  }

  async supportedProperties() {
    return [];
  }
}
