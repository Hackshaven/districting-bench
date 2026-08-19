"""Null cases: neutrally drawn plans that *look* biased, and are not.

The positive half of the ground truth is easy -- build a gerrymander and you know
it is one. This half is the hard one, and CRITERIA.md section 8 says so outright:

    Null cases are as important as positive cases. A detector that flags every
    map in a state with clustered urban population has learned political
    geography, not gerrymandering.

Because Democratic voters cluster in Polk, Linn, Johnson and Scott while
Republican voters spread evenly across rural Iowa, a map drawn with no reference
whatever to election results can still return a lopsided seat outcome (Chen &
Rodden 2013; CRITERIA.md section 5.4). Those maps are exactly what a detector
must not flag. A null set of *typical* neutral plans tests nothing, so this
module deliberately selects the most extreme-looking ones it can find.

Round 2 measured the selection rule and it was measuring itself
---------------------------------------------------------------

The previous version of this module ranked candidates by
``(|seats - ensemble median|, |efficiency gap|)``. ``|efficiency gap|`` is a
monotone transform of the detector's own test statistic, so as the candidate
pool grew the selected nulls moved further into the tail of the very quantity
the detector thresholds, and **any** correct percentile-tail rule flagged them.
Measured, with the reference held fixed: the selected stratum's false positive
rate rose to 1.00 as the pool grew while the random stratum's fell to 0.125.
That stratum was measuring the selection rule, not the detector.

Re-measured on one footing -- pool = all 24,247 draws, 15 cases selected,
reference = the same ensemble -- as the median *two-sided* percentile
outlierness the selected nulls have in that ensemble's ``|efficiency gap|``
distribution. 1.000 means sitting exactly where a 0.99 two-sided rule fires:

============================== ============= =============
selection rule                  balanced      strict rank
                                (the default)
============================== ============= =============
``(|seats - median|, |EG|)``    **0.999**     **0.997**
``|seats - median|`` alone      0.636         0.472
minority-party concentration    0.988         0.687
uniform (the control)           0.745         0.745
============================== ============= =============

Two things to read off it, and the second one is uncomfortable.

**The tautology is gone.** The round-2 rule puts its cases at 0.999 at *every*
pool size, because it ranks on the statistic being thresholded; there is no
ensemble large enough for it to report anything else. Nothing in the replacement
reads a metric the detector reads.

**It is not sufficient, in this state.** The balanced concentration stratum
still lands at 0.988, and it drifts upward as the pool grows (0.586 at 200
draws, 0.586 at 1,000, 0.879 at 5,000, 0.991 at 24,247; 0.586 -> 0.848 unbalanced).
The mechanism is specific and worth naming: ``balance_directions`` deliberately
takes half the cases from the thin side of the median, which in Iowa is the
4R-0D sweeps -- and **every sweep has the same efficiency gap, +0.4163, pinned
at the top of the distribution**, because when one party wins every district the
wasted-vote arithmetic barely depends on the lines. Any rule that reaches for
extreme *geography* in Iowa collects sweeps, and sweeps are in the tail of a
metric that is degenerate on them. That is a fact about the efficiency gap in a
state one party dominates (CRITERIA.md 5.1), not a defect in the selector, and
it does not go away by choosing a different selector.

What follows is the reporting rule, not a tuning fix: **each stratum is reported
with its selector named and its rate given separately.** A pooled rate over
strata this different is a weighted average of unrelated quantities whose
weights are whoever set ``n_select``.

What replaced it
----------------

:func:`vote_concentration` -- the Herfindahl index of *one party's own votes*
across the districts of a plan. It reads a single party's vote totals and never
a ratio between the two, so it is not a fairness measure and is not a transform
of any metric in ``evaluate.partisan``: measured against the detector's metrics
on the same 2,217 plans, Spearman -0.419 against ``|efficiency gap|`` and 0.005
against ``|mean-median|``. It is the Chen & Rodden mechanism stated directly:
how packed the clustered party's voters are by this particular map. A neutral
map that packs them hard is the null case CRITERIA.md section 5.4 is about, and
whether a detector flags it is the question the false positive rate exists to
answer.

Three strata, never pooled
--------------------------

``concentration`` (hard negatives by the mechanism), ``seat_outcome`` (hard
negatives by realized outcome, which in Iowa is nearly the old rule -- see
above), and ``random`` (a uniform control). :func:`sample_strata` returns them as
a dict keyed by stratum with disjoint plans, because a pooled false positive
rate over strata this different is a weighted average of two unrelated
quantities whose weights are set by whoever chose ``n_select``.

The honest tension, stated because a reader could mistake it for a violation
--------------------------------------------------------------------------

**Generation is blind. Selection is not.** The plans come from a neutral sampler
that never sees votes; they are then scored with election data and the most
extreme are kept. That ordering is the whole point -- it is how a hard negative
set is built -- but it must be said out loud, because "we used election results
to choose the null cases" sounds like a firewall breach.

It is not one. ``tools/firewall.yaml`` permits ``adversarial`` to import
``evaluate``; what it forbids is partisan data reaching ``generate``, and nothing
here runs inside ``generate``. The neutral sampler is *injected* (see
``sampler`` below) precisely so that the drawing stays on the other side of the
boundary: this module never imports ``generate``, so it cannot pass election data
into it even by accident.

A false positive rate measured on a hard stratum is a rate on *adversarially
selected* nulls, not on a random neutral plan. It is a pessimistic bound, which
is the direction an honest bound should point, and every :class:`NullCase`
records its stratum, its selection rank and the size of the pool it was chosen
from so the selection pressure is visible.

What this produced on Iowa, and why the null half is the hard half
-----------------------------------------------------------------

Measured on a ReCom ensemble at k=4, epsilon=2e-4 (12 chains x 2,200 steps,
24,247 draws, 2,217 distinct plans):

===================== =========== ===========
Democratic seats won  draws       share
===================== =========== ===========
0                     136         0.6%
1                     12,790      52.7%
2                     11,321      46.7%
===================== =========== ===========

Median 1. Three consequences, and they shape everything downstream:

* **A neutrally drawn Iowa map gives the Democrats two seats 47% of the time.**
  The seat-maximising search in ``gerrymander.py`` also tops out at two seats on
  a normal budget. So *a 2-seat Democratic gerrymander is not distinguishable
  from a neutral map by its seat count at all* -- the detector has to work on
  where the plan sits in the ensemble's metric distributions, and a rule that
  looked at seats alone would be at chance. Only the 3-seat plan lies outside
  the neutral support.
* **The enacted 4R-0D map is in the bottom 0.6% of the neutral distribution.**
  The 136 draws that also sweep 4R-0D are the null cases that look most like it,
  and they were drawn without anyone seeing a vote total. That is the Chen &
  Rodden effect in one number, on this state, this cycle.
* **The efficiency gap is degenerate on those sweeps.** Every one of them
  reports +0.4163 to four decimals -- the same value as the enacted plan --
  because when one party wins every district the wasted-vote arithmetic depends
  on the district populations and hardly at all on where the lines are.
  CRITERIA.md section 5.1 warns that most partisan metrics are unreliable where
  one party predominates; this is that warning arriving in the data, on the one
  metric the literature says to keep trusting. It is also why
  ``balance_directions`` defaults to True: a strict ranking would fill the null
  set with those indistinguishable sweeps and never test the direction the
  gerrymander points.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

from evaluate.partisan import efficiency_gap, seat_counts
from evaluate.plan import Plan

from .gerrymander import PARTIES, LegalityRecord, check_legality

__all__ = [
    "NullCase",
    "NeutralSampler",
    "sample_nulls",
    "sample_strata",
    "null_strata",
    "seat_distribution",
    "median_seats",
    "sampler_from_plans",
    "vote_concentration",
    "STRATA",
    "ID_PREFIXES",
    "SELECTION_RULES",
    "SELECTION_RULE",
    "SELECTION_RULE_BALANCED",
]

# What the sampler contract is. A callable taking the same arguments a neutral
# ensemble needs and returning plans. `detect` supplies one that wraps
# `generate.ensemble.run_chains`; this module must not import `generate` itself
# (tools/firewall.yaml), and injecting the sampler is how the neutral draw stays
# on the far side of that boundary.
NeutralSampler = Callable[
    [Mapping[str, Iterable[str]], Mapping[str, int], int, float, Sequence[int]],
    Iterable[Plan],
]

#: The strata this module can produce, in the order a report should list them.
#: They are *strata*, not a single set: see the module docstring on why a pooled
#: rate over them is not a quantity.
STRATA: tuple[str, ...] = ("concentration", "seat_outcome", "random")

#: Scenario-id prefix per stratum. ``concentration`` keeps the ``null_geography``
#: prefix it has always had, and not only to spare the consumers that filter on
#: it: geography *is* what that stratum embodies (Chen & Rodden packing), and the
#: selector's name is carried separately on ``NullCase.stratum``. The other two
#: are named for what they are.
ID_PREFIXES: dict[str, str] = {
    "concentration": "null_geography",
    "seat_outcome": "null_seat_outcome",
    "random": "null_random",
}

SELECTION_RULES: dict[str, str] = {
    "concentration": (
        "distinct neutral plans ranked by the Herfindahl concentration of the "
        "minority party's own votes across districts, descending (Chen & Rodden "
        "packing; CRITERIA.md 5.4). The statistic reads one party's vote totals "
        "and no ratio between the two, so it is not a transform of any metric "
        "the detector thresholds. Generation blind to votes, selection not"
    ),
    "seat_outcome": (
        "distinct neutral plans ranked by |realized seats - ensemble median "
        "seats|, descending, ties broken on the plan itself and not on any "
        "metric. Read its rate knowing that in Iowa seats and |efficiency gap| "
        "are rank-correlated at -0.868, which makes this the stratum closest "
        "in spirit to the round-2 rule -- though not in effect: measured on "
        "24,247 draws it selects cases at 0.636 median |EG| outlierness "
        "against that rule's 0.999. Generation blind to votes, selection not"
    ),
    "random": (
        "uniform draw, without replacement, from the distinct neutral plans of "
        "the pool; not selected for looking biased at all. The control stratum"
    ),
}

#: Kept for callers that recorded the round-2 rule string. The rule it names is
#: gone; see the module docstring for why.
SELECTION_RULE = SELECTION_RULES["concentration"]
SELECTION_RULE_BALANCED = SELECTION_RULE + (
    "; taken alternately from the two sides of the median seat count, so the "
    "null set is not all one direction"
)


@dataclass(frozen=True)
class NullCase:
    """One neutrally drawn plan, kept because it looks biased.

    ``seat_shift`` is against the **ensemble median**, not against the enacted
    plan: the question a null case answers is "how far from the neutral centre
    can a neutral process land", and the neutral centre is the ensemble's own
    median. It is a float because a median of an even number of draws can fall
    on a half-seat.

    ``intended_seat_shift`` is 0 for every null case, always. That is what makes
    it a negative: nobody built it to move a seat. A detector flagging one of
    these is a false positive by construction (ARCHITECTURE section 6).

    ``efficiency_gap`` is **recorded and never ranked on**. It is here because a
    reader of the report wants to see it; the moment it re-enters
    ``selection_statistic`` this module is measuring the detector's own
    statistic again.
    """

    id: str
    plan: Plan
    party: str
    stratum: str
    realized_seat_count: int
    seat_counts: tuple[int, int, int]
    ensemble_median_seats: float
    seat_shift: float
    intended_seat_shift: int
    efficiency_gap: float
    vote_concentration: float
    population_spread: int
    selection_rank: int
    selection_rule: str
    selection_statistic: dict[str, float]
    pool_size: int
    distinct_pool_size: int
    legality: LegalityRecord
    drawn_by: str

    @property
    def legal(self) -> bool:
        return self.legality.passed


def sampler_from_plans(plans: Iterable[Plan]) -> NeutralSampler:
    """Wrap an already-drawn list of plans as a :data:`NeutralSampler`.

    For a caller that has an ensemble in hand (``EnsembleResult.plans``) and for
    tests. It ignores its arguments, which is safe only because the plans were
    drawn against those same arguments -- :func:`sample_nulls` re-checks every
    plan it is handed against ``k`` and ``epsilon`` regardless.
    """
    frozen = tuple(dict(plan) for plan in plans)

    def sampler(adjacency, populations, k, epsilon, seeds):  # noqa: ARG001
        return frozen

    return sampler


def _party_seats(counts: tuple[int, int, int], party: str) -> int:
    return counts[0] if party == "D" else counts[1]


def vote_concentration(plan: Plan, votes: Mapping[str, int]) -> float:
    """Herfindahl index of one party's votes across the districts of ``plan``.

    ``sum_d (v_d / V)^2`` where ``v_d`` is that party's vote total in district
    ``d``. It runs from ``1/k`` (the party's voters split perfectly evenly
    across districts) to ``1`` (all of them in one district), and it is the
    packing half of the Chen & Rodden mechanism written down: a map that
    concentrates the clustered party's voters wastes them, whether or not anyone
    drew it to.

    **Why this and not a fairness metric.** It reads exactly one party's vote
    totals. Every metric in ``evaluate.partisan`` needs both parties -- wasted
    votes on each side, or a vote *share* -- so this is not a monotone
    transform of any of them, which is the property the null selection rule has
    to have (module docstring). Measured against them on 2,217 neutral Iowa
    plans: Spearman -0.419 against ``|efficiency gap|``, 0.005 against
    ``|mean-median|``.

    Pass the **minority** party's votes -- the geographically clustered one, D
    in Iowa. Passing the majority's measures the mirror-image quantity and
    selects different plans; nothing here guesses which you meant.
    """
    totals: dict[int, float] = {}
    for unit, district in plan.items():
        totals[int(district)] = totals.get(int(district), 0.0) + float(votes[unit])
    total = sum(totals.values())
    if total <= 0:
        raise ValueError(
            "vote_concentration: the party has no votes in this plan; the "
            "concentration of nothing is undefined"
        )
    return sum((value / total) ** 2 for value in totals.values())


def seat_distribution(
    plans: Iterable[Plan],
    dem: Mapping[str, int],
    rep: Mapping[str, int],
    party: str = "D",
) -> dict[int, int]:
    """``{seats won by party: how many plans}``, ascending by seat count.

    The shape of this distribution is the null hypothesis a detector is
    implicitly testing against, so it is worth reporting on its own.
    """
    party = _check_party(party)
    counts: dict[int, int] = {}
    for plan in plans:
        seats = _party_seats(seat_counts(plan, dem, rep), party)
        counts[seats] = counts.get(seats, 0) + 1
    return {seats: counts[seats] for seats in sorted(counts)}


def median_seats(
    plans: Sequence[Plan],
    dem: Mapping[str, int],
    rep: Mapping[str, int],
    party: str = "D",
) -> float:
    """Median seats won by ``party`` across ``plans``."""
    party = _check_party(party)
    if not plans:
        raise ValueError("no plans given; the median seat count is undefined")
    return float(
        statistics.median(
            _party_seats(seat_counts(plan, dem, rep), party) for plan in plans
        )
    )


def sample_nulls(
    adjacency: Mapping[str, Iterable[str]],
    populations: Mapping[str, int],
    k: int,
    epsilon: float,
    seeds: Sequence[int],
    dem: Mapping[str, int],
    rep: Mapping[str, int],
    *,
    sampler: NeutralSampler,
    party: str = "D",
    n_select: int = 8,
    stratum: str = "concentration",
    require_legal: bool = True,
    balance_directions: bool = True,
    id_prefix: str | None = None,
    drawn_by: str = "injected neutral sampler",
    seed: int = 0,
    exclude: Iterable[Plan] = (),
) -> list[NullCase]:
    """Draw neutral plans, score them afterwards, keep one stratum of them.

    Args:
        adjacency: rook graph, ``{GEOID: [GEOID, ...]}``.
        populations: ``{GEOID: persons}``.
        k: number of districts.
        epsilon: the population tolerance the neutral draw was run at; every
            selected plan is re-checked against it here.
        seeds: seeds handed to the sampler. Reproducibility of the null set is
            the sampler's responsibility plus this function's ordering, which is
            deterministic given the plans.
        dem, rep: two-party votes by unit. **Used only after the draw**, to score
            and select -- see the module docstring.
        sampler: the neutral draw. ``detect`` passes a wrapper around
            ``generate.ensemble``; :func:`sampler_from_plans` wraps plans that
            are already in hand. Keyword-only and without a default, because a
            null case is only meaningful if the caller knows exactly what drew
            it.
        party: whose seat count is the headline, and whose votes the
            ``concentration`` stratum measures the packing of. Pass the
            clustered minority party (D in Iowa).
        n_select: how many cases to return.
        stratum: which of :data:`STRATA` to select. ``"concentration"`` is the
            hard negative by mechanism and the default; ``"seat_outcome"`` is
            the hard negative by realized outcome, and in Iowa it is nearly the
            round-2 rule -- read the module docstring before using its number;
            ``"random"`` is the uniform control. Use :func:`sample_strata` to get
            more than one, with the plans kept disjoint.
        balance_directions: for the two hard strata, take cases alternately from
            above and below the ensemble median rather than in strict rank
            order. On Iowa this matters a great deal: the plans furthest from
            the median are the ones that sweep 4R-0D, and their efficiency gap
            is *identical* to three decimal places across every such plan, so a
            strict ranking fills the whole null set with one direction. Ignored
            by the ``random`` stratum, which has no direction.
        require_legal: drop plans that fail :func:`check_legality` at
            ``epsilon`` rather than presenting them as legal neutral maps. A
            ReCom draw at this ``epsilon`` satisfies it by construction; a
            sampler that was run at a looser tolerance does not, and silently
            keeping those would make the null set easier than it looks.
        id_prefix: scenario ids are ``f"{id_prefix}_{rank:02d}"``, matching the
            ``scenarios[].id`` convention in ARCHITECTURE section 5. Defaults to
            :data:`ID_PREFIXES` for the stratum, which keeps the strata
            distinguishable in a report that lists their ids.
        drawn_by: free text recorded on every case, naming the sampler. Say what
            actually drew them; it is the only provenance a reader of
            bench-results.json gets.
        seed: used by the ``random`` stratum only. The other two are
            deterministic given the pool.
        exclude: plans to leave out of the candidate set, compared up to
            district relabelling. This is how :func:`sample_strata` keeps strata
            disjoint.

    Returns:
        Up to ``n_select`` :class:`NullCase` objects, most extreme first (in
        pool order for ``random``). Fewer if the pool was small or
        ``require_legal`` removed candidates. Empty list if the sampler produced
        nothing usable.

    Raises:
        ValueError: on malformed inputs.
    """
    party = _check_party(party)
    if n_select < 1:
        raise ValueError(f"n_select must be >= 1; got {n_select}")
    if stratum not in STRATA:
        raise ValueError(f"stratum must be one of {STRATA}; got {stratum!r}")
    if int(k) != k or k < 2:
        raise ValueError(f"k must be an integer >= 2; got {k!r}")
    if not 0 < epsilon < 1:
        raise ValueError(f"epsilon must lie in (0, 1); got {epsilon!r}")

    plans = [dict(plan) for plan in sampler(adjacency, populations, k, epsilon, seeds)]
    if not plans:
        return []

    # De-duplicate up to district relabelling: two plans that differ only in
    # which district got which number are the same plan, and would otherwise
    # take two slots in the null set while testing one thing.
    blocked = {_canonical(dict(plan)) for plan in exclude}
    seen: set = set()
    distinct: list[Plan] = []
    for plan in plans:
        key = _canonical(plan)
        if key in seen:
            continue
        seen.add(key)
        if key in blocked:
            continue
        distinct.append(plan)
    if not distinct:
        return []

    # The median is taken over every draw, duplicates included, because that is
    # the sampler's distribution and the sampler's centre is what "neutral"
    # means here. Selection then ranks the *distinct* plans, so a plan the chain
    # happened to sit on for fifty steps does not take fifty slots in the null
    # set while still counting fifty times towards where the centre is.
    median = median_seats(plans, dem, rep, party)
    votes = dem if party == "D" else rep

    scored = []
    for plan in distinct:
        counts = seat_counts(plan, dem, rep)
        seats = _party_seats(counts, party)
        concentration = vote_concentration(plan, votes)
        statistic = {
            "seat_deviation": abs(seats - median),
            "vote_concentration": concentration,
        }
        scored.append((statistic, plan, counts, seats, concentration))

    if stratum == "concentration":
        scored.sort(
            key=lambda row: (-row[0]["vote_concentration"], _order_key(row[1]))
        )
    elif stratum == "seat_outcome":
        scored.sort(key=lambda row: (-row[0]["seat_deviation"], _order_key(row[1])))
    else:
        scored.sort(key=lambda row: _order_key(row[1]))
        random.Random(seed).shuffle(scored)
    if balance_directions and stratum != "random":
        scored = _interleave_by_direction(scored, median)

    rule = SELECTION_RULES[stratum]
    if balance_directions and stratum != "random":
        rule += (
            "; taken alternately from the two sides of the median seat count, "
            "so the null set is not all one direction"
        )
    prefix = id_prefix if id_prefix is not None else ID_PREFIXES[stratum]

    cases: list[NullCase] = []
    for statistic, plan, counts, seats, concentration in scored:
        if len(cases) >= n_select:
            break
        legality = check_legality(plan, adjacency, populations, k, epsilon)
        if require_legal and not legality.passed:
            continue
        rank = len(cases) + 1
        cases.append(
            NullCase(
                id=f"{prefix}_{rank:02d}",
                plan=plan,
                party=party,
                stratum=stratum,
                realized_seat_count=seats,
                seat_counts=counts,
                ensemble_median_seats=median,
                seat_shift=float(seats) - median,
                intended_seat_shift=0,
                efficiency_gap=efficiency_gap(plan, dem, rep),
                vote_concentration=concentration,
                population_spread=legality.population_spread,
                selection_rank=rank,
                selection_rule=rule,
                selection_statistic=dict(statistic),
                pool_size=len(plans),
                distinct_pool_size=len(distinct),
                legality=legality,
                drawn_by=drawn_by,
            )
        )
    return cases


def sample_strata(
    adjacency: Mapping[str, Iterable[str]],
    populations: Mapping[str, int],
    k: int,
    epsilon: float,
    seeds: Sequence[int],
    dem: Mapping[str, int],
    rep: Mapping[str, int],
    *,
    sampler: NeutralSampler,
    n_per_stratum: Mapping[str, int] | int = 8,
    strata: Sequence[str] = STRATA,
    **kwargs,
) -> dict[str, list[NullCase]]:
    """Every stratum at once, with the plans kept disjoint, keyed by stratum.

    The return type is the argument: a caller who wants a single pooled false
    positive rate has to write the pooling itself and own it. Strata are filled
    in the order given, and each one excludes the plans the earlier ones took,
    so no plan is a negative twice and no rate double-counts it.

    ``n_per_stratum`` is either one count for all of them or a mapping from
    stratum name to count.
    """
    wanted = {name: 0 for name in strata}
    for name in strata:
        if name not in STRATA:
            raise ValueError(f"unknown stratum {name!r}; expected one of {STRATA}")
        wanted[name] = (
            int(n_per_stratum)
            if isinstance(n_per_stratum, int)
            else int(n_per_stratum.get(name, 0))
        )
    out: dict[str, list[NullCase]] = {}
    taken: list[Plan] = []
    for name in strata:
        if wanted[name] < 1:
            out[name] = []
            continue
        cases = sample_nulls(
            adjacency,
            populations,
            k,
            epsilon,
            seeds,
            dem,
            rep,
            sampler=sampler,
            n_select=wanted[name],
            stratum=name,
            exclude=tuple(taken),
            **kwargs,
        )
        out[name] = cases
        taken.extend(case.plan for case in cases)
    return out


def _interleave_by_direction(scored, median: float):
    """Alternate between the two sides of the median, each side kept in rank order.

    A neutral plan that is extreme *upwards* and one that is extreme
    *downwards* are different negatives and a detector can fail on either. Plans
    sitting exactly on the median are not extreme in any direction and go last,
    in their own rank order.
    """
    above = [row for row in scored if row[3] > median]
    below = [row for row in scored if row[3] < median]
    level = [row for row in scored if row[3] == median]
    # The larger side leads, so that when one side is empty the result is
    # exactly the strict ranking.
    first, second = (above, below) if len(above) >= len(below) else (below, above)
    out = []
    for left, right in zip(first, second):
        out.append(left)
        out.append(right)
    longer = first if len(first) > len(second) else second
    out.extend(longer[min(len(first), len(second)):])
    out.extend(level)
    return out


def _canonical(plan: Plan) -> frozenset:
    groups: dict[int, set] = {}
    for unit, district in plan.items():
        groups.setdefault(int(district), set()).add(unit)
    return frozenset(frozenset(members) for members in groups.values())


def _order_key(plan: Plan) -> tuple:
    """A stable total order on plans, for reproducible tie-breaking."""
    return tuple(int(plan[unit]) for unit in sorted(plan))


def _check_party(party: str) -> str:
    if not isinstance(party, str) or party.upper() not in PARTIES:
        raise ValueError(f"party must be one of {PARTIES}; got {party!r}")
    return party.upper()


#: The name this function had while it was being written. ``sample_strata`` is
#: the name the rest of the tree uses; both refer to the same function.
null_strata = sample_strata
