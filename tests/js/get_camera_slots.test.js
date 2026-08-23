/**
 * Reading the custom slots.
 *
 * The assertion that matters most is the ordering one: every read depends on
 * the cursor written before it, so a lost await would return several readings
 * of whichever slot the camera happened to be pointing at, which looks like a
 * correct answer rather than a failure.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { makeClock } from "./fakes/clock.js";
import { makeConfig, PROP_FILM_SIMULATION, PROP_SLOT_CURSOR, PROP_SLOT_NAME } from "./fakes/config.js";
import { FakePTPDevice } from "./fakes/ptp_device.js";
import {
  CameraConnectionError,
  CameraWriteError,
} from "../../src/interfaces/static/js/camera/vendor/ptp_device.js";
import { getCameraSlots } from "../../src/interfaces/static/js/camera/application/usecases/get_camera_slots.js";

function runtime(overrides = {}) {
  const clock = makeClock();
  return { config: makeConfig(overrides), sleep: clock.sleep, clock };
}

/**
 * A camera whose slots hold distinct values, so a test can tell which slot a
 * read actually came from.
 */
class SlotAwareDevice extends FakePTPDevice {
  constructor(slots, options = {}) {
    super(options);
    this._slots = slots;
    this._cursor = 1;
    /** The cursor positions written, in order. */
    this.cursors = [];
    /** (cursor, code) for every read, so ordering can be asserted. */
    this.readsAtCursor = [];
  }

  // These go through _oneAtATime and the unguarded helpers rather than super,
  // so the base class's overlap guard still applies exactly once per call.
  async setPropertyUint16(code, value) {
    return this._oneAtATime(() => {
      const rc = this._write(code, value, "_intStore", (v) => v & 0xffff);
      if (code === PROP_SLOT_CURSOR && rc === 0) {
        this.cursors.push(value);
        this._cursor = value;
      }
      return rc;
    });
  }

  async getPropertyString(code) {
    return this._oneAtATime(() => {
      this.readsAtCursor.push([this._cursor, code]);
      this._readString(code); // let the error knobs apply
      return code === PROP_SLOT_NAME
        ? this._slots[this._cursor - 1].name
        : this._readString(code);
    });
  }

  async getPropertyInt(code) {
    return this._oneAtATime(() => {
      this.readsAtCursor.push([this._cursor, code]);
      this._readInt(code);
      return code === PROP_FILM_SIMULATION
        ? this._slots[this._cursor - 1].filmSim
        : this._readInt(code);
    });
  }
}

const FOUR_SLOTS = [
  { name: "Portra", filmSim: 11 },
  { name: "Acros", filmSim: 12 },
  { name: "", filmSim: 1 },
  { name: "Eterna", filmSim: 16 },
];

describe("getCameraSlots", () => {
  it("reads one state per slot the model offers", async () => {
    const device = new SlotAwareDevice(FOUR_SLOTS, { cameraName: "X-S10" });

    const states = await getCameraSlots(device, runtime());

    assert.equal(states.length, 4);
    assert.deepEqual(states.map((s) => s.index), [1, 2, 3, 4]);
  });

  it("returns the name and film simulation of each slot", async () => {
    const device = new SlotAwareDevice(FOUR_SLOTS, { cameraName: "X-S10" });

    const states = await getCameraSlots(device, runtime());

    assert.deepEqual(states.map((s) => s.name), ["Portra", "Acros", "", "Eterna"]);
    assert.deepEqual(states.map((s) => s.filmSimName), [
      "Classic Chrome",
      "Acros STD",
      "Provia",
      "Eterna",
    ]);
  });

  it("moves the cursor to each slot in turn", async () => {
    const device = new SlotAwareDevice(FOUR_SLOTS, { cameraName: "X-S10" });

    await getCameraSlots(device, runtime());

    assert.deepEqual(device.cursors, [1, 2, 3, 4]);
  });

  it("reads each slot only after pointing at it", async () => {
    // The failure this prevents is silent: reads that overlap the cursor
    // return a plausible-looking list of the wrong slots.
    const device = new SlotAwareDevice(FOUR_SLOTS, { cameraName: "X-S10" });

    await getCameraSlots(device, runtime());

    for (const [cursor, code] of device.readsAtCursor) {
      assert.ok([PROP_SLOT_NAME, PROP_FILM_SIMULATION].includes(code));
      assert.ok(cursor >= 1 && cursor <= 4);
    }
    // Two reads per slot, grouped: 1,1,2,2,3,3,4,4.
    assert.deepEqual(
      device.readsAtCursor.map(([cursor]) => cursor),
      [1, 1, 2, 2, 3, 3, 4, 4]
    );
  });

  it("pauses after each cursor move before reading", async () => {
    // Reading too soon returns the previous slot's values.
    const device = new SlotAwareDevice(FOUR_SLOTS, { cameraName: "X-S10" });
    const rt = runtime({ CAMERA_POST_CURSOR_DELAY_S: 0.05, CAMERA_INTER_SLOT_DELAY_S: 0.02 });

    await getCameraSlots(device, rt);

    // First slot: cursor pause only. Each later slot: inter-slot then cursor.
    assert.deepEqual(rt.clock.slept, [0.05, 0.02, 0.05, 0.02, 0.05, 0.02, 0.05]);
  });

  it("returns nothing for a model with no custom slots", async () => {
    const device = new SlotAwareDevice(FOUR_SLOTS, { cameraName: "X-H9" });

    const states = await getCameraSlots(device, runtime());

    assert.deepEqual(states, []);
    assert.deepEqual(device.cursors, []);
  });

  it("returns nothing when the camera reported no name", async () => {
    // Better than guessing four: a write into a slot that does not exist goes
    // nowhere useful and the user is told nothing happened.
    const device = new SlotAwareDevice(FOUR_SLOTS, { cameraName: "" });

    assert.deepEqual(await getCameraSlots(device, runtime()), []);
  });

  it("retries a transport failure and carries on", async () => {
    const device = new SlotAwareDevice(FOUR_SLOTS, {
      cameraName: "X-S10",
      setFailuresBeforeSuccess: { [PROP_SLOT_CURSOR]: 2 },
    });

    const states = await getCameraSlots(device, runtime());

    assert.equal(states.length, 4);
  });

  it("backs off exponentially between attempts", async () => {
    const device = new SlotAwareDevice(FOUR_SLOTS, {
      cameraName: "X-S10",
      setFailuresBeforeSuccess: { [PROP_SLOT_CURSOR]: 2 },
    });
    const rt = runtime({ CAMERA_POST_CURSOR_DELAY_S: 0, CAMERA_INTER_SLOT_DELAY_S: 0 });

    await getCameraSlots(device, rt);

    assert.deepEqual(rt.clock.slept.filter((s) => s > 0), [0.15, 0.3]);
  });

  it("gives up when the camera stays unreachable", async () => {
    const device = new SlotAwareDevice(FOUR_SLOTS, {
      cameraName: "X-S10",
      defaultGetError: new CameraConnectionError("gone"),
    });

    await assert.rejects(
      () => getCameraSlots(device, runtime()),
      (error) => error instanceof CameraConnectionError
    );
  });

  it("does not retry a refused cursor write", async () => {
    // The camera answered and declined, so repeating it only delays the error.
    const device = new SlotAwareDevice(FOUR_SLOTS, {
      cameraName: "X-S10",
      setRejectionCodes: { [PROP_SLOT_CURSOR]: 0x2005 },
    });

    await assert.rejects(
      () => getCameraSlots(device, runtime()),
      (error) => error instanceof CameraWriteError
    );
    // Attempts, not successes: a refused write never moves the cursor, so
    // counting moves would pass even if it had been tried three times.
    const attempts = device.writes.filter(([code]) => code === PROP_SLOT_CURSOR);
    assert.equal(attempts.length, 1);
  });

  it("names an unrecognised film simulation rather than blanking it", async () => {
    // A slot set from the camera body to something this build has not heard of
    // is worth showing as-is; an empty cell reads as an empty slot.
    const slots = [{ name: "Mystery", filmSim: 99 }, ...FOUR_SLOTS.slice(1)];
    const device = new SlotAwareDevice(slots, { cameraName: "X-S10" });

    const states = await getCameraSlots(device, runtime());

    assert.equal(states[0].filmSimName, "Unknown(99)");
    assert.equal(states[1].filmSimName, "Acros STD");
  });
});
