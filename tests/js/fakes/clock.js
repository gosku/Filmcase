/**
 * A sleep that records instead of waiting.
 *
 * The Python suite zeroes the camera delays in conftest.py; this is the same
 * idea, except it also keeps what it was asked to wait for. That turns the
 * delays into something assertable: the ordering of a push, and the backoff
 * sequence of a retry, are both behaviour worth pinning rather than timing
 * worth enduring.
 */

/**
 * @returns {{sleep: (seconds: number) => Promise<void>, slept: number[]}}
 */
export function makeClock() {
  /** Every duration asked for, in seconds, in order. */
  const slept = [];

  async function sleep(seconds) {
    slept.push(seconds);
  }

  return { sleep, slept };
}
