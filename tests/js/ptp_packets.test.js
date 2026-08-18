/**
 * JavaScript half of the shared PTP wire-format golden vectors.
 *
 * The Python transport asserts against the same file. Between them these tests
 * say: both implementations put identical bytes on the wire.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  _commandPacket,
  _dataPacket,
  _decodePtpString,
  _deviceInfoOffsets,
  _encodePtpString,
  _parseDeviceInfoModel,
  _parseDeviceInfoSupportedProps,
  _parseResponse,
  _skipPtpString,
  _skipPtpUint16Array,
} from "../../src/interfaces/static/js/camera/vendor/ptp_usb_device.js";
import { CameraConnectionError } from "../../src/interfaces/static/js/camera/vendor/ptp_device.js";

const FIXTURE = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../fixtures/camera/ptp_vectors.json", import.meta.url)),
    "utf8"
  )
);

/** @param {Uint8Array} bytes */
function toHex(bytes) {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** @param {string} hex */
function fromHex(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

describe("_commandPacket", () => {
  for (const vector of FIXTURE.command_packets) {
    it(`matches the frozen bytes: ${vector.name}`, () => {
      const packet = _commandPacket(vector.code, vector.tx_id, ...vector.params);

      assert.equal(toHex(packet), vector.hex);
    });
  }
});

describe("_dataPacket", () => {
  for (const vector of FIXTURE.data_packets) {
    it(`matches the frozen bytes: ${vector.name}`, () => {
      const packet = _dataPacket(vector.code, vector.tx_id, fromHex(vector.payload_hex));

      assert.equal(toHex(packet), vector.hex);
    });
  }
});

describe("_encodePtpString", () => {
  for (const vector of FIXTURE.ptp_strings) {
    it(`encodes to the frozen bytes: ${vector.name}`, () => {
      assert.equal(toHex(_encodePtpString(vector.value)), vector.hex);
    });
  }
});

describe("_decodePtpString", () => {
  for (const vector of FIXTURE.ptp_strings) {
    it(`round trips back to the original: ${vector.name}`, () => {
      const encoded = fromHex(vector.hex);

      const { value, offset } = _decodePtpString(encoded, 0);

      assert.equal(value, vector.value);
      assert.equal(offset, encoded.length);
    });
  }

  it("returns an empty string when the offset is past the end", () => {
    const { value, offset } = _decodePtpString(new Uint8Array([1, 2]), 5);

    assert.equal(value, "");
    assert.equal(offset, 5);
  });

  it("advances past a zero-length string without consuming characters", () => {
    // A zero count is one byte and no payload; reading two more would slide
    // every later field along and silently corrupt the whole walk.
    const { value, offset } = _decodePtpString(new Uint8Array([0, 0xaa]), 0);

    assert.equal(value, "");
    assert.equal(offset, 1);
  });
});

describe("_parseResponse", () => {
  for (const vector of FIXTURE.responses) {
    it(`parses to the frozen code and params: ${vector.name}`, () => {
      const { code, params } = _parseResponse(fromHex(vector.hex));

      assert.equal(code, vector.expected_code);
      assert.deepEqual(params, vector.expected_params);
    });
  }

  it("throws a connection error on a truncated container", () => {
    // A short read means the camera went away mid-transaction; treating it as a
    // parse failure would report the wrong cause and skip the retry.
    assert.throws(
      () => _parseResponse(new Uint8Array([1, 2, 3])),
      (error) => error instanceof CameraConnectionError
    );
  });

  it("reports the length it actually got, so the failure is diagnosable", () => {
    assert.throws(
      () => _parseResponse(new Uint8Array(3)),
      /PTP response too short \(3 bytes\)/
    );
  });
});

describe("_parseDeviceInfoModel", () => {
  for (const vector of FIXTURE.device_info) {
    it(`finds the model name: ${vector.name}`, () => {
      assert.equal(_parseDeviceInfoModel(fromHex(vector.hex)), vector.expected_model);
    });
  }
});

describe("_parseDeviceInfoSupportedProps", () => {
  for (const vector of FIXTURE.device_info) {
    it(`finds the supported properties: ${vector.name}`, () => {
      assert.deepEqual(
        _parseDeviceInfoSupportedProps(fromHex(vector.hex)),
        vector.expected_supported_props
      );
    });
  }
});

describe("_skipPtpUint16Array", () => {
  it("skips the count and its entries", () => {
    // uint32 count of 2, then two uint16 values.
    const data = new Uint8Array([2, 0, 0, 0, 0x11, 0x11, 0x22, 0x22, 0xff]);

    assert.equal(_skipPtpUint16Array(data, 0), 8);
  });

  it("skips an empty array as four bytes", () => {
    const data = new Uint8Array([0, 0, 0, 0, 0xff]);

    assert.equal(_skipPtpUint16Array(data, 0), 4);
  });

  it("stops rather than running past the end of a truncated payload", () => {
    // Returning the offset unchanged is what lets the DeviceInfo walk bail out
    // instead of reading whatever memory follows.
    const data = new Uint8Array([2, 0]);

    assert.equal(_skipPtpUint16Array(data, 0), 0);
  });
});

describe("_skipPtpString", () => {
  it("returns the offset just past the string", () => {
    const data = _encodePtpString("Hi");

    assert.equal(_skipPtpString(data, 0), data.length);
  });
});

describe("_deviceInfoOffsets", () => {
  it("points at the supported properties array and the manufacturer string", () => {
    const vector = FIXTURE.device_info.find((v) => v.name === "x_s10");
    const data = fromHex(vector.hex);

    const { propsOffset, manufacturerOffset } = _deviceInfoOffsets(data);

    // The props offset must land on the uint32 count of the four codes.
    const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    assert.equal(view.getUint32(propsOffset, true), 4);
    // The manufacturer offset must land on a PTP string that decodes cleanly.
    assert.equal(_decodePtpString(data, manufacturerOffset).value, "FUJIFILM");
  });
});
