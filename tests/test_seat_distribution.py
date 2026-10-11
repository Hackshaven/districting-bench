"""The README's first result is a pure function of committed files, and still says what it says.

`docs/figures/ia-neutral-seat-distribution.png` sits at the top of the README.
Until D-039 it was drawn from a gitignored results file, so neither the figure
nor the numbers quoted beside it could be checked by anyone who had not built the
data, and nothing in the suite pinned them. Both are now recomputed by
`tools/plot_seat_distribution.py` from `docs/experiment-2/ia-draws-v2.csv.gz`
and `docs/phase-2/phase-2-report.json`, so they are pinned here and run in CI.

The counts below are the published ones. A failure means the draws file, the
loader's rectangle or the seat recovery changed, and the README is now wrong; it
does not mean the test needs its numbers updated. The controls further down are
the other half: each one must make `recover_seats` refuse, because a guard that
cannot fail is not a guard (docs/RESEARCH-LOOP-PLAYBOOK.md section 4.2).

No data guard: every file read here is committed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import plot_seat_distribution as S   # noqa: E402

#: Democratic seats -> draws on the D-035 rectangle (6 of 12 chains x 4,594
#: draws). README "First result", docs/progress.md.
PRESIDENT_2020 = {0: 395, 1: 13_516, 2: 13_653, 3: 0, 4: 0}
#: The same draws under the 2020 Senate vote: the span's upper edge moves.
SENATE_2020 = {0: 270, 1: 11_410, 2: 15_876, 3: 8, 4: 0}

#: Two-party totals for the controls: the 2020 presidential race in Iowa, and
#: Colorado's as tools/prepare_data_co.py asserts it (D-016).
IOWA_VOTES = sum(S.TWO_PARTY["G20PRE"])
TOTAL_VOTES = {"IA": IOWA_VOTES, "CO": 1_804_352 + 1_364_607}


@pytest.fixture(scope="module")
def dist():
    return S.seat_distribution()


@pytest.fixture(scope="module")
def levels():
    dem, rep = S.TWO_PARTY["G20PRE"]
    return S.seat_levels(dem / (dem + rep), 4)


def test_the_readme_seat_distribution_is_pinned(dist):
    assert dist["primary"]["contest"] == "G20PRE"
    assert (dist["n_chains"], dist["n_chains_requested"], dist["rectangle"],
            dist["n_draws"]) == (6, 12, 4594, 27_564)
    assert dist["primary"]["counts"] == PRESIDENT_2020
    assert dist["enacted_dem_seats"] == 0


def test_the_numbers_quoted_beside_it_are_pinned(dist):
    # README, the figure and docs/progress.md quote each of these. A change to
    # generate.convergence or to the loader would otherwise move them silently.
    p = dist["primary"]
    two = [chain[2] for chain in p["per_chain_shares"]]
    assert min(two) == pytest.approx(0.4131, abs=1e-4)
    assert max(two) == pytest.approx(0.5795, abs=1e-4)
    assert p["seat_count_split_rhat"] == pytest.approx(1.0136, abs=1e-4)
    assert p["seat_count_ess"] == pytest.approx(286.1, abs=0.5)
    assert p["mcse"][2] == pytest.approx(0.0305, abs=1e-4)
    assert p["after_burn_in"][0] == pytest.approx(0.0115, abs=1e-4)
    first, second = p["half_shares"]
    assert (first[2], second[2]) == (pytest.approx(0.461, abs=1e-3),
                                     pytest.approx(0.530, abs=1e-3))
    assert dist["n_as_equal_as_enacted"] == 454
    assert dist["as_equal_counts"][0] == 2
    assert dist["alternate"]["counts"] == SENATE_2020
    assert dist["alternate"]["chains_seen"][3] == 1


def test_every_sweep_sits_on_its_level_to_the_vote(dist):
    # A plan the Democrats win none of sits on its level up to the strict-
    # majority threshold, k/2T to k/T. This is what makes the 0-seat count --
    # the one the enacted-plan comparison quotes -- a count rather than a reading.
    for contest in ("primary", "alternate"):
        low, high = dist[contest]["sweep_window"]
        first, last = dist[contest]["sweep_residuals"]
        assert low - S.SWEEP_SLACK <= first <= last <= high + S.SWEEP_SLACK


def test_every_other_draw_keeps_a_wide_margin(dist):
    # recover_seats refuses beyond MARGIN of the half-gap. The data sit much
    # closer than that, and docs/progress.md quotes how much closer.
    p = dist["primary"]
    assert p["max_residual"] == pytest.approx(0.0143, abs=1e-4)
    assert p["max_residual"] < 0.35 * p["half_gap"]


@pytest.mark.parametrize("state", ["IA", "CO"])
def test_reading_seats_off_the_gap_agrees_with_a_direct_count(state):
    # The Phase 2 report counted each enacted plan's seats from the returns.
    # Iowa's plan is a sweep, so it checks the vote share and the sign but not
    # the turnout term; Colorado's 5 of 8 exercises the turnout term. Neither
    # sits near Iowa's 1-versus-2 boundary, which rests on the margin check.
    partisan = json.loads(S.REPORT.read_text())[state]["partisan"]
    levels = S.seat_levels(partisan["dem_vote_share"], partisan["n_districts"])
    seats, _ = S.recover_seats([abs(partisan["efficiency_gap"])], levels,
                               TOTAL_VOTES[state])
    assert seats == [partisan["dem_seats"]]


def test_a_draw_past_the_margin_refuses_the_whole_sample(levels):
    # 0.7 of the half-gap is still nearer the 2-seat level than the 1-seat one,
    # so nearness alone would read it as 2 seats. That is the case the margin
    # exists for: a 1-seat plan with a large turnout imbalance lands there.
    half_gap = (levels[1] - levels[2]) / 2
    seats, _ = S.recover_seats([levels[2] + 0.4 * half_gap], levels, IOWA_VOTES)
    assert seats == [2]
    with pytest.raises(ValueError, match="cannot be read off"):
        S.recover_seats([levels[2] + 0.4 * half_gap, levels[2] + 0.7 * half_gap],
                        levels, IOWA_VOTES)


def test_a_draw_read_as_a_sweep_must_be_one(levels):
    seats, _ = S.recover_seats([levels[0] + 3 / IOWA_VOTES], levels, IOWA_VOTES)
    assert seats == [0]
    # 1e-4 off is nothing for a 1-seat plan and impossible for a sweep; exactly
    # on the level is impossible too, under the strict-majority threshold.
    for gap in (levels[0] + 1e-4, levels[0]):
        with pytest.raises(ValueError, match="not a sweep"):
            S.recover_seats([gap], levels, IOWA_VOTES)


@pytest.mark.parametrize("gaps", [[], ["nan", "two"], ["two", "nan"]])
def test_nothing_to_read_refuses(gaps, levels):
    # NaN must be refused wherever it sits: min() and max() both pass a NaN
    # through silently in one of the two orders.
    values = [float("nan") if g == "nan" else levels[2] for g in gaps]
    with pytest.raises(ValueError):
        S.recover_seats(values, levels, IOWA_VOTES)


def test_the_figure_draws(dist, tmp_path):
    out = tmp_path / "figure.png"
    S.draw(dist, out)
    assert out.stat().st_size > 10_000


def test_a_report_for_another_contest_is_refused(tmp_path, monkeypatch):
    report = json.loads(S.REPORT.read_text())
    report["IA"]["contest"] = "G20USS"
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    monkeypatch.setattr(S, "REPORT", path)
    with pytest.raises(ValueError, match="different election"):
        S.seat_distribution()
