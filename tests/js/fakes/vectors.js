/**
 * The shared golden vectors, and the encodings they were frozen against.
 *
 * The JavaScript suite has no Django to ask for the encoding tables, so they
 * travel inside the vectors file, next to the expectations they belong to. That
 * placement is deliberate: it reads as test input pinned with its results,
 * rather than as a mirror of constants.py that somebody is on the hook to keep
 * current. Production never uses it; the browser reads the live endpoint.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function load(name) {
  return JSON.parse(
    readFileSync(
      fileURLToPath(new URL(`../../fixtures/camera/${name}`, import.meta.url)),
      "utf8"
    )
  );
}

const recipeVectors = load("recipe_ptp_vectors.json");

/** The encodings block of the client config, as the server would serve it. */
export const ENCODINGS = recipeVectors.encodings;

/** Recipe to expected (code, value) pairs, asserted by both suites. */
export const RECIPE_VECTORS = recipeVectors.vectors;

/** Recipe overrides to accept/reject outcome, asserted by both suites. */
export const VALIDATION_VECTORS = recipeVectors.validation_vectors;

/** PTP wire-format byte vectors, asserted by both suites. */
export const PTP_VECTORS = load("ptp_vectors.json");

/**
 * A recipe that validates and converts cleanly, for tests that need a starting
 * point rather than a particular case.
 *
 * @param {object} [overrides]
 * @returns {object}
 */
export function makeRecipe(overrides = {}) {
  const base = RECIPE_VECTORS.find((v) => v.name === "named_white_balance").recipe;
  return { ...base, ...overrides };
}
