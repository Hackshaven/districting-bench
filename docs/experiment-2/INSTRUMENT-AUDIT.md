# Experiment 2 — adversarial audit of the instrument

Run before the results were written up, against `tools/experiment_2_tradeoffs.py`
and `tests/test_experiment_2.py` at commit `5162758`, with the measured draws for
both states on disk.

Five auditors attacked the instrument along independent lenses; every alleged
defect was handed to a separate refuter instructed to default to *refuted*.
**20 defects alleged, 9 survived refutation.** 26 agents, 630 tool calls.

The audit's own summary follows verbatim. It is kept because it is the reason the
first Colorado result was not published, and because `docs/DECISIONS.md` D-019
requires that a refuted claim be recorded as a failure rather than dropped.

---

I have my own reproductions. Writing the conclusion.

## 1. The fix is REAL, but it certifies the wrong regime — and the original defect recurred inside the gap

The controls are not cosmetic. `controls()` genuinely runs all three tests on three structures, `CONTROL_EXPECTATIONS` genuinely aborts the run, and `tests/test_experiment_2.py:62,71` genuinely catch a monkeypatched constant. That machinery works.

But the question is whether each test can produce both verdicts **on data resembling the real ensembles**, and the answer is 2½ out of 3. I measured the attainable range of each test's statistic against the real marginals (`scratchpad/attain.py`), and dialed real dependence into the real draws while preserving each chain's marginals and the between-chain heterogeneity (`scratchpad/blind.py`, `tail.py`, `tail2.py`, `power.py`).

- **`test_correlation` — real.** Produces both verdicts. Realised firing threshold on the shipped data lies between |rho| = 0.24 (did not fire) and 0.31 (fired); on synthetic-but-real-shaped data, |rho| ≈ 0.18.
- **`test_achievability` — technically live, practically inert.** It is not a constant, but across all 36 unordered pairs in both states it fired **once** (IA `fairness_mm × competitiveness`, rho = −0.768) and **never without the correlation test also firing**. Its practical floor is |rho| ≈ 0.5. As a corroborating vote it carries almost no information the correlation test does not already carry.
- **`test_conditional` — a proven constant on one real column.** For B = `competitiveness@G20PRE` in Iowa, the adversarially worst possible decile gives effect exactly **+0.000**, against a firing threshold of −0.20. No arrangement of any A can make it fire. The census of all criterion × contest × state combinations shows exactly one such dead cell (IA/G20PRE competitiveness); every other criterion attains −1.07 to −10.95. It affects 5 of 30 Iowa ordered pairs, all reported with `n_deciding: 3, degenerate_tests: []` — an affirmative false claim that three tests decided.

`_synthetic` (:643) emits only continuous Gaussian AR(1), so the controls never exercise a 3-valued criterion, and `_varies` (:445) passes anything with more than one distinct value. **The class of defect the controls were written to prevent recurred in the one regime the controls do not generate.** D-023 made it worse, not better: the MAD→plain-SD fallback converted an honest `degenerate` abstention on this column into a counted `none` vote.

Verdict: real fix, incomplete coverage. The instrument is not one test wearing three hats — but on the shipped data it is closer to *one and a half* tests than three. Seven of Iowa's ten `weak` verdicts and one of Colorado's three rest on the conditional test **alone**, which is the test carrying every defect below.

## 2. Yes, it can report "no tradeoff" over a real tradeoff. The floor is |Spearman rho| ≈ 0.13.

Measured by injecting anti-monotone dependence into the real Iowa draws with per-chain marginals held exact:

| dependence | first test to fire | pair verdict |
|---|---|---|
| \|rho\| ≤ 0.07 | none | **none** |
| \|rho\| ≈ 0.10–0.13 | conditional only | weak |
| \|rho\| ≈ 0.18–0.29 | + correlation | weak |
| \|rho\| ≥ 0.49 | + achievability | strong |

So: **a null from this instrument means "no monotone tradeoff stronger than about Spearman 0.13," and nothing weaker.** That is a publishable number, and it is honest against Stephanopoulos — 0.13 is well inside "weak to nonexistent."

It is not the whole story. Two harder blind spots:

- **Coarse B raises the floor to ≈ 0.16** and removes the only test with power below 0.3. With B = competitiveness under G20PRE, the conditional test is dead at every rho; correlation alone rescues the pair.
- **Tail-localised tradeoffs on a coarse criterion are invisible at any magnitude.** This is the failure that matters, because it is the case a commission actually occupies. On the real Iowa draws, forcing the best 5% of compactness draws onto the worst competitiveness values — which **halves the chance of getting three competitive districts, 46.1% → 25.3%** — yields `{correlation: none, conditional: none, achievability: none}`, pair verdict `none`, `n_deciding: 3`, `degenerate_tests: []`. Push it to 10% and P(3 competitive districts | best compactness decile) goes to **0/1200**, and the conditional test still reports `effect = 0.000`.

I tried and failed to break it on continuous criteria. With a continuous B the conditional test caught a 5%-localised tradeoff cleanly (effect −1.07, p = 0.003) while correlation and achievability both said none. So the tail-sensitivity the docstring claims is real — it just evaporates when B is a small count.

## 3. Fix / disclose / noise

**FIX BEFORE COLORADO IS WRITTEN UP (three code changes, all small):**

1. **The tie-break at `_conditional_effect:491`.** This is the one that touches Colorado directly, and it is the reason Colorado cannot be written up as it stands. I re-ran every Colorado pair with the eight exchangeable chains relabelled (8 random orders, `scratchpad/order2.py`):

   | pair | shipped | conditional effect across relabellings | flips |
   |---|---|---|---|
   | `competitiveness -> compactness_cut` | **none** (−0.024) | −0.016 … −0.455 | 3/8 tradeoff |
   | `competitiveness -> compactness_pp` | **none** (−0.172) | −0.133 … −0.360 | 1/8 tradeoff |
   | `county_integrity -> competitiveness` | **none** (0.000) | 0.000, −0.674 | 1/8 tradeoff |

   Colorado's entire result is 39 `none` / 3 `weak`. The null **is** the product, and three of those nulls are decided by the order chains happen to sit in the file. `test_achievability:553` already uses `>=` (includes ties); make the decile do the same, or average the effect over random tie-breaks. Note the permutation null cannot rescue this: `_circular_shift` preserves each chain's multiset, so the null decile has the identical chain composition as the observed one on every replicate.

2. **An attainability guard in `test_conditional`.** Before deciding, take the `cut` smallest values of B; if that decile's median shift cannot reach `EFFECT_TRADEOFF`, return `degenerate` with a reason. Five lines. It is the per-pair analogue of what `controls()` already does globally, and without it `n_deciding: 3` is false on five shipped pairs. (A mean or rank shift instead of a median would also restore power — three of the five flip to firing at p = 0.001 under a mean — but the abstention is the minimum honest fix.)

3. **A coarsely-discrete arm in `_synthetic`.** Add a fourth control whose B is quantised onto competitiveness' real 3-level frequencies. I verified it fails today (`conditional: none` on a perfect tradeoff), which is exactly what you want a control to do. Without it this hole reopens silently the next time the criteria set changes.

**Also fix before write-up (presentation, not code correctness):** stop presenting 30 and 42 *ordered* pairs as independent evidence. `test_correlation` and `test_achievability` are provably symmetric in (A,B) — I verified **0 direction-dependent instances** across every pair in both states. Iowa has 15 relationships, not 30, and **8 of the 15 report different verdicts in the two directions**, every one of those asymmetries manufactured solely by the conditional test. The verdict matrix figure currently reads as 30 findings when it is 15 findings and 8 self-contradictions.

**DISCLOSE AS LIMITATIONS:**

- The detection floor above (|rho| ≈ 0.13 continuous / 0.16 coarse), stated as the meaning of every `none`.
- That `achievability` fired once in 36 unordered pairs and never independently — "three independent tests" is empirically two, plus a third that only speaks above |rho| ≈ 0.5.
- Convergence: IA `fairness_eg` R-hat 1.155 / ESS 35.4 and `compactness_cut` R-hat 1.146 / ESS 38.3 (CO: 1.12 / 64). Every verdict touching those criteria rests on ~36 effective draws.
- No multiplicity correction across 144 conditional permutation tests (72 ordered pairs × 2 contests) at alpha = 0.05.
- The conditional `effect` column is not a comparable magnitude. IA `fairness_eg` is bimodal with its ensemble median on the mode boundary, so as I dialed dependence up the effect stepped from −0.00 to −4.95 between two adjacent settings. Report it as fired/not-fired, not as an effect size.

**NOISE — do not spend time on:**

- "Block bootstrap has only 8 units." It is the documented rule, its cost is visible in the published CI, and it does not change any verdict.
- `_robust_sd`'s outlier fragility. Requires a marginal shape no criterion here has.
- "controls only certify rho ≈ −0.96." True and harmless — a liveness check is not a calibration curve. The calibration gap is disclosed separately above.
- The strict-nesting claim. Correctly refuted.

## 4. What the auditors missed that a hostile reader hits first

All nine surviving defects are variations on **one function**, `_conditional_effect`. Five auditors converged on the same 7 lines. That concentration is itself the tell: nobody attacked the framing.

1. **Direction-symmetry / double counting.** Not raised as a finding by any auditor. Two of three tests are mathematically symmetric in (A,B); 8 of Iowa's 15 relationships report different verdicts depending on which way you read them, and every one of those disagreements comes from the single most defective test. A referee sees this in the first figure.
2. **Multiplicity.** 144 permutation tests at alpha = 0.05, no correction, and 7 of Iowa's 10 `weak` verdicts rest on that test alone. The expected number of false firings under a global null is the same order as the reported signal. Nobody computed it.
3. **The ensemble, not the tests.** The R-hat/ESS allegation was refuted on the narrow ground that "the driver computes diagnostics and ignores them" is only a code fact. The substantive point was never re-examined: with ESS ≈ 36, the block bootstrap over 8 chains and the within-chain circular-shift null are both resampling a chain set that has not mixed. A hostile reader attacks the sample before the statistics.
4. **Non-monotone dependence.** All three tests are monotone-association or upper-tail statistics. A pair where *both* extremes of A hurt B is invisible to all three by construction. **I did not demonstrate this** — I ran out of budget before building the case — but nothing in the instrument or the controls covers it, and it is a natural shape for compactness against fairness.
5. **The frontier claim.** `pareto_size` is reported for every pair and the commit message says the frontier line is "explicitly not trusted." No auditor tested whether `frontier_fraction` behaves as claimed, and it is printed in the artifact next to verdicts that were audited.

**Bottom line.** The instrument can distinguish a real tradeoff from a null down to about Spearman 0.13, which is good enough to be evidence against or for Stephanopoulos. It is not currently good enough to *publish* Colorado, because Colorado's product is a near-null and three of its nulls flip on an information-free relabelling of chains. Fix the tie-break, add the attainability guard and the discrete control arm, collapse the ordered-pair matrix to unordered relationships, and state the 0.13 floor — then the null is worth something.
