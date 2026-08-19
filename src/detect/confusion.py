"""The decision rule, and what it scores against manufactured ground truth.

``outlier.py`` says where a plan sits, per metric, and stops there. This module
holds the step that ``outlier.py`` refuses to take: turning a set of percentiles
into a single boolean flag. `docs/ARCHITECTURE.md` section 6:

    ``outlier.py`` returns a percentile per metric plus the ensemble
    distribution; the decision rule that turns percentiles into a flag lives in
    ``confusion.py`` and is an explicit, logged parameter — never buried in a
    scoring function.

So the rule is a :class:`Rule` — a frozen dataclass with documented defaults,
a ``describe()`` one-liner and an ``as_dict()`` for ``bench-results.json``. Every
number a reader would need to re-run the detector differently is a constructor
argument. Nothing here is hardcoded inside a function body, and no
``FlagDecision`` exists that cannot name the rule that produced it.

Why a flag is allowed here at all, when CRITERIA.md section 11 forbids collapsing
fairness to one number
----------------------------------------------------------------------------

Because this boolean is not a fairness verdict, and the difference is the whole
design. CRITERIA.md section 8: the detection gates are *the only thresholds worth
optimizing against*, precisely because their ground truth is manufacturable — the
adversarial package builds a plan with a known intended seat shift, so a flag on
it is a true positive by construction and a flag on a null is a false positive by
construction. The flag is a claim about **whether a plan is an outlier relative
to the ensemble**, measurable against a label; it is not a claim about whether
the plan is fair, which nothing in this repository computes.

The protection is that the flag never travels alone. A :class:`FlagDecision`
carries which metrics fired, at what percentile, on which side, and which
metrics were excluded and why — so the boolean can always be unwound back into
the distribution it came from.

Ground truth is **intent**, not realized shift
----------------------------------------------

A scenario is positive iff it was *planted* (``kind="planted"``). It is not
positive because its realized seat shift is large. CRITERIA.md section 5.4 is the
reason: a neutrally drawn Iowa map can move a seat purely because Democrats
cluster in Polk, Linn, Johnson and Scott, and ARCHITECTURE.md section 5's own
schema shows a null with ``intended_seat_shift: 0`` and
``realized_seat_shift: 1``. Labelling that null positive because a seat moved
would define away the exact failure the false-positive gate exists to catch — a
detector that has learned political geography rather than gerrymandering. So
``realized_seat_shift`` is carried, reported, and never used as a label.

The gates (CRITERIA.md section 8)
---------------------------------

===============================  ====================  =========================
gate                             target                measured by
===============================  ====================  =========================
TPR on planted gerrymanders      >= 0.95 at 2 seats    :func:`detection_curve`
FPR on neutral null cases        <= 0.05               :func:`confusion_matrix`
minimum detectable seat shift    **report, not gate**  :func:`min_detectable_seat_shift`
===============================  ====================  =========================

Two degenerate detectors exist as module constants, :data:`ALWAYS_FLAG` and
:data:`NEVER_FLAG`, because the pair of gates is only meaningful if it rejects
them: a detector that flags everything scores TPR 1.0 and fails the FPR gate at
1.0, and one that flags nothing scores FPR 0.0 and fails the TPR gate at 0.0.
Reporting either number alone would make each look like a success. That is why
:func:`confusion_matrix` returns the full matrix and **no accuracy, F1 or single
skill number** — on a scenario set that is mostly nulls, ``ALWAYS_FLAG`` and
``NEVER_FLAG`` both post respectable accuracies.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from detect.outlier import LOCATED, Location

# --------------------------------------------------------------------------- #
# the rule
# --------------------------------------------------------------------------- #

#: ``"upper"`` fires only on the high tail (for the four partisan metrics, the
#: tail favouring the party a positive value favours — see
#: ``evaluate.partisan.FAVOURS``, whose directions are *not* uniform).
#: ``"lower"`` only the low tail. ``"two_sided"`` either.
TAILS: tuple[str, ...] = ("two_sided", "upper", "lower")

#: How per-metric firings combine.
#:
#: ``"any"``      flag if at least one eligible metric fires (``k=1``)
#: ``"k_of_n"``   flag if at least ``k`` eligible metrics fire
#: ``"all"``      flag if every eligible metric fires, and there is at least one
#: ``"named"``    flag on exactly one named metric; ``metrics`` must have length 1
#: ``"none"``     never flag — the null detector of :data:`NEVER_FLAG`
COMBINATIONS: tuple[str, ...] = ("any", "k_of_n", "all", "named", "none")

#: What to do with a metric ``evaluate.partisan.trusted_metrics`` rejected for
#: this regime (``Location.trusted is False``).
#:
#: ``"exclude"``  it cannot fire; it is still reported, in ``excluded``
#: ``"include"``  it fires like any other metric
#:
#: ``outlier.locate`` marks rather than drops such metrics; this says whether the
#: *decision* may rest on one. The default is ``"exclude"`` because CRITERIA.md
#: section 5.1 says the number is unreliable in the regime, and a flag resting on
#: an unreliable number is an unreliable flag. On Iowa's enacted plan this leaves
#: the efficiency gap alone eligible of the four partisan metrics.
UNTRUSTED_POLICIES: tuple[str, ...] = ("exclude", "include")


@dataclass(frozen=True)
class Rule:
    """The decision rule. Explicit, printable, and entirely made of parameters.

    Defaults, and why each is what it is — all four are `VALUE` choices in the
    sense of CRITERIA.md, chosen here and changeable by a reader:

    ``threshold = 0.99``
        A metric fires when its mid-rank percentile is at least this
        (``upper``), at most ``1 - threshold`` (``lower``), or either
        (``two_sided``). Not 0.95, and the arithmetic is the reason: under
        ``two_sided`` a threshold ``t`` gives each metric a nominal
        ``2(1 - t)`` chance of firing on a plan drawn from the ensemble itself,
        so ``m`` independent eligible metrics under ``"any"`` give a nominal
        false-positive rate of ``1 - (1 - 2(1-t))^m``. At ``t = 0.95`` and four
        metrics that is 0.34 — seven times the CRITERIA.md section 8 gate before
        a single plan has been drawn. At ``t = 0.99`` it is 0.077, and at one
        eligible metric 0.02. The nominal figure is an upper-bound sanity check,
        not a prediction: null plans are not ensemble draws (CRITERIA.md section
        5.4) and the metrics are strongly correlated. The measured FPR is what
        the gate reads.
    ``tail = "two_sided"``
        A gerrymander favours *some* party, and the four partisan metrics do not
        share a sign convention (``evaluate.partisan.FAVOURS``). One-sided is
        available and doubles the resolution at the threshold, but only for a
        caller who has decided in advance which party is being tested for.
    ``combination = "any"``
        With one eligible metric — Iowa's case — ``"any"``, ``"all"`` and
        ``"named"`` coincide, so this choice costs nothing there and matters
        wherever more metrics survive the trust test. ``"any"`` is the most
        sensitive and the most false-positive-prone; ``"k_of_n"`` is the knob
        for trading one against the other.
    ``untrusted = "exclude"``
        See :data:`UNTRUSTED_POLICIES`.

    ``metrics`` restricts and orders the metrics considered; ``None`` means
    every located metric in the ``locations`` mapping. ``min_n`` refuses a
    firing computed from fewer than that many ensemble draws even if
    ``outlier.locate`` was run with a lower floor.
    """

    threshold: float = 0.99
    tail: str = "two_sided"
    combination: str = "any"
    k: int = 1
    metrics: tuple[str, ...] | None = None
    untrusted: str = "exclude"
    min_n: int = 20
    name: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(f"Rule.threshold must be in [0, 1], got {self.threshold}")
        if self.tail not in TAILS:
            raise ValueError(f"Rule.tail must be one of {TAILS}, got {self.tail!r}")
        if self.combination not in COMBINATIONS:
            raise ValueError(
                f"Rule.combination must be one of {COMBINATIONS}, "
                f"got {self.combination!r}"
            )
        if self.untrusted not in UNTRUSTED_POLICIES:
            raise ValueError(
                f"Rule.untrusted must be one of {UNTRUSTED_POLICIES}, "
                f"got {self.untrusted!r}"
            )
        if self.k < 1:
            raise ValueError(f"Rule.k must be >= 1, got {self.k}")
        if self.combination == "named":
            if self.metrics is None or len(self.metrics) != 1:
                raise ValueError(
                    "Rule(combination='named') needs exactly one name in "
                    f"metrics, got {self.metrics!r}"
                )
        if self.metrics is not None:
            object.__setattr__(self, "metrics", tuple(self.metrics))

    # -- reporting ---------------------------------------------------------- #

    @property
    def effective_k(self) -> int:
        """The number of firings required, for the combinations that use one."""
        return self.k if self.combination == "k_of_n" else 1

    def describe(self) -> str:
        """One line, suitable for a log or a plot caption.

        Every :class:`FlagDecision`, confusion matrix and detection curve this
        module returns carries this string, so a result can never be read
        without the rule that produced it.
        """
        where = "any metric" if self.metrics is None else ", ".join(self.metrics)
        if self.combination == "none":
            body = "never flags (null detector)"
        elif self.combination == "named":
            body = f"{self.metrics[0]} alone"
        elif self.combination == "k_of_n":
            body = f"at least {self.k} of [{where}]"
        elif self.combination == "all":
            body = f"all of [{where}]"
        else:
            body = f"any of [{where}]"
        lo = 1.0 - self.threshold
        if self.tail == "two_sided":
            band = f"percentile >= {self.threshold:g} or <= {lo:g}"
        elif self.tail == "upper":
            band = f"percentile >= {self.threshold:g}"
        else:
            band = f"percentile <= {lo:g}"
        tag = f"{self.name}: " if self.name else ""
        return (
            f"{tag}flag when {body} has {band} "
            f"(tail={self.tail}, untrusted={self.untrusted}, min_n={self.min_n})"
        )

    def nominal_fpr(self, n_metrics: int) -> float:
        """Upper-bound nominal FPR if ``n_metrics`` fired independently.

        A sanity check on the threshold, **not** a prediction and never a
        substitute for the measured rate. It assumes the plan is itself an
        ensemble draw and that the metrics are independent; neither holds —
        CRITERIA.md section 5.4 says null plans sit off-centre for reasons of
        geography, and the partisan metrics are strongly correlated with one
        another. Under ``"all"`` and ``"k_of_n"`` the true nominal rate is
        lower, and this returns the ``"any"`` bound regardless, which is the
        conservative direction.
        """
        if self.combination == "none" or n_metrics <= 0:
            return 0.0
        per = (1.0 - self.threshold) * (2.0 if self.tail == "two_sided" else 1.0)
        per = min(1.0, max(0.0, per))
        return 1.0 - (1.0 - per) ** n_metrics

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "threshold": self.threshold,
            "tail": self.tail,
            "combination": self.combination,
            "k": self.effective_k,
            "metrics": None if self.metrics is None else list(self.metrics),
            "untrusted": self.untrusted,
            "min_n": self.min_n,
            "describe": self.describe(),
        }


#: The default rule, named. See :class:`Rule` for every default and its reason.
DEFAULT_RULE = Rule(name="default")

#: Flags every plan it is shown. Present so the gates can be shown to reject it:
#: it scores TPR 1.0, which passes the true-positive gate, and FPR 1.0, which
#: fails the false-positive gate — the asymmetry CRITERIA.md section 8 means by
#: "null cases are as important as positive cases".
ALWAYS_FLAG = Rule(
    threshold=0.0,
    tail="two_sided",
    combination="any",
    untrusted="include",
    min_n=0,
    name="always-flag",
)

#: Flags nothing. Scores FPR 0.0, which passes the false-positive gate, and TPR
#: 0.0, which fails the true-positive gate. The mirror of :data:`ALWAYS_FLAG`,
#: and the reason ``"none"`` is a listed combination rather than something a
#: caller has to fake with an impossible threshold.
NEVER_FLAG = Rule(combination="none", name="never-flag")


# --------------------------------------------------------------------------- #
# firing one metric
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MetricFiring:
    """One metric that fired, and the numbers that made it fire."""

    metric: str
    percentile: float
    side: str  # "high" | "low"
    threshold: float
    z: float | None = None
    two_sided_p: float | None = None
    n: int = 0
    trusted: bool | None = None
    value: float | None = None

    def describe(self) -> str:
        mark = " [UNTRUSTED in this regime]" if self.trusted is False else ""
        bound = self.threshold if self.side == "high" else 1.0 - self.threshold
        rel = ">=" if self.side == "high" else "<="
        return (
            f"{self.metric} percentile {self.percentile:.4f} {rel} {bound:g} "
            f"({self.side} tail, n={self.n}){mark}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "value": self.value,
            "percentile": self.percentile,
            "side": self.side,
            "threshold": self.threshold,
            "z": self.z,
            "two_sided_p": self.two_sided_p,
            "n": self.n,
            "trusted": self.trusted,
        }


def _eligibility(loc: Location, rule: Rule) -> str | None:
    """``None`` if this location may fire, else the prose reason it may not."""
    if loc.status != LOCATED:
        return f"no percentile ({loc.status})"
    if loc.n < rule.min_n:
        return f"only {loc.n} ensemble draws (rule.min_n={rule.min_n})"
    if loc.trusted is False and rule.untrusted == "exclude":
        return (
            "not trusted in this regime (CRITERIA.md section 5.1) and "
            "rule.untrusted='exclude'"
        )
    return None


def _fire(loc: Location, rule: Rule) -> MetricFiring | None:
    """Does this eligible location cross the rule's threshold?"""
    p = loc.percentile
    assert p is not None  # guaranteed by _eligibility
    high = p >= rule.threshold
    low = p <= 1.0 - rule.threshold
    if rule.tail == "upper":
        low = False
    elif rule.tail == "lower":
        high = False
    if not (high or low):
        return None
    # A threshold of exactly 0.5 under two_sided makes both true; report the
    # side the value actually sits on, breaking the exact centre as "high".
    side = "high" if high and (not low or p >= 0.5) else "low"
    return MetricFiring(
        metric=loc.metric,
        percentile=p,
        side=side,
        threshold=rule.threshold,
        z=loc.z,
        two_sided_p=loc.two_sided_p,
        n=loc.n,
        trusted=loc.trusted,
        value=loc.value,
    )


# --------------------------------------------------------------------------- #
# the decision
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FlagDecision:
    """A flag that cannot be read without the reasoning behind it.

    ``fired`` names every metric that crossed the threshold and at what
    percentile; ``excluded`` names every metric that was not allowed to try and
    why. A decision with ``flagged=False`` and four excluded metrics is a very
    different statement from one with ``flagged=False`` and four metrics that
    all sat mid-distribution, and this dataclass keeps them distinguishable.
    """

    flagged: bool
    rule: Rule
    fired: tuple[MetricFiring, ...] = ()
    eligible: tuple[str, ...] = ()
    excluded: tuple[tuple[str, str], ...] = ()
    reason: str = ""

    @property
    def fired_metrics(self) -> tuple[str, ...]:
        return tuple(f.metric for f in self.fired)

    def as_dict(self) -> dict[str, Any]:
        return {
            "flagged": self.flagged,
            "rule": self.rule.as_dict(),
            "fired": [f.as_dict() for f in self.fired],
            "fired_metrics": list(self.fired_metrics),
            "eligible": list(self.eligible),
            "excluded": {name: why for name, why in self.excluded},
            "reason": self.reason,
        }


def flag(
    locations: Mapping[str, Location], rule: Rule = DEFAULT_RULE
) -> FlagDecision:
    """Apply ``rule`` to per-metric locations. The only place a flag is decided.

    ``locations`` is ``outlier.locate``'s return value. ``rule`` defaults to
    :data:`DEFAULT_RULE` and is carried on the result, so no decision in this
    repository exists without its rule attached.

    Metrics with no percentile — undefined values, degenerate metrics, ensembles
    too small — are **excluded with a reason**, never treated as unremarkable.
    That distinction is the whole point of ``outlier``'s statuses: an absent
    percentile is not a percentile of 0.5.

    Empty eligibility never flags. Under ``"all"`` that is an explicit choice
    against vacuous truth: "every eligible metric fired" is trivially satisfied
    by no metrics at all, and a detector that fires hardest when it can measure
    least is worse than useless.
    """
    names = (
        list(locations) if rule.metrics is None
        else [m for m in rule.metrics]
    )

    eligible: list[str] = []
    excluded: list[tuple[str, str]] = []
    fired: list[MetricFiring] = []

    for name in names:
        loc = locations.get(name)
        if loc is None:
            excluded.append((name, "not present in locations"))
            continue
        why = _eligibility(loc, rule)
        if why is not None:
            excluded.append((name, why))
            continue
        eligible.append(name)
        hit = _fire(loc, rule)
        if hit is not None:
            fired.append(hit)

    n_fired = len(fired)
    n_eligible = len(eligible)

    if rule.combination == "none":
        flagged = False
        reason = "rule never flags (null detector)"
    elif n_eligible == 0:
        flagged = False
        reason = (
            "no metric was eligible to fire — "
            + ("; ".join(f"{m}: {w}" for m, w in excluded) or "no metrics given")
        )
    elif rule.combination == "all":
        flagged = n_fired == n_eligible
        reason = f"{n_fired} of {n_eligible} eligible metrics fired (all required)"
    elif rule.combination == "k_of_n":
        flagged = n_fired >= rule.k
        reason = f"{n_fired} of {n_eligible} eligible metrics fired (k={rule.k})"
    else:  # "any", "named"
        flagged = n_fired >= 1
        reason = f"{n_fired} of {n_eligible} eligible metrics fired (any required)"

    if fired:
        reason += ": " + "; ".join(f.describe() for f in fired)

    return FlagDecision(
        flagged=flagged,
        rule=rule,
        fired=tuple(fired),
        eligible=tuple(eligible),
        excluded=tuple(excluded),
        reason=reason,
    )


# --------------------------------------------------------------------------- #
# scenarios: manufactured ground truth
# --------------------------------------------------------------------------- #

#: ``"planted"`` — built by ``adversarial`` with a known intended seat shift;
#: ground-truth positive. ``"null"`` — neutrally drawn, ground-truth negative,
#: and as important as the positives (CRITERIA.md section 8).
KINDS: tuple[str, ...] = ("planted", "null")


@dataclass(frozen=True)
class Scenario:
    """One labelled test case: a plan's locations plus what it actually is.

    ``intended_seat_shift`` is the label's magnitude — how many seats the
    adversarial construction was aiming to move, signed by direction if the
    caller wants (``+`` and ``-`` are treated as the same magnitude by
    :func:`detection_curve`). A null must have ``intended_seat_shift == 0``;
    anything else is a mislabelled scenario and raises here rather than
    silently deflating the false-positive rate.

    ``realized_seat_shift`` is what the plan actually did, carried for the
    report (ARCHITECTURE.md section 5) and **never used as a label** — see the
    module docstring.
    """

    id: str
    kind: str
    locations: Mapping[str, Location]
    intended_seat_shift: int = 0
    realized_seat_shift: int | None = None
    target_party: str | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(
                f"Scenario {self.id!r}: kind must be one of {KINDS}, "
                f"got {self.kind!r}"
            )
        if self.kind == "null" and self.intended_seat_shift != 0:
            raise ValueError(
                f"Scenario {self.id!r}: a null case has intended_seat_shift 0 "
                f"by definition, got {self.intended_seat_shift}. A planted plan "
                "labelled null would be counted as a false positive when the "
                "detector got it right."
            )
        if self.kind == "planted" and self.intended_seat_shift == 0:
            raise ValueError(
                f"Scenario {self.id!r}: a planted case with intended_seat_shift "
                "0 has no ground truth to detect. Label it 'null' or give it a "
                "shift."
            )

    @property
    def is_positive(self) -> bool:
        """Ground truth. Intent, not outcome."""
        return self.kind == "planted"

    @property
    def magnitude(self) -> int:
        """``abs(intended_seat_shift)`` — the x axis of the detection curve."""
        return abs(int(self.intended_seat_shift))


def as_scenario(obj: Any) -> Scenario:
    """Coerce a mapping to a :class:`Scenario`; pass one through unchanged."""
    if isinstance(obj, Scenario):
        return obj
    if isinstance(obj, Mapping):
        known = {
            "id", "kind", "locations", "intended_seat_shift",
            "realized_seat_shift", "target_party", "notes",
        }
        unknown = set(obj) - known
        if unknown:
            raise ValueError(f"scenario has unknown keys: {sorted(unknown)}")
        data = dict(obj)
        data["notes"] = tuple(data.get("notes", ()))
        return Scenario(**data)
    raise TypeError(f"cannot read a scenario from {type(obj).__name__}")


def _scenarios(scenarios: Iterable[Any]) -> list[Scenario]:
    out = [as_scenario(s) for s in scenarios]
    seen: set[str] = set()
    for s in out:
        if s.id in seen:
            raise ValueError(f"duplicate scenario id {s.id!r}")
        seen.add(s.id)
    return out


# --------------------------------------------------------------------------- #
# the confusion matrix
# --------------------------------------------------------------------------- #

def wilson_interval(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    """95% Wilson score interval for ``k`` successes in ``n``, or ``None``.

    Reported beside every rate because the scenario counts here are small. A
    measured TPR of 1.00 on 20 planted plans has a lower bound near 0.84 — below
    the 0.95 gate — and a gate read off the point estimate alone would call that
    a pass with a straight face. The interval does not change the gate (the gate
    is on the measured rate, per CRITERIA.md section 8); it states how much of
    the measurement is sampling noise.

    Normal-approximation based, so it is itself approximate at these counts.
    """
    if n <= 0:
        return None
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _rate(k: int, n: int) -> float | None:
    """``k/n``, or ``None`` when ``n`` is 0 — never 0.0 by default."""
    return None if n == 0 else k / n


def decide(
    scenarios: Iterable[Any], rule: Rule = DEFAULT_RULE
) -> list[tuple[Scenario, FlagDecision]]:
    """Run ``rule`` over every scenario, keeping the decisions intact."""
    return [(s, flag(s.locations, rule)) for s in _scenarios(scenarios)]


def confusion_matrix(
    scenarios: Iterable[Any], rule: Rule = DEFAULT_RULE
) -> dict[str, Any]:
    """The full confusion matrix for ``rule`` over labelled scenarios.

    Returns counts (``tp``, ``fp``, ``tn``, ``fn``), the four rates derived from
    them, Wilson intervals for the two that are gated, the rule, a per-scenario
    row for every case, and a tally of which metrics fired on positives versus
    on nulls.

    **There is no accuracy key, no F1 and no single skill number.** On a
    scenario set that is mostly nulls, :data:`ALWAYS_FLAG` and :data:`NEVER_FLAG`
    both post a respectable accuracy, and either would be reported as a working
    detector by any of those summaries. The matrix is the output; the reader
    reads both rates or neither.

    ``tpr`` and ``fpr`` are ``None`` when the corresponding class is empty. Not
    0.0, not 1.0: a rate over no cases is a measurement that was not made, and
    :func:`gates` refuses to pass a gate on one.

    The metric tally is the diagnostic that separates the two ways a detector
    fails. A detector firing on the same metric for planted and null plans alike
    has learned the metric's geography-driven baseline, which CRITERIA.md
    section 5.4 says exists in Iowa; one that fires on different metrics for the
    two classes is at least responding to the plant.
    """
    decisions = decide(scenarios, rule)

    tp = fp = tn = fn = 0
    rows: list[dict[str, Any]] = []
    fired_positive: dict[str, int] = {}
    fired_null: dict[str, int] = {}

    for scenario, decision in decisions:
        if scenario.is_positive:
            tp += decision.flagged
            fn += not decision.flagged
            tally = fired_positive
        else:
            fp += decision.flagged
            tn += not decision.flagged
            tally = fired_null
        for name in decision.fired_metrics:
            tally[name] = tally.get(name, 0) + 1
        rows.append(
            {
                "id": scenario.id,
                "kind": scenario.kind,
                "target_party": scenario.target_party,
                "intended_seat_shift": scenario.intended_seat_shift,
                "realized_seat_shift": scenario.realized_seat_shift,
                "truth": "positive" if scenario.is_positive else "null",
                "flagged": decision.flagged,
                "outcome": _outcome(scenario.is_positive, decision.flagged),
                "fired_metrics": list(decision.fired_metrics),
                "excluded": {m: w for m, w in decision.excluded},
                "reason": decision.reason,
            }
        )

    n_positive = tp + fn
    n_null = fp + tn
    return {
        "rule": rule.as_dict(),
        "n": n_positive + n_null,
        "n_positive": n_positive,
        "n_null": n_null,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "tpr": _rate(tp, n_positive),
        "fnr": _rate(fn, n_positive),
        "fpr": _rate(fp, n_null),
        "tnr": _rate(tn, n_null),
        "tpr_ci95": wilson_interval(tp, n_positive),
        "fpr_ci95": wilson_interval(fp, n_null),
        "fired_on_positives": dict(sorted(fired_positive.items())),
        "fired_on_nulls": dict(sorted(fired_null.items())),
        "scenarios": rows,
    }


def _outcome(is_positive: bool, flagged: bool) -> str:
    if is_positive:
        return "true_positive" if flagged else "false_negative"
    return "false_positive" if flagged else "true_negative"


# --------------------------------------------------------------------------- #
# detection as a function of magnitude
# --------------------------------------------------------------------------- #

def detection_curve(
    scenarios: Iterable[Any], rule: Rule = DEFAULT_RULE
) -> list[dict[str, Any]]:
    """TPR against intended seat shift — ARCHITECTURE.md section 5's ``by_magnitude``.

    One row per distinct ``abs(intended_seat_shift)`` among the **planted**
    scenarios, ascending. Nulls have no TPR (their rate is the FPR and lives in
    :func:`confusion_matrix`), so they are not points on this curve.

    Rows carry ``seats``, ``n``, ``flagged``, ``tpr``, ``ci95``, the ids in the
    bucket, and ``by_direction`` — the R-favouring and D-favouring counts, kept
    because a curve that looks fine in aggregate can be hiding a detector that
    only sees gerrymanders in one direction, and the four partisan metrics are
    not sign-symmetric to begin with (``evaluate.partisan.FAVOURS``).

    Magnitudes are bucketed on the **intended** shift. A planted 2-seat plan
    that only realized 1 stays in the 2 bucket: the question the curve answers
    is "how large a manipulation must be before this detector sees it", and
    re-bucketing on the realized shift would quietly grade the adversarial
    package instead of the detector.
    """
    rows: dict[int, dict[str, Any]] = {}
    for scenario, decision in decide(scenarios, rule):
        if not scenario.is_positive:
            continue
        row = rows.setdefault(
            scenario.magnitude,
            {
                "seats": scenario.magnitude,
                "n": 0,
                "flagged": 0,
                "ids": [],
                "by_direction": {"R": 0, "D": 0, "unspecified": 0},
                "realized_seat_shifts": [],
            },
        )
        row["n"] += 1
        row["flagged"] += int(decision.flagged)
        row["ids"].append(scenario.id)
        key = scenario.target_party if scenario.target_party in ("R", "D") else "unspecified"
        row["by_direction"][key] += 1
        row["realized_seat_shifts"].append(scenario.realized_seat_shift)

    out = []
    for seats in sorted(rows):
        row = rows[seats]
        row["tpr"] = _rate(row["flagged"], row["n"])
        row["ci95"] = wilson_interval(row["flagged"], row["n"])
        row["rule"] = rule.describe()
        out.append(row)
    return out


def tpr_at(curve: Sequence[Mapping[str, Any]], seats: int) -> float | None:
    """TPR at one magnitude, or ``None`` if no scenario was run there."""
    for row in curve:
        if row["seats"] == seats:
            return row["tpr"]
    return None


def min_detectable_seat_shift(
    curve: Sequence[Mapping[str, Any]],
    target_tpr: float = 0.95,
    *,
    require_monotone: bool = True,
) -> int | None:
    """Smallest measured seat shift the detector reaches ``target_tpr`` at.

    CRITERIA.md section 8 classes this `DERIVED` and says **report, do not
    gate** — it is "the honest headline number for the whole system", and a
    number that is honest precisely because nothing is being tuned against it.
    :func:`gates` therefore returns it with no pass/fail attached.

    ``None`` means no measured magnitude reached the target. It does **not**
    mean 0 and it does not mean "undetectable": it means the scenario set does
    not contain a magnitude where this detector cleared the bar, which can be
    fixed by running larger plants as easily as by improving the detector.

    ``require_monotone`` (default true) additionally demands that every larger
    magnitude measured also clears the target. Without it, one lucky bucket
    reports a smaller minimum than the curve supports — a 1-seat bucket of three
    scenarios that happens to score 1.00 while the 2-seat bucket scores 0.90
    would publish "minimum detectable shift: 1", which the next line of the same
    table contradicts. Set it false to see the raw first crossing.
    """
    rows = sorted(
        (r for r in curve if r.get("tpr") is not None), key=lambda r: r["seats"]
    )
    for i, row in enumerate(rows):
        if row["tpr"] < target_tpr:
            continue
        if require_monotone and any(r["tpr"] < target_tpr for r in rows[i + 1:]):
            continue
        return int(row["seats"])
    return None


# --------------------------------------------------------------------------- #
# gates
# --------------------------------------------------------------------------- #

#: CRITERIA.md section 8, true-positive gate: TPR >= 0.95 at a 2-seat shift.
TPR_GATE = 0.95

#: CRITERIA.md section 8, false-positive gate: FPR <= 0.05 on neutral nulls.
FPR_GATE = 0.05

#: The magnitude the TPR gate is stated at.
GATE_SEAT_SHIFT = 2


def gates(
    scenarios: Iterable[Any],
    rule: Rule = DEFAULT_RULE,
    *,
    tpr_gate: float = TPR_GATE,
    fpr_gate: float = FPR_GATE,
    seat_shift: int = GATE_SEAT_SHIFT,
) -> dict[str, Any]:
    """The two detection gates of CRITERIA.md section 8, plus what is reported.

    Shaped for ARCHITECTURE.md section 5's ``gates`` block: each entry carries
    ``target``, ``value`` and ``pass``.

    ``pass`` is ``None`` — not ``False``, and emphatically not ``True`` — when
    the gate could not be measured, i.e. there are no scenarios of the class it
    needs. ``None`` is falsy, so a caller writing ``if result["pass"]`` gets the
    conservative answer, while a caller rendering the table sees that the
    measurement is missing rather than that the detector failed. Those are
    different findings and the schema should not blur them.

    ``min_detectable_seat_shift`` appears with ``"gated": False``, because
    CRITERIA.md section 8 says to report it and not gate it.
    """
    matrix = confusion_matrix(scenarios, rule)
    curve = detection_curve(scenarios, rule)
    tpr = tpr_at(curve, seat_shift)
    fpr = matrix["fpr"]
    return {
        "rule": rule.as_dict(),
        f"tpr_at_{seat_shift}seat": {
            "target": tpr_gate,
            "value": tpr,
            "pass": None if tpr is None else tpr >= tpr_gate,
            "n": next((r["n"] for r in curve if r["seats"] == seat_shift), 0),
            "note": None if tpr is not None
            else f"no planted scenarios at a {seat_shift}-seat shift",
        },
        "fpr_on_nulls": {
            "target": fpr_gate,
            "value": fpr,
            "pass": None if fpr is None else fpr <= fpr_gate,
            "n": matrix["n_null"],
            "note": None if fpr is not None else "no null scenarios",
        },
        "min_detectable_seat_shift": {
            "value": min_detectable_seat_shift(curve, tpr_gate),
            "target_tpr": tpr_gate,
            "gated": False,
            "note": "CRITERIA.md section 8: report, do not gate",
        },
    }


def report_lines(matrix: Mapping[str, Any], curve: Sequence[Mapping[str, Any]]) -> list[str]:
    """Human-readable confusion report. Both rates, always, side by side."""
    lines = [
        f"rule: {matrix['rule']['describe']}",
        f"scenarios: {matrix['n']} ({matrix['n_positive']} planted, "
        f"{matrix['n_null']} null)",
        f"          flagged   not flagged",
        f"planted   {matrix['tp']:>7}   {matrix['fn']:>11}",
        f"null      {matrix['fp']:>7}   {matrix['tn']:>11}",
        f"TPR = {_fmt(matrix['tpr'])}  (95% CI {_fmt_ci(matrix['tpr_ci95'])})",
        f"FPR = {_fmt(matrix['fpr'])}  (95% CI {_fmt_ci(matrix['fpr_ci95'])})",
    ]
    for row in curve:
        lines.append(
            f"  {row['seats']}-seat shift: TPR {_fmt(row['tpr'])} "
            f"({row['flagged']}/{row['n']}, 95% CI {_fmt_ci(row['ci95'])})"
        )
    mds = min_detectable_seat_shift(curve)
    lines.append(
        "minimum detectable seat shift: "
        + ("not reached at any measured magnitude" if mds is None else str(mds))
        + "  [reported, not gated]"
    )
    return lines


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.4f}"


def _fmt_ci(ci: Sequence[float] | None) -> str:
    return "n/a" if ci is None else f"{ci[0]:.3f}-{ci[1]:.3f}"


__all__ = [
    "TAILS",
    "COMBINATIONS",
    "UNTRUSTED_POLICIES",
    "KINDS",
    "Rule",
    "DEFAULT_RULE",
    "ALWAYS_FLAG",
    "NEVER_FLAG",
    "MetricFiring",
    "FlagDecision",
    "Scenario",
    "as_scenario",
    "flag",
    "decide",
    "confusion_matrix",
    "detection_curve",
    "tpr_at",
    "min_detectable_seat_shift",
    "wilson_interval",
    "TPR_GATE",
    "FPR_GATE",
    "GATE_SEAT_SHIFT",
    "gates",
    "report_lines",
]
