/**
 * Reading and writing camera properties.
 *
 * Two contracts matter most, because the layers above are built on them.
 *
 * A set returns a response code rather than throwing. A camera that considers
 * a write and refuses it is telling you something different from a camera that
 * has been unplugged, and only the caller knows which of those to give up on.
 *
 * A read retries; a write does not. _getPropWithRetry catches
 * CameraConnectionError, which _checkRc raises for a refusal as well as for a
 * transport failure, so a refused read is in fact asked three times. That is
 * the Python's behaviour and is pinned here rather than quietly improved.
 * Writes go through _setProp, which has no retry loop at all; retrying those
 * is the operations layer's job.
 */

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

import { makeClock } from "./fakes/clock.js";
import { makeConfig, PROP_FILM_SIMULATION, PROP_PING, PROP_SLOT_NAME } from "./fakes/config.js";
import { FakeUSBDevice } from "./fakes/usb_device.js";
import { CameraConnectionError } from "../../src/interfaces/static/js/camera/vendor/ptp_device.js";
import {
  PTP_READ_FAILED,
  PTP_READ_SUCCEEDED,
  PTP_WRITE_FAILED,
  PTP_WRITE_SUCCEEDED,
  recent,
  reset,
} from "../../src/interfaces/static/js/camera/vendor/events.js";
import {
  ClientPTPUSBDevice,
  _PTP_DATA,
  _RC_OK,
} from "../../src/interfaces/static/js/camera/vendor/ptp_usb_device.js";

async function connected(usbOptions = {}, configOverrides = {}) {
  const usbDevice = new FakeUSBDevice(usbOptions);
  const clock = makeClock();
  const device = new ClientPTPUSBDevice({
    usbDevice,
    config: makeConfig(configOverrides),
    sleep: clock.sleep,
    timeoutMs: 5,
  });
  await device.connect();
  clock.slept.length = 0; // ignore anything connect() spent
  return { device, usbDevice, clock };
}

/** The payload of the last data container written, as bytes. */
function lastWrittenPayload(usbDevice) {
  const dataPackets = usbDevice.sent.filter((s) => s.type === _PTP_DATA);
  return dataPackets[dataPackets.length - 1].bytes.slice(12);
}

beforeEach(() => reset());

describe("getPropertyInt", () => {
  it("reads a positive value", async () => {
    const { device } = await connected({ intValues: { [PROP_FILM_SIMULATION]: 11 } });

    assert.equal(await device.getPropertyInt(PROP_FILM_SIMULATION), 11);
  });

  it("reads a negative value as a signed int32", async () => {
    // Tone curves and white balance shifts are negative half the time; reading
    // them unsigned would turn -40 into 4294967256.
    const { device } = await connected({ intValues: { [PROP_FILM_SIMULATION]: -40 } });

    assert.equal(await device.getPropertyInt(PROP_FILM_SIMULATION), -40);
  });

  it("waits the configured pause after a successful read", async () => {
    const { device, clock } = await connected(
      { intValues: { [PROP_FILM_SIMULATION]: 1 } },
      { CAMERA_POST_READ_DELAY_S: 0.05 }
    );

    await device.getPropertyInt(PROP_FILM_SIMULATION);

    assert.deepEqual(clock.slept, [0.05]);
  });

  it("publishes a success event carrying the value", async () => {
    const { device } = await connected({ intValues: { [PROP_FILM_SIMULATION]: 11 } });

    await device.getPropertyInt(PROP_FILM_SIMULATION);

    const events = recent().filter((e) => e.eventType === PTP_READ_SUCCEEDED);
    assert.equal(events.length, 1);
    assert.equal(events[0].prop, "0xD192");
    assert.equal(events[0].value, 11);
  });

  it("publishes a failure event before giving up", async () => {
    const { device, usbDevice } = await connected();
    usbDevice.failNextReads(99);

    await assert.rejects(() => device.getPropertyInt(PROP_FILM_SIMULATION));

    const events = recent().filter((e) => e.eventType === PTP_READ_FAILED);
    assert.equal(events.length, 1);
    assert.equal(events[0].prop, "0xD192");
  });
});

describe("getPropertyInt16", () => {
  it("reinterprets a zero-extended negative as signed", async () => {
    // The camera sends int16 values zero-extended into four bytes, so -10
    // arrives as 65526. Without this every negative tune reads as a large
    // positive and the slot listing is nonsense.
    const { device } = await connected({ intValues: { [PROP_FILM_SIMULATION]: 65526 } });

    assert.equal(await device.getPropertyInt16(PROP_FILM_SIMULATION), -10);
  });

  it("leaves a positive value alone", async () => {
    const { device } = await connected({ intValues: { [PROP_FILM_SIMULATION]: 15 } });

    assert.equal(await device.getPropertyInt16(PROP_FILM_SIMULATION), 15);
  });

  it("treats the sign boundary as negative", async () => {
    const { device } = await connected({ intValues: { [PROP_FILM_SIMULATION]: 32768 } });

    assert.equal(await device.getPropertyInt16(PROP_FILM_SIMULATION), -32768);
  });

  it("treats one below the boundary as positive", async () => {
    const { device } = await connected({ intValues: { [PROP_FILM_SIMULATION]: 32767 } });

    assert.equal(await device.getPropertyInt16(PROP_FILM_SIMULATION), 32767);
  });
});

describe("getPropertyString", () => {
  it("reads a slot name", async () => {
    const { device } = await connected({
      stringValues: { [PROP_SLOT_NAME]: "Kodak Portra" },
    });

    assert.equal(await device.getPropertyString(PROP_SLOT_NAME), "Kodak Portra");
  });

  it("reads an empty slot name", async () => {
    const { device } = await connected({ stringValues: { [PROP_SLOT_NAME]: "" } });

    assert.equal(await device.getPropertyString(PROP_SLOT_NAME), "");
  });
});

describe("setPropertyInt", () => {
  it("returns 0 when the camera accepts the write", async () => {
    const { device } = await connected();

    assert.equal(await device.setPropertyInt(PROP_FILM_SIMULATION, 11), 0);
  });

  it("returns the response code rather than throwing when refused", async () => {
    // The layer above decides what a refusal means. Throwing here would take
    // that decision away and make a rejected property indistinguishable from a
    // camera that vanished.
    const { device } = await connected({
      setRejectionCodes: { [PROP_FILM_SIMULATION]: 0x2005 },
    });

    assert.equal(await device.setPropertyInt(PROP_FILM_SIMULATION, 11), 0x2005);
  });

  it("sends the value as a little-endian int32", async () => {
    const { device, usbDevice } = await connected();

    await device.setPropertyInt(PROP_FILM_SIMULATION, -40);

    assert.deepEqual(Array.from(lastWrittenPayload(usbDevice)), [0xd8, 0xff, 0xff, 0xff]);
  });

  it("reuses the command's transaction id for its data packet", async () => {
    // PTP pairs the two by transaction id; a fresh id on the data phase makes
    // the camera discard it.
    const { device, usbDevice } = await connected();
    usbDevice.sent.length = 0;

    await device.setPropertyInt(PROP_FILM_SIMULATION, 11);

    const [command, data] = usbDevice.sent;
    assert.equal(command.txId, data.txId);
  });

  it("publishes a success event", async () => {
    const { device } = await connected();

    await device.setPropertyInt(PROP_FILM_SIMULATION, 11);

    const events = recent().filter((e) => e.eventType === PTP_WRITE_SUCCEEDED);
    assert.deepEqual(events.map((e) => e.prop), ["0xD192"]);
  });

  it("publishes a failure event carrying the response code", async () => {
    const { device } = await connected({
      setRejectionCodes: { [PROP_FILM_SIMULATION]: 0x2005 },
    });

    await device.setPropertyInt(PROP_FILM_SIMULATION, 11);

    const events = recent().filter((e) => e.eventType === PTP_WRITE_FAILED);
    assert.deepEqual(events.map((e) => e.rc), ["0x2005"]);
  });
});

describe("setPropertyUint16", () => {
  it("sends two bytes little-endian", async () => {
    const { device, usbDevice } = await connected();

    await device.setPropertyUint16(0xd18c, 4);

    assert.deepEqual(Array.from(lastWrittenPayload(usbDevice)), [0x04, 0x00]);
  });

  it("masks a value wider than sixteen bits", async () => {
    const { device, usbDevice } = await connected();

    await device.setPropertyUint16(0xd18c, 0x1_0004);

    assert.deepEqual(Array.from(lastWrittenPayload(usbDevice)), [0x04, 0x00]);
  });
});

describe("setPropertyString", () => {
  it("sends a NUL-counted PTP string", async () => {
    const { device, usbDevice } = await connected();

    await device.setPropertyString(PROP_SLOT_NAME, "A");

    assert.deepEqual(Array.from(lastWrittenPayload(usbDevice)), [0x02, 0x41, 0x00, 0x00, 0x00]);
  });

  it("sends a single zero byte for an empty name", async () => {
    const { device, usbDevice } = await connected();

    await device.setPropertyString(PROP_SLOT_NAME, "");

    assert.deepEqual(Array.from(lastWrittenPayload(usbDevice)), [0x00]);
  });
});

describe("_getPropWithRetry", () => {
  it("succeeds on a later attempt after a transient failure", async () => {
    const { device, usbDevice } = await connected({
      intValues: { [PROP_FILM_SIMULATION]: 11 },
    });
    usbDevice.failNextReads(1);

    assert.equal(await device.getPropertyInt(PROP_FILM_SIMULATION), 11);
  });

  it("backs off exponentially between attempts", async () => {
    // 0.15 then 0.30, matching backoff * 2**(attempt-1) in the Python. The
    // first attempt is immediate, so three attempts mean two waits.
    const { device, usbDevice, clock } = await connected();
    usbDevice.failNextReads(99);

    await assert.rejects(() => device.getPropertyInt(PROP_FILM_SIMULATION));

    assert.deepEqual(clock.slept, [0.15, 0.3]);
  });

  it("gives up after the configured number of attempts", async () => {
    const { device, usbDevice } = await connected();
    usbDevice.failNextReads(99);
    usbDevice.sent.length = 0;

    await assert.rejects(
      () => device.getPropertyInt(PROP_FILM_SIMULATION),
      (error) => error instanceof CameraConnectionError
    );

    assert.equal(usbDevice.sent.length, 3);
  });

  it("honours a different retry count from the config", async () => {
    const { device, usbDevice } = await connected({}, { CAMERA_MAX_RETRIES: 5 });
    usbDevice.failNextReads(99);
    usbDevice.sent.length = 0;

    await assert.rejects(() => device.getPropertyInt(PROP_FILM_SIMULATION));

    assert.equal(usbDevice.sent.length, 5);
  });

  it("retries a refused read too, as the Python does", async () => {
    // Worth pinning even though it is arguably generous: _check_rc turns a
    // non-OK response into a CameraConnectionError, which the retry loop
    // catches, so a camera that refuses is asked three times. Writes are the
    // ones never retried here, and they go through _setProp instead.
    const { device, usbDevice } = await connected({
      noDataPhaseOn: [PROP_FILM_SIMULATION],
      noDataPhaseRc: 0x2005,
    });
    usbDevice.sent.length = 0;

    await assert.rejects(() => device.getPropertyInt(PROP_FILM_SIMULATION));

    assert.equal(usbDevice.sent.length, 3);
  });
});

describe("ping", () => {
  it("returns 0 when the camera answers", async () => {
    const { device } = await connected({ intValues: { [PROP_PING]: 0 } });

    assert.equal(await device.ping(), 0);
  });

  it("returns -1 when the camera does not", async () => {
    const { device, usbDevice } = await connected();
    usbDevice.failNextReads(99);

    assert.equal(await device.ping(), -1);
  });
});

describe("supportedProperties", () => {
  it("lists the codes GetDeviceInfo reports", async () => {
    const { device } = await connected();

    assert.deepEqual(await device.supportedProperties(), [0xd18c, 0xd18d, 0xd192, 0xd199]);
  });

  it("returns an empty list rather than failing", async () => {
    // Callers treat it as a diagnostic, so it must never be the thing that
    // stops a push.
    const { device, usbDevice } = await connected();
    usbDevice.transferIn = async () => {
      throw new Error("gone");
    };

    assert.deepEqual(await device.supportedProperties(), []);
  });
});

describe("client config", () => {
  it("refuses to guess a missing timing setting", async () => {
    // A missing key means the server and the browser are out of step. Falling
    // back to a default would hide that and leave the browser writing on
    // timings nobody chose.
    const usbDevice = new FakeUSBDevice();
    const device = new ClientPTPUSBDevice({
      usbDevice,
      config: { settings: {}, encodings: {} },
      sleep: async () => {},
      timeoutMs: 5,
    });
    await device.connect();

    await assert.rejects(
      () => device.getPropertyInt(PROP_FILM_SIMULATION),
      (error) =>
        error instanceof CameraConnectionError &&
        /CAMERA_MAX_RETRIES missing/.test(error.message)
    );
  });
});
