#!/usr/bin/env python3
"""Figure for Experiment 3 — metric gameability, adversarial.

`prompt.md`: *"For each fairness metric, search for a plan that scores well on
it while producing a lopsided seat outcome. Reproduce arXiv:2409.17186 on your
own data."* The finding is a table of plans against metrics, and the argument
lives in the rows, so the figure is that table drawn as a grid.

**The alarm colour marks the passes, not the flags.** Every other chart in this
repo uses the quiet colour for "nothing here". This one inverts it: a cell is
filled red when the metric would *pass* the plan through a single-metric screen,
because three of these plans hand one party seven or eight of eight seats. A
reader who skims the colour and thinks "mostly fine" has drawn exactly the
conclusion the experiment refutes.

The inversion is stated rather than assumed, because it does not hold on every
row. The two enacted maps are drawn as references, and a red cell on a reference
row means only "this metric would pass this map" -- which for a 5-3 map is not
a scandal. Reference rows are therefore labelled in italic and separated by a
rule, and the legend says "would pass a single-metric screen" rather than
calling every pass a failure.

**Undefined is not blank.** Declination is undefined when no district falls on
one side of 50%, which is precisely what a sweep produces. A blank cell reads as
missing data; this reads as a metric declining to answer about the maps it most
needs to answer about, so it gets its own hatch and its own legend entry.

**The seat panel is what makes a clean row damning.** Metric values alone cannot
show lopsidedness, so the left panel draws seats won against proportionality and
against the neutral ensemble's range. The grid says "the metric is happy"; the
panel says "and the map is a sweep". Neither half carries the finding alone.

**Only rows this repo can regenerate are drawn.** Seven searches were run; three
gamed Colorado plans plus both enacted plans are committed as CSVs and are
recomputed here from those CSVs by `evaluate.partisan` at draw time, so every
number in the figure is reproducible from the repository. Four rows of the
written table in `docs/progress.md` are not drawn, because their plan CSVs were
never committed and a figure must not assert a number it cannot regenerate. The
count of what is omitted is printed on the figure rather than left silent.

The two Iowa searches that claimed success are excluded on their merits as well
as their artifacts: 0 of 4 is inside Iowa's neutral support and is the enacted
plan's own outcome, so those plans were refuted as gaming demonstrations.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from evaluate import elections as E, plan as EP, partisan as P   # noqa: E402

OUT = ROOT / "docs" / "figures"
PLANS = ROOT / "docs" / "experiment-3-plans"
PROCESSED = ROOT / "data" / "processed"
NEUTRAL = ROOT / "data" / "results"

INK, MUTED, SURFACE = "#1a1a1a", "#6b6b6b", "#ffffff"
FOOLED = "#c1583f"        # the metric passed a sweep; the alarm
FIRES = "#e8eef5"         # the metric caught it; working as advertised
UNDEFINED = "#d6d6d6"     # the metric declined to answer
SEATS = "#4a6fa5"

#: Metric, display name, and the band a single-metric screen would use. Bands
#: are the ones Experiment 3 ran with; they are screen thresholds, not claims
#: about what is fair.
METRICS = [
    ("efficiency_gap", "efficiency gap", 0.07),
    ("mean_median", "mean-median", 0.02),
    ("declination", "declination", 0.1),
    ("partisan_bias", "partisan bias", 0.05),
]

#: Plans whose CSVs are committed, so every value below is regenerated rather
#: than transcribed. `gamed` marks the three adversarial results; the enacted
#: maps are drawn as the reference a reader needs to judge the others.
ROWS = [
    ("co", "mm_plan_D_shape", "CO — mean-median gamed", True),
    ("co", "co_declination_gamed_D7", "CO — declination gamed", True),
    ("co", "co_partisan_bias_gamed_D8", "CO — partisan-bias gamed", True),
    ("co", None, "CO — enacted (reference; VTD, not contiguous)", False),
    ("ia", None, "IA — enacted (reference)", False),
]

#: Rows of the written cross-metric table whose plan CSVs were not committed.
#: Named on the figure so "five rows" is never mistaken for "all of it".
NOT_DRAWN = [
    "CO efficiency-gap attempt (honest negative)",
    "IA efficiency-gap attempt (honest negative)",
    "IA mean-median plan (refuted: 0/4 is inside Iowa's neutral support)",
    "IA partisan-bias plan (refuted: same reason)",
]


def _frame(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)


def _votes(prefix: str, contest: str):
    elections = E.load_elections(PROCESSED / f"{prefix}_elections.csv")
    dem_col, rep_col = E.two_party_columns(elections, contest)
    return E.two_party(elections, dem_col, rep_col)


def _neutral_range(prefix: str) -> tuple[int, int, int] | None:
    """Seat counts the neutral reference reached, with the draw count.

    The draw count travels with the range because these references are small
    -- 720 completed draws on Colorado, 1,820 on Iowa -- and a band drawn
    without its n invites the reader to treat "never reached" as "impossible".
    `docs/progress.md` section 1 records that two larger fresh Colorado
    ensembles did reach 7 D, in 0.05% and 1.35% of draws.
    """
    path = NEUTRAL / f"{prefix}_neutral_seat_distribution.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    counts = data["dem_seat_counts"]
    seats = [int(k) for k, v in counts.items() if v > 0]
    if not seats:
        return None
    return min(seats), max(seats), int(data.get("n_completed", sum(counts.values())))


def measure(contest: str = "G20PRE") -> list[dict]:
    """Recompute every drawable row from committed CSVs."""
    cache: dict[str, tuple] = {}
    out = []
    for prefix, stem, label, gamed in ROWS:
        if prefix not in cache:
            cache[prefix] = _votes(prefix, contest)
        dem, rep = cache[prefix]
        path = (PLANS / f"{stem}.csv" if stem
                else PROCESSED / f"{prefix}_enacted_cd118.csv")
        plan = EP.load_plan(path)
        d_seats, r_seats, tied = P.seat_counts(plan, dem, rep)
        k = d_seats + r_seats + tied
        share = P.statewide_dem_share(dem, rep)
        out.append({
            "label": label, "gamed": gamed, "k": k, "prefix": prefix,
            "d_seats": d_seats, "r_seats": r_seats, "tied": tied,
            "proportional": share * k, "dem_share": share,
            "metrics": P.all_metrics(plan, dem, rep),
            "source": str(path.relative_to(ROOT)),
        })
    return out


def _cell_text(value: float | None) -> str:
    if value is None:
        return "undefined"
    if value == 0.0:
        return "0.0 exactly"
    if abs(value) < 1e-4:
        return f"{value:.1e}"
    return f"{value:+.4f}"


def gameability(rows: list[dict], path: Path, contest: str) -> Path:
    n = len(rows)
    fig, (seat_ax, grid) = plt.subplots(
        1, 2, figsize=(13.4, 1.9 + 0.72 * n),
        gridspec_kw={"width_ratios": [1.0, 2.5], "wspace": 0.06})
    _frame(seat_ax)
    _frame(grid)

    y = list(range(n))[::-1]
    neutral_n: dict[str, int] = {}

    # ----- left: the seat outcome, which is what makes a clean row damning ---
    for slot, row in zip(y, rows):
        k = row["k"]
        seat_ax.barh(slot, row["d_seats"] / k, height=0.5, color=SEATS,
                     zorder=3)
        seat_ax.plot([row["proportional"] / k] * 2,
                     [slot - 0.33, slot + 0.33],
                     color=INK, linewidth=1.8, zorder=5)
        span = _neutral_range(row["prefix"])
        if span is not None:
            lo, hi, n_draws = span
            neutral_n[row["prefix"]] = n_draws
            seat_ax.add_patch(Rectangle(
                (lo / k, slot - 0.4), (hi - lo) / k, 0.8,
                facecolor="#f0c987", alpha=0.35, edgecolor="none", zorder=1))
        if row["d_seats"] == 0:
            # A zero-width bar is indistinguishable from a missing one.
            seat_ax.plot([0, 0], [slot - 0.25, slot + 0.25], color=SEATS,
                         linewidth=2.4, zorder=4)

    seat_ax.set_xlim(0, 1.0)
    seat_ax.set_ylim(-0.7, n - 0.3)
    seat_ax.set_yticks(y)
    labels = []
    for row in rows:
        tied = f" +{row['tied']} tied" if row["tied"] else ""
        labels.append(f"{row['label']}\n{row['d_seats']} D – "
                      f"{row['r_seats']} R{tied}")
    seat_ax.set_yticklabels(labels, fontsize=8.6, color=INK)
    for tick, row in zip(seat_ax.get_yticklabels(), rows):
        if not row["gamed"]:
            tick.set_fontstyle("italic")
            tick.set_color(MUTED)

    # A rule between the searched plans and the enacted references, so a red
    # cell on a reference row is never read as a gaming result.
    first_reference = next((i for i, r in enumerate(rows) if not r["gamed"]),
                           None)
    if first_reference is not None:
        boundary = y[first_reference] + 0.5
        for ax, right in ((seat_ax, 1.0), (grid, len(METRICS))):
            ax.plot([0, right], [boundary, boundary], color="#c8c8c8",
                    linewidth=0.9, linestyle=(0, (4, 3)), zorder=6)

    seat_ax.set_xticks([0, 0.5, 1.0])
    seat_ax.set_xticklabels(["0", "half", "all"], fontsize=7.5)
    seat_ax.set_xlabel("share of seats won by D", fontsize=8, color=MUTED)

    # ----- right: the metric grid ------------------------------------------
    grid.set_xlim(0, len(METRICS))
    grid.set_ylim(-0.7, n - 0.3)
    grid.set_yticks([])
    grid.set_xticks([i + 0.5 for i in range(len(METRICS))])
    grid.set_xticklabels([f"{name}\n(screen |x| ≤ {band})"
                          for _, name, band in METRICS],
                         fontsize=8, color=INK)
    grid.xaxis.set_ticks_position("top")
    grid.xaxis.set_label_position("top")

    for slot, row in zip(y, rows):
        for i, (key, _, band) in enumerate(METRICS):
            value = row["metrics"].get(key)
            if value is None:
                face, hatch, edge = UNDEFINED, "xx", "#b0b0b0"
            elif abs(value) <= band:
                face, hatch, edge = FOOLED, None, FOOLED
            else:
                face, hatch, edge = FIRES, None, "#c8d4e0"
            grid.add_patch(Rectangle(
                (i + 0.04, slot - 0.36), 0.92, 0.72, facecolor=face,
                edgecolor=edge, hatch=hatch, linewidth=0.8, zorder=3))
            grid.text(i + 0.5, slot, _cell_text(value), va="center",
                      ha="center", fontsize=7.6, zorder=4,
                      color="#ffffff" if face == FOOLED else INK,
                      fontweight="bold" if face == FOOLED else "normal")

    legend = [
        Patch(facecolor=FOOLED, edgecolor=FOOLED,
              label="reads clean — would pass a single-metric screen"),
        Patch(facecolor=FIRES, edgecolor="#c8d4e0",
              label="flags the plan — working as advertised"),
        Patch(facecolor=UNDEFINED, edgecolor="#b0b0b0", hatch="xx",
              label="undefined — the metric declines to answer"),
        Patch(facecolor=SEATS, edgecolor=SEATS, label="seats won by D"),
        Patch(facecolor="#f0c987", alpha=0.35, edgecolor="none",
              label="range the neutral reference reached ("
                    + ", ".join(f"{p.upper()} n={v:,}"
                                for p, v in sorted(neutral_n.items()))
                    + ")"),
    ]
    fig.legend(handles=legend, loc="lower left", bbox_to_anchor=(0.005, -0.055),
               ncol=3, frameon=False, fontsize=8, labelcolor=INK,
               handlelength=1.6, columnspacing=1.6)

    fig.suptitle("Metric gameability: legal plans on which a fairness metric "
                 "reads clean while one party sweeps",
                 fontsize=13, color=INK, fontweight="bold", x=0.005, ha="left")
    note = (
        f"contest {contest} · every value recomputed from the committed plan "
        f"CSV by evaluate.partisan at draw time · black tick = proportionality"
        f"\nNot drawn, plan CSV not committed: " + "; ".join(NOT_DRAWN) +
        f"\n{len(NOT_DRAWN)} of the {len(ROWS) + len(NOT_DRAWN) - 2} searched "
        "plans in docs/progress.md are therefore absent here."
    )
    fig.text(0.005, -0.085, note, fontsize=7.6, color=MUTED, ha="left",
             va="top")
    # tight_layout warns on this figure (the grid axes carry only patches and
    # a top-side x axis, which it cannot size), and savefig's bbox already
    # trims the margins. Reserve the header band explicitly instead.
    fig.subplots_adjust(top=0.86, bottom=0.12)
    fig.savefig(path, bbox_inches="tight", facecolor=SURFACE, dpi=150)
    plt.close(fig)
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contest", default="G20PRE")
    args = parser.parse_args(argv)

    rows = measure(args.contest)
    OUT.mkdir(parents=True, exist_ok=True)
    path = gameability(rows, OUT / "exp3-gameability.png", args.contest)
    print(f"wrote {path.relative_to(ROOT)}")
    for row in rows:
        print(f"  {row['label']}: {row['d_seats']}D-{row['r_seats']}R "
              f"from {row['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
