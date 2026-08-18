# Feasibility pass — Iowa

Pre-Phase-1. Four questions: does the firewall work, is the data obtainable, what
does the adjacency graph look like, and will a ReCom ensemble run. All four are
answered below, with the numbers that produced the answer.

**Verdict: feasible, with one finding that changes how Phase 1 must be built.**
See §5.

No implementation code was written. `src/` still contains no Python. Everything
here was produced by throwaway probes in `feasibility/`, and
`tools/firewall.yaml` is untouched.

Reproduce with `feasibility/fetch_data.sh` then the scripts listed in
`feasibility/README.md`. Environment: Python 3.11.15, GerryChain 1.0.0,
GeoPandas 1.1.4, NetworkX 3.6.1, Shapely 2.1.2.

---

## 1. The firewall works — and has four gaps

**Required canary: passed.** `tools/check_firewall.py` reports `clean` on the
current tree. Planting `src/generate/canary.py` containing `df["pre_20_dem"]`
produces:

```
src/generate/canary.py:6: [partisan-data-in-generator] 'pre_20_dem' matches denied pattern 'pre_'
exit 1
```

Deleting the canary returns the tree to `clean`. The guardrail fails when it
should. The canary was removed; it is not in any commit.

One test is not verification, so I probed further. Four constructions reach
`src/generate/` without tripping the check:

| Probe | Result |
| --- | --- |
| `df["pre_20_dem"]` — ALARM/DRA naming | caught |
| `df["G20PRED"]` — **VEST naming** | **passes** |
| `df["G20PREDBID"]` — VEST naming with candidate suffix | **passes** |
| `df["precinct_pre_20_dem"]` — **allowlist collision** | **passes** |
| `c = "pre" + "_20_dem"; df[c]` — split literal | caught |
| `pd.read_csv("data/ia_elections_2020.csv")` — **file read, no column named** | **passes** |
| `df["vap_black"]` | caught |
| `df["BVAP"]` — **common shorthand** | **passes** |

Three of these matter more than they look:

**VEST naming is not covered, though the config says it is.** The comment above
`column_denylist` states the patterns "cover the column naming conventions used by
VEST, the ALARM 2020 Redistricting Data Files, and Dave's Redistricting exports."
The ALARM tidied convention (`pre_20_dem`) is covered. VEST's own published
convention is not: `G20PRED` contains no underscore, so `pre_` and `_dem` both
miss. Anyone loading raw VEST files — the primary source ALARM is built from —
gets no protection.

**The allowlist exempts whole tokens, not just the matching part.**
`matches_denylist()` returns `None` on the first allowlist substring found
anywhere in the token, before the denylist is consulted at all. `precinct` is on
the allowlist, so *any* identifier or string containing `precinct` is exempt in
full. `precinct_pre_20_dem` passes. This is the most consequential of the four,
because `precinct` is exactly the word a partisan column name is most likely to
carry.

**Reading a file by name is invisible to it.** The check is static analysis of
identifiers and string constants in `src/`. A generator that opens an election
results CSV and uses positional or runtime-derived column access never names a
denied column in its source. No pattern list can close this; it needs a different
mechanism (a load-time guard on the dataframe schema, or a data-layer allowlist of
readable paths).

`prompt.md` says not to modify or work around the firewall, and to say so rather
than edit if the config seems wrong. **`tools/firewall.yaml` is unmodified.**
Three of the four gaps are closable by adding denylist patterns — a config change,
and therefore a human decision, recorded in a commit that changes nothing else.
The fourth needs a design, and is a Phase 1 question.

---

## 2. Data — obtained, with exact provenance

All four inputs are US Census Bureau products. Census Bureau works are US
Government works and are not subject to copyright protection (17 U.S.C. § 105);
the Census Bureau states explicitly that the TIGER/Line Shapefiles are not
copyrighted. No attribution obligation, no redistribution restriction.

| Input | Source | Vintage |
| --- | --- | --- |
| County population | [`ia2020.pl.zip`](https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/Iowa/ia2020.pl.zip) — 2020 Census Redistricting Data (P.L. 94-171) Summary File, Iowa | 2020 |
| County boundaries | [`tl_2020_us_county.zip`](https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/tl_2020_us_county.zip) — TIGER/Line, filtered to `STATEFP = 19` | 2020 |
| Enacted plan | [`tl_2022_19_cd118.zip`](https://www2.census.gov/geo/tiger/TIGER2022/CD/tl_2022_19_cd118.zip) — TIGER/Line congressional districts, 118th Congress | 2022 |
| Adjacency cross-check | [`county_adjacency.txt`](https://www2.census.gov/geo/docs/reference/county_adjacency.txt) — Census County Adjacency File | 2010 |

Nothing is fabricated, approximated, or hand-entered. `data/` is gitignored;
`feasibility/fetch_data.sh` reproduces it (~180 MB).

**The Census API now requires a key.** `api.census.gov/data/2020/dec/pl` 302s to a
"Missing Key" page, so the API route is unavailable non-interactively. The bulk PL
file is the primary source anyway. Logged as D-002.

**Population, from `P0010001` at `SUMLEV=050`:**

- 99 counties
- 3,190,369 total — matches Iowa's published 2020 census resident population
  exactly (the apportionment population, 3,192,406, differs because it counts
  overseas federal personnel; `P0010001` is the resident count and is the correct
  base for districting)
- ideal district (4 CDs): **797,592.25**
- largest county Polk 492,401 (61.7% of a district); smallest Adams 3,704

---

## 3. The adjacency graph

| | edges | components | connected |
| --- | --- | --- | --- |
| Rook (shared boundary of positive length) | 222 | 1 | yes |
| Queen (any touch, including corners) | 294 | 1 | yes |

Degree under rook: min 2, max 7, mean 4.48. Lowest are Allamakee, Fremont and
Lyon at 2 — the three corner counties, as expected.

**72 pairs touch at a single point only** — 24% of queen edges, listed in full by
`feasibility/adjacency.py`. Iowa's counties approximate a survey grid, so
four-corner meetings are everywhere. Rook versus queen is not a technicality here;
it changes the graph by a third.

**Cross-check against the Census County Adjacency File: exact match, under
queen.** 294 Iowa–Iowa pairs in the Census file; 294 in our queen graph; zero
disagreement in either direction. The 72 pairs the Census file has that our rook
graph lacks are precisely the point contacts. Worth stating plainly: **the Census
County Adjacency File is queen-based.** Anyone using it as an adjacency source is
silently accepting corner connections.

**Water and single-point adjacency.** No Iowa county pair is adjacent only across
water. Iowa's two water borders — the Missouri and the Mississippi — are state
boundaries, not internal county boundaries, so they never appear as an Iowa–Iowa
edge. Internal boundaries are survey lines or river centerlines; a centerline
boundary is a shared boundary of positive length, so it is a rook edge on the
merits. Supporting evidence: zero counties have detached parts (all 99 geometries
are simple polygons, no MultiPolygons, no islands), zero invalid geometries, and
the highest water share of any county is Dickinson at 5.80% (the Iowa Great
Lakes). A full hydrographic audit against TIGER AREAWATER was not run and is not
needed for county-level work; it will be needed for any precinct-level state.

**We chose rook** (D-004), and §4 gives the evidence that this is safe.

---

## 4. The enacted plan

Derived by point-in-polygon of each county's representative point against
CD118, then verified.

| CD | counties | population | deviation from ideal |
| --- | --- | --- | --- |
| 1 | 20 | 797,584 | −8 |
| 2 | 22 | 797,589 | −3 |
| 3 | 21 | 797,551 | −41 |
| 4 | 36 | 797,645 | +53 |

- **max−min spread: 94 persons — 0.0118% of ideal**
- district populations sum to 3,190,369, exactly the state total, confirming a
  clean whole-county partition
- **all four districts are connected under rook**, so the real map does not
  depend on corner adjacency

Five counties show a small geometric overhang against their district polygon
(largest Warren, 0.58 km²). This is a vintage artifact — 2020 county geometry
against 2022 district geometry, digitized separately — not a split county. The
exact population sum proves the assignment is whole-county.

---

## 5. The ensemble — and the finding that matters

Iowa Code ch. 42 criteria only: population equality (the ε constraint),
contiguity (guaranteed by ReCom on the rook graph), whole counties (guaranteed by
construction), compactness (measured, not constrained). No partisan or racial data
is loaded anywhere in `feasibility/`.

### 5.1 How tight can the population constraint be?

4 chains × 300 steps at each ε:

| ε | max−min observed | ms/step | cut edges (mean) | distinct plans | PSRF | status |
| --- | --- | --- | --- | --- | --- | --- |
| 0.05 | 9.94% | 4.1 | 42.14 | 1055/1200 | 1.0207 | ok |
| 0.01 | 1.99% | 15.9 | 43.89 | 854/1200 | 1.0361 | ok |
| 0.005 | 0.99% | 36.0 | 43.15 | 745/1200 | 1.0129 | ok |
| 0.002 | 0.39% | 60.0 | 41.90 | 476/1200 | 0.9994 | ok |
| 0.001 | 0.20% | 125.4 | 43.17 | 399/1200 | 1.0567 | ok |
| 0.0005 | — | — | — | — | — | **fails** |
| 0.0002 | — | — | — | — | — | **fails** |
| 0.0001 | — | — | — | — | — | **fails** |

Below ε = 0.001 the sampler dies with `Could not find a possible cut after 100000
attempts`. Cost rises ~30× from ε=0.05 to ε=0.001 while the reachable space
shrinks: distinct plans per 1200 steps falls from 1055 to 399.

### 5.2 Headline run

4 chains × 1500 steps at ε = 0.001 and ε = 0.002:

| | ε = 0.002 | ε = 0.001 |
| --- | --- | --- |
| wall clock | 442.9 s | 755.7 s |
| per step | 73.8 ms | 125.9 ms |
| cut edges | 42.75 ± 4.68, range 33–62 | 42.64 ± 4.84, range 33–63 |
| median population spread | 0.267% | 0.143% |
| **minimum spread reached** | **123 persons (0.0154%)** | **123 persons (0.0154%)** |
| PSRF (cut edges, n=1500) | 1.0208 | **1.0033** |

**County splits: identically zero in every plan, by construction.** Districts are
unions of whole counties, so the criterion cannot vary. It carries no information
for Iowa congressional and cannot serve as a detection signal on this state. The
distribution is a point mass at 0.

Convergence behaves unexpectedly. PSRF at ε=0.001 falls monotonically with chain
length — 1.3699 → 1.1663 → 1.0162 → 1.0033 at n = 250/500/1000/1500 — and clears
the §8 gate of 1.00–1.01. At the *looser* ε=0.002 it does not: 1.0198 → 1.0170 →
1.0070 → 1.0208, non-monotonic and outside the gate at full length. A tighter
constraint mixing better than a looser one is backwards from the usual intuition
and deserves a proper diagnostic in Phase 1 rather than the single scalar used
here.

### 5.3 The finding

**Of 12,000 neutrally-sampled plans across both ε settings, not one is as
population-equal as the enacted plan.**

| spread ≤ | plans at ε=0.002 | plans at ε=0.001 |
| --- | --- | --- |
| 0.050% | 14 / 6000 | 89 / 6000 |
| 0.020% | 2 / 6000 | 5 / 6000 |
| 0.010% | 0 | 0 |
| **0.0118% (enacted)** | **0** | **0** |

The best plan the sampler found anywhere, at either tolerance, has a **123-person**
spread. The enacted plan sits at **94 persons** — the sampler's best is 31% worse
than the real map, and that floor did not improve when the constraint was
tightened from ε=0.002 to ε=0.001.

This is not a defect in Iowa's map. It is what the Legislative Services Agency
does: population equality is criterion #1 in ch. 42, and a human optimizing it
directly beats a random walk that merely has to stay inside a tolerance band.

**Why this changes Phase 1.** The detector's premise is that a plan is suspicious
when it is an outlier against what the stated criteria produce. But on the very
first criterion in the statute, the enacted plan is already an extreme outlier —
in the *good* direction, and for an innocent reason. A detector that scores plans
against this ensemble would flag Iowa's map on population equality, and be wrong.
Worse, it would compare the enacted plan on compactness and every other axis
against a reference set that does not meet the legal standard the plan itself
meets. The comparison is contaminated at the source.

The ensemble must be conditioned on the same standard as the plan under review, or
the comparison is not like-for-like. That is not achievable by tightening ε: the
sampler fails below 0.001, and rejection sampling to the enacted plan's tolerance
has a measured acceptance rate of 0 in 12,000. Options for Phase 1, none chosen
here:

1. **A different sampler.** Sequential Monte Carlo (McCartan & Imai; ALARM
   `redist`) is designed for tight balance constraints where ReCom's tree
   bipartition stalls. Cost: R, or a second toolchain.
2. **A two-stage chain** — ReCom to move, then a local population-balancing step
   (swap boundary counties to reduce spread) as a separate move type.
3. **Compare within a matched band.** Restrict the reference set to plans in the
   same spread stratum as the plan under review, and report the stratum. Honest,
   and shrinks the usable ensemble by ~99%.
4. **Report population equality as a pass/fail lint, not a detection axis** —
   consistent with CRITERIA.md §1 treating federal constraints as lint — and
   detect only on axes where the ensemble is a fair reference.

Option 4 is cheapest and may be right, but it concedes that the ensemble's plans
are not legal plans, which weakens every downstream outlier claim by an amount
that has not been measured. **This is a decision for the human, not for me**, and
it is the substantive question the feasibility pass surfaced.

---

## 6. What surprised me

1. **The enacted plan beats the entire ensemble on criterion #1.** §5.3. I
   expected the enacted plan to sit somewhere inside the neutral distribution.
   It is outside it, on the first criterion in the statute, in the direction
   that means the map is *better* rather than worse. The whole outlier framing
   has to absorb this before it can be used.

2. **The firewall's stated coverage does not match its actual coverage.** The
   config claims VEST conventions are covered. They are not — `G20PRED` passes
   cleanly. The file that exists specifically to be trustworthy has a comment
   that overstates it.

3. **The allowlist is a bigger hole than the denylist is a wall.** Because the
   allowlist short-circuits on any substring match, `precinct` exempts every
   token containing it. A denylist entry can be defeated by concatenating an
   allowlisted word — and `precinct` is the single most likely word to appear in
   a real partisan column name.

4. **CRITERIA.md's prediction of disconnected components does not hold here.**
   It warns that naive shapefile adjacency "produces disconnected components in
   nearly every state" and to fix it before anything else. Iowa needed no repair:
   rook is connected in one component, no islands, no invalid geometries. That
   warning is about precinct-level data; at county level in a grid state it does
   not apply. Good to know the fix-first work is unnecessary for the first
   target.

5. **A quarter of Iowa's queen adjacencies are corner touches** — 72 of 294,
   because the state is a survey grid. And the Census County Adjacency File, the
   obvious authoritative source, is queen. Anyone taking it at face value inherits
   corner adjacency without deciding to.

6. **County splits are a degenerate metric here.** Zero in every plan, always.
   One of the four ch. 42 criteria carries no information on the first target
   state. It cannot be a detection signal for Iowa.

7. **Tighter mixed better.** PSRF cleared the gate at ε=0.001 (1.0033) but not at
   ε=0.002 (1.0208). Backwards from expectation, and a caution against trusting a
   single scalar convergence number.

8. **The Census API now requires a key.** A documented, widely-cited access route
   silently became unusable for automation.

---

## 7. State of the repository

- `src/` — still no Python. Nothing implemented.
- `tools/firewall.yaml`, `tools/check_firewall.py` — **unmodified**, `clean`.
- `feasibility/` — throwaway probes, reproducible from the repo root.
- `docs/DECISIONS.md` — D-001 through D-006.
- `data/` — gitignored, refetchable via `feasibility/fetch_data.sh`.

Phase 1 has not started and will not start without a go.
