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
published 2020 apportionment population exactly.

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
queen graph has 294 edges to rook's 222. **32% of queen edges are single-point
contacts.** Treating a corner as a connection is a substantive choice, not a
technicality — it lets a district pass through a point of zero width.

*Chosen:* rook. Two counties are adjacent only if they share a boundary of
positive length.

*Evidence this is safe:* all four enacted districts are connected under rook. The
real map does not rely on corner adjacency, so excluding it does not exclude the
plan under review.

*Note:* the Census County Adjacency File is queen-based — its 294 Iowa–Iowa pairs
match our queen graph exactly, in both directions. Anyone using that file as an
adjacency source is silently getting queen.

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

*Open question for the human:* three of the four gaps are fixable by adding
denylist patterns, which is a config change and therefore a human decision. The
fourth (reading a partisan file by filename, with no column reference in the
source) is not reachable by static analysis of `src/` at all and needs a
different mechanism.
