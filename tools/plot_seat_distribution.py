#!/usr/bin/env python3
"""Figure: the neutral seat distribution for Iowa, with the enacted plan located.

Form: the data's job is magnitude across three discrete outcomes, so bars. One
series, so no legend -- the title names it. The enacted plan is a single point,
not a category, so it is annotated rather than colour-encoded; colouring its bucket
differently would imply a second series that does not exist.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SRC = Path("data/results/ia_neutral_seat_distribution.json")
OUT = Path("docs/figures/ia-neutral-seat-distribution.png")

INK, MUTED, HUE, SURFACE = "#1a1a1a", "#6b6b6b", "#4a6fa5", "#ffffff"

d = json.loads(SRC.read_text())
counts = {int(k): v for k, v in d["dem_seat_counts"].items()}
total = sum(counts.values())
xs = sorted(counts)
shares = [100 * counts[x] / total for x in xs]

fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=200)
fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)

bars = ax.bar(xs, shares, width=0.62, color=HUE, zorder=3)
for b in bars:                       # 4px-equivalent rounded data-end
    b.set_linewidth(0); b.set_joinstyle("round")

for x, s, n in zip(xs, shares, (counts[x] for x in xs)):
    ax.text(x + 0.30, s + 1.6, f"{s:.1f}%", ha="left", va="bottom",
            color=INK, fontsize=11, fontweight="bold", zorder=4)
    ax.text(x + 0.30, s + 0.2, f"{n:,} plans", ha="left", va="bottom",
            color=MUTED, fontsize=8.5, zorder=4)

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
# placed in the empty upper-left so the leader never crosses another bar
ax.annotate(
    f"Iowa's enacted plan\n{enacted} D seats\n{shares[xs.index(enacted)]:.1f}% of the ensemble",
    xy=(enacted, shares[xs.index(enacted)] + 0.6), xytext=(enacted - 0.30, 26),
    color=INK, fontsize=9.5, ha="left", va="center",
    arrowprops=dict(arrowstyle="->", color=INK, lw=1.4,
                    shrinkA=6, shrinkB=3,
                    connectionstyle="arc3,rad=0.0"), zorder=5)

ax.set_title("What Iowa's neutral process produces", color=INK,
             fontsize=13.5, fontweight="bold", loc="left", pad=16)
ax.text(0, 1.015,
        f"Democratic seats of 4, over {total:,} ReCom plans drawn without election data "
        f"({d['distinct_plans']} distinct)",
        transform=ax.transAxes, color=MUTED, fontsize=9.5, va="bottom")

ax.set_xlabel("Democratic seats won (of 4)", color=MUTED, fontsize=10)
ax.set_ylabel("share of neutral ensemble", color=MUTED, fontsize=10)
ax.set_xticks(xs); ax.set_ylim(0, 62); ax.set_xlim(-0.55, 2.85)
ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
ax.grid(axis="y", color="#e6e6e6", lw=0.8, zorder=0)
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color("#cccccc")
ax.tick_params(colors=MUTED, length=0)

fig.text(0.008, 0.005,
         "A 2-seat outcome is 43% of the neutral distribution, so a 2-seat shift "
         "is not detectable as a gerrymander on Iowa.",
         color=MUTED, fontsize=8.5, va="bottom")
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.tight_layout(rect=(0, 0.035, 1, 1))
fig.savefig(OUT, facecolor=SURFACE)
print("wrote", OUT)
