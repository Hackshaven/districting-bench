"""The committed Experiment 3 plans still say what the write-up says they say.

Three gamed Colorado plans are the whole surviving artifact of Experiment 3 --
the searches were run once and are not to be re-run, so these CSVs plus
`evaluate.partisan` are the only things standing behind the headline. Nothing
in the suite pinned them, which meant a drift in any metric implementation
would silently rewrite a published finding and change `exp3-gameability.png`
underneath it.

The values below are transcribed from the cross-metric table in
`docs/progress.md`, which recorded them to six decimal places after an
independent verifier re-derived every one from the same CSVs. A failure here
means either the metric changed or the write-up is now wrong; it does not mean
the test needs its numbers updated.

Skipped when `data/processed` has not been built, following the convention in
`test_adversarial.py` -- the election returns are not redistributable, so they
are fetched rather than committed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from dataguard import requires

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from evaluate import elections as E, plan as EP, partisan as P   # noqa: E402

PROCESSED = ROOT / "data" / "processed"
PLANS = ROOT / "docs" / "experiment-3-plans"

colorado = requires("co_elections.csv", "co_adjacency.json")

#: Colorado's two-party Democratic share on G20PRE. Every "lopsided against
#: proportionality" claim in Experiment 3 is measured against 0.5694 x 8 = 4.56
#: seats, so the share is pinned too.
CO_DEM_SHARE = 0.5693831949230015

#: plan stem -> (D seats, R seats, tied, efficiency gap, mean-median,
#: declination, partisan bias). None means the metric is undefined on that
#: plan, which for declination is itself a finding: it declines to answer about
#: a sweep, which is the map it most needs to answer about.
PUBLISHED = {
    "mm_plan_D_shape": (7, 1, 0, -0.240319, -0.00000015, -0.537822, 0.0),
    "co_declination_gamed_D7": (7, 1, 0, -0.247778, +0.009486, -0.00000042, 0.0),
    "co_partisan_bias_gamed_D8": (8, 0, 0, -0.361236, +0.031637, None, 0.0),
}

#: The screen bands Experiment 3 ran with. A plan "passes" a metric when its
#: value sits inside the band; these are screen thresholds, not fairness claims.
BANDS = {"efficiency_gap": 0.07, "mean_median": 0.02,
         "declination": 0.1, "partisan_bias": 0.05}


@pytest.fixture(scope="module")
def votes():
    elections = E.load_elections(PROCESSED / "co_elections.csv")
    dem_col, rep_col = E.two_party_columns(elections, "G20PRE")
    return E.two_party(elections, dem_col, rep_col)


@colorado
def test_the_statewide_share_the_lopsidedness_claim_rests_on(votes):
    dem, rep = votes
    assert P.statewide_dem_share(dem, rep) == pytest.approx(CO_DEM_SHARE)


@colorado
@pytest.mark.parametrize("stem", sorted(PUBLISHED))
def test_a_committed_gamed_plan_still_reports_its_published_numbers(stem, votes):
    dem, rep = votes
    plan = EP.load_plan(PLANS / f"{stem}.csv")
    d_seats, r_seats, tied, eg, mm, decl, bias = PUBLISHED[stem]

    assert P.seat_counts(plan, dem, rep) == (d_seats, r_seats, tied)

    metrics = P.all_metrics(plan, dem, rep)
    assert metrics["efficiency_gap"] == pytest.approx(eg, abs=5e-7)
    assert metrics["mean_median"] == pytest.approx(mm, abs=5e-7)
    assert metrics["partisan_bias"] == pytest.approx(bias, abs=5e-7)
    if decl is None:
        assert metrics["declination"] is None, (
            "declination became defined on a plan where the write-up records "
            "it refusing to answer; that is a finding, not a passing test"
        )
    else:
        assert metrics["declination"] == pytest.approx(decl, abs=5e-7)


@colorado
@pytest.mark.parametrize("stem", sorted(PUBLISHED))
def test_each_gamed_plan_is_legal_by_every_standard_this_repo_applies(stem):
    """A gamed plan that is not a valid plan proves nothing."""
    plan = EP.load_plan(PLANS / f"{stem}.csv")
    adjacency = EP.load_adjacency(PROCESSED / "co_adjacency.json")
    EP.validate(plan, adjacency, k=8)


@colorado
@pytest.mark.parametrize("stem", sorted(PUBLISHED))
def test_the_gamed_metric_passes_its_screen_on_a_lopsided_map(stem, votes):
    """The experiment's claim, stated as an assertion.

    Each of these plans hands one party seven or eight of eight seats on 56.94%
    of the two-party vote, and at least one named fairness metric reads inside
    the band a single-metric screen would use. If this ever fails, the headline
    of Experiment 3 has stopped being true.
    """
    dem, rep = votes
    plan = EP.load_plan(PLANS / f"{stem}.csv")
    d_seats, r_seats, _ = P.seat_counts(plan, dem, rep)
    assert max(d_seats, r_seats) >= 7

    metrics = P.all_metrics(plan, dem, rep)
    passing = [name for name, band in BANDS.items()
               if metrics.get(name) is not None and abs(metrics[name]) <= band]
    assert passing, f"{stem} no longer passes any single-metric screen"
