"""Tests for tools/experiment_2_tradeoffs.py — the tradeoff-frontier instrument.

The experiment itself runs once and is not re-run; what is worth guarding is the
*instrument*, because the previous run of this experiment produced two findings
that were properties of the driver rather than of the data:

1. It reported "all three deciding tests agree" when two of the three could not
   have disagreed — they were constants.
2. It diagnosed Iowa's convergence on 216 of 36,784 draws, because a driver had
   truncated every chain to the shortest survivor's length.

So the tests here are mostly about the instrument's ability to be wrong. Each of
the three tests must return ``tradeoff`` on synthetic data that has one and
``none`` on data that does not; :func:`controls` must *fail* when a test is
replaced by something that cannot decide; and the convergence reporter must both
exclude dead chains and say how many draws it actually used.

The verdict arithmetic is tested separately from the tests themselves, because
"two of three tests fired" and "the pair is a weak tradeoff" are different
claims and a bug in the mapping between them would be invisible in the
per-test output.
"""

from __future__ import annotations

import csv
import dataclasses
import gzip
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import experiment_2_tradeoffs as X    # noqa: E402
import check_metric_algebra as _algebra_module_available   # noqa: E402,F401


# --------------------------------------------------------------------------- #
# the three tests can produce both verdicts
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(X.TESTS))
@pytest.mark.parametrize(
    "kind,expected",
    [("tradeoff", "tradeoff"), ("independent", "none"), ("synergy", "none")],
)
def test_each_test_decides_correctly_on_known_structure(name, kind, expected):
    rng = random.Random(11)
    a, b = X._synthetic(kind, rng)
    assert X.TESTS[name](a, b, rng)["verdict"] == expected


@pytest.mark.parametrize("name", sorted(X.TESTS))
def test_no_test_denies_a_perfect_tradeoff_on_a_coarse_criterion(name):
    """The regime the original controls never generated.

    The conditional test was a proven constant here: with more than half the mass
    on the lowest of three values, the decile median cannot move, so it returned
    "none" on a perfect tradeoff. Detecting it or abstaining are both acceptable;
    denying it is not.
    """
    rng = random.Random(11)
    a, b = X._synthetic("discrete_tradeoff", rng)
    assert X.TESTS[name](a, b, rng)["verdict"] != "none"


def test_the_discrete_control_really_is_coarse():
    """Guard the guard: a control arm that drifted continuous would test nothing."""
    _, b = X._synthetic("discrete_tradeoff", random.Random(5))
    values = {v for chain in b for v in chain}
    assert len(values) == len(X.DISCRETE_CONTROL_LEVELS) <= 3
    pooled = [v for chain in b for v in chain]
    commonest = max(set(pooled), key=pooled.count)
    assert pooled.count(commonest) / len(pooled) > 0.5, (
        "the median must sit on the modal level, which is what makes the "
        "conditional effect unattainable"
    )


def test_controls_pass_on_the_real_tests():
    report = X.controls(seed=4242)
    for kind, expectation in X.CONTROL_EXPECTATIONS.items():
        got = set(report[kind]["got"].values())
        if expectation is None:
            assert "none" not in got, kind
        else:
            assert got == {expectation}, kind


def test_controls_reject_a_test_that_can_never_say_tradeoff(monkeypatch):
    """The exact defect the controls exist to catch: a test that is a constant."""
    monkeypatch.setitem(
        X.TESTS, "correlation", lambda a, b, rng: {"verdict": "none"}
    )
    with pytest.raises(AssertionError, match="control failed"):
        X.controls(seed=4242)


def test_controls_reject_a_test_that_always_says_tradeoff(monkeypatch):
    monkeypatch.setitem(
        X.TESTS, "achievability", lambda a, b, rng: {"verdict": "tradeoff"}
    )
    with pytest.raises(AssertionError, match="control failed"):
        X.controls(seed=4242)


# --------------------------------------------------------------------------- #
# degeneracy is not "no tradeoff"
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(X.TESTS))
def test_a_constant_criterion_is_degenerate_not_none(name):
    rng = random.Random(3)
    a = [[rng.gauss(0, 1) for _ in range(50)] for _ in range(4)]
    b = [[0.0] * 50 for _ in range(4)]
    assert X.TESTS[name](a, b, rng)["verdict"] == "degenerate"


def test_pair_verdict_is_degenerate_if_any_test_is():
    rng = random.Random(3)
    rows = [[{"cut_edges": i, "county_splits": 0} for i in range(40)]
            for _ in range(4)]
    result = X.evaluate_pair(rows, "compactness_cut", "county_integrity", rng)
    assert result["verdict"] == "degenerate"
    assert result["pareto"] is None


# --------------------------------------------------------------------------- #
# verdict arithmetic
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "verdicts,expected",
    [
        (("tradeoff", "tradeoff", "tradeoff"), "strong"),
        (("tradeoff", "tradeoff", "none"), "weak"),
        (("tradeoff", "none", "none"), "weak"),
        (("none", "none", "none"), "none"),
    ],
)
def test_votes_map_to_verdict(monkeypatch, verdicts, expected):
    for name, verdict in zip(sorted(X.TESTS), verdicts):
        monkeypatch.setitem(
            X.TESTS, name, lambda a, b, rng, v=verdict: {"verdict": v}
        )
    key = X.criteria_for(X.PRIMARY_CONTEST)["fairness_eg"][0]
    rows = [[{"cut_edges": i, key: (i % 7) / 10}
             for i in range(40)] for _ in range(3)]
    result = X.evaluate_pair(rows, "compactness_cut", "fairness_eg",
                             random.Random(0))
    assert result["verdict"] == expected
    assert result["votes"] == sum(1 for v in verdicts if v == "tradeoff")


# --------------------------------------------------------------------------- #
# direction handling — a sign error here inverts every finding silently
# --------------------------------------------------------------------------- #

def test_goodness_flips_lower_is_better_criteria():
    rows = [{"cut_edges": 10, "polsby_popper_mean": 0.3}]
    assert X.goodness(rows, "compactness_cut") == [-10.0]
    assert X.goodness(rows, "compactness_pp") == [0.3]


def test_every_criterion_declares_a_direction_and_a_statement():
    for name, (key, direction, statement) in X.CRITERIA.items():
        assert direction in (1, -1), name
        assert statement and not statement.endswith("."), name
        assert key


def test_partisan_criteria_are_bound_to_a_contest_and_others_are_not():
    bound = X.criteria_for("G20USS")
    for name in X.PARTISAN_CRITERIA:
        assert bound[name][0].endswith("@G20USS"), name
    assert bound["compactness_pp"][0] == "polsby_popper_mean"
    assert set(X.PARTISAN_CRITERIA) == {
        "fairness_eg", "fairness_mm", "competitiveness"
    }


def test_the_two_contests_bind_to_different_row_keys():
    primary = X.criteria_for(X.PRIMARY_CONTEST)
    alternate = X.criteria_for(X.ALTERNATE_CONTEST)
    assert X.PRIMARY_CONTEST != X.ALTERNATE_CONTEST
    for name in X.PARTISAN_CRITERIA:
        assert primary[name][0] != alternate[name][0], name


# --------------------------------------------------------------------------- #
# partial degeneracy must not erase the tests that could decide
# --------------------------------------------------------------------------- #

def _rows(n=60, chains=3):
    key = X.criteria_for(X.PRIMARY_CONTEST)["fairness_eg"][0]
    return [[{"cut_edges": (i * 3) % 17, key: ((i * 5) % 13) / 10}
             for i in range(n)] for _ in range(chains)]


def test_one_degenerate_test_leaves_the_others_deciding(monkeypatch):
    monkeypatch.setitem(X.TESTS, "correlation",
                        lambda a, b, rng: {"verdict": "degenerate"})
    monkeypatch.setitem(X.TESTS, "conditional",
                        lambda a, b, rng: {"verdict": "tradeoff"})
    monkeypatch.setitem(X.TESTS, "achievability",
                        lambda a, b, rng: {"verdict": "tradeoff"})
    result = X.evaluate_pair(_rows(), "compactness_cut", "fairness_eg",
                             random.Random(0))
    assert result["verdict"] == "weak"
    assert result["partial"] is True
    assert result["n_deciding"] == 2
    assert result["degenerate_tests"] == ["correlation"]


def test_strong_requires_all_three_tests_to_have_decided(monkeypatch):
    """Two firing tests and one that could not answer is never 'strong'."""
    monkeypatch.setitem(X.TESTS, "correlation",
                        lambda a, b, rng: {"verdict": "degenerate"})
    for name in ("conditional", "achievability"):
        monkeypatch.setitem(X.TESTS, name,
                            lambda a, b, rng: {"verdict": "tradeoff"})
    assert X.evaluate_pair(_rows(), "compactness_cut", "fairness_eg",
                           random.Random(0))["verdict"] != "strong"


def test_a_degenerate_test_is_not_a_vote_against_a_tradeoff(monkeypatch):
    monkeypatch.setitem(X.TESTS, "correlation",
                        lambda a, b, rng: {"verdict": "degenerate"})
    for name in ("conditional", "achievability"):
        monkeypatch.setitem(X.TESTS, name,
                            lambda a, b, rng: {"verdict": "none"})
    result = X.evaluate_pair(_rows(), "compactness_cut", "fairness_eg",
                             random.Random(0))
    assert result["verdict"] == "none"
    assert result["votes"] == 0


def test_robust_sd_falls_back_to_the_plain_sd_on_a_discrete_criterion():
    """More than half the mass on the median: the MAD is 0, the criterion is not."""
    values = [3.0] * 70 + [1.0] * 15 + [5.0] * 15
    assert X._robust_sd(values) > 0


def test_contest_comparison_counts_a_missing_pair_as_a_disagreement():
    primary = {"contest": "A", "pairs": [
        {"a": "x", "b": "y", "verdict": "none"},
        {"a": "y", "b": "x", "verdict": "weak"},
    ]}
    replication = {"contest": "B", "pairs": [
        {"a": "x", "b": "y", "verdict": "none"},
    ]}
    out = X.compare_contests(primary, replication)
    assert out["n_agree"] == 1
    assert out["n_differ"] == 1
    assert out["disagreements"][0]["B"] is None


# --------------------------------------------------------------------------- #
# the Pareto frontier
# --------------------------------------------------------------------------- #

def test_frontier_is_everything_under_a_perfect_tradeoff():
    a = [[float(i) for i in range(20)]]
    b = [[float(-i) for i in range(20)]]
    assert X.pareto_size(a, b)["frontier_fraction"] == 1.0


def test_frontier_collapses_to_one_point_under_perfect_synergy():
    a = [[float(i) for i in range(20)]]
    b = [[float(i) for i in range(20)]]
    frontier = X.pareto_size(a, b)
    assert frontier["n_frontier"] == 1
    assert frontier["b_at_best_a"] == frontier["best_b"]


# --------------------------------------------------------------------------- #
# convergence reporting — the second lost-run defect
# --------------------------------------------------------------------------- #

EG = X.criteria_for(X.PRIMARY_CONTEST)["fairness_eg"][0]


def _chain(seed, n, *, failure=None, steps=None):
    rows = [{"cut_edges": (i * 7) % 13,
             EG: ((i * 3) % 11) / 10,
             "population_spread": (i * 5) % 17}
            for i in range(n)]
    return X.ChainResult(seed=seed, steps_requested=steps or n,
                         rows=rows, failure=failure)


def test_diagnostics_use_every_draw_of_every_completed_chain():
    chains = [_chain(i, 200) for i in range(4)]
    report = X.diagnostics(chains)
    assert report["n_chains"] == 4
    assert report["n_draws_total"] == 800
    for metric in report["metrics"].values():
        assert metric["n_draws_used"] == 800


def test_diagnostics_exclude_dead_chains_and_do_not_truncate_to_them():
    """A chain that died at 4 draws must not set the length for the others."""
    chains = [_chain(i, 200) for i in range(3)]
    chains.append(_chain(9, 4, failure="RuntimeError: boom", steps=200))
    report = X.diagnostics(chains)
    assert report["n_chains"] == 3
    assert report["n_draws_total"] == 600
    for metric in report["metrics"].values():
        assert metric["n_draws_used"] == 600


def test_diagnostics_name_their_sample_and_refuse_a_single_chain():
    report = X.diagnostics([_chain(0, 100)])
    assert report["sample"] == "completed_chains"
    assert report["metrics"] == {}
    assert "fewer than two" in report["note"]


# --------------------------------------------------------------------------- #
# small helpers whose failure modes are quiet
# --------------------------------------------------------------------------- #

def test_robust_sd_is_zero_on_a_constant_and_positive_otherwise():
    assert X._robust_sd([3.0] * 10) == 0.0
    assert X._robust_sd([0.0, 1.0, 2.0, 3.0, 4.0]) > 0


def test_circular_shift_preserves_the_multiset():
    chain = [1.0, 2.0, 3.0, 4.0]
    assert sorted(X._circular_shift(chain, 3)) == sorted(chain)
    assert X._circular_shift(chain, 4) == chain


def test_quantile_interpolates():
    xs = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert X._quantile(xs, 0.0) == 0.0
    assert X._quantile(xs, 1.0) == 4.0
    assert X._quantile(xs, 0.5) == 2.0


def test_state_specs_pin_node_repeats_free_parameters():
    for spec in X.STATES.values():
        assert spec.chains >= 2, "the chain-level bootstrap needs chains"
        assert spec.steps > 0
    assert X.IOWA.county_prefix_len is None, (
        "Iowa's units are the counties; a prefix map would invent splits"
    )
    assert X.COLORADO.county_prefix_len == 5, "state FIPS + county FIPS"


# --------------------------------------------------------------------------- #
# checkpointing and parallelism must not change the ensemble
# --------------------------------------------------------------------------- #

TINY = X.StateSpec("IA", "ia", 4, 2e-4, 2, 12, county_prefix_len=None)
CONTESTS = (X.PRIMARY_CONTEST, X.ALTERNATE_CONTEST)


@pytest.fixture(scope="module")
def tiny_context():
    if not (X.PROCESSED / "ia_units.gpkg").exists():
        pytest.skip("Iowa data not on disk; run tools/prepare_data.py")
    return X.load_context(TINY, CONTESTS)


def test_resuming_from_checkpoints_reproduces_the_run(tmp_path, tiny_context):
    """The whole point of the checkpoint: resuming is the same run, not a rerun.

    If this ever fails, checkpointing is worse than useless -- it would produce
    an ensemble that differs from the uninterrupted one while looking identical
    in the artifact.
    """
    fresh = X.measure_ensemble(TINY, tiny_context, log=lambda *_: None,
                               checkpoints=tmp_path)
    resumed = X.measure_ensemble(TINY, tiny_context, log=lambda *_: None,
                                 checkpoints=tmp_path)
    assert [c.rows for c in resumed] == [c.rows for c in fresh]
    assert [c.seed for c in resumed] == [c.seed for c in fresh]
    assert [c.failure for c in resumed] == [c.failure for c in fresh]


def test_parallel_chains_match_serial_chains(tmp_path, tiny_context):
    serial = X.measure_ensemble(TINY, tiny_context, log=lambda *_: None, jobs=1)
    parallel = X.measure_ensemble(TINY, tiny_context, log=lambda *_: None, jobs=2)
    assert [c.rows for c in parallel] == [c.rows for c in serial]
    assert [c.seed for c in parallel] == [c.seed for c in serial]


def test_a_checkpoint_from_a_different_config_is_ignored(tmp_path, tiny_context):
    """A stale checkpoint that looked like a fresh run is the worst failure here."""
    X.measure_ensemble(TINY, tiny_context, log=lambda *_: None,
                       checkpoints=tmp_path)
    other = X.StateSpec("IA", "ia", 4, 2e-4, 2, 24, county_prefix_len=None)
    assert X.config_digest(other) != X.config_digest(TINY)
    assert X.load_checkpoint(other, 0, tmp_path) is None


def test_a_checkpoint_whose_seed_disagrees_is_ignored(tmp_path, tiny_context):
    """Belt and braces: the seed is re-derived, not trusted from the file."""
    X.measure_ensemble(TINY, tiny_context, log=lambda *_: None,
                       checkpoints=tmp_path)
    path = X.checkpoint_path(TINY, 0, tmp_path)
    with gzip.open(path, "rt") as handle:
        data = json.load(handle)
    data["seed"] += 1
    with gzip.open(path, "wt") as handle:
        json.dump(data, handle)
    assert X.load_checkpoint(TINY, 0, tmp_path) is None


def test_a_truncated_checkpoint_is_ignored_rather_than_raising(tmp_path,
                                                              tiny_context):
    X.measure_ensemble(TINY, tiny_context, log=lambda *_: None,
                       checkpoints=tmp_path)
    path = X.checkpoint_path(TINY, 0, tmp_path)
    path.write_bytes(path.read_bytes()[: len(path.read_bytes()) // 2])
    assert X.load_checkpoint(TINY, 0, tmp_path) is None


def test_config_digest_covers_every_parameter_that_changes_the_ensemble():
    base = X.COLORADO
    for field, value in (("k", 7), ("epsilon", 0.02), ("steps", 999),
                         ("county_prefix_len", 2), ("key", "XX")):
        altered = dataclasses.replace(base, **{field: value})
        assert X.config_digest(altered) != X.config_digest(base), field


# --------------------------------------------------------------------------- #
# the tie-break: a verdict must not depend on the order draws sit in
# --------------------------------------------------------------------------- #

def test_the_decile_is_tie_inclusive():
    """Ties at the boundary are all in, so selection depends on values only."""
    xs = [5.0] * 10 + [1.0] * 90
    ys = list(range(100))
    _, _, n = X._conditional_effect(xs, [float(y) for y in ys], 1.0)
    assert n == 10
    xs = [5.0] * 30 + [1.0] * 70          # decile boundary lands inside the tie
    _, _, n = X._conditional_effect(xs, [float(y) for y in ys], 1.0)
    assert n == 30, "every draw tying the boundary must be included"


def test_conditional_verdict_is_invariant_to_chain_relabelling():
    """The defect that stopped the first Colorado write-up.

    Three of Colorado's thirty-nine nulls flipped to 'tradeoff' when the eight
    exchangeable chains were relabelled -- a permutation carrying no information.
    Built here from a coarse A, which is what makes ties the normal case.
    """
    rng = random.Random(7)
    a_chains = [[float(rng.randrange(4)) for _ in range(150)] for _ in range(6)]
    b_chains = [[rng.gauss(0, 1) for _ in range(150)] for _ in range(6)]

    verdicts, effects = set(), set()
    for shuffle_seed in range(8):
        order = list(range(len(a_chains)))
        random.Random(shuffle_seed).shuffle(order)
        result = X.test_conditional([a_chains[i] for i in order],
                                    [b_chains[i] for i in order],
                                    random.Random(0))
        verdicts.add(result["verdict"])
        if result.get("effect") is not None:
            effects.add(round(result["effect"], 9))
    assert len(verdicts) == 1, f"verdict depends on chain order: {verdicts}"
    assert len(effects) <= 1, f"effect depends on chain order: {sorted(effects)}"


# --------------------------------------------------------------------------- #
# the attainability guard
# --------------------------------------------------------------------------- #

def test_conditional_abstains_when_no_ordering_could_make_it_fire():
    """More than half the mass on the minimum: the decile median cannot move."""
    rng = random.Random(3)
    b_chains = [[0.0] * 120 + [1.0] * 40 + [2.0] * 20 for _ in range(4)]
    a_chains = [[rng.gauss(0, 1) for _ in range(180)] for _ in range(4)]
    result = X.test_conditional(a_chains, b_chains, rng)
    assert result["verdict"] == "degenerate"
    assert "no ordering" in result["reason"]
    assert result["attainable_effect"] > X.EFFECT_TRADEOFF


def test_attainable_effect_is_the_worst_case_and_is_reachable_when_it_should_be():
    ys = [float(i) for i in range(100)]
    xs = [float(i) for i in range(100)]
    worst = X._attainable_effect(xs, ys, 1.0)
    assert worst < X.EFFECT_TRADEOFF, "a continuous criterion must be reachable"
    flat = [0.0] * 95 + [1.0] * 5
    assert X._attainable_effect(xs, flat, 1.0) == 0.0


# --------------------------------------------------------------------------- #
# symmetry, multiplicity, detection floor
# --------------------------------------------------------------------------- #

def _fake_pairs(verdict_ab, verdict_ba, sym="none"):
    def pair(a, b, v):
        return {"a": a, "b": b, "verdict": v,
                "tests": {"correlation": {"verdict": sym},
                          "achievability": {"verdict": sym},
                          "conditional": {"verdict": v, "p": 0.5, "effect": 0.0}}}
    return [pair("x", "y", verdict_ab), pair("y", "x", verdict_ba)]


def test_symmetry_check_reports_zero_when_symmetric_tests_agree():
    out = X.check_symmetry(_fake_pairs("none", "weak"))
    assert out["n_direction_dependent"] == 0
    assert out["directional_tests"] == ["conditional"]


def test_symmetry_check_catches_a_symmetric_test_that_disagrees():
    pairs = _fake_pairs("none", "none")
    pairs[1]["tests"]["correlation"]["verdict"] = "tradeoff"
    assert X.check_symmetry(pairs)["n_direction_dependent"] == 1


def test_relationships_collapse_two_directions_into_one():
    out = X.relationships(_fake_pairs("none", "weak"))
    assert out["n_relationships"] == 1
    assert out["n_direction_dependent"] == 1
    assert out["relationships"][0]["verdict"] == "weak"
    assert len(out["relationships"][0]["directions"]) == 2


def test_relationships_agree_gives_one_undivided_verdict():
    out = X.relationships(_fake_pairs("none", "none"))
    assert out["counts"] == {"none": 1}
    assert out["n_direction_dependent"] == 0


def test_benjamini_hochberg_is_monotone_and_never_below_the_raw_p():
    pairs = []
    for i, p in enumerate([0.001, 0.01, 0.02, 0.04, 0.5]):
        pairs.append({"a": f"a{i}", "b": "b", "verdict": "none",
                      "tests": {"conditional": {"verdict": "none", "p": p,
                                                "effect": -1.0}}})
    X.adjust_multiplicity(pairs)
    qs = [p["tests"]["conditional"]["q_value"] for p in pairs]
    assert qs == sorted(qs), "q-values must be monotone in p"
    for pair, q in zip(pairs, qs):
        assert q >= pair["tests"]["conditional"]["p"] - 1e-12


def test_injection_preserves_each_chain_marginal_exactly():
    """The detection floor is only meaningful if only the pairing changed."""
    rng = random.Random(4)
    a = [[rng.gauss(0, 1) for _ in range(60)] for _ in range(3)]
    b = [[float(rng.randrange(5)) for _ in range(60)] for _ in range(3)]
    for blend in (0.0, 0.3, 2.0):
        _, injected = X._inject(a, b, blend, random.Random(1))
        for before, after in zip(b, injected):
            assert sorted(before) == sorted(after)


def test_the_calibration_grid_reaches_negligible_dependence():
    """A floor of 'below the weakest thing I tried' is not a floor."""
    assert min(X.CALIBRATION_BLEND) == 0.0, "must include the strongest reversal"
    rng = random.Random(4)
    a = [[rng.gauss(0, 1) for _ in range(300)] for _ in range(3)]
    b = [[rng.gauss(0, 1) for _ in range(300)] for _ in range(3)]
    _, weakest = X._inject(a, b, max(X.CALIBRATION_BLEND), random.Random(1))
    rho = X.C.spearman([v for c in a for v in c],
                       [v for c in weakest for v in c])
    assert abs(rho) < 0.10, (
        f"the weakest grid point still carries |rho|={abs(rho):.3f}; every test "
        f"must have stopped firing before the grid runs out"
    )


def test_injection_at_zero_blend_is_a_strong_reversal():
    rng = random.Random(4)
    a = [[rng.gauss(0, 1) for _ in range(200)] for _ in range(3)]
    b = [[rng.gauss(0, 1) for _ in range(200)] for _ in range(3)]
    _, injected = X._inject(a, b, 0.0, random.Random(1))
    flat_a = [v for c in a for v in c]
    flat_b = [v for c in injected for v in c]
    assert X.C.spearman(flat_a, flat_b) < -0.9


def test_written_draws_are_byte_stable_across_runs(tmp_path):
    """gzip stamps the clock into its header unless told not to.

    A committed artifact whose bytes change on every identical re-run cannot be
    diffed, and the reason for committing the draws at all is that a reader can
    check them without re-sampling.
    """
    keys = sorted({key for contest in (X.PRIMARY_CONTEST, X.ALTERNATE_CONTEST)
                   for key, _, _ in X.criteria_for(contest).values()})
    rows = [{k: float(i) for k in keys} for i in range(5)]
    chains = [X.ChainResult(seed=1, steps_requested=5, rows=rows)]
    first, second = tmp_path / "a.csv.gz", tmp_path / "b.csv.gz"
    X.write_rows(TINY, chains, first)
    X.write_rows(TINY, chains, second)
    assert first.read_bytes() == second.read_bytes()


# --------------------------------------------------------------------------- #
# the re-analysis path — report assembly, not statistics
# --------------------------------------------------------------------------- #

def _truncated_draws(tmp_path, prefix, keep=90):
    """A small but structurally complete draws file, plus its sidecar."""
    src = X.OUT / f"{prefix}-draws.csv.gz"
    if not src.exists():
        pytest.skip(f"{src} not on disk")
    out = tmp_path / f"{prefix}-draws.csv.gz"
    kept = {}
    with gzip.open(src, "rt", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = []
        for row in reader:
            index = int(row["chain_index"])
            if kept.get(index, 0) >= keep:
                continue
            kept[index] = kept.get(index, 0) + 1
            rows.append(row)
    with gzip.open(out, "wt", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    sidecar = X.OUT / f"{prefix}-chains.json"
    if sidecar.exists():
        data = json.loads(sidecar.read_text())
        for record in data["chains"]:
            record["n_rows"] = kept.get(record["index"], 0)
        (tmp_path / f"{prefix}-chains.json").write_text(json.dumps(data))
    return out


def test_reanalysis_assembles_a_complete_report(tmp_path, monkeypatch):
    """Exercise every block of the report, cheaply.

    This is a wiring test, not a statistics test: the thresholds are turned down
    so it runs in seconds. It exists because the re-analysis path shipped with a
    NameError in report assembly -- it referenced the sampling context that this
    path never builds -- and every statistical test in this module passed while
    the driver could not produce a report at all.
    """
    monkeypatch.setattr(X, "BOOTSTRAP", 20)
    monkeypatch.setattr(X, "PERMUTATIONS", 20)
    monkeypatch.setattr(X, "CALIBRATION_BLEND", (0.0, 64.0))
    draws = _truncated_draws(tmp_path, "ia")

    report, chains = X.run_state(X.IOWA, draws=draws, log=lambda *_: None)

    for key in ("state", "config", "ensemble", "convergence", "criteria",
                "pairs", "symmetry", "relationships", "multiplicity",
                "detection_floor", "summary", "replication",
                "contest_agreement"):
        assert key in report, key
    assert report["config"]["columns"]["G20PRE"] == ["G20PREDBID", "G20PRERTRU"]
    assert report["relationships"]["n_relationships"] > 0
    assert report["multiplicity"]["method"] == "Benjamini-Hochberg"
    assert len(report["detection_floor"]) == 2
    assert json.dumps(report, default=str)          # must be serialisable
    assert chains


def test_reanalysis_recovers_chains_that_produced_no_draws(tmp_path):
    """The failure rate is part of the result; an empty chain must not vanish."""
    draws = _truncated_draws(tmp_path, "ia")
    chains = X.chains_from_draws(X.IOWA, draws)
    assert len(chains) == X.IOWA.chains, (
        "every attempted chain must be recovered, including those that died "
        "before producing a draw"
    )
    assert sum(1 for c in chains if not c.completed) == 4


def test_reanalysis_refuses_a_draws_file_from_another_configuration(tmp_path):
    draws = _truncated_draws(tmp_path, "ia")
    other = dataclasses.replace(X.IOWA, key="CO")
    with pytest.raises(ValueError, match="different run"):
        X.chains_from_draws(other, draws)


# --------------------------------------------------------------------------- #
# multiplicity — the correction has to reach the headline, not sit beside it
# --------------------------------------------------------------------------- #

def _pair(a, b, *, p, corr="none", ach="none"):
    """A pair whose stated verdict agrees with its own tests, as the driver builds it."""
    tests = {
        "correlation": {"verdict": corr},
        "conditional": {"verdict": "tradeoff" if p < X.ALPHA else "none",
                        "p": p, "effect": -1.0},
        "achievability": {"verdict": ach},
    }
    verdict, votes, deciding = X.verdict_from(
        {name: t["verdict"] for name, t in tests.items()}, len(tests))
    return {"a": a, "b": b, "verdict": verdict, "votes": votes,
            "n_deciding": deciding, "tests": tests}


def test_correction_downgrades_a_verdict_carried_by_one_marginal_test():
    """Twenty tests, one at p=0.03: that is what a global null looks like."""
    pairs = [_pair("a", f"b{i}", p=0.03 if i == 0 else 0.6) for i in range(20)]
    report = X.adjust_multiplicity(pairs)
    assert report["applied_to_headline"] is True
    assert pairs[0]["verdict_uncorrected"] == "weak"
    assert pairs[0]["verdict"] == "none"
    assert report["n_pair_verdicts_changed"] == 1


def test_correction_leaves_a_strongly_significant_finding_alone():
    pairs = [_pair("a", f"b{i}", p=0.0001 if i == 0 else 0.6) for i in range(20)]
    X.adjust_multiplicity(pairs)
    assert pairs[0]["verdict"] == "weak"
    assert pairs[0]["tests"]["conditional"]["fires_after_correction"] is True


def test_correction_cannot_erase_a_finding_another_test_carries():
    """A pair the correlation test fires on does not depend on the permutation."""
    pairs = [_pair("a", f"b{i}", p=0.03 if i == 0 else 0.6) for i in range(20)]
    pairs[0]["tests"]["correlation"]["verdict"] = "tradeoff"
    X.adjust_multiplicity(pairs)
    assert pairs[0]["verdict"] == "weak"
    assert pairs[0]["votes"] == 1


def test_q_values_are_monotone_in_p():
    pairs = [_pair("a", f"b{i}", p=(i + 1) / 40) for i in range(20)]
    X.adjust_multiplicity(pairs)
    qs = [p["tests"]["conditional"]["q_value"] for p in
          sorted(pairs, key=lambda p: p["tests"]["conditional"]["p"])]
    assert qs == sorted(qs), "Benjamini-Hochberg q-values must not decrease"
    assert all(q >= p["tests"]["conditional"]["p"]
               for q, p in zip(qs, sorted(pairs,
                                          key=lambda p: p["tests"]["conditional"]["p"])))


def test_verdict_arithmetic_is_one_rule_used_twice():
    assert X.verdict_from({"a": "tradeoff", "b": "tradeoff", "c": "tradeoff"}, 3)[0] == "strong"
    assert X.verdict_from({"a": "tradeoff", "b": "none", "c": "none"}, 3)[0] == "weak"
    assert X.verdict_from({"a": "none", "b": "none", "c": "none"}, 3)[0] == "none"
    assert X.verdict_from({"a": "degenerate"}, 1)[0] == "degenerate"
    # three firing tests but one abstained: cannot be "strong"
    assert X.verdict_from(
        {"a": "tradeoff", "b": "tradeoff", "c": "degenerate"}, 3)[0] == "weak"


# --------------------------------------------------------------------------- #
# the algebra check — the guard on the one surviving finding
# --------------------------------------------------------------------------- #

import check_metric_algebra as A        # noqa: E402


def test_algebra_check_detects_a_genuine_tautology(monkeypatch):
    """The check must be able to FAIL, or it is decoration.

    Make the two metrics genuinely redundant -- competitiveness defined as a
    decreasing function of |mean-median| on the same vector -- and the
    arithmetic null must report the strong negative correlation that the real
    metrics do not produce. If this ever passes trivially, the check cannot
    defend the finding it exists to defend.
    """
    monkeypatch.setattr(
        A, "competitive",
        lambda shares, lo=0.45, hi=0.55: -abs(A.mean_median(shares)))
    rho = A.synthetic_rho(4, 0.45, 0.08, draws=2000)
    assert rho > 0.9, (
        f"a tautological pair must show as strongly correlated, got {rho}"
    )


def test_the_real_metric_pair_is_not_that():
    """The same call on the real definitions must not look tautological."""
    assert abs(A.synthetic_rho(4, 0.45, 0.08, draws=2000)) < 0.4


def test_arithmetic_rho_is_positive_for_both_states():
    """The finding this defends: the functional form pushes the OTHER way."""
    for state, (k, mu, observed) in A.OBSERVED.items():
        rho = A.synthetic_rho(k, mu, 0.08, draws=3000)
        assert rho > 0, f"{state}: arithmetic rho {rho} is not positive"
        assert rho > observed, state


def test_holding_the_mean_is_the_stricter_null():
    """A null that lets the statewide share float answers the wrong question."""
    free = A.synthetic_rho(4, 0.45, 0.08, draws=3000, hold_mean=False)
    held = A.synthetic_rho(4, 0.45, 0.08, draws=3000, hold_mean=True)
    assert free == pytest.approx(free)
    assert isinstance(held, float)


def test_check_flags_a_state_whose_observation_the_arithmetic_reproduces(
        monkeypatch):
    monkeypatch.setitem(A.OBSERVED, "XX", (4, 0.45, +0.9))
    report = A.check()
    assert report["states"]["XX"]["arithmetic_explains_observation"] is True
    assert report["states"]["IA"]["arithmetic_explains_observation"] is False


# --------------------------------------------------------------------------- #
# determinism of the controls themselves
# --------------------------------------------------------------------------- #

def test_controls_draw_the_same_seed_in_every_process():
    """The controls gate whether the experiment may run; they must not be flaky.

    The first version seeded them with ``seed + hash(kind)``, and hash() is
    salted per process for str, so every run drew a different seed. It surfaced
    as an intermittent suite failure. It could equally have surfaced as an
    experiment that ran on a day the controls happened to pass, which is the
    same defect the controls exist to prevent, one level up.
    """
    import subprocess
    script = (
        "import sys; sys.path.insert(0, 'tools'); sys.path.insert(0, 'src');"
        "import experiment_2_tradeoffs as X;"
        "print(X.controls(seed=4242)['tradeoff']['got'])"
    )
    outputs = {
        subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                       capture_output=True, text=True).stdout.strip()
        for _ in range(3)
    }
    assert len(outputs) == 1, f"controls are not process-stable: {outputs}"
    assert outputs.pop()


def test_no_salted_hash_decides_anything_in_the_experiment_drivers():
    """A regression guard on the whole class, not just the two call sites."""
    import re
    for name in ("experiment_1_sensitivity.py", "experiment_2_tradeoffs.py"):
        source = (ROOT / "tools" / name).read_text()
        for line_no, line in enumerate(source.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            assert not re.search(r"(?<!\w)hash\(", line), (
                f"{name}:{line_no} uses the builtin hash(), which is salted per "
                f"process for str and bytes. Use generate.seeds.derive."
            )
