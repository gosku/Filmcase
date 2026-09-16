/*
 * Gallery date timeline ("go to date X").
 *
 * Renders the right-edge rail from the monthly distribution embedded in
 * #timeline-data, applying the granularity rule client-side (latest 2 years by
 * month, the 5 years before by year, older in 3-year steps). Clicking a mark —
 * or the rail between two marks, which interpolates proportionally — travels the
 * gallery to that month via the gallery-results endpoint. It is navigation, not
 * a filter: the response reseeds two-way keyset scrolling around the landing.
 */
(function () {
  "use strict";

  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  // Top-to-top spacing per band (recent months get the most room). Mobile marks
  // are bigger touch targets, so they need more space between them.
  var GAP_DESKTOP = { month: 30, year: 26, multi: 22 };
  var GAP_MOBILE = { month: 58, year: 52, multi: 48 };

  function isMobile() {
    return window.matchMedia("(max-width: 1024px) and (orientation: portrait), (max-width: 768px)").matches;
  }

  // Marks are centred on their y (translateY(-50%)), so the top and bottom need
  // at least half a mark's height of padding or the first/last mark is clipped
  // at the rail edge. Mobile marks are bigger.
  function topPad() { return isMobile() ? 32 : 16; }

  var lastSignature = null;
  var lastData = null;       // last distribution, for re-focusing on a jump
  var allMarks = [];         // full set from the granularity rule
  var marks = [];            // {monthIndex, label, kind, y} — the displayed subset
  var currentMonthIndex = null;

  function scroller() { return document.querySelector(".gallery-scroll"); }
  function rail() { return document.getElementById("timeline-rail"); }

  function monthIndex(year, month) { return year * 12 + (month - 1); }
  function yearOf(idx) { return Math.floor(idx / 12); }
  function monthOf(idx) { return (idx % 12) + 1; }

  function readData() {
    var el = document.getElementById("timeline-data");
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  // The focused month: the server's "YYYY-MM" focus, or the newest month.
  function focusToIndex(data) {
    if (data.focus) {
      var p = data.focus.split("-");
      return monthIndex(parseInt(p[0], 10), parseInt(p[1], 10));
    }
    return monthIndex(data.today.year, data.today.month);
  }

  // Build the ordered marks (newest first): every year in the library as a
  // single mark, EXCEPT the selected (focused) year, which is expanded into its
  // months. Only one year is ever expanded. If the result overflows the rail,
  // layout() lets it scroll rather than dropping marks.
  function buildMarks(data, focusIdx) {
    var ty = data.today.year;
    var tm = data.today.month;
    var todayIdx = monthIndex(ty, tm);
    var oldestIdx = todayIdx;
    var yearsSet = {};
    (data.months || []).forEach(function (m) {
      var i = monthIndex(m.year, m.month);
      if (i < oldestIdx) oldestIdx = i;
      yearsSet[m.year] = true;
    });
    yearsSet[ty] = true; // the current year is always listed, even before it has photos
    var expandYear = yearOf(focusIdx != null ? focusIdx : todayIdx);
    yearsSet[expandYear] = true; // the selected year is always listed

    function clampYearMark(year) {
      var idx = year === ty ? todayIdx : monthIndex(year, 12);
      return Math.max(oldestIdx, Math.min(todayIdx, idx));
    }

    var out = [];
    Object.keys(yearsSet).map(Number).sort(function (a, b) { return b - a; }).forEach(function (year) {
      if (year !== expandYear) {
        out.push({ monthIndex: clampYearMark(year), kind: "year", expanded: false, label: String(year) });
        return;
      }
      var pushed = 0;
      for (var mo = year === ty ? tm : 12; mo >= 1; mo--) {
        var idx = monthIndex(year, mo);
        if (idx > todayIdx || idx < oldestIdx) continue;
        out.push({ monthIndex: idx, kind: "month", expanded: true, label: monthLabel(year, mo) });
        pushed++;
      }
      if (!pushed) out.push({ monthIndex: clampYearMark(year), kind: "year", expanded: false, label: String(year) });
    });

    out.sort(function (a, b) { return b.monthIndex - a.monthIndex; });
    return out;
  }

  function monthLabel(year, month) {
    return month === 1 ? MONTHS[0] + " '" + String(year).slice(2) : MONTHS[month - 1];
  }

  // Position the marks and return the content height. When the marks fit, they
  // spread to fill the rail; when they do not, they keep their natural spacing
  // and the mount scrolls (see render()) — the list is never thinned.
  function layout(available) {
    var gap = isMobile() ? GAP_MOBILE : GAP_DESKTOP;
    var pad = topPad();
    var y = pad;
    for (var i = 0; i < marks.length; i++) {
      marks[i].y = y;
      if (i < marks.length - 1) y += gap[marks[i].kind];
    }
    var lastY = marks.length ? marks[marks.length - 1].y : pad;
    var natural = lastY + pad;
    if (natural <= available && marks.length > 1) {
      var factor = (available - 2 * pad) / (lastY - pad);
      for (var j = 0; j < marks.length; j++) marks[j].y = pad + (marks[j].y - pad) * factor;
      return available;
    }
    return natural;
  }

  function render() {
    var railEl = rail();
    if (!railEl) return;
    var mount = railEl.querySelector(".timeline-rail__mount");
    if (!mount) return;
    marks = allMarks.slice();
    var available = mount.clientHeight;
    if (available <= 0) available = 600;
    var contentHeight = layout(available);

    mount.innerHTML = "";
    // A spacer gives the (absolutely-positioned) marks a scroll height so the
    // mount can scroll when the list is taller than the rail.
    var spacer = document.createElement("div");
    spacer.className = "timeline-rail__spacer";
    spacer.style.height = contentHeight + "px";
    mount.appendChild(spacer);
    renderFocusZone(mount);
    marks.forEach(function (mark) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "timeline-mark timeline-mark--" + mark.kind;
      if (mark.monthIndex === currentMonthIndex) btn.className += " timeline-mark--current";
      btn.style.top = mark.y + "px";
      btn.dataset.monthIndex = String(mark.monthIndex);
      btn.innerHTML =
        '<span class="timeline-mark__tick"></span>' +
        '<span class="timeline-mark__pill">' + mark.label + "</span>";
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        jumpTo(mark.monthIndex);
      });
      mount.appendChild(btn);
    });
    if (contentHeight > available) scrollCurrentIntoView(mount, available, contentHeight);
  }

  // Keep the selected mark visible (centred) when the rail is taller than the
  // viewport and therefore scrolls.
  function scrollCurrentIntoView(mount, available, contentHeight) {
    var best = null;
    var bestDist = Infinity;
    for (var i = 0; i < marks.length; i++) {
      var d = Math.abs(marks[i].monthIndex - currentMonthIndex);
      if (d < bestDist) { bestDist = d; best = marks[i]; }
    }
    if (!best) return;
    var target = best.y - available / 2;
    mount.scrollTop = Math.max(0, Math.min(contentHeight - available, target));
  }

  // Draw the highlighted band behind an expanded year, with a vertical label.
  function renderFocusZone(mount) {
    var expanded = marks.filter(function (m) { return m.expanded; });
    if (!expanded.length) return;
    var top = Infinity;
    var bottom = -Infinity;
    for (var i = 0; i < expanded.length; i++) {
      top = Math.min(top, expanded[i].y);
      bottom = Math.max(bottom, expanded[i].y);
    }
    var zone = document.createElement("div");
    zone.className = "timeline-focus-zone";
    zone.style.top = (top - 14) + "px";
    zone.style.height = (bottom - top + 28) + "px";
    mount.appendChild(zone);

    var tag = document.createElement("div");
    tag.className = "timeline-focus-tag";
    tag.style.top = ((top + bottom) / 2) + "px";
    tag.textContent = yearOf(expanded[0].monthIndex) + " · expanded";
    mount.appendChild(tag);
  }

  // Map a pointer y (within the mount) to a month index, interpolating linearly
  // in time between the two bracketing marks so the rail reads as continuous.
  function monthIndexAt(offsetY) {
    if (!marks.length) return null;
    if (offsetY <= marks[0].y) return marks[0].monthIndex;
    var last = marks[marks.length - 1];
    if (offsetY >= last.y) return last.monthIndex;
    for (var i = 0; i < marks.length - 1; i++) {
      var a = marks[i], b = marks[i + 1];
      if (offsetY >= a.y && offsetY <= b.y) {
        var f = (offsetY - a.y) / (b.y - a.y || 1);
        return Math.round(a.monthIndex + (b.monthIndex - a.monthIndex) * f);
      }
    }
    return last.monthIndex;
  }

  function toYearMonth(idx) {
    return yearOf(idx) + "-" + String(monthOf(idx)).padStart(2, "0");
  }

  // Scroll so the first (newest) card of the landing sits at the top of the
  // viewport, with the newer sentinel's spacer just above it.
  function pinLandingTop() {
    var s = scroller();
    var first = document.querySelector("#gallery-results .image-card");
    if (s && first) s.scrollTop += first.getBoundingClientRect().top - s.getBoundingClientRect().top;
  }

  function jumpTo(idx) {
    var railEl = rail();
    var form = document.getElementById("filter-form");
    if (!railEl || !window.htmx) return;
    var url = railEl.dataset.resultsUrl;
    var values = {};
    if (form) {
      var fd = new FormData(form);
      fd.forEach(function (v, k) {
        if (Object.prototype.hasOwnProperty.call(values, k)) {
          values[k] = [].concat(values[k], v);
        } else {
          values[k] = v;
        }
      });
    }
    var ym = toYearMonth(idx);
    values.to_date = ym;
    currentMonthIndex = idx;
    // Carry the date with the filters so a later filter change keeps it, and
    // reflect it in the URL (a new history entry per jump, deep-linkable).
    var input = document.getElementById("to-date-input");
    if (input) input.value = ym;
    writeGalleryUrl(false); // a jump is a deliberate navigation → new history entry
    // Re-focus the rail on the target: a collapsed year expands to its months.
    if (lastData) {
      allMarks = buildMarks(lastData, currentMonthIndex);
      render();
    }
    // Positioning happens in the htmx:afterSettle handler, once the grid and the
    // out-of-band sentinels have been swapped in.
    jumpArmed = true;
    window.htmx.ajax("GET", url, { target: "#gallery-results", swap: "innerHTML", values: values });
  }

  // Write the current filter-form state (filters + rating_first + to_date) into
  // the URL so a refresh or shared link restores the same view. Empty fields are
  // dropped to keep the URL tidy. `replace` swaps the current entry (used while
  // scrolling, so browsing does not flood history); a jump pushes a new one.
  function writeGalleryUrl(replace) {
    var form = document.getElementById("filter-form");
    if (!form) return;
    var clean = new URLSearchParams();
    new URLSearchParams(new FormData(form)).forEach(function (v, k) {
      if (v !== "") clean.append(k, v);
    });
    var qs = clean.toString();
    var url = window.location.pathname + (qs ? "?" + qs : "");
    if (replace) history.replaceState({}, "", url);
    else history.pushState({}, "", url);
  }

  // ── Keep the timeline + URL synced to the scrolled-to month ──────────
  var syncedMonth = null;

  // The month of the topmost card currently in view (its data-month), or null.
  // In rating-first mode the timeline navigates only the date-ordered (unrated)
  // region, so while the top of the view is in the leading rated block we return
  // null and the timeline holds still.
  function topVisibleMonth() {
    var s = scroller();
    if (!s) return null;
    var ratingFirst = (document.getElementById("rating-first-input") || {}).value === "1";
    var top = s.getBoundingClientRect().top;
    var cards = document.querySelectorAll("#gallery-results .image-card");
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      if (card.getBoundingClientRect().bottom > top + 4) {
        if (ratingFirst && Number(card.getAttribute("data-rating") || 0) > 0) return null;
        return card.getAttribute("data-month") || null;
      }
    }
    return null;
  }

  // Move the current-mark highlight to the mark nearest a month index.
  function highlightNearest(idx) {
    var mount = rail() && rail().querySelector(".timeline-rail__mount");
    if (!mount) return;
    var best = null;
    var bestDist = Infinity;
    mount.querySelectorAll(".timeline-mark").forEach(function (el) {
      var d = Math.abs(Number(el.dataset.monthIndex) - idx);
      if (d < bestDist) { bestDist = d; best = el; }
    });
    mount.querySelectorAll(".timeline-mark--current").forEach(function (el) {
      el.classList.remove("timeline-mark--current");
    });
    if (best) best.classList.add("timeline-mark--current");
  }

  function syncToScroll() {
    var month = topVisibleMonth();
    if (!month || month === syncedMonth) return;
    syncedMonth = month;
    var parts = month.split("-");
    var newIdx = monthIndex(parseInt(parts[0], 10), parseInt(parts[1], 10));
    var yearChanged = currentMonthIndex == null || yearOf(newIdx) !== yearOf(currentMonthIndex);
    currentMonthIndex = newIdx;
    if (yearChanged && lastData) {
      // Crossed a year boundary: close the old year, expand the new one.
      allMarks = buildMarks(lastData, currentMonthIndex);
      render(); // marks + centres the current month
    } else {
      highlightNearest(currentMonthIndex);
    }
    var input = document.getElementById("to-date-input");
    if (input) input.value = month;
    writeGalleryUrl(true); // replace, not push, so scrolling does not spam history
  }

  var syncTimer = null;
  function bindScrollSync() {
    var s = scroller();
    if (!s) return;
    s.addEventListener("scroll", function () {
      clearTimeout(syncTimer);
      syncTimer = setTimeout(syncToScroll, 120);
    }, { passive: true });
  }

  // ── Bubble tracking + click on empty rail space ──────────────────────
  function bindPointer() {
    var railEl = rail();
    if (!railEl || railEl.dataset.pointerBound) return;
    railEl.dataset.pointerBound = "1";
    var bubble = railEl.querySelector(".timeline-bubble");
    var mount = railEl.querySelector(".timeline-rail__mount");

    // Mark positions are in the mount's scrolled content space, so add scrollTop.
    function pointerToMonth(ev) {
      var rect = mount.getBoundingClientRect();
      return monthIndexAt(ev.clientY - rect.top + mount.scrollTop);
    }
    railEl.addEventListener("pointermove", function (ev) {
      if (!mount) return;
      var idx = pointerToMonth(ev);
      if (idx === null || !bubble) return;
      bubble.textContent = MONTHS[monthOf(idx) - 1] + " " + yearOf(idx);
      bubble.style.top = ev.clientY - railEl.getBoundingClientRect().top + "px";
      bubble.hidden = false;
    });
    railEl.addEventListener("pointerleave", function () {
      if (bubble) bubble.hidden = true;
    });
    // Clicking the rail background (not a mark) jumps to the interpolated month.
    railEl.addEventListener("click", function (ev) {
      if (ev.target.closest(".timeline-mark") || !mount) return;
      var idx = pointerToMonth(ev);
      if (idx !== null) jumpTo(idx);
    });
  }

  // ── Reveal: hover-summoned (desktop) / toggle button (mobile) ────────
  // Desktop summons the rail on pointer-near-the-right-edge and hides it again.
  // Mobile does NOT auto-reveal on scroll (too intrusive while browsing): the
  // rail is shown only when the user turns it on with the Dates toggle.
  var hideTimer = null;
  var railOpen = false; // mobile toggle state

  function show() {
    var r = rail();
    if (r) r.classList.add("timeline-rail--visible");
  }
  function hideSoon(delay) {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(function () {
      var r = rail();
      if (r) r.classList.remove("timeline-rail--visible");
    }, delay);
  }

  function bindReveal() {
    var main = document.querySelector(".main");
    if (main && window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
      main.addEventListener("mousemove", function (ev) {
        var rect = main.getBoundingClientRect();
        if (ev.clientX >= rect.right - 90) show();
        else if (ev.clientX < rect.right - 150) hideSoon(200);
      });
      main.addEventListener("mouseleave", function () { hideSoon(200); });
    }
    bindTimelineToggle();
  }

  function setTimelineOpen(open) {
    railOpen = open;
    var r = rail();
    var btn = document.getElementById("toggle-timeline-btn");
    if (r) r.classList.toggle("timeline-rail--visible", open);
    if (btn) {
      btn.classList.toggle("mobile-timeline-btn--active", open);
      btn.setAttribute("aria-pressed", open ? "true" : "false");
    }
    try { localStorage.setItem("galleryTimelineOpen", open ? "1" : "0"); } catch (e) { /* ignore */ }
    if (open) render(); // lay the marks out for the current height
  }

  function bindTimelineToggle() {
    var btn = document.getElementById("toggle-timeline-btn");
    if (!btn) return;
    btn.addEventListener("click", function () { setTimelineOpen(!railOpen); });
    // Restore the last choice on mobile only (desktop uses hover, not the toggle).
    if (isMobile()) {
      var open = false;
      try { open = localStorage.getItem("galleryTimelineOpen") === "1"; } catch (e) { /* ignore */ }
      if (open) setTimelineOpen(true);
    }
  }

  // ── Scroll anchoring when newer pages prepend ────────────────────────
  // Prepending above the viewport shifts everything down; capture the scroll
  // metrics before the swap and restore the offset after so the view stays put.
  var pendingAnchor = null;
  var jumpArmed = false;
  var loadingNewer = false;
  var NEWER_TRIGGER_PX = 220;

  // The newer (top) sentinel is partly visible at a jump landing, so an
  // IntersectionObserver would not re-fire on scroll-up. Drive it deterministically:
  // when the user scrolls UP within NEWER_TRIGGER_PX of the top, fire its load.
  function bindNewerScroll() {
    var s = scroller();
    if (!s) return;
    var lastTop = s.scrollTop;
    s.addEventListener("scroll", function () {
      var top = s.scrollTop;
      var goingUp = top < lastTop;
      lastTop = top;
      if (!goingUp || top > NEWER_TRIGGER_PX || loadingNewer) return;
      var el = document.querySelector("#load-newer-sentinel .infinite-scroll-sentinel");
      if (el && window.htmx) window.htmx.trigger(el, "loadnewer");
    }, { passive: true });
  }

  function bindAnchoring() {
    document.body.addEventListener("htmx:beforeRequest", function (evt) {
      var elt = evt.detail && evt.detail.elt;
      if (!elt) return;
      if (elt.classList && elt.classList.contains("sentinel-newer")) {
        loadingNewer = true;
        var s = scroller();
        pendingAnchor = s ? { height: s.scrollHeight, top: s.scrollTop } : null;
      } else if (elt.id === "filter-form") {
        // A filter change that keeps a date should land at the date, not the top.
        var input = document.getElementById("to-date-input");
        if (input && input.value) jumpArmed = true;
      }
    });
    document.body.addEventListener("htmx:afterSettle", function () {
      // A jump just settled: align the landing month to the top of the viewport.
      // Done synchronously (not via rAF, which is paused while the tab is hidden);
      // getBoundingClientRect forces the layout we need.
      if (jumpArmed) {
        jumpArmed = false;
        pinLandingTop();
        return;
      }
      if (!pendingAnchor) return;
      var s = scroller();
      if (s) s.scrollTop = pendingAnchor.top + (s.scrollHeight - pendingAnchor.height);
      pendingAnchor = null;
      loadingNewer = false;
    });
  }

  // ── Init / rebuild ───────────────────────────────────────────────────
  function init() {
    var data = readData();
    if (!data || !rail()) return;
    var signature = JSON.stringify(data);
    if (signature === lastSignature) return;  // unchanged (e.g. a scroll settle)
    lastSignature = signature;
    lastData = data;
    // The server tells us the focus: a "YYYY-MM" when the URL carries a date
    // (deep link, or a filter change that kept the date), else the newest month.
    currentMonthIndex = focusToIndex(data);
    syncedMonth = null; // a fresh/filtered gallery: let the next scroll re-sync
    allMarks = buildMarks(data, currentMonthIndex);
    render();
    bindPointer();
  }

  var resizeTimer = null;
  function relayoutOnResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { if (allMarks.length) render(); }, 150);
  }

  document.addEventListener("DOMContentLoaded", function () {
    init();
    bindReveal();
    bindAnchoring();
    bindNewerScroll();
    bindScrollSync();
    // Deep link with a date: the grid is already server-rendered at it, so pin
    // the landing to the top (the newer sentinel spacer sits above).
    if (lastData && lastData.focus) pinLandingTop();
  });
  // Re-fill the rail when the viewport changes size or the tab becomes visible
  // (its height may have been unknown — zero — when the rail first laid out).
  window.addEventListener("resize", relayoutOnResize);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && allMarks.length) render();
  });
  // Rebuild after a filter change replaces #timeline-rail out-of-band.
  document.body.addEventListener("htmx:afterSettle", function () { init(); });
  // Rebuild after a filter change replaces #timeline-rail out-of-band.
  document.body.addEventListener("htmx:afterSettle", function () { init(); });
})();
