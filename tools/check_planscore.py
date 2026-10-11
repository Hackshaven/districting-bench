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

Every difference found is a definition, not an error, and each one is stated
by reproducing PlanScore's number from this repository's:

* **Efficiency gap: two formulas, not two signs.** PlanScore computes
  ``(S - 1/2) - 2(V - 1/2)`` -- seat share and statewide vote share only, the
  equal-turnout form -- positive for the Democrats (``calculate_EG`` in
  :data:`PLANSCORE_SOURCE`). ``evaluate.partisan`` counts wasted votes district
  by district, as CRITERIA.md section 5.1 defines the metric, positive for the
  Republicans. The two agree only when every district casts the same number of
  votes. Otherwise they differ by ``tau - S``, the share of votes cast in
  districts the Democrats won less the share of seats they won.
* **Mean-median**: the same quantity, opposite sign (PlanScore: median - mean).
* **Partisan bias**: the same quantity, same sign.
* **Declination**: PlanScore publishes Warrington's angle rescaled by
  ``ln(k)/2`` and negated, and gives a one-party sweep the extreme value
  where ``evaluate.partisan.declination`` returns None.

Only the efficiency gap is compared against a *published* PlanScore number,
because it is the only metric PlanScore computes on actual past results. Its
headline metrics are averages over elections simulated from its own vote
model, so no input here could reproduce them. The other three definitions were
checked once by running PlanScore's own functions on the same totals; that
check is recorded in ``docs/progress.md``, and this script does not execute
PlanScore's code.

**No election data is committed.** PlanScore's files are fetched at run time
and pinned by sha256, and ``docs/cross-checks/planscore.json`` carries metric
values and statewide shares only, never district vote counts: CRITERIA.md
section 9.1 commits nothing under an unstated licence, and PlanScore's files
state none.

Run::

    PYTHONPATH=src python tools/check_planscore.py

Exits non-zero if a fetched file no longer matches its pin, or if a published
PlanScore number cannot be reproduced from this repository's under the
definitions above. See D-040.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from evaluate import partisan as P   # noqa: E402

OUT = ROOT / "docs" / "cross-checks" / "planscore.json"
REPORT = ROOT / "docs" / "phase-2" / "phase-2-report.json"
URL = "https://planscore.s3.amazonaws.com/uploads/{id}/index.json"

#: The PlanScore source whose definitions the conversions below follow.
PLANSCORE_SOURCE = (
    "https://github.com/PlanScore/planscore/blob/"
    "3f866f96c8f3dccdfb6e88ebd5dd9e61f0e532c2/planscore/score.py"
)

#: state -> (PlanScore upload id, sha256 of its index.json when pinned).
#: PlanScore's own titles call the Iowa plan a draft. It is identified as the
#: enacted map by its district populations, which match docs/FEASIBILITY.md
#: section 4 (see :data:`ENACTED_SPREAD`), and by its 2020 presidential metrics,
#: which match the Phase 2 report's.
PLANS = {
    "IA": ("20251203T023554.470826564Z",
           "3b6e73c849712673330e08df323f258292dcf23cb387fafdf9b8b0dabac2092d"),
    "CO": ("20251203T023818.696378561Z",
           "f2f46c823d2941b3fb38215c589abbaa056286fb89ef3f1de202fc5eb77fde4e"),
}

#: The enacted plans' max-min population spread as documented elsewhere in the
#: repository: Iowa from docs/FEASIBILITY.md section 4. Colorado has no entry,
#: because this repository represents its plan only approximately (D-015).
ENACTED_SPREAD = {"IA": 94}

RACES = ("US President 2020", "US Senate 2020", "US President 2016", "US Senate 2016")

#: The Phase 2 report's contest. Its values are compared with ours on
#: PlanScore's totals for the same race.
COMMITTED_RACE = "US President 2020"

#: PlanScore publishes its per-election gaps to four decimal places.
PUBLISHED_ROUNDING = 5e-5

#: How closely ours on PlanScore's totals must match the Phase 2 report where
#: both describe the same plan exactly (Iowa: whole counties). PlanScore's
#: statewide totals differ from the certified ones by a few votes.
SAME_PLAN_TOLERANCE = 1e-4

#: PlanScore's ``calculate_EG`` swings the statewide share into this band
#: before computing. :func:`equal_turnout_gap` does not, so it refuses outside.
PLANSCORE_CLAMP = (0.25, 0.75)

#: Shown on every record so a reader of the JSON alone knows which way is which.
CONVENTIONS = {
    "ours": {m: f"positive favours {P.FAVOURS[m]}" for m in P.METRICS},
    "planscore": {
        "efficiency_gap": "positive favours D; (S - 1/2) - 2(V - 1/2), the "
                          "equal-turnout form",
        "mean_median": "positive favours D; median - mean of D shares",
        "partisan_bias": "positive favours D; same definition as ours",
        "declination": "positive favours D; -(Warrington's angle) * ln(k) / 2, "
                       "and +/-ln(k)/2 when one party wins every seat",
    },
}


def fetch(plan_id: str, sha256: str) -> dict:
    """PlanScore's scored plan, refused unless it is the file that was pinned."""
    url = URL.format(id=plan_id)
    with urllib.request.urlopen(url, timeout=60) as response:
        body = response.read()
    digest = hashlib.sha256(body).hexdigest()
    if digest != sha256:
        raise SystemExit(
            f"{url} no longer matches its pin (sha256 {digest}, pinned "
            f"{sha256}). PlanScore may have re-scored the plan. Read the new "
            "file and re-pin it deliberately; a changed input must not pass "
            "as the same check."
        )
    return json.loads(body)


def race_votes(index: dict, race: str) -> tuple[dict, dict, dict]:
    """``(plan, dem, rep)`` with each district as its own unit."""
    plan, dem, rep = {}, {}, {}
    for district in index["districts"]:
        unit = f"district-{district['number']}"
        plan[unit] = int(district["number"])
        dem[unit] = district["totals"][f"{race} - DEM"]
        rep[unit] = district["totals"][f"{race} - REP"]
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


def compare_race(index: dict, race: str) -> dict:
    """Ours on PlanScore's totals for one race, beside PlanScore's convention."""
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
    declination = ours["declination"]
    return {
        "n_districts": k,
        "dem_seats": dem_seats,
        "dem_vote_share": vote_share,
        "ours": ours,
        "ours_in_planscore_convention": {
            "efficiency_gap_wasted_votes": -ours["efficiency_gap"],
            "efficiency_gap_equal_turnout": predicted,
            "mean_median": -ours["mean_median"],
            "partisan_bias": ours["partisan_bias"],
            "declination": (None if declination is None
                            else -declination * math.log(k) / 2),
        },
        "planscore_published_efficiency_gap": published,
        "published_reproduced": (published is not None
                                 and abs(predicted - published) <= PUBLISHED_ROUNDING),
        "turnout_term": -ours["efficiency_gap"] - predicted,
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
    """Every comparison, and every way the result fails to reproduce."""
    failures: list[str] = []
    plans = {}
    for state, index in indexes.items():
        plan_id, sha256 = PLANS[state]
        races = {race: compare_race(index, race) for race in RACES}
        for race, record in races.items():
            if not record["published_reproduced"]:
                failures.append(
                    f"{state} {race}: PlanScore publishes "
                    f"{record['planscore_published_efficiency_gap']}, the "
                    "equal-turnout form of ours gives "
                    f"{record['ours_in_planscore_convention']['efficiency_gap_equal_turnout']:+.6f}"
                )
        committed = report[state]["partisan"]
        record = compare_committed(state, races[COMMITTED_RACE], committed)
        if state == "IA":
            if record["on_planscore_totals"]["dem_seats"] != committed["dem_seats"]:
                failures.append(f"IA: seats differ from the Phase 2 report")
            for key, diff in record["differences"].items():
                same_none = (record["committed"][key] is None
                             and record["on_planscore_totals"][key] is None)
                if not same_none and (diff is None or abs(diff) > SAME_PLAN_TOLERANCE):
                    failures.append(f"IA {key}: {diff} from the Phase 2 report "
                                    "on the same plan")
        pops = [d["totals"]["Population 2020"] for d in index["districts"]]
        spread = round(max(pops) - min(pops))
        if state in ENACTED_SPREAD and spread != ENACTED_SPREAD[state]:
            failures.append(f"{state}: PlanScore's plan spreads {spread} persons, "
                            f"the enacted plan {ENACTED_SPREAD[state]}")
        plans[state] = {
            "planscore_id": plan_id,
            "url": URL.format(id=plan_id),
            "sha256": sha256,
            "description": index["description"],
            "model_version": index.get("model_version"),
            "population_spread": spread,
            "enacted_spread_documented": ENACTED_SPREAD.get(state),
            "races": races,
            "phase_2_report": record,
            "compactness": compactness(index, report[state]["compactness"]),
        }
    return {
        "generated_by": "tools/check_planscore.py",
        "planscore_source": PLANSCORE_SOURCE,
        "conventions": CONVENTIONS,
        "note": ("metric values and statewide shares only; no district vote "
                 "counts are stored (CRITERIA.md section 9.1)"),
        "plans": plans,
    }, failures


def summary_lines(result: dict) -> list[str]:
    lines = []
    for state, plan in result["plans"].items():
        lines.append(f"{state}: {plan['description']} ({plan['planscore_id']}), "
                     f"spread {plan['population_spread']} persons")
        for race, r in plan["races"].items():
            conv = r["ours_in_planscore_convention"]
            lines.append(
                f"  {race}: {r['dem_seats']}/{r['n_districts']} D, V {r['dem_vote_share']:.4f} | "
                f"PlanScore EG {r['planscore_published_efficiency_gap']:+.4f} "
                f"= equal-turnout {conv['efficiency_gap_equal_turnout']:+.4f} "
                f"{'ok' if r['published_reproduced'] else 'NOT REPRODUCED'} | "
                f"wasted-vote {conv['efficiency_gap_wasted_votes']:+.4f}, "
                f"turnout term {r['turnout_term']:+.4f}"
            )
        diffs = plan["phase_2_report"]["differences"]
        lines.append("  vs Phase 2 report (" + plan["phase_2_report"]["plan"] + "): "
                     + ", ".join(f"{k} {'n/a' if v is None else f'{v:+.6f}'}"
                                 for k, v in diffs.items()))
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    indexes = {state: fetch(*PLANS[state]) for state in PLANS}
    report = json.loads(REPORT.read_text())
    result, failures = check(indexes, report)
    for line in summary_lines(result):
        print(line)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print("wrote", args.out)
    for failure in failures:
        print("FAIL:", failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
