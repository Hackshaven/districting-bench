"""Tests for src/detect/bench.py — the headless bench.

The bench is plumbing, and the things that go wrong in plumbing are not wrong
formulas but wrong wiring: a report that quietly loses a chain failure, a rate
computed over the wrong denominator, a "deterministic" run that is not. So the
tests here fall into three groups.

**Pure functions, no data needed.** :func:`bench.plant_cases` and friends need
Iowa on disk, but the report assembly helpers do not: ``_json_safe``,
``_achievable``, ``_stratum``, ``_diagnostics`` and ``_summary`` are exercised
against hand-built inputs where the right answer is known before the code runs.

**Contract tests against ARCHITECTURE.md section 5.** Every key the schema names
is checked to exist with the right shape and the right nesting, because that
document is the contract critics read the file against and a silently renamed
key is the failure that makes a report unreadable without saying so.

**One real `--quick` run, twice.** The determinism requirement can only be tested
by running it, so ``test_two_quick_runs_are_identical_except_for_timing`` does
exactly that and diffs the two reports with the ``timing`` block removed. It is
the slowest test in the suite (about a minute for the pair) and it is the one
that would catch an unseeded ``random.Random()`` or a dict built from a set.

The gate values are deliberately **not** asserted. A test that pinned the TPR
would turn the detection gates into something the test suite protects rather
than something the bench measures, and CRITERIA.md section 8 is explicit that
the measurement is the point. What is asserted is that the gates are computed,
that they read the rates they claim to read, and that a degenerate detector
fails one of them.
"""
from __future__ import annotations

import json
import math
import pathlib
from pathlib import Path

import pytest

from detect import bench
from detect import confusion as C
from detect import outlier as O

PROCESSED = Path("data/processed")
HAVE_IOWA = all(
    (PROCESSED / name).exists()
    for name in ("ia_units.csv", "ia_units.gpkg", "ia_adjacency.json",
                 "ia_elections.csv", "ia_enacted_cd118.csv")
)
iowa = pytest.mark.skipif(not HAVE_IOWA, reason="data/processed not built")


# --------------------------------------------------------------------------- #
# configuration constants
# --------------------------------------------------------------------------- #

def test_the_operating_point_is_the_measured_one():
    """FEASIBILITY.md 5.1: epsilon 2e-4 with node_repeats 0, and nothing else."""
    assert bench.EPSILON == pytest.approx(2e-4)
    assert bench.NODE_REPEATS == 0
    assert bench.FULL.epsilon == bench.EPSILON
    assert bench.QUICK.epsilon > bench.EPSILON, (
        "the smoke test runs looser on purpose; see Size.__doc__ for why, and "
        "config.epsilon records what actually ran"
    )


def test_the_rule_of_record_is_printable_and_partisan_only():
    """The decision rule is a parameter, not a buried scoring function."""
    assert bench.RULE.metrics == bench.PARTISAN_METRICS
    assert bench.RULE.threshold == 0.99
    assert bench.RULE.tail == "two_sided"
    assert bench.RULE.untrusted == "exclude"
    assert "flag when" in bench.RULE.describe()


def test_no_function_collapses_fairness_to_one_number():
    """prompt.md: no ``fairness_score()``.

    Checked structurally across all of ``src/``, not by grepping for the string.
    A substring search fails on the docstrings that exist precisely to say the
    function is absent, which is the opposite of the property under test: the
    ban is on a callable that returns one summary number, not on discussing one.
    """
    import ast

    names = [n for n in dir(bench) if not n.startswith("__")]
    assert not [n for n in names if "score" in n.lower()]

    offenders = []
    for path in sorted(pathlib.Path("src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                low = node.name.lower()
                if "fairness" in low or "score" in low:
                    offenders.append(f"{path}:{node.lineno} {node.name}")
    assert not offenders, f"a fairness-collapsing definition exists: {offenders}"


def test_quick_is_smaller_than_full_in_every_dimension():
    for field in ("chains", "steps", "null_chains", "null_steps", "replicates",
                  "n_hard_nulls", "n_random_nulls"):
        assert getattr(bench.QUICK, field) <= getattr(bench.FULL, field)


def test_seed_purposes_carry_the_round_number():
    """prompt.md: scenarios regenerate every round rather than being re-scored."""
    assert bench._purpose(1, "ensemble") != bench._purpose(2, "ensemble")
    assert "round-7" in bench._purpose(7, "plant/D/2")


# --------------------------------------------------------------------------- #
# report helpers, hand-built inputs
# --------------------------------------------------------------------------- #

def test_json_safe_turns_nan_and_inf_into_null_not_zero():
    out = bench._json_safe(
        {"a": float("nan"), "b": float("inf"), "c": [1.0, float("-inf")], "d": (1, 2)}
    )
    assert out == {"a": None, "b": None, "c": [1.0, None], "d": [1, 2]}
    json.dumps(out, allow_nan=False)  # would raise if a nan survived


def test_json_safe_leaves_real_numbers_alone():
    assert bench._json_safe({"x": 0.0, "y": -1.5, "z": None}) == {
        "x": 0.0, "y": -1.5, "z": None
    }


def test_achievable_range_reports_attempts_not_assumptions():
    attempts = [
        {"target_party": "D", "intended_seat_shift": 1, "reached": True},
        {"target_party": "D", "intended_seat_shift": 2, "reached": True},
        {"target_party": "D", "intended_seat_shift": 3, "reached": False},
        {"target_party": "R", "intended_seat_shift": 1, "reached": False},
    ]
    out = bench._achievable(attempts)
    assert out["D"]["reached"] == [1, 2]
    assert out["D"]["max_reached"] == 2
    assert out["D"]["success_by_magnitude"]["3"] == {"reached": 0, "attempted": 1}
    assert out["R"]["max_reached"] == 0, "an unreached magnitude is 0, never absent"


def _loc(metric: str, percentile: float) -> O.Location:
    return O.Location(
        metric=metric, status=O.LOCATED, value=0.0, percentile=percentile,
        p_below=percentile, p_at_or_below=percentile,
        two_sided_p=2 * min(percentile, 1 - percentile), z=0.0, n=100,
        trusted=True,
    )


def _case(case_id: str, kind: str, percentile: float) -> bench.Case:
    return bench.Case(
        id=case_id, kind=kind, plan={"a": 1},
        intended_seat_shift=0 if kind == "null" else 2,
        realized_seat_shift=0, target_party=None, baseline="x",
        metrics={}, locations={"efficiency_gap": _loc("efficiency_gap", percentile)},
        legal=True, legal_failures=[], notes=(),
    )


def test_stratum_reports_a_rate_and_an_interval_per_stratum():
    cases = [_case("null_a", "null", 0.999), _case("null_b", "null", 0.5)]
    decisions = {s.id: d for s, d in C.decide([c.scenario() for c in cases], bench.RULE)}
    out = bench._stratum(cases, decisions)
    assert out["n"] == 2 and out["flagged"] == 1 and out["fpr"] == 0.5
    assert out["ci95"][0] < 0.5 < out["ci95"][1]


def test_stratum_of_no_cases_reports_none_not_zero():
    assert bench._stratum([], {})["fpr"] is None


def test_diagnostics_refuse_a_between_chain_statistic_on_one_chain():
    out = bench._diagnostics([[1.0, 2.0, 3.0, 4.0, 5.0]])
    assert out["split_rhat"] is None and out["ess"] is None
    assert "two" in out["note"]


def test_diagnostics_compute_rhat_and_ess_on_two_chains():
    chains = [[float((i * 7 + j) % 13) for i in range(40)] for j in range(4)]
    out = bench._diagnostics(chains)
    assert out["split_rhat"] is not None and out["split_rhat"] > 0
    assert out["ess"] is not None and out["ess"] > 0


def test_diagnostics_on_a_constant_quantity_report_none_not_a_number():
    out = bench._diagnostics([[3.0] * 20, [3.0] * 20])
    assert out["split_rhat"] is None
    assert out["note"]


def test_summary_of_an_all_undefined_column_says_so():
    out = bench._summary([None, None, None])
    assert out["n"] == 0 and out["n_undefined"] == 3 and "undefined" in out["note"]


def test_summary_counts_undefined_draws_separately():
    out = bench._summary([1.0, 2.0, None, 4.0])
    assert out["n"] == 3 and out["n_undefined"] == 1
    assert out["median"] == pytest.approx(2.0)


def test_finite_rejects_nan_and_inf():
    assert bench._finite(1.5) == 1.5
    assert bench._finite(float("nan")) is None
    assert bench._finite(float("inf")) is None
    assert bench._finite(None) is None


# --------------------------------------------------------------------------- #
# the real run
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def quick_report(tmp_path_factory):
    """One real ``--quick`` run, shared by every test below."""
    out = tmp_path_factory.mktemp("bench-quick")
    return bench.run(master_seed=20260818, round_number=1, size=bench.QUICK,
                     out_dir=out, make_plots=True)


@iowa
def test_a_quick_run_records_the_epsilon_it_actually_used(quick_report):
    """A loosened smoke test must be visible as one in the file it writes."""
    assert quick_report["config"]["epsilon"] == bench.QUICK.epsilon
    assert quick_report["config"]["size"] == "quick"


@iowa
def test_the_report_has_every_key_architecture_section_5_names(quick_report):
    for key in ("schema_version", "round", "config", "ensemble", "scenarios",
                "confusion", "gates", "firewall"):
        assert key in quick_report, f"ARCHITECTURE.md 5 requires {key!r}"
    assert quick_report["schema_version"] == bench.SCHEMA_VERSION
    config = quick_report["config"]
    for key in ("state", "units", "n_districts", "epsilon", "steps", "chains",
                "master_seed", "node_repeats"):
        assert key in config
    assert config["state"] == "IA" and config["units"] == "county"
    assert config["n_districts"] == 4 and config["node_repeats"] == 0


@iowa
def test_the_ensemble_block_reports_failures_and_names_its_samples(quick_report):
    """ARCHITECTURE.md 7: the failure rate is itself a sampling bias, so it is reported."""
    ens = quick_report["ensemble"]
    for key in ("n_requested", "n_completed", "chain_failures", "failure_rate",
                "distinct_plans", "convergence", "population_spread"):
        assert key in ens
    assert ens["n_requested"] == bench.QUICK.chains * bench.QUICK.steps
    assert 0.0 <= ens["failure_rate"] <= 1.0
    assert ens["failure_rate"] == pytest.approx(
        ens["chain_failures"] / bench.QUICK.chains
    )
    assert ens["distinct_plans"] <= ens["n_completed"]
    assert ens["population_spread"]["sample"] in ("completed_chains", "all_draws")
    assert ens["reference_sample"] == "all_draws"


@iowa
def test_convergence_covers_both_quantities_with_both_statistics(quick_report):
    conv = quick_report["ensemble"]["convergence"]
    for name in ("cut_edges", "pop_spread"):
        assert "split_rhat" in conv[name] and "ess" in conv[name]
    assert conv["sample"] == "completed_chains"


@iowa
def test_every_scenario_is_labelled_and_carries_its_percentiles(quick_report):
    scenarios = quick_report["scenarios"]
    assert scenarios, "a bench with no scenarios measures nothing"
    ids = [s["id"] for s in scenarios]
    assert len(ids) == len(set(ids)), "scenario ids must be unique"
    for s in scenarios:
        assert s["kind"] in ("planted", "null")
        assert set(s["metrics"]) == set(bench.LOCATED_METRICS)
        assert set(s["percentiles"]) == set(bench.LOCATED_METRICS)
        assert isinstance(s["flagged"], bool)
        if s["kind"] == "null":
            assert s["intended_seat_shift"] == 0
        else:
            assert s["intended_seat_shift"] != 0
            assert s["realized_seat_shift"] == s["intended_seat_shift"], (
                "plant_gerrymander guarantees the realized shift equals the "
                "intended one; a near miss must never be relabelled"
            )


@iowa
def test_both_null_strata_are_present_and_reported_separately(quick_report):
    strata = quick_report["diagnostics"]["null_strata"]
    assert strata["null_geography"]["n"] == bench.QUICK.n_hard_nulls
    assert strata["null_random"]["n"] >= 1
    pooled = quick_report["confusion"]["matrix"]
    assert pooled["n_null"] == (
        strata["null_geography"]["n"] + strata["null_random"]["n"]
    )


@iowa
def test_administrative_metrics_get_no_percentile_on_county_units(quick_report):
    """FEASIBILITY.md 5.3: county splits are identically 0, so 0.5 would be a lie."""
    for s in quick_report["scenarios"]:
        for name in bench.ADMIN_METRICS:
            assert s["percentiles"][name] is None
            assert s["statuses"][name] == O.DEGENERATE


@iowa
def test_the_confusion_block_matches_the_scenarios_it_was_built_from(quick_report):
    matrix = quick_report["confusion"]["matrix"]
    scenarios = quick_report["scenarios"]
    planted = [s for s in scenarios if s["kind"] == "planted"]
    nulls = [s for s in scenarios if s["kind"] == "null"]
    assert matrix["n_positive"] == len(planted)
    assert matrix["n_null"] == len(nulls)
    assert matrix["tp"] == sum(1 for s in planted if s["flagged"])
    assert matrix["fp"] == sum(1 for s in nulls if s["flagged"])
    assert matrix["tp"] + matrix["fn"] == len(planted)
    assert matrix["fp"] + matrix["tn"] == len(nulls)
    assert "accuracy" not in matrix and "f1" not in matrix


@iowa
def test_the_gates_block_has_all_four_gates_in_schema_shape(quick_report):
    gates = quick_report["gates"]
    for key in ("tpr_at_2seat", "fpr_on_nulls", "split_rhat", "legal_compliance"):
        assert key in gates
        for field in ("target", "value", "pass"):
            assert field in gates[key]
        assert gates[key]["pass"] in (True, False, None)
    assert gates["tpr_at_2seat"]["target"] == C.TPR_GATE
    assert gates["fpr_on_nulls"]["target"] == C.FPR_GATE
    assert gates["split_rhat"]["target"] == bench.RHAT_GATE


@iowa
def test_the_gates_read_the_rates_they_claim_to_read(quick_report):
    gates, conf = quick_report["gates"], quick_report["confusion"]
    assert gates["fpr_on_nulls"]["value"] == conf["fpr_on_nulls"]
    assert gates["tpr_at_2seat"]["value"] == conf["tpr_at_2seat"]
    if gates["fpr_on_nulls"]["value"] is not None:
        assert gates["fpr_on_nulls"]["pass"] == (
            gates["fpr_on_nulls"]["value"] <= C.FPR_GATE
        )


@iowa
def test_min_detectable_seat_shift_is_reported_and_not_gated(quick_report):
    """CRITERIA.md 8 classes it DERIVED: report, do not gate."""
    assert "min_detectable_seat_shift" in quick_report["confusion"]
    assert "min_detectable_seat_shift" not in quick_report["gates"]


@iowa
def test_the_firewall_block_records_the_verdict_and_the_config_hash(quick_report):
    fw = quick_report["firewall"]
    assert fw["clean"] is True, "check_firewall.py must be clean for a valid run"
    assert len(fw["config_sha256"]) == 64
    import hashlib
    expected = hashlib.sha256(
        (Path(bench.REPO_ROOT) / "tools" / "firewall.yaml").read_bytes()
    ).hexdigest()
    assert fw["config_sha256"] == expected


@iowa
def test_the_plan_under_review_is_reported_but_never_scored(quick_report):
    review = quick_report["plan_under_review"]
    assert review["seats"]["dem"] + review["seats"]["rep"] == 4
    ids = {s["id"] for s in quick_report["scenarios"]}
    assert review["id"] not in ids, (
        "the enacted plan carries no manufactured ground truth and must not "
        "contribute to any rate"
    )


@iowa
def test_degenerate_detectors_each_fail_exactly_one_gate(quick_report):
    """CRITERIA.md 8's asymmetry: flag-everything and flag-nothing each pass one."""
    alts = {a["rule"]["name"]: a for a in quick_report["diagnostics"]["alternative_rules"]}
    always, never = alts["always-flag"], alts["never-flag"]
    assert always["tpr"] == 1.0 and always["fpr"] == 1.0
    assert never["tpr"] == 0.0 and never["fpr"] == 0.0


@iowa
def test_metric_disagreement_covers_compactness_and_fairness(quick_report):
    block = quick_report["diagnostics"]["metric_disagreement"]
    comp = {(r["a"], r["b"]) for r in block["compactness"]["pairs"]}
    assert len(comp) == len(bench.COMPACTNESS_METRICS) * (
        len(bench.COMPACTNESS_METRICS) - 1) // 2
    fair = {(r["a"], r["b"]) for r in block["fairness"]["pairs"]}
    assert len(fair) == len(bench.PARTISAN_METRICS) * (
        len(bench.PARTISAN_METRICS) - 1) // 2
    assert block["compactness"]["oriented_by_direction"] is True
    assert block["fairness"]["oriented_by_direction"] is False


@iowa
def test_the_plots_are_written(quick_report):
    out = Path(quick_report["_path"]).parent
    for name in ("confusion-over-rounds.png", "detection-curve.png",
                 "ensemble-distributions.png", "metric-disagreement.png",
                 "convergence-trace.png"):
        assert (out / name).exists(), f"missing plot {name}"
        assert (out / name).stat().st_size > 1000


@iowa
def test_the_json_on_disk_parses_strictly(quick_report):
    """No ``NaN`` token: the file must be readable by a parser that is not Python."""
    text = Path(quick_report["_path"]).read_text(encoding="utf-8")
    parsed = json.loads(text, parse_constant=_reject)
    assert parsed["round"] == quick_report["round"]


def _reject(token):  # pragma: no cover - only runs on a malformed file
    raise AssertionError(f"bench-results.json contains the non-JSON token {token!r}")


@iowa
def test_timing_is_the_only_wall_clock_in_the_report(quick_report):
    """Segregation is what makes a diff between two runs meaningful."""
    assert "timing" in quick_report
    assert "generated_at" in quick_report["timing"]
    body = json.dumps(bench._json_safe(_without_timing(quick_report)))
    for word in ("seconds", "generated_at", "elapsed"):
        assert word not in body, f"{word!r} leaked outside the timing block"


def _without_timing(report):
    return {k: v for k, v in report.items() if k not in ("timing", "_path")}


@iowa
def test_two_quick_runs_are_identical_except_for_timing(tmp_path):
    """The determinism requirement, tested the only way it can be: by running it."""
    first = bench.run(master_seed=4242, round_number=3, size=bench.QUICK,
                      out_dir=tmp_path / "a", make_plots=False)
    second = bench.run(master_seed=4242, round_number=3, size=bench.QUICK,
                       out_dir=tmp_path / "b", make_plots=False)
    a = json.dumps(bench._json_safe(_without_timing(first)), sort_keys=True)
    b = json.dumps(bench._json_safe(_without_timing(second)), sort_keys=True)
    assert a == b


@iowa
def test_a_different_round_draws_different_scenarios(tmp_path):
    """Fresh seeds per round: nothing overfits to a fixed case (prompt.md)."""
    one = bench.run(master_seed=4242, round_number=1, size=bench.QUICK,
                    out_dir=tmp_path / "r1", make_plots=False)
    two = bench.run(master_seed=4242, round_number=2, size=bench.QUICK,
                    out_dir=tmp_path / "r2", make_plots=False)
    assert one["ensemble"]["seeds"] != two["ensemble"]["seeds"]
    digests_one = {s["metrics"]["cut_edges"] for s in one["scenarios"]}
    digests_two = {s["metrics"]["cut_edges"] for s in two["scenarios"]}
    assert digests_one != digests_two


@iowa
def test_the_cli_runs_and_reports(tmp_path, capsys):
    code = bench.main([
        "--master-seed", "20260818", "--round", "1", "--quick",
        "--out-dir", str(tmp_path), "--no-plots",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "TPR" in out and "FPR" in out and "gates:" in out
    assert (tmp_path / "bench-results.json").exists()


def test_summary_lines_show_both_rates_never_one():
    """A report quoting one rate presents a degenerate detector as a working one."""
    report = json.loads(_MINIMAL_REPORT)
    lines = "\n".join(bench.summary_lines(report))
    assert "TPR" in lines and "FPR" in lines
    assert "split_rhat" in lines and "legal_compliance" in lines


_MINIMAL_REPORT = json.dumps({
    "round": 1,
    "config": {"master_seed": 1, "size": "quick"},
    "ensemble": {
        "n_completed": 10, "n_requested": 10, "distinct_plans": 5,
        "chain_failures": 0, "failure_rate": 0.0,
        "convergence": {
            "cut_edges": {"split_rhat": 1.0, "ess": 10.0},
            "pop_spread": {"split_rhat": 1.0, "ess": 10.0},
        },
    },
    "confusion": {},
    "gates": {
        "tpr_at_2seat": {"target": 0.95, "value": 1.0, "pass": True},
        "fpr_on_nulls": {"target": 0.05, "value": 0.0, "pass": True},
        "split_rhat": {"target": 1.01, "value": 1.0, "pass": True},
        "legal_compliance": {"target": 1.0, "value": 1.0, "pass": True},
    },
    "firewall": {"clean": True, "config_sha256": "0" * 64},
    "diagnostics": {
        "report_lines": ["TPR = 1.0000", "FPR = 0.0000"],
        "null_strata": {
            "null_geography": {"n": 1, "flagged": 0, "fpr": 0.0},
            "null_random": {"n": 1, "flagged": 0, "fpr": 0.0},
        },
    },
})
