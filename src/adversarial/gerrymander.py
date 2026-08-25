"""Seat-maximising plan construction, subject to every legal constraint.

This module manufactures ground truth. A plan that comes out of here is a
gerrymander *because it was built to be one*, and its magnitude is known: the
realised seat count is measured by ``evaluate.partisan.seat_count``, never
merely intended. That is the whole reason detection is optimisable at all —
docs/ARCHITECTURE.md section 6, docs/CRITERIA.md section 8.

What "legal" means here is Iowa Code ch. 42 plus the federal floor, in the
statutory order (CRITERIA.md section 2.1):

1. **population equality** — every district within ``epsilon`` of ideal. As in
   ``generate.ensemble``, ``epsilon`` bounds each *district's* deviation, not the
   max-min spread, so the permitted spread is up to ``2 * epsilon * ideal``
   (docs/FEASIBILITY.md section 5.2 corrects a reading that conflated the two).
2. **contiguity** — every district connected on the rook graph.
3. **whole counties** — automatic: the units *are* counties, so a plan cannot
   split one. County splits are identically zero for Iowa congressional
   (FEASIBILITY.md section 5.3), which is also why they carry no detection signal.
4. **compactness** — constrained, since round 3, by an injected
   :class:`ShapeEnvelope`. The previous version of this docstring said the
   opposite: "measured elsewhere, never constrained here ... the resulting
   compactness is a *symptom* for the detector to find". Round 2 measured what
   that produced and it was not a symptom, it was a signature. Every planted
   plan had ~2x the cut edges and ~1/3 the Polsby-Popper of every neutral map,
   with no overlap, so ``cut_edges > 60`` alone scored TPR 1.0 and FPR 0.0 while
   knowing nothing about partisanship. A gerrymander a compactness screen
   catches is not the adversary this system exists to detect
   (docs/DECISIONS.md D-010). See "The shape envelope" below.

Every one of those is checked on the returned plan by :func:`check_legality`,
which also calls ``evaluate.plan.validate`` as the authority on the structural
invariants, and :func:`maximize_seats` refuses to return a plan whose record does
not pass. Asserted, not assumed.

The shape envelope
------------------

There are two constructions and they are not interchangeable. Both are
calibrated from the neutral ensemble rather than from a hand-picked constant, so
"inside the envelope" means what the detector means by "not an outlier"; they
differ in what they are calibrated *to*.

:func:`calibrate_shape_envelope` returns the **central ``coverage`` band** of the
reference's own distribution on five non-partisan measures (cut edges,
Polsby-Popper, Reock, Schwartzberg, convex hull). It is a feasible set.

:func:`envelope_around_plan` — and :func:`envelope_from_measurements`, which is
the same bound built from columns a caller has already measured — returns bounds
**anchored on one neutral draw**, ``target +/- width * IQR`` per measure. It is a
match to a particular plan.

Passing either to :func:`maximize_seats` confines the search: two of the five
measures are maintained exactly and incrementally so they can be enforced on
every accepted move, and all five are re-measured through
``evaluate.compactness`` on the finished plan before it is returned.

**The band does not work and the reason is structural, not a matter of its
width.** Inside a band the seat objective is very nearly monotone in raggedness,
because raggedness is what buys seats, so every planted plan ends up against the
band's upper edge: the planted marginal becomes a point mass at the ceiling of
the neutral one rather than a sample of it. Tightening the band moves the
ceiling without changing that, which is what round 3's frontier measured — yield
fell 32/32 to 0/24 while separability never reached 0.5 (docs/progress.md). An
independent measurement of the shipped round-3 path, by an agent that saw none of
the implementation, put it at **AUC 0.890**.

Anchoring on a draw cannot be empty (the draw is in it) and gives the planted
plans the reference's own spread. Since round 4 that is what ``detect.bench``
ships, one envelope per plant, the anchor drawn uniformly over reference *draws*
before the search runs.

Measured for round 4 on a 1,664-draw ReCom reference (8 chains x 250 at
epsilon=2e-4, 369 distinct, 2 chain failures), planting 1-, 2- and 3-seat shifts
in both directions at 40,000 iterations x 4 restarts. "AUC" separates the 18
planted plans from the 1,664 neutral draws using **only** the five non-partisan
measures; 0.5 is indistinguishable, 1.0 is a compactness screen that works
perfectly:

============================ ================================= ==============
Iowa, matched at width 0.5    per measure                        joint
                                                                 (Mahalanobis)
============================ ================================= ==============
cut edges                     0.622                              **0.489**
Polsby-Popper                 0.422                              95% CI
Reock                         0.476                              0.356-0.622
Schwartzberg                  0.577
convex hull                   0.406
============================ ================================= ==============

The joint interval covers 0.5 and the worst single measure is 0.62. The band
was re-measured beside it on the *same* reference, budget and seeds, so the
comparison is like-for-like rather than against round 3's differently-sized run:

=========================== =========== =========== =========== ===========
same reference, same seeds   Iowa band   Iowa        Colorado    Colorado
                                         matched     band        matched
=========================== =========== =========== =========== ===========
cut edges                    **0.880**   0.622       **0.939**   0.761
Polsby-Popper                0.214       0.422       0.282       0.385
Reock                        0.282       0.476       0.695       0.338
Schwartzberg                 0.800       0.577       0.798       0.640
convex hull                  0.245       0.406       0.395       0.475
joint (Mahalanobis)          0.696       **0.489**   0.569       **0.529**
plants reached               21 of 48    18 of 48    4 of 24     8 of 24
=========================== =========== =========== =========== ===========

On Iowa the matched envelope costs 3 plants of 48 and takes the best single
screen from 0.88 to 0.62. **On Colorado it costs nothing at all** — it doubles
the yield, 8 of 24 against 4 of 24, while taking the best screen from 0.94 to
0.76 — because a band that must hold on five correlated measures at once is a
much smaller feasible set than an envelope around a plan that is already in it.
The band's Iowa figure here, 0.88 on cut edges, is the same finding an
independent measurement reported as 0.890 for the round-3 shipped path. **Yield is what it costs**, and
it is reported rather than traded away: of 8 attempts per cell, D +1 3, D +2 6,
D +3 **0**; R +1 6, R +2 3, R +3 **0** (R measured from the ensemble's most
Democratic draw, which is the only baseline giving R headroom in Iowa).

**The obvious way this construction could still leak, checked.** Only 18 of 48
attempts reached their magnitude, so the planted set is anchored on a *surviving*
subset of the reference — and if the search only succeeded from unusually ragged
anchors, the anchoring would be laundering the same bias through a different
door. Comparing the 18 surviving anchors against all 1,664 reference draws on
the five measures gives AUC 0.523, 0.494, 0.451, 0.499, 0.443 and a joint 0.537,
every 95% interval covering 0.5. The anchors that worked are shape-typical, so
the yield is not buying separability back.

**The 3-seat magnitude is out of reach inside a matched envelope on Iowa, and
that is the finding, not a reason to loosen the envelope.** Three D seats is
Iowa's arithmetic ceiling and the plan is razor thin — three districts at 50.17%,
50.07% and 50.12% — so the legal region around it is tiny, and the unconstrained
search needs roughly 200,000 iterations x 12 restarts to find it at all, at 84
cut edges against a neutral range of 39-64. D-013 states Iowa's detection gate at
a 3-seat magnitude because the neutral seat distribution spans 2. So on Iowa the
only magnitude the gate can be stated at is one this adversary cannot reach while
staying shape-typical. Note what that is and is not: it is a statement about this
search at this budget in this state, **not** a proof that no such plan exists.
Round 3 made exactly that inference from a yield of 0/24 and had to retract it,
because the neutral sampler had been producing counterexamples in the same
artifact all along.

Colorado: the same instrument, a second geography
-------------------------------------------------

The envelope was calibrated on Iowa's 99 counties, so nothing above transfers
until it is re-measured. Round 4 measured it on Colorado — 3,108 VTDs, 8
districts, epsilon=1e-2 — against a 720-draw reference (6 chains x 120, 708
distinct, no chain failures), 4 replicates per cell, same 40,000 x 4 budget:

=========================== ============= ======================= ===========
measure                      Iowa (n=18)   Colorado, all (n=8)     Colorado at
                                                                   3 seats (4)
=========================== ============= ======================= ===========
cut edges                    0.622         **0.761** (0.57-0.96)   0.663
Polsby-Popper                0.422         0.385                   0.509
Reock                        0.476         0.338                   0.424
Schwartzberg                 0.577         0.640                   0.554
convex hull                  0.406         0.475                   0.535
joint (Mahalanobis)          **0.489**     **0.529** (0.33-0.73)   **0.332**
=========================== ============= ======================= ===========

Yield, 4 attempts per cell: D +1 **1**, D +2 0, D +3 0; R +1 1, R +2 2, R +3
**4 of 4**. Two things in that row are worth more than the AUCs.

* **Colorado's gate magnitude is reachable and Iowa's is not.** D-013 states both
  states' gates at 3 seats, and on Colorado the search plants a 3-seat shift on
  every attempt while staying shape-typical — the joint AUC on those four plans
  is 0.332 (95% CI 0.100-0.563) and no single measure's interval excludes 0.5.
  This is the first round in which ground truth exists at the magnitude the gate
  is stated at.
* **The easy direction is R, and that is geography.** A 3-seat R shift means
  packing Democrats out of three districts, and Democratic votes in Colorado are
  already concentrated in Denver and Boulder; going the other way — 6, 7 or 8 D
  seats of 8 — means spreading them, which this search reached once in twelve
  attempts. A generator whose yield is that asymmetric produces a confusion
  matrix dominated by one direction, and the direction is reported per case
  rather than pooled.

**The residual leak, and exactly where it comes from.** Colorado's cut-edge AUC
is 0.761 and its 95% interval does not cover 0.5, so a cut-edge screen still has
signal there. Measuring each plant's position inside *its own* envelope, in
units of the half-width, says why: on Colorado the plants sit at +0.96 of the
cut-edge ceiling on average (min +0.91, max +0.99), and on Iowa at +0.41. The
seat objective is still monotone in raggedness, so the search still runs to a
ceiling — anchoring moved the ceiling from a fixed quantile of the ensemble to a
per-plant one, which is what turns a point mass into a distribution, but it does
not remove the offset. The size of the residual is therefore
``width * IQR * (fraction of ceiling reached)``, and Colorado's cut-edge IQR is
103.5 edges against Iowa's 6.0 — the same construction leaks about seventeen
times more absolute raggedness on the larger graph.

That is a measurement and not a knob. Reducing :data:`DEFAULT_MATCH_WIDTH` would
shrink the residual and the yield together, and choosing it by which value makes
the acceptance test pass is precisely the move this project does not make. The
construction that would remove the offset without touching the width — bounding
each measure on the side the search runs toward, so the ceiling *is* the anchor's
own value — is a change of instrument rather than of a threshold, and it belongs
in a round that can measure it independently rather than in this one's report.

At 2 seats the classes genuinely overlap on the partisan metrics too. 43% of
Iowa's neutral draws already give the Democrats two seats, and conditioned on
that outcome the plants are indistinguishable from the neutral draws that also
win two: AUC 0.53 on efficiency gap, 0.57 on mean-median, at efficiency-gap
percentiles 0.16-0.94 of the full reference, nowhere near a 0.99 tail. **No
percentile-tail detector can reach TPR 0.95 at a 2-seat shift in Iowa**, and that
is a fact about the state and the magnitude rather than a defect in any rule.

Baselines: a shift is a difference, so say what from
----------------------------------------------------

Every result carries ``baseline_source``, and :func:`achievable_seats` measures
both directions from one baseline and marks the pair ``comparable``. Round 2 did
not: its D-direction shifts were measured from the enacted plan and its
R-direction shifts from the single most Democratic-favouring draw of a 14-plan
reference, and the two were pooled into one gate. See the table in
:func:`achievable_seats` for what the choice is worth on Iowa — a 2-seat R shift
exists only from a baseline that already gives the Democrats two of four seats.

Iowa is hard for this, and the honest number goes in the result
------------------------------------------------------------

Iowa 2020 is R+8.4 statewide (two-party D share 0.4582) and the enacted plan is
already 4R-0D. A *Republican* gerrymander therefore has no headroom at all: you
cannot win more than 4 of 4, and the neutral map already does. Measured on the
99-county rook graph at k=4, epsilon=2e-4, against the enacted plan as baseline:

============ ========= ============= =====================================
target       ceiling   seat shift    effort to reach it
============ ========= ============= =====================================
R            4 of 4    **0**         every seed tried, seconds
D            3 of 4    **+3**        ~200,000 iterations x 12 restarts
D            2 of 4    +2            every seed tried, seconds
============ ========= ============= =====================================

Two things make those numbers claims rather than guesses:

* **4 D seats is arithmetically impossible, not merely unfound.** Winning a
  district takes more than half its two-party votes, so winning all four takes
  more than half the statewide two-party total — 828,367 votes. The Democrats
  cast 759,061. Three is therefore the true ceiling and the search reaches it.
* **The R shift is zero by definition of the ceiling**, since the baseline is
  already at it. No amount of search moves it, and the gate at a 2-seat shift
  (CRITERIA.md section 8) simply cannot be exercised in the R direction in this
  state. That is a finding about Iowa, not a defect in the search.

The 3-seat D plan is razor thin — three districts at 50.17%, 50.07% and 50.12%
D against one packed at 32.7% — which is why it takes an order of magnitude more
search than the 2-seat one: the legal region around it is tiny. The default
settings here are the cheap ones, so ``maximize_seats`` at its defaults usually
returns the 2-seat plan; ``seat_ceiling_at_work_epsilon`` on the result says
when the search saw a better seat structure and could not legalise it, and
:func:`achievable_seats` measures the range rather than asserting it.

For calibration against the neutral baseline: a ReCom ensemble at the same
epsilon gives the Democrats 2 seats in 45% of draws and has a median of 1 (see
``nulls.py``). A 2-seat "gerrymander" is therefore *not* distinguishable from a
neutral map by seat count alone in Iowa. Only the 3-seat plan sits outside the
neutral ensemble's support entirely.

Method
------

Local search over boundary-county reassignments — the neighbourhood
docs/FEASIBILITY.md section 5.3 found sufficient to beat the enacted plan's
population equality in seconds. Three phases per restart, all seeded:

* **balance** — greedy best-improvement descent on population, from a random
  seeded growth plan, into a loose *working* band (``work_epsilon``). Population
  and adjacency only.
* **seats** — simulated annealing on a seat objective, hard-constrained to stay
  inside the working band. The objective is the realised seat count plus a
  sigmoid relaxation of it, which is what makes cracking and packing appear:
  the sigmoid saturates, so pushing an already-lost district from 0.35 to 0.30
  costs almost nothing while lifting a district from 0.48 to 0.52 pays. Several
  plans are kept *at each seat level*, because planting a 1-seat shift needs a
  1-seat plan rather than a truncated 2-seat one, and because the next phase
  can fail on a given plan and need another at the same level.
* **repair** — tighten from the working band to the real ``epsilon`` while
  holding the seat count, by best-improvement descent over single moves and
  boundary *swaps*, with random kicks on stalling. Swaps are what make the tight
  band reachable at all: the smallest county is 3,704 persons, so a single move
  cannot land inside a +/-159-person band, whereas exchanging two counties of
  similar size moves a district by their difference.

A working band is needed because the tight band and the county granularity are
incompatible for single moves; optimising seats directly at ``epsilon`` finds
almost no legal states to move between.

The population bound is a constraint, not a score — and the Colorado scare
--------------------------------------------------------------------------

Round 4's first Colorado run reported ``legal_compliance = 0.25`` and the
obvious reading was that this search had walked off its population bound at VTD
scale. Measured, it had not. All three planted plans in that run were legal at
the operating epsilon; the nine illegal cases were **neutral ReCom draws** made
at ``--quick``'s looser epsilon and read at the operating one. On Iowa's quick
runs the same gate reads 0.00 to 0.083 and planted plans *are* among the
failures, so Colorado was the better-behaved state, not the worse one.

The bound is hard here and it is hard in one place: ``_repair`` records a
candidate only when its excess over the band is exactly zero, so it returns
``None`` rather than the best plan it saw, and ``maximize_seats`` re-checks the
winner through :func:`check_legality` and raises rather than return it. The one
place the bound used to be soft was the **baseline** a magnitude is measured
from: :func:`plant_gerrymander` built its own neutral reference and never
checked it, so a shift could be measured from a plan that was not a lawful
districting. It now refuses.

The deviation trajectory through one Colorado plant (D +1, 3,108 VTDs, k=8,
epsilon=1e-2, ideal 721,714, baseline the enacted plan):

============================== ================== =====================
stage                           max |dev| / ideal   spread (persons)
============================== ================== =====================
start plan (balance phase)      2.4e-06             3
end of seat phase (band 0.10)   0.0618              86,889
after repair                    1.0e-06             **1**
--- for comparison ---
enacted plan, as whole VTDs     0.00857             9,995
epsilon=1e-2 permits            0.01                up to 14,434
============================== ================== =====================

The search walks off the bound on purpose, into the working band, and walks
back. **What it walks back to is 8,000 times tighter than Colorado's operating
epsilon and 10,000 times tighter than the enacted plan's own VTD
approximation.** So on Colorado the population constraint is not binding on this
adversary at any magnitude: epsilon=1e-2 is a concession to representing the
*enacted* plan in whole VTDs (docs/DECISIONS.md D-015), and the adversary never
comes near it. Any Colorado result about what a gerrymander can achieve "inside
the legal population bound" is really a result about the other constraints.

The frontier, and the counterexample sitting next to it
-------------------------------------------------------

Colorado, epsilon=1e-2, baseline the enacted plan as whole VTDs (5D-3R), 12,000
iterations x 3 restarts, **no shape envelope** — so these are an upper bound on
what a shape-matched adversary could reach, not the bench's own yield:

========== ========= =============== ============ ======================
direction   asked     reached          spread       max |dev| / ideal
========== ========= =============== ============ ======================
D           +1        yes, 6D-2R       1 person     1.04e-06
D           +2        yes, 7D-1R       1 person     1.04e-06
D           +3        no (8 of 8)      --           --
R           +1..+3    no               --           --
open-ended  D         **7 of 8**       1 person     1.04e-06
open-ended  R         **3 of 8**       1 person     1.04e-06
========== ========= =============== ============ ======================

Every plan that reached its magnitude came back at a **one-person spread**. The
bound permits 14,434. It is not the constraint; it was never the constraint.

The open-ended R run reproduces Iowa's finding in a state chosen because Iowa's
version of it was thought to be an Iowa problem: the R ceiling *is* the enacted
plan's own R count, so the achievable R shift is zero, and
``seat_ceiling_at_work_epsilon`` is 3 as well — the seat phase never saw a
four-R structure even inside the 10% working band, in 74,911 evaluated moves.

**And that is where this stops being a claim about Colorado.** Four R seats
means four D seats, and the neutral ReCom ensemble at the same epsilon produces
four-D plans in 83 of 720 draws (11.5%, docs/progress.md). Legal plans at the
magnitude the R search could not reach exist, in this project, in the same
artifact. So the right reading of "R +1 not reached" is *this search, at this
budget, from this baseline, failed* — not that the feasible set is empty. Round
3 made exactly the opposite inference from a yield of zero and had to retract
it; the difference here is that the counterexample was looked for.

The 8-of-8 D case has no such counterexample and is not claimed either way:
Colorado is 56.9% D two-party, so eight majority-D districts are not
arithmetically excluded, and the search's seventh seat already sits at 50.03%.

Getting there needed a fix, and the fix is a scale story
--------------------------------------------------------

Before round 4 the balance phase could not reach the working band on Colorado at
all: growth plans start at 0.52-0.54 of ideal and the descent stalled at 0.166,
0.485 and 0.491 on three seeds. A start outside the working band freezes the
seat phase completely — it accepts a move only into a state with zero excess —
so ``maximize_seats`` ran its whole budget without moving and then blamed the
iteration budget in its exhaustion message. The cause was an absolute probe cap
of 60 sized on Iowa's 99 counties; see :func:`_descend_population` for the
measurement and the table. Nothing in the shipped bench path hit it, because the
bench supplies ``start_plans`` from the neutral ensemble, which is exactly the
kind of accident that hides a broken default until someone calls it.

Firewall
--------

``adversarial`` may import ``evaluate`` and nothing else from ``src/``
(tools/firewall.yaml). In particular it does **not** import ``generate``: the
starting plans here are built locally from population and adjacency. That
duplication is deliberate (ARCHITECTURE section 1) — these are not neutral
ensemble draws and must not be mistaken for them. Nothing in this module is a
sampler; it is a search, it is biased on purpose, and its output is only ever a
positive case for the detector.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from evaluate.compactness import all_metrics, cut_edges, district_geometries
from evaluate.partisan import district_shares, seat_counts
from evaluate.plan import Plan, districts, validate

__all__ = [
    "SearchExhausted",
    "LegalityRecord",
    "GerrymanderResult",
    "ShapeEnvelope",
    "check_legality",
    "maximize_seats",
    "plant_gerrymander",
    "achievable_seats",
    "calibrate_shape_envelope",
    "envelope_around_plan",
    "envelope_from_measurements",
    "shape_metrics",
    "PARTIES",
    "ENVELOPE_MEASURES",
    "IN_LOOP_MEASURES",
    "DEFAULT_SHAPE_COVERAGE",
    "DEFAULT_MATCH_WIDTH",
]

PARTIES = ("D", "R")

# Search defaults, measured on the Iowa 99-county graph at k=4, epsilon=2e-4.
# They reach the R ceiling (4 seats) on every seed tried and 2 of the 3
# available D seats in a few seconds. The third D seat needs roughly
# max_iterations=200_000 and restarts=12 — see the module docstring; the default
# is the cheap setting, not the exhaustive one, and the result says which
# ceiling it reached rather than implying it is the ceiling.
DEFAULT_MAX_ITERATIONS = 60_000
DEFAULT_RESTARTS = 6
DEFAULT_WORK_EPSILON = 0.10
DEFAULT_REPAIR_ROUNDS = 60
#: Distinct plans kept per seat level by the seat phase, each of which the
#: repair phase may try. See _anneal_seats on why one is not enough.
DEFAULT_KEEP_PER_LEVEL = 6
DEFAULT_SIGMOID = 0.03
DEFAULT_SURROGATE_WEIGHT = 0.5

# --- the population descent's two budgets, and why one of them is a fraction --
#
# Both were absolute constants until round 4, and both were sized on Iowa's
# 99-county graph. Measured on Colorado's 3,108 VTDs they made the descent
# report a local minimum that was not one, which is the whole of the Colorado
# failure described in _descend_population's docstring.
#
# DEFAULT_DESCENT_PROBES is the floor. DEFAULT_DESCENT_PROBE_FRACTION is what
# makes the cap scale: the candidate list grows with the boundary, and the
# fraction of its head that a fixed 60 covers shrinks as the graph grows. On
# Iowa the *cap* never moves (5% of ~267 candidates is 13, below the floor of
# 60), so no Iowa result changes because of it; on Colorado 5% of ~28,000 is
# ~1,400, and the first connectivity-legal improving move measured at the stall
# sat at rank 66-72.
DEFAULT_DESCENT_PROBES = 60
DEFAULT_DESCENT_PROBE_FRACTION = 0.05
# How many moves one candidate enumeration may be reused for. Enumerating costs
# 79.8 ms on Colorado against 0.5 ms on Iowa -- 26,848 of Colorado's 27,835
# candidates are boundary swaps, which is O(|boundary|^2) -- while a single
# probe costs 0.33 ms. Rebuilding the list for every move is what made a
# working descent unaffordable rather than merely slow: measured, 46-196 s per
# call against 5-11 s when the list is reused. Each candidate's cost is
# repriced against the live district totals, and rechecked against the live
# plan, before it is applied -- see _live_cost, which is not optional.
#
# **This one does change Iowa's trajectory, and that is stated rather than
# glossed.** Reuse alters which intermediate plans the descent visits, so the
# same seed no longer produces the same plan as round 3: on 20 Iowa growth
# seeds, 0 of 20 land on an identical plan. What it does not change is the
# answer. Median deviation reached is 0.0019 against 0.00206, the count landing
# inside the working band goes *up* (19 of 20 against 16 of 20), the median call
# costs 6.0 ms against 11.3 ms, and every Iowa figure asserted in
# tests/test_adversarial.py -- the D ceiling of 2, the R ceiling of 4, the
# reachable 3-seat plan, the spreads inside the band -- is unchanged.
# Reproducibility within a version is intact (same seed, same code, same plan);
# reproducibility *across* this version boundary is not, and a reader comparing
# a round-3 artifact to a round-4 one on plan identity will see differences that
# are this constant and not a finding.
DEFAULT_DESCENT_MOVES_PER_PASS = 400

# Seed derivation domain. `generate.seeds.derive` does the same job on the other
# side of the firewall; this package may not import it, and re-deriving here is
# the deliberate duplication ARCHITECTURE section 1 requires rather than an
# oversight. The domain string differs so the two never produce the same stream.
_SEED_DOMAIN = b"districting-bench/adversarial/gerrymander/v1"


class SearchExhausted(RuntimeError):
    """No plan satisfying every legal constraint was found within the budget.

    This is a statement about the search, not a proof of infeasibility. It is
    raised rather than returning a plan that fails a constraint, and
    :func:`plant_gerrymander` converts it into ``None``.
    """


# --------------------------------------------------------------------------- #
# the shape envelope (docs/DECISIONS.md D-010)
# --------------------------------------------------------------------------- #

#: The measures the envelope bounds. Deliberately the same five non-partisan
#: metrics the acceptance test's classifier is allowed to use: if the search is
#: constrained on exactly the metrics an adversary would be screened on, the
#: constraint cannot be satisfied by hiding in a measure nobody bounded.
ENVELOPE_MEASURES: tuple[str, ...] = (
    "cut_edges",
    "polsby_popper_mean",
    "reock_mean",
    "schwartzberg_mean",
    "convex_hull_mean",
)

#: The two the search enforces on *every accepted move*, because both are exact
#: and O(degree) to maintain incrementally: cut edges from the graph alone, and
#: Polsby-Popper from precomputed unit areas, unit perimeters and shared
#: boundary lengths (a dissolved district's perimeter is the sum of its units'
#: perimeters less twice the boundaries interior to it -- verified against
#: ``evaluate.compactness.polsby_popper`` at a worst relative error of 6e-15
#: over 40 real ensemble plans). Reock and convex hull need a bounding circle
#: and a hull; neither survives an incremental update, so they are checked once
#: on the finished plan by :func:`shape_metrics`, which is the authority.
#: Schwartzberg is ``1/sqrt(polsby_popper)`` per district and so is bounded
#: already, up to the difference between a mean of a function and a function of
#: a mean; it too is re-checked at the end.
IN_LOOP_MEASURES: tuple[str, ...] = ("cut_edges", "polsby_popper_mean")

#: The envelope constructions this module knows how to describe. See
#: :class:`ShapeEnvelope` for what each one's numeric fields mean; the point of
#: naming them is that round 3 had one field standing for three different
#: quantities and rendered all three with the same sentence.
KINDS: tuple[str, ...] = ("central_band", "matched", "one_sided_floor")

#: **VALUE.** How much of the neutral ensemble's own compactness distribution
#: the adversary is confined to, as a central interval: at 0.90 a planted plan
#: must sit between the 5th and the 95th percentile of the neutral ensemble on
#: every bounded measure.
#:
#: Three choices are packed in here and each is arguable.
#:
#: 1. *That the bound is calibrated from the ensemble at all* rather than from a
#:    constant. A constant would be a number nobody can defend; a quantile of
#:    the reference distribution is the same object the detector compares plans
#:    against, so "inside the envelope" means "not an outlier on shape", which
#:    is exactly the claim D-010 makes.
#: 2. *That it is two-sided.* The obvious reading of D-010 is a ceiling on
#:    raggedness. But a plan far *more* compact than any neutral draw is just as
#:    easy to pick out of a percentile-tail rule, and a one-sided bound leaves
#:    the adversary free to be conspicuous in the compact direction. Both tails
#:    are closed.
#: 3. *That the default is 0.90 rather than 1.0.* Bounding by the observed
#:    min/max (coverage 1.0) admits the single most ragged draw the sampler ever
#:    produced, and a planted set piled against that edge is separable at AUC
#:    0.96 on cut edges alone. 0.90 leaves a 10% two-sided tail, which is the
#:    same order as the 0.99 percentile rule the detector runs.
#:
#: **A band at this coverage is not on its own enough, and the measurement says
#: so:** at 0.90 the planted plans still land at 50-52 cut edges inside a
#: [40, 52] band whose reference median is 44, and a cut-edge classifier
#: separates them at AUC 0.84. Reaching AUC 0.5 needs
#: :func:`envelope_around_plan`, which anchors the bounds on one neutral draw
#: instead of on a quantile of all of them. This constant is the band's default,
#: not a claim that the band suffices; the frontier over it is in the module
#: docstring.
DEFAULT_SHAPE_COVERAGE = 0.90


@dataclass(frozen=True)
class ShapeEnvelope:
    """Non-partisan shape bounds, calibrated from a neutral ensemble.

    This is the feasible set the seat-maximising search is confined to. It
    exists because of what round 2 measured: every planted plan had roughly
    twice the cut edges and a third the Polsby-Popper of every neutral map, so
    ``cut_edges > 60`` alone scored TPR 1.0 and FPR 0.0 while knowing nothing
    about partisanship. Ground truth separable on the generator's fingerprint is
    not ground truth about gerrymandering (docs/DECISIONS.md D-010).

    ``bounds`` maps a measure name to an inclusive ``(low, high)`` pair. A
    measure the calibration could not compute -- the four shape measures need
    geometry -- is simply absent, and :meth:`violations` says so rather than
    passing it silently.

    **``kind`` says what construction produced the bounds, and no field means
    anything without it.** Round 3 shipped one numeric field, ``coverage``, and
    used it for three incompatible quantities: the width of a central quantile
    band, the half-width in interquartile ranges of an envelope anchored on one
    draw, and the constant 1.0 standing for a one-sided floor at the observed
    extreme. ``check_legality`` then rendered all three as "the central N% of
    the reference", which was true of one of them. The kinds are now named, each
    carries only the parameter that applies to it, and :attr:`description` is the
    one place a human-readable rendering is produced:

    ``central_band``
        ``[q(centre - coverage/2), q(centre + coverage/2)]`` per measure over
        the reference. ``coverage`` and ``centre`` apply; ``width`` does not.
        Built by :func:`calibrate_shape_envelope`.
    ``matched``
        ``target +/- width * IQR`` per measure, anchored on **one** reference
        draw. ``width`` applies; ``coverage`` and ``centre`` do not, and
        ``coverage`` is ``None`` — an envelope around one draw covers no stated
        fraction of anything, and saying 0.5 was a category error, not a
        rounding one. Built by :func:`envelope_around_plan` or
        :func:`envelope_from_measurements`.
    ``one_sided_floor``
        A half-open bound per measure at the reference's own extreme, in the
        direction ``evaluate.compactness.DIRECTION`` says is less compact. No
        width parameter applies. Built by ``detect.bench.compactness_floor``.

    The remaining provenance fields are here so a reader of
    ``bench-results.json`` can tell a bound calibrated on 2,217 distinct plans
    from one calibrated on fourteen.
    """

    coverage: float | None
    bounds: dict[str, tuple[float, float]]
    reference_plans: int
    reference_draws: int
    measures: tuple[str, ...]
    source: str
    centre: float = 0.5
    kind: str = "central_band"
    width: float | None = None
    #: For a ``matched`` envelope: the anchor draw's own measurements, so a
    #: reader can see how far the planted plan moved from the neutral draw it
    #: was matched to without re-deriving the midpoint of every bound.
    anchor: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown envelope kind {self.kind!r}; known: {KINDS}")
        if self.kind == "central_band":
            if self.coverage is None or not 0 < self.coverage <= 1:
                raise ValueError(
                    f"a central_band envelope needs a coverage in (0, 1]; got "
                    f"{self.coverage!r}"
                )
            if self.width is not None:
                raise ValueError("width does not apply to a central_band envelope")
        else:
            if self.coverage is not None:
                raise ValueError(
                    f"coverage does not apply to a {self.kind} envelope; it is "
                    "not a fraction of the reference distribution. Round 3 "
                    "overloaded this field and check_legality mislabelled every "
                    "envelope that was not a band"
                )
            if self.kind == "matched" and not (self.width and self.width > 0):
                raise ValueError(
                    f"a matched envelope needs a positive width in IQRs; got "
                    f"{self.width!r}"
                )
            if self.kind == "one_sided_floor" and self.width is not None:
                raise ValueError("width does not apply to a one_sided_floor envelope")

    @property
    def description(self) -> str:
        """What these bounds *are*, in words. The only rendering of record.

        Used by :func:`check_legality`'s note and by the search's exhaustion
        message, so a mislabelling has one place to be wrong rather than three.
        """
        if self.kind == "central_band":
            return f"the central {self.coverage:.0%} of {self.source}"
        if self.kind == "matched":
            return (
                f"within +/-{self.width:g} interquartile range(s) of one draw "
                f"from {self.source}"
            )
        return f"no less compact than any of {self.source}"

    @property
    def in_loop(self) -> tuple[str, ...]:
        """The bounded measures the search can enforce at every step."""
        return tuple(name for name in IN_LOOP_MEASURES if name in self.bounds)

    def violations(self, metrics: Mapping[str, float]) -> dict[str, str]:
        """``{measure: why it fails}`` for every bound ``metrics`` breaks.

        A bounded measure missing from ``metrics`` is a violation with the
        reason "not measured": an envelope that quietly ignores the measures a
        caller forgot to compute would certify plans nobody looked at.
        """
        out: dict[str, str] = {}
        for name, (low, high) in sorted(self.bounds.items()):
            if name not in metrics:
                out[name] = f"not measured; bound is [{low:.4g}, {high:.4g}]"
                continue
            value = float(metrics[name])
            if value < low - 1e-12:
                out[name] = f"{value:.4g} below the {low:.4g} lower bound"
            elif value > high + 1e-12:
                out[name] = f"{value:.4g} above the {high:.4g} upper bound"
        return out

    def contains(self, metrics: Mapping[str, float]) -> bool:
        return not self.violations(metrics)


def _quantile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated quantile of ``values`` (numpy's default method)."""
    ordered = sorted(float(v) for v in values)
    if not ordered:
        raise ValueError("no values to take a quantile of")
    if len(ordered) == 1:
        return ordered[0]
    h = (len(ordered) - 1) * p
    low = math.floor(h)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (h - low) * (ordered[high] - ordered[low])


def shape_metrics(
    plan: Plan,
    adjacency: Mapping[str, Iterable[str]],
    geometry=None,
) -> dict[str, float]:
    """The five envelope measures of one plan, from ``evaluate.compactness``.

    This is the authority. The search maintains its own incremental copies of
    two of these numbers for speed, and every plan it is about to return is
    re-measured here before the envelope is applied to it, so a bug in the
    incremental arithmetic cannot certify a plan that the shipped compactness
    module would reject.

    ``geometry`` is the projected unit table (``generate.units.load_geometry``
    on Iowa). Without it only ``cut_edges`` can be computed -- it is the one
    measure that reads the graph rather than the shapes -- and the returned dict
    has one key.
    """
    out: dict[str, float] = {"cut_edges": float(cut_edges(plan, adjacency))}
    if geometry is None:
        return out
    measured = all_metrics(plan, geometry, adjacency)
    for name in ENVELOPE_MEASURES:
        if name in measured:
            out[name] = float(measured[name])
    return out


def calibrate_shape_envelope(
    plans: Sequence[Plan],
    adjacency: Mapping[str, Iterable[str]],
    geometry=None,
    *,
    coverage: float = DEFAULT_SHAPE_COVERAGE,
    centre: float = 0.5,
    measures: Sequence[str] = ENVELOPE_MEASURES,
    source: str = "unnamed neutral ensemble",
    reference_draws: int | None = None,
) -> ShapeEnvelope:
    """Bound each measure by a ``coverage``-wide interval of ``plans``.

    ``plans`` must be neutral draws -- the same ensemble the detector locates
    plans against, or one drawn the same way. Pass them exactly as they came
    out of the sampler if you want the bound the detector's own percentiles see:
    a ReCom chain repeats plans, and de-duplicating first shifts every quantile
    (measured on Iowa: the median cut-edge count is 44 over 24,247 draws and 49
    over the 2,217 distinct plans among them, because the chain spends its time
    in the compact part of the space). Neither is wrong and the difference is
    real, so ``reference_plans`` and ``reference_draws`` are both recorded.

    ``centre`` is where in the reference distribution the interval sits, as a
    quantile: the default 0.5 gives the central interval, and the bounds are
    ``[q(centre - coverage/2), q(centre + coverage/2)]``. The window slides
    rather than shrinking when it runs off an end, so its width is always
    ``coverage``.

    **``centre`` is how a caller matches the neutral distribution instead of
    merely staying inside it, and the measurement says it has to.** A central
    band still lets the search pile every planted plan against its ragged edge,
    because raggedness is what buys seats: measured on Iowa at ``coverage=0.90``
    the planted plans sit at 50-52 cut edges inside a [40, 52] band whose
    reference median is 44, and a cut-edge classifier separates them from the
    neutral draws at AUC 0.91 while a partisan one cannot tell them apart at
    all. Drawing ``centre`` per plant from ``U(0, 1)`` with a narrow
    ``coverage`` instead makes the planted plans' marginal distribution on each
    bounded measure a sample of the neutral one, which is what AUC 0.5 requires.
    Pair it with ``start_plans`` filtered to the same band, so the search starts
    feasible.

    ``adversarial`` may not import ``generate`` (tools/firewall.yaml), so the
    plans are injected here exactly as ``nulls.sample_nulls`` injects its
    sampler. Nothing in this function reads a vote.
    """
    if not 0 < coverage <= 1:
        raise ValueError(f"coverage must lie in (0, 1]; got {coverage!r}")
    if not 0 <= centre <= 1:
        raise ValueError(f"centre must lie in [0, 1]; got {centre!r}")
    plans = [dict(p) for p in plans]
    if not plans:
        raise ValueError("no plans to calibrate a shape envelope from")
    wanted = tuple(measures)
    unknown = [name for name in wanted if name not in ENVELOPE_MEASURES]
    if unknown:
        raise ValueError(f"unknown envelope measure(s) {unknown}")

    series = _series(plans, adjacency, geometry, wanted)

    low_p = min(max(centre - coverage / 2.0, 0.0), 1.0 - coverage)
    high_p = low_p + coverage
    bounds: dict[str, tuple[float, float]] = {}
    for name in wanted:
        values = series[name]
        if not values:
            continue  # geometry was not supplied; the measure is unbounded
        bounds[name] = (_quantile(values, low_p), _quantile(values, high_p))
    return ShapeEnvelope(
        coverage=float(coverage),
        centre=float(centre),
        bounds=bounds,
        reference_plans=len(plans),
        reference_draws=int(reference_draws if reference_draws is not None else len(plans)),
        measures=tuple(bounds),
        source=source,
        kind="central_band",
    )


def _series(
    plans: Sequence[Plan],
    adjacency: Mapping[str, Iterable[str]],
    geometry,
    wanted: Sequence[str],
) -> dict[str, list[float]]:
    """``{measure: [one value per plan]}``, measured through :func:`shape_metrics`."""
    series: dict[str, list[float]] = {name: [] for name in wanted}
    for plan in plans:
        measured = shape_metrics(plan, adjacency, geometry)
        for name in wanted:
            if name in measured:
                series[name].append(measured[name])
    return series


#: **VALUE.** Half-width, in reference interquartile ranges, of the envelope
#: :func:`envelope_around_plan` builds around one neutral draw. Since round 4
#: this is the constraint the shipped bench runs (``detect.bench.AnchorPool``),
#: so it is the number that decides what the ground truth is.
#:
#: **What the width trades.** At 0 the planted plan would have to reproduce the
#: anchor draw's five measures exactly, which is unsatisfiable; as it grows the
#: envelope approaches an uninformative box and the search returns to piling
#: against an edge. In between, the planted marginal on each measure is the
#: neutral marginal *blurred* by at most this many IQRs — the plants inherit the
#: reference's spread rather than sitting at its ceiling, at the cost of a small
#: variance inflation. 0.5 IQR is wide enough that the search has somewhere to
#: go and narrow enough that the plan stays near the draw it was matched to.
#: Nobody can derive it, which is why it is marked `VALUE` and why the yield it
#: produces is reported at every magnitude rather than being tuned for.
DEFAULT_MATCH_WIDTH = 0.5


def envelope_around_plan(
    target: Plan,
    plans: Sequence[Plan],
    adjacency: Mapping[str, Iterable[str]],
    geometry=None,
    *,
    width: float = DEFAULT_MATCH_WIDTH,
    measures: Sequence[str] = ENVELOPE_MEASURES,
    source: str = "one neutral draw",
) -> ShapeEnvelope:
    """An envelope centred on **one neutral plan's** measurements.

    Bounds are ``target_value +/- width * IQR`` per measure, the IQR taken from
    ``plans`` (the neutral reference). Use it with ``start_plans`` containing
    ``target``: the search then starts feasible by construction and cannot
    wander more than ``width`` of an IQR away from a plan the neutral sampler
    actually produced.

    **This is the instrument that matches the neutral distribution rather than
    bounding it, and the measurement is why it exists.** Two things went wrong
    with the quantile band:

    1. A central band lets the search pile every planted plan against its
       ragged edge, so a cut-edge classifier still separates the classes at
       AUC ~0.9 even at ``coverage=0.90``.
    2. Sliding a *narrow* quantile window to a random centre -- the obvious fix
       -- fails outright, because the five measures disagree (CRITERIA.md
       section 3) and the region where all five sit in the same 20% window is
       usually **empty**: of 2,217 distinct Iowa plans, 0 satisfied it for 8 of
       12 randomly drawn centres, and the planted search reached its magnitude
       in 2 of 24 attempts.

    Anchoring on a real draw cannot be empty -- the draw itself is in it -- and
    the planted plans then inherit the reference's own spread, which is what
    AUC 0.5 requires. Drawing ``target`` with draw weight (not from the distinct
    plans) matches the distribution the detector's percentiles are taken over.
    """
    if width <= 0:
        raise ValueError(f"width must be positive; got {width!r}")
    plans = [dict(p) for p in plans]
    if not plans:
        raise ValueError("no reference plans to take an interquartile range from")
    wanted = tuple(measures)
    unknown = [name for name in wanted if name not in ENVELOPE_MEASURES]
    if unknown:
        raise ValueError(f"unknown envelope measure(s) {unknown}")

    return envelope_from_measurements(
        shape_metrics(target, adjacency, geometry),
        _series(plans, adjacency, geometry, wanted),
        width=width,
        measures=wanted,
        source=source,
        reference_plans=len(plans),
        reference_draws=len(plans),
    )


def envelope_from_measurements(
    anchor: Mapping[str, float],
    series: Mapping[str, Sequence[float]],
    *,
    width: float = DEFAULT_MATCH_WIDTH,
    measures: Sequence[str] = ENVELOPE_MEASURES,
    source: str = "one neutral draw",
    reference_plans: int | None = None,
    reference_draws: int | None = None,
) -> ShapeEnvelope:
    """:func:`envelope_around_plan`, from measurements that already exist.

    Same arithmetic, same object, no geometry: ``anchor`` is one plan's five
    measures and ``series`` is the reference's own columns of them. It exists
    because the caller that ships this envelope -- ``detect.bench`` -- has
    already measured every reference draw for the detector's percentiles, and
    re-measuring them inside this module would cost 2.7 s per Colorado plan
    (measured; 0.17 s on Iowa) for numbers that are sitting in a column. A
    matched envelope is drawn **per plant**, so that cost would be paid once per
    planted plan rather than once per round.

    :func:`envelope_around_plan` is the plan-level entry point and delegates
    here, so there is one implementation of the bound and not two that can
    drift.
    """
    if width <= 0:
        raise ValueError(f"width must be positive; got {width!r}")
    wanted = tuple(measures)
    unknown = [name for name in wanted if name not in ENVELOPE_MEASURES]
    if unknown:
        raise ValueError(f"unknown envelope measure(s) {unknown}")
    if not any(series.get(name) for name in wanted):
        raise ValueError("no reference measurements to take an interquartile range from")

    bounds: dict[str, tuple[float, float]] = {}
    used: dict[str, float] = {}
    for name in wanted:
        values = list(series.get(name) or ())
        if not values or name not in anchor:
            continue
        spread = _quantile(values, 0.75) - _quantile(values, 0.25)
        half = width * spread
        centre_value = float(anchor[name])
        bounds[name] = (centre_value - half, centre_value + half)
        used[name] = centre_value
    n = max((len(list(series.get(name) or ())) for name in wanted), default=0)
    return ShapeEnvelope(
        coverage=None,
        width=float(width),
        kind="matched",
        bounds=bounds,
        anchor=used,
        reference_plans=int(reference_plans if reference_plans is not None else n),
        reference_draws=int(reference_draws if reference_draws is not None else n),
        measures=tuple(bounds),
        source=source,
    )


class _Guard:
    """The envelope in the form the search can afford to consult every step.

    Holds the geometry weights (unit area, unit perimeter, shared boundary
    length per adjacent pair) and the two in-loop bounds, and turns a
    ``(cut edges, mean Polsby-Popper)`` pair into a single violation number.

    The two violations are each divided by their own band width before being
    added, so the sum is dimensionless and neither measure's units decide the
    trade-off. A state inside the envelope scores exactly 0.
    """

    __slots__ = (
        "area", "perimeter", "shared",
        "cut_bounds", "pp_bounds", "cut_width", "pp_width", "has_geometry",
    )

    def __init__(self, envelope: ShapeEnvelope, geometry, adjacency) -> None:
        self.cut_bounds = envelope.bounds.get("cut_edges")
        self.pp_bounds = envelope.bounds.get("polsby_popper_mean")
        self.cut_width = max(1e-9, self.cut_bounds[1] - self.cut_bounds[0]) if self.cut_bounds else 1.0
        self.pp_width = max(1e-9, self.pp_bounds[1] - self.pp_bounds[0]) if self.pp_bounds else 1.0
        self.area: dict[str, float] = {}
        self.perimeter: dict[str, float] = {}
        self.shared: dict[str, dict[str, float]] = {}
        self.has_geometry = self.pp_bounds is not None and geometry is not None
        if self.pp_bounds is not None and geometry is None:
            raise ValueError(
                "the shape envelope bounds polsby_popper_mean but no geometry "
                "was given to enforce it with; pass geometry= or calibrate the "
                "envelope without it"
            )
        if self.has_geometry:
            self._load(geometry, adjacency)

    def _load(self, geometry, adjacency) -> None:
        # One dissolved geometry per *unit*, which is the unit's own polygon --
        # taken through evaluate.compactness so the projection guard runs on
        # this table exactly as it does for the measures themselves.
        singleton = {unit: index for index, unit in enumerate(sorted(adjacency), start=1)}
        shapes = district_geometries(singleton, geometry)
        by_unit = {unit: shapes[index] for unit, index in singleton.items()}
        for unit, shape in by_unit.items():
            self.area[unit] = float(shape.area)
            self.perimeter[unit] = float(shape.length)
            self.shared[unit] = {}
        for unit, neighbours in adjacency.items():
            for other in neighbours:
                if unit >= other:
                    continue
                overlap = by_unit[unit].intersection(by_unit[other])
                length = float(overlap.length)
                if overlap.geom_type in ("Polygon", "MultiPolygon"):
                    # A sliver overlap is walked on both sides by .length.
                    length /= 2.0
                self.shared[unit][other] = length
                self.shared[other][unit] = length

    def violation(self, cut: int, polsby_popper: float | None) -> float:
        total = 0.0
        if self.cut_bounds is not None:
            low, high = self.cut_bounds
            total += (max(0.0, low - cut) + max(0.0, cut - high)) / self.cut_width
        if self.pp_bounds is not None and polsby_popper is not None:
            low, high = self.pp_bounds
            total += (
                max(0.0, low - polsby_popper) + max(0.0, polsby_popper - high)
            ) / self.pp_width
        return total


# --------------------------------------------------------------------------- #
# legality
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class LegalityRecord:
    """Evidence that every constraint was checked, and what it came to.

    ``checks`` is the record: a name -> pass/fail for each constraint, and
    :attr:`passed` is true only if every one of them passed. ``notes`` carries
    the reason for anything that failed, plus the standing note on whole
    counties. Nothing here is inferred from the search having "succeeded" — the
    checks are re-run on the finished plan.
    """

    k: int
    epsilon: float
    ideal_population: float
    district_populations: dict[int, int]
    max_deviation_persons: int
    max_deviation_fraction: float
    population_spread: int
    checks: dict[str, bool]
    notes: dict[str, str]

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    def failures(self) -> list[str]:
        return sorted(name for name, ok in self.checks.items() if not ok)


def check_legality(
    plan: Plan,
    adjacency: Mapping[str, Iterable[str]],
    populations: Mapping[str, int],
    k: int,
    epsilon: float,
    *,
    shape_envelope: "ShapeEnvelope | None" = None,
    plan_shape_metrics: Mapping[str, float] | None = None,
) -> LegalityRecord:
    """Check every legal constraint on ``plan`` and record the outcome of each.

    The structural invariants (assignment, ids ``1..k``, contiguity) are checked
    twice on purpose: once here in a form that yields one boolean per constraint,
    and once by ``evaluate.plan.validate``, which is the contract's authority
    (ARCHITECTURE section 3) but raises on the first failure and so cannot
    produce a per-constraint record on its own. If the two ever disagree,
    ``validate`` wins and the ``validate`` check fails.

    **Compactness — Iowa Code ch. 42's fourth criterion — is checked only if
    you give it something to check against.** The statute ranks compactness
    last and states no numerical standard, so there is no threshold to test;
    what round 2 exposed is the consequence of leaving it out entirely, which
    was that plans with a third the Polsby-Popper of every neutral draw came
    back ``legal_compliance = 1.0``. Passing ``shape_envelope`` together with
    ``plan_shape_metrics`` (from :func:`shape_metrics`) adds a
    ``compactness_within_neutral_envelope`` check that says whether the plan
    would survive the traditional-criteria review a real map receives. Omit
    them and the record carries a note saying compactness was not tested, in
    place of a silent pass.
    """
    if int(k) != k or k < 1:
        raise ValueError(f"k must be a positive integer; got {k!r}")
    k = int(k)
    if not 0 < epsilon < 1:
        raise ValueError(f"epsilon must lie in (0, 1); got {epsilon!r}")

    units = set(adjacency)
    checks: dict[str, bool] = {}
    notes: dict[str, str] = {}

    assigned = set(plan)
    checks["every_unit_assigned_exactly_once"] = assigned == units
    if assigned != units:
        notes["every_unit_assigned_exactly_once"] = (
            f"{len(units - assigned)} unassigned, "
            f"{len(assigned - units)} not in the unit graph"
        )

    members = districts(plan)
    ids = set(members)
    checks["district_ids_are_1_to_k"] = ids <= set(range(1, k + 1))
    checks["no_empty_district"] = set(range(1, k + 1)) <= ids
    if not checks["district_ids_are_1_to_k"]:
        stray = sorted(ids - set(range(1, k + 1)))
        notes["district_ids_are_1_to_k"] = f"stray ids {stray}"
    if not checks["no_empty_district"]:
        notes["no_empty_district"] = f"empty {sorted(set(range(1, k + 1)) - ids)}"

    # A plan naming units the graph does not contain cannot be checked for
    # contiguity or population at all -- there is nowhere to look them up. Those
    # checks are recorded as failed with the reason, rather than raising a
    # KeyError from inside a function whose job is to report what failed.
    unknown = assigned - units
    if unknown:
        for name in ("contiguous_on_rook_graph", "population_within_epsilon"):
            checks[name] = False
            notes[name] = (
                f"not checkable: the plan names {len(unknown)} unit(s) outside "
                "the graph, e.g. " + ", ".join(sorted(unknown)[:3])
            )
    else:
        disconnected = [
            d
            for d, units_in in members.items()
            if not _connected(set(units_in), adjacency)
        ]
        checks["contiguous_on_rook_graph"] = not disconnected
        if disconnected:
            notes["contiguous_on_rook_graph"] = (
                f"districts {sorted(disconnected)} disconnected"
            )

    # Whole counties: the unit of assignment is the county, so a district is a
    # union of whole counties by construction and a split is unrepresentable.
    # Recorded rather than silently assumed, because the claim is what makes
    # Iowa Code ch. 42 criterion 3 automatically satisfied here.
    checks["whole_units_no_splits"] = True
    notes["whole_units_no_splits"] = (
        "units are whole counties; a plan assigns each county to exactly one "
        "district, so county splits are 0 by construction (FEASIBILITY 5.3)"
    )

    ideal = sum(int(populations[u]) for u in units) / k if units else 0.0
    band = epsilon * ideal
    totals: dict[int, int] = {}
    max_dev, spread = 0.0, 0
    if not unknown:
        for d, units_in in members.items():
            totals[d] = sum(int(populations[u]) for u in units_in)
        if totals:
            max_dev = max(abs(t - ideal) for t in totals.values())
            spread = max(totals.values()) - min(totals.values())
        checks["population_within_epsilon"] = bool(totals) and max_dev <= band + 1e-9
        notes["population_within_epsilon"] = (
            f"epsilon bounds each district's deviation from ideal, not the "
            f"spread: |dev| <= {band:.1f} persons, observed {max_dev:.1f}"
        )

    # Compactness (Iowa Code ch. 42 criterion 4). See the docstring: a check
    # only when a standard to check against was supplied, and a note otherwise.
    if shape_envelope is not None and plan_shape_metrics is not None:
        broken = shape_envelope.violations(plan_shape_metrics)
        checks["compactness_within_neutral_envelope"] = not broken
        notes["compactness_within_neutral_envelope"] = (
            shape_envelope.description
            + (f"; {'; '.join(f'{n}: {w}' for n, w in broken.items())}" if broken else "")
        )
    else:
        notes["compactness_not_checked"] = (
            "Iowa Code ch. 42 criterion 4 is compactness and nothing here "
            "tested it; pass shape_envelope= and plan_shape_metrics= for a "
            "check against the neutral ensemble's own distribution"
        )

    try:
        validate(plan, adjacency, k)
        checks["evaluate_plan_validate"] = True
    except ValueError as exc:
        checks["evaluate_plan_validate"] = False
        notes["evaluate_plan_validate"] = str(exc)[:300]

    return LegalityRecord(
        k=k,
        epsilon=float(epsilon),
        ideal_population=float(ideal),
        district_populations=dict(sorted(totals.items())),
        max_deviation_persons=int(round(max_dev)),
        max_deviation_fraction=(max_dev / ideal) if ideal else 0.0,
        population_spread=int(spread),
        checks=checks,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# result
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GerrymanderResult:
    """A plan built to favour one party, with its magnitude measured.

    ``realized_seat_count`` and ``baseline_seat_count`` are both produced by
    ``evaluate.partisan.seat_counts`` — the shift is a measurement, not the
    search's intention. ``intended_seat_shift`` records what was asked for
    (``None`` for an open-ended maximisation) so that a caller can see the two
    side by side; :func:`plant_gerrymander` refuses to return a result where
    they differ.

    Two fields are easy to misread:

    * ``district_shares`` is the **target party's** share in each district, so
      the same plan reports different numbers under ``target_party="D"`` and
      ``"R"``. ``seat_counts`` is always ``(D, R, tied)`` in that order, from
      ``evaluate.partisan``, and is not relabelled.
    * ``seat_ceiling_at_work_epsilon`` is the best seat count the seat phase
      reached inside the *loose working band*, which can exceed
      ``realized_seat_count``: a seat structure can exist at 10% population
      deviation and have no counterpart inside the real band. When the two
      differ, the search found a gerrymander it could not legalise, and saying
      so is the point of carrying the field.
    """

    plan: Plan
    target_party: str
    realized_seat_count: int
    baseline_seat_count: int
    seat_shift: int
    population_spread: int
    iterations: int
    legality: LegalityRecord

    k: int
    epsilon: float
    seed: int
    intended_seat_shift: int | None
    seat_counts: tuple[int, int, int]
    district_shares: dict[int, float]
    baseline_plan: Plan
    baseline_source: str
    baseline_legality: LegalityRecord
    seat_ceiling_at_work_epsilon: int
    restarts_run: int
    restart_used: int
    work_epsilon: float
    seconds: float
    baseline_seat_counts: tuple[int, int, int] = (0, 0, 0)
    shape_envelope: ShapeEnvelope | None = None
    shape_metrics: dict[str, float] = field(default_factory=dict)
    shape_rejections: int = 0
    start_source: str = "internal neutral reference"

    @property
    def legal(self) -> bool:
        return self.legality.passed

    @property
    def shape_constrained(self) -> bool:
        """Was this plan built inside a calibrated shape envelope (D-010)?

        ``False`` marks a round-2-style plan: legal, partisan, and separable
        from a neutral map on compactness alone. Any confusion matrix mixing
        the two is measuring two different adversaries.
        """
        return self.shape_envelope is not None


# --------------------------------------------------------------------------- #
# public search
# --------------------------------------------------------------------------- #

def maximize_seats(
    target_party: str,
    adjacency: Mapping[str, Iterable[str]],
    populations: Mapping[str, int],
    dem: Mapping[str, int],
    rep: Mapping[str, int],
    k: int,
    epsilon: float,
    seed: int,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    *,
    restarts: int = DEFAULT_RESTARTS,
    baseline_plan: Plan | None = None,
    baseline_source: str | None = None,
    target_seats: int | None = None,
    work_epsilon: float = DEFAULT_WORK_EPSILON,
    repair_rounds: int = DEFAULT_REPAIR_ROUNDS,
    sigmoid: float = DEFAULT_SIGMOID,
    surrogate_weight: float = DEFAULT_SURROGATE_WEIGHT,
    shape_envelope: ShapeEnvelope | None = None,
    geometry=None,
    start_plans: Sequence[Plan] | None = None,
) -> GerrymanderResult:
    """Search for the legal plan that wins ``target_party`` the most seats.

    Args:
        target_party: ``"D"`` or ``"R"``. The party whose seat count is
            maximised. Everything else is symmetric between the two.
        adjacency: ``{GEOID: [GEOID, ...]}`` rook graph; defines the unit set.
        populations: ``{GEOID: persons}``.
        dem, rep: two-party votes by unit, from ``evaluate.elections.two_party``.
        k: number of districts.
        epsilon: per-district population tolerance as a fraction of ideal. The
            returned plan satisfies it; see the module docstring on spread.
        seed: every random draw is derived from this. Same inputs and same seed
            give the same plan.
        max_iterations: annealing budget for the seat phase, per restart. The
            ``iterations`` field of the result counts *every* candidate move
            evaluated across all phases and restarts, which is larger.
        restarts: independent seeded restarts; the best legal plan wins. More
            than one is not optional when the ceiling is the question, and the
            reason is structural rather than a matter of luck: Polk County is
            492,401 persons, 62% of an Iowa district, so *no* single-county move
            or swap can ever relocate it inside any usable population band. Its
            district is fixed by the plan the restart starts from, and restarts
            are the only way the search explores placing it differently.
        baseline_plan: the plan ``seat_shift`` is measured against. Defaults to a
            neutral reference plan built here from population and adjacency only
            (never from votes), reported as
            ``baseline_source="neutral_reference"``. Pass the enacted plan, or
            an ensemble-median plan, to measure the shift against that instead
            — which is what detection wants.
        baseline_source: what to call that baseline in the record. **Name it.**
            A seat shift is meaningless without saying what it is a shift
            *from*, and round 2 pooled a D-direction shift measured from the
            enacted plan with an R-direction shift measured from the single
            most Democratic-favouring draw of a 14-plan ensemble — two
            different quantities under one gate. See ``achievable_seats``,
            which measures both directions from one stated baseline, and the
            module docstring's baseline table.
        shape_envelope: the non-partisan shape bounds the search may not leave
            (:class:`ShapeEnvelope`, docs/DECISIONS.md D-010). ``None`` runs the
            unconstrained round-2 search, whose output is separable from a
            neutral map by ``cut_edges`` alone; that is kept reachable because
            the comparison between the two *is* the frontier result, not
            because it is a reasonable default for ground truth.
        geometry: the projected unit geometry table. Required when the envelope
            bounds any shape measure, and used to re-measure the finished plan
            through ``evaluate.compactness`` before it is returned.
        start_plans: plans to start the restarts from, used round-robin. Pass
            neutral ensemble draws: they are inside the envelope by
            construction, so the search begins feasible instead of walking in
            from a growth plan, and the resulting adversary is the realistic
            one — a mapper who starts from a compact map and edits it.
        target_seats: if given, search for a plan winning *exactly* this many
            seats rather than as many as possible. Used by
            :func:`plant_gerrymander` to plant a specified magnitude.
        work_epsilon: the loose population band the seat phase runs inside. Must
            be wide enough that moving one county keeps a district legal; on
            Iowa counties anything below about 0.005 strands the search.
        repair_rounds: descent-and-kick rounds available to tighten from
            ``work_epsilon`` to ``epsilon``.
        sigmoid: temperature of the sigmoid relaxation of the seat count, in
            vote-share units. Smaller is a sharper approximation of the step.
        surrogate_weight: weight on the summed sigmoid relative to one seat.

    Returns:
        A :class:`GerrymanderResult` whose plan has been re-checked against every
        constraint. ``legality.passed`` is always true here — a plan that fails
        is never returned.

    Raises:
        SearchExhausted: no legal plan (at ``target_seats``, if given) was found
            within the budget.
        ValueError: on malformed inputs.
    """
    started = time.perf_counter()
    party = _check_party(target_party)
    _check_inputs(adjacency, populations, dem, rep, k, epsilon, work_epsilon)
    if restarts < 1:
        raise ValueError(f"restarts must be >= 1; got {restarts}")
    if max_iterations < 1:
        raise ValueError(f"max_iterations must be >= 1; got {max_iterations}")
    if target_seats is not None and not 0 <= target_seats <= k:
        raise ValueError(f"target_seats must lie in 0..{k}; got {target_seats}")

    units = sorted(adjacency)
    adj = {u: tuple(sorted(adjacency[u])) for u in units}
    pops = {u: int(populations[u]) for u in units}
    target_votes = dem if party == "D" else rep
    other_votes = rep if party == "D" else dem
    ideal = sum(pops.values()) / k
    band = epsilon * ideal
    work_band = work_epsilon * ideal

    counter = _Counter()
    guard = None if shape_envelope is None else _Guard(shape_envelope, geometry, adj)

    # ---- baseline ---------------------------------------------------------
    if baseline_plan is None:
        base_rng = random.Random(_derive(seed, "baseline", 0))
        base = _neutral_reference(
            adj, pops, units, k, band, work_band, base_rng, counter, guard=guard
        )
        baseline_name = "neutral_reference"
    else:
        base = dict(baseline_plan)
        baseline_name = baseline_source or "supplied (unnamed)"
    if baseline_plan is None and baseline_source:
        baseline_name = baseline_source
    baseline_legality = check_legality(base, adj, pops, k, epsilon)
    base_seats = _party_seats(base, dem, rep, party)

    starts = None
    if start_plans is not None:
        starts = [dict(p) for p in start_plans]
        if not starts:
            raise ValueError("start_plans was given but empty")

    # ---- restarts ---------------------------------------------------------
    best: tuple[tuple[int, int], Plan, int, int] | None = None
    ceiling_seen = 0
    rejected_on_shape = 0
    # Restarts whose starting plan was already outside the working band. The
    # seat phase accepts a move only if the state it lands in has zero excess
    # over that band, so such a restart can take no move that does not close the
    # whole gap at once, and on a large graph no single reassignment ever does:
    # the annealer runs its full budget without moving and returns the start
    # plan's own seat count as if it were a ceiling. That failure was silent
    # until round 4, and the exhaustion message blamed the iteration budget for
    # it. Counted here so the message can say what actually happened.
    started_outside = 0
    worst_start_excess = 0.0
    for index in range(restarts):
        rng = random.Random(_derive(seed, "restart", index))
        if starts is not None:
            start = dict(starts[index % len(starts)])
        else:
            start = _neutral_reference(
                adj, pops, units, k, band, work_band, rng, counter,
                tighten=False, guard=guard,
            )
        state = _State(start, adj, pops, target_votes, other_votes, k, guard)
        start_excess = state.excess(work_band, ideal)
        if start_excess > 0.0:
            started_outside += 1
            worst_start_excess = max(worst_start_excess, start_excess)
        by_seats = _anneal_seats(
            state, rng, max_iterations, work_band, sigmoid, surrogate_weight, counter
        )
        if by_seats:
            ceiling_seen = max(ceiling_seen, max(by_seats))
        wanted = (
            [target_seats]
            if target_seats is not None
            else sorted(by_seats, reverse=True)
        )
        for seats in wanted:
            if seats not in by_seats:
                continue
            if best is not None and target_seats is None and seats < best[0][0]:
                break  # cannot beat what another restart already legalised
            found = None
            for candidate in by_seats[seats]:
                found = _repair(
                    _State(
                        candidate, adj, pops, target_votes, other_votes, k, guard
                    ),
                    rng,
                    band,
                    seats,
                    repair_rounds,
                    counter,
                )
                if found is None:
                    continue
                # The envelope is applied to the finished plan by
                # evaluate.compactness, not by the search's own incremental
                # arithmetic, and on every measure it bounds rather than the
                # two the search could afford to track.
                if shape_envelope is not None:
                    measured = shape_metrics(found[1], adj, geometry)
                    if shape_envelope.violations(measured):
                        rejected_on_shape += 1
                        found = None
                        continue
                break
            if found is None:
                continue
            spread, plan = found
            key = (seats, -spread)
            if best is None or key > best[0]:
                best = (key, plan, spread, index)
            break

    if best is None:
        raise SearchExhausted(
            f"no plan satisfying epsilon={epsilon} was found for target_party="
            f"{party}"
            + (f" at exactly {target_seats} seats" if target_seats is not None else "")
            + f" in {restarts} restart(s) of {max_iterations} iterations "
            f"(seat ceiling reached at work_epsilon={work_epsilon}: {ceiling_seen}"
            + (
                f"; {rejected_on_shape} repaired plan(s) rejected by the shape "
                f"envelope: {shape_envelope.description}"
                if shape_envelope is not None
                else ""
            )
            + ")."
            + (
                ""
                if started_outside == 0
                else (
                    f" {started_outside} of {restarts} restart(s) began OUTSIDE "
                    f"the working band (worst excess {worst_start_excess:,.0f} "
                    f"persons over work_epsilon={work_epsilon:g}, i.e. "
                    f"{worst_start_excess / (work_epsilon * ideal):.1f}x the "
                    "band), and the seat phase cannot move from there — so for "
                    "those restarts the budget was never the binding "
                    "constraint. Supply start_plans (neutral ensemble draws are "
                    "inside the band by construction), or raise work_epsilon."
                )
            )
            + " This is a statement about the search budget, not a proof that "
            "no such plan exists."
        )

    (seats, _), plan, spread, restart_used = best
    measured_shape = shape_metrics(plan, adj, geometry) if (
        shape_envelope is not None or geometry is not None
    ) else {}
    if shape_envelope is not None:
        broken = shape_envelope.violations(measured_shape)
        if broken:  # pragma: no cover - the acceptance check above enforces it
            raise AssertionError(
                f"maximize_seats produced a plan outside its own shape "
                f"envelope: {broken}; refusing to return it"
            )
    legality = check_legality(
        plan, adj, pops, k, epsilon,
        shape_envelope=shape_envelope,
        plan_shape_metrics=measured_shape or None,
    )
    if not legality.passed:  # pragma: no cover - the repair phase enforces this
        raise AssertionError(
            "maximize_seats produced a plan that fails "
            f"{legality.failures()}; refusing to return it"
        )
    counts = seat_counts(plan, dem, rep)
    realized = counts[0] if party == "D" else counts[1]
    if realized != seats:  # pragma: no cover - internal/evaluate disagreement
        raise AssertionError(
            f"internal seat count {seats} disagrees with "
            f"evaluate.partisan.seat_counts {counts} for party {party}"
        )
    return GerrymanderResult(
        plan=plan,
        target_party=party,
        realized_seat_count=realized,
        baseline_seat_count=base_seats,
        seat_shift=realized - base_seats,
        population_spread=spread,
        iterations=counter.value,
        legality=legality,
        k=k,
        epsilon=float(epsilon),
        seed=int(seed),
        intended_seat_shift=(
            None if target_seats is None else target_seats - base_seats
        ),
        seat_counts=counts,
        district_shares=_shares_for(plan, dem, rep, party),
        baseline_plan=base,
        baseline_source=baseline_name,
        baseline_seat_counts=seat_counts(base, dem, rep),
        baseline_legality=baseline_legality,
        seat_ceiling_at_work_epsilon=ceiling_seen,
        restarts_run=restarts,
        restart_used=restart_used,
        work_epsilon=float(work_epsilon),
        seconds=time.perf_counter() - started,
        shape_envelope=shape_envelope,
        shape_metrics=measured_shape,
        shape_rejections=rejected_on_shape,
        start_source=(
            "supplied start_plans" if starts is not None
            else "internal neutral reference (population and adjacency only)"
        ),
    )


def plant_gerrymander(
    target_party: str,
    seat_shift: int,
    adjacency: Mapping[str, Iterable[str]],
    populations: Mapping[str, int],
    dem: Mapping[str, int],
    rep: Mapping[str, int],
    k: int,
    epsilon: float,
    seed: int,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    *,
    baseline_plan: Plan | None = None,
    **kwargs,
) -> GerrymanderResult | None:
    """Plant a gerrymander of exactly ``seat_shift`` seats, or return ``None``.

    ``None`` means the magnitude was not reached — most often because it is not
    reachable at all (Iowa cannot give R a positive shift: the neutral map
    already wins every seat), sometimes because the budget ran out. Either way
    the caller gets ``None`` rather than an exception to swallow or, worse, a
    near miss quietly relabelled as the magnitude that was asked for. The
    returned result always satisfies
    ``realized_seat_count - baseline_seat_count == seat_shift``.

    A negative ``seat_shift`` is meaningful and allowed: it plants a plan that
    *sacrifices* seats for the target party, which is the same construction seen
    from the other party's side.

    Raises:
        SearchExhausted: when no ``baseline_plan`` was supplied and the neutral
            reference this function built for itself is not legal at
            ``epsilon``. That is not a magnitude this function failed to reach,
            so it is not ``None``: the shift would be measured from a plan that
            is not a lawful districting, and every number downstream would
            inherit it.
    """
    party = _check_party(target_party)
    if not isinstance(seat_shift, int) or isinstance(seat_shift, bool):
        raise TypeError(f"seat_shift must be an int; got {seat_shift!r}")

    if baseline_plan is None:
        # The baseline has to be fixed before the search, since the requested
        # magnitude is relative to it. maximize_seats would otherwise build one
        # per call, and this function calls it twice.
        base_rng = random.Random(_derive(seed, "baseline", 0))
        units = sorted(adjacency)
        adj = {u: tuple(sorted(adjacency[u])) for u in units}
        pops = {u: int(populations[u]) for u in units}
        ideal = sum(pops.values()) / k
        envelope = kwargs.get("shape_envelope")
        baseline_plan = _neutral_reference(
            adj,
            pops,
            units,
            k,
            epsilon * ideal,
            kwargs.get("work_epsilon", DEFAULT_WORK_EPSILON) * ideal,
            base_rng,
            _Counter(),
            guard=(
                None if envelope is None
                else _Guard(envelope, kwargs.get("geometry"), adj)
            ),
        )
        kwargs.setdefault("baseline_source", "neutral_reference")
        # The magnitude this function plants is measured *from* this baseline,
        # so an illegal baseline makes the planted magnitude a measurement
        # against a plan no legislature could adopt -- ground truth that is not
        # ground truth. _neutral_reference returns the most balanced plan it
        # reached rather than raising when it cannot reach the band, which is
        # the right behaviour for a function whose caller may only want a
        # starting point, and the wrong thing to accept silently here.
        # maximize_seats records its baseline's legality; this refuses to
        # proceed on it. Only the self-built baseline is checked: a caller who
        # supplies baseline_plan has named what they are measuring from (the
        # enacted map, an ensemble median) and that choice is theirs.
        base_record = check_legality(baseline_plan, adj, pops, k, epsilon)
        if not base_record.passed:
            raise SearchExhausted(
                "the neutral reference plant_gerrymander built for itself is "
                f"not legal at epsilon={epsilon:g} ("
                + ", ".join(base_record.failures())
                + f"; max deviation {base_record.max_deviation_persons:,} "
                f"persons = {base_record.max_deviation_fraction:.4g} of ideal), "
                "so the seat shift would be measured from a plan that is not a "
                "lawful districting. Supply baseline_plan= to say what the "
                "magnitude is measured from."
            )
    base_seats = _party_seats(baseline_plan, dem, rep, party)
    wanted = base_seats + seat_shift
    if not 0 <= wanted <= k:
        return None
    try:
        result = maximize_seats(
            party,
            adjacency,
            populations,
            dem,
            rep,
            k,
            epsilon,
            seed,
            max_iterations,
            baseline_plan=baseline_plan,
            target_seats=wanted,
            **kwargs,
        )
    except SearchExhausted:
        return None
    if result.seat_shift != seat_shift:  # pragma: no cover - guarded above
        return None
    return result


def achievable_seats(
    adjacency: Mapping[str, Iterable[str]],
    populations: Mapping[str, int],
    dem: Mapping[str, int],
    rep: Mapping[str, int],
    k: int,
    epsilon: float,
    seed: int,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    *,
    baseline_plan: Plan | None = None,
    baseline_source: str | None = None,
    **kwargs,
) -> dict:
    """Measure the seat ceiling, and hence the achievable shift, both ways.

    Returns a dict keyed by party with the highest seat count a legal plan
    reached, the baseline seat count it is measured against, and the resulting
    shift — plus ``max_shift``, the largest shift available in *either*
    direction.

    **Both directions are measured from the same baseline, and it is named.**
    That is the whole point of this function existing beside
    :func:`maximize_seats`. A seat *shift* is a difference, so a D shift taken
    from one plan and an R shift taken from another are not comparable and must
    not be pooled into one detection gate; round 2 did exactly that and
    manufactured R-direction headroom Iowa does not have. ``comparable`` is
    ``True`` here by construction, and ``baseline_source`` says what the number
    is a shift *from*.

    On Iowa the answer depends entirely on that choice, which is the finding:

    ================================ ========= ========= ==========
    baseline                          D seats   D shift   R shift
    ================================ ========= ========= ==========
    enacted CD118 (4R-0D)                    0        +2          0
    neutral-ensemble median plan             1        +2         +1
    most-D draw of the ensemble              2        +1         +2
    ================================ ========= ========= ==========

    A 2-seat R shift exists only from a baseline that already gives the
    Democrats two of four seats — the top of the neutral distribution, not its
    centre — because R's ceiling is 4 of 4 and the enacted map is already there.
    Reported as a range, not resolved into one number.
    """
    source = baseline_source or (
        "supplied (unnamed)" if baseline_plan is not None else "neutral_reference"
    )
    out: dict = {"baseline_source": source, "comparable": True}
    for party in PARTIES:
        result = maximize_seats(
            party,
            adjacency,
            populations,
            dem,
            rep,
            k,
            epsilon,
            _derive(seed, f"ceiling-{party}", 0),
            max_iterations,
            baseline_plan=baseline_plan,
            baseline_source=source,
            **kwargs,
        )
        if baseline_plan is None:
            baseline_plan = result.baseline_plan  # share it across both parties
            out["baseline_source"] = result.baseline_source
        out[party] = {
            "max_seats": result.realized_seat_count,
            "baseline_seats": result.baseline_seat_count,
            "max_shift": result.seat_shift,
            "population_spread": result.population_spread,
            "plan": result.plan,
            "shape_metrics": dict(result.shape_metrics),
        }
    out["max_shift"] = max(out[p]["max_shift"] for p in PARTIES)
    out["baseline_plan"] = baseline_plan
    out["baseline_seat_counts"] = seat_counts(baseline_plan, dem, rep)
    out["shape_constrained"] = kwargs.get("shape_envelope") is not None
    return out


# --------------------------------------------------------------------------- #
# search internals
# --------------------------------------------------------------------------- #

class _Counter:
    """Total candidate moves evaluated, across every phase and restart."""

    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = 0

    def bump(self, n: int = 1) -> None:
        self.value += n


class _State:
    """A plan plus the per-district sums the search needs, updated in place."""

    __slots__ = (
        "plan", "adj", "pops", "target_votes", "other_votes", "k",
        "members", "totals", "tv", "ov", "units",
        "guard", "cut", "area", "perim",
    )

    def __init__(self, plan, adj, pops, target_votes, other_votes, k, guard=None):
        self.plan = dict(plan)
        self.adj = adj
        self.pops = pops
        self.target_votes = target_votes
        self.other_votes = other_votes
        self.k = k
        self.units = tuple(sorted(plan))
        self.members = {d: set() for d in range(1, k + 1)}
        for unit, d in self.plan.items():
            self.members[d].add(unit)
        self.totals = {d: sum(pops[u] for u in m) for d, m in self.members.items()}
        self.tv = {d: sum(target_votes[u] for u in m) for d, m in self.members.items()}
        self.ov = {d: sum(other_votes[u] for u in m) for d, m in self.members.items()}
        self.guard = guard
        self.cut = 0
        self.area: dict[int, float] = {}
        self.perim: dict[int, float] = {}
        if guard is not None:
            self.cut = sum(
                1
                for unit in self.units
                for other in adj[unit]
                if unit < other and self.plan[unit] != self.plan[other]
            )
            if guard.has_geometry:
                for d, m in self.members.items():
                    self.area[d] = sum(guard.area[u] for u in m)
                    self.perim[d] = sum(guard.perimeter[u] for u in m) - 2.0 * sum(
                        guard.shared[u][v]
                        for u in m
                        for v in guard.shared[u]
                        if v in m and u < v
                    )

    def polsby_popper_mean(self) -> float:
        """Mean Polsby-Popper over districts, from the incremental area/perimeter.

        Exact, not an approximation: dissolving a district unions polygons that
        share their boundaries exactly, so its area is the sum of its units'
        areas and its perimeter is the sum of their perimeters less twice every
        boundary interior to it. Checked against
        ``evaluate.compactness.polsby_popper`` -- see :data:`IN_LOOP_MEASURES`.
        """
        total = 0.0
        for d, a in self.area.items():
            p = self.perim[d]
            total += (4.0 * math.pi * a / (p * p)) if p > 0.0 else 0.0
        return total / len(self.area) if self.area else 0.0

    def shape_violation(self) -> float:
        """How far outside the shape envelope this state is; 0.0 when inside."""
        guard = self.guard
        if guard is None:
            return 0.0
        return guard.violation(
            self.cut, self.polsby_popper_mean() if guard.has_geometry else None
        )

    def move(self, unit: str, source: int, dest: int) -> None:
        guard = self.guard
        if guard is not None:
            for other in self.adj[unit]:
                neighbour = self.plan[other]
                if neighbour == source:
                    self.cut += 1
                elif neighbour == dest:
                    self.cut -= 1
            if guard.has_geometry:
                self.area[source] -= guard.area[unit]
                self.area[dest] += guard.area[unit]
                rejoined = 0.0
                severed = 0.0
                for other, length in guard.shared[unit].items():
                    neighbour = self.plan[other]
                    if neighbour == source:
                        rejoined += length
                    elif neighbour == dest:
                        severed += length
                self.perim[source] += 2.0 * rejoined - guard.perimeter[unit]
                self.perim[dest] += guard.perimeter[unit] - 2.0 * severed
        self.members[source].discard(unit)
        self.members[dest].add(unit)
        self.plan[unit] = dest
        p = self.pops[unit]
        self.totals[source] -= p
        self.totals[dest] += p
        t = self.target_votes[unit]
        o = self.other_votes[unit]
        self.tv[source] -= t
        self.tv[dest] += t
        self.ov[source] -= o
        self.ov[dest] += o

    def undo(self, moves) -> None:
        for unit, source, dest in moves:
            self.move(unit, source, dest)

    def seats(self) -> int:
        return sum(1 for d in self.tv if self.tv[d] > self.ov[d])

    def objective(self, sigmoid: float, weight: float) -> tuple[float, int]:
        seats = 0
        surrogate = 0.0
        for d in self.tv:
            t, o = self.tv[d], self.ov[d]
            if t > o:
                seats += 1
            share = 0.5 if t + o == 0 else t / (t + o)
            surrogate += 1.0 / (1.0 + math.exp(-(share - 0.5) / sigmoid))
        return seats + weight * surrogate, seats

    def excess(self, band: float, ideal: float) -> float:
        return sum(max(0.0, abs(t - ideal) - band) for t in self.totals.values())

    def spread(self) -> int:
        return max(self.totals.values()) - min(self.totals.values())


def _connected(members: set, adjacency: Mapping[str, Iterable[str]]) -> bool:
    if not members:
        return False
    start = next(iter(members))
    seen = {start}
    stack = [start]
    while stack:
        unit = stack.pop()
        for other in adjacency[unit]:
            if other in members and other not in seen:
                seen.add(other)
                stack.append(other)
    return len(seen) == len(members)


def _stays_connected(members: set, unit: str, adjacency) -> bool:
    """Would ``members - {unit}`` still be connected? ``unit`` must be in it."""
    inside = [v for v in adjacency[unit] if v in members]
    if len(inside) <= 1:
        return True  # a leaf (or isolated) node cannot disconnect anything
    rest = members - {unit}
    start = inside[0]
    seen = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for other in adjacency[node]:
            if other in rest and other not in seen:
                seen.add(other)
                stack.append(other)
    return len(seen) == len(rest)


def _random_growth(adj, pops, units, k, rng) -> Plan:
    """A contiguous k-partition grown from k random seeds, population-balanced.

    Population and adjacency only — no votes reach this function, which is what
    lets the default baseline be described as a neutral reference. It is a
    *starting point*, not a sample: nothing about its distribution is claimed,
    and it is never used as a neutral ensemble draw.
    """
    for _ in range(64):
        seeds = rng.sample(units, k)
        plan: Plan = {}
        members = {d: set() for d in range(1, k + 1)}
        totals = {d: 0 for d in range(1, k + 1)}
        for d, unit in enumerate(seeds, start=1):
            plan[unit] = d
            members[d].add(unit)
            totals[d] = pops[unit]
        unassigned = set(units) - set(seeds)
        stuck = False
        while unassigned:
            order = sorted(totals, key=lambda d: (totals[d], d))
            frontier: list[str] = []
            chosen = order[0]
            for d in order:
                frontier = sorted(
                    {v for u in members[d] for v in adj[u] if v in unassigned}
                )
                if frontier:
                    chosen = d
                    break
            if not frontier:
                stuck = True
                break
            unit = frontier[rng.randrange(len(frontier))]
            plan[unit] = chosen
            members[chosen].add(unit)
            totals[chosen] += pops[unit]
            unassigned.discard(unit)
        if not stuck:
            return plan
    raise SearchExhausted(  # pragma: no cover - needs a pathological graph
        "could not grow a contiguous starting partition; is the unit graph "
        "connected?"
    )


def _neutral_reference(
    adj, pops, units, k, band, work_band, rng, counter, tighten: bool = True,
    guard=None,
) -> Plan:
    """A population-balanced starting plan, drawn without reference to votes.

    ``tighten`` asks for the tight band; the seat phase only needs the working
    band, and starting it from a tight plan would just be undone.

    With a ``guard``, the descent is confined to the shape envelope from the
    first move. That matters more than it looks: measured on Iowa, a growth
    plan has 38-68 cut edges -- inside the neutral ensemble's own 39-64 range --
    and it is the *population descent* that drags it to 60-91, because the
    descent optimises squared population deviation and is indifferent to shape.
    The raggedness round 2 detected is manufactured here, before the partisan
    phase starts.
    """
    ideal = sum(pops.values()) / k
    state = _State(
        _random_growth(adj, pops, units, k, rng), adj, pops, pops, pops, k, guard
    )
    target = band if tighten else work_band
    best = None

    def observe() -> None:
        nonlocal best
        if state.excess(target, ideal) != 0.0:
            return
        spread = state.spread()
        if best is None or spread < best[0]:
            best = (spread, dict(state.plan))

    for _ in range(DEFAULT_REPAIR_ROUNDS if tighten else 3):
        _descend_population(
            state, ideal, counter, min_seats=None, exact_seats=None, observe=observe
        )
        if best is not None and not tighten:
            break
        _kick(state, rng, 3, counter, min_seats=None, exact_seats=None)
    if best is not None:
        return best[1]
    # Could not reach the requested band. Return the most balanced plan seen;
    # check_legality on the caller's side reports it as failing, rather than
    # this function pretending otherwise.
    _descend_population(state, ideal, counter, min_seats=None, exact_seats=None)
    return dict(state.plan)


def _boundary(state) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    plan = state.plan
    for unit in state.units:
        own = plan[unit]
        others = {plan[v] for v in state.adj[unit]}
        others.discard(own)
        if others:
            out[unit] = others
    return out


def _population_candidates(state, ideal) -> tuple[list[tuple], float]:
    """Every legal-looking single move and boundary swap, by population cost.

    Cost is the sum of squared district deviations, which drives the districts
    towards equal size rather than merely towards a small spread. Contiguity is
    *not* checked here — it is the expensive part, and checking it only on the
    few candidates that actually improve the cost is what makes the descent fast
    enough to run thousands of times.
    """
    boundary = _boundary(state)
    totals = state.totals
    base = sum((t - ideal) ** 2 for t in totals.values())
    cands: list[tuple] = []
    for unit, others in boundary.items():
        source = state.plan[unit]
        if len(state.members[source]) > 1:
            p = state.pops[unit]
            for dest in others:
                a = totals[source] - p - ideal
                b = totals[dest] + p - ideal
                delta = (
                    a * a + b * b
                    - (totals[source] - ideal) ** 2
                    - (totals[dest] - ideal) ** 2
                )
                cands.append((delta, "move", unit, None, source, dest))
    ordered = sorted(boundary)
    for unit in ordered:
        source = state.plan[unit]
        for other in ordered:
            dest = state.plan[other]
            if dest <= source:
                continue
            if dest not in boundary[unit] or source not in boundary[other]:
                continue
            if len(state.members[source]) < 2 or len(state.members[dest]) < 2:
                continue
            diff = state.pops[unit] - state.pops[other]
            a = totals[source] - diff - ideal
            b = totals[dest] + diff - ideal
            delta = (
                a * a + b * b
                - (totals[source] - ideal) ** 2
                - (totals[dest] - ideal) ** 2
            )
            cands.append((delta, "swap", unit, other, source, dest))
    cands.sort(key=lambda c: c[0])
    return cands, base


def _apply_candidate(state, cand):
    """Apply a candidate if it keeps both districts connected; else ``None``."""
    _, kind, unit, other, source, dest = cand
    if kind == "move":
        if not _stays_connected(state.members[source], unit, state.adj):
            return None
        state.move(unit, source, dest)
        return ((unit, dest, source),)
    state.move(unit, source, dest)
    state.move(other, dest, source)
    if not _connected(state.members[source], state.adj) or not _connected(
        state.members[dest], state.adj
    ):
        state.undo(((unit, dest, source), (other, source, dest)))
        return None
    return ((unit, dest, source), (other, source, dest))


def _seat_ok(state, min_seats, exact_seats) -> bool:
    if exact_seats is not None:
        return state.seats() == exact_seats
    if min_seats is not None:
        return state.seats() >= min_seats
    return True


def _live_cost(state, cand, ideal) -> float:
    """``cand``'s change in summed squared deviation against the *live* totals.

    :func:`_population_candidates` prices every candidate against the totals at
    the moment it enumerated them, and enumerates only candidates that were on
    the district boundary then. Reusing one enumeration for several moves makes
    both facts stale, so each candidate is rechecked and repriced here, and one
    the earlier moves have invalidated prices at 0.0 and is skipped. Cheap: a
    handful of lookups against 0.33 ms for the connectivity probe it guards.

    **The adjacency recheck is load-bearing, not defensive.**
    ``_apply_candidate`` verifies that the *source* district survives losing the
    unit; for a plain move it never verifies that the unit touches the
    destination, because a freshly enumerated candidate always did. Without the
    recheck, reuse can hand it a unit whose last neighbour in the destination
    has itself moved away, and the destination comes back in two pieces — a
    disconnected district returned as a legal plan. That is not hypothetical:
    ``test_colorado_the_default_start_reaches_the_band_at_vtd_scale`` failed on
    contiguity the first time enumeration reuse was switched on, which is why
    that test asserts contiguity before it asserts anything about population.
    """
    _, kind, unit, other, source, dest = cand
    totals = state.totals
    plan = state.plan
    if plan[unit] != source or len(state.members[source]) < 2:
        return 0.0
    if not any(plan[v] == dest for v in state.adj[unit]):
        return 0.0  # no longer a boundary move: the unit has been cut adrift
    if kind == "move":
        diff = state.pops[unit]
    else:
        if plan[other] != dest or len(state.members[dest]) < 2:
            return 0.0
        if not any(plan[v] == source for v in state.adj[other]):
            return 0.0
        diff = state.pops[unit] - state.pops[other]
    a = totals[source] - diff - ideal
    b = totals[dest] + diff - ideal
    return a * a + b * b - (totals[source] - ideal) ** 2 - (totals[dest] - ideal) ** 2


def _descend_population(
    state, ideal, counter, min_seats, exact_seats, observe=None,
    max_steps: int = 400,
    probes: int = DEFAULT_DESCENT_PROBES,
    probe_fraction: float = DEFAULT_DESCENT_PROBE_FRACTION,
    moves_per_pass: int = DEFAULT_DESCENT_MOVES_PER_PASS,
) -> None:
    """Best-improvement descent on population, holding the seat constraint.

    ``observe`` is called on every state the descent passes through, including
    the one it starts from. The descent minimises the sum of squared deviations,
    which is *not* the constraint — a state can satisfy ``|dev| <= band`` and
    still be improvable on that sum — so a caller that only looked at the final
    state would walk past legal plans without noticing.

    **The probe cap must be relative to the candidate list, and round 4 measured
    what happens when it is not.** Until round 4 the cap was an absolute 60,
    sized on Iowa's 99-county graph, where a boundary of 47 units yields 267
    candidates and the descent converges in ~74 probes. Colorado's 3,108 VTDs
    give a boundary of 932 and 27,835 candidates, and at the point where the
    descent declared itself finished there were still 6,833–12,911 *improving*
    candidates available, with the first connectivity-legal one at rank 66, 71
    and 72 on three seeds — just past the cap. Not one of the top 60 survived
    the contiguity check, because on a large boundary the moves with the largest
    population payoff are overwhelmingly articulation points. The descent was
    reporting a local minimum that did not exist.

    Measured on three Colorado growth plans, starting deviation 0.52–0.54 of
    ideal, budget 2,000 steps:

    ==================================== ================== ==============
    variant                               final |dev|/ideal   inside 0.10
    ==================================== ================== ==============
    absolute cap 60 (the round-3 code)    0.166, 0.485, 0.491   0 of 3
    relative cap only                     4e-6, 9e-6, 0.043     3 of 3
    enumeration reuse only                0.161, 0.485, 0.491   0 of 3
    **both (shipped)**                    **3e-6, 5e-6, 9e-5**  **3 of 3**
    ==================================== ================== ==============

    Reuse alone fixes nothing — it is the cap that binds. Reuse is what makes
    the fix affordable: 46–196 s per call with the relative cap alone against
    5–11 s with both, because one enumeration costs 79.8 ms on Colorado.

    On Iowa the *cap* does not move: ``probe_fraction`` of 267 candidates is 13,
    below the floor of 60. That is why the floor and the fraction are both kept
    rather than the constant simply being raised — raising it would have changed
    Iowa's numbers to fix a bug Iowa does not have. ``moves_per_pass`` does
    change Iowa's trajectory, and :data:`DEFAULT_DESCENT_MOVES_PER_PASS` says by
    how much and what it costs.
    """
    if observe is not None:
        observe()
    for _ in range(max_steps):
        cands, _ = _population_candidates(state, ideal)
        cap = max(probes, int(probe_fraction * len(cands)))
        applied_here = 0
        tried = 0
        for cand in cands:
            if tried >= cap or applied_here >= moves_per_pass:
                break
            if cand[0] >= -1e-9:
                break  # sorted: nothing after this improves either
            if _live_cost(state, cand, ideal) >= -1e-9:
                continue  # an earlier move in this pass invalidated it
            tried += 1
            counter.bump()
            # Re-read before *every* move, not once per pass: the rule
            # _shape_ok enforces is non-increasing violation, and applying
            # several moves against one snapshot would let the violation ratchet
            # up within a pass. At moves_per_pass=1 this is the round-3 code.
            before = state.shape_violation()
            applied = _apply_candidate(state, cand)
            if applied is None:
                continue
            if not _seat_ok(state, min_seats, exact_seats) or not _shape_ok(
                state, before
            ):
                state.undo(applied)
                continue
            applied_here += 1
            if observe is not None:
                observe()
        if applied_here == 0:
            return


def _shape_ok(state, before: float) -> bool:
    """Did the move just applied keep the state inside the shape envelope?

    The rule is *non-increasing violation*, not "inside the envelope": a search
    that starts outside it -- a growth plan drawn before the envelope existed,
    or a supplied baseline -- must be able to walk in, and once the violation
    reaches 0 this rule never lets it back out. Without an envelope every state
    scores 0 and the rule is vacuous, which is the unconstrained search of
    round 2 exactly.
    """
    return state.shape_violation() <= before + 1e-12


def _kick(state, rng, n, counter, min_seats, exact_seats) -> None:
    """Random legal perturbation, to leave a local optimum."""
    for _ in range(n):
        before = state.shape_violation()
        for _attempt in range(24):
            counter.bump()
            applied = _propose(state, rng, 0.5)
            if applied is None:
                continue
            if not _seat_ok(state, min_seats, exact_seats) or not _shape_ok(
                state, before
            ):
                state.undo(applied)
                continue
            break


def _propose(state, rng, swap_probability: float):
    """One random move or boundary swap, applied. ``None`` if it was illegal."""
    units = state.units
    unit = units[rng.randrange(len(units))]
    source = state.plan[unit]
    others = {state.plan[v] for v in state.adj[unit]}
    others.discard(source)
    if not others:
        return None
    choices = sorted(others)
    dest = choices[rng.randrange(len(choices))]
    if rng.random() < swap_probability:
        partners = sorted(
            w
            for w in state.members[dest]
            if any(state.plan[x] == source for x in state.adj[w])
        )
        if not partners:
            return None
        if len(state.members[source]) < 2 or len(state.members[dest]) < 2:
            return None
        other = partners[rng.randrange(len(partners))]
        state.move(unit, source, dest)
        state.move(other, dest, source)
        if not _connected(state.members[source], state.adj) or not _connected(
            state.members[dest], state.adj
        ):
            state.undo(((unit, dest, source), (other, source, dest)))
            return None
        return ((unit, dest, source), (other, source, dest))
    if len(state.members[source]) == 1:
        return None
    if not _stays_connected(state.members[source], unit, state.adj):
        return None
    state.move(unit, source, dest)
    return ((unit, dest, source),)


def _anneal_seats(
    state, rng, iterations, work_band, sigmoid, weight, counter,
    cycles: int = 3, t_start: float = 0.25, t_end: float = 0.002,
    keep_per_level: int = DEFAULT_KEEP_PER_LEVEL,
) -> dict[int, list[Plan]]:
    """Anneal the seat objective inside the working band.

    Returns the best plans seen *at each seat level*, not only at the maximum:
    planting a 1-seat shift needs a plan that wins exactly one seat, and it is
    far cheaper to keep the ones the search walked through than to search again
    with a different constraint.

    Several plans are kept per level, not one, because the phase that follows
    can fail: a seat structure reachable inside the *working* band need not be
    tightenable to the real band while holding its seats, and on Iowa the
    3-seat Democratic structures are exactly the ones that usually cannot. One
    stored plan per level makes that a coin flip; a handful of distinct ones
    makes it a search.
    """
    ideal = sum(state.pops.values()) / state.k
    per_cycle = max(1, iterations // cycles)
    kept: dict[int, list[tuple[float, Plan]]] = {}
    seen: dict[int, set] = {}

    def record() -> None:
        value, seats = state.objective(sigmoid, weight)
        key = _canonical(state.plan)
        if key in seen.setdefault(seats, set()):
            return
        bucket = kept.setdefault(seats, [])
        if len(bucket) >= keep_per_level and value <= bucket[-1][0]:
            return
        seen[seats].add(key)
        bucket.append((value, dict(state.plan)))
        bucket.sort(key=lambda row: -row[0])
        del bucket[keep_per_level:]

    record()
    for _cycle in range(cycles):
        current, _ = state.objective(sigmoid, weight)
        for step in range(per_cycle):
            temperature = t_start * (t_end / t_start) ** (step / per_cycle)
            counter.bump()
            before = state.shape_violation()
            applied = _propose(state, rng, 0.4)
            if applied is None:
                continue
            if state.excess(work_band, ideal) > 0.0 or not _shape_ok(state, before):
                state.undo(applied)
                continue
            value, _ = state.objective(sigmoid, weight)
            if value >= current or rng.random() < math.exp(
                (value - current) / max(temperature, 1e-9)
            ):
                current = value
                record()
            else:
                state.undo(applied)
        # Reheat from the best plan seen, which is where the next cycle has the
        # most to gain; a plain restart would throw the seat structure away.
        top = max(kept)
        state = _State(
            kept[top][0][1],
            state.adj,
            state.pops,
            state.target_votes,
            state.other_votes,
            state.k,
            state.guard,
        )
    return {seats: [plan for _value, plan in bucket] for seats, bucket in kept.items()}


def _canonical(plan: Plan) -> frozenset:
    """A district-label-invariant key, so relabellings are not stored twice."""
    groups: dict[int, set] = {}
    for unit, district in plan.items():
        groups.setdefault(int(district), set()).add(unit)
    return frozenset(frozenset(members) for members in groups.values())


def _repair(state, rng, band, seats, rounds, counter) -> tuple[int, Plan] | None:
    """Tighten to the real band while holding the seat count exactly.

    Exact, not "at least": a plan planted at one seat must not drift to two, or
    the intended magnitude and the realised one part company and the ground
    truth stops being ground truth.
    """
    ideal = sum(state.pops.values()) / state.k
    if state.seats() != seats:
        return None
    best: tuple[int, Plan] | None = None

    def observe() -> None:
        nonlocal best
        if state.excess(band, ideal) != 0.0 or state.seats() != seats:
            return
        spread = state.spread()
        if best is None or spread < best[0]:
            best = (spread, dict(state.plan))

    for _ in range(max(1, rounds)):
        _descend_population(
            state, ideal, counter, min_seats=None, exact_seats=seats, observe=observe
        )
        _kick(state, rng, 3, counter, min_seats=None, exact_seats=seats)
    return best


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def _check_party(party: str) -> str:
    if not isinstance(party, str) or party.upper() not in PARTIES:
        raise ValueError(f"target_party must be one of {PARTIES}; got {party!r}")
    return party.upper()


def _check_inputs(adjacency, populations, dem, rep, k, epsilon, work_epsilon) -> None:
    units = set(adjacency)
    if not units:
        raise ValueError("adjacency is empty")
    for name, mapping in (("populations", populations), ("dem", dem), ("rep", rep)):
        missing = units - set(mapping)
        extra = set(mapping) - units
        if missing or extra:
            raise ValueError(
                f"{name} does not cover the unit graph: {len(missing)} missing, "
                f"{len(extra)} unknown"
            )
    if int(k) != k or k < 2:
        raise ValueError(f"k must be an integer >= 2; got {k!r}")
    if k > len(units):
        raise ValueError(f"k={k} exceeds the {len(units)} units available")
    if not 0 < epsilon < 1:
        raise ValueError(f"epsilon must lie in (0, 1); got {epsilon!r}")
    if not epsilon <= work_epsilon < 1:
        raise ValueError(
            f"work_epsilon must satisfy epsilon <= work_epsilon < 1; got "
            f"{work_epsilon!r} against epsilon={epsilon!r}"
        )
    for unit, neighbours in adjacency.items():
        for other in neighbours:
            if other not in units:
                raise ValueError(f"adjacency of {unit} names unknown unit {other}")
            if unit not in set(adjacency[other]):
                raise ValueError(
                    f"adjacency is not symmetric: {other} in adjacency[{unit}] but "
                    f"not the reverse"
                )


def _party_seats(plan: Plan, dem, rep, party: str) -> int:
    counts = seat_counts(plan, dem, rep)
    return counts[0] if party == "D" else counts[1]


def _shares_for(plan: Plan, dem, rep, party: str) -> dict[int, float]:
    shares = district_shares(plan, dem, rep)
    if party == "D":
        return shares
    return {d: 1.0 - s for d, s in shares.items()}


def _derive(seed: int, purpose: str, index: int) -> int:
    """Deterministic sub-seed. Mirrors ``generate.seeds.derive``; see above."""
    payload = bytearray()
    for field_bytes in (
        _SEED_DOMAIN,
        str(int(seed)).encode("ascii"),
        purpose.encode("utf-8"),
        str(int(index)).encode("ascii"),
    ):
        payload += len(field_bytes).to_bytes(8, "big")
        payload += field_bytes
    digest = hashlib.blake2b(bytes(payload), digest_size=8).digest()
    return int.from_bytes(digest, "big") >> 1
