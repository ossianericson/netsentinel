"""
topology_cytoscape_style.py — Cytoscape.js stylesheet builder.

Extracted from topology_cytoscape.py (Audit Cleanup sprint).
All colours reference modules/colours.py constants — no raw hex literals.
"""
from __future__ import annotations

from modules.colours import (
    ACCENT, ACCENT_DARK, ACCENT_PURPLE, AMBER, BORDER,
    GREEN, RED, TEAL, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)


def _build_style() -> list:
    """Return the Cytoscape.js stylesheet list."""
    return [
        # ── Base node ─────────────────────────────────────────────────────────
        {
            "selector": "node",
            "style": {
                "label":              "data(label)",
                "text-valign":        "bottom",
                "text-halign":        "center",
                "text-wrap":          "wrap",
                "text-max-width":     "120px",
                "font-size":          "11px",
                "font-family":        "-apple-system, BlinkMacSystemFont, sans-serif",
                "text-outline-width": "2px",
                "text-outline-color": WHITE,
                "color":              TEXT_PRIMARY,
                "background-color":   TEXT_SECONDARY,
                "width":              "44px",
                "height":             "44px",
                "border-width":       "2px",
                "border-color":       BORDER,
            },
        },
        # ── Risk levels ───────────────────────────────────────────────────────
        {"selector": "node.risk-high",    "style": {"background-color": RED}},
        {"selector": "node.risk-medium",  "style": {"background-color": AMBER}},
        {"selector": "node.risk-low",     "style": {"background-color": ACCENT}},
        {"selector": "node.risk-clean",   "style": {"background-color": GREEN}},
        {"selector": "node.risk-unknown", "style": {"background-color": TEXT_SECONDARY}},
        # ── Segment membership ring (outline around node) ─────────────────────
        {
            "selector": "node[seg_color != '']",
            "style": {
                "outline-color":   "data(seg_color)",
                "outline-width":   "4px",
                "outline-opacity": "0.55",
            },
        },
        # ── Infrastructure nodes ──────────────────────────────────────────────
        {
            "selector": "node.internet",
            "style": {
                "background-color": ACCENT,
                "shape":            "round-rectangle",
                "width":            "60px",
                "height":           "60px",
                "font-size":        "11px",
                "font-weight":      "bold",
                "color":            TEXT_PRIMARY,
            },
        },
        {
            "selector": "node.gateway",
            "style": {
                "background-color": ACCENT,
                "shape":            "round-rectangle",
                "width":            "50px",
                "height":           "50px",
                "border-color":     ACCENT_DARK,
                "border-width":     "3px",
                "font-weight":      "bold",
                "color":            TEXT_PRIMARY,
            },
        },
        {
            "selector": "node.mesh-sat",
            "style": {
                "background-color": ACCENT_PURPLE,
                "shape":            "pentagon",
                "width":            "44px",
                "height":           "44px",
                "color":            TEXT_PRIMARY,
            },
        },
        {
            "selector": "node.modem",
            "style": {
                "background-color": GREEN,
                "shape":            "round-rectangle",
                "width":            "44px",
                "height":           "44px",
                "color":            TEXT_PRIMARY,
            },
        },
        {
            "selector": "node.infrastructure",
            "style": {
                "background-color": TEAL,
                "shape":            "rectangle",
                "width":            "40px",
                "height":           "40px",
                "color":            TEXT_PRIMARY,
            },
        },
        {
            "selector": "node.lldp-leaf",
            "style": {
                "background-color": TEAL,
                "shape":            "diamond",
                "width":            "36px",
                "height":           "36px",
                "color":            TEXT_PRIMARY,
            },
        },
        # ── Status overlays ───────────────────────────────────────────────────
        {
            "selector": "node.status-down",
            "style": {"border-color": RED, "border-width": "3px"},
        },
        {
            "selector": "node.new-device",
            "style": {"border-color": TEAL, "border-width": "3px"},
        },
        # ── Diff: ghost (removed) nodes ───────────────────────────────────────
        {
            "selector": "node.ghost",
            "style": {
                "background-color": TEXT_SECONDARY,
                "opacity":          "0.3",
                "border-style":     "dashed",
                "border-color":     TEXT_SECONDARY,
            },
        },
        # ── Focus mode (faded) ────────────────────────────────────────────────
        {
            "selector": "node.faded, edge.faded",
            "style": {"opacity": "0.15"},
        },
        # ── Selected node highlight ───────────────────────────────────────────
        {
            "selector": "node:selected",
            "style": {
                "border-color":     ACCENT,
                "border-width":     "3px",
                "overlay-color":    ACCENT,
                "overlay-padding":  "6px",
                "overlay-opacity":  "0.1",
            },
        },
        # ── Traffic overlay ───────────────────────────────────────────────────
        {
            "selector": "node.traffic-high",
            "style": {
                "border-color":     RED,
                "border-width":     "4px",
                "shadow-blur":      "12px",
                "shadow-color":     RED,
                "shadow-offset-x":  "0px",
                "shadow-offset-y":  "0px",
                "shadow-opacity":   "0.55",
            },
        },
        {
            "selector": "node.traffic-medium",
            "style": {
                "border-color":    AMBER,
                "border-width":    "3px",
                "shadow-blur":     "8px",
                "shadow-color":    AMBER,
                "shadow-offset-x": "0px",
                "shadow-offset-y": "0px",
                "shadow-opacity":  "0.4",
            },
        },
        {
            "selector": "node.traffic-low",
            "style": {
                "border-color": GREEN,
                "border-width": "3px",
            },
        },
        # ── Hidden (Show Changes toggle) ──────────────────────────────────────
        {"selector": ".hidden", "style": {"display": "none"}},
        # ── Base edge ─────────────────────────────────────────────────────────
        {
            "selector": "edge",
            "style": {
                "width":              "1.5px",
                "line-color":         BORDER,
                "curve-style":        "bezier",
                "target-arrow-shape": "none",
            },
        },
        # ── Edge status / type classes ────────────────────────────────────────
        {"selector": "edge.status-up",      "style": {"line-color": GREEN, "width": "2px"}},
        {"selector": "edge.status-degraded","style": {"line-color": AMBER, "width": "2.5px"}},
        {"selector": "edge.status-down",    "style": {"line-color": RED, "width": "2.5px"}},
        {
            "selector": "edge.lldp-edge",
            "style": {"line-color": TEAL, "width": "2.5px"},
        },
        {
            "selector": "edge.mesh-edge",
            "style": {"line-color": ACCENT_PURPLE, "width": "2px", "line-style": "dashed"},
        },
        {
            "selector": "edge.new-edge",
            "style": {
                "line-color": GREEN, "width": "2px",
                "line-style": "dashed",
            },
        },
        {
            "selector": "edge.removed-edge",
            "style": {
                "line-color": RED, "width": "2px",
                "line-style": "dotted",
            },
        },
    ]
