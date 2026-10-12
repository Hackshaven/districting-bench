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

*Authorship.* `CITATION.cff` names one human author, with the ORCID supplied by
that author and checked two ways before being written down: the ISO 7064 MOD 11-2
checksum, and the ORCID public API, which returns the matching name. Neither
check was skippable — a mistyped ORCID in a permanent deposit attributes the work
to a stranger.

What share of this work an agent performed is visible in the commit history and
is left for the author to describe. It is deliberately not encoded in citation
metadata by the agent itself.

## D-039 — Iowa's seat counts are read off the committed efficiency gap, not recounted

**Date:** 2026-10-11 · **Phase:** post-release

*Since:* D-043 counts every committed draw's seats from the returns, on plans
regenerated from their seeds, and the reading agrees on all 57,553 under both
contests.

The README's figure and its two numbers came from a 1,820-draw ensemble and a
gitignored results file (`docs/progress.md`, "The README's first result,
re-derived on the v2 ensemble"). Re-deriving them on the v2 ensemble needs each
draw's Democratic seat count, and `docs/experiment-2/ia-draws-v2.csv.gz` does not
record one. It records |efficiency gap|, |mean-median| and competitive districts
per contest.

*Chosen:* read the seat count off the efficiency gap. On a fixed election the gap
is pinned by the outcome. With wasted votes counted against half of each
district's votes, `EG = 2V − ½ − τ` exactly, where `τ` is the share of two-party
votes cast in districts the Democrats win, and `τ = s/k` when turnout is equal.
Each seat count therefore has a level, `|2V − ½ − s/k|`, and a draw sits off its
own level by its turnout imbalance. `tools/plot_seat_distribution.py` assigns
each draw to its level only under two checks, and refuses the whole sample if
either fails:
- a draw read as a sweep (0 or `k` seats) must sit above its level by exactly
  what the strict-majority threshold allows: `k − j/2` votes, where `j` counts
  the districts with an odd total and so has the parity of the statewide total
  `T`. That is 2.5 or 3.5 votes under the 2020 presidential vote, and 2, 3 or 4
  under the Senate vote;
- every other draw must sit within half of the half-gap of its level.

*Alternatives:*
- **Recount from plans and returns.** Not done: the plans are not committed (the
  draws file holds metrics only) and would have to be regenerated from their
  seeds, and the returns cannot be redistributed, so only a reader who has
  fetched VEST could check the result, as for every experiment. A one-time
  recount of one chain would verify that chain's readings and test the method
  on the rest, and is worth doing wherever the data are built. Verifying the
  0-seat count takes the draws read as 0 in all six chains, which means
  rerunning each chain to its last such draw: 20,127 of the rectangle's 27,564
  draws. The whole rectangle, for 37% more, would also verify the 1-versus-2
  split.
- **Keep the 1,820-draw figure.** Rejected: no reader can regenerate it (D-036),
  and its sample is the least converged Iowa ensemble the repository quotes.
- **Add a seats column to the draws file.** Rejected: that is a new measurement,
  and the committed file is the record of the one that was made (D-027).
- **Assign each draw to its nearest level, with no margin.** That was the first
  version, and review showed the guard was nearly empty. Storing |EG| rather than
  EG folds the sign away and brings Iowa's 1- and 2-seat levels to 0.083 apart,
  and a nearest-level rule refuses only a draw exactly at the midpoint. A 1-seat
  plan whose Democratic district cast 30% of the state's votes would have been
  read as 2 seats without complaint.

*What the checks establish:* the identity is exact and its only free term is
turnout. Draws read as sweeps are checked to the half vote: all 395 draws read
as 0 seats sit 2.5 or 3.5 votes above their level (216 and 179 of them), the
only two offsets an odd statewide total allows. That check is necessary, not
sufficient. Under the presidential vote a plan that is not a sweep, and has no
exactly tied district, lands on the same grid only if the districts the
Democrats win cast one of six totals, 1,379,512 to 1,379,517 votes (`4V − 1` of
the two-party vote, 83%): a turnout imbalance of 0.083 at 3 seats, 0.333 at 2
and 0.583 at 1. Any other tie-free plan whose gap lands nearest the 0-seat level
stops the plotter, and none of the 57,553 committed draws does. A plan the
Democrats win none of is always read as 0 unless one of its districts is exactly
tied, so short of a tie a misreading could only add to the count. The 0-seat
count is therefore a reading, but a harder one to get wrong than the 1-versus-2
split, and only a recount of the draws read as 0, which are spread over all six
chains, would verify it. Every other draw sits at most 0.0143 from its level,
about a third of the 0.0413 half-gap, but that residual is measured from the
level the draw was read at, so it cannot show on its own that the reading is
right. Misreading a 1-seat plan as 2 would take a Democratic district casting
over 31% of the state's two-party vote against 25% at equal turnout: a turnout
imbalance of 0.062, three times the margin, by construction, and four times the
largest residual, by measurement. From there to 0.103, a band about 68,000 votes
wide, the misreading would pass without complaint, and so would a 2-seat plan
read as 1 from the same band the other way. The two enacted plans in the Phase 2
report, counted directly from the returns, read back correctly, but that is weak
support: Iowa's is a sweep, exact whatever the turnout, and Colorado's sits far
from Colorado's closest levels. Under the 2020 Senate vote the same checks pass
with more room: the largest residual is 0.0159, against a half-gap of 0.0570.

*Limits:* the method works only when every draw's turnout imbalance stays inside
the margin. How close the folded levels sit is a property of the vote share, the
district count, and the decision to store |EG|. On Colorado the closest levels
are 0.028 apart. Of the 20,000 v2 draws, 125 sit farther than that half-gap from
every level, and 9,857 farther than the margin the plotter applies, half the
half-gap, so the plotter refuses Colorado (`tests/test_seat_distribution.py`
pins both counts). Nothing uses the method there. Storing the signed gap, or
the seat count, in the next measurement would remove the need for any of this.

*Earlier entries:* D-012 and D-013 quote the 1,820-draw shares (2 seats at
43.0%). Their conclusions rest on the 0–2 span, which stands under the
presidential vote. The shares themselves are superseded by the ones recorded
here, and the entries are left as written.

*Corrected in review:* an earlier version of this entry called the 0-seat count
verified outright, because every draw read as a sweep sits on the half-vote
grid. GitHub Copilot's automated review of pull request #7 constructed district
vote totals that give the Democrats 2 of 4 seats and land on the grid too;
`tests/test_seat_distribution.py::test_every_sweep_sits_on_the_half_vote_grid`
keeps them. The paragraph above now says what the grid does and does not
establish, after the fourth audit in `docs/first-result/INSTRUMENT-AUDIT.md`.

## D-040 — PlanScore's published efficiency gaps use a different formula; this repository keeps CRITERIA.md's

**Date:** 2026-10-11 · **Phase:** post-release · **VALUE** (whether to report both forms)

`prompt.md` asks for the metric implementations to be cross-checked against
PlanScore. On the same district totals, rounded to whole votes, three metrics
agree up to sign and scale, and the efficiency gap does not. PlanScore's code
computes, and its files publish, the equal-turnout form `(S − ½) − 2(V − ½)`,
while `evaluate.partisan` counts wasted votes (`docs/progress.md`, "Cross-check
against PlanScore"). PlanScore's own metric page, which `CRITERIA.md` cites,
describes the wasted-vote form, as `CRITERIA.md` §5.1 does. PlanScore's code
counted wasted votes until August 2021, when commit 24331854 changed it "to use
vote share instead of raw counts"; the per-race values compared here arrived after
that (19927c3e, September 2021), so PlanScore's code has never computed them in
the wasted-vote form, though its plan page still describes them in wasted-vote
words (`planscore/website/static/plan.js` at 3f866f9). PlanScore first swings any
statewide vote share outside 25–75% into that band. Inside it, where all eight
races compared lie, and on a plan with no tied or empty district, as none of
these has, the two differ in PlanScore's orientation by `τ − S`, plus a
strict-majority term of at most `k/T`, so they agree whenever `τ = S`, which
includes equal turnout and any one-party sweep.

*Chosen:* keep the wasted-vote form, correct the docstring that called the two
the same up to sign, and record how far apart they are on a real plan. Whether
to report both forms is left open below, for the owner.

*Alternatives:*
- **Switch to PlanScore's form.** Rejected: `CRITERIA.md` §5.1 defines the
  efficiency gap by wasted votes, and only the owner amends it. Switching would
  also move every efficiency gap this repository has published, in the Phase 2
  report and in all three experiments.
- **Report both forms side by side.** Not done here, and the **VALUE** part of
  this entry. It is what `prompt.md`'s "disagreements highlighted rather than
  resolved" points toward. But it adds a metric to the report and to every
  experiment's columns, so it is the owner's call.
- **Commit PlanScore's files so the check runs offline.** Rejected: they hold
  district-level election returns under no stated licence, and `CRITERIA.md`
  §9.1 commits nothing under an unstated licence. The script fetches the files
  and pins each by sha256, so a re-scored file fails the check rather than
  passing as the same input. The cost is that the check needs the network, and
  needs PlanScore's storage to stay up.

*How the check is built:* PlanScore's four definitions are re-implemented in
`tools/check_planscore.py` from the formulas in `planscore/score.py` at 566cda4,
the commit both pinned files record as having scored them, sign, scale and tie
rules included; 3f866f9 rewrites the four functions in vectorized form, and they
compute the same. None of PlanScore's code is copied, and its repository states
no licence. Every run checks each conversion against the re-implementation
(declination only on Colorado: every Iowa race is a sweep, where ours is
undefined, so there the re-implementation is checked against PlanScore's sweep
value), the efficiency gap against PlanScore's published values, the identity
above with `τ` computed from the district totals, and the wasted-vote count
against GerryChain's own `wasted_votes`, which PlanScore's files cannot check
because they publish no wasted-vote gap. So a defect in the wasted-vote count
fails rather than passing as a difference of definition. Nothing in this
repository runs PlanScore's code. Whether to tell PlanScore that its published
values and its metric page describe different formulas is the owner's call.

## D-041 — The enacted-plan comparison is not conditioned on population equality or compactness

**Date:** 2026-10-11 · **Phase:** post-release · **VALUE**

The README locates Iowa's enacted plan in the v2 ensemble's seat distribution: it
returns 0 seats, as 1.43% of the draws do (`docs/progress.md`, "The enacted plan's
caveats, now with numbers"). The comparison is not like-for-like: the draws are
not held to the enacted plan's 94-person population spread, and only 454 of the
27,564 are that equal. How its compactness compares depends on the measure: 88% of
the draws have fewer cut edges than its 51, but on mean Polsby-Popper, the other
measure the draws carry, it sits mid-ensemble, with 48.7% of them more compact. The
two measures order the draws with a rank correlation of 0.76, below the ~0.9 above
which `CRITERIA.md` §3 says the choice of measure does not matter. Pooled,
restricting the draws to those no more compact than the plan raises the zero-seat
share to 4.5% on cut edges, where the plan is in the least compact eighth, and to
2.0% on Polsby-Popper, where it is mid-ensemble; neither restriction is a matched
reference, and the size of either contrast is not robust (`docs/progress.md`).

*Chosen:* report the unconditioned share, with the population mismatch as the
reason the comparison is not yet a finding; report compactness on both measures
beside it, in the README and `docs/progress.md` but not on the figure, which has no
room for both and their disagreement; and leave any conditioning to the owner.

*Why the two are not treated alike:* population equality ranks first in Iowa Code
§42.4 (Iowa Code 2026) and compactness fourth, "to the extent consistent with the
standards established by subsections 1, 2, and 3". For congressional districts
neither the statute nor *Karcher v. Daggett* sets a person count: Iowa Code
§42.4(1)(b) requires populations "as nearly equal as practicable" to the ideal,
with its one-percent cap yielding to Iowa Const. art. III, §37, and *Karcher v.
Daggett*, 462 U.S. 725, 730 (1983), requires population equality "as nearly as is
practicable". 94 persons is the spread the enacted plan reached (Iowa Legislative
Services Agency, Plan 2 report, Table 1, 21 October 2021). Matching the reference
to it would match on the enacted plan's achieved level of the first-ranked
standard, not on a legal threshold. In a sampler a population level is an input,
the bound its draws are held to, so matching on it means re-sampling under that
bound. Compactness is an output of where the lines go, and whether to match on it cannot be settled from
these draws, because the cut-edge gap has three possible sources that
conditioning treats differently. If it comes from choices made in drawing the plan,
conditioning absorbs part of the difference the comparison measures (the second
audit in `docs/first-result/INSTRUMENT-AUDIT.md`). If it comes from constraints
the draws are not held to, conditioning could move the reference toward a matched
one, but only if the draws' relation between compactness and seats carries over
to plans drawn at the enacted tolerance, which these draws cannot show;
illustrative reweightings of them, none a matched reference, give zero-seat shares
from 0.44% to 2.4% under the constructions the third audit there tried, and other
constructions give other values. If it comes from the sampler's own
preference for few cut edges, conditioning undoes part of the reference's target,
which is a choice about what the neutral baseline is. Which measure to match on is
a further question. Iowa Code §42.4(4) names length-width and perimeter
compactness for comparing plans, and the draws carry neither. For plans made of
whole counties the perimeter test, summed over a plan's districts as the statute
allows, ranks plans by the total length of the county boundaries their district
lines follow, a length-weighted form of cut edges; mean Polsby-Popper uses the
same district perimeters, scaled by each district's area. How closely either
measure the draws carry follows the statute's tests is unmeasured here, and the
statute does not say how to weigh its two tests if they disagree. Of the two
measures the draws do carry, they are more compact than the plan on cut edges and
not on Polsby-Popper. Part of the cut-edge gap may follow from the population gap,
by an amount these draws cannot measure: the 454 population-tight draws average
48.1 cut edges against 45.5 for the rest, but across the draws population spread
and cut edges are barely associated, and too few of the 454 give 0 seats to show
whether compactness matters among them.

*Alternatives:*
- **Filter the ensemble to draws as equal as the enacted plan.** Not done. A
  filter shows what goes with more equality inside this ensemble, not what a
  sampler drawing at that tolerance produces (Experiment 1 §3), and the 454
  population-tight draws hold one zero-seat plan.
- **Filter or constrain the ensemble on compactness.** Not done, for the reasons
  above; on cut edges the zero-seat share among the draws no more compact than the
  plan also halves once each chain's warm-up is dropped.
- **Re-sample at the enacted plan's tolerance.** The matched comparison, and a new
  experiment with its own name (D-036). Its plans may be less compact, and it may
  need another sampler or start: at this ensemble's tolerance 10 of its 12 chains
  stopped short of their 12,000 draws. It must also bound the spread itself, since
  a per-district tolerance that admits the enacted plan admits spreads up to 105.5
  persons.

*Why this is the owner's:* which features of an enacted plan a neutral ensemble
must match before a comparison with it counts, and on which compactness measure,
is a judgment `docs/CRITERIA.md` does not settle. Its §2.1 does not mention
§42.4(4)'s tests; the `Election Law Analyst`'s claim register on these sentences,
`docs/first-result/LEGAL-CLAIMS.md`, marks for an election-law attorney how a
court would apply them, and proposes a corrected §2.1 for the owner.

*Corrected in review:* the first version of this entry gave compactness on cut
edges alone, said the draws already exceed the enacted plan's level of it, and
argued only the first of the cases above. The third audit in
`docs/first-result/INSTRUMENT-AUDIT.md` records that correction; the routing
reviews after it added the third case, showed that none of the reweightings is a
matched reference, and brought in §42.4(4). Earlier versions also called matching
on population equality matching "on a constraint", which read the enacted plan's
94-person spread as a legal requirement.

## D-042 — An entry not yet merged is corrected in place, with a note

**Date:** 2026-10-11 · **Phase:** post-release

*Since:* the owner confirmed both decisions below on 2026-10-12 (D-044).

The decision log's rule is that entries aren't rewritten, and a reversal is a new
entry (`CLAUDE.md`, and this file's preamble). D-039 and D-041 were written in the
change that became pull request #7, which has not merged, and both were corrected
before merge: D-039 after GitHub Copilot's automated review of the pull request and
the fourth agent audit, D-041 after the third agent audit and the agent routing
reviews that followed it. The audits are recorded in
`docs/first-result/INSTRUMENT-AUDIT.md`; the routing reviews are not. Each entry was
corrected in place, under a "*Corrected in review:*" note that says what the
earlier version claimed and what showed it wrong.

*Chosen, by the owner:* asked whether those in-place corrections should stand, the
owner answered on 2026-10-11, in conversation with the author rather than on the
pull request: "corrected in review is the right approach". The question
concerned D-039 and D-041; the author applies the answer as a rule to every
unmerged entry, this one and D-043 included. So an entry that has not merged is
corrected in place, with such a note. Once an entry is on `main` it
is not rewritten, and a reversal is a new entry, as before. The author's reasons:
until merge an entry is a draft; correcting it in place keeps the log to the
decisions that were in force, and the note keeps each correction visible. The
author also reads the rule as letting an unmerged entry carry a pointer to a later
one, as D-039 points to D-043. Whether an entry on `main` may carry one is the
owner's question, not settled here.

*Alternative:* a new entry for every correction made before merge. Rejected by the
author: a reader of `main` would meet entries superseded before anyone could act
on them, with the one in force at the end.

*Also chosen, by the owner:* "let's use a merge commit" for pull request #7, not a
squash. The author's reason: the audit records in `docs/first-result/` and
`docs/cross-checks/` cite the branch's commits by hash, and a squash would leave
those hashes resolving to nothing on `main`.

*Not changed here:* `CLAUDE.md` and this file's preamble still state the rule
without the exception. Amending them is the owner's.

*Corrected in review:* the first version of this entry said the owner chose "on
pull request #7", which reads as a comment there, and nothing was posted there. It
gave the author's reasons under the owner's name, said "review" without naming
whose, and marked itself with an "Owner's decision" label this file does not
define. The Pre-Submission Peer Reviewer agent's review of the change showed all
four.

## D-043 — Every committed Iowa draw's seats are counted from the returns, and the reading agrees

**Date:** 2026-10-11 · **Phase:** post-release

*Since:* the owner confirmed both decisions below and answered the licence
question it leaves for merge: the counts carry VEST's credit and the licence link
(D-044).

D-039 reads each draw's Democratic seats off its committed |efficiency gap|,
because the draws file holds metrics, not plans. Its fourth audit showed that the
reading is hard to get wrong but cannot verify itself. The owner made two
decisions on 2026-10-11, in conversation with the author. The first was to count:
"Verify the count". The second answered this question: "Counting seats needs
VEST's Iowa 2020 returns (ia_2020.zip, 5 MB). The dataset's stated terms are CC BY
4.0 plus a no-warranty disclaimer; [...] Nothing from it would be committed except
per-draw seat counts, a derived metric like the |efficiency gap| already
committed. May I download it on your behalf?" The owner chose "Download it for
me", whose description read: "I fetch ia_2020.zip from the Dataverse API,
accepting CC BY 4.0 and the disclaimer on your behalf, use it locally to build
data/processed/ia_elections.csv (gitignored), and commit only the seat counts."
Counting every committed draw, rather than only those read as 0 seats, was the
author's choice, for the reasons under *Alternatives*, which are the author's.

*Chosen:* count every committed draw. Experiment 2's v1 draws, 12,050 rows, are
the v2 chains' first rows, row for row, in all ten chains that have any (the
Pre-Submission Peer Reviewer agent's check), so they are counted too.
`tools/recount_seats.py` regenerates each committed chain from its seed, as
`tools/experiment_2_tradeoffs.py` drew it, under Python 3.11 and the versions
`requirements.txt` pins, and measures every draw with that script's own
`measure_plan`. All 57,553 committed draws reproduce their committed rows exactly:
cut edges, population spread and competitive districts; |efficiency gap| and
|mean-median|, under both contests; and mean Polsby-Popper. County splits match
too, but they are 0 on every Iowa plan by construction, since the units are whole
counties. An earlier run under Python 3.13 found mean Polsby-Popper up to one unit
in the last place off, 5.6×10⁻¹⁷: the per-district values reproduce, but Python
3.12 made the built-in `sum` of floats compensated on most builds, and
`measure_plan` averages them with it. The match is of the chains' paths, not of
57,553 independent checks: the draws hold 5,588 distinct plans, and each change of
plan recurs at its committed step. It identifies the plans up to the numbering of
their districts, which seats do not depend on. Each draw's seats are then counted
from the returns, and the counts are committed as
`docs/first-result/ia-seats-v2.csv.gz`, with a key for each draw's plan that
ignores district numbers, and a record of what the count read and wrote: the draws
file's hash and the counts file's, which binds the two, the configuration, every
chain, the hashes of the inputs and of VEST's files, VEST's dataset, version and
file, and the Python and gerrychain versions. No district is tied; a tie would
refuse the count. The plotter checks its reading against the count on every draw,
under both contests, and refuses on any difference, if the record does not match
the draws and counts files it reads, or if a plan key names draws that differ.
None of these refuses, so every seat value behind the figure equals its count, and
no seat count, share or interval the repository has published moves. The Monte
Carlo intervals are unchanged in value and in meaning: they never included the
reading as a source of error, and their convergence caveats stand. The plan keys
do move published numbers: the distinct-plan counts in `docs/progress.md`, which
counted rows of metrics and called them a lower bound, and the two shares taken
over distinct plans, in four places there. A renumbered plan can leave two or
three rows. Those places now quote counted plans, and the D-043 section there says
what changed.

These are the same draws, counted, not new ones: each regenerated draw reproduces
its committed row. That is the author's reading of D-036, which names a re-run of
an experiment a new experiment, and of `prompt.md`'s "run each once": the sampler
is asked for exactly the committed draws and checked against them, and a draw that
differed would refuse the count rather than join it.

*The returns:* VEST's Iowa file, `ia_2020.zip`, as Harvard Dataverse served it on
2026-10-11: dataset doi:10.7910/DVN/K7760H, version 49.0, file 14304797, uploaded
2026-10-03, MD5 `500252facae6107b93128406ebf5177b`. The dataset's terms of use
state CC BY 4.0, with a no-warranty disclaimer; its structured licence field is
empty, and version 48, which `docs/CRITERIA.md` §9.1 records, carried the same
terms text, by the redistricting scientist and Pre-Submission Peer Reviewer
agents' reading of its Dataverse record. The file postdates the draws, and the
repository never recorded which version they were measured with. Three things tie
the count to the returns the draws were measured with:
- **The district totals.** Every |efficiency gap| and |mean-median|, under both
  contests, on every plan the chains visit, reproduces exactly. |Efficiency gap|
  alone could not show this: it is blind to an even number of votes moved between
  districts the same party wins, and to a trade of votes between the parties
  across two counties, wherever no district changes hands. |Mean-median| moved
  under both in the fifth audit's probes.
- **Which party is which.** Those metrics are unsigned, and would reproduce with
  the parties swapped, turning `s` seats into `4 − s`. The recount refuses unless
  each contest's statewide two-party totals equal the certified ones, 759,061 D
  and 897,672 R for president and 754,859 D and 864,997 R for Senate, and the
  plotter's reading is anchored on the same totals.
- **Version 48 against version 49.** The two files' attribute tables hold the same
  values in all 1,661 precinct rows, in the same order; two minor-candidate
  columns are renamed (`G20PREOFUE` to `G20PREADEL`, `G20USSOHER` to
  `G20USSIHER`). The `.shp` and `.shx` files differ, and version 49 adds a
  `.shp.xml`; `tools/prepare_data.py` sums precincts by their county attribute, so
  the county totals do not depend on them. Version 48's file is Dataverse file
  4789403, MD5 `f204468e6747db41f97573af1844a959`, created 2021-06-09. The
  redistricting scientist agent found this and the author checked it.

What this does not show is that the county totals are accurate. The code checks
only the statewide totals against the certified figures, and regenerated plans
have districts within 17 votes of a tie (fifth audit). The redistricting scientist
agent compared all 99 county totals with the Secretary of State's canvass under
both contests and found none different; the GIS QA Engineer has not confirmed it.

*Alternatives:*
- **Count only the draws read as 0 seats.** Verifying the 395 in the rectangle
  means regenerating 20,127 draws, and verifying all 832 committed ones, 55,159.
  Not chosen: the whole rectangle, 37% more than 20,127, would also check each
  draw's 1-or-2 reading, which the reading could get wrong without complaint, and
  every committed draw, as chosen, is 57,553: 2.9 times 20,127, and 4% more than
  55,159.
- **Keep the reading, and say on the figure that it is one.** Offered to the owner
  as a footer note. The owner asked whether counting would make it unnecessary
  ("the figure filter issue goes away if we verify the count?", the footer meant);
  it does, since the count confirms every reading.
- **Add a seats column to the draws file.** Rejected for D-039's reason: that file
  is the record of the measurement that was made (D-027). The counts sit beside
  it.

*Limits:* the recount needs the data and 25 to 30 minutes on an idle four-core
machine, so CI cannot run it; CI checks the committed counts and their record
instead. CI cannot tell a pair the recount wrote from one made some other way;
only rerunning the recount can.

Statements elsewhere say the returns carry no licence or cannot be redistributed.
Version 48's record, which `docs/CRITERIA.md` §9.1 cites, already stated CC BY 4.0
in its terms of use; only its licence field was empty. So §9.1's "the terms of
reuse are unstated" did not match that record when it was written, and the
statements that follow it are errors to correct, not statements made stale by the
owner's choice. Amending them is the owner's:
- `docs/CRITERIA.md` §9.1, which also records version 48.0 and Iowa's file date
  2021-06-09, and gives the missing licence as why no election data is committed;
- the README's licence section ("carry no declared licence at all") and its
  "Getting the data", which says the files sit behind a click-through a script
  cannot accept, though Dataverse serves them to a script;
- `CITATION.cff`, which says no licence is declared on the deposit;
- `.github/workflows/release.yml`, whose release notes, archived with every DOI,
  say the returns are not redistributable;
- the comments in `.github/workflows/tests.yml`, `tests/dataguard.py` and
  `tests/test_experiment_3_plans.py`;
- D-039 above, "the returns cannot be redistributed", unmerged;
- on `main`, as history: D-037 and `docs/progress.md`'s note on the suite.

The owner's choice covered committing per-draw seat counts and nothing else from
the file. Whether they need VEST's credit and a licence link under CC BY 4.0, and
whether they are election data under §9.1, are questions for the owner and the
election-law reader, to answer before this merges.

*Corrected in review:* the first version of this entry said reproducing
|efficiency gap| alone showed the returns give the draws' district totals, which
cannot fix which party is which; put the cost of counting every draw at 37% more
than the 0-seat recount, when 37% buys the rectangle; credited the Polsby-Popper
difference to the geometry library's rounding, when it came from running the
recount under Python 3.13, whose `sum` of floats is compensated; listed county
splits among the columns that confirm the regeneration; said the figure's bars are
counts; and named one owner's decision of two. The fifth agent audit in
`docs/first-result/INSTRUMENT-AUDIT.md` and the agent routing reviews showed each.
The second version called the licence statements stale, when version 48's own
record already stated CC BY 4.0, and its list of them was incomplete; the
Pre-Submission Peer Reviewer agent's second review showed both.

## D-044 — The seat counts carry VEST's credit and its licence link

**Date:** 2026-10-12 · **Phase:** post-release

D-043 left two questions for the owner, to answer before merge: whether the
committed seat counts need VEST's credit and a licence link under CC BY 4.0, and
whether they are election data under `docs/CRITERIA.md` §9.1. It also asked the
owner to confirm the decisions D-042 and D-043 quote.

*Chosen, by the owner,* on 2026-10-12, in conversation with the author: "Commit
the seat counts with a VEST credit and license link. I confirm the decisions." So
the counts are committed as material adapted from VEST's dataset, which VEST
licenses under CC BY 4.0, and the four decisions D-042 and D-043 quote stand as
recorded there. The author carried the credit and the link to where the counts
and what is drawn from them are read:

- `docs/first-result/ATTRIBUTION.md` gives VEST's citation, a link to version
  49, the licence and its link, where VEST states the licence, what was changed
  (the precinct returns summed to counties, then seats counted per draw; no vote
  count kept), where VEST describes its own processing, the counts' columns, and
  VEST's disclaimer of warranties;
- the recount's record, `docs/first-result/ia-seats-v2.json`, carries the
  citation, the licence (`CC-BY-4.0`) and its link, and a pointer to that notice,
  in `returns_source`;
- the first-result figure's footer ends with VEST's credit, the dataset's DOI,
  and the licence and its link, because the figure travels without the README or
  the notice, and the plotter refuses a record that does not name the dataset the
  footer credits;
- the README's licence section names VEST's licence, the counts as adapted from
  VEST's data, and the notice, where it said the returns carry no declared
  licence. It also says the counts' own licence is undecided, and that other
  committed files hold metrics computed from the same returns without a credit.

The recount's write step wrote the record twice for this entry, from the
committed counts, without regenerating the draws: a short script read the counts
file back into the form a run produces, gave every chain the float differences
the last full run recorded (all 0.0), and called `write` with `provenance()`
taken then. Three full runs have written the counts byte for byte the same, and
the credit changes nothing they measure; the counts file came out byte for byte
the same both times, and the record changed only in `returns_source`. The script
has no option that does this, so the steps are recorded here, and
`tests/test_recount_seats.py` holds every field of the committed record that the
write step takes from a constant, `returns_source` among them, to the script's
constants.

*Alternatives:* committing the counts without a credit, or withdrawing them so
that only the reading stands. The owner chose neither.

*Still the owner's to amend*, as statements that say the returns carry no
licence, cannot be redistributed, or cannot be fetched by a script, though
Dataverse serves them to one:
- `docs/CRITERIA.md`: §9.1, which says no licence is declared, records version
  48.0, and gives the missing licence as why no election data is committed; its
  Sources entry for VEST, "no licence declared"; and its table of sources, which
  says the returns cannot be fetched by script;
- the README's "Getting the data" and `tools/fetch_raw.sh`, which send the reader
  to download the returns by hand behind a click-through;
- `CITATION.cff`, which says no licence is declared on the deposit and names no
  version;
- `.github/workflows/release.yml`, whose release notes, archived with every DOI,
  say the returns are not redistributable;
- the comments in `.github/workflows/tests.yml`, `tests/dataguard.py` and
  `tests/test_experiment_3_plans.py`;
- D-039 above, "the returns cannot be redistributed", unmerged;
- on `main`, as history: D-037, D-038 and `docs/progress.md`'s note on the suite.

*Open, for the owner, with counsel where the question is one of law:*
- which licence, if any, the repository offers the counts under. The README says
  Apache 2.0 covers the repository's code and documentation, and the counts sit
  under `docs/`;
- whether the other committed files that hold metrics computed from VEST's
  returns need the same credit: the experiments' draws files, results and
  figures, the Phase 2 report, and the PlanScore cross-check;
- D-043's second question, whether the counts are election data under §9.1,
  which the owner's answer did not address;
- whether the figure's footer is notice enough for a figure that travels alone;
- whether this branch's earlier commits, which carry the counts without the
  notice and which a merge commit brings into `main`'s history (D-042), need
  anything.

*Corrected in review:* the first version of this entry left `docs/CRITERIA.md`'s
Sources entry and table of sources, `tools/fetch_raw.sh` and D-038 out of its
list, did not name the questions the owner's answer leaves open, and described
the README as naming "the adapted file", as if no other committed file held
values computed from VEST's returns. The Scientific Data Steward agent's review
showed each.
