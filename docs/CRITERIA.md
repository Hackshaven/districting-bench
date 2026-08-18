# districting-bench — Criteria Set

Reference for every criterion, threshold, and metric the system depends on: where
it comes from, who decided it, and whether it can be argued with.

The purpose of this document is to make the system's value judgments
**auditable**. A districting system that reports a fairness score is only as
honest as the choices buried in that score. Any criterion classed `VALUE` below
is a contested normative decision that we are making on someone's behalf.

---

## How to read this

| Class | Meaning | Risk if wrong |
| --- | --- | --- |
| `FEDERAL` | Required by the U.S. Constitution or federal statute as currently interpreted | Low, but **check the date** — this moved substantially in April 2026 |
| `STATE` | Jurisdiction-specific; read from config, never hardcode | Low — knowable per state, but varies enormously |
| `VALUE` | A contested normative choice | **High. This is where the system's honesty breaks.** |
| `EMPIRICAL` | A factual claim about the world that could be tested and might be false | Medium — testable, and some are currently disputed |
| `DERIVED` | Computed from the above | None |

**The central conclusion, stated up front:** every constraint that makes a map
*legal* is checkable pass/fail. Every criterion that makes a map *good* is
`VALUE` class. There is no exception to this and no amount of mathematics
dissolves it.

That asymmetry is what justifies the phase gate. Detection — is this plan an
outlier relative to what the stated legal criteria produce? — has manufacturable
ground truth and can be optimized against. Generation — what is the fair map? —
does not and cannot. Build and loop the detector; build but do not optimize the
generator.

This mirrors the geometry/photometry split in the sphere-sim project. Same
structure, same reason.

---

## Conventions

**Units.** Population in persons (not citizens, not voters — see §3.1). Vote
share as two-party Democratic fraction unless stated. Seats as integer counts.
Deviation as a fraction of the ideal district population.

**Geography.** Districts are built from units. Which unit matters enormously:

| Unit | Count per state | Use |
| --- | --- | --- |
| County | 3–254 | Iowa congressional. Tiny graphs, fast, legally mandated there. |
| Voting district (VTD/precinct) | 1,000–20,000 | The standard working unit. Election data attaches here. |
| Census block | 100,000–700,000 | Legally the finest unit. Too large for most ensemble work. |

**Start with counties.** Iowa's 99-county congressional problem closes a full
loop in seconds. Precinct-level work is a data-plumbing project, not a
methodology project.

**Adjacency.** Districts must be contiguous, which requires an adjacency graph,
which requires deciding whether units touching only at a corner are adjacent
(usually no — rook, not queen) and whether units separated by water are adjacent
(jurisdiction-specific, and the source of most real contiguity litigation).
Islands force explicit handling. `EMPIRICAL` note: naive adjacency from shapefile
topology produces disconnected components in nearly every state. Fix before
anything else.

**Ensembles.** Plans are sampled, not enumerated. The number of valid partitions
of a state exceeds the number of atoms in the universe, so every claim is a
statement about a sample from a distribution, and the distribution depends on the
sampler. State which sampler and report convergence diagnostics — the
Gelman–Rubin PSRF is the convention, with values between 1.00 and 1.01 taken as
good mixing.

---

## 1. Federal constraints — hard, checkable, pass/fail

These are lint, not loop material. Fail the build; do not iterate.

| Constraint | Threshold | Class | Source |
| --- | --- | --- | --- |
| Congressional population equality | Near-zero deviation; any deviation must be justified | `FEDERAL` | *Karcher v. Daggett* (1983). In practice single-digit persons. |
| State legislative population equality | ≤10% total deviation as safe harbor | `FEDERAL` | *Reynolds v. Sims* (1964), *Brown v. Thomson* (1983). Total deviation = (max − min) / ideal. |
| Contiguity | Every district connected | `FEDERAL` / `STATE` | Universal in practice; water contiguity varies. |
| Race may not predominate | No bright line | `FEDERAL` | *Shaw v. Reno*, *Miller v. Johnson*, *Cooper v. Harris*. Strict scrutiny if race predominates over traditional criteria. |
| VRA §2 vote dilution | See §4 | `FEDERAL` | Substantially rewritten by *Louisiana v. Callais* (Apr. 29, 2026). |
| Partisan gerrymandering | **No federal cause of action** | `FEDERAL` | *Rucho v. Common Cause* (2019), 5–4. Nonjusticiable political question. |

### 1.1 The Rucho consequence

There is no federal remedy for partisan gerrymandering. State courts have split:
several have found such claims justiciable under state constitutional provisions,
while courts in South Carolina, Kansas, Nevada, New Hampshire, and North Carolina
have held them nonjusticiable.

**This determines who the system is for, and it is jurisdiction-dependent.** In a
state whose supreme court has closed the door, a partisan outlier analysis is a
public-education artifact, not litigation evidence. Encode the available remedy
per state; do not produce output implying a cause of action that does not exist.

---

## 2. State criteria — configuration, never hardcode

States differ in *which* criteria apply, *how* they are measured, and critically
*in what order*. Ordered-criteria states are the cleanest targets because the
state has already made the value choices that would otherwise be ours.

### 2.1 Iowa — the recommended starting jurisdiction

`STATE`. Iowa Code Chapter 42. Congressional districts are composed of whole
counties. Criteria are explicitly ordered:

1. Population equality
2. Contiguity
3. Political subdivision integrity (whole counties)
4. Compactness

And Iowa **explicitly forbids** considering political affiliation, prior election
results, incumbent addresses, or demographic data other than population.

Two reasons this is the right first target: 99 units instead of thousands, and a
statutory criteria ordering that removes our discretion entirely. If the system
cannot reproduce sensible results on Iowa, nothing downstream is trustworthy.

### 2.2 Colorado — ordered criteria with a competitiveness mandate

`STATE`. Amendments Y and Z (2018), independent commissions. Criteria ordered
roughly: equal population and VRA compliance; contiguity; communities of interest
and political subdivision preservation; compactness; and then — unusually —
**maximize the number of politically competitive districts**, to the extent
possible without violating the preceding criteria. Protecting incumbents,
declared candidates, or political parties is prohibited.

Colorado is the interesting second target precisely because competitiveness is
mandated. Most states treat competitiveness as optional or ignore it, and it
trades against other criteria in ways worth measuring rather than assuming.

### 2.3 Common state criteria and their measurement problems

| Criterion | Typical form | Class | Note |
| --- | --- | --- | --- |
| County/municipality splits | Minimize count | `STATE` | Count of split subdivisions, or count of split *pieces* — these differ and rank plans differently. Pick one and say which. |
| Nesting | 2:1 or 3:1 house-in-senate | `STATE` | Hard combinatorial constraint; sharply reduces the feasible space. |
| Communities of interest | Preserve | `STATE` / `VALUE` | See §6. The least formalizable criterion in the entire field. |
| Competitiveness | Maximize or ignore | `STATE` / `VALUE` | Definition varies: margin within 5 points? 10? Under which election? |
| Incumbent protection | Prohibited, permitted, or **required** | `STATE` | See §4.2 — *Callais* made this federally relevant in a way it previously was not. |
| Core retention | Preserve prior district cores | `STATE` | Entrenches the prior map, including its flaws. A `VALUE` choice dressed as continuity. |

---

## 3. Compactness — four measures that disagree

`VALUE` throughout. There is no correct compactness measure, and the common ones
rank plans differently on the same data.

| Measure | Formula | Failure mode |
| --- | --- | --- |
| Polsby-Popper | 4πA / P² | Perimeter-sensitive. Punishes natural coastlines and river borders severely. A state with a fractal shoreline scores badly no matter how the lines are drawn. |
| Reock | A / A(min bounding circle) | Insensitive to boundary detail; a district can be visibly ragged and score well. |
| Schwartzberg | P / circumference of equal-area circle | Same perimeter sensitivity as Polsby-Popper, different scaling. |
| Convex hull | A / A(convex hull) | Punishes legitimately concave geography (bays, mountain valleys). |
| **Cut edges** | Count of adjacent unit pairs in different districts | Discrete, graph-based, immune to coastline fractality. Not intuitive to non-technical readers, and depends on the unit graph. |

**Consequence:** a plan can sit in the top decile on Reock and the bottom decile
on Polsby-Popper. Reporting one number is a choice about which geography to
forgive. Report all of them, always, and highlight disagreements rather than
resolving them.

`EMPIRICAL`, testable: measure the rank correlation between these on your
ensembles. If they correlate above ~0.9 in a given state, the choice does not
matter there and you can say so. If they diverge, the choice is doing real work
and must be surfaced.

---

## 4. Racial representation — the most unsettled section

### 4.1 The framework as it stood

VRA §2 prohibits practices that result in denial or abridgement of the right to
vote on account of race. The *Thornburg v. Gingles* (1986) framework required
plaintiffs to show a minority group sufficiently large and geographically compact
to constitute a majority in a district, political cohesion within that group, and
majority bloc voting usually sufficient to defeat the minority's preferred
candidate — then a totality-of-circumstances inquiry.

### 4.2 What *Louisiana v. Callais* changed — April 29, 2026

The Court held 6–3 that Louisiana engaged in an unconstitutional racial
gerrymander by creating a second majority-Black district to comply with §2, and
established a more stringent standard for vote-dilution claims. Three changes
matter algorithmically:

1. **Illustrative maps must satisfy all of the jurisdiction's nonracial goals,
   including its political goals and incumbent protection.** A neutrally-generated
   ensemble map — the standard practice for a decade — no longer suffices as
   §2 evidence on its own.
2. **Racially polarized voting analysis must control for partisan preference.**
   Evidence that Black and white voters supported different candidates is
   insufficient without showing the pattern is not explained by partisanship.
3. **Totality of circumstances now requires an objective likelihood of present-day
   intentional discrimination.** Historical evidence and present-day disparities
   are, per the majority, insufficient on their own.

Justice Kagan, joined in dissent, characterized the majority as having made "a
nullity of Section 2." The majority framed the decision as an update to the
evidentiary requirements rather than an abandonment of the framework. Both
characterizations are in the record; the system should describe the holding, not
adjudicate the dispute over its magnitude.

**Read the opinion, not summaries.** Coverage of this decision is heavily
polarized and secondary sources on both sides characterize the holding more
strongly than the text supports in places.

### 4.3 Racially polarized voting — what the methods can and cannot do

`EMPIRICAL`, and this is a hard limit rather than an implementation gap.

| Method | What it does | Limitation |
| --- | --- | --- |
| Homogeneous precincts | Read vote share directly from near-single-race precincts | Requires segregation to work; fails in integrated areas |
| Ecological regression | Bivariate fit of vote share on racial composition | Aggregation bias; can produce impossible estimates |
| Ecological inference (King; PyEI) | Hierarchical Bayesian per-precinct model | Best available, still subject to fundamental indeterminacy |
| Survey + MRP calibration | Individual-level data poststratified | Sparse subgroup samples; expensive |

**All of these estimate correlation from aggregate data. None establishes
causation.** *Callais* now asks whether polarization is explained by partisanship
rather than race — a causal question these tools cannot answer. The system must
report this limitation prominently in any output touching §4, rather than
producing a confident-looking number that implies more than the method supports.

`VALUE`: whether to attempt this at all. Recommendation for a first build: defer
entirely, document as a known omission with a note on why it matters.

---

## 5. Partisan fairness metrics — all `VALUE`, all gameable

### 5.1 The metrics

| Metric | Definition | Fails when |
| --- | --- | --- |
| Efficiency gap | (wasted votes A − wasted votes B) / total votes | Threshold for "too much" is arbitrary and sensitive to voter geography |
| Mean-median | mean(D vote share) − median(D vote share) | Unreliable when one party predominates |
| Partisan bias | Seat share asymmetry at a hypothetical 50-50 vote | Requires a counterfactual election |
| Declination | Angle between fitted lines through sorted district vote shares | Undefined when one party wins every seat |
| Seats-votes curve | Full mapping of vote share to seat share | Requires uniform-swing assumption |

Published guidance holds that all of these are reliable in competitive states,
but that only the efficiency gap and declination should be trusted where one
party predominates.

### 5.2 The gameability result — the central design constraint

For mean-median, efficiency gap, declination, and the GEO metric, it is possible
to construct plans with an extremely lopsided seat count while the metric value
stays within any reasonable predetermined bound (arXiv 2409.17186).

**Therefore:** optimizing toward any of these produces a gerrymander that scores
clean. This is Goodhart's law with a formal proof attached, and it is the reason
the generation half of this system must not have an objective function. Report
all metrics side by side; surface disagreements; never collapse to one number.

`EMPIRICAL`, and Experiment 3 in the prompt: reproduce this result on your own
data before building anything that consumes a fairness score.

### 5.3 What "fair" could mean — the choices we are declining to make for anyone

These are mutually incompatible and each has serious defenders. The system must
support all of them as selectable parameters and advocate for none.

| Definition | Claim | Objection |
| --- | --- | --- |
| Proportionality | Seat share should track vote share | Single-member districts have never delivered this anywhere; not a legal requirement in the U.S. and the VRA expressly disclaims racial proportionality |
| Partisan symmetry | Each party should get the same seats for the same vote share | Requires counterfactual elections |
| Competitiveness | More close races means more accountability | Produces high volatility and can reduce minority representation |
| Geographic representation | Districts should track real communities | Communities are contested and self-reported |
| Neutral-process | Whatever emerges from criteria applied blind to outcomes | Systematically biased in effect — see §5.4 |

### 5.4 Neutral criteria are not neutral in effect

`EMPIRICAL`, well-established. Because Democratic voters cluster densely in city
centers and along waterways and rail corridors while Republican voters distribute
more evenly across suburban, exurban, and rural areas, maps drawn without
reference to election results can systematically favor Republicans (Chen &
Rodden 2013). The same phenomenon has long been observed in other countries with
respected neutral boundary commissions.

The magnitude is not static: over recent cycles cities have become somewhat less
Democratic, suburbs have shifted, and rural areas more Republican, so the size of
the effect must be re-measured per state and per cycle rather than assumed.

**Consequence:** "apply neutral rules" is itself a `VALUE` choice with a
predictable partisan direction. Whether to correct for it is another. Neither can
be dissolved by better math, and the system should state which it is doing.

### 5.5 The tradeoff question — currently disputed

`EMPIRICAL`, and genuinely open. The law of redistricting assumes tradeoffs
between criteria: better compactness costs minority representation, better
partisan fairness costs county integrity, and so on. Recent work
(Stephanopoulos, *Redistricting Without Tradeoffs*, 126 Colum. L. Rev. 1001
(2026), using more than fourteen billion generated maps) finds these tradeoffs
are generally weak to nonexistent — progress on one dimension usually does not
require regress on another.

This is one recent paper against decades of contrary assumption. **Treat as a
hypothesis to test on your own ensembles, not a premise to build on.** If it
holds, a substantial portion of redistricting law's framing is empirically wrong,
which is the most interesting finding available in this project.

---

## 6. Communities of interest — the least formalizable criterion

`VALUE` entirely. Most state criteria lists include COI preservation. Almost none
define it operationally.

Available approaches, none satisfactory:

- **Self-reported.** Districtr and Representable collect public-submitted COI maps.
  Genuinely democratic, and unevenly distributed — well-organized communities
  submit, others do not, so optimizing for submitted COIs systematically favors
  the organized.
- **Proxy-based.** School districts, media markets, watersheds, commuting zones,
  municipal boundaries. Objective and arbitrary — the choice of proxy *is* the
  definition.
- **Inferred.** Clustering on demographic or economic similarity. Risks
  reconstructing racial segregation as a neutral-sounding criterion, and may
  trigger the race-predominance problem in §1.

**Recommendation:** support COI as an input layer, never as an objective function.
Let a user supply COI geometry and report how many are split; do not let the
optimizer chase a COI score.

---

## 7. Logistical and administrative constraints — the underrated section

These rarely appear in reform proposals and they determine whether a map can
actually be run. All `STATE` unless noted.

| Constraint | Effect | Note |
| --- | --- | --- |
| Split precincts | Each unique district combination creates a distinct ballot style | Direct cost and error-rate driver. Election officials weight this heavily; academic work usually ignores it. |
| Ballot style count | `DERIVED` — count of unique district tuples across the map | The single best proxy for administrative burden. Compute and report it. |
| Polling place integrity | Splitting a VTD splits a polling place | Voters at one location receiving different ballots is a known source of ballot-misassignment errors |
| County election administration | Counties administer; districts crossing counties multiply coordination | Distinct from the county-splits criterion, which is about representation, not logistics |
| Incumbent pairing | Two incumbents in one district | `STATE`: prohibited, permitted, or — post-*Callais* — potentially required as a "political objective" |
| Candidate filing deadlines | A map adopted after filing opens cannot be used | Hard operational deadline; several 2026 cases turned on it |
| Data vintage | Mid-decade redistricting uses stale census data | Population equality is measured against a snapshot that may be five years old |

`DERIVED` metric worth computing and reporting, because nobody else does: **ballot
styles per 10,000 voters.** It is objective, administratively meaningful, and
orthogonal to every partisan measure — which makes it one of the few criteria in
this document that is not a `VALUE` choice in disguise.

---

## 8. Detection gates — the only thresholds worth optimizing against

Phase 1 targets. Unlike everything in §3–§6, these have manufacturable ground
truth: you build the gerrymander, so you know it is one.

| Metric | Gate | Class | Basis |
| --- | --- | --- | --- |
| True positive rate on planted gerrymanders | ≥ 0.95 at a 2-seat shift | `VALUE` | Threshold chosen; the *measurement* is objective |
| False positive rate on neutral null cases | ≤ 0.05 | `VALUE` | Same |
| Minimum detectable seat shift | Report, do not gate | `DERIVED` | The honest headline number for the whole system |
| Ensemble convergence (PSRF) | 1.00–1.01 | `EMPIRICAL` | Standard mixing diagnostic |
| Legal constraint compliance | 100% | `FEDERAL` | Pass/fail lint, not a loop |

**Null cases are as important as positive cases.** A detector that flags every
map in a state with clustered urban population has learned political geography,
not gerrymandering. The false positive rate on neutrally-drawn maps is what
separates a real detector from a partisan-geography thermometer.

---

## 9. Data sources and known defects

| Source | Provides | Known defect |
| --- | --- | --- |
| Census PL 94-171 (2020) | Population, race, VAP by block | **Differential privacy noise** from the TopDown algorithm. Relative error is largest in small-population blocks. Whether redistricting law permits, forbids, or requires accounting for this is unsettled. Quantify the effect on your metrics; do not ignore it. |
| VEST | Precinct-level election results | Crosswalked from 2010 precinct shapes to 2020 blocks and re-aggregated. Introduces estimation error before you touch it. |
| ALARM 2020 Redistricting Data Files | VEST joined to Census at precinct level, tidied | The recommended starting point. Saves weeks. |
| Redistricting Data Hub | Shapefiles, enacted plans, COI submissions | Coverage varies by state |
| PlanScore | Scored enacted and historical plans | Useful as an external cross-check on your metric implementations |

`EMPIRICAL` and worth a one-time measurement: run the detection loop with and
without DP noise injected and report whether it changes any conclusion. If it
does, that is a publishable finding on its own.

---

## 10. What this system does not model

Stated explicitly so silence is not mistaken for a claim.

- Turnout differences between districts (all metrics here use votes cast, not
  eligible voters — this materially affects the efficiency gap)
- Candidate quality, incumbency advantage, and campaign spending
- Uncontested races (which break every vote-share metric and require imputation)
- Voter behavioral response to new district lines
- Primary elections, where most seats are actually decided in safe districts
- Multi-member districts and proportional systems
- Prison gerrymandering (incarcerated persons counted at facility, not residence)
- Non-citizen and under-18 population differences across districts
- Any state-court doctrine specific to a jurisdiction's constitution

The first, fifth, and eighth are the ones most likely to matter for
interpretation.

---

## 11. Provenance summary

| Class | Approximate count | Where the risk sits |
| --- | --- | --- |
| `FEDERAL` | 6 | Low, but §4 moved in April 2026 and may move again |
| `STATE` | 12+ per jurisdiction | Low — knowable, but must be read from config |
| `VALUE` | 20+ | **All of it.** Concentrated in §3 compactness, §5 fairness, §6 COI |
| `EMPIRICAL` | 6 | Testable. Three are actively disputed. |
| `DERIVED` | 4 | None |

**The four things most likely to make this system dishonest, in order:**

1. **Collapsing fairness to one number.** Every single metric is provably
   gameable. The moment output is a scalar, the system can be optimized against
   and becomes a gerrymandering tool with a certificate.
2. **The firewall leaking.** If partisan data reaches the ensemble generator by
   any path, the neutral baseline is no longer neutral and every outlier claim
   built on it is void.
3. **Implying a remedy that does not exist.** Post-*Rucho* and post-*Callais*, the
   available legal pathway is narrow and jurisdiction-dependent. Output that reads
   like litigation evidence where none is admissible misleads its reader.
4. **Presenting `VALUE` choices as computed results.** The failure mode is not a
   wrong number; it is a defensible number that conceals whose definition of fair
   it encodes.

None of the four is a mathematical problem. All four are addressed by the same
discipline: report distributions rather than verdicts, name the criteria set in
every output, and make every value choice a visible, changeable parameter.

---

## Sources

- Iowa Code Chapter 42 (ordered redistricting criteria, whole-county districts)
- Colorado Constitution, Amendments Y and Z (2018) — independent commissions, ordered criteria including competitiveness
- *Rucho v. Common Cause*, 588 U.S. 684 (2019) — partisan gerrymandering nonjusticiable in federal court
- *Louisiana v. Callais*, 608 U.S. ___ (Apr. 29, 2026) — https://www.supremecourt.gov/opinions/25pdf/24-109_21o3.pdf
- CRS, *Congressional Redistricting: High Court Narrows Voting Rights Act in Louisiana v. Callais* — https://www.congress.gov/crs-product/LSB11431
- *Thornburg v. Gingles*, 478 U.S. 30 (1986)
- *Karcher v. Daggett*, 462 U.S. 725 (1983); *Brown v. Thomson*, 462 U.S. 835 (1983)
- Chen & Rodden, "Unintentional Gerrymandering," 8 Q.J. Pol. Sci. 239 (2013)
- Chen & Rodden, "Cutting Through the Thicket," Election Law Journal (2015)
- Stephanopoulos, "Redistricting Without Tradeoffs," 126 Colum. L. Rev. 1001 (2026) — https://columbialawreview.org/content/redistricting-without-tradeoffs/
- "Don't Trust A Single Gerrymandering Metric," arXiv:2409.17186
- "Bounds and Bugs: The Limits of Symmetry Metrics," arXiv:2406.12167
- DeFord, Duchin & Solomon, "Recombination: A Family of Markov Chains for Redistricting"
- McCartan & Imai, "Sequential Monte Carlo for Sampling Balanced and Compact Redistricting Plans"
- MGGG GerryChain — https://mggg.org/posts/gerrychain
- ALARM Project `redist` and 50-State Simulations — https://alarm-redist.org/
- PlanScore metric documentation — https://planscore.org/metrics/
- Redistricting Data Hub, "Racially Polarized Voting" — https://redistrictingdatahub.org/resources/racially-polarized-voting/
- MGGG PyEI — https://www.mggg.org/posts/PyEI
- "Understanding and Mitigating the Impacts of Differentially Private Census Data on State Level Redistricting," arXiv:2409.06801

*This document describes an independent research system. It is not affiliated with
any redistricting commission, court, party, or advocacy organization, and it takes
no position on the merits of any cited decision.*
