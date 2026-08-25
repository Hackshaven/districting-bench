#!/usr/bin/env python3
"""Figure for Experiment 1 — criteria sensitivity.

`prompt.md` asks for a ranked list of which criteria bind and which are
decorative. The ranked list is the finding; this figure exists to stop three
specific misreadings of it, and every design choice below is one of those three.

**A bar without its own null is not a result.** Effective sample size on these
columns is 19-78 against a nominal 20,000-27,564, so a Cliff's delta of -0.3
means nothing until you know what the ensemble produces by chance. Each
criterion's null is a *different* number -- Iowa's run roughly twice Colorado's
-- so a single shared threshold line would be a lie. The 5th-percentile null is
therefore drawn as a per-bar tick, and a bar that does not reach its own tick is
drawn hollow. "Iowa binds harder" is partly Iowa mixing worse, and the ticks are
where a reader sees that.

**The ordering does not replicate; the classification does.** Re-derived on the
2020 Senate contest over the same draws, Kendall tau is +0.467 on Iowa and
+0.524 on Colorado -- changing the election reorders the list about as much as
changing the state. So both contests are drawn, as paired bars. A reader who
takes the rank order away from this chart has taken the half that does not
survive; a reader who takes the solid/hollow split has taken the half that does.

**Six rows are not six findings.** Ranks 1 and 2 in each state are one
relationship read from both ends -- the same competitiveness <-> mean-median
pair that was Experiment 2's only survivor. Both rows carry a dagger, because a
reader counting rows will otherwise count one relationship twice and conclude
the evidence is denser than it is.

Degenerate criteria are drawn in the degenerate colour with their reason, not
omitted. County integrity is constant on Iowa because the units *are* the
counties -- a criterion enforced by the choice of unit rather than by the plan
search. Dropping the row would read as "not measured"; a zero-length bar would
read as "measured, found nothing".

Sign convention: negative delta means the plans a criterion keeps are *worse* on
whatever it displaces. Bars therefore run left, and longer-left is more binding.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent.parent

OUT = ROOT / "docs" / "figures"
RESULTS = ROOT / "docs" / "experiment-1" / "experiment-1-results.json"
RESULTS_V2 = ROOT / "docs" / "experiment-1" / "experiment-1-results-v2.json"

INK, MUTED, SURFACE = "#1a1a1a", "#6b6b6b", "#ffffff"
BINDS = "#c1583f"          # clears its own null
QUIET = "#e8eef5"          # does not clear; the expected result
DEGENERATE = "#d6d6d6"
ALTERNATE = "#4a6fa5"      # the second contest
NULL_TICK = "#1a1a1a"

SHORT = {
    "compactness_pp": "compactness (Polsby-Popper)",
    "compactness_cut": "compactness (cut edges)",
    "county_integrity": "county integrity",
    "fairness_eg": "fairness (efficiency gap)",
    "fairness_mm": "fairness (mean-median)",
    "competitiveness": "competitive districts",
    "population_equality": "population equality",
}

#: The one relationship that appears twice in every ranking, read from both
#: ends. Daggered in the figure so its two rows are not counted as two
#: findings. Experiment 2 found the same pair as its only survivor.
MIRRORED_PAIR = ("competitiveness", "fairness_mm")


def _frame(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#d0d0d0")
    ax.tick_params(colors=MUTED, labelsize=8, length=3)


def _nulls(state: dict) -> dict[str, float]:
    """Each criterion's own 5th-percentile null, keyed by criterion."""
    return {d["criterion"]: d["null"]["p05"] for d in state["detail"]
            if d.get("null")}


def _alternate(state: dict) -> dict[str, dict]:
    """The same ranking re-derived on the other contest, keyed by criterion."""
    replication = state.get("replication") or {}
    return {r["criterion"]: r for r in replication.get("ranked", [])}


def sensitivity(state: dict, path: Path, *, ensemble: str, null_n: int) -> Path:
    ranked = state["ranked"]
    nulls = _nulls(state)
    alternate = _alternate(state)
    degenerate = state.get("degenerate") or {}

    rows = list(ranked) + [
        {"criterion": name, "worst_delta": 0.0, "displaces": None,
         "binds": False, "degenerate": True, "reason": info.get("reason", "")}
        for name, info in sorted(degenerate.items())
    ]

    height = 1.05 + 0.62 * len(rows)
    fig, ax = plt.subplots(figsize=(11.2, height))
    _frame(ax)

    y = list(range(len(rows)))[::-1]
    bar_h = 0.32

    for slot, row in zip(y, rows):
        criterion = row["criterion"]
        if row.get("degenerate"):
            ax.barh(slot, -0.02, height=bar_h * 2, color=DEGENERATE,
                    edgecolor="#bdbdbd", linewidth=0.8)
            ax.text(-0.035, slot, "degenerate — " + row["reason"].split(":")[0],
                    va="center", ha="right", fontsize=7.5, color=MUTED,
                    style="italic")
            continue

        delta = row["worst_delta"]
        clears = bool(row["binds"])
        # Solid = cleared its own null. Hollow = did not. The fill is the
        # verdict; the length is only the effect size.
        ax.barh(slot + bar_h / 2 + 0.02, delta, height=bar_h,
                color=BINDS if clears else QUIET,
                edgecolor=BINDS if clears else "#a8b8c8",
                linewidth=0 if clears else 1.0,
                hatch=None if clears else "///", zorder=3)

        alt = alternate.get(criterion)
        if alt is not None:
            ax.barh(slot - bar_h / 2 - 0.02, alt["worst_delta"], height=bar_h,
                    color=ALTERNATE if alt["binds"] else QUIET,
                    edgecolor=ALTERNATE if alt["binds"] else "#a8b8c8",
                    linewidth=0 if alt["binds"] else 1.0,
                    hatch=None if alt["binds"] else "///", zorder=3, alpha=0.9)

        p05 = nulls.get(criterion)
        if p05 is not None:
            # This criterion's own noise floor, not a shared threshold.
            ax.plot([p05, p05], [slot - bar_h - 0.06, slot + bar_h + 0.06],
                    color=NULL_TICK, linewidth=1.6, solid_capstyle="butt",
                    zorder=5)

        if row.get("displaces"):
            # Anchor left of whichever reaches further, the bar or the null
            # tick, so the annotation never sits on top of the threshold it
            # is the reader's job to compare the bar against.
            anchor = min(delta, p05 if p05 is not None else delta)
            ax.text(anchor - 0.015, slot + bar_h / 2 + 0.02,
                    f"displaces {SHORT.get(row['displaces'], row['displaces'])}",
                    va="center", ha="right", fontsize=7.2, color=MUTED)

    # The mirrored pair is marked on its labels rather than bracketed. A
    # bracket has to be drawn inside the data area, where it collides with
    # either the bars or the "displaces" annotations depending on the state;
    # a dagger on the label cannot collide with anything.
    mirrored = {name for name in MIRRORED_PAIR
                if any(r["criterion"] == name for r in rows)}
    marked = len(mirrored) == len(MIRRORED_PAIR)
    ax.set_yticks(y)
    ax.set_yticklabels(
        [SHORT.get(r["criterion"], r["criterion"])
         + (" †" if marked and r["criterion"] in mirrored else "")
         for r in rows],
        fontsize=9, color=INK)

    ax.axvline(0, color="#b8b8b8", linewidth=0.9, zorder=2)
    ax.set_xlabel("Cliff's delta, plans kept vs plans excluded  "
                  "(negative = the kept plans are worse on the displaced criterion)",
                  fontsize=8.5, color=MUTED)
    ax.set_ylim(-0.7, len(rows) - 0.3)

    primary = state["contest"]
    alt_contest = (state.get("replication") or {}).get("contest", "—")
    legend = [
        Patch(facecolor=BINDS, edgecolor=BINDS,
              label=f"{primary} — clears its own null"),
        Patch(facecolor=ALTERNATE, edgecolor=ALTERNATE,
              label=f"{alt_contest} — clears its own null"),
        Patch(facecolor=QUIET, edgecolor="#a8b8c8", hatch="///",
              label="does not clear its null"),
        Line2D([0], [0], color=NULL_TICK, linewidth=1.6,
               label="that criterion's 5th-percentile null"),
    ]
    if degenerate:
        legend.append(Patch(facecolor=DEGENERATE, edgecolor="#bdbdbd",
                            label="degenerate — constant by construction"))
    ax.legend(handles=legend, loc="lower left", bbox_to_anchor=(0.0, 1.005),
              ncol=3, frameon=False, fontsize=7.8, labelcolor=INK,
              handlelength=1.6, columnspacing=1.4)

    n_relationships = state.get("distinct_relationships_behind_ranking")
    note = (
        f"{state['state']} · {state['n_draws']:,} draws, "
        f"{state['n_chains']} chains, ensemble {ensemble} · null from "
        f"{null_n} circular-shift replicates within chains\n"
        f"{len(ranked)} rows rest on {n_relationships} distinct relationships. "
        "The rank ORDER does not replicate across contests; the solid/hollow "
        "classification does. Read the fill, not the order."
        + ("\n† these two rows are ONE relationship read from both ends — the "
           "same pair that was Experiment 2's only survivor. Counting rows "
           "double-counts it." if marked else "")
    )
    fig.suptitle(f"{state['state']}: which criteria actually bind",
                 fontsize=13, color=INK, fontweight="bold", x=0.01, ha="left")
    fig.text(0.01, -0.01, note, fontsize=8, color=MUTED, ha="left", va="top")
    fig.tight_layout(rect=(0, 0.02, 1, 0.94))
    fig.savefig(path, bbox_inches="tight", facecolor=SURFACE, dpi=150)
    plt.close(fig)
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ensemble", default="v2", choices=("v1", "v2"),
                        help="which named ensemble's results to draw; the "
                             "filename carries it so the two never overwrite "
                             "each other")
    args = parser.parse_args(argv)

    source = RESULTS if args.ensemble == "v1" else RESULTS_V2
    suffix = "" if args.ensemble == "v1" else "-v2"
    results = json.loads(source.read_text())

    # The v1 results predate the per-state "ensemble" field, so the label
    # comes from the file that was opened rather than from inside it.
    null_n = results.get("null_replicates", 60)
    OUT.mkdir(parents=True, exist_ok=True)
    for key, state in results["states"].items():
        path = sensitivity(
            state, OUT / f"exp1-{key.lower()}{suffix}-sensitivity.png",
            ensemble=state.get("ensemble", args.ensemble), null_n=null_n)
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
