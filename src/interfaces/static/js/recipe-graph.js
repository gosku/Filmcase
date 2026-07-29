/**
 * Radial recipe graph, shared by the film-simulation network and the per-recipe
 * neighbourhood pages.
 *
 * Both pages render the same shortest-path spanning tree: the root sits at the
 * centre and a node's ring is its Hamming distance from the root, so the edge
 * distances along a root-to-node path add up to that ring number. Edges whose
 * data carries is_exact === false are the exception and are drawn dashed.
 *
 * The sidebar recipe list and the comparison panel are rendered server side and
 * swapped in as HTML, so their markup lives in Django templates only.
 *
 * Usage:
 *
 *   var graph = RecipeGraph.init({
 *     containerId: "cy",
 *     elements: [...],
 *     rootId: 12,
 *     rootLabel: "My Provia",
 *     onSelectedGraphRequested: function (nodeId) { ... },  // optional
 *     onNamedOnlyChanged: function (namedOnly) { ... }      // optional
 *   });
 *
 *   graph.replaceGraph({
 *     elements: [...], rootId: 5, rootLabel: "...",
 *     sidebarHtml: "...", panelHtml: "..."
 *   });
 */
window.RecipeGraph = (function () {
  "use strict";

  var NODE_COLOR = "#334155";
  var NODE_BORDER_COLOR = "#111827";
  var ROOT_COLOR = "#ef4444";
  var ROOT_BORDER_COLOR = "#dc2626";
  var EDGE_COLOR_NEAR = "#1e293b";
  var EDGE_COLOR_FAR = "#94a3b8";
  var PATH_COLOR = "#ef4444";
  var CANVAS_COLOR = "#f5f5f5";

  // The compared node wears an accent ring, matching the sidebar legend's
  // "Selected to compare" swatch.
  var SELECTED_BORDER_COLOR = "#ef4444";
  var SELECTED_BORDER_WIDTH = 3;
  var BASE_BORDER_WIDTH = 1.5;

  var MIN_NODE_SIZE = 14;
  var MAX_NODE_SIZE = 80;
  var MIN_ROOT_SIZE = 32;

  var RING_SPACING = 45;
  // Keeps the innermost ring clear of the root node itself.
  var RING_OFFSET = 60;

  // A label is placed to the side of its node only once the node is far enough
  // off-axis; nearer the axis it is centred instead.
  var LABEL_AXIS_THRESHOLD = 0.4;
  var LABEL_GAP = 6;

  function isNodeElement(element) {
    return element.data && element.data.source === undefined;
  }

  function isEdgeElement(element) {
    return element.data && element.data.source !== undefined;
  }

  /* ------------------------------------ */
  /* Node sizing                          */
  /* ------------------------------------ */

  /**
   * The image count that maps to MAX_NODE_SIZE.
   *
   * The root is deliberately left out. It is usually the most-used recipe by a
   * wide margin, so letting it set the scale flattened everything else: with a
   * root on 2,444 images and the next recipe on 283, all 52 remaining Provia
   * recipes landed within 7.6px of each other. The root does not need the help,
   * being red, centred and floored at MIN_ROOT_SIZE.
   */
  function sizingMaxImageCount(elements, rootId) {
    var counts = elements
      .filter(isNodeElement)
      .filter(function (element) { return String(element.data.id) !== rootId; })
      .map(function (element) { return element.data.image_count || 0; });
    return Math.max.apply(null, counts.concat([1]));
  }

  /**
   * Size a node so its *area* is proportional to its image count, which is what
   * the eye actually compares between circles. Scaling the diameter directly
   * would overstate the busy recipes and flatten the rest.
   *
   * Counts above *scaleMax* clamp to the largest size; only the root can exceed
   * it, since it is excluded from the scale.
   */
  function sizeForImageCount(count, scaleMax) {
    var ratio = Math.min(count, scaleMax) / scaleMax;
    return MIN_NODE_SIZE + Math.sqrt(ratio) * (MAX_NODE_SIZE - MIN_NODE_SIZE);
  }

  /* ------------------------------------ */
  /* Radial layout                        */
  /* ------------------------------------ */

  /**
   * Compute a position per node before Cytoscape renders, so the built-in
   * "preset" layout can be used and no layout plugin is needed.
   *
   * Each subtree gets an angular slice proportional to its leaf count and each
   * node sits at the midpoint of its own slice. Because a child's slice is
   * always a subdivision of its parent's, edges point strictly outward and
   * never cross the centre.
   */
  function buildRadialPositions(elements, rootId) {
    var rootKey = String(rootId);
    var nodeDistance = {};
    var children = {};

    elements.forEach(function (element) {
      if (isNodeElement(element)) {
        var id = String(element.data.id);
        nodeDistance[id] = element.data.distance || 0;
        children[id] = [];
      }
    });
    elements.forEach(function (element) {
      if (isEdgeElement(element)) {
        var source = String(element.data.source);
        var target = String(element.data.target);
        if (children[source]) {
          children[source].push(target);
        }
      }
    });

    var leafCount = {};
    function countLeaves(id) {
      if (leafCount[id] !== undefined) {
        return leafCount[id];
      }
      var kids = children[id] || [];
      if (kids.length === 0) {
        leafCount[id] = 1;
        return 1;
      }
      var total = 0;
      kids.forEach(function (kid) { total += countLeaves(kid); });
      leafCount[id] = total;
      return total;
    }
    countLeaves(rootKey);

    var positions = {};
    function place(id, startAngle, endAngle) {
      var angle = (startAngle + endAngle) / 2;
      var distance = nodeDistance[id] || 0;
      var radius = distance * RING_SPACING + (distance ? RING_OFFSET : 0);
      positions[id] = {x: radius * Math.cos(angle), y: radius * Math.sin(angle)};

      var cursor = startAngle;
      (children[id] || []).forEach(function (kid) {
        var end = cursor + (leafCount[kid] / leafCount[id]) * (endAngle - startAngle);
        place(kid, cursor, end);
        cursor = end;
      });
    }
    place(rootKey, 0, 2 * Math.PI);
    return positions;
  }

  function makePresetLayout(positions, onStop) {
    return {
      name: "preset",
      positions: function (node) { return positions[node.data("id")]; },
      fit: true,
      padding: 60,
      animate: true,
      animationDuration: 600,
      stop: onStop || function () {},
    };
  }

  /* ------------------------------------ */
  /* Styles                               */
  /* ------------------------------------ */

  var EDGE_STYLES = [
    {
      selector: "edge[distance = 1]",
      style: {
        "line-color": EDGE_COLOR_NEAR,
        "line-style": "solid",
        "opacity": 0.75,
        "width": 1.5,
      },
    },
    {
      selector: "edge[distance > 1]",
      style: {
        "line-color": EDGE_COLOR_FAR,
        "line-style": "solid",
        "opacity": 0.45,
        "width": 1,
        "label": "data(distanceLabel)",
        "font-size": 9,
        "color": EDGE_COLOR_FAR,
        "text-background-color": CANVAS_COLOR,
        "text-background-opacity": 1,
        "text-background-padding": "2px",
      },
    },
    // Fallback attachments: the edge distances along this node's path do not sum
    // to its ring number, so the edge is drawn dashed to say so.
    {
      selector: "edge[?is_exact_false]",
      style: {
        "line-style": "dashed",
      },
    },
  ];

  var BASE_STYLE = [
    {
      selector: "node",
      style: {
        "label": "data(label)",
        "text-valign": "bottom",
        "text-margin-y": 4,
        "font-size": 11,
        "color": "#555555",
        "text-outline-color": CANVAS_COLOR,
        "text-outline-width": 2,
        "border-width": 1.5,
        "background-color": NODE_COLOR,
        "border-color": NODE_BORDER_COLOR,
        "width": MIN_NODE_SIZE,
        "height": MIN_NODE_SIZE,
      },
    },
    {
      selector: "edge",
      style: {
        "width": 1,
        "line-color": EDGE_COLOR_FAR,
        "line-style": "solid",
        "curve-style": "bezier",
        "opacity": 0.45,
      },
    },
  ].concat(EDGE_STYLES).concat([
    {
      selector: "node:selected",
      style: {
        "border-width": SELECTED_BORDER_WIDTH,
        "border-color": SELECTED_BORDER_COLOR,
      },
    },
  ]);

  /**
   * Cytoscape selectors cannot test for a false boolean, so mirror is_exact
   * into a truthy marker the stylesheet can match on.
   */
  function markInexactEdges(elements) {
    elements.forEach(function (element) {
      if (isEdgeElement(element) && element.data.is_exact === false) {
        element.data.is_exact_false = true;
      }
    });
    return elements;
  }

  /* ------------------------------------ */
  /* Controller                           */
  /* ------------------------------------ */

  function init(config) {
    var container = document.getElementById(config.containerId || "cy");
    var elements = markInexactEdges(config.elements || []);

    // Held as a string throughout: Cytoscape node ids are strings, while the
    // server sends the root as a number.
    var rootId = config.rootId === null || config.rootId === undefined
      ? null
      : String(config.rootId);
    var rootLabel = config.rootLabel || "";
    var selectedId = null;
    var selectedLabel = "";
    var highlightedEdges = [];
    // The node currently wearing the accent ring, so it can be unrung later.
    var markedNodeId = null;

    // The panel's markup is rendered server side; this only swaps it and binds
    // the controls it contains.
    var panelEl = document.getElementById("recipe-card");

    var tooltip = {
      root: document.getElementById("tooltip"),
      label: document.getElementById("tooltip-label"),
      meta: document.getElementById("tooltip-meta"),
    };

    var cy = cytoscape({
      container: container,
      elements: elements,
      wheelSensitivity: 0.15,
      style: BASE_STYLE,
      layout: makePresetLayout(buildRadialPositions(elements, rootId), applyRadialLabels),
    });

    /* --- Labels and node styling --- */

    /**
     * Push each label outward from the centre so it never sits on top of its
     * own node or the ring inside it.
     */
    function applyRadialLabels() {
      if (rootId === null) {
        return;
      }
      var centre = cy.getElementById(rootId).position();
      cy.nodes().forEach(function (node) {
        var position = node.position();
        var dx = position.x - centre.x;
        var dy = position.y - centre.y;
        var length = Math.sqrt(dx * dx + dy * dy);
        if (length < 1) {
          node.style({
            "text-valign": "bottom",
            "text-halign": "center",
            "text-margin-x": 0,
            "text-margin-y": 4,
          });
          return;
        }
        var cos = dx / length;
        var sin = dy / length;
        var offAxisX = Math.abs(cos) >= LABEL_AXIS_THRESHOLD;
        var offAxisY = Math.abs(sin) >= LABEL_AXIS_THRESHOLD;
        node.style({
          "text-halign": offAxisX ? (cos > 0 ? "right" : "left") : "center",
          "text-valign": offAxisY ? (sin > 0 ? "bottom" : "top") : "center",
          "text-margin-x": offAxisX ? cos * LABEL_GAP : 0,
          "text-margin-y": offAxisY ? sin * LABEL_GAP : 0,
        });
      });
    }

    /**
     * Ring the compared node in the accent colour and unring the previous one.
     *
     * Done explicitly rather than through the `node:selected` stylesheet rule
     * because applyNodeStyles sets border-color inline, and inline styles win
     * over the stylesheet in Cytoscape.
     */
    function markSelectedNode(nodeId) {
      if (markedNodeId !== null) {
        var previous = cy.getElementById(markedNodeId);
        if (previous.nonempty()) {
          var wasRoot = rootId !== null && markedNodeId === rootId;
          previous.style({
            "border-color": wasRoot ? ROOT_BORDER_COLOR : NODE_BORDER_COLOR,
            "border-width": BASE_BORDER_WIDTH,
          });
        }
      }
      markedNodeId = nodeId;
      if (nodeId === null) {
        return;
      }
      var node = cy.getElementById(nodeId);
      if (node.nonempty()) {
        node.style({
          "border-color": SELECTED_BORDER_COLOR,
          "border-width": SELECTED_BORDER_WIDTH,
        });
      }
    }

    function applyNodeStyles(currentElements) {
      var scaleMax = sizingMaxImageCount(currentElements, rootId);
      cy.nodes().forEach(function (node) {
        var isRoot = rootId !== null && node.data("id") === rootId;
        var size = sizeForImageCount(node.data("image_count") || 0, scaleMax);
        node.style({
          "background-color": isRoot ? ROOT_COLOR : NODE_COLOR,
          "border-color": isRoot ? ROOT_BORDER_COLOR : NODE_BORDER_COLOR,
          "width": isRoot ? Math.max(size, MIN_ROOT_SIZE) : size,
          "height": isRoot ? Math.max(size, MIN_ROOT_SIZE) : size,
        });
      });
    }

    /* --- Panel --- */

    /**
     * Replace the panel's contents and rebind the controls inside it.
     *
     * The markup comes from the server so the two panel states have a single
     * source; this only wires up what the fragment cannot do for itself.
     */
    function setPanelHtml(html) {
      if (!panelEl) {
        return;
      }
      panelEl.innerHTML = html;
      bindPanelControls();
    }

    function loadPanel(path) {
      if (!panelEl) {
        return;
      }
      panelEl.classList.add("graph-panel--loading");
      fetch("/recipes/graph/comparison/?ids=" + path.join(","))
        .then(function (response) { return response.text(); })
        .then(function (html) {
          panelEl.classList.remove("graph-panel--loading");
          setPanelHtml(html);
        });
    }

    function bindPanelControls() {
      var showGraphBtn = document.getElementById("card-show-graph-btn");
      if (showGraphBtn && config.onSelectedGraphRequested) {
        showGraphBtn.onclick = function () {
          config.onSelectedGraphRequested(selectedId);
        };
      }

      var compareBtn = document.getElementById("card-compare-btn");
      if (compareBtn && window.RecipeCompareOverlay) {
        compareBtn.onclick = function () {
          window.RecipeCompareOverlay.open({
            leftRecipeId: rootId,
            leftTitle: rootLabel,
            rightRecipeId: selectedId,
            rightTitle: selectedLabel,
          });
        };
      }

      bindPropertyFilter();
    }

    /**
     * The All / Only changes filter hides unchanged rows, and any group left
     * with nothing to show, without going back to the server.
     */
    function bindPropertyFilter() {
      var filter = document.getElementById("property-filter");
      if (!filter) {
        return;
      }
      filter.addEventListener("click", function (event) {
        var option = event.target.closest(".segmented-toggle__option");
        if (!option) {
          return;
        }
        var changesOnly = option.getAttribute("data-properties") === "changes";
        filter.querySelectorAll(".segmented-toggle__option").forEach(function (el) {
          el.classList.toggle(
            "segmented-toggle__option--active",
            (el.getAttribute("data-properties") === "changes") === changesOnly,
          );
        });
        var body = document.getElementById("graph-panel-body");
        if (body) {
          body.classList.toggle("graph-panel__body--changes-only", changesOnly);
        }
      });
    }

    /* --- Path finding and highlighting --- */

    function findPath(targetId) {
      if (rootId === null || rootId === targetId) {
        return [rootId];
      }
      var parentOf = {};
      var visited = {};
      visited[rootId] = true;
      var queue = [rootId];

      while (queue.length > 0) {
        var current = queue.shift();
        var neighbours = cy.getElementById(current).connectedEdges().map(function (edge) {
          return edge.data("source") === current ? edge.data("target") : edge.data("source");
        });
        for (var i = 0; i < neighbours.length; i++) {
          var neighbour = neighbours[i];
          if (visited[neighbour]) {
            continue;
          }
          visited[neighbour] = true;
          parentOf[neighbour] = current;
          if (neighbour === targetId) {
            var path = [];
            var node = targetId;
            while (node !== undefined) {
              path.unshift(node);
              node = parentOf[node];
            }
            return path;
          }
          queue.push(neighbour);
        }
      }
      return [rootId, targetId];
    }

    function resetEdgeStyle(edge) {
      if (edge.data("distance") === 1) {
        edge.style({"line-color": EDGE_COLOR_NEAR, "width": 1.5, "opacity": 0.75});
      } else {
        edge.style({"line-color": EDGE_COLOR_FAR, "width": 1, "opacity": 0.45});
      }
    }

    function clearPathHighlight() {
      highlightedEdges.forEach(resetEdgeStyle);
      highlightedEdges = [];
    }

    function highlightPath(path) {
      clearPathHighlight();
      for (var i = 0; i < path.length - 1; i++) {
        cy.getElementById(path[i]).edgesWith(cy.getElementById(path[i + 1])).forEach(function (edge) {
          edge.style({"line-color": PATH_COLOR, "width": 3, "opacity": 1});
          highlightedEdges.push(edge);
        });
      }
    }

    /* --- Tooltip --- */

    cy.on("mouseover", "node", function (event) {
      var node = event.target;
      var imageCount = node.data("image_count") || 0;
      var isRoot = rootId !== null && node.data("id") === rootId;
      tooltip.label.textContent = node.data("label");
      tooltip.meta.innerHTML =
        imageCount + " image" + (imageCount === 1 ? "" : "s") +
        (isRoot ? "<br><em>reference recipe</em>" : "");
      tooltip.root.style.display = "block";
    });

    cy.on("mousemove", "node", function (event) {
      tooltip.root.style.left = (event.originalEvent.clientX + 14) + "px";
      tooltip.root.style.top = (event.originalEvent.clientY + 14) + "px";
    });

    cy.on("mouseout", "node", function () {
      tooltip.root.style.display = "none";
    });

    /* --- Sidebar --- */

    var sidebarBody = document.getElementById("graph-sidebar-body");

    /**
     * Highlight the row for the compared recipe, or fall back to the reference
     * row when nothing is compared.
     */
    function markActiveRow(nodeId) {
      if (!sidebarBody) {
        return;
      }
      sidebarBody.querySelectorAll(".graph-recipe-list__row").forEach(function (row) {
        var isActive = nodeId !== null && row.getAttribute("data-recipe-id") === nodeId;
        row.classList.toggle("graph-recipe-list__row--active", isActive);
      });
    }

    function setLegendComparing(comparing) {
      if (!sidebarBody) {
        return;
      }
      var legend = sidebarBody.querySelector(".graph-legend");
      if (legend) {
        legend.classList.toggle("graph-legend--no-comparison", !comparing);
      }
    }

    // Delegated so the handlers survive the sidebar being replaced wholesale.
    if (sidebarBody) {
      sidebarBody.addEventListener("click", function (event) {
        var row = event.target.closest(".graph-recipe-list__row");
        if (row) {
          selectRecipe(row.getAttribute("data-recipe-id"));
        }
      });

      sidebarBody.addEventListener("change", function (event) {
        if (event.target.id === "named-only-toggle" && config.onNamedOnlyChanged) {
          config.onNamedOnlyChanged(event.target.checked);
        }
      });
    }

    /* --- Selection --- */

    /**
     * Select a recipe to compare against the reference. The single entry point
     * for both a graph node click and a sidebar row click, so the two stay in
     * step by construction.
     */
    function selectRecipe(nodeId) {
      var node = cy.getElementById(nodeId);
      if (node.empty()) {
        return;
      }
      if (rootId !== null && nodeId === rootId) {
        clearSelection();
        return;
      }

      selectedId = nodeId;
      selectedLabel = node.data("label");

      var path = findPath(nodeId);
      highlightPath(path);
      markSelectedNode(nodeId);
      markActiveRow(nodeId);
      setLegendComparing(true);
      loadPanel(path);
    }

    /** Drop back to showing the reference recipe on its own. */
    function clearSelection() {
      selectedId = null;
      selectedLabel = "";
      clearPathHighlight();
      markSelectedNode(null);
      markActiveRow(null);
      setLegendComparing(false);
      if (rootId !== null) {
        loadPanel([rootId]);
      }
    }

    cy.on("click", "node", function (event) {
      selectRecipe(event.target.data("id"));
    });

    /* --- Public surface --- */

    /**
     * Swap the whole graph in place, keeping the viewport and the panel in sync.
     * Used both by the film-simulation filter and by re-rooting onto a selected
     * recipe.
     */
    function replaceGraph(next) {
      var nextElements = markInexactEdges(next.elements || []);
      rootId = next.rootId === null || next.rootId === undefined
        ? null
        : String(next.rootId);
      rootLabel = next.rootLabel || "";
      selectedId = null;
      selectedLabel = "";
      highlightedEdges = [];
      // The old nodes are about to go, so there is nothing left to unring.
      markedNodeId = null;

      cy.elements().remove();
      cy.add(nextElements);
      applyNodeStyles(nextElements);
      cy.layout(makePresetLayout(buildRadialPositions(nextElements, rootId), applyRadialLabels)).run();

      // The recipe list, its counts and the panel all belong to the graph that
      // was just loaded, so they are re-rendered server side and swapped in
      // together with it.
      if (sidebarBody && next.sidebarHtml !== undefined) {
        sidebarBody.innerHTML = next.sidebarHtml;
      }
      if (next.panelHtml !== undefined) {
        setPanelHtml(next.panelHtml);
      }

      markActiveRow(null);
      setLegendComparing(false);
    }

    applyNodeStyles(elements);
    bindPanelControls();
    setLegendComparing(false);

    return {
      cy: cy,
      replaceGraph: replaceGraph,
      selectRecipe: selectRecipe,
      getRootId: function () { return rootId; },
    };
  }

  return {init: init};
})();
