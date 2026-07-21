"""
topology_cytoscape_html.py — HTML/JS template builder for the Cytoscape.js Network Map.

Split from topology_cytoscape.py (RULE-AH1: 780-line budget) to keep the element
builder and the HTML/JS page generator in separate files.

Exports:
  build_cytoscape_html()       — full self-contained HTML string for QWebEngineView
  build_elements_for_update()  — element list for window.updateTopology() JS calls

Architecture rules:
  • Pure Python — no PyQt imports.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from modules.topology_cytoscape import build_cytoscape_elements

# Mirror of topology_cytoscape._CANVAS_W/_CANVAS_H — reference pixel dimensions
# used in JS template placeholder substitution. Keep in sync if ever changed.
_CANVAS_W = 1400.0
_CANVAS_H = 900.0


# ── Cytoscape.js script loader ────────────────────────────────────────────────

def _cytoscape_script_tag() -> str:
    """Return an inline <script> block with the Cytoscape.js library.

    Checks for the bundled file at assets/js/cytoscape.min.js first.
    Falls back to the CDN for development use when the file is absent.
    """
    candidates = [
        Path(__file__).parent.parent / "assets" / "js" / "cytoscape.min.js",
    ]
    if getattr(sys, "frozen", False):
        candidates.insert(
            0,
            Path(sys._MEIPASS) / "assets" / "js" / "cytoscape.min.js",  # type: ignore[attr-defined]
        )
    for path in candidates:
        if path.exists():
            try:
                src = path.read_text(encoding="utf-8")
                return f"<script>{src}</script>"
            except OSError:
                pass  # non-fatal — fall through to CDN
    # CDN fallback (development only — production should always bundle the file)
    return (
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/'
        'cytoscape/3.30.4/cytoscape.min.js"></script>'
    )


# ── HTML/JS page templates ────────────────────────────────────────────────────
#
# The HTML page is assembled from two Python string constants:
#   _HTML_WRAPPER — static HTML shell with __PLACEHOLDER__ markers
#   _JS_TEMPLATE  — pure JavaScript (no Python format-string escaping needed)
#
# At build time, simple str.replace() swaps the markers for JSON-encoded data.
# This avoids the {{ }} escaping required by str.format() and makes the JS
# readable and maintainable.

_HTML_WRAPPER = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* { box-sizing:border-box; margin:0; padding:0; }
body { background:#F4F4F4; font-family:-apple-system,BlinkMacSystemFont,sans-serif; overflow:hidden; }
#cy { width:100vw; height:100vh; }
#tip {
  position:absolute; display:none; z-index:999; pointer-events:none;
  background:#FFFFFF; border:1px solid #D4D4D4; border-radius:4px;
  padding:6px 10px; font-size:12px; color:#1A1A2E; max-width:220px;
  box-shadow:0 2px 8px rgba(0,0,0,.15); white-space:pre-wrap;
}
</style>
</head>
<body>
<div id="cy"></div>
<div id="tip"></div>
__CYTOSCAPE_SCRIPT__
<script>
__JS_CODE__
</script>
</body>
</html>"""

# Pure JavaScript — no Python format-string escaping.  Placeholders:
#   __ELEMENTS__  → JSON array of Cytoscape elements
#   __LAYOUT__    → JSON string: "preset" | "breadthfirst" | "cose" | …
#   __STYLE__     → JSON array of Cytoscape stylesheet rules
#   __CANVAS_W__  → reference canvas width (number)
#   __CANVAS_H__  → reference canvas height (number)
_JS_TEMPLATE = """\
"use strict";

// ── State ─────────────────────────────────────────────────────────────────────
var cy, qtBridge;
var focusMode      = false;
var changesVisible = false;
var layoutLocked   = false;   // true when user presses "Lock Layout"
var _layoutRunning = false;   // true while a layout animation is active
var _activeLayout  = null;    // handle to the in-flight layout, if any — lets
                               // setPresetPositions() forcibly stop it instead
                               // of being silently dropped by _layoutRunning

// Data injected by Python at HTML-build time
var elements   = __ELEMENTS__;
var layoutName = __LAYOUT__;

// ── QWebChannel bridge ────────────────────────────────────────────────────────
// Injected via QWebEngineScript at document-creation time; guard required
// in case the injection races with page load or is absent in dev mode.
if (typeof QWebChannel !== 'undefined' && typeof qt !== 'undefined') {
  new QWebChannel(qt.webChannelTransport, function(channel) {
    qtBridge = channel.objects.bridge;
  });
}

// ── Layout options factory ────────────────────────────────────────────────────
// gravity on cose is the key anti-drift setting: it applies a centripetal
// force toward the canvas centre of mass and prevents nodes from floating
// rightward when force-directed simulation has no bounding force.
function _makeLayoutOpts(name, animate) {
  var o = {
    name:                        name,
    animate:                     !!animate,
    animationDuration:           400,
    padding:                     60,
    spacingFactor:               1.9,
    nodeDimensionsIncludeLabels: true,
  };
  if (name === 'breadthfirst') {
    o.directed      = true;
    o.roots         = '#__internet__';
    o.grid          = true;   // straight rows per level — internet top, devices bottom
    o.spacingFactor = 1.4;    // enough room for 20+ leaf devices in the bottom row
  }
  if (name === 'cose') {
    o.gravity         = 20;    // gentle centripetal pull — prevents clustering without over-centering
    o.nodeRepulsion   = 2000;  // stronger repulsion — gives each device room to breathe
    o.idealEdgeLength = 90;    // slightly tighter links keep structure readable
    o.edgeElasticity  = 0.45;
    o.numIter         = 500;
    o.coolingFactor   = 0.97;
    o.initialTemp     = 800;
    o.randomize       = false;
  }
  if (name === 'concentric') {
    // 3 clean rings: infrastructure (center) → intermediate nodes → leaf devices (outer)
    o.concentric = function(node) {
      if (node.hasClass('internet') || node.hasClass('gateway') || node.hasClass('modem')) return 3;
      if (node.degree() > 2) return 2;  // mesh nodes / switches (multiple connections)
      return 1;                          // leaf devices (one connection)
    };
    o.levelWidth    = function() { return 1; };
    o.minNodeSpacing = 20;
    o.spacingFactor  = 1.3;
  }
  return o;
}

// ── Infrastructure anchoring ──────────────────────────────────────────────────
// Locks Internet / Gateway / Modem after every layout run so these root nodes
// cannot drift on subsequent physics updates or incremental additions.
function _pinInfrastructure() {
  cy.$('.internet, .gateway, .modem').lock();
}

// ── Initialize Cytoscape ──────────────────────────────────────────────────────
cy = cytoscape({
  container:        document.getElementById('cy'),
  elements:         elements,
  style:            __STYLE__,
  minZoom:          0.05,
  maxZoom:          5.0,
  wheelSensitivity: 0.25,
  layout:           { name: 'preset' },
});

// Run the initial layout algorithm only when no preset positions were provided.
// Preset positions are embedded by Python when the user has a saved layout.
if (layoutName !== 'preset') {
  _layoutRunning = true;
  var _initOpts = _makeLayoutOpts(layoutName, false);
  _initOpts.stop = function() {
    _layoutRunning = false;
    _activeLayout  = null;
    _pinInfrastructure();
    cy.fit(undefined, 50);
  };
  _activeLayout = cy.layout(_initOpts);
  _activeLayout.run();
} else {
  _pinInfrastructure();
  cy.fit(undefined, 50);
}

// ── Events ────────────────────────────────────────────────────────────────────

cy.on('tap', 'node[ip]', function(evt) {
  var ip = evt.target.data('ip');
  if (ip && qtBridge) qtBridge.nodeClicked(ip);
});

// Persist position on drag-end (0–1 normalised to canvas size)
cy.on('dragfree', 'node', function(evt) {
  if (layoutLocked) return;
  var node = evt.target;
  var pos  = node.position();
  var cw   = cy.width()  || __CANVAS_W__;
  var ch   = cy.height() || __CANVAS_H__;
  if (qtBridge) {
    qtBridge.savePosition(
      node.id(),
      (pos.x / cw).toFixed(4),
      (pos.y / ch).toFixed(4)
    );
  }
});

var tip = document.getElementById('tip');
cy.on('mouseover', 'node', function(evt) {
  var d = evt.target.data();
  tip.textContent = d.tip || d.label || '';
  tip.style.display = 'block';
});
cy.on('mouseout', 'node', function() { tip.style.display = 'none'; });
document.getElementById('cy').addEventListener('mousemove', function(e) {
  tip.style.left = (e.clientX + 16) + 'px';
  tip.style.top  = (e.clientY - 10) + 'px';
});

cy.on('tap', function() { if (focusMode) window._applyFocus(); });

// ── Smart positioning for new nodes ──────────────────────────────────────────
// Places new nodes near their parent using a golden-angle spiral (no two nodes
// land on the same position regardless of insertion order).
function _smartPos(parentId, index) {
  var parent = cy.getElementById(parentId);
  if (!parent.length) {
    var angle = (index * 137.508) % 360;
    var r     = 120 + index * 25;
    var rad   = angle * Math.PI / 180;
    return { x: cy.width()  / 2 + r * Math.cos(rad),
             y: cy.height() / 2 + r * Math.sin(rad) };
  }
  var pp    = parent.position();
  var count = Math.max(1, parent.outgoers('node').length);
  var span  = Math.min(160, 35 * count);
  var start = 270 - span / 2;
  var step  = count > 1 ? span / (count - 1) : 0;
  var deg   = start + index * step;
  var rad2  = deg * Math.PI / 180;
  return { x: pp.x + 120 * Math.cos(rad2), y: pp.y + 120 * Math.sin(rad2) };
}

// ── Incremental topology update ───────────────────────────────────────────────
// Called by Python via runJavaScript on every rescan after the first render.
// Preserves all existing node positions — only adds, removes, or updates data.
window.updateTopology = function(elementsJson) {
  if (layoutLocked || _layoutRunning) return;

  var newElems = typeof elementsJson === 'string'
    ? JSON.parse(elementsJson) : elementsJson;

  var newById = {};
  newElems.forEach(function(e) { newById[e.data.id] = e; });

  var existingIds = {};
  cy.elements().forEach(function(e) { existingIds[e.id()] = true; });

  var addedNodeCount = 0;
  var addedNodeIds   = [];

  // Process nodes before edges so edge source/target exist when added
  var nodeElems = newElems.filter(function(e) { return e.group === 'nodes'; });
  var edgeElems = newElems.filter(function(e) { return e.group === 'edges'; });

  nodeElems.concat(edgeElems).forEach(function(el) {
    var id = el.data.id;
    if (existingIds[id]) {
      // Update label/class/data; position is NOT touched (preserves user arrangement)
      var ex = cy.getElementById(id);
      ex.data(el.data);
      if (typeof el.classes === 'string') ex.classes(el.classes);
    } else {
      var toAdd = { group: el.group, data: el.data, classes: el.classes || '' };
      if (el.group === 'nodes') {
        toAdd.position = _smartPos('__gateway__', addedNodeCount++);
        addedNodeIds.push(id);
      }
      try { cy.add(toAdd); } catch (err) { /* skip edges with missing endpoints */ }
    }
  });

  // Remove elements no longer in the scan; exempt locked infrastructure nodes
  cy.elements().forEach(function(e) {
    if (!newById[e.id()]) {
      var isInfra = e.hasClass('internet') || e.hasClass('gateway') || e.hasClass('modem');
      if (!isInfra) cy.remove(e);
    }
  });

  // Keep diff overlay in sync with the current toggle state
  if (changesVisible) {
    cy.elements('.ghost, .removed-edge, .new-edge').removeClass('hidden');
  } else {
    cy.elements('.ghost, .removed-edge, .new-edge').addClass('hidden');
  }

  _pinInfrastructure();

  // For a large batch of new nodes, run a constrained cose to spread them out
  if (addedNodeIds.length >= 6) {
    _runIncrementalLayout(addedNodeIds);
  }
};

// ── Constrained layout for newly added nodes ──────────────────────────────────
// Locks existing nodes so they cannot move; runs cose only on the new nodes.
function _runIncrementalLayout(newIds) {
  var newNodes = cy.nodes().filter(function(n) {
    return newIds.indexOf(n.id()) >= 0;
  });
  if (!newNodes.length) return;
  _layoutRunning = true;
  cy.nodes().not(newNodes).lock();
  _activeLayout = newNodes.layout({
    name: 'cose', animate: false, randomize: false,
    gravity: 80, nodeRepulsion: 5000, numIter: 250, coolingFactor: 0.97,
    stop: function() {
      cy.nodes().unlock();
      _pinInfrastructure();
      _layoutRunning = false;
      _activeLayout  = null;
    }
  });
  _activeLayout.run();
}

// ── Public API ────────────────────────────────────────────────────────────────

window.setLayout = function(name) {
  if (layoutLocked || _layoutRunning) return;
  _layoutRunning = true;
  layoutName = name;
  cy.nodes().unlock();
  var opts = _makeLayoutOpts(name, true);
  opts.stop = function() {
    _layoutRunning = false;
    _pinInfrastructure();
    cy.fit(undefined, 50);
  };
  cy.layout(opts).run();
};

window.fitView = function() { cy.fit(undefined, 50); };

window.resetLayout = function() {
  if (layoutLocked || _layoutRunning) return;
  _layoutRunning = true;
  cy.nodes().unlock();
  var opts = _makeLayoutOpts(layoutName, true);
  opts.stop = function() {
    _layoutRunning = false;
    _pinInfrastructure();
    cy.fit(undefined, 50);
  };
  cy.layout(opts).run();
};

// Freeze / unfreeze all node positions.
// When locked: dragging is disabled and updateTopology is a no-op.
window.lockLayout = function(locked) {
  layoutLocked = locked;
  if (locked) {
    cy.nodes().lock();
  } else {
    cy.nodes().unlock();
    _pinInfrastructure();  // keep infrastructure anchored even when unlocked
  }
};

window.toggleFocus = function(enabled) {
  focusMode = enabled;
  window._applyFocus();
};

window._applyFocus = function() {
  cy.elements().removeClass('faded');
  if (!focusMode) return;
  var sel = cy.nodes(':selected');
  if (!sel.length) return;
  var hood = sel.closedNeighborhood();
  cy.elements().not(hood).addClass('faded');
};

window.toggleChanges = function(show) {
  changesVisible = show;
  var ghosts = cy.elements('.ghost, .removed-edge, .new-edge');
  if (show) { ghosts.removeClass('hidden'); }
  else      { ghosts.addClass('hidden'); }
};

window.exportPng = function() {
  var data = cy.png({ full: true, scale: 2, bg: '#F4F4F4' });
  if (qtBridge) qtBridge.exportPng(data);
};

// Apply Python-computed geometric positions without running a physics layout.
// posMap: { "node_id": {"x": number, "y": number}, ... }
// Nodes absent from posMap keep their current position.
//
// These positions are always authoritative (the caller already decided the
// graph needs a clean reflow), so — unlike setLayout()/resetLayout() — this
// does NOT defer to _layoutRunning. It forcibly stops whatever physics pass
// is in flight instead. This matters because _runIncrementalLayout() kicks
// off an unanimated cose pass for any batch of 6+ new nodes (e.g. mesh nodes
// or devices appearing right after a scan), and Cytoscape's cose layout
// ticks across animation frames internally even with animate:false — so it
// is often still running moments later when network_map_page.py calls this
// right after window.updateTopology(). Deferring to _layoutRunning here
// would silently drop that automatic resync, leaving devices spiraled in
// around the gateway until the user manually re-picks a layout.
window.setPresetPositions = function(posMap) {
  if (layoutLocked) return;
  if (_activeLayout) {
    try { _activeLayout.stop(); } catch (e) { /* already finished */ }
    _activeLayout = null;
  }
  _layoutRunning = false;
  cy.nodes().unlock();
  cy.batch(function() {
    cy.nodes().forEach(function(n) {
      var p = posMap[n.id()];
      if (p && typeof p.x === 'number' && typeof p.y === 'number') {
        n.position({ x: p.x, y: p.y });
      }
    });
  });
  _pinInfrastructure();
  cy.fit(undefined, 50);
};"""


# ── Public build functions ────────────────────────────────────────────────────

def build_cytoscape_html(
    devices: list,
    edges: Optional[list] = None,
    diff: Optional[Any] = None,
    lldp_neighbors: Optional[list] = None,
    segments: Optional[list] = None,
    positions: Optional[Dict[str, Any]] = None,
    gateway_ip: Optional[str] = None,
    gateway_mac: Optional[str] = None,
    mesh_units: Optional[list] = None,
    mesh_enrichment: Optional[dict] = None,
    modem_data: Optional[dict] = None,
    down_ips: Optional[set] = None,
    new_ips: Optional[set] = None,
    initial_layout: str = "breadthfirst",
    bw_by_mac: Optional[Dict[str, float]] = None,
) -> str:
    """Return a complete self-contained HTML string for QWebEngineView.

    The HTML embeds Cytoscape.js (from the local bundle when available),
    a QWebChannel bridge, and all interaction logic.
    """
    result = build_cytoscape_elements(
        devices=devices,
        edges=edges,
        diff=diff,
        lldp_neighbors=lldp_neighbors,
        segments=segments,
        positions=positions,
        gateway_ip=gateway_ip,
        gateway_mac=gateway_mac,
        mesh_units=mesh_units,
        mesh_enrichment=mesh_enrichment,
        modem_data=modem_data,
        down_ips=down_ips,
        new_ips=new_ips,
        bw_by_mac=bw_by_mac,
    )

    # Use preset layout when saved positions exist; run algorithm otherwise
    layout = "preset" if positions else initial_layout

    js_code = (
        _JS_TEMPLATE
        .replace("__ELEMENTS__",  json.dumps(result["elements"]))
        .replace("__LAYOUT__",    json.dumps(layout))
        .replace("__STYLE__",     json.dumps(result["style"]))
        .replace("__CANVAS_W__",  str(_CANVAS_W))
        .replace("__CANVAS_H__",  str(_CANVAS_H))
    )
    return (
        _HTML_WRAPPER
        .replace("__CYTOSCAPE_SCRIPT__", _cytoscape_script_tag())
        .replace("__JS_CODE__",          js_code)
    )


def build_elements_for_update(
    devices: list,
    edges: Optional[list] = None,
    diff: Optional[Any] = None,
    lldp_neighbors: Optional[list] = None,
    segments: Optional[list] = None,
    gateway_ip: Optional[str] = None,
    gateway_mac: Optional[str] = None,
    mesh_units: Optional[list] = None,
    mesh_enrichment: Optional[dict] = None,
    modem_data: Optional[dict] = None,
    down_ips: Optional[set] = None,
    new_ips: Optional[set] = None,
    bw_by_mac: Optional[Dict[str, float]] = None,
) -> list:
    """Build an elements list for an incremental JS topology update.

    Returns the elements without preset positions so Cytoscape's internal
    node positions (including user drag arrangements) are fully preserved.
    New nodes are positioned by the JS _smartPos() function at runtime.
    """
    result = build_cytoscape_elements(
        devices=devices,
        edges=edges,
        diff=diff,
        lldp_neighbors=lldp_neighbors,
        segments=segments,
        positions=None,  # JS owns positions after initial load
        gateway_ip=gateway_ip,
        gateway_mac=gateway_mac,
        mesh_units=mesh_units,
        mesh_enrichment=mesh_enrichment,
        modem_data=modem_data,
        down_ips=down_ips,
        new_ips=new_ips,
        bw_by_mac=bw_by_mac,
    )
    # Strip position keys so Cytoscape does not override user-arranged positions
    return [{k: v for k, v in el.items() if k != "position"} for el in result["elements"]]
