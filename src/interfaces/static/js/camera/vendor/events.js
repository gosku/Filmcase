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

// Session lifecycle. These have no Python counterpart, and are here because the
// server has a log and the browser does not: without them a failure to open,
// claim or start a session produces no trace at all, which is the one part of a
// push where nothing else is recorded.
export const SESSION_STEP = "camera.session.step";
export const SESSION_OPENED = "camera.session.opened";
export const SESSION_FAILED = "camera.session.failed";
export const SESSION_CLOSED = "camera.session.closed";
export const PTP_READ_RETRY = "camera.ptp_read.retry";
export const PTP_CONTAINER = "camera.ptp_container";
export const PTP_TX_MISMATCH = "camera.ptp_transaction.mismatch";
export const SLOT_RETRY = "camera.slot_read.retry";

// Fine-grained tracing. Buffered always, printed only when verbose is on: a
// push produces three of these per property, which is what makes them useful
// for diagnosis and unbearable as a default.
export const PTP_SENT = "camera.ptp_sent";
export const PTP_RECEIVED = "camera.ptp_received";
export const SLOT_PROGRESS = "camera.slot_read.started";

/** Kept small enough to paste, large enough to hold a whole push. */
const MAX_RETAINED = 200;

const retained = [];

/** When the previous event was published, for the gap between them. */
let lastAt = null;

/**
 * Whether the fine-grained trace reaches the console.
 *
 * Off by default and remembered across reloads, because the answer to "what is
 * my camera doing" is usually needed on a machine that is already misbehaving,
 * and asking someone to edit a file first is a poor start.
 */
let verbose = (() => {
  try {
    return window.localStorage.getItem("filmcase.camera.verbose") === "1";
  } catch {
    // Storage can be unavailable in a private window; tracing off is fine.
    return false;
  }
})();

function setVerbose(on) {
  verbose = Boolean(on);
  try {
    window.localStorage.setItem("filmcase.camera.verbose", verbose ? "1" : "0");
  } catch {
    // Not persisting is survivable; the flag still applies to this page.
  }
  return `camera tracing ${verbose ? "on" : "off"}`;
}

/** Milliseconds since page load. */
function _now() {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

/**
 * Publish a structured camera event.
 *
 * @param {object} event
 * @param {string} event.eventType One of the constants above.
 */
export function publishEvent({ eventType, ...rest }, traceOnly = false) {
  const at = _now();
  // The gap matters as much as the order. A back-off that is not happening and
  // one that is look identical in a list of events, and the difference decides
  // whether a camera is being given time to recover or hammered three times in
  // a row. The delta is logged first so it can be read without arithmetic.
  const sinceLastMs = lastAt === null ? 0 : Math.round(at - lastAt);
  lastAt = at;

  const event = { eventType, ...rest, atMs: Math.round(at), sinceLastMs };
  retained.push(event);
  if (retained.length > MAX_RETAINED) {
    retained.shift();
  }
  if (!traceOnly || verbose) {
    if (typeof console !== "undefined" && console.debug) {
      console.debug(`+${String(sinceLastMs).padStart(5)}ms`, eventType, rest);
    }
  }
}

/**
 * Publish an event that is only worth reading when something is wrong.
 *
 * Kept in the buffer either way, so `FilmcaseCameraEvents.recent()` has the
 * full picture even when the console was quiet at the time. That matters: the
 * interesting failure is usually the one nobody was watching for.
 */
export function publishTrace(event) {
  publishEvent(event, true);
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
  lastAt = null;
}

// Exposed for support: a user can be asked to run these in the console.
//
//   FilmcaseCameraEvents.verbose(true)   trace every transfer from now on
//   FilmcaseCameraEvents.recent()        everything recorded, verbose or not
if (typeof window !== "undefined") {
  window.FilmcaseCameraEvents = { recent, reset, verbose: setVerbose };
}
