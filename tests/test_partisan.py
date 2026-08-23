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
exactly zero — at *every* hypothetical vote share, not only at 50-50, which is
what the partisan-bias tests below turn on.

``TIED`` — three districts, shares 0.5, 0.4, 0.7. The only regime in which the
module's two seat-share conventions can disagree about the observed election.

``COMPETITIVE_EIGHT`` — eight districts, statewide exactly 50-50, four seats
each, median share 0.5. The case where no reliability caveat fires at all.

The transposition tests (swap the two parties' vote columns and nothing else)
are the ones that catch a wrong denominator or a transposed party, because a
sign error survives a single-plan expected-value test surprisingly often.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from dataguard import require

from evaluate.elections import load_elections, two_party
from evaluate.plan import load_plan
from evaluate.partisan import (
    DEFAULT_SWINGS,
    FAVOURS,
    METRICS,
    MINORITY_DISTRICT_SHARE,
    PREDOMINANCE_BAND,
    SEAT_TIE_RULES,
    TRUSTED_WHERE_ONE_PARTY_PREDOMINATES,
    all_metrics,
    caveats,
    declination,
    district_shares,
    district_votes,
    efficiency_gap,
    mean_median,
    partisan_bias,
    one_party_predominates,
    seat_count,
    seat_counts,
    seats_votes_curve,
    statewide_dem_share,
    trusted_metrics,
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

#: Three districts, one of them exactly tied: shares 0.5, 0.4, 0.7. The only
#: regime in which the module's two seat-share conventions disagree.
TIED = _toy([(500, 500), (400, 600), (700, 300)])

#: Eight districts, statewide exactly 50-50, four seats each, median share 0.5.
#: No arm of the predominance test fires and every metric survives.
COMPETITIVE_EIGHT = _toy(
    [(400, 600), (450, 550), (480, 520), (520, 480), (550, 450),
     (600, 400), (470, 530), (530, 470)]
)


def swap(case):
    """The same plan with the two parties' votes exchanged."""
    plan, dem, rep = case
    return plan, rep, dem


@pytest.fixture(scope="module")
def iowa():
    """The enacted CD118 plan with the real 2020 presidential two-party votes."""
    require("ia_enacted_cd118.csv", "ia_elections.csv")
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


# --------------------------------------------------------------------------- #
# the predominance regime — the gate that has to fire on Iowa
# --------------------------------------------------------------------------- #

def test_the_statewide_margin_alone_does_not_fire_on_iowa(iowa):
    # The finding that forced the rewrite, stated as an assertion. Iowa 2020 is
    # 0.041833 from a tied statewide vote, INSIDE the +/-0.05 band, so a
    # predominance test keyed to the margin alone calls it competitive.
    share = statewide_dem_share(iowa[1], iowa[2])
    assert share == pytest.approx(0.4581673691536295)
    assert abs(share - 0.5) == pytest.approx(0.0418326308, abs=1e-9)
    assert abs(share - 0.5) < PREDOMINANCE_BAND
    reasons = one_party_predominates(*iowa)
    assert not [r for r in reasons if r.startswith("statewide margin")]
    # ... and yet the Republicans hold four seats of four on 45.8% of the vote,
    # which is the regime CRITERIA.md section 5.1 says to distrust.
    assert reasons, "Iowa 2020 must be in the one-party-predominates regime"
    assert any(r.startswith("district sweep") for r in reasons)
    assert seat_counts(*iowa) == (0, 4, 0)


def test_iowa_mean_median_is_reported_untrusted_not_bare(iowa):
    # -0.024256 has a sign that reads as a DEMOCRATIC advantage on a plan where
    # the Republicans won every seat. The number is not wrong arithmetic; it is
    # the interpretation that fails, so the module must say so.
    out = all_metrics(*iowa)
    assert out["mean_median"] == pytest.approx(-0.024256, abs=5e-7)
    assert out["mean_median"] < 0  # i.e. reads as favouring D
    assert FAVOURS["mean_median"] == "R"
    assert "mean_median" not in trusted_metrics(*iowa)
    notes = " ".join(caveats(*iowa))
    assert "One party predominates" in notes
    assert "district sweep" in notes
    assert "treat mean_median, partisan_bias as unreliable here" in notes


def test_iowa_trusted_set_collapses_to_the_efficiency_gap_alone(iowa):
    # Predominance leaves {efficiency_gap, declination} per CRITERIA.md 5.1,
    # and declination is undefined here because one party won every seat, so
    # one metric of four survives. That is the honest size of the claim.
    assert trusted_metrics(*iowa) == ("efficiency_gap",)
    assert declination(*iowa) is None


def test_caveats_say_positively_what_remains_usable(iowa):
    # A list of what is broken is not the same statement as a list of what is
    # usable; a reader given only the first assumes the rest are fine.
    positive = [n for n in caveats(*iowa) if n.startswith("Still usable")]
    assert len(positive) == 1
    note = positive[0]
    assert "efficiency_gap (1 of 4)" in note
    assert "Do not report mean_median, declination, partisan_bias" in note
    assert "still gameable" in note  # surviving the regime test is not a verdict


@pytest.mark.parametrize(
    "case, arm",
    [
        # Statewide margin only: shares 0.30/0.48/0.52/0.56 with the first
        # district carrying 100x the turnout, so the state is 0.3064 overall
        # while the districts split 2-2 and their median is exactly 0.5.
        (_toy([(30000, 70000), (480, 520), (520, 480), (560, 440)]),
         "statewide margin"),
        # District sweep only: an Iowa-shaped case. Statewide 0.4823 and median
        # 0.4815 are both inside the band; all four districts are below 0.5.
        (_toy([(485, 515), (478, 522), (498, 502), (468, 532)]),
         "district sweep"),
        # Median district only: five districts split 3-2, statewide 0.5040,
        # but the median district sits at 0.44 and decides nothing.
        (_toy([(200, 800), (420, 580), (440, 560), (560, 440), (900, 100)]),
         "median district"),
    ],
    ids=["statewide-margin", "district-sweep", "median-district"],
)
def test_each_arm_of_the_predominance_test_fires_on_its_own(case, arm):
    reasons = one_party_predominates(*case)
    assert [r.split(" — ")[0] for r in reasons] == [arm]


def test_no_arm_fires_on_a_competitive_plan():
    assert one_party_predominates(*COMPETITIVE_EIGHT) == []
    assert one_party_predominates(*SYMMETRIC) == []
    assert one_party_predominates(*swap(SYMMETRIC)) == []
    assert caveats(*COMPETITIVE_EIGHT) == []


def test_the_predominance_test_is_symmetric_between_the_parties():
    # Whichever party sweeps, the regime is the same regime.
    for case in (PACKED, COMPETITIVE_EIGHT, SYMMETRIC):
        assert bool(one_party_predominates(*case)) == bool(
            one_party_predominates(*swap(case))
        )
        assert trusted_metrics(*case) == trusted_metrics(*swap(case))


def test_the_predominance_thresholds_are_arguable_parameters():
    # Both bands are VALUE choices, so both must move the answer. PACKED fires
    # two arms at the defaults (sweep: one district of four above 0.5; median:
    # 0.4). Narrowing the sweep threshold below one district in four and
    # widening the band past 0.1 silences both, and the plan is then called
    # competitive — which is the point: the judgement is visible and arguable,
    # not buried in the metric.
    assert [r.split(" — ")[0] for r in one_party_predominates(*PACKED)] == [
        "district sweep",
        "median district",
    ]
    assert one_party_predominates(*PACKED, minority_district_share=0.2) == [
        r for r in one_party_predominates(*PACKED) if r.startswith("median")
    ]
    assert one_party_predominates(
        *PACKED, minority_district_share=0.2, predominance_band=0.15
    ) == []
    assert MINORITY_DISTRICT_SHARE == 0.25 and PREDOMINANCE_BAND == 0.05


def test_no_setting_of_the_statewide_band_alone_silences_iowa(iowa):
    # The gate must not be recoverable by tuning the margin: with the band at
    # its widest the statewide arm can never fire, and Iowa is still flagged,
    # because it is flagged on the seats and shares rather than on the margin.
    assert one_party_predominates(*iowa, predominance_band=0.5)
    assert trusted_metrics(*iowa, predominance_band=0.5) == ("efficiency_gap",)
    # Narrowing it below 0.041833 brings the statewide arm in as well.
    reasons = one_party_predominates(*iowa, predominance_band=0.04)
    assert [r.split(" — ")[0] for r in reasons] == [
        "statewide margin",
        "district sweep",
    ]


# --------------------------------------------------------------------------- #
# which metrics survive the regime
# --------------------------------------------------------------------------- #

def test_trusted_metrics_is_all_four_only_on_a_competitive_plan_with_enough_districts():
    assert trusted_metrics(*COMPETITIVE_EIGHT) == METRICS


def test_trusted_metrics_drops_declination_where_it_is_undefined():
    # Eight districts, statewide 0.5025, median 0.51, split 4-3 with one tie:
    # no arm of the predominance test fires, but a tied district makes
    # declination None, and an undefined metric is not a trusted one.
    tied_eight = _toy([(400, 600), (450, 550), (470, 530), (500, 500),
                       (530, 470), (550, 450), (600, 400), (520, 480)])
    assert one_party_predominates(*tied_eight) == []
    assert declination(*tied_eight) is None
    assert trusted_metrics(*tied_eight) == (
        "efficiency_gap",
        "mean_median",
        "partisan_bias",
    )


def test_trusted_metrics_drops_declination_on_a_four_district_state():
    # SYMMETRIC is competitive and declination is defined (0.0), but four
    # districts put each of its two fitted lines on two points.
    assert one_party_predominates(*SYMMETRIC) == []
    assert declination(*SYMMETRIC) == pytest.approx(0.0, abs=1e-15)
    assert trusted_metrics(*SYMMETRIC) == (
        "efficiency_gap",
        "mean_median",
        "partisan_bias",
    )
    # ... and it is a parameter, so the judgement can be overturned.
    assert trusted_metrics(*SYMMETRIC, min_districts_for_declination=4) == METRICS


def test_trusted_metrics_returns_names_and_cannot_be_reduced_to_a_number():
    # prompt.md: no function collapses fairness to one number. This one returns
    # a subset of the metric NAMES in METRICS order and no values at all.
    for case in (PACKED, SYMMETRIC, COMPETITIVE_EIGHT, TIED):
        usable = trusted_metrics(*case)
        assert all(isinstance(m, str) for m in usable)
        assert set(usable) <= set(METRICS)
        assert list(usable) == [m for m in METRICS if m in usable]
        assert "efficiency_gap" in usable  # never disqualified by the regime


# --------------------------------------------------------------------------- #
# partisan bias away from 50-50 — an asymmetry, not a level
# --------------------------------------------------------------------------- #

def test_partisan_bias_is_zero_at_every_at_on_a_plan_symmetric_by_construction():
    # SYMMETRIC has shares 0.4, 0.4, 0.6, 0.6: whatever the Democrats get with
    # v of the vote, the Republicans get with v of the vote. Its asymmetry is
    # zero at EVERY hypothetical vote share, not only at 50-50.
    for at in (0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7):
        assert partisan_bias(*SYMMETRIC, at=at) == pytest.approx(0.0, abs=1e-15)


def test_the_democratic_seat_share_at_a_vote_share_is_not_the_asymmetry():
    # The defect this replaced: `S_D(at) - 0.5` returned +0.25 at at=0.6 and
    # -0.25 at at=0.4 for the symmetric plan above, reporting a quarter-seat
    # bias for a plan with none. It was measuring the level of Democratic seats,
    # which mixes the plan's asymmetry with the ordinary fact that a party with
    # 60% of the vote wins more than half the seats under any districting.
    (_, seats_at_60), = seats_votes_curve(*SYMMETRIC, swings=[0.6])
    (_, seats_at_40), = seats_votes_curve(*SYMMETRIC, swings=[0.4])
    assert seats_at_60 - 0.5 == pytest.approx(0.25)   # the old return value
    assert seats_at_40 - 0.5 == pytest.approx(-0.25)  # and its mirror
    assert partisan_bias(*SYMMETRIC, at=0.6) == pytest.approx(0.0, abs=1e-15)
    assert partisan_bias(*SYMMETRIC, at=0.4) == pytest.approx(0.0, abs=1e-15)


def test_partisan_bias_is_the_two_party_difference_at_the_same_vote_share():
    # bias(v) = (S_D(v) - S_R(v)) / 2 with S_R(v) = 1 - S_D(1 - v), recomputed
    # here from the seats-votes curve rather than from the implementation.
    for case in (PACKED, SYMMETRIC, TIED, swap(PACKED)):
        for at in (0.35, 0.45, 0.5, 0.55, 0.65):
            (_, s_dem), = seats_votes_curve(*case, swings=[at])
            (_, s_mirror), = seats_votes_curve(*case, swings=[1 - at])
            expected = (s_dem - (1 - s_mirror)) / 2
            assert partisan_bias(*case, at=at) == pytest.approx(expected)


def test_partisan_bias_reads_the_same_whichever_party_holds_the_larger_share():
    # bias(v) == bias(1 - v): the asymmetry at 60-40 is one number, and which
    # party is named as holding the 60 is not part of it.
    for case in (PACKED, SYMMETRIC, TIED):
        for at in (0.3, 0.42, 0.5):
            assert partisan_bias(*case, at=at) == pytest.approx(
                partisan_bias(*case, at=1 - at)
            )


def test_partisan_bias_is_antisymmetric_under_swapping_the_parties_at_any_at():
    for at in (0.3, 0.45, 0.5, 0.55, 0.7):
        assert partisan_bias(*swap(PACKED), at=at) == pytest.approx(
            -partisan_bias(*PACKED, at=at), abs=1e-12
        )


def test_no_published_partisan_bias_number_moved(iowa):
    # The default at=0.5 reduces to S_D(0.5) - 0.5 exactly, so the generalised
    # formula changes nothing this module has ever reported. Pinned.
    assert partisan_bias(*PACKED) == -0.25
    assert partisan_bias(*SYMMETRIC) == 0.0
    assert partisan_bias(*iowa) == 0.25
    assert all_metrics(*iowa)["partisan_bias"] == 0.25


def test_iowa_partisan_bias_away_from_fifty_fifty(iowa):
    # At 60-40 the Iowa map gives whichever party holds the 60 all four seats,
    # so its asymmetry there is zero — a fact the old `S_D(0.6) - 0.5` hid
    # behind a +0.5, the largest bias the metric can express.
    (_, s_dem_at_60), = seats_votes_curve(*iowa, swings=[0.6])
    assert s_dem_at_60 == 1.0
    assert partisan_bias(*iowa, at=0.6) == 0.0
    assert partisan_bias(*iowa, at=0.4) == 0.0


# --------------------------------------------------------------------------- #
# the two seat-share conventions, named rather than silent
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "case",
    [PACKED, SYMMETRIC, TIED, COMPETITIVE_EIGHT, swap(PACKED)],
    ids=["packed", "symmetric", "tied", "eight", "swapped"],
)
def test_the_curve_at_the_observed_share_equals_the_reported_seat_share(case):
    # The identity swing, delta = 0, under the observed-election tie rule.
    out = all_metrics(*case)
    (v, seat_share), = seats_votes_curve(
        *case, swings=[out["dem_vote_share"]], tie="neither"
    )
    assert v == out["dem_vote_share"]
    assert seat_share == out["dem_seat_share"]


def test_the_curve_at_the_observed_share_equals_the_reported_seat_share_on_iowa(iowa):
    out = all_metrics(*iowa)
    (_, seat_share), = seats_votes_curve(
        *iowa, swings=[out["dem_vote_share"]], tie="neither"
    )
    assert seat_share == out["dem_seat_share"] == 0.0
    # Iowa has no tied district, so the default rule agrees to the last bit and
    # nothing published from the real data depends on the choice.
    (_, default_rule), = seats_votes_curve(*iowa, swings=[out["dem_vote_share"]])
    assert default_rule == seat_share


def test_the_two_tie_conventions_differ_only_on_a_tied_district():
    # TIED: shares 0.5, 0.4, 0.7. The observed seat share is 1/3 (the tie is a
    # seat for nobody); the counterfactual rule splits it, giving 1/2. The gap
    # is exactly tied / (2n), and caveats() announces it.
    out = all_metrics(*TIED)
    observed = out["dem_vote_share"]
    (_, neither), = seats_votes_curve(*TIED, swings=[observed], tie="neither")
    (_, half), = seats_votes_curve(*TIED, swings=[observed], tie="half")
    assert out["tied_districts"] == 1
    assert neither == pytest.approx(1 / 3)
    assert half == pytest.approx(1 / 2)
    assert half - neither == pytest.approx(1 / (2 * out["n_districts"]))
    assert "seat-share conventions can disagree" in " ".join(caveats(*TIED))

    # ... and on a plan with no tied district the two rules agree about the
    # election that happened. They still differ away from it, wherever a swing
    # puts a district exactly on 0.5 — PACKED's 0.9 district does that at
    # v = 0.125 — which is a property of the counterfactual, not a
    # disagreement about the observed result.
    observed_packed = all_metrics(*PACKED)["dem_vote_share"]
    (_, packed_neither), = seats_votes_curve(
        *PACKED, swings=[observed_packed], tie="neither"
    )
    (_, packed_half), = seats_votes_curve(*PACKED, swings=[observed_packed])
    assert packed_neither == packed_half == 0.25
    assert all_metrics(*PACKED)["tied_districts"] == 0
    (_, edge_neither), = seats_votes_curve(*PACKED, swings=[0.125], tie="neither")
    (_, edge_half), = seats_votes_curve(*PACKED, swings=[0.125], tie="half")
    assert edge_neither == 0.0 and edge_half == 0.125


def test_only_the_half_rule_keeps_the_curve_antisymmetric():
    # Why "half" is the default for the counterfactual: SYMMETRIC lands two
    # districts exactly on 0.5 at v = 0.6, and the observed-election rule
    # awards them to nobody, so curve(0.6) != 1 - curve(0.4) and the property
    # partisan bias is defined from fails.
    (_, up_half), = seats_votes_curve(*SYMMETRIC, swings=[0.6], tie="half")
    (_, down_half), = seats_votes_curve(*SYMMETRIC, swings=[0.4], tie="half")
    assert up_half == pytest.approx(1 - down_half)
    (_, up_neither), = seats_votes_curve(*SYMMETRIC, swings=[0.6], tie="neither")
    (_, down_neither), = seats_votes_curve(*SYMMETRIC, swings=[0.4], tie="neither")
    assert up_neither == pytest.approx(0.5)
    assert down_neither == pytest.approx(0.0)
    assert up_neither != pytest.approx(1 - down_neither)


def test_an_unknown_tie_rule_is_rejected():
    assert SEAT_TIE_RULES == ("neither", "half")
    with pytest.raises(ValueError, match="tie must be one of"):
        seats_votes_curve(*PACKED, swings=[0.5], tie="coin-flip")


# --------------------------------------------------------------------------- #
# exact ties: the sweep arm must not fire on a plan where nothing sweeps
# --------------------------------------------------------------------------- #

#: Eight districts at shares 0.40, 0.45, 0.50, 0.50, 0.50, 0.50, 0.55, 0.60,
#: statewide exactly 4,000 of 8,000. Two districts below 0.5, two above, four
#: exactly on it. Nothing sweeps by any reading, and src/adversarial builds
#: plans of this shape on purpose.
BALANCED_WITH_TIES = _toy(
    [(400, 600), (450, 550), (500, 500), (500, 500),
     (500, 500), (500, 500), (550, 450), (600, 400)]
)


def test_exact_ties_do_not_manufacture_a_sweep():
    """The bug: ties were counted out of *both* tallies, deflating both.

    ``below`` and ``above`` were each 2 of 8, so ``min(below, above) = 2`` met
    the ``0.25 * 8 = 2`` threshold and the arm fired — on a plan that is 2-2-4,
    statewide 50-50, with a median of exactly 0.5. A district a party has not
    won is not a district it has swept, so a tie now counts in the minority.
    """
    plan, dem, rep = BALANCED_WITH_TIES
    shares = sorted(district_shares(plan, dem, rep).values())
    assert shares == [0.40, 0.45, 0.50, 0.50, 0.50, 0.50, 0.55, 0.60]
    assert statewide_dem_share(dem, rep) == pytest.approx(0.5)
    assert seat_counts(plan, dem, rep) == (2, 2, 4)
    assert one_party_predominates(plan, dem, rep) == []
    assert trusted_metrics(plan, dem, rep) == ("efficiency_gap", "mean_median",
                                               "partisan_bias")
    assert not [n for n in caveats(plan, dem, rep) if "predominates" in n]


def test_the_sweep_arm_never_reports_neither_party():
    """The other half of the same defect: the message assumed two sides.

    With ``above == below`` the old code set ``leader = "neither party"`` into a
    sentence written for a party name, and produced "2 of 8 district vote shares
    fall on the neither party side of 0.5". That branch is now unreachable —
    the arm requires a strict leader — and this asserts it stays that way.
    """
    for case in (BALANCED_WITH_TIES, SYMMETRIC, COMPETITIVE_EIGHT, TIED,
                 PACKED, swap(PACKED)):
        for reason in one_party_predominates(*case):
            assert "neither party side" not in reason
            assert "the neither" not in reason


def test_a_real_sweep_counts_its_ties_in_the_minority():
    """Seven districts Democratic, one exactly tied, none Republican.

    This *is* a sweep, so the arm must still fire — but the tied district is on
    nobody's side, so the minority share is 1/8, not 0, and the sentence has to
    say where that district went.
    """
    case = _toy([(600, 400), (610, 390), (620, 380), (630, 370),
                 (640, 360), (650, 350), (660, 340), (500, 500)])
    (sweep,) = [r for r in one_party_predominates(*case)
                if r.startswith("district sweep")]
    assert "7 of 8 district vote shares fall on the Democratic side of 0.5" in sweep
    assert "0 on the other and 1 exactly tied, on neither side" in sweep
    assert "a minority share of 0.125" in sweep
    # tightening the threshold below 1/8 silences it, which is the arm's own
    # parameter doing the work rather than the tie being quietly discarded
    assert not [r for r in one_party_predominates(*case, minority_district_share=0.1)
                if r.startswith("district sweep")]


def test_a_tie_can_be_the_difference_between_sweeping_and_not():
    """Four districts, three Republican and one tied: a 1/4 minority, not 0."""
    case = _toy([(400, 600), (420, 580), (440, 560), (500, 500)])
    reasons = [r for r in one_party_predominates(*case)
               if r.startswith("district sweep")]
    assert reasons and "a minority share of 0.25" in reasons[0]
    # the same plan with the tied district pushed to the Republican side sweeps
    # outright, and the minority share falls to 0
    outright = _toy([(400, 600), (420, 580), (440, 560), (490, 510)])
    (sweep,) = [r for r in one_party_predominates(*outright)
                if r.startswith("district sweep")]
    assert "a minority share of 0" in sweep


# --------------------------------------------------------------------------- #
# the sweep caveat: what the seats-votes curve does and does not do
# --------------------------------------------------------------------------- #

def test_iowa_sweep_caveat_gives_the_margin_instead_of_claiming_a_flat_curve(iowa):
    """The claim that was false on the repository's only real dataset.

    The caveat said "the seats-votes curve is flat through the observed
    election". Iowa's district 3 sits at 0.498241, so a uniform swing of
    0.001759 — 0.18 points — takes the Democratic seat share from 0 to 0.25.
    The curve is flat on the Republican side of the observed election and steps
    almost immediately on the other, which is the opposite of what a reader
    would take from "flat".
    """
    shares = district_shares(*iowa)
    assert shares[3] == pytest.approx(0.498241, abs=5e-7)
    assert max(shares.values()) == shares[3]

    (note,) = [n for n in caveats(*iowa) if n.startswith("One party wins every seat")]
    assert "flat through the observed election" not in note
    assert "flat on the Republican side of the observed election" in note
    assert "district 3 sits at 0.498241" in note
    assert "uniform swing of 0.001759" in note
    assert "0.18 points" in note
    assert "moves the Democratic seat share from 0 to 0.25" in note


def test_the_sweep_caveat_names_the_district_that_nearly_flipped():
    """Generic, not an Iowa constant: the note tracks the real nearest margin."""
    case = _toy([(100, 900), (200, 800), (499, 501), (300, 700)])
    (note,) = [n for n in caveats(*case) if n.startswith("One party wins every seat")]
    assert "district 3 sits at 0.499000" in note
    assert "uniform swing of 0.001000" in note
    # a plan with no near miss reports its own, much larger, margin
    safe = _toy([(100, 900), (200, 800), (250, 750), (300, 700)])
    (note,) = [n for n in caveats(*safe) if n.startswith("One party wins every seat")]
    assert "uniform swing of 0.200000" in note


def test_caveats_are_plain_prose_with_no_markup(iowa):
    """caveats() is documented as plain-language warnings, so it must be plain.

    A caveat used to end "...differ by 0.125 here (:data:`SEAT_TIE_RULES`)", and
    the positive note called the survivors "still `VALUE` class". Backticks and
    reST roles are for the docstrings, not for the reader of a warning.
    """
    cases = [iowa, PACKED, TIED, BALANCED_WITH_TIES, COMPETITIVE_EIGHT,
             swap(PACKED), swap(TIED)]
    for case in cases:
        for note in caveats(*case):
            assert "`" not in note, note
            assert ":data:" not in note and ":func:" not in note, note
            assert note.endswith(".") or note.endswith(")"), note
    # the tie note still tells the reader what the two conventions disagree by
    (tie_note,) = [n for n in caveats(*TIED) if "exactly tied" in n]
    assert tie_note.endswith("so the two differ by 0.166667 here.")
