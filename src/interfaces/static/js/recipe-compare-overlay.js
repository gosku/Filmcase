/**
 * Side-by-side image comparison overlay for two recipes.
 *
 * Expects the markup from recipes/_compare_overlay.html to be on the page.
 * Each side loads a low-resolution image first and swaps in the full-size one
 * once it has decoded, then preloads the neighbouring images so stepping
 * through the carousel is instant.
 *
 * Usage:
 *
 *   RecipeCompareOverlay.open({
 *     leftRecipeId: 3, leftTitle: "Provia base",
 *     rightRecipeId: 8, rightTitle: "Provia warm"
 *   });
 */
window.RecipeCompareOverlay = (function () {
  "use strict";

  var PREVIEW_WIDTH = 600;

  var overlay = null;
  var preloaded = null;
  var state = {
    left: {recipeId: null, prevId: null, nextId: null},
    right: {recipeId: null, prevId: null, nextId: null},
  };

  function element(side, suffix) {
    return document.getElementById("compare-" + side + "-" + suffix);
  }

  function preload(url) {
    if (!url || preloaded.has(url)) {
      return;
    }
    var image = new Image();
    image.onload = function () { preloaded.add(url); };
    image.src = url;
  }

  function loadImage(side, imageId) {
    var sideState = state[side];
    var imageEl = element(side, "img");
    var prevBtn = element(side, "prev");
    var nextBtn = element(side, "next");

    imageEl.src = "/images/file/" + imageId + "/?width=" + PREVIEW_WIDTH;
    imageEl.style.display = "";
    element(side, "area").querySelectorAll(".compare-empty").forEach(function (el) {
      el.remove();
    });

    fetch("/recipes/" + sideState.recipeId + "/images/" + imageId + "/")
      .then(function (response) { return response.json(); })
      .then(function (data) {
        sideState.prevId = data.prev_id;
        sideState.nextId = data.next_id;
        prevBtn.style.display = data.prev_id ? "" : "none";
        nextBtn.style.display = data.next_id ? "" : "none";

        var fullSrc = data.full_url;

        function showFullSize() {
          imageEl.src = fullSrc;
          if (data.prev_id) {
            preload("/images/file/" + data.prev_id + "/");
          }
          if (data.next_id) {
            preload("/images/file/" + data.next_id + "/");
          }
        }

        if (preloaded.has(fullSrc)) {
          showFullSize();
          return;
        }
        var full = new Image();
        full.onload = function () {
          preloaded.add(fullSrc);
          showFullSize();
        };
        full.src = fullSrc;
      });
  }

  function showEmpty(side) {
    var imageEl = element(side, "img");
    imageEl.src = "";
    imageEl.style.display = "none";
    element(side, "prev").style.display = "none";
    element(side, "next").style.display = "none";

    var empty = document.createElement("span");
    empty.className = "compare-empty";
    empty.textContent = "No images";
    element(side, "area").appendChild(empty);
  }

  function loadSide(side, recipeId) {
    fetch("/recipes/" + recipeId + "/images/")
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (data.images.length > 0) {
          loadImage(side, data.images[0].id);
        } else {
          showEmpty(side);
        }
      });
  }

  function close() {
    overlay.style.display = "none";
  }

  function isOpen() {
    return overlay.style.display === "flex";
  }

  function open(config) {
    state.left.recipeId = config.leftRecipeId;
    state.right.recipeId = config.rightRecipeId;

    element("left", "title").textContent = config.leftTitle || config.leftRecipeId;
    element("right", "title").textContent = config.rightTitle || config.rightRecipeId;

    preloaded.clear();
    overlay.style.display = "flex";

    loadSide("left", config.leftRecipeId);
    loadSide("right", config.rightRecipeId);
  }

  function step(side, direction) {
    var target = state[side][direction === "prev" ? "prevId" : "nextId"];
    if (target) {
      loadImage(side, target);
    }
  }

  function bind() {
    overlay = document.getElementById("compare-overlay");
    preloaded = new Set();

    document.getElementById("compare-close").onclick = close;

    ["left", "right"].forEach(function (side) {
      ["prev", "next"].forEach(function (direction) {
        element(side, direction).onclick = function () { step(side, direction); };
      });
    });

    document.addEventListener("keydown", function (event) {
      if (isOpen() && event.key === "Escape") {
        close();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }

  return {open: open, close: close};
})();
