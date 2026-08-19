/**
 * Camera events, browser side.
 *
 * Ports src/domain/camera/events.py. The server publishes these into structlog,
 * where they end up queryable; a browser has nowhere comparable to send them, so
 * they go to console.debug and to a bounded buffer on window.
 *
 * That buffer is the point. When a push fails on someone else's machine the only
 * evidence is whatever they can be talked through reading out, and
 * `FilmcaseCameraEvents.recent()` in the console is a great deal easier to ask
 * for than a screenshot of a scrolled console.
 *
 * Sending these to the server is deliberately not done here. It would need a
 * CSRF token and an endpoint, and it is worth doing only once there is evidence
 * anyone needs it.
 */

// Event type constants (reverse domain name notation), identical to the Python
// so a browser report and a server log can be grepped with one pattern.
export const PTP_WRITE_FAILED = "camera.ptp_write.failed";
export const PTP_WRITE_SUCCEEDED = "camera.ptp_write.succeeded";
export const PTP_READ_FAILED = "camera.ptp_read.failed";
export const PTP_READ_SUCCEEDED = "camera.ptp_read.succeeded";

/** Kept small enough to paste, large enough to hold a whole push. */
const MAX_RETAINED = 200;

const retained = [];

/**
 * Publish a structured camera event.
 *
 * @param {object} event
 * @param {string} event.eventType One of the constants above.
 */
export function publishEvent({ eventType, ...rest }) {
  const event = { eventType, ...rest };
  retained.push(event);
  if (retained.length > MAX_RETAINED) {
    retained.shift();
  }
  if (typeof console !== "undefined" && console.debug) {
    console.debug(eventType, rest);
  }
}

/**
 * The events published so far, oldest first.
 *
 * @returns {object[]}
 */
export function recent() {
  return [...retained];
}

/** Drop everything retained. Used by tests, and available for a fresh attempt. */
export function reset() {
  retained.length = 0;
}

// Exposed for support: a user can be asked to run this in the console.
if (typeof window !== "undefined") {
  window.FilmcaseCameraEvents = { recent, reset };
}
