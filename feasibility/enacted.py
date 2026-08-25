"""Derive the enacted Iowa congressional plan (county -> district) and check topology.

Districts: TIGER/Line 2022 CD118 for Iowa (tl_2022_19_cd118), which encodes the
plan enacted 4 Nov 2021 under Iowa Code ch. 42. Iowa CDs are whole counties, so
assignment is by which district contains each county's interior point.
"""
from pathlib import Path
import geopandas as gpd, pandas as pd

RAW, OUT = Path("data/raw"), Path("data/processed")
cty = gpd.read_file(OUT / "ia_counties.gpkg").to_crs(26975)
cd = gpd.read_file(RAW / "tl_2022_19_cd118.shp").to_crs(26975)
print("districts in CD118 file:", sorted(cd.CD118FP.tolist()))

pts = cty.copy(); pts["geometry"] = cty.representative_point()
asg = gpd.sjoin(pts, cd[["CD118FP", "geometry"]], predicate="within", how="left")
assert asg.CD118FP.notna().all(), "unassigned counties"
cty["CD"] = asg.CD118FP.astype(int).values

# Whole-county check: is every county entirely inside its district?
bad = []
for _, r in cty.iterrows():
    d = cd[cd.CD118FP == f"{r.CD:02d}"].geometry.union_all()
    outside = r.geometry.difference(d).area
    if outside > 1000:  # >1000 m^2, i.e. beyond float noise
        bad.append((r.NAME, r.CD, outside))
print(f"counties not wholly inside their district: {len(bad)}")
for n, d, a in bad: print(f"   {n} -> CD{d}, {a:,.0f} m^2 outside")

tot = cty.P0010001.sum(); ideal = tot / 4
summary = cty.groupby("CD").agg(counties=("NAME", "size"), pop=("P0010001", "sum"))
summary["dev"] = summary["pop"] - ideal
summary["dev_pct"] = 100 * summary["dev"] / ideal
print(f"\nideal = {ideal:,.2f}")
print(summary.to_string(float_format=lambda v: f"{v:,.3f}"))
spread = summary["pop"].max() - summary["pop"].min()
print(f"\nmax-min spread: {spread:,} persons  ({100*spread/ideal:.4f}% of ideal)")
print(f"largest single-district deviation: {summary.dev.abs().max():,.0f} persons")

cty[["GEOID", "NAME", "P0010001", "CD"]].to_csv(OUT / "ia_enacted_cd118.csv", index=False)

# topology sanity
mp = cty[cty.geometry.geom_type != "Polygon"]
print(f"\nnon-simple-polygon counties (islands/detached parts): {len(mp)}")
print("invalid geometries:", (~cty.geometry.is_valid).sum())
