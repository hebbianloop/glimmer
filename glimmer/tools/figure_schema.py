#!/usr/bin/env python3
"""Generate Figure 1: the Glimmer schema diagram.

Shows the 7 entity types as nodes and canonical edge types as labeled directed edges.
Output: figures/schema_diagram.pdf (for inclusion in the LaTeX paper)
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
import networkx as nx
from pathlib import Path

OUT = Path(__file__).parent.parent / "figures" / "schema_diagram.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

# Entity types. Monochromatic — distinguish by node shape/style, not by color.
# Two-tone scheme: data nodes (dataset, derivative) are dark grey; everything else is light grey.
DATA_FILL  = "#3B3B3B"
META_FILL  = "#D0D0D0"
TEXT_DARK  = "#FFFFFF"
TEXT_LIGHT = "#1A1A1A"

NODES = {
    # Layout: dataset at the center, method/derivative on left column, qc-rater on right column,
    # publication and standard at top/bottom to avoid edge crossings through the data nodes.
    "dataset":     {"pos": (0.0,  0.0),  "fill": DATA_FILL, "text": TEXT_DARK,  "label": "dataset"},
    "method":      {"pos": (-2.8, 0.0),  "fill": META_FILL, "text": TEXT_LIGHT, "label": "method"},
    "derivative":  {"pos": (-1.4, 1.6),  "fill": DATA_FILL, "text": TEXT_DARK,  "label": "derivative"},
    "qc-artifact": {"pos": (1.6,  0.0),  "fill": META_FILL, "text": TEXT_LIGHT, "label": "qc-artifact"},
    "rater":       {"pos": (3.2,  0.0),  "fill": META_FILL, "text": TEXT_LIGHT, "label": "rater"},
    "standard":    {"pos": (0.0, -1.8),  "fill": META_FILL, "text": TEXT_LIGHT, "label": "standard"},
    "publication": {"pos": (0.0,  2.6),  "fill": META_FILL, "text": TEXT_LIGHT, "label": "publication"},
}

EDGES = [
    # (from, to, label) — pruned to the canonical edge set so labels do not occlude.
    ("dataset",     "method",      "produced-by"),
    ("method",      "derivative",  "produces"),
    ("derivative",  "dataset",     "derives-from"),
    ("dataset",     "qc-artifact", "has-qc-artifact"),
    ("qc-artifact", "rater",       "issued-by"),
    ("rater",       "standard",    "trained-on"),
    ("dataset",     "standard",    "conforms-to"),
    ("publication", "dataset",     "cites"),
]
# Note: cites-method / cites-derivative omitted from the schematic for legibility;
# they're declared in the textual schema (Section 2) but every publication edge
# is collapsed to "cites" in the figure to avoid the three-way overlap on the publication node.

def main():
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.set_xlim(-3.2, 5.0)
    ax.set_ylim(-2.2, 3.2)
    ax.set_aspect("equal")
    ax.axis("off")

    # Draw nodes
    for nid, attrs in NODES.items():
        x, y = attrs["pos"]
        box = mpatches.FancyBboxPatch(
            (x - 0.5, y - 0.18), 1.0, 0.36,
            boxstyle="round,pad=0.04,rounding_size=0.08",
            linewidth=1.2, edgecolor="#1A1A1A", facecolor=attrs["fill"], alpha=1.0
        )
        ax.add_patch(box)
        ax.text(x, y, attrs["label"], ha="center", va="center",
                fontsize=10.5, fontweight="bold", color=attrs["text"])

    # Draw edges
    drawn_pairs = {}
    for src, dst, label in EDGES:
        sx, sy = NODES[src]["pos"]
        dx, dy = NODES[dst]["pos"]
        # Curve when reverse edge exists to avoid overlap
        key = tuple(sorted([src, dst]))
        rad = 0.0
        if key in drawn_pairs:
            rad = 0.25 if drawn_pairs[key] == 0 else -0.25
        drawn_pairs[key] = drawn_pairs.get(key, 0) + 1

        # shorten endpoints so arrows don't overlap node boxes
        import math
        dxv = dx - sx; dyv = dy - sy
        L = math.sqrt(dxv*dxv + dyv*dyv)
        shrink = 0.55
        if L > 0:
            ux, uy = dxv / L, dyv / L
            sx2, sy2 = sx + ux * shrink, sy + uy * shrink
            dx2, dy2 = dx - ux * shrink, dy - uy * shrink
        else:
            sx2, sy2, dx2, dy2 = sx, sy, dx, dy

        arrow = FancyArrowPatch(
            (sx2, sy2), (dx2, dy2),
            arrowstyle="->,head_width=4,head_length=6",
            linewidth=0.9, color="#444",
            connectionstyle=f"arc3,rad={rad}",
        )
        ax.add_patch(arrow)
        # Edge label
        mx, my = (sx2 + dx2) / 2 + rad * 0.3 * (dy2 - sy2), (sy2 + dy2) / 2 + rad * 0.3 * (sx2 - dx2)
        # adjust label position perpendicular for curved edges
        ax.text(mx, my, label, fontsize=7.5, color="#333",
                ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.85))

    ax.set_title("Glimmer schema: typed entities and canonical edges",
                 fontsize=12, pad=10)
    plt.tight_layout()
    plt.savefig(OUT, bbox_inches="tight", dpi=200)
    # Also a PNG for previewing
    plt.savefig(OUT.with_suffix(".png"), bbox_inches="tight", dpi=200)
    print(f"Wrote {OUT}")
    print(f"Wrote {OUT.with_suffix('.png')}")

if __name__ == "__main__":
    main()
