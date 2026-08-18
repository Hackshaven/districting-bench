"""Extract Iowa county populations from the 2020 PL 94-171 legacy-format files.

Source: US Census Bureau, 2020 Census Redistricting Data (P.L. 94-171) Summary File,
        https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/Iowa/
Segment 1 field 6 is P0010001 (total population); geoheader field 3 is SUMLEV,
field 8 LOGRECNO, field 10 GEOCODE, field 88 NAME.
"""
import csv
from pathlib import Path

RAW = Path("data/raw")
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

# logrecno -> (geocode, name) for county records only
counties = {}
with (RAW / "iageo2020.pl").open(encoding="latin-1") as fh:
    for line in fh:
        f = line.rstrip("\n").split("|")
        if f[2] == "050":  # SUMLEV 050 = county
            counties[f[7]] = (f[9], f[87])

pops = {}
with (RAW / "ia000012020.pl").open(encoding="latin-1") as fh:
    for line in fh:
        f = line.rstrip("\n").split("|")
        if f[4] in counties:
            pops[f[4]] = int(f[5])  # P0010001

rows = sorted(
    (counties[l][0], counties[l][1], pops[l]) for l in counties if l in pops
)
with (OUT / "ia_county_pop.csv").open("w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["GEOID", "NAME", "P0010001"])
    w.writerows(rows)

total = sum(r[2] for r in rows)
print(f"counties: {len(rows)}")
print(f"total population: {total:,}")
print(f"ideal district (4 CDs): {total/4:,.1f}")
print("largest :", *sorted(rows, key=lambda r: -r[2])[:3], sep="\n  ")
print("smallest:", *sorted(rows, key=lambda r: r[2])[:3], sep="\n  ")
