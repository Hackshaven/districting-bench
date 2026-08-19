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
import random
import subprocess
import sys
import time
from dataclasses import dataclass, field
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

STATE = "IA"
UNIT_KIND = "county"
K = 4

#: FEASIBILITY.md 5.1, measured: at this epsilon roughly 7 of 8 seeds complete
#: and the sampler reaches a 57-71 person spread. Tighter fails on most seeds.
EPSILON = 2e-4

#: FEASIBILITY.md 5.1: a positive value re-roots an already-exhausted spanning
#: tree and the chain dies. Not a tunable; 0 is the only correct value here.
NODE_REPEATS = 0

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = REPO_ROOT / "data" / "processed"
FIREWALL_CONFIG = REPO_ROOT / "tools" / "firewall.yaml"
FIREWALL_SCRIPT = REPO_ROOT / "tools" / "check_firewall.py"
ENACTED_PLAN = PROCESSED / "ia_enacted_cd118.csv"
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
    a percentile at the rule's threshold.
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


FULL = Size(
    label="full",
    epsilon=EPSILON,
    chains=8,
    steps=130,
    null_chains=4,
    null_steps=70,
    replicates=8,
    magnitudes=(1, 2),
    probe_magnitudes=(3,),
    probe_replicates=2,
    n_hard_nulls=15,
    n_random_nulls=15,
    max_iterations=40_000,
    restarts=4,
)

QUICK = Size(
    label="quick",
    epsilon=1e-3,
    chains=2,
    steps=14,
    null_chains=2,
    null_steps=12,
    replicates=1,
    magnitudes=(1, 2),
    probe_magnitudes=(),
    probe_replicates=0,
    n_hard_nulls=3,
    n_random_nulls=3,
    max_iterations=4_000,
    restarts=2,
    trace_checkpoints=4,
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
    gen_adjacency, gen_populations = ensemble.load_inputs()
    inputs = Inputs(
        gen_adjacency=gen_adjacency,
        gen_populations=gen_populations,
        adjacency=EP.load_adjacency(),
        populations=EP.populations(),
        units=EP.load_units(),
        geometry=GU.load_geometry(),
        dem={},
        rep={},
        enacted=EP.load_plan(ENACTED_PLAN),
    )
    dem, rep = elections.two_party(elections.load_elections())
    inputs.dem, inputs.rep = dict(dem), dict(rep)
    inputs.check()
    return inputs


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
    """One scored scenario on its way into the report."""

    id: str
    kind: str
    plan: dict
    intended_seat_shift: int
    realized_seat_shift: float | None
    target_party: str | None
    baseline: str | None
    metrics: dict
    locations: dict
    legal: bool
    legal_failures: list
    notes: tuple
    seconds: float = 0.0

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
                restarts=size.restarts,
            )
            seconds = time.perf_counter() - started
            case_id = f"gerry_{party.lower()}_{magnitude}seat_{index:02d}"
            attempts.append(
                {
                    "id": case_id,
                    "target_party": party,
                    "baseline": baseline_id,
                    "intended_seat_shift": magnitude,
                    "seed": seed,
                    "reached": result is not None,
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
                    legal=result.legality.passed,
                    legal_failures=result.legality.failures(),
                    notes=(
                        f"baseline {baseline_id}: {result.baseline_seat_count} "
                        f"{party} seats -> {result.realized_seat_count}; "
                        f"population spread {result.population_spread}; "
                        f"seat ceiling at work epsilon "
                        f"{result.seat_ceiling_at_work_epsilon}",
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
    """Neutral maps, in two strata, both labelled ground-truth negative.

    ``null_geography_*`` come from ``adversarial.nulls.sample_nulls``, which
    ranks distinct neutral plans by distance from the ensemble's median seat
    count and then by efficiency gap, taking them alternately from either side of
    the median. Those are the hardest negatives available: neutral by
    construction, extreme by selection.

    ``null_random_*`` are drawn uniformly from the same pool's distinct plans,
    excluding anything the first stratum already took. They are the ordinary
    negative — what a neutral process usually produces rather than what it
    produces at its worst — and without them the pooled FPR would be reporting
    the selection rule rather than the detector.

    Both strata are drawn from a pool sampled under its own seeds, so no null is
    scored against an ensemble it is itself a draw from.
    """
    cases: list[Case] = []
    plan_cache = compactness.MeasureCache()

    hard = N.sample_nulls(
        inputs.adjacency,
        inputs.populations,
        K,
        size.epsilon,
        (),
        inputs.dem,
        inputs.rep,
        sampler=N.sampler_from_plans(pool),
        party="D",
        n_select=size.n_hard_nulls,
        balance_directions=True,
        drawn_by=(
            f"generate.ensemble.run_chains, {size.null_chains} independent "
            f"chains x {size.null_steps} steps at epsilon={size.epsilon:g}"
        ),
    )
    taken = {frozenset(plan.items()) for plan in (case.plan for case in hard)}
    for case in hard:
        cases.append(
            _null_case(
                case.id,
                case.plan,
                case.seat_shift,
                inputs,
                size,
                plan_cache,
                notes=(
                    f"selection rank {case.selection_rank} of "
                    f"{case.distinct_pool_size} distinct plans; "
                    f"{case.selection_rule}",
                    f"ensemble median {case.ensemble_median_seats} D seats, this "
                    f"plan {case.realized_seat_count}",
                ),
            )
        )

    distinct: list[dict] = []
    seen: set = set()
    for plan in pool:
        key = ensemble.canonical(dict(plan), K)
        if key in seen:
            continue
        seen.add(key)
        if frozenset(dict(plan).items()) in taken:
            continue
        distinct.append(dict(plan))
    distinct.sort(key=lambda p: tuple(sorted(p.items())))
    rng = random.Random(seeds.derive(master_seed, _purpose(round_number, "null-random"), 0))
    wanted = min(size.n_random_nulls, len(distinct))
    for rank, plan in enumerate(rng.sample(distinct, wanted), start=1):
        median = N.median_seats(list(pool), inputs.dem, inputs.rep, "D")
        seats = partisan.seat_counts(plan, inputs.dem, inputs.rep)[0]
        cases.append(
            _null_case(
                f"null_random_{rank:02d}",
                plan,
                float(seats) - median,
                inputs,
                size,
                plan_cache,
                notes=(
                    "uniform draw from the distinct plans of an independent "
                    "neutral pool; not selected for looking biased",
                    f"ensemble median {median} D seats, this plan {seats}",
                ),
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
) -> Case:
    legality = G.check_legality(dict(plan), inputs.adjacency, inputs.populations, K, size.epsilon)
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
        legal=legality.passed,
        legal_failures=legality.failures(),
        notes=notes,
    )


def relocate(cases: Sequence[Case], columns: Mapping[str, Sequence[Any]], inputs: Inputs) -> None:
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


def _finite(x: float | None) -> float | None:
    """A real finite float, or ``None``. ``nan`` and ``inf`` are not measurements."""
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else x


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
# the run
# --------------------------------------------------------------------------- #

def run(
    master_seed: int,
    round_number: int,
    size: Size = FULL,
    out_dir: Path | None = None,
    make_plots: bool = True,
) -> dict[str, Any]:
    """Do the whole bench and return the report dict. Writes JSON and PNGs."""
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
    ens = ensemble.run_chains(
        inputs.gen_adjacency,
        inputs.gen_populations,
        K,
        size.epsilon,
        size.steps,
        chain_seeds,
        NODE_REPEATS,
    )
    timing["ensemble_seconds"] = time.perf_counter() - started
    timing["ensemble_chain_seconds"] = [t.seconds for t in ens.traces]

    # 2. the null pool, independently seeded --------------------------------- #
    started = time.perf_counter()
    null_seeds = seeds.stream(
        master_seed, _purpose(round_number, "null-pool"), size.null_chains
    )
    pool = ensemble.run_chains(
        inputs.gen_adjacency,
        inputs.gen_populations,
        K,
        size.epsilon,
        size.null_steps,
        null_seeds,
        NODE_REPEATS,
    )
    timing["null_pool_seconds"] = time.perf_counter() - started

    # 3. reference columns --------------------------------------------------- #
    started = time.perf_counter()
    columns, cache_stats = ensemble_columns(ens.plans, inputs)
    timing["ensemble_metrics_seconds"] = time.perf_counter() - started

    # 4. scenarios ----------------------------------------------------------- #
    baselines = {
        "enacted": dict(inputs.enacted),
        "ensemble_max_d": pick_max_dem_plan(ens.plans, inputs),
    }
    started = time.perf_counter()
    planted, attempts = plant_cases(inputs, baselines, master_seed, round_number, size)
    timing["planting_seconds"] = time.perf_counter() - started
    timing["plant_seconds"] = {case.id: case.seconds for case in planted}

    started = time.perf_counter()
    nulls = null_cases(inputs, pool.plans, master_seed, round_number, size)
    timing["nulls_seconds"] = time.perf_counter() - started

    cases = planted + nulls
    started = time.perf_counter()
    relocate(cases, columns, inputs)
    timing["scoring_seconds"] = time.perf_counter() - started

    # 5. decisions ----------------------------------------------------------- #
    scenarios = [case.scenario() for case in cases]
    decisions = {s.id: d for s, d in C.decide(scenarios, RULE)}
    matrix = C.confusion_matrix(scenarios, RULE)
    curve = C.detection_curve(scenarios, RULE)
    gate_block = C.gates(scenarios, RULE)

    # 6. the plan under review ----------------------------------------------- #
    review_metrics = plan_metrics(inputs.enacted, inputs)
    review_locations = O.locate(
        inputs.enacted,
        columns,
        review_metrics,
        context=context_for(inputs.enacted, inputs),
        metrics=LOCATED_METRICS,
    )
    review_decision = C.flag(review_locations, RULE)

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
        attempts=attempts,
        baselines=baselines,
        inputs=inputs,
        review_metrics=review_metrics,
        review_locations=review_locations,
        review_decision=review_decision,
        scenarios=scenarios,
        out_dir=out_dir,
        make_plots=make_plots,
    )

    timing["total_seconds"] = time.perf_counter() - t0
    timing["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report["timing"] = timing

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
    ``gates.tpr_at_2seat`` finds it where the contract says it is.
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
    legal = [case.legal for case in cases]
    legal_fraction = (sum(legal) / len(legal)) if legal else None

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
                "legal": case.legal,
                "legal_failures": case.legal_failures,
                "metrics": {name: case.metrics.get(name) for name in LOCATED_METRICS},
                "percentiles": O.percentiles(case.locations),
                "statuses": {n: loc.status for n, loc in case.locations.items()},
                "fired_metrics": list(decision.fired_metrics),
                "eligible_metrics": list(decision.eligible),
                "excluded_metrics": {m: w for m, w in decision.excluded},
                "seats": {
                    "dem": case.metrics.get("dem_seats"),
                    "rep": case.metrics.get("rep_seats"),
                },
                "notes": list(case.notes),
            }
        )

    gates_out = {
        "tpr_at_2seat": gate_block["tpr_at_2seat"],
        "fpr_on_nulls": gate_block["fpr_on_nulls"],
        "split_rhat": {
            "target": RHAT_GATE,
            "value": worst_rhat,
            "pass": None if worst_rhat is None else worst_rhat <= RHAT_GATE,
            "note": (
                "worst of cut_edges and pop_spread, rank-normalized split R-hat "
                "over completed chains; CRITERIA.md 8 target band 1.00-1.01"
            ),
        },
        "legal_compliance": {
            "target": 1.0,
            "value": legal_fraction,
            "pass": None if legal_fraction is None else legal_fraction >= 1.0,
            "n": len(legal),
            "note": (
                "fraction of scenario plans passing every constraint in "
                "adversarial.gerrymander.check_legality at this epsilon"
            ),
        },
        "rule": RULE.as_dict(),
    }

    hard = [c for c in cases if c.id.startswith("null_geography")]
    random_nulls = [c for c in cases if c.id.startswith("null_random")]

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
            "tpr_at_2seat": C.tpr_at(curve, 2),
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
                )
            },
            "tpr_ci95": list(matrix["tpr_ci95"]) if matrix["tpr_ci95"] else None,
            "fpr_ci95": list(matrix["fpr_ci95"]) if matrix["fpr_ci95"] else None,
        },
        "gates": gates_out,
        "firewall": firewall_block(),
        "plan_under_review": {
            "id": "ia_enacted_cd118",
            "source": str(ENACTED_PLAN.relative_to(REPO_ROOT)),
            "plan_digest": O.plan_digest(inputs.enacted),
            "metrics": {n: kw["review_metrics"].get(n) for n in LOCATED_METRICS},
            "percentiles": O.percentiles(kw["review_locations"]),
            "statuses": {n: l.status for n, l in kw["review_locations"].items()},
            "flagged": kw["review_decision"].flagged,
            "reason": kw["review_decision"].reason,
            "seats": {
                "dem": kw["review_metrics"]["dem_seats"],
                "rep": kw["review_metrics"]["rep_seats"],
            },
            "note": (
                "reported, never scored: the enacted plan carries no manufactured "
                "ground truth, so it is not a scenario and contributes to no rate "
                "in the confusion matrix"
            ),
        },
        "diagnostics": {
            "null_strata": {
                "null_geography": _stratum(hard, decisions),
                "null_random": _stratum(random_nulls, decisions),
                "note": (
                    "the gate reads the pooled rate; these are the same cases "
                    "split by how they were chosen"
                ),
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
            "convergence_trace": convergence_trace(ens, size.trace_checkpoints),
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


def _summary(column: Sequence[Any]) -> dict[str, Any]:
    """``outlier.summarize`` of one column, or an explicit reason it has none."""
    defined = [float(v) for v in column if v is not None]
    undefined = len(column) - len(defined)
    if not defined:
        return {"n": 0, "n_undefined": undefined,
                "note": "every draw is undefined for this metric"}
    return O.summarize(defined, n_undefined=undefined).as_dict()


def _stratum(cases: Sequence[Case], decisions) -> dict[str, Any]:
    n = len(cases)
    flagged = sum(1 for case in cases if decisions[case.id].flagged)
    ci = C.wilson_interval(flagged, n)
    return {
        "n": n,
        "flagged": flagged,
        "fpr": (flagged / n) if n else None,
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
        "statement about what is legally constructible from that baseline"
    )
    return out


def _alternative(rule: C.Rule, scenarios) -> dict[str, Any]:
    matrix = C.confusion_matrix(scenarios, rule)
    curve = C.detection_curve(scenarios, rule)
    return {
        "rule": rule.as_dict(),
        "tpr": matrix["tpr"],
        "fpr": matrix["fpr"],
        "tpr_at_2seat": C.tpr_at(curve, 2),
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
    ax.set_title(f"round {report['round']}: confusion matrix\n{RULE.describe()}", fontsize=8)

    ax = axes[1]
    rounds = [h["round"] for h in history]
    nan = float("nan")
    pick = lambda key: [nan if h[key] is None else h[key] for h in history]
    ax.plot(rounds, pick("tpr"), "o-", label="TPR (all planted)")
    ax.plot(rounds, pick("tpr_at_2seat"), "s-", label="TPR at 2-seat shift")
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
                    "tpr_at_2seat": other["confusion"]["tpr_at_2seat"],
                    "fpr": other["confusion"]["fpr_on_nulls"],
                }
            except Exception:
                continue
    rows[int(report["round"])] = {
        "round": int(report["round"]),
        "tpr": report["confusion"]["matrix"]["tpr"],
        "tpr_at_2seat": report["confusion"]["tpr_at_2seat"],
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
    for name in ("null_geography", "null_random"):
        s = strata[name]
        lines.append(f"  {name:<16} FPR {_fmt(s['fpr'])}  ({s['flagged']}/{s['n']})")
    lines.append("")
    lines.append("gates:")
    for key in ("tpr_at_2seat", "fpr_on_nulls", "split_rhat", "legal_compliance"):
        gate = report["gates"][key]
        verdict = {True: "PASS", False: "FAIL", None: "NOT MEASURED"}[gate["pass"]]
        lines.append(
            f"  {key:<18} target {gate['target']}  value {_fmt(gate['value'])}  {verdict}"
        )
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
    parser.add_argument("--master-seed", type=int, required=True,
                        help="the one integer the whole run is reproducible from")
    parser.add_argument("--round", type=int, required=True,
                        help="round number; part of every derived seed, so scenarios "
                             "regenerate rather than being re-scored")
    parser.add_argument("--quick", action="store_true",
                        help="much smaller ensemble at a looser epsilon, for tests")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="default docs/progress/round-NN")
    parser.add_argument("--no-plots", action="store_true", help="skip the PNGs")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run(
        master_seed=args.master_seed,
        round_number=args.round,
        size=QUICK if args.quick else FULL,
        out_dir=args.out_dir,
        make_plots=not args.no_plots,
    )
    print("\n".join(summary_lines(report)))
    print(f"\nwrote {report['_path']}")
    for name in report.get("plots", []):
        print(f"wrote {Path(report['_path']).parent / name}")
    failed = [
        key for key in ("tpr_at_2seat", "fpr_on_nulls", "split_rhat", "legal_compliance")
        if report["gates"][key]["pass"] is not True
    ]
    if failed:
        print(f"\ngates not passed: {', '.join(failed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
