/**
 * Write a recipe into one of the camera's custom slots.
 *
 * Ports src/application/usecases/camera/push_recipe.py.
 *
 * Two rules run through the whole sequence and neither is negotiable.
 *
 * Order. Every write after the first lands in whichever slot the cursor points
 * at, and within the recipe the colour temperature has to precede the two white
 * balance shifts or the camera zeroes them. Nothing here may run concurrently.
 *
 * Failure. A camera that refuses one property is still there, so the remaining
 * properties are still worth writing and the user is told which one did not
 * take. A camera that has stopped answering is not, so the sequence stops
 * rather than spending three retries each on eighteen more writes.
 */

import { CameraConnectionError, CameraWriteError } from "../../vendor/ptp_device.js";
import {
  setCursorWithRetry,
  setPropWithRetry,
  verifyWrittenProperties,
} from "../../domain/operations.js";
import { ptpValueItems, recipeToPtpValues } from "../../domain/queries.js";

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
 * Write a recipe to a custom slot.
 *
 * The device must already be connected; disconnecting is the caller's job, as
 * it is the caller that obtained the device from the browser in the first place.
 *
 * @param {import("../../vendor/ptp_device.js").CameraDevice} device
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
export async function pushRecipeToCamera(device, recipe, { slotIndex, runtime }) {
  const { config, sleep } = runtime;
  const encodings = config.encodings;
  const settings = config.settings;

  // --- Step 1: point the camera at the slot ---
  // Retried, unlike the Python, which calls this once. The slot listing already
  // retries its cursor writes and this is the same write; leaving it bare meant
  // a single stall abandoned the push before a byte of the recipe was sent,
  // which on hardware that stalls intermittently is the difference between a
  // push that works and one that works most of the time.
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
