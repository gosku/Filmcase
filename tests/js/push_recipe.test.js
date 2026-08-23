/**
 * Writing a recipe into a slot.
 *
 * The assertions worth having are about order and about failure. Order,
 * because every write lands wherever the cursor points and the colour
 * temperature has to precede the shifts. Failure, because a refused property
 * and a vanished camera look similar from inside and mean opposite things.
 */

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

import { makeClock } from "./fakes/clock.js";
import { makeConfig, PROP_SLOT_CURSOR, PROP_SLOT_NAME } from "./fakes/config.js";
import { FakePTPDevice } from "./fakes/ptp_device.js";
import { ENCODINGS, makeRecipe } from "./fakes/vectors.js";
import {
  CameraConnectionError,
  CameraWriteError,
} from "../../src/interfaces/static/js/camera/vendor/ptp_device.js";
import { RecipeValidationError } from "../../src/interfaces/static/js/camera/domain/validation.js";
import { reset } from "../../src/interfaces/static/js/camera/vendor/events.js";
import {
  RecipeWriteError,
  pushRecipeToCamera,
} from "../../src/interfaces/static/js/camera/application/usecases/push_recipe.js";

const CODES = ENCODINGS.custom_slot_codes;

function runtime(overrides = {}) {
  const clock = makeClock();
  return { config: makeConfig(overrides), sleep: clock.sleep, clock };
}

async function push(device, { recipe = makeRecipe(), slotIndex = 2, rt = runtime() } = {}) {
  await pushRecipeToCamera(device, recipe, { slotIndex, runtime: rt });
}

/** Codes written, in order, excluding the cursor. */
function propertyWrites(device) {
  return device.writes.map(([code]) => code).filter((code) => code !== PROP_SLOT_CURSOR);
}

beforeEach(() => reset());

describe("pushRecipeToCamera", () => {
  it("points at the slot before writing anything", async () => {
    // Every later write lands wherever the cursor is, so this being first is
    // the difference between filling C2 and overwriting whatever was current.
    const device = new FakePTPDevice();

    await push(device, { slotIndex: 3 });

    assert.deepEqual(device.writes[0], [PROP_SLOT_CURSOR, 3]);
  });

  it("writes the slot name before the recipe properties", async () => {
    const device = new FakePTPDevice();

    await push(device);

    assert.equal(propertyWrites(device)[0], PROP_SLOT_NAME);
  });

  it("writes every property the conversion produced", async () => {
    const device = new FakePTPDevice();

    await push(device);

    // Name plus the fifteen properties this recipe sets.
    assert.equal(propertyWrites(device).length, 16);
  });

  it("writes the properties in the server's order", async () => {
    const device = new FakePTPDevice();

    await push(device);

    const expected = ENCODINGS.write_order
      .map((name) => CODES[name])
      .filter((code) => propertyWrites(device).includes(code));
    assert.deepEqual(propertyWrites(device).slice(1), expected);
  });

  it("writes the colour temperature before the two shifts", async () => {
    // Writing the shifts first makes the camera zero them when the temperature
    // lands, which produces a recipe that looks right in the app and wrong on
    // the camera.
    const device = new FakePTPDevice();

    await push(device, { recipe: makeRecipe({ white_balance: "6500K", white_balance_red: -2 }) });

    const order = propertyWrites(device);
    assert.ok(
      order.indexOf(CODES.WhiteBalanceColorTemperature) < order.indexOf(CODES.WhiteBalanceRed)
    );
  });

  it("stores the name as a string, not as an integer", async () => {
    const device = new FakePTPDevice();

    await push(device, { recipe: makeRecipe({ name: "Kodak Portra" }) });

    assert.equal(await device.getPropertyString(PROP_SLOT_NAME), "Kodak Portra");
  });
});

describe("timing", () => {
  it("pauses before and after every write", async () => {
    const device = new FakePTPDevice();
    const rt = runtime({ CAMERA_PRE_WRITE_DELAY_S: 0.05, CAMERA_POST_WRITE_DELAY_S: 0.2 });

    await push(device, { rt });

    // One pause after the cursor, then a pre/post pair per write.
    const writes = propertyWrites(device).length;
    assert.equal(rt.clock.slept.length, 1 + writes * 2);
    assert.equal(rt.clock.slept[0], 0.05);
    assert.deepEqual(rt.clock.slept.slice(1, 3), [0.05, 0.2]);
  });

  it("still pauses after a refused write", async () => {
    // The camera handled a request either way, so the next one needs the same
    // breathing room; skipping it is how a refusal turns into a cascade.
    const device = new FakePTPDevice({
      setRejectionCodes: { [CODES.FilmSimulation]: 0x2005 },
    });
    const rt = runtime({ CAMERA_POST_WRITE_DELAY_S: 0.2 });

    await assert.rejects(() => push(device, { rt }));

    const posts = rt.clock.slept.filter((s) => s === 0.2);
    assert.equal(posts.length, propertyWrites(device).length);
  });
});

describe("a camera that refuses one property", () => {
  it("carries on writing the rest", async () => {
    // The camera is still there. Abandoning eighteen good properties because
    // of one refusal would leave a far worse slot than finishing does.
    const device = new FakePTPDevice({
      setRejectionCodes: { [CODES.FilmSimulation]: 0x2005 },
    });

    await assert.rejects(() => push(device), (error) => error instanceof RecipeWriteError);

    assert.ok(propertyWrites(device).includes(CODES.Definition));
  });

  it("names the property that did not take", async () => {
    const device = new FakePTPDevice({
      setRejectionCodes: { [CODES.FilmSimulation]: 0x2005 },
    });

    await assert.rejects(
      () => push(device),
      (error) => {
        assert.deepEqual(error.failedProperties, ["FilmSimulation"]);
        return true;
      }
    );
  });

  it("names every property that did not take", async () => {
    const device = new FakePTPDevice({
      setRejectionCodes: { [CODES.FilmSimulation]: 0x2005, [CODES.Sharpness]: 0x2005 },
    });

    await assert.rejects(
      () => push(device),
      (error) => {
        assert.deepEqual(error.failedProperties, ["FilmSimulation", "Sharpness"]);
        return true;
      }
    );
  });

  it("reports a refused slot name by name", async () => {
    const device = new FakePTPDevice({ setRejectionCodes: { [PROP_SLOT_NAME]: 0x2005 } });

    await assert.rejects(
      () => push(device),
      (error) => {
        assert.deepEqual(error.failedProperties, ["SlotName"]);
        return true;
      }
    );
  });

  it("reads the same as the Python's message", async () => {
    const error = new RecipeWriteError(["SlotName", "FilmSimulation"]);

    assert.equal(
      error.message,
      "Recipe write incomplete: 2 property/properties failed (['SlotName', 'FilmSimulation'])"
    );
  });
});

describe("a camera that stops answering", () => {
  it("abandons the sequence rather than working through the rest", async () => {
    // Continuing would spend three retries each on every remaining property
    // before failing anyway, which is a long wait for a foregone conclusion.
    const device = new FakePTPDevice({
      setErrors: { [CODES.FilmSimulation]: new CameraConnectionError("unplugged") },
    });

    await assert.rejects(() => push(device), (error) => error instanceof CameraConnectionError);

    assert.ok(!propertyWrites(device).includes(CODES.Definition));
  });

  it("reports a connection failure, not an incomplete write", async () => {
    // They mean different things to the user: one says try again, the other
    // says check the cable.
    const device = new FakePTPDevice({
      setErrors: { [CODES.FilmSimulation]: new CameraConnectionError("unplugged") },
    });

    await assert.rejects(
      () => push(device),
      (error) =>
        error instanceof CameraConnectionError && !(error instanceof RecipeWriteError)
    );
  });

  it("refuses the push when the slot cursor will not move", async () => {
    // Nothing has been written yet, so there is no partly applied recipe: the
    // user only needs to know the push never started.
    const device = new FakePTPDevice({ setRejectionCodes: { [PROP_SLOT_CURSOR]: 0x2005 } });

    await assert.rejects(
      () => push(device),
      (error) =>
        error instanceof CameraConnectionError && /slot cursor/.test(error.message)
    );
    assert.equal(propertyWrites(device).length, 0);
  });
});

describe("an invalid recipe", () => {
  it("never reaches the camera", async () => {
    const device = new FakePTPDevice();

    await assert.rejects(
      () => push(device, { recipe: makeRecipe({ film_simulation: "Velvia 100F" }) }),
      (error) => error instanceof RecipeValidationError
    );

    assert.equal(propertyWrites(device).length, 0);
  });

  it("leaves the slot as the user left it", async () => {
    // The cursor has moved, which changes nothing the user can see; no value
    // in the slot has been touched.
    const device = new FakePTPDevice();

    await assert.rejects(() => push(device, { recipe: makeRecipe({ color: "1.5" }) }));

    assert.deepEqual(device.writes, [[PROP_SLOT_CURSOR, 2]]);
  });
});

describe("verification", () => {
  it("is skipped unless it is switched on", async () => {
    const device = new FakePTPDevice();

    await push(device);

    assert.equal(device.reads.length, 0);
  });

  it("reads back every property when switched on", async () => {
    const device = new FakePTPDevice();
    const rt = runtime({ CAMERA_VERIFY_WRITES: true });

    await push(device, { rt });

    assert.ok(device.reads.length > 0);
  });

  it("does not read back grain written as the sentinel", async () => {
    // The camera normalises the sentinel to something else, so its read-back
    // never matches and verifying it would fail every push with grain off.
    const device = new FakePTPDevice();
    const rt = runtime({ CAMERA_VERIFY_WRITES: true });
    const recipe = makeRecipe({ grain_roughness: "Off", grain_size: null });

    await push(device, { recipe, rt });

    assert.ok(!device.reads.includes(CODES.GrainEffect));
  });

  it("reads back grain that was not the sentinel", async () => {
    const device = new FakePTPDevice();
    const rt = runtime({ CAMERA_VERIFY_WRITES: true });
    const recipe = makeRecipe({ grain_roughness: "Weak", grain_size: "Small" });

    await push(device, { recipe, rt });

    assert.ok(device.reads.includes(CODES.GrainEffect));
  });

  it("reports a property that did not stick", async () => {
    // A write can report success and still not take; this is the only thing
    // that would notice.
    const device = new FakePTPDevice({ intReadOverrides: { [CODES.Sharpness]: 999 } });
    const rt = runtime({ CAMERA_VERIFY_WRITES: true });

    await assert.rejects(
      () => push(device, { rt }),
      (error) => {
        assert.ok(error instanceof RecipeWriteError);
        assert.deepEqual(error.failedProperties, ["Sharpness"]);
        return true;
      }
    );
  });

  it("does not report a property that was refused and so never verified", async () => {
    // It is already in the failure list; counting it twice would tell the user
    // one setting failed in two different ways.
    const device = new FakePTPDevice({
      setRejectionCodes: { [CODES.Sharpness]: 0x2005 },
    });
    const rt = runtime({ CAMERA_VERIFY_WRITES: true });

    await assert.rejects(
      () => push(device, { rt }),
      (error) => {
        assert.deepEqual(error.failedProperties, ["Sharpness"]);
        return true;
      }
    );
  });
});

describe("a push that works", () => {
  it("resolves without throwing", async () => {
    const device = new FakePTPDevice();

    await push(device);
  });

  it("leaves every value in the slot", async () => {
    const device = new FakePTPDevice();

    await push(device, { recipe: makeRecipe({ sharpness: "+2" }) });

    assert.equal(await device.getPropertyInt(CODES.Sharpness), 20);
  });

  it("resolves with verification switched on", async () => {
    const device = new FakePTPDevice();

    await push(device, { rt: runtime({ CAMERA_VERIFY_WRITES: true }) });
  });
});
