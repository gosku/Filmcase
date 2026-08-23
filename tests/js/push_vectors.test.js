/**
 * JavaScript half of the shared push sequences.
 *
 * The Python replays the same scenarios. Between them these say the browser and
 * the server hit the camera with the same writes, in the same order, with the
 * same pauses, and fail in the same way.
 *
 * This is the fixture that covers the use case rather than its parts. The
 * others pin how a packet is framed, what a recipe converts to and which
 * recipes are rejected; a port can get all three right and still write them in
 * the wrong order, or keep going when it should stop.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { makeClock } from "./fakes/clock.js";
import { makeConfig } from "./fakes/config.js";
import { FakePTPDevice } from "./fakes/ptp_device.js";
import { ENCODINGS, RECIPE_VECTORS } from "./fakes/vectors.js";
import {
  CameraConnectionError,
  CameraWriteError,
} from "../../src/interfaces/static/js/camera/vendor/ptp_device.js";
import {
  RecipeWriteError,
  pushRecipeToCamera,
} from "../../src/interfaces/static/js/camera/application/usecases/push_recipe.js";

const PUSH = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../fixtures/camera/push_vectors.json", import.meta.url)),
    "utf8"
  )
);

const CODES = ENCODINGS.custom_slot_codes;

/** A fake that keeps every write attempted, refused ones included. */
class Recording extends FakePTPDevice {
  constructor(options) {
    super(options);
    this.attempted = [];
    this.readBacks = [];
  }

  async setPropertyInt(code, value) {
    this.attempted.push([code, value]);
    return super.setPropertyInt(code, value);
  }

  async setPropertyUint16(code, value) {
    this.attempted.push([code, value]);
    return super.setPropertyUint16(code, value);
  }

  async setPropertyString(code, value) {
    this.attempted.push([code, value]);
    return super.setPropertyString(code, value);
  }

  async getPropertyInt(code) {
    this.readBacks.push(code);
    return super.getPropertyInt(code);
  }

  async getPropertyString(code) {
    this.readBacks.push(code);
    return super.getPropertyString(code);
  }
}

function deviceFor(behaviour) {
  const reject = {};
  for (const [name, rc] of Object.entries(behaviour.reject ?? {})) {
    reject[CODES[name]] = rc;
  }
  if ("reject_cursor" in behaviour) reject[ENCODINGS.prop_slot_cursor] = behaviour.reject_cursor;
  if ("reject_slot_name" in behaviour) reject[ENCODINGS.prop_slot_name] = behaviour.reject_slot_name;

  const setErrors = {};
  for (const name of behaviour.fail ?? []) {
    setErrors[CODES[name]] = new CameraConnectionError("camera stopped answering");
  }

  const intReadOverrides = {};
  for (const [name, value] of Object.entries(behaviour.read_overrides ?? {})) {
    intReadOverrides[CODES[name]] = value;
  }

  return new Recording({
    setRejectionCodes: reject,
    setErrors,
    intReadOverrides,
  });
}

/** Run one scenario against the current code and record what it did. */
async function replay(scenario) {
  const recipe = RECIPE_VECTORS.find((v) => v.name === scenario.recipe).recipe;
  const clock = makeClock();
  const runtime = {
    config: makeConfig({
      ...PUSH.settings,
      CAMERA_VERIFY_WRITES: Boolean(scenario.device.verify),
    }),
    sleep: clock.sleep,
  };
  const device = deviceFor(scenario.device);

  let error = null;
  try {
    await pushRecipeToCamera(device, recipe, {
      slotIndex: PUSH.slot_index,
      runtime,
    });
  } catch (caught) {
    if (caught instanceof RecipeWriteError) {
      error = { type: "RecipeWriteError", failed_properties: caught.failedProperties };
    } else if (caught instanceof CameraConnectionError) {
      error = { type: "CameraConnectionError", message: caught.message };
    } else if (caught instanceof CameraWriteError) {
      error = { type: "CameraWriteError", code: caught.code };
    } else {
      throw caught;
    }
  }

  return {
    writes: device.attempted,
    sleeps: clock.slept.map((s) => Number(s.toFixed(6))),
    reads: device.readBacks,
    error,
  };
}

describe("shared push vectors", () => {
  for (const scenario of PUSH.scenarios) {
    describe(scenario.name, () => {
      it("writes the same sequence the Python does", async () => {
        const result = await replay(scenario);

        assert.deepEqual(result.writes, scenario.writes, scenario.why);
      });

      it("pauses in the same places the Python does", async () => {
        // The delays are distinct in this fixture, so this says which pause
        // happened where, not merely how many there were.
        const result = await replay(scenario);

        assert.deepEqual(result.sleeps, scenario.sleeps, scenario.why);
      });

      it("fails the same way the Python does", async () => {
        const result = await replay(scenario);

        assert.deepEqual(result.error, scenario.error, scenario.why);
      });

      it("reads back the same properties the Python does", async () => {
        const result = await replay(scenario);

        assert.deepEqual(result.reads, scenario.reads, scenario.why);
      });
    });
  }

  it("has scenarios to replay", () => {
    // A fixture that lost this section would turn every test above into zero
    // tests without failing anything.
    assert.ok(PUSH.scenarios.length >= 10);
  });
});
