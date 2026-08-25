#!/usr/bin/env python3
"""Figures for Experiment 2 — the tradeoff frontier.

Two figures per state, because the finding has two halves and one chart cannot
carry both.

**The verdict matrix.** Every ordered pair of criteria, coloured by what the
three tests concluded. This is a categorical grid, so it is a grid: no
interpolation, no continuous colour ramp implying a magnitude the verdict does
not have. Read down a row for "what does prioritising this criterion cost".

The matrix is drawn as a **triangle, not a square**, and this is the point of it.
Two of the three tests are mathematically symmetric in (A, B) -- Spearman rho by
definition, and the joint top-tercile rate because both indicator sets enter it
the same way -- so only the conditional test can distinguish direction. Drawing
all 42 ordered cells invites a reader to count 42 findings when Colorado has 21
relationships, and every apparent asymmetry would be manufactured by the one test
the audit found carrying every defect. The lower triangle therefore shows the
relationship, and a cell whose two directions disagree is marked rather than
silently averaged or silently doubled.

**The frontier panels.** For the pairs the law actually argues about, the
ensemble as a density with its Pareto frontier drawn on top. This is the chart
that shows the *shape* behind the verdict: whether the cloud is one blob, whether
a criterion is secretly discrete, where the extremes sit. The axes are always
goodness -- larger is better on both -- so up and to the right is unambiguously
better.

The frontier line is drawn but deliberately not trusted. Its points are the
non-dominated draws, so once it leaves the dense part of the cloud every point on
it is a single plan, and it will fall steeply on a few extreme draws even when the
bulk shows nothing. Colorado's compactness-against-population-equality panel is
exactly that: a dramatic-looking frontier over an ensemble whose top 0.1% of
compactness costs about 3% of population spread. The verdict comes from the three
tests, which are bulk and tail-quantile tests; the line is there to show what the
tests are summarising, not to be read as a result.

No verdict is drawn without its sample size, and a pair no test could decide is
drawn in the degenerate colour rather than left blank, so that "we could not
tell" never reads as "no tradeoff".
"""
from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import experiment_2_tradeoffs as X    # noqa: E402

OUT = ROOT / "docs" / "figures"
RESULTS = ROOT / "docs" / "experiment-2" / "experiment-2-results.json"
RESULTS_V2 = ROOT / "docs" / "experiment-2" / "experiment-2-results-v2.json"

INK, MUTED, SURFACE = "#1a1a1a", "#6b6b6b", "#ffffff"
VERDICT_COLOUR = {
    "none": "#e8eef5",        # the expected result; deliberately the quietest
    "weak": "#f0c987",
    "strong": "#c1583f",
    "degenerate": "#d6d6d6",
}
HUE, FRONTIER = "#4a6fa5", "#c1583f"

#: The pairs redistricting law actually argues about, in the order it argues them.
HEADLINE_PAIRS = [
    ("compactness_pp", "fairness_eg"),
    ("compactness_pp", "county_integrity"),
    ("county_integrity", "fairness_eg"),
    ("compactness_pp", "competitiveness"),
    ("competitiveness", "fairness_eg"),
    ("compactness_pp", "population_equality"),
]

SHORT = {
    "compactness_pp": "compactness\n(Polsby-Popper)",
    "compactness_cut": "compactness\n(cut edges)",
    "county_integrity": "county\nintegrity",
    "fairness_eg": "fairness\n(eff. gap)",
    "fairness_mm": "fairness\n(mean-median)",
    "competitiveness": "competitive\ndistricts",
    "population_equality": "population\nequality",
}


def load_draws(path: Path) -> tuple[list[dict], list[list[dict]]]:
    """Completed-chain rows, pooled and grouped, from the driver's CSV."""
    by_chain: dict[int, list[dict]] = {}
    with gzip.open(path, "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["chain_completed"] != "1":
                continue
            typed = {k: float(v) for k, v in row.items()
                     if k not in ("chain_index", "chain_seed", "chain_completed")}
            by_chain.setdefault(int(row["chain_index"]), []).append(typed)
    chains = [by_chain[i] for i in sorted(by_chain)]
    return [r for c in chains for r in c], chains


def _frame(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#d0d0d0")
    ax.tick_params(colors=MUTED, labelsize=8, length=3)


# --------------------------------------------------------------------------- #
# figure 1 — the verdict matrix
# --------------------------------------------------------------------------- #

def verdict_matrix(state: dict, path: Path) -> Path:
    names = state["criteria"]["varying"] + sorted(state["criteria"]["degenerate"])
    index = {n: i for i, n in enumerate(names)}
    verdicts = {(p["a"], p["b"]): p for p in state["pairs"]}
    rel = {r["relationship"]: r
           for r in state.get("relationships", {}).get("relationships", [])}

    n = len(names)
    fig, ax = plt.subplots(figsize=(1.15 * n + 3.2, 1.15 * n + 2.2), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    drawn = set()
    for (a, b), pair in verdicts.items():
        # Canonical order is position in the criteria list, not alphabetical:
        # sorting by name scatters the cells off the triangle.
        key = tuple(sorted((a, b), key=lambda n: index[n]))
        if key in drawn:
            continue
        drawn.add(key)
        # lower triangle: row is the later name, so each relationship is one cell
        row, col = index[key[1]], index[key[0]]   # lower triangle
        record = (rel.get(f"{key[0]} <-> {key[1]}")
                  or rel.get(f"{key[1]} <-> {key[0]}"))
        verdict = record["verdict"] if record else pair["verdict"]
        ax.add_patch(plt.Rectangle(
            (col - 0.5, row - 0.5), 1, 1,
            facecolor=VERDICT_COLOUR[verdict], edgecolor=SURFACE, lw=2))
        if verdict != "degenerate":
            other = verdicts.get((b, a))
            votes = max(pair["votes"], other["votes"] if other else 0)
            deciding = max(pair["n_deciding"], other["n_deciding"] if other else 0)
            mark = "*" if record and record["direction_dependent"] else ""
            ax.text(col, row, f"{votes}/{deciding}{mark}",
                    ha="center", va="center", fontsize=8,
                    color=INK if verdict != "strong" else "#ffffff")

    for name in names:
        if name in state["criteria"]["degenerate"]:
            for other in names:
                for r, c in ((index[name], index[other]), (index[other], index[name])):
                    ax.add_patch(plt.Rectangle(
                        (c - 0.5, r - 0.5), 1, 1,
                        facecolor=VERDICT_COLOUR["degenerate"],
                        edgecolor=SURFACE, lw=2))
        ax.add_patch(plt.Rectangle(
            (index[name] - 0.5, index[name] - 0.5), 1, 1,
            facecolor="#fafafa", edgecolor=SURFACE, lw=2))

    labels = [SHORT.get(x, x).replace("\n", " ") for x in names]
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8.5, color=INK)
    ax.set_yticklabels(labels, fontsize=8.5, color=INK)
    ax.set_xlim(-0.5, n - 0.5); ax.set_ylim(n - 0.5, -0.5)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)

    sample = state["ensemble"]["analysis_sample"]
    floors = [f["floor_any_test"]["weakest_detected_rho"]
              for f in state.get("detection_floor", [])
              if f.get("floor_any_test", {}).get("fires")]
    floor = f" · blind below |rho| ~ {min(floors):.2f}" if floors else ""
    n_rel = state.get("relationships", {}).get("n_relationships", "?")
    ax.set_title(
        f"{state['state']}: do these two criteria trade off against each other?",
        fontsize=13, color=INK, fontweight="bold", pad=16, loc="left")
    fig.text(0.0, -0.03,
             f"{sample['n_draws']:,} neutral draws over {sample['n_chains']} "
             f"completed chains · {n_rel} relationships, not ordered pairs{floor}\n"
             f"cell shows tests firing / tests able to decide, after "
             f"Benjamini-Hochberg correction · * marks a relationship whose two "
             f"directions disagree, which only the conditional test can produce",
             fontsize=8.5, color=MUTED, ha="left", va="top")

    ax.legend(handles=[Patch(facecolor=VERDICT_COLOUR[v], label=v)
                       for v in ("none", "weak", "strong", "degenerate")],
              loc="upper left", bbox_to_anchor=(1.02, 1.0), frameon=False,
              fontsize=9)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- #
# figure 2 — the frontier panels
# --------------------------------------------------------------------------- #

def _frontier_points(xs, ys):
    points = sorted(set(zip(xs, ys)), key=lambda p: (-p[0], -p[1]))
    out, best = [], float("-inf")
    for x, y in points:
        if y > best:
            out.append((x, y))
            best = y
    return out


def frontier_panels(state: dict, chains, path: Path) -> Path:
    criteria = X.criteria_for(state["config"]["primary_contest"])
    verdicts = {(p["a"], p["b"]): p for p in state["pairs"]}
    available = [pair for pair in HEADLINE_PAIRS
                 if pair in verdicts or (pair[1], pair[0]) in verdicts]
    missing = [pair for pair in HEADLINE_PAIRS if pair not in available]

    cols = 3
    rows = max(1, -(-len(available) // cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.1 * cols, 3.7 * rows), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    flat = list(axes.flat) if hasattr(axes, "flat") else [axes]

    pooled = [r for c in chains for r in c]
    for ax, (a, b) in zip(flat, available):
        _frame(ax)
        xs = X.goodness(pooled, a, criteria)
        ys = X.goodness(pooled, b, criteria)
        ax.scatter(xs, ys, s=3, color=HUE, alpha=0.10, linewidths=0, zorder=2)
        front = _frontier_points(xs, ys)
        ax.plot([p[0] for p in front], [p[1] for p in front], color=FRONTIER,
                lw=1.6, marker="o", ms=3.0, zorder=4)

        pair = verdicts.get((a, b)) or verdicts[(b, a)]
        rho = pair["tests"]["correlation"].get("rho")
        head = f"{SHORT.get(a, a)} vs {SHORT.get(b, b)}".replace("\n", " ")
        ax.set_title(head, fontsize=9.5, color=INK, loc="left", pad=8)
        ax.text(0.02, 0.97,
                f"{pair['verdict']}"
                + (f" · rho {rho:+.2f}" if rho is not None else ""),
                transform=ax.transAxes, va="top", ha="left", fontsize=8.5,
                color=INK if pair["verdict"] == "none" else FRONTIER)
        ax.set_xlabel(f"better {SHORT.get(a, a)} ->".replace("\n", " "),
                      fontsize=8, color=MUTED)
        ax.set_ylabel(f"better {SHORT.get(b, b)} ->".replace("\n", " "),
                      fontsize=8, color=MUTED)

    for ax in flat[len(available):]:
        ax.axis("off")

    note = (f"{len(pooled):,} neutral draws · both axes are goodness, so up and to "
            f"the right is better on both\n"
            f"red line is the Pareto frontier. Read it with care: its points are "
            f"non-dominated draws, so away from the cloud each one is a single "
            f"plan.\nA frontier can fall steeply on a handful of extreme draws "
            f"while the bulk shows no tradeoff at all -- which is the case here "
            f"for compactness against population equality, where the top 0.1% of "
            f"compactness costs about 3% of population spread. The verdict comes "
            f"from the three tests, not from this line.")
    if missing:
        note += ("\nnot shown, no varying pair on this state: "
                 + "; ".join(f"{m[0]} vs {m[1]}" for m in missing))
    fig.suptitle(f"{state['state']}: the frontier, criterion against criterion",
                 fontsize=13, color=INK, fontweight="bold", x=0.01, ha="left")
    fig.text(0.01, 0.005 if rows > 1 else -0.02, note, fontsize=8.5, color=MUTED,
             ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(path, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return path


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ensemble", default="v1", choices=("v1", "v2"),
                        help="which named ensemble's results to draw; the "
                             "filename carries it so the two never overwrite "
                             "each other")
    args = parser.parse_args(argv)
    source = RESULTS if args.ensemble == "v1" else RESULTS_V2
    suffix = "" if args.ensemble == "v1" else "-v2"
    results = json.loads(source.read_text())
    written = []
    for key, state in results["states"].items():
        draws = ROOT / state["draws_file"]["path"]
        _, chains = load_draws(draws)
        written.append(verdict_matrix(
            state, OUT / f"exp2-{key.lower()}{suffix}-verdict-matrix.png"))
        written.append(frontier_panels(
            state, chains, OUT / f"exp2-{key.lower()}{suffix}-frontier.png"))
    for path in written:
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
