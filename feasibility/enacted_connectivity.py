"""Does the enacted plan hold together on the rook graph, or does it need corners?

If any enacted district is disconnected under rook but connected under queen, then
Iowa's real map depends on single-point adjacency and the sampler must too.
"""
from pathlib import Path
import geopandas as gpd, networkx as nx, pandas as pd

OUT = Path("data/processed")
rook = nx.read_gml(OUT / "ia_county_rook.gml")
cty = gpd.read_file(OUT / "ia_counties.gpkg").to_crs(26975)
asg = pd.read_csv(OUT / "ia_enacted_cd118.csv", dtype={"GEOID": str}).set_index("GEOID")

# rebuild queen for comparison
queen = nx.Graph(); queen.add_nodes_from(rook.nodes)
sindex = cty.sindex
for i, row in cty.iterrows():
    for j in sindex.query(row.geometry, predicate="touches"):
        if j > i:
            queen.add_edge(cty.GEOID[i], cty.GEOID[j])

print(f"{'CD':>3} {'counties':>9} {'rook comps':>11} {'queen comps':>12}")
for cd in sorted(asg.CD.unique()):
    nodes = [g for g in asg.index if asg.CD[g] == cd]
    r = nx.number_connected_components(rook.subgraph(nodes))
    q = nx.number_connected_components(queen.subgraph(nodes))
    flag = "  <-- needs corner adjacency" if r > 1 and q == 1 else ""
    print(f"{cd:>3} {len(nodes):>9} {r:>11} {q:>12}{flag}")

# the suspiciously short Marion--Polk border
name = cty.set_index("GEOID").NAME
g_marion = cty[cty.NAME == "Marion"].geometry.iloc[0]
g_polk = cty[cty.NAME == "Polk"].geometry.iloc[0]
shared = g_marion.boundary.intersection(g_polk.boundary)
print(f"\nMarion--Polk shared boundary: {shared.length:,.1f} m, type {shared.geom_type}")
print(f"  Marion CD {asg.CD['19125']}, Polk CD {asg.CD['19153']}")
print(f"\ncounty area units: TIGER ALAND/AWATER, water share of total area:")
top = cty.assign(gj=cty.GEOID).merge(
    gpd.read_file("data/raw/tl_2020_us_county.shp")[["GEOID","ALAND","AWATER"]], on="GEOID")
top["wpct"] = 100*top.AWATER/(top.ALAND+top.AWATER)
for _, r in top.nlargest(5, "wpct").iterrows():
    print(f"   {r.NAME:<12} {r.wpct:5.2f}%")
