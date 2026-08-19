"""Seat-maximising plan construction, subject to every legal constraint.

This module manufactures ground truth. A plan that comes out of here is a
gerrymander *because it was built to be one*, and its magnitude is known: the
realised seat count is measured by ``evaluate.partisan.seat_count``, never
merely intended. That is the whole reason detection is optimisable at all —
docs/ARCHITECTURE.md section 6, docs/CRITERIA.md section 8.

What "legal" means here is Iowa Code ch. 42 plus the federal floor, in the
statutory order (CRITERIA.md section 2.1):

1. **population equality** — every district within ``epsilon`` of ideal. As in
   ``generate.ensemble``, ``epsilon`` bounds each *district's* deviation, not the
   max-min spread, so the permitted spread is up to ``2 * epsilon * ideal``
   (docs/FEASIBILITY.md section 5.2 corrects a reading that conflated the two).
2. **contiguity** — every district connected on the rook graph.
3. **whole counties** — automatic: the units *are* counties, so a plan cannot
   split one. County splits are identically zero for Iowa congressional
   (FEASIBILITY.md section 5.3), which is also why they carry no detection signal.
4. **compactness** — measured elsewhere, never constrained here. Ch. 42 ranks it
   last and a gerrymanderer would not respect it; letting the search ignore it is
   the point, and the resulting compactness is a *symptom* for the detector to
   find, not a constraint the search obeys.

Every one of those is checked on the returned plan by :func:`check_legality`,
which also calls ``evaluate.plan.validate`` as the authority on the structural
invariants, and :func:`maximize_seats` refuses to return a plan whose record does
not pass. Asserted, not assumed.

Iowa is hard for this, and the honest number goes in the result
------------------------------------------------------------

Iowa 2020 is R+8.4 statewide (two-party D share 0.4582) and the enacted plan is
already 4R-0D. A *Republican* gerrymander therefore has no headroom at all: you
cannot win more than 4 of 4, and the neutral map already does. Measured on the
99-county rook graph at k=4, epsilon=2e-4, against the enacted plan as baseline:

============ ========= ============= =====================================
target       ceiling   seat shift    effort to reach it
============ ========= ============= =====================================
R            4 of 4    **0**         every seed tried, seconds
D            3 of 4    **+3**        ~200,000 iterations x 12 restarts
D            2 of 4    +2            every seed tried, seconds
============ ========= ============= =====================================

Two things make those numbers claims rather than guesses:

* **4 D seats is arithmetically impossible, not merely unfound.** Winning a
  district takes more than half its two-party votes, so winning all four takes
  more than half the statewide two-party total — 828,367 votes. The Democrats
  cast 759,061. Three is therefore the true ceiling and the search reaches it.
* **The R shift is zero by definition of the ceiling**, since the baseline is
  already at it. No amount of search moves it, and the gate at a 2-seat shift
  (CRITERIA.md section 8) simply cannot be exercised in the R direction in this
  state. That is a finding about Iowa, not a defect in the search.

The 3-seat D plan is razor thin — three districts at 50.17%, 50.07% and 50.12%
D against one packed at 32.7% — which is why it takes an order of magnitude more
search than the 2-seat one: the legal region around it is tiny. The default
settings here are the cheap ones, so ``maximize_seats`` at its defaults usually
returns the 2-seat plan; ``seat_ceiling_at_work_epsilon`` on the result says
when the search saw a better seat structure and could not legalise it, and
:func:`achievable_seats` measures the range rather than asserting it.

For calibration against the neutral baseline: a ReCom ensemble at the same
epsilon gives the Democrats 2 seats in 45% of draws and has a median of 1 (see
``nulls.py``). A 2-seat "gerrymander" is therefore *not* distinguishable from a
neutral map by seat count alone in Iowa. Only the 3-seat plan sits outside the
neutral ensemble's support entirely.

Method
------

Local search over boundary-county reassignments — the neighbourhood
docs/FEASIBILITY.md section 5.3 found sufficient to beat the enacted plan's
population equality in seconds. Three phases per restart, all seeded:

* **balance** — greedy best-improvement descent on population, from a random
  seeded growth plan, into a loose *working* band (``work_epsilon``). Population
  and adjacency only.
* **seats** — simulated annealing on a seat objective, hard-constrained to stay
  inside the working band. The objective is the realised seat count plus a
  sigmoid relaxation of it, which is what makes cracking and packing appear:
  the sigmoid saturates, so pushing an already-lost district from 0.35 to 0.30
  costs almost nothing while lifting a district from 0.48 to 0.52 pays. Several
  plans are kept *at each seat level*, because planting a 1-seat shift needs a
  1-seat plan rather than a truncated 2-seat one, and because the next phase
  can fail on a given plan and need another at the same level.
* **repair** — tighten from the working band to the real ``epsilon`` while
  holding the seat count, by best-improvement descent over single moves and
  boundary *swaps*, with random kicks on stalling. Swaps are what make the tight
  band reachable at all: the smallest county is 3,704 persons, so a single move
  cannot land inside a +/-159-person band, whereas exchanging two counties of
  similar size moves a district by their difference.

A working band is needed because the tight band and the county granularity are
incompatible for single moves; optimising seats directly at ``epsilon`` finds
almost no legal states to move between.

Firewall
--------

``adversarial`` may import ``evaluate`` and nothing else from ``src/``
(tools/firewall.yaml). In particular it does **not** import ``generate``: the
starting plans here are built locally from population and adjacency. That
duplication is deliberate (ARCHITECTURE section 1) — these are not neutral
ensemble draws and must not be mistaken for them. Nothing in this module is a
sampler; it is a search, it is biased on purpose, and its output is only ever a
positive case for the detector.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from dataclasses import dataclass
from typing import Iterable, Mapping

from evaluate.partisan import district_shares, seat_counts
from evaluate.plan import Plan, districts, validate

__all__ = [
    "SearchExhausted",
    "LegalityRecord",
    "GerrymanderResult",
    "check_legality",
    "maximize_seats",
    "plant_gerrymander",
    "achievable_seats",
    "PARTIES",
]

PARTIES = ("D", "R")

# Search defaults, measured on the Iowa 99-county graph at k=4, epsilon=2e-4.
# They reach the R ceiling (4 seats) on every seed tried and 2 of the 3
# available D seats in a few seconds. The third D seat needs roughly
# max_iterations=200_000 and restarts=12 — see the module docstring; the default
# is the cheap setting, not the exhaustive one, and the result says which
# ceiling it reached rather than implying it is the ceiling.
DEFAULT_MAX_ITERATIONS = 60_000
DEFAULT_RESTARTS = 6
DEFAULT_WORK_EPSILON = 0.10
DEFAULT_REPAIR_ROUNDS = 60
#: Distinct plans kept per seat level by the seat phase, each of which the
#: repair phase may try. See _anneal_seats on why one is not enough.
DEFAULT_KEEP_PER_LEVEL = 6
DEFAULT_SIGMOID = 0.03
DEFAULT_SURROGATE_WEIGHT = 0.5

# Seed derivation domain. `generate.seeds.derive` does the same job on the other
# side of the firewall; this package may not import it, and re-deriving here is
# the deliberate duplication ARCHITECTURE section 1 requires rather than an
# oversight. The domain string differs so the two never produce the same stream.
_SEED_DOMAIN = b"districting-bench/adversarial/gerrymander/v1"


class SearchExhausted(RuntimeError):
    """No plan satisfying every legal constraint was found within the budget.

    This is a statement about the search, not a proof of infeasibility. It is
    raised rather than returning a plan that fails a constraint, and
    :func:`plant_gerrymander` converts it into ``None``.
    """


# --------------------------------------------------------------------------- #
# legality
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class LegalityRecord:
    """Evidence that every constraint was checked, and what it came to.

    ``checks`` is the record: a name -> pass/fail for each constraint, and
    :attr:`passed` is true only if every one of them passed. ``notes`` carries
    the reason for anything that failed, plus the standing note on whole
    counties. Nothing here is inferred from the search having "succeeded" — the
    checks are re-run on the finished plan.
    """

    k: int
    epsilon: float
    ideal_population: float
    district_populations: dict[int, int]
    max_deviation_persons: int
    max_deviation_fraction: float
    population_spread: int
    checks: dict[str, bool]
    notes: dict[str, str]

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    def failures(self) -> list[str]:
        return sorted(name for name, ok in self.checks.items() if not ok)


def check_legality(
    plan: Plan,
    adjacency: Mapping[str, Iterable[str]],
    populations: Mapping[str, int],
    k: int,
    epsilon: float,
) -> LegalityRecord:
    """Check every legal constraint on ``plan`` and record the outcome of each.

    The structural invariants (assignment, ids ``1..k``, contiguity) are checked
    twice on purpose: once here in a form that yields one boolean per constraint,
    and once by ``evaluate.plan.validate``, which is the contract's authority
    (ARCHITECTURE section 3) but raises on the first failure and so cannot
    produce a per-constraint record on its own. If the two ever disagree,
    ``validate`` wins and the ``validate`` check fails.
    """
    if int(k) != k or k < 1:
        raise ValueError(f"k must be a positive integer; got {k!r}")
    k = int(k)
    if not 0 < epsilon < 1:
        raise ValueError(f"epsilon must lie in (0, 1); got {epsilon!r}")

    units = set(adjacency)
    checks: dict[str, bool] = {}
    notes: dict[str, str] = {}

    assigned = set(plan)
    checks["every_unit_assigned_exactly_once"] = assigned == units
    if assigned != units:
        notes["every_unit_assigned_exactly_once"] = (
            f"{len(units - assigned)} unassigned, "
            f"{len(assigned - units)} not in the unit graph"
        )

    members = districts(plan)
    ids = set(members)
    checks["district_ids_are_1_to_k"] = ids <= set(range(1, k + 1))
    checks["no_empty_district"] = set(range(1, k + 1)) <= ids
    if not checks["district_ids_are_1_to_k"]:
        stray = sorted(ids - set(range(1, k + 1)))
        notes["district_ids_are_1_to_k"] = f"stray ids {stray}"
    if not checks["no_empty_district"]:
        notes["no_empty_district"] = f"empty {sorted(set(range(1, k + 1)) - ids)}"

    # A plan naming units the graph does not contain cannot be checked for
    # contiguity or population at all -- there is nowhere to look them up. Those
    # checks are recorded as failed with the reason, rather than raising a
    # KeyError from inside a function whose job is to report what failed.
    unknown = assigned - units
    if unknown:
        for name in ("contiguous_on_rook_graph", "population_within_epsilon"):
            checks[name] = False
            notes[name] = (
                f"not checkable: the plan names {len(unknown)} unit(s) outside "
                "the graph, e.g. " + ", ".join(sorted(unknown)[:3])
            )
    else:
        disconnected = [
            d
            for d, units_in in members.items()
            if not _connected(set(units_in), adjacency)
        ]
        checks["contiguous_on_rook_graph"] = not disconnected
        if disconnected:
            notes["contiguous_on_rook_graph"] = (
                f"districts {sorted(disconnected)} disconnected"
            )

    # Whole counties: the unit of assignment is the county, so a district is a
    # union of whole counties by construction and a split is unrepresentable.
    # Recorded rather than silently assumed, because the claim is what makes
    # Iowa Code ch. 42 criterion 3 automatically satisfied here.
    checks["whole_units_no_splits"] = True
    notes["whole_units_no_splits"] = (
        "units are whole counties; a plan assigns each county to exactly one "
        "district, so county splits are 0 by construction (FEASIBILITY 5.3)"
    )

    ideal = sum(int(populations[u]) for u in units) / k if units else 0.0
    band = epsilon * ideal
    totals: dict[int, int] = {}
    max_dev, spread = 0.0, 0
    if not unknown:
        for d, units_in in members.items():
            totals[d] = sum(int(populations[u]) for u in units_in)
        if totals:
            max_dev = max(abs(t - ideal) for t in totals.values())
            spread = max(totals.values()) - min(totals.values())
        checks["population_within_epsilon"] = bool(totals) and max_dev <= band + 1e-9
        notes["population_within_epsilon"] = (
            f"epsilon bounds each district's deviation from ideal, not the "
            f"spread: |dev| <= {band:.1f} persons, observed {max_dev:.1f}"
        )

    try:
        validate(plan, adjacency, k)
        checks["evaluate_plan_validate"] = True
    except ValueError as exc:
        checks["evaluate_plan_validate"] = False
        notes["evaluate_plan_validate"] = str(exc)[:300]

    return LegalityRecord(
        k=k,
        epsilon=float(epsilon),
        ideal_population=float(ideal),
        district_populations=dict(sorted(totals.items())),
        max_deviation_persons=int(round(max_dev)),
        max_deviation_fraction=(max_dev / ideal) if ideal else 0.0,
        population_spread=int(spread),
        checks=checks,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# result
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GerrymanderResult:
    """A plan built to favour one party, with its magnitude measured.

    ``realized_seat_count`` and ``baseline_seat_count`` are both produced by
    ``evaluate.partisan.seat_counts`` — the shift is a measurement, not the
    search's intention. ``intended_seat_shift`` records what was asked for
    (``None`` for an open-ended maximisation) so that a caller can see the two
    side by side; :func:`plant_gerrymander` refuses to return a result where
    they differ.

    Two fields are easy to misread:

    * ``district_shares`` is the **target party's** share in each district, so
      the same plan reports different numbers under ``target_party="D"`` and
      ``"R"``. ``seat_counts`` is always ``(D, R, tied)`` in that order, from
      ``evaluate.partisan``, and is not relabelled.
    * ``seat_ceiling_at_work_epsilon`` is the best seat count the seat phase
      reached inside the *loose working band*, which can exceed
      ``realized_seat_count``: a seat structure can exist at 10% population
      deviation and have no counterpart inside the real band. When the two
      differ, the search found a gerrymander it could not legalise, and saying
      so is the point of carrying the field.
    """

    plan: Plan
    target_party: str
    realized_seat_count: int
    baseline_seat_count: int
    seat_shift: int
    population_spread: int
    iterations: int
    legality: LegalityRecord

    k: int
    epsilon: float
    seed: int
    intended_seat_shift: int | None
    seat_counts: tuple[int, int, int]
    district_shares: dict[int, float]
    baseline_plan: Plan
    baseline_source: str
    baseline_legality: LegalityRecord
    seat_ceiling_at_work_epsilon: int
    restarts_run: int
    restart_used: int
    work_epsilon: float
    seconds: float

    @property
    def legal(self) -> bool:
        return self.legality.passed


# --------------------------------------------------------------------------- #
# public search
# --------------------------------------------------------------------------- #

def maximize_seats(
    target_party: str,
    adjacency: Mapping[str, Iterable[str]],
    populations: Mapping[str, int],
    dem: Mapping[str, int],
    rep: Mapping[str, int],
    k: int,
    epsilon: float,
    seed: int,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    *,
    restarts: int = DEFAULT_RESTARTS,
    baseline_plan: Plan | None = None,
    target_seats: int | None = None,
    work_epsilon: float = DEFAULT_WORK_EPSILON,
    repair_rounds: int = DEFAULT_REPAIR_ROUNDS,
    sigmoid: float = DEFAULT_SIGMOID,
    surrogate_weight: float = DEFAULT_SURROGATE_WEIGHT,
) -> GerrymanderResult:
    """Search for the legal plan that wins ``target_party`` the most seats.

    Args:
        target_party: ``"D"`` or ``"R"``. The party whose seat count is
            maximised. Everything else is symmetric between the two.
        adjacency: ``{GEOID: [GEOID, ...]}`` rook graph; defines the unit set.
        populations: ``{GEOID: persons}``.
        dem, rep: two-party votes by unit, from ``evaluate.elections.two_party``.
        k: number of districts.
        epsilon: per-district population tolerance as a fraction of ideal. The
            returned plan satisfies it; see the module docstring on spread.
        seed: every random draw is derived from this. Same inputs and same seed
            give the same plan.
        max_iterations: annealing budget for the seat phase, per restart. The
            ``iterations`` field of the result counts *every* candidate move
            evaluated across all phases and restarts, which is larger.
        restarts: independent seeded restarts; the best legal plan wins. More
            than one is not optional when the ceiling is the question, and the
            reason is structural rather than a matter of luck: Polk County is
            492,401 persons, 62% of an Iowa district, so *no* single-county move
            or swap can ever relocate it inside any usable population band. Its
            district is fixed by the plan the restart starts from, and restarts
            are the only way the search explores placing it differently.
        baseline_plan: the plan ``seat_shift`` is measured against. Defaults to a
            neutral reference plan built here from population and adjacency only
            (never from votes), reported as
            ``baseline_source="neutral_reference"``. Pass the enacted plan, or
            an ensemble-median plan, to measure the shift against that instead
            — which is what detection wants.
        target_seats: if given, search for a plan winning *exactly* this many
            seats rather than as many as possible. Used by
            :func:`plant_gerrymander` to plant a specified magnitude.
        work_epsilon: the loose population band the seat phase runs inside. Must
            be wide enough that moving one county keeps a district legal; on
            Iowa counties anything below about 0.005 strands the search.
        repair_rounds: descent-and-kick rounds available to tighten from
            ``work_epsilon`` to ``epsilon``.
        sigmoid: temperature of the sigmoid relaxation of the seat count, in
            vote-share units. Smaller is a sharper approximation of the step.
        surrogate_weight: weight on the summed sigmoid relative to one seat.

    Returns:
        A :class:`GerrymanderResult` whose plan has been re-checked against every
        constraint. ``legality.passed`` is always true here — a plan that fails
        is never returned.

    Raises:
        SearchExhausted: no legal plan (at ``target_seats``, if given) was found
            within the budget.
        ValueError: on malformed inputs.
    """
    started = time.perf_counter()
    party = _check_party(target_party)
    _check_inputs(adjacency, populations, dem, rep, k, epsilon, work_epsilon)
    if restarts < 1:
        raise ValueError(f"restarts must be >= 1; got {restarts}")
    if max_iterations < 1:
        raise ValueError(f"max_iterations must be >= 1; got {max_iterations}")
    if target_seats is not None and not 0 <= target_seats <= k:
        raise ValueError(f"target_seats must lie in 0..{k}; got {target_seats}")

    units = sorted(adjacency)
    adj = {u: tuple(sorted(adjacency[u])) for u in units}
    pops = {u: int(populations[u]) for u in units}
    target_votes = dem if party == "D" else rep
    other_votes = rep if party == "D" else dem
    ideal = sum(pops.values()) / k
    band = epsilon * ideal
    work_band = work_epsilon * ideal

    counter = _Counter()

    # ---- baseline ---------------------------------------------------------
    if baseline_plan is None:
        base_rng = random.Random(_derive(seed, "baseline", 0))
        base = _neutral_reference(
            adj, pops, units, k, band, work_band, base_rng, counter
        )
        baseline_source = "neutral_reference"
    else:
        base = dict(baseline_plan)
        baseline_source = "supplied"
    baseline_legality = check_legality(base, adj, pops, k, epsilon)
    base_seats = _party_seats(base, dem, rep, party)

    # ---- restarts ---------------------------------------------------------
    best: tuple[tuple[int, int], Plan, int, int] | None = None
    ceiling_seen = 0
    for index in range(restarts):
        rng = random.Random(_derive(seed, "restart", index))
        start = _neutral_reference(
            adj, pops, units, k, band, work_band, rng, counter, tighten=False
        )
        state = _State(start, adj, pops, target_votes, other_votes, k)
        by_seats = _anneal_seats(
            state, rng, max_iterations, work_band, sigmoid, surrogate_weight, counter
        )
        if by_seats:
            ceiling_seen = max(ceiling_seen, max(by_seats))
        wanted = (
            [target_seats]
            if target_seats is not None
            else sorted(by_seats, reverse=True)
        )
        for seats in wanted:
            if seats not in by_seats:
                continue
            if best is not None and target_seats is None and seats < best[0][0]:
                break  # cannot beat what another restart already legalised
            found = None
            for candidate in by_seats[seats]:
                found = _repair(
                    _State(candidate, adj, pops, target_votes, other_votes, k),
                    rng,
                    band,
                    seats,
                    repair_rounds,
                    counter,
                )
                if found is not None:
                    break
            if found is None:
                continue
            spread, plan = found
            key = (seats, -spread)
            if best is None or key > best[0]:
                best = (key, plan, spread, index)
            break

    if best is None:
        raise SearchExhausted(
            f"no plan satisfying epsilon={epsilon} was found for target_party="
            f"{party}"
            + (f" at exactly {target_seats} seats" if target_seats is not None else "")
            + f" in {restarts} restart(s) of {max_iterations} iterations "
            f"(seat ceiling reached at work_epsilon={work_epsilon}: {ceiling_seen}). "
            "This is a statement about the search budget, not a proof that no "
            "such plan exists."
        )

    (seats, _), plan, spread, restart_used = best
    legality = check_legality(plan, adj, pops, k, epsilon)
    if not legality.passed:  # pragma: no cover - the repair phase enforces this
        raise AssertionError(
            "maximize_seats produced a plan that fails "
            f"{legality.failures()}; refusing to return it"
        )
    counts = seat_counts(plan, dem, rep)
    realized = counts[0] if party == "D" else counts[1]
    if realized != seats:  # pragma: no cover - internal/evaluate disagreement
        raise AssertionError(
            f"internal seat count {seats} disagrees with "
            f"evaluate.partisan.seat_counts {counts} for party {party}"
        )
    return GerrymanderResult(
        plan=plan,
        target_party=party,
        realized_seat_count=realized,
        baseline_seat_count=base_seats,
        seat_shift=realized - base_seats,
        population_spread=spread,
        iterations=counter.value,
        legality=legality,
        k=k,
        epsilon=float(epsilon),
        seed=int(seed),
        intended_seat_shift=(
            None if target_seats is None else target_seats - base_seats
        ),
        seat_counts=counts,
        district_shares=_shares_for(plan, dem, rep, party),
        baseline_plan=base,
        baseline_source=baseline_source,
        baseline_legality=baseline_legality,
        seat_ceiling_at_work_epsilon=ceiling_seen,
        restarts_run=restarts,
        restart_used=restart_used,
        work_epsilon=float(work_epsilon),
        seconds=time.perf_counter() - started,
    )


def plant_gerrymander(
    target_party: str,
    seat_shift: int,
    adjacency: Mapping[str, Iterable[str]],
    populations: Mapping[str, int],
    dem: Mapping[str, int],
    rep: Mapping[str, int],
    k: int,
    epsilon: float,
    seed: int,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    *,
    baseline_plan: Plan | None = None,
    **kwargs,
) -> GerrymanderResult | None:
    """Plant a gerrymander of exactly ``seat_shift`` seats, or return ``None``.

    ``None`` means the magnitude was not reached — most often because it is not
    reachable at all (Iowa cannot give R a positive shift: the neutral map
    already wins every seat), sometimes because the budget ran out. Either way
    the caller gets ``None`` rather than an exception to swallow or, worse, a
    near miss quietly relabelled as the magnitude that was asked for. The
    returned result always satisfies
    ``realized_seat_count - baseline_seat_count == seat_shift``.

    A negative ``seat_shift`` is meaningful and allowed: it plants a plan that
    *sacrifices* seats for the target party, which is the same construction seen
    from the other party's side.
    """
    party = _check_party(target_party)
    if not isinstance(seat_shift, int) or isinstance(seat_shift, bool):
        raise TypeError(f"seat_shift must be an int; got {seat_shift!r}")

    if baseline_plan is None:
        # The baseline has to be fixed before the search, since the requested
        # magnitude is relative to it. maximize_seats would otherwise build one
        # per call, and this function calls it twice.
        base_rng = random.Random(_derive(seed, "baseline", 0))
        units = sorted(adjacency)
        adj = {u: tuple(sorted(adjacency[u])) for u in units}
        pops = {u: int(populations[u]) for u in units}
        ideal = sum(pops.values()) / k
        baseline_plan = _neutral_reference(
            adj,
            pops,
            units,
            k,
            epsilon * ideal,
            kwargs.get("work_epsilon", DEFAULT_WORK_EPSILON) * ideal,
            base_rng,
            _Counter(),
        )
    base_seats = _party_seats(baseline_plan, dem, rep, party)
    wanted = base_seats + seat_shift
    if not 0 <= wanted <= k:
        return None
    try:
        result = maximize_seats(
            party,
            adjacency,
            populations,
            dem,
            rep,
            k,
            epsilon,
            seed,
            max_iterations,
            baseline_plan=baseline_plan,
            target_seats=wanted,
            **kwargs,
        )
    except SearchExhausted:
        return None
    if result.seat_shift != seat_shift:  # pragma: no cover - guarded above
        return None
    return result


def achievable_seats(
    adjacency: Mapping[str, Iterable[str]],
    populations: Mapping[str, int],
    dem: Mapping[str, int],
    rep: Mapping[str, int],
    k: int,
    epsilon: float,
    seed: int,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    *,
    baseline_plan: Plan | None = None,
    **kwargs,
) -> dict:
    """Measure the seat ceiling, and hence the achievable shift, both ways.

    Returns a dict keyed by party with the highest seat count a legal plan
    reached, the baseline seat count it is measured against, and the resulting
    shift — plus ``max_shift``, the largest shift available in *either*
    direction. In Iowa that number is 2, and it is available only to D.
    """
    source = "supplied" if baseline_plan is not None else "neutral_reference"
    out: dict = {"baseline_source": source}
    for party in PARTIES:
        result = maximize_seats(
            party,
            adjacency,
            populations,
            dem,
            rep,
            k,
            epsilon,
            _derive(seed, f"ceiling-{party}", 0),
            max_iterations,
            baseline_plan=baseline_plan,
            **kwargs,
        )
        if baseline_plan is None:
            baseline_plan = result.baseline_plan  # share it across both parties
            out["baseline_source"] = result.baseline_source
        out[party] = {
            "max_seats": result.realized_seat_count,
            "baseline_seats": result.baseline_seat_count,
            "max_shift": result.seat_shift,
            "population_spread": result.population_spread,
            "plan": result.plan,
        }
    out["max_shift"] = max(out[p]["max_shift"] for p in PARTIES)
    out["baseline_plan"] = baseline_plan
    return out


# --------------------------------------------------------------------------- #
# search internals
# --------------------------------------------------------------------------- #

class _Counter:
    """Total candidate moves evaluated, across every phase and restart."""

    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = 0

    def bump(self, n: int = 1) -> None:
        self.value += n


class _State:
    """A plan plus the per-district sums the search needs, updated in place."""

    __slots__ = (
        "plan", "adj", "pops", "target_votes", "other_votes", "k",
        "members", "totals", "tv", "ov", "units",
    )

    def __init__(self, plan, adj, pops, target_votes, other_votes, k):
        self.plan = dict(plan)
        self.adj = adj
        self.pops = pops
        self.target_votes = target_votes
        self.other_votes = other_votes
        self.k = k
        self.units = tuple(sorted(plan))
        self.members = {d: set() for d in range(1, k + 1)}
        for unit, d in self.plan.items():
            self.members[d].add(unit)
        self.totals = {d: sum(pops[u] for u in m) for d, m in self.members.items()}
        self.tv = {d: sum(target_votes[u] for u in m) for d, m in self.members.items()}
        self.ov = {d: sum(other_votes[u] for u in m) for d, m in self.members.items()}

    def move(self, unit: str, source: int, dest: int) -> None:
        self.members[source].discard(unit)
        self.members[dest].add(unit)
        self.plan[unit] = dest
        p = self.pops[unit]
        self.totals[source] -= p
        self.totals[dest] += p
        t = self.target_votes[unit]
        o = self.other_votes[unit]
        self.tv[source] -= t
        self.tv[dest] += t
        self.ov[source] -= o
        self.ov[dest] += o

    def undo(self, moves) -> None:
        for unit, source, dest in moves:
            self.move(unit, source, dest)

    def seats(self) -> int:
        return sum(1 for d in self.tv if self.tv[d] > self.ov[d])

    def objective(self, sigmoid: float, weight: float) -> tuple[float, int]:
        seats = 0
        surrogate = 0.0
        for d in self.tv:
            t, o = self.tv[d], self.ov[d]
            if t > o:
                seats += 1
            share = 0.5 if t + o == 0 else t / (t + o)
            surrogate += 1.0 / (1.0 + math.exp(-(share - 0.5) / sigmoid))
        return seats + weight * surrogate, seats

    def excess(self, band: float, ideal: float) -> float:
        return sum(max(0.0, abs(t - ideal) - band) for t in self.totals.values())

    def spread(self) -> int:
        return max(self.totals.values()) - min(self.totals.values())


def _connected(members: set, adjacency: Mapping[str, Iterable[str]]) -> bool:
    if not members:
        return False
    start = next(iter(members))
    seen = {start}
    stack = [start]
    while stack:
        unit = stack.pop()
        for other in adjacency[unit]:
            if other in members and other not in seen:
                seen.add(other)
                stack.append(other)
    return len(seen) == len(members)


def _stays_connected(members: set, unit: str, adjacency) -> bool:
    """Would ``members - {unit}`` still be connected? ``unit`` must be in it."""
    inside = [v for v in adjacency[unit] if v in members]
    if len(inside) <= 1:
        return True  # a leaf (or isolated) node cannot disconnect anything
    rest = members - {unit}
    start = inside[0]
    seen = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for other in adjacency[node]:
            if other in rest and other not in seen:
                seen.add(other)
                stack.append(other)
    return len(seen) == len(rest)


def _random_growth(adj, pops, units, k, rng) -> Plan:
    """A contiguous k-partition grown from k random seeds, population-balanced.

    Population and adjacency only — no votes reach this function, which is what
    lets the default baseline be described as a neutral reference. It is a
    *starting point*, not a sample: nothing about its distribution is claimed,
    and it is never used as a neutral ensemble draw.
    """
    for _ in range(64):
        seeds = rng.sample(units, k)
        plan: Plan = {}
        members = {d: set() for d in range(1, k + 1)}
        totals = {d: 0 for d in range(1, k + 1)}
        for d, unit in enumerate(seeds, start=1):
            plan[unit] = d
            members[d].add(unit)
            totals[d] = pops[unit]
        unassigned = set(units) - set(seeds)
        stuck = False
        while unassigned:
            order = sorted(totals, key=lambda d: (totals[d], d))
            frontier: list[str] = []
            chosen = order[0]
            for d in order:
                frontier = sorted(
                    {v for u in members[d] for v in adj[u] if v in unassigned}
                )
                if frontier:
                    chosen = d
                    break
            if not frontier:
                stuck = True
                break
            unit = frontier[rng.randrange(len(frontier))]
            plan[unit] = chosen
            members[chosen].add(unit)
            totals[chosen] += pops[unit]
            unassigned.discard(unit)
        if not stuck:
            return plan
    raise SearchExhausted(  # pragma: no cover - needs a pathological graph
        "could not grow a contiguous starting partition; is the unit graph "
        "connected?"
    )


def _neutral_reference(
    adj, pops, units, k, band, work_band, rng, counter, tighten: bool = True
) -> Plan:
    """A population-balanced starting plan, drawn without reference to votes.

    ``tighten`` asks for the tight band; the seat phase only needs the working
    band, and starting it from a tight plan would just be undone.
    """
    ideal = sum(pops.values()) / k
    state = _State(
        _random_growth(adj, pops, units, k, rng), adj, pops, pops, pops, k
    )
    target = band if tighten else work_band
    best = None

    def observe() -> None:
        nonlocal best
        if state.excess(target, ideal) != 0.0:
            return
        spread = state.spread()
        if best is None or spread < best[0]:
            best = (spread, dict(state.plan))

    for _ in range(DEFAULT_REPAIR_ROUNDS if tighten else 3):
        _descend_population(
            state, ideal, counter, min_seats=None, exact_seats=None, observe=observe
        )
        if best is not None and not tighten:
            break
        _kick(state, rng, 3, counter, min_seats=None, exact_seats=None)
    if best is not None:
        return best[1]
    # Could not reach the requested band. Return the most balanced plan seen;
    # check_legality on the caller's side reports it as failing, rather than
    # this function pretending otherwise.
    _descend_population(state, ideal, counter, min_seats=None, exact_seats=None)
    return dict(state.plan)


def _boundary(state) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    plan = state.plan
    for unit in state.units:
        own = plan[unit]
        others = {plan[v] for v in state.adj[unit]}
        others.discard(own)
        if others:
            out[unit] = others
    return out


def _population_candidates(state, ideal) -> tuple[list[tuple], float]:
    """Every legal-looking single move and boundary swap, by population cost.

    Cost is the sum of squared district deviations, which drives the districts
    towards equal size rather than merely towards a small spread. Contiguity is
    *not* checked here — it is the expensive part, and checking it only on the
    few candidates that actually improve the cost is what makes the descent fast
    enough to run thousands of times.
    """
    boundary = _boundary(state)
    totals = state.totals
    base = sum((t - ideal) ** 2 for t in totals.values())
    cands: list[tuple] = []
    for unit, others in boundary.items():
        source = state.plan[unit]
        if len(state.members[source]) > 1:
            p = state.pops[unit]
            for dest in others:
                a = totals[source] - p - ideal
                b = totals[dest] + p - ideal
                delta = (
                    a * a + b * b
                    - (totals[source] - ideal) ** 2
                    - (totals[dest] - ideal) ** 2
                )
                cands.append((delta, "move", unit, None, source, dest))
    ordered = sorted(boundary)
    for unit in ordered:
        source = state.plan[unit]
        for other in ordered:
            dest = state.plan[other]
            if dest <= source:
                continue
            if dest not in boundary[unit] or source not in boundary[other]:
                continue
            if len(state.members[source]) < 2 or len(state.members[dest]) < 2:
                continue
            diff = state.pops[unit] - state.pops[other]
            a = totals[source] - diff - ideal
            b = totals[dest] + diff - ideal
            delta = (
                a * a + b * b
                - (totals[source] - ideal) ** 2
                - (totals[dest] - ideal) ** 2
            )
            cands.append((delta, "swap", unit, other, source, dest))
    cands.sort(key=lambda c: c[0])
    return cands, base


def _apply_candidate(state, cand):
    """Apply a candidate if it keeps both districts connected; else ``None``."""
    _, kind, unit, other, source, dest = cand
    if kind == "move":
        if not _stays_connected(state.members[source], unit, state.adj):
            return None
        state.move(unit, source, dest)
        return ((unit, dest, source),)
    state.move(unit, source, dest)
    state.move(other, dest, source)
    if not _connected(state.members[source], state.adj) or not _connected(
        state.members[dest], state.adj
    ):
        state.undo(((unit, dest, source), (other, source, dest)))
        return None
    return ((unit, dest, source), (other, source, dest))


def _seat_ok(state, min_seats, exact_seats) -> bool:
    if exact_seats is not None:
        return state.seats() == exact_seats
    if min_seats is not None:
        return state.seats() >= min_seats
    return True


def _descend_population(
    state, ideal, counter, min_seats, exact_seats, observe=None,
    max_steps: int = 400, probes: int = 60,
) -> None:
    """Best-improvement descent on population, holding the seat constraint.

    ``observe`` is called on every state the descent passes through, including
    the one it starts from. The descent minimises the sum of squared deviations,
    which is *not* the constraint — a state can satisfy ``|dev| <= band`` and
    still be improvable on that sum — so a caller that only looked at the final
    state would walk past legal plans without noticing.
    """
    if observe is not None:
        observe()
    for _ in range(max_steps):
        cands, _ = _population_candidates(state, ideal)
        moved = False
        for tried, cand in enumerate(cands):
            if cand[0] >= -1e-9 or tried >= probes:
                break
            counter.bump()
            applied = _apply_candidate(state, cand)
            if applied is None:
                continue
            if not _seat_ok(state, min_seats, exact_seats):
                state.undo(applied)
                continue
            moved = True
            break
        if observe is not None:
            observe()
        if not moved:
            return


def _kick(state, rng, n, counter, min_seats, exact_seats) -> None:
    """Random legal perturbation, to leave a local optimum."""
    for _ in range(n):
        for _attempt in range(24):
            counter.bump()
            applied = _propose(state, rng, 0.5)
            if applied is None:
                continue
            if not _seat_ok(state, min_seats, exact_seats):
                state.undo(applied)
                continue
            break


def _propose(state, rng, swap_probability: float):
    """One random move or boundary swap, applied. ``None`` if it was illegal."""
    units = state.units
    unit = units[rng.randrange(len(units))]
    source = state.plan[unit]
    others = {state.plan[v] for v in state.adj[unit]}
    others.discard(source)
    if not others:
        return None
    choices = sorted(others)
    dest = choices[rng.randrange(len(choices))]
    if rng.random() < swap_probability:
        partners = sorted(
            w
            for w in state.members[dest]
            if any(state.plan[x] == source for x in state.adj[w])
        )
        if not partners:
            return None
        if len(state.members[source]) < 2 or len(state.members[dest]) < 2:
            return None
        other = partners[rng.randrange(len(partners))]
        state.move(unit, source, dest)
        state.move(other, dest, source)
        if not _connected(state.members[source], state.adj) or not _connected(
            state.members[dest], state.adj
        ):
            state.undo(((unit, dest, source), (other, source, dest)))
            return None
        return ((unit, dest, source), (other, source, dest))
    if len(state.members[source]) == 1:
        return None
    if not _stays_connected(state.members[source], unit, state.adj):
        return None
    state.move(unit, source, dest)
    return ((unit, dest, source),)


def _anneal_seats(
    state, rng, iterations, work_band, sigmoid, weight, counter,
    cycles: int = 3, t_start: float = 0.25, t_end: float = 0.002,
    keep_per_level: int = DEFAULT_KEEP_PER_LEVEL,
) -> dict[int, list[Plan]]:
    """Anneal the seat objective inside the working band.

    Returns the best plans seen *at each seat level*, not only at the maximum:
    planting a 1-seat shift needs a plan that wins exactly one seat, and it is
    far cheaper to keep the ones the search walked through than to search again
    with a different constraint.

    Several plans are kept per level, not one, because the phase that follows
    can fail: a seat structure reachable inside the *working* band need not be
    tightenable to the real band while holding its seats, and on Iowa the
    3-seat Democratic structures are exactly the ones that usually cannot. One
    stored plan per level makes that a coin flip; a handful of distinct ones
    makes it a search.
    """
    ideal = sum(state.pops.values()) / state.k
    per_cycle = max(1, iterations // cycles)
    kept: dict[int, list[tuple[float, Plan]]] = {}
    seen: dict[int, set] = {}

    def record() -> None:
        value, seats = state.objective(sigmoid, weight)
        key = _canonical(state.plan)
        if key in seen.setdefault(seats, set()):
            return
        bucket = kept.setdefault(seats, [])
        if len(bucket) >= keep_per_level and value <= bucket[-1][0]:
            return
        seen[seats].add(key)
        bucket.append((value, dict(state.plan)))
        bucket.sort(key=lambda row: -row[0])
        del bucket[keep_per_level:]

    record()
    for _cycle in range(cycles):
        current, _ = state.objective(sigmoid, weight)
        for step in range(per_cycle):
            temperature = t_start * (t_end / t_start) ** (step / per_cycle)
            counter.bump()
            applied = _propose(state, rng, 0.4)
            if applied is None:
                continue
            if state.excess(work_band, ideal) > 0.0:
                state.undo(applied)
                continue
            value, _ = state.objective(sigmoid, weight)
            if value >= current or rng.random() < math.exp(
                (value - current) / max(temperature, 1e-9)
            ):
                current = value
                record()
            else:
                state.undo(applied)
        # Reheat from the best plan seen, which is where the next cycle has the
        # most to gain; a plain restart would throw the seat structure away.
        top = max(kept)
        state = _State(
            kept[top][0][1],
            state.adj,
            state.pops,
            state.target_votes,
            state.other_votes,
            state.k,
        )
    return {seats: [plan for _value, plan in bucket] for seats, bucket in kept.items()}


def _canonical(plan: Plan) -> frozenset:
    """A district-label-invariant key, so relabellings are not stored twice."""
    groups: dict[int, set] = {}
    for unit, district in plan.items():
        groups.setdefault(int(district), set()).add(unit)
    return frozenset(frozenset(members) for members in groups.values())


def _repair(state, rng, band, seats, rounds, counter) -> tuple[int, Plan] | None:
    """Tighten to the real band while holding the seat count exactly.

    Exact, not "at least": a plan planted at one seat must not drift to two, or
    the intended magnitude and the realised one part company and the ground
    truth stops being ground truth.
    """
    ideal = sum(state.pops.values()) / state.k
    if state.seats() != seats:
        return None
    best: tuple[int, Plan] | None = None

    def observe() -> None:
        nonlocal best
        if state.excess(band, ideal) != 0.0 or state.seats() != seats:
            return
        spread = state.spread()
        if best is None or spread < best[0]:
            best = (spread, dict(state.plan))

    for _ in range(max(1, rounds)):
        _descend_population(
            state, ideal, counter, min_seats=None, exact_seats=seats, observe=observe
        )
        _kick(state, rng, 3, counter, min_seats=None, exact_seats=seats)
    return best


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def _check_party(party: str) -> str:
    if not isinstance(party, str) or party.upper() not in PARTIES:
        raise ValueError(f"target_party must be one of {PARTIES}; got {party!r}")
    return party.upper()


def _check_inputs(adjacency, populations, dem, rep, k, epsilon, work_epsilon) -> None:
    units = set(adjacency)
    if not units:
        raise ValueError("adjacency is empty")
    for name, mapping in (("populations", populations), ("dem", dem), ("rep", rep)):
        missing = units - set(mapping)
        extra = set(mapping) - units
        if missing or extra:
            raise ValueError(
                f"{name} does not cover the unit graph: {len(missing)} missing, "
                f"{len(extra)} unknown"
            )
    if int(k) != k or k < 2:
        raise ValueError(f"k must be an integer >= 2; got {k!r}")
    if k > len(units):
        raise ValueError(f"k={k} exceeds the {len(units)} units available")
    if not 0 < epsilon < 1:
        raise ValueError(f"epsilon must lie in (0, 1); got {epsilon!r}")
    if not epsilon <= work_epsilon < 1:
        raise ValueError(
            f"work_epsilon must satisfy epsilon <= work_epsilon < 1; got "
            f"{work_epsilon!r} against epsilon={epsilon!r}"
        )
    for unit, neighbours in adjacency.items():
        for other in neighbours:
            if other not in units:
                raise ValueError(f"adjacency of {unit} names unknown unit {other}")
            if unit not in set(adjacency[other]):
                raise ValueError(
                    f"adjacency is not symmetric: {other} in adjacency[{unit}] but "
                    f"not the reverse"
                )


def _party_seats(plan: Plan, dem, rep, party: str) -> int:
    counts = seat_counts(plan, dem, rep)
    return counts[0] if party == "D" else counts[1]


def _shares_for(plan: Plan, dem, rep, party: str) -> dict[int, float]:
    shares = district_shares(plan, dem, rep)
    if party == "D":
        return shares
    return {d: 1.0 - s for d, s in shares.items()}


def _derive(seed: int, purpose: str, index: int) -> int:
    """Deterministic sub-seed. Mirrors ``generate.seeds.derive``; see above."""
    payload = bytearray()
    for field_bytes in (
        _SEED_DOMAIN,
        str(int(seed)).encode("ascii"),
        purpose.encode("utf-8"),
        str(int(index)).encode("ascii"),
    ):
        payload += len(field_bytes).to_bytes(8, "big")
        payload += field_bytes
    digest = hashlib.blake2b(bytes(payload), digest_size=8).digest()
    return int.from_bytes(digest, "big") >> 1
