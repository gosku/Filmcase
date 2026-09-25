/**
 * Write one recipe to one camera slot through the server-side push endpoint.
 *
 * Used when the Filmcase host drives the camera (server transport): the browser
 * only sequences the writes, so talking to that endpoint is a vendor concern,
 * the same as fetching a recipe payload. Nothing is cached — each call is one
 * write the user asked for.
 */

/**
 * @param {object} args
 * @param {string|number} args.recipeId The recipe to write.
 * @param {string} args.slotLabel The target slot, e.g. "C1".
 * @param {string} args.csrfToken The Django CSRF token for the POST.
 * @returns {Promise<void>} Resolves on success; rejects if the write fails.
 */
export async function pushRecipeToSlot({ recipeId, slotLabel, csrfToken }) {
  const response = await fetch(`/recipes/${recipeId}/push/${slotLabel}/`, {
    method: "POST",
    headers: { "X-CSRFToken": csrfToken },
  });
  if (!response.ok) {
    throw new Error(`Push request failed: ${response.status}`);
  }
}
