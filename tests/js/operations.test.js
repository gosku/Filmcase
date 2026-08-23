/**
 * Writing properties, and reading them back.
 *
 * The distinction under test throughout: a transport failure is retried, a
 * rejection is not, and the two leave by different exceptions because the push
 * sequence abandons the recipe on one and carries on past the other. Confusing
 * them turns a single refused property into an abandoned recipe, or a vanished
 * camera into eighteen pointless writes.
 */

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

import { makeClock } from "./fakes/clock.js";
import { makeConfig, PROP_FILM_SIMULATION, PROP_SLOT_NAME } from "./fakes/config.js";
import { FakePTPDevice } from "./fakes/ptp_device.js";
import {
  CameraConnectionError,
  CameraWriteError,
} from "../../src/interfaces/static/js/camera/vendor/ptp_device.js";
import {
  PTP_WRITE_FAILED,
  PTP_WRITE_SUCCEEDED,
  recent,
  reset,
} from "../../src/interfaces/static/js/camera/vendor/events.js";
import {
  setPropWithRetry,
  verifyWrittenProperties,
} from "../../src/interfaces/static/js/camera/domain/operations.js";

function runtime(overrides = {}) {
  const clock = makeClock();
  return { config: makeConfig(overrides), sleep: clock.sleep, clock };
}

beforeEach(() => reset());

describe("setPropWithRetry", () => {
  it("writes a value through on the first attempt", async () => {
    const device = new FakePTPDevice();

    await setPropWithRetry(device, PROP_FILM_SIMULATION, 11, runtime());

    assert.deepEqual(device.writes, [[PROP_FILM_SIMULATION, 11]]);
  });

  it("dispatches strings to the string setter", async () => {
    // The slot name is the only string property, and sending it through the
    // integer setter would write four bytes of nonsense.
    const device = new FakePTPDevice();

    await setPropWithRetry(device, PROP_SLOT_NAME, "Kodak Portra", runtime());

    assert.equal(await device.getPropertyString(PROP_SLOT_NAME), "Kodak Portra");
  });

  it("retries a transport failure and succeeds", async () => {
    const device = new FakePTPDevice({
      setFailuresBeforeSuccess: { [PROP_FILM_SIMULATION]: 2 },
    });

    await setPropWithRetry(device, PROP_FILM_SIMULATION, 11, runtime());

    assert.equal(device.writes.length, 3);
    assert.equal(await device.getPropertyInt(PROP_FILM_SIMULATION), 11);
  });

  it("backs off exponentially between attempts", async () => {
    // 0.15 then 0.30. The attempt counter is 1-based here and 0-based in the
    // transport, so the exponents differ while the sequence does not.
    const device = new FakePTPDevice({
      setFailuresBeforeSuccess: { [PROP_FILM_SIMULATION]: 2 },
    });
    const rt = runtime();

    await setPropWithRetry(device, PROP_FILM_SIMULATION, 11, rt);

    assert.deepEqual(rt.clock.slept, [0.15, 0.3]);
  });

  it("gives up after the configured number of attempts", async () => {
    const device = new FakePTPDevice({
      setErrors: { [PROP_FILM_SIMULATION]: new CameraConnectionError("gone") },
    });

    await assert.rejects(
      () => setPropWithRetry(device, PROP_FILM_SIMULATION, 11, runtime()),
      (error) => error instanceof CameraConnectionError
    );
    assert.equal(device.writes.length, 3);
  });

  it("honours a different retry count", async () => {
    const device = new FakePTPDevice({
      setErrors: { [PROP_FILM_SIMULATION]: new CameraConnectionError("gone") },
    });

    await assert.rejects(() =>
      setPropWithRetry(device, PROP_FILM_SIMULATION, 11, runtime({ CAMERA_MAX_RETRIES: 5 }))
    );

    assert.equal(device.writes.length, 5);
  });

  it("does not retry a rejection", async () => {
    // The camera answered. It considered the write and refused it, so asking
    // again would only slow the push down before failing anyway.
    const device = new FakePTPDevice({
      setRejectionCodes: { [PROP_FILM_SIMULATION]: 0x2005 },
    });

    await assert.rejects(
      () => setPropWithRetry(device, PROP_FILM_SIMULATION, 11, runtime()),
      (error) => error instanceof CameraWriteError
    );
    assert.equal(device.writes.length, 1);
  });

  it("carries the code, value and response code on a rejection", async () => {
    const device = new FakePTPDevice({
      setRejectionCodes: { [PROP_FILM_SIMULATION]: 0x2005 },
    });

    await assert.rejects(
      () => setPropWithRetry(device, PROP_FILM_SIMULATION, 11, runtime()),
      (error) => {
        assert.equal(error.code, PROP_FILM_SIMULATION);
        assert.equal(error.value, 11);
        assert.equal(error.rc, 0x2005);
        return true;
      }
    );
  });

  it("distinguishes a rejection from an unreachable camera", async () => {
    // The push sequence branches on exactly this: it continues past one and
    // abandons the recipe on the other.
    const rejecting = new FakePTPDevice({
      setRejectionCodes: { [PROP_FILM_SIMULATION]: 0x2005 },
    });
    const gone = new FakePTPDevice({
      setErrors: { [PROP_FILM_SIMULATION]: new CameraConnectionError("gone") },
    });

    await assert.rejects(
      () => setPropWithRetry(rejecting, PROP_FILM_SIMULATION, 11, runtime()),
      (error) => error instanceof CameraWriteError && !(error instanceof CameraConnectionError)
    );
    await assert.rejects(
      () => setPropWithRetry(gone, PROP_FILM_SIMULATION, 11, runtime()),
      (error) => error instanceof CameraConnectionError && !(error instanceof CameraWriteError)
    );
  });

  it("publishes a success event naming the property and value", async () => {
    const device = new FakePTPDevice();

    await setPropWithRetry(device, PROP_FILM_SIMULATION, 11, runtime());

    const events = recent().filter((e) => e.eventType === PTP_WRITE_SUCCEEDED);
    assert.equal(events.length, 1);
    assert.equal(events[0].description, "0xD192 = 11");
  });

  it("publishes an attempt-numbered event for each transport failure", async () => {
    // The attempt numbers are what make a support log readable: they say
    // whether the camera was flaky or simply absent.
    const device = new FakePTPDevice({
      setErrors: { [PROP_FILM_SIMULATION]: new CameraConnectionError("gone") },
    });

    await assert.rejects(() => setPropWithRetry(device, PROP_FILM_SIMULATION, 11, runtime()));

    const failures = recent().filter((e) => e.eventType === PTP_WRITE_FAILED);
    assert.equal(failures.length, 3);
    assert.ok(failures[0].description.includes("attempt 1/3"));
    assert.ok(failures[2].description.includes("attempt 3/3"));
  });

  it("publishes one event naming the response code on a rejection", async () => {
    const device = new FakePTPDevice({
      setRejectionCodes: { [PROP_FILM_SIMULATION]: 0x2005 },
    });

    await assert.rejects(() => setPropWithRetry(device, PROP_FILM_SIMULATION, 11, runtime()));

    const failures = recent().filter((e) => e.eventType === PTP_WRITE_FAILED);
    assert.equal(failures.length, 1);
    assert.ok(failures[0].description.includes("rc=0x2005"));
  });

  it("quotes a string value the way the Python does", async () => {
    const device = new FakePTPDevice({
      setRejectionCodes: { [PROP_SLOT_NAME]: 0x2005 },
    });

    await assert.rejects(() => setPropWithRetry(device, PROP_SLOT_NAME, "Portra", runtime()));

    const failure = recent().find((e) => e.eventType === PTP_WRITE_FAILED);
    assert.ok(failure.description.startsWith("0xD18D = 'Portra':"));
  });
});

describe("verifyWrittenProperties", () => {
  it("reports nothing when every value stuck", async () => {
    const device = new FakePTPDevice();
    await setPropWithRetry(device, PROP_FILM_SIMULATION, 11, runtime());

    const mismatched = await verifyWrittenProperties(
      device,
      [[PROP_FILM_SIMULATION, 11]],
      runtime()
    );

    assert.deepEqual(mismatched, []);
  });

  it("reports a property the camera changed underneath", async () => {
    // A write can report success and still not take, which is the only reason
    // this function exists.
    const device = new FakePTPDevice({ intReadOverrides: { [PROP_FILM_SIMULATION]: 6 } });

    const mismatched = await verifyWrittenProperties(
      device,
      [[PROP_FILM_SIMULATION, 11]],
      runtime()
    );

    assert.deepEqual(mismatched, [PROP_FILM_SIMULATION]);
  });

  it("compares negatives as sixteen bits", async () => {
    // -40 goes out as a signed int32 and comes back as the uint16 0xFFD8.
    // Comparing them whole would fail every negative value in every recipe.
    const device = new FakePTPDevice({ intReadOverrides: { [PROP_FILM_SIMULATION]: 0xffd8 } });

    const mismatched = await verifyWrittenProperties(
      device,
      [[PROP_FILM_SIMULATION, -40]],
      runtime()
    );

    assert.deepEqual(mismatched, []);
  });

  it("compares strings exactly", async () => {
    const device = new FakePTPDevice({
      strReadOverrides: { [PROP_SLOT_NAME]: "Kodak Port" },
    });

    const mismatched = await verifyWrittenProperties(
      device,
      [[PROP_SLOT_NAME, "Kodak Portra"]],
      runtime()
    );

    assert.deepEqual(mismatched, [PROP_SLOT_NAME]);
  });

  it("treats a read that fails as a mismatch rather than throwing", async () => {
    // The caller wants the whole list to show the user; throwing here would
    // hide every property after the first unreadable one.
    const device = new FakePTPDevice({
      defaultIntGetError: new CameraConnectionError("gone"),
    });

    const mismatched = await verifyWrittenProperties(
      device,
      [
        [PROP_FILM_SIMULATION, 11],
        [0xd195, 2],
      ],
      runtime()
    );

    assert.deepEqual(mismatched, [PROP_FILM_SIMULATION, 0xd195]);
  });

  it("pauses before each read", async () => {
    const device = new FakePTPDevice();
    const rt = runtime({ CAMERA_PRE_WRITE_DELAY_S: 0.05 });

    await verifyWrittenProperties(
      device,
      [
        [PROP_FILM_SIMULATION, 0],
        [0xd195, 0],
      ],
      rt
    );

    assert.deepEqual(rt.clock.slept, [0.05, 0.05]);
  });

  it("checks every property rather than stopping at the first mismatch", async () => {
    const device = new FakePTPDevice({
      intReadOverrides: { [PROP_FILM_SIMULATION]: 6, 0xd195: 9 },
    });

    const mismatched = await verifyWrittenProperties(
      device,
      [
        [PROP_FILM_SIMULATION, 11],
        [0xd195, 2],
      ],
      runtime()
    );

    assert.deepEqual(mismatched, [PROP_FILM_SIMULATION, 0xd195]);
  });
});
