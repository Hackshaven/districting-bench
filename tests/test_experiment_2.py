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

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import experiment_2_tradeoffs as X    # noqa: E402


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


def test_controls_pass_on_the_real_tests():
    report = X.controls(seed=4242)
    for kind, expectation in X.CONTROL_EXPECTATIONS.items():
        assert set(report[kind]["got"].values()) == {expectation}


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
    rows = [[{"cut_edges": i, "abs_efficiency_gap": (i % 7) / 10}
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

def _chain(seed, n, *, failure=None, steps=None):
    rows = [{"cut_edges": (i * 7) % 13,
             "abs_efficiency_gap": ((i * 3) % 11) / 10,
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
