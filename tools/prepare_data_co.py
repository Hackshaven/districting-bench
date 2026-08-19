#!/usr/bin/env python3
"""Build data/processed/co_* from the raw Colorado downloads.

Colorado congressional districts are NOT built from whole counties, so the unit is
the voting district (VTD). This is the precinct-level plumbing prompt.md deferred
until Iowa closed the loop end to end; see DECISIONS D-014.

Neutral outputs only. The partisan layer needs VEST, which is fetched separately.
"""
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

RAW, OUT = Path("data/raw"), Path("data/processed")
STATE_FP, CRS = "08", 5070   # NAD83 Conus Albers, equal-area (D-005)


def neutral():
    # VTD population from PL 94-171: SUMLEV 700 is the state-VTD summary level.
    vtds, pops = {}, {}
    with (RAW / "cogeo2020.pl").open(encoding="latin-1") as fh:
        for line in fh:
            f = line.rstrip("\n").split("|")
            if f[2] == "700":
                vtds[f[7]] = (f[9], f[87])
    with (RAW / "co000012020.pl").open(encoding="latin-1") as fh:
        for line in fh:
            f = line.rstrip("\n").split("|")
            if f[4] in vtds:
                pops[f[4]] = int(f[5])
    units = pd.DataFrame(
        [(vtds[k][0], vtds[k][1], pops[k]) for k in vtds if k in pops],
        columns=["GEOID", "NAME", "pop"],
    ).sort_values("GEOID").reset_index(drop=True)
    print(f"PL 94-171 VTD records: {len(units)}  population {units['pop'].sum():,}")

    geo = gpd.read_file(RAW / "tl_2020_08_vtd20.shp")
    gcol = "GEOID20" if "GEOID20" in geo.columns else "GEOID"
    geo = geo[[gcol, "geometry"]].rename(columns={gcol: "GEOID"}).to_crs(CRS)
    # PL GEOIDs for VTDs carry a summary-level prefix; match on the trailing 11 chars
    units["GEOID"] = units.GEOID.str[-11:]
    gdf = gpd.GeoDataFrame(units.merge(geo, on="GEOID", how="inner"),
                           geometry="geometry", crs=CRS)
    print(f"joined to geometry: {len(gdf)} of {len(units)} units")
    assert len(gdf) > 2500, "VTD join lost too many units"

    # rook adjacency
    adj = {g: [] for g in gdf.GEOID}
    sindex = gdf.sindex
    for i, row in gdf.iterrows():
        for j in sindex.query(row.geometry, predicate="touches"):
            if j <= i:
                continue
            if row.geometry.boundary.intersection(gdf.geometry[j].boundary).length > 0:
                adj[gdf.GEOID[i]].append(gdf.GEOID[j])
                adj[gdf.GEOID[j]].append(gdf.GEOID[i])
    n_edges = sum(len(v) for v in adj.values()) // 2

    import networkx as nx
    g = nx.Graph(); g.add_nodes_from(adj)
    for a, bs in adj.items():
        for b in bs: g.add_edge(a, b)
    comps = nx.number_connected_components(g)
    sizes = sorted((len(c) for c in nx.connected_components(g)), reverse=True)[:5]
    print(f"rook edges {n_edges}  components {comps}  largest {sizes}")

    cd = gpd.read_file(RAW / "tl_2022_08_cd118.shp").to_crs(CRS)
    print(f"CD118 districts: {sorted(cd.CD118FP.tolist())}")
    pts = gdf.copy(); pts["geometry"] = gdf.representative_point()
    asg = gpd.sjoin(pts, cd[["CD118FP", "geometry"]], predicate="within", how="left")
    enacted = pd.DataFrame({"GEOID": gdf.GEOID.values,
                            "district": asg.CD118FP.values})
    unassigned = int(enacted.district.isna().sum())
    print(f"unassigned units: {unassigned}")
    enacted = enacted.dropna()
    enacted["district"] = enacted.district.astype(int)

    OUT.mkdir(parents=True, exist_ok=True)
    gdf[["GEOID", "NAME", "pop"]].to_csv(OUT / "co_units.csv", index=False)
    gdf.to_file(OUT / "co_units.gpkg", driver="GPKG")
    (OUT / "co_adjacency.json").write_text(
        json.dumps({k: sorted(v) for k, v in sorted(adj.items())}, indent=0))
    enacted.to_csv(OUT / "co_enacted_cd118.csv", index=False)

    ideal = gdf["pop"].sum() / len(cd)
    dev = enacted.merge(gdf[["GEOID", "pop"]], on="GEOID").groupby("district")["pop"].sum()
    print(f"\nideal district: {ideal:,.2f}")
    print(dev.to_string())
    print(f"max-min spread: {dev.max()-dev.min():,} persons ({100*(dev.max()-dev.min())/ideal:.4f}% of ideal)")
    return gdf


if __name__ == "__main__":
    neutral()
