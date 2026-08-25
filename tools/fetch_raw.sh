#!/usr/bin/env bash
# Fetch every raw input that can be fetched, for both states.
#
# `feasibility/fetch_data.sh` predates Colorado and Phase 2. It fetches four
# Iowa files and is left alone because it is part of the feasibility record --
# this script is what the rest of the repository actually needs, and it is a
# superset.
#
# Everything here is US Census Bureau, public domain (17 U.S.C. 105). The Census
# Bureau asks for citation and holds the TIGER/Line trademark, which are requests
# rather than licence conditions; see docs/CRITERIA.md.
#
# NOT FETCHED, AND THIS SCRIPT CANNOT FIX IT: the precinct-level election
# returns. Both preparers read data/raw/vest/ia_2020.shp and
# data/raw/vest_co/co_2020.shp, which come from VEST on the Harvard Dataverse
# behind a click-through agreement that curl cannot accept on your behalf. See
# the "elections" section printed at the end, and README.md.
#
# Usage:  tools/fetch_raw.sh [ia|co|all]     (default: all)
# Run from the repository root. Downloads ~700 MB into data/raw/.
set -euo pipefail

WHICH="${1:-all}"
case "$WHICH" in ia|co|all) ;; *) echo "usage: $0 [ia|co|all]" >&2; exit 2 ;; esac

cd "$(dirname "$0")/.."
mkdir -p data/raw && cd data/raw

TIGER=https://www2.census.gov/geo/tiger
PL=https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171

# get URL -- skip if the unzipped marker file is already present, so re-running
# after a partial failure does not re-download 700 MB.
get() {
  local url="$1" marker="${2:-}"
  local file="${url##*/}"
  if [ -n "$marker" ] && [ -e "$marker" ]; then
    echo "  have  $file"
    return 0
  fi
  echo "  get   $file"
  curl -fsSL -O "$url"
  case "$file" in *.zip) unzip -oq "$file" ;; esac
}

fetch_ia() {
  echo "Iowa (FIPS 19)"
  # 2020 Census Redistricting Data (P.L. 94-171): population by county.
  get "$PL/Iowa/ia2020.pl.zip"                        iageo2020.pl
  # Counties are the districting unit for Iowa (Iowa Code ch. 42, whole counties).
  get "$TIGER/TIGER2020/COUNTY/tl_2020_us_county.zip" tl_2020_us_county.shp
  # The enacted plan, 118th Congress.
  get "$TIGER/TIGER2022/CD/tl_2022_19_cd118.zip"      tl_2022_19_cd118.shp
  # Independent cross-check on the computed adjacency graph.
  get "https://www2.census.gov/geo/docs/reference/county_adjacency.txt" county_adjacency.txt
  # Phase 2 split metrics. Missing from feasibility/fetch_data.sh, which is why
  # prepare_municipalities.py could not run on a clean checkout.
  get "$TIGER/TIGER2020/PLACE/tl_2020_19_place.zip"   tl_2020_19_place.shp
  get "$TIGER/TIGER2020/SLDL/tl_2020_19_sldl.zip"     tl_2020_19_sldl.shp
  get "$TIGER/TIGER2020/SLDU/tl_2020_19_sldu.zip"     tl_2020_19_sldu.shp
}

fetch_co() {
  echo "Colorado (FIPS 08)"
  # Colorado districts are not built from whole counties, so the unit is the
  # voting district (VTD) and population comes at SUMLEV 700. D-014.
  get "$PL/Colorado/co2020.pl.zip"                    cogeo2020.pl
  # The 2020 VTD layer is NOT under TIGER2020/VTD -- that path 404s. It ships
  # in the redistricting-specific TIGER2020PL tree, per state.
  get "$TIGER/TIGER2020PL/STATE/08_COLORADO/08/tl_2020_08_vtd20.zip" tl_2020_08_vtd20.shp
  get "$TIGER/TIGER2022/CD/tl_2022_08_cd118.zip"      tl_2022_08_cd118.shp
  get "$TIGER/TIGER2020/PLACE/tl_2020_08_place.zip"   tl_2020_08_place.shp
  get "$TIGER/TIGER2020/SLDL/tl_2020_08_sldl.zip"     tl_2020_08_sldl.shp
  get "$TIGER/TIGER2020/SLDU/tl_2020_08_sldu.zip"     tl_2020_08_sldu.shp
}

if [ "$WHICH" = ia ] || [ "$WHICH" = all ]; then fetch_ia; fi
if [ "$WHICH" = co ] || [ "$WHICH" = all ]; then fetch_co; fi

echo
echo "Census inputs: $(du -sh . | cut -f1) in data/raw/"
echo
missing=0
for want in vest/ia_2020.shp vest_co/co_2020.shp; do
  [ -e "$want" ] || { missing=1; echo "MISSING  data/raw/$want"; }
done
if [ "$missing" = 1 ]; then
  cat <<'MSG'

The election returns are not fetchable by script.

VEST 2020 precinct boundaries and returns are published on the Harvard
Dataverse under a click-through agreement, so they must be downloaded by hand.
One dataset holds every state as a separate shapefile:

  VEST, "2020 Precinct-Level Election Results"
  https://doi.org/10.7910/DVN/K7760H

Take the Iowa and Colorado files and unpack them where the preparers look --
these directory names are this repository's convention, not VEST's:

  ia_2020.shp  ->  data/raw/vest/ia_2020.shp
  co_2020.shp  ->  data/raw/vest_co/co_2020.shp

prepare_data.py asserts the Iowa totals (897,672 R and 759,061 D on G20PRE), so
a wrong or mis-vintaged file fails loudly rather than silently changing results.

Without them, tools/prepare_data.py builds the NEUTRAL layer only: units,
adjacency and the enacted plan. That is enough to draw ensembles, and it is
exactly the split the firewall exists to enforce -- generation never needed the
election data in the first place. Every partisan metric, and every experiment,
needs them.
MSG
fi
