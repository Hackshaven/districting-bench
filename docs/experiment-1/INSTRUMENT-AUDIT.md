# Experiment 1 — adversarial audit of the instrument and its headline

Run before the results were written up, against `tools/experiment_1_sensitivity.py`
and `docs/experiment-1/experiment-1-results.json`, with both states' committed
draws and the epsilon-sweep checkpoints on disk.

Five auditors attacked along independent lenses; every allegation went to a
separate refuter instructed to default to *refuted*. **20 alleged, 5 survived.**
26 agents, 817 tool calls.

**It refuted this experiment's headline claim using a number larger than the one
the headline claimed.** The assertion that the tolerance-compactness tradeoff is
invisible to any within-ensemble design is false: a tail filter on a single
fixed-tolerance ensemble recovers Cliff's delta −0.480, against the −0.417 the
experiment called "the largest tradeoff in the project". The experiment's own
results file already published a within-ensemble version of the same effect.

It also found that two of the five published rungs sit at the centre of their own
permutation null, that the ranked list is Experiment 2's correlation matrix
re-summarised with ranks 1 and 2 being one relationship counted twice, that the
ordering does not survive changing the election, and that Colorado's
population-equality row is measured entirely outside the range *Karcher* permits.

Kept verbatim, as `docs/DECISIONS.md` D-019 requires of a refuted claim.

---

# Audit of Experiment 1 — findings

All numbers below I ran myself (`/tmp/aud1/a1.py` … `a15.py`, checkpoints re-read via `dataclasses.replace(E2.IOWA, epsilon=…, chains=4, steps=400)` + `E2.load_checkpoint`; committed draws via `E1.load_rows`). Where I confirm a prior auditor I say so; where the number is new I say that too.

---

## 1. Is the epsilon-vs-compactness tradeoff REAL?

**Yes — three of the five published rungs are real, two are not, and the published magnitude is the *weakest* of the available estimates.** It is not burn-in. It is not sample size at the loose end. It *is* partly mixing at the tight end.

**What survives.** My own chain-label permutation, all 35 4-vs-4 relabellings of the 8 chains (4 tight + 4 loose), on `polsby_popper_mean`:

| epsilon | observed | rank in null | p | null median |
|---|---|---|---|---|
| 5e-4 | −0.0904 | 19/35 | 0.543 | +0.000 |
| 1e-3 | −0.1448 | 14/35 | 0.400 | +0.000 |
| 5e-3 | −0.3610 | **1/35** | 0.029 (floor) | +0.000 |
| 1e-2 | −0.4127 | **1/35** | 0.029 | +0.000 |
| 5e-2 | −0.4172 | **1/35** | 0.029 | +0.000 |

The two tight rungs sit *at their own null's centre*. They carry no information about epsilon. The three loose rungs are the single most extreme of all 35 relabellings. This confirms the two surviving "confounding" allegations and the "methodological-claim" allegation exactly.

**Not burn-in — I tested it and the allegation fails.** Using the committed 8×1500 Iowa chains at the identical epsilon 2e-4: pooled median PP 0.3258; first-400-of-each-chain 0.3294; last-400 0.3281. No drift. Per-chain 300-draw windows wander without trend. Delta vs the 5e-2 cell is **−0.512 using first-400s and −0.483 using last-400s**, against the shipped −0.417 from the 4×400 replay. Longer chains *strengthen* the effect. The "monotonicity is a burn-in transient" line of attack is dead.

**Mixing is a real confound, but only on the tight side.** The sweep's baseline cell is split R-hat 1.157 / ESS 19.2 on the headline column (24–112 distinct plans per 400-step chain) against 1.012 / 188.2 at 5e-2. The 2-vs-2 within-cell noise floor is ~3× larger at tight epsilon. That is exactly what puts the two tight rungs inside the null and nothing else.

**Honest strength.** The claim that survives is: *loosening Iowa's population tolerance past roughly 1e-3 buys compactness, as a threshold, not a gradient.* Supporting evidence: 16/16 cross-chain pairs negative at 5e-2; p at the permutation floor at three rungs; stable under 3.75× longer chains and 2× more chains; strengthens to −0.48/−0.52 on the better sample.

**Honest magnitude — the deltas oversell it.** Cliff's delta −0.417 corresponds to median mean-Polsby-Popper **0.3258 → 0.3652**, a 0.039 (12%) shift. Publish both numbers.

**New: the shape is a threshold in absolute persons, not a function of epsilon.** Pooling all 22,000 Iowa draws (7 sweep cells + the committed ensemble) and binning by absolute population spread — bins that draw from *multiple* epsilon cells, so this is not a cell label:

```
spread [0,100)      n=724   medPP 0.3361
spread [100,200)    n=4647  medPP 0.3346
spread [200,400)    n=9010  medPP 0.3250
spread [400,800)    n=1484  medPP 0.3470   <- sources: 5e-4, 1e-3, 5e-3
spread [800,1600)   n=1361  medPP 0.3483
spread [1600,3200)  n=205   medPP 0.3545
spread [3200,6400)  n=1144  medPP 0.3611
spread [6400,12800) n=1416  medPP 0.3651
spread [25600,+)    n=1502  medPP 0.3650
```

Flat-to-inverted below 400 persons; the entire effect accrues between ~300 and ~6,000 persons and saturates. "Monotone over a 250-fold range of tolerance" is false in the raw units as well as in the deltas.

**Scope, which changes what the finding means.** Iowa's ideal district is 797,592. Epsilon 5e-3 permits a spread of ~7,976 = **1.0% total deviation**; *Karcher* struck down 0.6984%. Every rung that clears the noise floor is a plan no congressional map may legally occupy. Every epsilon a congressional plan can actually be drawn at (2e-4 through 1e-3, spread ≤ 1,548 = 0.19%) sits on the flat part where p = 0.40–0.54. **The tradeoff is real and legally inert.** That is a finding, not a defect — but it must be the second sentence of the write-up, not a footnote.

---

## 2. The methodological claim: **FALSE. Strike the sentence.**

> "the largest tradeoff here lives between a criterion's TOLERANCE and another criterion, and no within-ensemble correlation design can see it"

**The number that kills it.** Take the ensemble at a *single fixed* epsilon = 5e-4 (1,600 draws, one cell, no resampling, no tolerance variation). Restrict to the 116 draws whose population spread falls inside the tight ensemble's support (≤ 314 persons — the 2e-4 cell's maximum). Cliff's delta on Polsby-Popper of that subset against the rest:

> **−0.480** (median PP 0.3081 vs 0.3443)

That is **larger than the −0.417 the experiment calls "the largest tradeoff in the project"**, and it is obtained by a within-ensemble filter on a fixed-epsilon ensemble. It holds in all four chains separately: **−0.355, −0.810, −0.265, −0.573** (n_sub = 26, 22, 30, 38). The same filter on the 1e-3 cell gives **−0.421** (31 draws).

**And the instrument already publishes a within-ensemble version of the effect, in the same JSON file.** `states.IA.detail[population_equality].levels[q=0.90].delta.compactness_pp = −0.171`, from the committed fixed-epsilon 12,000-draw ensemble. That clears the module's own `BINDS_AT = 0.147`. So one half of Experiment 1 measures the effect within a fixed ensemble and the other half asserts it cannot be measured within a fixed ensemble. (It is chain-noisy — per-chain, on a global cut of 147 persons, 7 of 8 chains negative, median ≈ −0.15 — but it is there and it is above the instrument's own threshold.)

**What is actually true, and is worth keeping.** The within-ensemble design goes blind when the ensemble's own tolerance does not straddle the band where the effect lives:

| ensemble epsilon | rho(spread-goodness, PP) | matched-tail Cliff's delta |
|---|---|---|
| 5e-4 | −0.142 | **−0.480** |
| 1e-3 | −0.084 | −0.312 |
| 5e-3 | −0.087 | −0.123 |
| 1e-2 | −0.038 | −0.092 |
| 5e-2 | −0.049 | −0.021 |

At 5e-2 the minimum spread in 1,600 draws is 6,418 persons — **the loose ensemble contains no plan as balanced as the tight ensemble's *worst***. That is a statement about the *support* of one ensemble, not about correlation designs. And note the second column: a Spearman correlation never exceeds |0.14| anywhere, while a tail filter reaches −0.48 at the same epsilon. The blindness is in the *statistic* (a monotone correlation summary over the whole range), not in the *design* (within-ensemble). Experiment 2's own audit already found and published exactly this — "tail-localised tradeoffs on a coarse criterion are invisible at any magnitude" — so Experiment 1 is re-deriving a known limitation of its sibling and mislabelling it as a limitation of an entire class of study.

**Replacement wording, both sentences:**

> Within one ensemble the association between realised population spread and compactness is a tail effect, not a monotone one: Spearman rho never exceeds 0.14 at any tolerance, while restricting a fixed epsilon = 5e-4 ensemble to the 7% of plans whose spread falls inside the tight ensemble's support moves Polsby-Popper by Cliff's delta −0.480 (4 of 4 chains). A rank-correlation summary over a single ensemble therefore misses it, and a tail filter over the same ensemble does not.
>
> The limit on a single-tolerance study is one of support, not of design: an ensemble drawn at 5e-2 contains no plan as population-equal as the worst plan drawn at 2e-4, so it cannot report on that range at all. Any study that fixes one population tolerance measures the tolerance-compactness relationship only over the deviation band that tolerance admits.

**Consequence for the Stephanopoulos critique.** The strong form does not survive and must be removed. The weak form above is defensible and is worth stating, but it is a scope caveat, not a refutation, and it cannot be presented as "no within-ensemble correlation design can see it."

---

## 3. Is the ranked list sound? **No. It ranks pairwise rank-correlation, and the top two entries are one relationship counted twice.**

**(a) The statistic is the correlation matrix's row-minimum.** Compare `worst_delta_anywhere` against "most negative Spearman rho with any other criterion":

| | rank correlation of the two orderings | `displaces` == argmin-rho partner |
|---|---|---|
| IA | **0.928** | 6/6 |
| CO | **0.955** | 6/7 (the miss has rho = −0.001) |

The ranked list is Experiment 2's correlation matrix re-summarised as a row-min and relabelled "binds"/"decorative". It is not an independent measurement of binding.

**(b) It is symmetric, so it double-counts.** In *both* states ranks 1 and 2 are the same single relationship read from both ends: IA competitiveness ↔ fairness_mm (rho −0.768), CO competitiveness ↔ fairness_mm (rho −0.309). Iowa's "two hardest-binding criteria" is one relationship. `INSTRUMENT-AUDIT.md` §3 already ordered E2's ordered-pair matrix collapsed to unordered relationships for exactly this reason; E1 reintroduced it. **No auditor raised this.**

**(c) `min()` makes it a *cost* measure, not a *binding* measure — and that is where "decorative" breaks.** Colorado compactness_pp at q=0.90, from the shipped JSON:

```
compactness_cut  +0.637      county_integrity +0.394
fairness_eg      +0.076      fairness_mm      +0.069
competitiveness  +0.028      population_equality +0.109
worst_delta = -0.036  ->  DECORATIVE
```

Enforcing compactness in Colorado removes 90% of the maps, moves its own median Polsby-Popper 0.1766 → 0.2121, truncates its own range from [0.111, 0.286] to [0.203, 0.286], and drags cut-edges and county integrity by +0.64 and +0.39. The instrument files that as "a commission could adopt it, enforce it to the letter, and change nothing." That is false on the instrument's own numbers. The statistic cannot see a criterion that reorganises the ensemble *constructively*.

**(d) It reports no attainability at all.** The module docstring, line 86: *"This computes displacement directly and reports the attainable range alongside it."* `sweep_one` returns `distinct_values` and `strictest_kept_fraction` and no attainable range; there is no such key in the shipped JSON. Unimplemented promise.

**(e) "Iowa binds harder" is partly an ESS statement.** IA ESS on the columns carrying its ranking is 35.4 (fairness_eg) and 38.3 (compactness_cut) out of 12,000 nominal draws; CO is 77.7 and 64.4 out of 8,000. My own circular-shift null (B=60, shift within each completed chain, same statistic, same criterion):

| | observed | null median | p | P(fires at −0.147 \| null) |
|---|---|---|---|---|
| IA compactness_pp | −0.619 | **−0.122** | 0.016 | **0.27** |
| CO compactness_pp | −0.036 | **−0.067** | 0.836 | 0.02 |
| IA population_equality | −0.266 | −0.067 | 0.016 | 0.02 |
| CO population_equality | −0.054 | −0.070 | 0.770 | 0.00 |

Same statistic, same criterion, roughly **double the noise floor in Iowa**. Some of "Iowa binds harder" is Iowa mixing worse. My null also confirms the surviving auditors and vindicates Colorado's decorative calls: they are not false negatives (p = 0.77, 0.84).

**(f) The list is not stable to the election — nobody tested this.** Re-running the filter half on `ALTERNATE_CONTEST` (G20USS), which E2 runs for every partisan criterion:

```
IA G20PRE: competitiveness  fairness_mm  compactness_pp  fairness_eg  population_equality  compactness_cut
IA G20USS: competitiveness  compactness_pp  compactness_cut  fairness_mm  fairness_eg  population_equality
CO G20PRE: competitiveness  fairness_mm  fairness_eg  county_integrity  population_equality  compactness_pp  compactness_cut
CO G20USS: competitiveness  fairness_mm  fairness_eg  compactness_pp  compactness_cut  population_equality  county_integrity
```

Kendall tau: IA PRE vs IA USS **0.467**; CO PRE vs CO USS 0.524; IA vs CO under PRE 0.733; **IA vs CO under USS 0.467**. Iowa's compactness_cut moves from rank 6 (−0.167, its weakest) to rank 3 (−0.534). Changing the election reorders the deliverable as much as changing the state does, and the headline "Iowa binds harder but orders the same" is a G20PRE-only artifact — under G20USS they do not order the same. Colorado's *labels* are stable (same 3 binds, same 4 decorative), Iowa's ordering is not. E2's own comment says a finding that flips when the office changes is a finding about the office; E1 never ran the check.

**(g) The tightening ladder is degenerate on the coarse criteria.** IA competitiveness (3 distinct values): q=0.25 and q=0.50 both keep 11,995/12,000 (5 excluded); q=0.75 and q=0.90 both keep 46.075%. Two distinct levels, one of which is an 11,995-vs-5 comparison — and `binds_at_realistic: true` for Iowa's rank-1 criterion is that 5-plan cell (`worst_delta_at_realistic = −0.757`). CO competitiveness collapses q=0.50/0.75; CO county_integrity's q=0.75 keeps 39.2%, not 25%. Confirms the auditors' "separate defect found en route."

**(h) The two states' population_equality rows are not comparable and one is outside the law.** IA ensemble spread: 12–314 persons = 0.0015%–0.039% of ideal, entirely inside the legal window. CO ensemble spread: 4,652–14,404 = **0.645%–1.996%** of ideal (ideal 721,714) — the *most* population-equal plan in the whole Colorado ensemble sits at the *Karcher* line and the median is 2.4× over it. Colorado's tightest filter (q=0.90) reaches 9,676 = 1.34%, still unconstitutional. "Population equality is decorative in Colorado" is measured entirely outside the range the criterion legally occupies, in a table beside an Iowa row measured entirely inside it. **Nobody attacked this.**

---

## 4. Is "decorative" a claim about districting or about ReCom?

**About ReCom, about the tolerance the ensemble was drawn at, and about the other six columns in the table — in that order. It is not a claim about districting.** Three independent reasons, each on the instrument's own numbers:

1. **It is relative to the criterion set.** Colorado compactness moves nothing *among these six criteria* while removing 90% of maps and moving cut-edges +0.64. "Decorative" means orthogonal, not inert.
2. **It is relative to what ReCom put in the ensemble.** The docstring already concedes contiguity ("decorative inside this instrument, absolutely binding outside it"). Iowa county integrity is constant because the *units are the counties*. And ReCom's balanced-spanning-tree proposal is compactness-biased by construction, so the ensemble under-populates the non-compact region a commission can actually draw — the reason a compactness filter has little left to remove. The same bias is visible in the initial partitions before the walk starts: `recursive_tree_part` seeds at 2e-4 have PP 0.3550/0.2698/0.2890/0.3537, at 5e-2 0.3595/0.3753/0.4135/0.3741. The epsilon-compactness relation is a property of the *balanced-tree-cut family*, present before a single ReCom step is taken.
3. **It is relative to the epsilon the ensemble was drawn at.** Colorado's "decorative" population-equality verdict covers 0.65%–2.0% deviation only.

**Wording the write-up should use.** Replace every unqualified "decorative" with:

> **Non-displacing on this ensemble.** Over the ReCom ensemble drawn for this state at this population tolerance, tightening this criterion to its best decile does not move any of the six other criteria measured here by more than a small effect (Cliff's delta −0.147). It does change the maps — the Colorado compactness filter removes 90% of them and raises median Polsby-Popper from 0.177 to 0.212 — and it moves cut-edges and county integrity strongly in the *same* direction. "Non-displacing" is a statement about the six columns in this table and about the plans ReCom reaches, not a statement that the criterion does nothing.

And add, once, near the ranked list:

> Contiguity and (in Iowa) county integrity are constant by construction of the sampler and the unit, and are excluded from the ranking rather than ranked last. Two of Iowa Code ch. 42's four ordered criteria therefore cannot appear in Iowa's ranked list at all, and the first — population equality — had to be moved to the resampling half. The Iowa ranking below is dominated by criteria (competitiveness, mean-median, efficiency gap) that Iowa Code ch. 42 **expressly forbids a redistricting body from considering** (`docs/CRITERIA.md` §2.1). It is a measurement of what those criteria would do if Iowa applied them, not a ranking of Iowa's criteria.

---

## 5. FIX / DISCLOSE / NOISE

### FIX before this goes into `docs/progress.md` (blocking)

1. **Strike the methodological claim** and the Stephanopoulos critique built on it. Replace with the two-sentence version in §2. Ship the −0.480 counterexample as the evidence against your own earlier draft — it is the strongest thing in the experiment.
2. **Delete the two tight rungs as measurements** (5e-4, 1e-3; p = 0.54, 0.40 against the 35-split chain permutation), delete the word "monotonically", and suppress the `monotone: true` flag at lines 392–394 or gate it on rungs that clear their own cell's between-chain floor. Report "a threshold between 1e-3 and 5e-3", and print the permutation p beside each rung.
3. **Re-baseline the curve on the committed 8×1500 ensemble** (−0.512/−0.483) or state explicitly that the shipped −0.417 is the *weaker* of the two available estimates. Do not publish the 4×400 replay as if it were the best measurement when a 12,000-draw ensemble at the identical epsilon is committed in the repo.
4. **Add `E2.diagnostics` per epsilon cell.** `prompt.md` line 89 mandates PSRF every round with a 1.00–1.01 target; the chosen baseline cell is at R-hat 1.157 / ESS 19.2 on the exact column carrying the headline, and the shipped JSON contains no `rhat`, no `ess`, no `limitations` key.
5. **Run the filter half on `ALTERNATE_CONTEST` and publish both.** Iowa's ordering does not survive it (tau 0.467) and "orders the same as Colorado" does not survive it. Publish only what holds under both contests, or publish both orderings side by side.
6. **Collapse the double count.** State that ranks 1 and 2 in each state are one relationship. Iowa has 5 relationships behind 6 rows; Colorado 6 behind 7.
7. **Guard the tightening ladder** (`sweep_one:203-205`): refuse a level whose kept or excluded set is below a floor (say 1% of the ensemble), and de-duplicate levels that produce the same cut. Iowa's rank-1 `binds_at_realistic: true` is currently an 11,995-vs-5 comparison, and Iowa competitiveness has 2 distinct levels, not 4.
8. **Report a null beside `worst_delta_anywhere`** (within-chain circular shift, the null E2 already implements) and correct for the 13 tests. On my numbers Colorado is unchanged — all 3 binds clear, all 4 decoratives are correct at p ≥ 0.77 — and Iowa loses compactness_cut (−0.167 against a null median of −0.098).
9. **Implement the attainable range promised at docstring line 86, or delete the sentence.**
10. **Print the raw magnitude beside every Cliff's delta.** −0.417 is median mean-Polsby-Popper 0.326 → 0.365.
11. **Add `tests/test_experiment_1.py` and a `controls()` equivalent.** Experiment 2 has both; Experiment 1 has neither, and the known-history defects are exactly the class a liveness control catches.

### DISCLOSE as limitations

- Every rung of the cost curve that clears the noise floor lies at 1%–10% total deviation. *Karcher* struck 0.6984%. **The tradeoff is real and legally unreachable for a congressional plan.**
- `worst_delta_anywhere` is a *cost* statistic (a `min`); strong positive couplings are invisible to it by construction, and Colorado compactness has one at +0.637.
- ESS 35–38 (IA) vs 64–78 (CO) on the criteria carrying the rankings; the same statistic's null floor is −0.122 in Iowa and −0.067 in Colorado, so cross-state magnitude comparisons are not calibrated.
- Colorado's entire ensemble sits at 0.645%–1.996% population deviation; its population-equality verdict says nothing about the criterion inside its legal range.
- The two halves use different samples of the same state (12,000 draws × 1500 steps vs 1,600 × 400) and the sweep's 2e-4 cell is a bit-identical replay of committed chains 0–3, not an independent resample.
- The ranked list is a summary of the pairwise rank-correlation matrix (rho 0.93/0.96 with the row-min of Spearman), not an independent construct.

### NOISE — do not spend another agent on these

- **"The baseline is survivor-selected."** Four of four chains complete at 2e-4; the 1e-4 cell is excluded with a documented reason and the reasoning is in the source. Alleged and refuted four separate times in this audit. Closed.
- **"The epsilon effect is a burn-in transient."** Falsified: first-400 −0.512 vs last-400 −0.483 over 1500-step chains; no within-chain drift. Closed.
- **"Colorado's decorative calls are false negatives."** p = 0.836 and 0.770 against my own null. They are correct. Closed.
- **The `abs()` in the `monotone` flag** (a sign-alternating curve would be flagged monotone). Real, bites nothing shipped, fix it in passing.
- **Chain-bootstrap-with-4-units complaints applied to the loose end.** 16/16 cross-chain pairs negative, permutation p at floor, effect strengthens on 8 chains. The loose end is the most robust number in the experiment.

---

## 6. What did nobody attack?

All five surviving allegations, and eleven of the fifteen refuted ones, attack the *null distribution* of one statistic. Nobody asked what the statistic measures or whether the deliverable is stable. Six things:

1. **The ranked list is Experiment 2's correlation matrix.** Rank correlation 0.928 (IA) / 0.955 (CO) with each criterion's most-negative Spearman against any other; `displaces` equals the argmin-rho partner in 12 of 13 rows. The word "binds" adds nothing to a number E2 already published — which also means E1's framing ("E2 measured within a fixed epsilon and found almost nothing") is describing its own filter half.
2. **It is symmetric, so ranks 1 and 2 are one relationship in both states.** `INSTRUMENT-AUDIT.md` §3 already required this collapse for E2; E1 reintroduced the defect.
3. **`min()` cannot see constructive coupling.** Colorado compactness is "decorative" at −0.036 while moving cut-edges +0.637 and county integrity +0.394. The single most consequential criterion in the Colorado table is filed under "changes nothing."
4. **One contest.** Kendall tau between Iowa's G20PRE and G20USS orderings is **0.467** — the election reorders the deliverable as much as the state does, and "Iowa orders the same as Colorado" fails under G20USS. E2 runs both contests for exactly this reason; E1 runs one.
5. **Cross-state incomparability, twice.** Noise floor (−0.122 IA vs −0.067 CO on the identical criterion) and epsilon (0.04% IA vs 2.0% CO deviation, one inside the legal window and one entirely outside).
6. **Iowa's ranked list ranks criteria Iowa forbids.** `CRITERIA.md` §2.1: Iowa Code ch. 42 expressly forbids considering political affiliation and prior election results. Ranks 1, 2 and 4 are competitiveness, mean-median and efficiency gap. Meanwhile contiguity and county integrity are structurally unrankable and population equality had to be moved to the other half — so the Iowa deliverable ranks almost none of Iowa's actual statutory criteria, in the state chosen *because* its statute removes the value choices.

Minor and unattacked: the docstring's unimplemented "attainable range" (line 86); no `limitations`, `rhat`, `ess` or interval key anywhere in the shipped JSON; no `tests/test_experiment_1.py` and no `controls()` where Experiment 2 has both; no `docs/DECISIONS.md` entry and no write-up for Experiment 1 at all.

**Bottom line.** The epsilon half's headline is real, is stronger than published, and is legally inert — say all three. The methodological sentence is false and must be struck; the −0.480 within-ensemble counterexample should replace it. The ranked list — the thing `prompt.md` actually asked for — is a correlation matrix with a double-counted top, a cost statistic mistaken for a binding statistic, no attainability, no null, and an ordering that does not survive changing the election. Colorado's verdicts survive everything I threw at them. Iowa's ordering does not.
