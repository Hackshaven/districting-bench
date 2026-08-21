"""Experiment 1 — criteria sensitivity: which criteria bind, and which are decorative.

``prompt.md``: *"Vary each criterion's weight and tolerance across its plausible
range; report which ones actually bind and which are decorative. Output a ranked
list."*

Two things about that instruction have to be answered before it can be obeyed.

**There are no weights.** ``prompt.md`` itself forbids the object whose weights
would be varied: *"If you find yourself writing a function called
`fairness_score()` that returns one number, stop."* Nor is a weighted objective
what the jurisdictions use. Iowa Code ch. 42 is **lexicographic** -- population
equality, then contiguity, then county integrity, then compactness -- and
Colorado's Amendments Y and Z likewise order rather than weight. A weight sweep
would be measuring the sensitivity of a scoring function this project declines to
build and no state applies. So this measures the other half of the instruction's
own wording: **tolerance**.

**Only one criterion has a tolerance anyone has ever stated.** ``docs/CRITERIA.md``
gives congressional population equality a near-zero deviation standard from
*Karcher v. Daggett*. Compactness has no threshold; competitiveness has no
threshold; the efficiency gap's threshold CRITERIA.md section 5 calls *"arbitrary
and sensitive to voter geography"*. A criterion for which nobody states a number
cannot bind, because binding requires a line to be on the wrong side of. That is
a finding about the criteria, not an obstacle to measuring them, and it is why the
sweep below is expressed in percentiles of each criterion's own ensemble
distribution: it is the only scale on which criteria with no legal threshold can
be compared with one that has.

What binding means here
-----------------------
A criterion **binds** if requiring plans to be good on it removes plans *and*
moves the rest of the picture. It is **decorative** if a commission could adopt
it, enforce it to the letter, and change nothing.

For criterion ``X`` at tightening level ``q`` -- keep only the draws in the best
``1 - q`` of the ensemble on ``X`` -- the cost is the largest displacement it
forces on any *other* criterion, measured as **Cliff's delta between the plans it
keeps and the plans it excludes**: the probability that a kept plan is better on
``Y`` than an excluded one, minus the probability that it is worse. A criterion
that can be tightened to the top decile without moving anything else is decorative
on this ensemble.

Cliff's delta rather than a shift in robust SDs, and the reason is a defect this
instrument had in its first form. Several Iowa criteria came back displacing the
efficiency gap by exactly -5.07 SD -- an identical, enormous number for unrelated
criteria, which is the signature of an artifact rather than a finding. Iowa's
efficiency gap is bimodal with its ensemble median sitting on the boundary between
modes, so any filter tips the median across the gap, and dividing that jump by a
robust spread of 0.015 manufactures five standard deviations of "cost".
``docs/experiment-2/INSTRUMENT-AUDIT.md`` predicted precisely this: *"the
conditional effect column is not a comparable magnitude ... it stepped from -0.00
to -4.95 between two adjacent settings. Report it as fired/not-fired, not as an
effect size."*

Cliff's delta has no scale estimator to be fooled by, is bounded in [-1, 1], is
invariant to any monotone rescaling of the criterion, and is unaffected by
multimodality because it compares ranks rather than centres. The median shift is
still reported for every cell, because it is legible and because a reader should
be able to see the artifact that the delta avoids -- it is simply not what decides
anything.

Two mechanisms, and only one of them can be measured by filtering
----------------------------------------------------------------
Compactness, county integrity, competitiveness and the fairness metrics are
properties of a finished plan, so a tolerance on them is a filter and can be swept
over the committed draws.

**Population equality is not.** It is a parameter of the sampler: epsilon decides
which plans ReCom can reach at all, and no post-hoc filter recovers the plans a
tighter epsilon would have excluded from the walk. It is also the criterion Iowa
ranks *first*. So it gets its own sweep, which re-samples.

Contiguity is not swept. Every ReCom draw is contiguous by construction, so a
contiguity filter excludes exactly nothing -- decorative inside this instrument,
absolutely binding outside it, and the difference is a property of the sampler
rather than of the criterion.

Relation to Experiment 2
------------------------
Experiment 2 asked, for each *pair*, whether prioritising A costs B. This asks,
for each criterion *alone*, whether constraining it does anything at all, and
ranks them. The conditional machinery is deliberately not shared: Experiment 2's
conditional test was found by audit to be a constant on coarse criteria, and its
decile is the thing that failed. This computes displacement directly and reports
the attainable range alongside it.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import experiment_2_tradeoffs as E2          # noqa: E402  (draws loader, criteria)

OUT = ROOT / "docs" / "experiment-1"

#: How hard the criterion is enforced: keep the best (1 - q) of the ensemble.
#: 0.0 is "adopt the criterion but never let it exclude anything"; 0.9 is "only
#: the best tenth of plans are acceptable", which is stricter than any real
#: commission applies to a criterion with no stated threshold.
TIGHTENING = (0.0, 0.25, 0.50, 0.75, 0.90)

#: Cliff's delta at which imposing one criterion is treated as visibly moving
#: another. 0.147 is the conventional "small" effect boundary (Romano et al.,
#: "Appropriate statistics for ordinal level data", 2006), and it is deliberately
#: the *lowest* published threshold: this experiment asks whether a criterion does
#: anything at all, so the bar for "does something" should be generous. A
#: criterion that cannot clear a small effect at the top decile is decorative by
#: any standard.
BINDS_AT = 0.147

#: The tightening level treated as "a commission actually applying this criterion".
REALISTIC = 0.50


def cliffs_delta(kept, excluded) -> float:
    """P(kept better) - P(kept worse), computed from ranks in O(n log n).

    The pairwise definition is O(n*m) and these sets run to five figures, so it
    goes through the Mann-Whitney statistic, which is the same number. Ties are
    handled by average ranks and so contribute zero to the delta, which is the
    behaviour the pairwise definition has.
    """
    n1, n2 = len(kept), len(excluded)
    if n1 == 0 or n2 == 0:
        return 0.0
    pooled = sorted((v, 0) for v in kept)
    pooled += sorted((v, 1) for v in excluded)
    pooled.sort(key=lambda t: t[0])

    rank_sum = 0.0
    i = 0
    while i < len(pooled):
        j = i
        while j + 1 < len(pooled) and pooled[j + 1][0] == pooled[i][0]:
            j += 1
        average = (i + j) / 2 + 1                 # ranks are 1-based
        rank_sum += average * sum(1 for k in range(i, j + 1) if pooled[k][1] == 0)
        i = j + 1

    u = rank_sum - n1 * (n1 + 1) / 2
    return 2 * u / (n1 * n2) - 1


def robust_sd(values) -> float:
    """MAD rescaled to a normal SD, falling back to the plain SD. See E2 D-023."""
    if not values:
        return 0.0
    centre = st.median(values)
    mad = 1.4826 * st.median([abs(v - centre) for v in values])
    if mad > 0:
        return mad
    mean = st.fmean(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def load_rows(prefix: str) -> list[dict]:
    """Completed-chain draws from the committed Experiment 2 file."""
    path = E2.OUT / f"{prefix}-draws.csv.gz"
    keys = sorted({key for contest in (E2.PRIMARY_CONTEST, E2.ALTERNATE_CONTEST)
                   for key, _, _ in E2.criteria_for(contest).values()})
    rows = []
    with gzip.open(path, "rt", newline="") as handle:
        for record in csv.DictReader(handle):
            if record["chain_completed"] != "1":
                continue
            rows.append({key: float(record[key]) for key in keys})
    return rows


def sweep_one(rows, criteria, target: str, others: list[str]) -> dict:
    """Tighten one criterion; measure what it costs every other criterion."""
    good = E2.goodness(rows, target, criteria)
    columns = {name: E2.goodness(rows, name, criteria) for name in others}
    scales = {name: robust_sd(values) for name, values in columns.items()}
    baseline = {name: st.median(values) for name, values in columns.items()}

    levels = []
    for q in TIGHTENING:
        if q == 0.0:
            # The criterion is adopted but never excludes anything. Nothing can
            # move, and saying so explicitly keeps the zero row honest rather
            # than comparing a set with itself.
            levels.append({
                "tightening": 0.0, "kept_fraction": 1.0, "n_kept": len(rows),
                "delta": {name: 0.0 for name in others},
                "median_shift_sd": {name: 0.0 for name in others},
                "worst_delta": 0.0, "worst_criterion": None,
            })
            continue

        cut = sorted(good, reverse=True)[max(1, int(round((1 - q) * len(good)))) - 1]
        keep = [i for i, v in enumerate(good) if v >= cut]
        drop = [i for i, v in enumerate(good) if v < cut]

        delta, shift = {}, {}
        for name in others:
            values = columns[name]
            kept_vals = [values[i] for i in keep]
            drop_vals = [values[i] for i in drop]
            delta[name] = cliffs_delta(kept_vals, drop_vals)
            shift[name] = ((st.median(kept_vals) - baseline[name]) / scales[name]
                           if scales[name] else None)
        levels.append({
            "tightening": q,
            "kept_fraction": len(keep) / len(rows),
            "n_kept": len(keep),
            "n_excluded": len(drop),
            "delta": delta,
            "median_shift_sd": shift,
            "worst_delta": min(delta.values()) if delta else None,
            "worst_criterion": (min(delta, key=delta.get) if delta else None),
        })

    realistic = next(l for l in levels if l["tightening"] == REALISTIC)
    worst_any = min((l["worst_delta"] for l in levels
                     if l["worst_delta"] is not None), default=None)
    return {
        "criterion": target,
        "distinct_values": len(set(good)),
        "levels": levels,
        "worst_delta_at_realistic": realistic["worst_delta"],
        "worst_delta_anywhere": worst_any,
        "binds": (worst_any is not None and worst_any <= -BINDS_AT),
        "binds_at_realistic": (realistic["worst_delta"] is not None
                               and realistic["worst_delta"] <= -BINDS_AT),
        "decorative": (worst_any is not None and worst_any > -BINDS_AT),
        "strictest_kept_fraction": levels[-1]["kept_fraction"],
        "measure": "Cliffs delta, kept vs excluded; negative means the kept "
                   "plans are worse on the displaced criterion",
    }


def rank(state: str, prefix: str, *, log=print) -> dict:
    rows = load_rows(prefix)
    criteria = E2.criteria_for(E2.PRIMARY_CONTEST)

    varying, degenerate = [], {}
    for name, (key, _, _) in criteria.items():
        values = [row[key] for row in rows]
        if len(set(values)) > 1:
            varying.append(name)
        else:
            degenerate[name] = {
                "constant_value": values[0],
                "reason": ("the units are the subdivisions, so no plan over them "
                           "can split one: the criterion is enforced by the "
                           "choice of unit, not by the plan search"
                           if name == "county_integrity"
                           else "did not vary over this ensemble"),
            }

    results = []
    for target in varying:
        others = [n for n in varying if n != target]
        result = sweep_one(rows, criteria, target, others)
        results.append(result)
        log(f"  [{state}] {target:20s} worst delta "
            f"{result['worst_delta_anywhere']:+.3f} -> "
            f"{'BINDS' if result['binds'] else 'decorative'}")

    ordered = sorted(results,
                     key=lambda r: (r["worst_delta_anywhere"]
                                    if r["worst_delta_anywhere"] is not None
                                    else 0.0))
    return {
        "state": state,
        "n_draws": len(rows),
        "source": f"docs/experiment-2/{prefix}-draws.csv.gz",
        "tightening_levels": list(TIGHTENING),
        "binds_at": BINDS_AT,
        "realistic_level": REALISTIC,
        "degenerate": degenerate,
        "ranked": [
            {"rank": i + 1, "criterion": r["criterion"],
             "worst_delta": r["worst_delta_anywhere"],
             "displaces": next((l["worst_criterion"] for l in r["levels"]
                                if l["worst_delta"] == r["worst_delta_anywhere"]),
                               None),
             "binds": r["binds"], "binds_at_realistic": r["binds_at_realistic"]}
            for i, r in enumerate(ordered)
        ],
        "detail": results,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(OUT / "experiment-1-results.json"))
    args = parser.parse_args(argv)

    report = {"tightening": list(TIGHTENING), "binds_at": BINDS_AT, "states": {}}
    for state, prefix in (("IA", "ia"), ("CO", "co")):
        report["states"][state] = rank(state, prefix)
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2))
        print(f"wrote {path} ({len(report['states'])} state(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
