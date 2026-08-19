/**
 * Validate a recipe before writing it to a camera.
 *
 * Ports src/domain/camera/validation.py, checks in the same order so the two
 * reject the same recipe for the same reason.
 *
 * Where the Python derives a vocabulary from a constants table, this derives it
 * from the served encodings. Where the Python hardcodes one, so does this: the
 * grain size rules in particular cannot be read off the encoding table, because
 * the table says what to write and the rules say what a user may set.
 *
 * The dangerous part of this port is number parsing. Python's int() rejects
 * "1.5"; JavaScript's parseInt() silently returns 1. A validator that quietly
 * accepted half-steps for an integer field would let a recipe through here and
 * have it truncated at conversion, so both parsers below are strict and throw.
 */

/** Values meaning "not applicable", accepted wherever a field is optional. */
const EMPTY_OR_NA = new Set(["", "N/A"]);

/** A white balance given as a colour temperature, e.g. "6500K". */
const KELVIN_RE = /^\d+K$/;

/** Recipe names must be ASCII: the camera has no way to show anything else. */
const ASCII_RE = /^[\x00-\x7F]*$/;

// Grain roughness and the sizes each allows. Hardcoded here exactly as in the
// Python, because they cannot be derived from grain_to_ptp: when roughness is
// Off the camera keeps whatever size it last remembered, so a recipe may carry
// any size, or none, and still be valid.
const VALID_ROUGHNESS = new Set(["Off", "Weak", "Strong"]);
const VALID_OFF_SIZES = new Set(["Off", "Small", "Large"]);
const VALID_ON_SIZES = new Set(["Small", "Large"]);

/** Raised when a field holds a value the camera cannot accept. */
export class RecipeValidationError extends Error {
  /**
   * @param {string} field
   * @param {unknown} value
   */
  constructor(field, value) {
    super(`Invalid value for field ${_repr(field)}: ${_repr(value)}`);
    this.name = "RecipeValidationError";
    this.field = field;
    this.value = value;
  }
}

/**
 * Render a value the way Python's repr would, so both implementations report a
 * rejection in the same words.
 *
 * @param {unknown} value
 * @returns {string}
 */
function _repr(value) {
  if (value === null || value === undefined) return "None";
  if (Array.isArray(value)) return `(${value.map(_repr).join(", ")})`;
  if (typeof value === "string") return `'${value}'`;
  return String(value);
}

/** True when a field is absent rather than set to something. */
function _isAbsent(value) {
  return value === null || value === undefined || value === "";
}

/**
 * Parse an integer the way Python's int() does, rejecting anything else.
 *
 * parseInt("1.5") is 1, which would let a half-step through an integer field
 * and truncate it silently at conversion time. This throws instead.
 *
 * Marginally stricter than Python, which also accepts digit separators like
 * "1_0". Nothing in the recipe schema can produce one, and erring toward
 * rejection is the safe direction for a value bound for a camera.
 *
 * @param {unknown} value
 * @returns {number}
 */
export function _parseIntStrict(value) {
  const text = String(value).trim();
  if (!/^[+-]?\d+$/.test(text)) {
    throw new RangeError(`not an integer: ${text}`);
  }
  return Number(text);
}

/**
 * Parse a decimal the way Python's float() does, rejecting anything else.
 *
 * Number("") is 0 in JavaScript while float("") raises, so the empty string has
 * to be rejected explicitly or a blank field would validate as zero.
 *
 * @param {unknown} value
 * @returns {number}
 */
export function _parseFloatStrict(value) {
  const text = String(value).trim();
  if (text === "") {
    throw new RangeError("not a number: empty");
  }
  const parsed = Number(text);
  if (!Number.isFinite(parsed)) {
    throw new RangeError(`not a number: ${text}`);
  }
  return parsed;
}

function _validateIntStr(recipe, field) {
  const value = recipe[field];
  if (_isAbsent(value) || EMPTY_OR_NA.has(value)) return;
  try {
    _parseIntStrict(value);
  } catch {
    throw new RecipeValidationError(field, value);
  }
}

function _validateFloatStr(recipe, field) {
  const value = recipe[field];
  if (_isAbsent(value) || EMPTY_OR_NA.has(value)) return;
  try {
    _parseFloatStrict(value);
  } catch {
    throw new RecipeValidationError(field, value);
  }
}

/**
 * Check every field holds a value the camera can accept.
 *
 * Throws on the first failure, carrying the field name and the offending value.
 *
 * @param {object} recipe A recipe in FujifilmRecipeData shape.
 * @param {object} encodings The encodings block of the client config.
 * @returns {void}
 */
export function validateRecipeForCamera(recipe, encodings) {
  const validFilmSims = new Set(Object.keys(encodings.film_simulation_to_ptp));
  const validWbModes = new Set(Object.keys(encodings.white_balance_to_ptp));
  const validDrModes = new Set(Object.keys(encodings.drange_mode_to_ptp));
  const validDrPriorities = new Set(Object.keys(encodings.dr_priority_to_ptp));
  const validCce = new Set(Object.keys(encodings.cce_to_ptp));
  const validCfx = new Set(Object.keys(encodings.cfx_to_ptp));
  // JSON object keys are always strings, so these come back as "-4", "0", "4".
  // Converting is what makes the membership test below compare like with like.
  const validNrInts = new Set(Object.keys(encodings.nr_to_ptp).map(Number));

  // --- name: required for writing; non-blank ASCII within the length limit ---
  const name = recipe.name;
  if (!name || !String(name).trim()) {
    throw new RecipeValidationError("name", name);
  }
  if (name.length > encodings.recipe_name_max_len) {
    throw new RecipeValidationError("name", name);
  }
  if (!ASCII_RE.test(name)) {
    throw new RecipeValidationError("name", name);
  }

  // --- film_simulation ---
  if (!validFilmSims.has(recipe.film_simulation)) {
    throw new RecipeValidationError("film_simulation", recipe.film_simulation);
  }

  // --- white_balance: a named mode, or a colour temperature like "6500K" ---
  const wb = recipe.white_balance;
  if (!validWbModes.has(wb) && !KELVIN_RE.test(String(wb))) {
    throw new RecipeValidationError("white_balance", wb);
  }

  // --- dynamic_range: absent is fine; "N/A" is not a dynamic range ---
  if (!_isAbsent(recipe.dynamic_range)) {
    if (!validDrModes.has(recipe.dynamic_range)) {
      throw new RecipeValidationError("dynamic_range", recipe.dynamic_range);
    }
  }

  // --- d_range_priority ---
  if (
    !EMPTY_OR_NA.has(recipe.d_range_priority) &&
    !validDrPriorities.has(recipe.d_range_priority)
  ) {
    throw new RecipeValidationError("d_range_priority", recipe.d_range_priority);
  }

  // --- grain: roughness and size are validated together ---
  const roughness = recipe.grain_roughness;
  const size = recipe.grain_size;
  if (!VALID_ROUGHNESS.has(roughness)) {
    throw new RecipeValidationError("grain_roughness", [roughness, size ?? null]);
  }
  if (_isAbsent(size)) {
    // An omitted size only makes sense when the grain is off.
    if (roughness !== "Off") {
      throw new RecipeValidationError("grain_roughness", [roughness, size ?? null]);
    }
  } else {
    const validSizes = roughness === "Off" ? VALID_OFF_SIZES : VALID_ON_SIZES;
    if (!validSizes.has(size)) {
      throw new RecipeValidationError("grain_roughness", [roughness, size]);
    }
  }

  // --- colour chrome effect / FX blue ---
  if (
    !EMPTY_OR_NA.has(recipe.color_chrome_effect) &&
    !validCce.has(recipe.color_chrome_effect)
  ) {
    throw new RecipeValidationError("color_chrome_effect", recipe.color_chrome_effect);
  }
  if (
    !EMPTY_OR_NA.has(recipe.color_chrome_fx_blue) &&
    !validCfx.has(recipe.color_chrome_fx_blue)
  ) {
    throw new RecipeValidationError("color_chrome_fx_blue", recipe.color_chrome_fx_blue);
  }

  // --- high ISO noise reduction: an integer the non-linear table knows ---
  if (!EMPTY_OR_NA.has(recipe.high_iso_nr)) {
    let nrInt;
    try {
      nrInt = _parseIntStrict(recipe.high_iso_nr);
    } catch {
      throw new RecipeValidationError("high_iso_nr", recipe.high_iso_nr);
    }
    if (!validNrInts.has(nrInt)) {
      throw new RecipeValidationError("high_iso_nr", recipe.high_iso_nr);
    }
  }

  // --- numeric string fields ---
  _validateIntStr(recipe, "color");
  _validateIntStr(recipe, "sharpness");
  _validateIntStr(recipe, "clarity");
  _validateFloatStr(recipe, "highlight");
  _validateFloatStr(recipe, "shadow");
  _validateFloatStr(recipe, "monochromatic_color_warm_cool");
  _validateFloatStr(recipe, "monochromatic_color_magenta_green");
}
