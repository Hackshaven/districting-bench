# Instrument audit — the cross-check against PlanScore

The audit `CLAUDE.md` and D-007 require before a new result goes to
`docs/progress.md`: one auditor and one refuter, each a fresh agent given the diff
and the committed evidence and not the author's reasoning.

- **Audited state:** commit `afab97e`, after three rounds of review by the routing
  reviewers. Line numbers in the reports refer to that commit.
- **Auditor:** the `Computational Redistricting Scientist` agent, attacking the
  metrics lens.
- **Refuter:** a general-purpose agent, told to default to "refuted" and to
  reproduce every number before agreeing.

Both reports are verbatim. The last section is the author's response, and is not
part of either report. Neither agent committed anything; PlanScore's district
vote totals stayed in their scratch directories (`CRITERIA.md` §9.1).

---

## Auditor — Computational Redistricting Scientist

# Instrument audit, metrics lens: the PlanScore cross-check at commit afab97e

**Verdict: SOUND WITH CHANGES.** I recomputed the cross-check with my own code on PlanScore's pinned files, and the arithmetic, the conversions and the identity all hold wherever I tested them.
- **One material problem:** the README tells readers that this repository's efficiency gap reproduces PlanScore's published values. On every Colorado race it does not.
- **Nine minor problems:** wording and scope, plus one attribution (the compactness residual) that the write-up leaves open but public inputs settle.

**Scope.** The audit covers these files on branch `claude/first-result-and-planscore`:
- `tools/check_planscore.py`
- `tests/test_planscore_check.py`
- `docs/cross-checks/planscore.json`
- `docs/progress.md`, "Cross-check against PlanScore" (lines 2473–2612)
- `docs/DECISIONS.md` D-040 (lines 1161–1203)
- the `efficiency_gap` docstring in `src/evaluate/partisan.py` (lines 338–364)
- the README paragraph at lines 233–245

I did not read commit messages or other reviewers' scratch files.

## What I ran

Everything was written under `/tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/audit2-crs/`. I committed nothing, and `git status` in the worktree is empty afterwards.

**The repository's own run:**
- `python tools/check_planscore.py --out audit2-crs/planscore.json` exited 0.
- Both fetched files matched their sha256 pins: 3b6e73c8… for Iowa and f2f46c82… for Colorado.
- The output is byte-identical to the committed `docs/cross-checks/planscore.json`.
- `pytest tests/test_planscore_check.py`: 31 passed.

**PlanScore's code, read as text and never run:**
- `planscore/score.py` at 566cda4, and at 3f866f9 (identical to `main` today)
- `planscore/compactness/__init__.py` and `planscore/constants.py` at 566cda4 (`ROUND_FLOAT = 4`)

**PlanScore's site:** planscore.org/metrics/ and /metrics/efficiencygap/, fetched 2026-10-11.

**My reproductions** (scripts in `audit2-crs/scripts/`). None of them uses repository code except where stated.

**R1 — exact recomputation** (`independent_metrics.py`). PlanScore's district totals rounded to whole votes, in `fractions.Fraction`:
```python
T = sum(dem)+sum(rep); V = F(sum(dem),T); W = [i for i in range(n) if dem[i] > rep[i]]
S = F(len(W),n); tau = F(sum(dem[i]+rep[i] for i in W), T)
need = F(t,2) if half else F(t//2 + 1)          # per district; the winner wastes votes - need, the loser all
eg_Dpos = -(wasted_D - wasted_R)/T;  eg_equal_turnout = (S-F(1,2)) - 2*(V-F(1,2))
moved = [F(d,d+r) + (F(1,2)-V) for ...]          # uniform swing to 50%; counts ties exactly
```
It also computes mean-median as median − mean, and Warrington's declination with the −ln(n)/2 scaling.

**R2 — PlanScore's formula on the raw totals** (`raw_eg.py`). I transcribed `calculate_EG` by hand and ran it on the unrounded fractional totals:
```python
round(s - 0.5 - 2*(v - 0.5), 4)
```

**R3 — GerryChain** (`gerrychain_eg.py`). GerryChain 1.0.0 is already pinned at requirements.txt:10:
```python
gc = sum(w2 - w1 for w1, w2 in map(gerrychain.metrics.partisan.wasted_votes, dem, rep)) / T   # D first: + favours D
```

**R4 — compactness on PlanScore's own outlines** (`compact_check.py`, `compact_precise.py`). Inputs are `uploads/<id>/geometry.json`, gzip, EPSG:4326: sha256 6efa580e… for Iowa and c6cf03bb… for Colorado.
```python
g = shapely.ops.transform(pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform, shape(f["geometry"]))
pp = 4*math.pi*g.area/g.length**2;  reock = g.area/(math.pi*shapely.minimum_bounding_radius(g)**2)
```
`crs` is one of EPSG:3857, EPSG:5070, or a Lambert azimuthal equal-area projection centred on the state.

**R5 — ensemble locations** (`location.py`, `pp_location.py`), read straight from `docs/experiment-2/co-draws-v2.csv.gz`.

## Allegations

### 1. The README says `evaluate.partisan` reproduces PlanScore's efficiency gaps. It does not, on any Colorado race. Severity: material.

- **Where:** README.md:233–238.
- **Claim:** the check "recomputes the per-election metrics from PlanScore's district totals with `evaluate.partisan`. It exits 0 only if every efficiency gap PlanScore publishes is reproduced".
- **Problem:**
  - What reproduces PlanScore's values is `equal_turnout_gap(S, V)` (check_planscore.py:188–202, 292, 316). That is PlanScore's formula fed with the seat and vote shares `evaluate.partisan` computes.
  - The repository's own wasted-vote gap misses all four Colorado values, by 7 to 266 units in the fourth decimal.
  - The README never mentions D-040 or the formula difference. A reader would therefore compare this repository's gaps with PlanScore's as if they measured the same thing, which is exactly the mistake D-040 was written to prevent.
- **Reproduction (R1).** Positive favours D. Each cell is published / equal-turnout / ours (wasted votes):

  | Colorado race | published | equal-turnout | ours |
  |---|---|---|---|
  | President 2020 | −0.0138 | −0.013766 | −0.015249 |
  | Senate 2020 | +0.0296 | +0.029569 | +0.028864 |
  | President 2016 | −0.0537 | −0.053666 | −0.027090 |
  | Senate 2016 | +0.0649 | +0.064911 | +0.063745 |

- **Fix:** say that the published gaps are reproduced by PlanScore's formula, (S − ½) − 2(V − ½), from the seats and votes `evaluate.partisan` computes. Add that `evaluate.partisan`'s wasted-vote gap differs from them on every Colorado race, by a factor of two under the 2016 presidential vote (D-040).

### 2. "PlanScore's efficiency gap is the equal-turnout form" is true of PlanScore's code, but the PlanScore page CRITERIA.md cites defines the wasted-vote form. Severity: minor, but it bears on D-040's VALUE question.

- **Where:**
  - DECISIONS.md:1161 (the title) and 1167–1168
  - progress.md:2512–2518
  - partisan.py:350–352
  - check_planscore.py:16–19
- **Problem:**
  - CRITERIA.md:493 cites "PlanScore metric documentation — https://planscore.org/metrics/". That URL serves the Efficiency Gap page, the same content as /metrics/efficiencygap/ apart from cache-busting strings.
  - The page reads: "all votes cast for the winning candidate, above the 50% (plus one) threshold needed for victory, are inefficient. The efficiency gap is calculated by taking one party's total inefficient votes in an election, subtracting the other party's total inefficient votes, and dividing by the total number of votes cast."
  - It does not mention equal turnout or the seats-and-votes formula.
  - So the disagreement is between PlanScore's code and PlanScore's documentation. `calculate_EG` is at score.py@566cda4:203–233 and is the same in substance at 3f866f9:409–484.
  - `evaluate.partisan`'s default — wasted votes with a strict-majority threshold — is the documented definition. A reader who checks D-040 against the source CRITERIA.md cites finds the opposite of what D-040 says.
- **The code-level claim itself is SUPPORTED (R2).** Each of the eight published values is exactly `round(·, 4)` of the equal-turnout form on PlanScore's unrounded totals. For example, Colorado President 2016 gives −0.0536667, which rounds to −0.0537. All eight match.
- **Fix:** scope the sentence to "PlanScore's code at 566cda4 computes, and its files publish, …". Add that PlanScore's metric page describes the wasted-vote definition `evaluate.partisan` implements. Whether to tell PlanScore is the owner's decision.

### 3. "What this does not check" leaves out that the repository's wasted-vote count has no external reference. Severity: minor.

- **Where:** progress.md:2537–2540 and 2590–2598; check_planscore.py:22–27.
- **Problem:**
  - PlanScore publishes no wasted-vote gap, so its published values validate only S and V.
  - The wasted-vote count is checked only against an identity the repository derived itself (see the algebra under "Checked and found sound"). The algebra is right, but it is an internal check.
  - prompt.md asks for an external cross-check of the implementation. For the efficiency gap as CRITERIA.md §5.1 defines it, there is none, and the list should say so.
- **Reproduction (R3):**
  - GerryChain 1.0.0's `wasted_votes` (half-vote threshold), on the same totals, agrees with the record's `efficiency_gap_wasted_votes` on all eight races.
  - The differences run from −1.85e−6 to +9.7e−7. Each is within k/T (2.4e−6 to 3.1e−6), the gap between the two threshold conventions.
  - So an external reference already sits in the pinned requirements, and it agrees.
- **Fix:** add the item to the list. Optionally, make the GerryChain comparison a recorded check, labelled as half-vote threshold against the repository's majority threshold.

### 4. The compactness residual is compared with the wrong quantity, and left "not separated", though public inputs separate it. Severity: minor.

- **Where:** progress.md:2578–2588.
- **Claim:** "The residual is the size of the projection artifact src/evaluate/compactness.py measures for EPSG:5070 on Iowa, about 0.43% on Polsby-Popper and 1.15% on Reock … Which accounts for it is not separated here." On Colorado: "recorded and not interpreted".
- **What is right:**
  - The formulas match. PlanScore computes Reock as area over the smallest enclosing circle of the boundary points, and Polsby-Popper as 4πA/L² with every ring counted.
  - PlanScore does measure in EPSG:3857 (compactness/__init__.py:14–22).
- **What is wrong:** the 0.43% and 1.15% figures measure EPSG:5070 against local projections. What separates the two sides is EPSG:3857 against EPSG:5070.
- **Iowa (R4):**
  - **The scored outline:** in EPSG:3857, PlanScore's own outlines reproduce its published Reock exactly in all four districts (0.3529, 0.5341, 0.4237, 0.4877), and its Polsby-Popper to within 0.0008. The served geometry is therefore the scored one, up to vertex detail.
  - **The decomposition:** the same outlines reprojected to EPSG:5070 give Reock mean, min and max of 0.450669, 0.357962 and 0.535618. The committed values are 0.450664, 0.357962 and 0.535611. **The Iowa Reock residual is entirely projection.** Polsby-Popper still differs by +0.07%, +0.28% and +0.04% after reprojection; that part is outline or vertex density.
  - **Size of the projection difference:** per district it is 1.42%, 0.28%, 0.29% and 0.72% on Reock. The largest observed residual (district 1, 0.3529 against 0.3580, 1.4%) is therefore bigger than the "about 1.15%" quoted.
  - **Which projection distorts more:** against the local equal-area projection, EPSG:3857 errs by at most 0.61% on Polsby-Popper and 0.80% on Reock. EPSG:5070 errs by 0.43% and 1.16%. On Reock, then, PlanScore's figures are the less distorted ones, even though compactness.py:120 rejects EPSG:3857 for Iowa.
- **Colorado:**
  - Reprojecting PlanScore's outlines from 3857 to 5070 moves mean Polsby-Popper only from 0.26573 to 0.26598.
  - Against the committed 0.286974, that leaves about 0.021 (−7.3%) that comes from the outline, meaning D-015's whole-VTD approximation including the two-piece district 4.
  - Reock max differs by 2.4% and Reock mean by 1.0%.
- **Fix:** replace the sentence with the measured split, or keep "not separated" and drop the comparison with EPSG:5070's own distortion.

### 5. "What D-015's approximation costs": the heading claims more than the text, and the section leaves out a cost and two caveats. Severity: minor.

- **Where:** progress.md:2562–2574; check_planscore.py:451–452; tests/test_planscore_check.py:373.
- **(a) Attribution.**
  - The text says the approximation and PlanScore's allocation of votes move the metrics "together", and that "this check cannot separate the two sources". The heading and the test comment attribute the whole shift to D-015.
  - Supporting fact: Colorado's statewide two-party share on PlanScore's totals equals the Phase 2 report's to every digit (0.5693831949230015). So the difference sits in how the split VTDs are assigned and allocated.
- **(b) Precision.**
  - Reproduced (R5): |efficiency gap| 41.815% → 43.160%, with 269 of the 20,000 draws lying between 0.014742 and 0.015249.
  - |mean-median| 66.265% → 66.735%, with 94 draws between.
  - That ensemble has split R-hat 1.026 on the efficiency gap, above the 1.01 bar, and an effective sample size of 269 (co-convergence-rectangles.json).
  - The committed |efficiency gap| sits at 34.0% to 55.0% chain by chain. The absolute location therefore carries roughly ±3 points of Monte Carlo error.
  - The 1.4-point shift is a paired difference on the same draws, so it is real, but it is smaller than that error. The sentence prints 0.1-point precision and states neither fact.
- **(c) A missing caveat.** Mean-median is located on a plan and election where the repository's own trust rule marks it unreliable. The Phase 2 report lists mean_median and partisan_bias as untrusted for Colorado, because the statewide-margin test fires at V = 0.569. No caveat is attached, which is CRITERIA.md §11 failure mode 4 (partisan.py:742–744).
- **(d) A missing cost.**
  - The largest measured cost is on compactness: mean Polsby-Popper is 0.287 for the approximation against 0.266 for PlanScore's outline in the same projection, −7.3% (allegation 4).
  - In location terms it is small: the plan moves from above all 20,000 draws (the ensemble's maximum is 0.2861) to above 99.98% of them.
  - It should still be stated. For a perimeter measure in a VTD-unit ensemble the VTD outline is arguably the like-for-like one, so neither value is simply "the enacted plan's".

### 6. "Partisan bias: identical, same definition" overstates. The tie rules differ, and the script's tie refusal misses the tie that matters. Severity: minor.

- **Where:** progress.md:2509 and 2596–2598; check_planscore.py:29, 151 and 285–288.
- **Problem:**
  - After the swing to 50%, PlanScore counts a tied district as a Republican seat (`R < B`, score.py@566cda4:269). `evaluate.partisan` gives it half a seat (partisan.py:554–555).
  - The script refuses ties in the observed election only. Partisan bias reads ties after the swing.
  - Such a tie would fail `definition_partisan_bias` loudly, so nothing passes silently, but "same definition" and "the script refuses a tied district" both claim more than holds.
- **Reproduction (R1):** counted exactly, there are 0 ties after the swing in all eight races, so the equality holds on these data.

### 7. The record stores PlanScore's sweep value under "ours" where ours is undefined. Severity: minor.

- **Where:**
  - planscore.json:65, 108, 151 and 194 (Iowa `ours_in_planscore_convention.declination` = −0.6931…)
  - check_planscore.py:260–270 and 302–309
  - progress.md:2507 and 2511
- **Problem:**
  - On Iowa this repository's declination is undefined (`null`). A field labelled "ours" nonetheless holds −ln(4)/2, PlanScore's extreme value for a Republican sweep.
  - Read without the conventions block, the record says the repository measured maximal Republican-favouring declination. That is the float-in-place-of-undefined that partisan.py:451–455 rules out.
  - PlanScore's own summary marks its Iowa declination `"Declination Is Valid": 0`.
  - The table header "4 elections × 2 plans" implies eight declination tests. Four (Colorado's) are real tests; Iowa's four only map one convention onto the other.
  - Notation: k here means the number of districts, but partisan.py:431 uses k for the number of Republican-won districts.
- **Fix:** store null, put the PlanScore value under a name that says it is PlanScore's convention, write "4 of 8" for declination, and define k.

### 8. Wording that reads as a verdict about a real map. Severity: minor.

- **Where:** partisan.py:362–363 ("both favour the Republicans, PlanScore's by twice as much") and progress.md:2544–2545.
- **Problem:**
  - This reads the 2016 presidential result for Colorado's enacted plan off each metric's zero line, with no neutral distribution beside it. Under prompt.md:173 that reads as a verdict.
  - The zero line is not a neutral expectation (CRITERIA.md §5.4), and the repository has no 2016 ensemble to place either value in.
- **Fix:** "both are on the Republican side of zero in their own orientation (FAVOURS), PlanScore's twice as far from it".

### 9. The test file's docstring claims more than its last test can detect. Severity: minor; for the Code Reviewer.

- **Where:** tests/test_planscore_check.py:16–18, against the test at 349–380.
- **Problem:**
  - The docstring says a change to either formula, or a hand edit to the record, "fails here". The last test reads only the committed JSON and recomputes nothing.
  - A change to `evaluate.partisan.efficiency_gap` passes it until the record is regenerated.
  - A hand edit to an unpinned field also passes: the published gap, any `ours` value, or the compactness values.
  - The earlier hand-built tests do catch formula changes.

### 10. "Per-election gaps for the 2016 and 2020 races only" misdescribes the code. Severity: minor.

- **Where:** progress.md:2480–2482.
- **Problem:**
  - `calculate_fva_biases` at 566cda4 (score.py:685–691) also lists US Senate 2018. Neither file carries 2018 totals, because neither state had a 2018 Senate race, so nothing changes.
  - At 3f866f9 the list comes from `data.PRESIDENTIAL_YEARS` and `data.US_SENATE_YEARS` (score.py:1058–1059), so a re-scored file could carry more races. The sha256 pins already guard against that.

## The six claims, classed

| # | Claim | Class | Evidence |
|---|---|---|---|
| 1 | PlanScore's gap is (S−½)−2(V−½); it differs from the wasted-vote form by τ−S plus a term of at most k/T; all 8 published values are reproduced by it, only Iowa's 4 by the wasted-vote form | SUPPORTED. Scope of the wording: allegation 2 | R1, R2, the algebra below |
| 2 | Mean-median has the opposite sign; partisan bias is identical; declination is −ours·ln(k)/2 with sweeps at ∓ln(k)/2; the re-implementation follows 566cda4 | SUPPORTED, except "identical / same definition" for partisan bias, which is OVERSTATED (allegation 6) | R1; score.py read; record agreement within 1.5e−16 |
| 3 | The Iowa "Second Draft" is the enacted plan | SUPPORTED as the same plan as the repository's, and strengthened by R4 | populations, metadata, metrics; Reock agrees to within 8e−6 |
| 4 | The approximation costs 0.0005, 0.0002 and 0.0006; the location moves 41.8→43.2 and 66.3→66.7 | Numbers SUPPORTED. Attribution and precision OVERSTATED (allegation 5) | R5 |
| 5 | The compactness comparison and its residual | Numbers and formulas SUPPORTED. Attribution incomplete (allegation 4) | R4 |
| 6 | What the check does not check, and when it fails | Partly SUPPORTED. Omissions in allegations 1, 3, 6 and 9 | code read; 31 tests pass |

## Checked and found sound

**The algebra.**
- Write T for the two-party votes and τ for the share of them cast in districts the Democrats won.
- Under the half-vote threshold, wasted_D − wasted_R = (D − R) − (T_W − T_L)/2, where T_W is the two-party votes in Democratic-won districts and T_L the rest. So −EG_ours = (τ − ½) − 2(V − ½), and −EG_ours − EG_PS = τ − S exactly.
- The strict-majority threshold lowers each winner's waste by ½ or 1 vote. That adds a term no larger in size than k/T. This matches the tolerance `k/total + 1e-12` at check_planscore.py:317.
- **Numbers (R1):** the threshold term runs from −1.37e−6 to −1.85e−6 on Iowa and from +2.0e−7 to +9.7e−7 on Colorado. Every race is within k/T.

**Printed numbers.** Every number in progress.md's two tables, at partisan.py:360–363, and in D-040 matches R1 to the printed digit. Mean-median, partisan bias and declination match the record to 9 decimals in all 8 races.

**Re-implementation.**
- The re-implemented definitions (check_planscore.py:211–257) match `calculate_MMD`, `calculate_PB` and `calculate_D2` at 566cda4 line by line: the filters, the swing of −margin/2 (= ½ − V), the strict R < B, `share <= 0.5` counted as Republican, sweeps at ±1, and the −δ·ln(seats)/2 scaling.
- The vectorized versions at 3f866f9 compute the same on these inputs. The clamp to [0.25, 0.75] is never triggered (V runs from 0.372 to 0.569), and no district is tied in the observed elections.

**Orientation.**
- The four conversions — minus, minus, minus times ln(k)/2, and plus — are correct.
- Their signs are tested on real data: mean-median is non-zero in all 8 races, partisan bias is −0.125 in two Colorado races, and declination is defined in the four Colorado races.

**Iowa identity.**
- PlanScore's district populations (797,576 / 797,589 / 797,551 / 797,645) match FEASIBILITY.md:218–221 except district 1, which is 8 short.
- The spread is 94 persons.
- Statewide totals on PlanScore's district figures: President 759,060 D / 897,668 R against the asserted 759,061 / 897,672; Senate 754,858 / 864,994 against 754,859 / 864,997. All are within 4 votes.
- The 2020 presidential gap differs from the Phase 2 report by +1.26e−6 and mean-median by −8.5e−7.
- `library_metadata` links gis.legis.iowa.gov/Plan2.

**Failure paths.** The script fails on each of the following, and refuses without writing the record:
- a pin mismatch, a published value that does not reproduce, the identity, a definition mismatch
- a different PlanScore commit, a missing race, Iowa's spread, an Iowa mismatch with the Phase 2 report, the wrong contest
- a tie, a vote share outside the clamp, a missing ensemble

The re-run is deterministic, and the record holds no district vote counts.

**Other claims.**
- Only the efficiency gap has a published per-election number. PlanScore's headline metrics are averages over simulated elections (`matrix.model_votes`).
- PlanScore's repository shows no licence at 566cda4: LICENSE, LICENSE.md, LICENSE.txt and COPYING all return 404, and `setup.py` and `README.md` mention none.
- Nothing in the change combines metrics into one score; `combined_score` stays null.

## The ensemble behind claim 4 (Colorado v2)

| Field | Value |
|---|---|
| Sampler | ReCom, gerrychain==1.0.0 |
| Target | not characterized |
| Population tolerance | ε = 0.01 (experiment_2_tradeoffs.py:125): each district within ±7,217 of 721,714.25, a spread of up to about 14,434 persons |
| Units and contiguity | whole VTDs (3,108), rook contiguity |
| Left out | the 1-person standard the enacted plan meets |
| Chains | 8 × 2,500, all completed, none failed |
| Convergence | split R-hat 1.026 on the efficiency gap, 1.037 on cut edges, 1.004 on population |
| Effective sample size | 269 on the efficiency gap, 268 on cut edges, 2,096 on population |
| Draws | 20,000, with 9,850 distinct \|efficiency gap\| values |
| Election | 2020 presidential (G20PRE) only |
| Legal plans? | No: ±1% population deviation, as D-015 already records |

**Political geography.** No claim under audit attributes an outcome to the lines. Allegation 8 is where an orientation read off a metric's zero line stands in for a neutral expectation.

## Handoffs

- **Statistician:** the Monte Carlo error in allegation 5(b). Should 0.1-point locations from an ensemble at R-hat 1.026 and effective sample size 269 be printed without an interval?
- **Code Reviewer:** allegation 9. Also, `ENACTED_SPREAD` (check_planscore.py:416) checks only the spread, not the per-district populations the record stores.
- **GIS QA Engineer:**
  - On Iowa, after reprojection, Polsby-Popper still differs by up to 0.28% between PlanScore's block-dissolved outlines and the TIGER counties.
  - PlanScore's served geometry.json may be simplified relative to the geometry it scored: Polsby-Popper differs by up to 0.0008 while Reock is identical.
- **Election Law Analyst:** whether Iowa's 2021 "Plan 2" and Colorado's "Final Approved Congressional Plan" are the plans in force (progress.md:2489–2503, README.md:239–240). That they are the same plans as this repository's is a data question, supported above for Iowa.

## Unverified

- **Colorado plan identity.** It rests on PlanScore's title alone; `library_metadata` is null. It is consistent with the metrics: 5 seats, efficiency gap, mean-median and declination within 0.0006 of the VTD approximation, and district 1's Reock within 0.013%. Comparing PlanScore's outline with the commission's published plan geometry would settle it.
- **PlanScore's allocation of precinct votes to blocks.** The write-up states it. The fractional totals are consistent with it, but I did not check PlanScore's data pipeline.

AI-assisted review, a partial measure. A redistricting scientist outside the authoring loop should read any claim headed for publication, testimony, or a commission.

---

## Refuter

# Refutation, metrics lens: the PlanScore cross-check at commit afab97e

**Result: none of the ten allegations is refuted.** Eight are upheld and two are partly upheld (6 and 7).
- **Numbers:** every number inside the allegations reproduces with my own code, to the printed digit.
- **Evidence corrected:** allegations 3, 4, 5(d) and 7.
- **Severity lowered to cosmetic:** allegations 6, 7 and 10. No number, record or conclusion changes under them.
- **New facts:** my reproductions add two facts the auditor did not have. PlanScore's own git history dates its switch of efficiency-gap formula (allegation 2). And a district tied after the swing can never pass the check silently (allegation 6).
- **"Checked and found sound":** every item reproduces. Four small imprecisions are listed at the end.

**Inputs, fetched 2026-10-11:**
- PlanScore's two pinned files (sha256 3b6e73c8… and f2f46c82…).
- Its served `geometry.json` files (6efa580e… and c6cf03bb…).
- Its metric pages.
- Its source, read as text from a bare clone and never run: 566cda4, and 3f866f9, which is today's HEAD.

**What I did not read:** commit messages, and other reviewers' files.

**Code used:**
- R1, R3, R4 and R5 use no repository code.
- R6 and R9 run the worktree's own functions, but only to test claims about those functions.

**Housekeeping:**
- `git status` in the worktree is empty. The gitignored `__pycache__` directories there predate this run.
- PlanScore's files hold district vote totals. They exist only under the scratch directory, and nothing was committed.

---

## 1. The README implies that `evaluate.partisan` reproduces PlanScore's gaps — UPHELD, material

**Reproduction (R1: exact rationals on PlanScore's totals rounded to whole votes; positive favours D):**

| Colorado | published | equal-turnout | ours (wasted votes) | miss, in units of 1e-4 |
|---|---|---|---|---|
| President 2020 | −0.0138 | −0.013766 | −0.015249 | 14.5 |
| Senate 2020 | +0.0296 | +0.029569 | +0.028864 | 7.4 |
| President 2016 | −0.0537 | −0.053666 | −0.027090 | 266.1 |
| Senate 2016 | +0.0649 | +0.064911 | +0.063745 | 11.6 |

Iowa's four races reproduce under the wasted-vote form, to within 0.03–0.38 units, because τ = S = 0 there. README.md mentions neither D-040 nor equal turnout anywhere (checked with grep).

**Assessment:**
- README.md:234–238 is literally true. The script does reproduce every published gap.
- But it does so with (S−½)−2(V−½) applied to `evaluate.partisan`'s seat count and vote share (check_planscore.py:292, 316), not with `evaluate.partisan.efficiency_gap`.
- The sentence's natural reading is therefore the opposite of the check's main finding.

**Severity:** material stands. It misdescribes what was validated, in the document most readers stop at. No published number is wrong, and the fix is one sentence.

## 2. PlanScore's code and its documentation disagree — UPHELD, minor, strengthened

**The pages:**
- planscore.org/metrics/ and /metrics/efficiencygap/ differ only in cache-busting query strings.
- The auditor's quotation appears verbatim ("…above the 50% (plus one) threshold … dividing by the total number of votes cast").
- Neither page mentions turnout, seat share or a formula. Nor do /about/, /about/historical-data/ or /models/ (/about/methodology/ and /faq/ return 403).

**R2:** `round(EG_equal_turnout(unrounded totals), 4)` equals the published value in all 8 races. For example, Colorado President 2016 gives −0.05366667, which rounds to −0.0537.

**New finding, from PlanScore's history:**
- `calculate_EG` counted wasted votes, with threshold `district_votes / 2`, until commit 24331854 (2021-08-22, "Changed EG calculation to use vote share instead of raw counts").
- So the metric page describes PlanScore's earlier definition. Its 50%-plus-one threshold is also `evaluate.partisan`'s default.

**Assessment:**
- Every sentence the auditor cites is scoped to PlanScore's code, with a commit citation, so none is false.
- The omission is still real, and it bears on D-040's VALUE question.
- "The opposite of what D-040 says" overstates. A reader checking CRITERIA.md's cited source finds a different definition from the one D-040 attributes to PlanScore.

## 3. The wasted-vote count has no external reference — UPHELD, minor, evidence corrected

**R3:** GerryChain 1.0.0's `wasted_votes` uses a half-vote threshold (gerrychain/metrics/partisan.py:93–100). Run on the same integers, record − GerryChain equals the record's threshold term in all 8 races:
- the differences run from −1.852e−6 to +9.667e−7;
- each is within k/T, which runs from 2.41e−6 to 3.15e−6.

**Correction:** "its published values validate only S and V" is slightly too strong.
- On Iowa's four sweeps, the wasted-vote gap itself reproduces the published value, so those values do exercise the Republican-won branch of the count.
- But in a sweep the two formulas coincide, so those values cannot tell CRITERIA.md §5.1's definition apart from PlanScore's.
- The term that separates the two, τ − S, is non-zero only in Colorado. No published value checks it; only the repository's internal identity does.

GerryChain's agreement lowers the practical risk.

## 4. The compactness residual is compared with the wrong quantity — UPHELD, minor, evidence qualified

**R4** (shapely 2.1.2 and pyproj 3.7.2, run on PlanScore's served outlines):

*Reproducing PlanScore's published values in EPSG:3857:*
- Reock rounds to PlanScore's published value in all 4 Iowa districts (0.3529, 0.5341, 0.4237, 0.4877) and all 8 Colorado districts.
- Polsby-Popper is within 0.0008 (Iowa) and 0.0010 (Colorado).

*Iowa reprojected to EPSG:5070, against the committed values:*

| | PlanScore outline (mean / min / max) | committed (mean / min / max) | committed vs outline |
|---|---|---|---|
| Reock | 0.450669 / 0.357962 / 0.535618 | 0.450664 / 0.357962 / 0.535611 | within 0.0014% |
| Polsby-Popper | 0.333611 / 0.276288 / 0.419682 | 0.333382 / 0.275516 / 0.419518 | −0.07% / −0.28% / −0.04% |

*Iowa, the size of each projection effect:*
- Changing EPSG:3857 to EPSG:5070 moves each district's Reock by +1.44%, +0.28%, +0.29% and −0.72%.
- The observed residual is 1.43% on Reock min and 0.54% on Polsby-Popper min. Both exceed the "about 1.15% / 0.43%" that progress.md:2583–2584 quotes.
- Against a Lambert azimuthal equal-area projection centred on Iowa:
  - EPSG:3857's largest error is 0.61% on Polsby-Popper and 0.80% on Reock;
  - EPSG:5070's is 0.43% and 1.16%.
- Moving the projection's centre from the centroid to the bounding-box centre changes these by at most 1.4e−5 relative.

*Colorado:*
- Mean Polsby-Popper moves from 0.265731 (EPSG:3857) to 0.265981 (EPSG:5070).
- The committed value is 0.286974, a difference of +0.020993. PlanScore's outline is 7.3% below it.
- Reock max differs by −2.35% and Reock mean by −1.02%.

**Corrections:**
- **The Colorado remainder is not purely the approximation.** It lumps together D-015's reassignment of split VTDs and the differences between the commission's block-built lines and TIGER VTD lines. Iowa bounds the second effect at 0.28% for one plan built two ways, so most of the 7.3% is plausibly the approximation. That is an inference, not a measurement.
- **"The served geometry is the scored one"** rests on Reock reproducing in all 12 districts.
  - Polsby-Popper is slightly off, which is consistent with simplified vertices.
  - Colorado's `geometry.json` carries a gzip timestamp of 2022-02-04, earlier than its 2025-12-03 upload.

## 5. "What D-015's approximation costs" — UPHELD, minor, with (d) only partly upheld

**(a) Attribution — upheld.**
- The heading (progress.md:2562), check_planscore.py:451–452 and the test at line 373 all attribute the whole shift to D-015.
- The body (progress.md:2566–2570) says the check cannot separate the approximation from PlanScore's allocation.
- Colorado's statewide share on PlanScore's totals equals the Phase 2 report's, 0.5693831949230015, to every digit.

**(b) Precision — upheld.** R5 reads co-draws-v2.csv.gz directly.

| | location, committed → PlanScore's totals | draws between the two values | absolute location: Monte Carlo SE | paired shift |
|---|---|---|---|---|
| \|efficiency gap\| | 41.815% → 43.160% | 269 | 2.8 points (indicator ESS 302), 3.0 at bulk ESS, 2.6 between chains | 1.35 ± 0.23 points |
| \|mean-median\| | 66.265% → 66.735% | 94 | 2.2–2.5 points | 0.47 ± 0.07 points |

- My own rank-normalized split R̂ is 1.0257 and bulk ESS 269.0 on the efficiency gap. Both match co-convergence-rectangles.json.
- The committed location runs from 34.0% to 55.0% chain by chain.
- The efficiency-gap shift is positive in all eight chains, from 0.60 to 2.16 points.
- So the shift is real. The absolute locations, printed to 0.1 point, are not resolved to that precision.

**(c) Mean-median caveat — upheld.**
- The Phase 2 report marks mean_median and partisan_bias untrusted for Colorado, because the statewide margin is 0.069 against a ±0.05 band.
- D-032 (DECISIONS.md:857–860) reports untrusted values beside their trust flags. This section does not.

**(d) A missing compactness cost — partly upheld.**
- *The numbers reproduce:*
  - the ensemble's maximum Polsby-Popper is 0.286104;
  - the committed 0.286974 lies above all 20,000 draws;
  - PlanScore's outline (0.265981; also 0.265731 and the published 0.26525) lies above 19,997 of them (99.985%).
- *But the section is not silent:*
  - it defers to "D-015's caveats on … compactness" (progress.md:2573–2574);
  - progress.md:1155–1161 already calls the plan's 0.287 "not a well-defined measurement";
  - progress.md:2586–2588 records 0.265 against 0.287.
- *What is missing:* the measured size of the cost, and its consequence for the plan's location.
- *A side note:* D-015 itself (DECISIONS.md) contains no compactness caveat. That caveat lives in progress.md:1155–1161.

## 6. Partisan bias: "same definition", and the tie refusal — PARTLY UPHELD, cosmetic

**R1:** counted exactly, there are 0 ties after the swing in all 8 races.

**R6:** I constructed 401 plans that tie exactly after the swing.
- 400 fail `definition_partisan_bias`, 1 is refused, and none passes.
- The two rules always differ by 1/(2k) there. Ours lands on exactly 0.5 in floating point and splits the seat; PlanScore's strict `R < B` never splits it.
- So the auditor's "nothing passes silently" holds.

**What is overstated:**
- "same definition" (progress.md:2509; check_planscore.py:29 and 151).
- "the script refuses a tied district" (progress.md:2598) holds for observed ties only. A tie after the swing fails a check instead, with the same outcome: no record is written.

The tie-rule difference is already disclosed at progress.md:2596–2598, so the section corrects its own table.

## 7. Declination: PlanScore's sweep value stored under "ours" — PARTLY UPHELD, cosmetic

**Verified facts:** record lines 65, 108, 151 and 194 each hold −0.6931471805599453, with `ours.declination` null beside them.

**Not upheld:**
- **The record does not claim the repository measured this value.** The key name and CONVENTIONS (check_planscore.py:152–154) call it a conversion, and the null is kept beside it.
- **No eight angle tests are claimed.** progress.md:2511 says "wherever ours is defined" and names the sweep constants.
- **The cited flag is a different quantity.** `Declination Is Valid: 0` is PlanScore's flag for its simulated-election headline (score.py@566cda4:634–635, 657), not a per-election value.

**Upheld:**
- On Iowa, `definition_declination` compares two constants. It tests only that `evaluate.partisan.declination` returns None, or ±1, on a sweep.
- k is undefined in progress.md (lines 2511 and 2521). In partisan.py, k means districts at line 357 and Republican-won districts at line 431.

## 8. Verdict-reading wording — UPHELD, minor

**Numbers:** under the 2016 presidential vote, PlanScore's −0.0537 (positive favours D) and ours +0.0271 (positive favours R) are both on the Republican side, with a ratio of 1.98.

**No distribution exists:** no committed draws carry a 2016 election. The CO and IA v2 draws carry only @G20PRE and @G20USS columns.

**Context:** "favours" is the repository's vocabulary for a sign (`FAVOURS`; report.py:262, "which party this plan favours"). What makes this sentence read as a verdict is that it names the party and quantifies the advantage ("by twice as much") for a real map that has no neutral distribution. The auditor's rewording fixes it.

## 9. The test docstring overclaims — UPHELD, minor

**R9** pointed `C.OUT` at edited scratch copies of the record and ran all 31 tests:

| Variant | Result |
|---|---|
| Unedited copy | 31 pass |
| Eight hand edits to unpinned fields: the published gap, `ours` efficiency gap, `ours_in_planscore_convention`, compactness, Iowa mean-median sign, Iowa district-1 population, Colorado τ | 31 pass, every time |
| Control: an edit to the pinned field `turnout_term` | the last test fails |
| `evaluate.partisan.efficiency_gap` swapped for the equal-turnout form | 10 earlier tests fail; the last test passes |

## 10. "2016 and 2020 races only" — UPHELD, cosmetic

**At 566cda4:** score.py:685–691 also lists US Senate 2018. Neither file carries 2018 Senate totals.

**At 3f866f9:** score.py:1058–1059 takes its years from data.py:77–78, where PRESIDENTIAL_YEARS includes 2024. So a re-score would publish a 2024 presidential gap for these files, and the pins would refuse it. No number changes.

---

## The auditor's "checked and found sound"

**Reproduce as stated:**
- **The repository's run:** exit 0, both pins match, output byte-identical to the committed record, 31 tests pass.
- **The algebra:**
  - With the half-vote threshold, the identity's residual is exactly 0 in all 8 races, in exact arithmetic.
  - The threshold term runs from −1.37e−6 to −1.85e−6 on Iowa and from +2.0e−7 to +9.7e−7 on Colorado. All are within k/T.
- **Printed numbers:** match the record to within 1.1e−16.
- **Iowa identity:**
  - district 1 is 8 persons short, and the spread is 94;
  - statewide totals are within 4 votes (759,060/897,668 against 759,061/897,672; 754,858/864,994 against 754,859/864,997);
  - the Phase 2 differences are +1.2565e−6 and −8.51e−7.
- **Failure paths:** reproduce.
- **Licence:** no licence file anywhere in PlanScore's tree at either commit (`git ls-tree`).
- **`combined_score`:** null.
- **Ensemble diagnostics:** my own code gives R̂/ESS of 1.0257/269.0 on the efficiency gap, 1.0370/268.2 on cut edges and 1.0039/2096.6 on population. There are 9,850 distinct |EG| values.

**Imprecise:**
- **Re-implementation.** PlanScore's `swing_vote` (566cda4:118–119) returns its input unchanged for a zero swing, where `_swing` recomputes. The difference is at floating-point level only, and no race has V = ½.
- **Orientation.** Partisan bias is also +0.25 in all four Iowa races, so its sign is exercised in 6 of 8 races, not 2.
- **Ensemble table.** "Election: G20PRE only" — the draws also carry G20USS columns. The location itself uses G20PRE.
- **Unverified section.** "Within 0.0006": declination differs by 0.000645.

## Reproduce

All of the above re-runs with one command:

```
bash /tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/refute2-crs/scripts/reproduce.sh
```

What the script does:
- It runs `tools/check_planscore.py --out <scratch>`, compares the output with the committed record, and runs pytest on the test file.
- It fetches both `index.json` and both `geometry.json` files and checks their sha256.
- It fetches the PlanScore pages.
- It reads PlanScore's source with `git show` on 566cda4 and 3f866f9, and runs `git log -S"statewide_seat_share - 0.5 - 2"`.
- It then runs these scripts, each from /tmp with `python -I`:

| Script | What it does |
|---|---|
| `r1_exact.py` | `fractions.Fraction`. Wasted votes with `need = t//2+1` (majority) or `t/2` (half). EG_ET = (S−½)−2(V−½). Mean-median, partisan bias with exact post-swing tie counts, and declination. Also R2, transcribing `calculate_EG` on the unrounded totals. |
| `r3_gerrychain.py` | `sum(w2-w1 for w1,w2 in map(wasted_votes, dem, rep))/T` |
| `r4_compactness.py` | `4πA/L²` and `A/(π·minimum_bounding_radius²)` after `pyproj.Transformer(4326→crs, always_xy=True)`, for EPSG:3857, EPSG:5070 and a state-centred Lambert azimuthal equal-area projection |
| `r5_location.py` | Mid-rank location. Arviz-style rank-normalized split R̂ and bulk ESS. Indicator-ESS Monte Carlo SE. |
| `r6_swing_ties.py` | Runs the worktree's `compare_race` on 401 plans that tie exactly after the swing |
| `r9_mutation.py` | pytest with a plugin that resets `check_planscore.OUT` to an edited scratch copy, or swaps `efficiency_gap` |

The full log is `refute2-crs/out/reproduce.log`.

---

## Author's response

The refuter refuted no allegation, so each is answered by a change, in the commit
that follows `afab97e`. The script and the record it writes carry the changes to
the check itself; `tests/test_planscore_check.py` pins them.

| # | Allegation | Refuter | What changed |
| --- | --- | --- | --- |
| 1 | The README implies that `evaluate.partisan` reproduces PlanScore's published efficiency gaps | Upheld; material | The README now says PlanScore's own formula, fed the seats and votes `evaluate.partisan` computes, reproduces the published values, and that this repository's wasted-vote gap differs from them on every Colorado race, by a factor of two under the 2016 presidential vote (D-040). |
| 2 | PlanScore's code and the metric page `CRITERIA.md` cites define the efficiency gap differently | Upheld, strengthened | `docs/progress.md`, D-040, the `efficiency_gap` docstring and the script's docstring scope the claim to PlanScore's code and published values, give the metric page's wasted-vote definition, and record from the refuter that PlanScore's code counted wasted votes until August 2021. Whether to tell PlanScore is left to the owner. |
| 3 | The wasted-vote count has no external reference | Upheld, evidence corrected | The script now checks the count against GerryChain's own `wasted_votes` on every race, within `k/T`, and fails otherwise. `docs/progress.md` notes that Iowa's published values exercise the count only where the two formulas coincide. |
| 4 | The compactness residual is compared with the wrong quantity | Upheld, qualified | `docs/progress.md` reports the reprojection split from these reports: Iowa's Reock difference is projection alone, and up to 0.3% of Polsby-Popper remains. Colorado's remainder is plausibly mostly the VTD outline, with line differences bounded at 0.3% on Iowa. The finding that EPSG:3857 distorts Iowa's Reock less than EPSG:5070 is pointed at D-005. |
| 5 | "What D-015's approximation costs" claims more than it shows | Upheld; (d) partly | The section is retitled to name both sources. It gives the paired shift (1.35 ± 0.23 points, positive in all eight chains) and the location's Monte Carlo error of about 3 points, marks mean-median untrusted on this plan as the Phase 2 report does, adds the compactness cost (0.287 against 0.266) and its location, and cites the plan's compactness caveat where it lives, Experiment 2 §7, rather than D-015. |
| 6 | Partisan bias: "same definition", and the tie refusal | Partly upheld; cosmetic | The table says the two definitions differ for a district tied after the swing to 50%, of which these races have none. "What this does not check" says such a tie fails the check rather than being refused. |
| 7 | PlanScore's sweep value is stored under "ours" | Partly upheld; cosmetic | The record now stores null under `ours_in_planscore_convention.declination` where ours is undefined, and says what each declination check compared. `docs/progress.md` defines `k` and says the conversion is tested in Colorado's four races. |
| 8 | Wording that reads as a verdict on a real map | Upheld | `partisan.py` and `docs/progress.md` now say both values lie on the Republican side of zero in their own orientation, PlanScore's twice as far from it. |
| 9 | The test file's docstring claims more than its last test can detect | Upheld | The docstring now says what the last test pins and what it cannot see. |
| 10 | "Per-election gaps for the 2016 and 2020 races only" | Upheld; cosmetic | `docs/progress.md` lists the races PlanScore's code at 566cda4 scores, the 2018 Senate race among them. |

The auditor's handoffs are left for the people they name: the spread check that
does not test district populations one by one (`Code Reviewer`), the difference
between PlanScore's block-built outlines and the TIGER counties (`GIS QA
Engineer`), and whether the two plans are the ones in force (`Election Law
Analyst`).
