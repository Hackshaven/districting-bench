"""Tests for src/evaluate/administrative.py.

Iowa cannot test this module. Units are counties there, so no subdivision can be
split and every split metric is a structural constant (docs/FEASIBILITY.md
section 5.3). Testing only against Iowa would run the general code paths through
a single degenerate case and pass whatever they contained.

So the arithmetic is pinned on a **synthetic sub-county geography**: 10 counties
of 4 precincts each, where a county can be cut up to four ways, and every
expected count below is worked out by hand in the test that uses it. The Iowa
checks at the end are there to pin the *degeneracy*, not the arithmetic — they
assert that the constants are the constants and that the module says so.

The cases are chosen to fail on a subtly wrong formula rather than a missing
one: the three plans in ``test_splits_and_pieces_rank_plans_differently`` have
been built so that the two counting conventions of docs/CRITERIA.md section 2.3
produce *inverted* orderings, so an implementation that computed one and named
it the other passes neither. ``test_per_10k_denominator_is_voters_not_population``
uses a population an order of magnitude off the electorate, so the common
denominator error changes the answer by 10x instead of by a rounding.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from evaluate import administrative as A

PROCESSED = Path("data/processed")
HAVE_IOWA = (PROCESSED / "ia_units.csv").exists()
iowa = pytest.mark.skipif(not HAVE_IOWA, reason="data/processed not built")

#: Sum of the G20PRE* columns of data/processed/ia_elections.csv — the
#: electorate the module docstring quotes. Pinned by test_iowa_voter_total.
IA_2020_PRESIDENTIAL_VOTES = 1_690_871


# --------------------------------------------------------------------------- #
# the synthetic geography: 10 counties x 4 precincts, units *inside* counties
# --------------------------------------------------------------------------- #

COUNTIES = [f"c{i}" for i in range(10)]
UNITS = {f"{c}p{j}": c for c in COUNTIES for j in range(4)}   # unit -> county


def plan_from(cuts: dict[str, list[int]]) -> dict[str, int]:
    """A plan over all 40 precincts.

    ``cuts`` names the counties that are cut and gives the district of each of
    their four precincts in order. Every other county goes wholly to district 1.
    """
    plan = {}
    for county in COUNTIES:
        districts = cuts.get(county, [1, 1, 1, 1])
        assert len(districts) == 4
        for j, d in enumerate(districts):
            plan[f"{county}p{j}"] = d
    return plan


# One county cut four ways.
PLAN_A = plan_from({"c0": [1, 2, 3, 4]})
# Three counties cut two ways each.
PLAN_B = plan_from({"c0": [1, 1, 2, 2], "c1": [1, 1, 2, 2], "c2": [1, 1, 2, 2]})
# Two counties cut three ways each.
PLAN_C = plan_from({"c0": [1, 1, 2, 3], "c1": [1, 1, 2, 3]})
# Nothing cut: every county whole, but four districts exist.
PLAN_WHOLE = plan_from({})
PLAN_WHOLE_4 = {u: 1 + COUNTIES.index(c) % 4 for u, c in UNITS.items()}


# --------------------------------------------------------------------------- #
# subdivision_map — the four accepted input forms
# --------------------------------------------------------------------------- #

def test_subdivision_map_from_mapping_is_used_as_given():
    assert A.subdivision_map(UNITS)["c3p2"] == "c3"
    assert len(A.subdivision_map(UNITS)) == 40


def test_subdivision_map_from_iterable_is_the_identity():
    got = A.subdivision_map(["19001", "19003"])
    assert got == {"19001": "19001", "19003": "19003"}


def test_subdivision_map_coerces_ids_to_str():
    # Leading zeros are significant in GEOIDs; an int key silently merges
    # "01" and "1".
    got = A.subdivision_map({1: 2})
    assert got == {"1": "2"}


def test_subdivision_map_from_dataframe_with_a_county_column():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"GEOID": ["a1", "a2", "b1"], "county": ["a", "a", "b"]})
    assert A.subdivision_map(frame) == {"a1": "a", "a2": "a", "b1": "b"}


def test_subdivision_map_from_dataframe_without_one_is_the_identity():
    # This is exactly data/processed/ia_units.csv, and the degenerate case.
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"GEOID": ["19001", "19003"], "NAME": ["Adair", "Adams"],
                          "pop": [7496, 3704]})
    assert A.subdivision_map(frame) == {"19001": "19001", "19003": "19003"}


def test_subdivision_map_refuses_to_guess_between_two_candidate_columns():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"GEOID": ["a1"], "county": ["a"], "subdivision": ["z"]})
    with pytest.raises(ValueError, match="more than one subdivision column"):
        A.subdivision_map(frame)


def test_subdivision_map_rejects_a_table_without_geoid():
    pd = pytest.importorskip("pandas")
    with pytest.raises(ValueError, match="GEOID"):
        A.subdivision_map(pd.DataFrame({"id": ["a1"], "county": ["a"]}))


# --------------------------------------------------------------------------- #
# the two split conventions, and the fact that they disagree
# --------------------------------------------------------------------------- #

def test_uncut_plan_has_zero_splits_and_one_piece_per_county():
    # The trap this pins: split_pieces of an uncut map is the number of
    # subdivisions, NOT zero. An implementation that returned 0 here has
    # computed excess pieces and called them pieces.
    assert A.county_splits(PLAN_WHOLE_4, UNITS) == 0
    assert A.split_pieces(PLAN_WHOLE_4, UNITS) == 10
    assert A.all_metrics(PLAN_WHOLE_4, UNITS)["excess_pieces"] == 0


def test_splits_and_pieces_counted_by_hand():
    # PLAN_A: c0 -> districts {1,2,3,4}, nine whole counties.
    #         split subdivisions: 1.  pieces: 4 + 9*1 = 13.
    assert A.county_splits(PLAN_A, UNITS) == 1
    assert A.split_pieces(PLAN_A, UNITS) == 13
    # PLAN_B: c0,c1,c2 -> {1,2} each, seven whole.
    #         split subdivisions: 3.  pieces: 3*2 + 7*1 = 13.
    assert A.county_splits(PLAN_B, UNITS) == 3
    assert A.split_pieces(PLAN_B, UNITS) == 13
    # PLAN_C: c0,c1 -> {1,2,3} each, eight whole.
    #         split subdivisions: 2.  pieces: 2*3 + 8*1 = 14.
    assert A.county_splits(PLAN_C, UNITS) == 2
    assert A.split_pieces(PLAN_C, UNITS) == 14


def test_splits_and_pieces_rank_plans_differently():
    """CRITERIA.md section 2.3: the two conventions "rank plans differently"."""
    plans = {"A": PLAN_A, "B": PLAN_B, "C": PLAN_C}
    by_splits = sorted(plans, key=lambda p: A.county_splits(plans[p], UNITS))
    by_pieces = sorted(plans, key=lambda p: A.split_pieces(plans[p], UNITS))
    # On splits, A(1) < C(2) < B(3): A is best, B is worst.
    assert by_splits == ["A", "C", "B"]
    # On pieces, A and B tie at 13 and C is worst at 14 — so B moves from worst
    # to joint-best and C from middle to worst. The orderings are not a
    # relabelling of each other.
    assert A.split_pieces(PLAN_A, UNITS) == A.split_pieces(PLAN_B, UNITS) == 13
    assert by_pieces[-1] == "C"
    assert A.county_splits(PLAN_C, UNITS) < A.county_splits(PLAN_B, UNITS)
    assert A.split_pieces(PLAN_C, UNITS) > A.split_pieces(PLAN_B, UNITS)


def test_pieces_count_districts_not_units():
    # A county whose four precincts all sit in district 2 is one piece, not
    # four. Counting units per county instead of districts per county would
    # give 40 here.
    plan = {u: 2 for u in UNITS}
    assert A.split_pieces(plan, UNITS) == 10
    assert A.county_splits(plan, UNITS) == 0


def test_pieces_do_not_count_disconnected_fragments():
    # Documented limitation: pieces are (subdivision, district) intersections.
    # c0's district-1 share is precincts 0 and 3, which a geometry-aware count
    # might call two fragments; this module calls it one piece and says so.
    plan = plan_from({"c0": [1, 2, 2, 1]})
    assert A.split_pieces(plan, UNITS) == 11
    assert A.county_splits(plan, UNITS) == 1


# --------------------------------------------------------------------------- #
# ballot styles
# --------------------------------------------------------------------------- #

def test_single_layer_ballot_styles_equal_the_district_count():
    # True at every unit level, not just Iowa's: a 1-tuple is its own district.
    assert A.ballot_styles(PLAN_A, UNITS) == 4
    assert A.ballot_styles(PLAN_B, UNITS) == 2
    assert A.ballot_styles(PLAN_C, UNITS) == 3
    assert A.ballot_styles(PLAN_WHOLE, UNITS) == 1


def test_overlaid_layers_produce_more_styles_than_any_one_layer():
    # Six units. Congressional has 2 districts, senate has 3; the distinct
    # (cong, senate) pairs are (1,1), (1,2), (2,2), (2,3) -> 4 styles.
    # Worked by hand:
    #   u1 (1,1)  u2 (1,2)  u3 (1,1)  u4 (2,2)  u5 (2,3)  u6 (2,3)
    # An implementation that read only the first layer would say 2, only the
    # second 3, and the product of the district counts 6. None of those is 4.
    units = {f"u{i}": f"u{i}" for i in range(1, 7)}
    cong = {"u1": 1, "u2": 1, "u3": 1, "u4": 2, "u5": 2, "u6": 2}
    senate = {"u1": 1, "u2": 2, "u3": 1, "u4": 2, "u5": 3, "u6": 3}
    assert A.ballot_styles({"cong": cong, "senate": senate}, units) == 4
    # A sequence of plans is the same input in another shape.
    assert A.ballot_styles([cong, senate], units) == 4
    assert A.ballot_styles(cong, units) == 2
    assert A.ballot_styles(senate, units) == 3


def test_layer_order_does_not_change_the_count():
    units = {f"u{i}": f"u{i}" for i in range(1, 7)}
    cong = {"u1": 1, "u2": 1, "u3": 1, "u4": 2, "u5": 2, "u6": 2}
    senate = {"u1": 1, "u2": 2, "u3": 1, "u4": 2, "u5": 3, "u6": 3}
    assert (A.ballot_styles([cong, senate], units)
            == A.ballot_styles([senate, cong], units))


def test_layers_must_cover_the_same_units():
    units = {"u1": "u1", "u2": "u2"}
    with pytest.raises(ValueError, match="does not assign the same units"):
        A.ballot_styles([{"u1": 1, "u2": 1}, {"u1": 1}], units)


def test_ballot_styles_by_subdivision_equal_split_pieces_for_one_layer():
    # The link between CRITERIA.md section 7 and section 2.3: one style per
    # (county, district) combination is one style per piece.
    for plan in (PLAN_A, PLAN_B, PLAN_C, PLAN_WHOLE_4):
        assert (A.ballot_styles(plan, UNITS, by_subdivision=True)
                == A.split_pieces(plan, UNITS))
    # And the two definitions genuinely differ: 4 vs 13 on the same plan.
    assert A.ballot_styles(PLAN_A, UNITS) == 4
    assert A.ballot_styles(PLAN_A, UNITS, by_subdivision=True) == 13


# --------------------------------------------------------------------------- #
# ballot styles per 10,000 voters
# --------------------------------------------------------------------------- #

def test_per_10k_is_exact_arithmetic():
    # 4 styles, 20,000 voters -> 4 / 2 per 10k = 2.0 exactly.
    assert A.ballot_styles_per_10k(PLAN_A, UNITS, 20_000) == 2.0
    # 13 styles by subdivision over the same electorate.
    assert A.ballot_styles_per_10k(
        PLAN_A, UNITS, 20_000, by_subdivision=True
    ) == 6.5


def test_per_10k_scales_inversely_with_the_electorate():
    a = A.ballot_styles_per_10k(PLAN_A, UNITS, 10_000)
    b = A.ballot_styles_per_10k(PLAN_A, UNITS, 40_000)
    assert a == pytest.approx(4 * b)
    assert a == pytest.approx(4.0)


def test_per_10k_denominator_is_voters_not_population():
    # The population of this toy state is 400,000; its electorate is 40,000.
    # Confusing the two changes the answer by a factor of ten, not a rounding.
    population = {u: 10_000 for u in UNITS}
    voters = {u: 1_000 for u in UNITS}
    assert sum(population.values()) == 400_000
    assert sum(voters.values()) == 40_000
    assert A.ballot_styles_per_10k(PLAN_A, UNITS, voters) == pytest.approx(1.0)
    assert A.ballot_styles_per_10k(PLAN_A, UNITS, population) == pytest.approx(0.1)


def test_per_10k_accepts_a_per_unit_mapping_and_sums_it():
    voters = {u: (i + 1) for i, u in enumerate(sorted(UNITS))}
    total = sum(voters.values())          # 40*41/2 = 820
    assert total == 820
    assert A.ballot_styles_per_10k(PLAN_A, UNITS, voters) == pytest.approx(
        10_000.0 * 4 / 820
    )


def test_per_10k_raises_on_an_undefined_electorate():
    # CRITERIA.md quality bar: handle the undefined regime explicitly rather
    # than returning inf, which downstream percentile code would happily rank.
    for bad in (0, -1, -0.5):
        with pytest.raises(ValueError, match="undefined for an electorate"):
            A.ballot_styles_per_10k(PLAN_A, UNITS, bad)
    with pytest.raises(ValueError, match="finite"):
        A.ballot_styles_per_10k(PLAN_A, UNITS, float("nan"))
    with pytest.raises(ValueError, match="finite"):
        A.ballot_styles_per_10k(PLAN_A, UNITS, float("inf"))
    with pytest.raises(ValueError, match="no voter count"):
        A.ballot_styles_per_10k(PLAN_A, UNITS, {"c0p0": 5})


# --------------------------------------------------------------------------- #
# coverage errors — a silently dropped county is a plausible wrong number
# --------------------------------------------------------------------------- #

def test_plan_with_a_unit_missing_from_the_units_table_raises():
    plan = dict(PLAN_A)
    plan["ghost"] = 1
    with pytest.raises(ValueError, match="not in the units table"):
        A.county_splits(plan, UNITS)
    with pytest.raises(ValueError, match="not in the units table"):
        A.ballot_styles(plan, UNITS)


def test_units_table_with_an_unassigned_unit_raises():
    plan = dict(PLAN_A)
    del plan["c9p3"]
    with pytest.raises(ValueError, match="not assigned by the plan"):
        A.split_pieces(plan, UNITS)
    with pytest.raises(ValueError, match="not assigned by the plan"):
        A.ballot_styles(plan, UNITS)


# --------------------------------------------------------------------------- #
# degeneracy
# --------------------------------------------------------------------------- #

def test_sub_county_units_are_not_split_degenerate():
    flags = A.degeneracy(PLAN_A, UNITS)
    assert flags["splits"] is False
    # ...but a single districting layer still makes ballot_styles a constant.
    assert flags["ballot_styles"] is True
    assert flags["degenerate"] is True
    assert "single districting layer" in flags["reason"]
    assert "split a subdivision" not in flags["reason"]


def test_units_that_are_their_own_subdivisions_are_split_degenerate():
    units = [f"c{i}" for i in range(10)]
    plan = {c: 1 + i % 4 for i, c in enumerate(units)}
    flags = A.degeneracy(plan, units)
    assert flags["splits"] is True
    assert flags["degenerate"] is True
    assert "no plan over these units can split a subdivision" in flags["reason"]
    # And the constants really are constant, whatever the plan.
    assert A.county_splits(plan, units) == 0
    assert A.split_pieces(plan, units) == len(units)
    assert A.county_splits({c: 1 for c in units}, units) == 0


def test_two_layers_remove_the_ballot_style_degeneracy():
    units = {f"u{i}": f"s{i // 2}" for i in range(4)}
    a = {"u0": 1, "u1": 1, "u2": 2, "u3": 2}
    b = {"u0": 1, "u1": 2, "u2": 1, "u3": 2}
    flags = A.degeneracy({"cong": a, "senate": b}, units)
    assert flags["ballot_styles"] is False
    assert flags["splits"] is False
    assert flags["degenerate"] is False
    assert flags["reason"] == ""


# --------------------------------------------------------------------------- #
# all_metrics
# --------------------------------------------------------------------------- #

def test_all_metrics_reports_every_metric_and_the_flags():
    got = A.all_metrics(PLAN_A, UNITS, voters=20_000)
    assert got["county_splits"] == 1
    assert got["split_pieces"] == 13
    assert got["excess_pieces"] == 3
    assert got["ballot_styles"] == 4
    assert got["ballot_styles_by_subdivision"] == 13
    assert got["ballot_styles_per_10k"] == 2.0
    assert got["n_units"] == 40
    assert got["n_subdivisions"] == 10
    assert got["n_districts"] == 4
    assert got["n_layers"] == 1
    assert got["degenerate_splits"] is False


def test_all_metrics_omits_the_rate_when_no_electorate_is_given():
    got = A.all_metrics(PLAN_A, UNITS)
    assert got["ballot_styles_per_10k"] is None


def test_all_metrics_carries_a_reason_whenever_it_flags_degenerate():
    for plan, units in ((PLAN_A, UNITS),
                        ({"c0": 1, "c1": 2}, ["c0", "c1"])):
        got = A.all_metrics(plan, units)
        if got["degenerate"]:
            assert got["degenerate_reason"], "flagged degenerate with no reason"
        else:
            assert got["degenerate_reason"] == ""


# --------------------------------------------------------------------------- #
# Iowa — pinning the degeneracy, not the arithmetic
# --------------------------------------------------------------------------- #

def _iowa():
    import csv

    with (PROCESSED / "ia_units.csv").open(newline="", encoding="utf-8") as fh:
        units = [row["GEOID"] for row in csv.DictReader(fh)]
    with (PROCESSED / "ia_enacted_cd118.csv").open(
        newline="", encoding="utf-8"
    ) as fh:
        plan = {row["GEOID"]: int(row["district"]) for row in csv.DictReader(fh)}
    return plan, units


@iowa
def test_iowa_enacted_plan_is_a_point_mass_on_every_split_metric():
    plan, units = _iowa()
    assert len(units) == 99 and len(plan) == 99
    got = A.all_metrics(plan, units, voters=IA_2020_PRESIDENTIAL_VOTES)
    assert got["county_splits"] == 0
    assert got["split_pieces"] == 99
    assert got["excess_pieces"] == 0
    assert got["ballot_styles"] == 4
    assert got["ballot_styles_by_subdivision"] == 99
    assert got["n_districts"] == 4
    assert got["degenerate"] is True
    assert got["degenerate_splits"] is True
    assert got["degenerate_ballot_styles"] is True
    assert "Iowa Code ch. 42" in got["degenerate_reason"]


@iowa
def test_iowa_constants_do_not_move_for_any_other_plan():
    """The point mass claim, tested rather than asserted.

    docs/FEASIBILITY.md section 5.3: "identically zero in every plan, by
    construction". Three arbitrary re-assignments of the 99 counties — none of
    them legal plans — still produce the same three numbers, which is what
    "structural constant" means and why an ensemble percentile on them is
    undefined.
    """
    _, units = _iowa()
    for k in (1, 2, 4, 17):
        plan = {g: 1 + i % k for i, g in enumerate(units)}
        assert A.county_splits(plan, units) == 0
        assert A.split_pieces(plan, units) == 99
        assert A.ballot_styles(plan, units) == k


@iowa
def test_iowa_ballot_styles_per_10k():
    plan, units = _iowa()
    rate = A.ballot_styles_per_10k(plan, units, IA_2020_PRESIDENTIAL_VOTES)
    assert rate == pytest.approx(10_000.0 * 4 / 1_690_871)
    assert rate == pytest.approx(0.02365645, abs=5e-8)
    # Per-county administered styles, the number an election office would
    # recognise: 99 counties each printing one congressional style.
    admin = A.ballot_styles_per_10k(
        plan, units, IA_2020_PRESIDENTIAL_VOTES, by_subdivision=True
    )
    assert admin == pytest.approx(10_000.0 * 99 / 1_690_871)
    assert admin == pytest.approx(0.58549706, abs=5e-8)


@iowa
def test_iowa_voter_total_matches_the_documented_denominator():
    """Pin the 1,690,871 the module docstring quotes.

    The module never reads this file — the point of taking ``voters`` as a
    parameter — so the number in its docstring would otherwise be unchecked
    prose. This test is the check, and it lives here because tests may read
    anything (tests/README.md).
    """
    import csv

    path = PROCESSED / "ia_elections.csv"
    if not path.exists():
        pytest.skip("ia_elections.csv not built")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    columns = [c for c in rows[0] if c.startswith("G20PRE")]
    assert len(columns) >= 2
    total = sum(int(row[c]) for row in rows for c in columns)
    assert total == IA_2020_PRESIDENTIAL_VOTES


def test_no_nan_leaks_from_any_reported_number():
    got = A.all_metrics(PLAN_C, UNITS, voters=1234.5)
    numeric = [v for v in got.values() if isinstance(v, (int, float))
               and not isinstance(v, bool)]
    assert numeric and all(math.isfinite(v) for v in numeric)
