#!/usr/bin/env python3
"""Figure: the neutral seat distribution for Iowa, with the enacted plan located.

Form: the data's job is magnitude across three discrete outcomes, so bars. One
series, so no legend -- the title names it. The enacted plan is a single point,
not a category, so it is annotated rather than colour-encoded; colouring its bucket
differently would imply a second series that does not exist.

**Every number is recomputed from committed files at draw time** (D-036). The
first version of this script read ``data/results/ia_neutral_seat_distribution.json``,
which is gitignored, so the figure at the top of the README was the one figure in
the repository no reader could regenerate, and its footer carried "43%" as a
literal string. It now reads two committed files:

* ``docs/experiment-2/ia-draws-v2.csv.gz``, through Experiment 2's own loader, so
  the sample is the D-035 rectangle -- six chains truncated to their common
  4,594-draw prefix -- with every chain's seed checked against the one its index
  derives;
* ``docs/phase-2/phase-2-report.json``, for the statewide two-party vote share,
  the district count and the enacted plan's seat count.

**Seats are recovered from the efficiency gap, not recounted** (D-039). The draws
file records each draw's |efficiency gap|, not its seats, and a recount needs the
election returns, which this repository cannot redistribute. It does not need
them: with wasted votes counted against half of each district's votes, the gap is
exactly ``2V - 1/2 - tau``, where ``V`` is the statewide two-party Democratic
share and ``tau`` the share of two-party votes cast in districts the Democrats
win (``evaluate.partisan.wasted_votes``). ``tau`` is the seat share ``s/k`` when
every district casts the same number of votes, so a plan winning ``s`` seats sits
at ``|2V - 1/2 - s/k|`` give or take its turnout imbalance. The committed gap uses
the strict-majority threshold, one vote per district away from half -- about
``4 / 1.66e6`` on Iowa. :func:`recover_seats` refuses the whole sample unless
every draw sits nearer its own level than half the smallest gap between levels,
so a draw cannot be assigned to a seat count it is merely closest to.

**The chains are drawn, not only the pool.** The bars are the pooled ensemble;
each dot is one chain's share. Six chains that disagree about the 2-seat share by
more than ten points are the uncertainty a pooled bar hides, and drawing them is
cheaper than describing them.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import experiment_2_tradeoffs as X          # noqa: E402
from generate import convergence as CV      # noqa: E402

OUT = ROOT / "docs" / "figures" / "ia-neutral-seat-distribution.png"
REPORT = ROOT / "docs" / "phase-2" / "phase-2-report.json"

STATE, PREFIX, ENSEMBLE = "IA", "ia", "v2"
#: The contest the Phase 2 report's vote share and enacted seat count are
#: computed on. The levels are only valid against the same contest's gaps.
CONTEST = "G20PRE"

INK, MUTED, HUE, SURFACE = "#1a1a1a", "#6b6b6b", "#4a6fa5", "#ffffff"
#: Bar width, narrow enough that the 0-seat bar's labels clear the 1-seat bar.
WIDTH = 0.56


def seat_levels(dem_share: float, k: int) -> dict[int, float]:
    """The |efficiency gap| a plan winning ``s`` of ``k`` seats sits at, ``s = 0..k``.

    Exact when every district casts the same number of two-party votes; a real
    plan sits off its level by its turnout imbalance. See the module docstring.
    """
    return {s: abs(2 * dem_share - 0.5 - s / k) for s in range(k + 1)}


def recover_seats(abs_gaps: list[float],
                  levels: dict[int, float]) -> tuple[list[int], float, float]:
    """Each draw's Democratic seat count, from its |efficiency gap|.

    Returns ``(seats, max_residual, half_gap)``: the largest distance of any draw
    from its own level, and half the smallest distance between two levels.
    Raises ``ValueError`` unless ``max_residual < half_gap`` -- below that every
    draw is nearer its own level than to any other, so the assignment is
    unambiguous; at or above it some draw could belong to either of two seat
    counts, and assigning it to the nearer one would be a guess. Two seat counts
    whose levels coincide give a zero gap and are refused the same way.
    """
    ordered = sorted(levels.values())
    half_gap = min(b - a for a, b in zip(ordered, ordered[1:])) / 2
    seats, residuals = [], []
    for gap in abs_gaps:
        s = min(levels, key=lambda n: abs(gap - levels[n]))
        seats.append(s)
        residuals.append(abs(gap - levels[s]))
    max_residual = max(residuals)
    if not max_residual < half_gap:
        raise ValueError(
            f"a draw sits {max_residual:.4f} from its nearest seat level, and the "
            f"levels are only {2 * half_gap:.4f} apart: its seat count cannot be "
            "read off its efficiency gap. Recount from the plan and the returns."
        )
    return seats, max_residual, half_gap


def seat_distribution() -> dict:
    """The neutral seat distribution, every value recomputed from committed files."""
    report = json.loads(REPORT.read_text())[STATE]
    if report["contest"] != CONTEST:
        raise ValueError(
            f"{REPORT} is computed on {report['contest']}, not {CONTEST}; its vote "
            "share would place the seat levels for the wrong election."
        )
    partisan = report["partisan"]
    k, dem_share = partisan["n_districts"], partisan["dem_vote_share"]
    levels = seat_levels(dem_share, k)

    rectangle = X.ENSEMBLES[ENSEMBLE]["rectangle"][STATE]
    chains = X.chains_from_draws(X.ensemble_spec(STATE, ENSEMBLE),
                                 X.draws_path(PREFIX, ENSEMBLE),
                                 rectangle=rectangle)
    key = f"abs_efficiency_gap@{CONTEST}"
    per_chain, max_residual, half_gap = [], 0.0, None
    for chain in chains:
        seats, residual, half_gap = recover_seats(
            [row[key] for row in chain.rows], levels)
        per_chain.append(seats)
        max_residual = max(max_residual, residual)

    pooled = [s for seats in per_chain for s in seats]
    outcomes = sorted(set(pooled))
    counts = {s: pooled.count(s) for s in outcomes}
    shares = {s: counts[s] / len(pooled) for s in outcomes}

    def indicator(s):
        return [[float(x == s) for x in seats] for seats in per_chain]

    # Monte Carlo standard error of each share, from its own effective sample
    # size: the chains are autocorrelated, so len(pooled) is not the sample size.
    ess = {s: CV.ess(indicator(s)) for s in outcomes}
    mcse = {s: math.sqrt(shares[s] * (1 - shares[s]) / ess[s]) for s in outcomes}

    seat_series = [[float(x) for x in seats] for seats in per_chain]
    return {
        "contest": CONTEST,
        "dem_vote_share": dem_share,
        "n_districts": k,
        "levels": levels,
        "rectangle": rectangle,
        "n_chains": len(per_chain),
        "n_draws": len(pooled),
        "counts": counts,
        "shares": shares,
        "per_chain_shares": [{s: seats.count(s) / len(seats) for s in outcomes}
                             for seats in per_chain],
        "ess": ess,
        "mcse": mcse,
        "seat_count_split_rhat": CV.split_rhat(seat_series),
        "seat_count_ess": CV.ess(seat_series),
        "max_residual": max_residual,
        "half_gap": half_gap,
        "enacted_dem_seats": partisan["dem_seats"],
    }


def draw(d: dict, out: Path = OUT) -> None:
    counts, shares = d["counts"], d["shares"]
    xs = sorted(counts)
    pct = [100 * shares[x] for x in xs]
    chain_pct = {x: [100 * c[x] for c in d["per_chain_shares"]] for x in xs}

    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=200)
    fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)

    bars = ax.bar(xs, pct, width=WIDTH, color=HUE, zorder=3)
    for b in bars:                       # 4px-equivalent rounded data-end
        b.set_linewidth(0); b.set_joinstyle("round")

    # one dot per chain, ringed in the surface colour so overlapping dots and
    # the bar edge behind them stay separable
    for x in xs:
        ax.scatter([x] * len(chain_pct[x]), chain_pct[x], s=18, color=INK,
                   edgecolors=SURFACE, linewidths=1.2, zorder=4)

    # offsets in points, not data units, so the two labels cannot collide
    # however tall the axis ends up after the title and footer take their room
    for x, p in zip(xs, pct):
        ax.annotate(f"{p:.1f}%", xy=(x + WIDTH / 2 + 0.02, p), xytext=(0, 12),
                    textcoords="offset points", ha="left", va="bottom",
                    color=INK, fontsize=11, fontweight="bold", zorder=5)
        ax.annotate(f"{counts[x]:,} draws", xy=(x + WIDTH / 2 + 0.02, p),
                    xytext=(0, 1), textcoords="offset points", ha="left",
                    va="bottom", color=MUTED, fontsize=8.5, zorder=5)

    # the enacted plan is a point on this axis, not a category
    enacted = d["enacted_dem_seats"]
    if enacted not in counts:
        # xs.index(enacted) raises ValueError here, and this is precisely the case
        # worth plotting: an enacted outcome the neutral process never produced is
        # the strongest version of the finding, not an error. Refuse loudly rather
        # than crashing in a list lookup three lines further down.
        raise SystemExit(
            f"enacted plan returns {enacted} D seats, which this ensemble never "
            f"produced (it spans {min(counts)}-{max(counts)}). That is a finding, "
            "not a plotting bug -- annotate it deliberately rather than letting "
            "the arrow point at a bar that does not exist."
        )
    top_dot = max(chain_pct[enacted])
    # placed in the empty upper-left so the leader never crosses another bar
    ax.annotate(
        f"Iowa's enacted plan\n{enacted} D seats\n{pct[xs.index(enacted)]:.1f}% of the ensemble",
        xy=(enacted, max(pct[xs.index(enacted)], top_dot) + 0.8),
        xytext=(enacted - 0.30, 26),
        color=INK, fontsize=9.5, ha="left", va="center",
        arrowprops=dict(arrowstyle="->", color=INK, lw=1.4,
                        shrinkA=6, shrinkB=3,
                        connectionstyle="arc3,rad=0.0"), zorder=6)

    ax.set_title("What Iowa's neutral process produces", color=INK,
                 fontsize=13.5, fontweight="bold", loc="left", pad=30)
    ax.text(0, 1.065,
            f"Democratic seats of {d['n_districts']} under the 2020 presidential "
            f"vote, over {d['n_draws']:,} ReCom draws",
            transform=ax.transAxes, color=MUTED, fontsize=9.5, va="bottom")
    ax.text(0, 1.015,
            f"made without election data.  Dots: each of its {d['n_chains']} "
            f"chains, cut to {d['rectangle']:,} draws (D-035).",
            transform=ax.transAxes, color=MUTED, fontsize=9.5, va="bottom")

    ax.set_xlabel(f"Democratic seats won (of {d['n_districts']})",
                  color=MUTED, fontsize=10)
    ax.set_ylabel("share of neutral ensemble", color=MUTED, fontsize=10)
    ax.set_xticks(xs)
    ceiling = max(max(pct), max(max(v) for v in chain_pct.values()))
    ax.set_ylim(0, 5 * math.ceil((ceiling + 5) / 5))
    ax.set_xlim(-0.55, 2.85)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="y", color="#e6e6e6", lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#cccccc")
    ax.tick_params(colors=MUTED, length=0)

    two = 100 * shares.get(2, 0.0)
    fig.text(0.008, 0.032,
             f"A 2-seat outcome is {two:.1f}% of the neutral distribution, so a "
             "2-seat shift is not detectable as a gerrymander on Iowa.",
             color=MUTED, fontsize=8.5, va="bottom")
    fig.text(0.008, 0.005,
             f"Seats read off each draw's |efficiency gap| (DECISIONS D-039). "
             f"Seat count: split R-hat {d['seat_count_split_rhat']:.3f}, "
             f"effective sample {d['seat_count_ess']:.0f}.",
             color=MUTED, fontsize=8.5, va="bottom")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.065, 1, 1))
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def summary_lines(d: dict) -> list[str]:
    lines = [
        f"{d['n_draws']:,} draws, {d['n_chains']} chains x {d['rectangle']:,} "
        f"(D-035), {d['contest']}, V = {d['dem_vote_share']:.6f}, k = {d['n_districts']}",
        f"seat recovery: max residual {d['max_residual']:.4f} < half-gap "
        f"{d['half_gap']:.4f}",
        f"seat count: split R-hat {d['seat_count_split_rhat']:.4f}, "
        f"ESS {d['seat_count_ess']:.1f}",
    ]
    for s in sorted(d["counts"]):
        chain = [100 * c[s] for c in d["per_chain_shares"]]
        lines.append(
            f"  {s} D: {d['counts'][s]:6,d}  {100 * d['shares'][s]:5.2f}%  "
            f"MCSE {100 * d['mcse'][s]:.2f} pts (ESS {d['ess'][s]:.0f})  "
            f"chains {min(chain):.1f}-{max(chain):.1f}%"
        )
    lines.append(f"enacted plan: {d['enacted_dem_seats']} D seats")
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    d = seat_distribution()
    for line in summary_lines(d):
        print(line)
    draw(d, args.out)
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
