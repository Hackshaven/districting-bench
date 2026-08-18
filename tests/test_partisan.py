"""Tests for evaluate.partisan.

Every metric here is checked against a case whose answer was worked out on
paper, not against the implementation's own output. The two toy plans below
were built so that all four asymmetry metrics are hand-computable:

``PACKED`` — four districts of 1,000 two-party votes each, three of them 400 D
to 600 R and one 900 D to 100 R. Statewide the Democrats take 2,100 of 4,000
votes (52.5%) and one seat of four. Every expected value in this file that
mentions PACKED is derived in the test that asserts it.

``SYMMETRIC`` — four districts of 1,000 votes each, shares 0.4, 0.4, 0.6, 0.6.
A plan that treats the two parties alike, so every asymmetry metric must be
exactly zero.

The transposition tests (swap the two parties' vote columns and nothing else)
are the ones that catch a wrong denominator or a transposed party, because a
sign error survives a single-plan expected-value test surprisingly often.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from evaluate.elections import load_elections, two_party
from evaluate.plan import load_plan
from evaluate.partisan import (
    DEFAULT_SWINGS,
    FAVOURS,
    METRICS,
    TRUSTED_WHERE_ONE_PARTY_PREDOMINATES,
    all_metrics,
    caveats,
    declination,
    district_shares,
    district_votes,
    efficiency_gap,
    mean_median,
    partisan_bias,
    seat_count,
    seat_counts,
    seats_votes_curve,
    statewide_dem_share,
    wasted_votes,
)

REPO = Path(__file__).resolve().parents[1]
PROCESSED = REPO / "data" / "processed"

# Iowa 2020, certified, two-party presidential: Biden 759,061, Trump 897,672.
IA_DEM_SHARE = 0.4582


# --------------------------------------------------------------------------- #
# hand-built plans
# --------------------------------------------------------------------------- #

def _toy(district_totals):
    """Build (plan, dem, rep) from ``[(dem, rep), ...]``, one district per pair.

    Each district is split across two units so that district aggregation is
    actually exercised rather than bypassed: the first unit gets a lopsided
    share of each party's votes and the second gets the rest.
    """
    plan, dem, rep = {}, {}, {}
    for index, (d_votes, r_votes) in enumerate(district_totals, start=1):
        a, b = f"u{index}a", f"u{index}b"
        plan[a] = plan[b] = index
        dem[a], dem[b] = d_votes // 4, d_votes - d_votes // 4
        rep[a], rep[b] = r_votes - r_votes // 3, r_votes // 3
    return plan, dem, rep


#: Three districts at 400 D / 600 R and one at 900 D / 100 R.
PACKED = _toy([(400, 600), (400, 600), (400, 600), (900, 100)])

#: Shares 0.4, 0.4, 0.6, 0.6 — symmetric under swapping the two parties.
SYMMETRIC = _toy([(400, 600), (400, 600), (600, 400), (600, 400)])


def swap(case):
    """The same plan with the two parties' votes exchanged."""
    plan, dem, rep = case
    return plan, rep, dem


@pytest.fixture(scope="module")
def iowa():
    """The enacted CD118 plan with the real 2020 presidential two-party votes."""
    plan = load_plan(PROCESSED / "ia_enacted_cd118.csv")
    dem, rep = two_party(load_elections(PROCESSED / "ia_elections.csv"))
    return plan, dem, rep


# --------------------------------------------------------------------------- #
# aggregation
# --------------------------------------------------------------------------- #

def test_district_votes_aggregates_units_into_districts():
    assert district_votes(*PACKED) == {
        1: (400, 600),
        2: (400, 600),
        3: (400, 600),
        4: (900, 100),
    }


def test_district_shares_are_the_two_party_democratic_fraction():
    assert district_shares(*PACKED) == {1: 0.4, 2: 0.4, 3: 0.4, 4: 0.9}


def test_statewide_share_is_turnout_weighted_not_the_mean_of_district_shares():
    # 60/40, 400/600, 450/550: mean of the district shares is 0.48333, but the
    # share of votes actually cast is 910/2100 = 0.43333. A metric that used
    # the wrong one of these would still look plausible.
    case = _toy([(60, 40), (400, 600), (450, 550)])
    _, dem, rep = case
    assert statewide_dem_share(dem, rep) == pytest.approx(910 / 2100)
    shares = list(district_shares(*case).values())
    assert sum(shares) / len(shares) == pytest.approx(0.48333333, abs=1e-8)


def test_mismatched_or_negative_vote_dicts_raise():
    plan, dem, rep = PACKED
    short = {k: v for k, v in rep.items() if k != "u1a"}
    with pytest.raises(ValueError, match="cover different units"):
        district_votes(plan, dem, short)
    negative = dict(rep, u1a=-1)
    with pytest.raises(ValueError, match="negative"):
        district_votes(plan, dem, negative)


# --------------------------------------------------------------------------- #
# seats
# --------------------------------------------------------------------------- #

def test_seat_count_on_the_hand_built_plans():
    assert seat_count(*PACKED) == 1
    assert seat_count(*swap(PACKED)) == 3
    assert seat_count(*SYMMETRIC) == 2
    assert seat_count(*swap(SYMMETRIC)) == 2


def test_an_exact_tie_is_a_seat_for_neither_party():
    tied = _toy([(500, 500), (400, 600), (700, 300)])
    assert seat_counts(*tied) == (1, 1, 1)
    assert seat_count(*tied) == 1
    # and the tie is still a tie with the parties exchanged
    assert seat_counts(*swap(tied)) == (1, 1, 1)


# --------------------------------------------------------------------------- #
# efficiency gap
# --------------------------------------------------------------------------- #

def test_wasted_votes_by_hand():
    # Each district has 1,000 two-party votes, so the majority threshold is
    # 1000 // 2 + 1 = 501 votes.
    #   R-won district (400 D, 600 R): D wastes all 400; R wastes 600 - 501 = 99
    #   D-won district (900 D, 100 R): D wastes 900 - 501 = 399; R wastes all 100
    assert wasted_votes(*PACKED) == {
        1: (400, 99),
        2: (400, 99),
        3: (400, 99),
        4: (399, 100),
    }


def test_efficiency_gap_by_hand_and_its_sign_favours_republicans():
    # wasted D = 3*400 + 399 = 1599; wasted R = 3*99 + 100 = 397
    # (1599 - 397) / 4000 = 0.3005
    assert efficiency_gap(*PACKED) == pytest.approx(1202 / 4000)
    assert efficiency_gap(*PACKED) > 0
    assert FAVOURS["efficiency_gap"] == "R"
    # The Democrats hold 52.5% of the vote and one seat of four, so the plan
    # does favour the Republicans and the sign convention is the stated one.
    assert statewide_dem_share(PACKED[1], PACKED[2]) == pytest.approx(0.525)
    assert seat_count(*PACKED) == 1


def test_efficiency_gap_is_zero_on_a_symmetric_plan():
    # 0.4/0.4/0.6/0.6 at equal turnout: wasted D = 400+400+99+99 = 998 and
    # wasted R = 99+99+400+400 = 998, so the gap is exactly zero.
    assert efficiency_gap(*SYMMETRIC) == 0.0


def test_efficiency_gap_matches_the_closed_form_at_equal_turnout():
    # With the "half" threshold and identical turnout in every district the
    # gap reduces algebraically to 2*V_D - 0.5 - S_D. This is an independent
    # derivation, not a restatement of the implementation.
    for case in (PACKED, SYMMETRIC, swap(PACKED)):
        plan, dem, rep = case
        v = statewide_dem_share(dem, rep)
        s = seat_count(*case) / len(district_votes(*case))
        assert efficiency_gap(*case, threshold="half") == pytest.approx(
            2 * v - 0.5 - s
        )


def test_the_two_wasted_vote_thresholds_differ_by_one_vote_per_district():
    # Every district has an even vote total, so the majority threshold is one
    # vote above half. PACKED has one D-won and three R-won districts, so the
    # numerator moves by (-1) - (-3) = +2 votes out of 4,000.
    assert efficiency_gap(*PACKED) - efficiency_gap(
        *PACKED, threshold="half"
    ) == pytest.approx(2 / 4000)


def test_efficiency_gap_rejects_an_unknown_threshold():
    with pytest.raises(ValueError, match="majority"):
        efficiency_gap(*PACKED, threshold="plurality")


def test_efficiency_gap_needs_votes():
    empty = _toy([(0, 0), (0, 0)])
    with pytest.raises(ValueError, match="denominator"):
        efficiency_gap(*empty)


# --------------------------------------------------------------------------- #
# mean-median
# --------------------------------------------------------------------------- #

def test_mean_median_by_hand_and_its_sign_favours_republicans():
    # shares 0.4, 0.4, 0.4, 0.9: mean 0.525, median (0.4 + 0.4)/2 = 0.4
    assert mean_median(*PACKED) == pytest.approx(0.525 - 0.4)
    assert FAVOURS["mean_median"] == "R"


def test_mean_median_is_zero_on_a_symmetric_plan():
    assert mean_median(*SYMMETRIC) == pytest.approx(0.0, abs=1e-15)


def test_mean_median_uses_the_median_not_the_middle_district_by_index():
    # Districts arrive in an order unrelated to their vote share. The true
    # median share is 0.5 and the mean is 0.5, so the metric is zero; an
    # implementation that took the middle district *as listed* would find 0.4
    # and report 0.1.
    case = _toy([(100, 900), (900, 100), (400, 600), (600, 400), (500, 500)])
    listed = list(district_shares(*case).values())
    assert listed == [0.1, 0.9, 0.4, 0.6, 0.5]
    assert listed[len(listed) // 2] == 0.4  # what the wrong answer would use
    assert mean_median(*case) == pytest.approx(0.0, abs=1e-15)


def test_mean_median_needs_a_defined_share_in_every_district():
    case = _toy([(400, 600), (0, 0)])
    with pytest.raises(ValueError, match="no two-party votes"):
        mean_median(*case)
    with pytest.raises(ValueError, match="undefined"):
        district_shares(*case)


# --------------------------------------------------------------------------- #
# declination
# --------------------------------------------------------------------------- #

def test_declination_matches_an_independent_geometric_construction():
    # Rebuild Warrington's two angles from explicit points rather than from the
    # implementation's algebraic shortcut. With n = 4 districts of which k = 3
    # are Republican-won, the centre of the losing group sits at x = k/(2n),
    # the crossing point at x = k/n, and the centre of the winning group at
    # x = k/n + (n-k)/(2n).
    n, k = 4, 3
    mean_losing, mean_winning = 0.4, 0.9
    theta = math.atan2(0.5 - mean_losing, k / n - k / (2 * n))
    gamma = math.atan2(mean_winning - 0.5, (n - k) / (2 * n))
    expected = 2.0 * (gamma - theta) / math.pi

    assert declination(*PACKED) == pytest.approx(expected)
    assert round(expected, 4) == 0.6413
    assert declination(*PACKED) > 0
    assert FAVOURS["declination"] == "R"


def test_declination_is_zero_on_a_symmetric_plan():
    assert declination(*SYMMETRIC) == pytest.approx(0.0, abs=1e-15)


def test_declination_is_none_when_one_party_wins_every_seat():
    # CRITERIA.md section 5.1: undefined, so None rather than a number.
    d_sweep = _toy([(600, 400), (700, 300), (800, 200), (900, 100)])
    assert declination(*d_sweep) is None
    assert declination(*swap(d_sweep)) is None
    assert all_metrics(*d_sweep)["declination"] is None


def test_declination_is_none_when_a_district_is_exactly_tied():
    # A tied district belongs to neither group. Assigning it to one (as
    # implementations testing `share <= 0.5` do) would make the metric depend
    # on which party is listed first.
    tied = _toy([(500, 500), (400, 600), (700, 300)])
    assert declination(*tied) is None
    assert declination(*swap(tied)) is None


def test_declination_is_defined_with_one_district_on_each_side():
    two = _toy([(400, 600), (700, 300)])
    value = declination(*two)
    assert value is not None
    assert value == pytest.approx(-declination(*swap(two)))


# --------------------------------------------------------------------------- #
# partisan bias and the seats-votes curve
# --------------------------------------------------------------------------- #

def test_partisan_bias_by_hand_and_its_sign_favours_democrats():
    # Observed statewide D share 0.525, so the uniform swing to a tied
    # election is -0.025. Shares become 0.375, 0.375, 0.375, 0.875: the
    # Democrats win one seat of four, a seat share of 0.25.
    assert partisan_bias(*PACKED) == pytest.approx(0.25 - 0.5)
    assert partisan_bias(*PACKED) < 0
    assert FAVOURS["partisan_bias"] == "D"
    # The opposite orientation to the other three is deliberate and recorded.
    assert {m: FAVOURS[m] for m in METRICS} == {
        "efficiency_gap": "R",
        "mean_median": "R",
        "declination": "R",
        "partisan_bias": "D",
    }


def test_partisan_bias_is_zero_on_a_symmetric_plan():
    assert partisan_bias(*SYMMETRIC) == 0.0


def test_partisan_bias_swings_on_the_turnout_weighted_share():
    # 60/40, 400/600, 450/550. Statewide D share 910/2100 = 0.43333, so the
    # swing to 50-50 is +0.06667 and the shifted shares are 0.66667, 0.46667,
    # 0.51667 -> two seats of three -> bias +1/6.
    # Swinging on the unweighted mean of district shares (0.48333) instead
    # would give +0.01667, shares 0.61667, 0.41667, 0.46667, one seat of
    # three, and a bias of -1/6: same magnitude, opposite sign.
    case = _toy([(60, 40), (400, 600), (450, 550)])
    assert partisan_bias(*case) == pytest.approx(2 / 3 - 0.5)


def test_partisan_bias_equals_the_seats_votes_curve_at_fifty_fifty():
    for case in (PACKED, SYMMETRIC, swap(PACKED)):
        (_, seat_share), = seats_votes_curve(*case, swings=[0.5])
        assert partisan_bias(*case) == pytest.approx(seat_share - 0.5)


def test_seats_votes_curve_is_monotone_and_reaches_both_ends():
    curve = seats_votes_curve(*PACKED, swings=[i / 20 for i in range(21)])
    votes = [v for v, _ in curve]
    seats = [s for _, s in curve]
    assert votes == [i / 20 for i in range(21)]
    assert seats == sorted(seats)
    assert seats[0] == 0.0
    assert seats[-1] == 1.0


def test_seats_votes_curve_is_antisymmetric_under_swapping_the_parties():
    # This is the definition of partisan symmetry: the seat share the
    # Democrats get with v of the vote must equal the seat share the
    # Republicans get with v of the vote, i.e. 1 - curve(1 - v).
    grid = [i / 40 for i in range(1, 40)]
    mirrored = [(40 - i) / 40 for i in range(1, 40)]
    ours = seats_votes_curve(*PACKED, swings=grid)
    theirs = seats_votes_curve(*swap(PACKED), swings=mirrored)
    for (v, seats), (mirror_v, mirror_seats) in zip(ours, theirs):
        assert v + mirror_v == pytest.approx(1.0)
        assert seats == pytest.approx(1.0 - mirror_seats)


def test_a_symmetric_plan_has_a_symmetric_seats_votes_curve():
    grid = [i / 40 for i in range(1, 40)]
    mirrored = [(40 - i) / 40 for i in range(1, 40)]
    curve = seats_votes_curve(*SYMMETRIC, swings=grid)
    mirror = seats_votes_curve(*SYMMETRIC, swings=mirrored)
    for (_, seats), (_, mirror_seats) in zip(curve, mirror):
        assert seats == pytest.approx(1.0 - mirror_seats)


def test_default_swings_bracket_the_plausible_range_and_contain_a_tie():
    assert DEFAULT_SWINGS[0] == 0.30
    assert DEFAULT_SWINGS[-1] == 0.70
    assert 0.5 in DEFAULT_SWINGS  # exactly, not approximately
    assert len(seats_votes_curve(*PACKED)) == len(DEFAULT_SWINGS)


def test_seats_votes_curve_rejects_vote_shares_outside_zero_one():
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        seats_votes_curve(*PACKED, swings=[0.4, 1.4])
    with pytest.raises(ValueError, match="empty"):
        seats_votes_curve(*PACKED, swings=[])
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        partisan_bias(*PACKED, at=-0.1)


# --------------------------------------------------------------------------- #
# transposition — the test that catches a swapped party
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("case", [PACKED, SYMMETRIC], ids=["packed", "symmetric"])
def test_swapping_the_parties_flips_every_asymmetry_metric(case):
    original = all_metrics(*case)
    swapped = all_metrics(*swap(case))

    for metric in METRICS:
        a, b = original[metric], swapped[metric]
        if a is None or b is None:
            assert a is None and b is None, metric
            continue
        assert b == pytest.approx(-a, abs=1e-12), metric
        assert abs(b) == pytest.approx(abs(a), abs=1e-12), metric

    n = original["n_districts"]
    assert swapped["dem_seats"] == n - original["dem_seats"]
    assert swapped["dem_vote_share"] == pytest.approx(
        1 - original["dem_vote_share"]
    )


def test_swapping_the_parties_flips_every_metric_on_iowa(iowa):
    original = all_metrics(*iowa)
    swapped = all_metrics(*swap(iowa))
    for metric in METRICS:
        a, b = original[metric], swapped[metric]
        if a is None or b is None:
            # Republicans win all four Iowa seats, so declination is undefined
            # in both directions.
            assert a is None and b is None, metric
            continue
        assert b == pytest.approx(-a), metric
    assert swapped["dem_seats"] == 4 and original["dem_seats"] == 0


# --------------------------------------------------------------------------- #
# all_metrics: side by side, and combined into nothing
# --------------------------------------------------------------------------- #

def test_all_metrics_reports_every_metric_and_no_summary():
    out = all_metrics(*PACKED)
    assert set(out) == {
        "n_districts",
        "dem_seats",
        "rep_seats",
        "tied_districts",
        "dem_seat_share",
        "dem_vote_share",
        "efficiency_gap",
        "mean_median",
        "declination",
        "partisan_bias",
    }
    # prompt.md and CRITERIA.md section 5.2: no key may collapse these to one
    # number. Every metric here is provably gameable in isolation.
    forbidden = ("score", "fairness", "index", "composite", "overall", "rating")
    assert not [k for k in out if any(word in k.lower() for word in forbidden)]


def test_all_metrics_agrees_with_the_individual_functions():
    out = all_metrics(*PACKED)
    assert out["efficiency_gap"] == efficiency_gap(*PACKED)
    assert out["mean_median"] == mean_median(*PACKED)
    assert out["declination"] == declination(*PACKED)
    assert out["partisan_bias"] == partisan_bias(*PACKED)
    assert out["dem_seats"] == seat_count(*PACKED)


def test_the_metrics_can_disagree_about_which_party_a_plan_favours():
    # Not a pathology to be fixed: CRITERIA.md section 5 is titled "five
    # metrics that disagree" in spirit, and this is the disagreement. Three
    # districts just below 0.5 and one far below it give a large efficiency
    # gap against the Democrats while partisan bias, which swings the whole
    # map to a tie, says the opposite.
    case = _toy([(490, 510), (485, 515), (480, 520), (300, 700)])
    out = all_metrics(*case)
    assert out["efficiency_gap"] > 0  # positive: favours R
    assert out["partisan_bias"] > 0  # positive: favours D
    assert FAVOURS["efficiency_gap"] != FAVOURS["partisan_bias"]


# --------------------------------------------------------------------------- #
# regime caveats
# --------------------------------------------------------------------------- #

def test_caveats_are_silent_on_a_competitive_symmetric_plan_with_enough_seats():
    case = _toy([(400, 600), (450, 550), (480, 520), (520, 480), (550, 450),
                 (600, 400), (470, 530), (530, 470)])
    assert caveats(*case) == []


def test_caveats_name_the_one_party_predominates_regime():
    lopsided = _toy([(200, 800), (250, 750), (300, 700), (350, 650)])
    notes = " ".join(caveats(*lopsided))
    assert "One party predominates" in notes
    for trusted in TRUSTED_WHERE_ONE_PARTY_PREDOMINATES:
        assert trusted in notes
    assert "mean_median" in notes  # named as the one to distrust
    assert "declination is undefined" in notes  # Republicans win every seat


def test_caveats_flag_a_small_number_of_districts(iowa):
    notes = caveats(*iowa)
    assert any("Only 4 districts" in n for n in notes)


# --------------------------------------------------------------------------- #
# Iowa, enacted plan, real 2020 presidential votes
# --------------------------------------------------------------------------- #

def test_iowa_enacted_plan_two_party_share_and_seats(iowa):
    out = all_metrics(*iowa)
    assert out["n_districts"] == 4
    assert round(out["dem_vote_share"], 4) == IA_DEM_SHARE
    # Republicans carried all four districts on 2020 presidential votes.
    assert out["dem_seats"] == 0
    assert out["rep_seats"] == 4
    assert out["tied_districts"] == 0


def test_iowa_enacted_plan_efficiency_gap_from_the_district_totals(iowa):
    # Recomputed here from the four district totals by hand, independently of
    # the aggregation path: the Republicans win every district, so every
    # Democratic vote is wasted, and the Republicans waste what they hold above
    # the majority threshold in each district.
    totals = district_votes(*iowa)
    assert totals == {
        1: (203400, 215742),
        2: (203246, 222312),
        3: (205591, 207043),
        4: (146824, 252575),
    }
    wasted_d = sum(d for d, _ in totals.values())
    wasted_r = sum(r - ((d + r) // 2 + 1) for d, r in totals.values())
    cast = sum(d + r for d, r in totals.values())
    assert wasted_d == 759_061  # every Democratic vote in the state
    assert cast == 759_061 + 897_672
    assert efficiency_gap(*iowa) == pytest.approx((wasted_d - wasted_r) / cast)
    assert efficiency_gap(*iowa) == pytest.approx(0.41634, abs=5e-6)


def test_iowa_enacted_plan_declination_is_undefined(iowa):
    # Republicans win all four seats. CRITERIA.md section 5.1.
    assert declination(*iowa) is None


def test_iowa_enacted_plan_metrics_disagree_in_direction(iowa):
    # The headline finding for this plan, and the reason nothing here is
    # combined: the efficiency gap says a large Republican advantage (the
    # Democrats took 45.8% of the vote and no seats, so all of it is wasted),
    # while partisan bias says the opposite, because three of the four
    # districts are within 2.5 points of a tie and flip on a uniform swing to
    # 50-50.
    out = all_metrics(*iowa)
    assert out["efficiency_gap"] > 0.4  # favours R
    assert out["partisan_bias"] == 0.25  # favours D: 3 of 4 seats at 50-50
    assert out["mean_median"] < 0  # favours D, weakly
    assert out["declination"] is None


def test_iowa_seats_votes_curve_crosses_where_the_close_districts_flip(iowa):
    curve = dict(seats_votes_curve(*iowa))
    assert curve[0.30] == 0.0
    assert curve[0.45] == 0.0
    assert curve[0.50] == 0.75
    assert curve[0.70] == 1.0
    seats = [s for _, s in seats_votes_curve(*iowa)]
    assert seats == sorted(seats)
