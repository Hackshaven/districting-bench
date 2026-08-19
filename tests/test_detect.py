"""Tests for src/detect/outlier.py and src/detect/confusion.py.

Ground truth here is **manufactured**, which is the whole reason CRITERIA.md
section 8 says the detection gates are the only thresholds worth optimizing
against. Almost every test below builds its own locations and its own labels, so
the expected TPR and FPR are known exactly before the code runs and a detector
that gets them by luck cannot pass.

The two tests the task specification names by hand are
``test_always_flag_detector_fails_the_fpr_gate`` and
``test_never_flag_detector_fails_the_tpr_gate``. They exist because each
degenerate detector passes *one* of the two gates: flag-everything scores a
perfect TPR of 1.00 and flag-nothing scores a perfect FPR of 0.00, and a report
quoting either number alone would present it as a working detector. They are run
against the same scenario set as ``test_a_calibrated_detector_passes_both_gates``
so the three results are directly comparable.

Four regimes get their own tests because each produces a number that *looks*
like a percentile and is not one, and in each case the naive implementation is
also tested — the point is not that the right answer is produced but that the
plausible wrong one is refused:

* ``test_a_none_metric_is_not_a_percentile`` — declination under a one-party
  sweep. The wrong answer, ``None`` coerced to 0.0, would land in the low tail
  of the ensemble used there and **fire**, so the test fails loudly against an
  implementation that coerces.
* ``test_a_point_mass_ensemble_gets_no_percentile`` — county splits at county
  units. The wrong answer under the mid-rank convention is 0.5, which reads as
  "perfectly typical" and is a statement about nothing.
* ``test_untrusted_metrics_are_marked_not_dropped`` — Iowa's regime. Dropping
  hides a disagreement; reporting unmarked publishes a number CRITERIA.md
  section 5.1 says is unreliable.
* ``test_ties_do_not_read_as_extreme`` — the discrete metrics. ``p_below``
  alone calls a plan on the modal value extreme-low and ``p_at_or_below`` calls
  the same plan extreme-high.

The Iowa section at the end pins the regimes against the real enacted plan and
the real 2020 election. Its ensembles are **synthetic** and labelled as such:
they exist to drive the plumbing, and no test there asserts anything about where
Iowa's enacted plan actually sits relative to a neutral ensemble, because
nothing in this repository has drawn one at test time.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import pytest

from detect import confusion as C
from detect import outlier as O

PROCESSED = Path("data/processed")
HAVE_IOWA = (PROCESSED / "ia_units.csv").exists() and (
    PROCESSED / "ia_elections.csv"
).exists()
iowa = pytest.mark.skipif(not HAVE_IOWA, reason="data/processed not built")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def one(metric: str, value, ensemble, **kwargs) -> O.Location:
    """Locate a single metric. Keyword arguments go to :func:`outlier.locate`."""
    return O.locate(None, {metric: list(ensemble)}, {metric: value}, **kwargs)[metric]


def located(
    metric: str,
    percentile: float,
    *,
    trusted: bool | None = None,
    n: int = 1000,
    value: float = 0.0,
) -> O.Location:
    """A hand-built LOCATED location, for decision-rule tests.

    Built directly rather than through ``locate`` so that the decision tests
    control the percentile exactly and depend on none of the percentile
    arithmetic; the arithmetic has its own tests above.
    """
    return O.Location(
        metric=metric,
        status=O.LOCATED,
        value=value,
        percentile=percentile,
        p_below=percentile,
        p_at_or_below=percentile,
        two_sided_p=min(1.0, 2 * min(percentile, 1 - percentile)),
        z=None,
        n=n,
        trusted=trusted,
    )


# --------------------------------------------------------------------------- #
# percentile arithmetic
# --------------------------------------------------------------------------- #

def test_percentile_z_and_tails_on_a_known_distribution():
    loc = one("m", 95, range(100))
    assert loc.status == O.LOCATED
    assert loc.n == 100
    assert loc.p_below == pytest.approx(0.95)
    assert loc.p_at_or_below == pytest.approx(0.96)
    assert loc.percentile == pytest.approx(0.955)      # 95 below + half of 1 tie
    assert loc.two_sided_p == pytest.approx(0.10)      # 2 * min(0.96, 0.05)
    assert loc.z == pytest.approx((95 - 49.5) / math.sqrt(833.25))
    assert loc.distribution is not None
    assert loc.distribution.median == pytest.approx(49.5)
    assert loc.distribution.n_distinct == 100


def test_a_plan_outside_the_ensemble_reaches_the_extremes():
    high = one("m", 1000, range(100))
    low = one("m", -1000, range(100))
    assert high.percentile == 1.0
    assert high.two_sided_p == 0.0
    assert low.percentile == 0.0
    assert low.two_sided_p == 0.0


def test_ties_do_not_read_as_extreme():
    """A plan sitting on the ensemble's modal value is typical, not extreme.

    The discrete metrics — cut edges, county splits, seat counts — tie
    constantly. Here 60 of 100 draws have the plan's exact value, so ``p_below``
    reports 0.20 (extreme-low) and ``p_at_or_below`` reports 0.80 (high), while
    the mid-rank percentile reports 0.50. Both one-sided readings are wrong
    about the same plan and the pair is reported so the reader can see it.
    """
    ensemble = [0] * 20 + [1] * 60 + [2] * 20
    loc = one("cut_edges", 1, ensemble)
    assert loc.p_below == pytest.approx(0.20)
    assert loc.p_at_or_below == pytest.approx(0.80)
    assert loc.percentile == pytest.approx(0.50)
    assert loc.two_sided_p == 1.0
    assert any("mid-rank" in r for r in loc.reasons)


def test_quantiles_match_the_linear_interpolation_convention():
    dist = O.summarize(list(range(1, 11)))       # 1..10
    assert dist.median == pytest.approx(5.5)
    assert dist.p25 == pytest.approx(3.25)
    assert dist.p75 == pytest.approx(7.75)
    assert dist.minimum == 1 and dist.maximum == 10


# --------------------------------------------------------------------------- #
# regime 1: an undefined metric is not a percentile
# --------------------------------------------------------------------------- #

def test_a_none_metric_is_not_a_percentile():
    """Declination is None when one party wins every seat (CRITERIA.md 5.1).

    The ensemble here is centred at 0.30, so the wrong implementation — ``None``
    coerced to 0.0 anywhere along the way — would report a percentile of 0.0,
    which under the default rule fires. The right answer is a status and no
    number.
    """
    ensemble = [0.30 + 0.01 * i for i in range(100)]
    loc = one("declination", None, ensemble)
    assert loc.status == O.VALUE_UNDEFINED
    assert loc.percentile is None
    assert loc.z is None
    assert loc.value is None
    assert any("undefined, not zero" in r for r in loc.reasons)

    # and the decision rule cannot fire on it
    decision = C.flag({"declination": loc})
    assert decision.flagged is False
    assert dict(decision.excluded)["declination"].startswith("no percentile")

    # the coercion this guards against would have fired
    coerced = one("declination", 0.0, ensemble)
    assert coerced.percentile == 0.0
    assert C.flag({"declination": coerced}, C.Rule(untrusted="include")).flagged


def test_undefined_ensemble_draws_are_dropped_and_counted():
    ensemble = [None] * 30 + list(range(70))
    loc = one("declination", 10, ensemble)
    assert loc.n == 70
    assert loc.distribution.n_undefined == 30
    assert loc.percentile == pytest.approx((10 + 0.5) / 70)
    assert any("not a random subset" in r for r in loc.reasons)


def test_an_all_none_ensemble_column_is_missing_not_empty():
    loc = one("declination", 0.1, [None] * 50)
    assert loc.status == O.MISSING_FROM_ENSEMBLE
    assert loc.percentile is None
    assert loc.n == 0


# --------------------------------------------------------------------------- #
# regime 2: a degenerate metric is not a percentile
# --------------------------------------------------------------------------- #

def test_a_point_mass_ensemble_gets_no_percentile():
    """County splits at county units: identically 0 for every plan that exists.

    A mid-rank percentile against a constant is 0.5, which reads as "perfectly
    typical". It is not a measurement of anything, and 0.5 is exactly the value
    a reader would take as reassurance.
    """
    loc = one("county_splits", 0, [0] * 100)
    assert loc.status == O.DEGENERATE
    assert loc.percentile is None
    assert loc.distribution.constant is True
    assert any("point mass" in r for r in loc.reasons)


def test_a_caller_flagged_degeneracy_outranks_a_varying_sample():
    """A structural constant stays degenerate even if the sample seems to vary.

    ``evaluate.administrative`` asserts that no plan over these units can move
    the metric. An ensemble that appeared to move it would mean the ensemble is
    wrong, not the flag, so the flag wins and the reason is reported verbatim.
    """
    ctx = O.Context(degenerate={"county_splits": "units are their own subdivisions"})
    loc = one("county_splits", 3, range(100), context=ctx)
    assert loc.status == O.DEGENERATE
    assert loc.percentile is None
    assert loc.value == 3
    assert any("units are their own subdivisions" in r for r in loc.reasons)


def test_an_ensemble_below_min_n_gets_no_percentile():
    loc = one("m", 5, range(10))
    assert loc.status == O.INSUFFICIENT_ENSEMBLE
    assert loc.percentile is None
    assert loc.n == 10
    assert one("m", 5, range(10), min_n=5).status == O.LOCATED


# --------------------------------------------------------------------------- #
# regime 3: trust is marked, not applied silently
# --------------------------------------------------------------------------- #

def test_untrusted_metrics_are_marked_not_dropped():
    ctx = O.Context(
        trusted=frozenset({"efficiency_gap"}),
        trust_assessed=frozenset(
            {"efficiency_gap", "mean_median", "declination", "partisan_bias"}
        ),
    )
    locations = O.locate(
        None,
        {"efficiency_gap": list(range(100)), "mean_median": list(range(100))},
        {"efficiency_gap": 99, "mean_median": 99},
        context=ctx,
    )
    assert set(locations) == {"efficiency_gap", "mean_median"}     # not dropped
    assert locations["efficiency_gap"].trusted is True
    assert locations["mean_median"].trusted is False
    assert locations["mean_median"].percentile is not None         # not silenced
    assert any(
        "not trusted in this regime" in r for r in locations["mean_median"].reasons
    )


def test_trust_is_three_valued_and_scoped():
    """`not assessed` and `assessed and rejected` are different claims."""
    ctx = O.Context(
        trusted=frozenset({"efficiency_gap"}),
        trust_assessed=frozenset({"efficiency_gap", "mean_median"}),
    )
    locs = O.locate(
        None,
        {m: list(range(100)) for m in ("efficiency_gap", "mean_median", "polsby_popper")},
        {"efficiency_gap": 50, "mean_median": 50, "polsby_popper": 50},
        context=ctx,
    )
    assert locs["efficiency_gap"].trusted is True
    assert locs["mean_median"].trusted is False
    assert locs["polsby_popper"].trusted is None       # never examined


def test_context_merge_unions_both_sides():
    a = O.Context(trusted=frozenset({"x"}), trust_assessed=frozenset({"x", "y"}))
    b = O.Context(degenerate={"z": "constant"}, notes=("note",))
    merged = a.merge(b)
    assert merged.trust_of("x") is True
    assert merged.trust_of("y") is False
    assert merged.trust_of("z") is None
    assert merged.degenerate == {"z": "constant"}
    assert merged.notes == ("note",)


# --------------------------------------------------------------------------- #
# locate's bookkeeping
# --------------------------------------------------------------------------- #

def test_metrics_present_on_one_side_only_are_reported_not_dropped():
    locs = O.locate(
        None,
        {"a": list(range(100)), "b": list(range(100))},
        {"a": 5, "c": 5},
    )
    assert locs["a"].status == O.LOCATED
    assert locs["b"].status == O.MISSING_FROM_PLAN
    assert locs["c"].status == O.MISSING_FROM_ENSEMBLE


def test_non_numeric_values_are_reported_not_raised():
    locs = O.locate(
        None,
        {"splits_layer": ["district"] * 100, "flagged": [True] * 100},
        {"splits_layer": "district", "flagged": True},
    )
    assert locs["splits_layer"].status == O.NON_NUMERIC
    assert locs["flagged"].status == O.NON_NUMERIC       # bools are not numbers
    assert one("m", float("nan"), range(100)).status == O.NON_NUMERIC


def test_locate_accepts_rows_as_well_as_columns():
    rows = [{"a": i, "b": 2 * i} for i in range(100)]
    from_rows = O.locate(None, rows, {"a": 50, "b": 100})
    from_cols = O.locate(
        None,
        {"a": list(range(100)), "b": [2 * i for i in range(100)]},
        {"a": 50, "b": 100},
    )
    assert from_rows["a"].percentile == from_cols["a"].percentile
    assert from_rows["b"].percentile == from_cols["b"].percentile


def test_as_columns_pads_missing_keys_with_none():
    cols = O.as_columns([{"a": 1}, {"b": 2}, {"a": 3, "b": 4}])
    assert cols == {"a": [1, None, 3], "b": [None, 2, 4]}


def test_plan_digest_is_order_independent_and_label_sensitive():
    a = {"19001": 1, "19003": 2}
    b = {"19003": 2, "19001": 1}
    c = {"19001": 2, "19003": 1}
    assert O.plan_digest(a) == O.plan_digest(b)
    assert O.plan_digest(a) != O.plan_digest(c)
    assert O.plan_digest(None) is None
    loc = O.locate(a, {"m": list(range(100))}, {"m": 50})["m"]
    assert loc.plan_id == O.plan_digest(a)


def test_locate_returns_metrics_and_nothing_else():
    """No summary key, no score, no verdict — ARCHITECTURE.md section 6."""
    locs = O.locate(None, {"a": list(range(100))}, {"a": 1, "b": 2})
    assert set(locs) == {"a", "b"}
    banned = ("fairness", "score", "verdict", "overall", "combined")
    assert not [
        name
        for name in dir(O) + dir(C)
        if not name.startswith("_") and any(b in name.lower() for b in banned)
    ]


def test_percentiles_view_keeps_unlocatable_metrics_as_none():
    locs = O.locate(
        None, {"a": list(range(100)), "b": [7] * 100}, {"a": 50, "b": 7, "c": 1}
    )
    assert O.percentiles(locs) == {
        "a": pytest.approx(0.505),
        "b": None,
        "c": None,
    }
    statuses = O.by_status(locs)
    assert statuses[O.LOCATED] == ("a",)
    assert statuses[O.DEGENERATE] == ("b",)
    assert len(O.summary_lines(locs)) == 3


# --------------------------------------------------------------------------- #
# the rule itself
# --------------------------------------------------------------------------- #

def test_the_rule_is_a_printable_parameter():
    rule = C.Rule(threshold=0.98, tail="upper", combination="k_of_n", k=2, name="r")
    text = rule.describe()
    assert "0.98" in text and "at least 2" in text and "r:" in text
    assert rule.as_dict()["threshold"] == 0.98
    assert rule.as_dict()["describe"] == text
    assert C.DEFAULT_RULE.threshold == 0.99
    assert C.DEFAULT_RULE.tail == "two_sided"
    assert C.DEFAULT_RULE.combination == "any"
    assert C.DEFAULT_RULE.untrusted == "exclude"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"threshold": 1.5},
        {"threshold": -0.1},
        {"tail": "sideways"},
        {"combination": "vibes"},
        {"untrusted": "ignore"},
        {"k": 0},
        {"combination": "named"},                       # needs exactly one metric
        {"combination": "named", "metrics": ("a", "b")},
    ],
)
def test_bad_rules_raise(kwargs):
    with pytest.raises(ValueError):
        C.Rule(**kwargs)


def test_nominal_fpr_is_why_the_default_threshold_is_not_095():
    loose = C.Rule(threshold=0.95)
    assert loose.nominal_fpr(4) == pytest.approx(1 - 0.9 ** 4)      # 0.3439
    assert C.DEFAULT_RULE.nominal_fpr(4) == pytest.approx(1 - 0.98 ** 4)
    assert C.DEFAULT_RULE.nominal_fpr(1) == pytest.approx(0.02)
    assert C.NEVER_FLAG.nominal_fpr(10) == 0.0


# --------------------------------------------------------------------------- #
# flag()
# --------------------------------------------------------------------------- #

def test_flag_fires_on_either_tail_by_default():
    assert C.flag({"m": located("m", 0.995)}).flagged is True
    assert C.flag({"m": located("m", 0.005)}).flagged is True
    assert C.flag({"m": located("m", 0.50)}).flagged is False
    assert C.flag({"m": located("m", 0.98)}).flagged is False


def test_one_sided_rules_ignore_the_other_tail():
    upper = C.Rule(tail="upper")
    lower = C.Rule(tail="lower")
    assert C.flag({"m": located("m", 0.995)}, upper).flagged is True
    assert C.flag({"m": located("m", 0.005)}, upper).flagged is False
    assert C.flag({"m": located("m", 0.005)}, lower).flagged is True
    assert C.flag({"m": located("m", 0.995)}, lower).flagged is False


def test_the_firing_side_is_reported():
    high = C.flag({"m": located("m", 0.999)})
    low = C.flag({"m": located("m", 0.001)})
    assert high.fired[0].side == "high"
    assert low.fired[0].side == "low"
    assert "0.9990" in high.reason


def test_combination_rules_differ_on_the_same_locations():
    locations = {
        "a": located("a", 0.999),
        "b": located("b", 0.500),
        "c": located("c", 0.500),
    }
    assert C.flag(locations, C.Rule(combination="any")).flagged is True
    assert C.flag(locations, C.Rule(combination="all")).flagged is False
    assert C.flag(locations, C.Rule(combination="k_of_n", k=2)).flagged is False
    assert C.flag(locations, C.Rule(combination="k_of_n", k=1)).flagged is True
    named_a = C.Rule(combination="named", metrics=("a",))
    named_b = C.Rule(combination="named", metrics=("b",))
    assert C.flag(locations, named_a).flagged is True
    assert C.flag(locations, named_b).flagged is False


def test_all_does_not_flag_vacuously_when_nothing_is_eligible():
    """"Every eligible metric fired" must not be true of no metrics at all."""
    locations = {"a": O.Location(metric="a", status=O.DEGENERATE)}
    decision = C.flag(locations, C.Rule(combination="all"))
    assert decision.flagged is False
    assert decision.eligible == ()
    assert "no metric was eligible" in decision.reason


def test_untrusted_metrics_are_excluded_by_default_and_includable_by_parameter():
    locations = {"mean_median": located("mean_median", 0.999, trusted=False)}
    default = C.flag(locations)
    assert default.flagged is False
    assert "not trusted" in dict(default.excluded)["mean_median"]
    permissive = C.flag(locations, C.Rule(untrusted="include"))
    assert permissive.flagged is True
    assert permissive.fired[0].trusted is False        # still marked when it fires


def test_unlocatable_metrics_are_excluded_with_reasons_never_scored_as_typical():
    locations = {
        "efficiency_gap": located("efficiency_gap", 0.50, trusted=True),
        "declination": O.Location(metric="declination", status=O.VALUE_UNDEFINED),
        "county_splits": O.Location(metric="county_splits", status=O.DEGENERATE),
    }
    decision = C.flag(locations)
    assert decision.flagged is False
    assert decision.eligible == ("efficiency_gap",)
    assert set(dict(decision.excluded)) == {"declination", "county_splits"}
    assert decision.as_dict()["excluded"]["declination"].startswith("no percentile")


def test_a_thin_ensemble_cannot_fire():
    locations = {"m": located("m", 0.999, n=5)}
    assert C.flag(locations).flagged is False
    assert C.flag(locations, C.Rule(min_n=1)).flagged is True


def test_every_decision_carries_its_rule():
    decision = C.flag({"m": located("m", 0.999)}, C.Rule(name="named-rule"))
    assert decision.rule.name == "named-rule"
    assert "named-rule" in decision.as_dict()["rule"]["describe"]


# --------------------------------------------------------------------------- #
# scenarios and labels
# --------------------------------------------------------------------------- #

def scenario(
    ident: str,
    kind: str,
    percentile: float,
    *,
    shift: int = 0,
    realized: int | None = None,
    party: str | None = None,
) -> C.Scenario:
    """One labelled case whose single trusted metric sits at ``percentile``."""
    return C.Scenario(
        id=ident,
        kind=kind,
        intended_seat_shift=shift,
        realized_seat_shift=realized,
        target_party=party,
        locations={
            "efficiency_gap": located("efficiency_gap", percentile, trusted=True),
            "mean_median": located("mean_median", percentile, trusted=False),
            "declination": O.Location(metric="declination", status=O.VALUE_UNDEFINED),
        },
    )


def calibrated_scenarios() -> list[C.Scenario]:
    """20 planted plans across three magnitudes, plus 20 nulls.

    The planted plans sit further into the tail the larger the intended shift;
    the 1-seat plants sit at 0.97, inside the default 0.99 threshold, so this
    set has a genuine detection floor rather than a detector that sees
    everything. Expected under the default rule: TPR 0/6 at one seat, 7/7 at
    two, 7/7 at three, FPR 0/20.
    """
    planted = (
        [scenario(f"g1_{i}", "planted", 0.970, shift=1, party="R") for i in range(6)]
        + [scenario(f"g2_{i}", "planted", 0.9995, shift=2, party="R") for i in range(7)]
        + [scenario(f"g3_{i}", "planted", 0.9999, shift=-3, party="D") for i in range(7)]
    )
    nulls = [
        scenario(f"n_{i}", "null", 0.30 + 0.02 * i, realized=i % 2)
        for i in range(20)
    ]
    return planted + nulls


def test_a_null_with_a_nonzero_intended_shift_is_a_mislabelled_scenario():
    with pytest.raises(ValueError, match="intended_seat_shift 0 by definition"):
        C.Scenario(id="x", kind="null", locations={}, intended_seat_shift=2)


def test_a_planted_scenario_with_no_intended_shift_has_nothing_to_detect():
    with pytest.raises(ValueError, match="no ground truth"):
        C.Scenario(id="x", kind="planted", locations={}, intended_seat_shift=0)


def test_ground_truth_is_intent_not_realized_shift():
    """A null that moved a seat from geography alone is still a null.

    CRITERIA.md section 5.4 and ARCHITECTURE.md section 5's own example. If the
    realized shift were the label, this null would be counted as a planted plan
    the detector missed, and the false-positive gate would be measuring the
    wrong thing.
    """
    null_that_moved = scenario("n", "null", 0.30, realized=1)
    planted_that_did_not = scenario("g", "planted", 0.999, shift=2, realized=0)
    assert null_that_moved.is_positive is False
    assert planted_that_did_not.is_positive is True
    matrix = C.confusion_matrix([null_that_moved, planted_that_did_not])
    assert matrix["tp"] == 1 and matrix["tn"] == 1
    assert matrix["fp"] == 0 and matrix["fn"] == 0
    rows = {r["id"]: r for r in matrix["scenarios"]}
    assert rows["n"]["realized_seat_shift"] == 1          # reported, not used
    assert rows["n"]["truth"] == "null"


def test_duplicate_scenario_ids_raise():
    a = scenario("same", "null", 0.5)
    b = scenario("same", "null", 0.5)
    with pytest.raises(ValueError, match="duplicate scenario id"):
        C.confusion_matrix([a, b])


def test_scenarios_may_be_plain_mappings():
    as_dict = {
        "id": "g",
        "kind": "planted",
        "intended_seat_shift": 2,
        "locations": {"efficiency_gap": located("efficiency_gap", 0.999, trusted=True)},
    }
    assert C.as_scenario(as_dict).is_positive is True
    with pytest.raises(ValueError, match="unknown keys"):
        C.as_scenario(dict(as_dict, flagged=True))


# --------------------------------------------------------------------------- #
# the confusion matrix and the gates
# --------------------------------------------------------------------------- #

def test_the_confusion_matrix_counts_are_exact():
    matrix = C.confusion_matrix(calibrated_scenarios())
    assert matrix["n_positive"] == 20 and matrix["n_null"] == 20
    assert matrix["tp"] == 14 and matrix["fn"] == 6      # the six 1-seat plants
    assert matrix["fp"] == 0 and matrix["tn"] == 20
    assert matrix["tpr"] == pytest.approx(0.70)
    assert matrix["fpr"] == pytest.approx(0.0)
    assert matrix["tnr"] == pytest.approx(1.0)
    assert matrix["fnr"] == pytest.approx(0.30)
    assert matrix["fired_on_positives"] == {"efficiency_gap": 14}
    assert matrix["fired_on_nulls"] == {}


def test_no_single_accuracy_number_is_reported():
    """CRITERIA.md section 11 failure mode 1, in the detector's own output.

    On this scenario set — 20 planted, 60 nulls — flag-nothing posts an accuracy
    of 0.75 and flag-everything 0.25; neither is a detector. The matrix is the
    output.
    """
    scenarios = calibrated_scenarios() + [
        scenario(f"extra_{i}", "null", 0.5) for i in range(40)
    ]
    matrix = C.confusion_matrix(scenarios, C.NEVER_FLAG)
    assert (matrix["tn"] + matrix["tp"]) / matrix["n"] == pytest.approx(0.75)
    for banned in ("accuracy", "f1", "score", "skill", "auc"):
        assert banned not in matrix
    assert matrix["tpr"] == 0.0 and matrix["fpr"] == 0.0


def test_a_calibrated_detector_passes_both_gates():
    gates = C.gates(calibrated_scenarios())
    assert gates["tpr_at_2seat"]["value"] == pytest.approx(1.0)
    assert gates["tpr_at_2seat"]["pass"] is True
    assert gates["fpr_on_nulls"]["value"] == pytest.approx(0.0)
    assert gates["fpr_on_nulls"]["pass"] is True
    assert gates["min_detectable_seat_shift"]["value"] == 2
    assert gates["min_detectable_seat_shift"]["gated"] is False


def test_always_flag_detector_fails_the_fpr_gate():
    """A detector that flags everything scores a perfect TPR and is worthless.

    CRITERIA.md section 8: "null cases are as important as positive cases". The
    TPR gate alone passes this detector; the FPR gate is what rejects it.
    """
    gates = C.gates(calibrated_scenarios(), C.ALWAYS_FLAG)
    assert gates["tpr_at_2seat"]["value"] == pytest.approx(1.0)
    assert gates["tpr_at_2seat"]["pass"] is True         # passes on TPR alone
    assert gates["fpr_on_nulls"]["value"] == pytest.approx(1.0)
    assert gates["fpr_on_nulls"]["pass"] is False        # and is rejected here
    matrix = C.confusion_matrix(calibrated_scenarios(), C.ALWAYS_FLAG)
    assert matrix["tn"] == 0 and matrix["fn"] == 0
    assert C.min_detectable_seat_shift(
        C.detection_curve(calibrated_scenarios(), C.ALWAYS_FLAG)
    ) == 1


def test_never_flag_detector_fails_the_tpr_gate():
    """The mirror image: a perfect FPR, and nothing detected."""
    gates = C.gates(calibrated_scenarios(), C.NEVER_FLAG)
    assert gates["fpr_on_nulls"]["value"] == pytest.approx(0.0)
    assert gates["fpr_on_nulls"]["pass"] is True         # passes on FPR alone
    assert gates["tpr_at_2seat"]["value"] == pytest.approx(0.0)
    assert gates["tpr_at_2seat"]["pass"] is False        # and is rejected here
    assert gates["min_detectable_seat_shift"]["value"] is None


def test_a_detector_cannot_flag_what_it_cannot_measure():
    """Even ALWAYS_FLAG needs one located metric; degeneracy is not evidence."""
    blind = C.Scenario(
        id="blind",
        kind="planted",
        intended_seat_shift=2,
        locations={
            "declination": O.Location(metric="declination", status=O.VALUE_UNDEFINED),
            "county_splits": O.Location(metric="county_splits", status=O.DEGENERATE),
        },
    )
    assert C.flag(blind.locations, C.ALWAYS_FLAG).flagged is False
    matrix = C.confusion_matrix([blind], C.ALWAYS_FLAG)
    assert matrix["fn"] == 1


def test_rates_over_an_empty_class_are_none_and_gate_pass_is_none():
    """A gate that could not be measured must not silently read as passed."""
    only_nulls = [scenario(f"n_{i}", "null", 0.5) for i in range(5)]
    matrix = C.confusion_matrix(only_nulls)
    assert matrix["tpr"] is None and matrix["tpr_ci95"] is None
    gates = C.gates(only_nulls)
    assert gates["tpr_at_2seat"]["value"] is None
    assert gates["tpr_at_2seat"]["pass"] is None
    assert not gates["tpr_at_2seat"]["pass"]             # falsy: conservative
    assert "no planted scenarios" in gates["tpr_at_2seat"]["note"]


def test_wilson_interval_shows_what_a_small_scenario_set_cannot_prove():
    low, high = C.wilson_interval(20, 20)
    assert high == pytest.approx(1.0, abs=1e-9)
    assert low < 0.95                       # 20/20 does not establish TPR >= 0.95
    assert C.wilson_interval(0, 0) is None
    lo2, hi2 = C.wilson_interval(1, 2)
    assert lo2 < 0.5 < hi2


# --------------------------------------------------------------------------- #
# the detection curve
# --------------------------------------------------------------------------- #

def test_the_detection_curve_is_per_intended_magnitude():
    curve = C.detection_curve(calibrated_scenarios())
    assert [row["seats"] for row in curve] == [1, 2, 3]
    assert curve[0]["tpr"] == pytest.approx(0.0) and curve[0]["n"] == 6
    assert curve[1]["tpr"] == pytest.approx(1.0) and curve[1]["n"] == 7
    assert curve[2]["tpr"] == pytest.approx(1.0) and curve[2]["n"] == 7
    assert curve[2]["by_direction"]["D"] == 7        # signed shifts share a bucket
    assert C.tpr_at(curve, 2) == pytest.approx(1.0)
    assert C.tpr_at(curve, 9) is None
    assert all("rule" in row for row in curve)


def test_the_curve_buckets_on_intended_not_realized_shift():
    scenarios = [
        scenario(f"g_{i}", "planted", 0.999, shift=2, realized=1) for i in range(4)
    ]
    curve = C.detection_curve(scenarios)
    assert [row["seats"] for row in curve] == [2]
    assert curve[0]["realized_seat_shifts"] == [1, 1, 1, 1]


def test_min_detectable_seat_shift_requires_the_larger_shifts_to_hold():
    """One lucky small bucket must not publish a minimum the curve contradicts."""
    curve = [
        {"seats": 1, "tpr": 1.00},
        {"seats": 2, "tpr": 0.90},
        {"seats": 3, "tpr": 0.99},
    ]
    assert C.min_detectable_seat_shift(curve) == 3
    assert C.min_detectable_seat_shift(curve, require_monotone=False) == 1
    assert C.min_detectable_seat_shift([{"seats": 1, "tpr": 0.10}]) is None
    assert C.min_detectable_seat_shift([]) is None
    assert C.min_detectable_seat_shift(curve, target_tpr=0.85) == 1


def test_report_lines_show_both_rates_and_the_rule():
    scenarios = calibrated_scenarios()
    lines = C.report_lines(
        C.confusion_matrix(scenarios), C.detection_curve(scenarios)
    )
    text = "\n".join(lines)
    assert "TPR" in text and "FPR" in text
    assert "reported, not gated" in text
    assert C.DEFAULT_RULE.describe() in text


# --------------------------------------------------------------------------- #
# Iowa — the real regimes, on synthetic ensembles
# --------------------------------------------------------------------------- #

def iowa_inputs():
    from evaluate import elections, plan as planmod

    enacted = planmod.load_plan(PROCESSED / "ia_enacted_cd118.csv")
    dem, rep = elections.two_party(elections.load_elections())
    return enacted, dem, rep


def synthetic_partisan_ensemble(n: int = 200) -> dict[str, list[float | None]]:
    """A stand-in ensemble, deterministic and **not** a neutral baseline.

    No test asserts where Iowa's enacted plan sits relative to this; drawing a
    real ensemble is ``generate``'s job and the bench's, and a percentile
    against made-up draws is not a finding. It exists so the plumbing runs on
    the real metric values and the real regime flags.
    """
    rng = random.Random(20260818)
    return {
        "efficiency_gap": [rng.gauss(0.0, 0.05) for _ in range(n)],
        "mean_median": [rng.gauss(0.0, 0.02) for _ in range(n)],
        "declination": [rng.gauss(0.0, 0.30) for _ in range(n)],
        "partisan_bias": [rng.gauss(0.0, 0.10) for _ in range(n)],
    }


@iowa
def test_iowa_enacted_plan_has_an_undefined_declination():
    from evaluate import partisan

    enacted, dem, rep = iowa_inputs()
    metrics = partisan.all_metrics(enacted, dem, rep)
    assert metrics["rep_seats"] == 4 and metrics["dem_seats"] == 0
    assert metrics["declination"] is None

    locations = O.locate(
        enacted,
        synthetic_partisan_ensemble(),
        metrics,
        context=O.election_context(enacted, dem, rep),
    )
    assert locations["declination"].status == O.VALUE_UNDEFINED
    assert locations["declination"].percentile is None


@iowa
def test_iowa_leaves_exactly_one_trusted_partisan_metric():
    from evaluate import partisan

    enacted, dem, rep = iowa_inputs()
    ctx = O.election_context(enacted, dem, rep)
    assert ctx.trusted == frozenset({"efficiency_gap"})
    assert ctx.trust_assessed == frozenset(partisan.METRICS)
    assert ctx.notes                                   # caveats came through

    locations = O.locate(
        enacted,
        synthetic_partisan_ensemble(),
        partisan.all_metrics(enacted, dem, rep),
        context=ctx,
    )
    assert locations["efficiency_gap"].trusted is True
    assert locations["mean_median"].trusted is False
    assert locations["mean_median"].percentile is not None      # marked, not dropped

    decision = C.flag(locations)
    assert decision.eligible == ("efficiency_gap",)
    assert "mean_median" in dict(decision.excluded)
    assert "declination" in dict(decision.excluded)


@iowa
def test_iowa_administrative_metrics_are_degenerate_not_typical():
    from evaluate import administrative, plan as planmod

    enacted, _, _ = iowa_inputs()
    units = planmod.load_units()
    ctx = O.administrative_context(enacted, units)
    assert "county_splits" in ctx.degenerate

    metrics = administrative.all_metrics(enacted, units)
    assert metrics["county_splits"] == 0
    # a varying stand-in ensemble is still refused: the flag is structural
    locations = O.locate(
        enacted,
        {"county_splits": list(range(100))},
        {"county_splits": metrics["county_splits"]},
        context=ctx,
    )
    assert locations["county_splits"].status == O.DEGENERATE
    assert locations["county_splits"].percentile is None
    assert C.flag(locations).flagged is False


def test_summary_lines_survive_a_location_without_a_distribution():
    """Hand-built locations (and any future serialized round trip) still render."""
    lines = O.summary_lines(
        {
            "efficiency_gap": located("efficiency_gap", 0.99, trusted=True),
            "mean_median": located("mean_median", 0.99, trusted=False),
            "declination": O.Location(metric="declination", status=O.VALUE_UNDEFINED),
        }
    )
    assert len(lines) == 3
    assert "no distribution summary" in lines[0]
    assert "UNTRUSTED" in lines[1] and "UNTRUSTED" not in lines[0]
    assert O.VALUE_UNDEFINED in lines[2]
