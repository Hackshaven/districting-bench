# Decision log

Every non-obvious choice, the alternatives considered, and why. Entries are
appended as decisions are made, not reconstructed afterwards.

Entries marked **VALUE** are normative choices `docs/CRITERIA.md` did not settle
for us. Those are candidates for promotion into CRITERIA.md as new `VALUE`-class
rows, per `prompt.md`.

---

## D-001 — Feasibility probes live in `feasibility/`, not `src/`

**Date:** 2026-08-18 · **Phase:** feasibility

`src/` still contains no Python. The probes needed to answer "is this buildable
at all" are throwaway, and putting them under `src/generate/` or `src/evaluate/`
would commit us to an internal architecture for those packages before we have
grounds to choose one.

*Alternatives:* write probes directly in `src/` and refactor later — rejected,
because the firewall's package boundaries are permanent and code placed inside
them acquires an implied design; a scratch directory outside the repo — rejected,
because the reviewer cannot reproduce the numbers.

*Consequence:* `feasibility/` is not scanned by the firewall (which reads `src/`
only). Nothing in it may be imported by Phase 1 code. It should be deleted or
rewritten when Phase 1 begins.

---

## D-002 — PL 94-171 bulk files, not the Census API

**Date:** 2026-08-18 · **Phase:** feasibility

`api.census.gov/data/2020/dec/pl` now 302-redirects to a "Missing Key" page; the
API requires a registered key, which we cannot obtain non-interactively.

*Chosen:* the published PL 94-171 legacy-format summary file for Iowa
(`ia2020.pl.zip`, 21 MB). This is the primary source the API serves, so it is
strictly more authoritative, at the cost of parsing a pipe-delimited fixed-schema
file by field position.

*Verification:* parsed total = 3,190,369 across 99 counties, matching Iowa's
published 2020 census **resident** population exactly. (Corrected: this entry
originally said "apportionment", contradicting FEASIBILITY.md §2. The apportionment
population is 3,192,406; the 2,037 difference is overseas federal personnel.
Verified against `apportionment-2020-tableA.xlsx`.)

---

## D-003 — TIGER/Line geometry, not cartographic boundary files

**Date:** 2026-08-18 · **Phase:** feasibility

Cartographic boundary files (`cb_*_500k`) are ~8x smaller and would have saved a
75 MB download.

*Rejected* because they are generalized. Generalization moves vertices, which
changes both the adjacency graph (short shared borders can vanish — Iowa has a
1.9 km Marion–Polk border that is a plausible casualty) and every perimeter-based
compactness measure. Using generalized geometry for compactness would make
Polsby-Popper a measure of the simplification algorithm.

---

## D-004 — Rook adjacency, not queen

**Date:** 2026-08-18 · **Phase:** feasibility · **VALUE**

Iowa's counties are close to a survey grid, so corner contacts are abundant: the
queen graph has 294 edges to rook's 222. **24% of queen edges are single-point
contacts** (72 of 294; equivalently 32% of the 222 rook edges — this entry
originally gave 32% against the wrong denominator, contradicting FEASIBILITY.md §3).
Treating a corner as a connection is a substantive choice, not a
technicality — it lets a district pass through a point of zero width.

*Chosen:* rook. Two counties are adjacent only if they share a boundary of
positive length.

*Evidence this is safe:* all four enacted districts are connected under rook. The
real map does not rely on corner adjacency, so excluding it does not exclude the
plan under review.

*Note:* the Census County Adjacency File includes corner-only contacts — its 294
Iowa–Iowa pairs match our queen graph exactly, in both directions, so anyone using
that file as an adjacency source is silently getting corner adjacency. It does not
follow that the file *is* the queen graph; nationally the two disagree on a few
dozen pairs. Corrected from "is queen-based" — see FEASIBILITY.md §3.

---

## D-005 — Projection: checked, and it does not matter for Iowa

**Date:** 2026-08-18 · **Phase:** feasibility

No projection preserves both area and perimeter, so Polsby-Popper (4πA/P²) is
projection-dependent in principle, and the choice is usually left implicit.

Measured on Iowa's 99 counties, total area against NAD83 Conus Albers (equal-area,
EPSG:5070): Iowa North (26975) +0.020%, Iowa South (26976) +0.033%, UTM 15N
(26915) −0.033%. Worst per-county error under Iowa North is +0.113% (Lee); the
spread across the state is 0.123 percentage points.

*Conclusion:* below any threshold that could reorder plans on compactness. The
feasibility numbers use EPSG:26975. **Phase 1 should standardise on EPSG:5070**
for area-based measures anyway, because the argument does not survive contact
with a large or coastal state, and the cost of being principled here is zero.

---

## D-006 — Firewall gaps found and reported, not patched

**Date:** 2026-08-18 · **Phase:** feasibility

Probing the firewall past the required canary found four ways partisan or racial
data could reach `src/generate/` without tripping it (see
`docs/FEASIBILITY.md` §1). `prompt.md` is explicit: do not modify, relax, or work
around `tools/firewall.yaml`, and if the config seems wrong, stop and say so.

*Chosen:* report, do not edit. `tools/firewall.yaml` is untouched.

*Open question for the human:* **two** of the gaps are fixable by adding denylist
patterns (`bvap`/`hvap`/`wvap`, which add cleanly), which is a config change and
therefore a human decision. Corrected from "three": adding `g20` false-positives on
ordinary strings and misses other VEST vintages, and the allowlist short-circuit
cannot be closed by *any* denylist addition — that needs word-boundary matching in
`check_firewall.py` itself. Review also found the gap count is at least six, not
four. See FEASIBILITY.md §1.

---

## D-007 — Feasibility findings put through adversarial review before acting on them

**Date:** 2026-08-18 · **Phase:** feasibility

The feasibility findings were about to drive an architectural decision (which
sampler, whether to add an R toolchain, whether to concede that ensemble plans are
not legal plans). Before spending that, every claim in `docs/FEASIBILITY.md` was
assigned to an independent agent instructed to **refute** it — six claims, six
refuters with no visibility into each other, then a synthesizer instructed to
discard bad refutations rather than propagate them.

*Result:* two invalidating findings and five material ones. The headline finding
was withdrawn. The full corrections are marked **[C]** in FEASIBILITY.md.

*Alternatives:* review the findings myself — rejected, since I had already missed
a warning printed on my own terminal, and self-review does not fix that;
review only the headline claim — rejected, and the decision is vindicated, because
two self-contradictions between FEASIBILITY.md and this file (D-002 apportionment,
D-004 32%) were caught by no refuter and only by the synthesizer reading both
documents side by side.

*What this cost and returned:* 7 agents, ~632k tokens, 72 minutes wall clock. It
overturned the recommendation the human was about to act on.

*Carry into Phase 1:* the `prompt.md` loop mechanic — builder and critic with
separate context, critic reads only artifacts — is not ceremony. The bug that
survived my own review was caught within minutes by an agent whose only instruction
was to break the claim. **One refuter was itself wrong** (it re-ran the wrong entry
point and declared results irreproducible that reproduce exactly), which is the
argument for a synthesis stage that checks refutations rather than trusting them.

---

## D-008 — Bench artifacts stay gitignored; the numbers go in `docs/progress.md`

**Date:** 2026-08-19 · **Phase:** 1

The scaffold's `.gitignore` excludes `progress/` and `bench-results.json` as run
artifacts. That is the original author's decision and it is a reasonable one — the
PNGs and the full scenario dump are regenerable from one master seed.

*Chosen:* leave the ignore rule alone and write every reported number into
`docs/progress.md`, which is committed. A reviewer reading the repository on GitHub
sees the gate results, the confusion matrix and the findings without needing the
working tree; anyone who wants the raw artifact regenerates it deterministically.

*Rejected:* committing the artifacts anyway (silently overriding a human's
`.gitignore`), and reporting the numbers only in chat (they would not survive the
session).

---

## D-009 — Round 2 is reported as a failure rather than repaired before publication

**Date:** 2026-08-19 · **Phase:** 1 · **VALUE**

The first full bench run fails three of four gates, and the audit found the ground
truth itself is confounded: planted gerrymanders are separable from neutral maps by
`cut_edges > 60` alone, with TPR 1.0 and FPR 0.0, knowing nothing about
partisanship.

The tempting move is to fix the adversarial generator first and publish only the
repaired round. *Rejected.* `prompt.md` makes detection the loop precisely because
its ground truth is manufacturable and its failures are therefore visible; a loop
whose failing rounds are never written down is not a loop, it is a filter. The
round-1 → round-2 delta is also the most informative result so far — it is what
shows that the round-1 PASSes were artifacts of a 14-plan reference rather than
evidence of detection.

*Consequence:* `docs/progress.md` records AUC 0.25 (the rule ranks neutral maps as
more gerrymandered than planted ones), an always-flag detector tying both round-1
PASSes, and `min_detectable_seat_shift = null`. These are unflattering and they are
the honest state of the system.

---

## D-010 — A planted gerrymander must be indistinguishable from a neutral map on non-partisan metrics

**Date:** 2026-08-19 · **Phase:** 1 · **VALUE**

Measured in round 2: every planted plan has ~2x the cut edges and ~1/3 the
Polsby-Popper of every neutral map, with no overlap. The seat-maximizing search
wanders into ragged corners of the space that ReCom's spanning-tree proposal never
visits, and a compactness screen alone separates the classes perfectly.

*Decision:* the adversarial generator will be constrained to stay inside the
neutral ensemble's compactness distribution. A gerrymander that a compactness
screen catches is not the adversary this system exists to detect, and ground truth
that leaks its own provenance makes every downstream detection number meaningless.

*This is a `VALUE` choice, not a technical one.* It encodes a claim about what
counts as a realistic adversary: one that would survive the traditional-criteria
review a real map receives. A less capable adversary would make the detector look
better. That is the reason to state the choice here rather than bury it in the
search's acceptance rule.

---

## D-011 — Round 3's adversary is not accepted, despite improving its headline number

**Date:** 2026-08-19 · **Phase:** 1

Non-partisan separability fell from AUC 1.00 to 0.89. That is a real improvement
and it is not sufficient: D-010 requires indistinguishability, and 0.89 means a
compactness screen alone still classifies the ground truth nearly perfectly.

*Chosen:* record round 3 as failing its acceptance test and leave the numbers in
`docs/progress.md` as measured. The alternative — accepting 0.89 as "much better
than 1.00" — would reinstate exactly the failure D-009 was written about, since
every detection result built on that ground truth stays confounded by an amount
nobody would have quantified.

*Note on process:* the acceptance test was measured by an agent with no sight of
the implementation, generating fresh plans from the committed code. The
implementing agent reported far better figures for a function
(`envelope_around_plan`) that is exported but called from nowhere in `src/`. The
gap between "a good instrument exists in the module" and "the shipped path uses it"
is precisely what an independent artifact-only check is for.

---

## D-012 — The compactness/yield frontier is a result, not a tuning curve

**Date:** 2026-08-19 · **Phase:** 1 · **EMPIRICAL**

Measured on Iowa, D-direction, 2-seat shift: as the compactness constraint tightens
from the neutral ensemble's central 100% band to its central 10%, planted-plan
yield falls 32/32 → 0/24 while non-partisan AUC falls only 0.994 → unscoreable,
passing through 0.654 at the 25% band with 4/32 yield.

*Interpretation, stated as a hypothesis rather than a conclusion:* on this problem
a gerrymander that is shape-typical of the neutral ensemble may not exist at a
2-seat magnitude. Compactness is doing real constraining work in Iowa's
4-whole-county congressional problem, and there is little room for a gerrymander to
hide inside the traditional criteria.

> **RETRACTED 2026-08-19.** The interpretation above is false. Measuring the
> neutral ensemble's seat distribution directly (1,820 draws, 323 distinct plans)
> gives 0 D seats 1.0%, 1 D seat 56.0%, **2 D seats 43.0%** — shape-typical plans at
> a 2-seat shift are not rare, they are nearly half of what the neutral sampler
> produces unprompted. The collapsing yield measured the adversarial search failing
> under a constraint, not an empty feasible set. The frontier table itself stands as
> a measurement of that search; the conclusion drawn from it does not. See
> `docs/progress.md`, "The neutral seat distribution — and a retraction".
>
> The error was inferring impossibility from a search returning nothing, without
> checking whether an independent method produced counterexamples. It did, in the
> same artifact, all along.

*Why this is logged as a decision:* the frontier could have been treated as a knob
to turn until the acceptance test passed. Treating it instead as a measurement —
and reporting that the tight end is empty — is the choice. It is also a `VALUE`-adjacent
judgement about what counts as a realistic adversary, and it belongs in
`docs/CRITERIA.md` as a candidate row if it survives replication in a second state.

*Not generalisable as measured:* one state, one direction, one magnitude, one
search algorithm. Colorado or any precinct-level state would need it re-measured.

---

## D-013 — Detection magnitude is measured in units of the null spread, not absolute seats

**Date:** 2026-08-19 · **Phase:** 1 · **Proposed amendment to `CRITERIA.md` §8**

`CRITERIA.md` §8 sets the Phase 1 target at "TPR ≥ 0.95 at a 2-seat shift", class
`VALUE`, with the note that the threshold is chosen but the measurement is
objective. Measurement has now shown the threshold is not merely strict on Iowa —
it is unreachable in principle.

Iowa's neutral ensemble spans 0–2 D seats of 4, with 2 seats making up 43.0% of the
distribution (1,820 draws, 323 distinct plans). A plan producing a 2-seat outcome is
what the neutral process routinely produces, so no detector can separate it from a
neutral plan. The gate asks for a discrimination that does not exist.

*Decision:* detection magnitude is expressed relative to the spread of the neutral
seat distribution for the state under test. Concretely, the bench computes
`null_spread_seats` from the ensemble and reports a magnitude below that spread as
**unreachable**, distinct from **failed**. A gate no method could pass is a property
of the problem and must not be scored as a deficiency of the detector.

*Why this is a `VALUE` choice and not a technical correction:* choosing to measure
in units of the null makes detection thresholds state-relative and therefore not
comparable across states without stating the null width alongside. The alternative —
keeping an absolute seat threshold — is comparable across states but is unreachable
in small delegations and trivially easy in large ones. Neither is neutral. This
system states which it uses and reports the null width in every artifact so a reader
can convert.

*Status:* proposed for promotion into `CRITERIA.md` §8 as a replacement for the
absolute-seat row, per `prompt.md`'s instruction that decision-log entries recording
value judgements CRITERIA.md did not settle are candidates for promotion. Not yet
applied to `CRITERIA.md`, which remains the human's authority to amend.

---

## D-014 — Colorado becomes the detection target; Iowa becomes the null-case laboratory

**Date:** 2026-08-19 · **Phase:** 1

Iowa did what `prompt.md` chose it for: 99 whole counties and an ordered statutory
criteria list closed the full loop end to end quickly, and every architectural
question was settled against a graph small enough to iterate on in seconds. It
cannot, however, *grade* a detector — its four-district delegation gives a null
spanning half the seats (D-013).

*Chosen:* move the detection loop to Colorado, which `prompt.md` names as the second
target and `CRITERIA.md` §2.2 describes: eight districts, ordered criteria, and a
rare explicit competitiveness mandate (Amendments Y and Z). Eight districts leaves
real headroom between the null spread and a detectable shift.

*Iowa is retained*, not retired, as the null-case laboratory. A detector that fires
on Iowa's neutral maps has learned political geography rather than gerrymandering
(`CRITERIA.md` §5.4, §8), and Iowa's tiny graph makes that the cheapest possible
false-positive test in the project.

*Known cost, accepted:* Colorado congressional districts are not built from whole
counties, so this is the precinct-level data plumbing `prompt.md` deliberately
deferred — VTD geometry, a VEST join, and a much larger adjacency graph. That work
is now justified because the methodology questions it would have obscured have been
answered on Iowa first, which was the whole point of the ordering.

---

## D-015 — Colorado units are whole VTDs, so the enacted plan is an approximation

**Date:** 2026-08-19 · **Phase:** 1

Colorado's neutral layer is built: 3,108 VTDs, 5,773,714 persons (matching the
state's certified 2020 resident population), 8,754 rook edges in a **single
connected component** — no topology repair needed, contrary to `CRITERIA.md`'s
warning that naive shapefile adjacency disconnects in nearly every state. Both
target states have now come out connected on the first attempt.

**The enacted plan cannot be represented exactly at this unit level.** Assigning
whole VTDs by representative point gives a max−min spread of **9,995 persons
(1.385% of ideal)**, where the real enacted plan is near-zero because it is built
from census blocks and splits VTDs. The 1.385% is an artifact of the unit choice,
not a property of Colorado's map.

*Consequences, stated rather than absorbed:*

- The population-equality constraint for a Colorado ensemble cannot be Karcher-tight.
  Whole-VTD plans cannot reach single-digit deviation, so ε must be set at the
  VTD-feasible scale and **reported as a modelling choice**, not presented as the
  legal standard. This is the same like-for-like problem that contaminated the Iowa
  comparison (`FEASIBILITY.md` §5.3), arriving from the opposite direction.
- Any statement locating Colorado's enacted plan in an ensemble is a statement about
  a **VTD approximation** of that plan, and must say so.
- Iowa remains the only target where the enacted plan is exactly representable,
  because whole counties are what the statute requires there. That is a further
  reason to keep Iowa as the null-case laboratory (D-014).

*Deferred:* block-level assignment would represent the enacted plan exactly, at the
cost of a ~140,000-node graph. Not justified until the VTD-level loop works.

---

## D-016 — VEST subdivides 107 Colorado VTDs; an id-only join would have biased the data toward Republicans

**Date:** 2026-08-19 · **Phase:** 1

VEST's 2020 Colorado file has 3,215 precincts where TIGER's VTD layer — and the PL
94-171 VTD summary level — has 3,108. VEST subdivides 107 of them.

**An id-only join drops those 107 silently, and the loss is not random.** The
dropped precincts carry 215,617 votes at a **60.0% two-party Democratic share
against a 56.9% statewide**, concentrated in Jefferson, Douglas, El Paso, Denver and
Larimer counties — the populous Front Range. Shipping that join would have biased
every partisan metric toward Republicans by an amount nobody would have noticed,
because the join reported "unmatched units: 0" — it is the *precincts* that were
unmatched, not the units, and only a vote-total check catches it.

*Chosen:* assign each VEST precinct to the VTD containing its representative point,
so a subdivided precinct aggregates into its parent and no vote is lost. **But the id
match wins wherever it exists**: a point test misplaced 15 precincts that have an
exact id, because VEST and TIGER digitise the same boundary slightly differently.
Spatial assignment is used only for the 107 subdivisions that have no id.

*Verification:* 6,492,770 votes in, 6,492,770 votes out (100.0000%), with D
1,804,352 and R 1,364,607 matching Colorado's certified 2020 presidential result
exactly. Both totals are asserted in `tools/prepare_data_co.py`, so a future change
that reintroduces the leak fails loudly.

*Generalisable warning:* "every unit matched" is not evidence that a join is sound
when the two tables have different cardinality. The check that matters is
conservation of the quantity being joined.

---

## D-017 — Experiment 3 ships one demonstration, not three

**Date:** 2026-08-20 · **Phase:** experiments

Three Colorado plans were found on which a named fairness metric reads essentially
zero while one party takes 7 or 8 of 8 seats. Independent verification confirmed
every number. But **two of the three fail this repository's own compactness
standard** (`gerrymander.check_legality`'s envelope, D-010): they sit outside the
entire 12,000-draw neutral range on all five measures, at roughly one seventh the
Polsby-Popper and four times the cut edges of the *worst* neutral draw.

*Chosen:* `co-mean-median` is the headline demonstration. It is the only plan in the
set that is legal by every standard this repo applies **and** inside the full neutral
compactness range on all five measures — a map a commission could plausibly adopt.
The other two are reported with the qualification stated in the same breath as the
result, never as free-standing findings.

*Why this is a decision and not bookkeeping:* the dramatic version of this
experiment is "three metrics gamed, one of them on an 8–0 sweep". The honest version
is "one metric gamed on a plan that would survive traditional-criteria review, and
two more on plans that a compactness screen rejects on sight". Round 2 established
that a gerrymander a compactness screen catches is not the adversary this system
exists to detect; applying that standard to our own headline result is the same rule
pointed inward.

---

## D-018 — Two Iowa cells were refuted and are recorded as failures

**Date:** 2026-08-20 · **Phase:** experiments

`ia-mean-median` and `ia-partisan-bias` were returned as successes and **refuted on
verification**. Both produce 0 D of 4 — which is inside Iowa's neutral range of 0–2
and is the enacted plan's own outcome. The neutral process produces that result
unprompted, so it is not lopsided against the null however extreme it looks against
proportionality.

The structural reason is worth keeping: **Iowa's neutral support bottoms out at
0 D, so no R-favouring seat outcome in Iowa lies outside the neutral range at any
search quality.** That cell was unwinnable by construction, not by budget — the same
shape of finding as D-013, arriving from the other direction.

*Recorded as failures rather than quietly dropped*, because a searcher's claim that
does not survive verification is evidence about the method, and this project has
already shipped one false headline (`FEASIBILITY.md` §5.1) by not applying that rule.

---

## D-019 — "no tradeoff" and "cannot tell" are reported as different findings

**Date:** 2026-08-21 · **Phase:** experiments · **EMPIRICAL**

Experiment 2 returned three Colorado cells at `none`, two cells at `weak`, and the
independent verifier set `can_evidence_support_conclusion = False` for the
experiment taken as a whole.

Those are not in tension, and collapsing them would be the error. The Colorado
compactness × partisan-fairness null is **supportable**; everything involving county
integrity is **cannot tell**. The finding reports them separately and says which is
which, because a reader who takes "we found no tradeoffs" from a section where half
the cells were unmeasurable has been misled by the summary rather than the data.

*What makes the compactness × fairness null different, and this is the part worth
keeping:* it is a **ceiling result, not a sampling result**. Inside the top
Polsby-Popper decile the ensemble already attains |EG| = 1.8×10⁻⁴, |mean-median| =
1.0×10⁻⁵, |declination| = 5.8×10⁻⁴ — the metrics' optima. Zero cannot be beaten from
outside the compact region, so the usual objection (a compactness-biased sampler
never visits the region where tradeoffs live) has no purchase here. It was tested
directly rather than argued: Experiment 3's deliberately non-compact Colorado plans,
seven times less compact at PP 0.0152, are **worse** on efficiency gap and
mean-median and better on declination by 1.1×10⁻⁵ radians, which is nothing.

*The general lesson:* an objection to a null is answered by measuring the region the
objection names, not by acknowledging it in a caveat. Where we could do that we
claim the null; where we could not, we say `cannot tell`.

---

## D-020 — Two defects in Experiment 2's own instrumentation, recorded

**Date:** 2026-08-21 · **Phase:** experiments

The verifier audited the shared test module before touching any cell, killed all
twelve planted mutants (every direction flip, the goodness sign inversion, decile
inversion, Pareto min/max inversion, three hard-coded verdicts), and reproduced every
headline within bootstrap noise. The module is sound and the direction table is
correct for all fifteen criteria. Two real defects were still found:

1. **Iowa's convergence diagnostics were computed on 216 of 36,784 draws.** The
   scratch driver's `chains_of()` filtered chains by `len > 1` and then truncated all
   of them to the shortest survivor, which had 4 draws. The reported R-hat of
   3.73–4.01 was a statistic about four draws per chain, not about the ensemble. The
   finding uses the 47 full-length chains instead.
2. **"All three deciding tests agree" was one test plus two constants.** The
   Pareto-binding and achievability tests only vote "tradeoff" at |ρ| ≳ 0.89, far
   above anything present in these ensembles, so their agreement carried no
   independent information. A statistic promoted to "the deciding statistic" in three
   cells (`free_gain_ratio_a`) is also non-monotone in dependence strength and cannot
   distinguish independence from |ρ| ≈ 0.3 at the observed values.

*Recorded rather than quietly corrected* because both are the same failure this
project keeps finding in itself: a number that looks like corroboration but is
structurally incapable of disagreeing. Round 1's gates were tied by a constant
detector; round 3's acceptance test was met by a function nothing called; here two
of three "confirming" tests could not have said no.

---

## D-021 — The tradeoff instrument carries its own controls, and the run aborts if they fail

**Date:** 2026-08-21 · **Phase:** experiments

Experiment 2 decides each criterion pair by three tests — a bootstrapped Spearman
rho, a conditional-degradation test on the best decile, and a joint-achievability
test. The previous run of this experiment reported that all three agreed; the
verification pass found that **two of the three were constants and could not have
disagreed**. The finding was therefore one test wearing three hats.

*Chosen:* every test is run against synthetic tradeoff, independent and
synergistic data before any real data is loaded, and `tools/experiment_2_tradeoffs.py`
raises rather than proceeding if a test does not return the verdict that structure
demands. `tests/test_experiment_2.py` then asserts that the control *fails* when a
test is stubbed to a constant in either direction, so the control cannot decay into
a formality that always passes.

*Alternatives:* fix the two tests and re-run — rejected as insufficient, because it
leaves nothing that would catch the same defect the next time a test is edited;
report the tests separately and let a reader judge — rejected, because "all three
agree" is exactly the claim a reader cannot check without the controls.

*Generalisable:* a test that cannot produce both verdicts is not evidence, and a
pipeline that reports its own defaults as a finding will do so silently. The check
belongs in the instrument, not in the review of the instrument.

---

## D-022 — Colorado's county integrity is measured from an explicit GEOID-prefix map

**Date:** 2026-08-21 · **Phase:** experiments

`data/processed/co_units.csv` carries `GEOID`, `NAME` and `pop` and no county
column, so `evaluate.administrative.subdivision_map` correctly falls through to its
documented degenerate case: **each VTD is its own subdivision, county splits are
identically zero, and every county-integrity result is vacuous.** The module says
so in its own `degeneracy` report; nothing was broken, and nothing said "no county
tradeoff" was a false negative either.

*Chosen:* the experiment driver passes an explicit `{VTD: county}` map built from
the GEOID prefix — 11-character VTD GEOIDs are state FIPS (2) + county FIPS (3) +
VTD (6), and `[:5]` recovers 64 distinct counties, which is Colorado's county
count. The enacted plan then splits 9 counties into 80 pieces, so the criterion
varies and the pair tests are live.

*Alternatives:* add a `county` column to `co_units.csv` — rejected for now, because
that file is a *neutral* artifact read by `src/generate` under the schema allowlist
of ARCHITECTURE.md §4, and widening that allowlist to carry a column only
`evaluate` needs weakens the guard for no gain; derive the parent spatially —
rejected, the id prefix is exact and a spatial test would reintroduce exactly the
class of error D-016 records.

*Consequence:* the county criterion is measured at whole-VTD resolution, so a
county split that falls inside a VTD is invisible. That is the same D-015
approximation the rest of the Colorado work carries.

---

## D-023 — A test that cannot decide is not a vote against a tradeoff

**Date:** 2026-08-21 · **Phase:** experiments

Two things were being conflated under `degenerate`: a criterion that does not vary
at all, and a *test* that cannot answer for this pair while the other two can.

*Chosen:* a pair's verdict is taken over the tests that could decide. `strong` is
reserved for pairs where all three answered and all three fired; anything else with
at least one firing test is `weak`; zero firing tests is `none`; and only a pair no
test could decide is `degenerate`. Each pair records `n_deciding`, a `partial` flag,
and the names of the tests that abstained.

The conditional test was also abstaining on criteria that plainly vary. Its effect
size is measured in robust SDs, and for a small-integer criterion — competitiveness
is a count of districts, county splits a count of counties — more than half the
ensemble can sit on the median, making the MAD exactly zero. The scale estimator now
falls back to the plain SD, so only a genuinely constant criterion returns zero.

*Why this is a decision and not a bug fix:* the previous rule was defensible —
"if any test could not answer, do not report a verdict" is conservative. It is also
the rule that turns a partially-instrumented pair into a silent no-finding, and
`none` and `cannot tell` were exactly the two things the last run of this experiment
was criticised for merging.

---

## D-024 — Both elections, one ensemble

**Date:** 2026-08-21 · **Phase:** experiments

`docs/progress.md` records "one election" as the first limitation of Experiment 3.
The neutral ensemble knows nothing about any election — that is what the firewall
guarantees — so scoring the same draws twice costs no sampling.

*Chosen:* every partisan criterion is measured on both the 2020 presidential and
the 2020 US Senate two-party results, the entire pair analysis runs against each,
and the artifact carries a `contest_agreement` block naming every pair where the two
elections disagree. A verdict that flips when the office changes is a finding about
the office, and it should not take a second experiment to see it.

*Alternatives:* run the experiment twice with a `--contest` flag — rejected, it
doubles the sampling cost for nothing and invites the two runs to drift apart on
seeds; report the presidential result only and list the limitation — rejected, that
is what Experiment 3 did and the limitation is cheap to remove here.

*Not fixed by this:* two contests from the same election day, in the same state,
with the same electorate is a weak form of replication. It cannot speak to turnout
composition, to a different cycle, or to uncontested races.

---

## D-025 — The multiplicity correction is applied to the verdict, not reported beside it

**Date:** 2026-08-21 · **Phase:** experiments

Experiment 2 runs one conditional permutation test per ordered pair per contest:
25 on Iowa, 42 on Colorado, at `alpha = 0.05`, uncorrected. Under a global null
that produces false firings of the same order as the reported signal. The first
implementation computed Benjamini-Hochberg q-values and attached them to each
pair while the headline verdict was still built from the raw p.

*Chosen:* the correction rewrites the verdict. `verdict_uncorrected` is kept on
every pair so the difference is visible, and one function computes the verdict in
both places rather than two rules that could drift apart.

*Consequence, and why this is a decision rather than a detail:* it changed the
result. Three of Colorado's four non-null relationships were carried by a single
conditional firing at `p ~ 0.02` with rank correlations of −0.022, +0.006 and
−0.077 — indistinguishable from zero. None survives. I had already reported those
three to the user as a coherent "prioritising competitiveness costs compactness"
pattern, with a geographic mechanism attached. The pattern was three false
positives sitting beside one real effect, and the mechanism was invented for it.

*Alternatives:* report both and let a reader choose — rejected, because the
uncorrected table is the one people quote; correct only within a state — rejected
as arbitrary, the tests are run together and are exchangeable within a state.

---

## D-026 — A correlation between two metrics is not a finding until the arithmetic is ruled out

**Date:** 2026-08-21 · **Phase:** experiments

Experiment 2's one surviving relationship on both states is competitiveness
against mean-median. Both are functions of the same district vote-share vector,
so a correlation between them can be a property of the two functions rather than
of the maps — true of any *k* numbers, and silent about Iowa or Colorado.

*Chosen:* `tools/check_metric_algebra.py` measures what the arithmetic alone
produces, on share vectors with no map behind them, holding the statewide mean
exactly — the one constraint districting actually faces, since a map cannot
choose the statewide vote share. The arithmetic gives **+0.003 to +0.20** at
every spread and both district counts; both states observe a strongly negative
rho. The functional form pushes the opposite way, so the observation is not an
artifact of it.

The check is built so that it can fail: one test makes the two metrics genuinely
redundant and asserts the null then reports the strong correlation the real pair
does not; another asserts that a state whose observation the arithmetic *does*
reproduce is flagged. Without those it would be decoration — the same failure
D-021 records against the first controls.

*Generalisable, and the reason this is a decision:* this project's metrics are
mostly functions of two or three underlying vectors, so **any** future
correlation between two of them needs this check before it is called a finding.
It is cheap and it is the difference between a result and a tautology.

---

## D-027 — The experiment is a pure function of its committed draws

**Date:** 2026-08-21 · **Phase:** experiments

The execution environment reclaimed its container roughly every ninety minutes
and destroyed five long runs, twice after the analysis had finished but before
the results file was written. Nothing committed was ever lost — the remote held
every push — but the sampling and the analysis were entangled, so losing the
process meant re-sampling.

*Chosen:* `--from-draws` re-derives every verdict from
`docs/experiment-2/{ia,co}-draws.csv.gz` with no sampling and no GerryChain, and
the results file is written after each state rather than once at the end. A
`{prefix}-chains.json` sidecar carries every attempted chain including those that
died before producing a draw, because the CSV alone understates the failure rate
and ARCHITECTURE.md §7 makes that rate part of the result. Each recovered chain's
seed is checked against the one its index derives, so a draws file from another
configuration is refused rather than silently mixed in.

*The better reason, independent of the environment:* a reader checking a verdict
should spend a file read, not an hour of CPU and a working sampler. The
separation was forced by an infrastructure problem and should have been there
anyway.

*Also recorded:* completion is now **read** from the draws file rather than
re-derived from the row count. Recomputing it let a truncated file quietly
re-describe a completed chain as a failed one, changing a reported number.

---

## D-028 — "Vary each criterion's weight" is answered as tolerance, and the substitution is stated

**Date:** 2026-08-21 · **Phase:** experiments

`prompt.md`'s Experiment 1 asks to vary each criterion's *weight and tolerance*.
There is no weighted objective in this repository to vary weights in, and
`prompt.md` is the document that forbids building one. Neither jurisdiction uses
weights either: Iowa Code ch. 42 is lexicographic and Colorado's Amendments Y and
Z order rather than weight.

*Chosen:* measure tolerance, and say plainly in the write-up that half the
instruction was not obeyed and why.

*Alternative considered and not taken:* vary the lexicographic **order** — permute
Iowa's four ordered criteria and measure which permutations change outcomes. The
audit raised this as a genuine gap and it is the closest available analogue to a
weight sweep. It is not done here because two of Iowa's four ordered criteria
(contiguity, county integrity) are constant by construction in this ensemble, so
only two positions could actually be permuted. Recorded as a gap rather than
argued away.

*Also recorded:* "plausible range" is substituted too. Only population equality
has a legally plausible range (*Karcher*). For every other criterion the sweep
uses percentiles of that criterion's own ensemble distribution, which is a
different thing and is labelled as such.

---

## D-029 — A verdict must clear a null computed at the ensemble's real sample size

**Date:** 2026-08-21 · **Phase:** experiments

Experiment 1's first version compared Cliff's delta against a fixed threshold
(0.147, the conventional "small effect" boundary). That threshold is calibrated
for independent observations. These ensembles have nominal sizes of 8,000 and
12,000 draws and **effective sample sizes of 19 to 78** on the columns that carry
the ranking.

*Chosen:* every criterion's delta is compared against a within-chain
circular-shift null on the same ensemble — the null Experiment 2 already uses,
which preserves each chain's autocorrelation and marginal while destroying the
cross-criterion pairing. `binds` requires clearing both the fixed threshold and
the null.

*Consequence:* it changed the result. Colorado's efficiency gap at −0.152 does not
clear its own noise floor of −0.157, so Colorado drops from three binding criteria
to two. And Iowa's floor is roughly double Colorado's, which means part of "Iowa
binds harder than Colorado" was Iowa mixing worse — a statement about the sampler
reported as a statement about the state.

*Generalisable:* any threshold in this project that was chosen from a statistics
convention assumes independent draws, and no ensemble here supplies them. The
same correction is owed anywhere else a fixed cutoff is applied to ReCom output.

---

## D-030 — An effect that only exists outside the legal range is reported as legally inert

**Date:** 2026-08-21 · **Phase:** experiments

The epsilon sweep found tight population equality costing compactness, and the
first write-up called it the largest tradeoff in the project. Attaching a
chain-label permutation test to each rung, and converting each tolerance into the
deviation the law actually speaks about, changed what it means rather than whether
it exists.

*Karcher v. Daggett* struck down a congressional plan at 0.6984% total deviation —
5,570 persons for Iowa's ideal district. Every rung that clears its permutation
null sits at or past that line (0.681%, 1.368%, 6.756%). Every rung a
congressional plan could lawfully occupy (0.066%, 0.139%) is indistinguishable
from a relabelling of the chains.

*Chosen:* report the effect as **real and legally inert**, with the legal scope as
the second sentence rather than a footnote, and record that the two undetectable
rungs are also the two worst-mixed cells so a reader can see that "no detectable
effect" is partly a power statement.

*Why this is a decision:* the tempting write-up is "population equality trades off
against compactness", which is true of the numbers and false of anything a
commission could do. A finding whose entire support lies in unconstitutional
territory has to say so, and the same check — convert the parameter into the units
the governing authority uses — is owed by every other tolerance this project
sweeps.

---

## D-031 — "Decorative" replaced by "non-displacing on this ensemble"

**Date:** 2026-08-21 · **Phase:** experiments

`prompt.md` asks which criteria are "decorative". Experiment 1's statistic is the
worst displacement a criterion forces on any *other* criterion, and reporting a
small value as "decorative" says something much stronger than the statistic
supports.

Colorado's compactness filter at its strictest removes **90% of the ensemble**,
moves median Polsby-Popper from 0.177 to 0.212, and drags cut edges and county
integrity strongly in the same direction. It reorganises the ensemble
constructively, which a worst-case displacement statistic cannot see, and calling
that "a commission could adopt it and change nothing" is false on the
instrument's own numbers.

*Chosen:* every such verdict reads "non-displacing on this ensemble", with the
qualification spelled out once: it is a statement about the criteria in this table
and the plans ReCom reaches, not about districting. The qualification carries three
specific caveats — ReCom's compactness bias, Colorado's population-equality row
being measured entirely outside the *Karcher* window, and the criteria that are
constant by construction being excluded from the ranking rather than ranked last.

*Consequence:* the experiment no longer answers `prompt.md`'s question in
`prompt.md`'s vocabulary. That is the right trade: the word was doing work the
measurement cannot support.

---

## D-032 — The report reports; it does not resolve

**Date:** 2026-08-21 · **Phase:** 2

`prompt.md` Phase 2 requires every metric side by side *"with disagreements
between them highlighted rather than resolved"*. The tempting implementation is a
function that takes the disagreement and returns the better answer — pick the
trusted metric, drop the untrusted ones, average the compactness measures.

*Chosen:* `src/evaluate/report.py` returns every value plus a list of
disagreements and resolves none of them. `combined_score` is an explicit `None`
carrying the sentence from `prompt.md` that forbids it, because an absent key
reads as an oversight while `None` with a reason reads as a choice, and a test
asserts no other key in the report is a score.

Untrusted metrics are reported **with their values** beside the trust flags rather
than filtered out. A reader handed a filtered dict cannot tell that filtering
happened, and cannot tell the difference between "this metric is fine" and "this
metric was removed for you".

*Consequence:* the report is harder to read than a score would be. That is the
trade `prompt.md` is asking for — on Iowa's enacted plan the efficiency gap
(+0.416) and mean-median (−0.024) disagree about which party the map favours, and
any resolution step would have deleted the most informative thing in the file.

---

## D-033 — A membership layer and a districting layer are different objects

**Date:** 2026-08-21 · **Phase:** 2

`tools/prepare_municipalities.py` assigns each unit to the parent holding the
largest share of its area, above a 50% floor. I applied that floor uniformly and
it was wrong for half the layers.

A **membership** layer — municipalities — is genuinely partial. A rural unit
belongs to no city, `None` is the true answer, and the floor is what stops a VTD
that clips a city's corner from counting as inside it.

A **districting** layer — state house, state senate — is not partial. Every voter
is in exactly one state house district, and a ballot style is the tuple of
districts a voter sits in, undefined if any component is missing. Six Iowa
counties whose area splits roughly evenly across three house districts came back
unassigned under the floor, and `evaluate.administrative.layers` correctly refused
the overlay because the layers no longer assigned the same units.

*Chosen:* the floor applies only to layers declared partial. The distinction is in
the layer table with the reason, not inferred from the data.

*Generalisable:* "belongs to nothing" is meaningful for some layers and impossible
for others, and a loader that cannot tell them apart will silently produce either
invented membership or missing districts. The failure surfaced as a refusal from a
downstream module rather than as a wrong number, which is the only reason it was
cheap to find.

---

## D-034 — No community-of-interest data ships

**Date:** 2026-08-21 · **Phase:** 2 · **VALUE**

`prompt.md` names community-of-interest splits among the metrics to implement.
CRITERIA.md §6 marks COI `VALUE` entirely and recommends supporting it *"as an
input layer, never as an objective function"*.

*Chosen:* the split-counting layer argument is a generic `{name: {unit: parent}}`
mapping, so a COI layer is supplied by a user and counted exactly like
municipalities — and **no COI dataset is included**.

*Why not ship a proxy:* §6 lists the three available approaches and rejects each.
Self-reported maps (Districtr, Representable) systematically favour well-organised
communities. Proxy-based definitions — school districts, media markets, watersheds
— are objective and arbitrary, and *the choice of proxy is the definition*.
Inferred clustering risks reconstructing racial segregation under a
neutral-sounding name and may trigger the §1 race-predominance problem. Picking
one and shipping it would make that `VALUE` choice silently, on behalf of every
future user, inside a file that looks like plumbing.

*Consequence:* the metric `prompt.md` asked for returns nothing until someone
supplies geometry. The report says so in a field rather than a comment, so a
reader can tell "supported and unsupplied" from "forgotten".

---

## D-035 — Convergence is diagnosed on the largest usable rectangle, not on full-length chains

**Date:** 2026-08-22 · **Phase:** convergence re-sample

Split R-hat and ESS need every chain the same length. This project got that
rectangle by keeping only chains that ran to completion. At 1,500 steps it was
nearly free — Iowa lost 4 of 12 and the survivors were full length.

At 12,000 steps it stops being free. Iowa's chains reach 12,000, 8,133, 6,495,
4,282 and 0 draws, so "keep the complete ones" keeps **one chain** and there is no
ensemble left to diagnose. Raising the chain length to fix R-hat destroyed the
sample R-hat is computed on.

*Chosen:* truncate every chain to a common prefix and diagnose on that.
`tools/convergence_rectangle.py` reports R-hat and ESS at every prefix length a
distinct chain count allows, so the tradeoff — longer prefix, fewer chains — is
shown rather than made silently.

*Why this is less biased, not more:* ARCHITECTURE.md §7 is what made
full-length-only look right — surviving seeds are not a random subset of attempted
seeds. That argument is correct and it points the other way here. **Selecting on
completion selects on the chain's whole path**; a chain that died at step 6,496 is
excluded for a property of its tail while its first 6,495 draws are as valid as
any others. Truncating to a common prefix selects on nothing, because the prefix
was drawn before any chain knew it was going to die.

*Two failure modes, kept apart.* Seeds derive from the chain index, so the same
seeds fail every run: Iowa's chain 4 finds no initial partition at any length
tried. That is a property of the seed and truncation does not recover it.
Mid-chain deaths are the length-dependent ones. A fixed set of unusable seeds and
a rising death rate are different facts about the sampler and are reported
separately.

*Consequence:* the ensemble's reported size is now a choice with a stated
tradeoff rather than a fixed consequence of the failure pattern, and the artifact
must say which rectangle a verdict was computed on.

## D-036 — A figure draws only what the repository can regenerate

**Date:** 2026-08-23 · **Phase:** experiment figures

`prompt.md` asks each of the three experiments for "a plot and a written
finding". Experiments 1 and 3 had the finding and no plot: Experiment 3's plots
were produced during the run and written to a scratch directory that a container
reclaim then deleted. Rebuilding them raised a question the other two plots never
faced, because Experiment 3's seven searched plans are not all in the repository
— three Colorado plan CSVs were committed and four were not.

*Chosen:* the figure draws the five rows it can recompute from committed files,
recomputes them at draw time rather than reading a stored table, and prints the
four it is not drawing along with why. `tools/plot_experiment_3.py` imports
`evaluate.partisan` and derives every cell from the plan CSV on each run.

*Why not transcribe the missing four from `docs/progress.md`:* they were verified
once and the numbers are almost certainly right. But a figure that mixes
regenerated cells with transcribed ones has no way to show a reader which is
which, and the transcribed cells would then be the only claims in the repository
that no code can check. Re-running the four searches was also rejected —
`prompt.md` says "Run each once… do not iterate to improve the result", and a
re-run under a different random draw is a new experiment wearing the old one's
label.

*Consequence:* `tests/test_experiment_3_plans.py` pins the three committed plans'
seat counts and metric values against the published table, so a drift in any
metric implementation fails the suite instead of silently rewriting both the
finding and the figure. The four absent rows remain absent, named on the figure
itself, until their plans are regenerated by a run that commits them.

*A second choice inside the same figure:* the alarm colour marks metrics that
**pass** a screen, inverting this repo's convention everywhere else. On a map
that hands one party seven of eight seats, "the metric is satisfied" is the
finding, and a reader skimming a conventionally-coloured grid would read the
experiment's result as reassurance. The inversion is stated in the legend, and
the two enacted maps are separated by a rule and italicised, because a passing
metric on a 5–3 map is not a scandal and must not be coloured as though it were.

## D-037 — The suite must run on a machine that has never fetched the data

**Date:** 2026-08-23 · **Phase:** check-in

Every "the suite is green at N" line in `docs/progress.md` was produced inside a
container where `data/processed` had already been built. Run on a clean checkout
of the same commit, the suite produced **2 failures and 45 errors** — every one a
`FileNotFoundError` from a module-scoped fixture loading Iowa. Four test modules
guarded for the missing data and four did not, and the four that did not held the
`evaluate` surface: elections, partisan, plan, and one Experiment 2 test.

`data/` is gitignored because the election returns are not redistributable, so
its absence is the normal state for anyone who is not us. The suite could
therefore only be run green by someone who had already run `prepare_data.py` —
which meant the pass count was a claim no reviewer could check, and CI could not
be wired at all.

*Chosen:* one guard, in `tests/dataguard.py`, imported by every module.

*Why the guard goes in the fixture, not on the test:* forty-six tests would each
need a mark, and the forty-seventh — written later by someone who did not know
the convention — would not get one. `require()` raises skip from inside a
module-scoped fixture, so every test that depends on real data inherits the guard
by depending on the fixture. Only the two tests that read a path directly carry a
mark.

*A second defect fixed on the way:* four of the eight existing guards were
written `Path("data/processed")`, relative to the working directory rather than
to the repository. Running pytest from anywhere but the repo root made those
guards report the data missing and skip tests that could have run — silently,
because a skip is not a failure. This is also what made the first attempt to
measure the problem wrong: run from a scratch directory, the relative guards
skipped spuriously and the absolute ones did not, producing four failures that
were artifacts of the measurement rather than of the repository. Everything is
now anchored to `dataguard.__file__`.

*Consequence:* `.github/workflows/tests.yml` runs the suite on a runner with no
data — 573 pass, 151 skip, exit 0. Two numbers now have to be quoted together,
and both appear in the progress log: what passes anywhere, and what passes only
here. `requirements.txt` exists for the same reason, pinning the versions every
published number was produced with; `gerrychain` is pinned exactly, because its
cut-finder is where the `node_repeats` defect lived.

## D-038 — A release is cut by a version bump, not by a merge

**Date:** 2026-08-23 · **Phase:** archiving

Zenodo mints a DOI for every GitHub release, and a DOI is permanent: it can be
superseded but never withdrawn. "Release on merge to main" therefore means "a
permanent identifier per merge", and a citation history nobody can read.

*Chosen:* `.github/workflows/release.yml` fires on a push to `main` that changes
`CITATION.cff`, and skips if the resulting tag already exists. Routine merges do
nothing; bumping the version is the deliberate act that says this state is
citable. `workflow_dispatch` cuts one without a bump.

*Why the release job re-runs the checks:* the archive Zenodo takes is the tree at
that commit. `tests.yml` already ran on the same commit, so this is redundant in
the ordinary case — and it stays, because the case it guards is not ordinary. A
DOI pointing at a tree whose firewall check fails is not fixable afterwards; the
cost of being wrong is asymmetric enough to pay for a duplicate run.

*What this cannot automate:* the Zenodo–GitHub webhook is installed by the
repository owner through Zenodo's own settings, and Zenodo does not see releases
published before it is switched on. The workflow says so in its step summary
rather than leaving a silent no-op. If a release is cut before the toggle, the
fix is to delete the release and tag and re-cut with `workflow_dispatch` — the
only genuinely recoverable moment in this whole path.

*A contradiction found on the way:* `README.md` said "License: TBD before any
public release" while `LICENSE` had been Apache-2.0 since the scaffold and the
repository was already public. Zenodo requires a licence, so this had to be
resolved rather than noted. Apache-2.0 stands; the README now also says what the
licence does **not** cover, since no input data is redistributed here and the
election returns carry no declared licence at all (§9.1).

*Authorship is a real question and is not settled here.* `CITATION.cff` names one
human author and no ORCID, with a comment saying an ORCID cannot be guessed. What
share of this work an agent performed is visible in the commit history and is
left for the author to describe rather than encoded in metadata by the agent.
