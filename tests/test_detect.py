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

from dataguard import PROCESSED, have, requires   # noqa: F401

HAVE_IOWA = have("ia_units.csv", "ia_elections.csv")
iowa = requires("ia_units.csv", "ia_elections.csv")


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
    distinct: int | None = None,
    ess: float | None = None,
) -> O.Location:
    """A hand-built LOCATED location, for decision-rule tests.

    Built directly rather than through ``locate`` so that the decision tests
    control the percentile exactly and depend on none of the percentile
    arithmetic; the arithmetic has its own tests above.

    The resolution block defaults to ``n`` distinct draws with no repeats — the
    best case an ``n``-draw reference can be — so that a decision test which
    says nothing about resolution is testing the decision. Tests that care pass
    ``distinct`` or ``ess`` explicitly. Nothing here defaults to "unknown",
    because ``Rule.resolvable`` refuses an unknown and every decision test would
    then be a resolution test.
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
        n_distinct=n if distinct is None else distinct,
        ess=float(n) if ess is None else float(ess),
        ess_basis="values",
        max_interior_percentile=(n - 0.5) / n,
        min_interior_percentile=0.5 / n,
        outside_support=False,
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

    # and the decision rule cannot fire on it — and does not answer "not
    # flagged" either, because it read nothing
    decision = C.flag({"declination": loc})
    assert decision.flagged is None
    assert decision.resolved is False
    assert "not a finding that the plan is typical" in decision.reason
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
    """"Every eligible metric fired" must not be true of no metrics at all.

    And the answer is an abstention, not a clean bill of health: round 2
    returned False here, so a plan the detector could not look at was counted a
    correct rejection.
    """
    locations = {"a": O.Location(metric="a", status=O.DEGENERATE)}
    decision = C.flag(locations, C.Rule(combination="all"))
    assert decision.flagged is None
    assert decision.resolved is False
    assert decision.eligible == ()
    assert "UNRESOLVED" in decision.reason
    assert not decision.flagged                 # still falsy: conservative


def test_never_flag_still_answers_false_when_nothing_is_eligible():
    """The one exception, and it has to be: a control that abstains is no floor."""
    locations = {"a": O.Location(metric="a", status=O.DEGENERATE)}
    assert C.flag(locations, C.NEVER_FLAG).flagged is False


def test_untrusted_metrics_are_excluded_by_default_and_includable_by_parameter():
    locations = {"mean_median": located("mean_median", 0.999, trusted=False)}
    default = C.flag(locations)
    assert default.flagged is None            # excluded, so nothing was read
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
    """Five draws cannot express a 0.99 threshold, and lowering min_n does not help.

    Finding 1 of the round-2 critique in one test. ``min_n`` counts draws; the
    question is whether the reference can express the threshold, and at n=5 the
    largest interior percentile is 4.5/5 = 0.9. Setting ``min_n=1`` used to make
    the rule fire — on a plan whose 0.999 could only have come from sitting
    outside the observed support.
    """
    locations = {"m": located("m", 0.999, n=5)}
    assert C.flag(locations).flagged is None
    permissive = C.flag(locations, C.Rule(min_n=1))
    assert permissive.flagged is None
    why = dict(permissive.unresolvable)["m"]
    assert "cannot express threshold 0.99" in why
    assert "needs at least 50 draws" in why
    # a threshold the reference *can* express is answered normally
    assert C.flag(locations, C.Rule(threshold=0.8, min_n=1)).flagged is True


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


def test_no_accuracy_or_f1_but_the_two_numbers_a_constant_cannot_tie():
    """CRITERIA.md section 11 failure mode 1, and the round-3 amendment to it.

    On this scenario set — 20 planted, 60 nulls — flag-nothing posts an accuracy
    of 0.75 and flag-everything 0.25; neither is a detector, which is why
    accuracy and F1 stay banned. AUC and Youden J are the opposite case: both
    constants score exactly at their floor, so a summary built from them cannot
    report a constant as a working detector. That is the whole reason they were
    added, and the reason they are reported *beside* the counts and never
    instead of them.
    """
    scenarios = calibrated_scenarios() + [
        scenario(f"extra_{i}", "null", 0.5) for i in range(40)
    ]
    matrix = C.confusion_matrix(scenarios, C.NEVER_FLAG)
    assert (matrix["tn"] + matrix["tp"]) / matrix["n"] == pytest.approx(0.75)
    for banned in ("accuracy", "f1", "balanced_accuracy", "fairness_score"):
        assert banned not in matrix
    assert matrix["tpr"] == 0.0 and matrix["fpr"] == 0.0

    # never-flag reads nothing, so it induces no ranking and gets no AUC
    assert matrix["auc"]["value"] is None
    assert matrix["youden_j"] == 0.0

    # and the working rule is scored against both constants, in the matrix
    good = C.confusion_matrix(scenarios)
    assert set(good["baselines"]) == {"always-flag", "never-flag"}
    assert good["baselines"]["always-flag"]["youden_j"] == 0.0
    assert good["baselines"]["never-flag"]["youden_j"] == 0.0
    assert good["youden_j"] > 0.0
    assert good["auc"]["value"] > 0.5
    assert good["beats_baselines"]["verdict"] is True


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
    assert C.flag(blind.locations, C.ALWAYS_FLAG).flagged is None
    matrix = C.confusion_matrix([blind], C.ALWAYS_FLAG)
    assert matrix["fn"] == 0                    # not a miss — nothing was read
    assert matrix["unresolved_positive"] == 1
    assert matrix["tpr"] is None                # no positive was resolved
    assert matrix["tpr_bounds"]["lower"] == 0.0
    assert matrix["tpr_bounds"]["upper"] == 1.0


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
    assert C.flag(locations).flagged is None


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


# --------------------------------------------------------------------------- #
# the percentile floor — round-2 finding 1
# --------------------------------------------------------------------------- #

def test_the_largest_interior_percentile_is_arithmetic_not_a_preference():
    """(n - 0.5)/n, and at n=28 that is below a 0.99 threshold.

    The exact statement round 1 violated. ``required_n`` is the inverse: 50
    draws at t=0.99, 10 at t=0.95, and no finite reference at t=1.0.
    """
    assert O.required_n(0.99) == 50
    assert O.required_n(0.95) == 10
    assert O.required_n(1.0) is None
    assert O.required_n(0.0) == 1               # ALWAYS_FLAG asks nothing

    unique = O.locate(None, {"m": list(range(28))}, {"m": 27.0})["m"]
    assert unique.max_interior_percentile == pytest.approx(27.5 / 28)
    assert unique.max_interior_percentile < 0.99


def test_a_reference_that_cannot_express_the_threshold_is_refused_not_answered():
    """Round 1's regime: 28 draws over 14 distinct plans, a 0.99 rule.

    The plan sits 0.0005 outside a support pinched shut by 14 distinct values —
    the shape of two of round 1's six false positives. The old rule returned
    ``flagged=True`` with percentile 1.0. The fix is an abstention naming the
    arithmetic, not a smaller number.
    """
    ensemble = [float(i % 14) for i in range(28)]         # 28 draws, 14 plans
    loc = O.locate(None, {"m": ensemble}, {"m": 13.0005})["m"]
    assert loc.percentile == 1.0                          # outside the support
    assert loc.outside_support is True
    assert loc.max_interior_percentile == pytest.approx(1 - 1.0 / 28)

    decision = C.flag({"m": loc})
    assert decision.flagged is None
    why = dict(decision.unresolvable)["m"]
    assert "degenerates into 'outside the observed support'" in why
    assert "needs at least 50 draws" in why


def test_min_n_counts_draws_and_ess_counts_what_they_are_worth():
    """Round-2 finding 2: 806 draws, 177 distinct plans, ESS 11.7.

    ``Rule.min_n=20`` is satisfied by all three of those numbers, which is the
    complaint. The reference is built to reproduce the measured figures: one
    plan repeated 630 times and 176 others once each.
    """
    ids = (
        ["dup"] * 234                                     # one plan, 234 times
        + [f"a{i}" for i in range(44) for _ in range(4)]  # 44 plans, 4 times
        + [f"b{i}" for i in range(132) for _ in range(3)] # 132 plans, 3 times
    )
    assert len(ids) == 806 and len(set(ids)) == 177
    # distinct values, so the expressibility and distinct-plan checks both pass
    # and the effective sample size is the one thing that fails
    values = [0.001 * i for i in range(806)]
    loc = O.locate(
        None, {"m": values}, {"m": 0.5}, ensemble_plan_ids=ids
    )["m"]

    counts = [234] + [4] * 44 + [3] * 132
    assert loc.n == 806                                   # passes min_n=20
    assert loc.n_distinct_plans == 177
    assert loc.ess == pytest.approx(
        sum(counts) ** 2 / sum(m * m for m in counts), rel=1e-9
    )
    assert 11.0 < loc.ess < 12.0                          # round 2 measured 11.7
    assert loc.ess_basis == "plans"

    decision = C.flag({"m": loc})
    assert decision.flagged is None
    why = dict(decision.unresolvable)["m"]
    assert "effective sample size" in why and "needs at least 50" in why


def test_kish_ess_is_a_duplication_count_at_both_extremes():
    assert O.kish_ess([1] * 40) == pytest.approx(40.0)     # no repeats
    assert O.kish_ess([40]) == pytest.approx(1.0)          # one plan, 40 times
    assert O.kish_ess([]) == 0.0
    assert O.kish_ess([2, 2]) == pytest.approx(2.0)


def test_plan_ids_give_the_exact_distinct_count_and_values_the_conservative_one():
    """Two distinct plans sharing a value lower the value-basis ESS, never raise it."""
    values = [0.0, 0.0, 1.0, 2.0]
    ids = ["a", "b", "c", "d"]                             # four distinct plans
    with_ids = O.locate(None, {"m": values}, {"m": 1.0}, ensemble_plan_ids=ids)["m"]
    without = O.locate(None, {"m": values}, {"m": 1.0})["m"]
    assert with_ids.n_distinct_plans == 4
    assert with_ids.n_distinct_reference == 4
    assert without.n_distinct_plans is None
    assert without.n_distinct_reference == 3               # distinct values
    assert without.ess < with_ids.ess                      # conservative


def test_mismatched_plan_ids_raise_rather_than_misalign():
    with pytest.raises(ValueError, match="ensemble_plan_ids has 2 entries"):
        O.locate(None, {"m": [1.0, 2.0, 3.0]}, {"m": 1.0}, ensemble_plan_ids=["a", "b"])


def test_the_resolution_travels_with_every_location():
    loc = O.locate(None, {"m": [float(i) for i in range(60)]}, {"m": 30.0})["m"]
    block = loc.as_dict()["resolution"]
    assert block["n"] == 60 and block["n_distinct_values"] == 60
    assert block["ess"] == pytest.approx(60.0)
    assert block["max_interior_percentile"] == pytest.approx(59.5 / 60)
    assert any("reference resolution" in r for r in loc.reasons)


def test_rule_resolution_requirements_are_derived_from_the_threshold():
    """Not constants. A fixed floor here would be one more dial pointed at a gate."""
    strict = C.Rule(threshold=0.99)
    loose = C.Rule(threshold=0.95)
    assert strict.required_n == 50 and strict.required_distinct == 50
    assert strict.required_ess == 50.0
    assert loose.required_n == 10 and loose.required_ess == 10.0
    assert C.NEVER_FLAG.required_n == 0
    assert C.ALWAYS_FLAG.required_n == 1                   # controls stay usable
    assert "50" in strict.describe()
    override = C.Rule(threshold=0.99, min_distinct=4, min_ess=4)
    assert override.required_distinct == 4 and override.required_ess == 4.0
    assert override.as_dict()["resolution_requirement"]["required_n"] == 50


# --------------------------------------------------------------------------- #
# AUC and the constant detectors — round-2 finding 3
# --------------------------------------------------------------------------- #

def inverted_scenarios() -> list[C.Scenario]:
    """Two plants the rule ranks below two nulls. AUC 0.25 — round 2's number.

    ``outlierness`` is ``max(p, 1 - p)`` — the quantity the rule compares
    against its threshold — so percentiles 0.95 / 0.50 for the plants and
    0.75 / 0.975 for the nulls put exactly one of the four pairs the right way
    round.
    """
    return [
        scenario("g_a", "planted", 0.950, shift=2, party="R"),
        scenario("g_b", "planted", 0.500, shift=1, party="D"),
        scenario("n_a", "null", 0.750),
        scenario("n_b", "null", 0.975),
    ]


def test_auc_below_half_means_the_ranking_is_inverted():
    """The decisive round-2 number, now a first-class output."""
    block = C.auc(inverted_scenarios())
    assert block["value"] == pytest.approx(0.25)
    assert block["beats_coin_flip"] is False
    assert block["coin_flip"] == 0.5
    assert block["constant_baseline"] is None      # no such floor on this number
    assert block["n_pairs"] == 4
    assert "ranking is inverted" in block["note"]

    matrix = C.confusion_matrix(inverted_scenarios())
    assert matrix["auc"]["value"] == pytest.approx(0.25)
    assert matrix["beats_baselines"]["verdict"] is False
    assert matrix["beats_baselines"]["ranking"]["beats"] is False


def test_a_constant_detector_scores_exactly_the_auc_floor():
    """0.5, and it is the *decision* that is 0.5, not the statistic.

    Always-flag can see the same outlierness every rule can — on this set that
    statistic ranks perfectly — and discards all of it at a threshold of 0.0.
    So its statistic AUC is 1.0 and its decision AUC is exactly 0.5. The floor
    "beats both baselines" is measured against is the decision, which is why the
    baseline block reports that one.
    """
    scenarios = calibrated_scenarios()
    assert C.auc(scenarios, C.ALWAYS_FLAG)["value"] == pytest.approx(1.0)

    always = C.confusion_matrix(scenarios, C.ALWAYS_FLAG, with_baselines=False)
    assert always["auc"]["decision_auc"] == pytest.approx(0.5)
    assert always["youden_j"] == pytest.approx(0.0)

    never = C.confusion_matrix(scenarios, C.NEVER_FLAG, with_baselines=False)
    assert never["auc"]["decision_auc"] == pytest.approx(0.5)
    assert never["auc"]["value"] is None       # reads nothing, induces no ranking

    baselines = C.confusion_matrix(scenarios)["baselines"]
    assert baselines["always-flag"]["auc"] == pytest.approx(0.5)
    assert baselines["never-flag"]["auc"] == pytest.approx(0.5)
    assert baselines["always-flag"]["statistic_auc"] == pytest.approx(1.0)


def test_every_matrix_gate_block_and_report_line_carries_both_baselines():
    """Finding 3: round 2 buried these in diagnostics, where no gate saw them."""
    scenarios = calibrated_scenarios()
    matrix = C.confusion_matrix(scenarios)
    assert set(matrix["baselines"]) == {"always-flag", "never-flag"}
    assert matrix["baselines"]["always-flag"]["fpr"] == pytest.approx(1.0)
    assert matrix["baselines"]["always-flag"]["tpr"] == pytest.approx(1.0)
    assert matrix["baselines"]["never-flag"]["tpr"] == pytest.approx(0.0)

    gate_block = C.gates(scenarios)
    assert set(gate_block["baselines"]) == {"always-flag", "never-flag"}
    assert gate_block["beats_baselines"]["gated"] is False
    assert gate_block["auc"]["gated"] is False

    text = "\n".join(C.report_lines(matrix, C.detection_curve(scenarios)))
    assert "always-flag" in text and "never-flag" in text
    assert "AUC" in text and "Youden J" in text
    assert "does the rule beat both constant detectors? YES" in text


def test_a_rule_a_constant_ties_is_reported_as_not_beating_it():
    """The round-1 situation: the shipped rule and always-flag score alike."""
    scenarios = [
        scenario(f"g{i}", "planted", 0.9999, shift=2, party="R") for i in range(4)
    ] + [scenario(f"n{i}", "null", 0.9999) for i in range(4)]
    matrix = C.confusion_matrix(scenarios)
    assert matrix["tpr"] == pytest.approx(1.0) and matrix["fpr"] == pytest.approx(1.0)
    assert matrix["youden_j"] == pytest.approx(0.0)
    assert matrix["auc"]["value"] == pytest.approx(0.5)
    assert matrix["beats_baselines"]["verdict"] is False
    assert matrix["beats_baselines"]["operating_point"]["beats"] is False


# --------------------------------------------------------------------------- #
# abstention and the gates
# --------------------------------------------------------------------------- #

def thin(ident: str, kind: str, percentile: float, *, shift: int = 0) -> C.Scenario:
    """A scenario whose reference is five draws — too coarse for a 0.99 rule."""
    return C.Scenario(
        id=ident,
        kind=kind,
        intended_seat_shift=shift,
        locations={"efficiency_gap": located("efficiency_gap", percentile, n=5)},
    )


def test_abstaining_cannot_pass_a_gate():
    """A detector that declines to answer must not collect a clean FPR for it.

    Every case here is unresolvable, so the rule flags nothing. Reading the rate
    over resolved cases would report FPR 0/0 and the gate would go to ``None``;
    reading it over all nulls with abstentions as clean would report 0.00 and
    the gate would PASS. Both are wrong, and the second is how a broken detector
    ships. The gate reads the bound that is worst for the rule.
    """
    scenarios = [thin(f"g{i}", "planted", 0.999, shift=2) for i in range(4)]
    scenarios += [thin(f"n{i}", "null", 0.5) for i in range(10)]
    matrix = C.confusion_matrix(scenarios)
    assert (matrix["tp"], matrix["fp"], matrix["tn"], matrix["fn"]) == (0, 0, 0, 0)
    assert matrix["unresolved_positive"] == 4 and matrix["unresolved_null"] == 10
    assert matrix["coverage"] == 0.0
    assert matrix["fpr"] is None                       # nothing was measured

    gate_block = C.gates(scenarios)
    assert gate_block["fpr_on_nulls"]["value"] is None
    assert gate_block["fpr_on_nulls"]["bounds"]["upper"] == 1.0
    assert gate_block["fpr_on_nulls"]["pass"] is False
    assert gate_block["tpr_at_2seat"]["bounds"]["lower"] == 0.0
    assert gate_block["tpr_at_2seat"]["pass"] is False
    assert gate_block["coverage"]["value"] == 0.0


def test_an_abstention_is_not_a_true_negative_and_not_a_false_negative():
    scenarios = [thin("g", "planted", 0.999, shift=2), scenario("n", "null", 0.5)]
    matrix = C.confusion_matrix(scenarios)
    rows = {row["id"]: row for row in matrix["scenarios"]}
    assert rows["g"]["outcome"] == "unresolved_positive"
    assert rows["g"]["flagged"] is None and rows["g"]["resolved"] is False
    assert rows["n"]["outcome"] == "true_negative"
    assert matrix["fn"] == 0 and matrix["tn"] == 1


def test_a_bucket_the_rule_abstained_on_is_not_a_detected_magnitude():
    """min_detectable_seat_shift reads the worst case, so abstention cannot help."""
    curve = C.detection_curve(
        [thin(f"g{i}", "planted", 0.999, shift=2) for i in range(4)]
    )
    assert curve[0]["n"] == 4 and curve[0]["unresolved"] == 4
    assert curve[0]["tpr"] is None
    assert curve[0]["tpr_bounds"]["lower"] == 0.0
    assert C.min_detectable_seat_shift(curve) is None


# --------------------------------------------------------------------------- #
# no verdict on a real map — round-2 finding 4
# --------------------------------------------------------------------------- #

def review_locations() -> dict[str, O.Location]:
    return {
        "efficiency_gap": located(
            "efficiency_gap", 0.87, trusted=True, n=200, value=0.1234
        ),
        "mean_median": located("mean_median", 0.60, trusted=False, n=200, value=0.02),
        "declination": O.Location(metric="declination", status=O.VALUE_UNDEFINED),
        "county_splits": O.Location(metric="county_splits", status=O.DEGENERATE),
    }


def test_the_enacted_plan_gets_a_location_and_no_boolean():
    """README line 28 and CRITERIA.md 11: a verdict on a real map is a bug."""
    report = O.review_report(
        review_locations(),
        plan_id="ia_enacted_cd118",
        context=O.Context(
            trusted=frozenset({"efficiency_gap"}),
            trust_assessed=frozenset({"efficiency_gap", "mean_median", "declination"}),
        ),
    )
    flat = repr(sorted(report))
    assert "flagged" not in flat and "verdict" not in flat.replace("no_verdict", "")
    assert report["percentiles"]["efficiency_gap"] == pytest.approx(0.87)
    assert report["percentiles"]["declination"] is None
    assert report["trusted"]["trusted"] == ["efficiency_gap"]
    assert report["trusted"]["untrusted_marked_not_dropped"] == ["mean_median"]
    assert "county_splits" in report["trusted"]["not_assessed"]
    assert report["statuses"]["county_splits"] == O.DEGENERATE
    assert report["resolution"]["efficiency_gap"]["ess"] == 200.0
    assert "no flag, no score and no judgement" in report["no_verdict"]


def test_the_review_report_says_when_it_cannot_tell_two_plans_apart():
    """Iowa's enacted efficiency gap is bit-identical to a planted R-gerrymander's.

    Under a 4-0 sweep every Republican vote in a won district is surplus and
    every Democratic vote is lost, so the wasted-vote arithmetic barely depends
    on the lines. A percentile on that metric locates the value, not the plan,
    and the report has to say so rather than publishing the number alone.
    """
    report = O.review_report(
        review_locations(),
        comparators={"gerry_r_2seat": {"efficiency_gap": 0.1234, "mean_median": 0.09}},
    )
    assert report["indistinguishable"]["matches"] == {
        "efficiency_gap": ["gerry_r_2seat"]
    }
    assert any(
        "cannot distinguish them" in note for note in report["notes"]
    )
    assert any("locates the value, not the plan" in n for n in report["notes"])


def test_flag_refuses_a_plan_that_carries_no_ground_truth():
    """The boolean is only defined against a manufactured label."""
    decision = C.flag(review_locations(), for_scenario=False)
    assert decision.flagged is None
    assert "REFUSED" in decision.reason
    assert "review_report" in decision.reason
    assert decision.fired == ()


def test_an_inverted_ranking_settles_the_baseline_verdict_on_its_own():
    """Round 1: AUC 0.25 and no measurable operating point. Still a NO."""
    thin_positives = [thin(f"g{i}", "planted", 0.999, shift=2) for i in range(2)]
    scenarios = inverted_scenarios() + thin_positives
    matrix = C.confusion_matrix(scenarios)
    assert matrix["auc"]["value"] < 0.5
    assert matrix["beats_baselines"]["verdict"] is False


# --------------------------------------------------------------------------- #
# round-3 finding: `Rule.resolvable` ORed the two tails
# --------------------------------------------------------------------------- #

def one_tailed_reference() -> list[float]:
    """200 draws whose minimum is tied 8 times and whose maximum is unique.

    At ``t = 0.99`` the high tail is expressible (the largest interior mid-rank
    percentile is 1 - 0.5/200 = 0.9975 >= 0.99) and the low tail is not
    (the smallest is 0.5 * 8 / 200 = 0.02 > 0.01). A reference can be this
    lopsided for an ordinary reason: ReCom repeats plans, and repeats at one
    extreme of a column are not repeats at the other.
    """
    return [0.0] * 8 + [float(i) for i in range(1, 193)]


#: Only expressibility is under test in this section; the distinct-plan and ESS
#: floors have their own tests above and are satisfied here by construction.
EXPRESSIBILITY_ONLY = dict(min_distinct=1, min_ess=1.0)


def test_a_two_sided_rule_needs_both_tails_expressible():
    """The round-3 bug: one expressible tail declared the whole rule resolvable.

    The low-tail plan sits at mid-rank percentile 0.02, exactly the smallest the
    column can state, and 0.99 asks for 0.01. Before the fix ``resolvable``
    returned ``None`` because the *high* tail happened to reach 0.99, and the
    plan was answered ``flagged=False`` — a measurement the arithmetic could not
    make, on the tail the reference provably cannot express.
    """
    column = one_tailed_reference()
    low = O.locate(None, {"m": column}, {"m": 0.0})["m"]
    dist = low.distribution
    assert dist.max_interior_percentile == pytest.approx(1 - 0.5 / 200)   # 0.9975
    assert dist.min_interior_percentile == pytest.approx(0.02)
    assert dist.max_interior_percentile >= 0.99                          # high: yes
    assert dist.min_interior_percentile > 0.01                           # low:  no

    rule = C.Rule(threshold=0.99, **EXPRESSIBILITY_ONLY)
    assert rule.tail_expressibility(low) == {"high": True, "low": False}

    decision = C.flag({"m": low}, rule)
    assert decision.flagged is None                    # was False before the fix
    why = dict(decision.unresolvable)["m"]
    assert "low tail" in why and "'two_sided'" in why
    assert "[0.02, 0.9975]" in why                     # both attained bounds named
    assert "Rule(tail='upper')" in why                 # and the remedy named


def test_a_one_sided_rule_declared_in_advance_is_resolvable_on_the_live_tail():
    """The narrowing is available — to a caller, never to the reference.

    ``tail="upper"`` fires on the expressible tail and resolves; ``tail="lower"``
    asks for the dead one and abstains. Which of those a run uses is a logged
    rule parameter, not a property of the ensemble's tie multiplicities.
    """
    column = one_tailed_reference()
    high = O.locate(None, {"m": column}, {"m": 191.5})["m"]
    low = O.locate(None, {"m": column}, {"m": 0.0})["m"]

    upper = C.Rule(threshold=0.99, tail="upper", **EXPRESSIBILITY_ONLY)
    assert upper.fires_on == ("high",)
    assert upper.resolvable(high) is None
    assert C.flag({"m": high}, upper).flagged is True
    assert C.flag({"m": low}, upper).flagged is False       # read, and not extreme

    lower = C.Rule(threshold=0.99, tail="lower", **EXPRESSIBILITY_ONLY)
    assert lower.fires_on == ("low",)
    assert C.flag({"m": low}, lower).flagged is None
    assert "low tail" in dict(C.flag({"m": low}, lower).unresolvable)["m"]

    # and the rule that was actually shipped abstains on both, because it claims
    # both tails and only owns one.
    two_sided = C.Rule(threshold=0.99, **EXPRESSIBILITY_ONLY)
    assert C.flag({"m": high}, two_sided).flagged is None
    assert C.flag({"m": low}, two_sided).flagged is None


def test_the_one_tail_bug_deflated_fpr_and_the_fix_restores_the_abstention():
    """Why it mattered: those silent ``False``\\ s were counted as true negatives.

    Six nulls in the inexpressible tail. Pre-fix they were ``tn`` and the FPR
    gate read 0.0000 over them; post-fix they are ``unresolved_null``, ``fpr``
    is ``None`` (no null was resolved), and ``fpr_bounds["upper"]`` — the number
    the gate reads — is 1.0. A rule that cannot look has not passed anything.
    """
    column = one_tailed_reference()
    low = O.locate(None, {"m": column}, {"m": 0.0})["m"]
    nulls = [
        C.Scenario(id=f"n{i}", kind="null", locations={"m": low})
        for i in range(6)
    ]
    rule = C.Rule(threshold=0.99, **EXPRESSIBILITY_ONLY)
    matrix = C.confusion_matrix(nulls, rule)
    assert matrix["tn"] == 0 and matrix["fp"] == 0
    assert matrix["unresolved_null"] == 6
    assert matrix["fpr"] is None
    assert matrix["fpr_bounds"]["upper"] == 1.0

    blocks = C.gates(nulls, rule)
    assert blocks["fpr_on_nulls"]["pass"] is not True
    assert blocks["coverage"]["value"] == 0.0


# --------------------------------------------------------------------------- #
# round-3 finding: `outlierness` was not the statistic the rule thresholds
# --------------------------------------------------------------------------- #

def test_outlierness_is_the_quantity_the_rule_compares_against_its_threshold():
    """``max(p, 1 - p)`` under two_sided, and thresholding it reproduces ``flag``.

    ``1 - two_sided_p`` — what this returned before — is computed inclusively
    and disagrees with the mid-rank percentile the rule reads wherever the
    plan's value is tied in the reference.
    """
    column = one_tailed_reference()
    tied = O.locate(None, {"m": column}, {"m": 0.0})["m"]        # 8 ties
    assert tied.percentile == pytest.approx(0.02)
    assert tied.two_sided_p == pytest.approx(0.08)               # inclusive
    rule = C.Rule(threshold=0.99, **EXPRESSIBILITY_ONLY)
    assert C.metric_statistic(tied, rule) == pytest.approx(0.98)  # mid-rank
    assert C.outlierness({"m": tied}, rule) == pytest.approx(0.98)
    assert 1.0 - tied.two_sided_p == pytest.approx(0.92)          # the old value

    # thresholding the statistic at the rule's own threshold reproduces flag()
    for value in (0.0, 100.0, 186.5, 191.5, 200.0):
        loc = O.locate(None, {"m": column}, {"m": value})["m"]
        for tail in ("two_sided", "upper", "lower"):
            r = C.Rule(threshold=0.95, tail=tail, require_expressible=False,
                       **EXPRESSIBILITY_ONLY)
            fired = C.flag({"m": loc}, r).flagged
            assert fired == (C.outlierness({"m": loc}, r) >= r.threshold), (
                value, tail
            )


def test_the_old_score_ranked_two_plans_the_opposite_way_from_the_rule():
    """The AUC round 2 called decisive was over a statistic the rule does not use.

    A tied-bottom plant at mid-rank 0.02 is more extreme than an untied null at
    0.97 *by the rule* (0.98 > 0.97) and less extreme by ``1 - two_sided_p``
    (0.92 < 0.94). One pair, so the AUC is 1.0 one way and 0.0 the other.
    """
    column = one_tailed_reference()
    plant = O.locate(None, {"m": column}, {"m": 0.0})["m"]        # p = 0.02
    null = O.locate(None, {"m": column}, {"m": 186.5})["m"]       # p = 0.97
    rule = C.Rule(threshold=0.99, **EXPRESSIBILITY_ONLY)

    assert C.outlierness({"m": plant}, rule) > C.outlierness({"m": null}, rule)
    old_plant = 1.0 - plant.two_sided_p
    old_null = 1.0 - null.two_sided_p
    assert old_plant < old_null                                  # the inversion

    scenarios = [
        C.Scenario(id="p", kind="planted", locations={"m": plant},
                   intended_seat_shift=3),
        C.Scenario(id="n", kind="null", locations={"m": null}),
    ]
    block = C.auc(scenarios, rule)
    assert block["value"] == pytest.approx(1.0)                  # was 0.0
    assert block["score_threshold"] == 0.99
    assert "1 - two_sided_p" in block["score"]


# --------------------------------------------------------------------------- #
# round-3 finding: the "both constants score at their floor" claim was false
# --------------------------------------------------------------------------- #

def test_the_statistic_auc_has_no_constant_detector_floor():
    """Always-flag reads the same statistic and scores 1.0 on it, not 0.5.

    The floor belongs to ``decision_auc`` and to ``youden_j``. The old docstring
    claimed it for the statistic AUC as well, and ``report_lines`` printed
    "constant-detector floor 0.5" next to a number the constant had just tied at
    1.0.
    """
    scenarios = calibrated_scenarios()
    shipped = C.confusion_matrix(scenarios)
    always = C.confusion_matrix(scenarios, C.ALWAYS_FLAG, with_baselines=False)

    assert shipped["auc"]["value"] == pytest.approx(1.0)
    assert always["auc"]["value"] == pytest.approx(1.0)          # tied, not floored
    assert shipped["auc"]["constant_baseline"] is None
    assert "no constant-detector floor" in shipped["auc"]["constant_baseline_note"]

    # the floor that is real
    assert always["auc"]["decision_auc"] == pytest.approx(0.5)
    assert always["youden_j"] == pytest.approx(0.0)


def test_report_lines_print_each_auc_with_the_floor_that_is_actually_its_own():
    scenarios = calibrated_scenarios()
    matrix = C.confusion_matrix(scenarios)
    lines = C.report_lines(matrix, C.detection_curve(scenarios))
    statistic = next(l for l in lines if l.startswith("AUC (planted vs null"))
    decision = next(l for l in lines if l.startswith("decision AUC"))
    assert "1.0000" in statistic
    assert "NOT a constant-detector floor" in statistic
    assert "coin flip 0.5" in statistic
    assert "0.8500" in decision
    assert "both constant detectors score exactly 0.5" in decision
    # and the constants' own statistic AUC is on the page, so the claim is checkable
    assert any("statistic AUC 1.0000" in l for l in lines if "always-flag" in l)
