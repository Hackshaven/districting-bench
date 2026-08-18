# Feasibility pass — Iowa

Pre-Phase-1. Four questions: does the firewall work, is the data obtainable, what
does the adjacency graph look like, and will a ReCom ensemble run. All four are
answered below, with the numbers that produced the answer.

> **Corrected 2026-08-18, after adversarial review.** The first version of this
> document reported that ReCom "cannot operate" below ε = 0.001 and that no
> sampled plan reached the enacted plan's population equality. **Both were
> artifacts of a library misuse in my own probe** — `node_repeats=10` passed to a
> cut-finder that GerryChain warns must receive `0`, with the warning suppressed by
> `warnings.filterwarnings("ignore")` in `feasibility/epsilon_sweep.py`. Setting it
> to `0` and changing nothing else, ε = 1×10⁻⁴ samples fine and ReCom reaches a
> 71-person spread, better than the enacted plan's 94. §5 is rewritten. §6 item 1
> is withdrawn. The architectural recommendation that rested on it is withdrawn.
> Corrections are marked **[C]**; what survived review is marked **[✓]**.

**Verdict: feasible. The blocking finding of the first draft was my bug, not a
property of the problem.** The real open question is mixing, not feasibility —
see §5.

No implementation code was written. `src/` still contains no Python. Everything
here was produced by throwaway probes in `feasibility/`, and
`tools/firewall.yaml` is untouched.

Reproduce with `feasibility/fetch_data.sh` then the scripts listed in
`feasibility/README.md`. Environment: Python 3.11.15, GerryChain 1.0.0,
GeoPandas 1.1.4, NetworkX 3.6.1, Shapely 2.1.2.

---

## 1. The firewall works — and has at least six gaps  **[C]**

**Required canary: passed.** `tools/check_firewall.py` reports `clean` on the
current tree. Planting `src/generate/canary.py` containing `df["pre_20_dem"]`
produces:

```
src/generate/canary.py:6: [partisan-data-in-generator] 'pre_20_dem' matches denied pattern 'pre_'
exit 1
```

Deleting the canary returns the tree to `clean`. The guardrail fails when it
should. The canary was removed; it is not in any commit.

One test is not verification, so I probed further. Adversarial review then found
more than I did. **At least six** constructions reach `src/generate/` untouched:

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
| `df["Dem_Votes"]`, `df["Black"]` — **Dave's Redistricting naming** | **passes** |
| a file at `src/shim.py` (not inside a package dir) | **never scanned** |
| `src/generate/cols.yaml` holding `target: pre_20_dem` | **never parsed** |

Four of these matter more than they look:

**VEST naming is not covered, though the config says it is.** The comment above
`column_denylist` states the patterns "cover the column naming conventions used by
VEST, the ALARM 2020 Redistricting Data Files, and Dave's Redistricting exports."
The ALARM tidied convention (`pre_20_dem`) is covered. VEST's own published
convention is not: `G20PRED` contains no underscore, so `pre_` and `_dem` both
miss. Anyone loading raw VEST files — the primary source ALARM is built from —
gets no protection. **[C]** Dave's Redistricting is uncovered too: `_dem` requires a
leading underscore, so `Dem_Votes` misses, as do `Rep_Votes`, `White`, `Black`,
`Hispanic` and `Minority`. Two of the three conventions the comment names are
uncovered, not one. VEST's published columns are `G20PREDBID` / `G20PRERTRU` /
`G16PREDCLI`; `G20PRED` is the office/party prefix, not a whole column. No VEST file
exists in `data/`, so this is asserted from VEST's documentation, not verified
against a downloaded file.

**The allowlist exempts whole tokens, not just the matching part.**
`matches_denylist()` returns `None` on the first allowlist substring found
anywhere in the token, before the denylist is consulted at all. `precinct` is on
the allowlist, so *any* identifier or string containing `precinct` is exempt in
full. `precinct_pre_20_dem` passes. This is the most consequential of the four,
because `precinct` is exactly the word a partisan column name is most likely to
carry.

**Two whole classes of file are never examined. [C]** `owning_package()` takes
`rel.parts[0]` and returns `None` unless it names a package, so a file at the top of
`src/` — `src/shim.py` — is skipped entirely; a one-file shim there launders any
denied column into `generate`, and the import check does not catch it either because
`shim` is not a package. And only `*.py` is parsed: a `cols.yaml` inside
`src/generate/` containing `target: pre_20_dem`, read at runtime, reports `clean`.

**Reading a file by name is invisible to it.** The check is static analysis of
identifiers and string constants in `src/`. A generator that opens an election
results CSV and uses positional or runtime-derived column access never names a
denied column in its source. No pattern list can close this; it needs a different
mechanism (a load-time guard on the dataframe schema, or a data-layer allowlist of
readable paths).

`prompt.md` says not to modify or work around the firewall, and to say so rather
than edit if the config seems wrong. **`tools/firewall.yaml` is unmodified.**

**[C] Only two of the gaps are closable by adding denylist patterns**, not three as
the first draft said — and that draft contradicted itself, explaining the
short-circuit mechanism two paragraphs before counting that gap as config-closable.

- `bvap` / `hvap` / `wvap` add cleanly: zero matches across GerryChain, GeoPandas,
  NetworkX and Shapely.
- `g20` does **not** add cleanly. It false-positives on ordinary strings
  (`config2020.yaml`, `redistricting2020`, a `g200` local in NetworkX) and it is
  year- and office-specific, so `G16PREDCLI`, `G18GOVDHUB` and `G22USSRGRA` still
  pass. Covering VEST by substring needs an enumeration of vintages and will
  silently miss future ones.
- The allowlist collision **cannot be closed by any denylist addition at all**,
  because `matches_denylist()` returns before the denylist is consulted:
  `precinct_G20PRED` and `precinct_BVAP` still pass with those patterns added. Nor
  is it specific to `precinct` — `report_dem_share` and
  `preserve_two_party_voteshare` pass on `report` and `preserve`. Closing it needs
  word-boundary matching in `check_firewall.py`, a code change, not a config edit.

So: two gaps are a config decision for you; the rest need a design, and are Phase 1
questions.

---

## 2. Data — obtained, with exact provenance

All four inputs are US Census Bureau products. Census Bureau works are US
Government works and are not subject to copyright protection (17 U.S.C. § 105);
the Census Bureau states explicitly that the TIGER/Line Shapefiles are not
copyrighted. **[C]** No *copyright-based* restriction — but the first draft's "no
attribution obligation, no redistribution restriction" was overstated. Two
non-copyright conditions attach, both framed by the Bureau as requests rather than
legal obligations: it asks to be cited as the source, and TIGER/Line® is a
registered trademark that may not be used within a product name, with a request that
repackaged TIGER/Line data carry a conspicuous statement to that effect. 17 U.S.C.
§ 105 also bars copyright only within the United States.

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
  exactly. **[✓]** Verified against the Census apportionment tables, not asserted
  from memory: `apportionment-2020-tableA.xlsx` gives Iowa apportionment 3,192,406,
  resident 3,190,369, overseas 2,037. The SUMLEV=040 state record in the same PL
  file independently reports 3,190,369, matching the county sum. `P0010001` is the
  resident count and is the correct base for districting.
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
merits.

**[C]** The first draft offered "zero MultiPolygons, zero invalid geometries, max
water share Dickinson 5.80%" as evidence for this. That is a non sequitur: those
facts rule out islands and detached parts, but say nothing about water *along a
shared boundary*, which I did not measure. Review did measure it against TIGER
AREAWATER for 98 of 99 counties: 85 of the 222 rook edges have some water along the
shared boundary, and one — Des Moines–Lee — is about 83% water (Skunk River and
Mississippi backwaters), close enough to the line to matter if the criterion were
ever applied strictly. **No pair is water-only**, so the conclusion holds; the
original evidence for it did not.

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
- district populations sum to 3,190,369, exactly the state total — **[C]** a
  consistency check on the join, *not* evidence of a whole-county partition.
  `feasibility/enacted.py` assigns each county to exactly one district by
  point-in-polygon on its representative point, so the sum holds by construction
  whatever the real plan looks like. The first draft called this a proof; it is a
  tautology.
- **all four districts are connected under rook**, so the real map does not
  depend on corner adjacency

Five counties show a small geometric overhang against their district polygon
(largest Warren, 0.58 km²). This is a vintage artifact — 2020 county geometry
against 2022 district geometry, digitized separately — not a split county. **[✓]** The conclusion survived review on better evidence than I gave it: against
2022-vintage county geometry Warren is 100.000000% inside CD01 with zero area
outside; the 2020-vs-2022 Warren polygon symmetric difference (917,016 m²) is larger
than the overhang itself; and the overhang decomposes into ~1,269 slivers 23–60 m
thick strung along the Warren–Polk boundary. Iowa Code ch. 42 forbids county splits
for congressional districts, and the published enacted CD1 county list matches ours
county-for-county with Warren whole. Warren is in **CD1**.

---

## 5. The ensemble — and the bug that produced the first draft's headline

Iowa Code ch. 42 criteria only: population equality (the ε constraint),
contiguity (guaranteed by ReCom on the rook graph), whole counties (guaranteed by
construction), compactness (measured, not constrained). No partisan or racial data
is loaded anywhere in `feasibility/`.

### 5.1 The bug  **[C]**

`feasibility/ensemble.py` passes `node_repeats=10` to both `recursive_tree_part`
and `recom`. GerryChain 1.0.0 warns that this is wrong for the default
`find_balanced_edge_cuts_memoization` cut-finder, which already searches each
spanning tree exhaustively — a positive `node_repeats` re-roots the *same exhausted
tree* instead of drawing a new one, so the 100,000-attempt budget is spent without
ever seeing a new tree. `feasibility/epsilon_sweep.py` calls
`warnings.filterwarnings("ignore")`, which suppressed the warning that said so.

The failure was in the ReCom proposal, not in seeding: `recursive_tree_part`
succeeded at ε=0.0005 on every seed tried, and the chain then died inside
`bipartition_tree`.

A/B with everything else identical, 300 steps, seed 2000:

| ε | `node_repeats=10` | `node_repeats=0` |
| --- | --- | --- |
| 5×10⁻⁴ | fails after 36.8 s | **ok** 300/300, 43.8 ms/step, best spread 198, 107 distinct |
| 2×10⁻⁴ | fails after 21.9 s | **ok** 300/300, 119.5 ms/step, **best spread 71**, 48 distinct |
| 1×10⁻⁴ | fails after 109.2 s | **ok** 300/300, 74.6 ms/step, best spread 125, 7 distinct |

**The practical floor is ≈1×10⁻⁴, not 1×10⁻³** — a factor of ten, from one
character.

**But `node_repeats=0` is not a universal fix, and the tight region is
seed-fragile.** Eight seeds × 150 steps each:

| ε | seeds that ran | best spread found |
| --- | --- | --- |
| 1×10⁻³ | 8/8 | 160 |
| 5×10⁻⁴ | 8/8 | 103 |
| 2×10⁻⁴ | **7/8** (seed 1001 fails) | **57** |

At ε=2×10⁻⁴ the sampler both beats the enacted plan's 94-person spread (57, on two
of eight seeds) *and* fails outright on one seed. Any Phase 1 ensemble at this
tolerance needs per-seed failure handling and a reported failure rate, not a single
lucky chain. ε=1×10⁻⁴ is slower still and was not run to completion across seeds. Seeding from the enacted plan rather than `recursive_tree_part` reaches
≈7×10⁻⁵. `pair_selection='cut_edges'` also runs at ε=5×10⁻⁴ but is not required;
`allow_pair_reselection=True` with `max_attempts=100` is *worse*, failing at step 79
with `MetagraphError`.

### 5.2 The original sweep, with its caveats

4 chains × 300 steps per ε, all with the bad `node_repeats`:

| ε | max−min observed | ms/step | cut edges (mean) | distinct plans | PSRF | status |
| --- | --- | --- | --- | --- | --- | --- |
| 0.05 | 9.94% | 4.1 | 42.14 | 1055/1200 | 1.0207 | ok |
| 0.01 | 1.99% | 15.9 | 43.89 | 854/1200 | 1.0361 | ok |
| 0.005 | 0.99% | 36.0 | 43.15 | 745/1200 | 1.0129 | ok |
| 0.002 | 0.39% | 60.0 | 41.90 | 476/1200 | 0.9994 | ok |
| 0.001 | 0.20% | 125.4 | 43.17 | 399/1200 | 1.0567 | ok |
| 5×10⁻⁴ … 1×10⁻⁴ | — | — | — | — | — | ~~fails~~ **runs with `node_repeats=0`** |

**[C] ε bounds *per-district* deviation, so the "max−min observed" column is
largely reporting 2ε.** `within_percent_of_ideal_population` builds
`Bounds(population, ((1−ε)·ideal, (1+ε)·ideal))`. At ε=0.001 the constraint permits
a **1,595-person** spread — **17× the enacted plan's 94.** The sweep never came
within an order of magnitude of the enacted standard, so nothing was "tightened
toward" it and then found wanting.

**[C]** The ε=0.001 configuration is also not reliably runnable across seeds even on
its own terms: seed 1003 crashes at step 350 with the same 100,000-attempt error.

### 5.3 The headline run — reproducible, but its conclusion is withdrawn

4 chains × 1500 steps at ε=0.001 and ε=0.002 (`tight_equality.py`, seeds 3000–3003):

| | ε = 0.002 | ε = 0.001 |
| --- | --- | --- |
| wall clock | 442.9 s | 755.7 s |
| per step | 73.8 ms | 125.9 ms |
| cut edges | 42.75 ± 4.68, range 33–62 | 42.64 ± 4.84, range 33–63 |
| median population spread | 0.267% | 0.143% |
| minimum spread reached | 123 persons | 123 persons |
| PSRF (cut edges, n=1500) | 1.0208 | 1.0033 |

**[✓] These numbers reproduce exactly.** An initial reviewer reported they did not,
having re-run `ensemble.py`'s CLI (seeds 1000–1003) rather than `tight_equality.py`
(seeds 3000–3003); on the correct seeds every figure matches to four decimals.

**[C] But the 123-person "floor" is a seed artifact, not a floor.** It recurs
identically at both ε because it is the *same plan*, found by the same seed in both
runs — not independent confirmation. An independent re-run at ε=0.001 with seeds
1000–1003 reaches **91 persons**, beating the enacted plan, with `node_repeats`
unchanged. And with `node_repeats=0` at ε=2×10⁻⁴, ReCom reaches **71 persons**
(§5.1). The measured 0-in-12,000 acceptance rate is a property of one four-seed run
at a tolerance 17× too loose — at ε=3×10⁻⁴ one 500-step chain put 24 of its 500
states at or below 94, an acceptance rate of **4.8%**.

**[C] "12,000 plans" overstates the sample.** Chain states are heavily duplicated:
658–738 distinct per 1500 at ε=0.002 and 456–515 at ε=0.001, so 12,000 states is
roughly 5,600 distinct plans.

**[C] The enacted plan is not near-optimal, either.** A direct beam search over
single-county boundary reassignments, with contiguity enforced by articulation
points, finds whole-county rook-contiguous 4-partitions **better than 94 persons in
seconds** — independently verified at 70 persons (99 counties each assigned once,
all four districts rook-connected, populations summing to 3,190,369). A larger
search reported hundreds more, best 13; that figure is single-source and is not
reproduced here. The mechanism is compactness: the sub-94 plans carry 57–67 cut
edges against an ensemble mean of 42.6 and the enacted plan's 51, so the tight
region is real but less compact.

**County splits: identically zero in every plan, by construction. [✓]** Districts
are unions of whole counties, so the criterion cannot vary. It carries no
information for Iowa congressional and cannot serve as a detection signal on this
state. The distribution is a point mass at 0.

### 5.4 Convergence — the diagnostic cannot support the weight put on it  **[C]**

The first draft concluded "tighter mixed better". **Withdrawn.**

`psrf()` is a correct textbook Gelman–Rubin R̂ (BDA3), missing only the 1992 df
correction — the implementation is fine. But it is **unsplit**, and at m=4 chains it
is noise-dominated. Simulating perfectly mixed i.i.d. chains: median R̂ 0.9996,
**P(R̂ < 1.0) = 0.62**. So §5.2's 0.9994 is the *modal* outcome for a converged
chain, and the 1.0033-versus-1.0208 contrast the first draft built an argument on is
inside the noise band — resampling which 4 of 8 chains you use at ε=0.002 alone
moves R̂ across 0.9999–1.0164.

With enough chains to see past that noise, the ordering is the intuitive one:
**ε=0.001 mixes an order of magnitude worse than ε=0.002.** Effective sample size on
cut edges is 542 of 12,000 draws at ε=0.002 against 49.7 of 7,500 at ε=0.001.
Rank-normalized split R̂ (Vehtari et al. 2021) is systematically higher than the
unsplit statistic — 1.0122 vs 1.0069 at ε=0.002, 1.0862 vs 1.0594 at ε=0.001 — and
on an AR(1) surrogate matched to the observed autocorrelation the unsplit statistic
passes a visibly unconverged chain about half the time. Discarding 50% burn-in
*raises* R̂ from 1.0083 to 1.0156, so the reported value was flattered by retaining
the transient.

Phase 1 should report rank-normalized split R̂ **and** ESS, on population spread as
well as cut edges — the two disagree in both direction and magnitude.

### 5.5 What the ensemble question actually is

Not feasibility. ReCom reaches the enacted plan's equality standard and beats it,
once configured correctly. The open question is **mixing**: distinct plans per 300
steps collapse from 107 at ε=5×10⁻⁴ to 48 at ε=2×10⁻⁴ to 7 at ε=1×10⁻⁴, and
seed-to-seed variance in the sub-94 hit rate is enormous (24/500 versus 0/500 at the
same ε). An ensemble that reaches the legal standard but barely moves is a different
problem from one that cannot reach it, and it needs a different fix.

**The first draft's four options are withdrawn as posed.** Options 1 (Sequential
Monte Carlo, a second toolchain in R) and 3 (matched-band comparison, "shrinks the
usable ensemble by ~99%") were both justified by an infeasibility that does not
exist. Option 4's concession that "the ensemble's plans are not legal plans" is not
forced. Option 2 (ReCom plus a local population-balancing move) is the one review
strengthened, since a plain hill-climb reaches the tight region in seconds.

**Recommendation: do not make the architectural decision yet.** Re-run §5.2–§5.4
with `node_repeats=0` at ε ≈ 2–3×10⁻⁴, reporting split R̂ and ESS on both scalars,
and measure the acceptance rate at the enacted spread properly. Decide once that
re-run exists.

---

## 6. What surprised me

Rewritten after review. Item 1 of the first draft is **withdrawn**; the biggest
surprise is now the correction itself.

1. **The finding I led with was my own bug. [C]** I reported that ReCom "cannot
   operate" below ε=0.001 and that no sampled plan matched the enacted plan's
   equality. GerryChain warned me — in a `UserWarning` naming the exact parameter
   and the exact fix — and my own sweep script called
   `warnings.filterwarnings("ignore")` on the line above. One character
   (`node_repeats=10` → `0`) moves the floor by a factor of ten and produces plans
   better than the enacted map. **The lesson is not about GerryChain.** It is that I
   suppressed a diagnostic and then reported the resulting failure as a property of
   the problem, and that the failure was interesting enough — it made a clean
   story about human map-drawers beating samplers — that I did not go back and
   check it. A more attractive finding needs *more* scrutiny, not less.

2. **The enacted plan is not near-optimal on population equality.** Both ReCom
   (once fixed) and a simple beam search find whole-county, contiguous plans
   well below its 94-person spread within seconds. The first draft told the reader
   Iowa's map sits near the achievable boundary. It does not.

3. **The tight region is real but less compact.** Sub-94 plans carry 57–67 cut edges
   against an ensemble mean of 42.6 and the enacted plan's 51. ReCom's spanning-tree
   proposal is compactness-biased, so a chain run against a loose bound concentrates
   far from the tight-but-ragged corner of the space. That interaction between two
   ch. 42 criteria — equality and compactness — is the thing worth studying, and it
   was invisible while the bug was in place.

4. **ε bounds per-district deviation, not spread.** So the sweep's "max−min" column
   was largely reporting 2ε, and the ε=0.001 run permitted a 1,595-person spread —
   17× the enacted plan's. I compared against a reference set whose constraint was
   never within an order of magnitude of the standard I was comparing to.

5. **The convergence diagnostic had no resolution.** An unsplit R̂ at 4 chains
   returns values below 1.0 the majority of the time for a *converged* chain, so the
   sub-1.0 numbers were not the anomaly I took them for — but the 1.0033-vs-1.0208
   contrast I reasoned from was smaller than the noise from reshuffling which chains
   you use. With enough chains the ordering reverses: tighter mixes *worse*, as
   intuition says.

6. **The firewall has more holes than I found, and fewer are config-fixable.** Six
   at least, not four; Dave's Redistricting naming is uncovered as well as VEST's;
   files at the top of `src/` are never scanned at all; non-`.py` files are never
   parsed. And only two of the gaps close with a denylist edit — the allowlist
   short-circuit cannot be closed by *any* addition, which the first draft explained
   and then miscounted anyway.

7. **CRITERIA.md's prediction of disconnected components does not hold here. [✓]**
   It warns that naive shapefile adjacency "produces disconnected components in
   nearly every state". Iowa needed no repair: rook is connected in one component,
   no islands, no invalid geometries. That warning is about precinct-level data.

8. **A quarter of Iowa's queen adjacencies are corner touches [✓]** — 72 of 294,
   because the state is a survey grid — and the Census County Adjacency File
   includes all of them, so anyone using it inherits corner adjacency without
   deciding to.

9. **County splits are a degenerate metric here. [✓]** Zero in every plan, always.
   One of ch. 42's four criteria carries no information on the first target state.

10. **The Census API now requires a key.** A documented, widely-cited access route
    silently became unusable for automation.

---

## 7. State of the repository

- `src/` — still no Python. Nothing implemented.
- `tools/firewall.yaml`, `tools/check_firewall.py` — **unmodified**, `clean`.
- `feasibility/` — throwaway probes, reproducible from the repo root.
- `docs/DECISIONS.md` — D-001 through D-007.
- `data/` — gitignored, refetchable via `feasibility/fetch_data.sh`.

Every claim above was put through an adversarial review pass (six independent
refuters plus a synthesizer, D-007). Two findings were invalidating, five material.
Corrections are marked **[C]**; claims that survived are marked **[✓]** and are
better evidenced than before.

Phase 1 has not started and will not start without a go.
