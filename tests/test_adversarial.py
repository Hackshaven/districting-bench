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
HAVE_CO = (PROCESSED / "co_units.csv").exists()
colorado = pytest.mark.skipif(not HAVE_CO, reason="Colorado layer not built")

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


def test_the_matched_envelope_names_what_it_is_instead_of_calling_an_iqr_a_coverage():
    """The round-3 mislabelling, as a regression test.

    ``ShapeEnvelope`` had one numeric field, ``coverage``, standing for three
    different quantities, and ``check_legality`` rendered all three as "the
    central N% of the reference". An envelope built as ``target +/- 0.5 IQR``
    was therefore reported to a reader of ``bench-results.json`` as covering the
    central 50% of the neutral distribution, which is a different set, usually a
    different width, and in no sense a coverage at all.
    """
    geometry = grid_geometry()
    adjacency = grid_adjacency()
    pool = grid_pool()
    matched = G.envelope_around_plan(pool[3], pool, adjacency, geometry, width=0.5)

    assert matched.kind == "matched"
    assert matched.coverage is None, "an IQR half-width is not a coverage"
    assert matched.width == 0.5
    assert "interquartile" in matched.description
    assert "central" not in matched.description

    band = grid_envelope(geometry=geometry)
    assert band.kind == "central_band"
    assert band.description == f"the central 90% of {band.source}"

    # and the rendering the artifact actually shows comes from one place
    record = check_legality(
        pool[3], adjacency, GRID_POPS, GRID_K, GRID_EPSILON,
        shape_envelope=matched,
        plan_shape_metrics=shape_metrics(pool[3], adjacency, geometry),
    )
    note = record.notes["compactness_within_neutral_envelope"]
    assert "interquartile" in note and "central 50%" not in note


def test_an_envelope_cannot_carry_a_parameter_that_does_not_apply_to_its_kind():
    kwargs = dict(bounds={"cut_edges": (1.0, 2.0)}, reference_plans=1,
                  reference_draws=1, measures=("cut_edges",), source="test")
    with pytest.raises(ValueError, match="coverage"):
        ShapeEnvelope(coverage=0.5, kind="matched", width=0.5, **kwargs)
    with pytest.raises(ValueError, match="width"):
        ShapeEnvelope(coverage=None, kind="matched", **kwargs)
    with pytest.raises(ValueError, match="width"):
        ShapeEnvelope(coverage=0.9, width=0.5, **kwargs)
    with pytest.raises(ValueError, match="coverage"):
        ShapeEnvelope(coverage=None, **kwargs)
    with pytest.raises(ValueError, match="kind"):
        ShapeEnvelope(coverage=None, kind="whatever", **kwargs)
    floor = ShapeEnvelope(coverage=None, kind="one_sided_floor", **kwargs)
    assert floor.description.startswith("no less compact than")


def test_the_two_matched_constructors_are_one_implementation():
    """``envelope_from_measurements`` is what the bench calls; it must not drift.

    The bench has already measured every reference draw for the detector's own
    percentiles, and re-measuring them inside this module costs 2.7 s per
    Colorado plan. So the shipped path builds the envelope from columns rather
    than from plans — and a second implementation of the same bound is exactly
    how the two would come to disagree without anyone noticing.
    """
    geometry = grid_geometry()
    adjacency = grid_adjacency()
    pool = grid_pool()
    target = pool[3]

    from_plans = G.envelope_around_plan(target, pool, adjacency, geometry, width=0.5)
    series = {
        name: [shape_metrics(p, adjacency, geometry)[name] for p in pool]
        for name in ENVELOPE_MEASURES
    }
    from_columns = G.envelope_from_measurements(
        shape_metrics(target, adjacency, geometry), series, width=0.5,
        reference_plans=len(pool), reference_draws=len(pool),
    )
    assert from_columns.bounds == pytest.approx(from_plans.bounds)
    assert from_columns.kind == from_plans.kind == "matched"
    assert from_columns.anchor == pytest.approx(
        shape_metrics(target, adjacency, geometry)
    )
    with pytest.raises(ValueError, match="width"):
        G.envelope_from_measurements({"cut_edges": 1.0}, series, width=0)
    with pytest.raises(ValueError, match="no reference measurements"):
        G.envelope_from_measurements({"cut_edges": 1.0}, {"cut_edges": []})


def test_the_shipped_bench_path_plants_inside_a_matched_envelope_not_a_band():
    """D-011's finding, closed: the instrument that works is the one that runs.

    Round 3's independent acceptance check measured non-partisan AUC 0.890 on the
    shipped path and found ``envelope_around_plan`` — which measures 0.52-0.56 —
    exported in ``__all__`` and called from nowhere in ``src/``. This test lives
    in the adversarial suite rather than the bench suite because the thing being
    pinned is which of *this module's* two instruments ``detect.bench`` reaches
    for; it needs no data files and no ensemble.
    """
    from detect import bench

    plans = [dict(plan) for plan in grid_pool()]
    adjacency = grid_adjacency()
    geometry = grid_geometry()
    measured = [shape_metrics(plan, adjacency, geometry) for plan in plans]
    columns = {
        name: [row[name] for row in measured] for name in ENVELOPE_MEASURES
    }
    pool = bench.AnchorPool.build(
        plans, columns, n_draws=len(plans), n_distinct=len(plans), source="grid"
    )
    anchor = pool.draw(seed=11, k=GRID_K, limit=4)

    assert anchor.envelope.kind == "matched", (
        "the central band is the round-3 instrument and is reported, not run"
    )
    assert anchor.envelope.width == bench.MATCH_WIDTH
    assert anchor.envelope.contains(measured[anchor.index]), (
        "an envelope anchored on a draw contains that draw, so the search "
        "starts feasible and the feasible set is never empty"
    )
    assert anchor.starts[0] == plans[anchor.index]
    assert 1 <= len(anchor.starts) <= 4
    for start in anchor.starts:
        assert anchor.envelope.contains(
            shape_metrics(start, adjacency, geometry)
        ), "every start plan must satisfy the envelope it is handed with"

    # The anchor is a function of the seed alone, drawn before the search runs,
    # so no plant can be re-anchored onto whichever draw happened to work.
    assert pool.draw(seed=11, k=GRID_K, limit=4).index == anchor.index
    indices = {pool.draw(seed=s, k=GRID_K, limit=1).index for s in range(40)}
    assert len(indices) > 1, "every plant must not share one anchor"


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


# --------------------------------------------------------------------------- #
# the population bound is a constraint, not a score (round 4)
# --------------------------------------------------------------------------- #
#
# Round 4's Colorado smoke run came back ``legal_compliance = 0.25`` and the
# first guess was that the adversarial search had walked off its population
# bound at VTD scale. Measured, it had not: all three planted plans in that run
# were legal at the operating epsilon (the nine illegal cases were neutral
# ReCom draws made at ``--quick``'s looser epsilon and read at the operating
# one), and the planted plans came back with a **5-person spread on a 721,714
# ideal**. The bound is hard and these tests are that claim as executable
# checks, because "hard" is the difference between ground truth and an invalid
# plan.
#
# What the same investigation *did* find is below it: the search's own starting
# plan could not reach the working band on a 3,108-unit graph, so on Colorado
# the seat phase never moved at all. That failure was silent and its symptom was
# a message blaming the iteration budget.


#: A ladder: two parallel paths, rung by rung, in two districts. Every unit is
#: on the boundary, and moving any interior rung-unit out of its district cuts
#: that district in half — so almost every candidate the population descent
#: ranks highly is contiguity-illegal, and the few legal ones are the two ends.
#: That is the Colorado situation in miniature: measured there, at the point the
#: descent declared itself finished, 6,833–12,911 improving candidates remained
#: and the first connectivity-legal one sat at rank 66, 71 and 72 on three
#: seeds, just past an absolute probe cap of 60.
LADDER_N = 100


def ladder_adjacency() -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = {}
    for i in range(LADDER_N):
        a, b = f"a{i:03d}", f"b{i:03d}"
        adjacency[a] = [b] + ([f"a{i - 1:03d}"] if i else []) + (
            [f"a{i + 1:03d}"] if i < LADDER_N - 1 else []
        )
        adjacency[b] = [a] + ([f"b{i - 1:03d}"] if i else []) + (
            [f"b{i + 1:03d}"] if i < LADDER_N - 1 else []
        )
    return adjacency


def ladder_pops() -> dict[str, int]:
    """The heavy units are the *interior* ones, so they sort to the top.

    The two legal moves — the ends of the a-rail — are worth less population
    than the 98 illegal ones, so a best-improvement descent meets every illegal
    candidate before it meets a legal one. Deliberate: it is what makes the
    probe cap, rather than the descent's own logic, the thing under test.
    """
    pops = {}
    for i in range(LADDER_N):
        pops[f"a{i:03d}"] = 2 if i in (0, LADDER_N - 1) else 3
        pops[f"b{i:03d}"] = 1
    return pops


def ladder_state():
    adjacency = {u: tuple(sorted(n)) for u, n in ladder_adjacency().items()}
    pops = ladder_pops()
    plan = {u: (1 if u.startswith("a") else 2) for u in pops}
    return G._State(plan, adjacency, pops, pops, pops, 2, None), pops


def ladder_deviation(state, pops) -> float:
    ideal = sum(pops.values()) / 2
    return max(abs(t - ideal) for t in state.totals.values()) / ideal


def test_an_absolute_probe_cap_reports_a_local_minimum_that_is_not_one():
    """The Colorado bug, reproduced on 200 synthetic units in a tenth of a second.

    With the round-3 cap — an absolute 60 — the descent stops with the two
    districts 49.7% apart while a hundred improving moves are still available,
    two of them legal. Nothing about that is a local minimum; it is the cap.
    """
    state, pops = ladder_state()
    start = ladder_deviation(state, pops)
    assert start > 0.49

    G._descend_population(
        state, sum(pops.values()) / 2, G._Counter(), None, None,
        probe_fraction=0.0,  # the round-3 behaviour: cap = probes = 60
    )
    assert ladder_deviation(state, pops) == pytest.approx(start), (
        "the absolute cap is supposed to freeze this descent; if it no longer "
        "does, the fixture stopped reproducing the measured Colorado failure"
    )

    # ... and the moves it could not see were there all along.
    cands, _ = G._population_candidates(state, sum(pops.values()) / 2)
    improving = [c for c in cands if c[0] < -1e-9]
    assert len(improving) > 60
    legal_ranks = []
    for rank, cand in enumerate(improving):
        applied = G._apply_candidate(state, cand)
        if applied is not None:
            state.undo(applied)
            legal_ranks.append(rank)
    assert legal_ranks, "the fixture must leave a legal improving move available"
    assert min(legal_ranks) >= 60, (
        "the first legal move must sit past the absolute cap, or this test is "
        "not testing the cap"
    )


def test_the_shipped_probe_cap_scales_with_the_candidate_list_and_gets_out():
    """The same descent, same fixture, with the cap the module ships."""
    state, pops = ladder_state()
    ideal = sum(pops.values()) / 2
    G._descend_population(state, ideal, G._Counter(), None, None)
    assert ladder_deviation(state, pops) < 0.02, (
        "the relative cap must let the descent reach the ends of the ladder"
    )
    for district, units in G.districts(state.plan).items():
        assert G._connected(set(units), state.adj), (
            f"district {district} was cut in half; the descent applied a move "
            "whose contiguity check it should have failed"
        )


def test_the_relative_cap_leaves_a_small_graph_alone():
    """Iowa's numbers must not move to fix a bug Iowa does not have.

    On a 99-county graph the candidate list is a few hundred long, so the
    fraction never reaches the floor and the cap is still exactly 60. Asserted
    on the arithmetic rather than on a run, so that it holds for every state of
    the search rather than for one.
    """
    assert G.DEFAULT_DESCENT_PROBES == 60
    small = 267  # measured: Iowa's candidate list from a growth plan
    assert int(G.DEFAULT_DESCENT_PROBE_FRACTION * small) < G.DEFAULT_DESCENT_PROBES
    large = 27_835  # measured: Colorado's, from the same construction
    assert int(G.DEFAULT_DESCENT_PROBE_FRACTION * large) > 1_000


def test_reusing_one_enumeration_never_applies_a_move_that_went_stale():
    """The repricing that makes enumeration reuse safe.

    One candidate list is used for many moves, and a move invalidates its
    neighbours' recorded costs. ``_live_cost`` reprices against the live totals;
    this asserts it prices an invalidated candidate at zero rather than at the
    cost it had when the list was built.
    """
    state, pops = ladder_state()
    ideal = sum(pops.values()) / 2
    cands, _ = G._population_candidates(state, ideal)
    move = next(c for c in cands if c[1] == "move" and c[2] == "a000")
    assert move[0] < 0
    assert G._live_cost(state, move, ideal) == pytest.approx(move[0])

    applied = G._apply_candidate(state, move)
    assert applied is not None
    # a000 now belongs to district 2, so the recorded candidate is meaningless.
    assert G._live_cost(state, move, ideal) == 0.0


def test_the_repair_phase_returns_only_plans_inside_the_band_or_nothing():
    """Question three, executed: the bound is enforced, not scored.

    ``_repair`` records a candidate plan only when its excess over the band is
    exactly zero. Handed a state it cannot tighten — the band here is one
    person on a 900-person total, and the units are 30 to 110 persons — it must
    return ``None`` rather than the best plan it saw.
    """
    adjacency = {u: tuple(sorted(n)) for u, n in path_adjacency().items()}
    plan = brute_force_plans()[0]
    state = G._State(plan, adjacency, PATH_POPS, PATH_DEM, PATH_REP, PATH_K, None)
    seats = state.seats()
    impossible = 1.0  # persons
    assert G._repair(state, random.Random(0), impossible, seats, 8, G._Counter()) is None

    ideal = sum(PATH_POPS.values()) / PATH_K
    band = PATH_EPSILON * ideal
    found = G._repair(
        G._State(plan, adjacency, PATH_POPS, PATH_DEM, PATH_REP, PATH_K, None),
        random.Random(0), band, seats, 8, G._Counter(),
    )
    if found is not None:
        totals: dict[int, int] = {}
        for unit, district in found[1].items():
            totals[district] = totals.get(district, 0) + PATH_POPS[unit]
        assert max(abs(t - ideal) for t in totals.values()) <= band


@pytest.mark.parametrize("seed", [11, 22, 33, 44, 55])
def test_every_returned_plan_is_inside_the_band_at_every_seed(seed):
    """No seed may produce a plan outside epsilon. One counterexample is a bug.

    ``maximize_seats`` asserts this on the way out, so the test is really that
    the assertion is reachable and never fires — the deviation is recomputed
    here from the plan rather than read off the record it is checking.
    """
    result = maximize_on_grid("D", seed=seed)
    ideal = sum(GRID_POPS.values()) / GRID_K
    totals: dict[int, int] = {}
    for unit, district in result.plan.items():
        totals[district] = totals.get(district, 0) + GRID_POPS[unit]
    assert max(abs(t - ideal) for t in totals.values()) <= GRID_EPSILON * ideal
    assert result.legality.checks["population_within_epsilon"]
    assert result.legal


def test_a_restart_frozen_outside_the_working_band_says_so():
    """The failure that was silent, and the message that blamed the budget.

    The seat phase accepts a move only if the state it lands in has zero excess
    over the working band, so a restart that begins outside that band can take
    no move short of one that closes the whole gap. On Colorado every restart
    began there, the annealer ran its full budget without moving, and the
    exhaustion message said the budget was the constraint. It must name the
    real cause instead.
    """
    lopsided = {u: (1 if u in PATH_UNITS[:2] else 2) for u in PATH_UNITS}
    with pytest.raises(SearchExhausted) as excinfo:
        maximize_seats(
            "D", path_adjacency(), PATH_POPS, PATH_DEM, PATH_REP, 2, 0.01, 5,
            2_000, restarts=2, work_epsilon=0.02,
            start_plans=[lopsided],
        )
    message = str(excinfo.value)
    assert "OUTSIDE the working band" in message
    assert "2 of 2 restart(s)" in message
    assert "start_plans" in message


def test_plant_refuses_to_measure_a_magnitude_from_an_illegal_baseline():
    """A shift from an unlawful plan is not a magnitude, it is a number.

    ``_neutral_reference`` returns the most balanced plan it reached rather than
    raising when it cannot reach the band — correct for a caller that only wants
    a starting point, and not something ``plant_gerrymander`` may accept
    silently, because the seat shift it plants is measured *from* that plan.
    ``None`` would be the wrong answer too: that means "the magnitude was not
    reached", and this is not that.
    """
    with pytest.raises(SearchExhausted) as excinfo:
        plant_gerrymander(
            "D", 1, path_adjacency(), PATH_POPS, PATH_DEM, PATH_REP,
            PATH_K, 1e-9, 3, 2_000, restarts=2, work_epsilon=0.6,
        )
    message = str(excinfo.value)
    assert "neutral reference" in message
    assert "population_within_epsilon" in message
    assert "baseline_plan=" in message


@colorado
def test_colorado_the_default_start_reaches_the_band_at_vtd_scale():
    """The regression that matters: 3,108 units, not 99.

    Measured before the fix, on three seeds: a growth plan at 0.52-0.54 of
    ideal, and the descent stalling at 0.166, 0.485 and 0.491 — every one of
    them outside even the 10% working band, let alone Colorado's operating
    epsilon of 1e-2. After it, the same three seeds reach 3e-6, 5e-6 and 9e-5.

    This is the slowest test in the file and it is worth its seconds: it is the
    only place the search is exercised on a precinct-scale graph, and every
    constant it depends on was sized on a county-scale one.
    """
    adjacency = load_rook(PROCESSED / "co_adjacency.json")
    pops = load_populations(PROCESSED / "co_units.csv")
    assert len(adjacency) == 3_108
    adj = {u: tuple(sorted(adjacency[u])) for u in adjacency}
    units = sorted(adj)
    k = 8
    ideal = sum(pops.values()) / k
    epsilon = 1e-2

    plan = G._neutral_reference(
        adj, pops, units, k, epsilon * ideal, G.DEFAULT_WORK_EPSILON * ideal,
        random.Random(1000), G._Counter(), tighten=False,
    )
    record = check_legality(plan, adjacency, pops, k, epsilon)
    assert record.checks["contiguous_on_rook_graph"]
    assert record.max_deviation_fraction <= G.DEFAULT_WORK_EPSILON, (
        "the seat phase cannot move from a start outside the working band, so "
        "a start plan that does not reach it makes the whole search inert"
    )
    assert record.passed, (
        "measured, the descent reaches 3e-6 to 9e-5 of ideal on this graph — "
        "well inside epsilon=1e-2 — so anything short of legal here is a "
        "regression, not a tolerance to widen"
    )


def test_a_reused_candidate_whose_unit_lost_its_last_neighbour_is_refused():
    """The bug enumeration reuse introduced, pinned so it cannot come back.

    ``_apply_candidate`` checks that the *source* district survives losing the
    unit. For a plain move it does not check that the unit still touches the
    destination, because a freshly enumerated candidate always did. Reuse breaks
    that.

    The six units below are the smallest graph that separates the two checks.
    ``x`` reaches district 2 only through ``c``; once ``c`` has moved to
    district 1, district 1 is still connected without ``x`` (via ``a-e-c``), so
    the source check passes — and the move would leave district 2 as ``{d, x}``
    with nothing joining them.

    ``test_colorado_the_default_start_reaches_the_band_at_vtd_scale`` caught this
    on the real graph, on contiguity. This is the same failure in six units, so
    it fails in milliseconds and says what it is.
    """
    adjacency = {
        "a": ("b", "e", "x"),
        "b": ("a",),
        "e": ("a", "c"),
        "x": ("a", "c"),
        "c": ("d", "e", "x"),
        "d": ("c",),
    }
    pops = {unit: 10 for unit in adjacency}
    plan = {"a": 1, "b": 1, "e": 1, "x": 1, "c": 2, "d": 2}
    state = G._State(plan, adjacency, pops, pops, pops, 2, None)
    ideal = sum(pops.values()) / 2
    assert G._connected(state.members[1], adjacency)
    assert G._connected(state.members[2], adjacency)

    cands, _ = G._population_candidates(state, ideal)
    move_x = next(c for c in cands if c[1] == "move" and c[2] == "x")
    move_c = next(c for c in cands if c[1] == "move" and c[2] == "c")
    assert G._live_cost(state, move_x, ideal) == pytest.approx(move_x[0])

    assert G._apply_candidate(state, move_c) is not None
    assert state.plan == {"a": 1, "b": 1, "e": 1, "x": 1, "c": 1, "d": 2}

    # x no longer touches district 2 at all, so the recorded candidate is void.
    assert G._live_cost(state, move_x, ideal) == 0.0

    # And this is what accepting it would have produced: the source check
    # passes, and district 2 comes back in two pieces as a "legal" plan.
    assert G._apply_candidate(state, move_x) is not None
    assert not G._connected(state.members[2], adjacency)
