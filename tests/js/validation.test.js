/**
 * Recipe validation, mirroring tests/unit/domain/camera coverage of
 * validate_recipe_for_camera.
 *
 * The cases that earn their place are the ones where a naive port would differ
 * from the Python: "1.5" in an integer field, an empty string in a float field,
 * and the grain rules, which cannot be read off the encoding table.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { ENCODINGS, VALIDATION_VECTORS, makeRecipe } from "./fakes/vectors.js";
import {
  RecipeValidationError,
  _parseFloatStrict,
  _parseIntStrict,
  validateRecipeForCamera,
} from "../../src/interfaces/static/js/camera/domain/validation.js";

function validate(overrides = {}) {
  validateRecipeForCamera(makeRecipe(overrides), ENCODINGS);
}

/** Assert validation rejects, and says which field. */
function rejects(overrides, field) {
  assert.throws(
    () => validate(overrides),
    (error) => {
      assert.ok(error instanceof RecipeValidationError, `got ${error}`);
      assert.equal(error.field, field);
      return true;
    }
  );
}

describe("validateRecipeForCamera", () => {
  it("accepts a recipe that came out of the payload endpoint", () => {
    validate();
  });
});

describe("name", () => {
  it("rejects a blank name", () => {
    // The camera needs something to label the slot, and the button that starts
    // a push is disabled without one, so reaching here means something is off.
    rejects({ name: "" }, "name");
  });

  it("rejects a name of only whitespace", () => {
    rejects({ name: "   " }, "name");
  });

  it("accepts a name at the length limit", () => {
    validate({ name: "X".repeat(ENCODINGS.recipe_name_max_len) });
  });

  it("rejects a name one character too long", () => {
    rejects({ name: "X".repeat(ENCODINGS.recipe_name_max_len + 1) }, "name");
  });

  it("rejects a non-ASCII name", () => {
    // The camera cannot render anything else, so it would show mojibake.
    rejects({ name: "Café Provia" }, "name");
  });
});

describe("film simulation", () => {
  it("accepts every simulation the encodings know", () => {
    for (const sim of Object.keys(ENCODINGS.film_simulation_to_ptp)) {
      validate({
        film_simulation: sim,
        // Monochrome simulations carry toning rather than colour, but
        // validation does not enforce that; conversion decides what to write.
      });
    }
  });

  it("rejects an unknown simulation", () => {
    rejects({ film_simulation: "Velvia 100F" }, "film_simulation");
  });
});

describe("white balance", () => {
  it("accepts a named mode", () => {
    validate({ white_balance: "Daylight" });
  });

  it("accepts a colour temperature", () => {
    validate({ white_balance: "6500K" });
  });

  it("rejects a temperature without its K", () => {
    rejects({ white_balance: "6500" }, "white_balance");
  });

  it("rejects a non-numeric temperature", () => {
    rejects({ white_balance: "warmK" }, "white_balance");
  });

  it("rejects an unknown mode", () => {
    rejects({ white_balance: "Tungsten" }, "white_balance");
  });
});

describe("dynamic range", () => {
  it("accepts an absent value", () => {
    validate({ dynamic_range: null });
    validate({ dynamic_range: "" });
  });

  it("rejects N/A, which is not a dynamic range", () => {
    // Unlike the other optional fields, "N/A" is not accepted here: it would
    // have to map to a real DR value and there is none.
    rejects({ dynamic_range: "N/A" }, "dynamic_range");
  });

  it("rejects an unknown value", () => {
    rejects({ dynamic_range: "DR800" }, "dynamic_range");
  });
});

describe("d-range priority", () => {
  it("accepts the placeholder values", () => {
    validate({ d_range_priority: "" });
    validate({ d_range_priority: "N/A" });
  });

  it("rejects an unknown value", () => {
    rejects({ d_range_priority: "Maximum" }, "d_range_priority");
  });
});

describe("grain", () => {
  it("accepts any size when the grain is off", () => {
    // The camera keeps whatever size it last remembered, so all three are
    // legitimate inputs. This is why the rule cannot be derived from
    // grain_to_ptp, whose Off entry names only one.
    for (const size of ["Off", "Small", "Large"]) {
      validate({ grain_roughness: "Off", grain_size: size });
    }
  });

  it("accepts an omitted size when the grain is off", () => {
    validate({ grain_roughness: "Off", grain_size: null });
  });

  it("rejects an omitted size when the grain is on", () => {
    rejects({ grain_roughness: "Weak", grain_size: null }, "grain_roughness");
  });

  it("rejects size Off when the grain is on", () => {
    rejects({ grain_roughness: "Strong", grain_size: "Off" }, "grain_roughness");
  });

  it("rejects an unknown roughness", () => {
    rejects({ grain_roughness: "Heavy", grain_size: "Large" }, "grain_roughness");
  });

  it("reports the pair, not just one half", () => {
    assert.throws(
      () => validate({ grain_roughness: "Weak", grain_size: null }),
      (error) => {
        assert.deepEqual(error.value, ["Weak", null]);
        return true;
      }
    );
  });
});

describe("colour chrome", () => {
  it("accepts the placeholder values", () => {
    validate({ color_chrome_effect: "", color_chrome_fx_blue: "N/A" });
  });

  it("rejects an unknown effect", () => {
    rejects({ color_chrome_effect: "Vivid" }, "color_chrome_effect");
  });

  it("rejects an unknown fx blue", () => {
    rejects({ color_chrome_fx_blue: "Vivid" }, "color_chrome_fx_blue");
  });
});

describe("high ISO noise reduction", () => {
  it("accepts every value the table knows", () => {
    for (const value of Object.keys(ENCODINGS.nr_to_ptp)) {
      validate({ high_iso_nr: value });
    }
  });

  it("rejects a value outside the table", () => {
    rejects({ high_iso_nr: "5" }, "high_iso_nr");
  });

  it("rejects a half step", () => {
    rejects({ high_iso_nr: "1.5" }, "high_iso_nr");
  });

  it("accepts the placeholder values", () => {
    validate({ high_iso_nr: "" });
    validate({ high_iso_nr: "N/A" });
  });
});

describe("integer fields", () => {
  for (const field of ["color", "sharpness", "clarity"]) {
    it(`rejects a half step in ${field}`, () => {
      // The hazard this whole module exists to guard. parseInt("1.5") is 1, so
      // a lenient port would accept this and silently write 1 to the camera.
      rejects({ [field]: "1.5" }, field);
    });

    it(`rejects text in ${field}`, () => {
      rejects({ [field]: "high" }, field);
    });

    it(`accepts a signed integer in ${field}`, () => {
      validate({ [field]: "+2" });
      validate({ [field]: "-4" });
    });

    it(`accepts the placeholder values in ${field}`, () => {
      validate({ [field]: "" });
      validate({ [field]: "N/A" });
    });
  }
});

describe("decimal fields", () => {
  const fields = [
    "highlight",
    "shadow",
    "monochromatic_color_warm_cool",
    "monochromatic_color_magenta_green",
  ];

  for (const field of fields) {
    it(`accepts a half step in ${field}`, () => {
      validate({ [field]: "+1.5" });
      validate({ [field]: "-1.5" });
    });

    it(`rejects text in ${field}`, () => {
      rejects({ [field]: "bright" }, field);
    });

    it(`accepts an absent value in ${field}`, () => {
      validate({ [field]: null });
      validate({ [field]: "" });
    });
  }
});

describe("RecipeValidationError", () => {
  it("reports the same message the Python does", () => {
    const error = new RecipeValidationError("name", "");

    assert.equal(error.message, "Invalid value for field 'name': ''");
  });

  it("renders an absent value as None, as Python does", () => {
    const error = new RecipeValidationError("grain_size", null);

    assert.equal(error.message, "Invalid value for field 'grain_size': None");
  });

  it("renders a pair as a tuple, as Python does", () => {
    const error = new RecipeValidationError("grain_roughness", ["Weak", null]);

    assert.equal(
      error.message,
      "Invalid value for field 'grain_roughness': ('Weak', None)"
    );
  });
});

describe("_parseIntStrict", () => {
  it("parses signed integers", () => {
    assert.equal(_parseIntStrict("+2"), 2);
    assert.equal(_parseIntStrict("-4"), -4);
    assert.equal(_parseIntStrict("0"), 0);
  });

  it("tolerates surrounding whitespace, as int() does", () => {
    assert.equal(_parseIntStrict(" 2 "), 2);
  });

  it("refuses a decimal rather than truncating it", () => {
    assert.throws(() => _parseIntStrict("1.5"));
  });

  it("refuses an empty string", () => {
    assert.throws(() => _parseIntStrict(""));
  });

  it("refuses text", () => {
    assert.throws(() => _parseIntStrict("twelve"));
  });
});

describe("_parseFloatStrict", () => {
  it("parses decimals", () => {
    assert.equal(_parseFloatStrict("+1.5"), 1.5);
    assert.equal(_parseFloatStrict("-1.5"), -1.5);
  });

  it("refuses an empty string rather than returning zero", () => {
    // Number("") is 0, which would make a blank field validate as a real value.
    assert.throws(() => _parseFloatStrict(""));
  });

  it("refuses text", () => {
    assert.throws(() => _parseFloatStrict("bright"));
  });

  it("refuses infinity", () => {
    assert.throws(() => _parseFloatStrict("Infinity"));
  });
});

describe("shared validation vectors", () => {
  // The same accept/reject table the Python asserts. Between them these say
  // the two validators agree case for case, which the per-case tests above
  // cannot: they only say this one behaves as I expected it to.
  for (const vector of VALIDATION_VECTORS) {
    it(`agrees with the Python: ${vector.name}`, () => {
      const recipe = { ...makeRecipe(), ...vector.overrides };
      let outcome;
      try {
        validateRecipeForCamera(recipe, ENCODINGS);
        outcome = "ok";
      } catch (error) {
        assert.ok(error instanceof RecipeValidationError, `unexpected ${error}`);
        outcome = `reject:${error.field}`;
      }

      assert.equal(outcome, vector.expected);
    });
  }

  it("has vectors to assert", () => {
    // A fixture that lost this section would turn every test above into zero
    // tests without failing anything.
    assert.ok(VALIDATION_VECTORS.length >= 40);
  });
});
