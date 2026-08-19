/**
 * A minimal client config for tests that only need timings and a few codes.
 *
 * Deliberately hand-written and short. The full encodings tables travel with
 * the golden vectors, next to the expectations they were frozen against; tests
 * of the transport, the retry loops and the use cases need none of that, and a
 * 300-line dump here would obscure the handful of values that actually matter.
 */

/** Property codes, matching src/data/camera/constants.py. */
export const PROP_PING = 0xd023;
export const PROP_SLOT_CURSOR = 0xd18c;
export const PROP_SLOT_NAME = 0xd18d;
export const PROP_FILM_SIMULATION = 0xd192;

/**
 * @param {object} [overrides] Settings to change, by their Django names.
 * @returns {object}
 */
export function makeConfig(overrides = {}) {
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
      ...overrides,
    },
    encodings: {
      vendor_id: 0x04cb,
      prop_ping: PROP_PING,
      prop_slot_cursor: PROP_SLOT_CURSOR,
      prop_slot_name: PROP_SLOT_NAME,
      recipe_name_max_len: 25,
      custom_slot_codes: {
        FilmSimulation: PROP_FILM_SIMULATION,
        GrainEffect: 0xd195,
      },
      camera_custom_slot_counts: { "X-S10": 4, "X-T4": 7 },
    },
  };
}
