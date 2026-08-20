/**
 * The camera configuration, fetched from the server.
 *
 * Vendor rather than data: there is no data layer on the client, and this talks
 * to something outside the browser. It is also the reason the browser holds no
 * copy of the encoding tables. They are served, so a film simulation added on
 * the server reaches the client on the next request with no second file to
 * update and nothing to keep in step.
 */

/** Resolved once per page: the config does not change under a loaded page. */
let cached = null;

/**
 * Fetch the client config, or return the fetch already in flight.
 *
 * @param {string} url
 * @returns {Promise<object>}
 */
export function loadClientConfig(url) {
  if (cached === null) {
    cached = fetch(url, { headers: { Accept: "application/json" } }).then((response) => {
      if (!response.ok) {
        throw new Error(`Camera config request failed: ${response.status}`);
      }
      return response.json();
    });
    // A failed fetch must not poison the page: dropping the cache lets the next
    // click try again rather than replaying the same rejection for ever.
    cached.catch(() => {
      cached = null;
    });
  }
  return cached;
}

/** Forget the cached config. Used by tests, and after a failure. */
export function resetClientConfig() {
  cached = null;
}
