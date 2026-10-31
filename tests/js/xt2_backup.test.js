/**
 * The browser X-T2 backup codec, asserted against the same committed pristine
 * blob and served layout as the Python codec (tests/unit/domain/camera/
 * test_xt2_backup_codec.py). Parity here is what lets the two run the same
 * read-modify-restore on the same bytes.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { makeConfig } from "./fakes/config.js";
import {
  RecipeNotRepresentable,
  applyRecipe,
  checkCollectionFeasibility,
  checkFeasibility,
  decodeSlotRecipe,
  decodeSlotStates,
  mapRecipe,
  prepareXt2,
  validateBackup,
  verifyRoundTrip,
} from "../../src/interfaces/static/js/camera/domain/xt2_backup.js";

const PRISTINE = new Uint8Array(
  readFileSync(fileURLToPath(new URL("../fixtures/camera/xt2_backup_pristine.bin", import.meta.url)))
);
const PROFILE = JSON.parse(
  readFileSync(fileURLToPath(new URL("../fixtures/camera/xt2_profile.json", import.meta.url)), "utf8")
);
const X = prepareXt2(PROFILE.xt2);
const ENCODINGS = makeConfig().encodings;

function recipe(overrides = {}) {
  return {
    name: "Test Recipe",
    film_simulation: "Classic Chrome",
    d_range_priority: "Off",
    grain_roughness: "Off",
    color_chrome_effect: "Off",
    color_chrome_fx_blue: "Off",
    grain_size: "",
    white_balance: "Daylight",
    white_balance_red: 0,
    white_balance_blue: 0,
    color: "0",
    sharpness: "0",
    high_iso_nr: "0",
    clarity: "0",
    dynamic_range: "DR200",
    highlight: "0",
    shadow: "0",
    ...overrides,
  };
}

describe("validateBackup", () => {
  it("accepts the pristine blob", () => {
    assert.equal(validateBackup(PRISTINE, X).ok, true);
  });

  it("rejects the wrong size", () => {
    assert.equal(validateBackup(PRISTINE.subarray(0, PRISTINE.length - 1), X).ok, false);
  });

  it("rejects bad magic", () => {
    const corrupt = Uint8Array.from(PRISTINE);
    corrupt.fill(0, 0, 8);
    assert.equal(validateBackup(corrupt, X).ok, false);
  });

  it("rejects an invalid film-sim byte", () => {
    const corrupt = Uint8Array.from(PRISTINE);
    corrupt[X.slot0Offset + X.off.film_simulation] = 0x7f;
    assert.equal(validateBackup(corrupt, X).ok, false);
  });
});

describe("decode", () => {
  it("reads seven slots", () => {
    const states = decodeSlotStates(PRISTINE, X, ENCODINGS);
    assert.deepEqual(
      states.map((s) => s.index),
      [1, 2, 3, 4, 5, 6, 7]
    );
  });

  it("decodes a known slot", () => {
    const states = decodeSlotStates(PRISTINE, X, ENCODINGS);
    assert.equal(states[1].name, "KODACHROME 2");
    assert.equal(states[1].filmSimPtp, ENCODINGS.film_simulation_to_ptp["Classic Chrome"]);
  });

  it("decodes recipe fields, leaving X-T2-absent ones empty", () => {
    const decoded = decodeSlotRecipe(PRISTINE, 2, X);
    assert.equal(decoded.film_simulation, "Classic Chrome");
    assert.equal(decoded.white_balance, "Auto");
    assert.equal(decoded.dynamic_range, "DR200");
    assert.equal(decoded.clarity, "");
    assert.equal(decoded.color_chrome_effect, "");
    assert.equal(decoded.grain_size, "");
  });
});

describe("mapRecipe", () => {
  it("drops the fields the X-T2 lacks", () => {
    const mapping = mapRecipe(
      recipe({ clarity: "3", color_chrome_effect: "Strong" }),
      X
    );
    assert.deepEqual(mapping.dropped, ["Clarity", "Color Chrome Effect"]);
  });

  it("rejects a film simulation the X-T2 lacks", () => {
    assert.throws(() => mapRecipe(recipe({ film_simulation: "Eterna" }), X), RecipeNotRepresentable);
  });

  it("rejects a measured-custom white balance by mapping, not here", () => {
    // Custom WB maps (it is a selector) but is refused at feasibility time.
    const mapping = mapRecipe(recipe({ white_balance: "Custom 1" }), X);
    assert.equal(checkFeasibility(PRISTINE, 0, mapping, X).ok, false);
  });
});

describe("apply round-trips through decode", () => {
  it("writes a recipe that decodes back and still validates", () => {
    const mapping = mapRecipe(recipe({ name: "NEW", white_balance: "Underwater" }), X);
    const edited = applyRecipe(PRISTINE, 0, mapping, X);
    assert.equal(validateBackup(edited, X).ok, true);
    assert.equal(decodeSlotRecipe(edited, 1, X).name, "NEW");
    assert.equal(decodeSlotRecipe(edited, 1, X).film_simulation, "Classic Chrome");
  });
});

describe("feasibility", () => {
  it("a free WB is feasible for every slot", () => {
    const mapping = mapRecipe(recipe({ white_balance: "Underwater", white_balance_red: 5 }), X);
    assert.equal(checkFeasibility(PRISTINE, 0, mapping, X).ok, true);
  });

  it("retuning a shared WB conflicts", () => {
    const mapping = mapRecipe(
      recipe({ white_balance: "Auto", white_balance_red: 5, white_balance_blue: 5 }),
      X
    );
    assert.equal(checkFeasibility(PRISTINE, 0, mapping, X).ok, false);
  });

  it("a collection needing two shifts on one WB conflicts", () => {
    const a = mapRecipe(recipe({ white_balance: "Underwater", white_balance_red: 3 }), X);
    const b = mapRecipe(recipe({ white_balance: "Underwater", white_balance_red: -3 }), X);
    assert.equal(
      checkCollectionFeasibility(PRISTINE, [[0, a], [1, b]], X).ok,
      false
    );
  });
});

describe("verifyRoundTrip", () => {
  it("a blob matches itself", () => {
    assert.equal(verifyRoundTrip(PRISTINE, PRISTINE, X).ok, true);
  });

  it("ignores the per-slot write counter", () => {
    const readBack = Uint8Array.from(PRISTINE);
    readBack[X.slot0Offset + X.slotWriteCounterOffset] ^= 0xff;
    assert.equal(verifyRoundTrip(readBack, PRISTINE, X).ok, true);
  });

  it("flags a changed recipe byte", () => {
    const readBack = Uint8Array.from(PRISTINE);
    readBack[X.slot0Offset + X.off.film_simulation] ^= 0x01;
    assert.equal(verifyRoundTrip(readBack, PRISTINE, X).ok, false);
  });
});
