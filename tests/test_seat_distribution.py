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
K = 4


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
    assert dist["repeats"] == 18_303
    assert dist["distinct_metric_rows"] == 4_020
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
    assert compact["enacted_cut_edges"] == 51
    assert compact["at_or_above"] == (pytest.approx(151 / 3341), 3341)
    assert compact["below"] == (pytest.approx(244 / 24_223), 24_223)
    assert compact["at_or_above_after_burn_in"][0] == pytest.approx(0.0216, abs=1e-4)
    assert compact["below_after_burn_in"][0] == pytest.approx(0.0102, abs=1e-4)
    # in every chain at this split, not only pooled; how far that rests on one
    # chain's early excursion is the next pin
    assert all(high > low for _, high, low in compact["per_chain"])
    assert compact["more_compact_share"] == pytest.approx(24_223 / 27_564)
    # the population-tight draws are less compact: much of the compactness gap
    # follows from the population gap
    assert compact["as_equal_profile"] == (pytest.approx(48.1, abs=0.05),
                                           pytest.approx(0.2159, abs=1e-4), 454)
    assert compact["rest_profile"] == (pytest.approx(45.5, abs=0.05),
                                       pytest.approx(0.1196, abs=1e-4), 27_110)


def test_zero_seat_plans_in_the_warm_up_are_one_chain_s_excursion(dist):
    early = [w[0] for w in dist["primary"]["warm_up_counts"]]
    assert dict(zip(dist["chain_index"], early)) == {0: 2, 1: 0, 2: 21, 5: 0, 6: 89, 10: 0}


def test_under_the_senate_vote_two_plans_early_in_one_chain_reach_3(dist):
    alt = dist["alternate"]
    assert alt["counts"] == SENATE_2020
    assert alt["chains_seen"][3] == 1
    assert alt["seat_count_split_rhat"] == pytest.approx(1.0203, abs=1e-4)
    beyond = dist["alternate_beyond"]
    assert beyond["seats"] == 3
    assert beyond["draws"] == [(0, j) for j in range(232, 240)]
    assert beyond["distinct"] == 2
    assert dist["contests_agree"] == 22_734


def test_every_sweep_sits_on_the_half_vote_grid(dist):
    # Each district's winner wastes one vote fewer when its total is even and
    # half a vote fewer when it is odd, so a sweep sits above its level by
    # k - j/2 votes, and j has the parity of the statewide total. This is what
    # makes the 0-seat count -- the one the enacted-plan comparison quotes -- a
    # count rather than a reading.
    assert S.sweep_grid(K, 1_656_733) == [3.5, 2.5]
    assert S.sweep_grid(K, 1_619_856) == [4.0, 3.0, 2.0]
    assert dist["primary"]["total_votes"] % 2 == 1
    assert dist["primary"]["sweeps_on_grid"] == {2.5: 216, 3.5: 179}
    assert dist["alternate"]["total_votes"] % 2 == 0
    assert dist["alternate"]["sweeps_on_grid"] == {2.0: 23, 3.0: 222, 4.0: 25}


def test_every_other_draw_keeps_a_wide_margin(dist):
    # recover_seats refuses beyond MARGIN of the half-gap. The data sit much
    # closer than that, and docs/progress.md quotes how much closer.
    p = dist["primary"]
    assert p["max_residual"] == pytest.approx(0.0143, abs=1e-4)
    assert p["max_residual"] < 0.35 * p["half_gap"]
    assert p["residual_sd"] == pytest.approx({1: 0.0020, 2: 0.0030}, abs=1e-4)


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
    note = " ".join(text["note"].split())
    for phrase in ("returns 0 D seats", "as 1.4% of these draws do (0.4–2.5% across "
                   "chains)", "on one district at 49.8% D",
                   "not held to its population equality",
                   "The plan is also less compact than 88% of them, and 0 seats is commoner "
                   "among less compact draws",
                   "Not yet a finding"):
        assert phrase in note
    footer = " ".join(text["footer"])
    for phrase in ("0–2 D seats of 4; none reached 3 or 4",
                   "2020 Senate vote, 8 draws reach 3: 2 distinct plans, all in "
                   "one chain's first 500 draws",
                   "2-seat share's standard error at 3.3–3.9 pts",
                   "R-hat 1.014, outside CRITERIA §8's 1.00–1.01 band"):
        assert phrase in footer
    assert all(len(line) <= S.FOOTER_WIDTH for line in text["footer"])


def test_the_figure_text_follows_the_values(dist):
    # Neither "outside" nor "more common" may be a literal: each is read off
    # the number it describes.
    d = copy.deepcopy(dist)
    d["primary"]["seat_count_split_rhat"] = 1.004
    assert "R-hat 1.004, inside" in " ".join(S.figure_text(d)["footer"])
    # the caution about relying on R-hat is read off the effective sample size
    assert "on 24 effective draws per split chain, below the 50 Vehtari et al. " \
           "(2021) ask for" in " ".join(" ".join(S.figure_text(dist)["footer"]).split())
    d["primary"]["seat_count_ess"] = 5_000
    assert "Vehtari" not in " ".join(S.figure_text(d)["footer"])
    compact = d["compactness"]
    compact["at_or_above"], compact["below"] = compact["below"], compact["at_or_above"]
    compact["more_compact_share"] = 0.25
    note = " ".join(S.figure_text(d)["note"].split())
    assert "less compact than 25% of them, and 0 seats is rarer among less compact" in note


def test_a_share_above_zero_is_never_printed_as_zero():
    assert (S.share_text(0.0), S.share_text(0.0003), S.share_text(0.0143)) == (
        "0.0%", "<0.1%", "1.4%")


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


def test_an_outcome_seen_in_one_chain_draws_without_a_whisker(dist, tmp_path):
    # Under the Senate vote 3 seats appear in one chain only, so they have no
    # standard error; the figure must say so, not crash or invent one.
    d = copy.deepcopy(dist)
    d["primary"] = d["alternate"]
    placed = S.draw(d, tmp_path / "senate.png")
    assert 3 not in placed["whiskers"]
    assert S.figure_text(d)["labels"][3] == ("<0.1%", "1 chain only\n8 draws")


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


def test_a_report_without_the_closest_district_is_refused(tmp_path, monkeypatch):
    _report_with(tmp_path, monkeypatch, lambda r: r["trust"].update(caveats=[]))
    with pytest.raises(ValueError, match="closest district"):
        S.seat_distribution()
