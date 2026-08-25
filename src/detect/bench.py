"""Headless bench: N seeded scenarios in, ``bench-results.json`` plus plots out.

``prompt.md``: *"Headless bench: runs N seeded scenarios, writes
bench-results.json plus plots to disk. Deterministic. This is what critics read.
Never screenshot a live interface for scoring."* So there is no interactive path
here, nothing is sampled from an unseeded source, and every number that reaches
the report came from a function in ``generate``, ``evaluate``, ``adversarial``
or ``detect`` rather than from this file. This module is plumbing and bookkeeping
by design: a bench that computes its own metrics is a second implementation free
to disagree with the first.

Run it::

    python -m detect.bench --master-seed 20260818 --round 1 [--quick]

What it does, in order
----------------------

1. **Neutral ensemble** at the measured operating point (FEASIBILITY.md 5.1:
   ``epsilon=2e-4``, ``node_repeats=0``) via ``generate.ensemble.run_chains``.
   Chain failures are counted and reported, never retried — ARCHITECTURE.md 7.
2. **Convergence**: rank-normalized split R-hat and ESS
   (``generate.convergence``) on **both** cut edges and population spread.
3. **Scenarios**, regenerated every round from ``seeds.derive(master_seed,
   purpose, index)`` where every ``purpose`` carries the round number, so round 2
   is a fresh draw rather than the round-1 set re-scored.
4. **Scoring** with ``detect.outlier`` (a percentile per metric) and
   ``detect.confusion`` (one printable rule, then the matrix and the curve).
5. ``bench-results.json`` to ARCHITECTURE.md 5, including the gates block and a
   firewall block carrying ``tools/check_firewall.py``'s verdict and a sha256 of
   ``tools/firewall.yaml``.
6. Five PNGs to the round's directory.

Three choices this file makes, which are the bench's and nobody else's
---------------------------------------------------------------------

**The decision rule is fixed before the run and restricted to the partisan
metrics.** :data:`RULE` is ``confusion.Rule`` with the module's own defaults
(0.99, two-sided, "any", untrusted excluded) plus ``metrics=partisan.METRICS``.
Compactness and administrative metrics are *measured, reported and plotted for
every scenario* but are not eligible to fire. The reason is arithmetic and is
stated in ``confusion.Rule``: under "any", each eligible metric adds roughly
``2(1-t)`` to the nominal false-positive rate, so putting five compactness
columns into the rule would add about 10 points of nominal FPR against a gate of
5. The counter-argument is real — a seat-maximising search is compactness-blind
and its plans are visibly ragged, so compactness carries signal — and it is
answered by *reporting* the alternative rules under ``diagnostics.
alternative_rules`` rather than by adopting whichever scores best. Picking the
rule after seeing the matrix is the one move that would make every number here
meaningless.

**Planted magnitudes are measured against two fixed, named baselines, not
against a per-seed random one.** ``adversarial.gerrymander`` measures a seat
shift against a baseline plan, and if each plant drew its own neutral reference
the label "2-seat shift" would mean different things in different scenarios: a
plan handing the Democrats two seats is a 2-seat shift from a 0-seat baseline
and a 1-seat shift from a 1-seat baseline, while being the *same plan* as far as
the detector is concerned. Both baselines are therefore fixed for the round and
recorded in the report with their seat counts:

* ``enacted`` — Iowa's enacted CD118 map, which wins Republicans all four seats.
  D-favouring plants are measured from it.
* ``ensemble_max_d`` — the plan in this round's own neutral ensemble that wins
  Democrats the most seats, chosen deterministically. R-favouring plants are
  measured from it.

**Null cases come in two strata and both are reported.**
``adversarial.nulls.sample_nulls`` deliberately selects the neutral plans that
look *worst* — furthest from the ensemble's median seat count, then largest
efficiency gap. That is the Chen & Rodden case CRITERIA.md 5.4 describes and it
is the hardest possible negative: a plan chosen for being in the tail of the very
metric the rule reads. Scoring only those would report an FPR that is really a
statement about the selection rule. Scoring only uniformly drawn neutral plans
would report an FPR that is too easy. So the null set is half of each —
``null_geography_*`` and ``null_random_*`` — the gate reads the pooled rate as
CRITERIA.md 8 requires, and ``diagnostics.null_strata`` gives the two rates
separately so a reader can see which stratum the FPR came from.

Five more, added in round 3 because the round-2 artifact could not be checked
----------------------------------------------------------------------------

**Every scenario carries its plan.** Round 2 published a legality claim, a
realized seat shift and a seat count per scenario and shipped nothing anyone
could recompute them from. Round 3 writes each scenario's assignment to
``plans/<scenario id>.csv`` in the round directory, in the exact
``GEOID,district`` form ARCHITECTURE.md 3 defines, and records in the report a
``plan.digest`` (``outlier.plan_digest``) plus the seed and purpose string the
plan was derived from. ``python -m detect.bench --verify <round dir>`` re-reads
the pair and re-derives every ground-truth claim in it. That checks the report
against its own plans -- transcription, a stale number, the wrong baseline -- and
not the code against reality: a bug shared by the bench and the verifier is
invisible to both, and the sidecar exists so that a critic can use neither.

**Legality is measured at the operating epsilon, whatever epsilon the run used.**
Round 1 ran the search at 1e-3, reported ``legal_compliance = 1.0``, and 7 of its
10 plans were illegal at the declared operating point of 2e-4. A gate that moves
with the size of the run is not a gate. :data:`GATE_EPSILON` is the operating
value and the gate is always read there; the run's own epsilon is measured too
and reported beside it, so a quick run now shows the honest failure rather than a
pass it did not earn.

**Compactness is part of that claim, and the standard is a value choice.** Iowa
Code ch. 42's fourth criterion is compactness and round 2's ``check_legality``
did not test it, so plans with a third the Polsby-Popper of every neutral draw
came back compliant. The statute states no number, so one had to be chosen; see
:func:`compactness_floor` for what was chosen and what it costs.

**A quick run says so in the gates block.** ``Size``'s docstring has said since
round 1 that a smoke run's gate values are not meaningful; the artifact said
nothing, and a reader of round 1's gates saw two PASSes, one of which a constant
detector ties. ``gates.qualification`` now carries that verdict, its reasons and
its measured caveats, every gate carries ``meaningful``, the stdout report leads
with it, and the confusion plot is stamped with it. See :func:`gate_qualification`
for what makes a run unmeaningful and — as importantly — what does not.

**The ensemble budget is a measured trade, and the R-hat gate is out of reach at
the operating epsilon.** ``FULL`` is 24 chains x 500 draws, about nine times
round 2's reference, sized to roughly twenty minutes on four cores with
:func:`run_chains_parallel`. That budget buys percentile resolution and it does
not buy convergence, because at ``epsilon=2e-4`` the chains do not mix. Measured
directly: 8 chains of 1,500 draws leave cut-edge split R-hat at 1.45,
non-monotone, with bulk ESS 9.8 — against 8.7 at the first checkpoint, so
nineteen times the draws bought one effective draw. The same sampler at
``epsilon=1e-3`` loses no chains and reaches R-hat 1.07 with ESS 89 and still
climbing. **The CRITERIA.md 8 band of 1.00-1.01 is therefore not reachable at the
operating epsilon at any budget this project could spend, and the binding
constraint is the population tolerance the legal standard requires rather than
the number of draws.** That is a finding about the sampler and the gate together.
The gate is not moved and no threshold is tuned; it fails, and
``gates.split_rhat.trend`` carries the evidence in the artifact.
:class:`Size` carries the costs, ``gates.split_rhat.trend`` carries this run's own
version of the measurement, and nothing here was sized to make the gate pass.

One more, added in round 4: the ground truth's shape constraint is now the
instrument that works
---------------------------------------------------------------------------

Round 3 constrained the planted search to a **central quantile band** of the
neutral ensemble's compactness distribution, and an independent measurement — an
agent that saw none of the implementation and regenerated plans from the
committed code — put the result at non-partisan AUC **0.890**, against D-010's
target of 0.5. The same module exported ``envelope_around_plan``, which that
measurement scored at 0.52-0.56, in ``__all__`` and called it from nowhere in
``src/``: the good instrument was in the box and the shipped path used the other
one.

:class:`AnchorPool` closes that. Every plant is now built inside its own
envelope, anchored on one independently drawn neutral plan and ``MATCH_WIDTH``
interquartile ranges wide, and the anchor is drawn from a seed that knows nothing
about the outcome. The band is still computed and still in the artifact, under
``diagnostics.plant_envelope.band_comparison``, because comparing the two
instruments on one reference is the measurement — but it is no longer what the
search runs inside. The reason a band cannot work, stated so it can be checked:
inside a band the seat objective is near-monotone in raggedness, because
raggedness is what buys seats, so the plants pile against the band's ceiling and
their marginal is a point mass at the edge of the neutral one rather than a
sample of it.

**The cost is yield and it is reported, never traded away.** A matched envelope
bounds five measures around one draw, and three of them cannot be maintained
incrementally, so a repaired plan is checked against them only at the end and may
be rejected. ``diagnostics.planting_attempts`` records every attempt with the
anchor it drew, and ``diagnostics.achievable_range`` reports the yield per
magnitude. A magnitude nothing reached is published as a magnitude nothing
reached; it is never retried from a friendlier anchor and the constraint is never
loosened to keep the yield.

Determinism
-----------

Same ``--master-seed`` and ``--round`` produce a byte-identical
``bench-results.json`` except for the ``timing`` block, which is the *only*
place a wall-clock number appears: chain seconds, search seconds, phase seconds
and the generation timestamp all live there, so ``diff`` on everything else is
meaningful. There is a test.

The null pool is drawn from its own seeds, independent of the reference
ensemble, so a null case is not scored against an ensemble it is a member of.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from adversarial import gerrymander as G
from adversarial import nulls as N
from detect import confusion as C
from detect import outlier as O
from evaluate import administrative, compactness, elections, partisan
from evaluate import plan as EP
from generate import convergence, ensemble, seeds, units as GU

# --------------------------------------------------------------------------- #
# fixed configuration — the operating point, not a tunable
# --------------------------------------------------------------------------- #

#: ARCHITECTURE.md 5.
SCHEMA_VERSION = 1

@dataclass(frozen=True)
class StateConfig:
    """Everything that differs between target states.

    Introduced for round 4. Until then the bench was hardcoded to Iowa, which was
    correct while Iowa was the only target and became a defect the moment it was
    not: a second state exposes every assumption the first one let pass silently.

    ``gate_magnitude`` is the seat shift the TPR gate is stated at, and it is
    per-state by DECISIONS D-013: detection magnitude is measured in units of the
    neutral distribution's own spread, not in absolute seats. ``null_spread`` is
    the measured width of that distribution, carried here so the artifact can say
    whether a requested magnitude is *unreachable* rather than merely failed.
    """

    key: str
    unit_kind: str
    k: int
    epsilon: float
    gate_magnitude: int
    null_spread: int
    prefix: str
    epsilon_note: str

    @property
    def units_csv(self): return PROCESSED / f"{self.prefix}_units.csv"
    @property
    def units_gpkg(self): return PROCESSED / f"{self.prefix}_units.gpkg"
    @property
    def adjacency_json(self): return PROCESSED / f"{self.prefix}_adjacency.json"
    @property
    def elections_csv(self): return PROCESSED / f"{self.prefix}_elections.csv"
    @property
    def enacted_csv(self): return PROCESSED / f"{self.prefix}_enacted_cd118.csv"


IOWA = StateConfig(
    key="IA", unit_kind="county", k=4, epsilon=2e-4,
    # Measured: the neutral ensemble spans 0-2 D seats of 4 (docs/progress.md).
    # A 2-seat gate asks the detector to separate an outcome from its own null,
    # so the smallest magnitude that is even in principle detectable is 3.
    gate_magnitude=3, null_spread=2, prefix="ia",
    epsilon_note="whole counties reach near-zero deviation; FEASIBILITY.md 5.1",
)

COLORADO = StateConfig(
    key="CO", unit_kind="vtd", k=8, epsilon=1e-2,
    # Measured: 4-6 D seats of 8, spread 2 - the SAME absolute null as Iowa.
    # Eight districts buy headroom above the floor, not a narrower floor.
    gate_magnitude=3, null_spread=2, prefix="co",
    epsilon_note=(
        "whole-VTD units cannot reach Karcher-tight (DECISIONS D-015); this "
        "epsilon is a modelling choice, not the legal standard"
    ),
)

STATES = {"IA": IOWA, "CO": COLORADO}

#: Rebound by :func:`configure`. Module-level so the many read sites stay
#: readable; every one of them reads at call time, not import time.
ACTIVE = IOWA
STATE = ACTIVE.key
UNIT_KIND = ACTIVE.unit_kind
K = ACTIVE.k
EPSILON = ACTIVE.epsilon

#: FEASIBILITY.md 5.1: a positive value re-roots an already-exhausted spanning
#: tree and the chain dies. Not a tunable; 0 is the only correct value here.
NODE_REPEATS = 0

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = REPO_ROOT / "data" / "processed"
FIREWALL_CONFIG = REPO_ROOT / "tools" / "firewall.yaml"
FIREWALL_SCRIPT = REPO_ROOT / "tools" / "check_firewall.py"
DEFAULT_OUT_ROOT = REPO_ROOT / "docs" / "progress"

#: The metrics located against the ensemble. The partisan four are
#: ``evaluate.partisan.METRICS``; the compactness five are the per-plan
#: summaries ``evaluate.compactness.metric_series`` produces (unweighted mean
#: over districts, plus the whole-plan cut-edge count); the administrative three
#: are here precisely because Iowa makes them degenerate — units are counties,
#: so ``county_splits`` is 0 for every plan that exists (FEASIBILITY.md 5.3) and
#: ``outlier.locate`` must refuse them a percentile rather than report 0.5.
PARTISAN_METRICS: tuple[str, ...] = tuple(partisan.METRICS)
COMPACTNESS_METRICS: tuple[str, ...] = tuple(
    f"{name}_mean" if name in compactness.SHAPE_MEASURES else name
    for name in compactness.MEASURES
)
ADMIN_METRICS: tuple[str, ...] = ("county_splits", "split_pieces", "ballot_styles")
LOCATED_METRICS: tuple[str, ...] = (
    PARTISAN_METRICS + COMPACTNESS_METRICS + ADMIN_METRICS
)

#: The decision rule of record, fixed before the run. See the module docstring
#: for why it is restricted to the partisan metrics, and
#: ``diagnostics.alternative_rules`` in the report for what the other rules score
#: on the same scenarios.
RULE = C.Rule(
    threshold=0.99,
    tail="two_sided",
    combination="any",
    metrics=PARTISAN_METRICS,
    untrusted="exclude",
    min_n=O.MIN_ENSEMBLE,
    name="partisan-any-99",
)

#: Rules scored beside the rule of record and reported, never substituted for
#: it. ``always``/``never`` are here because each passes exactly one gate, which
#: is the asymmetry CRITERIA.md 8 means by "null cases are as important as
#: positive cases".
ALTERNATIVE_RULES: tuple[C.Rule, ...] = (
    C.Rule(
        threshold=0.99,
        metrics=PARTISAN_METRICS + COMPACTNESS_METRICS,
        name="partisan+compactness-any-99",
    ),
    C.Rule(threshold=0.95, metrics=PARTISAN_METRICS, name="partisan-any-95"),
    C.Rule(
        threshold=0.99,
        combination="named",
        metrics=("efficiency_gap",),
        name="efficiency-gap-alone-99",
    ),
    C.ALWAYS_FLAG,
    C.NEVER_FLAG,
)

#: CRITERIA.md 8: PSRF target band is 1.00-1.01.
RHAT_GATE = 1.01

#: The epsilon the ``legal_compliance`` gate is read at, **always**, whatever
#: epsilon the run itself used. It is :data:`EPSILON`, the declared operating
#: point, and it is a separate name because the two roles are separate: a run
#: may legitimately be cheaper than the operating point (``--quick``), and a
#: legality claim may not be looser than it. Round 1 reported 1.0 at 1e-3 while
#: 7 of its 10 plans were illegal at 2e-4; measuring the gate here is what stops
#: that from being expressible.
GATE_EPSILON = EPSILON

#: **VALUE.** How much of the neutral ensemble's compactness distribution the
#: planted search is confined to (docs/DECISIONS.md D-010). The number is
#: ``adversarial.gerrymander.DEFAULT_SHAPE_COVERAGE`` and the argument for it is
#: that constant's; the bench does not get a second opinion. It is written here
#: rather than imported because the bounds are built from ``outlier.summarize``'s
#: ``p05``/``p95`` over reference columns that have already been measured --
#: ``calibrate_shape_envelope`` re-measures every plan it is given, at 166 ms
#: each, which is 11 minutes on a 4,000-draw reference and would be the single
#: largest line in the budget. ``diagnostics.plant_envelope.matches_module_default``
#: reports whether the two are still the same number.
PLANT_SHAPE_COVERAGE = 0.90

#: **VALUE.** The half-width, in reference interquartile ranges, of the envelope
#: each plant is actually built inside (``gerrymander.DEFAULT_MATCH_WIDTH``).
#: This is the constraint the shipped path now runs; :data:`PLANT_SHAPE_COVERAGE`
#: above is retained only as the reported comparison, because the band it
#: describes is the instrument round 3 measured at AUC 0.89 and the frontier
#: against it is the finding.
#:
#: **Why the search anchors on one draw instead of on the ensemble.** Both are
#: calibrated from the neutral ensemble and neither is a hand-picked constant, so
#: the choice is not about provenance; it is about what D-010 asks for. D-010
#: asks that the planted plans be *indistinguishable* from neutral maps on
#: non-partisan metrics, which is a statement about two distributions, not about
#: a feasible set. A central band is a feasible set: inside it the search's
#: objective is very nearly monotone in raggedness, because raggedness is what
#: buys seats, so every plant ends up against the band's upper edge and the
#: planted marginal is a point mass at the ceiling of the neutral one. That is
#: separable at AUC ~0.9 no matter how the band's width is set — measured in
#: round 3's frontier, where tightening the band bought separability only by
#: destroying yield. Anchoring each plant on an independently drawn neutral plan
#: makes the planted marginal the neutral marginal convolved with a bounded
#: perturbation: the plants inherit the reference's own spread instead of
#: piling at its edge, which is what AUC 0.5 requires.
#:
#: **The cost, named.** The perturbation is bounded but not zero, so the planted
#: distribution is the neutral one *blurred* by up to ``MATCH_WIDTH`` IQRs, which
#: inflates its variance slightly. A width of 0 would remove even that, and would
#: also demand that the planted plan match the anchor's shape exactly on five
#: measures, which is unsatisfiable. So the width trades a small variance
#: inflation against feasibility, and it is a `VALUE` choice for the same reason
#: the coverage was: nobody can derive it.
MATCH_WIDTH = G.DEFAULT_MATCH_WIDTH

#: The null strata drawn, in report order, and the subset the FPR gate pools.
#: See :func:`null_cases` for the argument; ``seat_outcome`` is drawn, scored
#: and published, and is excluded from the gate because it is selected by very
#: nearly the statistic the detector thresholds.
NULL_STRATA: tuple[str, ...] = ("concentration", "seat_outcome", "random")
GATE_NULL_STRATA: tuple[str, ...] = ("concentration", "random")

#: Sidecar directory, inside the round directory, holding one CSV per scenario
#: plan in the ``GEOID,district`` form of ARCHITECTURE.md 3.
PLANS_DIRNAME = "plans"

#: Default worker processes. Chains and plants are independent and the box has
#: four cores; the results do not depend on this number and there is a test.
DEFAULT_JOBS = min(4, os.cpu_count() or 1)


@dataclass(frozen=True)
class Size:
    """How big a run is. ``FULL`` is the committed artifact; ``QUICK`` is a smoke test.

    Every field is a cost/resolution trade and none of them is a threshold: no
    gate moves because a run was made larger, it only becomes better measured.
    ``QUICK`` also loosens ``epsilon``, which is the one place the two sizes
    differ in kind rather than in amount. The reason is not the mean cost per
    step — that is about half a second either way — but the variance: at 2e-4
    the ReCom proposal regularly exhausts its balanced-cut budget, and a single
    unlucky seed can hold a 14-step chain for minutes before it either recovers
    or dies. FEASIBILITY.md 5.1 measures the same fragility from the other side,
    as a 13% seed failure rate at this epsilon. A test suite cannot carry that
    tail. ``config.epsilon`` and ``config.size`` both record what actually ran,
    so a quick run can never be mistaken for a real one — and its gate values
    are not meaningful in any case, since an ensemble that small cannot support
    a percentile at the rule's threshold. ``meaningful_gates`` carries that
    statement into the artifact instead of leaving it in this docstring, which
    is where round 2 left it while the file itself showed two PASSes.

    **What ``FULL`` costs, measured.** On the four-core box this was built on, at
    ``epsilon=2e-4`` with ``jobs=4``: 8 chains x 1,500 steps took 506 s of wall
    clock for 7,500 completed draws, and 8 x 500 took 201 s. Measuring the
    reference columns costs a further 20 ms per draw. ``FULL`` at 24 x 500 is
    about 9 minutes of ensemble, 2 of columns, 2 of the null pool, 5 of planting
    and 2 of everything else — roughly 20 minutes uncontended, which is the
    budget this was sized to, and about nine times round 2's 806-draw reference.

    **Chain failure at this epsilon is an initialization failure, not a death in
    flight.** The same 3 of 8 seeds failed at both 500 and 1,500 steps, at 0 and
    5 draws in, with "could not find a balanced cut"; every seed that got past
    the start ran to whatever length it was asked for. So the failure rate is a
    property of the seed and the epsilon rather than of the budget, and longer
    chains cost nothing in extra failures. It is still not a random subset of
    seeds and is still reported (ARCHITECTURE.md 7).

    **Why the extra draws went into chains rather than steps.** They buy
    resolution, not convergence. Measured at ``epsilon=2e-4`` over 8 chains of
    500 draws, split R-hat on cut edges is 2.32 at 25 draws per chain, 1.73 at
    125, and 1.67 at 425 — flat from about 200 on — while bulk ESS sits between
    6.5 and 8.9 and does not grow. One chain of the eight visited 6 distinct
    plans in 500 draws. The chains are not slow to mix so much as stuck, so
    lengthening them adds draws to a region a chain has already exhausted, while
    starting another chain adds a region. More chains also widen the reference,
    which is what the detector's resolution test reads: ``confusion.Rule`` needs
    50 distinct plans and an effective sample of 50 before it will evaluate a
    0.99 threshold at all, and that is a count of plans, not of draws.

    **The measurement that settles whether more draws would ever be enough.** At
    ``epsilon=2e-4``, 8 chains of 1,500 draws — 7,500 completed draws, nine times
    round 2's reference — cut-edge split R-hat runs 1.60, 1.71, 1.66, 1.53, 1.50,
    1.54, 1.45 across the run: non-monotone, and 1.45 at the end against a gate
    of 1.01. Bulk ESS over those 7,500 draws is 9.8, against 8.7 at the first
    checkpoint: nineteen times the draws bought one effective draw. One surviving
    chain visited 12 distinct plans in 1,500 draws while another visited 282, so
    the chains are sitting in different regions rather than mixing slowly through
    one.

    **What the same sampler does at a looser tolerance, for contrast.** At
    ``epsilon=1e-3``, 8 chains of 2,000 draws: no chain dies, cut-edge R-hat
    falls 1.20 → 1.12 → 1.07 across the run with ESS reaching 89 and still
    growing, and population spread reaches R-hat 1.042 with ESS 596. So the
    1.00-1.01 band is approachable at 1e-3 and unreachable at the operating
    point, and the binding constraint is the population tolerance the legal
    standard requires rather than the number of draws anyone can afford.
    ``QUICK`` runs at 1e-3 for cost, not for this reason, and its gate values are
    marked unmeaningful regardless.

    The R-hat gate is discussed at ``gates.split_rhat``; nothing here is sized to
    make it pass.
    """

    label: str
    epsilon: float
    chains: int
    steps: int
    null_chains: int
    null_steps: int
    replicates: int
    magnitudes: tuple[int, ...]
    probe_magnitudes: tuple[int, ...]
    probe_replicates: int
    n_hard_nulls: int
    n_random_nulls: int
    max_iterations: int
    restarts: int
    trace_checkpoints: int = 12
    #: False when this size cannot support the gates it computes. Copied into
    #: ``gates.qualification`` and read by no arithmetic anywhere.
    meaningful_gates: bool = True


def configure(key: str) -> StateConfig:
    """Point the bench at a state. Must be called before anything else reads a path.

    Rebinds the module globals rather than threading a config object through
    forty call sites: every read happens at call time inside a function, so the
    rebinding is visible everywhere, and the alternative is a diff large enough
    to hide a mistake in.
    """
    global ACTIVE, STATE, UNIT_KIND, K, EPSILON, GATE_EPSILON, FULL, QUICK
    try:
        ACTIVE = STATES[key.upper()]
    except KeyError:
        raise SystemExit(f"unknown state {key!r}; known: {sorted(STATES)}") from None
    STATE, UNIT_KIND, K = ACTIVE.key, ACTIVE.unit_kind, ACTIVE.k
    EPSILON = GATE_EPSILON = ACTIVE.epsilon
    FULL = replace(FULL, epsilon=EPSILON)
    QUICK = replace(QUICK, epsilon=max(EPSILON * 5, QUICK_EPSILON_FLOOR))
    return ACTIVE


QUICK_EPSILON_FLOOR = 1e-3


def gate_key() -> str:
    """The TPR gate's name, which carries the magnitude it is stated at.

    Per-state by DECISIONS D-013. Writing the magnitude into the key means an
    artifact cannot be compared against one measured at a different magnitude by
    accident -- the field names simply will not line up.
    """
    return f"tpr_at_{ACTIVE.gate_magnitude}seat"

FULL = Size(
    label="full",
    epsilon=EPSILON,
    chains=24,
    steps=500,
    null_chains=8,
    null_steps=250,
    replicates=8,
    magnitudes=(1, 2, 3),
    probe_magnitudes=(4,),
    probe_replicates=2,
    n_hard_nulls=12,
    n_random_nulls=12,
    max_iterations=40_000,
    restarts=4,
    meaningful_gates=True,
)

QUICK = Size(
    label="quick",
    epsilon=1e-3,
    chains=2,
    steps=14,
    null_chains=2,
    null_steps=12,
    replicates=1,
    magnitudes=(1, 2, 3),
    probe_magnitudes=(),
    probe_replicates=0,
    n_hard_nulls=3,
    n_random_nulls=3,
    max_iterations=4_000,
    restarts=2,
    trace_checkpoints=4,
    meaningful_gates=False,
)


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #

@dataclass
class Inputs:
    """Everything the bench reads from disk, loaded once.

    Two adjacency dictionaries and two population views are held on purpose:
    ``generate`` and ``evaluate`` each load their own (ARCHITECTURE.md 1), and
    the bench keeps both rather than passing one package's object to the other.
    :meth:`check` asserts they agree, which is the only place the duplication is
    allowed to be observed.
    """

    gen_adjacency: dict
    gen_populations: dict
    adjacency: dict
    populations: dict
    units: Any
    geometry: Any
    dem: dict
    rep: dict
    enacted: dict

    def check(self) -> None:
        if set(self.gen_adjacency) != set(self.adjacency):
            raise RuntimeError(
                "generate and evaluate loaded different unit sets; one of the "
                "two loaders is reading a different file"
            )
        if self.gen_populations != self.populations:
            raise RuntimeError(
                "generate and evaluate disagree about unit populations"
            )


def load_inputs() -> Inputs:
    """Load every input, each through its own package's sanctioned loader.

    ``geometry`` comes from ``generate.units.load_geometry`` because that is the
    only guarded geopackage loader in the repository and geometry is neutral
    data — the schema allowlist there permits exactly ``GEOID``, ``NAME``,
    ``pop`` and ``geometry``, so nothing partisan can arrive by this route.
    ``detect`` may import ``generate`` (tools/firewall.yaml).
    """
    gen_adjacency, gen_populations = ensemble.load_inputs(
        ACTIVE.units_csv, ACTIVE.adjacency_json
    )
    inputs = Inputs(
        gen_adjacency=gen_adjacency,
        gen_populations=gen_populations,
        adjacency=EP.load_adjacency(ACTIVE.adjacency_json),
        populations=EP.populations(ACTIVE.units_csv),
        units=EP.load_units(ACTIVE.units_csv),
        geometry=GU.load_geometry(ACTIVE.units_gpkg),
        dem={},
        rep={},
        enacted=EP.load_plan(ACTIVE.enacted_csv),
    )
    dem, rep = elections.two_party(elections.load_elections(ACTIVE.elections_csv))
    inputs.dem, inputs.rep = dict(dem), dict(rep)
    inputs.check()
    return inputs



# --------------------------------------------------------------------------- #
# running chains in parallel — the same chains, in less wall clock
# --------------------------------------------------------------------------- #

def _one_chain(args) -> ensemble.EnsembleResult:
    """Worker: exactly ``ensemble.run_chains`` on a single seed."""
    adjacency, populations, k, epsilon, steps, seed, node_repeats = args
    return ensemble.run_chains(
        adjacency, populations, k, epsilon, steps, [seed], node_repeats
    )


def run_chains_parallel(
    adjacency: Mapping[str, Sequence[str]],
    populations: Mapping[str, int],
    k: int,
    epsilon: float,
    steps: int,
    chain_seeds: Sequence[int],
    node_repeats: int,
    jobs: int,
) -> ensemble.EnsembleResult:
    """``ensemble.run_chains``, one process per chain, merged back in seed order.

    Chains are independent by construction — one seed each, no shared state — so
    this changes wall clock and nothing else. ``jobs <= 1`` calls
    ``ensemble.run_chains`` directly rather than taking a slower path to the same
    answer, and ``tests/test_bench.py`` asserts the two agree trace for trace on
    a real ensemble, because the merge below is the one piece of arithmetic the
    bench does that ``generate`` also does.

    The merge recomputes exactly four aggregates, all of them counts, and
    ``distinct_plans`` through ``ensemble.canonical`` — the same function
    ``run_chains`` uses, so the relabelling-equivalence question is answered in
    one place. ``seconds`` is wall clock for the whole group, which is what a
    reader of ``timing`` wants and is not comparable with a serial run's.
    """
    chain_seeds = list(chain_seeds)
    if jobs <= 1 or len(chain_seeds) == 1:
        return ensemble.run_chains(
            adjacency, populations, k, epsilon, steps, chain_seeds, node_repeats
        )
    payload = [
        (dict(adjacency), dict(populations), k, epsilon, steps, seed, node_repeats)
        for seed in chain_seeds
    ]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=min(jobs, len(payload))) as pool:
        results = list(pool.map(_one_chain, payload))
    seconds = time.perf_counter() - started

    traces = tuple(trace for result in results for trace in result.traces)
    plans = tuple(plan for trace in traces for plan in trace.plans)
    failures = sum(1 for trace in traces if not trace.completed)
    return ensemble.EnsembleResult(
        k=k,
        epsilon=epsilon,
        steps=steps,
        seeds=tuple(chain_seeds),
        plans=plans,
        n_requested=len(chain_seeds) * steps,
        n_completed=len(plans),
        chain_failures=failures,
        failure_rate=failures / len(chain_seeds),
        distinct_plans=len({ensemble.canonical(plan, k) for plan in plans}),
        traces=traces,
        seconds=seconds,
    )


# --------------------------------------------------------------------------- #
# shape envelopes — one for the search, one for the legality claim
# --------------------------------------------------------------------------- #

def _shape_summaries(columns: Mapping[str, Sequence[Any]]) -> dict[str, O.Distribution]:
    """``outlier.summarize`` of each envelope measure over the reference draws."""
    out: dict[str, O.Distribution] = {}
    for name in G.ENVELOPE_MEASURES:
        values = [float(v) for v in columns[name] if v is not None]
        if values:
            out[name] = O.summarize(values)
    return out


def plant_envelope(
    columns: Mapping[str, Sequence[Any]], *, n_draws: int, n_distinct: int, source: str
) -> G.ShapeEnvelope | None:
    """The shape bounds the planted search may not leave (D-010).

    The central ``PLANT_SHAPE_COVERAGE`` of the reference ensemble on each of
    ``gerrymander.ENVELOPE_MEASURES``, read off ``outlier.summarize``'s ``p05``
    and ``p95``. Round 2's planted plans had twice the cut edges and a third the
    Polsby-Popper of every neutral draw, so ``cut_edges > 60`` alone separated
    the classes at TPR 1.0 and FPR 0.0 without reading a single vote; this is the
    constraint that stops the bench from measuring the search's fingerprint
    instead of the gerrymander.

    **Since round 4 this is REPORTED and is not what the search runs inside.**
    It was the round-3 shipped constraint, and an independent measurement put the
    planted plans it produces at non-partisan AUC 0.89 against the neutral
    ensemble (D-011): a central band is a feasible set, and the seat objective is
    near-monotone in raggedness inside it, so every plant lands against the
    band's upper edge. :class:`AnchorPool` replaced it with one matched envelope
    per plant. The band stays in the artifact under
    ``diagnostics.plant_envelope.band_comparison`` because the comparison between
    the two instruments on the same reference is the measurement, and because a
    reader of round 3's numbers needs to see what changed.

    ``None`` when the reference has no draws to calibrate from.
    """
    summaries = _shape_summaries(columns)
    if len(summaries) != len(G.ENVELOPE_MEASURES):
        return None
    return G.ShapeEnvelope(
        coverage=PLANT_SHAPE_COVERAGE,
        bounds={name: (d.p05, d.p95) for name, d in summaries.items()},
        reference_plans=n_distinct,
        reference_draws=n_draws,
        measures=G.ENVELOPE_MEASURES,
        source=source,
        centre=0.5,
    )


def compactness_floor(
    columns: Mapping[str, Sequence[Any]],
    neutral_metrics: Sequence[Mapping[str, Any]],
    *,
    n_draws: int,
    n_distinct: int,
    source: str,
) -> G.ShapeEnvelope | None:
    """The compactness standard the legality claim is made against. **VALUE.**

    Iowa Code ch. 42 lists compactness fourth and states no number for it, so
    including it in ``check_legality`` means choosing one, and the choice is
    normative rather than technical. What is chosen here is a **one-sided floor**
    per measure: a plan is compact enough if it is no less compact than *both*

    * the least compact plan the neutral process produced anywhere this round —
      every reference draw and every published null case — and
    * Iowa's enacted CD118 plan.

    ``neutral_metrics`` is that second set: the already-measured metrics of the
    null cases and of the enacted plan. Both are fixed before any legality is
    computed and neither depends on the outcome, which is what keeps this from
    being a standard widened to admit whatever failed it. The nulls are in it
    because they are neutral draws from the same process at the same epsilon,
    drawn from a *different* pool than the reference, and a floor that fails them
    would be measuring the reference's sampling noise rather than compactness.

    Three properties follow, and each is the reason for a part of the rule.

    *One-sided*, from ``evaluate.compactness.DIRECTION``, because the statute
    asks for compact districts and a plan more compact than any neutral draw
    breaks no law. (The search envelope in :func:`plant_envelope` is two-sided
    for a different reason: conspicuousness in either direction is detectable,
    and D-010 is about not being separable.)

    *At the neutral extreme rather than at a quantile*, because a floor inside
    the neutral distribution fails neutral plans by construction — a central 95%
    band on five correlated measures excludes a few percent of the very draws it
    was built from — and a legality gate whose target is 1.0 would then be
    reporting the width of its own band rather than anything about legality. At the extreme, every plan the neutral process drew passes, and
    the check has bite only against something built by a different process. That
    is exactly the round-2 failure it exists to catch: those plants sat at 93-99
    cut edges against a neutral 46-55.

    *Widened to admit the enacted plan*, because a standard that condemns the map
    actually in force under ch. 42 is not a description of ch. 42. In Iowa this
    costs nothing and is verified to cost nothing: against round 2's 806-draw
    ensemble the enacted plan is strictly inside the observed range on all five
    measures (cut edges 51 in [41, 59], Polsby-Popper 0.333 in [0.248, 0.401],
    Reock 0.451 in [0.300, 0.488], Schwartzberg 1.751 in [1.633, 2.073], convex
    hull 0.743 in [0.637, 0.796]). It is in the rule so that the property holds
    in a state where it does not.

    **What this standard cannot do.** It is calibrated, so it moves with the
    ensemble: a larger reference finds a more ragged worst draw and the floor
    loosens. It is a floor at the extreme, so it certifies as legal anything the
    neutral process could have produced, which is a much weaker claim than "a
    court would accept this". And every plan in the calibration set passes it by
    construction, so a passing null is evidence of nothing. The bounds, the size
    of the set they came from and this note are all in the report;
    ``check_legality``'s per-plan record names the measure and the margin
    whenever the floor is what failed.

    ``None`` when there is nothing to calibrate from, in which case
    ``check_legality`` records that compactness was not tested rather than
    passing it silently.
    """
    summaries = _shape_summaries(columns)
    if len(summaries) != len(G.ENVELOPE_MEASURES):
        return None
    bounds: dict[str, tuple[float, float]] = {}
    for name, dist in summaries.items():
        direction = compactness.DIRECTION[name.replace("_mean", "")]
        others = [
            float(m[name]) for m in neutral_metrics if m.get(name) is not None
        ]
        if direction > 0:  # larger is more compact: bound below
            bounds[name] = (min([dist.minimum] + others), math.inf)
        else:  # larger is less compact: bound above
            bounds[name] = (-math.inf, max([dist.maximum] + others))
    return G.ShapeEnvelope(
        coverage=None,
        kind="one_sided_floor",
        bounds=bounds,
        reference_plans=n_distinct,
        reference_draws=n_draws,
        measures=G.ENVELOPE_MEASURES,
        source=source,
    )


def _inside(
    plans: Sequence[Mapping[str, int]],
    columns: Mapping[str, Sequence[Any]],
    envelope: G.ShapeEnvelope | None,
    k: int,
) -> list[dict]:
    """The distinct reference draws that already satisfy ``envelope``.

    Handed to the search as ``start_plans`` so that it begins inside the feasible
    set instead of walking in from a growth plan — the realistic adversary is a
    mapper editing a compact map, not one building outwards from nothing. The
    test is read off the columns already measured for these very draws, so it
    costs nothing and cannot disagree with the envelope's own arithmetic.
    """
    if envelope is None:
        return []
    out: list[dict] = []
    seen: set = set()
    for i, plan in enumerate(plans):
        metrics = {}
        for name in envelope.bounds:
            value = columns[name][i] if i < len(columns[name]) else None
            if value is not None:
                metrics[name] = float(value)
        if not envelope.contains(metrics):
            continue
        key = ensemble.canonical(dict(plan), k)
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(plan))
    return out


@dataclass(frozen=True)
class Anchor:
    """One plant's matched envelope, the neutral draw it is anchored on, and its starts."""

    index: int
    plan: dict
    envelope: G.ShapeEnvelope
    starts: list[dict]
    metrics: dict[str, float]

    def block(self) -> dict[str, Any]:
        """What goes in the scenario's provenance, so the anchor is checkable."""
        return {
            "reference_draw_index": self.index,
            "plan_digest": O.plan_digest(self.plan),
            "shape_metrics": dict(self.metrics),
            "bounds": {
                name: {"at_least": low, "at_most": high}
                for name, (low, high) in sorted(self.envelope.bounds.items())
            },
            "start_plans": len(self.starts),
        }


@dataclass(frozen=True)
class AnchorPool:
    """The reference draws a plant's shape envelope may be anchored on (D-010).

    **This is the shipped constraint since round 4, and the change is the round's
    primary fix.** Round 3 shipped the central-band envelope of
    :func:`plant_envelope`, measured it at non-partisan AUC 0.89, and left the
    instrument that reaches 0.5 — ``gerrymander.envelope_around_plan`` — exported
    and called from nowhere in ``src/``. The band is retained here as the
    reported comparison and is no longer what the search runs inside.

    :meth:`draw` picks one reference draw per plant, **uniformly over draws
    rather than over distinct plans**, and builds
    ``gerrymander.envelope_from_measurements`` around it. Draw weight is the
    choice, not distinct-plan weight, because the distribution a plant has to be
    a sample of is the one the detector's percentiles are taken over, and those
    are taken over draws (``outlier`` reads the columns as sampled). A ReCom
    chain repeats plans, so the two weightings differ materially: measured on
    Iowa, the median cut-edge count is 44 over 24,247 draws and 49 over the 2,217
    distinct plans among them.

    The anchor is drawn **before** the search runs and from a seed that knows
    nothing about the outcome, so no anchor is chosen for having worked. A
    magnitude that is unreachable from a given anchor is recorded as a failure of
    that attempt; it is not retried from a friendlier one, because retrying until
    a plant lands is exactly how a yield collapse gets hidden.
    """

    plans: tuple
    columns: Mapping[str, Sequence[Any]]
    series: dict[str, list[float]]
    eligible: tuple[int, ...]
    n_draws: int
    n_distinct: int
    source: str
    width: float = MATCH_WIDTH

    @classmethod
    def build(
        cls,
        plans: Sequence[Mapping[str, int]],
        columns: Mapping[str, Sequence[Any]],
        *,
        n_draws: int,
        n_distinct: int,
        source: str,
        width: float = MATCH_WIDTH,
    ) -> "AnchorPool | None":
        """``None`` when no reference draw carries all five measures."""
        series = {
            name: [float(v) for v in columns.get(name, ()) if v is not None]
            for name in G.ENVELOPE_MEASURES
        }
        if any(not values for values in series.values()):
            return None
        eligible = tuple(
            i
            for i in range(len(plans))
            if all(
                i < len(columns.get(name, ())) and columns[name][i] is not None
                for name in G.ENVELOPE_MEASURES
            )
        )
        if not eligible:
            return None
        return cls(
            plans=tuple(dict(p) for p in plans),
            columns=columns,
            series=series,
            eligible=eligible,
            n_draws=int(n_draws),
            n_distinct=int(n_distinct),
            source=source,
            width=float(width),
        )

    def draw(self, seed: int, k: int, limit: int) -> Anchor:
        """One anchor, its envelope, and up to ``limit`` feasible start plans.

        The anchor's own plan is always the first start, so the search begins
        feasible by construction — an envelope built around a plan cannot be
        empty, which is the property a narrow quantile window does not have. The
        remaining starts are other reference draws that happen to fall inside the
        same envelope; they add restart diversity and cost nothing, since the
        test is read off columns already measured.
        """
        index = random.Random(seed).choice(self.eligible)
        metrics = {
            name: float(self.columns[name][index]) for name in G.ENVELOPE_MEASURES
        }
        envelope = G.envelope_from_measurements(
            metrics,
            self.series,
            width=self.width,
            source=self.source,
            reference_plans=self.n_distinct,
            reference_draws=self.n_draws,
        )
        anchor_plan = dict(self.plans[index])
        starts = [anchor_plan]
        anchor_key = ensemble.canonical(anchor_plan, k)
        seen = {anchor_key}
        for i in self.eligible:
            if len(starts) >= limit:
                break
            if i == index:
                continue
            row = {name: float(self.columns[name][i]) for name in G.ENVELOPE_MEASURES}
            if not envelope.contains(row):
                continue
            plan = dict(self.plans[i])
            key = ensemble.canonical(plan, k)
            if key in seen:
                continue
            seen.add(key)
            starts.append(plan)
        return Anchor(
            index=index,
            plan=anchor_plan,
            envelope=envelope,
            starts=starts,
            metrics=metrics,
        )


def _in_gate_sample(case: "Case") -> bool:
    """Whether this case counts toward the gate rates. Planted always; nulls by stratum."""
    if case.kind != "null":
        return True
    return bool(case.provenance.get("in_gate_sample", True))


def _envelope_block(envelope: G.ShapeEnvelope | None, kind: str) -> dict[str, Any]:
    """An envelope as JSON. Infinite bounds are reported as absent, not as null."""
    if envelope is None:
        return {"calibrated": False, "kind": kind,
                "note": "no reference draws to calibrate from; nothing was checked"}
    bounds = {}
    for name, (low, high) in sorted(envelope.bounds.items()):
        bounds[name] = {
            "at_least": None if low == -math.inf else low,
            "at_most": None if high == math.inf else high,
        }
    return {
        "calibrated": True,
        "kind": kind,
        "construction": envelope.kind,
        "description": envelope.description,
        "coverage": envelope.coverage,
        "width_iqr": envelope.width,
        "centre": envelope.centre if envelope.kind == "central_band" else None,
        "bounds": bounds,
        "reference_draws": envelope.reference_draws,
        "reference_plans": envelope.reference_plans,
        "source": envelope.source,
        "measures": list(envelope.measures),
    }


# --------------------------------------------------------------------------- #
# legality — measured at the operating point, whatever the run used
# --------------------------------------------------------------------------- #

def legality_records(
    plan: Mapping[str, int],
    metrics: Mapping[str, Any],
    inputs: "Inputs",
    size: Size,
    floor: G.ShapeEnvelope | None,
) -> tuple[G.LegalityRecord, G.LegalityRecord]:
    """``(at GATE_EPSILON, at the run's epsilon)`` for one plan.

    Both, because they answer different questions and round 1 published the
    second under the first's name. The gate reads the first. The second is
    reported beside it so that a reader can see the difference the run's own
    tolerance made — at ``--quick``'s 1e-3 it is the difference between "legal"
    and "illegal by a factor of five on population".

    ``metrics`` supplies the compactness measures, which have already been
    computed for this plan; nothing is re-measured here.
    """
    shape = (
        {name: float(metrics[name]) for name in G.ENVELOPE_MEASURES
         if metrics.get(name) is not None}
        if floor is not None else None
    )
    at_gate = G.check_legality(
        dict(plan), inputs.adjacency, inputs.populations, K, GATE_EPSILON,
        shape_envelope=floor, plan_shape_metrics=shape,
    )
    if size.epsilon == GATE_EPSILON:
        return at_gate, at_gate
    at_run = G.check_legality(
        dict(plan), inputs.adjacency, inputs.populations, K, size.epsilon,
        shape_envelope=floor, plan_shape_metrics=shape,
    )
    return at_gate, at_run


def relegalize(
    cases: Sequence["Case"],
    inputs: "Inputs",
    size: Size,
    floor: G.ShapeEnvelope | None,
) -> None:
    """Re-check every case's legality once the compactness floor exists, in place.

    The floor is calibrated from the reference ensemble, which does not exist
    when a plant or a null is built, so legality is settled here for every case
    at once — one code path, one epsilon pair, one envelope, for planted and null
    alike. The record the search kept for itself is not what the gate reads.
    """
    for case in cases:
        at_gate, at_run = legality_records(case.plan, case.metrics, inputs, size, floor)
        case.legality_at_gate = at_gate
        case.legality_at_run = at_run


# --------------------------------------------------------------------------- #
# metrics for one plan, and for a whole ensemble
# --------------------------------------------------------------------------- #

def plan_metrics(
    plan: Mapping[str, int],
    inputs: Inputs,
    cache: compactness.MeasureCache | None = None,
) -> dict[str, Any]:
    """Every located metric for one plan, side by side, combined into nothing.

    Returns the union of ``partisan.all_metrics``, ``compactness.all_metrics``
    and the three administrative names, restricted to :data:`LOCATED_METRICS`,
    plus the seat counts a reader needs to interpret them. There is no summary
    key here and there is none anywhere downstream — ``prompt.md`` forbids a
    ``fairness_score()`` and this dict is the closest thing the bench has to one.
    """
    part = partisan.all_metrics(plan, inputs.dem, inputs.rep)
    comp = compactness.all_metrics(plan, inputs.geometry, inputs.adjacency, cache)
    admin = administrative.all_metrics(dict(plan), inputs.units)
    merged: dict[str, Any] = {}
    for name in LOCATED_METRICS:
        if name in part:
            merged[name] = part[name]
        elif name in comp:
            merged[name] = comp[name]
        else:
            merged[name] = admin.get(name)
    merged["dem_seats"] = part["dem_seats"]
    merged["rep_seats"] = part["rep_seats"]
    merged["tied_districts"] = part["tied_districts"]
    merged["dem_seat_share"] = part["dem_seat_share"]
    return merged


def ensemble_columns(
    plans: Sequence[Mapping[str, int]], inputs: Inputs
) -> tuple[dict[str, list[Any]], dict[str, float]]:
    """``{metric: [one value per draw]}`` over the reference ensemble.

    Plans are measured **in the order the sampler produced them**, which is what
    makes ``compactness.MeasureCache`` pay: ReCom changes two districts of four
    per step, so the other two dissolve to a geometry the cache already holds.
    The result is identical either way (there is a test in
    ``tests/test_compactness.py``); only the cost changes.

    Administrative metrics are not in these columns. They are constant over
    every plan on a county geography, so a column of them would be a point mass
    and ``outlier.locate`` refuses those a percentile anyway — via
    ``administrative_context``, which carries ``evaluate.administrative``'s own
    reason string instead of an empirical guess from a finite sample.
    """
    cache = compactness.MeasureCache()
    columns: dict[str, list[Any]] = {
        name: [] for name in PARTISAN_METRICS + COMPACTNESS_METRICS
    }
    for plan in plans:
        part = partisan.all_metrics(plan, inputs.dem, inputs.rep)
        comp = compactness.all_metrics(plan, inputs.geometry, inputs.adjacency, cache)
        for name in PARTISAN_METRICS:
            columns[name].append(part[name])
        for name in COMPACTNESS_METRICS:
            columns[name].append(comp[name])
    stats = dict(cache.stats())
    stats["n_plans"] = len(plans)
    return columns, stats


def context_for(plan: Mapping[str, int], inputs: Inputs) -> O.Context:
    """Trust and degeneracy context from ``evaluate``, merged.

    ``election_context`` marks which partisan metrics CRITERIA.md 5.1 says are
    reliable *in this plan's regime* — on a four-seat sweep that is the
    efficiency gap alone, and the rule of record then excludes the rest rather
    than resting a flag on a number the literature calls unreliable there.
    ``administrative_context`` marks every administrative metric degenerate on
    Iowa, with ``evaluate.administrative``'s own reason attached.
    """
    return O.election_context(dict(plan), inputs.dem, inputs.rep).merge(
        O.administrative_context(dict(plan), inputs.units)
    )


# --------------------------------------------------------------------------- #
# scenarios
# --------------------------------------------------------------------------- #

@dataclass
class Case:
    """One scored scenario on its way into the report.

    ``provenance`` is what makes the scenario reconstructible: the seed stream
    name, the index in it and the derived seed for a plant; the pool's seeds and
    the selection rank for a null. With the plan CSV beside it in the round
    directory and the digest in the report, every ground-truth claim about this
    case can be recomputed by someone who has the artifact and the master seed
    and does not trust either.

    Legality is held as two records rather than a boolean, and neither is filled
    in until :func:`relegalize` runs — see it for why.
    """

    id: str
    kind: str
    plan: dict
    intended_seat_shift: int
    realized_seat_shift: float | None
    target_party: str | None
    baseline: str | None
    metrics: dict
    locations: dict
    notes: tuple
    provenance: dict = field(default_factory=dict)
    legality_at_gate: Any = None
    legality_at_run: Any = None
    seconds: float = 0.0

    @property
    def digest(self) -> str | None:
        """``outlier.plan_digest`` of this case's assignment."""
        return O.plan_digest(self.plan)

    @property
    def legal(self) -> bool | None:
        """Legal at :data:`GATE_EPSILON`, the operating point. ``None`` until checked."""
        return None if self.legality_at_gate is None else self.legality_at_gate.passed

    @property
    def legal_failures(self) -> list:
        return [] if self.legality_at_gate is None else self.legality_at_gate.failures()

    def legality_block(self, size: Size) -> dict[str, Any]:
        """Both legality records, each naming the epsilon it was measured at."""
        gate, run = self.legality_at_gate, self.legality_at_run
        if gate is None:
            return {"checked": False,
                    "note": "legality was not evaluated for this case"}
        return {
            "checked": True,
            "gate_epsilon": GATE_EPSILON,
            "legal_at_gate_epsilon": gate.passed,
            "failures_at_gate_epsilon": gate.failures(),
            "run_epsilon": size.epsilon,
            "legal_at_run_epsilon": None if run is None else run.passed,
            "failures_at_run_epsilon": [] if run is None else run.failures(),
            "population_spread": gate.population_spread,
            "max_deviation_persons": gate.max_deviation_persons,
            "max_deviation_fraction": gate.max_deviation_fraction,
            "compactness_checked": "compactness_within_neutral_envelope" in gate.checks,
            "notes": dict(sorted(gate.notes.items())),
        }

    def scenario(self) -> C.Scenario:
        return C.Scenario(
            id=self.id,
            kind=self.kind,
            locations=self.locations,
            intended_seat_shift=self.intended_seat_shift,
            realized_seat_shift=self.realized_seat_shift,
            target_party=self.target_party,
            notes=self.notes,
        )


def _purpose(round_number: int, tail: str) -> str:
    """Seed stream name. The round is inside it, so scenarios regenerate.

    ``prompt.md``: "Regenerate scenarios with fresh random seeds every round so
    nothing overfits to a fixed case." Advancing ``--round`` changes every
    purpose string and therefore every derived seed, which is the mechanism
    ARCHITECTURE.md 7 specifies.
    """
    return f"round-{round_number}/{tail}"


def pick_max_dem_plan(plans: Sequence[Mapping[str, int]], inputs: Inputs) -> dict:
    """The ensemble plan winning Democrats the most seats, chosen deterministically.

    The R-favouring baseline. Ties are broken on the plan's own sorted
    assignment, so the choice does not depend on the order the sampler happened
    to emit equally-good plans in.
    """
    best_key = None
    best: dict | None = None
    for plan in plans:
        seats = partisan.seat_counts(plan, inputs.dem, inputs.rep)[0]
        key = (seats, tuple(sorted(plan.items())))
        if best_key is None or key > best_key:
            best_key, best = key, dict(plan)
    if best is None:
        raise RuntimeError("no plans in the ensemble to pick a baseline from")
    return best


def plant_cases(
    inputs: Inputs,
    baselines: Mapping[str, dict],
    master_seed: int,
    round_number: int,
    size: Size,
    anchors: "AnchorPool | None" = None,
) -> tuple[list[Case], list[dict]]:
    """Planted gerrymanders across the achievable seat-shift range, both directions.

    For each (direction, magnitude) cell, ``size.replicates`` independent seeds
    are handed to ``adversarial.gerrymander.plant_gerrymander``, which returns
    ``None`` when the magnitude is not reachable from that baseline. Every
    attempt is recorded in the returned attempt log whether it succeeded or not:
    the log *is* the measurement of the achievable range, and a magnitude that no
    seed reached is a fact about Iowa, not a gap in the report.

    The probe magnitudes exist for exactly that reason. Nothing is retried and no
    near miss is relabelled — ``plant_gerrymander`` guarantees
    ``realized - baseline == seat_shift`` on everything it returns.

    ``anchors`` supplies the shape constraint (D-010), one **matched envelope per
    plant** anchored on an independently drawn neutral plan; see
    :class:`AnchorPool` for why the anchor is a draw rather than a band. Each
    attempt records the anchor it was given whether or not the search reached the
    magnitude, so the yield at each magnitude is a measurement of the constraint
    rather than of which anchors happened to be lucky. ``None`` runs the
    unconstrained round-2 search, which is kept reachable because the comparison
    is the frontier result.
    """
    cases: list[Case] = []
    attempts: list[dict] = []
    plan_cache = compactness.MeasureCache()

    cells: list[tuple[str, str, int, int]] = []
    for party, baseline_id in (("D", "enacted"), ("R", "ensemble_max_d")):
        for magnitude in size.magnitudes:
            cells.append((party, baseline_id, magnitude, size.replicates))
        for magnitude in size.probe_magnitudes:
            if size.probe_replicates:
                cells.append((party, baseline_id, magnitude, size.probe_replicates))

    for party, baseline_id, magnitude, replicates in cells:
        baseline = baselines[baseline_id]
        for index in range(replicates):
            purpose = _purpose(round_number, f"plant/{party}/{magnitude}")
            seed = seeds.derive(master_seed, purpose, index)
            anchor = (
                None if anchors is None
                else anchors.draw(
                    seeds.derive(master_seed, purpose + "/anchor", index),
                    K,
                    max(size.restarts, 1),
                )
            )
            envelope = None if anchor is None else anchor.envelope
            started = time.perf_counter()
            result = G.plant_gerrymander(
                party,
                magnitude,
                inputs.adjacency,
                inputs.populations,
                inputs.dem,
                inputs.rep,
                K,
                size.epsilon,
                seed,
                size.max_iterations,
                baseline_plan=baseline,
                baseline_source=baseline_id,
                restarts=size.restarts,
                shape_envelope=envelope,
                geometry=None if envelope is None else inputs.geometry,
                start_plans=None if anchor is None else [dict(p) for p in anchor.starts],
            )
            seconds = time.perf_counter() - started
            case_id = f"gerry_{party.lower()}_{magnitude}seat_{index:02d}"
            provenance = {
                "seed": seed,
                "purpose": purpose,
                "index": index,
                "derivation": "generate.seeds.derive(master_seed, purpose, index)",
                "built_by": "adversarial.gerrymander.plant_gerrymander",
                "baseline": baseline_id,
                "shape_envelope": None if anchor is None else "matched",
                "shape_anchor": None if anchor is None else anchor.block(),
            }
            attempts.append(
                {
                    "id": case_id,
                    "target_party": party,
                    "baseline": baseline_id,
                    "intended_seat_shift": magnitude,
                    "seed": seed,
                    "reached": result is not None,
                    "shape_anchor_draw": None if anchor is None else anchor.index,
                }
            )
            if result is None:
                continue
            metrics = plan_metrics(result.plan, inputs, plan_cache)
            locations = O.locate(
                result.plan,
                {},  # columns are attached by the caller; see score_cases
                metrics,
                context=context_for(result.plan, inputs),
                metrics=LOCATED_METRICS,
            )
            cases.append(
                Case(
                    id=case_id,
                    kind="planted",
                    plan=dict(result.plan),
                    intended_seat_shift=magnitude,
                    realized_seat_shift=result.seat_shift,
                    target_party=party,
                    baseline=baseline_id,
                    metrics=metrics,
                    locations=locations,
                    provenance=provenance,
                    notes=(
                        f"baseline {baseline_id}: {result.baseline_seat_count} "
                        f"{party} seats -> {result.realized_seat_count}; "
                        f"population spread {result.population_spread}; "
                        f"seat ceiling at work epsilon "
                        f"{result.seat_ceiling_at_work_epsilon}",
                        f"search kept its own legality record at epsilon "
                        f"{size.epsilon:g}: " + (
                            "passed" if result.legality.passed
                            else "failed " + ", ".join(result.legality.failures())
                        ) + "; the report's legality is re-derived by "
                        "bench.relegalize at the operating epsilon",
                    ),
                    seconds=seconds,
                )
            )
    return cases, attempts


def null_cases(
    inputs: Inputs,
    pool: Sequence[Mapping[str, int]],
    master_seed: int,
    round_number: int,
    size: Size,
) -> list[Case]:
    """Neutral maps in three strata, all labelled ground-truth negative.

    ``adversarial.nulls.sample_strata`` fills them from one pool with the plans
    kept disjoint, so no plan is a negative twice:

    ``null_concentration_*``
        Distinct neutral plans ranked by the Herfindahl concentration of the
        minority party's own votes across districts — the Chen & Rodden packing
        CRITERIA.md 5.4 describes, measured on one party's totals and on no ratio
        between the two. Hard negatives by mechanism.
    ``null_seat_outcome_*``
        Ranked by distance from the ensemble's median seat count. Hard negatives
        by outcome, and in Iowa seats and the absolute efficiency gap are rank-correlated
        at -0.868, so this stratum selects very nearly what ranking by the
        detector's own test statistic selects.
    ``null_random_*``
        A uniform draw from the pool's distinct plans. The control: what a
        neutral process usually produces rather than what it produces at its
        worst.

    **Which of them the gate reads is this file's choice and it is a normative
    one.** ``sample_strata`` returns a dict rather than a pooled list precisely
    so that the caller has to make it. The gate pools *concentration* and
    *random* and excludes *seat_outcome*, because a stratum ranked by a monotone
    transform of the statistic under test measures the selection rule and not the
    detector — round 2 measured that stratum's rate rising to 1.00 as the pool
    grew while the control's fell to 0.125, with the reference held fixed. The
    excluded stratum is drawn, scored, published as a scenario and reported with
    its own rate; it is left out of one number, not out of the artifact, and
    ``confusion.gate_sample`` names it and says why. Reported beside it is the
    pooled rate over all three, so a reader who disagrees with the choice can
    read the number this file did not use.

    The pool is sampled under its own seeds, so no null is scored against an
    ensemble it is itself a draw from.
    """
    cases: list[Case] = []
    plan_cache = compactness.MeasureCache()
    drawn_by = (
        f"generate.ensemble.run_chains, {size.null_chains} independent chains x "
        f"{size.null_steps} steps at epsilon={size.epsilon:g}, seeded from "
        f"{_purpose(round_number, 'null-pool')}"
    )
    by_stratum = N.sample_strata(
        inputs.adjacency,
        inputs.populations,
        K,
        size.epsilon,
        (),
        inputs.dem,
        inputs.rep,
        sampler=N.sampler_from_plans(pool),
        n_per_stratum={
            "concentration": size.n_hard_nulls,
            "seat_outcome": size.n_hard_nulls,
            "random": size.n_random_nulls,
        },
        strata=NULL_STRATA,
        party="D",
        balance_directions=True,
        drawn_by=drawn_by,
        seed=seeds.derive(master_seed, _purpose(round_number, "null-random"), 0),
    )
    for stratum in NULL_STRATA:
        for case in by_stratum[stratum]:
            cases.append(
                _null_case(
                    case.id,
                    case.plan,
                    case.seat_shift,
                    inputs,
                    size,
                    plan_cache,
                    notes=(
                        f"stratum {case.stratum}, selection rank "
                        f"{case.selection_rank} of {case.distinct_pool_size} "
                        f"distinct plans in a pool of {case.pool_size}",
                        case.selection_rule,
                        f"ensemble median {case.ensemble_median_seats} D seats, "
                        f"this plan {case.realized_seat_count}",
                    ),
                    provenance={
                        "stratum": case.stratum,
                        "ensemble_median_seats": case.ensemble_median_seats,
                        "party": case.party,
                        "selection_rank": case.selection_rank,
                        "selection_statistic": dict(case.selection_statistic),
                        "distinct_pool_size": case.distinct_pool_size,
                        "pool_size": case.pool_size,
                        "purpose": _purpose(round_number, "null-pool"),
                        "derivation": (
                            "generate.seeds.stream(master_seed, purpose, "
                            "null_chains) -> generate.ensemble.run_chains -> "
                            "adversarial.nulls.sample_strata"
                        ),
                        "drawn_by": case.drawn_by,
                        "in_gate_sample": case.stratum in GATE_NULL_STRATA,
                    },
                )
            )
    return cases


def _null_case(
    case_id: str,
    plan: Mapping[str, int],
    seat_shift: float,
    inputs: Inputs,
    size: Size,
    cache: compactness.MeasureCache,
    notes: tuple,
    provenance: Mapping[str, Any] = (),
) -> Case:
    metrics = plan_metrics(plan, inputs, cache)
    return Case(
        id=case_id,
        kind="null",
        plan=dict(plan),
        intended_seat_shift=0,
        realized_seat_shift=float(seat_shift),
        target_party=None,
        baseline="ensemble_median",
        metrics=metrics,
        locations=O.locate(
            plan,
            {},
            metrics,
            context=context_for(plan, inputs),
            metrics=LOCATED_METRICS,
        ),
        provenance=dict(provenance),
        notes=notes,
    )


def reference_ids(plans: Sequence[Mapping[str, int]]) -> list:
    """One identity per reference draw, label-invariant, in column order.

    ``ensemble.canonical`` rather than a digest of the raw assignment, because
    two draws differing only in which district got which number are one plan and
    counting them twice overstates the reference's resolution. Handing these to
    ``outlier.locate`` is what makes ``Location.ess`` count plan repeats instead
    of value repeats: 806 draws holding 177 plans worth 11.7 independent ones is
    the number the rule's resolution test needs, and it is not visible from the
    column alone.
    """
    return [ensemble.canonical(dict(plan), K) for plan in plans]


def relocate(
    cases: Sequence[Case],
    columns: Mapping[str, Sequence[Any]],
    inputs: Inputs,
    plan_ids: Sequence[Any] | None = None,
) -> None:
    """Attach the real ensemble columns to every case's locations, in place.

    :func:`plant_cases` and :func:`null_cases` build their locations against an
    empty ensemble so that a plan can be measured the moment it is built. This
    is where the percentile actually happens, once, against the reference
    ensemble every scenario shares.
    """
    for case in cases:
        case.locations = O.locate(
            case.plan,
            columns,
            case.metrics,
            context=context_for(case.plan, inputs),
            metrics=LOCATED_METRICS,
            ensemble_plan_ids=plan_ids,
        )


# --------------------------------------------------------------------------- #
# convergence
# --------------------------------------------------------------------------- #

def convergence_block(result: ensemble.EnsembleResult) -> dict[str, Any]:
    """Rank-normalized split R-hat and ESS on cut edges and population spread.

    Both quantities, because they measure different things about the same chain:
    cut edges is the compactness-shaped coordinate the literature reports, and
    population spread is the coordinate the epsilon constraint acts on directly.
    A chain can mix in one and not the other.

    Computed over **completed chains only** — a diagnostic over chains needs a
    rectangle and a partial trace is not one — and the block says so, per
    ARCHITECTURE.md 5's requirement that every subset be named.
    """
    out: dict[str, Any] = {"sample": "completed_chains", "n_chains": len(result.completed_traces)}
    series = {
        "cut_edges": result.cut_edges_chains(only_completed=True),
        "pop_spread": result.population_spread_chains(only_completed=True),
    }
    for name, chains in series.items():
        out[name] = _diagnostics(chains)
    return out


def _diagnostics(chains: Sequence[Sequence[float]]) -> dict[str, Any]:
    """``{split_rhat, ess}``, or an explicit reason why neither could be computed."""
    usable = [c for c in chains if len(c) >= convergence.MIN_DRAWS]
    if len(usable) < 2:
        return {
            "split_rhat": None,
            "ess": None,
            "note": (
                f"{len(usable)} chain(s) of at least {convergence.MIN_DRAWS} "
                "draws; a between-chain statistic needs two"
            ),
        }
    try:
        rhat = convergence.split_rhat(convergence.truncate(usable))
        n_eff = convergence.ess(convergence.truncate(usable))
    except Exception as exc:  # a diagnostic that cannot be computed says so
        return {"split_rhat": None, "ess": None, "note": f"{type(exc).__name__}: {exc}"}
    return {
        "split_rhat": _finite(rhat),
        "ess": _finite(n_eff),
        "note": None if _finite(rhat) is not None else "degenerate: the quantity never varies",
    }


def convergence_trace(
    result: ensemble.EnsembleResult, checkpoints: int
) -> dict[str, list[dict[str, Any]]]:
    """Split R-hat and ESS recomputed on growing prefixes of the same chains.

    A single end-of-run R-hat says whether the chains agree; the trace says
    whether they were converging or wandering. Both are cheap once the chains
    are in memory, and the second is what a reader needs to judge the first.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for name, chains in (
        ("cut_edges", result.cut_edges_chains(only_completed=True)),
        ("pop_spread", result.population_spread_chains(only_completed=True)),
    ):
        rows: list[dict[str, Any]] = []
        if len(chains) >= 2:
            longest = min(len(c) for c in chains)
            for i in range(1, checkpoints + 1):
                cut = max(convergence.MIN_DRAWS, (longest * i) // checkpoints)
                if cut > longest:
                    break
                if rows and rows[-1]["draws_per_chain"] == cut:
                    continue
                diag = _diagnostics([c[:cut] for c in chains])
                rows.append(
                    {
                        "draws_per_chain": cut,
                        "split_rhat": diag["split_rhat"],
                        "ess": diag["ess"],
                    }
                )
        out[name] = rows
    return out


def rhat_trend(trace: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Was R-hat falling, or had it stopped? Read off this run's own trace.

    A single end-of-run R-hat cannot distinguish a chain that needs more draws
    from one that will never converge, and the difference decides whether the
    gate is a budget problem or a sampler problem. This reports, per quantity,
    the first and last checkpoint and the change between the last two, so the
    claim lives in the artifact rather than in a builder's summary of an
    experiment nobody else ran.
    """
    out: dict[str, Any] = {}
    for name, rows in trace.items():
        usable = [r for r in rows if r.get("split_rhat") is not None]
        if len(usable) < 2:
            out[name] = {"note": "fewer than two checkpoints with a value"}
            continue
        first, last, penultimate = usable[0], usable[-1], usable[-2]
        out[name] = {
            "first": {"draws_per_chain": first["draws_per_chain"],
                      "split_rhat": first["split_rhat"], "ess": first["ess"]},
            "last": {"draws_per_chain": last["draws_per_chain"],
                     "split_rhat": last["split_rhat"], "ess": last["ess"]},
            "change_over_last_checkpoint": last["split_rhat"] - penultimate["split_rhat"],
            "still_falling": last["split_rhat"] < penultimate["split_rhat"],
            "ess_still_growing": (
                last["ess"] is not None and penultimate["ess"] is not None
                and last["ess"] > penultimate["ess"]
            ),
        }
    return out


def _all_chain_convergence(result: ensemble.EnsembleResult) -> dict[str, Any]:
    """The same diagnostics over *every* chain, truncated to the shortest.

    ``convergence_block`` uses the completed chains, because a diagnostic over
    chains needs a rectangle and that is the honest rectangle to build. But at
    this epsilon a third of the seeds die, and a chain that died at draw 300 of
    400 still carries 300 legitimate draws whose disagreement with the others is
    evidence. This block is that second rectangle: shorter, wider, and reported
    beside the first rather than in place of it. The gate reads the first.
    """
    out: dict[str, Any] = {
        "sample": "all_chains_truncated_to_shortest",
        "n_chains": len(result.traces),
        "note": (
            "reported, not gated: gates.split_rhat reads the completed-chain "
            "rectangle. A chain here may be a partial trace"
        ),
    }
    for name, chains in (
        ("cut_edges", result.cut_edges_chains(only_completed=False)),
        ("pop_spread", result.population_spread_chains(only_completed=False)),
    ):
        usable = [c for c in chains if len(c) >= convergence.MIN_DRAWS]
        out[name] = _diagnostics(usable)
        out[name]["draws_per_chain"] = min((len(c) for c in usable), default=0)
        out[name]["n_chains_used"] = len(usable)
    return out


def _finite(x: float | None) -> float | None:
    """A real finite float, or ``None``. ``nan`` and ``inf`` are not measurements."""
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else x


def gate_qualification(
    size: Size,
    result: ensemble.EnsembleResult,
    columns: Mapping[str, Sequence[Any]],
    conv: Mapping[str, Any],
    matrix: Mapping[str, Any],
) -> dict[str, Any]:
    """Whether this run's gate values can be read as measurements at all.

    ``Size``'s docstring has said since round 1 that a quick run's gate values
    are not meaningful. The artifact said nothing, and a reader of round 1's
    gates block saw two PASSes — one of which a constant detector ties. This puts
    the statement in the file, next to the numbers it qualifies.

    ``meaningful`` is false when the run is a smoke test, or when the reference
    cannot express the rule's threshold: those are the two conditions under which
    a rate is not a measurement of the detector. It is deliberately *not* false
    merely because a gate failed, or because R-hat is above its band — those are
    findings, and burying them under "unmeaningful" would be a way of not
    reporting them. They appear in ``caveats``, which a reader must read and no
    arithmetic reads.

    Every reason names the number it was computed from.
    """
    reasons: list[str] = []
    caveats: list[str] = []

    if not size.meaningful_gates:
        reasons.append(
            f"size={size.label!r}: a smoke run, made at epsilon="
            f"{size.epsilon:g} against an operating point of {EPSILON:g}, with "
            f"{size.chains} chains x {size.steps} steps. Its gate values are "
            "arithmetic on too few draws, not measurements of the detector"
        )

    required_distinct = RULE.required_distinct
    if required_distinct is not None and result.distinct_plans < required_distinct:
        reasons.append(
            f"the reference holds {result.distinct_plans} distinct plans and the "
            f"{RULE.threshold} threshold needs {required_distinct} "
            "(confusion.Rule.required_distinct); no plan strictly inside the "
            "ensemble can reach the threshold, so the rule degenerates into a "
            "test of the observed support"
        )

    required_ess = RULE.required_ess
    ess_by_metric: dict[str, float | None] = {}
    for name in RULE.metrics or ():
        values = [float(v) for v in columns.get(name, []) if v is not None]
        ess_by_metric[name] = O.summarize(values).ess if values else None
    usable = [v for v in ess_by_metric.values() if v is not None]
    if required_ess is not None and usable and max(usable) < required_ess:
        reasons.append(
            f"the best effective sample size over the rule's own metrics is "
            f"{max(usable):.1f} against a requirement of {required_ess:.0f}; "
            "repeated draws are not independent evidence about a 1% tail"
        )

    worst_rhat = max(
        (conv[name]["split_rhat"] for name in ("cut_edges", "pop_spread")
         if conv[name]["split_rhat"] is not None),
        default=None,
    )
    if worst_rhat is not None and worst_rhat > RHAT_GATE:
        caveats.append(
            f"split R-hat is {worst_rhat:.4f} against a band of 1.00-{RHAT_GATE}: "
            "every percentile in this report is taken against chains that do not "
            "agree with each other, so the reference is a sample of the sampler's "
            "reachable set rather than of the neutral distribution"
        )
    if matrix.get("coverage") is not None and matrix["coverage"] < 1.0:
        caveats.append(
            f"the rule could be evaluated on {matrix['coverage']:.3f} of the gate "
            f"scenarios ({matrix['n_resolved']}/{matrix['n']}); pass is read off "
            "the bound that is worst for the rule, so abstentions cannot help it"
        )
    if result.failure_rate:
        caveats.append(
            f"{result.chain_failures} of {len(result.seeds)} chains died "
            f"(rate {result.failure_rate:.3f}); surviving seeds are not a random "
            "subset of attempted seeds (ARCHITECTURE.md 7)"
        )

    meaningful = not reasons
    return {
        "meaningful": meaningful,
        "size": size.label,
        "reasons": reasons,
        "caveats": caveats,
        "reference": {
            "draws": len(result.plans),
            "distinct_plans": result.distinct_plans,
            "required_distinct": required_distinct,
            "ess_by_rule_metric": ess_by_metric,
            "required_ess": required_ess,
        },
        "note": (
            "gate values on this run are measurements"
            if meaningful else
            "GATE VALUES ON THIS RUN ARE NOT MEANINGFUL — see gates.qualification.reasons"
        ),
    }


# --------------------------------------------------------------------------- #
# metric disagreement
# --------------------------------------------------------------------------- #

def disagreement_block(columns: Mapping[str, Sequence[Any]]) -> dict[str, Any]:
    """Spearman rank correlation within the compactness set and within the fairness set.

    CRITERIA.md 3 asks this as an `EMPIRICAL` question and says to answer it per
    state: if the compactness measures correlate above ~0.9 the choice between
    them does not matter here and we can say so; if they diverge the choice is
    doing real work and must be surfaced rather than resolved. ``prompt.md``
    adds the correctness reading — measures correlating above 0.95 across the
    board mean one measure implemented five times.

    Compactness series are oriented by ``compactness.DIRECTION`` first, so a
    positive number always means agreement and Schwartzberg's inverted scale is
    not read as a finding. The partisan metrics are **not** oriented by
    ``partisan.FAVOURS``: their sign conventions genuinely differ and forcing
    them into one direction would hide precisely the disagreement this block
    exists to show. Pairs are computed on the draws where both metrics are
    defined; declination is ``None`` wherever a plan sweeps every seat, and the
    count of dropped draws is reported with each pair.
    """
    out: dict[str, Any] = {}
    oriented = {
        name: [
            compactness.DIRECTION[name.replace("_mean", "")] * float(v)
            for v in columns[name]
        ]
        for name in COMPACTNESS_METRICS
    }
    out["compactness"] = {
        "oriented_by_direction": True,
        "pairs": _pairs(oriented, COMPACTNESS_METRICS),
        "note": (
            "schwartzberg is a monotone transform of polsby_popper per district, "
            "so that pair is near 1.0 whatever the geography and is not evidence"
        ),
    }
    out["fairness"] = {
        "oriented_by_direction": False,
        "pairs": _pairs({n: list(columns[n]) for n in PARTISAN_METRICS}, PARTISAN_METRICS),
        "note": (
            "signs are as evaluate.partisan.FAVOURS defines them and are not "
            "harmonised; a negative entry between two of these is a real "
            "disagreement about which party a plan favours"
        ),
    }
    return out


def _pairs(series: Mapping[str, Sequence[Any]], names: Sequence[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            xs, ys = [], []
            for x, y in zip(series[a], series[b]):
                if x is None or y is None:
                    continue
                xs.append(float(x))
                ys.append(float(y))
            dropped = len(series[a]) - len(xs)
            rho = compactness.spearman(xs, ys) if len(xs) >= 2 else float("nan")
            rows.append(
                {
                    "a": a,
                    "b": b,
                    "spearman": _finite(rho),
                    "n": len(xs),
                    "n_dropped_undefined": dropped,
                }
            )
    return rows


# --------------------------------------------------------------------------- #
# firewall
# --------------------------------------------------------------------------- #

def firewall_block() -> dict[str, Any]:
    """Run ``tools/check_firewall.py`` and record its verdict plus a config hash.

    The hash is the point as much as the verdict: ``tools/firewall.yaml`` is the
    file whose relaxation would invalidate every result in the report, so a
    reader comparing two rounds can see whether the boundary moved between them
    without taking anyone's word for it. Neither file is written by this module
    and neither may be.
    """
    digest = hashlib.sha256(FIREWALL_CONFIG.read_bytes()).hexdigest()
    completed = subprocess.run(
        [sys.executable, str(FIREWALL_SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    output = (completed.stdout + completed.stderr).strip()
    return {
        "clean": completed.returncode == 0,
        "exit_code": completed.returncode,
        "config_sha256": digest,
        "config": str(FIREWALL_CONFIG.relative_to(REPO_ROOT)),
        "output": output,
    }


# --------------------------------------------------------------------------- #
# the sidecar: the plans themselves, and re-deriving the claims made about them
# --------------------------------------------------------------------------- #

def write_plan(path: Path, plan: Mapping[str, int]) -> None:
    """One plan to CSV, in the two columns ARCHITECTURE.md 3 defines and no others.

    Sorted by unit id so the file is a function of the assignment alone, which is
    what makes it comparable with :func:`outlier.plan_digest` and diffable
    between rounds.
    """
    lines = ["GEOID,district"]
    lines += [f"{unit},{int(plan[unit])}" for unit in sorted(plan)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_plans(
    cases: Sequence[Case], baselines: Mapping[str, Mapping[str, int]], out_dir: Path
) -> dict[str, Any]:
    """Write every scenario and baseline plan beside the report. Returns the manifest.

    ARCHITECTURE.md 5 makes ``bench-results.json`` the file critics read, and
    round 2's version asserted a legality, a seat count and a realized seat shift
    per scenario while shipping nothing to check them against. These files are
    that missing half. They are gitignored with the rest of the round directory
    (docs/DECISIONS.md D-008) and regenerate deterministically from the master
    seed, which is the same standing the PNGs have.
    """
    plans_dir = out_dir / PLANS_DIRNAME
    plans_dir.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, Any]] = []
    for case in cases:
        write_plan(plans_dir / f"{case.id}.csv", case.plan)
        written.append({"id": case.id, "file": f"{PLANS_DIRNAME}/{case.id}.csv",
                        "digest": case.digest})
    for name, plan in sorted(baselines.items()):
        write_plan(plans_dir / f"baseline_{name}.csv", plan)
        written.append({"id": f"baseline_{name}",
                        "file": f"{PLANS_DIRNAME}/baseline_{name}.csv",
                        "digest": O.plan_digest(plan)})
    return {
        "directory": PLANS_DIRNAME,
        "format": "CSV, columns GEOID,district, sorted by GEOID (ARCHITECTURE.md 3)",
        "digest": "sha256 of 'GEOID:district;...' over sorted units, first 16 hex "
                  "(detect.outlier.plan_digest)",
        "n_files": len(written),
        "files": written,
        "verify": "python -m detect.bench --verify <this directory>",
    }


def verify(round_dir: Path) -> dict[str, Any]:
    """Re-derive every ground-truth claim in a written artifact from its own plans.

    Reads ``bench-results.json`` and the ``plans/`` sidecar beside it and checks,
    per scenario: the plan's digest against the one published; the structural
    invariants through ``evaluate.plan.validate``; every located metric and both
    seat counts, recomputed from the plan; legality at :data:`GATE_EPSILON`,
    including the compactness floor the run used, against the published verdict
    and its failure list; and the realized seat shift against the named baseline
    plan, also read from the sidecar.

    **What this can and cannot establish.** It establishes that the report agrees
    with the plans it shipped — that no number was transcribed, carried over from
    an earlier run, or computed against a different baseline than the one named.
    It cannot establish that either is right: it calls the same ``evaluate`` and
    ``adversarial`` functions the bench called, so a bug in one of those is
    invisible to it. That is the reason the plans are on disk in a documented
    format rather than only their digests: a critic can compute the same
    quantities with their own tools and needs nothing from this function.

    Returns ``{"ok": bool, "checked": int, "checks": int, "failures": [...]}``.
    Every failure names the scenario, the field and both values.
    """
    round_dir = Path(round_dir)
    report = json.loads((round_dir / "bench-results.json").read_text(encoding="utf-8"))
    inputs = load_inputs()
    failures: list[dict[str, Any]] = []
    checks = 0

    def bad(scenario_id: str, field_name: str, reported: Any, recomputed: Any) -> None:
        failures.append({"id": scenario_id, "field": field_name,
                         "reported": reported, "recomputed": recomputed})

    floor = _floor_from_report(report)
    baselines: dict[str, dict] = {}
    for row in report.get("plans", {}).get("files", []):
        if row["id"].startswith("baseline_"):
            baselines[row["id"][len("baseline_"):]] = EP.load_plan(round_dir / row["file"])
    cache = compactness.MeasureCache()

    for scenario in report["scenarios"]:
        sid = scenario["id"]
        path = round_dir / scenario["plan"]["file"]
        if not path.exists():
            bad(sid, "plan.file", scenario["plan"]["file"], "missing")
            continue
        plan = EP.load_plan(path)
        checks += 1
        if O.plan_digest(plan) != scenario["plan"]["digest"]:
            bad(sid, "plan.digest", scenario["plan"]["digest"], O.plan_digest(plan))
            continue

        try:
            EP.validate(plan, inputs.adjacency, K)
        except Exception as exc:
            bad(sid, "evaluate.plan.validate", "valid", f"{type(exc).__name__}: {exc}")

        metrics = plan_metrics(plan, inputs, cache)
        for name in LOCATED_METRICS:
            checks += 1
            if not _close(metrics.get(name), scenario["metrics"].get(name)):
                bad(sid, f"metrics.{name}", scenario["metrics"].get(name), metrics.get(name))
        for key, name in (("dem", "dem_seats"), ("rep", "rep_seats")):
            checks += 1
            if metrics[name] != scenario["seats"][key]:
                bad(sid, f"seats.{key}", scenario["seats"][key], metrics[name])

        record = G.check_legality(
            plan, inputs.adjacency, inputs.populations, K, GATE_EPSILON,
            shape_envelope=floor,
            plan_shape_metrics={n: metrics[n] for n in G.ENVELOPE_MEASURES},
        )
        checks += 2
        if record.passed != scenario["legal"]:
            bad(sid, "legal", scenario["legal"], record.passed)
        if record.failures() != list(scenario["legal_failures"]):
            bad(sid, "legal_failures", scenario["legal_failures"], record.failures())

        # The realized shift, against whichever baseline this kind of scenario
        # names: a plan for a plant, the pool's median seat count for a null.
        # Both are published, so both can be re-derived without the ensemble.
        baseline_name = scenario.get("baseline")
        party = scenario.get("target_party")
        provenance = scenario.get("provenance") or {}
        here = partisan.seat_counts(plan, inputs.dem, inputs.rep)
        if party and baseline_name in baselines:
            checks += 1
            base = partisan.seat_counts(baselines[baseline_name], inputs.dem, inputs.rep)
            index = 0 if party == "D" else 1
            shift = here[index] - base[index]
            if shift != scenario["realized_seat_shift"]:
                bad(sid, "realized_seat_shift", scenario["realized_seat_shift"], shift)
        elif provenance.get("ensemble_median_seats") is not None:
            checks += 1
            index = 0 if provenance.get("party", "D") == "D" else 1
            shift = float(here[index]) - float(provenance["ensemble_median_seats"])
            if not _close(shift, scenario["realized_seat_shift"]):
                bad(sid, "realized_seat_shift", scenario["realized_seat_shift"], shift)

    return {
        "ok": not failures,
        "round_dir": str(round_dir),
        "checked": len(report["scenarios"]),
        "checks": checks,
        "failures": failures,
    }


def _floor_from_report(report: Mapping[str, Any]) -> G.ShapeEnvelope | None:
    """Rebuild the legality compactness floor from what the report published.

    Read back rather than recalibrated: the point of verification is to test the
    report against its own stated standard, and recalibrating from a fresh
    ensemble would test it against a different one.
    """
    block = report.get("diagnostics", {}).get("compactness_floor", {})
    if not block.get("calibrated"):
        return None
    bounds = {
        name: (
            -math.inf if row["at_least"] is None else float(row["at_least"]),
            math.inf if row["at_most"] is None else float(row["at_most"]),
        )
        for name, row in block["bounds"].items()
    }
    # ``construction`` carries the kind; a report written before round 4 has no
    # such key and its floor was published as a coverage-1.0 band, so read that
    # shape rather than refusing to verify an older artifact.
    kind = block.get("construction", "central_band")
    return G.ShapeEnvelope(
        coverage=block["coverage"] if kind == "central_band" else None,
        kind=kind,
        width=block.get("width_iqr") if kind == "matched" else None,
        bounds=bounds,
        reference_plans=block["reference_plans"],
        reference_draws=block["reference_draws"],
        measures=tuple(block["measures"]),
        source=block["source"],
        centre=block.get("centre") if kind == "central_band" else 0.5,
    )


def _close(a: Any, b: Any) -> bool:
    """Equality for a recomputed measurement against a published one."""
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #

def run(
    master_seed: int,
    round_number: int,
    size: Size = FULL,
    out_dir: Path | None = None,
    make_plots: bool = True,
    jobs: int = DEFAULT_JOBS,
) -> dict[str, Any]:
    """Do the whole bench and return the report dict. Writes JSON, plans and PNGs.

    ``jobs`` spreads the chains across processes. It changes wall clock and
    nothing in the report outside ``timing``; see :func:`run_chains_parallel`.
    """
    out_dir = Path(out_dir) if out_dir is not None else DEFAULT_OUT_ROOT / f"round-{round_number:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    timing: dict[str, Any] = {}
    t0 = time.perf_counter()

    inputs = load_inputs()
    timing["load_seconds"] = time.perf_counter() - t0

    # 1. the neutral ensemble ------------------------------------------------ #
    started = time.perf_counter()
    chain_seeds = seeds.stream(
        master_seed, _purpose(round_number, "ensemble"), size.chains
    )
    ens = run_chains_parallel(
        inputs.gen_adjacency,
        inputs.gen_populations,
        K,
        size.epsilon,
        size.steps,
        chain_seeds,
        NODE_REPEATS,
        jobs,
    )
    timing["ensemble_seconds"] = time.perf_counter() - started
    timing["ensemble_chain_seconds"] = [t.seconds for t in ens.traces]
    timing["jobs"] = jobs

    # 2. the null pool, independently seeded --------------------------------- #
    started = time.perf_counter()
    null_seeds = seeds.stream(
        master_seed, _purpose(round_number, "null-pool"), size.null_chains
    )
    pool = run_chains_parallel(
        inputs.gen_adjacency,
        inputs.gen_populations,
        K,
        size.epsilon,
        size.null_steps,
        null_seeds,
        NODE_REPEATS,
        jobs,
    )
    timing["null_pool_seconds"] = time.perf_counter() - started

    # 3. reference columns --------------------------------------------------- #
    started = time.perf_counter()
    columns, cache_stats = ensemble_columns(ens.plans, inputs)
    timing["ensemble_metrics_seconds"] = time.perf_counter() - started

    # 4. the two shape envelopes, both from the reference columns ------------ #
    source = (
        f"round {round_number} reference ensemble: {len(ens.plans)} draws, "
        f"{ens.distinct_plans} distinct, epsilon={size.epsilon:g}"
    )
    # The band is the reported comparison, not the search constraint: round 3
    # shipped it and measured non-partisan AUC 0.89 against it (D-011).
    envelope = plant_envelope(
        columns, n_draws=len(ens.plans), n_distinct=ens.distinct_plans, source=source
    )
    anchors = AnchorPool.build(
        ens.plans,
        columns,
        n_draws=len(ens.plans),
        n_distinct=ens.distinct_plans,
        source=source,
    )
    review_metrics = plan_metrics(inputs.enacted, inputs)
    starts = _inside(ens.plans, columns, envelope, K)

    # 5. scenarios ----------------------------------------------------------- #
    baselines = {
        "enacted": dict(inputs.enacted),
        "ensemble_max_d": pick_max_dem_plan(ens.plans, inputs),
    }
    started = time.perf_counter()
    planted, attempts = plant_cases(
        inputs, baselines, master_seed, round_number, size, anchors
    )
    timing["planting_seconds"] = time.perf_counter() - started
    timing["plant_seconds"] = {case.id: case.seconds for case in planted}

    started = time.perf_counter()
    nulls = null_cases(inputs, pool.plans, master_seed, round_number, size)
    timing["nulls_seconds"] = time.perf_counter() - started

    cases = planted + nulls
    floor = compactness_floor(
        columns,
        [case.metrics for case in nulls] + [review_metrics],
        n_draws=len(ens.plans),
        n_distinct=ens.distinct_plans,
        source=(
            "the neutral draws of "
            + source
            + f", this round's {len(nulls)} null cases, and the enacted CD118 "
            "plan (bench.compactness_floor)"
        ),
    )
    started = time.perf_counter()
    plan_ids = reference_ids(ens.plans)
    relocate(cases, columns, inputs, plan_ids)
    relegalize(cases, inputs, size, floor)
    timing["scoring_seconds"] = time.perf_counter() - started

    # 6. decisions ----------------------------------------------------------- #
    # The gate reads the pre-registered null strata; see null_cases for the
    # argument and confusion.gate_sample in the report for the labelling.
    scenarios = [case.scenario() for case in cases]
    gate_ids = {case.id for case in cases if _in_gate_sample(case)}
    gate_scenarios = [s for s in scenarios if s.id in gate_ids]
    decisions = {s.id: d for s, d in C.decide(scenarios, RULE)}
    matrix = C.confusion_matrix(gate_scenarios, RULE)
    curve = C.detection_curve(gate_scenarios, RULE)
    gate_block = C.gates(gate_scenarios, RULE, seat_shift=ACTIVE.gate_magnitude)
    matrix_all = C.confusion_matrix(scenarios, RULE)

    # 7. the plan under review ----------------------------------------------- #
    review_locations = O.locate(
        inputs.enacted,
        columns,
        review_metrics,
        context=context_for(inputs.enacted, inputs),
        metrics=LOCATED_METRICS,
        ensemble_plan_ids=plan_ids,
    )
    # No C.flag here, deliberately. See the plan_under_review block in assemble.

    report = assemble(
        master_seed=master_seed,
        round_number=round_number,
        size=size,
        ens=ens,
        pool=pool,
        columns=columns,
        cache_stats=cache_stats,
        cases=cases,
        decisions=decisions,
        matrix=matrix,
        curve=curve,
        gate_block=gate_block,
        matrix_all=matrix_all,
        envelope=envelope,
        anchors=anchors,
        floor=floor,
        starts=starts,
        jobs=jobs,
        attempts=attempts,
        baselines=baselines,
        inputs=inputs,
        review_metrics=review_metrics,
        review_locations=review_locations,
        scenarios=scenarios,
        out_dir=out_dir,
        make_plots=make_plots,
    )

    timing["total_seconds"] = time.perf_counter() - t0
    timing["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report["timing"] = timing

    report["plans"] = write_plans(cases, baselines, out_dir)

    path = out_dir / "bench-results.json"
    path.write_text(
        json.dumps(_json_safe(report), indent=2, sort_keys=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    report["_path"] = str(path)
    return report


def _json_safe(obj: Any) -> Any:
    """Recursively replace ``nan``/``inf`` with ``None`` and tuples with lists.

    ``nan`` is not JSON. It is also not a measurement: every place one can arise
    here — a correlation against a constant column, a diagnostic on a quantity
    that never varied — is a place where the honest report is "no value", and
    the modules upstream already say why in a neighbouring ``note`` field.
    Writing a bare ``NaN`` token instead would produce a file that only Python
    can read and that silently becomes 0.0 in several other parsers.
    """
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def assemble(**kw) -> dict[str, Any]:
    """Build the report dict to ARCHITECTURE.md 5, and draw the plots.

    The eight top-level keys the schema names come first and carry exactly the
    field names it gives. Everything else the bench measured lives under
    ``diagnostics``, ``plan_under_review`` and ``timing`` — additive keys, so
    the schema block is readable on its own and a reader looking for
    ``gates.tpr_at_<magnitude>seat`` finds it where the contract says it is.
    """
    ens: ensemble.EnsembleResult = kw["ens"]
    pool: ensemble.EnsembleResult = kw["pool"]
    size: Size = kw["size"]
    cases: list[Case] = kw["cases"]
    decisions = kw["decisions"]
    matrix = kw["matrix"]
    curve = kw["curve"]
    gate_block = kw["gate_block"]
    columns = kw["columns"]
    inputs: Inputs = kw["inputs"]
    out_dir: Path = kw["out_dir"]

    conv = convergence_block(ens)
    rhat_values = [
        conv[name]["split_rhat"] for name in ("cut_edges", "pop_spread")
        if conv[name]["split_rhat"] is not None
    ]
    worst_rhat = max(rhat_values) if rhat_values else None
    legal = [bool(case.legal) for case in cases]
    legal_fraction = (sum(legal) / len(legal)) if legal else None
    legal_at_run = [
        bool(case.legality_at_run.passed) for case in cases
        if case.legality_at_run is not None
    ]
    legal_fraction_at_run = (
        (sum(legal_at_run) / len(legal_at_run)) if legal_at_run else None
    )
    illegal_ids = sorted(case.id for case in cases if not case.legal)

    scenarios_out = []
    for case in cases:
        decision = decisions[case.id]
        scenarios_out.append(
            {
                "id": case.id,
                "kind": case.kind,
                "target_party": case.target_party,
                "baseline": case.baseline,
                "intended_seat_shift": case.intended_seat_shift,
                "realized_seat_shift": case.realized_seat_shift,
                "flagged": decision.flagged,
                "in_gate_sample": _in_gate_sample(case),
                "plan": {
                    "digest": case.digest,
                    "file": f"{PLANS_DIRNAME}/{case.id}.csv",
                    "n_units": len(case.plan),
                },
                "provenance": case.provenance,
                "legal": case.legal,
                "legal_failures": case.legal_failures,
                "legality": case.legality_block(size),
                "metrics": {name: case.metrics.get(name) for name in LOCATED_METRICS},
                "percentiles": O.percentiles(case.locations),
                "statuses": {n: loc.status for n, loc in case.locations.items()},
                "fired_metrics": list(decision.fired_metrics),
                "eligible_metrics": list(decision.eligible),
                "excluded_metrics": {m: w for m, w in decision.excluded},
                "unresolvable_metrics": {m: w for m, w in decision.unresolvable},
                "decision_reason": decision.reason,
                "seats": {
                    "dem": case.metrics.get("dem_seats"),
                    "rep": case.metrics.get("rep_seats"),
                },
                "notes": list(case.notes),
            }
        )

    trace = convergence_trace(ens, size.trace_checkpoints)
    trend = rhat_trend(trace)
    qualification = gate_qualification(size, ens, columns, conv, matrix)

    gates_out = {
        gate_key(): gate_block[gate_key()],
        "fpr_on_nulls": gate_block["fpr_on_nulls"],
        "split_rhat": {
            "target": RHAT_GATE,
            "value": worst_rhat,
            "pass": None if worst_rhat is None else worst_rhat <= RHAT_GATE,
            "trend": trend,
            "note": (
                "worst of cut_edges and pop_spread, rank-normalized split R-hat "
                "over completed chains; CRITERIA.md 8 target band 1.00-1.01. "
                "trend is this run's own R-hat against draws per chain: a value "
                "that has stopped falling while ESS has stopped growing is a "
                "statement about the sampler at this epsilon, not about the "
                "budget, and no number of further draws will move it. "
                "diagnostics.convergence_trace is the series it was read from "
                "and diagnostics.convergence_all_chains recomputes it over the "
                "partial traces as well"
            ),
        },
        "legal_compliance": {
            "target": 1.0,
            "value": legal_fraction,
            "pass": None if legal_fraction is None else legal_fraction >= 1.0,
            "n": len(legal),
            "epsilon": GATE_EPSILON,
            "measured_at": (
                f"epsilon={GATE_EPSILON:g}, the declared operating point "
                "(bench.GATE_EPSILON), whatever epsilon this run used"
            ),
            "run_epsilon": size.epsilon,
            "value_at_run_epsilon": legal_fraction_at_run,
            "illegal_ids": illegal_ids,
            "compactness_included": bool(kw["floor"] is not None),
            "note": (
                "fraction of scenario plans passing every constraint in "
                "adversarial.gerrymander.check_legality at the OPERATING "
                "epsilon. Round 1 reported 1.0 for a run made at 1e-3 while 7 of "
                "its 10 plans were illegal at 2e-4; the gate is read at the "
                "operating point so that a cheaper run cannot pass it. "
                "value_at_run_epsilon is the same fraction at the epsilon this "
                "run actually used and is reported, never gated. Compactness — "
                "Iowa Code ch. 42 criterion 4 — is included via a calibrated "
                "one-sided floor whose choice and cost are in "
                "bench.compactness_floor and diagnostics.compactness_floor"
            ),
        },
        "qualification": qualification,
        "rule": RULE.as_dict(),
    }
    for name in (gate_key(), "fpr_on_nulls", "split_rhat", "legal_compliance"):
        gates_out[name]["meaningful"] = qualification["meaningful"]
        gates_out[name]["meaningful_note"] = qualification["note"]

    strata_cases = {
        name: [c for c in cases if c.provenance.get("stratum") == name]
        for name in NULL_STRATA
    }

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "round": kw["round_number"],
        "config": {
            "state": STATE,
            "units": UNIT_KIND,
            "n_districts": K,
            "epsilon": size.epsilon,
            "steps": size.steps,
            "chains": size.chains,
            "master_seed": kw["master_seed"],
            "node_repeats": NODE_REPEATS,
            "size": size.label,
            "null_pool_chains": size.null_chains,
            "null_pool_steps": size.null_steps,
            "replicates_per_cell": size.replicates,
            "magnitudes": list(size.magnitudes),
            "probe_magnitudes": list(size.probe_magnitudes),
            "search_max_iterations": size.max_iterations,
            "search_restarts": size.restarts,
            "rule": RULE.as_dict(),
            "located_metrics": list(LOCATED_METRICS),
            "seed_purposes": [
                _purpose(kw["round_number"], t)
                for t in ("ensemble", "null-pool", "plant/<party>/<magnitude>", "null-random")
            ],
        },
        "ensemble": {
            "n_requested": ens.n_requested,
            "n_completed": ens.n_completed,
            "chain_failures": ens.chain_failures,
            "failure_rate": ens.failure_rate,
            "distinct_plans": ens.distinct_plans,
            "seeds": list(ens.seeds),
            "convergence": {
                "cut_edges": {
                    "split_rhat": conv["cut_edges"]["split_rhat"],
                    "ess": conv["cut_edges"]["ess"],
                    "note": conv["cut_edges"]["note"],
                },
                "pop_spread": {
                    "split_rhat": conv["pop_spread"]["split_rhat"],
                    "ess": conv["pop_spread"]["ess"],
                    "note": conv["pop_spread"]["note"],
                },
                "sample": conv["sample"],
                "n_chains": conv["n_chains"],
            },
            "population_spread": ens.population_spread_summary(only_completed=True),
            "reference_sample": "all_draws",
            "reference_n": len(ens.plans),
        },
        "scenarios": scenarios_out,
        "confusion": {
            "gate_sample": {
                "null_strata_pooled": list(GATE_NULL_STRATA),
                "null_strata_excluded": [
                    name for name in NULL_STRATA if name not in GATE_NULL_STRATA
                ],
                "n_scenarios_in_gate": matrix["n"],
                "n_scenarios_published": len(kw["scenarios"]),
                "excluded_ids": [
                    case.id for case in cases if not _in_gate_sample(case)
                ],
                "reason": (
                    "the seat_outcome stratum is selected by |seats - median|, "
                    "which is rank-correlated at -0.868 with the absolute "
                    "efficiency gap the rule thresholds; pooling it would make "
                    "the FPR a measurement of the selection rule. It is drawn, "
                    "scored and published as a scenario, and its rate is in "
                    "diagnostics.null_strata and confusion.all_strata"
                ),
            },
            "all_strata": {
                "fpr_on_nulls": kw["matrix_all"]["fpr"],
                "n_null": kw["matrix_all"]["n_null"],
                "unresolved_null": kw["matrix_all"]["unresolved_null"],
                "note": "every null stratum pooled, including the excluded one",
            },
            gate_key(): C.tpr_at(curve, ACTIVE.gate_magnitude),
            "fpr_on_nulls": matrix["fpr"],
            "min_detectable_seat_shift": C.min_detectable_seat_shift(curve),
            "by_magnitude": [
                {
                    "seats": row["seats"],
                    "tpr": row["tpr"],
                    "n": row["n"],
                    "flagged": row["flagged"],
                    "ci95": list(row["ci95"]) if row["ci95"] else None,
                    "by_direction": row["by_direction"],
                }
                for row in curve
            ],
            "matrix": {
                key: matrix[key]
                for key in (
                    "n", "n_positive", "n_null", "tp", "fp", "tn", "fn",
                    "tpr", "fnr", "fpr", "tnr", "fired_on_positives", "fired_on_nulls",
                    "unresolved_positive", "unresolved_null", "n_resolved",
                    "coverage",
                )
            },
            "tpr_ci95": list(matrix["tpr_ci95"]) if matrix["tpr_ci95"] else None,
            "fpr_ci95": list(matrix["fpr_ci95"]) if matrix["fpr_ci95"] else None,
        },
        "gates": gates_out,
        "firewall": firewall_block(),
        "plan_under_review": {
            "id": f"{ACTIVE.prefix}_enacted_cd118",
            "source": str(ACTIVE.enacted_csv.relative_to(REPO_ROOT)),
            "plan_digest": O.plan_digest(inputs.enacted),
            "plan_file": f"{PLANS_DIRNAME}/baseline_enacted.csv",
            "metrics": {n: kw["review_metrics"].get(n) for n in LOCATED_METRICS},
            "percentiles": O.percentiles(kw["review_locations"]),
            "statuses": {n: l.status for n, l in kw["review_locations"].items()},
            "seats": {
                "dem": kw["review_metrics"]["dem_seats"],
                "rep": kw["review_metrics"]["rep_seats"],
            },
            "indistinguishable_from": _indistinguishable(kw["review_metrics"], cases),
            "note": (
                "A LOCATION, NOT A VERDICT. There is no `flagged` field here and "
                "there must not be one: README.md and CRITERIA.md 11 forbid an "
                "output of this system that reads as a judgement on the plan "
                "under review, and round 2 published `flagged: true` on Iowa's "
                "in-force CD118 map. What is here instead is where the enacted "
                "plan sits in the neutral ensemble, metric by metric, with the "
                "trusted set named in `statuses` — and, since the same round "
                "found the enacted map's efficiency gap bit-identical to a "
                "manufactured gerrymander's, `indistinguishable_from` names "
                "every scenario this artifact cannot tell it apart from. It "
                "carries no manufactured ground truth, so it is not a scenario "
                "and contributes to no rate in the confusion matrix"
            ),
        },
        "diagnostics": {
            "null_strata": {
                **{
                    f"null_{name}": {
                        **_stratum(strata_cases[name], decisions),
                        "in_gate_sample": name in GATE_NULL_STRATA,
                        "selection_rule": N.SELECTION_RULES[name],
                    }
                    for name in NULL_STRATA
                },
                "note": (
                    "the gate pools "
                    + ", ".join(GATE_NULL_STRATA)
                    + "; every stratum is published and rated separately, and "
                    "confusion.gate_sample says which were pooled and why"
                ),
            },
            "compactness_floor": {
                **_envelope_block(kw["floor"], "legality floor, one-sided"),
                "role": (
                    "the compactness standard gates.legal_compliance is measured "
                    "against; see bench.compactness_floor for the value choice "
                    "and what it cannot establish"
                ),
            },
            "plant_envelope": {
                "kind": "matched" if kw["anchors"] is not None else None,
                "calibrated": kw["anchors"] is not None,
                "width_iqr": MATCH_WIDTH,
                "anchor_selection": (
                    "one reference draw per plant, uniform over draws (not over "
                    "distinct plans), seeded from "
                    "seeds.derive(master_seed, purpose + '/anchor', index) and "
                    "drawn before the search runs"
                ),
                "anchor_pool_draws": (
                    None if kw["anchors"] is None else len(kw["anchors"].eligible)
                ),
                "source": None if kw["anchors"] is None else kw["anchors"].source,
                "measures": list(G.ENVELOPE_MEASURES),
                "per_plant_bounds_in": "scenarios[].provenance.shape_anchor",
                "role": (
                    "the shape bounds adversarial.gerrymander's search may not "
                    "leave (D-010), one envelope per plant anchored on a neutral "
                    "draw. This is what the search ran inside; see "
                    "bench.AnchorPool for why an anchor rather than a band"
                ),
                "band_comparison": {
                    **_envelope_block(
                        kw["envelope"], "round-3 search constraint, two-sided"
                    ),
                    "role": (
                        "REPORTED, NOT USED as the search constraint. This is the "
                        "central band round 3 shipped and an independent check "
                        "measured at non-partisan AUC 0.89 (D-011). It is kept in "
                        "the artifact so the two instruments can be compared on "
                        "the same reference"
                    ),
                    "matches_module_default": (
                        PLANT_SHAPE_COVERAGE == G.DEFAULT_SHAPE_COVERAGE
                    ),
                    "module_default_coverage": G.DEFAULT_SHAPE_COVERAGE,
                    "start_plans_inside_the_band": len(kw["starts"]),
                },
            },
            "planting_attempts": kw["attempts"],
            "achievable_range": _achievable(kw["attempts"]),
            "baselines": {
                name: {
                    "plan_digest": O.plan_digest(plan),
                    "seat_counts_d_r_tied": list(
                        partisan.seat_counts(plan, inputs.dem, inputs.rep)
                    ),
                    "population_spread": G.check_legality(
                        plan, inputs.adjacency, inputs.populations, K, size.epsilon
                    ).population_spread,
                }
                for name, plan in kw["baselines"].items()
            },
            "null_pool": {
                "n_requested": pool.n_requested,
                "n_completed": pool.n_completed,
                "chain_failures": pool.chain_failures,
                "failure_rate": pool.failure_rate,
                "distinct_plans": pool.distinct_plans,
                "seeds": list(pool.seeds),
            },
            "metric_disagreement": disagreement_block(columns),
            "convergence_trace": trace,
            "convergence_all_chains": _all_chain_convergence(ens),
            "ensemble_distributions": {
                name: _summary(columns[name]) for name in columns
            },
            "alternative_rules": [
                _alternative(rule, kw["scenarios"]) for rule in ALTERNATIVE_RULES
            ],
            "measure_cache": kw["cache_stats"],
            "report_lines": C.report_lines(matrix, curve),
        },
    }

    report["plots"] = (
        draw_plots(report, columns, out_dir) if kw["make_plots"] else []
    )
    return report


def _indistinguishable(
    review_metrics: Mapping[str, Any], cases: Sequence[Case]
) -> dict[str, Any]:
    """Per metric, the scenarios whose value the enacted plan's cannot be told from.

    Round 2 reported the enacted map and a deliberately built R-gerrymander with
    a bit-identical efficiency gap — because under a 4-0 sweep the efficiency gap
    barely depends on the lines — and said nothing about it. A metric that gives
    the same number for the real map and for a planted one is not evidence about
    either, and the artifact should say so on its own face rather than leave it
    to be discovered.

    Exact equality to within 1e-12, per metric, listing the scenario ids.
    """
    out: dict[str, Any] = {}
    for name in LOCATED_METRICS:
        value = review_metrics.get(name)
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        same = [
            case.id for case in cases
            if isinstance(case.metrics.get(name), (int, float))
            and not isinstance(case.metrics.get(name), bool)
            and math.isclose(float(case.metrics[name]), float(value),
                             rel_tol=0.0, abs_tol=1e-12)
        ]
        if same:
            out[name] = same
    return {
        "metrics": out,
        "tolerance": 1e-12,
        "note": (
            "scenarios carrying the same value as the enacted plan on this "
            "metric; on such a metric the artifact cannot distinguish the map in "
            "force from a manufactured one, whatever the percentile says"
        ),
    }


def _summary(column: Sequence[Any]) -> dict[str, Any]:
    """``outlier.summarize`` of one column, or an explicit reason it has none."""
    defined = [float(v) for v in column if v is not None]
    undefined = len(column) - len(defined)
    if not defined:
        return {"n": 0, "n_undefined": undefined,
                "note": "every draw is undefined for this metric"}
    return O.summarize(defined, n_undefined=undefined).as_dict()


def _stratum(cases: Sequence[Case], decisions) -> dict[str, Any]:
    """One stratum's rate, with abstentions counted rather than read as clean.

    ``fpr`` is over the cases the rule could actually evaluate. A stratum where
    every case was unresolvable reports ``fpr: null`` and ``resolved: 0``, which
    is a different statement from a stratum that fired on none of them.
    """
    n = len(cases)
    resolved = [case for case in cases if decisions[case.id].flagged is not None]
    flagged = sum(1 for case in resolved if decisions[case.id].flagged)
    ci = C.wilson_interval(flagged, len(resolved))
    return {
        "n": n,
        "resolved": len(resolved),
        "unresolved": n - len(resolved),
        "flagged": flagged,
        "fpr": (flagged / len(resolved)) if resolved else None,
        "ci95": list(ci) if ci else None,
        "ids": [case.id for case in cases],
    }


def _achievable(attempts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """What the seat-shift range actually was this round, from the attempt log."""
    out: dict[str, Any] = {}
    for party in ("D", "R"):
        rows = [a for a in attempts if a["target_party"] == party]
        reached = [a["intended_seat_shift"] for a in rows if a["reached"]]
        out[party] = {
            "attempted": sorted({a["intended_seat_shift"] for a in rows}),
            "reached": sorted(set(reached)),
            "max_reached": max(reached) if reached else 0,
            "success_by_magnitude": {
                str(m): {
                    "reached": sum(1 for a in rows if a["intended_seat_shift"] == m and a["reached"]),
                    "attempted": sum(1 for a in rows if a["intended_seat_shift"] == m),
                }
                for m in sorted({a["intended_seat_shift"] for a in rows})
            },
        }
    out["note"] = (
        "measured, not assumed: a magnitude with 0 reached of n attempted is a "
        "statement about what this search, at this budget, could build from that "
        "baseline INSIDE the matched shape envelope (D-010). Three things it is "
        "not: a proof that no such plan exists, a property of the state alone, or "
        "a reason to loosen the envelope. Round 3 read a yield of 0/24 as "
        "evidence that shape-typical gerrymanders did not exist on Iowa and had "
        "to retract it — the neutral sampler was producing them all along"
    )
    return out


def _alternative(rule: C.Rule, scenarios) -> dict[str, Any]:
    matrix = C.confusion_matrix(scenarios, rule)
    curve = C.detection_curve(scenarios, rule)
    return {
        "rule": rule.as_dict(),
        "tpr": matrix["tpr"],
        "fpr": matrix["fpr"],
        gate_key(): C.tpr_at(curve, ACTIVE.gate_magnitude),
        "min_detectable_seat_shift": C.min_detectable_seat_shift(curve),
        "nominal_fpr_bound": rule.nominal_fpr(
            len(rule.metrics) if rule.metrics else len(LOCATED_METRICS)
        ),
    }


# --------------------------------------------------------------------------- #
# plots — the artifacts critics read
# --------------------------------------------------------------------------- #

def draw_plots(report: Mapping[str, Any], columns: Mapping[str, Sequence[Any]], out_dir: Path) -> list[str]:
    """Five PNGs. Every one of them carries the rule or the sample it describes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    written: list[str] = []
    for name, fn in (
        ("confusion-over-rounds.png", _plot_rounds),
        ("detection-curve.png", _plot_curve),
        ("ensemble-distributions.png", _plot_distributions),
        ("metric-disagreement.png", _plot_disagreement),
        ("convergence-trace.png", _plot_trace),
    ):
        path = out_dir / name
        try:
            fig = fn(report, columns, plt)
        except Exception as exc:  # a missing plot must not lose the JSON
            print(f"bench: plot {name} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        fig.savefig(path, dpi=140, bbox_inches="tight")
        plt.close(fig)
        written.append(name)
    return written


def _plot_rounds(report, columns, plt):
    """Confusion matrix for this round, and both rates across every round on disk."""
    history = _history(report)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    m = report["confusion"]["matrix"]
    grid = [[m["tp"], m["fn"]], [m["fp"], m["tn"]]]
    ax = axes[0]
    ax.imshow(grid, cmap="Blues", vmin=0, vmax=max(1, max(max(r) for r in grid)))
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(grid[i][j]), ha="center", va="center", fontsize=16)
    ax.set_xticks([0, 1], ["flagged", "not flagged"])
    ax.set_yticks([0, 1], ["planted", "null"])
    qual = report["gates"].get("qualification", {})
    banner = (
        "" if qual.get("meaningful", True)
        else f"  [NOT MEANINGFUL: {qual.get('size', '?')} run]"
    )
    ax.set_title(
        f"round {report['round']}: confusion matrix{banner}\n{RULE.describe()}",
        fontsize=8,
    )

    ax = axes[1]
    rounds = [h["round"] for h in history]
    nan = float("nan")
    pick = lambda key: [nan if h[key] is None else h[key] for h in history]
    ax.plot(rounds, pick("tpr"), "o-", label="TPR (all planted)")
    ax.plot(rounds, pick(gate_key()), "s-", label=f"TPR at {ACTIVE.gate_magnitude}-seat shift")
    ax.plot(rounds, pick("fpr"), "^-", label="FPR on nulls")
    ax.axhline(C.TPR_GATE, color="green", ls=":", lw=1, label=f"TPR gate {C.TPR_GATE}")
    ax.axhline(C.FPR_GATE, color="red", ls=":", lw=1, label=f"FPR gate {C.FPR_GATE}")
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("round")
    ax.set_ylabel("rate")
    ax.set_xticks(rounds)
    ax.set_title("gates over rounds", fontsize=9)
    ax.legend(fontsize=7)
    fig.tight_layout()
    return fig


def _history(report) -> list[dict[str, Any]]:
    """Every round's rates, read back off disk, with this round substituted in."""
    rows: dict[int, dict[str, Any]] = {}
    root = DEFAULT_OUT_ROOT
    if root.exists():
        for path in sorted(root.glob("round-*/bench-results.json")):
            try:
                other = json.loads(path.read_text(encoding="utf-8"))
                rows[int(other["round"])] = {
                    "round": int(other["round"]),
                    "tpr": other["confusion"]["matrix"]["tpr"],
                    gate_key(): other["confusion"].get(gate_key()),
                    "fpr": other["confusion"]["fpr_on_nulls"],
                }
            except Exception:
                continue
    rows[int(report["round"])] = {
        "round": int(report["round"]),
        "tpr": report["confusion"]["matrix"]["tpr"],
        gate_key(): report["confusion"].get(gate_key()),
        "fpr": report["confusion"]["fpr_on_nulls"],
    }
    return [rows[r] for r in sorted(rows)]


def _plot_curve(report, columns, plt):
    """Detection rate against intended seat shift, with Wilson intervals."""
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    rows = [r for r in report["confusion"]["by_magnitude"] if r["tpr"] is not None]
    xs = [r["seats"] for r in rows]
    ys = [r["tpr"] for r in rows]
    lo = [r["tpr"] - (r["ci95"][0] if r["ci95"] else r["tpr"]) for r in rows]
    hi = [(r["ci95"][1] if r["ci95"] else r["tpr"]) - r["tpr"] for r in rows]
    ax.errorbar(xs, ys, yerr=[lo, hi], fmt="o-", capsize=4, label="TPR (95% Wilson)")
    ax.axhline(C.TPR_GATE, color="green", ls=":", lw=1, label=f"gate {C.TPR_GATE} at 2 seats")
    fpr = report["confusion"]["fpr_on_nulls"]
    if fpr is not None:
        ax.axhline(fpr, color="red", ls="--", lw=1, label=f"measured FPR on nulls = {fpr:.3f}")
    for r in rows:
        ax.annotate(f"n={r['n']}", (r["seats"], r["tpr"]), textcoords="offset points",
                    xytext=(6, -12), fontsize=7)
    ax.set_xlabel("intended seat shift (magnitude, either direction)")
    ax.set_ylabel("detection rate")
    ax.set_ylim(-0.05, 1.05)
    ax.set_xticks(xs if xs else [0])
    mds = report["confusion"]["min_detectable_seat_shift"]
    ax.set_title(
        f"round {report['round']} detection threshold — "
        f"min detectable shift: {mds if mds is not None else 'not reached'}\n{RULE.describe()}",
        fontsize=8,
    )
    ax.legend(fontsize=7)
    fig.tight_layout()
    return fig


def _plot_distributions(report, columns, plt):
    """The ensemble distribution per metric, with the plan under review marked."""
    names = [n for n in PARTISAN_METRICS + COMPACTNESS_METRICS if n in columns]
    ncols = 3
    nrows = (len(names) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.0 * ncols, 2.7 * nrows))
    axes = axes.ravel() if hasattr(axes, "ravel") else [axes]
    review = report["plan_under_review"]
    for ax, name in zip(axes, names):
        values = [float(v) for v in columns[name] if v is not None]
        undefined = sum(1 for v in columns[name] if v is None)
        ax.hist(values, bins=min(40, max(8, len(set(values)))), color="#7799bb", edgecolor="none")
        value = review["metrics"].get(name)
        pct = review["percentiles"].get(name)
        if value is not None:
            ax.axvline(float(value), color="crimson", lw=2)
            label = f"enacted = {float(value):.4g}"
            if pct is not None:
                label += f"\npercentile {pct:.3f}"
            else:
                label += f"\n{review['statuses'].get(name, 'no percentile')}"
            ax.annotate(label, xy=(0.02, 0.95), xycoords="axes fraction",
                        va="top", fontsize=7, color="crimson")
        else:
            ax.annotate(f"enacted: {review['statuses'].get(name)}",
                        xy=(0.02, 0.95), xycoords="axes fraction", va="top",
                        fontsize=7, color="crimson")
        title = name + (f"  ({undefined} undefined draws)" if undefined else "")
        ax.set_title(title, fontsize=8)
        ax.tick_params(labelsize=7)
    for ax in axes[len(names):]:
        ax.axis("off")
    fig.suptitle(
        f"round {report['round']}: neutral ensemble ({report['ensemble']['reference_n']} draws, "
        f"{report['ensemble']['distinct_plans']} distinct) with the enacted plan marked",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return fig


def _plot_disagreement(report, columns, plt):
    """Rank-correlation matrices: compactness measures, and fairness metrics."""
    block = report["diagnostics"]["metric_disagreement"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, (key, names) in zip(
        axes, (("compactness", COMPACTNESS_METRICS), ("fairness", PARTISAN_METRICS))
    ):
        n = len(names)
        grid = [[1.0] * n for _ in range(n)]
        for row in block[key]["pairs"]:
            i, j = names.index(row["a"]), names.index(row["b"])
            v = row["spearman"]
            grid[i][j] = grid[j][i] = float("nan") if v is None else v
        im = ax.imshow(grid, cmap="RdBu", vmin=-1, vmax=1)
        for i in range(n):
            for j in range(n):
                v = grid[i][j]
                ax.text(j, i, "n/a" if v != v else f"{v:.2f}", ha="center",
                        va="center", fontsize=8)
        ax.set_xticks(range(n), names, rotation=45, ha="right", fontsize=7)
        ax.set_yticks(range(n), names, fontsize=7)
        oriented = "oriented so higher = more compact" if key == "compactness" else "signs as published, not harmonised"
        ax.set_title(f"{key}: Spearman across the ensemble\n({oriented})", fontsize=8)
        fig.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle(
        "do the measures rank plans differently here? (CRITERIA.md 3, 5.2)", fontsize=10
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def _plot_trace(report, columns, plt):
    """Split R-hat and ESS against draws per chain, for both quantities."""
    trace = report["diagnostics"]["convergence_trace"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
    for name, style in (("cut_edges", "o-"), ("pop_spread", "s-")):
        rows = [r for r in trace[name] if r["split_rhat"] is not None]
        if rows:
            axes[0].plot([r["draws_per_chain"] for r in rows],
                         [r["split_rhat"] for r in rows], style, label=name)
        rows = [r for r in trace[name] if r["ess"] is not None]
        if rows:
            axes[1].plot([r["draws_per_chain"] for r in rows],
                         [r["ess"] for r in rows], style, label=name)
    axes[0].axhline(RHAT_GATE, color="red", ls=":", lw=1, label=f"gate {RHAT_GATE}")
    axes[0].axhline(1.0, color="grey", ls="-", lw=0.5)
    axes[0].set_xlabel("draws per chain")
    axes[0].set_ylabel("rank-normalized split R-hat")
    axes[0].set_title(
        f"PSRF trace — {report['ensemble']['convergence']['n_chains']} completed chains "
        f"of {report['config']['chains']}", fontsize=8)
    axes[0].legend(fontsize=7)
    axes[1].set_xlabel("draws per chain")
    axes[1].set_ylabel("ESS (bulk)")
    axes[1].set_title("effective sample size", fontsize=8)
    axes[1].legend(fontsize=7)
    fig.suptitle(
        f"round {report['round']}: convergence, epsilon={report['config']['epsilon']:g}, "
        f"failure rate {report['ensemble']['failure_rate']:.3f}", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def summary_lines(report: Mapping[str, Any]) -> list[str]:
    """The report a reader gets on stdout. Both rates, always, and every gate."""
    lines = [
        f"districting-bench round {report['round']}  "
        f"master_seed={report['config']['master_seed']}  size={report['config']['size']}",
        "",
        f"ensemble: {report['ensemble']['n_completed']}/{report['ensemble']['n_requested']} draws, "
        f"{report['ensemble']['distinct_plans']} distinct, "
        f"{report['ensemble']['chain_failures']} chain failures "
        f"(rate {report['ensemble']['failure_rate']:.3f})",
    ]
    conv = report["ensemble"]["convergence"]
    for name in ("cut_edges", "pop_spread"):
        lines.append(
            f"  {name:<11} split R-hat "
            f"{_fmt(conv[name]['split_rhat'])}   ESS {_fmt(conv[name]['ess'], 1)}"
        )
    lines.append("")
    lines += report["diagnostics"]["report_lines"]
    lines.append("")
    strata = report["diagnostics"]["null_strata"]
    for name, stratum in strata.items():
        if name == "note":
            continue
        mark = "" if stratum.get("in_gate_sample", True) else "   [not in the gate]"
        lines.append(
            f"  {name:<22} FPR {_fmt(stratum['fpr'])}  "
            f"({stratum['flagged']}/{stratum['resolved']} resolved of "
            f"{stratum['n']}){mark}"
        )
    lines.append("")
    lines.append("gates:")
    # The TPR gate's key carries the magnitude it was measured at, so a report
    # written under a different state -- or an earlier round at a different
    # magnitude -- simply does not have the key this configuration expects. That
    # is information, not a crash: say the gate is absent and name the keys the
    # report does carry, so a reader can see it was measured at another magnitude.
    tpr_keys = [k for k in report["gates"] if k.startswith("tpr_at_")]
    ordered = (tpr_keys or [gate_key()]) + [
        "fpr_on_nulls", "split_rhat", "legal_compliance"
    ]
    for key in ordered:
        gate = report["gates"].get(key)
        if gate is None:
            lines.append(
                f"  {key:<18} ABSENT — this report carries "
                f"{sorted(report['gates']) if not tpr_keys else tpr_keys}"
            )
            continue
        verdict = {True: "PASS", False: "FAIL", None: "NOT MEASURED"}[gate["pass"]]
        extra = ""
        if key == "legal_compliance":
            extra = f"  at epsilon={gate['epsilon']:g}"
        lines.append(
            f"  {key:<18} target {gate['target']}  value {_fmt(gate['value'])}  "
            f"{verdict}{extra}"
        )
    qual = report["gates"].get("qualification")
    if qual and not qual["meaningful"]:
        lines.append("")
        lines.append("  *** " + qual["note"])
        for reason in qual["reasons"]:
            lines.append(f"      - {reason}")
    for caveat in (qual or {}).get("caveats", []):
        lines.append(f"  note: {caveat}")
    fw = report["firewall"]
    lines.append("")
    lines.append(f"firewall: {'clean' if fw['clean'] else 'VIOLATION'}  "
                 f"config sha256 {fw['config_sha256'][:16]}...")
    return lines


def _fmt(x, digits: int = 4) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m detect.bench",
        description="Headless districting bench: bench-results.json plus plots.",
    )
    parser.add_argument("--master-seed", type=int, required=False, default=None,
                        help="the one integer the whole run is reproducible from")
    parser.add_argument("--round", type=int, required=False, default=None,
                        help="round number; part of every derived seed, so scenarios "
                             "regenerate rather than being re-scored")
    parser.add_argument("--state", default="IA",
                        help="target state key: IA or CO (default IA)")
    parser.add_argument("--quick", action="store_true",
                        help="much smaller ensemble at a looser epsilon, for tests")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="default docs/progress/round-NN")
    parser.add_argument("--no-plots", action="store_true", help="skip the PNGs")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS,
                        help="worker processes for the chains; affects wall clock "
                             "and nothing in the report outside timing")
    parser.add_argument("--verify", type=Path, default=None, metavar="ROUND_DIR",
                        help="re-derive every ground-truth claim in a written "
                             "bench-results.json from the plans beside it, and "
                             "exit non-zero on any disagreement")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure(args.state)
    if args.verify is None and (args.master_seed is None or args.round is None):
        parser.error("--master-seed and --round are required unless --verify is given")
    if args.verify is not None:
        result = verify(args.verify)
        print(f"verifying {result['round_dir']}")
        print(f"  {result['checked']} scenarios, {result['checks']} claims "
              f"re-derived from the plans on disk")
        for failure in result["failures"]:
            print(f"  MISMATCH {failure['id']}.{failure['field']}: "
                  f"reported {failure['reported']!r}, recomputed "
                  f"{failure['recomputed']!r}")
        print("  OK" if result["ok"] else f"  {len(result['failures'])} MISMATCHES")
        return 0 if result["ok"] else 1
    report = run(
        master_seed=args.master_seed,
        round_number=args.round,
        size=QUICK if args.quick else FULL,
        out_dir=args.out_dir,
        make_plots=not args.no_plots,
        jobs=args.jobs,
    )
    print("\n".join(summary_lines(report)))
    out_dir = Path(report["_path"]).parent
    print(f"\nwrote {report['_path']}")
    print(f"wrote {out_dir / PLANS_DIRNAME}/ "
          f"({report['plans']['n_files']} plans; check them with "
          f"--verify {out_dir})")
    for name in report.get("plots", []):
        print(f"wrote {out_dir / name}")
    failed = [
        key for key in (gate_key(), "fpr_on_nulls", "split_rhat", "legal_compliance")
        if report["gates"][key]["pass"] is not True
    ]
    if failed:
        print(f"\ngates not passed: {', '.join(failed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
