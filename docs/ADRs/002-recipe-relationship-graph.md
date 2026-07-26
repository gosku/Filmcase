# ADR 002 — Recipe relationship graph

**Status**: Accepted
**Date**: 2026-04-05

---

## Problem

Over time a user accumulates many recipes. Some of them are nearly identical — a small
tweak to highlight tone, a colour shift, a different grain setting — while others are more
radically different. In practice many recipes are simply refinements of a previous one:
the user shot with recipe A, felt the shadows were too dark, dialled them up by two stops,
and saved the result as recipe B. The relationship between A and B is meaningful, but
nothing in the data makes it visible. A flat list of recipes gives no signal about which
ones are close together, which are remote, or how a cluster of similar recipes evolved
from a common ancestor.

The problem is compounded when the same film simulation is used across many recipes.
A photographer using Provia as their base may have a dozen Provia recipes that differ
only in white balance or dynamic range. Without a way to visualise their proximity, the
collection feels like an undifferentiated pile, and the user cannot easily decide which
recipe to reach for next.

---

## Graph definition

### Nodes and edges

Each **node** represents one recipe. Each **edge** connects two recipes that are related —
the edge weight encodes how different those two recipes are from each other.

### Hamming distance

The similarity measure between two recipes is their **Hamming distance**: the count of
fields that differ when the two recipes are compared field by field. Both recipes share
the same 18-field parameter set, so each field is compared independently.

```
Recipe A: { film_sim: Provia, grain: OFF, color: 0, sharpness: −2, wb: Auto, … }
Recipe B: { film_sim: Provia, grain: OFF, color: +2, sharpness: −2, wb: Daylight, … }

Hamming distance = 2  (color and wb differ)
```

The 18 fields used for comparison are:

```
film_simulation, dynamic_range, d_range_priority, grain_roughness, grain_size,
color_chrome_effect, color_chrome_fx_blue, white_balance, white_balance_red,
white_balance_blue, highlight, shadow, color, sharpness, high_iso_nr, clarity,
monochromatic_color_warm_cool, monochromatic_color_magenta_green
```

The maximum possible Hamming distance between any two recipes is 18. Hamming distance
is symmetric: `dist(A, B) == dist(B, A)`.

---

## Decision

Two complementary views were built, each targeting a different question the user might ask.

### View 1 — Per-recipe graph (`/recipes/graph/<recipe_id>/`)

**Problem it solves:** "I am looking at this specific recipe. What other recipes are
similar to it, and how different are they?"

The graph is centred on a chosen **reference recipe**. Every other recipe whose Hamming
distance from the reference is below a configurable threshold
(`settings.RECIPE_GRAPH_MAX_DISTANCE`, default 7) appears as a node. Recipes beyond the
threshold are excluded — they are too remote to be useful neighbours. Unlike the film
simulation view, the candidates span every film simulation.

Clicking a node selects it and shows a comparison between that node and the reference
recipe, surfacing the exact fields that differ between the two.

### View 2 — Film simulation complete graph (`/recipes/graph/`)

**Problem it solves:** "I shoot a lot with this film simulation. How do all my recipes
for it relate to each other?"

Rather than picking one recipe as a focal point, this view shows **all recipes that share
a given film simulation** as a single connected tree. There is no distance cutoff: every
recipe is included. The reference node is selected automatically as the most-used recipe for that
film simulation (highest image count), anchoring the tree at the most familiar point.

A dropdown lets the user switch film simulations without reloading the page.

---

## Topology

### Tree instead of a graph with cycles

The most faithful representation of the data would be a full graph: every pair of recipes
connected by an edge whenever their Hamming distance is below the cutoff threshold. In
that model, a recipe with distance 2 from the reference node would have edges to the
reference node, to every distance-1 recipe within reach, and to every other distance-2
recipe close enough to qualify. Every route between any two recipes would be visible
simultaneously, and the graph would encode all pairwise relationships without loss.

In practice this becomes unreadable quickly. A modest collection of 20 recipes can
produce up to 190 edges. Rendered on screen, the nodes are buried under a web of
crossing lines; it is impossible to follow any single relationship or understand the
overall structure. The graph also contains redundant information: if recipe C is
reachable from the reference node via B, the direct reference → C edge adds visual
noise without adding meaning.

For these reasons the structure is reduced to a **spanning tree**: each non-reference
node has exactly one parent. This removes all cycles and redundant edges while
preserving the information that matters — the relative distance of each recipe from the
reference node (encoded in ring radius) and the chain of transitions that connects them.
Visual complexity scales with the number of nodes, not the number of pairs.

### Chaining nodes through intermediate transitions

Nodes are deliberately chained through intermediaries when those intermediaries represent
a plausible transition path. If recipes N1, N2, and N3 exist at distances 0, 1, and 2
from the reference node and N3 is one step away from N2, the graph becomes:

```
N1 → N2 → N3   (chain through N2)
instead of:
N1 → N2, N1 → N3  (both hanging directly off the reference node)
```

The chain is more informative: it communicates that N3 is not just "different from the
reference node" but specifically "a further refinement of N2".

### One shortest-path spanning tree for both views

Both views are built by the same function, `build_recipe_tree`, which enforces a
**shortest-path constraint**: a node's parent `P` must satisfy
`dist(reference, P) + dist(P, node) == dist(reference, node)`. This means the sum of edge
distances along any reference → node path equals that node's Hamming distance from the
reference, so ring radius and summed edge labels always agree.

The constraint exists to prevent misleading path inflation. Without it, an algorithm that
simply attaches each node to its closest neighbour one ring up can chain A → B → C with
edge distances 1 + 2 = 3 even when `dist(reference, C) = 2`, making the displayed
distances untrue.

This matters because the two views did not originally share an algorithm. The per-recipe
view used the closest-parent-at-`d − 1` rule, which on the current collection left roughly
two thirds of nodes with path sums that exceeded their true distance from the reference.
Unifying both views onto the constrained algorithm removed that discrepancy entirely.

The two views differ only in which recipes they feed the builder as candidates: everything
sharing a film simulation, or everything within `settings.RECIPE_GRAPH_MAX_DISTANCE` of the
reference recipe.

**When the constraint cannot be met.** Occasionally no node already in the tree satisfies
it, which is more likely on the per-recipe view because truncating candidates at the
maximum distance can exclude the intermediate a node would have needed. Such a node is
attached to its nearest in-tree neighbour and its edge is flagged `is_exact=False` and
drawn **dashed**. A solid edge is therefore a guarantee that the path sums are truthful,
and a dashed one is an explicit admission that they are not.

### Concentric (radial) layout

Three layout strategies were evaluated:

1. **Columnar tree (dagre `rankDir: "LR"`)** — nodes organised into vertical columns by
   distance layer. Once Hamming distance became the layout signal (rather than hop depth),
   many nodes shared the same distance but landed in different columns, and the fixed-width
   rank separation wasted horizontal space.

2. **Force-directed (cose)** — nodes spread freely. Better space utilisation but no
   guarantee of outward direction; edges crossed through the centre and the arrangement
   changed on every render.

3. **Custom radial preset (current)** — node positions are computed before Cytoscape
   renders them, then applied via the built-in `preset` layout (no extra library needed).
   The reference node sits at the origin. Each non-reference node's radius is proportional to its Hamming
   distance from the reference node, so the ring a node sits on directly encodes its distance. Each
   subtree is allocated an angular slice proportional to its leaf count, and nodes are
   placed at the midpoint of their slice. Children are always a subdivision of their
   parent's slice, so edges always point strictly outward and never cross through the
   centre.

The radial layout was chosen because it makes the most of two-dimensional screen space.
A columnar tree grows primarily in one direction: as more nodes are added, the vertical
extent of the graph expands while the horizontal extent stays fixed. The radial layout
distributes nodes in all directions, so the graph fills the available canvas evenly.
The ring structure also gives the distance dimension a natural, immediately readable
encoding: the further from the centre, the more different from the reference recipe.

---

## Differences and breakdown of deltas

The graph visualises which recipes are close to each other and how they chain together,
but it does not on its own explain *what* the differences are. To surface that, an info
panel docked to the right of the canvas fills in when the user clicks a node.

The panel is a sibling of the canvas in a flex row rather than an overlay floating above
it. An overlay hid the right-hand portion of the graph and, because the canvas still
spanned the full width underneath, the radial tree centred itself partly behind the panel.
Docking it means the canvas owns a known width and the tree is centred in genuinely usable
space. The panel is also always mounted at a fixed width, with only its selected-recipe
section toggling, so selecting a node never resizes the canvas and re-centres the graph
under the user's cursor.

The panel shows the **path delta** from the reference node to the selected node: the list of fields
that differ between the two recipes, with the value each recipe carries for that field.
When the node is reached through a chain of intermediate nodes, the card also breaks the
path down by edge — showing which fields changed at each hop along the route.

This breakdown serves two purposes:

1. **Explaining the graph structure.** A node two rings out differs from the reference node in
   exactly two fields. The delta breakdown names those two fields, turning an abstract
   distance number into a concrete description of the variation.

2. **Tracing an evolutionary path.** When a chain passes through an intermediate node,
   the breakdown shows which parameters shifted at each step. This makes it possible to
   read the graph as a record of how a recipe evolved: "I started with highlight −1 and
   shadow 0, then I bumped shadow to +2, and from there I also changed the white balance
   to Daylight."

Together, the graph topology and the delta breakdown transform the recipe collection from
a flat list into a navigable, annotated map of the photographer's recipe space.
