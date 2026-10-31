/**
 * Per-model camera strategies: the middle layer between the camera use cases
 * and the PTP primitives.
 *
 * Ports src/domain/camera/strategies.py. A CameraStrategy owns the model-
 * specific algorithm for reading slots and pushing a recipe; a use case
 * resolves one from the camera model (getStrategy) and delegates to it, staying
 * thin. The device is passed in already connected; the strategy never manages
 * the connection lifecycle.
 *
 * Today there is one strategy, PerPropertyStrategy, for bodies with the custom-
 * slot PTP property interface (X-S10, X-T3+). The X-T2 backup-blob strategy
 * (download the settings backup over WebUSB, edit it, restore it) is selected
 * here in a follow-up, exactly as its Python counterpart is.
 *
 * Where the Python strategy reads a model's capabilities from a CameraProfile,
 * this reads them from the served config.encodings: the client has a served
 * vendor layer in place of a data layer (see ADR 016), so the served config is
 * the client's profile.
 */

import {
  CameraConnectionError,
  CameraWriteError,
  RestoreAckTimeout,
} from "../vendor/ptp_device.js";
import {
  SLOT_PROGRESS,
  SLOT_RETRY,
  publishEvent,
  publishTrace,
} from "../vendor/events.js";
import {
  setCursorWithRetry,
  setPropWithRetry,
  verifyWrittenProperties,
} from "./operations.js";
import { makeSlotState, ptpValueItems, recipeToPtpValues } from "./queries.js";
import {
  RecipeNotRepresentable,
  applyRecipe,
  applyRecipes,
  checkCollectionFeasibility,
  checkFeasibility,
  decodeSlotStates,
  mapRecipe,
  prepareXt2,
  validateBackup,
  verifyRoundTrip,
} from "./xt2_backup.js";

export { RecipeNotRepresentable } from "./xt2_backup.js";

/** Raised when one or more properties could not be written or verified. */
export class RecipeWriteError extends Error {
  /** @param {string[]} failedProperties Names, in the order they were attempted. */
  constructor(failedProperties) {
    const shown = failedProperties.map((name) => `'${name}'`).join(", ");
    super(
      `Recipe write incomplete: ${failedProperties.length} property/properties ` +
        `failed ([${shown}])`
    );
    this.name = "RecipeWriteError";
    this.failedProperties = failedProperties;
  }
}

/** Raised when a backup blob does not strictly validate, so editing is unsafe. */
export class BackupValidationError extends Error {
  /** @param {string[]} errors */
  constructor(errors) {
    super(`Backup failed validation: ${errors.length} error(s)`);
    this.name = "BackupValidationError";
    this.errors = errors;
  }
}

/** Raised when a push would retune a kept slot's shared white balance (X-T2). */
export class PushNotFeasibleError extends Error {
  /** @param {string[]} conflicts */
  constructor(conflicts) {
    super(conflicts.length ? conflicts.join("; ") : "Push not feasible");
    this.name = "PushNotFeasibleError";
    this.conflicts = conflicts;
  }
}

/**
 * Map PTP codes back to the names a person recognises.
 *
 * A failure report saying "0xd19d" helps nobody; "HighLightTone" tells the user
 * which setting to check on the camera.
 */
function _codeToPropName(encodings) {
  const names = { [encodings.prop_slot_name]: "SlotName" };
  for (const [name, code] of Object.entries(encodings.custom_slot_codes)) {
    names[code] = name;
  }
  return names;
}

/**
 * Call `fn` until it succeeds, retrying only transport failures.
 *
 * A CameraWriteError propagates immediately: the camera answered and refused,
 * so another identical request would be refused identically.
 *
 * @template T
 * @param {() => Promise<T>} fn
 * @param {{config: object, sleep: (seconds: number) => Promise<void>}} runtime
 * @returns {Promise<T>}
 */
async function _retry(fn, { config, sleep }, what) {
  const maxRetries = config.settings.CAMERA_MAX_RETRIES;
  const backoff = config.settings.CAMERA_RETRY_BACKOFF_S;
  let lastError = new CameraConnectionError("no retries attempted");
  for (let attempt = 1; attempt <= maxRetries; attempt += 1) {
    if (attempt > 1) {
      await sleep(backoff * 2 ** (attempt - 2));
    }
    try {
      return await fn();
    } catch (error) {
      if (!(error instanceof CameraConnectionError)) throw error;
      // This loop used to swallow its attempts silently, which made the slot
      // listing look like it gave up first time when it had in fact tried
      // three times. Of the three retry loops it is the only one that wraps a
      // whole slot operation, so its attempts are the ones worth seeing.
      publishEvent({
        eventType: SLOT_RETRY,
        operation: what,
        attempt: `${attempt}/${maxRetries}`,
        error: error.message,
      });
      lastError = error;
    }
  }
  throw lastError;
}

/**
 * Strategy for bodies with the custom-slot PTP property interface (X-S10, X-T3+).
 *
 * Reads and writes each recipe field as its own device property, selecting the
 * target slot via the slot cursor.
 */
export class PerPropertyStrategy {
  /**
   * Read every custom slot (1..slotCount), name and film simulation.
   *
   * The reads are sequential and deliberately so. Each one depends on the slot
   * cursor written before it, so running them together would return repeated
   * readings of whichever slot the camera happened to land on.
   *
   * @param {import("../vendor/ptp_device.js").CameraDevice} device Connected.
   * @param {object} options
   * @param {number} options.slotCount
   * @param {{config: object, sleep: (seconds: number) => Promise<void>}} options.runtime
   * @returns {Promise<Array<{index: number, name: string, filmSimPtp: number, filmSimName: string}>>}
   */
  async readSlots(device, { slotCount, runtime }) {
    const { config, sleep } = runtime;
    const encodings = config.encodings;
    const nameCode = encodings.prop_slot_name;
    const filmSimCode = encodings.custom_slot_codes.FilmSimulation;

    publishTrace({ eventType: SLOT_PROGRESS, camera: device.cameraName, slots: slotCount });
    const states = [];
    for (let index = 1; index <= slotCount; index += 1) {
      publishTrace({ eventType: SLOT_PROGRESS, slot: `C${index}`, of: slotCount });
      if (index > 1) {
        await sleep(config.settings.CAMERA_INTER_SLOT_DELAY_S);
      }
      await setCursorWithRetry(device, index, runtime);
      // The camera needs a moment to settle on the new slot; reading too soon
      // returns the previous slot's values, which is worse than an error
      // because it looks like a correct answer.
      await sleep(config.settings.CAMERA_POST_CURSOR_DELAY_S);

      const name = await _retry(
        () => device.getPropertyString(nameCode),
        runtime,
        `C${index} name`
      );
      const filmSimPtp = await _retry(
        () => device.getPropertyInt(filmSimCode),
        runtime,
        `C${index} film simulation`
      );

      states.push(makeSlotState({ index, name, filmSimPtp }, encodings));
    }
    return states;
  }

  /**
   * Write a recipe to a custom slot.
   *
   * Two rules run through the whole sequence and neither is negotiable.
   *
   * Order. Every write after the first lands in whichever slot the cursor
   * points at, and within the recipe the colour temperature has to precede the
   * two white balance shifts or the camera zeroes them. Nothing here may run
   * concurrently.
   *
   * Failure. A camera that refuses one property is still there, so the
   * remaining properties are still worth writing and the user is told which one
   * did not take. A camera that has stopped answering is not, so the sequence
   * stops rather than spending three retries each on eighteen more writes.
   *
   * @param {import("../vendor/ptp_device.js").CameraDevice} device Connected.
   * @param {object} recipe A recipe in FujifilmRecipeData shape.
   * @param {object} options
   * @param {number} options.slotIndex 1-based slot number.
   * @param {{config: object, sleep: (seconds: number) => Promise<void>}} options.runtime
   * @returns {Promise<void>}
   * @throws {RecipeValidationError} The recipe holds a value the camera cannot take.
   * @throws {CameraConnectionError} The camera stopped answering mid-sequence.
   * @throws {CameraWriteError} The camera refused the slot cursor.
   * @throws {RecipeWriteError} Some properties did not write or verify.
   */
  async pushRecipe(device, recipe, { slotIndex, runtime }) {
    const { config, sleep } = runtime;
    const encodings = config.encodings;
    const settings = config.settings;

    // --- Step 1: point the camera at the slot ---
    // Retried, unlike the Python, which calls this once. The slot listing
    // already retries its cursor writes and this is the same write; leaving it
    // bare meant a single stall abandoned the push before a byte of the recipe
    // was sent, which on hardware that stalls intermittently is the difference
    // between a push that works and one that works most of the time.
    try {
      await setCursorWithRetry(device, slotIndex, runtime);
    } catch (error) {
      if (error instanceof CameraWriteError) {
        // A refusal is reported as a connection failure, which the Python also
        // does: nothing has been written yet, so there is no partly applied
        // recipe to describe and the user only needs to know it did not start.
        throw new CameraConnectionError(
          `Failed to set slot cursor to slot ${slotIndex} (rc=${error.rc})`
        );
      }
      throw error;
    }

    await sleep(settings.CAMERA_PRE_WRITE_DELAY_S);

    // --- Step 2: validate and convert, before anything else is written ---
    // An invalid recipe never reaches the camera: the cursor has moved but no
    // value has changed, so the slot is exactly as the user left it.
    const ptpItems = ptpValueItems(recipeToPtpValues(recipe, encodings), encodings);

    // --- Step 3: write the name, then every property, in order ---
    const allWrites = [[encodings.prop_slot_name, recipe.name], ...ptpItems];
    const failedCodes = allWrites.map(([code]) => code);
    const written = [];

    for (const [code, value] of allWrites) {
      await sleep(settings.CAMERA_PRE_WRITE_DELAY_S);

      let succeeded = false;
      try {
        await setPropWithRetry(device, code, value, runtime);
        succeeded = true;
      } catch (error) {
        if (error instanceof CameraConnectionError) {
          // The camera is gone. Carrying on would spend three retries each on
          // every remaining property before failing anyway.
          throw error;
        }
        if (!(error instanceof CameraWriteError)) throw error;
        // Refused, but the camera is still listening, so the rest is worth
        // writing and this one property is reported at the end.
      }

      if (succeeded) {
        failedCodes.splice(failedCodes.indexOf(code), 1);
        written.push([code, value]);
      }

      // Paid even after a refusal, because the camera still handled a request
      // and the next one needs the same breathing room.
      await sleep(settings.CAMERA_POST_WRITE_DELAY_S);
    }

    // --- Step 4: read back what reported success ---
    if (settings.CAMERA_VERIFY_WRITES) {
      const grainCode = encodings.custom_slot_codes.GrainEffect;
      // Grain Off is written as a sentinel the camera normalises to something
      // else, so its read-back never matches and verifying it would always fail.
      const verifiable = written.filter(
        ([code, value]) => !(code === grainCode && value === encodings.grain_off_sentinel)
      );
      failedCodes.push(...(await verifyWrittenProperties(device, verifiable, runtime)));
    }

    if (failedCodes.length > 0) {
      const names = _codeToPropName(encodings);
      throw new RecipeWriteError(
        failedCodes.map((code) => names[code] ?? `0x${code.toString(16)}`)
      );
    }
  }

  /**
   * Write each assignment to its slot in turn (the server analogue of the
   * client's loop). Each slot is independent on a per-property body.
   *
   * @param {import("../vendor/ptp_device.js").CameraDevice} device
   * @param {Array<[number, object]>} assignments 1-based slot index, recipe
   * @param {object} options
   * @param {{config: object, sleep: Function}} options.runtime
   * @returns {Promise<void>}
   */
  async pushCollection(device, assignments, { runtime }) {
    for (const [slotIndex, recipe] of assignments) {
      await this.pushRecipe(device, recipe, { slotIndex, runtime });
    }
  }

  /**
   * Every slot is feasible and nothing is dropped on a per-property body.
   *
   * @returns {Promise<{slots: Array<{slotIndex: number, feasible: boolean, reason: string}>, droppedFields: string[]}>}
   */
  async planFeasibility(device, recipe, { slotCount }) {
    const slots = [];
    for (let idx = 1; idx <= slotCount; idx += 1) {
      slots.push({ slotIndex: idx, feasible: true, reason: "" });
    }
    return { slots, droppedFields: [] };
  }

  /**
   * Any collection is feasible on a per-property body.
   *
   * @returns {Promise<{ok: boolean, conflicts: string[], droppedFields: string[], unrepresentable: object[]}>}
   */
  async collectionFeasibility() {
    return { ok: true, conflicts: [], droppedFields: [], unrepresentable: [] };
  }
}

/**
 * Name the slot regions a round-trip mismatch touched, for RecipeWriteError.
 *
 * @param {number[]} mismatches
 * @param {object} X prepared X-T2 layout
 * @returns {string[]}
 */
function _affectedSlotLabels(mismatches, X) {
  const labels = new Set();
  const slotsEnd = X.slot0Offset + X.slotSize * X.slotCount;
  for (const offset of mismatches) {
    if (offset >= X.slot0Offset && offset < slotsEnd) {
      labels.add(`C${Math.floor((offset - X.slot0Offset) / X.slotSize) + 1}`);
    } else {
      labels.add("header");
    }
  }
  return labels.size ? [...labels].sort() : ["backup"];
}

/**
 * Strategy for bodies with no per-slot interface (X-T2 and older).
 *
 * Reads, edits and restores the whole settings backup blob; the codec in
 * ./xt2_backup.js does the pure byte work and this composes it over a connected
 * device. Ports src/domain/camera/strategies.py BackupBlobStrategy.
 */
export class BackupBlobStrategy {
  /** @param {object} xt2Layout prepared layout from prepareXt2() */
  constructor(xt2Layout) {
    this._X = xt2Layout;
  }

  async readSlots(device, { runtime }) {
    const encodings = runtime.config.encodings;
    const blob = await device.getBackup();
    return decodeSlotStates(blob, this._X, encodings).map((row) => makeSlotState(row, encodings));
  }

  async pushRecipe(device, recipe, { slotIndex, runtime }) {
    const blob = await this._validatedBackup(device);
    const mapping = mapRecipe(recipe, this._X);
    const feasibility = checkFeasibility(blob, slotIndex - 1, mapping, this._X);
    if (!feasibility.ok) throw new PushNotFeasibleError(feasibility.conflicts);
    const edited = applyRecipe(blob, slotIndex - 1, mapping, this._X);
    await this._restoreAndVerify(device, edited, runtime);
  }

  async pushCollection(device, assignments, { runtime }) {
    const blob = await this._validatedBackup(device);
    const mapped = assignments.map(([slotIndex, recipe]) => [slotIndex - 1, mapRecipe(recipe, this._X)]);
    const feasibility = checkCollectionFeasibility(blob, mapped, this._X);
    if (!feasibility.ok) throw new PushNotFeasibleError(feasibility.conflicts);
    const edited = applyRecipes(blob, mapped, this._X);
    await this._restoreAndVerify(device, edited, runtime);
  }

  async planFeasibility(device, recipe, { slotCount }) {
    const blob = await device.getBackup();
    let mapping;
    try {
      mapping = mapRecipe(recipe, this._X);
    } catch (error) {
      if (error instanceof RecipeNotRepresentable) {
        // A recipe this camera has no film simulation for needs no spelling out,
        // so the picker greys every slot with no note: the empty reason leaves
        // nothing to show.
        const slots = [];
        for (let idx = 1; idx <= slotCount; idx += 1) {
          slots.push({ slotIndex: idx, feasible: false, reason: "" });
        }
        return { slots, droppedFields: [] };
      }
      throw error;
    }
    const slots = [];
    for (let idx = 1; idx <= slotCount; idx += 1) {
      const feasibility = checkFeasibility(blob, idx - 1, mapping, this._X);
      slots.push({
        slotIndex: idx,
        feasible: feasibility.ok,
        reason: feasibility.ok ? "" : feasibility.conflicts.join("; "),
      });
    }
    return { slots, droppedFields: mapping.dropped };
  }

  async collectionFeasibility(device, assignments) {
    const blob = await device.getBackup();
    if (!validateBackup(blob, this._X).ok) {
      return {
        ok: false,
        conflicts: ["The camera's settings backup could not be read."],
        droppedFields: [],
        unrepresentable: [],
      };
    }
    const mapped = [];
    const unrepresentable = [];
    const dropped = [];
    for (const [slotIndex, recipe] of assignments) {
      let mapping;
      try {
        mapping = mapRecipe(recipe, this._X);
      } catch (error) {
        if (error instanceof RecipeNotRepresentable) {
          unrepresentable.push({ slotIndex, field: error.field, value: String(error.value) });
          continue;
        }
        throw error;
      }
      for (const field of mapping.dropped) {
        if (!dropped.includes(field)) dropped.push(field);
      }
      mapped.push([slotIndex - 1, mapping]);
    }
    const feasibility = checkCollectionFeasibility(blob, mapped, this._X);
    return {
      ok: feasibility.ok && unrepresentable.length === 0,
      conflicts: feasibility.conflicts,
      droppedFields: dropped,
      unrepresentable,
    };
  }

  async _validatedBackup(device) {
    const blob = await device.getBackup();
    const report = validateBackup(blob, this._X);
    if (!report.ok) throw new BackupValidationError(report.errors);
    return blob;
  }

  async _restoreAndVerify(device, edited, runtime) {
    const verify = runtime.config.settings.CAMERA_VERIFY_WRITES;
    try {
      await device.restoreBackup(edited);
    } catch (error) {
      // A lost ack may still have applied; only a read-back can confirm. With
      // verification off there is no way to confirm, so surface the failure.
      if (!(error instanceof RestoreAckTimeout) || !verify) throw error;
    }
    if (verify) {
      const result = verifyRoundTrip(await device.getBackup(), edited, this._X);
      if (!result.ok) throw new RecipeWriteError(_affectedSlotLabels(result.mismatches, this._X));
    }
  }
}

/**
 * Return the strategy that drives a camera model.
 *
 * Resolves the model's interface from the served profile (the same allow-list
 * get_profile uses on the server): a backup-blob body gets the backup strategy,
 * every other model the per-property one.
 *
 * @param {string} cameraName The model reported by the connected device.
 * @param {object} config The served client config (settings/encodings/profile).
 * @returns {PerPropertyStrategy|BackupBlobStrategy}
 */
export function getStrategy(cameraName, config) {
  const profile = config && config.profile;
  const interfaceByModel = (profile && profile.interface_by_model) || {};
  const defaultInterface = (profile && profile.default_interface) || "per_property";
  const iface = interfaceByModel[cameraName] ?? defaultInterface;
  if (iface === "backup_blob") {
    return new BackupBlobStrategy(prepareXt2(profile.xt2));
  }
  return new PerPropertyStrategy();
}
