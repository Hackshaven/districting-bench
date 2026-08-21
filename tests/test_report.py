"""Tests for src/evaluate/report.py — the Phase 2 side-by-side surface.

``prompt.md`` Phase 2 says to implement fully and unit-test fully, and to report
every metric side by side *always*, with disagreements highlighted rather than
resolved. The tests here are therefore mostly about the two ways that requirement
can be quietly violated:

**By omission.** A family missing from the report, or a metric silently dropped
because it was ``None``, still looks like a complete report. So the shape of the
output is pinned against the metric lists in the three modules rather than against
a hand-written list that could drift.

**By resolution.** The failure this file exists to prevent is a helper that
collapses the report to one number, or that filters the untrusted metrics out
instead of flagging them. Both are tested as absences: no numeric aggregate, and
untrusted values still present with their values.

The disagreement detector is tested on hand-built reports where the right answer
is known before the code runs, since a detector that never fires and a detector
that always fires are equally useless and neither is visible from real data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from evaluate import administrative, compactness, partisan, report  # noqa: E402
from evaluate import elections as E, plan as EP                     # noqa: E402
from generate import units as GU                                    # noqa: E402

PROCESSED = ROOT / "data" / "processed"


# --------------------------------------------------------------------------- #
# the report refuses to score
# --------------------------------------------------------------------------- #

def test_there_is_no_combined_score():
    """The single most important property of this module."""
    assert report.score_plan.__doc__
    forbidden = ("fairness_score", "overall_score", "composite")
    source = (ROOT / "src" / "evaluate" / "report.py").read_text()
    for name in forbidden:
        assert f"def {name}" not in source


def test_combined_score_is_present_as_an_explicit_none_with_a_reason():
    """An absent key reads as an oversight; None with a reason reads as a choice."""
    built = _tiny_report()
    assert built["combined_score"] is None
    assert "stop" in built["combined_score_note"]


def test_no_key_in_the_report_is_a_score():
    """Nothing may be added later that reduces the report to a ranking."""
    built = _tiny_report()
    scored = [key for key in built
              if "score" in key.lower() and key != "combined_score"
              and key != "combined_score_note"]
    assert scored == []


# --------------------------------------------------------------------------- #
# disagreement detection — must fire, and must not always fire
# --------------------------------------------------------------------------- #

def test_compactness_disagreement_fires_on_a_wide_spread():
    built = {"compactness": {"polsby_popper_mean": 0.20, "reock_mean": 0.40,
                             "convex_hull_mean": 0.80}}
    kinds = [d["kind"] for d in report.find_disagreements(built)]
    assert "compactness_measures_disagree" in kinds


def test_compactness_disagreement_is_silent_when_the_measures_agree():
    built = {"compactness": {"polsby_popper_mean": 0.40, "reock_mean": 0.44,
                             "convex_hull_mean": 0.46}}
    kinds = [d["kind"] for d in report.find_disagreements(built)]
    assert "compactness_measures_disagree" not in kinds


def test_schwartzberg_is_excluded_from_the_spread():
    """It is a ratio where smaller is better; including it invents disagreement."""
    assert "schwartzberg_mean" not in report.COMPARABLE_COMPACTNESS
    built = {"compactness": {"polsby_popper_mean": 0.40, "reock_mean": 0.44,
                             "convex_hull_mean": 0.46, "schwartzberg_mean": 2.1}}
    kinds = [d["kind"] for d in report.find_disagreements(built)]
    assert "compactness_measures_disagree" not in kinds


def test_partisan_sign_disagreement_fires_when_metrics_point_opposite_ways():
    built = {"partisan": {"efficiency_gap": 0.08, "mean_median": -0.03,
                          "declination": 0.10, "partisan_bias": 0.0}}
    found = [d for d in report.find_disagreements(built)
             if d["kind"] == "partisan_metrics_disagree_in_sign"]
    assert found
    assert found[0]["favouring_one_party"] == ["efficiency_gap", "declination"]
    assert found[0]["favouring_the_other"] == ["mean_median"]


def test_partisan_sign_disagreement_is_silent_when_they_agree():
    built = {"partisan": {"efficiency_gap": 0.08, "mean_median": 0.03,
                          "declination": 0.10}}
    kinds = [d["kind"] for d in report.find_disagreements(built)]
    assert "partisan_metrics_disagree_in_sign" not in kinds


def test_a_none_metric_does_not_count_as_a_sign():
    """Declination returns None where it is undefined; None is not negative."""
    built = {"partisan": {"efficiency_gap": 0.08, "declination": None}}
    kinds = [d["kind"] for d in report.find_disagreements(built)]
    assert "partisan_metrics_disagree_in_sign" not in kinds


def test_constant_metrics_are_reported_as_a_disagreement():
    built = {"administrative": {"degeneracy": {
        "county_splits": {"constant": True, "reason": "units are subdivisions"},
        "n_districts": {"constant": False, "reason": ""}}}}
    found = [d for d in report.find_disagreements(built)
             if d["kind"] == "metrics_constant_by_construction"]
    assert found
    assert found[0]["metrics"] == ["county_splits"]


def test_untrusted_metrics_are_flagged_but_still_reported():
    built = _tiny_report()
    trust = built["trust"]
    for name in trust["untrusted_partisan_metrics"]:
        assert name in built["partisan"], (
            "an untrusted metric must still appear with its value; a reader "
            "handed a filtered dict cannot tell that filtering happened"
        )


# --------------------------------------------------------------------------- #
# completeness — every metric each module exposes reaches the report
# --------------------------------------------------------------------------- #

def test_every_partisan_metric_reaches_the_report():
    built = _tiny_report()
    for name in partisan.METRICS:
        assert name in built["partisan"], name


def test_every_compactness_measure_reaches_the_report():
    built = _tiny_report()
    for measure in ("polsby_popper", "reock", "schwartzberg", "convex_hull"):
        assert f"{measure}_mean" in built["compactness"], measure
    assert "cut_edges" in built["compactness"]


def test_ballot_styles_per_10k_is_computed_not_none():
    """prompt.md calls it a first-class output and not an afterthought."""
    built = _tiny_report()
    value = built["administrative"]["ballot_styles_per_10k"]
    assert value is not None and value > 0


def test_electorate_is_required_rather_than_defaulted():
    """Defaulting it to None is how it stayed uncomputed while looking present."""
    import inspect
    signature = inspect.signature(report.score_plan)
    assert signature.parameters["electorate"].default is inspect.Parameter.empty


def test_summary_lines_print_every_family_and_end_on_disagreements():
    lines = report.summary_lines(_tiny_report())
    text = "\n".join(lines)
    for family in ("partisan:", "compactness:", "administrative:"):
        assert family in text
    assert any(line.startswith("  disagreements:") for line in lines)


# --------------------------------------------------------------------------- #
# a real plan, end to end
# --------------------------------------------------------------------------- #

def _tiny_report(subdivisions=None, districting=None):
    if not (PROCESSED / "ia_units.gpkg").exists():
        pytest.skip("Iowa data not on disk; run tools/prepare_data.py")
    geom = GU.load_geometry(PROCESSED / "ia_units.gpkg")
    adjacency = GU.load_adjacency(PROCESSED / "ia_adjacency.json")
    units = EP.load_units(PROCESSED / "ia_units.csv")
    el = E.load_elections(PROCESSED / "ia_elections.csv")
    dem_col, rep_col = E.two_party_columns(el, "G20PRE")
    dem, rep = E.two_party(el, dem_col, rep_col)
    enacted = EP.load_plan(PROCESSED / "ia_enacted_cd118.csv")
    electorate = {g: dem[g] + rep[g] for g in dem}
    return report.score_plan(enacted, geometry=geom, adjacency=adjacency,
                             units=units, dem=dem, rep=rep,
                             electorate=electorate,
                             subdivision_layers=(
                                 {"municipality": subdivisions} if subdivisions
                                 else None),
                             districting_layers=districting,
                             contest="G20PRE")


def test_the_iowa_enacted_plan_reports_every_family():
    built = _tiny_report()
    for key in ("partisan", "compactness", "administrative", "trust",
                "disagreements", "contest"):
        assert key in built, key
    assert built["contest"] == "G20PRE"


def test_iowa_reports_its_constant_metrics_as_degenerate():
    """Iowa's units are the counties, so county splits cannot vary."""
    built = _tiny_report()
    found = [d for d in built["disagreements"]
             if d["kind"] == "metrics_constant_by_construction"]
    assert found
    assert "county_splits" in found[0]["metrics"]


# --------------------------------------------------------------------------- #
# the municipality layer — partial by nature, empty on coarse units
# --------------------------------------------------------------------------- #

def _municipalities(prefix):
    import json
    path = PROCESSED / f"{prefix}_municipalities.json"
    if not path.exists():
        pytest.skip(f"{path} not on disk; run tools/prepare_municipalities.py")
    return json.loads(path.read_text())


def test_a_populated_municipality_layer_is_reported_and_informative():
    muni = _municipalities("co")
    built = _colorado_report(muni)
    block = built["subdivision_layers"]["municipality"]
    assert block["informative"] is True
    assert block["n_subdivisions"] > 0
    assert block["splits"] > 0, "Colorado's enacted plan does split municipalities"


def test_an_empty_municipality_layer_is_flagged_not_reported_as_zero_splits():
    """Zero splits from an empty layer is not the same claim as zero splits."""
    muni = _municipalities("ia")
    built = _tiny_report(subdivisions=muni)
    assert built["subdivision_layers"]["municipality"]["informative"] is False
    kinds = [d["kind"] for d in built["disagreements"]]
    assert "subdivision_layer_is_empty_on_these_units" in kinds


def test_omitting_the_layer_reports_none_rather_than_county_numbers():
    built = _tiny_report()
    assert built["subdivision_layers"] is None


def _colorado_report(subdivisions=None, districting=None):
    if not (PROCESSED / "co_units.gpkg").exists():
        pytest.skip("Colorado data not on disk")
    geom = GU.load_geometry(PROCESSED / "co_units.gpkg")
    adjacency = GU.load_adjacency(PROCESSED / "co_adjacency.json")
    counties = {g: g[:5] for g in EP.populations(PROCESSED / "co_units.csv")}
    el = E.load_elections(PROCESSED / "co_elections.csv")
    dem_col, rep_col = E.two_party_columns(el, "G20PRE")
    dem, rep = E.two_party(el, dem_col, rep_col)
    enacted = EP.load_plan(PROCESSED / "co_enacted_cd118.csv")
    electorate = {g: dem[g] + rep[g] for g in dem}
    return report.score_plan(enacted, geometry=geom, adjacency=adjacency,
                             units=counties, dem=dem, rep=rep,
                             electorate=electorate,
                             subdivision_layers=(
                                 {"municipality": subdivisions} if subdivisions
                                 else None),
                             districting_layers=districting,
                             contest="G20PRE")


def test_colorado_county_splits_are_live_with_an_explicit_county_map():
    """D-022: the units table has no county column, so the map must be passed."""
    built = _colorado_report()
    assert built["administrative"]["county_splits"] == 9


# --------------------------------------------------------------------------- #
# ballot styles — prompt.md's first-class output, degenerate on one layer
# --------------------------------------------------------------------------- #

def _layer(prefix, name):
    import json
    path = PROCESSED / f"{prefix}_{name}.json"
    if not path.exists():
        pytest.skip(f"{path} not on disk; run tools/prepare_municipalities.py")
    return json.loads(path.read_text())


def test_one_layer_makes_ballot_styles_identically_the_district_count():
    """The degenerate case CRITERIA.md section 7 warns about."""
    built = _tiny_report()
    assert built["administrative"]["ballot_styles"] == \
        built["administrative"]["n_districts"]


def test_overlaying_legislative_layers_makes_ballot_styles_do_work():
    built = _tiny_report(districting={
        "statehouse": _layer("ia", "statehouse"),
        "statesenate": _layer("ia", "statesenate"),
    })
    overlaid = built["administrative"]["ballot_styles_overlaid"]
    assert overlaid > built["administrative"]["n_districts"], (
        "with three layers a ballot style is a 3-tuple and must exceed the "
        "congressional district count"
    )
    assert built["administrative"]["ballot_styles_overlaid_per_10k"] > 0
    assert built["administrative"]["districting_layers"] == [
        "congressional", "statehouse", "statesenate"]


def test_coi_is_declared_supported_and_unsupplied_by_default():
    """CRITERIA.md section 6: an input layer, never an objective, no data shipped."""
    built = _tiny_report()
    assert built["coi"]["supported"] is True
    assert built["coi"]["supplied"] is False
    assert "never as an objective function" in built["coi"]["note"]


def test_a_supplied_coi_layer_is_counted_like_any_other():
    """Section 6's mechanism: a COI layer is a plain {unit: parent} map."""
    units = sorted(_layer("ia", "statehouse"))
    coi = {k: ("north" if i % 2 else "south") for i, k in enumerate(units)}
    built = _iowa_with_layers({"coi": coi})
    assert built["coi"]["supplied"] is True
    block = built["subdivision_layers"]["coi"]
    assert block["n_subdivisions"] == 2
    assert block["splits"] >= 0 and block["informative"] is True


def test_districting_layers_assign_every_unit():
    """A ballot style is undefined if any component district is missing."""
    for prefix in ("ia", "co"):
        for name in ("statehouse", "statesenate"):
            mapping = _layer(prefix, name)
            unassigned = [u for u, v in mapping.items() if not v]
            assert unassigned == [], (
                f"{prefix}/{name}: {len(unassigned)} units in no district; a "
                f"districting layer is not partial"
            )


def _iowa_with_layers(subdivision_layers):
    if not (PROCESSED / "ia_units.gpkg").exists():
        pytest.skip("Iowa data not on disk")
    geom = GU.load_geometry(PROCESSED / "ia_units.gpkg")
    adjacency = GU.load_adjacency(PROCESSED / "ia_adjacency.json")
    units = EP.load_units(PROCESSED / "ia_units.csv")
    el = E.load_elections(PROCESSED / "ia_elections.csv")
    dem_col, rep_col = E.two_party_columns(el, "G20PRE")
    dem, rep = E.two_party(el, dem_col, rep_col)
    enacted = EP.load_plan(PROCESSED / "ia_enacted_cd118.csv")
    return report.score_plan(enacted, geometry=geom, adjacency=adjacency,
                             units=units, dem=dem, rep=rep,
                             electorate={g: dem[g] + rep[g] for g in dem},
                             subdivision_layers=subdivision_layers,
                             contest="G20PRE")
