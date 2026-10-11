"""The README's first result is a pure function of committed files, and still says what it says.

`docs/figures/ia-neutral-seat-distribution.png` sits at the top of the README.
Until D-039 it was drawn from a gitignored results file, so neither the figure
nor the numbers quoted beside it could be checked by anyone who had not built the
data, and nothing in the suite pinned them. Both are now recomputed by
`tools/plot_seat_distribution.py` from `docs/experiment-2/ia-draws-v2.csv.gz` and
`docs/phase-2/phase-2-report.json`, so they are pinned here and run in CI.

The counts below are the published ones. A failure means the draws file, the
loader's rectangle or the seat recovery changed, and the README is now wrong; it
does not mean the test needs its numbers updated.

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

#: Democratic seats -> draws on the D-035 rectangle (6 chains x 4,594 draws),
#: 2020 presidential two-party vote. README "First result", docs/progress.md.
PUBLISHED = {0: 395, 1: 13_516, 2: 13_653}


@pytest.fixture(scope="module")
def dist():
    return S.seat_distribution()


def test_the_readme_seat_distribution_is_pinned(dist):
    assert dist["contest"] == "G20PRE"
    assert (dist["n_chains"], dist["rectangle"], dist["n_draws"]) == (6, 4594, 27_564)
    assert dist["counts"] == PUBLISHED
    assert dist["enacted_dem_seats"] == 0


def test_every_draw_sits_well_inside_its_own_seat_level(dist):
    # recover_seats already refuses at the half-gap. This pins half that again,
    # so a change to the draws that eats most of the margin fails here, with
    # the margin in the message, before it becomes a refusal nobody expected.
    assert dist["max_residual"] < dist["half_gap"] / 2, (
        f"largest residual {dist['max_residual']:.4f} against a half-gap of "
        f"{dist['half_gap']:.4f}"
    )


@pytest.mark.parametrize("state", ["IA", "CO"])
def test_reading_seats_off_the_gap_agrees_with_a_direct_count(state):
    # The Phase 2 report counted each enacted plan's seats from the returns.
    # Reading them back off the same plan's efficiency gap must give the same
    # answer -- the only check of the identity against a direct count that the
    # committed files allow.
    partisan = json.loads(S.REPORT.read_text())[state]["partisan"]
    levels = S.seat_levels(partisan["dem_vote_share"], partisan["n_districts"])
    seats, _, _ = S.recover_seats([abs(partisan["efficiency_gap"])], levels)
    assert seats == [partisan["dem_seats"]]


def test_a_draw_between_two_levels_refuses_the_whole_sample():
    # A control that must be able to fail: a gap midway between the 1-seat and
    # 2-seat levels belongs to neither, and assigning it to the nearer would be
    # a guess.
    levels = S.seat_levels(0.4581673691536295, 4)
    midway = (levels[1] + levels[2]) / 2
    with pytest.raises(ValueError, match="cannot be read off"):
        S.recover_seats([levels[0], midway], levels)
