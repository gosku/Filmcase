/**
 * Tests for the camera strategy registry.
 *
 * The strategy's read and push algorithms are exercised end to end through the
 * use cases in get_camera_slots.test.js and push_recipe.test.js, which now
 * delegate to it. This covers the registry seam itself.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { makeConfig } from "./fakes/config.js";
import {
  BackupBlobStrategy,
  PerPropertyStrategy,
  PushNotFeasibleError,
  getStrategy,
} from "../../src/interfaces/static/js/camera/domain/strategies.js";
import {
  decodeSlotRecipe,
  prepareXt2,
} from "../../src/interfaces/static/js/camera/domain/xt2_backup.js";

const PRISTINE = new Uint8Array(
  readFileSync(fileURLToPath(new URL("../fixtures/camera/xt2_backup_pristine.bin", import.meta.url)))
);
const PROFILE = JSON.parse(
  readFileSync(fileURLToPath(new URL("../fixtures/camera/xt2_profile.json", import.meta.url)), "utf8")
);
const X = prepareXt2(PROFILE.xt2);

function xt2Config(settingOverrides = {}) {
  return { ...makeConfig(settingOverrides), profile: PROFILE };
}

function xt2Runtime(settingOverrides = {}) {
  return { config: xt2Config(settingOverrides), sleep: async () => {} };
}

function xt2Device() {
  const state = { blob: Uint8Array.from(PRISTINE), restored: [] };
  return {
    cameraName: "X-T2",
    async getBackup() {
      return state.blob;
    },
    async restoreBackup(blob) {
      state.restored.push(Uint8Array.from(blob));
      state.blob = Uint8Array.from(blob);
    },
    get restored() {
      return state.restored;
    },
  };
}

function recipe(overrides = {}) {
  return {
    name: "Test Recipe",
    film_simulation: "Classic Chrome",
    d_range_priority: "Off",
    grain_roughness: "Off",
    color_chrome_effect: "Off",
    color_chrome_fx_blue: "Off",
    grain_size: "",
    white_balance: "Underwater",
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

describe("getStrategy", () => {
  it("resolves a known model to the per-property strategy", () => {
    assert.ok(getStrategy("X-S10") instanceof PerPropertyStrategy);
  });

  it("resolves an unknown model to the per-property strategy", () => {
    assert.ok(getStrategy("NOT-A-CAMERA") instanceof PerPropertyStrategy);
  });

  it("resolves the X-T2 to the backup-blob strategy from the served profile", () => {
    assert.ok(getStrategy("X-T2", xt2Config()) instanceof BackupBlobStrategy);
  });

  it("returns a strategy exposing readSlots and pushRecipe", () => {
    const strategy = getStrategy("X-S10");
    assert.equal(typeof strategy.readSlots, "function");
    assert.equal(typeof strategy.pushRecipe, "function");
  });
});

describe("BackupBlobStrategy", () => {
  const strategy = () => new BackupBlobStrategy(X);

  it("reads the slots from the backup", async () => {
    const slots = await strategy().readSlots(xt2Device(), { slotCount: 7, runtime: xt2Runtime() });
    assert.deepEqual(slots.map((s) => s.index), [1, 2, 3, 4, 5, 6, 7]);
    assert.equal(slots[1].name, "KODACHROME 2");
  });

  it("pushes a feasible recipe, restoring once", async () => {
    const device = xt2Device();
    await strategy().pushRecipe(device, recipe({ name: "NEW" }), { slotIndex: 1, runtime: xt2Runtime() });
    assert.equal(device.restored.length, 1);
    assert.equal(decodeSlotRecipe(device.restored[0], 1, X).name, "NEW");
  });

  it("refuses an infeasible push and writes nothing", async () => {
    const device = xt2Device();
    const clash = recipe({ white_balance: "Auto", white_balance_red: 5, white_balance_blue: 5 });
    await assert.rejects(
      () => strategy().pushRecipe(device, clash, { slotIndex: 1, runtime: xt2Runtime() }),
      PushNotFeasibleError
    );
    assert.equal(device.restored.length, 0);
  });

  it("pushes a collection as one restore", async () => {
    const device = xt2Device();
    const assignments = [
      [1, recipe({ name: "A", white_balance: "Underwater" })],
      [2, recipe({ name: "B", white_balance: "Fluorescent 3" })],
    ];
    await strategy().pushCollection(device, assignments, { runtime: xt2Runtime() });
    assert.equal(device.restored.length, 1);
    assert.equal(decodeSlotRecipe(device.restored[0], 1, X).name, "A");
    assert.equal(decodeSlotRecipe(device.restored[0], 2, X).name, "B");
  });

  it("reports feasibility and dropped fields for the picker", async () => {
    const plan = await strategy().planFeasibility(
      xt2Device(),
      recipe({ white_balance: "Underwater", clarity: "3" }),
      { slotCount: 7, runtime: xt2Runtime() }
    );
    assert.ok(plan.slots.every((s) => s.feasible));
    assert.deepEqual(plan.droppedFields, ["Clarity"]);
  });
});
