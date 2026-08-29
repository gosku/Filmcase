// Compact ("justified") gallery layout for the Images page.
//
// Adds a second, opt-in layout to the gallery alongside the default 3-column
// grid. In compact mode, thumbnails are packed into rows that are each scaled
// to a single height and fill the full content width — so mixed aspect ratios
// tile edge-to-edge with no cropping (Google-Photos style). Aspect ratios are
// measured from the loaded thumbnails; nothing is stored server-side.
//
// The view mode (grid|compact) and label mode (hover|always) are persisted in
// localStorage and applied client-side with no page reload. The same
// `.image-card` DOM is used in both modes, so multi-select, the detail overlay
// and rating keep working unchanged.

(function () {
  var VIEW_KEY = 'galleryViewMode';
  var LABEL_KEY = 'galleryLabelMode';
  var ROW_HEIGHT_KEY = 'galleryRowHeight';
  var GAP = 4; // must match `#gallery-results.layout-compact { gap }` in gallery.html
  var FALLBACK_RATIO = 1.5; // used until a thumbnail has loaded and can be measured
  var DEFAULT_ROW_HEIGHT = 280; // near the grid layout's fixed 300px, so switching feels size-consistent
  var MIN_ROW_HEIGHT = 120; // keep in sync with the size-slider min in gallery_actions.html
  var MAX_ROW_HEIGHT = 500; // keep in sync with the size-slider max in gallery_actions.html

  var container = document.getElementById('gallery-results');
  if (!container) return;

  function readView() {
    return localStorage.getItem(VIEW_KEY) === 'compact' ? 'compact' : 'grid';
  }

  function readLabels() {
    return localStorage.getItem(LABEL_KEY) === 'always' ? 'always' : 'hover';
  }

  // Preferred row height (the target the justified rows are solved toward),
  // set by the size slider. Actual per-row heights come out at or below it so
  // each row fills the width exactly.
  function readRowHeight() {
    var stored = parseInt(localStorage.getItem(ROW_HEIGHT_KEY), 10);
    if (isNaN(stored)) return DEFAULT_ROW_HEIGHT;
    return Math.max(MIN_ROW_HEIGHT, Math.min(MAX_ROW_HEIGHT, stored));
  }

  // ── Layout engine ──────────────────────────────────────────────────────

  function ratioOf(card) {
    var img = card.querySelector('.image-thumbnail');
    if (img && img.naturalWidth > 0 && img.naturalHeight > 0) {
      return img.naturalWidth / img.naturalHeight;
    }
    return FALLBACK_RATIO;
  }

  // Assign each row's cards an integer width/height so the row fills the
  // container exactly. Any rounding remainder is absorbed by the last card, so
  // the row sum plus its gaps equals the container width and the next card
  // wraps where intended.
  function sizeRow(cards, ratios, height, containerWidth) {
    var gaps = (cards.length - 1) * GAP;
    var used = 0;
    for (var i = 0; i < cards.length; i++) {
      var isLast = i === cards.length - 1;
      var w = isLast ? (containerWidth - gaps - used) : Math.floor(ratios[i] * height);
      used += w;
      cards[i].style.width = w + 'px';
      cards[i].style.height = Math.round(height) + 'px';
    }
  }

  function justify() {
    if (!container.classList.contains('layout-compact')) return;
    var containerWidth = container.clientWidth;
    if (containerWidth <= 0) return;

    var cards = Array.prototype.slice.call(container.querySelectorAll('.image-card'));
    if (cards.length === 0) return;

    var target = readRowHeight();
    var rowCards = [];
    var rowRatios = [];
    var ratioSum = 0;

    for (var i = 0; i < cards.length; i++) {
      var ratio = ratioOf(cards[i]);
      rowCards.push(cards[i]);
      rowRatios.push(ratio);
      ratioSum += ratio;

      var gaps = (rowCards.length - 1) * GAP;
      if (ratioSum * target + gaps >= containerWidth) {
        var height = (containerWidth - gaps) / ratioSum;
        sizeRow(rowCards, rowRatios, height, containerWidth);
        rowCards = [];
        rowRatios = [];
        ratioSum = 0;
      }
    }

    // Trailing partial row: keep the target height (left-aligned), unless it is
    // wide enough to warrant scaling down to fit.
    if (rowCards.length > 0) {
      var lastGaps = (rowCards.length - 1) * GAP;
      var natural = ratioSum * target + lastGaps;
      var h = natural > containerWidth ? (containerWidth - lastGaps) / ratioSum : target;
      sizeRow(rowCards, rowRatios, h, containerWidth);
    }
  }

  function clearSizes() {
    var cards = container.querySelectorAll('.image-card');
    for (var i = 0; i < cards.length; i++) {
      cards[i].style.width = '';
      cards[i].style.height = '';
    }
  }

  // Coalesce re-layout requests into one per animation frame.
  var scheduled = false;
  function scheduleJustify() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(function () {
      scheduled = false;
      justify();
    });
  }

  // ── View / label mode ──────────────────────────────────────────────────

  function setActive(buttons, attr, value) {
    for (var i = 0; i < buttons.length; i++) {
      var isActive = buttons[i].getAttribute(attr) === value;
      buttons[i].classList.toggle('segmented-toggle__option--active', isActive);
    }
  }

  function applyView(mode) {
    container.classList.remove('layout-grid', 'layout-compact');
    container.classList.add('layout-' + mode);
    setActive(viewButtons, 'data-view-mode', mode);
    if (labelControl) labelControl.hidden = mode !== 'compact';
    if (sizeControl) sizeControl.hidden = mode !== 'compact';
    if (mode === 'compact') {
      justify(); // immediate; load/resize/swap refine it via scheduleJustify
    } else {
      clearSizes();
    }
    localStorage.setItem(VIEW_KEY, mode);
  }

  function applyLabels(mode) {
    container.classList.remove('labels-hover', 'labels-always');
    container.classList.add('labels-' + mode);
    setActive(labelButtons, 'data-label-mode', mode);
    localStorage.setItem(LABEL_KEY, mode);
  }

  // ── Wiring ─────────────────────────────────────────────────────────────

  var viewSwitcher = document.getElementById('view-switcher');
  var labelControl = document.getElementById('label-mode');
  var sizeControl = document.getElementById('size-control');
  var sizeSlider = document.getElementById('size-slider');
  var viewButtons = viewSwitcher ? viewSwitcher.querySelectorAll('[data-view-mode]') : [];
  var labelButtons = labelControl ? labelControl.querySelectorAll('[data-label-mode]') : [];

  if (viewSwitcher) {
    viewSwitcher.addEventListener('click', function (evt) {
      var btn = evt.target.closest('[data-view-mode]');
      if (btn) applyView(btn.getAttribute('data-view-mode'));
    });
  }

  if (labelControl) {
    labelControl.addEventListener('click', function (evt) {
      var btn = evt.target.closest('[data-label-mode]');
      if (btn) applyLabels(btn.getAttribute('data-label-mode'));
    });
  }

  if (sizeSlider) {
    sizeSlider.value = readRowHeight();
    sizeSlider.addEventListener('input', function () {
      localStorage.setItem(ROW_HEIGHT_KEY, sizeSlider.value);
      scheduleJustify();
    });
  }

  // Re-justify as thumbnails finish loading (load does not bubble — capture it),
  // on resize, and after HTMX swaps replace or append cards.
  container.addEventListener('load', function (evt) {
    if (evt.target && evt.target.classList.contains('image-thumbnail')) scheduleJustify();
  }, true);

  window.addEventListener('resize', scheduleJustify);

  document.body.addEventListener('htmx:afterSwap', function () {
    if (container.classList.contains('layout-compact')) scheduleJustify();
  });

  // Apply the stored preferences. The inline script in gallery.html already set
  // the container classes to avoid a flash; this syncs the control states and
  // runs the initial justification.
  applyView(readView());
  applyLabels(readLabels());
}());
