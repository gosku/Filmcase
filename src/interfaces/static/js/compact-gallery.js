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
  var DEFAULT_ROW_HEIGHT_MOBILE = 200; // denser default on phones so rows show more than one image
  var MIN_ROW_HEIGHT = 120; // keep in sync with the size-slider min in gallery_actions.html
  var MAX_ROW_HEIGHT = 500; // keep in sync with the size-slider max in gallery_actions.html

  var container = document.getElementById('gallery-results');
  if (!container) return;

  // On a phone the gallery is always compact, with recipe-name labels shown
  // (there is no hover on touch). This is forced without persisting, so the
  // user's desktop grid/compact preference is left untouched.
  function isMobile() {
    return window.matchMedia('(max-width: 1024px) and (orientation: portrait), (max-width: 768px)').matches;
  }

  function readView() {
    if (isMobile()) return 'compact';
    return localStorage.getItem(VIEW_KEY) === 'compact' ? 'compact' : 'grid';
  }

  function readLabels() {
    var stored = localStorage.getItem(LABEL_KEY);
    if (stored === 'always') return 'always';
    if (stored === 'hover') return 'hover';
    return isMobile() ? 'always' : 'hover'; // default to always on mobile (no hover)
  }

  // Preferred row height (the target the justified rows are solved toward),
  // set by the size slider. Actual per-row heights come out at or below it so
  // each row fills the width exactly.
  function readRowHeight() {
    var stored = parseInt(localStorage.getItem(ROW_HEIGHT_KEY), 10);
    if (isNaN(stored)) return isMobile() ? DEFAULT_ROW_HEIGHT_MOBILE : DEFAULT_ROW_HEIGHT;
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
    // Fill 1px short of the container. A row whose widths sum to exactly the
    // container width can round just over the line width on high-DPR screens,
    // wrapping the last image onto its own line and leaving every multi-image
    // row half-empty on mobile. The 1px slack is imperceptible and prevents it.
    var fill = containerWidth - 1;
    var gaps = (cards.length - 1) * GAP;
    var used = 0;
    for (var i = 0; i < cards.length; i++) {
      var isLast = i === cards.length - 1;
      var w = isLast ? (fill - gaps - used) : Math.floor(ratios[i] * height);
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

  // `persist` is set only for explicit user choices from the header controls, so
  // the forced-compact-on-mobile default never overwrites the desktop preference.
  function applyView(mode, persist) {
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
    if (persist && !isMobile()) localStorage.setItem(VIEW_KEY, mode);
  }

  function applyLabels(mode, persist) {
    container.classList.remove('labels-hover', 'labels-always');
    container.classList.add('labels-' + mode);
    setActive(labelButtons, 'data-label-mode', mode);
    if (persist) localStorage.setItem(LABEL_KEY, mode);
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
      if (btn) applyView(btn.getAttribute('data-view-mode'), true);
    });
  }

  if (labelControl) {
    labelControl.addEventListener('click', function (evt) {
      var btn = evt.target.closest('[data-label-mode]');
      if (btn) applyLabels(btn.getAttribute('data-label-mode'), true);
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

  window.addEventListener('resize', function () {
    // Re-evaluate the forced-compact-on-mobile rule when crossing the breakpoint,
    // without persisting (readView/readLabels already fold in the mobile rule).
    var wantView = readView();
    if (!container.classList.contains('layout-' + wantView)) applyView(wantView);
    var wantLabels = readLabels();
    if (!container.classList.contains('labels-' + wantLabels)) applyLabels(wantLabels);
    scheduleJustify();
  });

  document.body.addEventListener('htmx:afterSwap', function () {
    if (container.classList.contains('layout-compact')) scheduleJustify();
  });

  // Apply the stored preferences. The inline script in gallery.html already set
  // the container classes to avoid a flash; this syncs the control states and
  // runs the initial justification.
  applyView(readView());
  applyLabels(readLabels());
}());
