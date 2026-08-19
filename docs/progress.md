# Progress — Phase 1 detection loop

The committed record of each bench round. Raw artifacts (`bench-results.json` and
the PNGs) are gitignored by the scaffold as run artifacts and live in
`docs/progress/round-NN/`; this file carries the numbers so a reader without the
working tree can see them.

Reproduce: `PYTHONPATH=src python -m detect.bench --master-seed 20260818 --round N`

---

## Round 1 (round-01, `--quick`) and Round 2 (round-02, full)

Round 1 was a smoke run; round 2 is the first real ensemble. Both are reported
because the difference between them **is** the finding.

| Gate | Target | Round 1 (quick) | Round 2 (full) | |
| --- | --- | --- | --- | --- |
| TPR at a 2-seat shift | ≥ 0.95 | 1.0000 | **0.5000** | FAIL |
| FPR on nulls | ≤ 0.05 | 1.0000 | **0.0667** | FAIL |
| Split R-hat | 1.00–1.01 | 1.8967 | **1.4738** | FAIL |
| Legal compliance | 1.0 | 1.0000 | 1.0000 | pass, but see §3 |

**Minimum detectable seat shift: `null`.** `CRITERIA.md` §8 calls this "the honest
headline number for the whole system". There is no magnitude at which the detector
reaches the target true-positive rate. At a 1-seat shift it flags 0 of 16; at
2 seats, 8 of 16.

Round 2 ensemble: 806 draws completed of 1040 requested across 8 chains, **2 chain
failures (25%)** at ε=2×10⁻⁴, 177 distinct plans. The failure rate is consistent
with `FEASIBILITY.md` §5.1 and is reported, not retried.

---

## 1. The detector does not work, and the round-1 PASSes were artifacts

Round 1's two passing gates did not survive a real ensemble.

**TPR 1.0 → 0.5** because at 28 draws the rule was flagging everything. An
always-flag detector scores identically on both round-1 PASSes and *beats* the
shipped rule on the headline number. A gate a constant ties is not a measurement.

**FPR 1.0 → 0.067** because the round-1 reference could not express its own
threshold. With *n* draws the largest interior percentile obtainable is
(*n*−0.5)/*n*; at *n*=28 that is 0.9821 < 0.99, so **no plan strictly inside the
ensemble range could ever fire**, and the "top 1%" rule silently degenerated into
"outside the observed support". All six round-1 false positives sat just outside a
support pinched shut by 14 distinct plans — two of them by **0.0005 of an
efficiency-gap point**. Interior firing at 0.99 first becomes possible at *n*=50;
`rule.min_n=20` admits exactly the regime where the threshold is unreachable, and
it counts draws rather than distinct plans or ESS, so duplicated draws defeat it.

An FPR-versus-ensemble-size sweep (detector and nulls held fixed) puts the
crossover between 28 and 60 draws: FPR falls from 1.00 to ≈0.06 and never returns.
Split R-hat never reaches 1.01 even at 24,247 draws, so **FPR and convergence are
not coupled the way round 1 suggested**.

### The decisive number

Ranking scenarios by the two-sided outlierness the rule actually reads:

> **AUC = 0.25** for separating planted gerrymanders from neutral maps.

Worse than a coin flip, and worse than always-flag or never-flag (0.5 by
construction). **The rule ranks neutral maps as more gerrymandered than the
deliberately planted ones.** Two 1-seat plants land *inside* the reference's own
cluster at percentile exactly 0.5000 — reading as perfectly typical — while
uniformly drawn neutral maps 0.0005 outside it are flagged.

---

## 2. The ground truth is separable on generator fingerprint, not on gerrymandering

This is the more serious problem, because it would survive fixing the detector.

Every planted plan has roughly **twice the cut edges and a third the
Polsby-Popper** of every neutral map — reference and null alike — with no overlap.
Planted: cut edges 93–99, Polsby-Popper 0.12–0.14. Neutral: cut edges 46–55,
Polsby-Popper 0.27–0.31. The enacted map sits at 51.

A one-line rule, `cut_edges > 60`, scores **TPR 1.0 and FPR 0.0** on this scenario
set while knowing nothing whatever about partisanship. Any gate passed on this
ground truth can be passed by detecting the search that built the plan rather than
the gerrymander it encodes. The seat-maximizing search wanders into ragged corners
of the space that ReCom's spanning-tree proposal never visits, and that shape is
what the "detector" is picking up.

**A gerrymander that a compactness screen catches is not the adversary this system
exists to detect.** The adversarial generator must be constrained to stay inside
the neutral ensemble's compactness distribution, or the ground truth is a
tautology.

---

## 3. Other findings from the audit

**The R-direction baseline is manufactured.** Iowa 2020 is R+8.4 two-party and the
enacted map is already 4R–0D, so a Republican gerrymander has no headroom. The
bench measured R-direction shifts from `ensemble_max_d` — the single most
Democratic-favouring draw of the unconverged 14-plan reference — rather than from
the enacted map, which manufactures headroom the adversarial module itself says
does not exist. It is disclosed in `scenario.baseline`, but it is a different
quantity from the D-direction shift and both are pooled into one gate.

**`legal_compliance = 1.0` is measured at a looser tolerance than the declared
operating point.** Round 1 ran at ε=1×10⁻³ against a declared operating ε=2×10⁻⁴;
7 of its 10 ground-truth plans are illegal at the operating value. `check_legality`
also does not test compactness, so plans with a third the Polsby-Popper of every
neutral draw are certified compliant with Iowa Code ch. 42, whose fourth criterion
is compactness.

**The artifact published a verdict on Iowa's enacted map.**
`plan_under_review.flagged = true` — a boolean judgement on the real in-force
CD118 plan, which `README.md` and `CRITERIA.md` §11 both forbid: *"any output of
this system that reads as a verdict rather than a distribution is a bug."* Worse,
its efficiency gap is bit-identical to the manufactured R-gerrymander's, because
efficiency gap barely depends on the lines under a 4–0 sweep. The artifact cannot
distinguish the enacted map from a deliberately built gerrymander and does not say
so.

**Scenarios are not verifiable.** No scenario carries its plan or a plan digest, so
no ground-truth claim in the artifact — legality, realized seat shift, seat counts
— can be checked from the artifact that `ARCHITECTURE.md` §5 designates as the
thing critics read.

**Declination never applies here.** `DECLINATION_MIN_DISTRICTS = 8` and Iowa has
k=4, so declination is untrusted on every Iowa plan and, with
`untrusted='exclude'`, excluded 100% of the time. The "any of 4 metrics" rule is
in practice any-of-1 or any-of-3; only `efficiency_gap` ever fired in either round.

**The FPR gate may not be well posed.** `nulls.py` ranks candidates by
(|seats − median|, |efficiency gap|), and |efficiency gap| is a monotone transform
of the detector's own test statistic. As the candidate pool grows, selected nulls
move further into the tail and *any* correct percentile-tail detector flags them:
measured, the selected stratum's FPR rises to 1.00 as the pool grows while the
random stratum's falls to 0.125, with the reference held fixed. The
`null_geography` stratum measures the selection rule, not the detector.

---

## 4. Where this leaves the loop

Round 2 is a real measurement of a detector that does not work. That is the loop
functioning as designed — ground truth was manufacturable, so the failure is
visible and quantified rather than hidden behind a plausible number.

Ranked by what has to change first:

1. **Constrain the adversarial search to the neutral compactness distribution.**
   Until a planted gerrymander is indistinguishable from a neutral map on
   non-partisan metrics, every detection result is confounded (§2).
2. **Fix the percentile floor.** Require the reference to be large enough to
   express the rule's threshold — gate on distinct plans and ESS, not raw draws.
3. **Rebuild the null strata.** Selected nulls must not be ranked by the
   detector's own statistic (§3).
4. **Give the R direction an honest baseline**, or state that the 2-seat gate is
   unreachable in that direction on Iowa and report the achievable range instead.
5. **Remove the verdict on the enacted plan**; report its location in the
   distribution, per metric, with the trusted-metric set named.
6. **Raise the ensemble.** Split R-hat 1.47 at 806 draws is far from 1.01, and the
   sweep shows convergence is the slower of the two problems.

Nothing in this round was tuned to make a gate pass. Every gate result above is
the run as it came out.

---

## Round 3 — the redesign fails its own acceptance test, and produces the round's real result

Round 3 reworked the adversary, the detector's percentile floor and the null
strata. It was given one falsifiable acceptance test, measured by an agent that
saw none of the implementation work:

> **AUC separating planted from neutral using ONLY non-partisan metrics.**
> 0.5 = indistinguishable (the goal). 1.0 = the ground truth leaks its provenance.

| | AUC | verdict |
| --- | --- | --- |
| Round 2 (unconstrained search) | 1.000 | trivially separable |
| **Round 3 (shipped path)** | **0.890** | **PARTIALLY_SEPARABLE — `still_confounded = true`** |

**D-010 is not met.** Separability fell from 1.00 to 0.89; it did not reach 0.5.
Planted cut edges 46–54 (n=19) against a neutral reference of 40–67 (n=8,793):
every plant now lies inside the neutral *range*, but only 5.3% sit inside the
neutral interquartile range, and the histogram overlap coefficient is 0.239. A
non-partisan screen still beats the shipped detector by a wide margin.

The instrument that *does* reach the target exists and is not wired in.
`envelope_around_plan` scores 0.52–0.56, is exported in `__all__`, and is called
from nothing in `src/` — only from tests. The path the bench actually runs is the
coverage-0.90 quantile band, and the plants pile against its ceiling exactly as the
module's own docstring predicts.

### The frontier — the actual finding

Asked what happens as the compactness constraint tightens, rather than allowed to
loosen it until the gate passed:

D-direction, 2-seat shift from the enacted plan, 40,000 iterations × 4 restarts:

| Constraint | Yield | Non-partisan AUC |
| --- | --- | --- |
| none (round-2 search) | 8/8 | 1.000 |
| band 1.00 | 32/32 | 0.994 |
| band 0.95 | 32/32 | 0.935 |
| **band 0.90 (shipped)** | **32/32** | **0.912** |
| band 0.75 | 30/32 | 0.759 |
| band 0.50 | 20/32 | 0.695 |
| band 0.25 | 4/32 | 0.654 |
| band 0.10 | **0/24** | unscoreable |

**Yield collapses to zero before separability reaches 0.5.** On Iowa, at a 2-seat
shift, a gerrymander that is shape-typical of the neutral ensemble appears not to
exist — the search cannot find one at any constraint tight enough to make it
indistinguishable.

If that survives scrutiny it is the most interesting result the project has
produced, and it points the opposite way from the usual worry: in Iowa's
4-whole-county congressional problem, **compactness is doing real work as a
constraint**, and there is very little room for a gerrymander to hide inside the
traditional criteria. It also means the detection gate as posed may be unreachable
here for a reason that is about Iowa, not about the detector.

Strong caveat: Iowa is 99 whole counties and 4 districts — an unusually constrained
problem, chosen precisely because it is small. Nothing here generalises to a
precinct-level state without being re-measured, and the frontier above is one
direction, one magnitude, one search algorithm.

### Two more gates that passed for the wrong reason

Round 2's lesson was that a passing gate can mean nothing. Two new instances:

- **`Rule.resolvable` ORs the two tails.** A two-sided rule is declared resolvable
  when only *one* tail is expressible, and then answers `flagged=False` on the tail
  the reference provably cannot express. That deflates FPR and lets the FPR gate
  pass. Round 2's percentile-floor finding survives in one direction.
- **The FPR gate passes at 0.0000 on a deliberately narrowed null sample**, and the
  run's only false positive sits in the stratum that was excluded.

Also: the compactness component added to `legal_compliance` cannot fail for any
scenario the bench can produce — it makes the gate look stricter while adding no
capacity to fail. And the detection-curve plot now crashes, with the failure
written to stderr only; `bench-results.json`, which `ARCHITECTURE.md` §5 designates
as the file critics read, records nothing about the missing plot.

### Round 4 must start here

1. **Wire in the envelope that works, or establish that it cannot work.** The
   frontier suggests the honest answer may be that a 2-seat shape-typical
   gerrymander does not exist on Iowa. If so, say that and re-pose the gate; do not
   ship an adversary at AUC 0.89 and call the ground truth clean.
2. **Fix `Rule.resolvable` to require both tails**, and re-run — the FPR gate's
   current pass is not evidence.
3. **Report strata separately and never pool them**, and stop excluding the
   stratum that contains the failures.
4. **A plot that fails must fail the run**, or at minimum be recorded in the
   artifact.

---

## The neutral seat distribution — and a retraction

Measured on 1,820 completed draws (8 chains × 260 at ε=2×10⁻⁴, 1 chain failure,
323 distinct plans). Every plan here is drawn by ReCom with no access to election
data, so all of them are shape-typical by construction.

| D seats | plans | share of the neutral ensemble |
| --- | --- | --- |
| 0 | 18 | **1.0%** |
| 1 | 1020 | 56.0% |
| 2 | 782 | **43.0%** |

**The neutral process spans 0–2 Democratic seats out of 4, and a 2-seat outcome is
43% of it.**

### Retraction: round 3's frontier claim was wrong

Round 3 recorded that on Iowa, at a 2-seat shift, "a gerrymander that is
shape-typical of the neutral ensemble appears not to exist", inferred from planted
yield collapsing to 0/24 as the compactness constraint tightened.

**That inference does not hold, and the claim is withdrawn.** Shape-typical plans
at a 2-seat shift are not rare — they are 43% of what the neutral sampler produces
without trying. The collapsing yield measured the *adversarial search failing under
a constraint*, not an empty feasible set. `docs/DECISIONS.md` D-012 is corrected
accordingly.

The lesson is the one round 2 already taught in a different costume: a number that
goes to zero is not evidence of impossibility until you have shown the search would
have found the thing if it were there. The neutral sampler was producing counter-
examples the whole time, in the same artifact, and nothing looked.

### The gate is malformed for Iowa

`CRITERIA.md` §8 asks for TPR ≥ 0.95 at a 2-seat shift. On a 4-district state whose
neutral distribution already spans 2 seats, that asks the detector to separate an
outcome from its own null. No detector can do it, and no amount of ensemble or
tuning changes that: a plan producing 2 D seats is, by measurement, what neutral
process routinely produces.

This is `CRITERIA.md` §5.4 (Chen & Rodden) arriving as a hard limit rather than a
caveat. With four districts and the Democratic vote concentrated in Polk, Linn,
Johnson and Scott, where the lines fall moves two seats with no intent involved.

**Detectability is bounded below by the width of the null distribution, and that
width is a property of the state, not of the method.** A detection gate stated in
absolute seats is not portable between states and is unreachable in Iowa.

### The enacted plan sits at the 1st percentile — stated carefully

Iowa's enacted plan returns 0 D seats. That outcome occurs in **1.0%** of the
neutral ensemble; 99% of neutrally drawn maps give Democrats at least one seat.

**This is not a finding yet, and must not be reported as one.** The reference
ensemble is not held to the standard the enacted plan meets: the enacted plan has a
94-person population spread, while the ensemble runs at ε=2×10⁻⁴ and spans far
wider deviations (`FEASIBILITY.md` §5.3 — the same contamination that round 2 was
built on). A comparison against a reference that would fail the plan's own legal
standard is not like-for-like, and the direction of that bias is unmeasured.

What can be said: the outcome is unusual against *this* reference, in the
R-favouring direction, and it is worth a matched-tolerance comparison before
anyone repeats the number. Iowa Code ch. 42 forbids considering political data, so
if the effect survives matching, the interesting question is whether optimizing
population equality to 94 persons has a partisan direction in this geography —
which is a measurable question and a genuinely novel one.

---

## Colorado — the second state, and what it does and does not fix

Colorado's layer is built: 3,108 VTDs, 5,773,714 persons, 8,754 rook edges in one
component, 8 districts, VEST 2020 joined with 100.0000% of votes conserved (D-016).

Neutral seat distribution, 720 draws at ε=0.01, **0 chain failures, 704 distinct
plans**:

| D seats | plans | share |
| --- | --- | --- |
| 4 | 83 | 11.5% |
| 5 | 480 | 66.7% |
| 6 | 157 | 21.8% |

### The comparison

| | Iowa | Colorado |
| --- | --- | --- |
| Districts | 4 | 8 |
| Neutral range | 0–2 D | 4–6 D |
| **Null spread** | **2 seats** | **2 seats** |
| As a share of the delegation | 50% | 25% |
| Smallest shift outside the null | 3 of 4 (75%) | 3 of 8 (37.5%) |
| Enacted plan sits at | 0 D — the 1.0% tail | 5 D — the 66.7% mode |
| Ensemble health | 806/1040 draws, 2 failures, **177 distinct** | 720/720, **0 failures, 704 distinct** |

**The absolute null spread is identical: 2 seats in both states.** Eight districts
did not narrow the null — it spread the same 2-seat uncertainty over twice the
delegation. So the `CRITERIA.md` §8 gate at a 2-seat shift **is unreachable on
Colorado too**, for exactly the reason it is unreachable on Iowa: a 2-seat outcome
is inside what neutral process produces.

This is the strongest evidence yet for D-013. The fix is not a bigger state; it is
measuring detection magnitude in units of the null spread. Two states, two very
different geographies and district counts, and the same 2-seat null.

What Colorado *does* buy is headroom above that floor. A 3-seat shift sits outside
its null while remaining 37.5% of the delegation — a magnitude a real gerrymander
could plausibly have. On Iowa the equivalent is 3 of 4 seats, which is close to
saying "the whole delegation" and is not a meaningful detection target.

**Colorado's ensemble is also far healthier**, and this matters more than it looks:
704 distinct plans from 720 draws (97.8%) against Iowa's 177 from 806 (22%), with no
chain failures at all. Iowa's percentile floor problem — the reference being too
coarse to express its own threshold (§1) — largely dissolves on a graph this size.

### Two caveats that keep this from being a clean comparison

1. **The tolerances differ.** Colorado runs at ε=0.01 because whole-VTD units cannot
   reach Karcher-tight (D-015); Iowa runs at ε=2×10⁻⁴. A looser tolerance admits
   more diverse plans, so Colorado's spread may be inflated relative to Iowa's — or,
   put the other way, Iowa's tight ε may be *narrowing* its null. The comparison
   likely understates Iowa's true spread, which would strengthen the conclusion
   rather than weaken it, but it has not been measured.
2. **Colorado's enacted plan is a VTD approximation** (D-015), so "5 D seats, the
   mode" is a statement about the approximation, not the in-force map.

Neither caveat is resolved here, and both are stated rather than absorbed.
