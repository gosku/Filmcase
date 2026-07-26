# ADR 012 — Pluggable card designs via a CardDesign abstraction

**Status**: Accepted
**Date**: 2026-07-25
**Supersedes**: the *card composition* portion of [ADR 005](005-recipe-sharing-via-image-cards.md) (the QR payload, import/decode, and persistence decisions in ADR 005 still stand)

---

## Context

[ADR 005](005-recipe-sharing-via-image-cards.md) introduced recipe cards and described their composition as a "template system": a `CardTemplate` value object holding a label style, a background effect, and an output size, consumed by a single `_compose_card` function. Four templates were shipped (full/short labels x blurred/sharp background), all on one 1080x1080 square layout, plus a separate `info_side` argument choosing which half held the info panel.

We now want cards that are not variations of that one layout but **fundamentally different designs** — a dark, story-format card with frosted-glass tiles, and a light "paper" spec-sheet — for sharing to Instagram Stories/Reels.

---

## Problem

ADR 005's composition model does not extend to genuinely different designs:

1. **One hardcoded layout.** `_compose_card` assumes a square canvas with a half-width info panel and a corner QR. A portrait card with a hero photo, tiled parameters, and a bottom import module cannot be expressed by tweaking `CardTemplate` fields.
2. **`info_side` is layout-specific.** It is a top-level argument to every card operation, yet it only means anything for the square design. Adding more layout-specific knobs this way pollutes the shared signature with options that do not apply to every design.
3. **Composition is a monolithic free function.** There is no seam at which a new design can supply its own drawing logic while reusing the shared concerns (QR generation, logo, EXIF embedding, file saving).
4. **The modal shows every knob at once.** The create-card UI assumes a single design and renders all its options together, with no room for designs that have different (or no) options.

---

## Decision

Replace the flat `CardTemplate` + `info_side` model with a **`CardDesign` abstraction**: an `abc.ABC` in `src/domain/recipes/cards/designs/` where each concrete design owns its full layout in a `render()` method and declares its own metadata.

```python
class CardDesign(abc.ABC):
    output_size: ClassVar[tuple[int, int]]
    requires_background_image: ClassVar[bool]

    @property
    @abc.abstractmethod
    def template_name(self) -> str: ...

    @abc.abstractmethod
    def render(self, *, recipe, background_image) -> RenderedCard: ...
```

- **`ClassicDesign`** reproduces the original square card. The four legacy templates collapse into this one class parameterized by `label_style` / `background_effect` / `info_side`; its `template_name` property still returns the original strings (`long_label`, `short_label`, `long_label_sharp`, `short_label_sharp`), so persisted `RecipeCard.template` values and the `recipe.card.created` event payload are unchanged.
- **`ApertureDesign`** and **`ContactSheetDesign`** are the two new portrait designs, each with a bespoke `render()`.
- Card operations (`create_recipe_card`, `preview_recipe_card_image`, ...) take a single `design: CardDesign` instead of `template` + `info_side`; layout-specific options live inside the design object.

### Why an ABC (and not the repo's usual Protocol / frozen-attrs)

The codebase otherwise favours frozen-attrs value objects with free functions, and a `typing.Protocol` when a seam is needed. Here an `abc.ABC` was chosen deliberately: designs are a small, closed, first-party set that share concrete helper behaviour by inheritance, and an explicit abstract base documents the contract new designs must implement. This is the first ABC in the codebase; it is a considered exception, not a new default.

### Shared globals vs per-design choices

- **Per-design:** the entire layout, the `output_size` (Classic stays 1080x1080; Aperture and Contact Sheet are 1080x1920, i.e. 9:16 for Stories/Reels), and whether the design `requires_background_image`.
- **Shared across every design:** the QR code (one size and spec, so any card scans the same way — see [ADR 006](006-qr-decode-library-and-size.md)), the filmcase logo, the gradient fallback background, EXIF embedding, and file saving. These live in a `rendering` module of reusable primitives (blurred/gradient backgrounds, rounded corners, tracked text, the QR, the logo/wordmark, fonts) that every design draws from.

> Note on QR size: the design handoff proposed a 240px QR, but the shared QR is kept at the existing 300px so every design — including the unchanged Classic card — scans identically. The 240px handoff value was believed to "match the current card"; the current card is in fact 300px.

### Photo-centric designs require a photo

Aperture and Contact Sheet are built around a real example photo (a hero image over a blurred version of the same photo), so `requires_background_image` is `True`. The gradient-background option is offered only for Classic. As a safety net, a photo-required design still renders on the gradient fallback if it is somehow called without an image, but the UI does not offer that path.

### Interface: per-design tabs

The create-card modal gains **htmx tabs**, one per design. Selecting a tab swaps in only that design's options (Classic keeps its label style / background effect / info side; the photo-centric designs have no extra knobs) and refreshes the live preview. A `RecipeCardDesignOptions` view serves each tab's controls, and the preview/create views resolve the chosen design from a single `design` request parameter.

### Fonts and assets

The new designs use the **Archivo** and **Space Mono** typefaces (OFL, vendored under `interfaces/static/fonts/`) and a pre-rasterized stacked filmcase logo PNG in `interfaces/static/images/original-branding/`. Pillow has no letter-spacing, so tracked labels are drawn glyph by glyph.

---

## Consequences

- New designs are added by subclassing `CardDesign` and registering the tab; the shared rendering primitives and the QR/import/decode pipeline from ADR 005 are reused unchanged.
- `RecipeCard.template` and the `recipe.card.created` event keep carrying a design-identifying string; Classic's strings are preserved for backward compatibility, and new designs add `aperture` / `contact_sheet`.
- The card operations' public signature is simpler (`design` replaces `template` + `info_side`), at the cost of introducing the first `abc.ABC` in the codebase.
- Card output size is now per-design rather than a single global, so downstream consumers must not assume 1080x1080.
