/**
 * The WebUSB transport plumbing: connecting, framing transfers, and the three
 * ways a camera can fail that PyUSB handles for us and WebUSB does not.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { FakeUSBDevice } from "./fakes/usb_device.js";
import { makeConfig } from "./fakes/config.js";
import { CameraConnectionError } from "../../src/interfaces/static/js/camera/vendor/ptp_device.js";
import {
  ClientPTPUSBDevice,
  _OC_CLOSE_SESSION,
  _OC_GET_DEVICE_INFO,
  _OC_GET_DEVICE_PROP_VALUE,
  _OC_OPEN_SESSION,
  _PTP_DATA,
  _PTP_RESPONSE,
  _RC_OK,
  _RC_SESSION_ALREADY,
  _commandPacket,
  _findBulkInterface,
} from "../../src/interfaces/static/js/camera/vendor/ptp_usb_device.js";

const noSleep = async () => {};

function makeDevice(options = {}) {
  const usbDevice = new FakeUSBDevice(options);
  const device = new ClientPTPUSBDevice({
    usbDevice,
    // A real config: connecting needs none of it, but the read retry loop
    // refuses to guess a missing timing setting, which is the point of it.
    config: makeConfig(),
    sleep: noSleep,
    // Short enough that the timeout tests cost milliseconds. At the real five
    // seconds each they would dominate the suite and stop it being run.
    timeoutMs: 5,
  });
  return { device, usbDevice };
}

describe("_findBulkInterface", () => {
  it("finds the interface carrying a bulk endpoint in each direction", () => {
    const usbDevice = new FakeUSBDevice();
    usbDevice.configuration = usbDevice._declaredConfiguration;

    const found = _findBulkInterface(usbDevice);

    assert.deepEqual(found, { interfaceNumber: 0, inEndpoint: 2, outEndpoint: 1 });
  });

  it("ignores interrupt endpoints", () => {
    // Real cameras expose an interrupt endpoint for PTP events alongside the
    // bulk pair. Picking it would send commands into a channel that never
    // answers.
    const usbDevice = new FakeUSBDevice();
    usbDevice.configuration = usbDevice._declaredConfiguration;

    const { inEndpoint } = _findBulkInterface(usbDevice);

    assert.notEqual(inEndpoint, 3);
  });

  it("returns null when no configuration has been selected", () => {
    assert.equal(_findBulkInterface({ configuration: null }), null);
  });

  it("returns null when no interface exposes both directions", () => {
    const device = {
      configuration: {
        interfaces: [
          {
            interfaceNumber: 0,
            alternates: [
              { endpoints: [{ endpointNumber: 1, direction: "out", type: "bulk" }] },
            ],
          },
        ],
      },
    };

    assert.equal(_findBulkInterface(device), null);
  });

  it("searches past an interface that does not carry the pair", () => {
    // The Python hardcodes interface (0, 0); a camera that puts PTP on a later
    // interface would break it and must not break this.
    const device = {
      configuration: {
        interfaces: [
          {
            interfaceNumber: 0,
            alternates: [
              { endpoints: [{ endpointNumber: 5, direction: "in", type: "interrupt" }] },
            ],
          },
          {
            interfaceNumber: 2,
            alternates: [
              {
                endpoints: [
                  { endpointNumber: 1, direction: "out", type: "bulk" },
                  { endpointNumber: 2, direction: "in", type: "bulk" },
                ],
              },
            ],
          },
        ],
      },
    };

    assert.equal(_findBulkInterface(device).interfaceNumber, 2);
  });
});

describe("ClientPTPUSBDevice.connect", () => {
  it("opens, claims the interface, opens a session and reads the model", async () => {
    const { device, usbDevice } = makeDevice();

    await device.connect();

    assert.equal(device.cameraName, "X-S10");
    assert.deepEqual(usbDevice.sentCommandCodes(), [
      _OC_OPEN_SESSION,
      _OC_GET_DEVICE_INFO,
    ]);
  });

  it("claims the interface that carries the bulk pair", async () => {
    const { device, usbDevice } = makeDevice();

    await device.connect();

    assert.ok(usbDevice.calls.includes("claimInterface(0)"));
  });

  it("selects a configuration when the device has none", async () => {
    const { device, usbDevice } = makeDevice();

    await device.connect();

    assert.ok(usbDevice.calls.includes("selectConfiguration(1)"));
  });

  it("starts transaction ids at 1", async () => {
    // The camera tracks them, so starting anywhere else after a page reload
    // makes ids appear to go backwards.
    const { device, usbDevice } = makeDevice();

    await device.connect();

    assert.equal(usbDevice.sent[0].txId, 1);
  });

  it("increments the transaction id for each command", async () => {
    const { device, usbDevice } = makeDevice();

    await device.connect();

    const txIds = usbDevice.sent.map((s) => s.txId);
    assert.deepEqual(txIds, [1, 2]);
  });

  it("tolerates a session that is already open", async () => {
    // A reload mid-session leaves the camera's session open; refusing to
    // continue would strand the user until they replugged the cable.
    const { device } = makeDevice({ openSessionRc: _RC_SESSION_ALREADY });

    await device.connect();

    assert.equal(device.cameraName, "X-S10");
  });

  it("reports a session that fails for any other reason", async () => {
    const { device } = makeDevice({ openSessionRc: 0x2005 });

    await assert.rejects(
      () => device.connect(),
      (error) =>
        error instanceof CameraConnectionError && /OpenSession failed/.test(error.message)
    );
  });

  it("explains an interface it cannot open", async () => {
    const { device } = makeDevice({
      failOpenWith: Object.assign(new Error("busy"), { name: "NetworkError" }),
    });

    await assert.rejects(
      () => device.connect(),
      (error) => error instanceof CameraConnectionError && /udev/.test(error.message)
    );
  });

  it("refuses a device with no PTP endpoints", async () => {
    const { device } = makeDevice({
      configuration: {
        configurationValue: 1,
        interfaces: [
          {
            interfaceNumber: 0,
            alternates: [
              { endpoints: [{ endpointNumber: 1, direction: "in", type: "interrupt" }] },
            ],
          },
        ],
      },
    });

    await assert.rejects(
      () => device.connect(),
      (error) =>
        error instanceof CameraConnectionError && /bulk USB endpoints/.test(error.message)
    );
  });

  it("returns an empty model rather than failing when DeviceInfo is unreadable", async () => {
    // The model only decides how many slots to offer, so a camera that will
    // not describe itself is still worth talking to.
    const { device } = makeDevice({ deviceInfoHex: "00" });

    await device.connect();

    assert.equal(device.cameraName, "");
  });
});

describe("ClientPTPUSBDevice.disconnect", () => {
  it("closes the session and releases the device", async () => {
    const { device, usbDevice } = makeDevice();
    await device.connect();

    await device.disconnect();

    assert.ok(usbDevice.sentCommandCodes().includes(_OC_CLOSE_SESSION));
    assert.ok(usbDevice.calls.includes("releaseInterface(0)"));
    assert.ok(usbDevice.calls.includes("close"));
  });

  it("does nothing when never connected", async () => {
    const device = new ClientPTPUSBDevice({ usbDevice: null, config: {}, sleep: noSleep });

    await device.disconnect();
  });

  it("never throws, even when the camera has already gone", async () => {
    // disconnect() runs in a finally block; if it threw it would replace the
    // real failure with a misleading one.
    const { device, usbDevice } = makeDevice();
    await device.connect();
    usbDevice.transferOut = async () => {
      throw new Error("device unplugged");
    };
    usbDevice.close = async () => {
      throw new Error("already gone");
    };

    await device.disconnect();
  });

  it("closes the device even when the session will not close", async () => {
    const { device, usbDevice } = makeDevice();
    await device.connect();
    usbDevice.transferOut = async () => {
      throw new Error("device unplugged");
    };

    await device.disconnect();

    assert.ok(usbDevice.calls.includes("close"));
  });
});

describe("ClientPTPUSBDevice transfer failures", () => {
  it("times out rather than hanging when a read never returns", async () => {
    // WebUSB has no timeout argument and a pending transferIn cannot be
    // cancelled, so without the wrapper this hangs the tab forever.
    const { device } = makeDevice({ hangOn: [_OC_OPEN_SESSION] });

    await assert.rejects(
      () => device.connect(),
      (error) => error instanceof CameraConnectionError && /timed out/.test(error.message)
    );
  });

  it("stays usable after a timeout, so the retry loops can retry", async () => {
    // A timeout means the camera did not answer, which on this hardware is a
    // dropped request rather than a late one: the server retries in place and
    // recovers. Refusing to continue would turn a recoverable stall into a dead
    // session, and would make all three retry loops decorative.
    const usbDevice = new FakeUSBDevice({ hangOn: [_OC_OPEN_SESSION] });
    const device = new ClientPTPUSBDevice({
      usbDevice,
      config: {},
      sleep: noSleep,
      timeoutMs: 5,
    });

    await assert.rejects(() => device.connect());

    // Still connected, and a fresh exchange is allowed. This says the code will
    // ask again, not that the camera will answer.
    assert.doesNotThrow(() => device._assertConnected());
  });

  it("reports a stalled write and tries to clear the halt", async () => {
    const { device, usbDevice } = makeDevice({ stallOn: [_OC_OPEN_SESSION] });

    await assert.rejects(
      () => device.connect(),
      (error) => error instanceof CameraConnectionError && /stall/.test(error.message)
    );
    assert.ok(usbDevice.calls.some((c) => c.startsWith("clearHalt")));
  });

  it("refuses to send when the device is not connected", async () => {
    const device = new ClientPTPUSBDevice({ usbDevice: null, config: {}, sleep: noSleep });

    await assert.rejects(
      () => device.connect(),
      (error) => error instanceof CameraConnectionError && /No camera/.test(error.message)
    );
  });
});

describe("ClientPTPUSBDevice._recvData", () => {
  it("returns the data container a property read produces", async () => {
    const { device } = makeDevice({ intValues: { 0xd023: 7 } });
    await device.connect();

    await device._send(_commandPacket(_OC_GET_DEVICE_PROP_VALUE, device._nextTx(), 0xd023));
    const { data, response } = await device._recvData();

    assert.ok(data.length > 12, "expected a header plus a payload");
    assert.equal(response, null, "a response should still be waiting");
    await device._recvResponse();
  });

  it("hands back the response when the camera skips the data phase", async () => {
    // The bug this replaced: _recvData returned the response container and left
    // the caller to read for a response that had already arrived. Nothing
    // further was on the wire, so that read waited out the entire timeout.
    const { device } = makeDevice({ noDataPhaseOn: [0xd023] });
    await device.connect();

    await device._send(_commandPacket(_OC_GET_DEVICE_PROP_VALUE, device._nextTx(), 0xd023));
    const { data, response } = await device._recvData();

    assert.notEqual(response, null, "the response was consumed and not reported");
    assert.equal(response.code, _RC_OK);
    // No value came back, so none is reported. Passing the response container
    // off as data would decode its parameters as a value.
    assert.equal(data.length, 0);
  });

  it("retries rather than reporting a value the camera never sent", async () => {
    // Observed on an X-S10: the camera acknowledges the read and sends no
    // value. An empty payload decodes to 0, a legitimate value for most of
    // these properties, so reporting it would put a real-looking setting on
    // screen and write it to a slot on a push.
    const { device } = makeDevice({
      noDataPhaseOn: [0xd192],
      noDataPhaseTimes: 1,
      intValues: { 0xd192: 13 },
    });
    await device.connect();

    assert.equal(await device.getPropertyInt(0xd192), 13);
  });

  it("gives up quickly when the camera never sends a value", async () => {
    const { device } = makeDevice({ noDataPhaseOn: [0xd192] });
    await device.connect();

    const started = Date.now();
    await assert.rejects(
      () => device.getPropertyInt(0xd192),
      (error) => error instanceof CameraConnectionError && /no value/.test(error.message)
    );

    assert.ok(Date.now() - started < 500, "it stalled instead of failing");
  });

  it("reports the error when a skipped data phase carries a failure", async () => {
    const { device } = makeDevice({ noDataPhaseOn: [0xd023], noDataPhaseRc: 0x2005 });
    await device.connect();

    await device._send(_commandPacket(_OC_GET_DEVICE_PROP_VALUE, device._nextTx(), 0xd023));

    await assert.rejects(
      () => device._recvData(),
      (error) =>
        error instanceof CameraConnectionError && /no data phase/.test(error.message)
    );
  });

  it("does not mistake a data container for a response", async () => {
    // _recvData peeks at the container type to spot cameras that skip the data
    // phase. Misreading a real data container as a response would drop the
    // value and leave the next read one container out of step.
    const { device } = makeDevice({ intValues: { 0xd023: 7 } });
    await device.connect();

    await device._send(_commandPacket(_OC_GET_DEVICE_PROP_VALUE, device._nextTx(), 0xd023));
    const { data } = await device._recvData();

    const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    assert.equal(view.getUint16(4, true), _PTP_DATA);
    await device._recvResponse();
  });
});
