#!/usr/bin/env python3
"""Cross-check ``evaluate.partisan`` against PlanScore on the plans it has scored.

``prompt.md``: *"Cross-check your metric implementations against PlanScore on
plans it has already scored."* PlanScore scores both enacted congressional
plans this repository studies, and for each one it publishes the district
two-party totals of four past elections -- the 2016 and 2020 presidential and
U.S. Senate races -- next to the efficiency gap it computes from them. That
makes an exact comparison possible: the same district totals go through
``evaluate.partisan`` here, and PlanScore's published number is reproduced
from ours or it is not.

Every difference found is a definition, not an error, and each one is checked
by reproducing PlanScore's number from this repository's:

* **Efficiency gap: two formulas, not two signs.** PlanScore's code computes,
  and its files publish, ``(S - 1/2) - 2(V - 1/2)`` -- the equal-turnout form,
  from the seat share and the statewide vote share, once any statewide share
  outside ``PLANSCORE_CLAMP`` has been swung into it -- positive for the
  Democrats (``calculate_EG``), although its metric page describes the
  wasted-vote form. ``evaluate.partisan`` counts wasted votes district by
  district, as CRITERIA.md section 5.1 defines the metric, positive for the
  Republicans. Inside that band, where every race compared lies and outside
  which :func:`equal_turnout_gap` refuses, and on a plan with no tied or empty
  district, as :func:`compare_race` requires, the two differ in PlanScore's
  orientation by ``tau - S``, the share of votes cast in districts the
  Democrats won less the share of seats they won, plus a strict-majority
  threshold term of at most ``k/T``. So there they agree whenever ``tau = S``:
  at equal turnout, and in any one-party sweep, whatever the turnout.
  PlanScore publishes no wasted-vote gap, so :func:`compare_race`
  checks that count two other ways: against the identity, with ``tau``
  computed from the district totals, and against GerryChain's own
  ``wasted_votes`` (:func:`gerrychain_gap`). A defect in the wasted-vote count
  cannot pass as a difference of definition.
* **Mean-median**: the same quantity, opposite sign (PlanScore: median - mean).
* **Partisan bias**: the same quantity, same sign.
* **Declination**: PlanScore publishes Warrington's angle rescaled by
  ``ln(k)/2`` and negated, and gives a Republican sweep ``-ln(k)/2`` and a
  Democratic one ``+ln(k)/2`` where ``evaluate.partisan.declination`` returns
  None.

Only the efficiency gap is compared against a *published* PlanScore number,
because it is the only metric PlanScore computes on actual past results. Its
headline metrics are averages over elections simulated from its own vote
model, so no input here could reproduce them. The other three conversions are
checked against PlanScore's definitions, re-implemented below --
:func:`planscore_mean_median`, :func:`planscore_partisan_bias` and
:func:`planscore_declination` -- from :data:`PLANSCORE_SOURCE`, the commit both
files were scored by. This script never runs PlanScore's code.

PlanScore's district totals are fractional, because it allocates precinct
votes to census blocks. :func:`race_votes` rounds them to whole votes, so both
sides of every comparison read the same integers.

**No election data is committed.** PlanScore's files are fetched at run time
and pinned by sha256, and ``docs/cross-checks/planscore.json`` carries metric
values, statewide shares and district populations only, never district vote
counts: CRITERIA.md section 9.1 commits nothing under an unstated licence, and
PlanScore's files state none.

Run::

    python tools/check_planscore.py     # fetches PlanScore's files

It writes ``docs/cross-checks/planscore.json`` only when every check passes,
and otherwise exits non-zero and writes nothing. It refuses outright if a
fetched file no longer matches its pin, if the Phase 2 report is not on the
2020 presidential vote, or if a race has a tied district or a statewide share
outside 1/4 to 3/4. It fails if a file was scored by another PlanScore commit
or lacks a race's totals; if a published PlanScore number, a re-implemented
definition, the identity or GerryChain's count cannot be reproduced from this
repository's under the conversions above; or, on Iowa, if ours on PlanScore's
totals does not reproduce the Phase 2 report, or the district populations
differ from the documented ones other than as
:data:`POPULATION_MINUS_DOCUMENTED` records. See D-040.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import statistics
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from evaluate import partisan as P                       # noqa: E402
from gerrychain.metrics import partisan as GERRYCHAIN    # noqa: E402

OUT = ROOT / "docs" / "cross-checks" / "planscore.json"
REPORT = ROOT / "docs" / "phase-2" / "phase-2-report.json"
URL = "https://planscore.s3.amazonaws.com/uploads/{id}/index.json"

#: The commit that scored both pinned files (their ``commit_sha``), and the
#: source whose formulas the definitions below re-implement. 3f866f9, the head of
#: PlanScore's main branch when this check was written, rewrites the four
#: metric functions in vectorized form; they compute the same.
PLANSCORE_COMMIT = "566cda433ab7d145c2c86daf5872aff0cc175707"
PLANSCORE_SOURCE = (
    f"https://github.com/PlanScore/planscore/blob/{PLANSCORE_COMMIT}/planscore/score.py"
)

#: state -> (PlanScore upload id, sha256 of its index.json when pinned).
#: PlanScore's own titles call the Iowa plan a draft. It is identified as the
#: enacted map by its district populations, which match docs/FEASIBILITY.md
#: section 4 in three districts and fall 8 persons short in district 1 (see
#: :data:`POPULATION_MINUS_DOCUMENTED`), by the Iowa Legislature's Plan 2 files
#: its ``library_metadata`` links, and by its 2020 presidential metrics, which
#: match the Phase 2 report's.
PLANS = {
    "IA": ("20251203T023554.470826564Z",
           "3b6e73c849712673330e08df323f258292dcf23cb387fafdf9b8b0dabac2092d"),
    "CO": ("20251203T023818.696378561Z",
           "f2f46c823d2941b3fb38215c589abbaa056286fb89ef3f1de202fc5eb77fde4e"),
}

#: The enacted plans' district populations as documented elsewhere in the
#: repository, by district number: Iowa from docs/FEASIBILITY.md section 4.
#: Colorado has no entry, because this repository represents its plan only
#: approximately (D-015).
ENACTED_POPULATIONS = {"IA": {1: 797_584, 2: 797_589, 3: 797_551, 4: 797_645}}
#: Their max-min spread, recorded beside the spread of PlanScore's copy.
ENACTED_SPREAD = {state: max(p.values()) - min(p.values())
                  for state, p in ENACTED_POPULATIONS.items()}
#: PlanScore's district populations less :data:`ENACTED_POPULATIONS`, as found
#: when its file was pinned: district 1 is 8 persons short, as is PlanScore's
#: statewide total, and the other three match. Any other difference fails,
#: including one that keeps the enacted plan's spread. A state with documented
#: populations and no entry here must match them exactly.
POPULATION_MINUS_DOCUMENTED = {"IA": {1: -8, 2: 0, 3: 0, 4: 0}}

RACES = ("US President 2020", "US Senate 2020", "US President 2016", "US Senate 2016")

#: The Phase 2 report's contest. Its values are compared with ours on
#: PlanScore's totals for the same race.
COMMITTED_CONTEST, COMMITTED_RACE = "G20PRE", "US President 2020"

#: PlanScore publishes its per-election gaps to four decimal places; the float
#: slack keeps a value exactly half a unit away from failing on representation.
PUBLISHED_ROUNDING = 5e-5 + 1e-12

#: How closely a re-implemented PlanScore definition must match its conversion
#: of ours. Both read the same integers, so only floating point separates them.
DEFINITION_TOLERANCE = 1e-9

#: How closely ours on PlanScore's totals must match the Phase 2 report where
#: both describe the same plan exactly (Iowa: whole counties). PlanScore's
#: statewide totals differ from the certified ones by a few votes.
SAME_PLAN_TOLERANCE = 1e-4

#: PlanScore's ``calculate_EG`` swings the statewide share into this band
#: before computing. :func:`equal_turnout_gap` does not, so it refuses outside.
PLANSCORE_CLAMP = (0.25, 0.75)

#: The state whose committed plan only approximates the enacted one (D-015),
#: and so the one where the approximation's cost is located in the ensemble.
APPROXIMATED = "CO"

#: Shown on every record so a reader of the JSON alone knows which way is which.
CONVENTIONS = {
    "ours": {m: f"positive favours {P.FAVOURS[m]}" for m in P.METRICS},
    "planscore": {
        "efficiency_gap": "positive favours D; (S - 1/2) - 2(V - 1/2), the "
                          "equal-turnout form",
        "mean_median": "positive favours D; median - mean of D shares",
        "partisan_bias": "positive favours D; same definition as ours",
        "declination": "positive favours D; -(Warrington's angle) * ln(k) / 2, "
                       "-ln(k)/2 when the Republicans win every seat and "
                       "+ln(k)/2 when the Democrats do",
    },
    "efficiency_gap_terms": "in PlanScore's orientation: -ours - equal_turnout = "
                            "turnout_term (tau - S) + threshold_term (at most k/T)",
    "gerrychain_wasted_vote_gap": "positive favours D; GerryChain's wasted_votes, "
                                  "which wastes a winner's votes above half the "
                                  "district's total; within k/T of ours",
}


def fetch(plan_id: str, sha256: str) -> dict:
    """PlanScore's scored plan, refused unless it is the file that was pinned."""
    url = URL.format(id=plan_id)
    with urllib.request.urlopen(url, timeout=60) as response:
        body = response.read()
    digest = hashlib.sha256(body).hexdigest()
    if digest != sha256:
        raise ValueError(
            f"{url} no longer matches its pin (sha256 {digest}, pinned "
            f"{sha256}). PlanScore may have re-scored the plan. Read the new "
            "file and re-pin it deliberately; a changed input must not pass "
            "as the same check."
        )
    return json.loads(body)


def race_votes(index: dict, race: str) -> tuple[dict, dict, dict]:
    """``(plan, dem, rep)`` with each district as its own unit, in whole votes."""
    plan, dem, rep = {}, {}, {}
    for district in index["districts"]:
        unit = f"district-{district['number']}"
        plan[unit] = int(district["number"])
        dem[unit] = round(district["totals"][f"{race} - DEM"])
        rep[unit] = round(district["totals"][f"{race} - REP"])
    return plan, dem, rep


def equal_turnout_gap(dem_seat_share: float, dem_vote_share: float) -> float:
    """PlanScore's efficiency gap, positive for the Democrats.

    ``(S - 1/2) - 2(V - 1/2)``: what the wasted-vote gap reduces to when every
    district casts the same number of votes. ``calculate_EG`` in
    :data:`PLANSCORE_SOURCE`.
    """
    low, high = PLANSCORE_CLAMP
    if not low <= dem_vote_share <= high:
        raise ValueError(
            f"statewide D share {dem_vote_share:.4f} is outside {PLANSCORE_CLAMP}, "
            "where PlanScore swings the vote before computing the gap; this "
            "function does not reproduce that"
        )
    return (dem_seat_share - 0.5) - 2 * (dem_vote_share - 0.5)


# PlanScore's other three definitions, re-implemented from the formulas in
# PLANSCORE_SOURCE -- sign, scale and tie rules included -- so the conversions
# can be checked without running fetched code. None of PlanScore's code is
# copied: its repository states no licence. Each takes district totals in
# district order and is positive for the Democrats, as PlanScore's is.

def planscore_mean_median(dem: list[float], rep: list[float]) -> float:
    """``calculate_MMD``: median minus mean of the district D shares."""
    shares = sorted(d / (d + r) for d, r in zip(dem, rep) if d + r > 0)
    return statistics.median(shares) - statistics.mean(shares)


def _swing(dem: list[float], rep: list[float], amount: float) -> tuple[list, list]:
    """``swing_vote``: every district's D share moved by ``amount``, totals kept."""
    kept = [(d, r) for d, r in zip(dem, rep) if d + r > 0]
    return ([(d / (d + r) + amount) * (d + r) for d, r in kept],
            [(r / (d + r) - amount) * (d + r) for d, r in kept])


def planscore_partisan_bias(dem: list[float], rep: list[float]) -> float:
    """``calculate_PB``: D seat share less D vote share at a uniform swing to 50%.

    A district tied after the swing is a Republican seat, as PlanScore counts it.
    """
    margin = (math.fsum(dem) - math.fsum(rep)) / (math.fsum(dem) + math.fsum(rep))
    dem50, rep50 = _swing(dem, rep, -margin / 2)
    seats = sum(1 for d, r in zip(dem50, rep50) if r < d)
    # fsum, not sum: the built-in rounds differently from Python 3.12 on, and
    # the committed record must not depend on which Python wrote it
    total50 = math.fsum(dem50) + math.fsum(rep50)
    return seats / len(dem50) - math.fsum(dem50) / total50


def planscore_declination(dem: list[float], rep: list[float]) -> float:
    """``calculate_D2``: Warrington's angle times ``-ln(k)/2``.

    A district at exactly 0.5 counts as Republican-won, and a sweep takes the
    extreme angle: +1 before scaling when the Republicans win every seat, -1
    when the Democrats do.
    """
    shares = [d / (d + r) for d, r in zip(dem, rep) if d + r > 0]
    k = len(shares)
    red = sorted(s for s in shares if s <= 0.5)
    blue = sorted(s for s in shares if s > 0.5)
    if not red:
        angle = -1.0
    elif not blue:
        angle = 1.0
    else:
        theta = math.atan((1 - 2 * statistics.mean(red)) * k / len(red))
        gamma = math.atan((2 * statistics.mean(blue) - 1) * k / len(blue))
        angle = 2.0 * (gamma - theta) / math.pi
    return -angle * math.log(k) / 2


def declination_in_planscore_convention(ours: float | None, dem_seats: int,
                                        k: int) -> float | None:
    """What PlanScore's declination should be, given ours, for ``k`` districts.

    Where ours is defined, ours converted. Where ours is undefined because one
    party wins every seat, PlanScore's convention for that sweep: that is a
    check of PlanScore's rule, not a measurement of ours, and the record keeps
    the two apart. None where ours is undefined for any other reason (a tied
    district), which PlanScore resolves differently.
    """
    if ours is not None:
        return -ours * math.log(k) / 2
    if dem_seats == 0:
        return -math.log(k) / 2
    if dem_seats == k:
        return math.log(k) / 2
    return None


def gerrychain_gap(dem: list[int], rep: list[int]) -> float:
    """The wasted-vote efficiency gap by GerryChain's own ``wasted_votes``,
    positive for the Democrats.

    An external reference for the wasted-vote count, which PlanScore does not
    publish: GerryChain (pinned in requirements.txt) wastes a winner's votes
    above half the district's total, where ``evaluate.partisan``'s default
    wastes those above a strict majority, so the two differ by at most ``k/T``.
    """
    wasted = [GERRYCHAIN.wasted_votes(d, r) for d, r in zip(dem, rep)]
    return math.fsum(w_r - w_d for w_d, w_r in wasted) / (sum(dem) + sum(rep))


def _close(a: float | None, b: float | None, tolerance: float) -> bool:
    return a is not None and b is not None and abs(a - b) <= tolerance


def compare_race(index: dict, race: str) -> dict:
    """Ours on PlanScore's totals for one race, beside PlanScore's convention.

    ``checks`` records each comparison this race must pass; :func:`check`
    turns every one that does not into a failure.
    """
    plan, dem, rep = race_votes(index, race)
    k = len(plan)
    dem_seats, _, tied = P.seat_counts(plan, dem, rep)
    if tied:
        raise ValueError(f"{race}: {tied} tied district(s); PlanScore counts a "
                         "tie as a Republican seat and this check does not model it")
    seat_share = dem_seats / k
    vote_share = P.statewide_dem_share(dem, rep)
    ours = P.all_metrics(plan, dem, rep)
    predicted = equal_turnout_gap(seat_share, vote_share)
    published = index["summary"].get(f"{race} Efficiency Gap")

    total = sum(dem.values()) + sum(rep.values())
    tau = sum(dem[u] + rep[u] for u in plan if dem[u] > rep[u]) / total
    difference = -ours["efficiency_gap"] - predicted
    turnout_term = tau - seat_share

    dem_list = [dem[u] for u in plan]
    rep_list = [rep[u] for u in plan]
    converted = {
        "efficiency_gap_wasted_votes": -ours["efficiency_gap"],
        "efficiency_gap_equal_turnout": predicted,
        "mean_median": -ours["mean_median"],
        "partisan_bias": ours["partisan_bias"],
        "declination": (None if ours["declination"] is None
                        else -ours["declination"] * math.log(k) / 2),
    }
    expected = dict(converted, declination=declination_in_planscore_convention(
        ours["declination"], dem_seats, k))
    external = gerrychain_gap(dem_list, rep_list)
    definitions = {
        "mean_median": planscore_mean_median(dem_list, rep_list),
        "partisan_bias": planscore_partisan_bias(dem_list, rep_list),
        "declination": planscore_declination(dem_list, rep_list),
    }
    checks = {
        "published_efficiency_gap": _close(predicted, published, PUBLISHED_ROUNDING),
        "efficiency_gap_identity": abs(difference - turnout_term) <= k / total + 1e-12,
        "external_wasted_vote_gap": abs(external + ours["efficiency_gap"])
                                    <= k / total + 1e-12,
    } | {f"definition_{m}": _close(expected[m], value, DEFINITION_TOLERANCE)
         for m, value in definitions.items()}
    return {
        "n_districts": k,
        "dem_seats": dem_seats,
        "dem_vote_share": vote_share,
        "tau": tau,
        "ours": ours,
        "ours_in_planscore_convention": converted,
        "planscore_definitions": definitions,
        "declination_compared_with": (
            "ours" if ours["declination"] is not None
            else "PlanScore's sweep convention: ours is undefined"),
        "gerrychain_wasted_vote_gap": external,
        "planscore_published_efficiency_gap": published,
        "efficiency_gap_terms": {
            "wasted_minus_equal_turnout": difference,
            "turnout_term": turnout_term,
            "threshold_term": difference - turnout_term,
        },
        "checks": checks,
    }


def compare_committed(state: str, race_record: dict, committed: dict) -> dict:
    """The Phase 2 report's values beside ours on PlanScore's totals."""
    keys = ("efficiency_gap", "mean_median", "partisan_bias", "declination")
    ours = race_record["ours"]
    differences = {}
    for key in keys:
        a, b = ours[key], committed[key]
        differences[key] = None if a is None or b is None else a - b
    return {
        "race": COMMITTED_RACE,
        "plan": ("exact: whole counties on both sides" if state == "IA" else
                 "approximate: the Phase 2 report's plan is whole VTDs (D-015), "
                 "PlanScore's is the enacted plan"),
        "committed": {key: committed[key] for key in keys + ("dem_seats",)},
        "on_planscore_totals": {key: ours[key] for key in keys}
                               | {"dem_seats": race_record["dem_seats"]},
        "differences": differences,
    }


def compactness(index: dict, committed: dict) -> dict:
    out = {}
    for name, key in (("polsby_popper", "Polsby-Popper"), ("reock", "Reock")):
        values = [d["compactness"][key] for d in index["districts"]]
        out[name] = {
            "planscore": {"mean": statistics.fmean(values),
                          "min": min(values), "max": max(values)},
            "committed": {stat: committed[f"{name}_{stat}"]
                          for stat in ("mean", "min", "max")},
        }
    return out


def check(indexes: dict[str, dict], report: dict) -> tuple[dict, list[str]]:
    """Every comparison, and every way the result fails to reproduce.

    Raises ValueError if the Phase 2 report describes another election: its
    values would then be compared with the wrong race.
    """
    failures: list[str] = []
    plans = {}
    for state, index in indexes.items():
        if report[state]["contest"] != COMMITTED_CONTEST:
            raise ValueError(
                f"{REPORT} is computed on {report[state]['contest']} for {state}, "
                f"not {COMMITTED_CONTEST}; it would be compared with the wrong race")
        plan_id, sha256 = PLANS[state]
        if index.get("commit_sha") != PLANSCORE_COMMIT:
            failures.append(f"{state}: scored by PlanScore commit "
                            f"{index.get('commit_sha')}, not the {PLANSCORE_COMMIT} "
                            "the re-implemented definitions follow")
        races = {}
        for race in RACES:
            if not all(f"{race} - {party}" in d["totals"] for d in index["districts"]
                       for party in ("DEM", "REP")):
                failures.append(f"{state} {race}: PlanScore's file has no totals")
                continue
            races[race] = compare_race(index, race)
            for name, passed in races[race]["checks"].items():
                if not passed:
                    failures.append(f"{state} {race}: {name} does not reproduce")
        committed = report[state]["partisan"]
        if COMMITTED_RACE in races:
            phase_2 = compare_committed(state, races[COMMITTED_RACE], committed)
            if state == "IA":
                if phase_2["on_planscore_totals"]["dem_seats"] != committed["dem_seats"]:
                    failures.append("IA: seats differ from the Phase 2 report")
                for key, diff in phase_2["differences"].items():
                    same_none = (phase_2["committed"][key] is None
                                 and phase_2["on_planscore_totals"][key] is None)
                    if not same_none and (diff is None or abs(diff) > SAME_PLAN_TOLERANCE):
                        failures.append(f"IA {key}: {diff} from the Phase 2 report "
                                        "on the same plan")
        else:
            phase_2 = None
        populations = {int(d["number"]): round(d["totals"]["Population 2020"])
                       for d in index["districts"]}
        spread = max(populations.values()) - min(populations.values())
        documented = ENACTED_POPULATIONS.get(state)
        difference = None
        if documented is not None:
            difference = {n: populations.get(n, 0) - documented.get(n, 0)
                          for n in sorted(populations.keys() | documented.keys())}
            accepted = POPULATION_MINUS_DOCUMENTED.get(state, dict.fromkeys(documented, 0))
            if difference != accepted:
                failures.append(
                    f"{state}: PlanScore's district populations less the enacted "
                    f"plan's are {difference}, not {accepted}")
        plans[state] = {
            "planscore_id": plan_id,
            "url": URL.format(id=plan_id),
            "sha256": sha256,
            "commit_sha": index.get("commit_sha"),
            "description": index["description"],
            "model_version": index.get("model_version"),
            "district_populations": populations,
            "population_spread": spread,
            "enacted_spread_documented": ENACTED_SPREAD.get(state),
            "population_minus_documented": difference,
            "races": races,
            "phase_2_report": phase_2,
            "compactness": compactness(index, report[state]["compactness"]),
        }
    return {
        "generated_by": "tools/check_planscore.py",
        "planscore_source": PLANSCORE_SOURCE,
        "conventions": CONVENTIONS,
        "note": ("metric values, statewide shares and district populations only; "
                 "no district vote counts are stored (CRITERIA.md section 9.1)"),
        "plans": plans,
    }, failures


def ensemble_location(state: str, phase_2: dict) -> dict:
    """Where the Phase 2 report's value and ours on PlanScore's totals sit in
    the state's v2 ensemble: the percentage of draws below each, by |metric|.

    This is what the approximation costs where it is used: Colorado's committed
    plan is whole VTDs (D-015), PlanScore's the enacted plan itself.
    """
    import experiment_2_tradeoffs as X
    spec = X.ensemble_spec(state, "v2")
    chains = X.chains_from_draws(spec, X.draws_path(spec.prefix, "v2"),
                                 rectangle=X.ENSEMBLES["v2"]["rectangle"][state])
    out = {"ensemble": f"{state} v2, {sum(len(c.rows) for c in chains):,} draws",
           "contest": COMMITTED_CONTEST}
    for metric in ("efficiency_gap", "mean_median"):
        draws = sorted(row[f"abs_{metric}@{COMMITTED_CONTEST}"]
                       for chain in chains for row in chain.rows)

        def below(value):
            value = abs(value)
            return 100 * (bisect.bisect_left(draws, value)
                          + bisect.bisect_right(draws, value)) / 2 / len(draws)
        out[metric] = {"committed": below(phase_2["committed"][metric]),
                       "on_planscore_totals": below(phase_2["on_planscore_totals"][metric])}
    return out


def _signed(value, places: int = 4) -> str:
    return "n/a" if value is None else f"{value:+.{places}f}"


def summary_lines(result: dict) -> list[str]:
    lines = []
    for state, plan in result["plans"].items():
        lines.append(f"{state}: {plan['description']} ({plan['planscore_id']}, "
                     f"scored by {str(plan['commit_sha'])[:7]}), spread "
                     f"{plan['population_spread']} persons"
                     + ("" if plan["population_minus_documented"] is None else
                        f", district populations minus documented "
                        f"{plan['population_minus_documented']}"))
        for race, r in plan["races"].items():
            conv, terms = r["ours_in_planscore_convention"], r["efficiency_gap_terms"]
            differ = [m for m in r["planscore_definitions"]
                      if not r["checks"][f"definition_{m}"]]
            lines.append(
                f"  {race}: {r['dem_seats']}/{r['n_districts']} D, "
                f"V {r['dem_vote_share']:.4f}, tau {r['tau']:.4f} | PlanScore EG "
                f"{_signed(r['planscore_published_efficiency_gap'])} = equal-turnout "
                f"{_signed(conv['efficiency_gap_equal_turnout'])} "
                f"{'ok' if r['checks']['published_efficiency_gap'] else 'NOT REPRODUCED'}"
                f" | wasted-vote {_signed(conv['efficiency_gap_wasted_votes'])} = "
                f"equal-turnout + tau - S {_signed(terms['turnout_term'])} + threshold "
                f"{_signed(terms['threshold_term'], 7)} "
                f"{'ok' if r['checks']['efficiency_gap_identity'] else 'NOT AN IDENTITY'}"
                f" | GerryChain {_signed(r['gerrychain_wasted_vote_gap'])} "
                f"{'ok' if r['checks']['external_wasted_vote_gap'] else 'DIFFERS'}"
                f" | MM, PB, D2 against PlanScore's definitions: "
                + ("ok" if not differ else "DIFFER: " + ", ".join(differ))
            )
        if plan["phase_2_report"]:
            diffs = plan["phase_2_report"]["differences"]
            lines.append("  vs Phase 2 report (" + plan["phase_2_report"]["plan"] + "): "
                         + ", ".join(f"{k} {_signed(v, 6)}" for k, v in diffs.items()))
    location = result.get("ensemble_location")
    if location:
        lines.append(
            f"located in {location['ensemble']} ({location['contest']}): % of draws "
            "below, Phase 2 report -> PlanScore's totals: "
            + ", ".join(f"|{m}| {location[m]['committed']:.1f} -> "
                        f"{location[m]['on_planscore_totals']:.1f}"
                        for m in ("efficiency_gap", "mean_median")))
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    try:
        indexes = {state: fetch(*PLANS[state]) for state in PLANS}
        result, failures = check(indexes, json.loads(REPORT.read_text()))
        phase_2 = result["plans"][APPROXIMATED]["phase_2_report"]
        if phase_2:
            result["ensemble_location"] = ensemble_location(APPROXIMATED, phase_2)
    except (ValueError, OSError) as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 1
    for line in summary_lines(result):
        print(line)
    if failures:
        for failure in failures:
            print("FAIL:", failure, file=sys.stderr)
        print(f"not written: {args.out} keeps the last record that passed",
              file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
