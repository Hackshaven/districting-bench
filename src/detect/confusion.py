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

The two constant detectors are outputs, not diagnostics
-------------------------------------------------------

:data:`ALWAYS_FLAG` and :data:`NEVER_FLAG` are scored **beside every confusion
matrix this module produces**, in :func:`confusion_matrix`, in :func:`gates` and
in :func:`report_lines`. Round 2 computed them and filed them under
``diagnostics.alternative_rules``, where they appeared in no gate, no report line
and none of the five plots — while an always-flag detector tied both of round
1's passing gates and beat the shipped rule on the headline number. **A gate a
constant ties is not a measurement**, and a baseline a reader has to go looking
for is not a baseline. So the comparison is structural: a matrix without its two
constants beside it cannot be produced by this module.

Which forces two numbers that are *not* accuracy or F1
------------------------------------------------------

The old rule here was "no accuracy, no F1, no single skill number", and the
reason was sound: on a mostly-null scenario set both constants post respectable
accuracies, so either summary would report a constant as a working detector.
That reasoning argues for the two statistics added in round 3 — but **only two
of the three numbers they produce score the constants at their floor, and round
3 claimed it of all of them**. The correction, because it was wrong in the
direction that flatters the report:

``auc["value"]`` — the **statistic** AUC
    Area under the ROC curve for separating planted from neutral plans, over the
    continuous statistic the rule actually thresholds (:func:`outlierness`).
    **A constant detector does not score 0.5 here and the old docstring's "any
    constant score gives 0.5, ties included" was false.** ``ALWAYS_FLAG`` is a
    constant *decision*, not a constant score: it reads the same percentiles
    every rule reads and merely thresholds them at 0.0, so on
    ``tests.calibrated_scenarios`` its statistic AUC is **1.0**, not 0.5, while
    the shipped rule's is also 1.0 — the number a constant supposedly could not
    tie, tied. (``NEVER_FLAG`` reads nothing and scores ``None``.) The statistic
    AUC is still first-class — round 2's rule scored **0.25**, an inverted
    ranking, and that number appeared nowhere in its artifact — but it is a
    property of the *statistic*, not of the *detector*, and it has no
    constant-detector floor. :func:`report_lines` labels it accordingly.
``auc["decision_auc"]``
    ``(1 + TPR - FPR)/2``, the area under the ROC through the rule's one shipped
    operating point. **This** is the number that is exactly 0.5 for both
    constants by construction, and it is the one the baseline block and
    ``beats_baselines`` compare against 0.5.
``youden_j``
    ``TPR - FPR`` at the rule's own operating point. Exactly 0.0 for always-flag
    and 0.0 for never-flag, so it cannot be tied by a constant without the
    detector being worthless.

None of the three is a fairness score and none replaces the matrix: all are
reported *after* the full counts, and :func:`confusion_matrix` still returns no
accuracy and no F1. CRITERIA.md section 11's prohibition is on collapsing
**fairness** to one number; these collapse **detection skill against
manufactured labels**, which CRITERIA.md section 8 calls the only thing in the
system worth optimizing against. They exist specifically to expose a detector
that a constant ties — which is why round 3's misplaced floor claim mattered.

A rule its reference cannot express is refused, not answered
------------------------------------------------------------

``outlier`` reports the resolution of every percentile — raw draws, distinct
plans, Kish ESS, and the interior percentile band the column can actually reach.
:class:`Rule` reads it and **abstains** rather than returning a decision the
arithmetic does not support. A threshold of 0.99 needs a reference whose interior
percentiles reach 0.99 (``n >= 50`` at best, more with ties at the extreme); at
28 draws they reach 0.96, so "top 1%" silently became "outside the observed
support" and produced six false positives, two of them 0.0005 of an
efficiency-gap point outside a support pinched shut by 14 distinct plans.

The abstention is visible everywhere downstream: :attr:`FlagDecision.flagged` is
``None`` (not ``False``), the confusion matrix counts ``unresolved_positive`` and
``unresolved_null`` separately from ``fn`` and ``tn``, and the gates read
**bounds** over the whole class rather than a rate over the answered subset — so
a detector cannot pass a gate by declining to answer. See :meth:`Rule.resolvable`
and :func:`gates`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from detect.outlier import LOCATED, Location
from detect.outlier import required_n as outlier_required_n

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
    every located metric in the ``locations`` mapping.

    The three resolution parameters — what round 2 got wrong
    -------------------------------------------------------

    ``min_n = 20``
        Raw defined draws. **The weakest of the three and no longer the gate.**
        Round 2 gated on this alone, comparing it against ``Location.n``: 28 raw
        draws over 14 distinct plans passed a floor of 20, and 806 raw draws
        worth 11.7 independent ones passed it too. A count of draws is not a
        measure of resolution when draws repeat, and ReCom draws repeat.
    ``min_distinct = None``
        Distinct plans in the reference (distinct *values* when the caller did
        not supply plan ids — see ``outlier.Location.n_distinct_reference``).
        ``None`` means *derived*: ``outlier.required_n(threshold)``, which is 50
        at ``t = 0.99``. Derived rather than a constant on purpose — a fixed
        number here would be one more tunable dial pointed at a gate, and the
        requirement genuinely is a function of the threshold.
    ``min_ess = None``
        Kish effective sample size. ``None`` means derived the same way. This is
        the check 806 draws fail: 11.7 effective draws cannot support a claim
        about a 1% tail no matter how many times they are written down.

    ``require_expressible = True``
        The exact check, and the one that subsumes the idealised ``required_n``:
        the reference's attained interior percentile band
        ``[min_interior_percentile, max_interior_percentile]`` must contain the
        threshold on **every** tail the rule fires on — both of them under
        ``two_sided``, and the check is an AND, not an OR (see
        :meth:`resolvable`). At 28 draws with a tied maximum that band tops out
        at 0.9643, so a 0.99 rule can only fire on a plan outside the observed
        support — which is a support test wearing a percentile's clothes, and is
        exactly how round 1 produced FPR 1.00.

    A location failing any of the four is **unresolvable**, not "not extreme":
    the rule abstains and says so. See :meth:`resolvable`.
    """

    threshold: float = 0.99
    tail: str = "two_sided"
    combination: str = "any"
    k: int = 1
    metrics: tuple[str, ...] | None = None
    untrusted: str = "exclude"
    min_n: int = 20
    min_distinct: int | None = None
    min_ess: float | None = None
    require_expressible: bool = True
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
        if self.min_distinct is not None and self.min_distinct < 1:
            raise ValueError(
                f"Rule.min_distinct must be >= 1 or None, got {self.min_distinct}"
            )
        if self.min_ess is not None and self.min_ess < 0:
            raise ValueError(f"Rule.min_ess must be >= 0 or None, got {self.min_ess}")
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

    @property
    def required_n(self) -> int | None:
        """``outlier.required_n(threshold)`` — the size floor this threshold implies.

        ``None`` at ``threshold`` 0.0 or 1.0, which no finite reference expresses.
        ``"none"``-combination rules never read a percentile, so they return 0.
        """
        if self.combination == "none":
            return 0
        return outlier_required_n(self.threshold)

    @property
    def required_distinct(self) -> int | None:
        """``min_distinct`` if set, else derived from the threshold."""
        if self.min_distinct is not None:
            return int(self.min_distinct)
        return self.required_n

    @property
    def required_ess(self) -> float | None:
        """``min_ess`` if set, else derived from the threshold."""
        if self.min_ess is not None:
            return float(self.min_ess)
        req = self.required_n
        return None if req is None else float(req)

    @property
    def fires_on(self) -> tuple[str, ...]:
        """The tails this rule can fire on: ``("high",)``, ``("low",)`` or both."""
        if self.tail == "upper":
            return ("high",)
        if self.tail == "lower":
            return ("low",)
        return ("high", "low")

    def tail_expressibility(self, loc: Location) -> dict[str, bool | None]:
        """Per-tail: can this reference express this threshold on that tail?

        ``True``/``False`` for each tail in :attr:`fires_on`, ``None`` when the
        location reports no interior band. Reported as well as read, so an
        artifact can show *which* half of a two-sided rule the reference
        supports rather than only that something was unresolvable.
        """
        hi = loc.max_interior_percentile
        lo = loc.min_interior_percentile
        out: dict[str, bool | None] = {}
        for side in self.fires_on:
            if side == "high":
                out["high"] = None if hi is None else hi >= self.threshold
            else:
                out["low"] = None if lo is None else lo <= 1.0 - self.threshold
        return out

    def resolvable(self, loc: Location) -> str | None:
        """``None`` if this reference can express this rule, else the prose why not.

        Four checks, in the order a reader should meet them. Each names the
        number it read, because "unresolvable" without the figure is the same
        opacity the round-2 artifact had.

        1. **Expressibility** (``require_expressible``), on **every tail the
           rule fires on** — see :attr:`fires_on` and
           :meth:`tail_expressibility`. The threshold must fall inside the
           attained interior percentile band on each of them. Failing this, the
           only plans that can fire are the ones outside the observed support,
           and the rule has stopped being a percentile rule.

           Round 3 found this check ORing the two tails, which is the bug it
           existed to prevent: a ``two_sided`` rule was declared resolvable when
           only the high tail was expressible and then answered ``False`` on
           plans in the low tail — the tail the reference provably cannot
           express. Those silent ``False``\\ s land on nulls, where they are
           counted as true negatives, so the bug **deflated FPR** and the FPR
           gate could pass on the strength of answers the arithmetic did not
           support. A two-sided rule is a claim about both tails and is
           resolvable only when both are expressible.

           **Why refuse rather than narrow to the expressible tail.** Narrowing
           is the other defensible repair and it is rejected on purpose: the
           direction of a one-sided test would then be chosen per metric, per
           plan, by tie multiplicities in the reference — a data-dependent
           hypothesis, and the resulting "FPR" would not be the false-positive
           rate of any rule that could be shipped. A caller who wants one tail
           declares ``Rule(tail="upper"|"lower")`` in advance, which is
           resolvable here and is recorded in ``rule.as_dict()`` like every
           other parameter. The refusal is not silence: the reason names both
           attained bounds, names the dead tail, and names that remedy.
        2. **Distinct reference items** against :attr:`required_distinct`.
        3. **Effective sample size** against :attr:`required_ess`.
        4. **A location that reports no resolution at all.** Refused rather than
           waved through: a percentile whose provenance is unstated is precisely
           what this check exists to catch, and defaulting an absent ESS to "fine"
           would reintroduce the bug in the check meant to prevent it.

        Raw ``min_n`` is *not* here — it is an eligibility screen in
        :func:`_screen`, kept separate because too few draws is a different
        complaint from draws that cannot express the threshold, and conflating
        them is how round 2 reported one when it meant the other.
        """
        if self.combination == "none":
            return None
        req_n = self.required_n
        if req_n is None:
            return (
                f"threshold {self.threshold:g} is not expressible by any finite "
                "reference: only a plan outside the observed support reaches it, "
                "which is a support test rather than a percentile test"
            )

        if self.require_expressible:
            hi = loc.max_interior_percentile
            lo = loc.min_interior_percentile
            if hi is None or lo is None:
                return (
                    "this location reports no interior percentile band, so "
                    "whether the reference can express the threshold is unknown"
                )
            reach = self.tail_expressibility(loc)
            dead = [name for name, ok in reach.items() if ok is False]
            if dead:
                which = " and ".join(f"{name} tail" for name in dead)
                these = "those tails" if len(dead) > 1 else "that tail"
                alive = [name for name, ok in reach.items() if ok is True]
                remedy = (
                    f" The {alive[0]} tail alone is expressible, so a one-sided "
                    f"rule — Rule(tail={'upper' if alive[0] == 'high' else 'lower'!r}) "
                    "— would resolve here; it has to be chosen in advance by a "
                    "caller who has decided which direction is being tested "
                    "for, because letting the reference pick the rule's "
                    "direction makes the test data-dependent."
                ) if alive else ""
                return (
                    f"the reference cannot express threshold {self.threshold:g} "
                    f"on the {which} of a {self.tail!r} rule: its interior "
                    f"percentiles reach only [{lo:.4g}, {hi:.4g}] over {loc.n} "
                    f"draws, so no plan inside the ensemble could fire on "
                    f"{these} and the rule degenerates into 'outside the "
                    f"observed support' there. It needs at least {req_n} draws "
                    f"with no tie at the extreme value." + remedy
                )

        distinct = loc.n_distinct_reference
        need_distinct = self.required_distinct
        if need_distinct is not None:
            if distinct is None:
                return (
                    "this location reports no distinct-item count, so the rule "
                    "cannot tell how much of the reference is repetition"
                )
            if distinct < need_distinct:
                return (
                    f"the reference holds {distinct} distinct "
                    f"{'plans' if loc.n_distinct_plans is not None else 'values'} "
                    f"over {loc.n} draws; threshold {self.threshold:g} needs at "
                    f"least {need_distinct}"
                )

        need_ess = self.required_ess
        if need_ess is not None:
            if loc.ess is None:
                return (
                    "this location reports no effective sample size, so the "
                    "rule cannot tell whether its draws are independent enough "
                    "to support the threshold"
                )
            if loc.ess < need_ess:
                return (
                    f"effective sample size {loc.ess:.4g} over {loc.n} raw draws "
                    f"(basis: {loc.ess_basis}); threshold {self.threshold:g} "
                    f"needs at least {need_ess:g}. Repeated draws inflate n "
                    "without adding resolution"
                )
        return None

    def resolution_requirement(self) -> dict[str, Any]:
        """The three numbers this rule needs from a reference, for the artifact."""
        return {
            "required_n": self.required_n,
            "required_distinct": self.required_distinct,
            "required_ess": self.required_ess,
            "require_expressible": self.require_expressible,
            "tails_that_must_be_expressible": list(self.fires_on),
            "min_n": self.min_n,
            "derivation": (
                "required_n = ceil(0.5 / (1 - max(t, 1 - t))) — the smallest "
                "reference whose interior mid-rank percentiles can reach the "
                "threshold t. required_distinct and required_ess default to the "
                "same figure; both are overridable per rule. Expressibility is "
                "required on EVERY tail the rule fires on — a two_sided rule "
                "with one dead tail is unresolvable, not half-answered."
            ),
        }

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
            f"(tail={self.tail}, untrusted={self.untrusted}, min_n={self.min_n}, "
            f"needs a reference with >= {self.required_distinct} distinct plans "
            f"and ESS >= {self.required_ess})"
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
            "min_distinct": self.min_distinct,
            "min_ess": self.min_ess,
            "require_expressible": self.require_expressible,
            "fires_on": list(self.fires_on),
            "resolution_requirement": self.resolution_requirement(),
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


#: A location this rule may fire on.
ELIGIBLE = "eligible"

#: A location this rule deliberately declines to read — no percentile at all, too
#: few draws, or a metric the trust policy rules out. A *narrowing*, decided in
#: advance and not a property of the reference's resolution.
EXCLUDED = "excluded"

#: A location whose reference cannot express this rule's threshold. **Not the
#: same as "not extreme."** The rule abstains; nothing about the plan has been
#: measured. See :meth:`Rule.resolvable`.
UNRESOLVABLE = "unresolvable"

SCREENS: tuple[str, ...] = (ELIGIBLE, EXCLUDED, UNRESOLVABLE)


def _screen(loc: Location, rule: Rule) -> tuple[str, str | None]:
    """``(screen, reason)`` — may this location fire, and if not, which kind of not.

    The order matters. Trust and measurability are checked first because they
    are decisions the caller made about the metric; resolution is checked last
    because it is a fact about the reference, and a metric excluded by policy
    was never going to fire whatever the reference looked like.
    """
    if loc.status != LOCATED:
        return EXCLUDED, f"no percentile ({loc.status})"
    if loc.n < rule.min_n:
        return EXCLUDED, f"only {loc.n} ensemble draws (rule.min_n={rule.min_n})"
    if loc.trusted is False and rule.untrusted == "exclude":
        return EXCLUDED, (
            "not trusted in this regime (CRITERIA.md section 5.1) and "
            "rule.untrusted='exclude'"
        )
    why = rule.resolvable(loc)
    if why is not None:
        return UNRESOLVABLE, why
    return ELIGIBLE, None


def _fire(loc: Location, rule: Rule) -> MetricFiring | None:
    """Does this eligible location cross the rule's threshold?

    The comparison is ``metric_statistic(loc, rule) >= rule.threshold`` and
    nothing else, so the quantity :func:`outlierness` ranks by and the quantity
    this thresholds cannot drift apart — round 3 found them already apart, with
    the AUC computed over ``1 - two_sided_p`` while the flag was decided on the
    mid-rank percentile. Two expressions of one rule is one expression too many.
    """
    p = loc.percentile
    assert p is not None  # guaranteed by _screen
    stat = metric_statistic(loc, rule)
    if stat is None or stat < rule.threshold:
        return None
    # Which tail it fired on. Under a one-sided rule the answer is the rule's
    # own tail; under two_sided a threshold of 0.5 or below makes both sides
    # true at once, so the exact centre is broken as "high".
    if rule.tail == "upper":
        side = "high"
    elif rule.tail == "lower":
        side = "low"
    else:
        side = "high" if p >= 0.5 else "low"
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

    ``flagged`` is **three-valued**:

    ``True``   at least the required number of eligible metrics fired
    ``False``  the rule was evaluated and did not fire
    ``None``   the rule could not be evaluated — every metric was excluded, or
               the reference cannot express the threshold (``unresolvable``)

    ``None`` is not ``False``. A rule that abstains has made no measurement, and
    counting an abstention as a correct rejection is how a detector passes a
    false-positive gate by being unable to look. ``None`` is falsy, so
    ``if decision.flagged`` still reads the conservative way, while every
    consumer that tallies outcomes has to notice the third case. Round 2's
    artifact had no third case and reported abstentions as clean.
    """

    flagged: bool | None
    rule: Rule
    fired: tuple[MetricFiring, ...] = ()
    eligible: tuple[str, ...] = ()
    excluded: tuple[tuple[str, str], ...] = ()
    unresolvable: tuple[tuple[str, str], ...] = ()
    reason: str = ""

    @property
    def fired_metrics(self) -> tuple[str, ...]:
        return tuple(f.metric for f in self.fired)

    @property
    def resolved(self) -> bool:
        """True when the rule was actually evaluated."""
        return self.flagged is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "flagged": self.flagged,
            "resolved": self.resolved,
            "rule": self.rule.as_dict(),
            "fired": [f.as_dict() for f in self.fired],
            "fired_metrics": list(self.fired_metrics),
            "eligible": list(self.eligible),
            "excluded": {name: why for name, why in self.excluded},
            "unresolvable": {name: why for name, why in self.unresolvable},
            "reason": self.reason,
        }


def flag(
    locations: Mapping[str, Location],
    rule: Rule = DEFAULT_RULE,
    *,
    for_scenario: bool = True,
) -> FlagDecision:
    """Apply ``rule`` to per-metric locations. The only place a flag is decided.

    ``locations`` is ``outlier.locate``'s return value. ``rule`` defaults to
    :data:`DEFAULT_RULE` and is carried on the result, so no decision in this
    repository exists without its rule attached.

    Metrics with no percentile — undefined values, degenerate metrics, ensembles
    too small — are **excluded with a reason**, never treated as unremarkable.
    That distinction is the whole point of ``outlier``'s statuses: an absent
    percentile is not a percentile of 0.5.

    Empty eligibility returns ``flagged=None`` — the rule abstains. Two things
    are folded into that one answer and both are deliberate:

    * Under ``"all"`` it is the choice against vacuous truth: "every eligible
      metric fired" is trivially satisfied by no metrics at all, and a detector
      that fires hardest when it can measure least is worse than useless.
    * Under every combination it is the refusal to report an abstention as a
      clean bill of health. Round 2 returned ``False`` here, so a plan the
      detector could not look at was counted as correctly not flagged.

    ``NEVER_FLAG`` is the one rule that still returns ``False`` on empty
    eligibility, because it is defined by its output rather than by reading
    anything: it is a control, and a control that abstains cannot serve as the
    floor the gates are checked against.

    ``for_scenario=False`` refuses to decide at all
    ----------------------------------------------

    A flag is only meaningful against a manufactured label — that is the whole
    justification for a boolean existing in this repository (see the module
    docstring). Pass ``for_scenario=False`` for a plan that carries no such
    label, above all a real enacted map, and this returns ``flagged=None`` with
    a reason pointing at ``outlier.review_report``, which reports the plan's
    location per metric and has no boolean in it.

    Round 2's artifact published ``plan_under_review.flagged = true`` — a verdict
    on Iowa's in-force CD118 plan, which README.md and CRITERIA.md section 11
    both forbid. The parameter exists so that the correct call is available and
    the incorrect one is named in the code rather than only in a document.
    """
    if not for_scenario:
        return FlagDecision(
            flagged=None,
            rule=rule,
            reason=(
                "REFUSED — this plan carries no manufactured ground truth, so a "
                "flag on it could not be scored as a true or false positive and "
                "would read as a verdict rather than a distribution (README.md, "
                "CRITERIA.md section 11). Use outlier.review_report to report "
                "where it sits in the ensemble, per metric, with the trusted "
                "set named."
            ),
        )
    names = (
        list(locations) if rule.metrics is None
        else [m for m in rule.metrics]
    )

    eligible: list[str] = []
    excluded: list[tuple[str, str]] = []
    unresolvable: list[tuple[str, str]] = []
    fired: list[MetricFiring] = []

    for name in names:
        loc = locations.get(name)
        if loc is None:
            excluded.append((name, "not present in locations"))
            continue
        screen, why = _screen(loc, rule)
        if screen == UNRESOLVABLE:
            unresolvable.append((name, why or "unresolvable"))
            continue
        if screen == EXCLUDED:
            excluded.append((name, why or "excluded"))
            continue
        eligible.append(name)
        hit = _fire(loc, rule)
        if hit is not None:
            fired.append(hit)

    n_fired = len(fired)
    n_eligible = len(eligible)

    flagged: bool | None
    if rule.combination == "none":
        flagged = False
        reason = "rule never flags (null detector)"
    elif n_eligible == 0:
        flagged = None
        parts = [f"{m}: {w}" for m, w in unresolvable] + [
            f"{m}: {w}" for m, w in excluded
        ]
        reason = (
            "UNRESOLVED — no metric was eligible to fire, so this rule made no "
            "measurement of this plan. This is not a finding that the plan is "
            "typical: "
            + ("; ".join(parts) or "no metrics given")
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
    if unresolvable and flagged is not None:
        reason += (
            "; "
            + str(len(unresolvable))
            + " metric(s) unresolvable and not read: "
            + "; ".join(f"{m}: {w}" for m, w in unresolvable)
        )

    return FlagDecision(
        flagged=flagged,
        rule=rule,
        fired=tuple(fired),
        eligible=tuple(eligible),
        excluded=tuple(excluded),
        unresolvable=tuple(unresolvable),
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


# --------------------------------------------------------------------------- #
# the continuous score the rule reads, and the AUC over it
# --------------------------------------------------------------------------- #

def metric_statistic(loc: Location, rule: Rule = DEFAULT_RULE) -> float | None:
    """The quantity ``rule`` compares against its threshold, for one metric.

    ``percentile`` under ``tail="upper"``, ``1 - percentile`` under ``"lower"``,
    ``max(percentile, 1 - percentile)`` under ``"two_sided"`` — the three forms
    of "fires when ``p >= t``, when ``p <= 1 - t``, or on either" written as one
    comparison, ``statistic >= threshold``. :func:`_fire` calls this rather than
    restating the comparison, and :func:`outlierness` maximises it, so the flag
    and the ranking are the same arithmetic by construction. ``None`` when the
    location carries no percentile.

    This is deliberately **not** ``1 - two_sided_p``. The two agree only when
    nothing in the reference ties the plan's value; ``two_sided_p`` is computed
    inclusively (``2 * min(#{x <= v}, #{x >= v}) / n``) while the rule reads the
    mid-rank percentile, so on any metric with ties — ``cut_edges``,
    ``county_splits``, seat counts, and every partisan metric on a reference
    holding duplicate plans — they are different numbers *and can rank two plans
    in opposite orders*. Round 3 found the AUC round 2 called "the decisive
    number" being computed over the inclusive statistic while the flag was
    decided on the mid-rank one, so the ROC belonged to a rule nobody ships.
    """
    p = loc.percentile
    if p is None:
        return None
    if rule.tail == "upper":
        return float(p)
    if rule.tail == "lower":
        return 1.0 - float(p)
    return max(float(p), 1.0 - float(p))


def outlierness(
    locations: Mapping[str, Location], rule: Rule = DEFAULT_RULE
) -> float | None:
    """The continuous quantity ``rule`` thresholds, in ``[0, 1]``. ``None`` if unmeasurable.

    :func:`metric_statistic`, maximised over the metrics the rule is willing to
    read. Under ``"any"`` — the default — thresholding this at ``rule.threshold``
    itself reproduces :func:`flag` exactly, so it is the rule's own statistic and
    not a parallel scoring function invented for the plot. Under ``two_sided``
    it runs on ``[0.5, 1]``, which is what a symmetric rule's statistic is; under
    a one-sided rule on ``[0, 1]``.

    Two deliberate departures from :func:`flag`'s screening:

    * **Threshold expressibility is not applied.** Whether a reference can
      express 0.99 is a fact about a threshold; a *ranking* of plans by
      outlierness is well defined however coarse the reference is. Excluding
      unresolvable locations here would make :func:`auc` uncomputable in exactly
      the regime where it is most needed — round 2's, where the rule scored 0.25
      and nothing said so. The coarseness does not vanish: it is reported beside
      the AUC as ``ess`` and ``n_distinct``.
    * **Combination is ignored.** ``"all"`` and ``"k_of_n"`` threshold a count of
      firings, not a max; ranking by the maximum is the ``"any"`` statistic in
      every case. :func:`auc` says so in its own output, and a caller wanting the
      ROC of a ``k_of_n`` rule needs a different score than this one.

    ``NEVER_FLAG`` and any ``"none"`` rule return ``None`` for every plan: they
    read nothing, so they induce no ranking, and their statistic AUC is
    undefined rather than 0.5 — a degenerate score is not manufactured to fill
    the hole. ``ALWAYS_FLAG``, by contrast, reads *everything*: its statistic
    AUC is the statistic's own, which is why 0.5 is not a floor on that number
    and :func:`auc` says so.
    """
    if rule.combination == "none":
        return None
    names = list(locations) if rule.metrics is None else list(rule.metrics)
    best: float | None = None
    for name in names:
        loc = locations.get(name)
        if loc is None or loc.status != LOCATED:
            continue
        if loc.n < rule.min_n:
            continue
        if loc.trusted is False and rule.untrusted == "exclude":
            continue
        score = metric_statistic(loc, rule)
        if score is None:
            continue
        if best is None or score > best:
            best = score
    return best


def auc(scenarios: Iterable[Any], rule: Rule = DEFAULT_RULE) -> dict[str, Any]:
    """Area under the ROC curve for planted-versus-null, over :func:`outlierness`.

    The Mann-Whitney statistic: the probability that a randomly chosen planted
    plan outranks a randomly chosen null, with ties counted as half. 1.0 is
    perfect separation, 0.5 is a coin flip, and **below 0.5 means the ranking is
    inverted** — the detector calls neutral maps more gerrymandered than the
    planted ones. Round 2's shipped rule scored 0.25 and the number appeared in
    no gate, no report line and none of the five plots.

    **This is the AUC of the statistic, not of the detector, and it has no
    constant-detector floor.** A rule whose *score* is constant would sit at 0.5
    because every pair ties — but neither shipped constant is one of those:
    ``ALWAYS_FLAG`` reads the same percentiles every rule reads and throws them
    away at a threshold of 0.0, so its ``value`` is whatever the statistic is
    worth on the set (1.0 on ``tests.calibrated_scenarios``), and ``NEVER_FLAG``
    reads nothing and returns ``None``. The number a constant cannot beat is
    ``decision_auc`` (:func:`_auc_with_decision`), which is exactly 0.5 for
    both, and that is the one ``beats_baselines`` compares against 0.5. Round 3
    asserted the floor for ``value`` and it is false; the assertion mattered
    because :func:`report_lines` printed the floor beside it.

    Returns ``value`` plus everything needed to distrust it: the class counts
    actually scored, how many scenarios produced no score at all, the tie count,
    ``coin_flip`` (0.5, stated rather than assumed) and ``constant_baseline``,
    which is ``None`` with a note saying why the concept does not apply to this
    number. ``value`` is ``None`` when either class has no scored member — a
    rate over no pairs is a measurement that was not made.
    """
    rows = _scenarios(scenarios)
    pos: list[float] = []
    neg: list[float] = []
    unscored_pos = unscored_neg = 0
    for scenario in rows:
        score = outlierness(scenario.locations, rule)
        if scenario.is_positive:
            if score is None:
                unscored_pos += 1
            else:
                pos.append(score)
        else:
            if score is None:
                unscored_neg += 1
            else:
                neg.append(score)

    pairs = len(pos) * len(neg)
    value: float | None = None
    ties = 0
    if pairs:
        wins = 0.0
        for a in pos:
            for b in neg:
                if a > b:
                    wins += 1.0
                elif a == b:
                    wins += 0.5
                    ties += 1
        value = wins / pairs

    note = "no scored pairs" if not pairs else (
        "AUC < 0.5 means the ranking is inverted: neutral maps score as more "
        "outlying than planted ones"
        if value is not None and value < 0.5
        else "0.5 is the coin-flip value for a ranking. It is NOT the "
        "constant-detector floor: always-flag reads this same statistic and "
        "scores 1.0 on a separable set — decision_auc is the number both "
        "constants sit at 0.5 on"
    )
    return {
        "value": value,
        "coin_flip": 0.5,
        "constant_baseline": None,
        "constant_baseline_note": (
            "no constant-detector floor exists for this number: a constant "
            "*decision* is not a constant *score*. always-flag reads the same "
            "statistic every rule reads and scores whatever that statistic is "
            "worth on the set — 1.0 where it separates the classes — so it can "
            "tie or beat the shipped rule here. The 0.5 constant floor belongs "
            "to decision_auc, which is reported beside this."
        ),
        "beats_coin_flip": None if value is None else value > 0.5,
        "n_positive_scored": len(pos),
        "n_null_scored": len(neg),
        "n_positive_unscored": unscored_pos,
        "n_null_unscored": unscored_neg,
        "n_pairs": pairs,
        "n_tied_pairs": ties,
        "score": (
            "max over readable metrics of the statistic this rule thresholds: "
            "max(percentile, 1 - percentile) under two_sided, percentile under "
            "upper, 1 - percentile under lower. Thresholding it at "
            "rule.threshold reproduces flag() under combination='any'. Not "
            "1 - two_sided_p, which differs from it wherever the plan's value "
            "is tied in the reference"
        ),
        "score_threshold": rule.threshold,
        "rule": rule.describe(),
        "note": note,
    }


def decide(
    scenarios: Iterable[Any], rule: Rule = DEFAULT_RULE
) -> list[tuple[Scenario, FlagDecision]]:
    """Run ``rule`` over every scenario, keeping the decisions intact."""
    return [(s, flag(s.locations, rule)) for s in _scenarios(scenarios)]


#: The two constant detectors, scored beside every matrix. See the module
#: docstring: a gate a constant ties is not a measurement, and a baseline filed
#: under diagnostics is not a baseline.
BASELINE_RULES: tuple[Rule, ...] = (ALWAYS_FLAG, NEVER_FLAG)


def confusion_matrix(
    scenarios: Iterable[Any],
    rule: Rule = DEFAULT_RULE,
    *,
    with_baselines: bool = True,
) -> dict[str, Any]:
    """The full confusion matrix for ``rule``, with both constant detectors beside it.

    Returns counts (``tp``, ``fp``, ``tn``, ``fn``), the abstention counts
    (``unresolved_positive``, ``unresolved_null``), the rates derived from them,
    Wilson intervals for the two that are gated, worst/best-case bounds over the
    unresolved cases, the rule, a per-scenario row for every case, a tally of
    which metrics fired on positives versus on nulls, the ``auc``, and the
    ``baselines`` block.

    **No accuracy key and no F1**, for the reason they were banned in round 1: on
    a scenario set that is mostly nulls both constants post a respectable
    accuracy. ``auc`` and ``youden_j`` are here instead. Two of the three numbers
    they carry — ``auc["decision_auc"]`` and ``youden_j`` — are exactly 0.5 and
    exactly 0.0 for both constants by construction, so neither can flatter one.
    ``auc["value"]``, the AUC of the underlying statistic, **has no such floor**:
    ``ALWAYS_FLAG`` sees the same statistic every rule sees and scores 1.0 on a
    well-separated set. Round 3's docstring claimed the floor for all of it and
    was wrong; see the module docstring.

    ``tpr`` and ``fpr`` are ``None`` when no case of the class was **resolved**.
    Not 0.0, not 1.0: a rate over no cases is a measurement that was not made.
    They are conditional on resolution — ``tp / (tp + fn)`` — and are therefore
    *not* the whole story when the rule abstained on part of the class, which is
    what ``tpr_bounds`` and ``fpr_bounds`` exist for: worst case counts every
    abstention against the rule, best case counts every one for it. The gates
    read the bounds so that abstaining cannot pass a gate.

    ``baselines`` carries the same matrix for :data:`ALWAYS_FLAG` and
    :data:`NEVER_FLAG` (computed with ``with_baselines=False``, which is the only
    reason that parameter exists), and ``beats_baselines`` states whether this
    rule is better than both.

    The metric tally is the diagnostic that separates the two ways a detector
    fails. A detector firing on the same metric for planted and null plans alike
    has learned the metric's geography-driven baseline, which CRITERIA.md
    section 5.4 says exists in Iowa; one that fires on different metrics for the
    two classes is at least responding to the plant.
    """
    rows_in = _scenarios(scenarios)
    decisions = decide(rows_in, rule)

    tp = fp = tn = fn = 0
    unresolved_positive = unresolved_null = 0
    rows: list[dict[str, Any]] = []
    fired_positive: dict[str, int] = {}
    fired_null: dict[str, int] = {}

    for scenario, decision in decisions:
        flagged = decision.flagged
        if scenario.is_positive:
            if flagged is None:
                unresolved_positive += 1
            elif flagged:
                tp += 1
            else:
                fn += 1
            tally = fired_positive
        else:
            if flagged is None:
                unresolved_null += 1
            elif flagged:
                fp += 1
            else:
                tn += 1
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
                "flagged": flagged,
                "resolved": decision.resolved,
                "outcome": _outcome(scenario.is_positive, flagged),
                "outlierness": outlierness(scenario.locations, rule),
                "fired_metrics": list(decision.fired_metrics),
                "excluded": {m: w for m, w in decision.excluded},
                "unresolvable": {m: w for m, w in decision.unresolvable},
                "reason": decision.reason,
            }
        )

    n_positive = tp + fn + unresolved_positive
    n_null = fp + tn + unresolved_null
    n_resolved = tp + fn + fp + tn
    tpr = _rate(tp, tp + fn)
    fpr = _rate(fp, fp + tn)

    matrix: dict[str, Any] = {
        "rule": rule.as_dict(),
        "n": n_positive + n_null,
        "n_positive": n_positive,
        "n_null": n_null,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "unresolved_positive": unresolved_positive,
        "unresolved_null": unresolved_null,
        "n_resolved": n_resolved,
        "coverage": _rate(n_resolved, n_positive + n_null),
        "tpr": tpr,
        "fnr": _rate(fn, tp + fn),
        "fpr": fpr,
        "tnr": _rate(tn, fp + tn),
        "tpr_ci95": wilson_interval(tp, tp + fn),
        "fpr_ci95": wilson_interval(fp, fp + tn),
        "tpr_bounds": _bounds(tp, unresolved_positive, n_positive),
        "fpr_bounds": _bounds(fp, unresolved_null, n_null),
        "rates_note": (
            "tpr and fpr are conditional on the rule having resolved the case. "
            "unresolved_* count cases where it abstained because the reference "
            "could not express its threshold; those are neither correct nor "
            "incorrect and are never folded into tn or fn. *_bounds give the "
            "worst and best case over them, and the gates read the bounds."
        ),
        "youden_j": None if (tpr is None or fpr is None) else tpr - fpr,
        "youden_j_note": (
            "TPR - FPR at this rule's operating point. Exactly 0.0 for both "
            "constant detectors, which is why it is reported: it is one of the "
            "two numbers a constant cannot tie. Not an accuracy and not a "
            "fairness score — see the module docstring."
        ),
        "auc": _auc_with_decision(rows_in, rule, tpr, fpr),
        "fired_on_positives": dict(sorted(fired_positive.items())),
        "fired_on_nulls": dict(sorted(fired_null.items())),
        "scenarios": rows,
    }

    if with_baselines:
        matrix["baselines"] = {
            baseline.name or baseline.describe(): _baseline_block(rows_in, baseline)
            for baseline in BASELINE_RULES
        }
        matrix["beats_baselines"] = _beats_baselines(matrix)
    return matrix


def _auc_with_decision(
    scenarios: Sequence[Scenario],
    rule: Rule,
    tpr: float | None,
    fpr: float | None,
) -> dict[str, Any]:
    """:func:`auc` plus ``decision_auc`` — and the two are different numbers.

    ``value`` is the AUC of the rule's continuous statistic: how well
    :func:`outlierness` *ranks* planted above null, over every threshold the
    statistic could take. ``decision_auc`` is the area under the ROC through the
    rule's single shipped operating point, ``(1 + TPR - FPR)/2``.

    Both matter and they answer different questions. ``ALWAYS_FLAG`` has access
    to the same statistic every rule does — on a well-behaved scenario set its
    ``value`` is 1.0 — and throws all of it away at a threshold of 0.0, which is
    why its ``decision_auc`` is exactly 0.5. The constant-detector floor is a
    claim about decisions, so it is ``decision_auc`` that is 0.5 for both
    constants, and ``decision_auc`` that the baseline block reports.
    """
    block = auc(scenarios, rule)
    j = None if (tpr is None or fpr is None) else tpr - fpr
    block["decision_auc"] = None if j is None else 0.5 * (1.0 + j)
    block["decision_auc_note"] = (
        "area under the ROC through this rule's one operating point, "
        "(1 + TPR - FPR)/2. Exactly 0.5 for always-flag and for never-flag, "
        "which is the floor 'beats both baselines' is measured against. "
        "'value' above is the AUC of the underlying statistic and can be high "
        "for a rule whose threshold discards it."
    )
    return block


def _bounds(hits: int, unresolved: int, n_class: int) -> dict[str, Any] | None:
    """Worst/best-case rate over the whole class, counting abstentions both ways.

    ``None`` when the class is empty. ``worst`` counts every abstention as a
    hit, ``best`` as a miss — for the TPR gate the *worst* number is the lower
    bound and for the FPR gate it is the upper, so :func:`gates` reads
    ``lower``/``upper`` rather than these names.
    """
    if n_class == 0:
        return None
    return {
        "lower": hits / n_class,
        "upper": (hits + unresolved) / n_class,
        "n_class": n_class,
        "unresolved": unresolved,
        "note": (
            "lower counts every abstention as a non-hit, upper as a hit. They "
            "coincide when the rule resolved every case."
        ),
    }


def _baseline_block(scenarios: Sequence[Scenario], rule: Rule) -> dict[str, Any]:
    """One constant detector's matrix and curve summary, for the comparison block."""
    matrix = confusion_matrix(scenarios, rule, with_baselines=False)
    curve = detection_curve(scenarios, rule)
    return {
        "rule": rule.describe(),
        "tp": matrix["tp"],
        "fp": matrix["fp"],
        "tn": matrix["tn"],
        "fn": matrix["fn"],
        "unresolved_positive": matrix["unresolved_positive"],
        "unresolved_null": matrix["unresolved_null"],
        "tpr": matrix["tpr"],
        "fpr": matrix["fpr"],
        "youden_j": matrix["youden_j"],
        "auc": matrix["auc"]["decision_auc"],
        "statistic_auc": matrix["auc"]["value"],
        "tpr_at_gate_shift": tpr_at(curve, GATE_SEAT_SHIFT),
        "min_detectable_seat_shift": min_detectable_seat_shift(curve),
    }


def _beats_baselines(matrix: Mapping[str, Any]) -> dict[str, Any]:
    """Does this rule beat both constants? A derived quantity, never a gate.

    Two independent comparisons, because they can disagree and the disagreement
    is informative:

    ``ranking``
        ``auc["value"] > 0.5``. A rule whose statistic AUC exceeds 0.5 has
        *some* threshold at which TPR > FPR, and therefore some threshold whose
        ``decision_auc`` beats both constants' 0.5 — even if the threshold it
        currently ships does not. Round 2's rule scored 0.25, so no threshold on
        its statistic would have. The 0.5 compared against here is the coin-flip
        value of a ranking, **not** a score either constant posts: always-flag
        reads the same statistic and scores it at whatever it is worth.
    ``operating_point``
        ``youden_j > 0``, i.e. TPR > FPR at the threshold the rule actually
        ships. Both constants sit at exactly 0.

    ``verdict`` is ``True`` only when both hold and ``False`` as soon as either
    definitely fails — an inverted ranking is not rescued by an unmeasurable
    operating point. ``None`` means one was unmeasurable and neither failed. It
    is reported, not gated: CRITERIA.md section 8 lists the gates
    and this is not among them, and adding it as a gate would create one more
    number to tune against.
    """
    auc_block = matrix.get("auc") or {}
    auc_value = auc_block.get("value")
    j = matrix.get("youden_j")
    ranking = None if auc_value is None else auc_value > 0.5
    operating = None if j is None else j > 0.0
    if ranking is False or operating is False:
        verdict = False        # one failure settles it; the other cannot rescue it
    elif ranking is None or operating is None:
        verdict = None
    else:
        verdict = True
    return {
        "verdict": verdict,
        "ranking": {
            "auc": auc_value,
            "coin_flip": 0.5,
            "compared_against": (
                "the coin-flip value of a ranking, not a constant detector's "
                "score — see auc.constant_baseline_note"
            ),
            "beats": ranking,
        },
        "operating_point": {
            "youden_j": j,
            "always_flag_youden_j": 0.0,
            "never_flag_youden_j": 0.0,
            "beats": operating,
        },
        "gated": False,
        "note": (
            "reported, not gated. A rule that does not beat both constants has "
            "not been shown to detect anything, whatever its gates say: "
            "always-flag tied both of round 1's passing gates."
        ),
    }


def _outcome(is_positive: bool, flagged: bool | None) -> str:
    if flagged is None:
        return "unresolved_positive" if is_positive else "unresolved_null"
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

    Rows carry ``seats``, ``n``, ``flagged``, ``unresolved``, ``n_resolved``,
    ``tpr`` (over resolved cases), ``tpr_bounds`` (worst/best over the whole
    bucket), ``ci95``, the ids in the bucket, and ``by_direction`` — the R-favouring and D-favouring counts, kept
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
                "unresolved": 0,
                "ids": [],
                "by_direction": {"R": 0, "D": 0, "unspecified": 0},
                "realized_seat_shifts": [],
            },
        )
        row["n"] += 1
        if decision.flagged is None:
            row["unresolved"] += 1
        else:
            row["flagged"] += int(decision.flagged)
        row["ids"].append(scenario.id)
        key = scenario.target_party if scenario.target_party in ("R", "D") else "unspecified"
        row["by_direction"][key] += 1
        row["realized_seat_shifts"].append(scenario.realized_seat_shift)

    out = []
    for seats in sorted(rows):
        row = rows[seats]
        resolved = row["n"] - row["unresolved"]
        row["n_resolved"] = resolved
        row["tpr"] = _rate(row["flagged"], resolved)
        row["ci95"] = wilson_interval(row["flagged"], resolved)
        row["tpr_bounds"] = _bounds(row["flagged"], row["unresolved"], row["n"])
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

    Buckets are read at their **worst case** — an unresolved scenario counts as
    undetected — so a rule cannot lower its published minimum by abstaining. On a
    curve where every case resolved, that is the plain TPR.

    ``require_monotone`` (default true) additionally demands that every larger
    magnitude measured also clears the target. Without it, one lucky bucket
    reports a smaller minimum than the curve supports — a 1-seat bucket of three
    scenarios that happens to score 1.00 while the 2-seat bucket scores 0.90
    would publish "minimum detectable shift: 1", which the next line of the same
    table contradicts. Set it false to see the raw first crossing.
    """
    def rate(row: Mapping[str, Any]) -> float | None:
        """Worst-case TPR for the bucket: abstentions count as misses.

        A magnitude the detector declined to answer at has not been shown to be
        detectable at that magnitude, and reading the conditional rate over the
        cases it did answer would let a rule publish a smaller minimum by
        abstaining on the hard ones.
        """
        bounds = row.get("tpr_bounds")
        if isinstance(bounds, Mapping) and bounds.get("lower") is not None:
            return float(bounds["lower"])
        return row.get("tpr")

    rows = sorted(
        (r for r in curve if rate(r) is not None), key=lambda r: r["seats"]
    )
    for i, row in enumerate(rows):
        if rate(row) < target_tpr:
            continue
        if require_monotone and any(rate(r) < target_tpr for r in rows[i + 1:]):
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
    CRITERIA.md section 8 says to report it and not gate it. ``auc``,
    ``baselines``, ``beats_baselines`` and ``coverage`` are here on the same
    terms — reported, not gated — and they are *here* rather than under
    diagnostics because round 2 put the constant detectors under diagnostics and
    nothing that reads the gates ever saw them.

    ``pass`` is read off ``bounds``, not off ``value``: for the TPR gate the
    lower bound (every abstention a missed plant) and for the FPR gate the upper
    (every abstention a null that might have fired). A rule that cannot evaluate
    a case has not passed anything on that case, and reading the conditional
    rate would let a detector clear both gates by abstaining on everything hard.
    """
    rows_in = _scenarios(scenarios)
    matrix = confusion_matrix(rows_in, rule)
    curve = detection_curve(rows_in, rule)
    tpr = tpr_at(curve, seat_shift)
    fpr = matrix["fpr"]

    bucket = next((r for r in curve if r["seats"] == seat_shift), None)
    tpr_bounds = bucket["tpr_bounds"] if bucket else None
    fpr_bounds = matrix["fpr_bounds"]

    # The gate reads the bound that is worst for the rule: an abstention must
    # never help. For TPR that is the lower bound (abstention = missed plant);
    # for FPR the upper (abstention = a null that might have been flagged).
    tpr_pass = None if tpr_bounds is None else tpr_bounds["lower"] >= tpr_gate
    fpr_pass = None if fpr_bounds is None else fpr_bounds["upper"] <= fpr_gate

    unresolved_note = (
        "pass is read off the bound that is worst for the rule, so abstaining "
        "cannot pass a gate. value is the rate over the cases the rule actually "
        "resolved and can be better than the bound."
    )
    return {
        "rule": rule.as_dict(),
        f"tpr_at_{seat_shift}seat": {
            "target": tpr_gate,
            "value": tpr,
            "bounds": tpr_bounds,
            "pass": tpr_pass,
            "n": bucket["n"] if bucket else 0,
            "unresolved": bucket["unresolved"] if bucket else 0,
            "note": (
                f"no planted scenarios at a {seat_shift}-seat shift"
                if bucket is None else unresolved_note
            ),
        },
        "fpr_on_nulls": {
            "target": fpr_gate,
            "value": fpr,
            "bounds": fpr_bounds,
            "pass": fpr_pass,
            "n": matrix["n_null"],
            "unresolved": matrix["unresolved_null"],
            "note": (
                "no null scenarios" if fpr_bounds is None else unresolved_note
            ),
        },
        "min_detectable_seat_shift": {
            "value": min_detectable_seat_shift(curve, tpr_gate),
            "target_tpr": tpr_gate,
            "gated": False,
            "note": "CRITERIA.md section 8: report, do not gate",
        },
        "auc": {
            **matrix["auc"],
            "gated": False,
            "note": (
                matrix["auc"]["note"]
                + ". Reported, not gated — a first-class number, not a "
                "diagnostic: a rule with AUC below 0.5 ranks neutral maps as "
                "more gerrymandered than planted ones whatever its gates say."
            ),
        },
        "baselines": matrix["baselines"],
        "beats_baselines": matrix["beats_baselines"],
        "coverage": {
            "value": matrix["coverage"],
            "n_resolved": matrix["n_resolved"],
            "n": matrix["n"],
            "unresolved_positive": matrix["unresolved_positive"],
            "unresolved_null": matrix["unresolved_null"],
            "gated": False,
            "note": (
                "the fraction of scenarios on which the rule could be evaluated "
                "at all. Below 1.0 the reference cannot express the rule's "
                "threshold on some cases; the requirement is in "
                "rule.resolution_requirement."
            ),
        },
    }


def report_lines(matrix: Mapping[str, Any], curve: Sequence[Mapping[str, Any]]) -> list[str]:
    """Human-readable confusion report. Both rates, the two constants, and the AUC.

    The baseline lines are not optional and not at the bottom. Round 2's report
    had neither them nor the AUC, so a reader could work through the whole thing
    without learning that a detector flagging everything scored the same on the
    gates and that the shipped rule's ranking was inverted.

    **Two AUC lines, not one.** Round 3 printed the statistic AUC annotated
    "constant-detector floor 0.5", which is false for that number: always-flag's
    statistic AUC is 1.0 wherever the statistic separates the classes, so the
    line invited a reader to conclude a rule had beaten a constant it had in
    fact tied. Both numbers are now printed, each with the floor that is
    actually its own, and the baseline lines print the constants' statistic AUC
    beside their decision AUC so the claim can be checked on the same page.
    """
    lines = [
        f"rule: {matrix['rule']['describe']}",
        f"scenarios: {matrix['n']} ({matrix['n_positive']} planted, "
        f"{matrix['n_null']} null)",
        f"          flagged   not flagged   unresolved",
        f"planted   {matrix['tp']:>7}   {matrix['fn']:>11}   "
        f"{matrix['unresolved_positive']:>10}",
        f"null      {matrix['fp']:>7}   {matrix['tn']:>11}   "
        f"{matrix['unresolved_null']:>10}",
        f"TPR = {_fmt(matrix['tpr'])}  (95% CI {_fmt_ci(matrix['tpr_ci95'])})"
        f"  worst/best over unresolved {_fmt_bounds(matrix['tpr_bounds'])}",
        f"FPR = {_fmt(matrix['fpr'])}  (95% CI {_fmt_ci(matrix['fpr_ci95'])})"
        f"  worst/best over unresolved {_fmt_bounds(matrix['fpr_bounds'])}",
        f"coverage = {_fmt(matrix['coverage'])} "
        f"({matrix['n_resolved']}/{matrix['n']} scenarios the rule could evaluate)",
    ]
    for row in curve:
        lines.append(
            f"  {row['seats']}-seat shift: TPR {_fmt(row['tpr'])} "
            f"({row['flagged']}/{row['n_resolved']} resolved of {row['n']}, "
            f"95% CI {_fmt_ci(row['ci95'])})"
        )
    mds = min_detectable_seat_shift(curve)
    lines.append(
        "minimum detectable seat shift: "
        + ("not reached at any measured magnitude" if mds is None else str(mds))
        + "  [reported, not gated]"
    )

    auc_block = matrix.get("auc") or {}
    lines.append(
        f"AUC (planted vs null, on the rule's own statistic) = "
        f"{_fmt(auc_block.get('value'))}  [coin flip 0.5; NOT a "
        f"constant-detector floor — always-flag reads this same statistic, see "
        f"the baselines' statistic AUC below; reported, not gated]"
    )
    lines.append(f"  {auc_block.get('note', '')}")
    lines.append(
        f"decision AUC (through this rule's operating point) = "
        f"{_fmt(auc_block.get('decision_auc'))}  [both constant detectors score "
        f"exactly 0.5 — this is the floor]"
    )
    lines.append(
        f"Youden J = TPR - FPR = {_fmt(matrix.get('youden_j'))}  "
        "[both constant detectors score exactly 0.0]"
    )

    baselines = matrix.get("baselines") or {}
    if baselines:
        lines.append("baselines scored on the same scenarios:")
        for name, block in baselines.items():
            lines.append(
                f"  {name:<12} TPR {_fmt(block['tpr'])}  FPR {_fmt(block['fpr'])}  "
                f"J {_fmt(block['youden_j'])}  decision AUC {_fmt(block['auc'])}  "
                f"statistic AUC {_fmt(block['statistic_auc'])}  "
                f"min detectable shift "
                f"{block['min_detectable_seat_shift'] if block['min_detectable_seat_shift'] is not None else 'none'}"
            )
    beats = matrix.get("beats_baselines") or {}
    if beats:
        verdict = beats.get("verdict")
        word = {True: "YES", False: "NO", None: "NOT MEASURED"}[verdict]
        lines.append(
            f"does the rule beat both constant detectors? {word} "
            f"(ranking: AUC {_fmt(beats['ranking']['auc'])} vs 0.5; "
            f"operating point: J {_fmt(beats['operating_point']['youden_j'])} vs 0.0)"
            "  [reported, not gated]"
        )
    return lines


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.4f}"


def _fmt_ci(ci: Sequence[float] | None) -> str:
    return "n/a" if ci is None else f"{ci[0]:.3f}-{ci[1]:.3f}"


def _fmt_bounds(bounds: Mapping[str, Any] | None) -> str:
    if not bounds:
        return "n/a"
    return f"{bounds['lower']:.4f}/{bounds['upper']:.4f}"


__all__ = [
    "TAILS",
    "SCREENS",
    "ELIGIBLE",
    "EXCLUDED",
    "UNRESOLVABLE",
    "BASELINE_RULES",
    "metric_statistic",
    "outlierness",
    "auc",
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
