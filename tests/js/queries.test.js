/**
 * Recipe to PTP value conversion.
 *
 * The golden vectors carry the weight here: the same twelve recipes are
 * asserted by the Python, so these tests say the two implementations agree
 * rather than merely that this one behaves as I expected.
 *
 * The cases below the vectors cover the scaling rules individually, because a
 * vector failing tells you a recipe converted wrongly and not which rule broke.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { ENCODINGS, RECIPE_VECTORS, makeRecipe } from "./fakes/vectors.js";
import { RecipeValidationError } from "../../src/interfaces/static/js/camera/domain/validation.js";
import {
  customSlotCount,
  makeSlotState,
  ptpValueItems,
  recipeToPtpValues,
} from "../../src/interfaces/static/js/camera/domain/queries.js";

/** Convert and flatten, which is what the push sequence actually consumes. */
function itemsFor(overrides = {}) {
  const values = recipeToPtpValues(makeRecipe(overrides), ENCODINGS);
  return ptpValueItems(values, ENCODINGS);
}

/** The value written for one property name, or undefined if not written. */
function written(name, overrides = {}) {
  const code = ENCODINGS.custom_slot_codes[name];
  const found = itemsFor(overrides).find(([c]) => c === code);
  return found ? found[1] : undefined;
}

describe("shared recipe vectors", () => {
  for (const vector of RECIPE_VECTORS) {
    it(`agrees with the Python: ${vector.name}`, () => {
      const values = recipeToPtpValues(vector.recipe, ENCODINGS);

      const items = ptpValueItems(values, ENCODINGS);

      assert.deepEqual(items, vector.expected_items, vector.why);
    });
  }

  it("has vectors to assert", () => {
    assert.ok(RECIPE_VECTORS.length >= 10);
  });
});

describe("write order", () => {
  it("puts colour temperature before the two shifts", () => {
    // The rule the whole ordering exists for: shifts written first are zeroed
    // by the camera when the temperature lands.
    const codes = ENCODINGS.custom_slot_codes;
    const items = itemsFor({ white_balance: "6500K", white_balance_red: -2 });
    const order = items.map(([code]) => code);

    assert.ok(
      order.indexOf(codes.WhiteBalanceColorTemperature) < order.indexOf(codes.WhiteBalanceRed)
    );
  });

  it("follows the server's order rather than object insertion order", () => {
    const expected = ENCODINGS.write_order
      .map((name) => ENCODINGS.custom_slot_codes[name])
      .filter((code) => itemsFor().some(([c]) => c === code));

    assert.deepEqual(itemsFor().map(([code]) => code), expected);
  });

  it("omits properties that do not apply", () => {
    // A monochrome recipe has no colour. Writing a placeholder would set the
    // slot's saturation to something the recipe never asked for.
    const codes = ENCODINGS.custom_slot_codes;
    const items = itemsFor({
      film_simulation: "Acros STD",
      color: null,
      monochromatic_color_warm_cool: "+3",
    });

    assert.ok(!items.some(([code]) => code === codes.ColorMode));
  });
});

describe("integer scaling", () => {
  for (const [field, property] of [
    ["color", "ColorMode"],
    ["sharpness", "Sharpness"],
    ["clarity", "Definition"],
  ]) {
    it(`multiplies ${field} by ten`, () => {
      assert.equal(written(property, { [field]: "+2" }), 20);
    });

    it(`keeps ${field} negative`, () => {
      assert.equal(written(property, { [field]: "-4" }), -40);
    });
  }

  it("writes zero for an unset sharpness rather than omitting it", () => {
    // Always written: a slot left at its previous sharpness would silently
    // inherit whatever the last recipe put there.
    assert.equal(written("Sharpness", { sharpness: "" }), 0);
  });

  it("writes zero for an unset clarity", () => {
    assert.equal(written("Definition", { clarity: "N/A" }), 0);
  });

  it("omits colour entirely when unset", () => {
    assert.equal(written("ColorMode", { color: null }), undefined);
  });
});

describe("decimal scaling", () => {
  it("keeps a half step in the highlight curve", () => {
    // The rule most easily lost in a port: truncating would write 10 here.
    assert.equal(written("HighLightTone", { highlight: "+1.5" }), 15);
  });

  it("keeps a negative half step in the shadow curve", () => {
    assert.equal(written("ShadowTone", { shadow: "-1.5" }), -15);
  });

  it("scales whole numbers the same way", () => {
    assert.equal(written("HighLightTone", { highlight: "-2" }), -20);
  });

  it("scales the monochrome toning axes", () => {
    const overrides = {
      film_simulation: "Acros STD",
      color: null,
      monochromatic_color_warm_cool: "+3",
      monochromatic_color_magenta_green: "-2",
    };

    assert.equal(written("MonochromaticColorWarmCool", overrides), 30);
    assert.equal(written("MonochromaticColorMagentaGreen", overrides), -20);
  });
});

describe("white balance", () => {
  it("writes a named mode with no colour temperature", () => {
    assert.equal(written("WhiteBalance", { white_balance: "Daylight" }), 4);
    assert.equal(written("WhiteBalanceColorTemperature", { white_balance: "Daylight" }), undefined);
  });

  it("writes the Kelvin mode and the temperature", () => {
    const overrides = { white_balance: "6500K" };

    assert.equal(written("WhiteBalance", overrides), ENCODINGS.white_balance_to_ptp.Kelvin);
    assert.equal(written("WhiteBalanceColorTemperature", overrides), 6500);
  });

  it("passes the shifts through unscaled", () => {
    // Unlike everything else numeric, these are not multiplied by ten.
    const overrides = { white_balance_red: -9, white_balance_blue: 9 };

    assert.equal(written("WhiteBalanceRed", overrides), -9);
    assert.equal(written("WhiteBalanceBlue", overrides), 9);
  });
});

describe("dynamic range", () => {
  it("writes the mode when priority is off", () => {
    assert.equal(written("DRangeMode", { d_range_priority: "Off", dynamic_range: "DR400" }), 400);
  });

  it("omits the mode when priority is active", () => {
    // The camera owns the tone curve in this mode, so writing DRangeMode would
    // be overruled and writing the curves would be misleading.
    assert.equal(
      written("DRangeMode", { d_range_priority: "Strong", dynamic_range: "DR400" }),
      undefined
    );
  });

  it("omits the mode when no dynamic range is set", () => {
    assert.equal(written("DRangeMode", { dynamic_range: null }), undefined);
  });

  it("writes Off for an unrecognised priority rather than failing", () => {
    assert.equal(
      written("DRangePriority", { d_range_priority: "N/A" }),
      ENCODINGS.dr_priority_to_ptp.Off
    );
  });
});

describe("grain", () => {
  it("writes the sentinel when the grain is off", () => {
    // Not the value the read table would invert to: the camera normalises the
    // sentinel and keeps whichever size it last remembered.
    assert.equal(
      written("GrainEffect", { grain_roughness: "Off", grain_size: null }),
      ENCODINGS.grain_off_sentinel
    );
  });

  it("writes the sentinel whatever size an off grain carries", () => {
    assert.equal(
      written("GrainEffect", { grain_roughness: "Off", grain_size: "Large" }),
      ENCODINGS.grain_off_sentinel
    );
  });

  it("writes the table value when the grain is on", () => {
    assert.equal(written("GrainEffect", { grain_roughness: "Weak", grain_size: "Small" }), 2);
    assert.equal(written("GrainEffect", { grain_roughness: "Strong", grain_size: "Large" }), 5);
  });
});

describe("noise reduction", () => {
  it("uses the non-linear table rather than scaling", () => {
    // The values are not ordered: +2 is 0 and 0 is 0x2000. Anything that looked
    // like arithmetic here would be wrong.
    assert.equal(written("HighIsoNoiseReduction", { high_iso_nr: "+4" }), 0x5000);
    assert.equal(written("HighIsoNoiseReduction", { high_iso_nr: "0" }), 0x2000);
    assert.equal(written("HighIsoNoiseReduction", { high_iso_nr: "-4" }), 0x8000);
  });

  it("looks the table up by number despite JSON string keys", () => {
    // nr_to_ptp arrives keyed "-4".."4". Indexing it with a number works only
    // because JavaScript coerces, and getting this wrong yields undefined.
    for (const key of Object.keys(ENCODINGS.nr_to_ptp)) {
      const value = written("HighIsoNoiseReduction", { high_iso_nr: key });
      assert.equal(typeof value, "number", `no value for ${key}`);
    }
  });

  it("defaults to normal when unset", () => {
    assert.equal(written("HighIsoNoiseReduction", { high_iso_nr: "" }), ENCODINGS.nr_to_ptp[0]);
  });
});

describe("validation runs first", () => {
  it("refuses to convert an invalid recipe", () => {
    // Validation lives inside the conversion so no call path can skip it.
    assert.throws(
      () => recipeToPtpValues(makeRecipe({ film_simulation: "Velvia 100F" }), ENCODINGS),
      (error) => error instanceof RecipeValidationError
    );
  });

  it("refuses a half step where an integer is required", () => {
    assert.throws(
      () => recipeToPtpValues(makeRecipe({ color: "1.5" }), ENCODINGS),
      (error) => error instanceof RecipeValidationError
    );
  });
});

describe("customSlotCount", () => {
  it("returns the count for a known model", () => {
    assert.equal(customSlotCount("X-S10", ENCODINGS), 4);
  });

  it("returns zero for a model the server does not know", () => {
    // Guessing would offer slots that do not exist, and a write into one goes
    // nowhere useful.
    assert.equal(customSlotCount("X-H9", ENCODINGS), 0);
  });

  it("returns zero for a camera that reported no name", () => {
    assert.equal(customSlotCount("", ENCODINGS), 0);
  });
});

describe("makeSlotState", () => {
  it("names the film simulation a slot holds", () => {
    const state = makeSlotState({ index: 1, name: "Portra", filmSimPtp: 11 }, ENCODINGS);

    assert.equal(state.filmSimName, "Classic Chrome");
  });

  it("shows the raw value for a simulation it does not recognise", () => {
    // Better than an empty cell: a slot set from the camera body to something
    // this build has not heard of is worth seeing.
    const state = makeSlotState({ index: 2, name: "Mystery", filmSimPtp: 99 }, ENCODINGS);

    assert.equal(state.filmSimName, "Unknown(99)");
  });
});
