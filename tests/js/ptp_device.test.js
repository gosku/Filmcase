import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  CameraConnectionError,
  CameraWriteError,
  formatCode,
  formatRc,
  formatValue,
} from "../../src/interfaces/static/js/camera/vendor/ptp_device.js";

describe("CameraConnectionError", () => {
  it("is an Error, so it survives instanceof across the retry helpers", () => {
    const error = new CameraConnectionError("USB write failed");

    assert.ok(error instanceof Error);
    assert.ok(error instanceof CameraConnectionError);
  });

  it("keeps its name after being thrown and caught", () => {
    // Subclassing Error is easy to get subtly wrong; without the explicit name
    // assignment this reports as "Error" and the logs stop being greppable.
    try {
      throw new CameraConnectionError("camera gone");
    } catch (error) {
      assert.equal(error.name, "CameraConnectionError");
      assert.equal(error.message, "camera gone");
    }
  });

  it("is distinguishable from a write error", () => {
    // The push sequence aborts on one and continues past the other, so telling
    // them apart is load-bearing rather than cosmetic.
    const connection = new CameraConnectionError("gone");

    assert.ok(!(connection instanceof CameraWriteError));
  });
});

describe("CameraWriteError", () => {
  it("carries the code, value and response code as properties", () => {
    const error = new CameraWriteError(0xd18d, "Kodak Portra", 0x2005);

    assert.equal(error.code, 0xd18d);
    assert.equal(error.value, "Kodak Portra");
    assert.equal(error.rc, 0x2005);
  });

  it("reports the same message the Python side does", () => {
    // Same wording on both transports, so a user pasting a failure into an
    // issue produces something greppable against the server logs.
    const error = new CameraWriteError(0xd18d, "Kodak Portra", 0x2005);

    assert.equal(
      error.message,
      "Camera rejected write of PTP property 0xD18D = 'Kodak Portra' (rc=0x2005)"
    );
  });

  it("reports integer values without quotes, as Python's repr does", () => {
    const error = new CameraWriteError(0xd192, 11, 0x2005);

    assert.equal(
      error.message,
      "Camera rejected write of PTP property 0xD192 = 11 (rc=0x2005)"
    );
  });

  it("reports negative values without quotes", () => {
    const error = new CameraWriteError(0xd19d, -15, 0x2005);

    assert.equal(
      error.message,
      "Camera rejected write of PTP property 0xD19D = -15 (rc=0x2005)"
    );
  });
});

describe("formatCode", () => {
  it("renders four uppercase hex digits, matching Python's 0x{code:04X}", () => {
    assert.equal(formatCode(0xd18c), "0xD18C");
  });

  it("pads short codes to four digits", () => {
    assert.equal(formatCode(0x1015), "0x1015");
    assert.equal(formatCode(0x01), "0x0001");
  });
});

describe("formatRc", () => {
  it("renders lowercase and unpadded, matching Python's {rc:#x}", () => {
    assert.equal(formatRc(0x2001), "0x2001");
    assert.equal(formatRc(0x5), "0x5");
  });
});

describe("formatValue", () => {
  it("quotes strings", () => {
    assert.equal(formatValue("Provia"), "'Provia'");
  });

  it("leaves numbers bare", () => {
    assert.equal(formatValue(0), "0");
    assert.equal(formatValue(-40), "-40");
  });
});
