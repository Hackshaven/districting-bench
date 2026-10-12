"""The PlanScore cross-check's formulas, its failure paths, and the record it committed.

`tools/check_planscore.py` found that PlanScore's efficiency gap is not this
repository's with the sign flipped: it is the equal-turnout form
``(S - 1/2) - 2(V - 1/2)``, and the two differ by ``tau - S`` wherever that is
not zero (D-040). The first tests pin that relation on `evaluate.partisan`
itself, with hand-built plans whose every number can be checked on paper.

The middle of the file feeds the script PlanScore-shaped files built here, so
every way it can fail is exercised offline: a published value one unit off, a
wasted-vote count that is wrong, a conversion with the wrong sign, a file that
is not the pinned one, a plan that is not the enacted one. Each must fail, and
`main` must then exit non-zero without writing. A check that cannot fail is not
a check (docs/RESEARCH-LOOP-PLAYBOOK.md section 4.2).

The last test pins what `docs/cross-checks/planscore.json` records: a hand edit
to a pinned field fails there rather than quietly changing what
`docs/progress.md` says the cross-check found. It reads the record and
recomputes nothing, so a change to `evaluate.partisan` shows up in the tests
above, and in the record only once the script is run again.

No network and no data: the script fetches PlanScore's files, the tests do not.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import check_planscore as C            # noqa: E402
import plot_seat_distribution as S     # noqa: E402
from evaluate import partisan as P     # noqa: E402

#: Four districts, two won by each party, turnout unequal: the Democratic wins
#: cast 2,500 of 4,000 votes, so tau = 0.625 against a seat share of 0.5.
UNEQUAL = {1: (600, 400), 2: (300, 700), 3: (900, 600), 4: (200, 300)}
#: The same seat outcome with every district casting 1,000 votes.
EQUAL = {1: (600, 400), 2: (300, 700), 3: (550, 450), 4: (200, 800)}
#: Republicans win every district, at very different turnouts.
SWEEP = {1: (400, 600), 2: (300, 900), 3: (450, 550), 4: (100, 1400)}
#: Democrats win 3 of 4 with 44% of the vote: every metric is away from zero,
#: so a sign error in any conversion shows.
LOPSIDED = {1: (600, 400), 2: (550, 450), 3: (520, 480), 4: (100, 900)}

#: Iowa's district populations as PlanScore's pinned file carries them
#: (docs/cross-checks/planscore.json), written out rather than derived from the
#: constants the check compares them with, so a typo in either fails here.
IOWA_POPULATIONS = {1: 797_576, 2: 797_589, 3: 797_551, 4: 797_645}


def as_plan(districts):
    plan = {f"u{d}": d for d in districts}
    dem = {f"u{d}": v[0] for d, v in districts.items()}
    rep = {f"u{d}": v[1] for d, v in districts.items()}
    return plan, dem, rep


def shares(districts):
    total = sum(d + r for d, r in districts.values())
    v = sum(d for d, _ in districts.values()) / total
    won = [d for d, (dv, rv) in districts.items() if dv > rv]
    s = len(won) / len(districts)
    tau = sum(sum(districts[d]) for d in won) / total
    return v, s, tau


def test_the_two_gaps_differ_by_the_turnout_term():
    plan, dem, rep = as_plan(UNEQUAL)
    v, s, tau = shares(UNEQUAL)
    assert (v, s, tau) == (0.5, 0.5, 0.625)
    # Ours is positive for the Republicans, PlanScore's for the Democrats.
    ours_d_positive = -P.efficiency_gap(plan, dem, rep, threshold="half")
    assert ours_d_positive == pytest.approx(0.125)
    assert C.equal_turnout_gap(s, v) == pytest.approx(0.0)
    assert ours_d_positive - C.equal_turnout_gap(s, v) == pytest.approx(tau - s)


@pytest.mark.parametrize("districts", [EQUAL, SWEEP], ids=["equal turnout", "sweep"])
def test_where_tau_equals_s_the_two_gaps_are_one_number(districts):
    # Equal turnout is one way; a one-party sweep at any turnout is the other,
    # and it is the one all four of Iowa's elections are.
    plan, dem, rep = as_plan(districts)
    v, s, tau = shares(districts)
    assert tau == s
    assert -P.efficiency_gap(plan, dem, rep, threshold="half") == pytest.approx(
        C.equal_turnout_gap(s, v))


# --------------------------------------------------------------------------- #
# the script, on files built here
# --------------------------------------------------------------------------- #

def planscore_index(districts=UNEQUAL, published="reproduce", races=C.RACES,
                    populations=None, commit=C.PLANSCORE_COMMIT):
    """A PlanScore-shaped index.json for a hand-built plan, every race the same."""
    v, s, _ = shares(districts)
    if published == "reproduce":
        published = round(C.equal_turnout_gap(s, v), 4)
    populations = populations or {d: 1000 for d in districts}
    return {
        "description": "built by the test",
        "model_version": "none",
        "commit_sha": commit,
        "districts": [
            {"number": d,
             "totals": {"Population 2020": populations[d]}
                       | {f"{race} - DEM": dv for race in races}
                       | {f"{race} - REP": rv for race in races},
             "compactness": {"Polsby-Popper": 0.3, "Reock": 0.4}}
            for d, (dv, rv) in districts.items()],
        "summary": {f"{race} Efficiency Gap": published for race in races},
    }


def phase_2_report(districts=UNEQUAL, contest=C.COMMITTED_CONTEST):
    """The Phase 2 report's entry for the same plan, as evaluate.partisan scores it."""
    return {"contest": contest,
            "partisan": P.all_metrics(*as_plan(districts)),
            "compactness": {f"{m}_{stat}": 0.3 for m in ("polsby_popper", "reock")
                            for stat in ("mean", "min", "max")}}


def run(state="CO", districts=UNEQUAL, **index):
    return C.check({state: planscore_index(districts, **index)},
                   {state: phase_2_report(districts)})


def test_a_plan_planscore_scores_the_same_way_passes():
    result, failures = run()
    assert failures == []
    race = result["plans"]["CO"]["races"]["US Senate 2016"]
    assert race["tau"] == 0.625
    assert race["efficiency_gap_terms"]["turnout_term"] == pytest.approx(0.125)
    assert all(race["checks"].values())


@pytest.mark.parametrize("off", [+1e-4, -1e-4])
def test_a_published_value_one_unit_off_fails(off):
    v, s, _ = shares(UNEQUAL)
    _, failures = run(published=round(C.equal_turnout_gap(s, v), 4) + off)
    assert len(failures) == len(C.RACES)
    assert all("published_efficiency_gap" in f for f in failures)


def test_a_missing_published_value_fails_and_is_still_reported():
    result, failures = run(published=None)
    assert all("published_efficiency_gap" in f for f in failures)
    assert len(failures) == len(C.RACES)
    assert any("PlanScore EG n/a" in line for line in C.summary_lines(result))


def test_a_race_missing_from_the_file_fails_cleanly():
    result, failures = run(races=C.RACES[1:])
    assert failures == [f"CO {C.RACES[0]}: PlanScore's file has no totals"]
    assert result["plans"]["CO"]["phase_2_report"] is None
    C.summary_lines(result)
    # missing from one district only, not the first
    index = planscore_index()
    del index["districts"][2]["totals"][f"{C.RACES[3]} - REP"]
    _, failures = C.check({"CO": index}, {"CO": phase_2_report()})
    assert failures == [f"CO {C.RACES[3]}: PlanScore's file has no totals"]


@pytest.mark.parametrize("extra", [50, 5])
def test_a_defect_in_the_wasted_vote_count_fails(monkeypatch, extra):
    # The published gap is reproduced from seats and votes alone, so it cannot
    # see a wrong wasted-vote count. The identity with tau can, down to a few
    # votes: 5 more in each of two districts is 10 of 4,000, past k/T = 0.001.
    honest = P.wasted_votes

    def overcounted(plan, dem, rep, *, threshold="majority"):
        # more wasted Democratic votes in every district the Democrats win
        wasted = honest(plan, dem, rep, threshold=threshold)
        totals = P.district_votes(plan, dem, rep)
        return {d: (w_d + extra if totals[d][0] > totals[d][1] else w_d, w_r)
                for d, (w_d, w_r) in wasted.items()}

    monkeypatch.setattr(P, "wasted_votes", overcounted)
    result, failures = run()
    # the identity and GerryChain's independent count both catch it, race by race
    assert sorted({f.split(": ")[1].split(" ")[0] for f in failures}) == [
        "efficiency_gap_identity", "external_wasted_vote_gap"]
    assert len(failures) == 2 * len(C.RACES)
    # the published values still reproduce: only the identity caught it
    assert all(r["checks"]["published_efficiency_gap"]
               for r in result["plans"]["CO"]["races"].values())


@pytest.mark.parametrize("metric", ["mean_median", "partisan_bias", "declination"])
def test_a_conversion_with_the_wrong_sign_fails(monkeypatch, metric):
    honest = getattr(P, metric)
    assert honest(*as_plan(LOPSIDED)) != 0
    monkeypatch.setattr(P, metric, lambda *a, **k: -honest(*a, **k))
    _, failures = run(districts=LOPSIDED)
    assert failures and all(f"definition_{metric}" in f for f in failures)


@pytest.mark.parametrize("metric", ["mean_median", "partisan_bias", "declination"])
def test_a_conversion_a_millionth_off_fails(monkeypatch, metric):
    # Both sides read the same integers, so the tolerance is float error, not
    # rounding: a millionth is already a different definition.
    honest = getattr(P, metric)
    monkeypatch.setattr(P, metric, lambda *a, **k: honest(*a, **k) + 1e-6)
    _, failures = run(districts=LOPSIDED)
    assert failures and all(f"definition_{metric}" in f for f in failures)


def test_gerrychain_counts_the_wasted_votes_on_paper():
    # half-vote threshold: D wastes 100 + 300 + 150 + 200, R 400 + 200 + 600 + 50
    dem, rep = [d for d, _ in UNEQUAL.values()], [r for _, r in UNEQUAL.values()]
    assert C.gerrychain_gap(dem, rep) == pytest.approx((1250 - 750) / 4000)


def test_planscore_counts_a_tie_after_the_swing_as_republican():
    # 50-50 statewide, so no swing; district 1 ties and is not a Democratic seat
    assert C.planscore_partisan_bias([500, 700, 300], [500, 300, 700]) == pytest.approx(
        1 / 3 - 1 / 2)


def test_each_planscore_definition_reads_on_paper():
    dem, rep = [d for d, _ in UNEQUAL.values()], [r for _, r in UNEQUAL.values()]
    # D shares 0.6, 0.3, 0.6, 0.4: median 0.5, mean 0.475
    assert C.planscore_mean_median(dem, rep) == pytest.approx(0.025)
    # a uniform swing of 0 (the state is already at 50%) leaves 2 of 4 D seats
    assert C.planscore_partisan_bias(dem, rep) == pytest.approx(0.0)
    # Republicans win every seat: the extreme, -ln(k)/2
    sweep_dem, sweep_rep = [d for d, _ in SWEEP.values()], [r for _, r in SWEEP.values()]
    assert C.planscore_declination(sweep_dem, sweep_rep) == pytest.approx(-math.log(4) / 2)
    assert C.planscore_declination(sweep_rep, sweep_dem) == pytest.approx(math.log(4) / 2)
    # ours is None at a sweep, and converts to PlanScore's extreme for it
    convert = C.declination_in_planscore_convention
    assert convert(None, 0, 4) == pytest.approx(-math.log(4) / 2)
    assert convert(None, 4, 4) == pytest.approx(math.log(4) / 2)
    assert convert(None, 2, 4) is None


def test_a_sweep_passes_with_ours_undefined():
    result, failures = run(districts=SWEEP)
    assert failures == []
    race = result["plans"]["CO"]["races"]["US President 2020"]
    assert race["ours"]["declination"] is None
    # ours stays undefined in the record; only PlanScore's rule is checked
    assert race["ours_in_planscore_convention"]["declination"] is None
    assert race["declination_compared_with"].startswith("PlanScore's sweep convention")
    assert race["planscore_definitions"]["declination"] == pytest.approx(
        -math.log(4) / 2)


def test_fractional_totals_are_read_as_whole_votes_on_both_sides():
    # PlanScore's totals are fractional. evaluate.partisan truncates them and
    # the re-implemented definitions would not, so the script rounds first; read
    # unrounded, the two sides would differ by far more than float error.
    fractional = {d: (dv + 0.6, rv + 0.6) for d, (dv, rv) in UNEQUAL.items()}
    result, failures = run(districts=fractional)
    assert failures == []
    assert result["plans"]["CO"]["races"]["US President 2020"]["tau"] == 2504 / 4008


def test_a_tie_a_repeated_district_and_a_vote_outside_the_clamp_are_refused():
    tied = dict(UNEQUAL) | {4: (250, 250)}
    with pytest.raises(ValueError, match="tied"):
        C.compare_race(planscore_index(tied), "US President 2020")
    with pytest.raises(ValueError, match="outside"):
        C.equal_turnout_gap(0.0, 0.2)
    # A file that numbers two districts alike would have one merged into the
    # other, votes and population, and every comparison could still pass.
    for state, populations in (("CO", None), ("IA", dict(IOWA_POPULATIONS))):
        index = planscore_index(populations=populations)
        index["districts"][2]["number"] = 4
        with pytest.raises(ValueError, match="repeats a district number"):
            C.check({state: index}, {state: phase_2_report()})


def test_iowa_must_be_the_enacted_plan(monkeypatch):
    # PlanScore's copy may differ from the documented populations only where it
    # was found to: district 1, 8 persons short.
    known = C.POPULATION_MINUS_DOCUMENTED["IA"]
    assert known == {1: -8, 2: 0, 3: 0, 4: 0}
    populations = dict(IOWA_POPULATIONS)
    result, failures = run(state="IA", populations=populations)
    assert failures == []
    assert result["plans"]["IA"]["population_minus_documented"] == known
    assert result["plans"]["IA"]["population_spread"] == 94
    # Any other difference fails: one that widens the spread; three that keep
    # it (5 persons moved from district 2 to district 1, the shortfall moved to
    # district 2, and the documented populations themselves, which the pinned
    # file does not carry); and a fifth district inside the spread.
    for changed, difference, spread in [
            ({4: populations[4] + 10}, {1: -8, 2: 0, 3: 0, 4: 10}, 104),
            ({1: populations[1] + 5, 2: populations[2] - 5}, {1: -3, 2: -5, 3: 0, 4: 0}, 94),
            ({1: populations[1] + 8, 2: populations[2] - 8}, {1: 0, 2: -8, 3: 0, 4: 0}, 94),
            (C.ENACTED_POPULATIONS["IA"], {1: 0, 2: 0, 3: 0, 4: 0}, 94),
            ({5: 797_600}, {1: -8, 2: 0, 3: 0, 4: 0, 5: 797_600}, 94)]:
        mutated = populations | changed
        votes = UNEQUAL | {5: (450, 550)}
        result, failures = run(state="IA", districts={n: votes[n] for n in mutated},
                               populations=mutated)
        assert result["plans"]["IA"]["population_spread"] == spread
        assert failures == [f"IA: PlanScore's district populations less the enacted "
                            f"plan's are {difference}, not {known}"]
    # A missing district fails rather than raising.
    missing = {n: p for n, p in populations.items() if n != 4}
    _, failures = run(state="IA", districts={n: UNEQUAL[n] for n in missing},
                      populations=missing)
    assert any("less the enacted plan's are {1: -8, 2: 0, 3: 0, 4: -797645}" in f
               for f in failures)
    # With no difference recorded, the documented populations must match exactly.
    monkeypatch.setattr(C, "POPULATION_MINUS_DOCUMENTED", {})
    assert run(state="IA", populations=dict(C.ENACTED_POPULATIONS["IA"]))[1] == []
    assert run(state="IA", populations=populations)[1] == [
        "IA: PlanScore's district populations less the enacted plan's are "
        "{1: -8, 2: 0, 3: 0, 4: 0}, not {1: 0, 2: 0, 3: 0, 4: 0}"]


def test_iowa_must_match_the_phase_2_report():
    # Iowa's plan is the same on both sides, so ours on PlanScore's totals must
    # reproduce the committed report; a report from other returns must not.
    index = planscore_index(populations=dict(IOWA_POPULATIONS))
    _, failures = C.check({"IA": index}, {"IA": phase_2_report(EQUAL)})
    assert "IA efficiency_gap" in " ".join(failures)
    # and the tolerance is a few votes, not a different election: 2e-4 fails
    report = phase_2_report()
    report["partisan"]["efficiency_gap"] += 2e-4
    _, failures = C.check({"IA": index}, {"IA": report})
    assert len(failures) == 1 and failures[0].startswith("IA efficiency_gap")


def test_a_file_scored_by_another_commit_fails():
    _, failures = run(commit="0" * 40)
    assert failures and "scored by PlanScore commit" in failures[0]


def test_a_report_on_another_contest_is_refused():
    with pytest.raises(ValueError, match="wrong race"):
        C.check({"CO": planscore_index()}, {"CO": phase_2_report(contest="G20USS")})


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_pin_refuses_any_other_file(monkeypatch):
    body = json.dumps(planscore_index()).encode()
    monkeypatch.setattr(C.urllib.request, "urlopen", lambda url, timeout: _Response(body))
    assert C.fetch("any", hashlib.sha256(body).hexdigest()) == json.loads(body)
    with pytest.raises(ValueError, match="no longer matches its pin"):
        C.fetch("any", hashlib.sha256(body + b" ").hexdigest())


def _main(monkeypatch, tmp_path, published="reproduce", fetch=None):
    indexes = {"IA": planscore_index(populations=dict(IOWA_POPULATIONS),
                                     published=published),
               "CO": planscore_index(published=published)}
    monkeypatch.setattr(C, "fetch", fetch or (lambda plan_id, sha256: next(
        indexes[s] for s, (i, _) in C.PLANS.items() if i == plan_id)))
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"IA": phase_2_report(), "CO": phase_2_report()}))
    monkeypatch.setattr(C, "REPORT", report)
    out = tmp_path / "planscore.json"
    return C.main(["--out", str(out)]), out


@pytest.mark.parametrize("published, code", [("reproduce", 0), (0.5, 1)])
def test_main_writes_the_record_only_when_everything_reproduces(
        monkeypatch, tmp_path, published, code):
    returned, out = _main(monkeypatch, tmp_path, published=published)
    assert returned == code
    if code:
        assert not out.exists()
    else:
        assert json.loads(out.read_text())["plans"].keys() == {"IA", "CO"}


def test_main_refuses_without_writing_when_a_pin_fails(monkeypatch, tmp_path):
    def wrong(plan_id, sha256):
        raise ValueError("no longer matches its pin")
    code, out = _main(monkeypatch, tmp_path, fetch=wrong)
    assert code == 1 and not out.exists()


def test_main_refuses_without_writing_when_the_ensemble_is_missing(monkeypatch, tmp_path):
    def missing(state, phase_2):
        raise FileNotFoundError("no draws file")
    monkeypatch.setattr(C, "ensemble_location", missing)
    code, out = _main(monkeypatch, tmp_path)
    assert code == 1 and not out.exists()


# --------------------------------------------------------------------------- #
# the committed record
# --------------------------------------------------------------------------- #

def test_the_committed_record_says_what_the_write_up_says():
    result = json.loads(C.OUT.read_text())
    assert C.PLANSCORE_COMMIT in result["planscore_source"]
    record = result["plans"]
    for state in ("IA", "CO"):
        assert record[state]["sha256"] == C.PLANS[state][1]
        assert record[state]["commit_sha"] == C.PLANSCORE_COMMIT
        races = record[state]["races"]
        assert set(races) == set(C.RACES)
        assert all(all(r["checks"].values()) for r in races.values()), state
        assert all("external_wasted_vote_gap" in r["checks"] for r in races.values())
    # Iowa's declination is undefined on every race (a sweep) and is recorded so
    assert all(r["ours_in_planscore_convention"]["declination"] is None
               for r in record["IA"]["races"].values())
    # Iowa is one plan on both sides: the Phase 2 report is reproduced, and it
    # is the enacted plan, as the figure's caveat takes it to be.
    for key, diff in record["IA"]["phase_2_report"]["differences"].items():
        assert diff is None or abs(diff) <= C.SAME_PLAN_TOLERANCE, key
    assert (record["IA"]["population_spread"] == C.ENACTED_SPREAD["IA"]
            == S.ENACTED_SPREAD == 94)
    assert record["IA"]["population_minus_documented"] == {"1": -8, "2": 0, "3": 0, "4": 0}
    assert record["IA"]["district_populations"] == {
        str(n): p for n, p in IOWA_POPULATIONS.items()}
    # The turnout term docs/progress.md and evaluate.partisan quote: small under
    # three Colorado races, and the size of the gap itself under one.
    terms = {race: r["efficiency_gap_terms"]["turnout_term"]
             for race, r in record["CO"]["races"].items()}
    assert terms["US President 2016"] == pytest.approx(0.0266, abs=5e-5)
    assert max(abs(t) for race, t in terms.items()
               if race != "US President 2016") < 0.002
    # The README: ours differs from PlanScore's published gap on every Colorado
    # race, by more than ten times PlanScore's rounding, and by a factor of
    # nearly two under the 2016 presidential vote. Declination is compared with
    # ours there.
    gaps = {race: (r["ours_in_planscore_convention"]["efficiency_gap_wasted_votes"],
                   r["planscore_published_efficiency_gap"])
            for race, r in record["CO"]["races"].items()}
    assert all(abs(ours - published) > 10 * C.PUBLISHED_ROUNDING
               for ours, published in gaps.values())
    # and agrees with it to four decimal places on Iowa's four, each a sweep
    assert all(abs(r["ours_in_planscore_convention"]["efficiency_gap_wasted_votes"]
                   - r["planscore_published_efficiency_gap"]) <= C.PUBLISHED_ROUNDING
               for r in record["IA"]["races"].values())
    assert gaps["US President 2016"][1] / gaps["US President 2016"][0] == pytest.approx(
        1.98, abs=0.005)
    assert all(r["declination_compared_with"] == "ours"
               for r in record["CO"]["races"].values())
    # docs/progress.md: wherever ours is defined, the conversions agree with
    # PlanScore's re-implemented definitions to within 2e-16.
    assert max(abs(r["planscore_definitions"][m] - r["ours_in_planscore_convention"][m])
               for plan in record.values() for r in plan["races"].values()
               for m in r["planscore_definitions"]
               if r["ours_in_planscore_convention"][m] is not None) < 2e-16
    # What D-015's approximation costs where the ensemble is used
    location = result["ensemble_location"]
    assert (location["efficiency_gap"]["committed"],
            location["efficiency_gap"]["on_planscore_totals"]) == pytest.approx(
        (41.8, 43.2), abs=0.05)
    assert (location["mean_median"]["committed"],
            location["mean_median"]["on_planscore_totals"]) == pytest.approx(
        (66.3, 66.7), abs=0.05)
