# ADR 020 - Similarity in the recipe graph (filtering and closeness, not layout)

**Status**: Accepted
**Date**: 2026-10-02

---

## Context

[ADR 002](002-recipe-relationship-graph.md) lays the recipe graph out by **Hamming distance**:
a node's ring is the count of fields that differ from the reference, and a shortest-path
spanning tree keeps the edge distances along any route summing to that ring (dashed edges when
they can't). [ADR 019](019-recipe-similarity-metric.md) added a richer **similarity** score - a
weighted, two-round `identity * (A + B * extras)` in `[0, 1]`, with a plain-language
`closeness_label` - and left the graph on Hamming.

We tried laying the graph out by similarity instead (radius = `1 - similarity`, a
nearest-relative tree, concentric closeness bands). It read well in the mockup, but on real
collections it crowded badly: because most recipes for one film simulation are highly similar,
they piled into the inner bands, overlapping labels and edges. A de-overlap pass stopped the
*nodes* overlapping, but the labels and edges stayed congested, and the layout no longer
communicated structure as clearly as the Hamming rings did. The Hamming layout, which spreads
nodes across integer rings, is simply a better picture.

So the graph **keeps its Hamming layout**, and similarity is used only where it adds value
without touching the topology.

## Decision

1. **Layout stays Hamming (ADR 002 unchanged).** Ring radius is Hamming distance from the root,
   the shortest-path spanning tree and its `is_exact` / dashed edges are unchanged, and edge
   labels are the field-count difference. No bands, no de-overlap.

2. **Similarity drives the neighbourhood filter.** The per-recipe graph's candidate cut changes
   from a Hamming `max_distance` to a **similarity floor** (`RECIPE_GRAPH_MIN_SIMILARITY`,
   default 0.8, a django-constance setting), with a slider on the page to raise or lower it.
   This is purely about *which* recipes appear, not how they are drawn - both the old
   `max_distance` and the new floor are filters, and the similarity floor is the more meaningful
   one (it weighs how much each field differs and how much it matters). The film-simulation
   network graph is unchanged: it still shows every recipe for the simulation.

3. **Each node shows its closeness.** A node carries its overall `similarity` to the root and
   displays it as a small percentage badge inside the circle - a non-intrusive read on "how
   alike overall", alongside the Hamming ring that shows "how many fields differ". The sidebar
   recipe list shows the same closeness as a coloured chip per row.

4. **The comparison panel leads with closeness.** Selecting a node shows a similarity headline -
   the percentage, the closeness word, and the Identity / Extras split from the two-round score -
   above the field-by-field diff.

5. **The identity/extras weights (ADR 019 A/B) are django-constance settings**
   (`RECIPE_SIMILARITY_IDENTITY_WEIGHT` = 0.7, `RECIPE_SIMILARITY_EXTRAS_WEIGHT` = 0.3), read at
   the application boundary and threaded into the metric, so the closeness shown on nodes, in the
   sidebar, in the panel and in "Related recipes" all agree and can be tuned at runtime.

## Consequences

- The graph stays as readable as it was: Hamming rings spread nodes out, and the structure is
  clear. Similarity rides along as an annotation (the badge, the chips, the panel) and as the
  neighbourhood filter, where it is genuinely better than a field count.
- The per-recipe neighbourhood is now chosen by a floor the user understands and can adjust,
  rather than a fixed field-count cutoff.
- Computing a node's badge needs its similarity to the root (Python `compute_similarity`, cheap
  over the bounded candidate set); the neighbourhood filter runs in the database via
  `annotate_similarity`.
- `RECIPE_GRAPH_MAX_DISTANCE` is retired in favour of `RECIPE_GRAPH_MIN_SIMILARITY`.

This leaves [ADR 002](002-recipe-relationship-graph.md)'s layout and topology in force; it only
replaces that ADR's `max_distance` neighbourhood cut with a similarity floor, and adds the
closeness annotations and panel headline.
