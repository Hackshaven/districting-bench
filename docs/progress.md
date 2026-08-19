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
