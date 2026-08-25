#!/usr/bin/env python3
"""Assign units to municipalities — the layer Phase 2's split metrics need.

``prompt.md`` Phase 2 names "county and municipality splits". County splits were
already available; municipality splits were not, because no municipality layer
existed on disk.

Source
------
2020 TIGER/Line Places, per state:
``https://www2.census.gov/geo/tiger/TIGER2020/PLACE/tl_2020_{STATE}_place.zip``
(Iowa 19, Colorado 08). US Census Bureau TIGER/Line files are in the **public
domain** — works of the United States Government, 17 U.S.C. section 105 — and the
Census Bureau places no restriction on redistribution.

A **Place** is an incorporated municipality (or a census designated place), which
is what "municipality" means in redistricting practice. It is deliberately not
County Subdivisions: those tile the state completely, so every unit would belong
to one and the layer would behave like a second county layer rather than like
municipalities.

Why this layer is partial, and why that is correct
--------------------------------------------------
Places do not cover a state. Rural units belong to no municipality at all, and
``src/evaluate/administrative.py`` already treats that as the normal state of a
municipal layer rather than as missing data: a unit mapped to ``None`` is *in no
subdivision* and is excluded from the split counts. That is why the module refuses
a partial layer for ``ballot_styles(by_subdivision=True)`` — every ballot is
printed by somebody — while accepting it for splits.

Assignment rule
---------------
A unit is assigned to the Place holding the **largest share of its area**, and
only when that share exceeds :data:`MIN_SHARE`. A VTD that clips the corner of a
city is not in that city for redistricting purposes, and assigning it there would
manufacture municipality splits no map drawer would recognise.

This is an approximation and is recorded as one: units are whole VTDs, so a
municipality boundary running through a VTD is invisible, exactly as D-015 records
for Colorado's county geography. The alternative — areal interpolation of
population — would put a population estimate inside a criterion that is meant to
be a hard count.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

#: A unit must have at least this share of its area inside a Place to be assigned
#: to it. Below this the overlap is a boundary artifact, not membership.
MIN_SHARE = 0.50

STATES = {"ia": "19", "co": "08"}

#: Layers built by this script. Places are the municipality layer; the two state
#: legislative layers exist so that the ballot style count stops being degenerate.
#: CRITERIA.md section 7 defines a ballot style as the unique district tuple a
#: unit sits in, so with a single congressional layer it is identically the
#: district count -- 4 for Iowa, forever. Overlay a state house and senate plan and
#: it becomes what an election office actually has to print.
#: ``name -> (TIGER directory, shapefile suffix, partial)``. ``partial`` is the
#: distinction that matters and it is not cosmetic.
#:
#: A **membership** layer (municipalities) is genuinely partial: a rural unit
#: belongs to no city, and forcing it into the nearest one would invent
#: membership. The area floor applies, and unassigned units are ``None``.
#:
#: A **districting** layer (state house, state senate) is not partial: every
#: voter is in exactly one state house district, and a ballot style is the tuple
#: of districts a voter sits in -- undefined if any component is missing. The
#: floor must NOT apply, or a unit whose area is split 40/35/25 across three
#: districts comes back unassigned and the overlay is refused for not covering
#: the same units. Six Iowa counties do exactly that.
LAYERS = {
    "municipalities": ("PLACE", "place", True),
    "statehouse": ("SLDL", "sldl", False),
    "statesenate": ("SLDU", "sldu", False),
}


def build(prefix: str, fips: str, shapefile: str,
          partial: bool = True) -> dict[str, str | None]:
    """``{unit: parent}`` by largest-area-share assignment.

    ``partial=True`` returns ``None`` where the best share is below
    :data:`MIN_SHARE` — correct for a membership layer, where belonging to
    nothing is a real answer. ``partial=False`` always takes the largest share —
    correct for a districting layer, where every unit is in exactly one district
    and "unassigned" is not a state a voter can be in.
    """
    units = gpd.read_file(PROCESSED / f"{prefix}_units.gpkg")
    parents = gpd.read_file(RAW / f"tl_2020_{fips}_{shapefile}.shp").to_crs(units.crs)

    units = units[["GEOID", "geometry"]].copy()
    units["unit_area"] = units.geometry.area

    overlap = gpd.overlay(
        units,
        parents[["GEOID", "geometry"]].rename(columns={"GEOID": "place"}),
        how="intersection", keep_geom_type=True)
    overlap["share"] = overlap.geometry.area / overlap["unit_area"]

    best = (overlap.sort_values("share", ascending=False)
                   .drop_duplicates(subset="GEOID", keep="first"))
    assigned = {
        row.GEOID: (row.place if (not partial or row.share >= MIN_SHARE) else None)
        for row in best.itertuples()
    }
    return {geoid: assigned.get(geoid) for geoid in units["GEOID"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", action="append", choices=sorted(STATES))
    args = parser.parse_args(argv)

    for prefix in (args.state or sorted(STATES)):
        for layer, (_, shapefile, partial) in LAYERS.items():
            mapping = build(prefix, STATES[prefix], shapefile, partial)
            path = PROCESSED / f"{prefix}_{layer}.json"
            path.write_text(json.dumps(mapping, indent=1, sort_keys=True))
            inside = sum(1 for v in mapping.values() if v)
            distinct = len({v for v in mapping.values() if v})
            print(f"{prefix}/{layer}: {len(mapping)} units, {inside} assigned "
                  f"({100 * inside / len(mapping):.1f}%), {distinct} distinct "
                  f"-> {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
