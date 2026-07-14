// Inject shared toolbar styles once so they're available in any template that
// includes this script, without duplicating CSS across templates.
(function () {
  if (document.getElementById('ms-controller-styles')) return;
  var s = document.createElement('style');
  s.id = 'ms-controller-styles';
  s.textContent = `
    .ms-toolbar { display: flex; align-items: center; gap: .5rem; }
    .ms-toolbar[hidden] { display: none; }
    .ms-count { font-size: .85rem; font-weight: 600; color: #444; min-width: 5rem; }
    .ms-cancel-btn { padding: .4rem .85rem; background: none; border: 1px solid #ccc; border-radius: 5px; font-size: .85rem; font-weight: 600; color: #555; cursor: pointer; }
    .ms-cancel-btn:hover { background: #f0f0f0; color: #333; }
    .ms-actions-wrap { position: relative; }
    .ms-actions-btn { display: inline-flex; align-items: center; gap: .35rem; padding: .4rem .85rem; background: var(--color-accent); color: #fff; border: none; border-radius: 5px; font-size: .85rem; font-weight: 600; cursor: pointer; white-space: nowrap; }
    .ms-actions-btn:hover { background: var(--color-accent-dark); }
    .ms-actions-dropdown { position: absolute; top: calc(100% + 6px); left: 0; min-width: 180px; background: #fff; border: 1px solid #ddd; border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,.12); z-index: 100; overflow: hidden; }
    .ms-actions-dropdown[hidden] { display: none; }
    .ms-actions-empty { display: block; padding: .65rem 1rem; font-size: .875rem; color: #aaa; font-style: italic; }
  `;
  document.head.appendChild(s);
}());

class MultiSelectController {
  constructor({ containerSelector, cardSelector, pkAttr = 'data-pk', toolbarSelector = null, onSelectionChange = null }) {
    this._containerSelector = containerSelector;
    this._toolbarSelector = toolbarSelector;
    this.cardSelector = cardSelector;
    this.pkAttr = pkAttr;
    this.onSelectionChange = onSelectionChange;
    this.selectedPks = new Set();
    this.active = false;
    // Card the next shift-click extends a range from.
    this.anchorPk = null;

    if (!document.querySelector(containerSelector)) return;
    this._init();
  }

  _init() {
    // Capture phase at document.body: survives HTMX history restorations that
    // replace the container element with a fresh DOM node.
    document.body.addEventListener('click', (evt) => {
      const container = document.querySelector(this._containerSelector);
      if (!container) return;

      const card = evt.target.closest(this.cardSelector);
      if (!card || !container.contains(card)) return;

      const pk = card.getAttribute(this.pkAttr);
      if (!pk) return;

      const onCheckbox = !!evt.target.closest('.ms-checkbox');

      if (onCheckbox || this.active) {
        // stopPropagation: prevents HTMX listeners on child elements (e.g. <a hx-get>).
        // preventDefault: prevents browser native anchor navigation.
        evt.stopPropagation();
        evt.preventDefault();
        if (evt.shiftKey && this.anchorPk !== null && this.anchorPk !== pk) {
          this._selectRange(pk, container);
        } else {
          this._toggle(pk, card, container);
        }
      }
    }, true);

    // A shift-click on a card would otherwise extend the browser's native text
    // selection across the cards in between.
    document.body.addEventListener('mousedown', (evt) => {
      if (!evt.shiftKey) return;
      if (!this.active && !evt.target.closest('.ms-checkbox')) return;
      const container = document.querySelector(this._containerSelector);
      if (!container) return;
      const card = evt.target.closest(this.cardSelector);
      if (card && container.contains(card)) evt.preventDefault();
    });

    // Cancel button inside the toolbar.
    document.body.addEventListener('click', (evt) => {
      if (!this._toolbarSelector) return;
      const btn = evt.target.closest('.ms-cancel-btn');
      if (!btn) return;
      const toolbar = document.querySelector(this._toolbarSelector);
      if (toolbar && toolbar.contains(btn)) this.clearSelection();
    });

    // Escape cancels multi-select (only when active, so it doesn't interfere
    // with overlay-close handlers when multi-select is idle).
    document.addEventListener('keydown', (evt) => {
      if (evt.key === 'Escape' && this.active) this.clearSelection();
    });

    // Belt-and-suspenders: cancel any HTMX request from a card while active.
    document.body.addEventListener('htmx:beforeRequest', (evt) => {
      const container = document.querySelector(this._containerSelector);
      if (!container) return;
      if (this.active && container.contains(evt.detail.elt)) {
        evt.preventDefault();
      }
    });

    // Reset selection when a filter response replaces the container's contents.
    document.body.addEventListener('htmx:afterSwap', (evt) => {
      const container = document.querySelector(this._containerSelector);
      if (evt.detail.target === container) this._resetState();
    });

    // HTMX history restoration replaces the DOM; internal state is now stale.
    document.body.addEventListener('htmx:historyRestore', () => this._resetState());
  }

  _toggle(pk, card, container) {
    this._setSelected(pk, card, !this.selectedPks.has(pk));
    this.anchorPk = pk;
    this._syncState(container);
  }

  // Shift-click: every card between the anchor and the clicked one takes the
  // state the clicked card is toggling into, so a range can be selected or
  // deselected in one go.
  _selectRange(pk, container) {
    const cards = Array.from(container.querySelectorAll(this.cardSelector));
    const anchorIndex = cards.findIndex(c => c.getAttribute(this.pkAttr) === this.anchorPk);
    const targetIndex = cards.findIndex(c => c.getAttribute(this.pkAttr) === pk);

    // The anchor's card is gone (e.g. filtered out): fall back to a plain toggle.
    if (anchorIndex === -1 || targetIndex === -1) {
      const card = cards[targetIndex] || null;
      if (card) this._toggle(pk, card, container);
      return;
    }

    const selected = !this.selectedPks.has(pk);
    const start = Math.min(anchorIndex, targetIndex);
    const end = Math.max(anchorIndex, targetIndex);
    cards.slice(start, end + 1).forEach(card => {
      const cardPk = card.getAttribute(this.pkAttr);
      if (cardPk) this._setSelected(cardPk, card, selected);
    });

    this.anchorPk = pk;
    this._syncState(container);
  }

  _setSelected(pk, card, selected) {
    if (selected) {
      this.selectedPks.add(pk);
      card.classList.add('ms-selected');
    } else {
      this.selectedPks.delete(pk);
      card.classList.remove('ms-selected');
    }
  }

  _syncState(container) {
    this.active = this.selectedPks.size > 0;
    if (!this.active) this.anchorPk = null;
    container.classList.toggle('ms-active', this.active);
    this._updateToolbar();
    this._dispatch(container);
  }

  _resetState() {
    this.selectedPks.clear();
    this.active = false;
    this.anchorPk = null;
    const container = document.querySelector(this._containerSelector);
    if (container) {
      container.classList.remove('ms-active');
      container.querySelectorAll(`${this.cardSelector}.ms-selected`).forEach(card => {
        card.classList.remove('ms-selected');
      });
    }
    this._updateToolbar();
    this._dispatch(container);
  }

  _updateToolbar() {
    if (!this._toolbarSelector) return;
    const toolbar = document.querySelector(this._toolbarSelector);
    if (!toolbar) return;
    toolbar.hidden = !this.active;
    const countEl = toolbar.querySelector('.ms-count');
    if (countEl) {
      const n = this.selectedPks.size;
      countEl.textContent = `${n} selected`;
    }
  }

  _dispatch(container) {
    const pks = Array.from(this.selectedPks);
    if (container) {
      container.dispatchEvent(new CustomEvent('multiselect:change', {
        bubbles: true,
        detail: { pks },
      }));
    }
    if (this.onSelectionChange) this.onSelectionChange(pks);
  }

  getSelectedPks() {
    return Array.from(this.selectedPks);
  }

  clearSelection() {
    this._resetState();
  }
}
