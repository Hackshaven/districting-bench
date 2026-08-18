"""Tests for evaluate.plan.

Toy graphs first, with answers worked out by hand, then the real Iowa data
against the numbers in docs/FEASIBILITY.md section 4.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluate.plan import (
    aggregate,
    districts,
    is_valid,
    load_adjacency,
    load_plan,
    load_units,
    populations,
    save_plan,
    validate,
)

REPO = Path(__file__).resolve().parents[1]
PROCESSED = REPO / "data" / "processed"

# a - b - c - d, a path graph. Every hand-checked answer below reads off this.
PATH4 = {
    "a": ["b"],
    "b": ["a", "c"],
    "c": ["b", "d"],
    "d": ["c"],
}

# Star: centre "c" touches a, b and d; a, b, d touch nothing else.
STAR = {
    "c": ["a", "b", "d"],
    "a": ["c"],
    "b": ["c"],
    "d": ["c"],
}


# --------------------------------------------------------------------------- #
# validate — the four cases the architecture makes invariants
# --------------------------------------------------------------------------- #

def test_validate_accepts_a_contiguous_two_district_split():
    validate({"a": 1, "b": 1, "c": 2, "d": 2}, PATH4, 2)


def test_validate_rejects_a_disconnected_district():
    # District 1 is {a, c}; a and c are two hops apart on the path graph.
    with pytest.raises(ValueError, match="district 1 is not connected"):
        validate({"a": 1, "b": 2, "c": 1, "d": 2}, PATH4, 2)


def test_validate_rejects_a_missing_unit():
    with pytest.raises(ValueError, match="does not assign every unit"):
        validate({"a": 1, "b": 1, "c": 2}, PATH4, 2)


def test_validate_rejects_an_empty_district():
    # k=3 but only ids 1 and 2 are used, so district 3 is empty.
    with pytest.raises(ValueError, match="district id"):
        validate({"a": 1, "b": 1, "c": 2, "d": 2}, PATH4, 3)


def test_validate_rejects_a_district_id_outside_1_to_k():
    with pytest.raises(ValueError, match="outside 1..2"):
        validate({"a": 1, "b": 1, "c": 2, "d": 5}, PATH4, 2)

    with pytest.raises(ValueError, match="outside 1..2"):
        validate({"a": 0, "b": 1, "c": 2, "d": 2}, PATH4, 2)


def test_validate_rejects_a_unit_outside_the_graph():
    plan = {"a": 1, "b": 1, "c": 2, "d": 2, "z": 2}
    with pytest.raises(ValueError, match="not in the adjacency graph") as caught:
        validate(plan, PATH4, 2)
    assert "'z'" in str(caught.value)


def test_connectivity_is_measured_on_the_induced_subgraph():
    """{a, b} are joined only through c, which is in the other district.

    A checker that ran BFS over the whole graph instead of the district's own
    induced subgraph would pass this plan. It must not.
    """
    with pytest.raises(ValueError, match="district 1 is not connected"):
        validate({"a": 1, "b": 1, "d": 1, "c": 2}, STAR, 2)

    # The same partition with the centre included is connected.
    validate({"a": 1, "b": 1, "c": 1, "d": 2}, STAR, 2)


def test_validate_rejects_a_nonsense_k():
    for k in (0, -1, 2.5):
        with pytest.raises(ValueError, match="k must be a positive integer"):
            validate({"a": 1, "b": 1, "c": 2, "d": 2}, PATH4, k)


def test_validate_rejects_a_non_integer_district_id():
    for bad in (2.0, "2", None):
        with pytest.raises(ValueError, match="district ids must be integers"):
            validate({"a": 1, "b": 1, "c": 2, "d": bad}, PATH4, 2)


def test_validate_rejects_an_empty_graph():
    with pytest.raises(ValueError, match="adjacency graph is empty"):
        validate({"a": 1}, {}, 1)


def test_is_valid_mirrors_validate():
    assert is_valid({"a": 1, "b": 1, "c": 2, "d": 2}, PATH4, 2)
    assert not is_valid({"a": 1, "b": 2, "c": 1, "d": 2}, PATH4, 2)


def test_single_district_plan_is_valid():
    validate({"a": 1, "b": 1, "c": 1, "d": 1}, PATH4, 1)


# --------------------------------------------------------------------------- #
# structure
# --------------------------------------------------------------------------- #

def test_districts_groups_and_sorts():
    assert districts({"d": 2, "a": 1, "c": 2, "b": 1}) == {1: ["a", "b"], 2: ["c", "d"]}


def test_aggregate_sums_by_district():
    plan = {"a": 1, "b": 1, "c": 2, "d": 2}
    values = {"a": 10, "b": 1, "c": 100, "d": 5}
    assert aggregate(plan, values) == {1: 11, 2: 105}


def test_aggregate_handles_floats_and_negatives():
    plan = {"a": 1, "b": 2}
    assert aggregate(plan, {"a": -1.5, "b": 2.25}) == {1: -1.5, 2: 2.25}


def test_aggregate_refuses_to_drop_a_unit():
    plan = {"a": 1, "b": 1, "c": 2, "d": 2}
    with pytest.raises(ValueError, match="no value for 1 unit"):
        aggregate(plan, {"a": 1, "b": 1, "c": 1})
    with pytest.raises(ValueError, match="not in the plan"):
        aggregate(plan, {"a": 1, "b": 1, "c": 1, "d": 1, "z": 99})


# --------------------------------------------------------------------------- #
# load / save
# --------------------------------------------------------------------------- #

def test_plan_round_trips_and_keeps_leading_zeros(tmp_path):
    plan = {"01001": 2, "01003": 1, "01005": 1}
    path = tmp_path / "plan.csv"
    save_plan(plan, path)
    assert path.read_text().splitlines()[0] == "GEOID,district"
    assert load_plan(path) == plan


def test_save_plan_is_sorted_and_byte_stable(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    save_plan({"c": 1, "a": 2, "b": 1}, a)
    save_plan({"a": 2, "b": 1, "c": 1}, b)
    assert a.read_bytes() == b.read_bytes()
    assert a.read_text().splitlines()[1] == "a,2"


def test_load_plan_rejects_a_repeated_unit(tmp_path):
    path = tmp_path / "dup.csv"
    path.write_text("GEOID,district\n19001,1\n19001,2\n")
    with pytest.raises(ValueError, match="assigned more than once"):
        load_plan(path)


def test_load_plan_rejects_wrong_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("geoid,cd\n19001,1\n")
    with pytest.raises(ValueError, match="must have columns GEOID,district"):
        load_plan(path)


def test_load_plan_rejects_a_non_integer_district(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("GEOID,district\n19001,1\n19003,two\n")
    with pytest.raises(ValueError, match="must be an integer"):
        load_plan(path)


def test_load_plan_rejects_an_empty_file(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("GEOID,district\n")
    with pytest.raises(ValueError, match="no rows"):
        load_plan(path)


# --------------------------------------------------------------------------- #
# the real Iowa data
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def adjacency():
    return load_adjacency(PROCESSED / "ia_adjacency.json")


@pytest.fixture(scope="module")
def enacted():
    return load_plan(PROCESSED / "ia_enacted_cd118.csv")


@pytest.fixture(scope="module")
def pops():
    return populations(PROCESSED / "ia_units.csv")


def test_adjacency_matches_the_feasibility_graph(adjacency):
    # FEASIBILITY.md section 3: 99 counties, 222 rook edges, one component.
    assert len(adjacency) == 99
    assert sum(len(v) for v in adjacency.values()) == 2 * 222
    assert all(a in adjacency[b] for a, ns in adjacency.items() for b in ns)
    assert all(a not in ns for a, ns in adjacency.items())
    degrees = sorted(len(v) for v in adjacency.values())
    assert degrees[0] == 2 and degrees[-1] == 7


def test_units_total_the_2020_census_count(pops):
    # FEASIBILITY.md section 2, verified against the Census apportionment tables.
    assert len(pops) == 99
    assert sum(pops.values()) == 3_190_369
    assert max(pops.values()) == 492_401      # Polk
    assert min(pops.values()) == 3_704        # Adams


def test_load_units_returns_the_documented_columns():
    frame = load_units(PROCESSED / "ia_units.csv")
    assert list(frame.columns) == ["GEOID", "NAME", "pop"]
    assert frame["GEOID"].map(type).eq(str).all()


def test_enacted_plan_is_valid(adjacency, enacted):
    assert len(enacted) == 99
    validate(enacted, adjacency, 4)


def test_enacted_district_populations_match_feasibility(enacted, pops):
    # FEASIBILITY.md section 4, table of the enacted CD118 plan.
    assert aggregate(enacted, pops) == {
        1: 797_584,
        2: 797_589,
        3: 797_551,
        4: 797_645,
    }
    by_district = aggregate(enacted, pops)
    assert sum(by_district.values()) == 3_190_369
    assert max(by_district.values()) - min(by_district.values()) == 94


def test_enacted_county_counts_match_feasibility(enacted):
    members = districts(enacted)
    assert [len(members[d]) for d in (1, 2, 3, 4)] == [20, 22, 21, 36]


def test_moving_one_county_across_the_state_breaks_contiguity(adjacency, enacted, tmp_path):
    """A concrete disconnection on the real graph, not just the toy one.

    Woodbury (19193) is on the western edge in CD4; putting it in CD1, which is
    the north-east corner, must leave CD1 in two pieces.
    """
    broken = dict(enacted)
    assert broken["19193"] == 4
    broken["19193"] = 1
    with pytest.raises(ValueError, match="district 1 is not connected"):
        validate(broken, adjacency, 4)

    # And it survives a round trip through the CSV unchanged.
    path = tmp_path / "broken.csv"
    save_plan(broken, path)
    assert load_plan(path) == broken


def test_dropping_a_county_from_the_enacted_plan_raises(adjacency, enacted):
    short = {g: d for g, d in enacted.items() if g != "19153"}   # Polk
    with pytest.raises(ValueError, match="19153"):
        validate(short, adjacency, 4)


def test_collapsing_a_district_raises(adjacency, enacted):
    # Merge CD4 into CD3: district 4 becomes empty while every unit stays assigned.
    merged = {g: (3 if d == 4 else d) for g, d in enacted.items()}
    with pytest.raises(ValueError, match=r"district\(s\) \[4\] are empty"):
        validate(merged, adjacency, 4)


def test_adjacency_json_is_the_file_on_disk(adjacency):
    raw = json.loads((PROCESSED / "ia_adjacency.json").read_text())
    assert {k: sorted(v) for k, v in adjacency.items()} == {
        str(k): sorted(str(x) for x in v) for k, v in raw.items()
    }
