/**
 * Convert a recipe into the PTP values a custom slot expects.
 *
 * Ports the write path of src/domain/camera/queries.py. The read path stays on
 * the server, which is the only side that reads a slot back.
 *
 * Three scaling rules, and they are not interchangeable:
 *
 *   - colour, sharpness and clarity are integers times ten
 *   - the tone curves and the monochrome toning axes allow half steps, so they
 *     round after scaling rather than truncate
 *   - white balance shifts and colour temperature pass through unscaled
 *
 * Getting the second one wrong turns +1.5 into 10 instead of 15, which is a
 * visible difference in the picture and an invisible one in the code.
 */

import { _parseFloatStrict, _parseIntStrict, validateRecipeForCamera } from "./validation.js";

/** True when a field carries no value, as opposed to a value of zero. */
function _isAbsent(value) {
  return value === null || value === undefined || value === "";
}

/** True when a field is absent or explicitly marked inapplicable. */
function _isAbsentOrNA(value) {
  return _isAbsent(value) || value === "N/A";
}

/**
 * Scale an integer field: value times ten, truncating nothing because the
 * parser has already refused anything that is not whole.
 */
function _scaleInt(value) {
  return _parseIntStrict(value) * 10;
}

/**
 * Scale a field that allows half steps: value times ten, rounded.
 *
 * Python rounds half to even and JavaScript rounds half up, so the two would
 * disagree on an exact tie. A tie needs two decimal places and the schema
 * stores one, so the inputs cannot produce it; the golden vectors pin the
 * boundary cases either way.
 */
function _scaleDecimal(value) {
  return Math.round(_parseFloatStrict(value) * 10);
}

/**
 * The PTP values to write for one recipe.
 *
 * Field names mirror the keys of custom_slot_codes. A null field is not
 * written at all, which is how "not applicable to this recipe" is expressed:
 * DRangeMode when D-Range Priority is active, colour on a monochrome
 * simulation, the toning axes on a colour one.
 *
 * @typedef {Record<string, number|null>} RecipePTPValues
 */

/**
 * Convert a recipe into PTP values, validating it first.
 *
 * Validation happens here rather than at the call site so an invalid recipe
 * cannot reach the camera by any route, exactly as the Python arranges it.
 *
 * @param {object} recipe A recipe in FujifilmRecipeData shape.
 * @param {object} encodings The encodings block of the client config.
 * @returns {RecipePTPValues}
 */
export function recipeToPtpValues(recipe, encodings) {
  validateRecipeForCamera(recipe, encodings);

  // --- film simulation (always set after validation) ---
  const filmSim = encodings.film_simulation_to_ptp[recipe.film_simulation];

  // --- white balance: a named mode, or a colour temperature like "6500K" ---
  const wbLabel = String(recipe.white_balance);
  let wb;
  let wbKelvin = null;
  if (wbLabel.endsWith("K") && /^\d+$/.test(wbLabel.slice(0, -1))) {
    wb = encodings.white_balance_to_ptp.Kelvin;
    wbKelvin = Number(wbLabel.slice(0, -1));
  } else {
    wb = encodings.white_balance_to_ptp[wbLabel];
  }

  // --- D-Range Priority (always written; anything unrecognised means Off) ---
  const drp = recipe.d_range_priority;
  const drPriority =
    drp in encodings.dr_priority_to_ptp
      ? encodings.dr_priority_to_ptp[drp]
      : encodings.dr_priority_to_ptp.Off;

  // --- D-Range mode: priority wins, so the mode is not written when it is on ---
  let drMode = null;
  if (!drp || drp === "Off") {
    drMode = _isAbsent(recipe.dynamic_range)
      ? null
      : encodings.drange_mode_to_ptp[recipe.dynamic_range] ?? null;
  }

  // --- grain (always written) ---
  const grain =
    recipe.grain_roughness === "Off"
      ? encodings.grain_off_sentinel
      : encodings.grain_to_ptp[recipe.grain_roughness][recipe.grain_size];

  // --- colour chrome effect / FX blue (always written; unset means Off) ---
  const cce =
    recipe.color_chrome_effect in encodings.cce_to_ptp
      ? encodings.cce_to_ptp[recipe.color_chrome_effect]
      : encodings.cce_to_ptp.Off;
  const cfx =
    recipe.color_chrome_fx_blue in encodings.cfx_to_ptp
      ? encodings.cfx_to_ptp[recipe.color_chrome_fx_blue]
      : encodings.cfx_to_ptp.Off;

  // --- scaled fields ---
  // Colour tests only for absence, not for "N/A", which is what the Python
  // does; sharpness and clarity test for both. Nothing reaching here can be
  // "N/A", because recipe_from_db produces either null or a signed number, and
  // the strict parser throws rather than yielding NaN if that ever changes.
  const color = _isAbsent(recipe.color) ? null : _scaleInt(recipe.color);
  const sharpness = _isAbsentOrNA(recipe.sharpness) ? 0 : _scaleInt(recipe.sharpness);
  const clarity = _isAbsentOrNA(recipe.clarity) ? 0 : _scaleInt(recipe.clarity);
  const highlight = _isAbsent(recipe.highlight) ? null : _scaleDecimal(recipe.highlight);
  const shadow = _isAbsent(recipe.shadow) ? null : _scaleDecimal(recipe.shadow);

  // --- high ISO noise reduction (non-linear; unset means 0/normal) ---
  const nrDomain = _isAbsentOrNA(recipe.high_iso_nr) ? 0 : _parseIntStrict(recipe.high_iso_nr);
  const nr = encodings.nr_to_ptp[nrDomain];

  // --- monochrome toning, only present on a monochrome simulation ---
  const monoWarmCool = _isAbsent(recipe.monochromatic_color_warm_cool)
    ? null
    : _scaleDecimal(recipe.monochromatic_color_warm_cool);
  const monoMagentaGreen = _isAbsent(recipe.monochromatic_color_magenta_green)
    ? null
    : _scaleDecimal(recipe.monochromatic_color_magenta_green);

  return {
    FilmSimulation: filmSim,
    WhiteBalance: wb,
    WhiteBalanceColorTemperature: wbKelvin,
    WhiteBalanceRed: recipe.white_balance_red,
    WhiteBalanceBlue: recipe.white_balance_blue,
    DRangeMode: drMode,
    DRangePriority: drPriority,
    GrainEffect: grain,
    ColorEffect: cce,
    ColorFx: cfx,
    ColorMode: color,
    Sharpness: sharpness,
    HighLightTone: highlight,
    ShadowTone: shadow,
    HighIsoNoiseReduction: nr,
    Definition: clarity,
    MonochromaticColorWarmCool: monoWarmCool,
    MonochromaticColorMagentaGreen: monoMagentaGreen,
  };
}

/**
 * Return (code, value) pairs for every property that is set, in write order.
 *
 * The order is the server's write_order, not this file's opinion. It matters:
 * WhiteBalanceColorTemperature has to be written before the two shifts, or the
 * camera zeroes them when the temperature lands.
 *
 * @param {RecipePTPValues} values
 * @param {object} encodings
 * @returns {Array<[number, number]>}
 */
export function ptpValueItems(values, encodings) {
  const codes = encodings.custom_slot_codes;
  return encodings.write_order
    .filter((name) => values[name] !== null && values[name] !== undefined)
    .map((name) => [codes[name], values[name]]);
}

/**
 * The number of custom slots a camera model offers.
 *
 * Returns 0 for a model the server does not know, which the caller shows as
 * "no custom slots" rather than guessing a count and writing into nothing.
 *
 * @param {string} cameraName
 * @param {object} encodings
 * @returns {number}
 */
export function customSlotCount(cameraName, encodings) {
  return encodings.camera_custom_slot_counts[cameraName] ?? 0;
}

/**
 * The state of one custom slot, as read from the camera.
 *
 * @param {object} state
 * @param {number} state.index 1-based slot number.
 * @param {string} state.name Display name stored in the slot.
 * @param {number} state.filmSimPtp Raw PTP FilmSimulation value.
 * @param {object} encodings
 * @returns {{index: number, name: string, filmSimPtp: number, filmSimName: string}}
 */
export function makeSlotState({ index, name, filmSimPtp }, encodings) {
  return {
    index,
    name,
    filmSimPtp,
    filmSimName: _filmSimName(filmSimPtp, encodings),
  };
}

function _filmSimName(filmSimPtp, encodings) {
  for (const [name, code] of Object.entries(encodings.film_simulation_to_ptp)) {
    if (code === filmSimPtp) return name;
  }
  // Naming the raw value beats an empty cell: a slot set from the camera body
  // to something this build has never heard of is worth seeing.
  return `Unknown(${filmSimPtp})`;
}
