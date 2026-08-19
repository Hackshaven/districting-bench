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
