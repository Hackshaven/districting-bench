#!/usr/bin/env bash
# Fetch the Iowa inputs. All sources are US Census Bureau, public domain.
# Run from the repository root. Downloads ~180 MB into data/raw/.
set -euo pipefail
mkdir -p data/raw && cd data/raw

# 2020 Census Redistricting Data (P.L. 94-171) Summary File, Iowa
curl -fsSL -O "https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/Iowa/ia2020.pl.zip"
unzip -oq ia2020.pl.zip

# TIGER/Line 2020 counties (national; filtered to STATEFP 19 downstream)
curl -fsSL -O "https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/tl_2020_us_county.zip"
unzip -oq tl_2020_us_county.zip

# TIGER/Line 2022 congressional districts, 118th Congress, Iowa — the enacted plan
curl -fsSL -O "https://www2.census.gov/geo/tiger/TIGER2022/CD/tl_2022_19_cd118.zip"
unzip -oq tl_2022_19_cd118.zip

# Census County Adjacency File — independent cross-check on the computed graph
curl -fsSL -O "https://www2.census.gov/geo/docs/reference/county_adjacency.txt"

echo "done: $(du -sh . | cut -f1) in data/raw/"
