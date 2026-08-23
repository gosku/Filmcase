/**
 * PTP over WebUSB.
 *
 * Ports src/domain/camera/ptp_usb_device.py. Names match that file so the two
 * can be read side by side: the leading underscores are kept even though they
 * mean nothing here, and snake_case becomes camelCase and nothing else.
 *
 * Three things differ from the Python. Two are forced by the platform; the
 * third is a deliberate choice, flagged as such so nobody "fixes" it back.
 *
 *   - the device is handed in rather than found. usb.core.find() has no browser
 *     equivalent that a transport could call: navigator.usb.requestDevice()
 *     shows UI and needs a live user gesture, so choosing the camera belongs to
 *     the click handler and this class receives the result.
 *
 *   - every transfer is wrapped in a timeout. PyUSB passes one to libusb;
 *     WebUSB has no timeout parameter and accepts no AbortSignal, so racing a
 *     timer is the only option. Without it a camera that stops answering hangs
 *     the tab for good.
 *
 *   - a timed-out transfer is treated as fatal to the connection, which the
 *     Python does not do. This is the deliberate one. Neither platform can
 *     stop a camera that has already queued a reply from delivering it, so
 *     after a timeout the next read may return the previous command's answer
 *     on either side; libusb cancelling the host-side transfer does not change
 *     that. The Python retries anyway and can act on a stale container. Here
 *     the device latches unusable instead and the caller reconnects, because a
 *     wrong value silently written to a camera slot is worse than an error
 *     message. The server-side equivalent is a known, separate issue.
 *
 * The transaction id also resets in connect() rather than only in the
 * constructor. That is not a behavioural difference in practice, since callers
 * build a fresh instance per push on both sides; it states the per-session
 * invariant where the session is opened rather than relying on call discipline.
 */

import { CameraConnectionError, formatCode, formatRc } from "./ptp_device.js";
import {
  PTP_READ_FAILED,
  PTP_READ_RETRY,
  PTP_READ_SUCCEEDED,
  PTP_WRITE_FAILED,
  PTP_CONTAINER,
  PTP_RECEIVED,
  PTP_SENT,
  PTP_TX_MISMATCH,
  PTP_WRITE_SUCCEEDED,
  SESSION_CLOSED,
  SESSION_FAILED,
  SESSION_OPENED,
  SESSION_STEP,
  publishEvent,
  publishTrace,
} from "./events.js";

// ---------------------------------------------------------------------------
// PTP/USB packet types (PIMA 15740:2000 5.3.1)
// ---------------------------------------------------------------------------

export const _PTP_COMMAND = 0x0001;
export const _PTP_DATA = 0x0002;
export const _PTP_RESPONSE = 0x0003;

// ---------------------------------------------------------------------------
// PTP operation codes
// ---------------------------------------------------------------------------

export const _OC_GET_DEVICE_INFO = 0x1001;
export const _OC_OPEN_SESSION = 0x1002;
export const _OC_CLOSE_SESSION = 0x1003;
export const _OC_GET_DEVICE_PROP_VALUE = 0x1015;
export const _OC_SET_DEVICE_PROP_VALUE = 0x1016;

// ---------------------------------------------------------------------------
// PTP response codes
// ---------------------------------------------------------------------------

export const _RC_OK = 0x2001;
export const _RC_SESSION_ALREADY = 0x201e; // treat as OK

// ---------------------------------------------------------------------------
// Timeout / buffer constants
// ---------------------------------------------------------------------------

// Class-specific control requests from the USB Still Image Capture Device
// definition. These travel on endpoint 0, which is what makes them useful: when
// a bulk read stalls, endpoint 0 is the only way left to talk to the camera.
export const _REQ_CANCEL = 0x64;
export const _REQ_DEVICE_RESET = 0x66;
export const _REQ_GET_DEVICE_STATUS = 0x67;
const _CANCELLATION_CODE = 0x4001;
const _RC_DEVICE_BUSY = 0x2019;

// Fallback only. The real value is served as CAMERA_USB_TIMEOUT_MS, so an
// operator can tune it against their own camera without a code change.
export const _USB_TIMEOUT_MS = 1500;
export const _READ_BUFFER = 65536; // max data to read in one call
export const _SESSION_ID = 1;

// The container header every packet starts with: uint32 length, uint16 type,
// uint16 code, uint32 transaction id.
const _HEADER_BYTES = 12;

// ---------------------------------------------------------------------------
// Packet construction / parsing helpers
// ---------------------------------------------------------------------------

/**
 * Build a PTP command container packet (no data payload).
 *
 * @param {number} code Operation code.
 * @param {number} txId Transaction id.
 * @param {...number} params Up to five uint32 parameters.
 * @returns {Uint8Array}
 */
export function _commandPacket(code, txId, ...params) {
  const length = _HEADER_BYTES + params.length * 4;
  const packet = new Uint8Array(length);
  const view = new DataView(packet.buffer);
  view.setUint32(0, length, true);
  view.setUint16(4, _PTP_COMMAND, true);
  view.setUint16(6, code, true);
  view.setUint32(8, txId, true);
  params.forEach((param, index) => {
    view.setUint32(_HEADER_BYTES + index * 4, param, true);
  });
  return packet;
}

/**
 * Build a PTP data container packet.
 *
 * @param {number} code Operation code.
 * @param {number} txId Transaction id, the same one its command used.
 * @param {Uint8Array} payload
 * @returns {Uint8Array}
 */
export function _dataPacket(code, txId, payload) {
  const length = _HEADER_BYTES + payload.length;
  const packet = new Uint8Array(length);
  const view = new DataView(packet.buffer);
  view.setUint32(0, length, true);
  view.setUint16(4, _PTP_DATA, true);
  view.setUint16(6, code, true);
  view.setUint32(8, txId, true);
  packet.set(payload, _HEADER_BYTES);
  return packet;
}

/**
 * Parse a PTP response container.
 *
 * Returns an object rather than Python's tuple, which is the one place the
 * shapes differ; callers read .code and .params.
 *
 * @param {Uint8Array} raw
 * @returns {{code: number, params: number[]}}
 */
export function _parseResponse(raw) {
  if (raw.length < _HEADER_BYTES) {
    throw new CameraConnectionError(
      `PTP response too short (${raw.length} bytes); camera may have disconnected.`
    );
  }
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  const length = view.getUint32(0, true);
  const code = view.getUint16(6, true);
  const paramCount = Math.floor((Math.min(length, raw.length) - _HEADER_BYTES) / 4);
  const params = [];
  for (let i = 0; i < paramCount; i += 1) {
    params.push(view.getUint32(_HEADER_BYTES + i * 4, true));
  }
  return { code, params };
}

/**
 * The container type of a packet, or null if it is too short to have one.
 *
 * @param {Uint8Array} raw
 * @returns {number|null}
 */
export function _containerType(raw) {
  if (raw.length < _HEADER_BYTES) return null;
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  return view.getUint16(4, true);
}

/**
 * The transaction id a container belongs to, or null if it is too short.
 *
 * @param {Uint8Array} raw
 * @returns {number|null}
 */
export function _containerTxId(raw) {
  if (raw.length < _HEADER_BYTES) return null;
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  return view.getUint32(8, true);
}

/**
 * The operation or response code a container carries.
 *
 * @param {Uint8Array} raw
 * @returns {number}
 */
export function _containerOpCode(raw) {
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  return view.getUint16(6, true);
}

/** A container type as a word, for logs a person has to read. */
export function _containerName(type) {
  if (type === _PTP_COMMAND) return "command";
  if (type === _PTP_DATA) return "data";
  if (type === _PTP_RESPONSE) return "response";
  return type === null ? "truncated" : `unknown(${type})`;
}

// ---------------------------------------------------------------------------
// PTP string encoding / decoding
// (PTP strings: uint8 numChars + numChars x uint16 UCS-2 LE, NUL included)
// ---------------------------------------------------------------------------

/**
 * Decode a PTP string starting at `offset`.
 *
 * @param {Uint8Array} data
 * @param {number} offset
 * @returns {{value: string, offset: number}}
 */
export function _decodePtpString(data, offset) {
  if (offset >= data.length) {
    return { value: "", offset };
  }
  const numChars = data[offset];
  offset += 1;
  if (numChars === 0) {
    return { value: "", offset };
  }
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const chars = [];
  for (let i = 0; i < numChars; i += 1) {
    chars.push(view.getUint16(offset + i * 2, true));
  }
  offset += numChars * 2;
  // The last unit is the NUL terminator; any other NUL is dropped too, which
  // is what the Python does.
  const value = chars
    .slice(0, -1)
    .filter((c) => c !== 0)
    .map((c) => String.fromCharCode(c))
    .join("");
  return { value, offset };
}

/**
 * Encode a string as a PTP string, NUL terminator included in the count.
 *
 * The empty string is a single zero byte, not a count of one followed by a NUL.
 *
 * @param {string} value
 * @returns {Uint8Array}
 */
export function _encodePtpString(value) {
  if (!value) {
    return new Uint8Array([0]); // numChars = 0
  }
  const chars = [];
  for (let i = 0; i < value.length; i += 1) {
    chars.push(value.charCodeAt(i));
  }
  chars.push(0); // NUL terminated
  const packet = new Uint8Array(1 + chars.length * 2);
  const view = new DataView(packet.buffer);
  view.setUint8(0, chars.length);
  chars.forEach((char, index) => {
    view.setUint16(1 + index * 2, char, true);
  });
  return packet;
}

/**
 * Skip a PTP string and return the new offset.
 *
 * @param {Uint8Array} data
 * @param {number} offset
 * @returns {number}
 */
export function _skipPtpString(data, offset) {
  return _decodePtpString(data, offset).offset;
}

/**
 * Skip a PTP uint16 array (uint32 count + count x uint16).
 *
 * @param {Uint8Array} data
 * @param {number} offset
 * @returns {number}
 */
export function _skipPtpUint16Array(data, offset) {
  if (offset + 4 > data.length) {
    return offset;
  }
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const count = view.getUint32(offset, true);
  return offset + 4 + count * 2;
}

// ---------------------------------------------------------------------------
// DeviceInfo parser
// ---------------------------------------------------------------------------

/**
 * Walk a GetDeviceInfo payload and return two byte offsets.
 *
 * DeviceInfo layout (PIMA 15740:2000 5.5.1):
 *     uint16  StandardVersion
 *     uint32  VendorExtensionID
 *     uint16  VendorExtensionVersion
 *     string  VendorExtensionDesc
 *     uint16  FunctionalMode
 *     array16 OperationsSupported    (uint32 count + count x uint16)
 *     array16 EventsSupported
 *     array16 DevicePropertiesSupported  <- first return value
 *     array16 CaptureFormats
 *     array16 ImageFormats
 *     string  Manufacturer               <- second return value
 *     string  Model
 *
 * @param {Uint8Array} data Including the data-container header.
 * @returns {{propsOffset: number, manufacturerOffset: number}}
 */
export function _deviceInfoOffsets(data) {
  let off = _HEADER_BYTES; // skip data-container header
  off += 2 + 4 + 2; // StandardVersion, VendorExtensionID, VendorExtensionVersion
  off = _skipPtpString(data, off); // VendorExtensionDesc
  off += 2; // FunctionalMode
  off = _skipPtpUint16Array(data, off); // OperationsSupported
  off = _skipPtpUint16Array(data, off); // EventsSupported
  const propsOffset = off;
  off = _skipPtpUint16Array(data, off); // DevicePropertiesSupported
  off = _skipPtpUint16Array(data, off); // CaptureFormats
  off = _skipPtpUint16Array(data, off); // ImageFormats
  return { propsOffset, manufacturerOffset: off };
}

/**
 * Extract the Model string from a GetDeviceInfo payload.
 *
 * @param {Uint8Array} data
 * @returns {string}
 */
export function _parseDeviceInfoModel(data) {
  const { manufacturerOffset } = _deviceInfoOffsets(data);
  const off = _skipPtpString(data, manufacturerOffset); // Manufacturer
  return _decodePtpString(data, off).value;
}

/**
 * Extract DevicePropertiesSupported codes from a GetDeviceInfo payload.
 *
 * @param {Uint8Array} data
 * @returns {number[]}
 */
export function _parseDeviceInfoSupportedProps(data) {
  const { propsOffset } = _deviceInfoOffsets(data);
  if (propsOffset + 4 > data.length) {
    return [];
  }
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const count = view.getUint32(propsOffset, true);
  const off = propsOffset + 4;
  if (count === 0 || off + count * 2 > data.length) {
    return [];
  }
  const props = [];
  for (let i = 0; i < count; i += 1) {
    props.push(view.getUint16(off + i * 2, true));
  }
  return props;
}

// ---------------------------------------------------------------------------
// Endpoint discovery
// ---------------------------------------------------------------------------

/**
 * Find the interface carrying a bulk endpoint in each direction.
 *
 * PTP needs exactly that pair, and the interface that has both is the one worth
 * claiming. Searching rather than assuming interface 0 is a deliberate
 * improvement on the Python, which hardcodes (0, 0); the browser hands us the
 * full descriptor, so there is no reason to guess.
 *
 * @param {USBDevice} device An opened device with a selected configuration.
 * @returns {{interfaceNumber: number, inEndpoint: number, outEndpoint: number}|null}
 */
export function _findBulkInterface(device) {
  const configuration = device.configuration;
  if (!configuration) {
    return null;
  }
  for (const iface of configuration.interfaces) {
    for (const alternate of iface.alternates) {
      const bulk = alternate.endpoints.filter((e) => e.type === "bulk");
      const inEndpoint = bulk.find((e) => e.direction === "in");
      const outEndpoint = bulk.find((e) => e.direction === "out");
      if (inEndpoint && outEndpoint) {
        return {
          interfaceNumber: iface.interfaceNumber,
          inEndpoint: inEndpoint.endpointNumber,
          outEndpoint: outEndpoint.endpointNumber,
        };
      }
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// ClientPTPUSBDevice
// ---------------------------------------------------------------------------

/** A uint16 payload, little-endian, as every cursor write needs. */
function _uint16(value) {
  const payload = new Uint8Array(2);
  new DataView(payload.buffer).setUint16(0, value & 0xffff, true);
  return payload;
}

/** Milliseconds since page load, for timing the handshake. */
function _now() {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

/** Resolve after `seconds`. Replaced in tests so delays cost nothing. */
function _realSleep(seconds) {
  return new Promise((resolve) => setTimeout(resolve, seconds * 1000));
}

export class ClientPTPUSBDevice {
  /**
   * @param {object} options
   * @param {USBDevice} options.usbDevice A device the user has already granted.
   * @param {object} options.config The client config, as served by the server.
   * @param {(seconds: number) => Promise<void>} [options.sleep]
   * @param {number} [options.timeoutMs] How long a transfer may take. Injected
   *   so tests can shrink it; a suite that waits out real five-second timeouts
   *   stops being run.
   */
  constructor({ usbDevice, config, sleep = _realSleep, timeoutMs = undefined }) {
    this._usbDevice = usbDevice;
    this._config = config;
    this._sleep = sleep;
    this._timeoutMs =
      timeoutMs ?? config?.settings?.CAMERA_USB_TIMEOUT_MS ?? _USB_TIMEOUT_MS;
    this._inEndpoint = null;
    this._outEndpoint = null;
    this._interfaceNumber = null;
    this._txId = 1;
    this._cameraName = "";
    /** The transaction a timed-out transfer left outstanding, if any. */
    this._stalledTxId = null;
    /** Consecutive stalls, reset by any transfer that completes. */
    this._stallCount = 0;
    /** Guards against recovery re-entering itself through its own transfers. */
    this._recovering = false;
    /** The last slot the cursor was pointed at, to restore after a reopen. */
    this._cursorSlot = null;
  }

  get cameraName() {
    return this._cameraName;
  }

  // ------------------------------------------------------------------
  // CameraDevice contract
  // ------------------------------------------------------------------

  /**
   * Open the device, claim its PTP interface, start a session and read the
   * model name.
   *
   * @returns {Promise<void>}
   */
  async connect() {
    if (!this._usbDevice) {
      throw new CameraConnectionError("No camera was selected.");
    }
    const startedAt = _now();
    try {
      await this._step("open", () => this._usbDevice.open());
      if (this._usbDevice.configuration === null) {
        await this._step("selectConfiguration", () =>
          this._usbDevice.selectConfiguration(1)
        );
      }
    } catch (error) {
      throw new CameraConnectionError(
        `Could not open the camera: ${error}. On Linux this is usually a udev ` +
          "rule, or another program holding the device."
      );
    }
    await this._step("claimInterface", () => this._claimInterface());
    this._txId = 1;
    await this._step("openSession", () => this._openSession());
    this._cameraName = await this._step("getDeviceInfo", () => this._fetchCameraName());
    publishEvent({
      eventType: SESSION_OPENED,
      camera: this._cameraName || "(model not reported)",
      durationMs: Math.round(_now() - startedAt),
    });
  }

  /**
   * Run one step of the session handshake, recording it either way.
   *
   * Connecting is the one part of a push where nothing else is written down, so
   * a failure here used to leave no trace at all: the console showed the reads
   * from the previous successful attempt and nothing from the failed one. The
   * step name is what says whether the device would not open, would not be
   * claimed, or would not start a session, and those have entirely different
   * causes.
   */
  async _step(name, fn) {
    publishEvent({ eventType: SESSION_STEP, step: name });
    const startedAt = _now();
    try {
      return await fn();
    } catch (error) {
      publishEvent({
        eventType: SESSION_FAILED,
        step: name,
        error: `${error?.name ?? "Error"}: ${error?.message ?? error}`,
        durationMs: Math.round(_now() - startedAt),
      });
      throw error;
    }
  }

  /**
   * Close the session and release the device. Never throws.
   *
   * @returns {Promise<void>}
   */
  async disconnect() {
    const device = this._usbDevice;
    if (!device) {
      return;
    }
    try {
      await this._send(_commandPacket(_OC_CLOSE_SESSION, this._nextTx()));
      await this._recvResponse();
    } catch {
      // The camera may already be gone; there is nothing useful to do.
    }
    try {
      if (this._interfaceNumber !== null) {
        await device.releaseInterface(this._interfaceNumber);
      }
    } catch {
      // Ignore: releasing a device that vanished is not a failure.
    }
    try {
      await device.close();
    } catch {
      // Ignore, as above.
    }
    this._usbDevice = null;
    this._inEndpoint = null;
    this._outEndpoint = null;
    this._interfaceNumber = null;
    publishEvent({ eventType: SESSION_CLOSED });
  }

  // ------------------------------------------------------------------
  // Internals
  // ------------------------------------------------------------------

  _nextTx() {
    const tx = this._txId;
    this._txId += 1;
    this._currentTx = tx;
    return tx;
  }

  /**
   * Warn if a container belongs to an earlier transaction than the one in hand.
   *
   * A timeout leaves a request unanswered. If the camera were merely late
   * rather than having dropped the request, its reply would arrive during the
   * next exchange and every container after that would be one behind, which on
   * the write path means confirming a property the camera refused.
   *
   * Retrying in place is what the server does and what works on real hardware,
   * so the evidence says the camera drops the request and no stale reply
   * exists. This checks that rather than assuming it: it costs a comparison,
   * and if the assumption is ever wrong it says so out loud instead of quietly
   * returning the wrong value.
   */
  _checkTxId(raw, phase) {
    const txId = _containerTxId(raw);
    if (txId === null || this._currentTx === undefined) return;
    if (txId !== this._currentTx) {
      publishEvent({
        eventType: PTP_TX_MISMATCH,
        phase,
        expected: this._currentTx,
        received: txId,
      });
      console.warn(
        `Camera replied about transaction ${txId} while ${this._currentTx} was ` +
          "in flight. A reply arrived late and the stream is out of step; the " +
          "value just read belongs to an earlier request."
      );
    }
  }

  /**
   * Race a transfer against the timeout PyUSB would have applied.
   *
   * @template T
   * @param {Promise<T>} transfer
   * @param {string} what Named in the error, so a failure says which phase.
   * @returns {Promise<T>}
   */
  async _withTimeout(transfer, what) {
    let timer;
    const expiry = new Promise((_, reject) => {
      timer = setTimeout(() => {
        // WebUSB cannot cancel a transfer. This abandons the promise, but the
        // read stays queued in the browser and the camera will never complete
        // it, so every later read queues behind a transfer that cannot finish.
        // That is why writes keep succeeding while every read times out, and
        // why retrying in place recovers on the server and cannot here.
        // Recorded so the next transfer clears it first.
        this._stalledTxId = this._currentTx ?? 0;
        this._stallCount += 1;
        reject(
          new CameraConnectionError(
            `USB ${what} timed out after ${this._timeoutMs} ms; the camera stopped responding.`
          )
        );
      }, this._timeoutMs);
    });
    try {
      return await Promise.race([transfer, expiry]);
    } finally {
      // Without this the pending timer keeps the process alive, which turns a
      // passing test suite into one that never exits.
      clearTimeout(timer);
    }
  }

  _assertConnected() {
    if (!this._usbDevice) {
      throw new CameraConnectionError("The camera is not connected.");
    }
  }

  /**
   * @param {Uint8Array} packet
   * @returns {Promise<void>}
   */
  async _send(packet) {
    this._assertConnected();
    await this._recoverIfStalled();
    publishTrace({
      eventType: PTP_SENT,
      container: _containerName(_containerType(packet)),
      op: formatCode(_containerOpCode(packet)),
      txId: _containerTxId(packet),
      bytes: packet.length,
    });
    const startedAt = _now();
    let result;
    try {
      result = await this._withTimeout(
        this._usbDevice.transferOut(this._outEndpoint, packet),
        "write"
      );
    } catch (error) {
      if (error instanceof CameraConnectionError) throw error;
      throw new CameraConnectionError(`USB write failed: ${error}`);
    }
    if (result.status !== "ok") {
      await this._clearHalt("out", this._outEndpoint);
      throw new CameraConnectionError(`USB write failed: endpoint ${result.status}`);
    }
    publishTrace({
      eventType: PTP_RECEIVED,
      phase: "write ack",
      durationMs: Math.round(_now() - startedAt),
    });
  }

  /**
   * Read a container from the camera.
   *
   * @param {number} length
   * @param {string} what
   * @returns {Promise<Uint8Array>}
   */
  async _read(length, what) {
    this._assertConnected();
    await this._recoverIfStalled();
    const startedAt = _now();
    let result;
    try {
      result = await this._withTimeout(
        this._usbDevice.transferIn(this._inEndpoint, length),
        `read (${what})`
      );
    } catch (error) {
      if (error instanceof CameraConnectionError) throw error;
      throw new CameraConnectionError(`USB read (${what}) failed: ${error}`);
    }
    if (result.status !== "ok") {
      await this._clearHalt("in", this._inEndpoint);
      throw new CameraConnectionError(`USB read (${what}) failed: endpoint ${result.status}`);
    }
    this._stallCount = 0;
    const data = result.data;
    const raw = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
    publishTrace({
      eventType: PTP_RECEIVED,
      phase: what,
      container: _containerName(_containerType(raw)),
      op: raw.length >= _HEADER_BYTES ? formatCode(_containerOpCode(raw)) : null,
      txId: _containerTxId(raw),
      bytes: raw.length,
      durationMs: Math.round(_now() - startedAt),
    });
    return raw;
  }

  /**
   * Free the IN endpoint after a timeout, so a retry can actually read.
   *
   * Without this a retry is theatre: the abandoned transfer still owns the
   * endpoint and the new read waits behind it until it too times out. The
   * protocol's own answer is a Cancel Request on endpoint 0, which reaches the
   * camera even while the bulk endpoint is blocked. If the camera will not come
   * back that way, reopening the device does it the hard way, because closing
   * rejects every pending transfer.
   */
  async _recoverIfStalled() {
    if (this._stalledTxId === null) return;
    // Recovery talks to the camera, and those transfers can stall too. Without
    // this it would recurse into itself and each level would start another
    // reset.
    if (this._recovering) return;
    const txId = this._stalledTxId;
    this._stalledTxId = null;
    this._recovering = true;
    try {
      await this._recover(txId);
    } finally {
      this._recovering = false;
    }
  }

  async _recover(txId) {

    // Escalate rather than trust the camera's own account of itself. A device
    // that answers Get Device Status is not necessarily one whose IN endpoint
    // has been freed, and believing it turns one stall into a loop of them.
    // A second stall with no completed read in between means cancelling did
    // not work, whatever the camera said.
    if (this._stallCount <= 1) {
      publishEvent({ eventType: SESSION_STEP, step: "cancelStalledTransaction", txId });
      if (await this._cancelTransaction(txId)) {
        return;
      }
    }
    publishEvent({
      eventType: SESSION_STEP,
      step: "reopenAfterStall",
      txId,
      stalls: this._stallCount,
    });
    await this._reopen();
  }

  /**
   * Read and discard whatever the camera still had to say.
   *
   * A cancelled transaction can leave its data and response queued. Reading
   * past them is what stops the next request collecting an answer to the last
   * one, which the transaction id check would otherwise report as a mismatch
   * for the rest of the session.
   */
  async _drain() {
    for (let i = 0; i < 4; i += 1) {
      let result;
      try {
        result = await this._withTimeout(
          this._usbDevice.transferIn(this._inEndpoint, _READ_BUFFER),
          "drain"
        );
      } catch {
        // Nothing left, which is the outcome we want.
        this._stalledTxId = null;
        return;
      }
      if (!result.data || result.data.byteLength === 0) return;
      publishTrace({
        eventType: PTP_RECEIVED,
        phase: "drained",
        bytes: result.data.byteLength,
      });
    }
  }

  /**
   * Ask the camera to abandon a transaction, and wait for it to say it has.
   *
   * @returns {Promise<boolean>} Whether the camera reported itself ready.
   */
  async _cancelTransaction(txId) {
    const payload = new Uint8Array(6);
    const view = new DataView(payload.buffer);
    view.setUint16(0, _CANCELLATION_CODE, true);
    view.setUint32(2, txId, true);
    try {
      await this._withTimeout(
        this._usbDevice.controlTransferOut(
          {
            requestType: "class",
            recipient: "interface",
            request: _REQ_CANCEL,
            value: 0,
            index: this._interfaceNumber,
          },
          payload
        ),
        "cancel"
      );
      const ready = await this._waitUntilReady();
      await this._clearHalt("in", this._inEndpoint);
      await this._clearHalt("out", this._outEndpoint);
      const drainTimeout = this._timeoutMs;
      this._timeoutMs = Math.min(200, drainTimeout);
      try {
        await this._drain();
      } finally {
        this._timeoutMs = drainTimeout;
      }
      this._stalledTxId = null;
      publishEvent({ eventType: SESSION_STEP, step: "cancelled", ready });
      return ready;
    } catch (error) {
      publishEvent({
        eventType: SESSION_FAILED,
        step: "cancelStalledTransaction",
        error: `${error?.name ?? "Error"}: ${error?.message ?? error}`,
      });
      // The stall flag was already cleared, and _withTimeout may have set it
      // again on the control transfer. Drop it: reopening supersedes it.
      this._stalledTxId = null;
      return false;
    }
  }

  /**
   * Reset the camera's PTP stack, closing whatever session it still holds.
   *
   * Best effort: a camera that will not accept this is one a reopen was never
   * going to rescue either, and the caller has a failure to report regardless.
   */
  async _resetDevice() {
    publishEvent({ eventType: SESSION_STEP, step: "deviceReset" });
    try {
      await this._withTimeout(
        this._usbDevice.controlTransferOut({
          requestType: "class",
          recipient: "interface",
          request: _REQ_DEVICE_RESET,
          value: 0,
          index: this._interfaceNumber,
        }),
        "device reset"
      );
      const ready = await this._waitUntilReady();
      publishEvent({ eventType: SESSION_STEP, step: "deviceResetDone", ready });
    } catch (error) {
      publishEvent({
        eventType: SESSION_FAILED,
        step: "deviceReset",
        error: `${error?.name ?? "Error"}: ${error?.message ?? error}`,
      });
    }
    this._stalledTxId = null;
  }

  /** Poll Get Device Status until the camera stops reporting itself busy. */
  async _waitUntilReady(attempts = 5) {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const result = await this._usbDevice.controlTransferIn(
        {
          requestType: "class",
          recipient: "interface",
          request: _REQ_GET_DEVICE_STATUS,
          value: 0,
          index: this._interfaceNumber,
        },
        4
      );
      if (result.status === "ok" && result.data && result.data.byteLength >= 4) {
        const code = result.data.getUint16(2, true);
        if (code !== _RC_DEVICE_BUSY) return true;
      }
      await this._sleep(0.05);
    }
    return false;
  }

  /**
   * Close and reopen the device, which is the only certain way to drop a
   * transfer WebUSB will not cancel.
   *
   * The slot cursor does not survive this: it is connection state, and every
   * later read or write goes to whichever slot the camera is pointing at. It is
   * restored here rather than left to callers, because a caller that forgets
   * does not fail, it writes a recipe into the wrong slot.
   */
  async _reopen() {
    const device = this._usbDevice;
    try {
      if (this._interfaceNumber !== null) await device.releaseInterface(this._interfaceNumber);
    } catch {
      // Already gone; closing below is what matters.
    }
    try {
      await device.close();
    } catch {
      // As above.
    }
    await device.open();
    if (device.configuration === null) await device.selectConfiguration(1);
    await this._claimInterface();

    // Reopening the USB device does not touch the camera's PTP state, which
    // lives above it. Observed on an X-S10: after a full close and reopen the
    // camera still answered OpenSession with SessionAlreadyOpen, still holding
    // the session its stuck transaction belonged to, and still refused to
    // answer the write that stalled. Reads worked; that one write did not.
    //
    // Device Reset is the class request for this. It resets the camera's PTP
    // stack, which Cancel does not: Cancel abandons a transaction and the
    // camera cheerfully reports itself ready while remaining stuck.
    await this._resetDevice();

    this._txId = 1;
    this._stalledTxId = null;
    this._stallCount = 0;
    await this._openSession();
    if (this._cursorSlot !== null) {
      const slot = this._cursorSlot;
      publishEvent({ eventType: SESSION_STEP, step: "restoreSlotCursor", slot });
      try {
        await this._setProp(this._config.encodings.prop_slot_cursor, _uint16(slot));
      } catch (error) {
        // Best effort. If the cursor write is itself what stalled, restoring it
        // here walks straight back into the same wall, and the caller is about
        // to retry that exact write anyway. Failing the reopen over it would
        // turn a recoverable stall into an abandoned session.
        publishEvent({
          eventType: SESSION_FAILED,
          step: "restoreSlotCursor",
          error: `${error?.name ?? "Error"}: ${error?.message ?? error}`,
        });
        this._stalledTxId = null;
        this._stallCount = 0;
      }
    }
  }

  async _clearHalt(direction, endpoint) {
    try {
      await this._usbDevice.clearHalt(direction, endpoint);
    } catch {
      // Best effort: if the halt cannot be cleared the caller is going to
      // reconnect anyway, and the original failure is the useful one.
    }
  }

  /**
   * Receive a data container from the camera (may be empty).
   *
   * @returns {Promise<Uint8Array>}
   */
  async _recvData() {
    const raw = await this._read(_READ_BUFFER, "data");
    const type = raw.length >= _HEADER_BYTES ? _containerType(raw) : null;
    // What the camera actually sent, which is the one thing a stalled read
    // leaves no evidence of. Cheap, and it distinguishes a short reply from a
    // missing one without anybody having to guess.
    publishEvent({
      eventType: PTP_CONTAINER,
      phase: "data",
      bytes: raw.length,
      container: _containerName(type),
      txId: _containerTxId(raw),
    });
    this._checkTxId(raw, "data");

    if (type === _PTP_RESPONSE) {
      // The camera answered without a data phase. Its response is in hand, so
      // there is nothing further to read: asking for one anyway waits out the
      // full timeout and then poisons the connection. The Python has the same
      // shape and the same latent stall.
      const { code, params } = _parseResponse(raw);
      if (code !== _RC_OK) {
        throw new CameraConnectionError(
          `PTP error ${formatCode(code)} (no data phase)`
        );
      }
      return { data: new Uint8Array(0), response: { code, params } };
    }
    return { data: raw, response: null };
  }

  /**
   * @returns {Promise<{code: number, params: number[]}>}
   */
  async _recvResponse() {
    const raw = await this._read(64, "response");
    this._checkTxId(raw, "response");
    const parsed = _parseResponse(raw);
    publishTrace({
      eventType: PTP_CONTAINER,
      phase: "response",
      rc: formatCode(parsed.code),
      txId: _containerTxId(raw),
      bytes: raw.length,
    });
    return parsed;
  }

  /**
   * @param {number} code
   * @param {string} context
   */
  _checkRc(code, context) {
    if (code === _RC_OK) {
      return;
    }
    throw new CameraConnectionError(`PTP error ${formatCode(code)} during ${context}`);
  }

  async _claimInterface() {
    const target = _findBulkInterface(this._usbDevice);
    if (target === null) {
      throw new CameraConnectionError(
        "Could not find PTP bulk USB endpoints on this device. " +
          "Is the camera in a PTP-compatible USB mode?"
      );
    }
    try {
      await this._usbDevice.claimInterface(target.interfaceNumber);
    } catch (error) {
      throw new CameraConnectionError(
        `Could not claim the camera's USB interface: ${error}. ` +
          "Another program may be holding it."
      );
    }
    this._interfaceNumber = target.interfaceNumber;
    this._inEndpoint = target.inEndpoint;
    this._outEndpoint = target.outEndpoint;
  }

  async _openSession() {
    await this._send(_commandPacket(_OC_OPEN_SESSION, this._nextTx(), _SESSION_ID));
    const { code } = await this._recvResponse();
    if (code !== _RC_OK && code !== _RC_SESSION_ALREADY) {
      throw new CameraConnectionError(
        `PTP OpenSession failed with code ${formatCode(code)}. ` +
          "The camera may be in the wrong USB mode."
      );
    }
  }

  /**
   * Read the camera model via GetDeviceInfo. Returns "" if anything goes wrong,
   * because the model is only used to decide how many slots to offer.
   *
   * @returns {Promise<string>}
   */
  async _fetchCameraName() {
    try {
      await this._send(_commandPacket(_OC_GET_DEVICE_INFO, this._nextTx()));
      const { data, response } = await this._recvData();
      if (response !== null) {
        throw new CameraConnectionError("Camera sent no device info");
      }
      const { code } = await this._recvResponse();
      if (code !== _RC_OK) {
        return "";
      }
      const model = _parseDeviceInfoModel(data);
      if (!model) {
        // Not an exception: a truncated or unexpected payload parses to an
        // empty string quite happily. Recorded anyway, because an empty model
        // means zero slots and the user is then told this camera has no custom
        // slots when the truth is that its reply made no sense.
        publishEvent({
          eventType: SESSION_FAILED,
          step: "getDeviceInfo",
          error: "the camera's device info carried no model name",
        });
      }
      return model;
    } catch (error) {
      // Swallowed deliberately, as the Python does: the model only decides how
      // many slots to offer. But it is recorded, because an empty model means
      // zero slots, and the user is then told this camera has no custom slots
      // when the truth is that it stopped answering.
      publishEvent({
        eventType: SESSION_FAILED,
        step: "getDeviceInfo",
        error: `${error?.name ?? "Error"}: ${error?.message ?? error}`,
      });
      return "";
    }
  }
}

// ---------------------------------------------------------------------------
// Property accessors
// ---------------------------------------------------------------------------

/**
 * Read one of the timing or retry settings, refusing to guess.
 *
 * A missing key means the served config and this code have diverged. Defaulting
 * would paper over that and leave the browser writing on timings the server
 * never chose, which is the exact failure the shared config exists to prevent.
 *
 * @param {object} config
 * @param {string} name
 * @returns {number|boolean}
 */
function _setting(config, name) {
  const settings = config && config.settings;
  if (!settings || !(name in settings)) {
    throw new CameraConnectionError(
      `Camera setting ${name} missing from the client config; the server and ` +
        "the browser are out of step."
    );
  }
  return settings[name];
}

Object.assign(ClientPTPUSBDevice.prototype, {
  /**
   * Read 0xD023 (GrainEffect, doubling as a liveness register).
   *
   * @returns {Promise<number>} 0 if alive, -1 if not.
   */
  async ping() {
    try {
      await this.getPropertyInt(this._config.encodings.prop_ping);
      return 0;
    } catch (error) {
      if (error instanceof CameraConnectionError) return -1;
      throw error;
    }
  },

  /**
   * Read a property as a signed 32-bit integer.
   *
   * @param {number} code
   * @returns {Promise<number>}
   */
  async getPropertyInt(code) {
    let data;
    try {
      data = await this._getPropWithRetry(code);
    } catch (error) {
      publishEvent({
        eventType: PTP_READ_FAILED,
        prop: formatCode(code),
        error: String(error.message ?? error),
      });
      throw error;
    }
    await this._sleep(_setting(this._config, "CAMERA_POST_READ_DELAY_S"));

    // The value follows the 12-byte container header. Most Fuji recipe
    // properties are uint16, but the payload is read as int32 when four bytes
    // are there, which is what makes negatives come back correctly.
    const payload = data.subarray(_HEADER_BYTES);
    const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
    let value;
    if (payload.length >= 4) {
      value = view.getInt32(0, true);
    } else if (payload.length >= 2) {
      value = view.getUint16(0, true);
    } else if (payload.length >= 1) {
      value = payload[0];
    } else {
      value = 0;
    }

    publishEvent({ eventType: PTP_READ_SUCCEEDED, prop: formatCode(code), value });
    return value;
  },

  /**
   * Read a property whose value is a signed 16-bit integer.
   *
   * The camera zero-extends int16 values into a four-byte payload, so a raw
   * read of -10 comes back as 65526. Reinterpreting the low sixteen bits is
   * what makes white balance shifts and tone curves read correctly.
   *
   * @param {number} code
   * @returns {Promise<number>}
   */
  async getPropertyInt16(code) {
    const raw = await this.getPropertyInt(code);
    const v = raw & 0xffff;
    return v >= 32768 ? v - 65536 : v;
  },

  /**
   * Read a property as a PTP string.
   *
   * @param {number} code
   * @returns {Promise<string>}
   */
  async getPropertyString(code) {
    let data;
    try {
      data = await this._getPropWithRetry(code);
    } catch (error) {
      publishEvent({
        eventType: PTP_READ_FAILED,
        prop: formatCode(code),
        error: String(error.message ?? error),
      });
      throw error;
    }
    await this._sleep(_setting(this._config, "CAMERA_POST_READ_DELAY_S"));
    const { value } = _decodePtpString(data, _HEADER_BYTES);
    publishEvent({ eventType: PTP_READ_SUCCEEDED, prop: formatCode(code), value });
    return value;
  },

  /**
   * Write a 32-bit signed integer property.
   *
   * @param {number} code
   * @param {number} value
   * @returns {Promise<number>} 0 on success, otherwise the camera's response code.
   */
  async setPropertyInt(code, value) {
    const payload = new Uint8Array(4);
    new DataView(payload.buffer).setInt32(0, value, true);
    return this._setProp(code, payload);
  },

  /**
   * Write a uint16 property. Used for the slot cursor.
   *
   * @param {number} code
   * @param {number} value
   * @returns {Promise<number>}
   */
  async setPropertyUint16(code, value) {
    if (code === this._config?.encodings?.prop_slot_cursor) {
      this._cursorSlot = value;
    }
    return this._setProp(code, _uint16(value));
  },

  /**
   * Write a PTP string property. Used for the slot name.
   *
   * @param {number} code
   * @param {string} value
   * @returns {Promise<number>}
   */
  async setPropertyString(code, value) {
    return this._setProp(code, _encodePtpString(value));
  },

  /**
   * List the property codes GetDeviceInfo reports.
   *
   * Returns [] on any failure, because callers treat it as optional: it is a
   * diagnostic, not something the push path depends on.
   *
   * @returns {Promise<number[]>}
   */
  async supportedProperties() {
    try {
      await this._send(_commandPacket(_OC_GET_DEVICE_INFO, this._nextTx()));
      const { data, response } = await this._recvData();
      if (response !== null) {
        return [];
      }
      const { code } = await this._recvResponse();
      if (code !== _RC_OK) {
        return [];
      }
      return _parseDeviceInfoSupportedProps(data);
    } catch {
      return [];
    }
  },

  /**
   * Send GetDevicePropValue and return the raw data, retrying transport failures.
   *
   * Reads only. Writes are deliberately not retried at this level: a rejected
   * write is a decision the camera made, and repeating it would not change the
   * answer. Retrying writes is the operations layer's job, and only for
   * transport failures.
   *
   * @param {number} code
   * @returns {Promise<Uint8Array>}
   */
  async _getPropWithRetry(code) {
    const maxAttempts = _setting(this._config, "CAMERA_MAX_RETRIES");
    const backoff = _setting(this._config, "CAMERA_RETRY_BACKOFF_S");
    let lastError = new CameraConnectionError("No retries attempted");
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      if (attempt > 0) {
        await this._sleep(backoff * 2 ** (attempt - 1));
      }
      try {
        // As in _setProp: the id has to be taken after any recovery, or it
        // refers to a numbering the camera has since abandoned.
        await this._recoverIfStalled();
        await this._send(
          _commandPacket(_OC_GET_DEVICE_PROP_VALUE, this._nextTx(), code)
        );
        const { data, response } = await this._recvData();
        if (response !== null) {
          // The camera acknowledged the read and sent no value with it. That
          // is not an answer, so it must not be reported as one: an empty
          // payload decodes to 0, which is a legitimate value for most of these
          // properties and would show as a real setting or be written to a slot.
          //
          // Retrying is what recovers, and the server reaches the same outcome
          // by accident. It re-reads for a response that has already arrived,
          // waits out the full timeout, and its retry loop then asks again.
          // This takes the same decision in milliseconds rather than seconds.
          throw new CameraConnectionError(
            `Camera answered ${formatCode(code)} with no value ` +
              `(rc=${formatRc(response.code)})`
          );
        }
        const { code: rc } = await this._recvResponse();
        this._checkRc(rc, `GetDevicePropValue(${formatCode(code)})`);
        return data;
      } catch (error) {
        if (!(error instanceof CameraConnectionError)) throw error;
        // Published per attempt, so a read that eventually succeeds still shows
        // that the camera needed asking twice. Only the final failure was
        // recorded before, which made a flaky camera look like a healthy one.
        publishEvent({
          eventType: PTP_READ_RETRY,
          prop: formatCode(code),
          attempt: `${attempt + 1}/${maxAttempts}`,
          error: error.message,
        });
        lastError = error;
      }
    }
    throw lastError;
  },

  /**
   * Write a property and return the camera's response code.
   *
   * Returns rather than throws, mirroring the Python. A non-zero rc means the
   * camera considered the request and refused it, which is a different thing
   * from the transport failing, and only the caller knows whether to give up.
   *
   * @param {number} code
   * @param {Uint8Array} payload
   * @returns {Promise<number>} 0 on success, otherwise the response code.
   */
  async _setProp(code, payload) {
    // Recover before taking a transaction id, not after. A reopen restarts the
    // camera's numbering from 1, so an id taken beforehand goes out stale: the
    // camera accepts it, but the exchange no longer matches the numbering
    // either side believes it is using, and the mismatch check reports every
    // reply from then on.
    await this._recoverIfStalled();
    const tx = this._nextTx();
    await this._send(_commandPacket(_OC_SET_DEVICE_PROP_VALUE, tx, code));
    await this._send(_dataPacket(_OC_SET_DEVICE_PROP_VALUE, tx, payload));
    const { code: rc } = await this._recvResponse();
    if (rc === _RC_OK) {
      publishEvent({ eventType: PTP_WRITE_SUCCEEDED, prop: formatCode(code) });
      return 0;
    }
    publishEvent({
      eventType: PTP_WRITE_FAILED,
      prop: formatCode(code),
      rc: formatCode(rc),
    });
    return rc;
  },
});
