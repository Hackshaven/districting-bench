"""Tests for src/generate: seed derivation, the ReCom sampler, convergence.

Every diagnostic here is checked against a case whose answer is known
analytically or by hand, not against a second run of the same code:

* split R-hat against an arithmetic computation written out in the test;
* ESS against ``n*m`` for i.i.d. draws and against ``n*m(1-phi)/(1+phi)`` for an
  AR(1) process, whose integrated autocorrelation time is known in closed form;
* cut edges and population spread against graphs small enough to count by hand;
* the rank-normalized statistic against its defining invariance property (any
  strictly increasing transform must leave it unchanged);
* failure accounting against a stand-in sampler whose failures are scripted, and
  then once more against real GerryChain at the epsilon the bench is configured
  with (docs/ARCHITECTURE.md section 5), where failures are not scripted.

An assertion that restates the code it is testing is not a test: it passes for a
wrong implementation as readily as a right one. Where the natural expected value
is "what the function returns", the expected value is derived some other way
here -- by hand, from a golden run, or from a second implementation written in
different terms.

Run: PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
"""

from __future__ import annotations

import ast
import inspect
import math
import os
import subprocess
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

from generate import convergence as cv
from generate import ensemble as ens
from generate import seeds as sd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"


# ==========================================================================
# seeds
# ==========================================================================


def test_derive_is_deterministic_and_stable():
    """Golden values. If these change, every earlier run is unreproducible."""
    assert sd.derive(20260818, "chain", 0) == 5226943157832607398
    assert sd.derive(20260818, "chain", 1) == 3305020079993976457
    assert sd.derive(0, "", 0) == 6564682913144652364
    assert sd.derive(-5, "scenario", 7) == 4405358474510424484


def test_derive_is_in_range():
    for index in range(200):
        value = sd.derive(1, "chain", index)
        assert 0 <= value < 2**63


def test_derive_does_not_use_the_salted_builtin_hash():
    """Reproducibility must survive a new process with a different hash salt."""
    program = (
        "from generate.seeds import derive; print(derive(20260818, 'chain', 0))"
    )
    outputs = set()
    for salt in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=salt, PYTHONPATH=str(ROOT / "src"))
        result = subprocess.run(
            [sys.executable, "-c", program],
            check=True,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
        )
        outputs.add(result.stdout.strip())
    assert outputs == {"5226943157832607398"}


def test_derive_separates_purposes_and_indices():
    assert sd.derive(1, "chain", 0) != sd.derive(1, "scenario", 0)
    assert sd.derive(1, "chain", 0) != sd.derive(1, "chain", 1)
    assert sd.derive(1, "chain", 0) != sd.derive(2, "chain", 0)


def test_derive_field_framing_is_injective():
    """A purpose containing the field separator must not impersonate another key.

    With a naive delimiter join these pairs are the same byte string.
    """
    assert sd.derive(1, "a", 11) != sd.derive(1, "a1", 1)
    assert sd.derive(1, "chain0", 1) != sd.derive(1, "chain", 1)
    assert sd.derive(11, "a", 1) != sd.derive(1, "1a", 1)


def test_derive_values_are_distinct_and_well_dispersed():
    values = [sd.derive(20260818, "chain", i) for i in range(20000)]
    assert len(set(values)) == len(values)

    # Uniformity of the top 4 bits: 16 buckets, 20000 draws, expected 1250 each.
    # chi-square with 15 df exceeds 37.7 with probability 0.001.
    buckets = np.bincount([v >> 59 for v in values], minlength=16)
    expected = len(values) / 16
    chi_square = float(((buckets - expected) ** 2 / expected).sum())
    assert chi_square < 37.7, f"top-bit buckets look non-uniform: {buckets}"

    # Mean of the normalized values should sit near 0.5; the standard error at
    # n=20000 for a uniform is 1/sqrt(12n) = 0.002, so 6 s.e. is 0.012.
    mean = float(np.mean([v / 2**63 for v in values]))
    assert abs(mean - 0.5) < 0.012


def test_derive_avalanches_on_a_one_bit_change():
    """Neighbouring master seeds must give unrelated streams, not neighbours."""
    distances = []
    for master in range(500):
        a = sd.derive(master, "chain", 0)
        b = sd.derive(master ^ 1, "chain", 0)
        distances.append(bin(a ^ b).count("1"))
    mean = sum(distances) / len(distances)
    # 63 bits flipping independently: expected 31.5, s.d. ~3.97, s.e. ~0.18.
    assert 30.5 < mean < 32.5, f"mean hamming distance {mean}"
    assert min(distances) > 8


def test_derive_rejects_wrong_types():
    with pytest.raises(TypeError):
        sd.derive("20260818", "chain", 0)
    with pytest.raises(TypeError):
        sd.derive(1, 5, 0)
    with pytest.raises(TypeError):
        sd.derive(1, "chain", "0")


def test_stream_is_the_first_n_seeds_of_a_purpose():
    """Golden values, not a restatement of stream()'s body.

    ``stream(...) == [derive(...) for i in range(n)]`` cannot fail for any
    implementation that loops over derive, including one that starts at index 1
    or reverses the order. These are the numbers on disk, plus the two structural
    properties a caller depends on.
    """
    assert sd.stream(7, "chain", 4) == [
        3566427239939341142,
        6510946294532200226,
        4868045547405297778,
        3628114716198446039,
    ]
    assert sd.stream(7, "chain", 0) == []

    # Prefix property: asking for more chains extends the list, it does not
    # redraw it, so adding a chain to a run leaves the earlier chains alone.
    assert sd.stream(7, "chain", 2) == sd.stream(7, "chain", 4)[:2]
    # Purposes are separate streams at the same index.
    assert sd.stream(7, "scenario", 4)[0] != sd.stream(7, "chain", 4)[0]

    with pytest.raises(ValueError):
        sd.stream(7, "chain", -1)


# ==========================================================================
# convergence: split R-hat
# ==========================================================================


def test_split_rhat_matches_a_hand_computation():
    """Two chains of four draws, split into four half-chains of two.

        halves      [1,2] [3,4] [5,6] [7,8]
        means        1.5   3.5   5.5   7.5
        W = mean of within variances (ddof=1) = 0.5
        B = n * var(means, ddof=1) = 2 * (20/3) = 40/3
        var_hat = (n-1)/n * W + B/n = 0.25 + 20/3 = 83/12
        R-hat = sqrt(var_hat / W) = sqrt(83/6)
    """
    value = cv.split_rhat([[1, 2, 3, 4], [5, 6, 7, 8]], rank_normalize=False, folded=False)
    assert value == pytest.approx(math.sqrt(83 / 6), rel=1e-12)


def test_split_rhat_uses_the_split_and_would_miss_the_drift_without_it():
    """The reason for the split, stated as a test.

    Four chains that each drift identically from -1 to +1 agree with each other
    perfectly, so the unsplit statistic sees nothing. Each chain disagrees with
    itself, which is exactly what splitting exposes.
    """
    rng = np.random.default_rng(4)
    drift = np.linspace(-1.0, 1.0, 1000)
    chains = [(drift + rng.normal(0, 0.01, 1000)).tolist() for _ in range(4)]

    # Unsplit Gelman-Rubin, written out here so the comparison is independent.
    matrix = np.asarray(chains)
    m, n = matrix.shape
    within = matrix.var(axis=1, ddof=1).mean()
    between = n * matrix.mean(axis=1).var(ddof=1)
    unsplit = math.sqrt(((n - 1) / n * within + between / n) / within)

    assert unsplit < 1.001, f"unsplit R-hat saw the drift: {unsplit}"
    assert cv.split_rhat(chains) > 1.5


def test_split_rhat_is_near_one_on_iid_chains():
    rng = np.random.default_rng(0)
    chains = rng.normal(size=(4, 1000)).tolist()
    value = cv.split_rhat(chains)
    assert 0.99 < value < 1.01, value


def test_split_rhat_flags_an_autocorrelated_chain_that_has_not_mixed():
    """AR(1) surrogate, strong autocorrelation, chains started far apart.

    This is the regime docs/FEASIBILITY.md section 5.4 says the unsplit
    statistic passes about half the time.
    """
    chains = [_ar1(1000, 0.99, start=start, seed=10 + i) for i, start in enumerate((-20, -7, 7, 20))]
    assert cv.split_rhat(chains) > 1.05


def test_split_rhat_is_invariant_to_monotone_transforms():
    """The defining property of the rank-normalized statistic."""
    rng = np.random.default_rng(3)
    chains = rng.normal(size=(4, 200)).tolist()
    stretched = [[math.exp(3 * x) for x in chain] for chain in chains]
    assert cv.split_rhat(chains, folded=False) == pytest.approx(
        cv.split_rhat(stretched, folded=False), rel=1e-12
    )


def test_split_rhat_survives_an_infinite_variance_quantity():
    """Cauchy draws have no variance for the raw statistic to compare."""
    rng = np.random.default_rng(11)
    chains = (rng.standard_cauchy(size=(4, 2000))).tolist()
    assert cv.split_rhat(chains) < 1.02


def test_folding_catches_chains_that_agree_on_location_but_not_scale():
    rng = np.random.default_rng(5)
    chains = [
        rng.normal(0, 1, 1000).tolist(),
        rng.normal(0, 1, 1000).tolist(),
        rng.normal(0, 8, 1000).tolist(),
        rng.normal(0, 8, 1000).tolist(),
    ]
    assert cv.split_rhat(chains, folded=False) < 1.02
    assert cv.split_rhat(chains, folded=True) > 1.1


def test_degenerate_regimes_are_explicit():
    constant = [[3.0] * 100, [3.0] * 100]
    assert math.isnan(cv.split_rhat(constant))
    assert math.isnan(cv.ess(constant))

    stuck = [[1.0] * 100, [2.0] * 100]
    assert cv.split_rhat(stuck) == float("inf")

    with pytest.raises(ValueError, match="at least 2 chains"):
        cv.split_rhat([[1.0, 2.0, 3.0, 4.0]])
    with pytest.raises(ValueError, match="unequal lengths"):
        cv.split_rhat([[1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0]])
    with pytest.raises(ValueError, match="at least 4 draws"):
        cv.split_rhat([[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]])
    with pytest.raises(ValueError, match="non-finite"):
        cv.split_rhat([[1.0, 2.0, 3.0, float("nan")], [1.0, 2.0, 3.0, 4.0]])


def test_truncate_is_explicit_rather_than_silent():
    ragged = [[1, 2, 3, 4, 5], [1, 2, 3, 4], [1, 2, 3, 4, 5, 6]]
    with pytest.raises(ValueError, match="unequal lengths"):
        cv.split_rhat(ragged)

    trimmed = cv.truncate(ragged)
    assert trimmed == [[1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4]]
    assert ragged == [[1, 2, 3, 4, 5], [1, 2, 3, 4], [1, 2, 3, 4, 5, 6]]  # not mutated

    # And the trimmed input has an answer of its own, computed here rather than
    # by calling split_rhat a second time. Three identical chains [1,2,3,4] split
    # into six half-chains, [1,2] three times and [3,4] three times:
    #     W       = mean within-half variance (ddof=1)        = 0.5
    #     means   = [1.5]*3 + [3.5]*3, var(ddof=1)            = 1.2
    #     B       = n * 1.2 = 2 * 1.2                         = 2.4
    #     var_hat = (n-1)/n * W + B/n = 0.25 + 1.2            = 1.45
    #     R-hat   = sqrt(1.45 / 0.5)                          = sqrt(2.9)
    assert cv.split_rhat(trimmed, rank_normalize=False, folded=False) == pytest.approx(
        math.sqrt(2.9), rel=1e-12
    )


# ==========================================================================
# convergence: ESS
# ==========================================================================


def _ar1(n: int, phi: float, start: float = 0.0, seed: int = 0) -> list[float]:
    """AR(1) with unit stationary variance: x_t = phi x_{t-1} + sqrt(1-phi^2) e_t."""
    rng = np.random.default_rng(seed)
    scale = math.sqrt(1.0 - phi**2)
    value = start
    out = []
    for _ in range(n):
        value = phi * value + scale * rng.normal()
        out.append(value)
    return out


def test_ess_of_iid_chains_is_near_the_number_of_draws():
    rng = np.random.default_rng(1)
    chains = rng.normal(size=(4, 1000)).tolist()
    draws = 4 * 1000
    value = cv.ess(chains)
    assert 0.7 * draws < value < 1.3 * draws, value


def test_ess_of_an_ar1_chain_matches_its_known_autocorrelation_time():
    """For AR(1), tau = (1+phi)/(1-phi), so ESS = N (1-phi)/(1+phi) exactly.

    A sign error or a wrong denominator in the Geyer sum shows up here as a
    factor, not as noise.
    """
    for phi in (0.8, 0.9):
        chains = [_ar1(2000, phi, seed=100 + i) for i in range(4)]
        draws = 4 * 2000
        expected = draws * (1 - phi) / (1 + phi)
        value = cv.ess(chains)
        assert value < 0.2 * draws, (phi, value)
        assert 0.5 * expected < value < 2.0 * expected, (phi, value, expected)


def test_ess_collapses_when_the_chain_barely_moves():
    chains = [_ar1(1000, 0.99, start=start, seed=200 + i) for i, start in enumerate((-20, -7, 7, 20))]
    draws = 4 * 1000
    assert cv.ess(chains) < 0.02 * draws


def test_ess_separates_nothing_varied_from_never_moved():
    """The two degenerate regimes are opposite findings and must read that way.

    A chain stuck at a constant is live here, not hypothetical:
    docs/FEASIBILITY.md section 5.1 records 7 distinct plans per 300 steps at
    epsilon=1e-4, so a short chain at the operating point can genuinely never
    move. R-hat already separated the two; ESS returned nan for both, so a bench
    reading nan as "degenerate, nothing varied" would have reported the opposite
    of the truth for the most badly unmixed sample there is.
    """
    nothing_varies = [[3.0] * 100, [3.0] * 100, [3.0] * 100]
    never_moved = [[1.0] * 100, [2.0] * 100, [3.0] * 100]

    assert math.isnan(cv.split_rhat(nothing_varies))
    assert math.isnan(cv.ess(nothing_varies))

    assert cv.split_rhat(never_moved) == float("inf")
    assert cv.ess(never_moved) == 0.0
    assert not math.isnan(cv.ess(never_moved))

    # The point of the distinction: a gate reads R-hat from above and ESS from
    # below, and on this sample both must fail rather than one of them being
    # unreadable.
    assert not cv.split_rhat(never_moved) <= 1.01
    assert not cv.ess(never_moved) >= 1.0

    # A chain that moves at all, however little, is not in either regime.
    barely = [[1.0] * 99 + [1.5], [2.0] * 99 + [2.5], [3.0] * 99 + [3.5]]
    value = cv.ess(barely)
    assert 0.0 < value < 0.05 * 300, value


def test_ess_and_rhat_disagree_by_design():
    """A well-mixed-looking R-hat with a small ESS is possible and must be visible.

    docs/FEASIBILITY.md section 5.4 found exactly this on the Iowa ensembles, and
    it is why both are reported rather than one.
    """
    chains = [_ar1(4000, 0.98, seed=300 + i) for i in range(4)]
    assert cv.split_rhat(chains) < 1.05
    assert cv.ess(chains) < 0.05 * 4 * 4000


# ==========================================================================
# ensemble: plan-level quantities on hand-countable graphs
# ==========================================================================


def _path_graph(n: int, population: int = 10, uneven: bool = False):
    """1 - 2 - ... - n. ``uneven`` makes every unit a different size, so no
    exactly equal split exists."""
    adjacency = {}
    for i in range(n):
        neighbours = []
        if i > 0:
            neighbours.append(f"u{i - 1:02d}")
        if i < n - 1:
            neighbours.append(f"u{i + 1:02d}")
        adjacency[f"u{i:02d}"] = neighbours
    populations = {f"u{i:02d}": population + (i if uneven else 0) for i in range(n)}
    return adjacency, populations


def _grid(side: int, uneven: bool = False):
    """A rook grid. ``uneven`` gives every unit a distinct size, so that no
    exactly balanced partition exists and a tight epsilon is genuinely
    infeasible."""
    adjacency, populations = {}, {}
    for row in range(side):
        for col in range(side):
            unit = f"r{row}c{col}"
            populations[unit] = 100 + (row * side + col if uneven else 0)
            neighbours = []
            for drow, dcol in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nrow, ncol = row + drow, col + dcol
                if 0 <= nrow < side and 0 <= ncol < side:
                    neighbours.append(f"r{nrow}c{ncol}")
            adjacency[unit] = neighbours
    return adjacency, populations


def test_cut_edges_counted_by_hand():
    adjacency, _ = _path_graph(4)
    units = sorted(adjacency)
    # One cut in the middle of a path: exactly one adjacent pair is split.
    assert ens.cut_edges(dict(zip(units, [1, 1, 2, 2])), adjacency) == 1
    # Alternating labels split all three edges.
    assert ens.cut_edges(dict(zip(units, [1, 2, 1, 2])), adjacency) == 3
    # Everything in one district cuts nothing.
    assert ens.cut_edges(dict(zip(units, [1, 1, 1, 1])), adjacency) == 0

    # 4x4 rook grid, 24 edges. A clean vertical cut down the middle severs the
    # 4 horizontal edges that cross it.
    grid_adjacency, _ = _grid(4)
    assert sum(len(v) for v in grid_adjacency.values()) // 2 == 24
    halves = {unit: (1 if unit[3] in "01" else 2) for unit in grid_adjacency}
    assert ens.cut_edges(halves, grid_adjacency) == 4


def test_population_spread_and_totals_by_hand():
    populations = {"a": 10, "b": 20, "c": 30, "d": 5}
    plan = {"a": 1, "b": 1, "c": 2, "d": 2}
    assert ens.district_totals(plan, populations, 2) == {1: 30, 2: 35}
    assert ens.population_spread(plan, populations, 2) == 5


def test_an_empty_district_is_reported_and_never_folded_away():
    """The k=4 plan whose fourth district holds nobody.

    Read off its own values it is a 3-district plan, and inferring the district
    set from ``plan.values()`` answers as though it were: totals {1: 30, 2: 30,
    3: 40}, a max-min of 10 against the true 40 over 1..4 -- understating by a
    factor of four -- and a canonical key of three blocks that compares equal to
    a genuine 3-district plan, which would make distinct_plans conflate the two.
    docs/ARCHITECTURE.md section 3 makes "district ids exactly 1..K, none empty"
    an invariant; evaluate.plan.validate is across the firewall and unreachable
    from here, so these functions enforce the part of it they depend on.
    """
    populations = {"a": 10, "b": 20, "c": 30, "d": 40}
    plan = {"a": 1, "b": 1, "c": 2, "d": 3}

    for call in (
        lambda: ens.district_totals(plan, populations, 4),
        lambda: ens.population_spread(plan, populations, 4),
        lambda: ens.canonical(plan, 4),
        lambda: ens.districts_of(plan, 4),
    ):
        with pytest.raises(ValueError, match=r"no units in district\(s\) \[4\]"):
            call()

    # The same plan read as what it is: three districts, hand-countable.
    assert ens.district_totals(plan, populations, 3) == {1: 30, 2: 30, 3: 40}
    assert ens.population_spread(plan, populations, 3) == 10

    # A genuine 4-district plan over the same units answers normally, and the
    # empty district it would have had is worth 40 persons of spread.
    whole = {"a": 1, "b": 2, "c": 3, "d": 4}
    assert ens.district_totals(whole, populations, 4) == {1: 10, 2: 20, 3: 30, 4: 40}
    assert ens.population_spread(whole, populations, 4) == 30


def test_k_is_required_and_none_is_an_explicit_opt_out():
    """Omitting k is a TypeError; asking about the observed districts is typed.

    k=None still refuses a gap or a non-1-based label, but it cannot see a
    trailing empty district -- nothing can, from the plan alone -- so it is
    reached deliberately rather than by leaving an argument off.
    """
    populations = {"a": 10, "b": 20, "c": 30, "d": 40}
    plan = {"a": 1, "b": 1, "c": 2, "d": 3}

    with pytest.raises(TypeError):
        ens.population_spread(plan, populations)
    with pytest.raises(TypeError):
        ens.district_totals(plan, populations)
    with pytest.raises(TypeError):
        ens.canonical(plan)

    assert ens.population_spread(plan, populations, None) == 10
    assert ens.districts_of(plan, None) == [1, 2, 3]

    with pytest.raises(ValueError, match="outside 1..3"):
        ens.districts_of({"a": 1, "b": 2, "c": 3, "d": 7}, 3)
    with pytest.raises(ValueError, match="1..K with no gaps"):
        ens.districts_of({"a": 1, "b": 2, "c": 4, "d": 4}, None)
    with pytest.raises(ValueError, match="1..K with no gaps"):
        ens.districts_of({"a": 0, "b": 0, "c": 1, "d": 1}, None)
    with pytest.raises(ValueError, match="assigns no units"):
        ens.districts_of({}, 4)


def test_canonical_ignores_district_labels_only():
    plan = {"a": 1, "b": 1, "c": 2}
    relabelled = {"a": 2, "b": 2, "c": 1}
    different = {"a": 1, "b": 2, "c": 2}
    assert ens.canonical(plan, 2) == ens.canonical(relabelled, 2)
    assert ens.canonical(plan, 2) != ens.canonical(different, 2)
    # Every district of 1..k is a block, so a k-district key can never equal a
    # key with a different number of districts.
    assert len(ens.canonical(plan, 2)) == 2
    assert len(ens.canonical({"a": 1, "b": 2, "c": 3}, 3)) == 3


def test_distinct_plans_counts_relabellings_once(monkeypatch):
    """Against a hand-counted answer rather than against canonical() itself.

    Five draws over the 4-unit path, k=2. Draw 2 relabels draw 0 and draw 3
    relabels draw 1, so the partitions are {ab|cd}, {a|bcd}, {ab|cd}, {a|bcd},
    {abc|d}: three distinct plans, counted by eye. Comparing distinct_plans to
    ``len({canonical(p) for p in plans})`` instead would restate run_chains'
    implementation and pass for any definition of canonical, right or wrong.
    """
    adjacency, populations = _path_graph(4)
    units = sorted(populations)
    labellings = [
        [1, 1, 2, 2],
        [1, 2, 2, 2],
        [2, 2, 1, 1],
        [2, 1, 1, 1],
        [1, 1, 1, 2],
    ]

    def fixed(_adjacency, _populations, _k, _epsilon, _steps, seed, node_repeats=0):
        return iter([dict(zip(units, labels)) for labels in labellings])

    monkeypatch.setattr(ens, "sample", fixed)
    result = ens.run_chains(adjacency, populations, 2, 0.5, len(labellings), [1])
    assert result.n_completed == 5
    assert result.distinct_plans == 3


def test_distinct_plans_on_a_real_run_matches_an_independent_key():
    """Cross-check on ReCom output, with the equivalence written out here.

    The key below is built from sorted tuples rather than frozensets and walks
    1..k explicitly, so it agrees with canonical() only if canonical() means what
    it says.
    """
    adjacency, populations = _grid(4)
    result = ens.run_chains(adjacency, populations, 4, 0.05, 12, [11, 12])

    def relabelling_free_key(plan):
        blocks = []
        for district in range(1, 5):
            members = tuple(sorted(u for u, d in plan.items() if d == district))
            assert members, f"district {district} is empty"
            blocks.append(members)
        return tuple(sorted(blocks))

    assert result.n_completed == 24
    assert result.distinct_plans == len({relabelling_free_key(p) for p in result.plans})
    assert result.distinct_plans == 10  # golden: 24 draws, 10 partitions


# ==========================================================================
# ensemble: input validation
# ==========================================================================


def test_duplicate_neighbours_are_refused_and_never_double_count_an_edge():
    """cut_edges counts each unordered pair once, and now check_inputs says so.

    The docstring used to claim check_inputs established "symmetric adjacency
    without duplicates"; it checked symmetry only, so a repeated neighbour
    contributed the same edge twice.
    """
    adjacency, populations = _path_graph(4)
    plan = {"u00": 1, "u01": 1, "u02": 2, "u03": 2}
    assert ens.cut_edges(plan, adjacency) == 1

    adjacency["u01"].append("u02")
    adjacency["u02"].append("u01")
    with pytest.raises(ValueError, match="duplicate neighbour"):
        ens.check_inputs(adjacency, populations, 2, 0.05, 10)
    # Still one edge, not two, on the graph check_inputs rejects.
    assert ens.cut_edges(plan, adjacency) == 1


def test_asymmetric_adjacency_is_refused():
    adjacency, populations = _path_graph(4)
    adjacency["u01"] = [u for u in adjacency["u01"] if u != "u00"]
    with pytest.raises(ValueError, match="not symmetric"):
        ens.check_inputs(adjacency, populations, 2, 0.05, 10)


def test_disconnected_graph_is_refused():
    adjacency, populations = _path_graph(4)
    adjacency["u01"].remove("u02")
    adjacency["u02"].remove("u01")
    with pytest.raises(ValueError, match="not connected"):
        ens.check_inputs(adjacency, populations, 2, 0.05, 10)


def test_mismatched_unit_sets_are_refused():
    adjacency, populations = _path_graph(4)
    populations["extra"] = 1
    with pytest.raises(ValueError, match="different unit sets"):
        ens.check_inputs(adjacency, populations, 2, 0.05, 10)


def test_bad_parameters_are_refused():
    adjacency, populations = _path_graph(4)
    with pytest.raises(ValueError, match="k must be"):
        ens.check_inputs(adjacency, populations, 1, 0.05, 10)
    with pytest.raises(ValueError, match="exceeds"):
        ens.check_inputs(adjacency, populations, 5, 0.05, 10)
    with pytest.raises(ValueError, match="epsilon"):
        ens.check_inputs(adjacency, populations, 2, 0.0, 10)
    with pytest.raises(ValueError, match="steps"):
        ens.check_inputs(adjacency, populations, 2, 0.05, 0)


def test_caller_errors_are_not_counted_as_chain_failures():
    """A malformed graph must raise, not show up as an unlucky run of seeds."""
    adjacency, populations = _path_graph(4)
    adjacency["u01"].remove("u02")
    adjacency["u02"].remove("u01")
    with pytest.raises(ValueError):
        ens.run_chains(adjacency, populations, 2, 0.05, 10, [1, 2])


# ==========================================================================
# ensemble: sampling
# ==========================================================================


def test_sampled_plans_satisfy_the_ordered_ch42_criteria():
    """Population equality, contiguity and whole units, checked per plan."""
    adjacency, populations = _grid(4)
    k, epsilon = 4, 0.05
    ideal = sum(populations.values()) / k
    graph = nx.Graph()
    graph.add_nodes_from(adjacency)
    for unit, neighbours in adjacency.items():
        for other in neighbours:
            graph.add_edge(unit, other)

    plans = list(ens.sample(adjacency, populations, k, epsilon, 25, seed=99))
    assert len(plans) == 25
    for plan in plans:
        assert set(plan) == set(populations)                    # every unit once
        assert sorted(set(plan.values())) == [1, 2, 3, 4]       # labels are 1..k
        totals = ens.district_totals(plan, populations, k)
        for total in totals.values():
            assert abs(total - ideal) <= epsilon * ideal + 1e-9  # equality
        for district in totals:
            members = [u for u, d in plan.items() if d == district]
            assert nx.is_connected(graph.subgraph(members))      # contiguity


def test_sampling_is_reproducible_from_the_seed():
    adjacency, populations = _grid(4)
    first = list(ens.sample(adjacency, populations, 4, 0.05, 15, seed=1234))
    again = list(ens.sample(adjacency, populations, 4, 0.05, 15, seed=1234))
    other = list(ens.sample(adjacency, populations, 4, 0.05, 15, seed=1235))
    assert first == again
    assert first != other


def test_run_chains_is_reproducible_from_a_master_seed():
    adjacency, populations = _grid(4)
    chain_seeds = sd.stream(20260818, "chain", 3)
    first = ens.run_chains(adjacency, populations, 4, 0.05, 10, chain_seeds)
    again = ens.run_chains(adjacency, populations, 4, 0.05, 10, chain_seeds)
    assert first.plans == again.plans
    assert first.distinct_plans == again.distinct_plans


# ==========================================================================
# ensemble: failure accounting
# ==========================================================================


def test_failure_accounting_keeps_partial_chains_and_counts_by_chain(monkeypatch):
    """The accounting itself, with the sampler's failures made deterministic.

    A real infeasible epsilon costs GerryChain 100,000 attempts per chain, so the
    bookkeeping is tested against a stand-in that fails on demand and the real
    failure path is exercised once, slowly, in the test below.
    """
    adjacency, populations = _path_graph(6)
    steps = 10

    def flaky(_adjacency, _populations, _k, _epsilon, _steps, seed, node_repeats=0):
        def run():
            for step in range(_steps):
                if seed == 2 and step == 4:
                    raise RuntimeError("Could not find a possible cut")
                if seed == 3 and step == 0:
                    raise RuntimeError("seeding failed before any state")
                yield {unit: 1 + (index % 2) for index, unit in enumerate(sorted(_populations))}
        return run()

    monkeypatch.setattr(ens, "sample", flaky)
    result = ens.run_chains(adjacency, populations, 2, 0.05, steps, [1, 2, 3, 4])

    assert result.n_requested == 40                 # 4 seeds x 10 steps
    assert result.n_completed == 10 + 4 + 0 + 10    # partial chains keep their draws
    assert result.chain_failures == 2
    assert result.failure_rate == 0.5               # a chain count, never a plan count
    assert [t.steps_completed for t in result.traces] == [10, 4, 0, 10]
    assert [t.completed for t in result.traces] == [True, False, False, True]
    assert "Could not find a possible cut" in result.traces[1].failure
    assert result.traces[2].plans == ()
    assert len(result.completed_traces) == 2

    for trace in result.traces:
        assert trace.steps_completed == len(trace.plans)
        assert len(trace.cut_edges) == trace.steps_completed
        assert len(trace.population_spread) == trace.steps_completed

    # Only the chains that finished make a rectangular block for the diagnostics.
    assert {len(chain) for chain in result.cut_edges_chains()} == {10}
    assert [len(chain) for chain in result.cut_edges_chains(only_completed=False)] == [10, 4, 0, 10]


def test_an_invariant_violating_plan_raises_instead_of_counting_as_a_failure(
    monkeypatch,
):
    """A sampler bug must not be filed as an unlucky seed.

    failure_rate is a reported sampling-bias quantity (docs/ARCHITECTURE.md
    section 7), so anything that is not a dead chain has to stay out of it. The
    plan-level quantities are therefore computed outside run_chains' except
    block: they are pure functions of a plan already produced, and the only way
    they raise is a violated 1..k invariant.
    """
    adjacency, populations = _path_graph(4)
    units = sorted(populations)

    def three_of_four(_adjacency, _populations, _k, _epsilon, _steps, seed, node_repeats=0):
        return iter([dict(zip(units, [1, 2, 3, 3]))] * 3)  # district 4 empty

    monkeypatch.setattr(ens, "sample", three_of_four)
    with pytest.raises(ValueError, match=r"no units in district\(s\) \[4\]"):
        ens.run_chains(adjacency, populations, 4, 0.5, 3, [1])


def test_the_spread_summary_covers_the_same_sample_as_the_diagnostics(monkeypatch):
    """One 'ensemble' object, one sample, and the sample named in the result.

    population_spread_summary used to pool every trace while cut_edges_chains
    defaulted to completed chains only, so two numbers describing two different
    subsets landed side by side in bench-results.json with nothing recording
    which was which. Both now default to the completed chains, and the summary
    reports the subset it covers.

    Six units of 10..15 persons, k=2: assigning the first j units to district 1
    gives spreads of 55, 33, 9 and 17 for j = 1, 2, 3, 4. The surviving chain
    cycles j = 2, 3, 4 for ten draws; the chain that dies sits at j = 1 for
    three draws and then fails, so the 55s exist only in the partial trace.
    """
    adjacency, populations = _path_graph(6, uneven=True)
    units = sorted(populations)

    def by_seed(_adjacency, _populations, _k, _epsilon, _steps, seed, node_repeats=0):
        def run():
            for step in range(_steps):
                if seed == 2:
                    if step == 3:
                        raise RuntimeError("Could not find a possible cut")
                    first = 1
                else:
                    first = 2 + step % 3
                yield {u: (1 if i < first else 2) for i, u in enumerate(units)}
        return run()

    monkeypatch.setattr(ens, "sample", by_seed)
    result = ens.run_chains(adjacency, populations, 2, 0.5, 10, [1, 2])

    assert [t.steps_completed for t in result.traces] == [10, 3]
    assert result.traces[1].population_spread == (55, 55, 55)

    default = result.population_spread_summary()
    assert default["sample"] == "completed_chains"
    assert (default["n_chains"], default["n_draws"]) == (1, 10)
    # ten draws: 9, 9, 9, 17, 17, 17, 33, 33, 33, 33 -- median (17+17)/2.
    assert (default["min"], default["median"], default["max"]) == (9.0, 17.0, 33.0)

    # thirteen draws: the ten above plus 55, 55, 55 -- median the 7th, 33.
    everything = result.population_spread_summary(only_completed=False)
    assert everything["sample"] == "all_draws"
    assert (everything["n_chains"], everything["n_draws"]) == (2, 13)
    assert (everything["min"], everything["median"], everything["max"]) == (
        9.0,
        33.0,
        55.0,
    )

    # The default is exactly the sample the convergence numbers are computed on.
    assert default["n_chains"] == len(result.cut_edges_chains())
    assert default["n_draws"] == sum(len(c) for c in result.population_spread_chains())


def test_a_real_infeasible_epsilon_is_recorded_rather_than_raised():
    """The real GerryChain failure path, once.

    Four units of 100, 101, 102 and 103 persons cannot be split into two equal
    halves, so no epsilon this tight is satisfiable. The test costs about 20
    seconds because the sampler spends its whole 100,000-attempt budget before
    giving up, which is the behaviour being checked: it gives up, and the run
    records that rather than propagating it.
    """
    adjacency, populations = _path_graph(4, uneven=True)
    result = ens.run_chains(adjacency, populations, 2, 1e-9, 5, [1])
    assert result.chain_failures == 1
    assert result.failure_rate == 1.0
    assert result.n_completed == 0
    assert result.distinct_plans == 0
    assert result.completed_traces == ()
    assert "Error" in result.traces[0].failure


# ==========================================================================
# the node_repeats regression guard
# ==========================================================================


def test_node_repeats_defaults_to_zero():
    """docs/FEASIBILITY.md section 5.1: a positive value is the documented bug."""
    for function in (ens.sample, ens.run_chains):
        default = inspect.signature(function).parameters["node_repeats"].default
        assert default == 0, f"{function.__name__} default is {default}"


def test_a_positive_node_repeats_warns_loudly():
    adjacency, populations = _grid(4)
    with pytest.warns(RuntimeWarning, match="node_repeats must be 0"):
        list(ens.sample(adjacency, populations, 4, 0.05, 3, seed=1, node_repeats=5))


def test_the_generator_package_never_suppresses_warnings():
    """The bug in the feasibility pass was hidden by exactly this call.

    GerryChain's warning named the parameter and the fix; a filterwarnings call
    one line above the sweep silenced it, and the resulting failure was reported
    as a property of the problem.
    """
    banned = {"filterwarnings", "simplefilter", "catch_warnings"}
    for path in sorted((ROOT / "src" / "generate").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                called = node.func
                name = getattr(called, "attr", None) or getattr(called, "id", None)
                assert name not in banned, f"{path}:{node.lineno} calls {name}"


# ==========================================================================
# Iowa, end to end
# ==========================================================================


needs_data = pytest.mark.skipif(
    not (PROCESSED / "ia_units.csv").exists(),
    reason="data/processed not built; run tools/prepare_data.py",
)


@needs_data
def test_units_load_through_the_guarded_loader():
    adjacency, populations = ens.load_inputs()
    assert len(populations) == 99
    assert sum(populations.values()) == 3190369
    assert set(adjacency) == set(populations)
    assert sum(len(v) for v in adjacency.values()) // 2 == 222


@needs_data
def test_a_short_iowa_chain_produces_legal_whole_county_plans():
    adjacency, populations = ens.load_inputs()
    graph = nx.Graph()
    graph.add_nodes_from(adjacency)
    for unit, neighbours in adjacency.items():
        for other in neighbours:
            graph.add_edge(unit, other)

    k, epsilon = 4, 2e-3
    ideal = sum(populations.values()) / k
    result = ens.run_chains(adjacency, populations, k, epsilon, 12, sd.stream(20260818, "test-chain", 2))
    assert result.n_completed > 0

    for plan in result.plans:
        assert set(plan) == set(populations)
        totals = ens.district_totals(plan, populations, k)
        assert sorted(totals) == [1, 2, 3, 4]
        assert sum(totals.values()) == 3190369
        for total in totals.values():
            assert abs(total - ideal) <= epsilon * ideal + 1e-9
        for district in totals:
            members = [u for u, d in plan.items() if d == district]
            assert nx.is_connected(graph.subgraph(members))
        # County splits are identically zero by construction: a plan assigns each
        # of the 99 whole counties to exactly one district, so the criterion is a
        # point mass at 0 on Iowa and carries no detection signal
        # (docs/FEASIBILITY.md section 5.3).
        assert len(plan) == 99


@needs_data
def test_iowa_at_the_configured_epsilon_counts_failures_rather_than_raising():
    """The operating point: Iowa, k=4, epsilon=2e-4 (docs/ARCHITECTURE.md section 5).

    The rest of the Iowa tests run at 2e-3 and 5e-3, 10x and 25x looser than the
    configured epsilon, and the only other real-GerryChain failure is a synthetic
    4-unit path at epsilon=1e-9. But the whole failure-accounting design exists
    for the 1e-4..2e-4 regime -- docs/FEASIBILITY.md section 5.1 measures a 13%
    per-seed failure rate at 2e-4 and 63% at 1e-4 -- so it is tested where it
    lives, on the real 99-county graph at the epsilon the bench is configured
    with.

    Cost: about two minutes, nearly all of it the one seed that dies. A seed
    fails by exhausting GerryChain's 100,000-attempt budget, and that is the
    price of observing a real failure rather than a stand-in; the accounting
    around it is tested cheaply and deterministically above. Only the epsilon and
    the graph match section 5's configuration -- 3 steps and 4 chains, not 2000
    and 8 -- because chain length is what costs time and the quantity under test
    does not depend on it.

    The four seeds are the first four of one purpose string, not a hand-picked
    set: the purpose is part of the run's identity (docs/ARCHITECTURE.md section
    7), so renaming it here would silently draw four different chains and the
    seed that dies would no longer be the one that dies.
    """
    adjacency, populations = ens.load_inputs()
    k, epsilon, steps = 4, 2e-4, 3
    ideal = sum(populations.values()) / k
    seeds = sd.stream(20260818, "tight-a", 4)

    result = ens.run_chains(adjacency, populations, k, epsilon, steps, seeds)

    # Counted, not raised: getting here at all is half the assertion.
    assert result.chain_failures == 1
    assert result.failure_rate == 0.25              # chains, not draws
    assert result.n_requested == 12
    assert result.n_completed == 9                  # 3 surviving chains x 3 steps
    assert [t.steps_completed for t in result.traces] == [3, 0, 3, 3]

    dead = result.traces[1]
    assert dead.completed is False
    assert "Could not find a possible cut" in dead.failure
    assert dead.plans == ()
    assert dead.seconds > 0

    # The surviving draws are legal plans at the configured tolerance. epsilon
    # bounds each district's deviation, so the permitted max-min spread is about
    # 2 * epsilon * ideal = 319 persons (docs/FEASIBILITY.md section 5.2).
    graph = nx.Graph()
    graph.add_nodes_from(adjacency)
    for unit, neighbours in adjacency.items():
        for other in neighbours:
            graph.add_edge(unit, other)
    for plan in result.plans:
        assert len(plan) == 99 and set(plan) == set(populations)
        totals = ens.district_totals(plan, populations, k)
        assert sorted(totals) == [1, 2, 3, 4]
        assert sum(totals.values()) == 3190369
        for total in totals.values():
            assert abs(total - ideal) <= epsilon * ideal + 1e-9
        for district in totals:
            members = [u for u, d in plan.items() if d == district]
            assert nx.is_connected(graph.subgraph(members))
        assert ens.population_spread(plan, populations, k) <= 2 * epsilon * ideal + 1

    # The reported summary says which of the four chains it describes.
    summary = result.population_spread_summary()
    assert summary["sample"] == "completed_chains"
    assert (summary["n_chains"], summary["n_draws"]) == (3, 9)


@needs_data
def test_convergence_diagnostics_run_on_a_real_ensemble():
    adjacency, populations = ens.load_inputs()
    result = ens.run_chains(
        adjacency, populations, 4, 5e-3, 60, sd.stream(20260818, "test-convergence", 4)
    )
    chains = result.cut_edges_chains()
    if len(chains) < 2:
        pytest.skip(f"too few chains survived: {result.failure_rate}")
    rhat = cv.split_rhat(chains)
    effective = cv.ess(chains)
    assert math.isfinite(rhat) and rhat > 0.9
    assert 0 < effective <= sum(len(chain) for chain in chains) * 2
