/**
 * Tests for the camera strategy registry.
 *
 * The strategy's read and push algorithms are exercised end to end through the
 * use cases in get_camera_slots.test.js and push_recipe.test.js, which now
 * delegate to it. This covers the registry seam itself.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  PerPropertyStrategy,
  getStrategy,
} from "../../src/interfaces/static/js/camera/domain/strategies.js";

describe("getStrategy", () => {
  it("resolves a known model to the per-property strategy", () => {
    assert.ok(getStrategy("X-S10") instanceof PerPropertyStrategy);
  });

  it("resolves an unknown model to the per-property strategy", () => {
    assert.ok(getStrategy("NOT-A-CAMERA") instanceof PerPropertyStrategy);
  });

  it("returns a strategy exposing readSlots and pushRecipe", () => {
    const strategy = getStrategy("X-S10");
    assert.equal(typeof strategy.readSlots, "function");
    assert.equal(typeof strategy.pushRecipe, "function");
  });
});
