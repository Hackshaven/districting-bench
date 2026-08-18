"""Tests for src/evaluate/administrative.py.

Iowa cannot test this module. Units are counties there, so no subdivision can be
split and every split metric is a structural constant (docs/FEASIBILITY.md
section 5.3). Worse, Iowa satisfies *both* of the module's degeneracy conditions
at once — units are their own subdivisions **and** there is one districting
layer — so it cannot tell them apart either. Testing only against Iowa would run
the general code paths through a single doubly-degenerate case and pass whatever
they contained.

So the arithmetic is pinned on a **synthetic sub-county geography**: 10 counties
of 4 precincts each, where a county can be cut up to four ways, and every
expected count below is worked out by hand in the test that uses it. The Iowa
checks at the end are there to pin the *degeneracy*, not the arithmetic — they
assert that the constants are the constants and that the module says so.

Three regimes exist that Iowa hides, and each has its own section:

* **the two degeneracy conditions coming apart** — sub-county units with one
  layer freeze only ``ballot_styles``; county-level units with two layers freeze
  only the split metrics. ``test_the_two_conditions_freeze_disjoint_sets_of_metrics``
  and ``test_units_that_are_their_own_subdivisions_freeze_only_the_split_metrics``
  are the pair, and ``test_the_metrics_flagged_varying_actually_vary`` measures
  the four metrics an ORed single boolean used to suppress.
* **several districting layers** — the splits criterion needs exactly one, and
  ``test_the_answer_never_depends_on_layer_insertion_order`` pins that picking
  it by dict order gave 1 or 0 for the same two plans.
* **partial subdivision coverage** — municipalities do not cover a state.
  ``test_units_in_no_municipality_are_excluded_not_lumped_together`` and
  ``test_the_sentinel_workaround_would_have_invented_a_split`` pin the right
  answer against the plausible wrong one.

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
# which districting layer the splits metrics use — never the first one silently
# --------------------------------------------------------------------------- #

# Two units in one subdivision, so a split is possible and the two layers
# disagree about whether there is one. This is the smallest case that shows the
# defect: L1 cuts the subdivision, L2 does not.
TWO_UNITS = {"x1": "s", "x2": "s"}
LAYER_CUTTING = {"x1": 1, "x2": 2}
LAYER_WHOLE = {"x1": 1, "x2": 1}


def test_splits_refuse_to_choose_between_several_layers():
    with pytest.raises(ValueError, match="pass layer="):
        A.county_splits({"a": LAYER_CUTTING, "b": LAYER_WHOLE}, TWO_UNITS)
    with pytest.raises(ValueError, match="pass layer="):
        A.split_pieces({"a": LAYER_CUTTING, "b": LAYER_WHOLE}, TWO_UNITS)
    with pytest.raises(ValueError, match="pass layer="):
        A.pieces_by_subdivision([LAYER_CUTTING, LAYER_WHOLE], TWO_UNITS)
    with pytest.raises(ValueError, match="pass layer="):
        A.all_metrics({"a": LAYER_CUTTING, "b": LAYER_WHOLE}, TWO_UNITS)


def test_the_answer_never_depends_on_layer_insertion_order():
    """The regression this pins.

    An earlier version took ``next(iter(layers(plan).values()))`` — the first
    layer in dict insertion order — so the same two plans gave
    ``county_splits = 1`` when built as ``{a: cutting, b: whole}`` and
    ``county_splits = 0`` when built as ``{b: whole, a: cutting}``. No error, no
    warning, and nothing in the output recording which one was used.
    """
    forward = {"a": LAYER_CUTTING, "b": LAYER_WHOLE}
    backward = {"b": LAYER_WHOLE, "a": LAYER_CUTTING}
    for built in (forward, backward):
        with pytest.raises(ValueError):
            A.county_splits(built, TWO_UNITS)
        assert A.county_splits(built, TWO_UNITS, layer="a") == 1
        assert A.county_splits(built, TWO_UNITS, layer="b") == 0
        assert A.split_pieces(built, TWO_UNITS, layer="a") == 2
        assert A.split_pieces(built, TWO_UNITS, layer="b") == 1


def test_select_layer_takes_the_only_layer_without_being_asked():
    name, assignment = A.select_layer(PLAN_A)
    assert name == "district"
    assert assignment == PLAN_A
    # Naming it is allowed; naming a different one is not.
    assert A.select_layer(PLAN_A, "district")[0] == "district"
    with pytest.raises(KeyError, match="the only layer"):
        A.select_layer(PLAN_A, "senate")


def test_select_layer_rejects_an_unknown_name_among_several():
    with pytest.raises(KeyError, match="no layer named"):
        A.select_layer({"a": LAYER_CUTTING, "b": LAYER_WHOLE}, "senate")


def test_a_sequence_of_layers_is_addressed_by_its_generated_name():
    assert A.county_splits([LAYER_CUTTING, LAYER_WHOLE], TWO_UNITS,
                           layer="layer_0") == 1
    assert A.county_splits([LAYER_CUTTING, LAYER_WHOLE], TWO_UNITS,
                           layer="layer_1") == 0


def test_ballot_styles_still_uses_every_layer_and_takes_no_layer_argument():
    # The asymmetry is deliberate: a ballot style is defined by all the
    # districts a voter sits in, a split by one plan against one set of
    # subdivisions.
    both = {"a": LAYER_CUTTING, "b": LAYER_WHOLE}
    assert A.ballot_styles(both, TWO_UNITS) == 2      # (1,1) and (2,1)
    assert A.ballot_styles(LAYER_WHOLE, TWO_UNITS) == 1


def test_all_metrics_records_which_layer_the_splits_came_from():
    got = A.all_metrics({"a": LAYER_CUTTING, "b": LAYER_WHOLE}, TWO_UNITS,
                        layer="b")
    assert got["splits_layer"] == "b"
    assert got["county_splits"] == 0
    assert got["n_districts"] == 1                    # of layer b
    assert got["n_districts_by_layer"] == {"a": 2, "b": 1}
    assert got["n_layers"] == 2


# --------------------------------------------------------------------------- #
# partial subdivision layers — municipalities do not cover a state
# --------------------------------------------------------------------------- #

# Six precincts. Two in Ames, two in Nevada, two unincorporated. This is the
# shape of every real municipal layer, and the shape the module used to refuse.
MUNI_UNITS = {"p1": "ames", "p2": "ames", "p3": "nevada", "p4": "nevada",
              "p5": None, "p6": None}
# Ames whole in district 1; Nevada cut between 1 and 2; the two unincorporated
# precincts land in different districts.
MUNI_PLAN = {"p1": 1, "p2": 1, "p3": 1, "p4": 2, "p5": 1, "p6": 2}


def test_units_in_no_municipality_are_excluded_not_lumped_together():
    # By hand: ames -> {1} whole, nevada -> {1,2} split. One split
    # municipality; pieces 1 + 2 = 3 over 2 municipalities, so 1 excess piece.
    # p5 and p6 are in no municipality and appear in none of these numbers.
    assert A.county_splits(MUNI_PLAN, MUNI_UNITS) == 1
    assert A.split_pieces(MUNI_PLAN, MUNI_UNITS) == 3
    assert set(A.pieces_by_subdivision(MUNI_PLAN, MUNI_UNITS)) == {"ames",
                                                                  "nevada"}


def test_the_sentinel_workaround_would_have_invented_a_split():
    """Why ``None`` and not a shared "unincorporated" id.

    Giving every unincorporated unit the same parent makes one pseudo-city
    spanning the state, which almost every plan cuts. Here it turns 1 split into
    2 and 3 pieces into 5 — a fabricated split of a thing that is not a
    municipality.
    """
    sentinel = {u: (p if p is not None else "UNINCORPORATED")
                for u, p in MUNI_UNITS.items()}
    assert A.county_splits(MUNI_PLAN, sentinel) == 2
    assert A.split_pieces(MUNI_PLAN, sentinel) == 5
    # The honest answer, from the same plan and the same geography.
    assert A.county_splits(MUNI_PLAN, MUNI_UNITS) == 1
    assert A.split_pieces(MUNI_PLAN, MUNI_UNITS) == 3


def test_partial_coverage_is_not_a_unit_coverage_error():
    # The units table still has to list every unit the plan assigns, and vice
    # versa. What it does not have to do is give each one a subdivision.
    short = {u: p for u, p in MUNI_UNITS.items() if u != "p6"}
    with pytest.raises(ValueError, match="not in the units table"):
        A.county_splits(MUNI_PLAN, short)


@pytest.mark.parametrize("missing", [None, "", "   ", float("nan"), "NaN",
                                     "None", "<NA>"])
def test_subdivision_map_reads_missing_values_as_no_subdivision(missing):
    got = A.subdivision_map({"p1": "ames", "p5": missing})
    assert got == {"p1": "ames", "p5": None}


def test_subdivision_map_from_a_dataframe_with_unincorporated_rows():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"GEOID": ["p1", "p2", "p5"],
                          "municipality": ["ames", "ames", None]})
    assert A.subdivision_map(frame) == {"p1": "ames", "p2": "ames", "p5": None}


def test_an_empty_municipal_layer_is_flagged_rather_than_scoring_zero():
    # No unit is in any city. county_splits is 0 — and that 0 is arithmetic,
    # exactly like Iowa's, so it must be flagged rather than read as "no city
    # was harmed".
    nowhere = {u: None for u in MUNI_UNITS}
    assert A.county_splits(MUNI_PLAN, nowhere) == 0
    assert A.split_pieces(MUNI_PLAN, nowhere) == 0
    flags = A.degeneracy(MUNI_PLAN, nowhere)
    assert flags["conditions"]["no_subdivision_coverage"] is True
    assert "county_splits" in flags["constant_metrics"]
    assert "belongs to any subdivision" in flags["metrics"]["county_splits"]["reason"]


def test_ballot_styles_by_subdivision_refuses_a_partial_layer():
    # Administered ballot styles need a layer that covers every voter; splits do
    # not. The error says which layer to pass.
    with pytest.raises(ValueError, match="belong to no subdivision"):
        A.ballot_styles(MUNI_PLAN, MUNI_UNITS, by_subdivision=True)
    with pytest.raises(ValueError, match="county"):
        A.ballot_styles_per_10k(MUNI_PLAN, MUNI_UNITS, 10_000,
                                by_subdivision=True)
    # The section 7 definition itself is unaffected: it never looks at
    # subdivisions.
    assert A.ballot_styles(MUNI_PLAN, MUNI_UNITS) == 2


def test_all_metrics_under_a_partial_layer_reports_rather_than_raising():
    got = A.all_metrics(MUNI_PLAN, MUNI_UNITS, voters=10_000)
    assert got["county_splits"] == 1
    assert got["split_pieces"] == 3
    assert got["excess_pieces"] == 1
    assert got["n_subdivisions"] == 2
    assert got["n_units"] == 6
    assert got["n_units_in_no_subdivision"] == 2
    # The one metric that cannot be defined here is None and says so, instead of
    # taking the whole report down with it.
    assert got["ballot_styles_by_subdivision"] is None
    assert "ballot_styles_by_subdivision" in got["unavailable_metrics"]
    assert got["degeneracy"]["ballot_styles_by_subdivision"]["computable"] is False
    assert "partial layer" in got["degeneracy"][
        "ballot_styles_by_subdivision"]["reason"]
    # ...and the split metrics are live, so they are offered to the percentile
    # machinery.
    for name in ("county_splits", "split_pieces", "excess_pieces"):
        assert name in got["varying_metrics"]


# --------------------------------------------------------------------------- #
# degeneracy — PER METRIC, because the two conditions are independent
# --------------------------------------------------------------------------- #

def test_the_two_conditions_freeze_disjoint_sets_of_metrics():
    """The gate. Sub-county units, one districting layer.

    ``single_layer`` holds, ``subdivisions_are_units`` does not. An ORed
    ``degenerate: True`` boolean here told a consumer that obeys "do not feed a
    flagged metric to an outlier percentile" to discard four metrics that vary.
    """
    flags = A.degeneracy(PLAN_A, UNITS)
    assert flags["conditions"] == {
        "subdivisions_are_units": False,
        "no_subdivision_coverage": False,
        "total_subdivision_coverage": True,
        "single_layer": True,
    }
    assert flags["constant_metrics"] == (
        "ballot_styles", "ballot_styles_per_10k", "n_units",
        "n_units_in_no_subdivision", "n_subdivisions", "n_layers",
    )
    assert flags["varying_metrics"] == (
        "county_splits", "split_pieces", "excess_pieces",
        "ballot_styles_by_subdivision", "n_districts",
    )
    assert flags["unavailable_metrics"] == ()
    # The reason attached to the one frozen metric is about layers, and says
    # nothing about splits.
    assert "single districting layer" in flags["metrics"]["ballot_styles"]["reason"]
    assert flags["metrics"]["county_splits"]["reason"] == ""
    assert flags["metrics"]["ballot_styles_by_subdivision"]["reason"] == ""


def test_the_metrics_flagged_varying_actually_vary():
    """The gate, measured rather than asserted.

    Same geography, same single layer, three plans. If any of these four were
    genuinely a structural constant, this test could not be written.
    """
    varying = A.degeneracy(PLAN_A, UNITS)["varying_metrics"]
    seen = {name: set() for name in varying}
    for plan in (PLAN_A, PLAN_B, PLAN_C):
        got = A.all_metrics(plan, UNITS)
        for name in varying:
            seen[name].add(got[name])
    assert seen["county_splits"] == {1, 3, 2}
    assert seen["split_pieces"] == {13, 13, 14}
    assert seen["excess_pieces"] == {3, 3, 4}
    assert seen["ballot_styles_by_subdivision"] == {13, 13, 14}
    assert all(len(values) > 1 for values in seen.values())
    # And the one that really is frozen does not move.
    assert {A.all_metrics(p, UNITS)["ballot_styles"] for p in
            (PLAN_A, PLAN_B, PLAN_C)} == {4, 2, 3}   # varies with K, not the map


def test_units_that_are_their_own_subdivisions_freeze_only_the_split_metrics():
    """The other side of the split: two layers over county-level units.

    ``subdivisions_are_units`` holds and ``single_layer`` does not, so exactly
    the metrics the previous test found live are the ones frozen here, and vice
    versa. This is the pair of cases the old single boolean could not tell apart.
    """
    units = [f"c{i}" for i in range(10)]
    cong = {c: 1 + i % 4 for i, c in enumerate(units)}
    senate = {c: 1 + i % 3 for i, c in enumerate(units)}
    flags = A.degeneracy({"cong": cong, "senate": senate}, units)
    assert flags["conditions"]["subdivisions_are_units"] is True
    assert flags["conditions"]["single_layer"] is False
    for name in ("county_splits", "split_pieces", "excess_pieces",
                 "ballot_styles_by_subdivision"):
        assert flags["metrics"][name]["constant"] is True
        assert "split a subdivision" in flags["metrics"][name]["reason"]
    assert flags["metrics"]["ballot_styles"]["constant"] is False
    assert "ballot_styles" in flags["varying_metrics"]
    assert "ballot_styles_per_10k" in flags["varying_metrics"]
    # The constants really are constant, whatever the plan.
    assert A.county_splits(cong, units) == 0
    assert A.split_pieces(cong, units) == len(units)
    assert A.county_splits({c: 1 for c in units}, units) == 0


def test_there_is_no_single_degenerate_boolean_to_misread():
    flags = A.degeneracy(PLAN_A, UNITS)
    assert "degenerate" not in flags
    got = A.all_metrics(PLAN_A, UNITS)
    assert "degenerate" not in got
    assert "degenerate_splits" not in got
    assert "degenerate_reason" not in got


def test_every_flagged_metric_carries_its_own_reason_and_nothing_else_does():
    for plan, units in ((PLAN_A, UNITS),
                        ({"c0": 1, "c1": 2}, ["c0", "c1"]),
                        (MUNI_PLAN, MUNI_UNITS)):
        flags = A.degeneracy(plan, units)
        for name, entry in flags["metrics"].items():
            if entry["constant"] or not entry["computable"]:
                assert entry["reason"], f"{name} flagged with no reason"
            else:
                assert entry["reason"] == "", f"{name} unflagged but explained"
        assert set(flags["metrics"]) == set(A.REPORTED_METRICS)


def test_the_declared_constant_value_is_the_value_actually_reported():
    # A flag that says "this is identically 0" and a report that says 3 would be
    # worse than no flag at all.
    for plan, units in ((PLAN_A, UNITS),
                        ({"c0": 1, "c1": 2}, ["c0", "c1"]),
                        (MUNI_PLAN, MUNI_UNITS)):
        got = A.all_metrics(plan, units)
        for name, entry in got["degeneracy"].items():
            if entry["value"] is not None:
                assert got[name] == entry["value"], name


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
    assert got["n_units_in_no_subdivision"] == 0
    assert got["n_subdivisions"] == 10
    assert got["n_districts"] == 4
    assert got["n_layers"] == 1
    assert got["splits_layer"] == "district"
    assert set(got["degeneracy"]) == set(A.REPORTED_METRICS)
    assert got["degeneracy"]["county_splits"]["constant"] is False


def test_all_metrics_omits_the_rate_when_no_electorate_is_given():
    got = A.all_metrics(PLAN_A, UNITS)
    assert got["ballot_styles_per_10k"] is None


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
    # Iowa is the case where both conditions hold at once — which is exactly why
    # it could not have caught the conflation the per-metric flags fix.
    assert got["degeneracy_conditions"]["subdivisions_are_units"] is True
    assert got["degeneracy_conditions"]["single_layer"] is True
    for name in ("county_splits", "split_pieces", "excess_pieces",
                 "ballot_styles", "ballot_styles_by_subdivision",
                 "ballot_styles_per_10k"):
        assert got["degeneracy"][name]["constant"] is True
        assert got["degeneracy"][name]["reason"]
    assert "Iowa Code ch. 42" in got["degeneracy"]["county_splits"]["reason"]
    # Nothing here may be fed to a percentile except the district count, which
    # is fixed by the ensemble rather than by these inputs.
    assert got["varying_metrics"] == ("n_districts",)


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
    numbers = [v for v in got.values()
               if isinstance(v, (int, float)) and not isinstance(v, bool)]
    numbers += [e["value"] for e in got["degeneracy"].values()
                if isinstance(e["value"], (int, float))
                and not isinstance(e["value"], bool)]
    numbers += list(got["n_districts_by_layer"].values())
    assert numbers and all(math.isfinite(v) for v in numbers)
