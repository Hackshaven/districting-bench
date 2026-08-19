"""Tests for src/adversarial/gerrymander.py and src/adversarial/nulls.py.

Two things are being tested here, and they need different evidence.

**The gerrymander must actually be one.** A search that reports a seat shift it
did not achieve is worse than no search at all — it would poison every true
positive in the confusion matrix. So the arithmetic is pinned against a **brute
force** on a nine-county synthetic path graph, where every contiguous plan can
be enumerated: ``test_maximize_seats_finds_the_brute_force_optimum`` asserts the
search reaches the true optimum, not merely a good plan, and
``test_brute_force_agrees_with_the_module_on_which_plans_are_legal`` checks the
two implementations of "legal" against each other before anything is concluded
from either. The Iowa cases then pin the *numbers that go in the report* — a D
ceiling of 2 seats and an R ceiling of 4, which is the enacted outcome, so R has
no headroom at all.

**The null cases must be blind where they claim to be blind.** The module's own
docstring makes a firewall-adjacent claim: the plans are drawn without reference
to election results, and only selected with them.
``test_the_sampler_is_never_shown_election_data`` and
``test_adversarial_never_imports_generate`` are that claim as executable checks
rather than a comment.

The synthetic graph is a path on purpose. Districts on a path are exactly the
contiguous intervals, so the enumeration is complete and short enough to trust,
and a bug in the search's own contiguity handling cannot hide inside a brute
force that shares it.
"""

from __future__ import annotations

import ast
import itertools
import random
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

from adversarial import gerrymander as G
from adversarial import nulls as N
from adversarial.gerrymander import (
    ENVELOPE_MEASURES,
    GerrymanderResult,
    LegalityRecord,
    SearchExhausted,
    ShapeEnvelope,
    achievable_seats,
    calibrate_shape_envelope,
    check_legality,
    maximize_seats,
    plant_gerrymander,
    shape_metrics,
)
from evaluate import compactness
from evaluate.elections import load_elections, two_party
from evaluate.plan import is_valid, load_plan, populations as load_populations
from evaluate.plan import load_adjacency as load_rook

PROCESSED = Path("data/processed")
HAVE_IOWA = (PROCESSED / "ia_units.csv").exists()
iowa = pytest.mark.skipif(not HAVE_IOWA, reason="data/processed not built")

#: Iowa 2020, from docs/FEASIBILITY.md section 2 and the enacted plan.
IA_IDEAL = 797_592.25
IA_ENACTED_SPREAD = 94


# --------------------------------------------------------------------------- #
# the synthetic path: nine units in a line, so districts are intervals
# --------------------------------------------------------------------------- #

PATH_UNITS = [f"u{i}" for i in range(12)]
#: Sum 900, so the ideal district is 300 at k=3. The unit sizes are coarse
#: relative to the band on purpose — that is the situation on real county
#: graphs, where the smallest county is thousands of persons and a single
#: reassignment overshoots any tight band.
PATH_POPS = dict(
    zip(PATH_UNITS, [90, 60, 60, 80, 30, 110, 60, 100, 30, 110, 80, 90])
)
#: Votes are lumpy on purpose, so which seats a party can win depends on where
#: the cuts fall rather than on turnout alone. The four legal plans give D
#: 2, 1, 1 and 0 seats and R 1, 2, 2 and 3 — so each party has exactly one best
#: plan, and they are different plans.
PATH_DEM = dict(zip(PATH_UNITS, [9, 14, 24, 28, 3, 33, 18, 10, 10, 33, 22, 14]))
PATH_REP = dict(zip(PATH_UNITS, [36, 16, 6, 12, 12, 22, 12, 40, 5, 22, 18, 31]))
PATH_K = 3
PATH_EPSILON = 0.10  # ideal 300, band 30 persons, four legal plans


def path_adjacency() -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = {unit: [] for unit in PATH_UNITS}
    for left, right in zip(PATH_UNITS, PATH_UNITS[1:]):
        adjacency[left].append(right)
        adjacency[right].append(left)
    return adjacency


def brute_force_plans(k: int = PATH_K, epsilon: float = PATH_EPSILON):
    """Every legal plan on the path, by enumeration of the cut points.

    Independent of the module under test: a district on a path is an interval,
    so choosing ``k-1`` cut points enumerates the whole space.
    """
    ideal = sum(PATH_POPS.values()) / k
    band = epsilon * ideal
    legal = []
    for cuts in itertools.combinations(range(1, len(PATH_UNITS)), k - 1):
        bounds = (0,) + cuts + (len(PATH_UNITS),)
        plan = {}
        totals = []
        for district, (start, stop) in enumerate(zip(bounds, bounds[1:]), start=1):
            for unit in PATH_UNITS[start:stop]:
                plan[unit] = district
            totals.append(sum(PATH_POPS[u] for u in PATH_UNITS[start:stop]))
        if all(abs(total - ideal) <= band for total in totals):
            legal.append(plan)
    return legal


def brute_force_seats(plan, party: str) -> int:
    """Seats for ``party`` under a plan, counted from scratch."""
    dem: dict[int, int] = {}
    rep: dict[int, int] = {}
    for unit, district in plan.items():
        dem[district] = dem.get(district, 0) + PATH_DEM[unit]
        rep[district] = rep.get(district, 0) + PATH_REP[unit]
    if party == "D":
        return sum(1 for d in dem if dem[d] > rep[d])
    return sum(1 for d in dem if rep[d] > dem[d])


def maximize_on_path(party: str, seed: int = 11, **kwargs) -> GerrymanderResult:
    return maximize_seats(
        party,
        path_adjacency(),
        PATH_POPS,
        PATH_DEM,
        PATH_REP,
        PATH_K,
        PATH_EPSILON,
        seed,
        kwargs.pop("max_iterations", 8_000),
        restarts=kwargs.pop("restarts", 8),
        work_epsilon=kwargs.pop("work_epsilon", 0.6),
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# the brute force and the module must agree on what "legal" means
# --------------------------------------------------------------------------- #

def test_brute_force_agrees_with_the_module_on_which_plans_are_legal():
    """Both halves of the oracle, checked against each other before use.

    If the enumeration and ``check_legality`` disagreed about the population
    band, every optimality claim below would be measured against the wrong
    feasible set — and it would still look like a pass.
    """
    adjacency = path_adjacency()
    legal = brute_force_plans()
    assert len(legal) >= 3, "the synthetic case must leave room to optimise"
    for plan in legal:
        assert check_legality(plan, adjacency, PATH_POPS, PATH_K, PATH_EPSILON).passed

    ideal = sum(PATH_POPS.values()) / PATH_K
    band = PATH_EPSILON * ideal
    for cuts in itertools.combinations(range(1, len(PATH_UNITS)), PATH_K - 1):
        bounds = (0,) + cuts + (len(PATH_UNITS),)
        plan = {}
        totals = []
        for district, (start, stop) in enumerate(zip(bounds, bounds[1:]), start=1):
            for unit in PATH_UNITS[start:stop]:
                plan[unit] = district
            totals.append(sum(PATH_POPS[u] for u in PATH_UNITS[start:stop]))
        expected = all(abs(total - ideal) <= band for total in totals)
        record = check_legality(plan, adjacency, PATH_POPS, PATH_K, PATH_EPSILON)
        assert record.checks["population_within_epsilon"] == expected
        assert record.passed == expected


@pytest.mark.parametrize("party", ["D", "R"])
def test_maximize_seats_finds_the_brute_force_optimum(party):
    optimum = max(brute_force_seats(plan, party) for plan in brute_force_plans())
    result = maximize_on_path(party)
    assert result.realized_seat_count == optimum
    assert result.target_party == party


def test_the_two_parties_want_different_plans():
    """The case is only a test of optimisation if the answer depends on it."""
    plans = brute_force_plans()
    assert max(brute_force_seats(p, "D") for p in plans) != max(
        brute_force_seats(p, "R") for p in plans
    )


# --------------------------------------------------------------------------- #
# the returned plan is legal, and that is checked rather than assumed
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("party", ["D", "R"])
def test_the_returned_plan_passes_every_legal_constraint(party):
    adjacency = path_adjacency()
    result = maximize_on_path(party)

    assert result.legality.passed
    assert set(result.legality.checks) == {
        "every_unit_assigned_exactly_once",
        "district_ids_are_1_to_k",
        "no_empty_district",
        "contiguous_on_rook_graph",
        "whole_units_no_splits",
        "population_within_epsilon",
        "evaluate_plan_validate",
    }
    assert result.legality.failures() == []

    # Re-derived here rather than read off the record: the record is the thing
    # under test.
    assert is_valid(result.plan, adjacency, PATH_K)
    ideal = sum(PATH_POPS.values()) / PATH_K
    totals: dict[int, int] = {}
    for unit, district in result.plan.items():
        totals[district] = totals.get(district, 0) + PATH_POPS[unit]
    assert max(abs(t - ideal) for t in totals.values()) <= PATH_EPSILON * ideal
    assert result.population_spread == max(totals.values()) - min(totals.values())


def test_the_realized_shift_is_measured_not_intended():
    """``seat_shift`` must come from the vote counts, not from the request."""
    baseline = brute_force_plans()[0]
    result = maximize_on_path("D", baseline_plan=baseline)
    assert result.baseline_source == "supplied (unnamed)"
    assert result.baseline_seat_count == brute_force_seats(baseline, "D")
    assert result.realized_seat_count == brute_force_seats(result.plan, "D")
    assert result.seat_shift == result.realized_seat_count - result.baseline_seat_count


def test_the_default_baseline_is_drawn_without_votes():
    """The neutral reference is a population-and-adjacency object.

    Its seat count is whatever the geography gives it; what matters is that it
    is reported as such, so a reader knows the shift is measured against a
    neutral draw and not against the enacted map.
    """
    result = maximize_on_path("D")
    assert result.baseline_source == "neutral_reference"
    assert result.baseline_seat_count == brute_force_seats(result.baseline_plan, "D")
    assert result.baseline_legality.checks["contiguous_on_rook_graph"]


# --------------------------------------------------------------------------- #
# seeding
# --------------------------------------------------------------------------- #

def test_the_same_seed_gives_the_same_plan():
    first = maximize_on_path("D", seed=4242)
    second = maximize_on_path("D", seed=4242)
    assert first.plan == second.plan
    assert first.iterations == second.iterations
    assert first.population_spread == second.population_spread


def test_other_seeds_still_return_legal_plans_at_the_optimum():
    optimum = max(brute_force_seats(plan, "D") for plan in brute_force_plans())
    for seed in (1, 7, 99, 20260818):
        result = maximize_on_path("D", seed=seed)
        assert result.legality.passed
        assert result.realized_seat_count == optimum


def test_swapping_the_parties_swaps_the_answer():
    """Nothing in the search prefers one party; the data does.

    Relabelling D as R and R as D must turn the D-maximising problem into the
    R-maximising one exactly. A party-specific bug (a stray ``> 0.5`` that
    should be ``>=``, an asymmetric tie rule) shows up here and nowhere else.
    """
    straight = maximize_seats(
        "D", path_adjacency(), PATH_POPS, PATH_DEM, PATH_REP,
        PATH_K, PATH_EPSILON, 5, 4_000, restarts=3, work_epsilon=0.6,
    )
    mirrored = maximize_seats(
        "R", path_adjacency(), PATH_POPS, PATH_REP, PATH_DEM,
        PATH_K, PATH_EPSILON, 5, 4_000, restarts=3, work_epsilon=0.6,
    )
    assert straight.realized_seat_count == mirrored.realized_seat_count
    assert straight.plan == mirrored.plan


# --------------------------------------------------------------------------- #
# planting a specified magnitude
# --------------------------------------------------------------------------- #

def test_plant_returns_exactly_the_requested_shift():
    baseline = brute_force_plans()[0]
    base_seats = brute_force_seats(baseline, "D")
    optimum = max(brute_force_seats(p, "D") for p in brute_force_plans())
    for shift in range(0, optimum - base_seats + 1):
        result = plant_gerrymander(
            "D", shift, path_adjacency(), PATH_POPS, PATH_DEM, PATH_REP,
            PATH_K, PATH_EPSILON, 31, 4_000, baseline_plan=baseline,
            restarts=3, work_epsilon=0.6,
        )
        assert result is not None, f"shift {shift} should be reachable"
        assert result.seat_shift == shift
        assert result.intended_seat_shift == shift
        assert result.realized_seat_count == base_seats + shift
        assert result.legality.passed


def test_plant_returns_none_rather_than_a_near_miss():
    """An unreachable magnitude is ``None``, not the closest plan relabelled."""
    baseline = brute_force_plans()[0]
    impossible = PATH_K + 1  # more seats than there are districts
    assert (
        plant_gerrymander(
            "D", impossible, path_adjacency(), PATH_POPS, PATH_DEM, PATH_REP,
            PATH_K, PATH_EPSILON, 3, 4_000, baseline_plan=baseline,
            restarts=2, work_epsilon=0.6,
        )
        is None
    )


def test_plant_rejects_a_non_integer_shift():
    with pytest.raises(TypeError):
        plant_gerrymander(
            "D", 1.5, path_adjacency(), PATH_POPS, PATH_DEM, PATH_REP,
            PATH_K, PATH_EPSILON, 3,
        )


def test_no_legal_plan_at_all_raises_rather_than_returning_an_illegal_one():
    """An impossible population band is a search failure, not a bad plan.

    ``epsilon`` here is far tighter than any whole-county split of this path can
    satisfy, so the search must come back empty-handed and say so.
    """
    with pytest.raises(SearchExhausted):
        maximize_seats(
            "D", path_adjacency(), PATH_POPS, PATH_DEM, PATH_REP,
            PATH_K, 1e-9, 3, 2_000, restarts=2, work_epsilon=0.6,
        )


# --------------------------------------------------------------------------- #
# the legality record: each constraint separately, and each failure visible
# --------------------------------------------------------------------------- #

def test_each_constraint_fails_on_its_own_broken_plan():
    adjacency = path_adjacency()
    good = brute_force_plans()[0]
    assert check_legality(good, adjacency, PATH_POPS, PATH_K, PATH_EPSILON).passed

    missing = {u: d for u, d in good.items() if u != PATH_UNITS[-1]}
    record = check_legality(missing, adjacency, PATH_POPS, PATH_K, PATH_EPSILON)
    assert not record.passed
    assert not record.checks["every_unit_assigned_exactly_once"]
    assert not record.checks["evaluate_plan_validate"]

    empty = dict(good)
    for unit in PATH_UNITS:
        if empty[unit] == PATH_K:
            empty[unit] = 1
    record = check_legality(empty, adjacency, PATH_POPS, PATH_K, PATH_EPSILON)
    assert not record.checks["no_empty_district"]

    stray = dict(good)
    stray[PATH_UNITS[0]] = PATH_K + 5
    record = check_legality(stray, adjacency, PATH_POPS, PATH_K, PATH_EPSILON)
    assert not record.checks["district_ids_are_1_to_k"]

    # Districts 1 and 3 are the ends of the path; swapping a unit across makes
    # one of them two pieces without changing any district's size.
    split = dict(good)
    ends = [u for u in PATH_UNITS if split[u] == 1]
    middle = [u for u in PATH_UNITS if split[u] == 2]
    split[middle[len(middle) // 2]] = 1
    record = check_legality(split, adjacency, PATH_POPS, PATH_K, PATH_EPSILON)
    assert ends, "district 1 must be non-empty for this case to mean anything"
    assert not record.checks["contiguous_on_rook_graph"]
    assert not record.checks["evaluate_plan_validate"]

    outside = dict(good)
    outside["not_a_unit"] = 1
    record = check_legality(outside, adjacency, PATH_POPS, PATH_K, PATH_EPSILON)
    assert not record.checks["every_unit_assigned_exactly_once"]
    assert not record.checks["contiguous_on_rook_graph"]
    assert not record.checks["population_within_epsilon"]
    assert "not checkable" in record.notes["contiguous_on_rook_graph"]

    record = check_legality(good, adjacency, PATH_POPS, PATH_K, 1e-9)
    assert not record.checks["population_within_epsilon"]
    assert record.checks["contiguous_on_rook_graph"]
    assert "persons" in record.notes["population_within_epsilon"]


def test_whole_counties_are_recorded_as_structural_not_checked_away():
    record = check_legality(
        brute_force_plans()[0], path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON
    )
    assert record.checks["whole_units_no_splits"]
    assert "by construction" in record.notes["whole_units_no_splits"]


def test_the_record_reports_the_deviation_it_measured():
    plan = brute_force_plans()[0]
    record = check_legality(plan, path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON)
    totals: dict[int, int] = {}
    for unit, district in plan.items():
        totals[district] = totals.get(district, 0) + PATH_POPS[unit]
    ideal = sum(PATH_POPS.values()) / PATH_K
    assert record.district_populations == dict(sorted(totals.items()))
    assert record.ideal_population == pytest.approx(ideal)
    assert record.max_deviation_persons == round(
        max(abs(t - ideal) for t in totals.values())
    )
    assert record.population_spread == max(totals.values()) - min(totals.values())


# --------------------------------------------------------------------------- #
# input validation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"party": "Green"}, "target_party"),
        ({"k": 1}, "k must"),
        ({"epsilon": 0.0}, "epsilon"),
        ({"work_epsilon": 0.05}, "work_epsilon"),
        ({"restarts": 0}, "restarts"),
        ({"max_iterations": 0}, "max_iterations"),
        ({"target_seats": 9}, "target_seats"),
    ],
)
def test_bad_arguments_are_refused(kwargs, message):
    call = dict(
        party="D", adjacency=path_adjacency(), populations=PATH_POPS,
        k=PATH_K, epsilon=PATH_EPSILON, work_epsilon=0.6,
        restarts=1, max_iterations=500, target_seats=None,
    )
    call.update(kwargs)
    with pytest.raises(ValueError, match=message):
        maximize_seats(
            call["party"], call["adjacency"], call["populations"], PATH_DEM, PATH_REP,
            call["k"], call["epsilon"], 1, call["max_iterations"],
            restarts=call["restarts"], work_epsilon=call["work_epsilon"],
            target_seats=call["target_seats"],
        )


def test_votes_must_cover_the_unit_graph():
    short = {u: v for u, v in PATH_DEM.items() if u != PATH_UNITS[0]}
    with pytest.raises(ValueError, match="dem does not cover"):
        maximize_seats(
            "D", path_adjacency(), PATH_POPS, short, PATH_REP,
            PATH_K, PATH_EPSILON, 1, 500, restarts=1, work_epsilon=0.6,
        )


def test_asymmetric_adjacency_is_refused():
    broken = path_adjacency()
    broken[PATH_UNITS[0]] = []
    with pytest.raises(ValueError, match="symmetric"):
        maximize_seats(
            "D", broken, PATH_POPS, PATH_DEM, PATH_REP,
            PATH_K, PATH_EPSILON, 1, 500, restarts=1, work_epsilon=0.6,
        )


# --------------------------------------------------------------------------- #
# the synthetic grid: shape varies here, so the envelope has something to bind
# --------------------------------------------------------------------------- #
#
# A path graph cannot test a shape constraint at all: every plan on a path has
# exactly ``k-1`` cut edges, so the envelope is a point and the search is either
# unconstrained or infeasible. The grid is the smallest thing that separates a
# compact partition from a ragged one.

#: A projected CRS that is locally undistorted over this figure's own extent,
#: so ``evaluate.compactness``'s projection guard is entered rather than
#: side-stepped. Same convention as tests/test_compactness.py.
GRID_CRS = "+proj=laea +lat_0=0 +lon_0=0 +datum=WGS84 +units=m +no_defs"
GRID_N = 6
GRID_CELL = 1000.0
GRID_UNITS = [f"g{r}{c}" for r in range(GRID_N) for c in range(GRID_N)]
GRID_K = 3
GRID_EPSILON = 0.05
GRID_POPS = {unit: 100 for unit in GRID_UNITS}
#: Democratic votes piled into the bottom-left 3x3 block, which is the Chen &
#: Rodden geography in miniature: a party that clusters can be packed by a map
#: nobody drew to pack it.
GRID_DEM = {
    unit: (80 if int(unit[1]) < 3 and int(unit[2]) < 3 else 30) for unit in GRID_UNITS
}
GRID_REP = {unit: 100 - GRID_DEM[unit] for unit in GRID_UNITS}


def grid_adjacency() -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = {unit: [] for unit in GRID_UNITS}
    for unit in GRID_UNITS:
        row, col = int(unit[1]), int(unit[2])
        for drow, dcol in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if 0 <= row + drow < GRID_N and 0 <= col + dcol < GRID_N:
                adjacency[unit].append(f"g{row + drow}{col + dcol}")
    return adjacency


def grid_geometry():
    """The grid as unit squares, in a projected CRS."""
    shapes = []
    for unit in GRID_UNITS:
        row, col = int(unit[1]), int(unit[2])
        shapes.append(
            box(
                col * GRID_CELL,
                row * GRID_CELL,
                (col + 1) * GRID_CELL,
                (row + 1) * GRID_CELL,
            )
        )
    return gpd.GeoDataFrame({"GEOID": GRID_UNITS}, geometry=shapes, crs=GRID_CRS)


def grid_pool():
    """A stand-in neutral pool: two strip plans plus twelve growth partitions.

    Blind to votes, exactly as a real neutral ensemble is: nothing in
    ``_random_growth`` reads an election result. Its spread on the shape
    measures is what gives the calibrated envelope a width.
    """
    rows = {unit: 1 + int(unit[1]) // 2 for unit in GRID_UNITS}
    cols = {unit: 1 + int(unit[2]) // 2 for unit in GRID_UNITS}
    adjacency = {unit: tuple(sorted(n)) for unit, n in grid_adjacency().items()}
    grown = [
        G._random_growth(adjacency, GRID_POPS, sorted(GRID_UNITS), GRID_K,
                         random.Random(seed))
        for seed in range(12)
    ]
    return [rows, cols] + grown


def grid_envelope(coverage: float = 0.90, geometry=None):
    return calibrate_shape_envelope(
        grid_pool(),
        grid_adjacency(),
        geometry,
        coverage=coverage,
        source="grid pool of 14 vote-blind partitions",
    )


def maximize_on_grid(party: str = "D", seed: int = 7, **kwargs):
    return maximize_seats(
        party,
        grid_adjacency(),
        GRID_POPS,
        GRID_DEM,
        GRID_REP,
        GRID_K,
        GRID_EPSILON,
        seed,
        kwargs.pop("max_iterations", 20_000),
        restarts=kwargs.pop("restarts", 4),
        work_epsilon=kwargs.pop("work_epsilon", 0.2),
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# the shape envelope (docs/DECISIONS.md D-010)
# --------------------------------------------------------------------------- #

def test_the_envelope_is_the_ensembles_own_quantiles_not_a_constant():
    """Calibration is the claim: the bound is the reference distribution."""
    pool = grid_pool()
    adjacency = grid_adjacency()
    counts = sorted(compactness.cut_edges(plan, adjacency) for plan in pool)

    full = calibrate_shape_envelope(pool, adjacency, coverage=1.0)
    assert full.bounds["cut_edges"] == (counts[0], counts[-1])

    ninety = calibrate_shape_envelope(pool, adjacency, coverage=0.90)
    low, high = ninety.bounds["cut_edges"]
    assert counts[0] <= low < high <= counts[-1]
    # Two-sided by construction: both tails are closed, not just the ragged one.
    assert low > counts[0] and high < counts[-1]
    assert ninety.reference_plans == len(pool)


def test_a_bounded_measure_that_was_not_measured_is_a_violation_not_a_pass():
    envelope = grid_envelope(geometry=grid_geometry())
    assert set(envelope.bounds) == set(ENVELOPE_MEASURES)
    broken = envelope.violations({"cut_edges": sum(envelope.bounds["cut_edges"]) / 2})
    assert set(broken) == set(ENVELOPE_MEASURES) - {"cut_edges"}
    assert all("not measured" in reason for reason in broken.values())


def test_without_geometry_only_the_graph_measure_is_bounded():
    envelope = grid_envelope()
    assert set(envelope.bounds) == {"cut_edges"}
    assert envelope.in_loop == ("cut_edges",)
    assert set(shape_metrics(grid_pool()[0], grid_adjacency())) == {"cut_edges"}


def test_the_incremental_shape_arithmetic_matches_evaluate_compactness():
    """The search's own numbers, checked against the module of record.

    The search cannot afford to dissolve polygons on every proposal, so it
    maintains cut edges and Polsby-Popper incrementally. If that arithmetic
    drifted, the envelope would be enforced against a number nobody else
    computes and every "inside the envelope" claim would be vacuous.
    """
    adjacency = grid_adjacency()
    ordered = {unit: tuple(sorted(adjacency[unit])) for unit in sorted(adjacency)}
    geometry = grid_geometry()
    guard = G._Guard(grid_envelope(geometry=geometry), geometry, ordered)
    state = G._State(
        grid_pool()[0], ordered, GRID_POPS, GRID_DEM, GRID_REP, GRID_K, guard
    )
    rng = random.Random(4)
    checked = 0
    for step in range(160):
        applied = G._propose(state, rng, 0.4)
        if applied is None:
            continue
        truth = compactness.all_metrics(state.plan, geometry, adjacency)
        assert state.cut == truth["cut_edges"]
        assert state.polsby_popper_mean() == pytest.approx(
            truth["polsby_popper_mean"], abs=1e-9
        )
        if step % 3 == 0:  # and the undo path, which is where drift accumulates
            state.undo(applied)
            truth = compactness.all_metrics(state.plan, geometry, adjacency)
            assert state.cut == truth["cut_edges"]
            assert state.polsby_popper_mean() == pytest.approx(
                truth["polsby_popper_mean"], abs=1e-9
            )
        checked += 1
    assert checked > 50, "the walk must actually move for this to test anything"


def test_the_constrained_search_stays_inside_the_envelope_and_the_old_one_does_not():
    """D-010, executed. This is the round-2 finding as a regression test.

    Round 2 measured planted plans at ~2x the cut edges and ~1/3 the
    Polsby-Popper of every neutral map, so ``cut_edges > 60`` alone scored
    TPR 1.0 and FPR 0.0. The unconstrained search is kept reachable — it is the
    other end of the frontier — and this test pins that it is *still* the
    separable one, so nobody can conclude the problem went away on its own.
    """
    geometry = grid_geometry()
    envelope = grid_envelope(geometry=geometry)
    adjacency = grid_adjacency()

    loose = maximize_on_grid()
    assert loose.shape_envelope is None
    assert loose.shape_constrained is False
    assert envelope.violations(shape_metrics(loose.plan, adjacency, geometry))

    tight = maximize_on_grid(shape_envelope=envelope, geometry=geometry)
    assert tight.shape_constrained is True
    measured = shape_metrics(tight.plan, adjacency, geometry)
    assert envelope.violations(measured) == {}
    assert tight.shape_metrics == pytest.approx(measured)
    assert tight.legality.passed
    # The constraint costs something or it is not a constraint.
    assert measured["cut_edges"] < shape_metrics(
        loose.plan, adjacency, geometry
    )["cut_edges"]


def test_an_envelope_around_one_plan_is_centred_on_that_plan_and_is_never_empty():
    """The distribution-matching instrument: bounds anchored on a real draw.

    A quantile window narrow enough to make the planted plans look *typical*
    rather than merely *admissible* is usually empty on all five measures at
    once, because the measures disagree (CRITERIA.md section 3). An envelope
    built around a plan that exists cannot be: that plan is inside it.
    """
    geometry = grid_geometry()
    adjacency = grid_adjacency()
    pool = grid_pool()
    target = pool[3]
    envelope = G.envelope_around_plan(target, pool, adjacency, geometry, width=0.5)

    measured = shape_metrics(target, adjacency, geometry)
    assert envelope.violations(measured) == {}
    for name, (low, high) in envelope.bounds.items():
        assert low < measured[name] < high
        assert (low + high) / 2 == pytest.approx(measured[name])

    result = maximize_on_grid(
        shape_envelope=envelope, geometry=geometry, start_plans=[target]
    )
    assert envelope.violations(result.shape_metrics) == {}
    with pytest.raises(ValueError, match="width"):
        G.envelope_around_plan(target, pool, adjacency, geometry, width=0)
    with pytest.raises(ValueError, match="no reference plans"):
        G.envelope_around_plan(target, [], adjacency, geometry)


def test_an_unsatisfiable_envelope_exhausts_the_search_rather_than_returning_a_plan():
    """No plan outside the envelope is ever handed back, and the message says so."""
    geometry = grid_geometry()
    impossible = ShapeEnvelope(
        coverage=0.90,
        bounds={"cut_edges": (0.0, 1.0)},
        reference_plans=1,
        reference_draws=1,
        measures=("cut_edges",),
        source="deliberately unsatisfiable",
    )
    with pytest.raises(SearchExhausted, match="shape envelope"):
        maximize_on_grid(shape_envelope=impossible, geometry=geometry)


def test_the_envelope_and_its_provenance_are_recorded_on_the_result():
    geometry = grid_geometry()
    envelope = grid_envelope(geometry=geometry)
    result = maximize_on_grid(shape_envelope=envelope, geometry=geometry)
    assert result.shape_envelope is envelope
    assert result.shape_envelope.coverage == 0.90
    assert "grid pool" in result.shape_envelope.source
    assert result.shape_envelope.reference_plans == len(grid_pool())
    assert set(result.shape_metrics) == set(ENVELOPE_MEASURES)


def test_starting_from_supplied_plans_is_recorded_and_used():
    """A realistic adversary starts from a compact map and edits it."""
    geometry = grid_geometry()
    envelope = grid_envelope(geometry=geometry)
    result = maximize_on_grid(
        shape_envelope=envelope, geometry=geometry, start_plans=grid_pool()[:4]
    )
    assert result.start_source == "supplied start_plans"
    assert envelope.violations(result.shape_metrics) == {}
    with pytest.raises(ValueError, match="start_plans"):
        maximize_on_grid(start_plans=[])


def test_bounding_polsby_popper_without_geometry_is_refused():
    """A bound nothing can enforce is an error, not a silently ignored field."""
    envelope = ShapeEnvelope(
        coverage=0.9,
        bounds={"polsby_popper_mean": (0.3, 0.6)},
        reference_plans=2,
        reference_draws=2,
        measures=("polsby_popper_mean",),
        source="test",
    )
    with pytest.raises(ValueError, match="geometry"):
        maximize_on_grid(shape_envelope=envelope)


def test_calibration_refuses_a_meaningless_coverage_or_measure():
    with pytest.raises(ValueError, match="coverage"):
        calibrate_shape_envelope(grid_pool(), grid_adjacency(), coverage=0.0)
    with pytest.raises(ValueError, match="envelope measure"):
        calibrate_shape_envelope(
            grid_pool(), grid_adjacency(), measures=("compactness",)
        )
    with pytest.raises(ValueError, match="no plans"):
        calibrate_shape_envelope([], grid_adjacency())


# --------------------------------------------------------------------------- #
# compactness in the legality record (Iowa Code ch. 42 criterion 4)
# --------------------------------------------------------------------------- #

def test_legality_says_compactness_was_not_checked_rather_than_passing_it():
    record = check_legality(
        grid_pool()[0], grid_adjacency(), GRID_POPS, GRID_K, GRID_EPSILON
    )
    assert "compactness_within_neutral_envelope" not in record.checks
    assert "ch. 42 criterion 4" in record.notes["compactness_not_checked"]
    assert record.passed


def test_legality_checks_compactness_when_given_a_standard_to_check_against():
    """Round 2 certified plans at a third the Polsby-Popper of every neutral draw."""
    geometry = grid_geometry()
    envelope = grid_envelope(geometry=geometry)
    adjacency = grid_adjacency()
    loose = maximize_on_grid()

    record = check_legality(
        loose.plan,
        adjacency,
        GRID_POPS,
        GRID_K,
        GRID_EPSILON,
        shape_envelope=envelope,
        plan_shape_metrics=shape_metrics(loose.plan, adjacency, geometry),
    )
    assert record.checks["compactness_within_neutral_envelope"] is False
    assert not record.passed
    assert "compactness_within_neutral_envelope" in record.failures()

    tight = maximize_on_grid(shape_envelope=envelope, geometry=geometry)
    assert tight.legality.checks["compactness_within_neutral_envelope"] is True
    assert tight.legality.passed


# --------------------------------------------------------------------------- #
# baselines: a shift is a difference, so the record says what from
# --------------------------------------------------------------------------- #

def test_a_supplied_baseline_that_is_not_named_says_so():
    baseline = brute_force_plans()[0]
    named = maximize_on_path("D", baseline_plan=baseline, baseline_source="enacted")
    assert named.baseline_source == "enacted"
    unnamed = maximize_on_path("D", baseline_plan=baseline)
    assert unnamed.baseline_source == "supplied (unnamed)"


def test_both_directions_come_from_one_baseline_and_the_pair_is_marked_comparable():
    """Round 2 pooled a D shift from one baseline with an R shift from another."""
    baseline = brute_force_plans()[0]
    found = achievable_seats(
        path_adjacency(), PATH_POPS, PATH_DEM, PATH_REP, PATH_K, PATH_EPSILON,
        11, 8_000, restarts=4, work_epsilon=0.6,
        baseline_plan=baseline, baseline_source="brute-force plan 0",
    )
    assert found["comparable"] is True
    assert found["baseline_source"] == "brute-force plan 0"
    assert found["baseline_plan"] == baseline
    for party in ("D", "R"):
        assert found[party]["baseline_seats"] == brute_force_seats(baseline, party)
        assert (
            found[party]["max_shift"]
            == found[party]["max_seats"] - found[party]["baseline_seats"]
        )
    assert sum(found[party]["baseline_seats"] for party in ("D", "R")) == PATH_K


# --------------------------------------------------------------------------- #
# null cases
# --------------------------------------------------------------------------- #

def path_pool():
    """A pool of legal path plans, with their D seat counts, for null tests."""
    return brute_force_plans()


def by_hand_concentration(plan, votes):
    """The selection statistic, recomputed from scratch by the test."""
    totals = {}
    for unit, district in plan.items():
        totals[district] = totals.get(district, 0) + votes[unit]
    total = sum(totals.values())
    return sum((value / total) ** 2 for value in totals.values())


def nulls_on_path(**kwargs):
    return N.sample_nulls(
        path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
        PATH_DEM, PATH_REP, sampler=N.sampler_from_plans(kwargs.pop("pool", path_pool())),
        **kwargs,
    )


def test_the_selection_statistic_is_not_a_metric_the_detector_reads():
    """The round-2 defect, as a test that fails if it comes back.

    ``|efficiency gap|`` was the tie-break, and it is a monotone transform of
    the detector's own test statistic, so the selected nulls walked into the
    tail the detector thresholds and *any* correct rule flagged them: the
    stratum's false positive rate rose to 1.00 as the pool grew while the random
    stratum's fell to 0.125. Nothing that appears in ``selection_statistic`` may
    be one of the detector's metrics.
    """
    cases = nulls_on_path(n_select=3)
    for case in cases:
        assert set(case.selection_statistic) == {"seat_deviation", "vote_concentration"}
        assert "efficiency_gap" not in case.selection_statistic
        assert "mean_median" not in case.selection_statistic
        assert case.stratum == "concentration"
        # recorded, because a reader wants it -- but not ranked on
        assert case.efficiency_gap == pytest.approx(
            case.efficiency_gap
        )


def test_the_concentration_stratum_ranks_by_concentration_and_nothing_else():
    pool = path_pool()
    expected = sorted(
        (by_hand_concentration(plan, PATH_DEM) for plan in pool), reverse=True
    )
    cases = nulls_on_path(n_select=len(pool), balance_directions=False)
    got = [case.vote_concentration for case in cases]
    assert got == pytest.approx(expected[: len(got)])
    assert [case.selection_rank for case in cases] == list(range(1, len(cases) + 1))
    assert [case.id for case in cases[:2]] == [
        "null_geography_01", "null_geography_02"
    ]


def test_vote_concentration_reads_one_party_and_nothing_else():
    """The property that makes it independent of the detector's metrics."""
    plan = path_pool()[0]
    value = N.vote_concentration(plan, PATH_DEM)
    assert 1.0 / PATH_K - 1e-12 <= value <= 1.0
    assert value == pytest.approx(by_hand_concentration(plan, PATH_DEM))
    # It cannot see the other party at all: doubling every R vote changes the
    # efficiency gap and every share-based metric, and leaves this unmoved.
    doubled = {unit: 2 * count for unit, count in PATH_REP.items()}
    assert N.vote_concentration(plan, PATH_DEM) == value
    assert doubled != PATH_REP
    # And it is invariant to district relabelling, like the plan itself.
    relabelled = {unit: PATH_K + 1 - d for unit, d in plan.items()}
    assert N.vote_concentration(relabelled, PATH_DEM) == pytest.approx(value)
    with pytest.raises(ValueError, match="no votes"):
        N.vote_concentration(plan, {unit: 0 for unit in plan})


def test_the_seat_outcome_stratum_ranks_by_seats_and_warns_what_it_is():
    """Kept, labelled, and reported apart: in Iowa it is nearly the old rule."""
    pool = path_pool()
    median = N.median_seats(pool, PATH_DEM, PATH_REP, "D")
    worst = max(abs(brute_force_seats(plan, "D") - median) for plan in pool)
    cases = nulls_on_path(n_select=3, stratum="seat_outcome")
    assert abs(cases[0].seat_shift) == worst
    assert all(case.stratum == "seat_outcome" for case in cases)
    assert all(case.id.startswith("null_seat_outcome_") for case in cases)
    assert N.ID_PREFIXES["concentration"] == "null_geography"
    assert "rank-correlated" in cases[0].selection_rule
    deviations = [case.selection_statistic["seat_deviation"] for case in cases]
    assert deviations[0] == max(deviations)


def test_the_random_stratum_is_a_control_and_is_seeded():
    pool = path_pool()
    one = nulls_on_path(n_select=2, stratum="random", seed=3)
    again = nulls_on_path(n_select=2, stratum="random", seed=3)
    other = nulls_on_path(n_select=len(pool), stratum="random", seed=9)
    assert [c.plan for c in one] == [c.plan for c in again]
    assert all(c.stratum == "random" for c in one)
    assert "not selected for looking biased" in one[0].selection_rule
    assert len(other) == len(pool)


def test_the_strata_are_returned_separately_and_share_no_plan():
    """A pooled false positive rate over these is not a quantity; see the docstring."""
    strata = N.sample_strata(
        path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
        PATH_DEM, PATH_REP, sampler=N.sampler_from_plans(path_pool()),
        n_per_stratum=1,
    )
    assert list(strata) == list(N.STRATA)
    assert N.null_strata is N.sample_strata  # the older name, kept as an alias
    plans = [case.plan for cases in strata.values() for case in cases]
    assert len(plans) == len({_plan_key(plan) for plan in plans})
    for name, cases in strata.items():
        assert all(case.stratum == name for case in cases)
    counted = N.sample_strata(
        path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
        PATH_DEM, PATH_REP, sampler=N.sampler_from_plans(path_pool()),
        n_per_stratum={"concentration": 2, "seat_outcome": 1, "random": 0},
    )
    assert [len(counted[name]) for name in N.STRATA] == [2, 1, 0]
    with pytest.raises(ValueError, match="unknown stratum"):
        N.sample_strata(
            path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
            PATH_DEM, PATH_REP, sampler=N.sampler_from_plans(path_pool()),
            strata=("efficiency_gap",),
        )


def _plan_key(plan):
    return tuple(sorted(plan.items()))


def test_the_null_set_is_not_all_one_direction():
    """Both sides of the median are negatives, and both must be tested.

    On Iowa the plans furthest from the median all sweep 4R-0D and share an
    efficiency gap to three decimals, so a strict ranking would fill the null
    set with that one direction and never test the direction the planted
    gerrymander actually points in.
    """
    pool = path_pool()
    median = N.median_seats(pool, PATH_DEM, PATH_REP, "D")
    balanced = nulls_on_path(n_select=2, stratum="seat_outcome")
    sides = {case.realized_seat_count > median for case in balanced}
    assert sides == {True, False}
    assert all("not all one direction" in c.selection_rule for c in balanced)

    strict = nulls_on_path(n_select=4, stratum="seat_outcome", balance_directions=False)
    deviations = [case.selection_statistic["seat_deviation"] for case in strict]
    assert deviations == sorted(deviations, reverse=True)
    assert "not all one direction" not in strict[0].selection_rule


def test_every_null_case_carries_zero_intended_shift_and_its_provenance():
    cases = nulls_on_path(n_select=3, drawn_by="ReCom, epsilon=0.1, seeds 1..3")
    for case in cases:
        assert case.intended_seat_shift == 0
        assert case.legality.passed
        assert case.drawn_by == "ReCom, epsilon=0.1, seeds 1..3"
        assert "selection not" in case.selection_rule
        assert case.pool_size == len(path_pool())
        assert case.realized_seat_count == brute_force_seats(case.plan, "D")
        assert case.seat_shift == case.realized_seat_count - case.ensemble_median_seats


def test_relabelled_duplicates_do_not_take_two_slots():
    pool = path_pool()
    relabelled = [{u: (PATH_K + 1 - d) for u, d in plan.items()} for plan in pool]
    cases = nulls_on_path(
        pool=pool + relabelled, n_select=len(pool) + len(relabelled)
    )
    assert cases[0].pool_size == 2 * len(pool)
    assert cases[0].distinct_pool_size == len(pool)
    assert len(cases) == len(pool)


def test_illegal_plans_are_dropped_rather_than_presented_as_neutral_maps():
    pool = path_pool()
    lopsided = dict(pool[0])
    lopsided[PATH_UNITS[0]] = PATH_K  # breaks contiguity and population both
    with_bad = [lopsided] + pool

    kept = nulls_on_path(pool=with_bad, n_select=10)
    assert all(case.legality.passed for case in kept)
    assert all(case.plan != lopsided for case in kept)

    kept_anyway = nulls_on_path(pool=with_bad, n_select=10, require_legal=False)
    assert any(not case.legality.passed for case in kept_anyway)


def test_the_sampler_is_never_shown_election_data():
    """The module's central claim, as a check rather than a comment.

    Generation is blind; selection is not. If a future edit passed votes into
    the sampler — the one call in this package that stands in for the neutral
    draw — the claim in the module docstring would be false and the null set
    would no longer be a neutral one.
    """
    seen: list[tuple] = []

    def spy(adjacency, populations, k, epsilon, seeds):
        seen.append((adjacency, populations, k, epsilon, seeds))
        return path_pool()

    N.sample_nulls(
        path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (7, 8),
        PATH_DEM, PATH_REP, sampler=spy, n_select=1,
    )
    assert len(seen) == 1
    adjacency, pops, k, epsilon, seeds = seen[0]
    assert k == PATH_K and epsilon == PATH_EPSILON and tuple(seeds) == (7, 8)
    assert pops == PATH_POPS
    for argument in (adjacency, pops):
        assert PATH_DEM not in (argument,)
        assert PATH_REP not in (argument,)
    # The vote mappings share their keys with the populations, so identity is
    # the check that means something: no vote object reached the sampler.
    assert all(value in PATH_POPS.values() for value in pops.values())


def test_seat_distribution_and_median_describe_the_pool():
    pool = path_pool()
    distribution = N.seat_distribution(pool, PATH_DEM, PATH_REP, "D")
    assert sum(distribution.values()) == len(pool)
    assert list(distribution) == sorted(distribution)
    by_hand: dict[int, int] = {}
    for plan in pool:
        seats = brute_force_seats(plan, "D")
        by_hand[seats] = by_hand.get(seats, 0) + 1
    assert distribution == dict(sorted(by_hand.items()))
    assert N.median_seats(pool, PATH_DEM, PATH_REP, "D") == pytest.approx(
        sorted(brute_force_seats(p, "D") for p in pool)[len(pool) // 2]
        if len(pool) % 2
        else sum(sorted(brute_force_seats(p, "D") for p in pool)[
            len(pool) // 2 - 1: len(pool) // 2 + 1
        ]) / 2
    )


def test_an_empty_draw_is_an_empty_null_set_not_a_crash():
    assert nulls_on_path(pool=[]) == []


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"party": "Whig"}, "party"),
        ({"n_select": 0}, "n_select"),
        ({"stratum": "efficiency_gap"}, "stratum"),
    ],
)
def test_sample_nulls_refuses_bad_arguments(kwargs, message):
    with pytest.raises(ValueError, match=message):
        nulls_on_path(**kwargs)


# --------------------------------------------------------------------------- #
# the firewall claim this package makes about itself
# --------------------------------------------------------------------------- #

def test_adversarial_never_imports_generate():
    """``adversarial`` may import ``evaluate`` only (tools/firewall.yaml).

    ``tools/check_firewall.py`` enforces this in CI. It is repeated here because
    the reason matters to *this* package specifically: the neutral draw is
    injected rather than imported precisely so that election data cannot reach
    the sampler through it, and that is the claim nulls.py makes in prose.
    """
    for path in sorted(Path("src/adversarial").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            assert "generate" not in names, f"{path} imports generate"
            assert "detect" not in names, f"{path} imports detect"


# --------------------------------------------------------------------------- #
# Iowa: the numbers that go in the report
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def iowa_inputs():
    adjacency = load_rook(PROCESSED / "ia_adjacency.json")
    pops = load_populations(PROCESSED / "ia_units.csv")
    dem, rep = two_party(load_elections(PROCESSED / "ia_elections.csv"))
    enacted = load_plan(PROCESSED / "ia_enacted_cd118.csv")
    return adjacency, pops, dem, rep, enacted


@pytest.fixture(scope="module")
def iowa_d(iowa_inputs):
    adjacency, pops, dem, rep, enacted = iowa_inputs
    return maximize_seats(
        "D", adjacency, pops, dem, rep, 4, 2e-4, 20260818, 40_000,
        restarts=3, baseline_plan=enacted,
    )


@pytest.fixture(scope="module")
def iowa_r(iowa_inputs):
    adjacency, pops, dem, rep, enacted = iowa_inputs
    return maximize_seats(
        "R", adjacency, pops, dem, rep, 4, 2e-4, 20260818, 40_000,
        restarts=3, baseline_plan=enacted,
    )


@iowa
def test_iowa_enacted_plan_is_legal_at_the_bench_epsilon(iowa_inputs):
    """The reference point for every shift below, checked not assumed."""
    adjacency, pops, _dem, _rep, enacted = iowa_inputs
    record = check_legality(enacted, adjacency, pops, 4, 2e-4)
    assert record.passed
    assert record.population_spread == IA_ENACTED_SPREAD
    assert record.ideal_population == pytest.approx(IA_IDEAL)


@iowa
def test_iowa_democratic_gerrymander_reaches_at_least_two_seats(iowa_d):
    """The positive case the 2-seat detection gate needs (CRITERIA section 8).

    Iowa's enacted map is 4R-0D, so two manufactured D seats is a +2 shift —
    the magnitude the gate is stated at, and the only direction it is reachable
    in. See ``test_iowa_republican_gerrymander_has_no_headroom``.

    The assertion is ``>= 2`` rather than ``== 2`` because the true ceiling is
    3 (``test_iowa_three_seat_ceiling_is_reachable_with_a_larger_budget``) and a
    cheap run reaching it would be a better search, not a broken test.
    """
    assert iowa_d.realized_seat_count >= 2
    assert iowa_d.baseline_seat_count == 0
    assert iowa_d.seat_shift == iowa_d.realized_seat_count
    assert iowa_d.legality.passed
    assert iowa_d.legality.max_deviation_persons <= 2e-4 * IA_IDEAL
    # A gerrymander is not required to be more equal than the enacted plan, but
    # it must satisfy the same standard the ensemble does.
    assert iowa_d.population_spread <= 2 * 2e-4 * IA_IDEAL


@iowa
def test_iowa_democratic_gerrymander_cracks_and_packs(iowa_d):
    """The two won seats are narrow and the lost ones are not.

    This is the signature the detector is meant to find: the manufactured seats
    sit just above half, and the D votes that would have been wasted improving
    them are dumped into districts that were lost anyway.
    """
    shares = sorted(iowa_d.district_shares.values())
    won = [s for s in shares if s > 0.5]
    lost = [s for s in shares if s <= 0.5]
    assert len(won) == iowa_d.realized_seat_count
    assert lost, "a 4-seat Democratic sweep is arithmetically impossible here"
    assert max(won) < 0.60, "a manufactured seat is a narrow seat"
    assert min(lost) < 0.45, "the sacrificed districts are given away, not contested"


@iowa
def test_iowa_republican_gerrymander_has_no_headroom(iowa_r, iowa_inputs):
    """The finding about the target state, not a bug to hide.

    Iowa 2020 is R+8.4 statewide and the enacted map already wins every seat, so
    the R ceiling *is* the enacted outcome and the achievable R shift is zero.
    A 2-seat R gerrymander is not constructible at any effort, which is why the
    detection gate can only be exercised in the D direction here.
    """
    assert iowa_r.realized_seat_count == 4
    assert iowa_r.baseline_seat_count == 4
    assert iowa_r.seat_shift == 0
    assert iowa_r.legality.passed


@iowa
def test_iowa_three_seat_ceiling_is_reachable_with_a_larger_budget(iowa_inputs):
    """The headline claim about the target state, executed rather than asserted.

    Three of four seats is the arithmetic maximum for the Democrats in Iowa
    2020: a district is won with more than half its two-party votes, so four
    would take more than half the statewide two-party total (828,367) and only
    759,061 Democratic votes were cast. The search reaching 3 therefore reaches
    the ceiling, and the resulting plan is the only magnitude in this state
    that lies outside the neutral ensemble's support.

    It is slow — the legal region around a 50.1%-three-ways plan is tiny — and
    that cost is the finding, not an inconvenience: a claim about what an
    adversary can do is worth the minute it takes to check.
    """
    adjacency, pops, dem, rep, enacted = iowa_inputs
    result = plant_gerrymander(
        "D", 3, adjacency, pops, dem, rep, 4, 2e-4, 987654321, 200_000,
        baseline_plan=enacted, restarts=12,
    )
    assert result is not None, "the 3-seat Democratic ceiling was not reached"
    assert result.realized_seat_count == 3
    assert result.seat_shift == 3
    assert result.legality.passed
    assert is_valid(result.plan, adjacency, 4)
    won = sorted(s for s in result.district_shares.values() if s > 0.5)
    assert len(won) == 3
    assert max(won) < 0.52, "three seats out of a 45.8% statewide share is thin"


@iowa
def test_iowa_cannot_plant_a_positive_republican_shift(iowa_inputs):
    adjacency, pops, dem, rep, enacted = iowa_inputs
    assert (
        plant_gerrymander(
            "R", 1, adjacency, pops, dem, rep, 4, 2e-4, 20260818, 20_000,
            baseline_plan=enacted, restarts=2,
        )
        is None
    )


@iowa
def test_iowa_plants_a_one_seat_shift_exactly(iowa_inputs):
    """A 1-seat plant must win one seat, not two.

    The detection threshold curve is a function of magnitude, so a plant that
    drifted to the ceiling would report a 1-seat true positive rate computed on
    2-seat plans.
    """
    adjacency, pops, dem, rep, enacted = iowa_inputs
    result = plant_gerrymander(
        "D", 1, adjacency, pops, dem, rep, 4, 2e-4, 20260818, 40_000,
        baseline_plan=enacted, restarts=3,
    )
    assert result is not None
    assert result.realized_seat_count == 1
    assert result.seat_shift == 1
    assert result.intended_seat_shift == 1
    assert result.legality.passed


@iowa
def test_iowa_achievable_range_is_two_seats_in_one_direction(iowa_inputs):
    adjacency, pops, dem, rep, enacted = iowa_inputs
    found = achievable_seats(
        adjacency, pops, dem, rep, 4, 2e-4, 20260818, 40_000,
        restarts=3, baseline_plan=enacted, baseline_source="enacted CD118",
    )
    assert found["D"]["max_seats"] == 2
    assert found["R"]["max_seats"] == 4
    assert found["D"]["max_shift"] == 2
    assert found["R"]["max_shift"] == 0
    assert found["max_shift"] == 2
    assert found["comparable"] is True
    assert found["baseline_source"] == "enacted CD118"
    assert found["baseline_seat_counts"] == (0, 4, 0)


@iowa
def test_iowa_r_direction_headroom_is_a_property_of_the_baseline(iowa_inputs, iowa_d):
    """The round-2 "manufactured headroom", as a measurement of the choice.

    Iowa 2020 is R+8.4 and the enacted map is already 4R-0D, so from the
    enacted plan the Republican ceiling *is* the baseline and the achievable R
    shift is 0. Measured from a plan that already gives the Democrats two of
    four seats — which 47% of neutral ReCom draws do — the same search in the
    same state reports a **+2** R shift. Nothing about Iowa changed; the
    subtrahend did. Round 2 took its D shifts from the enacted plan and its R
    shifts from the most Democratic-favouring draw of a 14-plan reference and
    pooled the two into one gate.
    """
    adjacency, pops, dem, rep, enacted = iowa_inputs
    assert iowa_d.realized_seat_count >= 2, "the second baseline must not be 4R-0D"

    from_enacted = maximize_seats(
        "R", adjacency, pops, dem, rep, 4, 2e-4, 20260818, 20_000,
        restarts=2, baseline_plan=enacted, baseline_source="enacted CD118",
    )
    from_two_seat = maximize_seats(
        "R", adjacency, pops, dem, rep, 4, 2e-4, 20260818, 20_000,
        restarts=2, baseline_plan=iowa_d.plan,
        baseline_source="a plan that already gives D two seats",
    )
    assert from_enacted.realized_seat_count == from_two_seat.realized_seat_count == 4
    assert from_enacted.seat_shift == 0
    assert from_two_seat.seat_shift == 4 - iowa_d.realized_seat_count >= 2
    assert from_enacted.baseline_source != from_two_seat.baseline_source


@iowa
def test_iowa_the_shape_envelope_makes_a_planted_plan_shape_typical(iowa_inputs):
    """D-010 on the real graph: the round-2 fingerprint, and its removal.

    Round 2's planted plans had 93-99 cut edges against 46-55 for every neutral
    map, so ``cut_edges > 60`` alone scored TPR 1.0 and FPR 0.0 without reading
    a vote. Inside a calibrated envelope the same search, at the same magnitude,
    returns a plan whose five non-partisan measures all sit within the neutral
    draws' own range — and the unconstrained search, run here beside it, still
    does not.

    ``generate`` is imported *in the test*, as in the null case below: the
    neutral draw happens on the far side of the firewall and this package never
    reaches across it. Both runs are at the quick epsilon, for the same reason
    the bench's QUICK size is: at 2e-4 a single unlucky ReCom seed can hold a
    chain for minutes.
    """
    from generate.ensemble import run_chains  # noqa: PLC0415 - see docstring
    from generate.units import load_geometry  # noqa: PLC0415

    adjacency, pops, dem, rep, enacted = iowa_inputs
    geometry = load_geometry()
    epsilon = 2e-3
    pool = list(run_chains(adjacency, pops, 4, epsilon, 30, (11, 12, 13)).plans)
    assert len(pool) > 20, "the neutral pool must be big enough to calibrate from"
    envelope = calibrate_shape_envelope(
        pool, adjacency, geometry, coverage=1.0,
        source="3 ReCom chains x 30 steps at epsilon=2e-3",
    )

    planted = plant_gerrymander(
        "D", 2, adjacency, pops, dem, rep, 4, epsilon, 20260818, 20_000,
        baseline_plan=enacted, baseline_source="enacted CD118", restarts=4,
        shape_envelope=envelope, geometry=geometry, start_plans=pool[::4],
    )
    assert planted is not None, "a 2-seat D shift must survive the envelope"
    assert planted.seat_shift == 2
    assert planted.legality.passed
    assert envelope.violations(planted.shape_metrics) == {}
    assert planted.legality.checks["compactness_within_neutral_envelope"] is True

    unconstrained = plant_gerrymander(
        "D", 2, adjacency, pops, dem, rep, 4, epsilon, 20260818, 20_000,
        baseline_plan=enacted, baseline_source="enacted CD118", restarts=4,
    )
    assert unconstrained is not None
    loose_shape = shape_metrics(unconstrained.plan, adjacency, geometry)
    assert envelope.violations(loose_shape), (
        "the unconstrained search is supposed to still be separable; if this "
        "stops being true the round-2 finding has changed and the numbers in "
        "docs/progress.md need re-measuring"
    )
    assert loose_shape["cut_edges"] > planted.shape_metrics["cut_edges"]


@iowa
def test_iowa_nulls_come_from_a_neutral_ensemble_and_look_biased(iowa_inputs):
    """End to end with the real sampler, wired the way ``detect`` wires it.

    ``generate`` is imported *here*, in the test, and handed to ``sample_nulls``
    as a callable. That is the shape the firewall requires: the neutral draw
    happens on the far side of the boundary and this package never reaches
    across it.
    """
    from generate.ensemble import run_chains  # noqa: PLC0415 - see docstring

    adjacency, pops, dem, rep, _enacted = iowa_inputs

    def sampler(adj, population, k, epsilon, seeds):
        return run_chains(adj, population, k, epsilon, 40, seeds).plans

    cases = N.sample_nulls(
        adjacency, pops, 4, 2e-3, (11, 12, 13), dem, rep,
        sampler=sampler, n_select=4, drawn_by="generate.ensemble.run_chains",
    )
    assert cases, "the neutral ensemble produced no usable plan"
    for case in cases:
        assert case.intended_seat_shift == 0
        assert case.legality.passed
        assert is_valid(case.plan, adjacency, 4)
        assert case.drawn_by == "generate.ensemble.run_chains"
        assert case.pool_size >= case.distinct_pool_size >= 1
    assert [c.selection_rank for c in cases] == [1, 2, 3, 4]
    assert abs(cases[0].seat_shift) >= abs(cases[-1].seat_shift)
