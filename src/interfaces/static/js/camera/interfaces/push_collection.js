/**
 * "Push all to camera" for a whole collection.
 *
 * Like send_to_camera.js this is the interfaces layer: it turns clicks into use
 * case calls and results into markup. It reuses the single-recipe primitives —
 * one recipe is written per slot, in slot order — and marks each row as it goes,
 * so a failure on one recipe never aborts the rest.
 *
 * Two transports share every bit of DOM/drag/progress logic below; they differ
 * only in how the modal opens and how one recipe is written:
 *   - Server transport: the modal is server-rendered (swapped into #slot-overlay
 *     by the button's hx-get) and each recipe is written by POSTing to the
 *     existing push-recipe-to-camera endpoint.
 *   - Browser transport: the modal is built here from the collection rows and a
 *     live slot read, and each recipe is written over WebUSB with
 *     pushRecipeToCamera, exactly as the single-recipe push does.
 */

import { loadClientConfig } from "../vendor/client_config.js";
import { fetchRecipePayload } from "../vendor/recipe_payload.js";
import { pushRecipeToSlot } from "../vendor/push_endpoint.js";
import { ClientPTPUSBDevice } from "../vendor/ptp_usb_device.js";
import { CameraConnectionError, CameraWriteError } from "../vendor/ptp_device.js";
import { RecipeValidationError } from "../domain/validation.js";
import { getCameraSlots } from "../application/usecases/get_camera_slots.js";
import { RecipeWriteError, pushRecipeToCamera } from "../application/usecases/push_recipe.js";

const NO_CAMERA =
  "No camera found. Make sure it's connected via USB and set to PC Connection " +
  "or RAW CONV. mode.";
const REJECTED = "The camera rejected a write operation. Please try again.";
const UNEXPECTED = "An unexpected error occurred. Please try again.";

// ---------------------------------------------------------------------------
// Shared: per-row status, drag reorder, progress, and the transfer loop.
// All of it works on the class/data contract that both the server template
// (collection_push_modal.html) and the browser-built modal below produce.
// ---------------------------------------------------------------------------

const CHECK_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
const CROSS_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>';
const SPINNER_SVG =
  '<svg class="cpush-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.2-8.5"></path></svg>';

function currentSlotNames(root) {
  const map = {};
  root.querySelectorAll(".cpush__col--before .cpush-slot").forEach((slot) => {
    const label = slot.querySelector(".cpush-badge").textContent.trim();
    const name = slot.querySelector(".cpush-slot__name").textContent.trim();
    map[label] = name;
  });
  return map;
}

function assignmentRows(root) {
  return Array.from(root.querySelectorAll('[data-transfer-list] .cpush-row[draggable="true"]'));
}

/** Re-label the target slots C1..Cn by their current order after a drag. */
function relabel(root) {
  const names = currentSlotNames(root);
  assignmentRows(root).forEach((row, i) => {
    const label = `C${i + 1}`;
    const badge = row.querySelector("[data-slot-badge]");
    if (badge) badge.textContent = label;
    const replaces = row.querySelector("[data-replaces]");
    if (replaces) replaces.textContent = `replaces ${names[label] || "empty"}`;
  });
}

function setStatus(row, state, onRetry) {
  row.classList.remove("cpush-row--sending", "cpush-row--sent", "cpush-row--failed");
  const cell = row.querySelector("[data-status]");
  if (!cell) return;
  if (state === "sending") {
    row.classList.add("cpush-row--sending");
    cell.innerHTML = `${SPINNER_SVG}<span>Sending…</span>`;
  } else if (state === "sent") {
    row.classList.add("cpush-row--sent");
    cell.innerHTML = `${CHECK_SVG}<span>Sent</span>`;
  } else if (state === "failed") {
    row.classList.add("cpush-row--failed");
    cell.innerHTML = `${CROSS_SVG}<span>Failed</span>`;
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "cpush-row__retry";
    retry.textContent = "Retry";
    retry.addEventListener("click", onRetry);
    cell.appendChild(retry);
  } else {
    cell.innerHTML = "";
  }
}

function showProgress(root) {
  const bar = root.querySelector("[data-progress]");
  if (bar) bar.hidden = false;
}

function setProgress(root, label, attempts, total) {
  const labelEl = root.querySelector("[data-progress-label]");
  const countsEl = root.querySelector("[data-progress-counts]");
  const fill = root.querySelector("[data-progress-fill]");
  if (labelEl) labelEl.textContent = label;
  if (fill) fill.style.width = total ? `${Math.round((attempts / total) * 100)}%` : "0%";
  if (countsEl) countsEl.dataset.done = String(attempts);
}

function setCounts(root, sent, failed, left) {
  const countsEl = root.querySelector("[data-progress-counts]");
  if (countsEl) countsEl.textContent = `${sent} sent · ${failed} failed · ${left} left`;
}

/**
 * Write every assigned recipe in slot order, marking each row as it resolves.
 *
 * `writeOne(row, recipeId, slotLabel, slotIndex)` performs one write and throws
 * on failure. Failures are caught per row so the run always continues.
 */
async function runTransfer(root, writeOne) {
  const rows = assignmentRows(root);
  if (rows.length === 0) return;

  // Lock ordering and the start button once the run begins.
  rows.forEach((row) => row.setAttribute("draggable", "false"));
  const start = root.querySelector("[data-start]");
  if (start) start.disabled = true;
  const hint = root.querySelector("[data-reorder-hint]");
  if (hint) hint.remove();
  showProgress(root);

  const total = rows.length;
  let sent = 0;
  let failed = 0;

  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const label = `C${i + 1}`;
    setProgress(root, `Transferring… slot ${label} of ${total}`, i, total);
    setCounts(root, sent, failed, total - i);
    setStatus(row, "sending");
    // eslint-disable-next-line no-await-in-loop
    const ok = await attempt(writeOne, row, label, i + 1);
    if (ok) sent++;
    else {
      failed++;
      wireRetry(root, row, label, i + 1, writeOne);
    }
    setCounts(root, sent, failed, total - i - 1);
  }

  setProgress(root, failed ? "Finished with errors" : "All recipes sent", total, total);
  setCounts(root, sent, failed, 0);
  if (start) {
    start.disabled = false;
    start.textContent = "Done";
    start.dataset.done = "true";
  }
}

/** Run one write, marking the row, and report whether it succeeded. */
async function attempt(writeOne, row, label, slotIndex) {
  try {
    await writeOne(row, row.dataset.recipeId, label, slotIndex);
    setStatus(row, "sent");
    return true;
  } catch (error) {
    console.error("Collection push: a recipe failed", error);
    return false;
  }
}

function wireRetry(root, row, label, slotIndex, writeOne) {
  setStatus(row, "failed", async () => {
    setStatus(row, "sending");
    const ok = await attempt(writeOne, row, label, slotIndex);
    if (!ok) wireRetry(root, row, label, slotIndex, writeOne);
    recount(root);
  });
}

/** Recompute the header counts from the rows' current states (used after a retry). */
function recount(root) {
  const rows = assignmentRows(root);
  const sent = rows.filter((r) => r.classList.contains("cpush-row--sent")).length;
  const failed = rows.filter((r) => r.classList.contains("cpush-row--failed")).length;
  setCounts(root, sent, failed, rows.length - sent - failed);
}

function wireDrag(root) {
  const list = root.querySelector("[data-transfer-list]");
  if (!list) return;
  let dragging = null;

  list.addEventListener("dragstart", (e) => {
    const row = e.target.closest('.cpush-row[draggable="true"]');
    if (!row) return;
    dragging = row;
    row.classList.add("cpush-row--dragging");
  });
  list.addEventListener("dragend", () => {
    if (dragging) dragging.classList.remove("cpush-row--dragging");
    dragging = null;
    relabel(root);
  });
  list.addEventListener("dragover", (e) => {
    if (!dragging) return;
    e.preventDefault();
    const rows = assignmentRows(root).filter((r) => r !== dragging);
    const after = rows.find((row) => {
      const box = row.getBoundingClientRect();
      return e.clientY < box.top + box.height / 2;
    });
    if (after) list.insertBefore(dragging, after);
    else {
      // Keep dragged rows above the kept/dropped rows, which never move.
      const firstStatic = list.querySelector(".cpush-row--kept, .cpush-row--dropped");
      if (firstStatic) list.insertBefore(dragging, firstStatic);
      else list.appendChild(dragging);
    }
  });
}

// ---------------------------------------------------------------------------
// Server transport: modal arrives via HTMX, recipes written by POSTing to the
// existing single-recipe push endpoint.
// ---------------------------------------------------------------------------

function serverWriter(root) {
  const csrfToken = root.dataset.csrf;
  return (_row, recipeId, slotLabel) => pushRecipeToSlot({ recipeId, slotLabel, csrfToken });
}

function initServerModal(root) {
  if (root.dataset.wired) return;
  root.dataset.wired = "true";
  wireDrag(root);
  const start = root.querySelector("[data-start]");
  if (start) {
    start.addEventListener("click", () => {
      if (start.dataset.done) {
        window.SlotOverlay.close();
        return;
      }
      runTransfer(root, serverWriter(root));
    });
  }
}

// ---------------------------------------------------------------------------
// Browser transport: build the modal from the collection rows plus a live slot
// read, and write each recipe over WebUSB.
// ---------------------------------------------------------------------------

let configPromise = null;
let grantedDevice = null;

function configUrl() {
  const el = document.getElementById("camera-client-config");
  return el ? el.dataset.url : null;
}

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

async function chooseDevice(vendorId) {
  if (grantedDevice) return grantedDevice;
  grantedDevice = await navigator.usb.requestDevice({ filters: [{ vendorId }] });
  return grantedDevice;
}

async function withCamera(config, work) {
  const usbDevice = await chooseDevice(config.encodings.vendor_id);
  const device = new ClientPTPUSBDevice({ usbDevice, config });
  await device.connect();
  try {
    return await work(device);
  } finally {
    await device.disconnect();
  }
}

const runtimeFor = (config) => ({
  config,
  sleep: (seconds) => new Promise((resolve) => setTimeout(resolve, seconds * 1000)),
});

/** The collection's recipes, in order, read from the detail list. */
function collectionRecipes() {
  return Array.from(document.querySelectorAll(".cdetail-row[data-recipe-id]")).map((row) => ({
    recipeId: row.dataset.recipeId,
    name: (row.querySelector(".cdetail-row__name")?.textContent || "").trim(),
    filmSim: row.dataset.filmSim || "",
    payloadUrl: `/recipes/${row.dataset.recipeId}/camera-payload.json`,
  }));
}

function showMessage(text) {
  const wrap = document.createElement("div");
  wrap.id = "collection-push";
  wrap.className = "cpush cpush--message";
  wrap.innerHTML =
    '<button class="slot-card-close" onclick="closeSlotOverlay()" title="Close">✕</button>' +
    `<p class="slot-error"></p>`;
  wrap.querySelector(".slot-error").textContent = text;
  window.SlotOverlay.show(wrap);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function slotRow(label, name, filmSim) {
  const row = el("div", "cpush-slot");
  row.appendChild(el("span", "cpush-badge", label));
  const info = el("span", "cpush-slot__info");
  info.appendChild(el("span", "cpush-slot__name", name || "—"));
  if (filmSim) info.appendChild(el("span", "slot-film-tag", filmSim));
  row.appendChild(info);
  return row;
}

function assignmentRow(label, recipe, replacesName) {
  const row = el("div", "cpush-row");
  row.setAttribute("draggable", "true");
  row.dataset.recipeId = recipe.recipeId;
  row.dataset.payloadUrl = recipe.payloadUrl;
  row.appendChild(el("span", "cpush-row__handle", "⋮⋮"));
  const badge = el("span", "cpush-badge cpush-badge--target", label);
  badge.dataset.slotBadge = "true";
  row.appendChild(badge);
  const info = el("span", "cpush-row__info");
  info.appendChild(el("span", "cpush-row__name", recipe.name));
  if (recipe.filmSim) info.appendChild(el("span", "slot-film-tag", recipe.filmSim));
  const replaces = el("span", "cpush-row__replaces", `replaces ${replacesName || "empty"}`);
  replaces.dataset.replaces = "true";
  info.appendChild(replaces);
  row.appendChild(info);
  const status = el("span", "cpush-row__status");
  status.dataset.status = "true";
  row.appendChild(status);
  return row;
}

function keptRow(label, name) {
  const row = el("div", "cpush-row cpush-row--kept");
  row.appendChild(el("span", "cpush-row__handle cpush-row__handle--empty"));
  row.appendChild(el("span", "cpush-badge cpush-badge--kept", label));
  const info = el("span", "cpush-row__info");
  info.appendChild(el("span", "cpush-row__name", name || "—"));
  info.appendChild(el("span", "cpush-row__meta", "kept · unchanged"));
  row.appendChild(info);
  return row;
}

function droppedRow(recipe) {
  const row = el("div", "cpush-row cpush-row--dropped");
  const info = el("span", "cpush-row__info");
  info.appendChild(el("span", "cpush-row__name", recipe.name));
  if (recipe.filmSim) info.appendChild(el("span", "slot-film-tag", recipe.filmSim));
  row.appendChild(info);
  return row;
}

/** Build the whole modal DOM from the plan; same class contract as the server template. */
function buildModal({ collectionName, cameraName, slots, recipes }) {
  const written = Math.min(recipes.length, slots.length);
  const root = el("div", "cpush");
  root.id = "collection-push";

  const header = el("div", "cpush__header");
  header.innerHTML =
    '<button class="slot-card-close" onclick="closeSlotOverlay()" title="Close">✕</button>' +
    '<p class="cpush__eyebrow">Push collection to camera</p>';
  header.appendChild(el("p", "cpush__title", collectionName));
  const camera = el("p", "cpush__camera");
  camera.appendChild(el("span", "cpush__camera-name", cameraName));
  camera.appendChild(el("span", "cpush__slotcount", `${slots.length} slot${slots.length === 1 ? "" : "s"}`));
  header.appendChild(camera);
  root.appendChild(header);

  const progress = el("div", "cpush__progress");
  progress.dataset.progress = "true";
  progress.hidden = true;
  progress.innerHTML =
    '<div class="cpush__progress-head"><span data-progress-label>Transferring…</span>' +
    '<span data-progress-counts></span></div>' +
    '<div class="cpush__progress-track"><div class="cpush__progress-fill" data-progress-fill></div></div>';
  root.appendChild(progress);

  const body = el("div", "cpush__body");
  const before = el("div", "cpush__col cpush__col--before");
  before.appendChild(el("p", "cpush__coltitle", "Camera now"));
  slots.forEach((slot) => before.appendChild(slotRow(`C${slot.index}`, slot.name, slot.filmSimName)));
  body.appendChild(before);

  const arrow = el("div", "cpush__arrow");
  arrow.setAttribute("aria-hidden", "true");
  arrow.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="13 6 19 12 13 18"></polyline></svg>';
  body.appendChild(arrow);

  const after = el("div", "cpush__col cpush__col--after");
  const coltitle = el("p", "cpush__coltitle", "After transfer ");
  const hint = el("span", "cpush__hint", "drag to reorder");
  hint.dataset.reorderHint = "true";
  coltitle.appendChild(hint);
  after.appendChild(coltitle);

  const list = el("div", "cpush__list");
  list.dataset.transferList = "true";
  recipes.slice(0, written).forEach((recipe, i) => {
    const slot = slots[i];
    list.appendChild(assignmentRow(`C${i + 1}`, recipe, slot ? slot.name : ""));
  });
  slots.slice(written).forEach((slot) => list.appendChild(keptRow(`C${slot.index}`, slot.name)));
  after.appendChild(list);

  const dropped = recipes.slice(written);
  if (dropped.length) {
    const box = el("div", "cpush__dropped");
    box.appendChild(el("p", "cpush__dropped-title", "Won’t fit — not transferred"));
    dropped.forEach((recipe) => box.appendChild(droppedRow(recipe)));
    after.appendChild(box);
  }
  body.appendChild(after);
  root.appendChild(body);

  const footer = el("div", "cpush__footer");
  const hintText = el(
    "span",
    "cpush__foot-hint",
    `${written} recipe${written === 1 ? "" : "s"} will be written to slots, one at a time.`
  );
  footer.appendChild(hintText);
  const cancel = el("button", "cpush__cancel", "Cancel");
  cancel.type = "button";
  cancel.addEventListener("click", () => window.SlotOverlay.close());
  footer.appendChild(cancel);
  const start = el("button", "cpush__start", `Transfer ${written} recipe${written === 1 ? "" : "s"}`);
  start.type = "button";
  start.dataset.start = "true";
  if (written === 0) start.disabled = true;
  footer.appendChild(start);
  root.appendChild(footer);

  return root;
}

function describe(error) {
  if (error instanceof RecipeWriteError) {
    return `Some settings couldn't be saved (${error.failedProperties.join(", ")}). Please try again.`;
  }
  if (error instanceof RecipeValidationError) {
    return `A recipe can't be written to the camera: ${error.field} is not valid.`;
  }
  if (error instanceof CameraConnectionError) {
    console.error("Camera connection failed", error.message);
    return NO_CAMERA;
  }
  if (error instanceof CameraWriteError) {
    console.error("Camera refused a write", error.message);
    return REJECTED;
  }
  if (error && error.name === "NotFoundError") return null; // picker cancelled
  console.error("Unexpected error pushing a collection", error);
  return UNEXPECTED;
}

function browserWriter() {
  return async (row, _recipeId, _slotLabel, slotIndex) => {
    const config = await configPromise;
    const recipe = await fetchRecipePayload(row.dataset.payloadUrl);
    await withCamera(config, (device) =>
      pushRecipeToCamera(device, recipe, { slotIndex, runtime: runtimeFor(config) })
    );
  };
}

async function openBrowserModal(button) {
  const reason = unavailableReason();
  if (reason) {
    showMessage(reason);
    return;
  }
  let config;
  try {
    config = await configPromise;
  } catch (error) {
    console.error("Could not load the camera configuration", error);
    showMessage(UNEXPECTED);
    return;
  }

  const recipes = collectionRecipes();
  window.SlotOverlay.showSpinner();

  let cameraName = "Camera";
  let slots;
  try {
    slots = await withCamera(config, (device) => {
      if (grantedDevice && grantedDevice.productName) cameraName = grantedDevice.productName;
      return getCameraSlots(device, runtimeFor(config));
    });
  } catch (error) {
    const message = describe(error);
    if (message === null) {
      window.SlotOverlay.close();
      return;
    }
    showMessage(message);
    return;
  }

  const modal = buildModal({
    collectionName: button.dataset.collectionName || "Collection",
    cameraName,
    slots,
    recipes,
  });
  window.SlotOverlay.show(modal);
  wireDrag(modal);
  const start = modal.querySelector("[data-start]");
  if (start) {
    start.addEventListener("click", () => {
      if (start.dataset.done) {
        window.SlotOverlay.close();
        return;
      }
      runTransfer(modal, browserWriter());
    });
  }
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

function start() {
  const url = configUrl();
  const browserMode = Boolean(url);

  if (browserMode) {
    configPromise = loadClientConfig(url);
    if ("usb" in navigator) {
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
      const button = event.target.closest("[data-collection-push]");
      if (!button) return;
      event.preventDefault();
      openBrowserModal(button);
    });
    return;
  }

  // Server transport: the modal is swapped into #slot-overlay by HTMX.
  document.body.addEventListener("htmx:afterSwap", (e) => {
    if (e.detail.target && e.detail.target.id === "slot-overlay") {
      const modal = e.detail.target.querySelector("#collection-push[data-collection-id]");
      if (modal) initServerModal(modal);
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", start);
} else {
  start();
}
