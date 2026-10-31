/**
 * X-T2 settings-backup codec for the browser.
 *
 * Ports src/domain/camera/xt2_backup/ (decode, validate, map, feasibility,
 * apply, verify). Pure functions over the backup blob bytes: no camera access.
 * The BackupBlobStrategy composes these over a connected device.
 *
 * Where the Python codec imports constants_xt2 directly, this reads the X-T2
 * byte layout from the served config (config.profile.xt2): the client has a
 * served vendor layer in place of a data layer (ADR 016), so the server's
 * constants_xt2 reaches it as data and cannot drift. prepareXt2() parses that
 * served shape (JSON string keys, decimal byte keys) into working maps once.
 */

/** Raised when a recipe holds a value the X-T2 cannot represent at all. */
export class RecipeNotRepresentable extends Error {
  /**
   * @param {string} field
   * @param {string|number} value
   */
  constructor(field, value) {
    super(`The X-T2 cannot represent ${field}=${JSON.stringify(value)}`);
    this.name = "RecipeNotRepresentable";
    this.field = field;
    this.value = value;
  }
}

const _EMPTY_OR_NA = new Set(["", "N/A"]);
const _KELVIN_RE = /^(\d+)K$/;
const _WB_SHIFT_LIMIT = 9;
const _WB_SEL_COLOR_TEMP = 0x08;
const _HEADER_END = 0xa8;

/**
 * Parse the served X-T2 layout into working maps, keyed by number where the
 * server keyed by byte. Builds the inverse (value -> byte) maps the writer needs.
 *
 * @param {object} xt2 config.profile.xt2
 * @returns {object}
 */
export function prepareXt2(xt2) {
  const byteKeyed = (table) => {
    const forward = new Map(); // byte -> value
    const inverse = new Map(); // value -> byte
    for (const [key, value] of Object.entries(table)) {
      const byte = Number(key);
      forward.set(byte, value);
      inverse.set(value, byte);
    }
    return { forward, inverse };
  };

  const filmSim = byteKeyed(xt2.film_simulation_by_byte);
  const grain = byteKeyed(xt2.grain_roughness_by_byte);
  const dynamicRange = byteKeyed(xt2.dynamic_range_by_byte);
  const color = byteKeyed(xt2.color_value_by_byte); // byte -> int, int -> byte
  const wbSelector = byteKeyed(xt2.white_balance_by_selector);

  return {
    magic: Uint8Array.from(xt2.magic),
    blobSize: xt2.blob_size,
    headerSizeOffset: xt2.header_size_offset,
    headerSizeValue: xt2.header_size_value,
    bodySizeOffset: xt2.body_size_offset,
    bodySizeValue: xt2.body_size_value,
    markerOffset: xt2.marker_offset,
    markerValue: xt2.marker_value,
    slot0Offset: xt2.slot0_offset,
    slotSize: xt2.slot_size,
    slotCount: xt2.slot_count,
    nameOffset: xt2.name_offset,
    nameFieldLen: xt2.name_field_len,
    off: xt2.off,
    slotWriteCounterOffset: xt2.slot_write_counter_offset,
    driftRange: xt2.drift_range,
    filmSimByByte: filmSim.forward,
    filmSimByteByName: filmSim.inverse,
    bwFilmSimBytes: new Set(xt2.bw_film_simulation_bytes),
    grainByByte: grain.forward,
    grainByteByName: grain.inverse,
    drByByte: dynamicRange.forward,
    drByteByName: dynamicRange.inverse,
    colorByByte: color.forward,
    colorByteByValue: color.inverse,
    wbBySelector: wbSelector.forward,
    wbSelectorByName: wbSelector.inverse,
    measuredCustomWb: new Set(xt2.measured_custom_wb),
    wbShiftTableBase: xt2.wb_shift_table_base,
    wbShiftEntries: xt2.wb_shift_entries,
    wbShiftTableIndex: xt2.wb_shift_table_index,
    kelvinSteps: xt2.kelvin_steps,
    toneByteMax: xt2.tone_byte_max,
    sharpnessByteMax: xt2.sharpness_byte_max,
    noiseReductionByteMax: xt2.noise_reduction_byte_max,
    wbShiftByteMax: xt2.wb_shift_byte_max,
    asciiMin: xt2.ascii_min,
    asciiMax: xt2.ascii_max,
    structuralAnchors: xt2.structural_anchors,
  };
}

function _signed(value) {
  return value > 0 ? `+${value}` : String(value);
}

function _slotBase(X, slotIndex) {
  return X.slot0Offset + slotIndex * X.slotSize;
}

function _slotName(X, blob, base) {
  const start = base + X.nameOffset;
  const window = blob.subarray(start, start + X.nameFieldLen);
  let end = window.indexOf(0);
  if (end === -1) end = window.length;
  let name = "";
  for (let i = 0; i < end; i += 1) name += String.fromCharCode(window[i]);
  return name;
}

function _wbShift(X, blob, wbName) {
  const index = X.wbShiftTableIndex[wbName];
  if (index === undefined) return [0, 0];
  const base = X.wbShiftTableBase + index * 2;
  return [9 - blob[base], 9 - blob[base + 1]];
}

/**
 * Read the name and film simulation of each custom slot from the blob.
 *
 * Returns rows in the {index, name, filmSimPtp} shape makeSlotState expects, so
 * the browser's slot list is identical to the per-property one.
 *
 * @param {Uint8Array} blob
 * @param {object} X prepared layout
 * @param {object} encodings served encodings (for film_simulation_to_ptp)
 * @returns {Array<{index: number, name: string, filmSimPtp: number}>}
 */
export function decodeSlotStates(blob, X, encodings) {
  const states = [];
  for (let idx = 0; idx < X.slotCount; idx += 1) {
    const base = _slotBase(X, idx);
    const name = _slotName(X, blob, base);
    const simName = X.filmSimByByte.get(blob[base + X.off.film_simulation]);
    const filmSimPtp = simName ? encodings.film_simulation_to_ptp[simName] ?? 0 : 0;
    states.push({ index: idx + 1, name, filmSimPtp });
  }
  return states;
}

/**
 * Decode one custom slot (1-based) into a FujifilmRecipeData-shaped object.
 *
 * @param {Uint8Array} blob
 * @param {number} slotIndex 1-based
 * @param {object} X prepared layout
 * @returns {object}
 */
export function decodeSlotRecipe(blob, slotIndex, X) {
  const base = _slotBase(X, slotIndex - 1);
  const simByte = blob[base + X.off.film_simulation];
  const simName = X.filmSimByByte.get(simByte) ?? "";
  const isBw = X.bwFilmSimBytes.has(simByte);

  const wbName = X.wbBySelector.get(blob[base + X.off.wb_selector]) ?? "";
  const [wbRed, wbBlue] = _wbShift(X, blob, wbName);
  let whiteBalance;
  if (wbName === "Kelvin") {
    const kelvinIndex = blob[base + X.off.kelvin_index];
    const kelvin = kelvinIndex < X.kelvinSteps.length ? X.kelvinSteps[kelvinIndex] : 0;
    whiteBalance = `${kelvin}K`;
  } else {
    whiteBalance = wbName;
  }

  const colorValue = X.colorByByte.get(blob[base + X.off.color]);
  const color = isBw || colorValue === undefined ? "" : _signed(colorValue);

  return {
    name: _slotName(X, blob, base),
    film_simulation: simName,
    white_balance: whiteBalance,
    white_balance_red: wbRed,
    white_balance_blue: wbBlue,
    dynamic_range: X.drByByte.get(blob[base + X.off.dynamic_range]) ?? "",
    d_range_priority: "",
    grain_roughness: X.grainByByte.get(blob[base + X.off.grain]) ?? "",
    grain_size: "",
    color_chrome_effect: "",
    color_chrome_fx_blue: "",
    color,
    sharpness: _signed(4 - blob[base + X.off.sharpness]),
    highlight: _signed(4 - blob[base + X.off.highlight]),
    shadow: _signed(4 - blob[base + X.off.shadow]),
    high_iso_nr: _signed(blob[base + X.off.noise_reduction] - 4),
    clarity: "",
  };
}

// --- validation ------------------------------------------------------------

function _u32(blob, offset) {
  return new DataView(blob.buffer, blob.byteOffset + offset, 4).getUint32(0, true);
}

function _checkHeader(blob, X, errors) {
  if (blob.length !== X.blobSize) errors.push(`size ${blob.length} != ${X.blobSize}`);
  const magicOk = blob.length >= X.magic.length && X.magic.every((b, i) => blob[i] === b);
  if (!magicOk) errors.push("magic mismatch");
  for (const [offset, want, label] of [
    [X.headerSizeOffset, X.headerSizeValue, "header-size@0x98"],
    [X.bodySizeOffset, X.bodySizeValue, "body-size@0xA0"],
    [X.markerOffset, X.markerValue, "marker@0xAC"],
  ]) {
    if (offset + 4 <= blob.length) {
      const got = _u32(blob, offset);
      if (got !== want) errors.push(`${label} ${got} != ${want}`);
    }
  }
}

function _checkName(blob, X, base, slot, errors) {
  const start = base + X.nameOffset;
  const window = blob.subarray(start, start + X.nameFieldLen);
  const nul = window.indexOf(0);
  if (nul === -1) {
    errors.push(`${slot} name: no NUL terminator in the name window`);
    return;
  }
  for (let i = 0; i < nul; i += 1) {
    const char = window[i];
    if (char < X.asciiMin || char > X.asciiMax) {
      errors.push(`${slot} name: non-printable byte at name+${i}`);
      return;
    }
  }
}

function _checkSlot(blob, X, idx, errors, warnings) {
  const base = _slotBase(X, idx);
  const slot = `C${idx + 1}`;

  const inRange = (offset, lo, hi, field) => {
    const value = blob[base + offset];
    if (value < lo || value > hi) errors.push(`${slot} ${field}: byte out of range`);
  };
  const member = (offset, validMap, field) => {
    if (!validMap.has(blob[base + offset])) errors.push(`${slot} ${field}: invalid byte`);
  };

  const filmSim = blob[base + X.off.film_simulation];
  member(X.off.film_simulation, X.filmSimByByte, "film-sim");
  member(X.off.grain, X.grainByByte, "grain");
  member(X.off.dynamic_range, X.drByByte, "dynamic-range");
  member(X.off.wb_selector, X.wbBySelector, "wb-selector");
  if (!X.bwFilmSimBytes.has(filmSim)) member(X.off.color, X.colorByByte, "color");
  inRange(X.off.highlight, 0, X.toneByteMax, "highlight");
  inRange(X.off.shadow, 0, X.toneByteMax, "shadow");
  inRange(X.off.sharpness, 0, X.sharpnessByteMax, "sharpness");
  inRange(X.off.noise_reduction, 0, X.noiseReductionByteMax, "noise-reduction");
  if (blob[base + X.off.wb_selector] === _WB_SEL_COLOR_TEMP) {
    inRange(X.off.kelvin_index, 0, X.kelvinSteps.length - 1, "kelvin-index");
  }

  _checkName(blob, X, base, slot, errors);

  for (const [offset, want] of Object.entries(X.structuralAnchors)) {
    const got = blob[base + Number(offset)];
    if (got !== want) warnings.push(`${slot} structural anchor +${offset}: ${got} != ${want}`);
  }
}

function _checkWbTable(blob, X, errors) {
  for (let i = 0; i < X.wbShiftEntries * 2; i += 1) {
    const offset = X.wbShiftTableBase + i;
    if (blob[offset] > X.wbShiftByteMax) errors.push(`WB-shift table @${offset}: byte too large`);
  }
}

/**
 * Strictly validate a backup blob's recipe regions.
 *
 * @param {Uint8Array} blob
 * @param {object} X prepared layout
 * @returns {{ok: boolean, errors: string[], warnings: string[]}}
 */
export function validateBackup(blob, X) {
  const errors = [];
  const warnings = [];
  _checkHeader(blob, X, errors);
  if (blob.length >= X.blobSize) {
    for (let idx = 0; idx < X.slotCount; idx += 1) _checkSlot(blob, X, idx, errors, warnings);
    _checkWbTable(blob, X, errors);
  }
  return { ok: errors.length === 0, errors, warnings };
}

// --- mapping ---------------------------------------------------------------

function _parseSigned(value, fallback = 0) {
  if (value === null || value === undefined || _EMPTY_OR_NA.has(value)) return fallback;
  return Math.round(Number(value));
}

function _clamp(value, lo, hi) {
  return Math.max(lo, Math.min(hi, value));
}

function _snapKelvin(X, kelvin) {
  let best = X.kelvinSteps[0];
  for (const step of X.kelvinSteps) {
    if (Math.abs(step - kelvin) < Math.abs(best - kelvin)) best = step;
  }
  return best;
}

function _droppedFields(recipe) {
  const dropped = [];
  const clarity = recipe.clarity;
  if (!_EMPTY_OR_NA.has(clarity) && clarity !== "0" && clarity !== null && clarity !== undefined) {
    dropped.push("Clarity");
  }
  const cce = recipe.color_chrome_effect;
  if (!_EMPTY_OR_NA.has(cce) && cce !== "Off" && cce !== null && cce !== undefined) {
    dropped.push("Color Chrome Effect");
  }
  const cfx = recipe.color_chrome_fx_blue;
  if (!_EMPTY_OR_NA.has(cfx) && cfx !== "Off" && cfx !== null && cfx !== undefined) {
    dropped.push("Color Chrome FX Blue");
  }
  const dr = recipe.d_range_priority;
  if (!_EMPTY_OR_NA.has(dr) && dr !== "Off" && dr !== null && dr !== undefined) {
    dropped.push("D-Range Priority");
  }
  const size = recipe.grain_size;
  if (size !== null && size !== undefined && size !== "" && size !== "Off" && size !== "N/A") {
    dropped.push("Grain Size");
  }
  return dropped;
}

function _mapWhiteBalance(X, recipe) {
  const wb = recipe.white_balance;
  const match = _KELVIN_RE.exec(wb);
  if (match) return ["Kelvin", _snapKelvin(X, Number(match[1]))];
  if (!X.wbSelectorByName.has(wb)) throw new RecipeNotRepresentable("white_balance", wb);
  return [wb, null];
}

/**
 * Map a recipe onto the X-T2 capability subset.
 *
 * @param {object} recipe FujifilmRecipeData shape
 * @param {object} X prepared layout
 * @returns {object} mapping with a `dropped` array
 * @throws {RecipeNotRepresentable}
 */
export function mapRecipe(recipe, X) {
  if (!X.filmSimByteByName.has(recipe.film_simulation)) {
    throw new RecipeNotRepresentable("film_simulation", recipe.film_simulation);
  }
  if (!X.grainByteByName.has(recipe.grain_roughness)) {
    throw new RecipeNotRepresentable("grain_roughness", recipe.grain_roughness);
  }

  let dynamicRange = recipe.dynamic_range;
  if (dynamicRange === null || dynamicRange === undefined || dynamicRange === "") {
    dynamicRange = "DR-Auto";
  }
  if (!X.drByteByName.has(dynamicRange)) {
    throw new RecipeNotRepresentable("dynamic_range", recipe.dynamic_range);
  }

  const [whiteBalance, kelvin] = _mapWhiteBalance(X, recipe);

  const highlight = _parseSigned(recipe.highlight);
  const shadow = _parseSigned(recipe.shadow);
  const color = _parseSigned(recipe.color);
  const sharpness = _parseSigned(recipe.sharpness);
  const noiseReduction = _parseSigned(recipe.high_iso_nr);
  for (const [field, value, lo, hi] of [
    ["highlight", highlight, -2, 4],
    ["shadow", shadow, -2, 4],
    ["color", color, -4, 4],
    ["sharpness", sharpness, -4, 4],
    ["high_iso_nr", noiseReduction, -4, 4],
  ]) {
    if (value < lo || value > hi) throw new RecipeNotRepresentable(field, value);
  }

  return {
    name: recipe.name,
    film_simulation: recipe.film_simulation,
    grain_roughness: recipe.grain_roughness,
    dynamic_range: dynamicRange,
    white_balance: whiteBalance,
    white_balance_red: _clamp(recipe.white_balance_red, -_WB_SHIFT_LIMIT, _WB_SHIFT_LIMIT),
    white_balance_blue: _clamp(recipe.white_balance_blue, -_WB_SHIFT_LIMIT, _WB_SHIFT_LIMIT),
    kelvin,
    highlight,
    shadow,
    color,
    sharpness,
    noise_reduction: noiseReduction,
    dropped: _droppedFields(recipe),
  };
}

// --- feasibility -----------------------------------------------------------

function _currentShift(X, blob, wbName) {
  const base = X.wbShiftTableBase + X.wbShiftTableIndex[wbName] * 2;
  return [9 - blob[base], 9 - blob[base + 1]];
}

function _slotsUsing(X, blob, wbName, excluding) {
  const selector = X.wbSelectorByName.get(wbName);
  const using = [];
  for (let other = 0; other < X.slotCount; other += 1) {
    if (excluding.has(other)) continue;
    const base = _slotBase(X, other);
    if (blob[base + X.off.wb_selector] === selector) using.push(other);
  }
  return using;
}

function _droppedNote(dropped) {
  return dropped.length ? [`Dropped (the X-T2 lacks these): ${dropped.join(", ")}`] : [];
}

function _fmt(value) {
  return value >= 0 ? `+${value}` : String(value);
}

/**
 * Decide whether a mapping can be pushed into slot slotIndex (0-based).
 *
 * @returns {{ok: boolean, conflicts: string[], notes: string[]}}
 */
export function checkFeasibility(blob, slotIndex, mapping, X) {
  const notes = _droppedNote(mapping.dropped);

  if (X.measuredCustomWb.has(mapping.white_balance)) {
    return {
      ok: false,
      conflicts: [
        `White balance '${mapping.white_balance}' is a measured Custom white balance stored ` +
          `on the camera; it cannot be sent over USB, so this recipe cannot be pushed.`,
      ],
      notes,
    };
  }

  const want = [mapping.white_balance_red, mapping.white_balance_blue];
  const current = _currentShift(X, blob, mapping.white_balance);
  // Feasibility is decided by the OTHER slots on this WB: a push is fine only if
  // it does not retune one that is kept.
  const sharers = _slotsUsing(X, blob, mapping.white_balance, new Set([slotIndex]));
  const conflicts = [];
  if ((want[0] !== current[0] || want[1] !== current[1]) && sharers.length) {
    // The detail names every slot on this WB, not the per-target sharers, so it
    // reads the same for each blocked slot and the picker shows it once, behind
    // the (i) on the single conflict note.
    const users = _slotsUsing(X, blob, mapping.white_balance, new Set());
    const names = users.map((other) => `C${other + 1}`).join(", ");
    const wb = mapping.white_balance;
    if (users.length === 1) {
      conflicts.push(
        `White balance '${wb}' is already used by ${names} with a different R/B shift. ` +
          `Pushing this recipe into any other slot would change ${names}'s white balance, ` +
          `turning it into a different recipe. The only slot it can go in is ${names}.`
      );
    } else {
      conflicts.push(
        `White balance '${wb}' is used by ${names}, each relying on its current R/B shift. ` +
          `This recipe needs a different shift, and the camera keeps only one shift per white ` +
          `balance, so pushing it would change all of them. Free '${wb}' down to a single slot first.`
      );
    }
  }
  return { ok: conflicts.length === 0, conflicts, notes };
}

/**
 * Decide whether every (slotIndex, mapping) assignment can be pushed in one blob.
 *
 * @param {Uint8Array} blob
 * @param {Array<[number, object]>} assignments 0-based slot index, mapping
 * @param {object} X
 * @returns {{ok: boolean, conflicts: string[], notes: string[]}}
 */
export function checkCollectionFeasibility(blob, assignments, X) {
  const conflicts = [];
  const droppedSet = new Set();
  for (const [, mapping] of assignments) {
    for (const field of mapping.dropped) droppedSet.add(field);
  }
  const notes = _droppedNote([...droppedSet].sort());
  const overwritten = new Set(assignments.map(([slotIndex]) => slotIndex));

  const desired = new Map();
  for (const [slotIndex, mapping] of assignments) {
    if (X.measuredCustomWb.has(mapping.white_balance)) {
      conflicts.push(
        `C${slotIndex + 1} '${mapping.name}': white balance ` +
          `'${mapping.white_balance}' is a measured Custom WB, not pushable.`
      );
      continue;
    }
    const want = [mapping.white_balance_red, mapping.white_balance_blue];
    const prior = desired.get(mapping.white_balance);
    if (prior && (prior[0] !== want[0] || prior[1] !== want[1])) {
      conflicts.push(
        `White balance '${mapping.white_balance}' needs two different shifts in this ` +
          `collection; the camera has only one shift for it.`
      );
    } else {
      desired.set(mapping.white_balance, want);
    }
  }

  for (const [wbName, want] of desired) {
    const current = _currentShift(X, blob, wbName);
    if (want[0] === current[0] && want[1] === current[1]) continue;
    const kept = _slotsUsing(X, blob, wbName, overwritten);
    if (kept.length) {
      const names = kept.map((other) => `C${other + 1}`).join(", ");
      conflicts.push(
        `White balance '${wbName}' has one global shift; setting it to ` +
          `(R${_fmt(want[0])}, B${_fmt(want[1])}) would change kept slot(s) ${names} that use it.`
      );
    }
  }

  return { ok: conflicts.length === 0, conflicts, notes };
}

// --- apply -----------------------------------------------------------------

function _toneByte(value) {
  return 4 - value;
}

function _nrByte(value) {
  return value + 4;
}

function _wbShiftByte(shift) {
  return 9 - shift;
}

function _writeName(out, X, base, name) {
  const nameBytes = [];
  for (let i = 0; i < name.length; i += 1) nameBytes.push(name.charCodeAt(i) & 0xff);
  if (nameBytes.length + 1 > X.nameFieldLen) {
    throw new Error(`name too long for the ${X.nameFieldLen}-byte field: ${name}`);
  }
  for (let i = 0; i < nameBytes.length; i += 1) out[base + X.nameOffset + i] = nameBytes[i];
  out[base + X.nameOffset + nameBytes.length] = 0;
}

function _applyOne(out, X, slotIndex, mapping) {
  const base = _slotBase(X, slotIndex);

  out[base + X.off.film_simulation] = X.filmSimByteByName.get(mapping.film_simulation);
  out[base + X.off.grain] = X.grainByteByName.get(mapping.grain_roughness);
  out[base + X.off.dynamic_range] = X.drByteByName.get(mapping.dynamic_range);
  out[base + X.off.wb_selector] = X.wbSelectorByName.get(mapping.white_balance);
  out[base + X.off.highlight] = _toneByte(mapping.highlight);
  out[base + X.off.shadow] = _toneByte(mapping.shadow);
  out[base + X.off.sharpness] = _toneByte(mapping.sharpness);
  out[base + X.off.noise_reduction] = _nrByte(mapping.noise_reduction);
  out[base + X.off.color] = X.colorByteByValue.get(mapping.color);

  if (mapping.white_balance === "Kelvin" && mapping.kelvin !== null && mapping.kelvin !== undefined) {
    out[base + X.off.kelvin_index] = X.kelvinSteps.indexOf(mapping.kelvin);
  }

  _writeName(out, X, base, mapping.name);

  const index = X.wbShiftTableIndex[mapping.white_balance];
  const shiftBase = X.wbShiftTableBase + index * 2;
  out[shiftBase] = _wbShiftByte(mapping.white_balance_red);
  out[shiftBase + 1] = _wbShiftByte(mapping.white_balance_blue);
}

/**
 * Return a copy of blob with mapping written into slot slotIndex (0-based).
 *
 * @param {Uint8Array} blob
 * @param {number} slotIndex 0-based
 * @param {object} mapping
 * @param {object} X
 * @returns {Uint8Array}
 */
export function applyRecipe(blob, slotIndex, mapping, X) {
  const out = Uint8Array.from(blob);
  _applyOne(out, X, slotIndex, mapping);
  return out;
}

/**
 * Return a copy of blob with every (slotIndex, mapping) assignment applied.
 *
 * @param {Uint8Array} blob
 * @param {Array<[number, object]>} assignments 0-based slot index, mapping
 * @param {object} X
 * @returns {Uint8Array}
 */
export function applyRecipes(blob, assignments, X) {
  const out = Uint8Array.from(blob);
  for (const [slotIndex, mapping] of assignments) _applyOne(out, X, slotIndex, mapping);
  return out;
}

// --- verify ----------------------------------------------------------------

function _isFidelityOffset(X, offset) {
  const slotsEnd = X.slot0Offset + X.slotSize * X.slotCount;
  if (offset < _HEADER_END) return true;
  if (offset >= X.slot0Offset && offset < slotsEnd) {
    const within = (offset - X.slot0Offset) % X.slotSize;
    return within !== X.slotWriteCounterOffset;
  }
  return false;
}

/**
 * Compare a read-back blob to the pushed blob over the header and slot regions.
 *
 * @param {Uint8Array} readBack
 * @param {Uint8Array} pushed
 * @param {object} X
 * @returns {{ok: boolean, mismatches: number[]}}
 */
export function verifyRoundTrip(readBack, pushed, X) {
  if (readBack.length !== pushed.length) return { ok: false, mismatches: [] };
  const mismatches = [];
  for (let offset = 0; offset < pushed.length; offset += 1) {
    if (readBack[offset] !== pushed[offset] && _isFidelityOffset(X, offset)) {
      mismatches.push(offset);
    }
  }
  return { ok: mismatches.length === 0, mismatches };
}
