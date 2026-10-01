# ADR 019 - Recipe similarity metric

**Status**: Accepted
**Date**: 2026-09-26

---

## Index

1. [Context and goal](#1-context-and-goal)
2. [How the measure works](#2-how-the-measure-works)
3. [Field roles: Identity, Modulator, Effect](#3-field-roles-identity-modulator-effect)
4. [Measuring each field](#4-measuring-each-field)
5. [Combining the field scores](#5-combining-the-field-scores)
6. [Weights and where the values live](#6-weights-and-where-the-values-live)
7. [The similarity score](#7-the-similarity-score)
8. [Worked examples](#8-worked-examples)
9. [Decisions log](#9-decisions-log)

---

## 1. Context and goal

[ADR 002](002-recipe-relationship-graph.md) defines the similarity between two recipes as
their **Hamming distance**: the count of fields that differ when the two recipes are compared
field by field. This was a deliberate simplification, and it has two known weaknesses.

1. **It ignores *how much* a field differs.** A recipe with `color = +4` and a recipe with
   `color = +3` are treated as exactly as different as `color = +4` and `color = -2`. For
   every numeric field, Hamming throws away the magnitude of the change and keeps only
   "equal / not equal".

2. **It treats every field as equally important.** Changing the `film_simulation` and
   changing the `high_iso_nr` each add exactly 1 to the distance, even though the first
   changes what the recipe fundamentally *is* and the second only changes how much noise is
   smoothed. Two recipes that differ only in noise reduction are, for most purposes, the same
   recipe rendered slightly differently.

The counter-proposal that usually comes up (Manhattan or Euclidean distance) fixes weakness 1
but not weakness 2, and it cannot be applied globally anyway because several fields
(`film_simulation`, `white_balance`) have no numeric axis to subtract along.

We want a single, bounded, interpretable number that answers "how different are these two
recipes?" while respecting both *how much* each field differs and *what kind of thing* that
field controls.

**What this powers.** The first use of this measure is a **"Related recipes" section in the
recipe detail view**: for the recipe you are looking at, rank the other recipes by how similar
they are and show the closest ones. Only the ordering matters here, so the score does not need
to behave like a strict distance (see [The similarity score](#7-the-similarity-score)).

**Scope.** This does not change the recipe graph in
[ADR 002](002-recipe-relationship-graph.md), which keeps using Hamming distance. The new
measure exists because Hamming is too coarse for the "Related recipes" ranking, not to replace
it in the graph. Whether the graph later switches to this measure is left for another day.

> **Update.** [ADR 020](020-recipe-graph-similarity-metric.md) later brings this measure into the
> graph, but not its layout: the graph keeps its Hamming topology, and similarity drives the
> neighbourhood filter, a per-node closeness badge, the sidebar chips and the comparison-panel
> headline.

---

## 2. How the measure works

The new measure works in two simple steps.

**Step 1: score each field on its own.** For every field, we work out how different the two
recipes are *on that field*, as a number from 0 (identical) to 1 (as different as that field
can possibly be). How we work it out depends on the field:

- For a number such as `color` or `sharpness`, it is how big the gap is. A gap of 1 counts
  less than a gap of 6.
- For something that is not a number, such as `film_simulation`, it is a more meaningful
  distance: Velvia is close to Provia and far from Acros. (Explained in detail later.)

**Step 2: combine the scores into one.** We take a weighted average of all the per-field
scores. Fields that matter more to the recipe's look (such as `color` or `film_simulation`)
get a bigger weight than fields that barely change it (such as noise reduction).

Because every per-field score is between 0 and 1, and we average them, the final result is
also between 0 and 1. So we can show it as a percentage, where 100% means the two recipes are
identical:

```
similarity% = (1 - overall_difference) * 100
```

One idea keeps this clean, and it is worth stating on its own:

> **First make every field comparable, then decide how much each one counts.**
> Step 1 puts every field on the same 0-to-1 scale, so a change in `color` and a change in
> `sharpness` can be compared at all. Step 2 is the only place where importance enters: the
> weights are what make `color` count for more than `sharpness`.

This is the same *shape* as the current Hamming distance, only less crude. Hamming also scores
each field and adds the scores up, but it can only ever score a field as 0 (equal) or 1
(different), and it treats every field as equally important. The new measure keeps the two
steps and makes both smarter: real per-field differences instead of just equal-or-not, and
weights instead of treating every field the same.

The next sections fill in the two steps: section 3 groups the fields by role, section 4
defines how each field is scored, and section 5 defines how the scores combine.

---

## 3. Field roles: Identity, Modulator, Effect

Fields are classified by the *role* they play in the recipe, because role is what should drive
the weight. Three tiers are used.

- **Identity** - defines what the recipe fundamentally *is*: its base look, colour and
  tonality. A difference here means the two recipes are genuinely different recipes.
- **Modulator** - shapes the tonality, but secondarily. A refinement of the look rather than a
  redefinition of it.
- **Effect** - applied on top of the image without touching its tonality (noise, grain, edge
  rendering). Two recipes differing only in effects are "the same recipe, rendered slightly
  differently".

All value domains below are taken from
[`src/domain/images/recipe_values.py`](../../src/domain/images/recipe_values.py). Every
per-field distance is normalized to `[0, 1]`; the exact formulas are in
[section 4](#4-measuring-each-field).

### Tier 1 - Identity

| Field | Value domain | Distance type | Scale (normalized to [0,1]) | Justification |
|---|---|---|---|---|
| `film_simulation` | 20 categorical values (11 colour, 9 B&W/Acros/Sepia) | Categorical, **semantic** | weighted Euclidean distance in Fujifilm's published feature space (see below) | The base colour science and tone response; the single strongest identity driver. |
| `white_balance` (mode) | Auto, Daylight, Kelvin, Incandescent, Daylight Fluorescent, Auto (white priority); Kelvin embeds a temperature such as `5200K` | Hybrid: numeric in mired space between temperature modes, categorical for Auto | see "White balance" below | Sets the overall colour cast, core to tonality. |
| `white_balance_red` + `white_balance_blue` | int -9..+9 each | **2D vector** | `sqrt(Δred² + Δblue²) / sqrt(18² + 18²)` | Fine colour-cast tint; jointly a point in the shift plane, so measured jointly. |
| `highlight` | -2.0..+4.0, step 0.5 | Numeric ordinal | `\|Δ\| / 6.0` | Tone curve top end; shapes contrast and exposure feel. |
| `shadow` | -2.0..+4.0, step 0.5 | Numeric ordinal | `\|Δ\| / 6.0` | Tone curve bottom end; shapes contrast. |
| `color` (saturation) | -4..+4, step 1; None for B&W | Numeric ordinal, **gated** | `\|Δ\| / 8.0` | Saturation is central to a colour recipe's look. Compared for two colour recipes; maxed against a B&W recipe (see section 5). |
| `monochromatic_color_warm_cool` | -18..+18; None on colour sims | Numeric ordinal, **gated** | `\|Δ\| / 36.0` | The toning *is* the identity of a B&W recipe. Compared for two B&W recipes; maxed against a colour recipe (see section 5). |
| `monochromatic_color_magenta_green` | -18..+18; None on colour sims | Numeric ordinal, **gated** | `\|Δ\| / 36.0` | Second toning axis; identity for B&W. Same gate as warm/cool. |

### Tier 2 - Modulator

| Field | Value domain | Distance type | Scale (normalized to [0,1]) | Justification |
|---|---|---|---|---|
| `dynamic_range` | DR-Auto, DR100, DR200, DR400 | Ordered categorical (ordinal in stops) | ladder position (see section 4) `/ 2` | Changes highlight retention; a real tonal effect, but secondary to the base look. |
| `d_range_priority` | Off, Weak, Strong, Auto | Ordered categorical | ladder position (see section 4) `/ 2` | Tonal-range shaping; mutually exclusive with `dynamic_range` on the camera. |
| `color_chrome_effect` | Off, Weak, Strong | Ordered categorical | `\|Δi\| / 2` | Adds depth in highly saturated areas; refines, does not redefine. |
| `color_chrome_fx_blue` | Off, Weak, Strong | Ordered categorical | `\|Δi\| / 2` | Deepens blues specifically; a targeted refinement. |
| `clarity` | -5..+5, step 1 | Numeric ordinal | `\|Δ\| / 10.0` | Midtone contrast and texture; a refinement of tone, not the base look. |

### Tier 3 - Effect

| Field | Value domain | Distance type | Scale (normalized to [0,1]) | Justification |
|---|---|---|---|---|
| `sharpness` | -4..+4, step 1 | Numeric ordinal | `\|Δ\| / 8.0` | Edge rendering only, not tonality. |
| `high_iso_nr` (noise reduction) | -4..+4, step 1 | Numeric ordinal | `\|Δ\| / 8.0` | Changes noise amount, not tonality. The canonical "effect". |
| `grain` (roughness + size) | roughness Off/Weak/Strong, size Off/Small/Large | 2D vector | `sqrt(Δrough² + Δsize²) / sqrt(2² + 2²)`, with Off = (0,0) | Grain texture laid on top; the two controls act as one, so compared jointly. |

### Excluded from the aesthetic distance

| Field | Reason |
|---|---|
| `sensor_signature` / `sensors` | Compatibility metadata, not a visual property. Best used as a *filter* ("only compare recipes for my sensor"), not a distance term. |
| `name`, `description`, `cover_image` | Not part of the look. |

---

## 4. Measuring each field

This section defines the per-field distance for each field type, plus the two rules that keep
the measure well-behaved (missing values and field interactions).

### 4.1 Numeric ordinal fields

`d = |v_a - v_b| / span`, where `span` is the field's full defined range (for example 8.0 for
`color`, which spans -4..+4). Normalizing by the *full defined* range, not the range observed
in the data, keeps the scale stable as the collection grows.

Worked example (the motivating case): `color +4` vs `color +3` gives `1/8 = 0.125`; `color +4`
vs `color -2` gives `6/8 = 0.75`. The first pair is correctly much closer.

### 4.2 Ordered categorical (ladder) fields

Each value is assigned an ordinal position, and `d = |pos_a - pos_b| / span_pos`.

`dynamic_range` ladder:

| Value | Position |
|---|---|
| DR100 | 0.0 |
| DR-Auto | 0.5 |
| DR200 | 1.0 |
| DR400 | 2.0 |

`span_pos` is 2.0 (DR100 to DR400). DR800 is not a recipe parameter (the camera reaches it
only by constraining other settings), so it is not on the ladder.

`d_range_priority` ladder: Off = 0, Weak = 1, Strong = 2, with DRP-Auto at 1.5.

**"Auto" as the expected value of a bounded interval.** DR-Auto lets the camera pick between
DR100 and DR200 only, so it genuinely lives on the ladder at the midpoint of that interval
(0.5), not off it with an arbitrary penalty. DRP-Auto likewise picks between Weak and Strong,
so it sits at 1.5. The general rule: *when an Auto setting is bounded to a known interval,
place it at the expected value (midpoint) of that interval.* This is an approximation (Auto is
really a distribution over the interval, not a point), and it is the correct approximation
because a recipe stores the *setting*, not the rendered outcome.

The rule does **not** apply to White Balance Auto, which is scene-adaptive and unbounded; that
stays categorical (see below).

### 4.3 White balance

White balance presets are named points on the colour-temperature axis, so the field is not
really categorical. Every temperature-bearing mode maps to a nominal Kelvin, and distance is
computed in **mired** space (`mired = 1_000_000 / K`) rather than raw Kelvin, because mireds
are perceptually uniform: a 500K difference near 3000K is far more visible than near 8000K.

```
mired(K) = 1_000_000 / K
d        = |mired(K_a) - mired(K_b)| / mired_span
```

Fuji's Kelvin range is 2500K..10000K, i.e. 400..100 mired, so `mired_span = 300`.

Nominal Kelvin map (starting values, approximate):

| WB mode | Nominal K | Mired | Notes |
|---|---|---|---|
| Incandescent | ~3200 | 312 | |
| Daylight | ~5500 | 182 | equivalent to selecting Kelvin 5500 |
| Kelvin | explicit | 1e6/K | user-set |
| Daylight Fluorescent | ~6500 | 154 | also carries a green tint not captured by a single temperature |
| Auto | n/a | n/a | scene-adaptive, categorical |
| Auto (white priority) | n/a | n/a | scene-adaptive, categorical |

Categorical rule for the Autos: same mode = 0; Auto vs any temperature mode = a fixed penalty
of **0.5** (Auto usually lands near daylight, so it is clearly different in intent but not at
the opposite end).

### 4.4 The white balance shift as a 2D vector

`white_balance_red` and `white_balance_blue` jointly define the fine tint, so their distance
is the Euclidean length of the difference vector, normalized by the maximum possible length:
`sqrt(Δred² + Δblue²) / sqrt(18² + 18²)`.

### 4.5 `film_simulation` semantic distance

Film simulations are not equidistant: Provia, Astia and Velvia are neighbours; Velvia and
Acros are far; every colour sim is very far from every B&W sim. The distance is therefore a
**feature-space distance**, and the feature space is not invented: Fujifilm publishes one.

**Authoritative source.** Each film simulation's page on fujifilm-x.com (for example the Acros
page) plots the sim on four axes, all relative to a **Provia baseline**:

| Axis | Low end | High end |
|---|---|---|
| Color | Muted | Vivid |
| Highlight Tone | Soft | Hard |
| Shadow Tone | Soft | Hard |
| Characteristics | Standard | Unique |

Each axis is a discrete tick scale, and each sim's position is marked against Provia's. This
gives every sim an authoritative 4-tuple of coordinates. The distance between two sims is the
(optionally weighted) Euclidean distance in this space, normalized by the maximum possible
diagonal so it lands in `[0, 1]`.

**The four axes only compare film simulations to each other.** They are the ruler for the
`film_simulation` field's distance, nothing more. They are not recipe-level dimensions and
they are never mixed with the recipe's own `color`, `highlight` and `shadow` fields. Those
recipe fields are the adjustments the user dials on top, and they are compared separately, as
listed in the Identity tier. The two things answer different questions: the axes say "how
different are these two film stocks?", the recipe fields say "what adjustments did the user
make?". Both belong, and there is no double counting because they measure different things.

**Captured data.** The coordinates were extracted from all 20 per-sim pages
(`fujifilm-x.com/en-au/products/film-simulation/<slug>/`). Each axis is an N-cell grid; the
sim's value is the `compare` marker, and the constant `marker` position is the Provia
baseline. Raw 1-based cell indices (axis resolutions: Color = 14, Highlight = 10, Shadow = 10,
Characteristics = 5):

| Film simulation | Color /14 | Highlight /10 | Shadow /10 | Characteristics /5 |
|---|---|---|---|---|
| Provia (baseline) | 8 | 6 | 6 | 1 |
| Velvia | 11 | 10 | 10 | 4 |
| Astia | 7 | 5 | 7 | 2 |
| Classic Chrome | 5 | 7 | 9 | 4 |
| Classic Negative | 4 | 10 | 7 | 5 |
| Nostalgic Negative | 6 | 4 | 4 | 5 |
| Reala Ace | 7 | 8 | 5 | 3 |
| Eterna | 5 | 2 | 2 | 1 |
| Eterna Bleach Bypass | 1 | 10 | 7 | 5 |
| Pro Neg. Hi | 7 | 9 | 9 | 1 |
| Pro Neg. Std | 6 | 6 | 4 | 1 |
| Acros STD | N/A | 8 | 8 | 1 |
| Acros Yellow | N/A | 8 | 8 | 2 |
| Acros Red | N/A | 8 | 8 | 2 |
| Acros Green | N/A | 8 | 8 | 3 |
| Monochrome STD | N/A | 6 | 6 | 1 |
| Monochrome Yellow | N/A | 6 | 6 | 2 |
| Monochrome Red | N/A | 6 | 6 | 2 |
| Monochrome Green | N/A | 6 | 6 | 3 |
| Sepia | N/A | 6 | 6 | 1 |

Normalize each axis to `[0, 1]` with `pos = (index - 1) / (N - 1)`, then compute the weighted
Euclidean distance, normalized by the maximum diagonal so it lands in `[0, 1]`.

**Monochrome handling.** Colour is `N/A` for every B&W sim (Fujifilm hides that axis). The
distance treats the colour/B&W split as follows:
- colour vs colour: use all four axes.
- B&W vs B&W: drop the Color axis, use the other three.
- colour vs B&W: drop the Color axis, and add a **weighted binary monochrome axis** (value 0
  for colour, 1 for B&W) that carries the colour-to-B&W identity gap.

The binary axis is necessary: an earlier attempt to encode B&W as `Color = 0` (fully muted)
gave `dist(Provia, Acros) = 0.31 < dist(Provia, Velvia) = 0.50`, which wrongly makes the jump
to monochrome smaller than a colour-to-colour change. A dedicated, heavily weighted monochrome
axis fixes this and keeps the colour/B&W boundary as strong as it should be.

Sanity checks on the captured data (equal axis weights, before adding the monochrome axis):
Eterna~Velvia = 0.77 (largest, flat-muted vs vivid-hard), Provia~Astia = 0.15 (smallest, Astia
is a soft Provia), Velvia~Acros = 0.56, Classic Neg~Classic Chrome = 0.24. These match
intuition.

**Data limitations the chart does not capture:**
- **Colour filter variants** (Acros/Monochrome Yellow/Red/Green) differ from their base sim
  only on the Characteristics axis, so they are nearly coincident in this space. Accepted, as
  the recipe's own fields and the sim name still distinguish them.
- **Sepia would otherwise sit exactly on Monochrome STD** (its warm toning is on none of the
  axes, and the recipe's toning fields do not apply to it). Fix: add a small dedicated toning
  marker in the film-sim space, set only for Sepia, so `Sepia~(neutral B&W)` is a fixed small
  distance rather than zero. It stays small, because Sepia is still a monochrome and far closer
  to the B&W sims than to any colour sim.

### 4.6 Fields with no value

Sometimes a field has no value for one or both recipes because the setting does not apply (for
example `color` on a black-and-white recipe, or `sharpness` shown as "Film Simulation"). When
that happens we **skip the field and only compare the fields that do have values**. A missing
field never adds a fake difference.

### 4.7 Field interactions

A few fields relate to each other and need a note:

- **`dynamic_range` and `d_range_priority` are mutually exclusive** on the camera: when one is
  active, the other is left empty. They stay two separate fields, and the "skip fields with no
  value" rule above handles it. If both recipes use DR, we compare `dynamic_range` (and
  `d_range_priority` is Off on both). If both use DRP, `dynamic_range` is empty on both and is
  skipped. If one uses each, the empty side is skipped and the difference shows up as
  `d_range_priority` (Off vs Weak/Strong). No special handling needed.
- **Grain roughness and size act as one control** (size is meaningless when roughness is Off),
  so they are compared jointly as the single 2D `grain` field above, rather than as two
  separate fields that would double-count.
- **The white-balance mode temperature and the R/B shift both nudge warm-cool**, so they
  overlap a little. We keep them as separate fields anyway: the shift (-9..+9) is a small trim
  next to the mode's temperature span, and merging them would need another unit conversion. The
  minor overlap is accepted.

---

## 5. Combining the field scores

Suppose we just averaged all the per-field scores into one number. Then a lot of small
differences in the effect fields (grain, sharpness, noise) could pile up and make two recipes
look as different as if the film simulation had changed. That feels wrong: if you switch the
film simulation, you have a genuinely different recipe, and no amount of matching grain or
sharpness should hide that.

So instead of one big average, we compare in two rounds, and the identity fields lead.

1. **Identity score.** Compare only the identity fields (the ones that define the look) and
   turn that into a score from 0 (completely different) to 1 (identical):
   `identity_score = 1 - average(identity field differences)`

2. **Extras score.** Compare everything else (the modulator and effect fields) into a second
   score the same way, giving the modulator fields more weight than the effect fields since
   they matter a little more:
   `extras_score = 1 - average(modulator and effect field differences)`

3. **Final score.** The identity score sets the limit, and the extras score can only move
   things a little within that limit:
   ```
   final_score = identity_score * (a + b * extras_score)      # a + b = 1
   similarity% = final_score * 100
   ```

What the two numbers `a` and `b` do:
- If two recipes match perfectly on identity but differ as much as possible on everything else,
  they still come out at `a` (times 100%). So `a` is the lowest a pair can drop to when only
  the extras differ.
- If the identity fields differ, the identity score pulls the whole result down, and no amount
  of matching extras can bring it back up. Identity always wins.

Starting values (to be tuned later): `a = 0.7`, `b = 0.3`. That means two recipes with the
same identity but completely different extras still land at 70% similar, which matches the idea
of "the same recipe, just rendered a bit differently".

### Fields that only apply to one kind of recipe

Some identity fields only make sense for one kind of recipe. `color` (saturation) only means
something for colour recipes, and the two `monochromatic_color_*` (toning) fields only mean
something for black-and-white recipes. So we compare them like this:

- Both recipes are colour: compare `color`, ignore the toning fields.
- Both recipes are black-and-white: compare the toning fields, ignore `color`.
- One of each: the two recipes differ in their most basic nature, colour versus B&W. Rather
  than skip, we count `color` and **both** toning fields as a **maximal difference (distance 1
  each)**. This registers the colour/B&W mismatch directly in these fields, on top of the
  `film_simulation` distance, so a colour recipe and a B&W recipe are pushed firmly apart.

When a field is genuinely absent on both sides (for example the toning fields when both recipes
are colour), it is skipped and only the fields that apply are averaged. The maximal-difference
rule above is the one deliberate exception, reserved for the colour-versus-B&W mismatch.

---

## 6. Weights and where the values live

These are starting values, picked to be sensible rather than final. The plan is to tune them
later by looking at real "Related recipes" results; the structure is what this ADR fixes, the
numbers are cheap to change.

- **Identity vs extras (`a` / `b`):** `a = 0.7`, `b = 0.3`. Two recipes with identical identity
  but completely different extras still score 70%.
- **Modulator vs Effect (inside the extras score):** each Modulator field counts twice as much
  as each Effect field.
- **Fields inside Identity:** all count equally, except `film_simulation`, which counts twice
  as much as any other identity field.
- **The four film-sim axes** (Color, Highlight, Shadow, Characteristics): count equally.
- **The monochrome axis** (in the film-sim distance): weighted heavily, so switching between
  colour and black-and-white is on its own a large jump. A starting value of about 3 (roughly
  the other three axes combined) makes `Provia~Acros` come out clearly larger than
  `Provia~Velvia`, as it should.

### Where the values live

- **Reference data** (the film-sim coordinate table, the per-field ranges, the Kelvin map) and
  all the weights except `a`/`b` live in a **static constants module**. They are tuned by a
  developer during calibration, not by an end user.
- **`a` and `b`** are **`django-constance` settings** (defaults `a = 0.7`, `b = 0.3`), so the
  identity-vs-extras balance can be adjusted at runtime while judging real results, without a
  deploy.

---

## 7. The similarity score

The user-facing value is a percentage where **100% means the two recipes are identical**. Two
properties to keep in mind, to be recorded so callers do not over-read the number:

1. **It is an ordinal display scale, not a ratio.** 80% is "more similar than 60%", but it is
   *not* "twice as similar as 40%". The weights are author-set, not physically calibrated, so
   linearity of the scale is not claimed.
2. **The distance-to-percentage mapping is linear by default** (`1 - distance`). A non-linear
   mapping (compressing the top end so near-identical recipes read as very high) is a separate,
   reversible presentation decision, not part of the distance math.

Mathematical properties:

- **Symmetry**: guaranteed. Every per-field distance is symmetric, and the combination is
  symmetric, so `sim(A, B) == sim(B, A)`.
- **Identity of indiscernibles**: `similarity% == 100` if and only if every compared field is
  equal.
- **Triangle inequality**: **not** guaranteed. This is the rule that the difference between two
  recipes should never be larger than adding up their differences to some third recipe in
  between. Our formula can break this rule. Whether that matters depends on how the score gets
  used later, so we leave this question for the future.

---

## 8. Worked examples

Two examples: a near-identical pair that should score high, and a colour-versus-B&W pair that
should score much lower.

### 8.1 A close pair: two Portra recipes

Two recipes from the same "Kodak Portra 400" version line, both on the same sensor. They are
expected to score high, since they are refinements of one recipe.

- **Recipe A** = "Kodak Portra 400 (v2)"
- **Recipe B** = "Kodak Portra 400 (v3)"

#### Field by field

| Tier | Field | Recipe A | Recipe B | Per-field distance |
|---|---|---|---|---|
| Identity | `film_simulation` | Classic Chrome | Classic Chrome | 0 |
| Identity | `white_balance` (mode) | 5200K | 5200K | 0 |
| Identity | white balance shift (red, blue) | (2, -4) | (2, -4) | 0 |
| Identity | `highlight` | 0 | 0 | 0 |
| Identity | `shadow` | -2 | -2 | 0 |
| Identity | `color` | +2 | +2 | 0 |
| Identity | `monochromatic_color_*` | n/a (colour) | n/a (colour) | skipped |
| Modulator | `dynamic_range` | DR400 | DR200 | `\|2 - 1\| / 2 = 0.5` |
| Modulator | `d_range_priority` | Off | Off | 0 |
| Modulator | `color_chrome_effect` | Strong | Strong | 0 |
| Modulator | `color_chrome_fx_blue` | Weak | Weak | 0 |
| Modulator | `clarity` | 0 | 0 | 0 |
| Effect | `sharpness` | 0 | -1 | `\|0 - (-1)\| / 8 = 0.125` |
| Effect | `high_iso_nr` | -4 | -2 | `\|-4 - (-2)\| / 8 = 0.25` |
| Effect | `grain` | Off (0,0) | Off (0,0) | 0 |

The two recipes are identical across every Identity field and differ only in one Modulator
(dynamic range) and two Effects (sharpness, noise reduction). This is exactly the "same recipe,
rendered a bit differently" case.

#### Round 1: identity score

Every identity distance is 0, so:

```
identity_score = 1 - 0 = 1.0
```

(The `film_simulation` double weight makes no difference here, since all the identity distances
are 0.)

#### Round 2: extras score

Modulators count twice as much as effects. There are 5 modulator fields and 3 effect fields
(grain counts once, as a single 2D field), so the total weight is `2*5 + 1*3 = 13`.

```
weighted difference sum = 2*(0.5 + 0 + 0 + 0 + 0) + 1*(0.125 + 0.25 + 0)
                        = 1.0 + 0.375
                        = 1.375

extras_difference = 1.375 / 13 = 0.106
extras_score      = 1 - 0.106 = 0.894
```

#### Final score

With `a = 0.7`, `b = 0.3`:

```
final_score = identity_score * (a + b * extras_score)
            = 1.0 * (0.7 + 0.3 * 0.894)
            = 0.7 + 0.268
            = 0.968

similarity% = 96.8%
```

**Result: 96.8%.** High, as expected: the two recipes share the same identity completely, and
differ only in a dynamic-range step and two small effect tweaks. For comparison, Hamming would
have reported a distance of 3 (three fields differ) with no sense of how minor those three
differences are.

### 8.2 A distant pair: Portra vs Tri-X

A colour recipe against a black-and-white one. They should score much lower.

- **Recipe A** = "Kodak Portra 400 (v2)" (colour, Classic Chrome)
- **Recipe B** = "Kodak Tri-X 400" (black-and-white, Acros Yellow)

#### Field by field

| Tier | Field | Recipe A | Recipe B | Per-field distance |
|---|---|---|---|---|
| Identity | `film_simulation` | Classic Chrome (colour) | Acros Yellow (B&W) | 0.739 (feature space, colour vs B&W) |
| Identity | `white_balance` (mode) | 5200K | Daylight (5500K) | 0.035 |
| Identity | white balance shift (red, blue) | (2, -4) | (9, -9) | `sqrt(7² + 5²) / sqrt(18² + 18²) = 0.338` |
| Identity | `highlight` | 0 | 0 | 0 |
| Identity | `shadow` | -2 | +3 | `\|-2 - 3\| / 6 = 0.833` |
| Identity | `color` | +2 | n/a (B&W) | 1.0 (maxed: colour vs B&W) |
| Identity | `monochromatic_color_warm_cool` | n/a (colour) | 0 | 1.0 (maxed: colour vs B&W) |
| Identity | `monochromatic_color_magenta_green` | n/a (colour) | 0 | 1.0 (maxed: colour vs B&W) |
| Modulator | `dynamic_range` | DR400 | DR200 | `\|2 - 1\| / 2 = 0.5` |
| Modulator | `d_range_priority` | Off | Off | 0 |
| Modulator | `color_chrome_effect` | Strong | Strong | 0 |
| Modulator | `color_chrome_fx_blue` | Weak | Off | `\|1 - 0\| / 2 = 0.5` |
| Modulator | `clarity` | 0 | 0 | 0 |
| Effect | `sharpness` | 0 | +1 | `\|0 - 1\| / 8 = 0.125` |
| Effect | `high_iso_nr` | -4 | -2 | `\|-4 - (-2)\| / 8 = 0.25` |
| Effect | `grain` | Off (0,0) | Off (0,0) | 0 |

Two things carry the colour/B&W difference here. First, the `film_simulation` distance: because
one sim is colour and the other B&W, the Color axis is dropped and a heavy binary monochrome
axis (weight 3) is added, so Classic Chrome vs Acros Yellow on Highlight, Shadow, Characteristics
plus that monochrome axis gives **0.739**. Second, `color` and both toning fields are each
**maxed to 1.0**, because a colour recipe and a B&W recipe differ in their most basic nature (see
section 5).

#### Round 1: identity score

`film_simulation` counts double; the other identity fields count once, and `color` plus the two
toning fields are each maxed to 1.0. Total weight `2 + 1 + 1 + 1 + 1 + 1 + 1 + 1 = 9`.

```
weighted difference sum = 2*0.739 + 0.035 + 0.338 + 0 + 0.833 + 1 + 1 + 1
                        = 5.684

identity_difference = 5.684 / 9 = 0.632
identity_score      = 1 - 0.632 = 0.368
```

#### Round 2: extras score

```
weighted difference sum = 2*(0.5 + 0 + 0 + 0.5 + 0) + 1*(0.125 + 0.25 + 0)
                        = 2.0 + 0.375
                        = 2.375

extras_difference = 2.375 / 13 = 0.183
extras_score      = 1 - 0.183 = 0.817
```

#### Final score

```
final_score = identity_score * (a + b * extras_score)
            = 0.368 * (0.7 + 0.3 * 0.817)
            = 0.368 * 0.945
            = 0.348

similarity% = 34.8%
```

**Result: 34.8%**, far below the 96.8% of the close pair. The ordering is right and the gap is
wide: the measure cleanly separates "a refinement of the same recipe" from "a genuinely
different recipe". The colour/B&W nature is now counted decisively, both inside
`film_simulation` and through the three maxed chroma/toning fields, so a colour recipe and a
B&W recipe can never read as close. The weights remain available to tune later once real
"Related recipes" output is on screen.

---

## 9. Decisions log

A record of the choices settled while writing this ADR.

1. **Tier placements.** `clarity`, `color_chrome_effect` and `color_chrome_fx_blue` are
   Modulators; grain is an Effect.
2. **Film-simulation distance.** Uses Fujifilm's published 4-axis feature space, with data
   captured for all 20 sims. The axes compare sims to each other only. Sepia gets a small
   dedicated toning marker; colour filter variants are accepted as near-coincident.
3. **Nominal Kelvin (starting values).** Incandescent 3200, Daylight 5500, Daylight Fluorescent
   6500.
4. **WB Auto penalty.** Auto vs a temperature mode = fixed penalty 0.5.
5. **Weights (starting values).** `a`/`b` = 0.7/0.3; modulators count double effects;
   `film_simulation` counts double other identity fields; the four film-sim axes are equal; the
   monochrome axis is heavy (about 3).
6. **Interactions.** DR vs DRP stay two fields (the skip rule handles it); grain
   roughness+size become one 2D field; WB mode temperature and R/B shift stay separate.
7. **Colour vs B&W chroma/toning fields.** When one recipe is colour and the other B&W, `color`
   and both toning fields are each maxed to distance 1 (not skipped), so the colour/B&W mismatch
   is registered directly, on top of the `film_simulation` distance.
8. **Where values live.** Reference data and weights live in a static constants module; `a`/`b`
   are `django-constance` settings (defaults 0.7 / 0.3).
