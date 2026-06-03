#!/usr/bin/env python3
"""Generate Figure 1: the Glimmer schema diagram.

Shows the 8 v0.3 entity types as nodes and a pruned set of canonical edge types
as labeled directed edges. The layout follows the two flows the schema encodes:
a left-to-right provenance flow (experiment → dataset → derivative) and an
upward knowledge flow (derivative → finding → publication), with `concept` as
the research-question layer findings and publications point up at.
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
    # Layout: provenance flow along the bottom (experiment → dataset → derivative,
    # with method + standard supporting), knowledge flow rising to the upper right
    # (finding → publication), and `concept` at the top as the research-question
    # layer that experiment, finding, and publication all point up at.
    "experiment":  {"pos": (-6.0,  0.4),  "fill": META_FILL, "text": TEXT_LIGHT, "label": "experiment"},
    "dataset":     {"pos": (-2.7,  0.4),  "fill": DATA_FILL, "text": TEXT_DARK,  "label": "dataset"},
    "derivative":  {"pos": ( 0.8,  0.4),  "fill": DATA_FILL, "text": TEXT_DARK,  "label": "derivative"},
    "method":      {"pos": (-1.0, -2.0),  "fill": META_FILL, "text": TEXT_LIGHT, "label": "method"},
    "standard":    {"pos": (-3.8, -2.0),  "fill": META_FILL, "text": TEXT_LIGHT, "label": "standard"},
    "finding":     {"pos": ( 3.0,  2.0),  "fill": META_FILL, "text": TEXT_LIGHT, "label": "finding"},
    "publication": {"pos": ( 6.0,  2.0),  "fill": META_FILL, "text": TEXT_LIGHT, "label": "publication"},
    "concept":     {"pos": ( 3.0,  4.0),  "fill": META_FILL, "text": TEXT_LIGHT, "label": "concept"},
}

EDGES = [
    # (from, to, label[, label_nudge]) — pruned to one representative canonical
    # edge per relation so labels do not occlude. label_nudge is an optional
    # (dx, dy) to pull a label clear of a neighbour. Full taxonomy in schema.md.
    ("experiment",  "dataset",     "realized-by", (0.0, -0.5)),
    ("experiment",  "concept",     "tests-hypothesis"),
    ("dataset",     "method",      "produced-by"),
    ("method",      "derivative",  "produces"),
    ("derivative",  "dataset",     "derives-from", (0.0, 0.52)),
    ("dataset",     "standard",    "conforms-to"),
    ("derivative",  "finding",     "supports-finding"),
    ("finding",     "concept",     "addresses-concept", (-0.62, 0.0)),
    ("finding",     "publication", "cited-in"),
    ("publication", "concept",     "addresses-concept", (0.55, 0.25)),
]
# Omitted for legibility (all in the textual schema): method↔dataset applies-to,
# method composes/requires-standard, derivative/dataset cited-in, publication
# cites-*/aggregates, standard defines/versions, and the concept→concept family
# (decomposes-into, extends-concept, subsumed-by, competes-with, superseded-by).

def main():
    import math
    fig, ax = plt.subplots(figsize=(13, 7.5))
    ax.set_xlim(-7.8, 8.0)
    ax.set_ylim(-3.2, 5.0)
    ax.set_aspect("equal")
    ax.axis("off")

    # Box half-width auto-sized to the label so text never overflows.
    def half_w(label):
        return 0.105 * len(label) + 0.30
    HALF_H = 0.24

    # Draw nodes
    for nid, attrs in NODES.items():
        x, y = attrs["pos"]
        hw = half_w(attrs["label"])
        box = mpatches.FancyBboxPatch(
            (x - hw, y - HALF_H), 2 * hw, 2 * HALF_H,
            boxstyle="round,pad=0.04,rounding_size=0.08",
            linewidth=1.2, edgecolor="#1A1A1A", facecolor=attrs["fill"], alpha=1.0
        )
        ax.add_patch(box)
        ax.text(x, y, attrs["label"], ha="center", va="center",
                fontsize=11, fontweight="bold", color=attrs["text"])

    # Draw edges
    drawn_pairs = {}
    for edge in EDGES:
        src, dst, label = edge[0], edge[1], edge[2]
        nudge = edge[3] if len(edge) > 3 else (0.0, 0.0)
        sx, sy = NODES[src]["pos"]
        dx, dy = NODES[dst]["pos"]
        # Curve when reverse edge exists to avoid overlap
        key = tuple(sorted([src, dst]))
        rad = 0.0
        if key in drawn_pairs:
            rad = 0.25 if drawn_pairs[key] == 0 else -0.25
        drawn_pairs[key] = drawn_pairs.get(key, 0) + 1

        # shorten endpoints to each box's edge (+ a small margin) so arrowheads
        # land just outside the node rather than under a wide label.
        dxv = dx - sx; dyv = dy - sy
        L = math.sqrt(dxv*dxv + dyv*dyv)
        if L > 0:
            ux, uy = dxv / L, dyv / L
            sx2 = sx + ux * (half_w(NODES[src]["label"]) + 0.10)
            sy2 = sy + uy * (HALF_H + 0.10)
            dx2 = dx - ux * (half_w(NODES[dst]["label"]) + 0.14)
            dy2 = dy - uy * (HALF_H + 0.14)
        else:
            sx2, sy2, dx2, dy2 = sx, sy, dx, dy

        arrow = FancyArrowPatch(
            (sx2, sy2), (dx2, dy2),
            arrowstyle="->,head_width=4,head_length=6",
            linewidth=0.9, color="#444",
            connectionstyle=f"arc3,rad={rad}",
        )
        ax.add_patch(arrow)
        # Edge label: midpoint, nudged off the line and clear of neighbours.
        mx = (sx2 + dx2) / 2 + rad * 0.3 * (dy2 - sy2) + nudge[0]
        my = (sy2 + dy2) / 2 + rad * 0.3 * (sx2 - dx2) + nudge[1]
        ax.text(mx, my, label, fontsize=8, color="#333",
                ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.9))

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
