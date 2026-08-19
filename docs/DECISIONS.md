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
