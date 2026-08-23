/**
 * A client config for tests.
 *
 * The settings are hand-written and short, because the delays are what a test
 * usually wants to change and a handful of named numbers is easier to reason
 * about than a served payload.
 *
 * The encodings are not hand-written. They come from the shared golden vectors,
 * so tests convert with the same tables the Python generated rather than with a
 * hand-made subset that could quietly disagree. An earlier version of this file
 * did keep a subset, and it was missing the film simulation table, which showed
 * up as a null dereference three commits later rather than as a wrong value.
 */

import { ENCODINGS } from "./vectors.js";

/** Property codes worth naming, matching src/data/camera/constants.py. */
export const PROP_PING = ENCODINGS.prop_ping;
export const PROP_SLOT_CURSOR = ENCODINGS.prop_slot_cursor;
export const PROP_SLOT_NAME = ENCODINGS.prop_slot_name;
export const PROP_FILM_SIMULATION = ENCODINGS.custom_slot_codes.FilmSimulation;

/**
 * @param {object} [settingOverrides] Settings to change, by their Django names.
 * @returns {object}
 */
export function makeConfig(settingOverrides = {}) {
  return {
    settings: {
      CAMERA_TRANSPORT: "browser",
      CAMERA_VERIFY_WRITES: false,
      // Zero by default, exactly as conftest.py does for the Python suite: the
      // delays exist for hardware, and paying them in tests only makes the
      // suite slow enough to stop being run.
      CAMERA_POST_READ_DELAY_S: 0,
      CAMERA_PRE_WRITE_DELAY_S: 0,
      CAMERA_POST_WRITE_DELAY_S: 0,
      CAMERA_POST_CURSOR_DELAY_S: 0,
      CAMERA_INTER_SLOT_DELAY_S: 0,
      CAMERA_MAX_RETRIES: 3,
      CAMERA_RETRY_BACKOFF_S: 0.15,
      CAMERA_USB_TIMEOUT_MS: 1500,
      ...settingOverrides,
    },
    encodings: ENCODINGS,
  };
}
