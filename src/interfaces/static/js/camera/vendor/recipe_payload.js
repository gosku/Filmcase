/**
 * A recipe, fetched from the server in the shape the camera write path expects.
 *
 * Deliberately not cached. A recipe edited in another tab should not be pushed
 * from a stale copy, and the endpoint says no-store for the same reason.
 */

/**
 * @param {string} url The recipe's camera-payload URL.
 * @returns {Promise<object>} A recipe in FujifilmRecipeData shape.
 */
export async function fetchRecipePayload(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`Recipe payload request failed: ${response.status}`);
  }
  return response.json();
}
