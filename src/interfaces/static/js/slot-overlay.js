/**
 * The "Send to camera" slot overlay.
 *
 * Expects a `<div id="slot-overlay" hidden>` on the page. HTMX swaps the slot
 * picker (`recipes/_select_slot_partial.html`) into it, and the push result
 * (`recipes/_push_result_partial.html`) into the `#slot-card` inside it.
 *
 * This module owns the overlay itself: showing a spinner while a request is in
 * flight, revealing the overlay once content arrives, and closing it on a
 * backdrop click. It does not own the Escape key, because each host page
 * decides which of its several overlays Escape should close first; those pages
 * call `SlotOverlay.isOpen()` and `SlotOverlay.close()` from their own handler.
 *
 * `closeSlotOverlay` is also exposed as a global because the close buttons in
 * both partials call it from an inline `onclick`.
 */
window.SlotOverlay = (function () {
  "use strict";

  var SPINNER_HTML =
    '<div class="slot-card slot-card--loading"><div class="slot-spinner"></div></div>';
  var PUSH_LOADING_HTML =
    '<div class="slot-push-loading"><div class="slot-spinner-large"></div></div>';

  function element() {
    return document.getElementById("slot-overlay");
  }

  function close() {
    var overlay = element();
    if (overlay) overlay.hidden = true;
  }

  function isOpen() {
    var overlay = element();
    return Boolean(overlay) && !overlay.hidden;
  }

  function bind() {
    // Showing the spinner on beforeRequest rather than afterSwap matters: the
    // camera can take a couple of seconds to answer, and without it the click
    // looks like it did nothing.
    document.body.addEventListener("htmx:beforeRequest", function (e) {
      if (e.detail.target && e.detail.target.id === "slot-overlay") {
        var overlay = element();
        overlay.innerHTML = SPINNER_HTML;
        overlay.hidden = false;
      }
      if (e.detail.target && e.detail.target.id === "slot-card") {
        e.detail.target.innerHTML = PUSH_LOADING_HTML;
      }
    });

    document.body.addEventListener("htmx:afterSwap", function (e) {
      if (e.detail.target.id === "slot-overlay") {
        e.detail.target.hidden = false;
      }
    });

    var overlay = element();
    if (overlay) {
      overlay.addEventListener("click", function (e) {
        if (e.target === this) close();
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }

  return {close: close, isOpen: isOpen};
})();

window.closeSlotOverlay = window.SlotOverlay.close;
