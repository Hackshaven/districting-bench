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

#: A tightening level is refused if either side of the split is smaller than this
#: fraction of the ensemble. Iowa's competitiveness takes three values, so the
#: nominal q=0.25 and q=0.50 levels both keep 11,995 of 12,000 draws and the
#: "realistic" verdict for Iowa's top-ranked criterion was an 11,995-versus-5
#: comparison. A delta computed against five plans is not a measurement.
MIN_SIDE = 0.01

#: Replicates for the within-chain circular-shift null. The same null Experiment 2
#: uses: it preserves each chain's autocorrelation and marginal while destroying
#: the cross-criterion pairing, so it measures how large a delta this ensemble
#: produces by chance at its true effective sample size rather than its nominal one.
NULL_REPLICATES = 60


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


def _shift(values, offset):
    offset %= len(values)
    return values[offset:] + values[:offset]


def null_delta(rows_by_chain, criteria, target: str, others: list[str],
               q: float, rng) -> dict:
    """How large a |delta| this ensemble produces by chance, by circular shift.

    Nominal draw counts here are 8,000-12,000 while effective sample size on the
    columns that carry the ranking is 19-78. A threshold calibrated against the
    nominal count is calibrated against a sample that does not exist. The shift is
    applied within each chain, so each chain keeps its own autocorrelation and its
    own marginal and only the pairing between criteria is destroyed.
    """
    draws = []
    for _ in range(NULL_REPLICATES):
        shuffled = []
        for chain in rows_by_chain:
            offset = rng.randrange(len(chain))
            good = _shift([r for r in chain], offset)
            shuffled.append(good)
        pooled_target = [r for chain in rows_by_chain for r in chain]
        pooled_other = [r for chain in shuffled for r in chain]
        good = E2.goodness(pooled_target, target, criteria)
        cut = sorted(good, reverse=True)[max(1, int(round((1 - q) * len(good)))) - 1]
        keep = [i for i, v in enumerate(good) if v >= cut]
        drop = [i for i, v in enumerate(good) if v < cut]
        if not keep or not drop:
            continue
        worst = 0.0
        for name in others:
            vals = E2.goodness(pooled_other, name, criteria)
            worst = min(worst, cliffs_delta([vals[i] for i in keep],
                                            [vals[i] for i in drop]))
        draws.append(worst)
    draws.sort()
    return {"n": len(draws),
            "median": draws[len(draws) // 2] if draws else None,
            "p05": draws[max(0, int(0.05 * len(draws)) - 1)] if draws else None}


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

        floor = MIN_SIDE * len(rows)
        if len(keep) < floor or len(drop) < floor:
            levels.append({
                "tightening": q, "kept_fraction": len(keep) / len(rows),
                "n_kept": len(keep), "n_excluded": len(drop),
                "refused": True,
                "reason": (f"a criterion taking {len(set(good))} distinct values "
                           f"cannot be split at this level: {len(keep)} kept vs "
                           f"{len(drop)} excluded, and a delta computed against "
                           f"the smaller side is not a measurement"),
                "delta": {}, "median_shift_sd": {},
                "worst_delta": None, "worst_criterion": None,
            })
            continue

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
    usable = [l for l in levels if l["worst_delta"] is not None]
    worst_any = min((l["worst_delta"] for l in usable), default=None)
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
        "n_levels_refused": sum(1 for l in levels if l.get("refused")),
        "distinct_cuts": len({round(l["kept_fraction"], 6) for l in usable}),
        "raw_medians": {},
        "measure": "Cliffs delta, kept vs excluded; negative means the kept "
                   "plans are worse on the displaced criterion",
    }


def load_rows_by_chain(prefix: str) -> list[list[dict]]:
    """Draws grouped by chain, for the within-chain null."""
    path = E2.OUT / f"{prefix}-draws.csv.gz"
    keys = sorted({key for contest in (E2.PRIMARY_CONTEST, E2.ALTERNATE_CONTEST)
                   for key, _, _ in E2.criteria_for(contest).values()})
    by: dict[int, list[dict]] = {}
    with gzip.open(path, "rt", newline="") as handle:
        for record in csv.DictReader(handle):
            if record["chain_completed"] != "1":
                continue
            by.setdefault(int(record["chain_index"]), []).append(
                {key: float(record[key]) for key in keys})
    return [by[i] for i in sorted(by)]


#: Ideal district population per state, for translating a tolerance into the
#: deviation the law actually speaks about. Karcher v. Daggett struck down a
#: congressional plan at 0.6984% total deviation, so a criterion measured only
#: outside that window is not being measured where it legally operates.
IDEAL_DISTRICT = {"IA": 797_592, "CO": 721_714}
KARCHER_STRUCK_DOWN = 0.006984


def rank(state: str, prefix: str, contest: str = E2.PRIMARY_CONTEST,
         *, log=print) -> dict:
    rows = load_rows(prefix)
    by_chain = load_rows_by_chain(prefix)
    criteria = E2.criteria_for(contest)

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

    import random as _random
    rng = _random.Random(20260821)
    results = []
    for target in varying:
        others = [n for n in varying if n != target]
        result = sweep_one(rows, criteria, target, others)

        # What this ensemble produces by chance, at its real effective sample
        # size rather than its nominal one.
        strict = next((l["tightening"] for l in reversed(result["levels"])
                       if l.get("worst_delta") is not None), None)
        if strict is not None:
            result["null"] = null_delta(by_chain, criteria, target, others,
                                        strict, rng)
            worst = result["worst_delta_anywhere"]
            floor = result["null"]["p05"]
            result["clears_null"] = (worst is not None and floor is not None
                                     and worst < floor)
            result["binds"] = bool(result["binds"] and result["clears_null"])
            result["decorative"] = not result["binds"]

        # Raw units, because a delta is not a magnitude a reader can act on.
        key, direction, _ = criteria[target]
        raw = [r[key] for r in rows]
        result["raw_medians"] = {
            "criterion_median_all": st.median(raw),
            "criterion_median_strictest": None,
        }
        top = next((l for l in reversed(result["levels"])
                    if l.get("worst_delta") is not None), None)
        if top is not None:
            good = E2.goodness(rows, target, criteria)
            cut = sorted(good, reverse=True)[
                max(1, int(round((1 - top["tightening"]) * len(good)))) - 1]
            kept_raw = [r[key] for r, g in zip(rows, good) if g >= cut]
            result["raw_medians"]["criterion_median_strictest"] = st.median(kept_raw)
        results.append(result)
        null = result.get("null", {})
        log(f"  [{state}/{contest}] {target:20s} delta "
            f"{result['worst_delta_anywhere']:+.3f} null p05 "
            f"{null.get('p05', float('nan')):+.3f} -> "
            f"{'BINDS' if result['binds'] else 'non-displacing'}")

    ordered = sorted(results,
                     key=lambda r: (r["worst_delta_anywhere"]
                                    if r["worst_delta_anywhere"] is not None
                                    else 0.0))
    # Ranks 1 and 2 are routinely the same relationship read from both ends.
    # INSTRUMENT-AUDIT.md section 3 required Experiment 2's ordered-pair matrix
    # be collapsed for exactly this reason; this states it rather than repeating
    # the mistake silently.
    pairs = {}
    for r in results:
        top = next((l["worst_criterion"] for l in reversed(r["levels"])
                    if l.get("worst_criterion")), None)
        if top:
            pairs[tuple(sorted((r["criterion"], top)))] = True

    ideal = IDEAL_DISTRICT.get(state)
    spreads = [r["population_spread"] for r in rows]
    legal = None
    if ideal:
        legal = {
            "ideal_district": ideal,
            "spread_min_pct_of_ideal": 100 * min(spreads) / ideal,
            "spread_max_pct_of_ideal": 100 * max(spreads) / ideal,
            "karcher_struck_down_pct": 100 * KARCHER_STRUCK_DOWN,
            "entirely_inside_karcher": max(spreads) / ideal < KARCHER_STRUCK_DOWN,
            "entirely_outside_karcher": min(spreads) / ideal > KARCHER_STRUCK_DOWN,
        }

    return {
        "state": state,
        "contest": contest,
        "n_draws": len(rows),
        "n_chains": len(by_chain),
        "distinct_relationships_behind_ranking": len(pairs),
        "population_equality_legal_scope": legal,
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


# --------------------------------------------------------------------------- #
# the sampler half: population equality, the one criterion with a legal tolerance
# --------------------------------------------------------------------------- #

#: Epsilon values swept, from tighter than Iowa's enacted congressional plan to
#: looser than any congressional standard would permit. Karcher requires near-zero
#: deviation for congressional districts -- single-digit persons in practice -- so
#: the lower end is the legally interesting one and the upper end is included to
#: show what the criterion is holding back.
EPSILON_SWEEP = (1e-4, 2e-4, 5e-4, 1e-3, 5e-3, 1e-2, 5e-2)
SWEEP_CHAINS = 4
SWEEP_STEPS = 400


def epsilon_sweep(*, checkpoints: Path | None = None, jobs: int = 3,
                  log=print) -> dict:
    """Re-sample Iowa across population tolerances and measure what changes.

    The filter sweep above is structurally unable to answer this. Iowa's committed
    ensemble was drawn at epsilon = 2e-4, so every plan in it already satisfies a
    tight population standard; filtering within that measures how much *more*
    equality costs, not what the criterion is doing. Population equality is a
    parameter of the walk -- it decides which plans ReCom can reach at all -- and
    no post-hoc filter recovers the plans a looser tolerance would have admitted.

    Two things are measured. **Chain failure rate against epsilon**, which is the
    criterion binding on the search itself rather than on the plans: at Iowa's
    tightest tolerances ReCom cannot find a balanced cut and chains die, and that
    is the tolerance doing work. And **Cliff's delta between the loosest and
    tightest ensembles on every other criterion**, which is what a commission
    gives up elsewhere by insisting on population equality.
    """
    import experiment_2_tradeoffs as E2mod

    base = E2mod.IOWA
    ctx = E2mod.load_context(base, (E2mod.PRIMARY_CONTEST, E2mod.ALTERNATE_CONTEST))
    criteria = E2mod.criteria_for(E2mod.PRIMARY_CONTEST)

    import dataclasses
    cells = []
    for epsilon in EPSILON_SWEEP:
        spec = dataclasses.replace(base, epsilon=epsilon,
                                   chains=SWEEP_CHAINS, steps=SWEEP_STEPS)
        log(f"  [IA] epsilon={epsilon:g} sampling {SWEEP_CHAINS}x{SWEEP_STEPS}")
        chains = E2mod.measure_ensemble(spec, ctx, log=lambda *_: None, jobs=jobs,
                                        checkpoints=checkpoints)
        completed = [c for c in chains if c.completed]
        rows = [row for c in completed for row in c.rows]
        diagnostics = E2mod.diagnostics(chains)
        cells.append({
            "epsilon": epsilon,
            "chains_requested": SWEEP_CHAINS,
            "chains_completed": len(completed),
            "convergence": diagnostics.get("metrics", {}),
            "failure_rate": 1 - len(completed) / SWEEP_CHAINS,
            "n_draws": len(rows),
            "rows": rows,
            "chains": [c.rows for c in completed],
            "population_spread": {
                "min": min((r["population_spread"] for r in rows), default=None),
                "median": (st.median([r["population_spread"] for r in rows])
                           if rows else None),
                "max": max((r["population_spread"] for r in rows), default=None),
            },
        })
        log(f"    completed {len(completed)}/{SWEEP_CHAINS}, {len(rows)} draws, "
            f"median spread {cells[-1]['population_spread']['median']}")

    # The baseline must be the tightest cell in which EVERY chain completed.
    # ARCHITECTURE.md section 7: surviving seeds are not a random subset of
    # attempted seeds, so a cell with a 75% failure rate is a biased sample and
    # differences against it are partly selection rather than tolerance. Using
    # the tightest cell regardless -- epsilon = 1e-4, where 3 of 4 chains die --
    # produced two tradeoffs that do not survive this correction: an efficiency
    # gap delta of -0.413 and a competitiveness delta of +0.281, both of which
    # collapse to noise once the baseline is unbiased.
    def rung_p(tight_rows_by_chain, loose_rows_by_chain, name):
        """Chain-label permutation: how extreme is this rung among relabellings?

        Every 4-versus-4 split of the eight chains is a relabelling that carries
        no information about epsilon. If the observed delta is not extreme among
        them, the rung is measuring between-chain variation rather than tolerance.
        """
        import itertools
        chains = tight_rows_by_chain + loose_rows_by_chain
        n = len(tight_rows_by_chain)
        observed = cliffs_delta(
            E2mod.goodness([r for c in tight_rows_by_chain for r in c], name, criteria),
            E2mod.goodness([r for c in loose_rows_by_chain for r in c], name, criteria))
        more_extreme = 0
        splits = list(itertools.combinations(range(len(chains)), n))
        for pick in splits:
            left = [r for i in pick for r in chains[i]]
            right = [r for i in range(len(chains)) if i not in pick
                     for r in chains[i]]
            value = cliffs_delta(E2mod.goodness(left, name, criteria),
                                 E2mod.goodness(right, name, criteria))
            if value <= observed:
                more_extreme += 1
        return {"observed": observed, "n_splits": len(splits),
                "p": more_extreme / len(splits)}

    usable = [c for c in cells if c["n_draws"] > 0 and c["failure_rate"] == 0.0]
    excluded = [c for c in cells if c["n_draws"] > 0 and c["failure_rate"] > 0.0]
    curve, comparisons = [], []
    if len(usable) >= 2:
        tight = usable[0]
        for loose in usable[1:]:
            point = {"epsilon": loose["epsilon"], "deltas": {}, "permutation_p": {}}
            for name in criteria:
                if name == "population_equality":
                    continue
                a = E2mod.goodness(tight["rows"], name, criteria)
                b = E2mod.goodness(loose["rows"], name, criteria)
                if len(set(a) | set(b)) <= 1:
                    continue
                point["deltas"][name] = cliffs_delta(a, b)
                if name == "compactness_pp":
                    point["permutation_p"][name] = rung_p(
                        tight["chains"], loose["chains"], name)["p"]
            curve.append(point)
        widest = curve[-1]["deltas"]
        comparisons = sorted(
            ({"criterion": name, "delta_tight_vs_loose": value,
              "tight_epsilon": tight["epsilon"],
              "loose_epsilon": curve[-1]["epsilon"],
              "monotone": all(
                  abs(p["deltas"].get(name, 0)) <= abs(q["deltas"].get(name, 0)) + 1e-9
                  for p, q in zip(curve, curve[1:]))}
             for name, value in widest.items()),
            key=lambda c: c["delta_tight_vs_loose"])

    return {
        "state": "IA",
        "epsilons": list(EPSILON_SWEEP),
        "chains_per_epsilon": SWEEP_CHAINS,
        "steps_per_chain": SWEEP_STEPS,
        "cells": [{k: v for k, v in c.items() if k not in ("rows", "chains")}
                  for c in cells],
        "baseline_epsilon": (usable[0]["epsilon"] if usable else None),
        "excluded_from_comparison": [
            {"epsilon": c["epsilon"], "failure_rate": c["failure_rate"],
             "reason": "chains failed, so the surviving draws are a biased "
                       "subset (ARCHITECTURE.md section 7)"}
            for c in excluded],
        "cost_curve": curve,
        "cost_of_tight_equality": comparisons,
        "binds_on_the_search": any(c["failure_rate"] > 0 for c in cells),
        "interpretation": (
            "failure_rate against epsilon is the criterion binding on the search "
            "itself: where it is non-zero, the tolerance is excluding plans ReCom "
            "would otherwise have reached. delta_tight_vs_loose is what insisting "
            "on the tightest tolerance costs each other criterion, negative "
            "meaning the tight ensemble is worse on it."
        ),
    }


def kendall_tau(a: list[str], b: list[str]) -> float:
    """Rank correlation between two orderings of the same criteria."""
    pos = {name: i for i, name in enumerate(b)}
    common = [name for name in a if name in pos]
    concordant = discordant = 0
    for i in range(len(common)):
        for j in range(i + 1, len(common)):
            left = pos[common[i]] - pos[common[j]]
            if left < 0:
                concordant += 1
            elif left > 0:
                discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else 1.0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(OUT / "experiment-1-results.json"))
    parser.add_argument("--epsilon-sweep", action="store_true",
                        help="also re-sample Iowa across population tolerances; "
                             "the filter sweep cannot measure that criterion")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--checkpoints", default=str(OUT / "checkpoints"))
    args = parser.parse_args(argv)

    report = {"tightening": list(TIGHTENING), "binds_at": BINDS_AT,
              "min_side": MIN_SIDE, "null_replicates": NULL_REPLICATES,
              "states": {}}
    for state, prefix in (("IA", "ia"), ("CO", "co")):
        primary = rank(state, prefix, E2.PRIMARY_CONTEST)
        # The ranking is re-derived under the other 2020 contest on the same
        # draws. Experiment 2 established that a verdict which flips when the
        # office changes is a finding about the office; a ranked list that
        # reorders is the same problem, and this experiment shipped without the
        # check until the audit asked for it.
        alternate = rank(state, prefix, E2.ALTERNATE_CONTEST, log=lambda *_: None)
        primary["replication"] = {
            "contest": E2.ALTERNATE_CONTEST,
            "ranked": alternate["ranked"],
            "kendall_tau": kendall_tau(
                [r["criterion"] for r in primary["ranked"]],
                [r["criterion"] for r in alternate["ranked"]]),
            "binds_agree": sorted(r["criterion"] for r in primary["ranked"]
                                  if r["binds"]) == sorted(
                r["criterion"] for r in alternate["ranked"] if r["binds"]),
        }
        log_tau = primary["replication"]["kendall_tau"]
        print(f"  [{state}] ordering under {E2.ALTERNATE_CONTEST}: "
              f"Kendall tau {log_tau:+.3f}, "
              f"same criteria bind: {primary['replication']['binds_agree']}")
        report["states"][state] = primary
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2))
        print(f"wrote {path} ({len(report['states'])} state(s))")

    if args.epsilon_sweep:
        report["epsilon_sweep"] = epsilon_sweep(
            checkpoints=Path(args.checkpoints), jobs=args.jobs)
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"wrote {args.out} (with epsilon sweep)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
