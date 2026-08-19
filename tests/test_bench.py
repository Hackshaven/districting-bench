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

**Round 3 adds a fourth group: the artifact has to be checkable.** Those tests
assert properties rather than values — that every scenario's plan is on disk and
hashes to the digest published for it, that ``verify`` rejects a report whose
numbers its own plans do not support, that the legality gate is read at the
operating epsilon rather than the run's, that compactness is in the legality
claim and its floor is one-sided, and that a ``--quick`` run says in the file
that its gates are not measurements. The tampering tests are the important ones:
a verifier that has never been shown a wrong artifact is not known to reject one.

The gate values are deliberately **not** asserted. A test that pinned the TPR
would turn the detection gates into something the test suite protects rather
than something the bench measures, and CRITERIA.md section 8 is explicit that
the measurement is the point. What is asserted is that the gates are computed,
that they read the rates they claim to read, and that a degenerate detector
fails one of them. The same goes for the ensemble budget: nothing here pins
``FULL``'s size, because the size is a cost decision that ``Size``'s docstring
argues for and a test would only freeze.
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
    """A location a resolution-checking rule will actually accept.

    ``n_distinct_plans``, ``ess`` and the interior band are not decoration: since
    round 3 ``confusion.Rule`` refuses to evaluate a location that cannot express
    its threshold, and a hand-built location missing them is unresolvable rather
    than unremarkable. Round 2's version of this helper omitted them, which is
    the same mistake in a test that the bench made in the artifact.
    """
    return O.Location(
        metric=metric, status=O.LOCATED, value=0.0, percentile=percentile,
        p_below=percentile, p_at_or_below=percentile,
        two_sided_p=2 * min(percentile, 1 - percentile), z=0.0, n=400,
        n_distinct=400, n_distinct_plans=400, ess=400.0, ess_basis="plans",
        min_interior_percentile=0.0025, max_interior_percentile=0.9975,
        outside_support=False, trusted=True,
    )


def _case(case_id: str, kind: str, percentile: float,
          stratum: str | None = None) -> bench.Case:
    provenance = {} if stratum is None else {
        "stratum": stratum, "in_gate_sample": stratum in bench.GATE_NULL_STRATA
    }
    return bench.Case(
        id=case_id, kind=kind, plan={"a": 1},
        intended_seat_shift=0 if kind == "null" else 2,
        realized_seat_shift=0, target_party=None, baseline="x",
        metrics={}, locations={"efficiency_gap": _loc("efficiency_gap", percentile)},
        notes=(), provenance=provenance,
    )


def test_stratum_reports_a_rate_and_an_interval_per_stratum():
    cases = [_case("null_a", "null", 0.999), _case("null_b", "null", 0.5)]
    decisions = {s.id: d for s, d in C.decide([c.scenario() for c in cases], bench.RULE)}
    out = bench._stratum(cases, decisions)
    assert out["n"] == 2 and out["flagged"] == 1 and out["fpr"] == 0.5
    assert out["resolved"] == 2 and out["unresolved"] == 0
    assert out["ci95"][0] < 0.5 < out["ci95"][1]


def test_stratum_counts_an_abstention_as_unresolved_not_as_clean():
    """A rule that could not look has not cleared the case. Round 2 reported it clean."""
    cases = [_case("null_a", "null", 0.999), _case("null_b", "null", 0.5)]
    cases[1].locations = {"efficiency_gap": O.Location(
        metric="efficiency_gap", status=O.INSUFFICIENT_ENSEMBLE, n=3)}
    decisions = {s.id: d for s, d in C.decide([c.scenario() for c in cases], bench.RULE)}
    out = bench._stratum(cases, decisions)
    assert out["n"] == 2 and out["resolved"] == 1 and out["unresolved"] == 1
    assert out["fpr"] == 1.0, "the rate is over the cases the rule could evaluate"


def test_only_the_pre_registered_null_strata_reach_the_gate():
    """The excluded stratum is published as a scenario and left out of one number."""
    assert "seat_outcome" in bench.NULL_STRATA
    assert "seat_outcome" not in bench.GATE_NULL_STRATA
    assert set(bench.GATE_NULL_STRATA) < set(bench.NULL_STRATA)
    assert bench._in_gate_sample(_case("p", "planted", 0.5)) is True
    assert bench._in_gate_sample(_case("n", "null", 0.5, "random")) is True
    assert bench._in_gate_sample(_case("n", "null", 0.5, "seat_outcome")) is False


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
        assert s["flagged"] in (True, False, None), (
            "flagged is three-valued: None is an abstention, not a clean case"
        )
        if s["flagged"] is None:
            assert s["decision_reason"], "an abstention must say why"
        if s["kind"] == "null":
            assert s["intended_seat_shift"] == 0
        else:
            assert s["intended_seat_shift"] != 0
            assert s["realized_seat_shift"] == s["intended_seat_shift"], (
                "plant_gerrymander guarantees the realized shift equals the "
                "intended one; a near miss must never be relabelled"
            )


@iowa
def test_every_null_stratum_is_published_and_rated_separately(quick_report):
    strata = quick_report["diagnostics"]["null_strata"]
    for name in bench.NULL_STRATA:
        assert strata[f"null_{name}"]["n"] >= 1
        assert strata[f"null_{name}"]["selection_rule"]
    published = [s for s in quick_report["scenarios"] if s["kind"] == "null"]
    assert len(published) == sum(
        strata[f"null_{name}"]["n"] for name in bench.NULL_STRATA
    ), "every stratum drawn is published as a scenario, gate or no gate"


@iowa
def test_the_gate_pools_only_the_pre_registered_strata_and_says_so(quick_report):
    """CRITERIA.md 8 wants one FPR; which nulls go into it is a choice, so it is named."""
    strata = quick_report["diagnostics"]["null_strata"]
    sample = quick_report["confusion"]["gate_sample"]
    assert sample["null_strata_pooled"] == list(bench.GATE_NULL_STRATA)
    assert sample["null_strata_excluded"] == ["seat_outcome"]
    assert sample["reason"]
    pooled = quick_report["confusion"]["matrix"]
    assert pooled["n_null"] == sum(
        strata[f"null_{name}"]["n"] for name in bench.GATE_NULL_STRATA
    )
    excluded_ids = set(sample["excluded_ids"])
    assert excluded_ids == {
        s["id"] for s in quick_report["scenarios"] if not s["in_gate_sample"]
    }
    assert excluded_ids, "the excluded stratum is still in the artifact"
    assert quick_report["confusion"]["all_strata"]["n_null"] > pooled["n_null"], (
        "the pooled-over-everything rate is reported beside the gate's"
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
    scenarios = [s for s in quick_report["scenarios"] if s["in_gate_sample"]]
    planted = [s for s in scenarios if s["kind"] == "planted"]
    nulls = [s for s in scenarios if s["kind"] == "null"]
    assert matrix["n_positive"] == len(planted)
    assert matrix["n_null"] == len(nulls)
    assert matrix["tp"] == sum(1 for s in planted if s["flagged"] is True)
    assert matrix["fp"] == sum(1 for s in nulls if s["flagged"] is True)
    assert matrix["tp"] + matrix["fn"] + matrix["unresolved_positive"] == len(planted)
    assert matrix["fp"] + matrix["tn"] + matrix["unresolved_null"] == len(nulls)
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
def test_the_artifact_publishes_no_verdict_on_the_enacted_plan(quick_report):
    """README and CRITERIA.md 11. Round 2 published ``flagged: true`` on CD118."""
    review = quick_report["plan_under_review"]
    assert "flagged" not in review, (
        "a boolean judgement on the map in force is the bug CRITERIA.md 11 names"
    )
    assert review["percentiles"] and review["statuses"], (
        "what replaces the verdict is the location, per metric"
    )
    body = json.dumps(review)
    for word in ("gerrymander", "verdict"):
        assert f'"{word}"' not in body


@iowa
def test_the_artifact_says_which_metrics_cannot_tell_the_enacted_map_apart(quick_report):
    """Round 2's enacted EG was bit-identical to a planted one and said nothing."""
    block = quick_report["plan_under_review"]["indistinguishable_from"]
    assert block["tolerance"] == 1e-12 and block["note"]
    for name, ids in block["metrics"].items():
        assert name in bench.LOCATED_METRICS
        for scenario_id in ids:
            s = next(x for x in quick_report["scenarios"] if x["id"] == scenario_id)
            assert s["metrics"][name] == quick_report["plan_under_review"]["metrics"][name]


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


# --------------------------------------------------------------------------- #
# round 3: the artifact has to be checkable, and the legality claim honest
# --------------------------------------------------------------------------- #

def test_write_plan_round_trips_through_evaluates_own_loader(tmp_path):
    """The sidecar is only useful if the loader in the contract can read it."""
    from evaluate import plan as EP
    plan = {"19001": 1, "19003": 2, "19005": 1}
    path = tmp_path / "p.csv"
    bench.write_plan(path, plan)
    assert path.read_text().splitlines()[0] == "GEOID,district"
    assert EP.load_plan(path) == plan
    assert O.plan_digest(EP.load_plan(path)) == O.plan_digest(plan)


def test_write_plan_is_a_function_of_the_assignment_alone(tmp_path):
    """Two orderings of the same plan give the same bytes, so digests compare."""
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    bench.write_plan(a, {"19005": 1, "19001": 2})
    bench.write_plan(b, {"19001": 2, "19005": 1})
    assert a.read_bytes() == b.read_bytes()


def test_compactness_floor_is_one_sided_and_admits_every_plan_it_was_built_from():
    """The value choice, tested as a property: no neutral draw is illegal by it."""
    from adversarial import gerrymander as G
    columns = {
        "cut_edges": [40.0, 45.0, 52.0],
        "polsby_popper_mean": [0.30, 0.33, 0.36],
        "reock_mean": [0.32, 0.40, 0.47],
        "schwartzberg_mean": [1.60, 1.75, 1.87],
        "convex_hull_mean": [0.70, 0.75, 0.79],
    }
    enacted = {"cut_edges": 51.0, "polsby_popper_mean": 0.29, "reock_mean": 0.33,
               "schwartzberg_mean": 1.90, "convex_hull_mean": 0.71}
    floor = bench.compactness_floor(
        columns, [enacted], n_draws=3, n_distinct=3, source="test")
    assert floor is not None
    # one-sided, in the direction evaluate.compactness declares
    assert floor.bounds["cut_edges"][0] == -math.inf
    assert floor.bounds["polsby_popper_mean"][1] == math.inf
    # every calibration plan is inside, including the enacted one
    for i in range(3):
        assert floor.contains({k: v[i] for k, v in columns.items()})
    assert floor.contains(enacted)
    # a plan more compact than anything neutral is legal; a raggeder one is not
    assert floor.contains({**enacted, "cut_edges": 20.0, "polsby_popper_mean": 0.9,
                           "reock_mean": 0.9, "schwartzberg_mean": 1.0,
                           "convex_hull_mean": 0.99})
    broken = floor.violations({**enacted, "cut_edges": 95.0})
    assert "cut_edges" in broken and "95" in broken["cut_edges"]


def test_compactness_floor_admits_a_neutral_draw_outside_the_reference():
    """The nulls come from a different pool; a floor that fails them measures noise."""
    columns = {name: [1.0, 2.0] for name in
               ("polsby_popper_mean", "reock_mean", "convex_hull_mean")}
    columns["cut_edges"] = [40.0, 45.0]
    columns["schwartzberg_mean"] = [1.6, 1.7]
    stray = {"cut_edges": 60.0, "polsby_popper_mean": 0.5, "reock_mean": 0.5,
             "schwartzberg_mean": 2.5, "convex_hull_mean": 0.5}
    floor = bench.compactness_floor(
        columns, [stray], n_draws=2, n_distinct=2, source="test")
    assert floor.contains(stray)


def test_plant_envelope_is_the_central_band_and_two_sided():
    """D-010's constraint is two-sided; conspicuously compact is conspicuous too."""
    columns = {name: [float(i) for i in range(101)] for name in
               ("cut_edges", "polsby_popper_mean", "reock_mean",
                "schwartzberg_mean", "convex_hull_mean")}
    env = bench.plant_envelope(columns, n_draws=101, n_distinct=101, source="test")
    assert env.coverage == bench.PLANT_SHAPE_COVERAGE
    for low, high in env.bounds.values():
        assert (low, high) == pytest.approx((5.0, 95.0))
    assert not env.contains({name: 100.0 for name in env.bounds})
    assert not env.contains({name: 0.0 for name in env.bounds})


def test_inside_filters_reference_draws_by_the_columns_already_measured():
    columns = {name: [0.0, 50.0, 100.0] for name in
               ("cut_edges", "polsby_popper_mean", "reock_mean",
                "schwartzberg_mean", "convex_hull_mean")}
    env = bench.plant_envelope(
        {name: [float(i) for i in range(101)] for name in columns},
        n_draws=101, n_distinct=101, source="test")
    plans = [{"a": 1, "b": 2}, {"a": 2, "b": 1}, {"a": 1, "b": 1}]
    inside = bench._inside(plans, columns, env, 2)
    assert inside == [{"a": 2, "b": 1}], "only the middle draw is in the band"
    assert bench._inside(plans, columns, None, 2) == []


def test_gate_qualification_is_false_on_a_reference_too_small_to_express_the_rule():
    ens = _FakeEnsemble(distinct=10, draws=100)
    out = bench.gate_qualification(
        bench.FULL, ens, {"efficiency_gap": [0.01 * i for i in range(100)]},
        _CONVERGED, {"coverage": 1.0, "n_resolved": 1, "n": 1})
    assert out["meaningful"] is False
    assert any("distinct" in r for r in out["reasons"])
    assert out["reference"]["required_distinct"] == bench.RULE.required_distinct


def test_gate_qualification_is_false_for_a_quick_run_however_it_scores():
    ens = _FakeEnsemble(distinct=5000, draws=5000)
    columns = {"efficiency_gap": [0.0001 * i for i in range(5000)]}
    out = bench.gate_qualification(
        bench.QUICK, ens, columns, _CONVERGED,
        {"coverage": 1.0, "n_resolved": 1, "n": 1})
    assert out["meaningful"] is False
    assert any("smoke run" in r for r in out["reasons"])
    assert "NOT MEANINGFUL" in out["note"]


def test_gate_qualification_keeps_findings_out_of_the_meaningfulness_verdict():
    """A failing R-hat is a finding to report, not a reason to void the gates."""
    ens = _FakeEnsemble(distinct=5000, draws=5000)
    columns = {"efficiency_gap": [0.0001 * i for i in range(5000)]}
    conv = {"cut_edges": {"split_rhat": 1.47}, "pop_spread": {"split_rhat": 1.18}}
    out = bench.gate_qualification(
        bench.FULL, ens, columns, conv,
        {"coverage": 1.0, "n_resolved": 1, "n": 1})
    assert out["meaningful"] is True
    assert any("R-hat" in c for c in out["caveats"])


def test_rhat_trend_separates_a_budget_problem_from_a_sampler_problem():
    """The distinction the split_rhat gate turns on, computed from the run itself."""
    falling = {"cut_edges": [
        {"draws_per_chain": 50, "split_rhat": 1.40, "ess": 10.0},
        {"draws_per_chain": 100, "split_rhat": 1.20, "ess": 20.0},
        {"draws_per_chain": 200, "split_rhat": 1.07, "ess": 40.0},
    ]}
    out = bench.rhat_trend(falling)["cut_edges"]
    assert out["still_falling"] is True and out["ess_still_growing"] is True
    assert out["first"]["split_rhat"] == 1.40 and out["last"]["split_rhat"] == 1.07
    assert out["change_over_last_checkpoint"] == pytest.approx(-0.13)

    stuck = {"cut_edges": [
        {"draws_per_chain": 100, "split_rhat": 1.66, "ess": 8.2},
        {"draws_per_chain": 300, "split_rhat": 1.68, "ess": 8.1},
        {"draws_per_chain": 500, "split_rhat": 1.67, "ess": 8.3},
    ]}
    out = bench.rhat_trend(stuck)["cut_edges"]
    assert out["still_falling"] is True, "1.67 < 1.68 — falling by a hair"
    assert abs(out["change_over_last_checkpoint"]) < 0.02, (
        "a run that has stopped moving reports a change near zero, which is the "
        "number that says more draws will not help"
    )
    assert bench.rhat_trend({"pop_spread": []})["pop_spread"]["note"]


@iowa
def test_the_rhat_gate_carries_the_trend_it_was_read_from(quick_report):
    gate = quick_report["gates"]["split_rhat"]
    assert gate["target"] == bench.RHAT_GATE
    assert "trend" in gate
    trace = quick_report["diagnostics"]["convergence_trace"]
    for name in ("cut_edges", "pop_spread"):
        if gate["trend"][name].get("last"):
            assert gate["trend"][name]["last"]["split_rhat"] == (
                [r for r in trace[name] if r["split_rhat"] is not None][-1]["split_rhat"]
            )


class _FakeEnsemble:
    def __init__(self, distinct, draws):
        self.distinct_plans = distinct
        self.plans = [None] * draws
        self.failure_rate = 0.0
        self.chain_failures = 0
        self.seeds = (1, 2)


_CONVERGED = {"cut_edges": {"split_rhat": 1.0}, "pop_spread": {"split_rhat": 1.0}}


@iowa
def test_parallel_chains_are_the_same_chains(tmp_path):
    """The merge is the one aggregate the bench computes that generate also computes."""
    from generate import ensemble, seeds
    inputs = bench.load_inputs()
    chain_seeds = list(seeds.stream(99, "parallel-test", 2))
    serial = ensemble.run_chains(
        inputs.gen_adjacency, inputs.gen_populations, bench.K, 1e-3, 6,
        chain_seeds, bench.NODE_REPEATS)
    parallel = bench.run_chains_parallel(
        inputs.gen_adjacency, inputs.gen_populations, bench.K, 1e-3, 6,
        chain_seeds, bench.NODE_REPEATS, jobs=2)
    assert parallel.seeds == serial.seeds
    assert parallel.plans == serial.plans
    assert parallel.n_completed == serial.n_completed
    assert parallel.chain_failures == serial.chain_failures
    assert parallel.failure_rate == serial.failure_rate
    assert parallel.distinct_plans == serial.distinct_plans
    assert [t.cut_edges for t in parallel.traces] == [t.cut_edges for t in serial.traces]
    assert [t.failure for t in parallel.traces] == [t.failure for t in serial.traces]


@iowa
def test_every_scenario_carries_a_digest_and_a_plan_on_disk(quick_report):
    """ARCHITECTURE.md 5 makes this file the one critics read; round 2 shipped no plans."""
    from evaluate import plan as EP
    out = Path(quick_report["_path"]).parent
    digests = set()
    for s in quick_report["scenarios"]:
        path = out / s["plan"]["file"]
        assert path.exists(), f"{s['id']} has no plan on disk"
        loaded = EP.load_plan(path)
        assert O.plan_digest(loaded) == s["plan"]["digest"]
        assert len(loaded) == s["plan"]["n_units"]
        digests.add(s["plan"]["digest"])
    assert len(digests) == len(quick_report["scenarios"]), (
        "two scenarios sharing a digest are the same plan counted twice"
    )
    manifest = quick_report["plans"]
    assert manifest["n_files"] == len(quick_report["scenarios"]) + 2
    for name in ("baseline_enacted", "baseline_ensemble_max_d"):
        assert (out / "plans" / f"{name}.csv").exists()


@iowa
def test_every_scenario_says_which_seed_it_came_from(quick_report):
    """ARCHITECTURE.md 7: a scenario is regenerable from the master seed or it is not."""
    for s in quick_report["scenarios"]:
        provenance = s["provenance"]
        assert provenance["derivation"]
        if s["kind"] == "planted":
            assert isinstance(provenance["seed"], int)
            assert provenance["purpose"].startswith(f"round-{quick_report['round']}/")
            assert provenance["baseline"] == s["baseline"]
        else:
            assert provenance["stratum"] in bench.NULL_STRATA
            assert provenance["selection_rank"] >= 1


@iowa
def test_verify_accepts_the_run_that_produced_it(quick_report):
    result = bench.verify(Path(quick_report["_path"]).parent)
    assert result["ok"], result["failures"]
    assert result["checked"] == len(quick_report["scenarios"])
    assert result["checks"] > result["checked"]


@iowa
@pytest.mark.parametrize("field,value", [
    ("legal", True),
    ("realized_seat_shift", 3),
])
def test_verify_catches_a_claim_the_plans_do_not_support(quick_report, tmp_path, field, value):
    """The point of the sidecar: a number nobody can check is not a measurement."""
    import shutil
    src = Path(quick_report["_path"]).parent
    dst = tmp_path / "tampered"
    shutil.copytree(src, dst)
    report = json.loads((dst / "bench-results.json").read_text())
    target = next(s for s in report["scenarios"] if s[field] != value)
    target[field] = value
    (dst / "bench-results.json").write_text(json.dumps(report))
    result = bench.verify(dst)
    assert not result["ok"]
    assert any(f["field"] == field and f["id"] == target["id"]
               for f in result["failures"]), result["failures"]


@iowa
def test_verify_catches_a_plan_swapped_under_its_digest(quick_report, tmp_path):
    import shutil
    src = Path(quick_report["_path"]).parent
    dst = tmp_path / "swapped"
    shutil.copytree(src, dst)
    report = json.loads((dst / "bench-results.json").read_text())
    a, b = report["scenarios"][0], report["scenarios"][1]
    (dst / a["plan"]["file"]).write_text((dst / b["plan"]["file"]).read_text())
    result = bench.verify(dst)
    assert not result["ok"]
    assert any(f["field"] == "plan.digest" for f in result["failures"])


@iowa
def test_the_legality_gate_is_read_at_the_operating_epsilon_not_the_run_s(quick_report):
    """Round 1 reported legal_compliance 1.0 at 1e-3 against an operating 2e-4."""
    gate = quick_report["gates"]["legal_compliance"]
    assert gate["epsilon"] == bench.GATE_EPSILON == bench.EPSILON
    assert quick_report["config"]["epsilon"] == bench.QUICK.epsilon
    assert gate["run_epsilon"] == bench.QUICK.epsilon
    assert gate["run_epsilon"] > gate["epsilon"], "the smoke run is looser on purpose"
    measured = sum(1 for s in quick_report["scenarios"] if s["legal"])
    assert gate["value"] == pytest.approx(measured / len(quick_report["scenarios"]))
    assert gate["value_at_run_epsilon"] is not None
    assert gate["value_at_run_epsilon"] >= gate["value"], (
        "the looser tolerance cannot certify fewer plans than the tighter one"
    )


@iowa
def test_a_quick_run_cannot_report_a_legality_pass_the_operating_point_would_fail(quick_report):
    """The whole finding, as one property."""
    gate = quick_report["gates"]["legal_compliance"]
    if gate["pass"] is True:
        for s in quick_report["scenarios"]:
            assert s["legality"]["legal_at_gate_epsilon"], s["id"]
    else:
        assert gate["illegal_ids"], "a failing gate must name the plans that failed it"
        for scenario_id in gate["illegal_ids"]:
            s = next(x for x in quick_report["scenarios"] if x["id"] == scenario_id)
            assert s["legal_failures"], "an illegal plan names the constraint it broke"


@iowa
def test_compactness_is_part_of_the_legality_claim(quick_report):
    """Iowa Code ch. 42 criterion 4. Round 2 certified plans nobody had measured."""
    gate = quick_report["gates"]["legal_compliance"]
    assert gate["compactness_included"] is True
    floor = quick_report["diagnostics"]["compactness_floor"]
    assert floor["calibrated"] is True
    assert set(floor["bounds"]) == set(bench.COMPACTNESS_METRICS)
    for name, row in floor["bounds"].items():
        assert (row["at_least"] is None) != (row["at_most"] is None), (
            f"{name}: the floor is one-sided; see bench.compactness_floor"
        )
    for s in quick_report["scenarios"]:
        assert s["legality"]["compactness_checked"] is True


@iowa
def test_the_gates_block_says_whether_it_is_meaningful(quick_report):
    """bench.Size has said so in a docstring since round 1; the artifact did not."""
    qual = quick_report["gates"]["qualification"]
    assert qual["meaningful"] is False, "a --quick run is never a measurement"
    assert qual["size"] == "quick"
    assert qual["reasons"], "an unmeaningful verdict has to say why"
    assert "NOT MEANINGFUL" in qual["note"]
    for key in ("tpr_at_2seat", "fpr_on_nulls", "split_rhat", "legal_compliance"):
        assert quick_report["gates"][key]["meaningful"] is False
        assert quick_report["gates"][key]["meaningful_note"] == qual["note"]


@iowa
def test_convergence_is_reported_over_both_rectangles(quick_report):
    """The completed chains are the gate's sample; the partial ones are evidence too."""
    gated = quick_report["ensemble"]["convergence"]
    assert gated["sample"] == "completed_chains"
    everything = quick_report["diagnostics"]["convergence_all_chains"]
    assert everything["sample"] == "all_chains_truncated_to_shortest"
    assert everything["n_chains"] >= gated["n_chains"]
    for name in ("cut_edges", "pop_spread"):
        assert "split_rhat" in everything[name] and "n_chains_used" in everything[name]


@iowa
def test_the_reference_resolution_is_counted_in_plans_not_in_repeated_draws(quick_report):
    """806 draws holding 177 plans are 177 plans. Round 2's rule read the 806."""
    ens = quick_report["ensemble"]
    assert ens["distinct_plans"] <= ens["n_completed"]
    qual = quick_report["gates"]["qualification"]["reference"]
    assert qual["distinct_plans"] == ens["distinct_plans"]
    assert set(qual["ess_by_rule_metric"]) == set(bench.RULE.metrics)


def test_summary_lines_show_both_rates_never_one():
    """A report quoting one rate presents a degenerate detector as a working one."""
    report = json.loads(_MINIMAL_REPORT)
    lines = "\n".join(bench.summary_lines(report))
    assert "TPR" in lines and "FPR" in lines
    assert "split_rhat" in lines and "legal_compliance" in lines


def test_summary_lines_carry_the_unmeaningful_banner_and_the_gate_epsilon():
    """Whatever else a reader skips, they cannot skip these two."""
    lines = "\n".join(bench.summary_lines(json.loads(_MINIMAL_REPORT)))
    assert "NOT MEANINGFUL" in lines
    assert "at epsilon=0.0002" in lines
    assert "not in the gate" in lines, "the excluded stratum is marked on stdout"


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
        "legal_compliance": {"target": 1.0, "value": 1.0, "pass": True,
                             "epsilon": 2e-4},
        "qualification": {"meaningful": False, "size": "quick",
                          "note": "GATE VALUES ON THIS RUN ARE NOT MEANINGFUL",
                          "reasons": ["a smoke run"], "caveats": []},
    },
    "firewall": {"clean": True, "config_sha256": "0" * 64},
    "diagnostics": {
        "report_lines": ["TPR = 1.0000", "FPR = 0.0000"],
        "null_strata": {
            "null_concentration": {"n": 1, "flagged": 0, "resolved": 1,
                                   "fpr": 0.0, "in_gate_sample": True},
            "null_seat_outcome": {"n": 1, "flagged": 1, "resolved": 1,
                                  "fpr": 1.0, "in_gate_sample": False},
            "null_random": {"n": 1, "flagged": 0, "resolved": 1,
                            "fpr": 0.0, "in_gate_sample": True},
            "note": "the gate pools concentration, random",
        },
    },
})
