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
 *
 * Every operation also yields once and refuses to overlap with another. PTP is
 * one transaction at a time: a second command sent before the first has had its
 * response interleaves containers on the wire and corrupts both. Nothing in the
 * Python needs this because its calls block, but here a single missing await
 * would produce exactly that, so the fake makes it a loud failure rather than
 * something only a real camera would notice.
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

    this._inFlight = false;
  }

  /**
   * Run one device operation, refusing to overlap with another.
   *
   * The yield is what makes overlap detectable: without it a caller that
   * forgot an await would still run to completion before the next started,
   * and the test would pass while the real transport corrupted itself.
   */
  async _oneAtATime(fn) {
    if (this._inFlight) {
      throw new Error(
        "FakePTPDevice: overlapping device calls. PTP is one transaction at a " +
          "time, so a missing await here corrupts the wire on real hardware."
      );
    }
    this._inFlight = true;
    try {
      await Promise.resolve();
      return fn();
    } finally {
      this._inFlight = false;
    }
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
    return this._oneAtATime(() => this._readInt(code));
  }

  /** The read itself, unguarded, so subclasses can reuse it. */
  _readInt(code) {
    this.reads.push(code);
    this._checkGet(code, true);
    if (code in this._intReadOverrides) return this._intReadOverrides[code];
    return code in this._intStore ? this._intStore[code] : 0;
  }

  async getPropertyInt16(code) {
    const raw = await this._oneAtATime(() => this._readInt(code));
    const v = raw & 0xffff;
    return v >= 32768 ? v - 65536 : v;
  }

  async getPropertyString(code) {
    return this._oneAtATime(() => this._readString(code));
  }

  /** The read itself, unguarded, so subclasses can reuse it. */
  _readString(code) {
    this.reads.push(code);
    this._checkGet(code, false);
    if (code in this._strReadOverrides) return this._strReadOverrides[code];
    return code in this._strStore ? this._strStore[code] : "";
  }

  // --- writes -------------------------------------------------------------

  /** The write itself, unguarded, so subclasses can reuse it. */
  _write(code, value, store, transform) {
    this._beforeSet(code, value);
    if (code in this._setRejectionCodes) return this._setRejectionCodes[code];
    this[store][code] = transform(value);
    return 0;
  }

  _beforeSet(code, value) {
    this.writes.push([code, value]);
    if (this._setFailuresLeft[code] > 0) {
      this._setFailuresLeft[code] -= 1;
      throw new CameraConnectionError(`transport failure writing ${code}`);
    }
    if (code in this._setErrors) throw this._setErrors[code];
  }

  async setPropertyInt(code, value) {
    return this._oneAtATime(() => this._write(code, value, "_intStore", (v) => v));
  }

  async setPropertyUint16(code, value) {
    return this._oneAtATime(() => this._write(code, value, "_intStore", (v) => v & 0xffff));
  }

  async setPropertyString(code, value) {
    return this._oneAtATime(() => this._write(code, value, "_strStore", (v) => v));
  }

  async supportedProperties() {
    return [];
  }
}
