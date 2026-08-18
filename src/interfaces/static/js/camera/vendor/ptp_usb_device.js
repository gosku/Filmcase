/**
 * PTP over WebUSB.
 *
 * Ports src/domain/camera/ptp_usb_device.py. Names match that file so the two
 * can be read side by side: the leading underscores are kept even though they
 * mean nothing here, and snake_case becomes camelCase and nothing else.
 *
 * This file currently holds the packet helpers. The transport class follows.
 */

import { CameraConnectionError } from "./ptp_device.js";

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

export const _USB_TIMEOUT_MS = 5000; // 5 s, camera can be slow to respond
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
