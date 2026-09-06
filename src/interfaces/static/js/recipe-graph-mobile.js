/**
 * Mobile chrome for the two recipe-graph pages.
 *
 * Desktop shows the filter sidebar and the inspect panel side by side with the
 * canvas. On small screens (styled in recipe-graph.css) the sidebar becomes an
 * off-canvas drawer and the inspect panel becomes a bottom sheet. This wires the
 * triggers for both; it does not touch selection, which RecipeGraph owns.
 *
 *   RecipeGraphMobile.setup(graph.cy);
 *
 * All the elements it looks for only exist / are only visible in the mobile
 * layout, so the handlers are harmless no-ops on desktop.
 */
window.RecipeGraphMobile = (function () {
  "use strict";

  function setup(cy) {
    var sidebar = document.getElementById("graph-sidebar");
    var panel = document.querySelector(".graph-panel");
    var backdrop = document.querySelector(".graph-backdrop");
    var menuBtn = document.querySelector(".graph-menu-btn");
    var sidebarClose = sidebar ? sidebar.querySelector(".sidebar__close") : null;
    var sheetClose = panel ? panel.querySelector(".graph-sheet__close") : null;
    var sidebarBody = document.getElementById("graph-sidebar-body");
    var compareOverlay = document.getElementById("compare-overlay");

    function openDrawer() {
      if (sidebar) { sidebar.classList.add("sidebar--open"); }
      if (backdrop) { backdrop.hidden = false; }
    }

    function closeDrawer() {
      if (sidebar) { sidebar.classList.remove("sidebar--open"); }
      if (backdrop) { backdrop.hidden = true; }
    }

    function openSheet() {
      if (panel) { panel.classList.add("graph-panel--sheet-open"); }
    }

    function closeSheet() {
      if (panel) { panel.classList.remove("graph-panel--sheet-open"); }
    }

    if (menuBtn) { menuBtn.addEventListener("click", openDrawer); }
    if (sidebarClose) { sidebarClose.addEventListener("click", closeDrawer); }
    if (sheetClose) { sheetClose.addEventListener("click", closeSheet); }
    if (backdrop) { backdrop.addEventListener("click", closeDrawer); }

    // Picking a recipe from the drawer list also moves the UI along: close the
    // drawer and reveal the inspect sheet. RecipeGraph handles the selection
    // itself off the same click; this only follows it.
    if (sidebarBody) {
      sidebarBody.addEventListener("click", function (event) {
        if (event.target.closest(".graph-recipe-list__row")) {
          closeDrawer();
          openSheet();
        }
      });
    }

    // `tap` is Cytoscape's unified mouse+touch event: on a node it opens the
    // inspect sheet, on empty canvas it dismisses it.
    if (cy) {
      cy.on("tap", "node", function () { openSheet(); });
      cy.on("tap", function (event) {
        if (event.target === cy) { closeSheet(); }
      });
    }

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") { return; }
      // The compare overlay sits on top and owns Escape while it is open.
      if (compareOverlay && getComputedStyle(compareOverlay).display !== "none") {
        return;
      }
      if (panel && panel.classList.contains("graph-panel--sheet-open")) {
        closeSheet();
        return;
      }
      if (sidebar && sidebar.classList.contains("sidebar--open")) {
        closeDrawer();
      }
    });
  }

  return { setup: setup };
})();
