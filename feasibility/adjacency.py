"""Build and interrogate the Iowa 99-county adjacency graph.

Geometry: TIGER/Line 2020 counties (tl_2020_us_county), STATEFP 19.
Cross-check: Census County Adjacency File (county_adjacency.txt).

Reports connectivity, components, rook-vs-queen differences, and any pair whose
shared boundary is a river or lake rather than land.
"""
import itertools
import json
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

gdf = gpd.read_file(RAW / "tl_2020_us_county.shp")
ia = gdf[gdf.STATEFP == "19"].copy().sort_values("GEOID").reset_index(drop=True)
print(f"Iowa counties in TIGER: {len(ia)}")
print(f"source CRS: {ia.crs}")

# Project to Iowa's official planar CRS before any metric work.
# EPSG:26975 = NAD83 / Iowa North (meters). Areas/perimeters in degrees are meaningless.
iap = ia.to_crs(26975)

pop = pd.read_csv(OUT / "ia_county_pop.csv", dtype={"GEOID": str})
iap = iap.merge(pop, on="GEOID", how="left", suffixes=("", "_pl"))
assert iap.P0010001.notna().all(), "population join incomplete"

# --- adjacency: rook (shared boundary of positive length) vs queen (any touch) ---
sindex = iap.sindex
rook, queen, point_only = nx.Graph(), nx.Graph(), []
for g in iap.GEOID:
    rook.add_node(g); queen.add_node(g)

for i, row in iap.iterrows():
    for j in sindex.query(row.geometry, predicate="touches"):
        if j <= i:
            continue
        a, b = iap.GEOID[i], iap.GEOID[j]
        shared = row.geometry.boundary.intersection(iap.geometry[j].boundary)
        queen.add_edge(a, b)
        if shared.length > 0:
            rook.add_edge(a, b, shared_m=shared.length)
        else:
            point_only.append((a, b, iap.NAME[i], iap.NAME[j]))

print(f"\nrook  edges: {rook.number_of_edges()}")
print(f"queen edges: {queen.number_of_edges()}")
print(f"connected (rook): {nx.is_connected(rook)}  components: {nx.number_connected_components(rook)}")
print(f"connected (queen): {nx.is_connected(queen)}  components: {nx.number_connected_components(queen)}")
print(f"\npairs touching at a single point only (queen-but-not-rook): {len(point_only)}")
for a, b, na, nb in point_only:
    print(f"   {na} ({a}) -- {nb} ({b})")

degs = dict(rook.degree())
print(f"\ndegree: min {min(degs.values())} max {max(degs.values())} mean {sum(degs.values())/len(degs):.2f}")
print("lowest-degree counties:",
      *[f"{iap.set_index('GEOID').NAME[g]} ({d})"
        for g, d in sorted(degs.items(), key=lambda kv: kv[1])[:5]], sep="\n   ")

# --- shortest shared borders: candidates for water-only or sliver adjacency ---
short = sorted(rook.edges(data=True), key=lambda e: e[2]["shared_m"])[:8]
name = iap.set_index("GEOID").NAME
print("\nshortest shared borders (metres):")
for a, b, d in short:
    print(f"   {d['shared_m']:10.1f}  {name[a]} -- {name[b]}")

# --- cross-check against the Census County Adjacency File ---
census_pairs = set()
cur = None
with (RAW / "county_adjacency.txt").open(encoding="latin-1") as fh:
    for line in fh:
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 4:
            if parts[0].strip():
                cur = parts[1].strip('" ')
            nb = parts[3].strip('" ')
            if cur and cur.startswith("19") and nb.startswith("19") and cur != nb:
                census_pairs.add(frozenset((cur, nb)))

ours_rook = {frozenset(e) for e in rook.edges()}
ours_queen = {frozenset(e) for e in queen.edges()}
print(f"\nCensus adjacency file, IA-IA pairs: {len(census_pairs)}")
print(f"  in Census but not our rook : {len(census_pairs - ours_rook)}")
print(f"  in our rook but not Census : {len(ours_rook - census_pairs)}")
print(f"  in Census but not our queen: {len(census_pairs - ours_queen)}")
print(f"  in our queen but not Census: {len(ours_queen - census_pairs)}")
for p in sorted(census_pairs - ours_rook):
    a, b = sorted(p); print(f"     Census-only: {name[a]} -- {name[b]}")

nx.write_gml(rook, OUT / "ia_county_rook.gml")
iap[["GEOID", "NAME", "P0010001", "geometry"]].to_file(OUT / "ia_counties.gpkg", driver="GPKG")
print(f"\nwrote {OUT/'ia_county_rook.gml'} and {OUT/'ia_counties.gpkg'}")
