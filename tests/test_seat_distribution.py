"""The README's first result is a pure function of committed files, and still says what it says.

`docs/figures/ia-neutral-seat-distribution.png` sits at the top of the README.
Until D-039 it was drawn from a gitignored results file, so neither the figure
nor the numbers quoted beside it could be checked by anyone who had not built the
data, and nothing in the suite pinned them. Both are now recomputed by
`tools/plot_seat_distribution.py` from committed files -- the v2 draws and
their sidecar, the v1 draws, the rectangle report and the Phase 2 report -- so
they are pinned here and run in CI. So are the numbers `docs/progress.md`
quotes about the same sample, which the script prints.

The counts below are the published ones. A failure means the draws file, the
loader's rectangle or the seat recovery changed, and the README is now wrong; it
does not mean the test needs its numbers updated. The controls further down are
the other half: each one must make the script refuse, because a guard that
cannot fail is not a guard (docs/RESEARCH-LOOP-PLAYBOOK.md section 4.2).

No data guard: every file read here is committed.
"""
from __future__ import annotations

import copy
import csv
import gzip
import hashlib
import itertools
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import plot_seat_distribution as S   # noqa: E402
from evaluate import partisan as P   # noqa: E402

#: Democratic seats -> draws on the D-035 rectangle (6 of 12 chains x 4,594
#: draws). README "First result", docs/progress.md.
PRESIDENT_2020 = {0: 395, 1: 13_516, 2: 13_653, 3: 0, 4: 0}
#: The same draws under the 2020 Senate vote: the span's upper edge moves.
SENATE_2020 = {0: 270, 1: 11_410, 2: 15_876, 3: 8, 4: 0}

#: Two-party totals for the controls: the 2020 presidential race in Iowa, and
#: Colorado's as tools/prepare_data_co.py asserts it (D-016).
IOWA_VOTES = sum(S.TWO_PARTY["G20PRE"])
TOTAL_VOTES = {"IA": IOWA_VOTES, "CO": 1_804_352 + 1_364_607}
K = 4

#: VEST's credit, as Harvard Dataverse cites version 49, and the link to the
#: licence it states, both of which the counts carry (D-044).
VEST_CREDIT = ('Voting and Election Science Team, 2020, "2020 Precinct-Level Election '
               'Results", https://doi.org/10.7910/DVN/K7760H, Harvard Dataverse, V49')
LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"


@pytest.fixture(scope="module")
def dist():
    return S.seat_distribution()


@pytest.fixture(scope="module")
def levels():
    dem, rep = S.TWO_PARTY["G20PRE"]
    return S.seat_levels(dem / (dem + rep), K)


def test_the_readme_seat_distribution_is_pinned(dist):
    assert dist["primary"]["contest"] == "G20PRE"
    assert (dist["n_chains"], dist["n_chains_requested"], dist["rectangle"],
            dist["n_draws"]) == (6, 12, 4594, 27_564)
    assert dist["chain_index"] == [0, 1, 2, 5, 6, 10]
    assert (dist["n_chains_never_started"], dist["n_chains_stopped_early"]) == (2, 4)
    assert dist["primary"]["counts"] == PRESIDENT_2020
    assert dist["enacted_dem_seats"] == 0


def test_the_numbers_quoted_beside_it_are_pinned(dist):
    # README, the figure and docs/progress.md quote each of these. A change to
    # generate.convergence or to the loader would otherwise move them silently.
    p = dist["primary"]
    for seats, (low, high) in {0: (0.0044, 0.0246), 1: (0.4040, 0.5623),
                               2: (0.4131, 0.5795)}.items():
        shares = [chain[seats] for chain in p["per_chain_shares"]]
        assert (min(shares), max(shares)) == (pytest.approx(low, abs=1e-4),
                                              pytest.approx(high, abs=1e-4))
    assert p["seat_count_split_rhat"] == pytest.approx(1.0136, abs=1e-4)
    assert p["seat_count_ess"] == pytest.approx(286.1, abs=0.5)
    assert [p["mcse"][s] for s in (0, 1, 2)] == pytest.approx([0.0038, 0.0300, 0.0305],
                                                              abs=1e-4)
    assert [p["outcome_rhat"][s] for s in (0, 1, 2)] == pytest.approx(
        [1.0031, 1.0118, 1.0134], abs=1e-4)
    # the standard error the README quotes as "3 to 4 points"
    assert list(p["batch_means_mcse"][2].values()) == pytest.approx(
        [0.0333, 0.0366, 0.0388], abs=1e-4)
    assert dist["enacted_closest_share"] == pytest.approx(0.498241)


def test_the_uncertainty_docs_progress_md_quotes_is_pinned(dist):
    p = dist["primary"]
    assert p["after_burn_in"][0] == pytest.approx(0.0115, abs=1e-4)
    assert p["after_burn_in"][2] == pytest.approx(0.5024, abs=1e-4)
    first, second = p["half_shares"]
    assert (first[2], second[2]) == (pytest.approx(0.461, abs=1e-3),
                                     pytest.approx(0.530, abs=1e-3))
    assert p["start_seats"] == [1, 2, 2, 2, 1, 2]
    # the two chains that start at 1 seat put a third of their first halves at 2
    starts_at_one = [h[0][2] for h, s in zip(p["per_chain_half_shares"],
                                             p["start_seats"]) if s == 1]
    assert starts_at_one == pytest.approx([0.337, 0.331], abs=1e-3)
    # what a 7-chain, 260-draw estimate -- v0.1.0's -- carries, three ways
    se = p["short_run_se"][2]
    assert (se["starts"], se["windows"], se["asymptotic"]) == pytest.approx(
        (0.0888, 0.1077, 0.1188), abs=1e-4)
    assert (se["n_starts"], se["n_windows"]) == (8, 218)
    shares = {key: round(v, 3) for key, v in dist["two_seat_share_by_rectangle"].items()}
    assert shares == {(4, 8133): 0.453, (5, 6495): 0.480, (6, 4594): 0.495,
                      (7, 4282): 0.505, (8, 1863): 0.503}
    everything = [s for seats in p["all_seats"] for s in seats]
    assert {s: everything.count(s) for s in range(K + 1)} == {
        0: 832, 1: 28_780, 2: 27_941, 3: 0, 4: 0}
    # distinct plans by the recount's plan keys (D-043): rows of metrics
    # overcount them, since a renumbered plan can leave two
    assert dist["repeats"] == 20_060
    assert (dist["distinct_plans"], dist["distinct_plans_committed"]) == (3_361, 5_588)
    assert dist["earlier_prefix"] == {i: (1500, 1500) for i in (0, 1, 2, 5, 6, 10)}


def test_a_row_that_differs_from_v1_is_counted():
    rows = [{"x": 1.0}, {"x": 2.0}, {"x": 3.0}]
    assert S.prefix_match(rows, rows[:2]) == (2, 2)
    assert S.prefix_match(rows, [{"x": 1.0}, {"x": 2.5}]) == (1, 2)
    assert S.prefix_match(rows, []) == (0, 0)


def test_the_chains_that_died_are_counted_with_their_last_state(dist):
    # D-035 drops chains for dying early; whether death follows seat state is a
    # question docs/progress.md answers from these.
    fates = {f["chain"]: f for f in dist["chain_fates"]}
    assert [i for i, f in fates.items() if f["completed"]] == [0, 6]
    assert [i for i, f in fates.items() if f["n_draws"] == 0] == [4, 7]
    died = {i: f["last_seats"] for i, f in fates.items()
            if not f["completed"] and f["n_draws"] > 1}
    assert died == {1: 2, 2: 2, 3: 2, 5: 2, 8: 2, 10: 1, 11: 1}
    assert (fates[3]["two_seat_share"], fates[8]["two_seat_share"]) == pytest.approx(
        (0.583, 0.700), abs=1e-3)


def test_the_enacted_plan_caveats_are_pinned(dist):
    assert dist["n_as_equal_as_enacted"] == 454
    assert dist["population_spread_median"] == 225
    assert dist["as_equal_counts"][0] == 2
    assert dist["as_equal_enacted_draws"] == [(5, 1584), (5, 1585)]
    assert dist["as_equal_enacted_distinct"] == 1
    compact = dist["compactness"]
    # On cut edges most draws are more compact than the enacted plan, and 0
    # seats is commoner among those that are not, in every chain at this split;
    # how far that rests on one chain's early excursion is the next pin.
    edges = compact["cut_edges"]
    assert edges["enacted"] == 51
    assert edges["median"] == 45
    assert edges["more_compact_share"] == pytest.approx(24_223 / 27_564)
    # each distinct plan counted once: a sensitivity check, not the distribution
    assert edges["more_compact_share_distinct"] == pytest.approx(2_190 / 3_361)
    # the location has its own Monte Carlo error, and the measure itself sits
    # outside CRITERIA.md section 8's band
    assert 2 * edges["more_compact_mcse"] == pytest.approx(0.0352, abs=1e-4)
    assert edges["measure_split_rhat"] == pytest.approx(1.0226, abs=1e-4)
    assert (min(edges["more_compact_by_chain"]), max(edges["more_compact_by_chain"])) == (
        pytest.approx(0.7714, abs=1e-4), pytest.approx(0.9190, abs=1e-4))
    assert edges["more_compact_share_as_equal"] == pytest.approx(0.7841, abs=1e-4)
    assert edges["no_more_compact"] == (pytest.approx(151 / 3341), 3341)
    assert edges["more_compact"] == (pytest.approx(244 / 24_223), 24_223)
    assert edges["no_more_compact_after_burn_in"][0] == pytest.approx(0.0216, abs=1e-4)
    assert edges["more_compact_after_burn_in"][0] == pytest.approx(0.0102, abs=1e-4)
    assert all(high > low for _, high, low in edges["by_chain"])
    # among the draws as equal as the plan, too few give 0 seats to tell
    assert edges["as_equal_split"] == ((0.0, 98), (pytest.approx(2 / 356), 356))
    # and the share is not monotone in cut edges: none at 40-42, a tenth at
    # exactly 51, none past 57
    profile = compact["by_cut_edges"]
    assert [sum(profile[e][i] for e in (40, 41, 42)) for i in range(3)] == [7850, 0, 42]
    assert profile[51][:2] == (999, 100) and profile[57][:2] == (126, 11)
    assert sum(profile[e][0] for e in range(58, 67) if e in profile) == 221
    assert sum(profile[e][1] for e in range(58, 67) if e in profile) == 0
    assert 65 not in profile and max(profile) == 66
    # On mean Polsby-Popper the plan sits mid-ensemble, the 0-seat contrast is
    # weaker, and one chain reverses it: the measures disagree (CRITERIA.md
    # section 3), and the two order the draws well short of its ~0.9.
    pp = compact["polsby_popper_mean"]
    assert pp["enacted"] == pytest.approx(0.33338, abs=1e-5)
    assert pp["median"] == pytest.approx(0.33252, abs=1e-5)
    assert pp["more_compact_share"] == pytest.approx(13_425 / 27_564)
    assert pp["more_compact_share_distinct"] == pytest.approx(575 / 3_361)
    assert 2 * pp["more_compact_mcse"] == pytest.approx(0.0592, abs=1e-4)
    assert pp["measure_split_rhat"] == pytest.approx(1.0302, abs=1e-4)
    assert (min(pp["more_compact_by_chain"]), max(pp["more_compact_by_chain"])) == (
        pytest.approx(0.3609, abs=1e-4), pytest.approx(0.6038, abs=1e-4))
    assert pp["more_compact_share_as_equal"] == pytest.approx(0.3370, abs=1e-4)
    assert pp["no_more_compact"] == (pytest.approx(281 / 14_139), 14_139)
    assert pp["more_compact"] == (pytest.approx(114 / 13_425), 13_425)
    assert pp["no_more_compact_after_burn_in"][0] == pytest.approx(0.0142, abs=1e-4)
    assert pp["more_compact_after_burn_in"][0] == pytest.approx(0.0087, abs=1e-4)
    assert [i for i, high, low in pp["by_chain"] if high <= low] == [2]
    assert compact["rank_correlation"] == pytest.approx(0.7579, abs=1e-4)
    # the population-tight draws have more cut edges on average, though how much
    # of the cut-edge gap follows from the population gap these draws cannot
    # measure (D-041)
    assert compact["as_equal_profile"] == (pytest.approx(48.1, abs=0.05),
                                           pytest.approx(0.2159, abs=1e-4), 454)
    assert compact["rest_profile"] == (pytest.approx(45.5, abs=0.05),
                                       pytest.approx(0.1196, abs=1e-4), 27_110)


def test_zero_seat_plans_in_the_warm_up_are_one_chain_s_excursion(dist):
    early = dict(zip(dist["chain_index"], dist["primary"]["warm_up_counts"]))
    assert {i: w[0] for i, w in early.items()} == {0: 2, 1: 0, 2: 21, 5: 0, 6: 89, 10: 0}
    # the whole window, so its length is pinned too
    assert early == {
        0: {0: 2, 1: 314, 2: 184, 3: 0, 4: 0}, 1: {0: 0, 1: 111, 2: 389, 3: 0, 4: 0},
        2: {0: 21, 1: 261, 2: 218, 3: 0, 4: 0}, 5: {0: 0, 1: 320, 2: 180, 3: 0, 4: 0},
        6: {0: 89, 1: 290, 2: 121, 3: 0, 4: 0}, 10: {0: 0, 1: 280, 2: 220, 3: 0, 4: 0},
    }
    assert all(sum(w.values()) == S.BURN_IN_CHECK for w in early.values())


def test_under_the_senate_vote_two_plans_early_in_one_chain_reach_3(dist):
    alt = dist["alternate"]
    assert alt["counts"] == SENATE_2020
    assert alt["chains_seen"][3] == 1
    assert alt["seat_count_split_rhat"] == pytest.approx(1.0203, abs=1e-4)
    beyond = dist["alternate_beyond"]
    assert beyond["seats"] == 3
    assert beyond["draws"] == [(0, j) for j in range(232, 240)]
    assert beyond["distinct"] == 2
    # beyond the rectangle they are not confined to a chain's first draws:
    # chain 1's are at draws 8,012-8,014
    everywhere = dist["alternate_beyond_all"]
    assert everywhere["draws"] == ([(0, j) for j in range(232, 240)]
                                   + [(1, j) for j in range(8_012, 8_015)]
                                   + [(8, j) for j in range(414, 417)])
    assert everywhere["distinct"] == 5
    assert dist["contests_agree"] == 22_734


def test_every_sweep_sits_on_the_half_vote_grid(dist, levels):
    # Each district's winner wastes one vote fewer when its total is even and
    # half a vote fewer when it is odd, so a sweep sits above its level by
    # k - j/2 votes, and j has the parity of the statewide total.
    assert S.sweep_grid(K, 1_656_733) == [3.5, 2.5]
    assert S.sweep_grid(K, 1_619_856) == [4.0, 3.0, 2.0]
    assert dist["primary"]["total_votes"] % 2 == 1
    assert dist["primary"]["sweeps_on_grid"] == {2.5: 216, 3.5: 179}
    assert dist["alternate"]["total_votes"] % 2 == 0
    assert dist["alternate"]["sweeps_on_grid"] == {2.0: 23, 3.0: 222, 4.0: 25}
    # The grid is necessary, not sufficient, so the 0-seat count the
    # enacted-plan comparison quotes is a reading, not a count (D-039). On
    # Iowa's statewide totals, district vote totals that give the Democrats 2
    # seats, and tie no district, can land on it, but only if the districts they
    # win cast 4V - 1 of the vote, 83%, to within a few votes: a turnout term of
    # 0.333. These totals are the ones GitHub Copilot's review constructed,
    # https://github.com/Hackshaven/districting-bench/pull/7#discussion_r4242234530
    votes = {"d1": (350_000, 339_756), "d2": (350_000, 339_758),
             "d3": (29_000, 109_609), "d4": (30_061, 108_549)}
    dem, rep = S.TWO_PARTY["G20PRE"]
    assert tuple(map(sum, zip(*votes.values()))) == (dem, rep)
    plan = {u: int(u[1]) for u in votes}
    dem_votes = {u: v[0] for u, v in votes.items()}
    rep_votes = {u: v[1] for u, v in votes.items()}
    assert P.seat_counts(plan, dem_votes, rep_votes) == (2, 2, 0)
    gap = P.efficiency_gap(plan, dem_votes, rep_votes)
    seats, diagnostics = S.recover_seats([abs(gap)], levels, IOWA_VOTES)
    assert (seats, diagnostics["sweeps_on_grid"]) == ([0], {3.5: 1})
    won = sum(d + r for d, r in votes.values() if d > r)
    terms = {s: 4 * dem / IOWA_VOTES - 1 - s / K for s in (1, 2, 3)}
    assert terms == pytest.approx({1: 0.583, 2: 0.333, 3: 0.083}, abs=5e-4)
    assert won / IOWA_VOTES - 2 / K == pytest.approx(terms[2], abs=1e-5)
    # Every way in, from the identity in evaluate.partisan.efficiency_gap's
    # docstring: a plan that is not a sweep, and ties no district, reads as 0
    # only if the votes cast where the Democrats win are 4D - T plus the grid
    # offset plus the threshold term (each district's winner wastes 1 vote fewer
    # at an even total, 1/2 at an odd one). Over every seat count and parity
    # pattern that leaves six totals, the ones D-039 quotes; the plan above
    # casts the third. With a tied district it is the votes cast where the
    # Democrats win plus half the tied district's that must hit them.
    base = 4 * dem - IOWA_VOTES
    totals = set()
    for s in (1, 2, 3):
        for odd in itertools.product((0, 1), repeat=K):
            if sum(odd) % 2 != IOWA_VOTES % 2:
                continue
            threshold = (sum(1 - o / 2 for o in odd[s:])
                         - sum(1 - o / 2 for o in odd[:s]))
            for offset in S.sweep_grid(K, IOWA_VOTES):
                cast = base + offset + threshold
                if cast == int(cast) and int(cast) % 2 == sum(odd[:s]) % 2:
                    totals.add(int(cast))
    assert sorted(totals) == list(range(1_379_512, 1_379_518))
    assert won == 1_379_514
    # D-039: verifying the 0-seat count means rerunning each chain to its last
    # draw read as 0, 20,127 of the 27,564; the whole rectangle is 37% more.
    seats = dist["primary"]["seats"]
    last = sum(max(i for i, n in enumerate(chain) if n == 0) + 1 for chain in seats)
    assert (last, sum(map(len, seats)), round(sum(map(len, seats)) / last - 1, 2)) == (
        20_127, 27_564, 0.37)


def test_every_other_draw_keeps_a_wide_margin(dist, levels):
    # recover_seats refuses beyond MARGIN of the half-gap. The data sit much
    # closer than that, and docs/progress.md quotes how much closer.
    p = dist["primary"]
    assert p["max_residual"] == pytest.approx(0.0143, abs=1e-4)
    assert p["max_residual"] < 0.35 * p["half_gap"]
    assert p["half_gap"] == pytest.approx(0.0413, abs=1e-4)
    assert p["residual_sd"] == pytest.approx({1: 0.0020, 2: 0.0030}, abs=1e-4)
    # A 1-seat plan is read as 2 from a turnout term of 0.062 (its district
    # casting over 31% of the vote) to 0.103, a band about 68,000 votes wide,
    # and a 2-seat plan as 1 from the same band the other way. That is the
    # nearer band: the gap is folded, so another sits near a turnout term of
    # 0.25. The 0.062 is three times the margin by construction, and four times
    # the largest residual by measurement (D-039).
    margin = S.MARGIN * p["half_gap"]
    edge, top = levels[1] - levels[2] - margin, levels[1] - levels[2] + margin
    assert (edge, 0.25 + edge, top) == pytest.approx((0.062, 0.312, 0.103), abs=5e-4)
    assert round((top - edge) * IOWA_VOTES, -3) == 68_000
    assert edge / margin == pytest.approx(3.0)
    assert int(edge / p["max_residual"]) == 4
    # and recover_seats reads it so, both ways: a 1-seat plan's gap sits at
    # levels[1] - t and a 2-seat plan's at levels[2] + t, for turnout term t.
    # Each is refused just short of the edge, misread from it to the top, and
    # refused again just past the top.
    for t, misread in ((edge - 1e-6, False), (edge + 1e-6, True),
                       (top - 1e-6, True), (top + 1e-6, False)):
        for other, gap in ((2, levels[1] - t), (1, levels[2] + t)):
            if misread:
                assert S.recover_seats([gap], levels, IOWA_VOTES)[0] == [other]
            else:
                with pytest.raises(ValueError, match="cannot be read off"):
                    S.recover_seats([gap], levels, IOWA_VOTES)


@pytest.mark.parametrize("state", ["IA", "CO"])
def test_reading_seats_off_the_gap_agrees_with_a_direct_count(state):
    # The Phase 2 report counted each enacted plan's seats from the returns.
    # Iowa's plan is a sweep, so it checks the vote share but not the turnout
    # term; Colorado's 5 of 8 exercises the turnout term. Neither sits near
    # Iowa's 1-versus-2 boundary, which rests on the margin check.
    partisan = json.loads(S.REPORT.read_text())[state]["partisan"]
    levels = S.seat_levels(partisan["dem_vote_share"], partisan["n_districts"])
    seats, _ = S.recover_seats([abs(partisan["efficiency_gap"])], levels,
                               TOTAL_VOTES[state])
    assert seats == [partisan["dem_seats"]]


def test_colorado_draws_are_refused():
    # D-039's limit: at k = 8 the folded levels sit 0.0275 apart, and the
    # turnout term is as large as that. The reading must refuse, not guess.
    spec = S.X.ensemble_spec("CO", "v2")
    chains = S.X.chains_from_draws(spec, S.X.draws_path(spec.prefix, "v2"))
    gaps = [row["abs_efficiency_gap@G20PRE"] for chain in chains for row in chain.rows]
    partisan = json.loads(S.REPORT.read_text())["CO"]["partisan"]
    levels = S.seat_levels(partisan["dem_vote_share"], partisan["n_districts"])
    with pytest.raises(ValueError, match="cannot be read off"):
        S.recover_seats(gaps, levels, TOTAL_VOTES["CO"])
    half_gap = min(b - a for a, b in zip(sorted(levels.values()),
                                         sorted(levels.values())[1:])) / 2
    off = [min(abs(g - v) for v in levels.values()) for g in gaps]
    # DECISIONS.md D-039 quotes both counts
    assert (len(gaps), sum(r > half_gap for r in off),
            sum(r > S.MARGIN * half_gap for r in off)) == (20_000, 125, 9_857)


def test_the_count_confirms_every_reading_and_a_contradiction_refuses(
        dist, tmp_path, monkeypatch):
    # tools/recount_seats.py regenerated every committed draw and counted its
    # seats from the returns (D-043). seat_distribution checks its reading
    # against that count on every draw under both contests, so every value the
    # figure draws is what the counts give. Each way the two could part must
    # refuse, past the rectangle and outside it as much as in it.
    assert dist["n_rows_counted"] == dist["n_rows_committed"] == 57_553
    counted, plans = S.counted_seats(S.RECOUNT)
    assert sum(map(len, counted.values())) == 2 * 57_553
    assert {i: len(keys) for i, keys in plans.items()} == {
        0: 12_000, 1: 8_133, 2: 6_495, 3: 4_282, 5: 4_594, 6: 12_000, 8: 1_863,
        9: 1, 10: 8_136, 11: 49}
    # docs/progress.md quotes the counts over every committed draw
    assert dist["counted_totals"] == {"G20PRE": {0: 832, 1: 28_780, 2: 27_941},
                                      "G20USS": {0: 389, 1: 23_408, 2: 33_742, 3: 14}}
    read = {key: list(seats) for key, seats in counted.items()}
    assert S.check_against_count(read, counted) == 57_553
    # a draw inside the rectangle, past its 4,594 draws, and in chains it drops
    for index, draw, contest in ((0, 7, "G20USS"), (0, 11_999, "G20PRE"),
                                 (6, 9_000, "G20USS"), (11, 48, "G20USS"),
                                 (3, 0, "G20PRE"), (9, 0, "G20PRE")):
        changed = {key: list(seats) for key, seats in counted.items()}
        changed[(index, contest)][draw] += 1
        with pytest.raises(ValueError, match=f"chain {index} draw {draw} reads as "
                                             f".* under {contest}"):
            S.check_against_count(changed, counted)
    # a chain cut short, either side, and a chain or contest only one side has
    short = {key: seats[:-1] if key == (0, "G20PRE") else seats
             for key, seats in counted.items()}
    for a, b in ((short, counted), (counted, short)):
        with pytest.raises(ValueError, match=r"chain 0 has \d+ draws read and "
                                             r"\d+ counted under G20PRE"):
            S.check_against_count(a, b)
    extra = counted | {(4, "G20PRE"): [1]}
    for a, b in ((extra, counted), (counted, extra)):
        with pytest.raises(ValueError, match="different draws"):
            S.check_against_count(a, b)

    with gzip.open(S.RECOUNT, "rt", newline="") as handle:
        header, *rows = list(csv.reader(handle))
    assert header == ["chain_index", "draw", "plan", "dem_seats@G20PRE",
                      "dem_seats@G20USS"]

    def recount(rows_, header_=header):
        path = tmp_path / f"recount-{len(list(tmp_path.iterdir()))}.csv.gz"
        with gzip.open(path, "wt", newline="") as handle:
            csv.writer(handle).writerows([header_, *rows_])
        return path
    with pytest.raises(ValueError, match="where draw 1 belongs"):
        S.counted_seats(recount([rows[0], rows[2], rows[1], *rows[3:]]))
    with pytest.raises(ValueError, match="has no column dem_seats@G20USS"):
        S.counted_seats(recount([r[:4] for r in rows[:3]], header[:4]))
    with pytest.raises(ValueError, match="has no column plan"):
        S.counted_seats(recount([r[:2] + r[3:] for r in rows[:3]],
                                header[:2] + header[3:]))
    with pytest.raises(ValueError, match="chain 0 draw 1 has plan key ''"):
        S.counted_seats(recount([rows[0], rows[1][:2] + [""] + rows[1][3:]]))
    # and end to end: one count changed, and the figure is not drawn
    changed = [list(r) for r in rows]
    changed[123][3] = str(int(changed[123][3]) + 1)
    monkeypatch.setattr(S, "RECOUNT", recount(changed))
    with pytest.raises(ValueError, match="chain 0 draw 123 reads as .* under G20PRE"):
        S.seat_distribution()


def test_the_count_s_record_names_the_draws_and_counts_read_here(tmp_path, monkeypatch):
    # The record says what the recount read: it must be these draws, and the
    # counts file beside it, byte for byte. That binds the pair to the draws; a
    # pair made some other way only rerunning the recount can tell (D-043).
    record = json.loads(S.RECOUNT_RECORD.read_text())
    spec = S.X.ensemble_spec(S.STATE, S.ENSEMBLE)
    draws = S.X.draws_path(spec.prefix, S.ENSEMBLE)
    S.check_recount_record(record, 57_553, spec, draws, S.RECOUNT)
    assert record["n_rows"] == 57_553
    assert (record["python"], record["gerrychain"]) == ("3.11.17", "1.0.0")
    # under Python 3.11, as the README pins it, every committed row reproduced
    assert set(record["largest_float_difference"].values()) == {0.0}
    # the returns: VEST's version 49 file, which D-043 names, by the files read,
    # with the credit and licence the counts carry, and the notice beside them
    # (D-044)
    assert record["returns_source"] == {
        "dataset": "doi:10.7910/DVN/K7760H", "version": "49.0", "file_id": 14304797,
        "file": "ia_2020.zip", "md5": "500252facae6107b93128406ebf5177b",
        "dbf_sha256": "c37230a71af50a83735ef80e1361447d23307175f7fcc22842f17706fbc16080",
        "shp_sha256": "33501da206b5171b0290f0a4a86e9f378cad2d7751485f431b33d9912a0b4c3a",
        "credit": VEST_CREDIT, "license": "CC-BY-4.0", "license_url": LICENCE_URL,
        "attribution": "docs/first-result/ATTRIBUTION.md"}
    for change, why in (
            (lambda r: r.update(draws_sha256="0" * 64), "a draws file other than"),
            (lambda r: r.update(counts_sha256="0" * 64), "a counts file other than"),
            (lambda r: r.update(config_digest="0" * 16), "configuration 0000"),
            (lambda r: r["chains"][4].update(n_rows=1), "row counts are not"),
            (lambda r: r["chains"].pop(), "row counts are not"),
            (lambda r: r.update(chains=[1, 2]), "row counts are not"),
            (lambda r: r.update(n_rows=57_552), "it records 57552 rows"),
            (lambda r: r.update(contests=["G20USS", "G20PRE"]), "it counted"),
            (lambda r: r["certified_two_party_totals"]["G20USS"].reverse(),
             "certified totals"),
            # the footer credits VEST's dataset and version, so the record must
            # name both
            (lambda r: r.update(returns_source=None), "the returns it counted from"),
            (lambda r: r["returns_source"].update(dataset="doi:10.0/other"),
             "the returns it counted from"),
            (lambda r: r["returns_source"].update(version="50.0"),
             "version 49.0, which the footer credits")):
        changed = copy.deepcopy(record)
        change(changed)
        with pytest.raises(ValueError, match=why):
            S.check_recount_record(changed, 57_553, spec, draws, S.RECOUNT)
    with pytest.raises(ValueError, match="is not a record"):
        S.check_recount_record([], 57_553, spec, draws, S.RECOUNT)
    # and end to end
    path = tmp_path / "ia-seats-v2.json"
    path.write_text(json.dumps(record | {"draws_sha256": "0" * 64}))
    monkeypatch.setattr(S, "RECOUNT_RECORD", path)
    with pytest.raises(ValueError, match="does not describe the count read here"):
        S.seat_distribution()


def test_the_counts_carry_vest_s_notice():
    # The record points to the notice beside the counts, and the notice gives
    # what D-044 says it gives: the file it covers, VEST's credit, the licence
    # and its link, what was changed, and VEST's disclaimer. Whether that is
    # enough is for the owner, not a test.
    record = json.loads(S.RECOUNT_RECORD.read_text(encoding="utf-8"))
    path = S.ROOT / "docs" / "first-result" / "ATTRIBUTION.md"
    assert S.ROOT / record["returns_source"]["attribution"] == path
    text = path.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "# Attribution — `ia-seats-v2.csv.gz`"
    notice = " ".join(text.split())
    for part in ("The seat counts in `ia-seats-v2.csv.gz`, in this directory, are made "
                 "from:", VEST_CREDIT.split(", https")[0],
                 "https://doi.org/10.7910/DVN/K7760H", "Harvard Dataverse, V49",
                 "CC BY 4.0", LICENCE_URL,
                 # what was changed: the returns summed to counties, seats counted
                 "**What was changed.** The file holds no vote count from the dataset.",
                 "`tools/prepare_data.py` summed Iowa's precinct returns to its 99 counties",
                 "`tools/recount_seats.py` counted, for each committed draw",
                 "WITHOUT WARRANTY OF ANY KIND"):
        assert part in notice, part


def test_a_plan_key_names_one_plan(dist, tmp_path, monkeypatch):
    # Draws that share a key are one plan, so they share both seat counts and
    # every integer metric; keys that name draws differing in any refuse.
    counted, plans = S.counted_seats(S.RECOUNT)
    spec = S.X.ensemble_spec(S.STATE, S.ENSEMBLE)
    every = S.X.chains_from_draws(spec, S.X.draws_path(spec.prefix, S.ENSEMBLE))
    rows = dict(zip(S.chain_indices(spec, every), (chain.rows for chain in every)))
    S.check_plan_keys(plans, counted, rows)
    one = {i: ["0" * 16] * len(keys) for i, keys in plans.items()}
    with pytest.raises(ValueError, match="names draws that differ"):
        S.check_plan_keys(one, counted, rows)
    shifted = {i: keys[1:] + keys[:1] for i, keys in plans.items()}
    with pytest.raises(ValueError, match="names draws that differ"):
        S.check_plan_keys(shifted, counted, rows)
    # and end to end, with a record that names the altered file, so that only
    # the keys are wrong
    with gzip.open(S.RECOUNT, "rt", newline="") as handle:
        header, *lines = list(csv.reader(handle))
    altered = tmp_path / "ia-seats-v2.csv.gz"
    with gzip.open(altered, "wt", newline="") as handle:
        csv.writer(handle).writerows([header, *([*r[:2], "0" * 16, *r[3:]] for r in lines)])
    record = json.loads(S.RECOUNT_RECORD.read_text())
    record["counts_sha256"] = hashlib.sha256(altered.read_bytes()).hexdigest()
    (tmp_path / "ia-seats-v2.json").write_text(json.dumps(record))
    monkeypatch.setattr(S, "RECOUNT", altered)
    monkeypatch.setattr(S, "RECOUNT_RECORD", tmp_path / "ia-seats-v2.json")
    with pytest.raises(ValueError, match="names draws that differ"):
        S.seat_distribution()


def test_a_malformed_counts_file_refuses(tmp_path):
    with gzip.open(S.RECOUNT, "rt", newline="") as handle:
        lines = handle.read().splitlines()
    for name, text, why in (
            ("short", "\n".join([lines[0], lines[1].rsplit(",", 1)[0]]),
             "does not have one field for each column"),
            ("long", "\n".join([lines[0], lines[1] + ",9"]),
             "does not have one field for each column")):
        path = tmp_path / f"{name}.csv.gz"
        with gzip.open(path, "wt", newline="") as handle:
            handle.write(text + "\n")
        with pytest.raises(ValueError, match=why):
            S.counted_seats(path)
    truncated = tmp_path / "truncated.csv.gz"
    truncated.write_bytes(S.RECOUNT.read_bytes()[:5_000])
    with pytest.raises(ValueError, match="cannot be read"):
        S.counted_seats(truncated)


def test_a_missing_committed_file_refuses_rather_than_failing(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(S, "REPORT", tmp_path / "no-such-report.json")
    assert S.main(["--out", str(tmp_path / "figure.png")]) == 1
    assert capsys.readouterr().err.startswith("refused: ")
    assert list(tmp_path.iterdir()) == []


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


@pytest.mark.parametrize("seats", [0, K])
def test_a_draw_read_as_a_sweep_must_be_one(levels, seats):
    # Odd statewide total: a sweep sits 2.5 or 3.5 votes above its level, and
    # nowhere else. Both sweeps are checked, not only the 0-seat one.
    for votes in (2.5, 3.5):
        read, _ = S.recover_seats([levels[seats] + votes / IOWA_VOTES], levels, IOWA_VOTES)
        assert read == [seats]
    # just outside the grid at either end; the wrong parity; on the level; below
    # it; and 1e-4 off, which is nothing for a 1-seat plan and impossible here
    for votes in (K + 0.5, K / 2 - 0.5, 3.0, 0.0, -2.5, 1e-4 * IOWA_VOTES):
        with pytest.raises(ValueError, match="not a sweep"):
            S.recover_seats([levels[seats] + votes / IOWA_VOTES], levels, IOWA_VOTES)


def test_the_grid_follows_the_parity_of_the_total(levels):
    even = IOWA_VOTES + 1
    read, _ = S.recover_seats([levels[0] + 3.0 / even], levels, even)
    assert read == [0]
    with pytest.raises(ValueError, match="not a sweep"):
        S.recover_seats([levels[0] + 2.5 / even], levels, even)


@pytest.mark.parametrize("gaps, refusal", [
    ([], "no draws"),
    (["nan", "two"], "not finite"),
    (["two", "nan"], "not finite"),
    (["inf"], "not finite"),
])
def test_nothing_to_read_refuses(gaps, refusal, levels):
    # NaN must be refused wherever it sits, and as itself: min() and max() both
    # pass a NaN through silently in one of the two orders, and a NaN that fell
    # to the 0-seat level would be refused for the wrong reason.
    values = [float(g) if g in ("nan", "inf") else levels[2] for g in gaps]
    with pytest.raises(ValueError, match=refusal):
        S.recover_seats(values, levels, IOWA_VOTES)


def test_the_figure_text_is_pinned(dist):
    text = S.figure_text(dist)
    assert text["title"] == "Seats in a neutral ReCom ensemble for Iowa"
    assert text["subtitle"] == [
        "Democratic seats of 4 under the 2020 presidential vote, in 27,564 ReCom "
        "draws made without election data",
        "6 of 12 chains, each cut to its first 4,594 draws (D-035); 2 never started "
        "and 4 stopped before 4,594",
        "About 286 effective draws for the seat count",
    ]
    assert text["labels"] == {
        0: ("1.4%", "±0.8 pts\n395 draws"),
        1: ("49.0%", "±6.0 pts\n13,516 draws"),
        2: ("49.5%", "±6.1 pts\n13,653 draws"),
        3: ("", "no draws"),
        4: ("", "no draws"),
    }
    assert text["enacted_x"] == 0
    # population is the reason, and compactness, whose reading depends on the
    # measure, stays off the figure (D-041)
    assert " ".join(text["note"].split()) == (
        "▲ Iowa's enacted plan gives Democrats 0 seats, as 1.4% of these draws do (0.4–2.5% "
        "across chains); its 0 turns on one district at 49.8% D. Not like-for-like: the "
        "draws are not held to its 94-person population spread (D-041). Not yet a "
        "finding.")
    # the last line stands on its own, and no line outruns the wrap width
    assert text["note"].splitlines()[-1] == "Not yet a finding."
    assert all(len(line) <= S.NOTE_WIDTH for line in text["note"].splitlines())
    footer = " ".join(text["footer"])
    for phrase in ("0–2 D seats of 4; none reached 3 or 4",
                   "2020 Senate vote, 8 draws reach 3 seats, in 2 distinct plans, "
                   "all in one chain's first 500 draws; committed draws outside these "
                   "reach it in 3 more plans.",
                   "2-seat share's standard error at 3.3–3.9 pts",
                   "R-hat 1.014, above CRITERIA §8's 1.00–1.01 band"):
        assert phrase in footer
    assert all(len(line) <= S.FOOTER_WIDTH for line in text["footer"])
    # VEST's credit closes the footer, on lines of its own, with the version
    # counted, the dataset's DOI and the licence's link, because the figure
    # travels without ATTRIBUTION.md (D-044); no-break spaces keep "licensed"
    # with the licence's name
    credit = ("Election returns: Voting and Election Science Team (VEST), 2020, version 49, "
              "doi.org/10.7910/DVN/K7760H; licensed\u00a0CC\u00a0BY\u00a04.0, "
              "creativecommons.org/licenses/by/4.0. Each draw's seats are counted from "
              "them (D-043,\u00a0D-044).")
    first = [i for i, line in enumerate(text["footer"]) if line.startswith("Election returns:")]
    assert len(first) == 1
    assert " ".join(text["footer"][first[0]:]) == credit
    assert text["footer"][first[0] - 1].endswith("from committed files only.")


def footer_of(d: dict) -> str:
    return " ".join(" ".join(S.figure_text(d)["footer"]).split())


def test_the_figure_text_follows_the_values(dist):
    # "Above" may not be a literal: it is read off the number it describes,
    # and so is each caution after it.
    low_ess = ("24 effective draws per split chain are below the 50 that Vehtari et al. "
               "(2021) ask for before relying on R-hat")
    understate = "these standard errors may understate the uncertainty"
    assert (f"R-hat 1.014, above CRITERIA §8's 1.00–1.01 band; {low_ess}, and "
            f"{understate}.") in footer_of(dist)
    d = copy.deepcopy(dist)
    # a reading far past anything a stationary chain gives at this size: the
    # caution about the standard errors stays, beside the effective sample's
    d["primary"]["seat_count_split_rhat"] = 1.08
    assert f"R-hat 1.080, above CRITERIA §8's 1.00–1.01 band; {low_ess}, and " \
           f"{understate}." in footer_of(d)
    # enough effective draws to rely on R-hat: the caution follows the R-hat alone
    d["primary"]["seat_count_ess"] = 5_000
    assert "Vehtari" not in footer_of(d)
    assert f"R-hat 1.080, above CRITERIA §8's 1.00–1.01 band; {understate}." in footer_of(d)
    d["primary"]["seat_count_split_rhat"] = 1.004
    assert "R-hat 1.004, inside CRITERIA §8's 1.00–1.01 band. Regenerate" in footer_of(d)
    assert "understate" not in footer_of(d)
    # below the band is no warning
    d["primary"]["seat_count_split_rhat"] = 0.998
    assert "R-hat 0.998, below CRITERIA §8's 1.00–1.01 band. Regenerate" in footer_of(d)
    # the Senate clause counts the plans only draws outside these reach, and
    # says so even when these draws reach none
    reach = "8 draws reach 3 seats, in 2 distinct plans, all in one chain's first 500 draws"
    d["alternate_beyond_all"]["more_plans"] = 0
    assert f"{reach}. Dots" in footer_of(d)
    d["alternate_beyond_all"]["more_plans"] = 1
    assert f"{reach}; committed draws outside these reach it in 1 more plan." in footer_of(d)
    d["alternate_beyond"].update(draws=[], distinct=0)
    d["alternate_beyond_all"]["more_plans"] = 3
    assert ("Under the 2020 Senate vote, none of these draws reach 3 seats, but committed "
            "draws outside them do, in 3 plans.") in footer_of(d)


def test_a_share_above_zero_is_never_printed_as_zero():
    assert (S.share_text(0.0), S.share_text(0.0003), S.share_text(0.0143)) == (
        "0.0%", "<0.1%", "1.4%")


#: How far, in pixels at the figure's 200 dpi, two strings' boxes may overlap:
#: each bar's two labels share about 2 px of padding, without touching.
PADDING_PX = 3


def assert_every_string_is_drawn_whole(d: dict, placed: dict):
    """Every string the figure prints is drawn, unclipped, on the canvas; no
    two overlap beyond a sliver of line padding, and the note's white box
    touches none of the others, whatever the wrap widths and in whatever font
    the machine renders."""
    text = S.figure_text(d)
    drawn = [t for t, _, _ in placed["texts"]]
    for line in (text["title"], *text["subtitle"], text["note"], *text["footer"],
                 *(t for pair in text["labels"].values() for t in pair if t)):
        assert line in drawn, line
    width, height = placed["canvas"]
    for t, (x0, y0, x1, y1), clipped in placed["texts"]:
        # an annotation matplotlib skips reports a unit box
        assert x1 - x0 > 1 and y1 - y0 > 1, t
        assert 0 <= x0 and x1 <= width and 0 <= y0 and y1 <= height, t
        assert not clipped, t
    # two strings may share a sliver of line padding, top to bottom, as each
    # bar's two labels do in the tallest font; side by side, a box hugs its
    # ink, so any overlap is touching glyphs; and the note's white box, which
    # hides what lies under it, may touch nothing
    boxes = [(t, box) for t, box, _ in placed["texts"] if t != text["note"]]
    boxes.append((text["note"], placed["note_box"]))
    for i, (a, p) in enumerate(boxes):
        for b, q in boxes[i + 1:]:
            across = min(p[2], q[2]) - max(p[0], q[0])
            down = min(p[3], q[3]) - max(p[1], q[1])
            if across > 0 and down > 0:
                assert text["note"] not in (a, b) and down <= PADDING_PX, (a, b, down)


def test_the_figure_draws_what_the_text_says(dist, tmp_path):
    out = tmp_path / "figure.png"
    placed = S.draw(dist, out)
    assert out.stat().st_size > 10_000
    p = dist["primary"]
    assert placed["bars"] == pytest.approx([100 * p["shares"][s] for s in range(K + 1)])
    assert placed["whiskers"] == pytest.approx({s: 200 * p["mcse"][s] for s in (0, 1, 2)})
    assert placed["marker_x"] == dist["enacted_dem_seats"]
    # the note sits right of every bar a draw reached, never on one
    assert placed["note_x"] > 2 + S.WIDTH / 2
    # and it, and the labels over every bar a draw reached, sit on the
    # surface's colour, so no gridline runs through them
    text = S.figure_text(dist)
    reached = [s for s in range(K + 1) if p["counts"][s]]
    assert {text["note"], *(t for s in reached for t in text["labels"][s])} <= placed["boxed"]
    assert_every_string_is_drawn_whole(dist, placed)


def test_an_outcome_seen_in_one_chain_draws_without_a_whisker(dist, tmp_path):
    # Under the Senate vote 3 seats appear in one chain only, so they have no
    # standard error; the figure must say so, not crash or invent one.
    d = copy.deepcopy(dist)
    d["primary"] = d["alternate"]
    placed = S.draw(d, tmp_path / "senate.png")
    assert 3 not in placed["whiskers"]
    assert S.figure_text(d)["labels"][3] == ("<0.1%", "1 chain only\n8 draws")
    # the note moves right, past the 3-seat bar, and must still fit
    assert_every_string_is_drawn_whole(d, placed)


@pytest.mark.parametrize("spread, cut_edges, polsby_popper, empty", [
    # no draw as equal as the plan, and none as uncompact as it on either measure
    (-1, 10**6, -1.0, "no_more_compact"),
    # every draw as equal as it, and none more compact on either measure
    (10**6, 0, 2.0, "more_compact"),
])
def test_an_empty_comparison_group_leaves_its_line_out(
        tmp_path, monkeypatch, spread, cut_edges, polsby_popper, empty):
    # The summary says there is nothing to compare, and the figure, which
    # carries neither comparison, still draws.
    monkeypatch.setattr(S, "ENACTED_SPREAD", spread)
    _report_with(tmp_path, monkeypatch, lambda r: r["compactness"].update(
        cut_edges=cut_edges, polsby_popper_mean=polsby_popper))
    d = S.seat_distribution()
    compact = d["compactness"]
    assert compact["as_equal_profile" if spread < 0 else "rest_profile"] is None
    for column in ("cut_edges", "polsby_popper_mean"):
        c = compact[column]
        assert c["more_compact_share"] == (1.0 if empty == "no_more_compact" else 0.0)
        assert c["more_compact_mcse"] is None
        assert c[empty] == (None, 0)
    lines = S.summary_lines(d)
    assert any("no profile" in line for line in lines)
    said = {"no_more_compact": "n/a of 0 draws no more compact",
            "more_compact": "n/a of 0 more compact"}[empty]
    assert sum(said in line for line in lines) == 2
    placed = S.draw(d, tmp_path / "empty.png")
    assert_every_string_is_drawn_whole(d, placed)


def test_the_compactness_split_counts_the_enacted_seat_count(tmp_path, monkeypatch):
    # The splits count the enacted plan's own seat count, not 0: a plan that
    # returned 1 seat would be compared on the 1-seat draws, which run the
    # other way on both measures.
    _report_with(tmp_path, monkeypatch, lambda r: r["partisan"].update(dem_seats=1))
    compact = S.seat_distribution()["compactness"]
    assert compact["cut_edges"]["no_more_compact"] == (pytest.approx(0.4289, abs=1e-4), 3341)
    assert compact["cut_edges"]["more_compact"] == (pytest.approx(0.4988, abs=1e-4), 24_223)
    assert compact["polsby_popper_mean"]["no_more_compact"] == (
        pytest.approx(0.4423, abs=1e-4), 14_139)
    assert compact["polsby_popper_mean"]["more_compact"] == (
        pytest.approx(0.5410, abs=1e-4), 13_425)


def _report_with(tmp_path, monkeypatch, change):
    report = json.loads(S.REPORT.read_text())
    change(report["IA"])
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    monkeypatch.setattr(S, "REPORT", path)


def test_a_report_for_another_contest_is_refused(tmp_path, monkeypatch):
    _report_with(tmp_path, monkeypatch, lambda r: r.update(contest="G20USS"))
    with pytest.raises(ValueError, match="different election"):
        S.seat_distribution()


def test_stale_vote_totals_are_refused(monkeypatch):
    dem, rep = S.TWO_PARTY["G20PRE"]
    monkeypatch.setitem(S.TWO_PARTY, "G20PRE", (dem + 1, rep))
    with pytest.raises(ValueError, match="stale"):
        S.seat_distribution()


def test_a_plan_with_another_district_count_is_refused(tmp_path, monkeypatch):
    _report_with(tmp_path, monkeypatch, lambda r: r["partisan"].update(n_districts=5))
    with pytest.raises(ValueError, match="districts"):
        S.seat_distribution()


def test_an_enacted_outcome_no_draw_produced_is_refused(tmp_path, monkeypatch):
    _report_with(tmp_path, monkeypatch, lambda r: r["partisan"].update(dem_seats=3))
    with pytest.raises(ValueError, match="never produced"):
        S.seat_distribution()


def test_a_non_finite_compactness_value_is_refused(tmp_path, monkeypatch):
    # Every comparison with a NaN is false, so it would read as "every draw is
    # more compact" rather than as no value at all.
    _report_with(tmp_path, monkeypatch,
                 lambda r: r["compactness"].update(polsby_popper_mean=float("nan")))
    with pytest.raises(ValueError, match="non-finite polsby_popper_mean"):
        S.seat_distribution()
    # and a missing one, which JSON writes as null
    _report_with(tmp_path, monkeypatch,
                 lambda r: r["compactness"].update(cut_edges=None))
    with pytest.raises(ValueError, match="non-finite cut_edges"):
        S.seat_distribution()


def test_a_report_without_the_closest_district_is_refused(tmp_path, monkeypatch):
    _report_with(tmp_path, monkeypatch, lambda r: r["trust"].update(caveats=[]))
    with pytest.raises(ValueError, match="closest district"):
        S.seat_distribution()
