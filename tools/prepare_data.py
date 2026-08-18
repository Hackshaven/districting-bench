#!/usr/bin/env python3
"""Build data/processed/ from the raw downloads. See docs/ARCHITECTURE.md section 2.

Neutral outputs (units, adjacency, enacted plan) and the partisan output
(elections) are written by separate functions that share no code path, so that
nothing in the neutral pipeline can pick up an election column by accident.

Run from the repository root, after feasibility/fetch_data.sh.
"""
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

RAW, OUT = Path("data/raw"), Path("data/processed")
STATE_FP, CRS = "19", 5070  # NAD83 Conus Albers, equal-area (DECISIONS D-005)


def neutral() -> gpd.GeoDataFrame:
    """Units, adjacency, enacted plan. Population and geometry only."""
    # population from PL 94-171
    counties, pops = {}, {}
    with (RAW / "iageo2020.pl").open(encoding="latin-1") as fh:
        for line in fh:
            f = line.rstrip("\n").split("|")
            if f[2] == "050":
                counties[f[7]] = (f[9], f[87])
    with (RAW / "ia000012020.pl").open(encoding="latin-1") as fh:
        for line in fh:
            f = line.rstrip("\n").split("|")
            if f[4] in counties:
                pops[f[4]] = int(f[5])

    units = pd.DataFrame(
        [(counties[k][0], counties[k][1], pops[k]) for k in counties if k in pops],
        columns=["GEOID", "NAME", "pop"],
    ).sort_values("GEOID").reset_index(drop=True)

    geo = gpd.read_file(RAW / "tl_2020_us_county.shp")
    geo = geo[geo.STATEFP == STATE_FP][["GEOID", "geometry"]].to_crs(CRS)
    gdf = gpd.GeoDataFrame(units.merge(geo, on="GEOID"), geometry="geometry", crs=CRS)
    assert len(gdf) == 99 and gdf["pop"].sum() == 3_190_369, "unit build failed"

    # rook adjacency: shared boundary of positive length (DECISIONS D-004)
    adj = {g: [] for g in gdf.GEOID}
    sindex = gdf.sindex
    for i, row in gdf.iterrows():
        for j in sindex.query(row.geometry, predicate="touches"):
            if j <= i:
                continue
            if row.geometry.boundary.intersection(gdf.geometry[j]. boundary).length > 0:
                adj[gdf.GEOID[i]].append(gdf.GEOID[j])
                adj[gdf.GEOID[j]].append(gdf.GEOID[i])
    n_edges = sum(len(v) for v in adj.values()) // 2
    assert n_edges == 222, f"expected 222 rook edges, got {n_edges}"

    # enacted plan, by containment of each unit's representative point
    cd = gpd.read_file(RAW / "tl_2022_19_cd118.shp").to_crs(CRS)
    pts = gdf.copy(); pts["geometry"] = gdf.representative_point()
    asg = gpd.sjoin(pts, cd[["CD118FP", "geometry"]], predicate="within", how="left")
    assert asg.CD118FP.notna().all(), "unassigned unit"
    enacted = pd.DataFrame({"GEOID": gdf.GEOID,
                            "district": asg.CD118FP.astype(int).values})

    OUT.mkdir(parents=True, exist_ok=True)
    units.to_csv(OUT / "ia_units.csv", index=False)
    gdf.to_file(OUT / "ia_units.gpkg", driver="GPKG")
    (OUT / "ia_adjacency.json").write_text(
        json.dumps({k: sorted(v) for k, v in sorted(adj.items())}, indent=0))
    enacted.to_csv(OUT / "ia_enacted_cd118.csv", index=False)
    print(f"neutral: 99 units, {n_edges} rook edges, {gdf['pop'].sum():,} persons")
    return gdf


def partisan() -> None:
    """Election results, aggregated from VEST precincts to counties.

    Kept in its own function with its own read, so no neutral output can inherit
    a column from this frame. Nothing here is importable by src/generate.
    """
    v = gpd.read_file(RAW / "vest" / "ia_2020.shp")
    cols = [c for c in v.columns if c.startswith(("G20PRE", "G20USS"))]
    by_name = v.groupby("COUNTY")[cols].sum().reset_index()

    def norm(x):
        # PL 94-171 NAME is "Adair County"; VEST COUNTY is "Adair".
        return (x.str.upper().str.replace(r"\s+COUNTY$", "", regex=True)
                 .str.replace(r"[^A-Z]", "", regex=True))

    units = pd.read_csv(OUT / "ia_units.csv", dtype={"GEOID": str})
    key = units.assign(k=norm(units.NAME))
    by_name["k"] = norm(by_name.COUNTY)
    merged = key.merge(by_name, on="k", how="left")
    missing = merged[merged[cols[0]].isna()].NAME.tolist()
    assert not missing, f"unmatched counties: {missing}"

    out = merged[["GEOID"] + cols].copy()
    assert int(out.G20PRERTRU.sum()) == 897_672, "VEST R total mismatch"
    assert int(out.G20PREDBID.sum()) == 759_061, "VEST D total mismatch"
    out.to_csv(OUT / "ia_elections.csv", index=False)
    print(f"partisan: {len(out)} units, {len(cols)} election columns, "
          f"two-party D share {out.G20PREDBID.sum()/(out.G20PREDBID.sum()+out.G20PRERTRU.sum()):.4f}")


if __name__ == "__main__":
    neutral()
    partisan()
