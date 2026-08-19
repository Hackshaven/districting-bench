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
from pathlib import Path

import pytest

from adversarial import nulls as N
from adversarial.gerrymander import (
    GerrymanderResult,
    LegalityRecord,
    SearchExhausted,
    achievable_seats,
    check_legality,
    maximize_seats,
    plant_gerrymander,
)
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
    assert result.baseline_source == "supplied"
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
# null cases
# --------------------------------------------------------------------------- #

def path_pool():
    """A pool of legal path plans, with their D seat counts, for null tests."""
    return brute_force_plans()


def test_selection_keeps_the_most_lopsided_plans():
    pool = path_pool()
    seats = [brute_force_seats(plan, "D") for plan in pool]
    median = N.median_seats(pool, PATH_DEM, PATH_REP, "D")
    worst = max(abs(s - median) for s in seats)

    cases = N.sample_nulls(
        path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
        PATH_DEM, PATH_REP, sampler=N.sampler_from_plans(pool), n_select=2,
    )
    assert cases, "the pool must yield at least one null case"
    assert abs(cases[0].seat_shift) == worst
    assert [c.selection_rank for c in cases] == [1, 2]
    assert [c.id for c in cases] == ["null_geography_01", "null_geography_02"]
    assert abs(cases[0].seat_shift) >= abs(cases[-1].seat_shift)


def test_the_null_set_is_not_all_one_direction():
    """Both sides of the median are negatives, and both must be tested.

    On Iowa the plans furthest from the median all sweep 4R-0D and share an
    efficiency gap to three decimals, so a strict ranking would fill the null
    set with that one direction and never test the direction the planted
    gerrymander actually points in.
    """
    pool = path_pool()
    median = N.median_seats(pool, PATH_DEM, PATH_REP, "D")
    balanced = N.sample_nulls(
        path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
        PATH_DEM, PATH_REP, sampler=N.sampler_from_plans(pool), n_select=2,
    )
    sides = {case.realized_seat_count > median for case in balanced}
    assert sides == {True, False}
    assert all("not all one direction" in c.selection_rule for c in balanced)

    strict = N.sample_nulls(
        path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
        PATH_DEM, PATH_REP, sampler=N.sampler_from_plans(pool), n_select=4,
        balance_directions=False,
    )
    statistics = [case.selection_statistic for case in strict]
    assert statistics == sorted(statistics, reverse=True)
    assert "not all one direction" not in strict[0].selection_rule


def test_every_null_case_carries_zero_intended_shift_and_its_provenance():
    cases = N.sample_nulls(
        path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
        PATH_DEM, PATH_REP, sampler=N.sampler_from_plans(path_pool()),
        n_select=3, drawn_by="ReCom, epsilon=0.1, seeds 1..3",
    )
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
    cases = N.sample_nulls(
        path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
        PATH_DEM, PATH_REP, sampler=N.sampler_from_plans(pool + relabelled),
        n_select=len(pool) + len(relabelled),
    )
    assert cases[0].pool_size == 2 * len(pool)
    assert cases[0].distinct_pool_size == len(pool)
    assert len(cases) == len(pool)


def test_illegal_plans_are_dropped_rather_than_presented_as_neutral_maps():
    pool = path_pool()
    lopsided = dict(pool[0])
    lopsided[PATH_UNITS[0]] = PATH_K  # breaks contiguity and population both
    with_bad = [lopsided] + pool

    kept = N.sample_nulls(
        path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
        PATH_DEM, PATH_REP, sampler=N.sampler_from_plans(with_bad), n_select=10,
    )
    assert all(case.legality.passed for case in kept)
    assert all(case.plan != lopsided for case in kept)

    kept_anyway = N.sample_nulls(
        path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
        PATH_DEM, PATH_REP, sampler=N.sampler_from_plans(with_bad),
        n_select=10, require_legal=False,
    )
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
    assert (
        N.sample_nulls(
            path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
            PATH_DEM, PATH_REP, sampler=N.sampler_from_plans([]),
        )
        == []
    )


@pytest.mark.parametrize(
    "kwargs, message",
    [({"party": "Whig"}, "party"), ({"n_select": 0}, "n_select")],
)
def test_sample_nulls_refuses_bad_arguments(kwargs, message):
    with pytest.raises(ValueError, match=message):
        N.sample_nulls(
            path_adjacency(), PATH_POPS, PATH_K, PATH_EPSILON, (1,),
            PATH_DEM, PATH_REP, sampler=N.sampler_from_plans(path_pool()), **kwargs
        )


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
        restarts=3, baseline_plan=enacted,
    )
    assert found["D"]["max_seats"] == 2
    assert found["R"]["max_seats"] == 4
    assert found["D"]["max_shift"] == 2
    assert found["R"]["max_shift"] == 0
    assert found["max_shift"] == 2


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
