"""Tests for evaluate.elections.

The statewide checks are against Iowa's certified 2020 returns, not against the
loader's own output.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from evaluate.elections import (
    DEFAULT_DEM,
    DEFAULT_REP,
    available_contests,
    columns,
    contest_columns,
    load_elections,
    party_name,
    totals,
    two_party,
    two_party_columns,
    zero_vote_units,
)

REPO = Path(__file__).resolve().parents[1]
IA_ELECTIONS = REPO / "data" / "processed" / "ia_elections.csv"

# Iowa, 2020 general election, certified:
IA_TRUMP = 897_672
IA_BIDEN = 759_061
IA_PRESIDENT_ALL_CANDIDATES = 1_690_871


@pytest.fixture(scope="module")
def ia():
    return load_elections(IA_ELECTIONS)


# --------------------------------------------------------------------------- #
# the certified statewide numbers
# --------------------------------------------------------------------------- #

def test_statewide_totals_match_iowas_certified_2020_returns(ia):
    assert len(ia) == 99
    summed = totals(ia)
    assert summed["G20PRERTRU"] == IA_TRUMP
    assert summed["G20PREDBID"] == IA_BIDEN
    assert sum(v for c, v in summed.items() if c.startswith("G20PRE")) == (
        IA_PRESIDENT_ALL_CANDIDATES
    )


def test_two_party_democratic_share_is_0_4582(ia):
    dem, rep = two_party(ia)
    d, r = sum(dem.values()), sum(rep.values())
    assert (d, r) == (IA_BIDEN, IA_TRUMP)
    assert round(d / (d + r), 4) == 0.4582


def test_two_party_share_uses_the_two_party_denominator(ia):
    """The share must divide by D+R, not by all votes cast.

    Iowa 2020 had 34,138 third-party and write-in presidential votes, so the
    two denominators differ in the third decimal: 0.4582 against 0.4489. A
    wrong-denominator implementation lands on the second number.
    """
    dem, rep = two_party(ia)
    d, r = sum(dem.values()), sum(rep.values())
    two_party_share = d / (d + r)
    all_candidate_share = d / IA_PRESIDENT_ALL_CANDIDATES
    assert round(two_party_share, 4) == 0.4582
    assert round(all_candidate_share, 4) == 0.4489
    assert d + r < IA_PRESIDENT_ALL_CANDIDATES


def test_defaults_name_the_2020_presidential_contest():
    assert DEFAULT_DEM == "G20PREDBID"
    assert DEFAULT_REP == "G20PRERTRU"


def test_two_party_is_not_transposed(ia):
    """Swapping the arguments must swap the result.

    This is the test that catches a transposed party: with the columns given in
    the other order, the 'Democratic' total becomes Trump's 897,672 — larger
    than the 'Republican' total, which is the opposite of the true ordering.
    """
    dem, rep = two_party(ia, dem_col=DEFAULT_DEM, rep_col=DEFAULT_REP)
    swapped_dem, swapped_rep = two_party(ia, dem_col=DEFAULT_REP, rep_col=DEFAULT_DEM)
    assert sum(dem.values()) < sum(rep.values())          # Iowa 2020 went R
    assert swapped_dem == rep and swapped_rep == dem
    assert sum(swapped_dem.values()) == IA_TRUMP


def test_a_single_county_matches_the_file(ia):
    # Polk County (Des Moines), the state's largest, read off ia_elections.csv.
    dem, rep = two_party(ia)
    assert dem["19153"] == 146_250
    assert rep["19153"] == 106_800
    assert round(dem["19153"] / (dem["19153"] + rep["19153"]), 4) == 0.5779


def test_senate_contest_totals(ia):
    dem, rep = two_party(ia, dem_col="G20USSDGRE", rep_col="G20USSRERN")
    assert sum(rep.values()) == 864_997      # Ernst
    assert sum(dem.values()) == 754_859      # Greenfield


def test_the_two_2020_contests_disagree(ia):
    """Different contests give different shares, which is why the column is a
    parameter rather than a constant."""
    pres_d, pres_r = two_party(ia)
    uss_d, uss_r = two_party(ia, dem_col="G20USSDGRE", rep_col="G20USSRERN")
    pres = sum(pres_d.values()) / (sum(pres_d.values()) + sum(pres_r.values()))
    uss = sum(uss_d.values()) / (sum(uss_d.values()) + sum(uss_r.values()))
    assert round(pres, 4) == 0.4582
    assert round(uss, 4) == 0.4660
    assert pres != uss


def test_no_iowa_county_is_undefined(ia):
    dem, rep = two_party(ia)
    assert zero_vote_units(dem, rep) == []


# --------------------------------------------------------------------------- #
# contest discovery
# --------------------------------------------------------------------------- #

def test_available_contests_collapses_candidate_columns(ia):
    assert available_contests(ia) == ["G20PRE", "G20USS"]
    assert len(columns(ia)) == 15        # 10 presidential + 5 senate candidates


def test_contest_columns_reads_the_vest_party_letter(ia):
    parties = contest_columns(ia, "G20PRE")
    assert parties["G20PREDBID"] == "D"
    assert parties["G20PRERTRU"] == "R"
    assert parties["G20PRELJOR"] == "L"
    assert sorted(parties) == sorted(c for c in columns(ia) if c.startswith("G20PRE"))


def test_two_party_columns_picks_the_major_party_pair(ia):
    assert two_party_columns(ia, "G20PRE") == (DEFAULT_DEM, DEFAULT_REP)
    assert two_party_columns(ia, "G20USS") == ("G20USSDGRE", "G20USSRERN")


def test_unknown_contest_raises(ia):
    with pytest.raises(ValueError, match="no columns for contest"):
        contest_columns(ia, "G16PRE")


def test_party_name():
    assert party_name("D") == "Democratic"
    assert party_name("r") == "Republican"
    assert party_name("Z") == "Z"


# --------------------------------------------------------------------------- #
# synthetic data: hand-computable, and the failure paths
# --------------------------------------------------------------------------- #

def _write(tmp_path, text):
    path = tmp_path / "e.csv"
    path.write_text(text)
    return path


def test_loader_reads_a_hand_written_file(tmp_path):
    path = _write(tmp_path, "GEOID,G20PREDBID,G20PRERTRU\n001,3,7\n002,10,0\n")
    data = load_elections(path)
    assert data == {"001": {"G20PREDBID": 3, "G20PRERTRU": 7},
                    "002": {"G20PREDBID": 10, "G20PRERTRU": 0}}
    assert totals(data) == {"G20PREDBID": 13, "G20PRERTRU": 7}
    dem, rep = two_party(data)
    assert (dem, rep) == ({"001": 3, "002": 10}, {"001": 7, "002": 0})
    assert sum(dem.values()) / (sum(dem.values()) + sum(rep.values())) == 0.65


def test_zero_vote_unit_is_reported_not_silently_shared(tmp_path):
    """A unit with no two-party votes has an undefined D share.

    CRITERIA.md's conventions define vote share as the two-party Democratic
    fraction, which is 0/0 here. The loader must surface the unit rather than
    hand back a number.
    """
    path = _write(tmp_path, "GEOID,G20PREDBID,G20PRERTRU\n001,0,0\n002,4,6\n")
    dem, rep = two_party(load_elections(path))
    assert zero_vote_units(dem, rep) == ["001"]


def test_zero_vote_units_rejects_mismatched_unit_sets():
    with pytest.raises(ValueError, match="different units"):
        zero_vote_units({"a": 1}, {"a": 1, "b": 2})


def test_negative_votes_raise(tmp_path):
    path = _write(tmp_path, "GEOID,G20PREDBID\n001,-1\n")
    with pytest.raises(ValueError, match="is negative"):
        load_elections(path)


def test_blank_or_non_integer_votes_raise(tmp_path):
    for cell in ("", "  ", "12.0", "n/a"):
        path = _write(tmp_path, f"GEOID,G20PREDBID\n001,{cell}\n")
        with pytest.raises(ValueError, match="must be an integer number of votes"):
            load_elections(path)


def test_repeated_unit_raises(tmp_path):
    path = _write(tmp_path, "GEOID,G20PREDBID\n001,5\n001,6\n")
    with pytest.raises(ValueError, match="appears more than once"):
        load_elections(path)


def test_missing_geoid_column_raises(tmp_path):
    path = _write(tmp_path, "county,G20PREDBID\n001,5\n")
    with pytest.raises(ValueError, match="must have a GEOID column"):
        load_elections(path)


def test_file_with_no_vote_columns_raises(tmp_path):
    path = _write(tmp_path, "GEOID\n001\n")
    with pytest.raises(ValueError, match="no vote columns"):
        load_elections(path)


def test_file_with_no_rows_raises(tmp_path):
    path = _write(tmp_path, "GEOID,G20PREDBID\n")
    with pytest.raises(ValueError, match="no rows"):
        load_elections(path)


def test_two_party_rejects_an_unknown_column(ia):
    with pytest.raises(ValueError, match="no column 'G16PREDCLI'"):
        two_party(ia, dem_col="G16PREDCLI")


def test_two_party_rejects_the_same_column_twice(ia):
    with pytest.raises(ValueError, match="same column"):
        two_party(ia, dem_col=DEFAULT_DEM, rep_col=DEFAULT_DEM)


def test_ragged_table_raises():
    ragged = {"001": {"G20PREDBID": 1, "G20PRERTRU": 2}, "002": {"G20PREDBID": 3}}
    with pytest.raises(ValueError, match="ragged"):
        columns(ragged)


def test_empty_table_raises():
    with pytest.raises(ValueError, match="no election data"):
        columns({})
