#!/usr/bin/env python3
"""Score the agent's verdicts vs. human ratings using pairwise Cohen's κ.

Outputs:
  - Per-rater-pair linear-weighted κ matrix (8×8: 7 humans + agent)
  - Mean κ for agent-vs-human pairs
  - Mean κ for human-vs-human pairs
  - Difference + interpretation
  - figures/kappa_matrix.png
"""
import json, sys, os, argparse
from pathlib import Path
from collections import defaultdict
import numpy as np

ROOT = Path(__file__).parent / "training-fsqc-rokb"
CATEGORIES = ["pial", "skull_strip", "wm_seg", "wm_mask", "gm_seg", "intensity_norm", "subcortical"]
HUMANS = ["shady", "melissa", "jackie", "kelly", "rachel", "amanda", "flavius"]

def linear_weighted_kappa(y1, y2, levels=range(6)):
    """Cohen's kappa with linear weights for ordinal data."""
    y1, y2 = np.asarray(y1), np.asarray(y2)
    n = len(y1)
    if n == 0: return None
    levels = list(levels)
    L = len(levels)
    # Build observed confusion matrix
    obs = np.zeros((L, L))
    for a, b in zip(y1, y2):
        obs[levels.index(int(a)), levels.index(int(b))] += 1
    # Linear weights: w_ij = 1 - |i-j| / (L-1)
    w = np.zeros((L, L))
    for i in range(L):
        for j in range(L):
            w[i, j] = 1 - abs(i - j) / (L - 1)
    # Marginals
    row = obs.sum(axis=1) / n
    col = obs.sum(axis=0) / n
    expected = np.outer(row, col) * n
    # κ = 1 - (1 - sum(w*obs)/n) / (1 - sum(w*expected)/n)
    p_o = (w * obs).sum() / n
    p_e = (w * expected).sum() / n
    if p_e >= 1.0: return 1.0 if p_o >= 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)

def load_human_ratings():
    """Read the RO-KB qc-artifacts to extract human ratings.
    Returns: dict {(rater, subject, category): rating}"""
    import re, yaml
    ratings = {}
    qc_dir = ROOT / "qc-artifacts"
    for path in sorted(qc_dir.glob("qc-*.md")):
        m = re.match(r"qc-(\w+)-on-(\w+)\.md", path.name)
        if not m: continue
        rater, subject = m.group(1), m.group(2)
        text = path.read_text()
        if not text.startswith("---\n"): continue
        _, fm, _ = text.split("---\n", 2)
        fm_dict = yaml.safe_load(fm) or {}
        for cat, val in (fm_dict.get("ratings") or {}).items():
            if isinstance(val, int) and 0 <= val <= 5:
                ratings[(rater, subject, cat)] = val
    return ratings

def load_agent_verdicts(verdicts_path):
    with open(verdicts_path) as f:
        data = json.load(f)
    out = {}
    for v in data["verdicts"]:
        if v.get("agent_rating") is None: continue
        out[("agent", v["subject"], v["category"])] = int(v["agent_rating"])
    return out, data["model"], data["condition"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdicts", default=str(Path(__file__).parent / "agent-verdicts.json"))
    ap.add_argument("--fig-out", default=str(Path(__file__).parent.parent / "figures" / "kappa_matrix.png"))
    args = ap.parse_args()

    human_ratings = load_human_ratings()
    agent_ratings, model, condition = load_agent_verdicts(args.verdicts)
    print(f"Loaded {len(human_ratings)} human ratings; {len(agent_ratings)} agent ratings")
    print(f"Agent model: {model}; condition: {condition}\n")

    all_ratings = {**human_ratings, **agent_ratings}
    raters = HUMANS + ["agent"]

    # Build the κ matrix
    kappa_mat = np.full((len(raters), len(raters)), np.nan)
    n_paired = np.zeros((len(raters), len(raters)), dtype=int)
    for i, ra in enumerate(raters):
        for j, rb in enumerate(raters):
            if i == j: continue
            y1, y2 = [], []
            for subject in ["001", "002", "003"]:
                for cat in CATEGORIES:
                    if (ra, subject, cat) in all_ratings and (rb, subject, cat) in all_ratings:
                        y1.append(all_ratings[(ra, subject, cat)])
                        y2.append(all_ratings[(rb, subject, cat)])
            if y1:
                kappa_mat[i, j] = linear_weighted_kappa(y1, y2)
                n_paired[i, j] = len(y1)

    # Print the matrix
    print("Linear-weighted Cohen's κ (pairwise, ordinal):")
    print("  raters:", raters)
    print()
    print(" " * 12 + " ".join(f"{r[:7]:>7s}" for r in raters))
    for i, ra in enumerate(raters):
        cells = []
        for j in range(len(raters)):
            if i == j: cells.append("    .  ")
            elif np.isnan(kappa_mat[i, j]): cells.append("   --  ")
            else: cells.append(f"{kappa_mat[i, j]:+.3f}")
        print(f"  {ra[:10]:>10s} " + " ".join(cells))
    print()

    # Compute summary stats
    agent_idx = raters.index("agent")
    agent_vs_humans = [kappa_mat[agent_idx, j] for j in range(len(raters)) if j != agent_idx and not np.isnan(kappa_mat[agent_idx, j])]
    human_vs_human = []
    for i in range(len(HUMANS)):
        for j in range(len(HUMANS)):
            if i < j and not np.isnan(kappa_mat[i, j]):
                human_vs_human.append(kappa_mat[i, j])

    def stats(arr, label):
        if not arr: return f"{label}: N=0"
        arr = np.array(arr)
        return f"{label}: N={len(arr)} pairs, mean κ={arr.mean():+.3f}, sd={arr.std():.3f}, range=[{arr.min():+.3f}, {arr.max():+.3f}]"

    print(stats(human_vs_human, "Human-vs-human"))
    print(stats(agent_vs_humans, "Agent-vs-human "))
    if human_vs_human and agent_vs_humans:
        delta = np.mean(agent_vs_humans) - np.mean(human_vs_human)
        print(f"Δ (agent − human): {delta:+.3f}")
        within_1sd = abs(delta) <= np.std(human_vs_human)
        print(f"\nArchitectural claim: agent κ within 1 SD of human κ → {'PASS' if within_1sd else 'FAIL'}")

    # Generate figure
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        Path(args.fig_out).parent.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(7, 6))
        masked = np.ma.masked_invalid(kappa_mat)
        im = ax.imshow(masked, vmin=-0.2, vmax=1.0, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(range(len(raters)))
        ax.set_yticks(range(len(raters)))
        ax.set_xticklabels(raters, rotation=45, ha="right")
        ax.set_yticklabels(raters)
        for i in range(len(raters)):
            for j in range(len(raters)):
                if not np.isnan(kappa_mat[i, j]) and i != j:
                    ax.text(j, i, f"{kappa_mat[i,j]:.2f}", ha="center", va="center", fontsize=8)
                elif i == j:
                    ax.text(j, i, "·", ha="center", va="center", fontsize=10, color="grey")
        ax.set_title(f"Pairwise linear-weighted κ — Training-FSQC\nAgent ({model}, {condition})")
        plt.colorbar(im, ax=ax, label="κ")
        plt.tight_layout()
        plt.savefig(args.fig_out, dpi=150, bbox_inches="tight")
        print(f"\nFigure: {args.fig_out}")
    except ImportError:
        print("\n(matplotlib not available; skipping figure)")

if __name__ == "__main__":
    main()
