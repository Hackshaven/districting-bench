"""Null cases: neutrally drawn plans that *look* biased, and are not.

The positive half of the ground truth is easy — build a gerrymander and you know
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

The honest tension, stated because a reader could mistake it for a violation
--------------------------------------------------------------------------

**Generation is blind. Selection is not.** The plans come from a neutral sampler
that never sees votes; they are then scored with election data and the most
lopsided are kept. That ordering is the whole point — it is how a hard negative
set is built, and it is what makes the false positive rate mean something — but
it must be said out loud, because "we used election results to choose the null
cases" sounds like a firewall breach.

It is not one. ``tools/firewall.yaml`` permits ``adversarial`` to import
``evaluate``; what it forbids is partisan data reaching ``generate``, and nothing
here runs inside ``generate``. The neutral sampler is *injected* (see
``sampler`` below) precisely so that the drawing stays on the other side of the
boundary: this module never imports ``generate``, so it cannot pass election data
into it even by accident.

Two consequences the reader should carry forward:

* A false positive rate measured on these cases is a rate on *adversarially
  selected* nulls, not on a random neutral plan. It is a pessimistic bound,
  which is the direction an honest bound should point, and every
  :class:`NullCase` records its selection rank and the size of the pool it was
  chosen from so the selection pressure is visible.
* Selection is by seat outcome first. Tie-breaking uses the efficiency gap,
  which is one of the metrics a detector is likely to use — that makes the
  negatives harder still, and it is a deliberate choice, recorded in
  ``selection_rule`` rather than buried here.

What this produced on Iowa, and why the null half is the hard half
-----------------------------------------------------------------

Measured on a ReCom ensemble at k=4, epsilon=2e-4 (8 seeds x 250 steps; 2 seeds
died, a 25% chain failure rate, 1,575 draws, 331 distinct plans):

===================== =========== ===========
Democratic seats won  draws       share
===================== =========== ===========
0                     63          4.0%
1                     798         50.7%
2                     714         45.3%
===================== =========== ===========

Median 1. Three consequences, and they shape everything downstream:

* **A neutrally drawn Iowa map gives the Democrats two seats 45% of the time.**
  The seat-maximising search in ``gerrymander.py`` also tops out at two seats on
  a normal budget. So *a 2-seat Democratic gerrymander is not distinguishable
  from a neutral map by its seat count at all* — the detector has to work on
  where the plan sits in the ensemble's metric distributions, and a rule that
  looked at seats alone would be at chance. Only the 3-seat plan lies outside
  the neutral support.
* **The enacted 4R-0D map is in the bottom 4% of the neutral distribution.**
  The 63 draws of 1,575 that also sweep 4R-0D are the null cases that look most
  like it, and they were drawn without anyone seeing a vote total. That is the
  Chen & Rodden effect in one number, on this state, this cycle.
* **The efficiency gap is degenerate on those sweeps.** Every one of them
  reports +0.4163 to four decimals — the same value as the enacted plan —
  because when
  one party wins every district the wasted-vote arithmetic depends on the
  district populations and hardly at all on where the lines are. CRITERIA.md
  section 5.1 warns that most partisan metrics are unreliable where one party
  predominates; this is that warning arriving in the data, on the one metric the
  literature says to keep trusting. It is also why ``balance_directions``
  defaults to True: a strict ranking would fill the null set with those
  indistinguishable sweeps and never test the direction the gerrymander points.
"""

from __future__ import annotations

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
    "seat_distribution",
    "median_seats",
    "sampler_from_plans",
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

SELECTION_RULE = (
    "distinct neutral plans ranked by (|seats - ensemble median seats|, "
    "|efficiency gap|), descending; generation blind to votes, selection not"
)

SELECTION_RULE_BALANCED = SELECTION_RULE + (
    "; taken alternately from the two sides of the median, so the null set is "
    "not all one direction"
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
    """

    id: str
    plan: Plan
    party: str
    realized_seat_count: int
    seat_counts: tuple[int, int, int]
    ensemble_median_seats: float
    seat_shift: float
    intended_seat_shift: int
    efficiency_gap: float
    population_spread: int
    selection_rank: int
    selection_rule: str
    selection_statistic: tuple[float, float]
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
    drawn against those same arguments — :func:`sample_nulls` re-checks every
    plan it is handed against ``k`` and ``epsilon`` regardless.
    """
    frozen = tuple(dict(plan) for plan in plans)

    def sampler(adjacency, populations, k, epsilon, seeds):  # noqa: ARG001
        return frozen

    return sampler


def _party_seats(counts: tuple[int, int, int], party: str) -> int:
    return counts[0] if party == "D" else counts[1]


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
    require_legal: bool = True,
    balance_directions: bool = True,
    id_prefix: str = "null_geography",
    drawn_by: str = "injected neutral sampler",
) -> list[NullCase]:
    """Draw neutral plans, score them afterwards, keep the ones that look worst.

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
            and select — see the module docstring.
        sampler: the neutral draw. ``detect`` passes a wrapper around
            ``generate.ensemble``; :func:`sampler_from_plans` wraps plans that
            are already in hand. Keyword-only and without a default, because a
            null case is only meaningful if the caller knows exactly what drew
            it.
        party: whose seat count is the headline. Selection uses the *absolute*
            deviation from the median, so both directions are eligible; the
            party only fixes what ``realized_seat_count`` counts.
        n_select: how many cases to return.
        balance_directions: take cases alternately from above and below the
            ensemble median rather than in strict rank order. On Iowa this
            matters a great deal: the plans furthest from the median are the
            ones that sweep 4R-0D, and their efficiency gap is *identical* to
            three decimal places across every such plan (when one party wins
            every district the wasted-vote arithmetic barely depends on where
            the lines are), so a strict ranking fills the whole null set with
            one direction. The other side — neutral maps that hand the
            Democrats two seats — is the side that matters most, because it is
            the seat outcome the planted gerrymander also produces. Set False
            for a pure ranking.
        require_legal: drop plans that fail :func:`check_legality` at
            ``epsilon`` rather than presenting them as legal neutral maps. A
            ReCom draw at this ``epsilon`` satisfies it by construction; a
            sampler that was run at a looser tolerance does not, and silently
            keeping those would make the null set easier than it looks.
        id_prefix: scenario ids are ``f"{id_prefix}_{rank:02d}"``, matching the
            ``scenarios[].id`` convention in ARCHITECTURE section 5.
        drawn_by: free text recorded on every case, naming the sampler. Say what
            actually drew them; it is the only provenance a reader of
            bench-results.json gets.

    Returns:
        Up to ``n_select`` :class:`NullCase` objects, most extreme first. Fewer
        if the pool was small or ``require_legal`` removed candidates. Empty
        list if the sampler produced nothing usable.

    Raises:
        ValueError: on malformed inputs.
    """
    party = _check_party(party)
    if n_select < 1:
        raise ValueError(f"n_select must be >= 1; got {n_select}")
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
    seen: set = set()
    distinct: list[Plan] = []
    for plan in plans:
        key = _canonical(plan)
        if key in seen:
            continue
        seen.add(key)
        distinct.append(plan)

    # The median is taken over every draw, duplicates included, because that is
    # the sampler's distribution and the sampler's centre is what "neutral"
    # means here. Selection then ranks the *distinct* plans, so a plan the chain
    # happened to sit on for fifty steps does not take fifty slots in the null
    # set while still counting fifty times towards where the centre is.
    median = median_seats(plans, dem, rep, party)

    scored = []
    for plan in distinct:
        counts = seat_counts(plan, dem, rep)
        seats = _party_seats(counts, party)
        gap = efficiency_gap(plan, dem, rep)
        scored.append((abs(seats - median), abs(gap), plan, counts, seats, gap))

    # Deterministic order: by the selection statistic, then by a stable
    # tie-break on the plan itself, so the same pool always yields the same set.
    scored.sort(key=lambda row: (-row[0], -row[1], _order_key(row[2])))
    if balance_directions:
        scored = _interleave_by_direction(scored, median)

    cases: list[NullCase] = []
    for row in scored:
        if len(cases) >= n_select:
            break
        deviation, gap_size, plan, counts, seats, gap = row
        legality = check_legality(plan, adjacency, populations, k, epsilon)
        if require_legal and not legality.passed:
            continue
        rank = len(cases) + 1
        cases.append(
            NullCase(
                id=f"{id_prefix}_{rank:02d}",
                plan=plan,
                party=party,
                realized_seat_count=seats,
                seat_counts=counts,
                ensemble_median_seats=median,
                seat_shift=float(seats) - median,
                intended_seat_shift=0,
                efficiency_gap=gap,
                population_spread=legality.population_spread,
                selection_rank=rank,
                selection_rule=(
                    SELECTION_RULE_BALANCED if balance_directions else SELECTION_RULE
                ),
                selection_statistic=(float(deviation), float(gap_size)),
                pool_size=len(plans),
                distinct_pool_size=len(distinct),
                legality=legality,
                drawn_by=drawn_by,
            )
        )
    return cases


def _interleave_by_direction(scored, median: float):
    """Alternate between the two sides of the median, each side kept in rank order.

    A neutral plan that is extreme *upwards* and one that is extreme
    *downwards* are different negatives and a detector can fail on either. Plans
    sitting exactly on the median are not extreme in any direction and go last,
    in their own rank order.
    """
    above = [row for row in scored if row[4] > median]
    below = [row for row in scored if row[4] < median]
    level = [row for row in scored if row[4] == median]
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
