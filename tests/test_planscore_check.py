"""The PlanScore cross-check's two formulas, and the record it committed.

`tools/check_planscore.py` found that PlanScore's efficiency gap is not this
repository's with the sign flipped: it is the equal-turnout form
``(S - 1/2) - 2(V - 1/2)``, and the two differ by ``tau - S`` whenever districts
cast different numbers of votes (D-040). The first two tests pin that relation
on `evaluate.partisan` itself, with hand-built plans whose every number can be
checked on paper. The third is a control that must be able to fail: a published
value is reproduced in PlanScore's form and refused in ours. The last pins what
`docs/cross-checks/planscore.json` records, so a change to either formula, or a
hand edit to the record, fails here rather than quietly changing what
`docs/progress.md` says the cross-check found.

No network and no data: the script fetches PlanScore's files, the tests do not.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import check_planscore as C          # noqa: E402
from evaluate import partisan as P   # noqa: E402

#: Four districts, two won by each party, turnout unequal: the Democratic wins
#: cast 2,500 of 4,000 votes, so tau = 0.625 against a seat share of 0.5.
UNEQUAL = {1: (600, 400), 2: (300, 700), 3: (900, 600), 4: (200, 300)}
#: The same seat outcome with every district casting 1,000 votes.
EQUAL = {1: (600, 400), 2: (300, 700), 3: (550, 450), 4: (200, 800)}


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


def test_with_equal_turnout_the_two_gaps_are_one_number():
    plan, dem, rep = as_plan(EQUAL)
    v, s, tau = shares(EQUAL)
    assert tau == s
    assert -P.efficiency_gap(plan, dem, rep, threshold="half") == pytest.approx(
        C.equal_turnout_gap(s, v))


def test_a_published_gap_is_reproduced_in_planscores_form_and_not_in_ours():
    race = "US Senate 2016"
    v, s, _ = shares(UNEQUAL)
    plan, dem, rep = as_plan(UNEQUAL)

    def index(published):
        return {
            "districts": [{"number": d, "totals": {f"{race} - DEM": dv,
                                                   f"{race} - REP": rv}}
                          for d, (dv, rv) in UNEQUAL.items()],
            "summary": {f"{race} Efficiency Gap": published},
        }

    planscores = round(C.equal_turnout_gap(s, v), 4)
    ours = round(-P.efficiency_gap(plan, dem, rep), 4)
    assert C.compare_race(index(planscores), race)["published_reproduced"]
    assert not C.compare_race(index(ours), race)["published_reproduced"]


def test_the_committed_record_says_what_the_write_up_says():
    record = json.loads(C.OUT.read_text())["plans"]
    for state in ("IA", "CO"):
        races = record[state]["races"]
        assert set(races) == set(C.RACES)
        assert all(r["published_reproduced"] for r in races.values()), state
    # Iowa is one plan on both sides: the Phase 2 report is reproduced.
    for key, diff in record["IA"]["phase_2_report"]["differences"].items():
        assert diff is None or abs(diff) <= C.SAME_PLAN_TOLERANCE, key
    assert record["IA"]["population_spread"] == 94
    # The turnout term docs/progress.md and evaluate.partisan quote: small under
    # three Colorado races, and the size of the gap itself under one.
    terms = {race: r["turnout_term"] for race, r in record["CO"]["races"].items()}
    assert terms["US President 2016"] == pytest.approx(0.0266, abs=5e-4)
    assert max(abs(t) for race, t in terms.items()
               if race != "US President 2016") < 0.002
