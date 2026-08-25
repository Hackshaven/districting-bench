"""ReCom sampler for the neutral baseline ensemble.

Iowa Code ch. 42 criteria only, in statutory order:

1. population equality  -> the epsilon constraint
2. contiguity           -> guaranteed by ReCom on the rook graph
3. whole counties       -> guaranteed by construction; counties are the units
4. compactness          -> measured, never constrained or optimised

This module sees population and adjacency. It sees nothing else, by any route:
inputs come from :mod:`generate.units`, whose schema allowlist rejects any column
outside ``{GEOID, NAME, pop, geometry}``. See docs/ARCHITECTURE.md section 4.

Two things here are not style choices.

**node_repeats must be 0.** GerryChain's default cut finder
(``find_balanced_edge_cuts_memoization``) already searches each spanning tree
exhaustively, so a positive ``node_repeats`` re-roots the same exhausted tree
instead of drawing a new one, and the attempt budget is spent without ever seeing
a new tree. Passing 10 made every epsilon <= 5e-4 look infeasible and produced a
false headline finding in the feasibility pass; docs/FEASIBILITY.md section 5.1
has the A/B. GerryChain warns about this, and the warning was suppressed by a
``filterwarnings("ignore")`` in the probe that hid it. **Nothing in this package
suppresses warnings**, and there is a test that asserts so.

**Chain failures are data, not errors.** At tight epsilon the ReCom proposal dies
on a large fraction of seeds (63% at epsilon=1e-4, 13% at 2e-4;
docs/FEASIBILITY.md section 5.1). Failures are caught per chain, counted and
reported. They are never retried under a fresh seed: the seeds that survive are
not a random subset of the seeds that were tried, so quietly re-drawing until a
chain lives would hide a real sampling bias behind a clean-looking ensemble. The
failure rate is a reported quantity of the run.

**Plan quantities take k.** ``district_totals``, ``population_spread`` and
``canonical`` are public and are called by ``detect`` on plans this module did
not draw — the enacted map and the adversarially planted ones. A plan with an
empty district is invisible in its own values, so those functions require the
number of districts and raise on a district of ``1..k`` that no unit was
assigned to, rather than reporting a spread over the districts that happen to be
occupied. See :func:`districts_of`.
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from functools import partial
from statistics import median
from typing import Iterable, Iterator, Mapping, Sequence

from .seeds import derive
from .units import load_adjacency, load_units

# GEOID -> district, districts numbered 1..k (docs/ARCHITECTURE.md section 3).
Plan = dict[str, int]

# Node attribute holding population. One of the four names the schema allowlist
# in units.py permits.
POP_ATTR = "pop"


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------


def load_inputs(units_path=None, adjacency_path=None):
    """Return ``(adjacency, populations)`` for the configured state.

    The only sanctioned way into this package. Both loaders live in units.py so
    the load-time schema guard applies; do not read data files from here.
    """
    frame = load_units(units_path)
    populations = {
        str(geoid): int(value) for geoid, value in zip(frame["GEOID"], frame[POP_ATTR])
    }
    adjacency = load_adjacency(adjacency_path)
    return adjacency, populations


def check_inputs(
    adjacency: Mapping[str, Sequence[str]],
    populations: Mapping[str, int],
    k: int,
    epsilon: float,
    steps: int,
) -> None:
    """Raise on anything that is a caller error rather than a chain failure.

    Called once by :func:`run_chains` before any chain starts, so a malformed
    graph raises loudly instead of being silently counted as a run of unlucky
    seeds.
    """
    if not populations:
        raise ValueError("no units given")
    if set(adjacency) != set(populations):
        only_adj = sorted(set(adjacency) - set(populations))[:5]
        only_pop = sorted(set(populations) - set(adjacency))[:5]
        raise ValueError(
            "adjacency and populations describe different unit sets; "
            f"adjacency-only e.g. {only_adj}, population-only e.g. {only_pop}"
        )
    for unit, value in populations.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"population for {unit} is not a non-negative int: {value!r}")
    for unit, neighbours in adjacency.items():
        if len(set(neighbours)) != len(neighbours):
            repeated = sorted({o for o in neighbours if list(neighbours).count(o) > 1})
            raise ValueError(
                f"adjacency of {unit} lists a duplicate neighbour {repeated}; "
                "an edge listed twice would be counted twice by cut_edges"
            )
        for other in neighbours:
            if other == unit:
                raise ValueError(f"self-loop in adjacency at {unit}")
            if other not in adjacency:
                raise ValueError(f"adjacency of {unit} names unknown unit {other}")
            if unit not in adjacency[other]:
                raise ValueError(
                    f"adjacency is not symmetric: {other} in adjacency[{unit}] "
                    f"but {unit} not in adjacency[{other}]"
                )
    if not isinstance(k, int) or isinstance(k, bool) or k < 2:
        raise ValueError(f"k must be an int >= 2, got {k!r}")
    if k > len(populations):
        raise ValueError(f"k={k} exceeds the {len(populations)} units available")
    if not (0 < epsilon < 1):
        raise ValueError(f"epsilon must lie in (0, 1), got {epsilon!r}")
    if not isinstance(steps, int) or isinstance(steps, bool) or steps < 1:
        raise ValueError(f"steps must be an int >= 1, got {steps!r}")
    if not _connected(adjacency):
        raise ValueError(
            "the unit graph is not connected; no contiguous partition into k "
            "districts exists for every k, and ReCom cannot start"
        )


def _connected(adjacency: Mapping[str, Sequence[str]]) -> bool:
    start = next(iter(adjacency))
    seen = {start}
    stack = [start]
    while stack:
        unit = stack.pop()
        for other in adjacency[unit]:
            if other not in seen:
                seen.add(other)
                stack.append(other)
    return len(seen) == len(adjacency)


def build_graph(
    adjacency: Mapping[str, Sequence[str]], populations: Mapping[str, int]
):
    """A GerryChain ``Graph`` carrying population and nothing else."""
    import networkx as nx
    from gerrychain import Graph

    raw = nx.Graph()
    for unit, value in populations.items():
        raw.add_node(unit, **{POP_ATTR: int(value)})
    for unit, neighbours in adjacency.items():
        for other in neighbours:
            raw.add_edge(unit, other)
    return Graph.from_networkx(raw)


# --------------------------------------------------------------------------
# plan-level quantities
# --------------------------------------------------------------------------


def districts_of(plan: Plan, k: int | None) -> list[int]:
    """The district ids a k-district plan is about, with the invariant enforced.

    docs/ARCHITECTURE.md section 3 requires district ids to be "exactly 1..K,
    none empty" and assigns the check to ``evaluate.plan.validate`` — which is on
    the far side of the firewall and cannot be called from here. So the part of
    that invariant these functions depend on is re-checked here. The duplication
    is the deliberate kind (ARCHITECTURE section 1); the alternative is a plan
    quantity that is quietly wrong.

    ``k`` is a required argument rather than an optional one because the failure
    it prevents is invisible by construction. A plan whose district ``k`` happens
    to be empty is, read off its own values, indistinguishable from a
    ``k-1``-district plan: ``{a:1, b:1, c:2, d:3}`` is a 3-district plan and a
    4-district plan with an empty district, and no amount of looking at it can
    tell you which. Inferring the district set from ``plan.values()`` therefore
    is not a safe default, it is the bug — it reports a max-min spread over three
    districts when the fourth holds 0 persons, and it makes the two plans compare
    equal under :func:`canonical`. Passing ``k`` is how the caller says which
    question it is asking. ReCom output always satisfies the invariant; the
    enacted and adversarially planted plans that ``detect`` puts through these
    same functions are not ReCom output.

    Pass ``k=None`` to opt out explicitly and ask only about the districts that
    appear. That path still rejects gaps and non-positive labels, but it cannot
    detect a trailing empty district — nothing can — so it is spelled out at the
    call site rather than reached by omission.

    Returns:
        ``[1, ..., k]`` (or ``[1, ..., K]`` for the observed ``K`` when
        ``k is None``).

    Raises:
        ValueError: if the plan is empty, carries labels outside ``1..k``, or
            leaves a district of ``1..k`` with no units.
    """
    labels = set(plan.values())
    if not labels:
        raise ValueError("plan assigns no units")
    if k is None:
        observed = sorted(labels)
        if observed != list(range(1, len(observed) + 1)):
            raise ValueError(
                f"district ids must be 1..K with no gaps, got {observed}; "
                "pass k explicitly if some district is meant to be empty"
            )
        return observed
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError(f"k must be an int >= 1 or None, got {k!r}")
    expected = set(range(1, k + 1))
    stray = sorted(labels - expected)
    if stray:
        raise ValueError(f"plan assigns districts outside 1..{k}: {stray}")
    empty = sorted(expected - labels)
    if empty:
        raise ValueError(
            f"plan has no units in district(s) {empty} of 1..{k}; an empty "
            "district is not a district, and folding it away would understate "
            "the population spread and canonicalize this as a "
            f"{len(labels)}-district plan"
        )
    return sorted(expected)


def district_totals(
    plan: Plan, populations: Mapping[str, int], k: int | None
) -> dict[int, int]:
    """Population per district, keyed by every district in ``1..k``.

    See :func:`districts_of` for why ``k`` is required and what ``k=None`` means.
    """
    totals: dict[int, int] = {district: 0 for district in districts_of(plan, k)}
    for unit, district in plan.items():
        totals[district] += int(populations[unit])
    return totals


def population_spread(plan: Plan, populations: Mapping[str, int], k: int | None) -> int:
    """max - min district population over all of ``1..k``, in persons.

    Persons, not a fraction of ideal, because that is the number the enacted plan
    is quoted in (94) and the one a reader can check by hand.

    ``k`` is required: an empty district makes this number wrong by an amount the
    size of a district, and it raises rather than reporting the spread over the
    districts that happen to be occupied. See :func:`districts_of`.
    """
    totals = district_totals(plan, populations, k)
    return max(totals.values()) - min(totals.values())


def cut_edges(plan: Plan, adjacency: Mapping[str, Sequence[str]]) -> int:
    """Count adjacent unit pairs assigned to different districts.

    Each unordered pair is counted once: the ``unit < other`` test takes one
    direction of a symmetric adjacency, and the neighbours of a unit are
    de-duplicated here so that a repeated entry cannot contribute the same edge
    twice. :func:`check_inputs` rejects both a duplicate neighbour and an
    asymmetric list, so on a checked graph the de-duplication is a no-op; it is
    here because this function is public and is also called on graphs it did not
    check itself.
    """
    total = 0
    for unit, neighbours in adjacency.items():
        for other in set(neighbours):
            if unit < other and plan[unit] != plan[other]:
                total += 1
    return total


def canonical(plan: Plan, k: int | None) -> frozenset:
    """A district-label-invariant key for a plan.

    Two plans that differ only in which district got which number are the same
    plan, and counting them twice would overstate how much of the space a chain
    covered.

    ``k`` is required for the reason given in :func:`districts_of`: with the
    district set inferred from the plan's own values, a 4-district plan with an
    empty district produces a 3-block key and compares equal to a genuine
    3-district plan, so ``distinct_plans`` would conflate the two. With ``k``
    supplied, an empty district raises instead, and the key always has exactly
    ``k`` non-empty blocks.
    """
    groups: dict[int, set] = {district: set() for district in districts_of(plan, k)}
    for unit, district in plan.items():
        groups[district].add(unit)
    return frozenset(frozenset(members) for members in groups.values())


# --------------------------------------------------------------------------
# sampling
# --------------------------------------------------------------------------


def sample(
    adjacency: Mapping[str, Sequence[str]],
    populations: Mapping[str, int],
    k: int,
    epsilon: float,
    steps: int,
    seed: int,
    node_repeats: int = 0,
) -> Iterator[Plan]:
    """Yield ``steps`` plans from one ReCom chain.

    The chain may die partway through — that is expected at tight epsilon and the
    exception is left to propagate here, so that :func:`run_chains` can record
    which seed failed and after how many steps. A caller iterating this directly
    is responsible for its own failure handling.

    Args:
        adjacency: ``{GEOID: [GEOID, ...]}``, symmetric.
        populations: ``{GEOID: persons}``.
        k: number of districts; plans are labelled ``1..k``.
        epsilon: per-district population tolerance as a fraction of ideal. Note
            it bounds each district's deviation, so the permitted max-min spread
            is about ``2 * epsilon * ideal`` — docs/FEASIBILITY.md section 5.2.
        steps: chain length, including the initial state.
        seed: this chain's seed; sub-seeds are derived from it.
        node_repeats: must be 0. See the module docstring.
    """
    check_inputs(adjacency, populations, k, epsilon, steps)
    return _iterate(adjacency, populations, k, epsilon, steps, seed, node_repeats)


def _iterate(adjacency, populations, k, epsilon, steps, seed, node_repeats):
    from gerrychain import MarkovChain, Partition, accept, constraints, updaters
    from gerrychain.partition import recursive_tree_part
    from gerrychain.proposals import recom

    if node_repeats:
        warnings.warn(
            "node_repeats must be 0 with GerryChain's default memoized cut "
            "finder; a positive value re-roots an already exhausted spanning "
            "tree and makes tight epsilon look infeasible. See "
            "docs/FEASIBILITY.md section 5.1.",
            RuntimeWarning,
            stacklevel=3,
        )

    graph = build_graph(adjacency, populations)
    ideal = sum(populations.values()) / k
    districts = list(range(1, k + 1))

    assignment = recursive_tree_part(
        graph,
        districts,
        ideal,
        POP_ATTR,
        epsilon,
        node_repeats=node_repeats,
        rng=derive(seed, "initial-partition", 0),
    )
    initial = Partition(
        graph,
        assignment,
        {"population": updaters.Tally(POP_ATTR, alias="population")},
    )
    chain = MarkovChain(
        proposal_fn=partial(
            recom,
            pop_col=POP_ATTR,
            pop_target=ideal,
            epsilon=epsilon,
            node_repeats=node_repeats,
        ),
        constraints=[constraints.within_percent_of_ideal_population(initial, epsilon)],
        acceptance_fn=accept.always_accept,
        initial_partition=initial,
        total_steps=steps,
        rng=derive(seed, "markov-chain", 0),
    )
    unit_of = _unit_labels(initial.graph, populations)
    for state in chain:
        plan: Plan = {}
        for district, nodes in state.parts.items():
            for node in nodes:
                plan[unit_of[node]] = int(district)
        yield plan


def _unit_labels(graph, populations: Mapping[str, int]) -> dict:
    """Map GerryChain's internal node ids back to GEOIDs.

    A ``Partition`` re-indexes the graph to integers and keeps the original label
    in node data. Getting this wrong would silently permute every plan, so the
    recovered labels are checked against the units we asked for.
    """
    labels = {}
    mismatched = []
    for node in graph.node_indices:
        data = graph.node_data(node)
        unit = str(data["__networkx_node__"] if "__networkx_node__" in data else node)
        labels[node] = unit
        # The set of names matching is not enough: a permutation would pass that.
        # The population carried by the node has to belong to the unit we think
        # the node is.
        if unit not in populations or data.get(POP_ATTR) != populations[unit]:
            mismatched.append(unit)
    if set(labels.values()) != set(populations) or mismatched:
        raise RuntimeError(
            "could not recover unit ids from the GerryChain graph "
            f"(first mismatches: {sorted(mismatched)[:5]}); refusing to emit "
            "plans whose units may be silently permuted"
        )
    return labels


# --------------------------------------------------------------------------
# many chains
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainTrace:
    """What one seed produced, including how it died."""

    seed: int
    steps_requested: int
    steps_completed: int
    seconds: float
    failure: str | None
    plans: tuple[Plan, ...]
    cut_edges: tuple[int, ...]
    population_spread: tuple[int, ...]

    @property
    def completed(self) -> bool:
        return self.failure is None and self.steps_completed == self.steps_requested


@dataclass(frozen=True)
class EnsembleResult:
    """An ensemble, with the shape of its own failures attached.

    ``plans`` holds every plan that was actually produced, including those from
    chains that later died. Discarding a dead chain's first 137 states would
    throw away 137 legitimate draws; keeping them means ``plans`` is not a set of
    equal-length chains, which is why ``traces`` exists and why the convergence
    helpers take chains rather than the pooled list.

    **Which sample each number describes.** Three different subsets live in here
    and docs/ARCHITECTURE.md section 7 makes the difference material -- surviving
    seeds are not a random subset of attempted seeds -- so no number should have
    to be guessed at:

    * ``n_requested``, ``chain_failures`` and ``failure_rate`` are over every
      seed *attempted*. That is the point of them.
    * ``n_completed`` is every draw *produced*, partial traces included, and
      ``distinct_plans`` counts relabelling-equivalence classes among exactly
      those draws. The two are reported adjacently in bench-results.json
      (ARCHITECTURE section 5) and are the same sample.
    * :meth:`cut_edges_chains`, :meth:`population_spread_chains` and
      :meth:`population_spread_summary` default to the *completed* chains, since
      a diagnostic over chains needs a rectangle and a ragged partial trace is
      not one. They all take ``only_completed`` and the summary reports which it
      used, so a reader never has to infer it.
    """

    k: int
    epsilon: float
    steps: int
    seeds: tuple[int, ...]
    plans: tuple[Plan, ...]
    n_requested: int
    n_completed: int
    chain_failures: int
    failure_rate: float
    distinct_plans: int
    traces: tuple[ChainTrace, ...]
    seconds: float

    @property
    def completed_traces(self) -> tuple[ChainTrace, ...]:
        return tuple(trace for trace in self.traces if trace.completed)

    def cut_edges_chains(self, only_completed: bool = True) -> list[list[int]]:
        """Per-chain cut-edge traces, for the convergence diagnostics."""
        source = self.completed_traces if only_completed else self.traces
        return [list(trace.cut_edges) for trace in source]

    def population_spread_chains(self, only_completed: bool = True) -> list[list[int]]:
        source = self.completed_traces if only_completed else self.traces
        return [list(trace.population_spread) for trace in source]

    def population_spread_summary(self, only_completed: bool = True) -> dict:
        """min / median / max population spread, over a named subset of draws.

        The default is the *completed* chains, matching
        :meth:`cut_edges_chains` and :meth:`population_spread_chains`, so that
        every number that lands in the ``ensemble`` object of bench-results.json
        describes the same sample. It previously summarised all traces while the
        diagnostics used only the completed ones, which put two numbers
        describing two different samples side by side with nothing saying so.

        Which subset it is cannot be left implicit either: docs/ARCHITECTURE.md
        section 7 records that surviving seeds are not a random subset of
        attempted seeds, so "completed chains only" is a biased view and
        "everything drawn" is a ragged one. The choice is therefore reported in
        the result, in ``sample``, alongside the draw and chain counts it covers.
        The three-number core is the shape ARCHITECTURE section 5 shows; the
        provenance keys are the section 7 requirement that the subset be
        explicit.

        Args:
            only_completed: restrict to chains that ran to ``steps`` without
                dying. Pass False for every draw produced, including the partial
                traces of chains that later failed.
        """
        source = self.completed_traces if only_completed else self.traces
        values = [spread for trace in source for spread in trace.population_spread]
        label = "completed_chains" if only_completed else "all_draws"
        summary: dict = {
            "sample": label,
            "n_chains": len(source),
            "n_draws": len(values),
        }
        if not values:
            summary.update(
                {"min": float("nan"), "median": float("nan"), "max": float("nan")}
            )
            return summary
        summary.update(
            {
                "min": float(min(values)),
                "median": float(median(values)),
                "max": float(max(values)),
            }
        )
        return summary


def run_chains(
    adjacency: Mapping[str, Sequence[str]],
    populations: Mapping[str, int],
    k: int,
    epsilon: float,
    steps: int,
    seeds: Iterable[int],
    node_repeats: int = 0,
) -> EnsembleResult:
    """Run one chain per seed, tolerating and counting per-chain failure.

    Nothing is retried and nothing aborts the run. A seed that dies contributes
    its partial trace, a ``failure`` string, and one to ``chain_failures``.
    """
    seeds = tuple(seeds)
    if not seeds:
        raise ValueError("no seeds given")
    check_inputs(adjacency, populations, k, epsilon, steps)

    traces: list[ChainTrace] = []
    started = time.perf_counter()

    for seed in seeds:
        plans: list[Plan] = []
        failure: str | None = None
        chain_started = time.perf_counter()
        try:
            for plan in sample(
                adjacency, populations, k, epsilon, steps, seed, node_repeats
            ):
                plans.append(plan)
        except Exception as exc:  # a dead chain is an observation, not a crash
            failure = f"{type(exc).__name__}: {exc}"[:500]
        # Derived quantities are computed outside the try on purpose. They are
        # pure functions of a plan that has already been produced, and the only
        # way they can raise is a violated plan invariant (a district of 1..k
        # with no units) -- which is a bug in this module, not an unlucky seed.
        # Computing them inside the try would file that bug as a chain failure
        # and inflate the failure rate ARCHITECTURE section 7 requires be real.
        cuts = [cut_edges(plan, adjacency) for plan in plans]
        spreads = [population_spread(plan, populations, k) for plan in plans]
        traces.append(
            ChainTrace(
                seed=seed,
                steps_requested=steps,
                steps_completed=len(plans),
                seconds=time.perf_counter() - chain_started,
                failure=failure,
                plans=tuple(plans),
                cut_edges=tuple(cuts),
                population_spread=tuple(spreads),
            )
        )

    every_plan = tuple(plan for trace in traces for plan in trace.plans)
    failures = sum(1 for trace in traces if not trace.completed)
    return EnsembleResult(
        k=k,
        epsilon=epsilon,
        steps=steps,
        seeds=seeds,
        plans=every_plan,
        n_requested=len(seeds) * steps,
        n_completed=len(every_plan),
        chain_failures=failures,
        failure_rate=failures / len(seeds),
        distinct_plans=len({canonical(plan, k) for plan in every_plan}),
        traces=tuple(traces),
        seconds=time.perf_counter() - started,
    )
