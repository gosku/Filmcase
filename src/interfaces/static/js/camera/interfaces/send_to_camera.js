/**
 * The "Send to camera" button, when the browser drives the camera.
 *
 * This is the interfaces layer: it turns clicks into use case calls and results
 * into markup, and holds no protocol knowledge of its own.
 *
 * Two browser constraints shape the whole file.
 *
 * The device picker needs a live user gesture, and the window is short. So the
 * config and the already-granted device are both fetched on page load, and the
 * click handler reaches requestDevice() with nothing awaited in front of it.
 * A camera granted once never prompts again.
 *
 * HTMX swaps the recipe detail in and out, and a module runs once per URL, so a
 * script inside the swapped fragment would never re-run. The button is wired by
 * one delegated listener on the body instead, the same shape the page already
 * uses for its HTMX hooks.
 */

import { loadClientConfig } from "../vendor/client_config.js";
import { fetchRecipePayload } from "../vendor/recipe_payload.js";
import { ClientPTPUSBDevice } from "../vendor/ptp_usb_device.js";
import { CameraConnectionError, CameraWriteError } from "../vendor/ptp_device.js";
import { RecipeValidationError } from "../domain/validation.js";
import { getCameraSlots } from "../application/usecases/get_camera_slots.js";
import {
  RecipeWriteError,
  pushRecipeToCamera,
} from "../application/usecases/push_recipe.js";

// The same wording the server-rendered path uses, so switching transports does
// not change what a user is told about the same failure.
const NO_CAMERA =
  "No camera found. Make sure it's connected via USB and set to PC Connection " +
  "or RAW CONV. mode.";
const REJECTED = "The camera rejected a write operation. Please try again.";
const UNEXPECTED = "An unexpected error occurred. Please try again.";

/** Resolved once, on load. */
let configPromise = null;
/** A camera this origin has already been granted, if one is plugged in. */
let grantedDevice = null;

function configUrl() {
  const element = document.getElementById("camera-client-config");
  return element ? element.dataset.url : null;
}

function templateNode(id) {
  const template = document.getElementById(id);
  return template ? template.content.cloneNode(true) : null;
}

/** Why this browser cannot drive a camera, or null if it can. */
function unavailableReason() {
  if (!window.isSecureContext) {
    return (
      "This page is not a secure context, so the browser will not allow USB " +
      "access. Reach Filmcase over HTTPS, or over http://localhost when it runs " +
      "on this machine."
    );
  }
  if (!("usb" in navigator)) {
    return (
      "This browser has no WebUSB support. It is available in Chrome, Edge, " +
      "Brave and Opera, and not in Firefox or Safari."
    );
  }
  return null;
}

function showUnavailable(reason) {
  const node = templateNode("camera-unavailable-template");
  if (!node) return;
  node.querySelector("[data-unavailable-reason]").textContent = reason;
  window.SlotOverlay.show(node);
}

/**
 * The card that overlay content sits in, creating one if none exists yet.
 *
 * The result and error templates deliberately carry no card of their own,
 * because on the server-rendered path HTMX swaps them into the #slot-card the
 * slot picker already put on the page. A failure before the picker renders,
 * which is every failure while looking for the camera, has no such card, and
 * putting the bare content into the overlay leaves the message floating on the
 * backdrop with no background behind it.
 *
 * @param {string} [recipeName] Shown in the header when a card has to be made.
 * @returns {Element|null}
 */
function ensureCard(recipeName) {
  const existing = document.getElementById("slot-card");
  if (existing) return existing;
  const shell = templateNode("camera-slot-card-template");
  if (!shell) return null;
  shell.querySelector("[data-recipe-name]").textContent = recipeName ?? "";
  window.SlotOverlay.show(shell);
  return document.getElementById("slot-card");
}

function showError(message, onRetry, recipeName) {
  const node = templateNode("camera-push-error-template");
  if (!node) return;
  node.querySelector("[data-push-error]").textContent = message;
  const retry = node.querySelector("[data-push-retry]");
  if (onRetry) {
    retry.textContent = "Try again";
    retry.addEventListener("click", onRetry);
  } else {
    retry.remove();
  }
  const card = ensureCard(recipeName);
  if (card) card.replaceChildren(node);
}

function showSuccess(message) {
  const node = templateNode("camera-push-success-template");
  if (!node) return;
  node.querySelector("[data-push-message]").textContent = message;
  const card = document.getElementById("slot-card");
  if (card) card.replaceChildren(node);
}

/**
 * Obtain a camera without spending the user gesture.
 *
 * getDevices() is consulted on load rather than here: awaiting it first would
 * put a promise between the click and requestDevice(), and the activation
 * window is measured in seconds.
 */
async function chooseDevice(vendorId) {
  if (grantedDevice) {
    console.debug("camera.device.remembered", {
      product: grantedDevice.productName,
      serial: grantedDevice.serialNumber,
    });
    return grantedDevice;
  }
  const device = await navigator.usb.requestDevice({ filters: [{ vendorId }] });
  console.debug("camera.device.picked", {
    product: device.productName,
    serial: device.serialNumber,
  });
  grantedDevice = device;
  return device;
}

/** Run `work` against a freshly connected camera, and always release it. */
async function withCamera(config, work) {
  const usbDevice = await chooseDevice(config.encodings.vendor_id);
  const device = new ClientPTPUSBDevice({ usbDevice, config });
  await device.connect();
  try {
    return await work(device);
  } finally {
    // Released even on failure: a camera left claimed cannot be picked up by
    // the next attempt, or by anything else on the machine.
    await device.disconnect();
  }
}

const runtimeFor = (config) => ({
  config,
  sleep: (seconds) => new Promise((resolve) => setTimeout(resolve, seconds * 1000)),
});

function renderSlots(recipe, slots, onPick) {
  const card = templateNode("camera-slot-card-template");
  card.querySelector("[data-recipe-name]").textContent = recipe.name;
  const rows = card.querySelector("[data-slot-rows]");

  for (const slot of slots) {
    const row = templateNode("camera-slot-row-template");
    const button = row.querySelector("[data-slot-index]");
    button.dataset.slotIndex = String(slot.index);
    row.querySelector("[data-slot-label]").textContent = `C${slot.index}`;
    // An em dash rather than nothing, matching the server-rendered picker: an
    // empty row reads as a broken layout rather than an unnamed slot.
    row.querySelector("[data-slot-name]").textContent = slot.name || "—";
    const tag = row.querySelector("[data-slot-film-sim]");
    if (slot.filmSimName) {
      tag.textContent = slot.filmSimName;
      tag.hidden = false;
    }
    button.addEventListener("click", () => onPick(slot.index));
    rows.appendChild(row);
  }

  window.SlotOverlay.show(card);
}

/** Turn a failure into the sentence a user should read. */
function describe(error, slotLabel) {
  if (error instanceof RecipeWriteError) {
    return (
      `Some settings couldn't be saved (${error.failedProperties.join(", ")}). ` +
      "Please try again."
    );
  }
  if (error instanceof RecipeValidationError) {
    // Worth naming the field: this one is fixable in the app rather than by
    // fiddling with the camera.
    return `This recipe can't be written to the camera: ${error.field} is not valid.`;
  }
  if (error instanceof CameraConnectionError) {
    // The card says something a user can act on, which loses the detail. Log
    // the original so the console still says which phase failed and why.
    console.error("Camera connection failed", error.message);
    return NO_CAMERA;
  }
  if (error instanceof CameraWriteError) {
    console.error("Camera refused a write", error.message);
    return REJECTED;
  }
  if (error && error.name === "NotFoundError") return null; // picker cancelled
  if (error && error.name === "SecurityError") return unavailableReason() ?? UNEXPECTED;
  console.error("Unexpected error pushing to the camera", error);
  return slotLabel ? UNEXPECTED : NO_CAMERA;
}

async function pushToSlot(config, recipe, slotIndex) {
  const label = `C${slotIndex}`;
  window.SlotOverlay.showPushSpinner();
  try {
    await withCamera(config, (device) =>
      pushRecipeToCamera(device, recipe, { slotIndex, runtime: runtimeFor(config) })
    );
  } catch (error) {
    const message = describe(error, label);
    if (message === null) return;
    showError(message, () => pushToSlot(config, recipe, slotIndex), recipe.name);
    return;
  }
  showSuccess(`Recipe saved to ${label}`);
}

async function openSlotPicker(button) {
  const reason = unavailableReason();
  if (reason) {
    showUnavailable(reason);
    return;
  }

  let config;
  let recipe;
  try {
    config = await configPromise;
    recipe = await fetchRecipePayload(button.dataset.payloadUrl);
  } catch (error) {
    console.error("Could not load the camera configuration or recipe", error);
    showError(UNEXPECTED, null);
    return;
  }

  window.SlotOverlay.showSpinner();
  let slots;
  try {
    slots = await withCamera(config, (device) =>
      getCameraSlots(device, runtimeFor(config))
    );
  } catch (error) {
    const message = describe(error, null);
    if (message === null) {
      window.SlotOverlay.close();
      return;
    }
    showError(message, () => openSlotPicker(button), recipe.name);
    return;
  }

  if (slots.length === 0) {
    showError(
      "This camera model has no custom slots to write to, or Filmcase does not " +
        "recognise it.",
      null,
      recipe.name
    );
    return;
  }

  renderSlots(recipe, slots, (slotIndex) => pushToSlot(config, recipe, slotIndex));
}

function start() {
  const url = configUrl();
  if (!url) {
    // The config element ships with the templates, which are only included when
    // the browser owns the transport. Its absence means server mode.
    return;
  }

  configPromise = loadClientConfig(url);
  if ("usb" in navigator) {
    // Warmed here so the click handler never has to await before showing the
    // picker. A camera granted on a previous visit is found without prompting.
    navigator.usb
      .getDevices()
      .then((devices) => {
        grantedDevice = devices[0] ?? null;
      })
      .catch(() => {
        grantedDevice = null;
      });
    navigator.usb.addEventListener("disconnect", () => {
      grantedDevice = null;
    });
  }

  document.body.addEventListener("click", (event) => {
    const button = event.target.closest("[data-camera-push]");
    if (!button) return;
    event.preventDefault();
    openSlotPicker(button);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", start);
} else {
  start();
}
