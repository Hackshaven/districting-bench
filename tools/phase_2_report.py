#!/usr/bin/env python3
"""Phase 2 — every metric, side by side, for a state's enacted plan.

``prompt.md`` Phase 2: implement every metric fully, do not optimize toward any of
them, and *"report all metrics side by side, always, with disagreements between
them highlighted rather than resolved."*

This is the entry point that does that. It scores the enacted congressional plan
of a state on every partisan, compactness and administrative metric the project
implements, overlays the state house and senate plans so that the ballot style
count is not degenerate, counts municipality splits, and prints the
disagreements last.

It computes no score and ranks nothing. ``prompt.md``: *"If you find yourself
writing a function called `fairness_score()` that returns one number, stop."*
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from evaluate import elections as E, plan as EP, report as R   # noqa: E402
from generate import units as GU                               # noqa: E402

PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "docs" / "phase-2"
STATES = ("ia", "co")
DISTRICTING = ("statehouse", "statesenate")


def build(prefix: str, contest: str = "G20PRE") -> dict:
    geometry = GU.load_geometry(PROCESSED / f"{prefix}_units.gpkg")
    adjacency = GU.load_adjacency(PROCESSED / f"{prefix}_adjacency.json")
    elections = E.load_elections(PROCESSED / f"{prefix}_elections.csv")
    dem_col, rep_col = E.two_party_columns(elections, contest)
    dem, rep = E.two_party(elections, dem_col, rep_col)
    enacted = EP.load_plan(PROCESSED / f"{prefix}_enacted_cd118.csv")

    # Colorado's units table carries no county column, so the county layer is
    # passed explicitly. D-022; without it every county-splits figure is zero.
    populations = EP.populations(PROCESSED / f"{prefix}_units.csv")
    units = ({geoid: geoid[:5] for geoid in populations} if prefix == "co"
             else EP.load_units(PROCESSED / f"{prefix}_units.csv"))

    def layer(name):
        path = PROCESSED / f"{prefix}_{name}.json"
        return json.loads(path.read_text()) if path.exists() else None

    subdivision_layers = {}
    municipalities = layer("municipalities")
    if municipalities is not None:
        subdivision_layers["municipality"] = municipalities

    districting_layers = {name: layer(name) for name in DISTRICTING
                          if layer(name) is not None}

    return R.score_plan(
        enacted, geometry=geometry, adjacency=adjacency, units=units,
        dem=dem, rep=rep,
        # The electorate is two-party votes cast in this contest. CRITERIA.md
        # section 7 leaves the choice to the caller; it is stated here rather
        # than defaulted so a reader knows what the denominator counts.
        electorate={geoid: dem[geoid] + rep[geoid] for geoid in dem},
        subdivision_layers=subdivision_layers or None,
        districting_layers=districting_layers or None,
        contest=contest,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", action="append", choices=STATES)
    parser.add_argument("--contest", default="G20PRE")
    parser.add_argument("--out", default=str(OUT / "phase-2-report.json"))
    args = parser.parse_args(argv)

    reports = {}
    for prefix in (args.state or STATES):
        built = build(prefix, args.contest)
        reports[prefix.upper()] = built
        print(f"===== {prefix.upper()} enacted congressional plan =====")
        for line in R.summary_lines(built):
            print(line)
        print()

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reports, indent=2, default=str))
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
