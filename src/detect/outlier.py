"""Locate a plan inside an ensemble distribution — **per metric, never combined**.

`docs/ARCHITECTURE.md` section 6 is the contract this module implements:

    The detector reports a distribution, never a verdict. ``outlier.py`` returns
    a percentile per metric plus the ensemble distribution; the decision rule
    that turns percentiles into a flag lives in ``confusion.py`` and is an
    explicit, logged parameter — never buried in a scoring function.

So there is no ``fairness_score`` here, no weighted combination, no ranking of
plans, and no boolean. :func:`locate` returns one :class:`Location` per metric
and provides no way to reduce them; that reduction is `confusion.Rule`'s job,
where it is a named, printable parameter a reader can change and re-run.

Three regimes `docs/CRITERIA.md` warns about, each of which produces a number
that *looks* like a percentile and is not one
------------------------------------------------------------------------------

**The metric is undefined.** ``evaluate.partisan.declination`` returns ``None``
when one party wins every seat (CRITERIA.md section 5.1), which is exactly
Iowa's enacted 2020 plan: Republicans hold four seats of four. ``None`` must not
become 0.0 and then a percentile of 0.02, which is what a naive
``sum(x < value)`` does with a ``None`` coerced anywhere along the way. It gets
:data:`VALUE_UNDEFINED` and no percentile. The same applies inside the ensemble:
draws whose value is ``None`` are removed from the comparison set and counted in
``n_undefined``, and the surviving subset is *not* a random subset of the
ensemble, so :attr:`Location.reasons` says so.

**The ensemble is a point mass.** ``evaluate.administrative.all_metrics``
reports per-metric degeneracy flags, and on Iowa ``county_splits`` is
identically 0 for every plan that exists (units are counties, Iowa Code ch. 42 —
FEASIBILITY.md section 5.3). A percentile against a constant is meaningless: the
enacted plan's 0 is simultaneously at the 0th and the 100th percentile, and a
mid-rank convention would report 0.5 and read as "perfectly typical", which is a
statement about nothing. Such a metric gets :data:`DEGENERATE` and no
percentile, whether the caller declared it degenerate (:func:`administrative_context`)
or this module measured it as constant.

**The metric is not trusted in this regime.** CRITERIA.md section 5.1 holds that
only the efficiency gap and declination should be trusted where one party
predominates, and ``evaluate.partisan.trusted_metrics`` on Iowa's enacted plan
returns ``("efficiency_gap",)`` — one metric of four. Untrusted metrics are
**marked, not dropped**: their percentile is still computed and reported, with
:attr:`Location.trusted` ``False`` and a reason attached. Dropping them would
hide a disagreement; reporting them unmarked would present a number CRITERIA.md
says is unreliable as though it were a measurement (section 11, failure mode 4).
Whether a marked metric may *fire* is a decision-rule question and lives in
``confusion.Rule.untrusted``.

Trust is scoped. :class:`Context` carries ``trust_assessed`` — the metrics the
judgement was made over — so ``polsby_popper`` comes back ``trusted=None``
("not assessed") rather than ``False`` ("assessed and failed"). Those are
different claims and this module does not conflate them.

Percentile convention
---------------------

Three tail probabilities are reported, not one, because they differ exactly
where it matters — at a tie, i.e. on the discrete metrics (``cut_edges``,
``county_splits``, seat counts) where ties are the common case:

* :attr:`Location.p_below`        ``#{x < v} / n``
* :attr:`Location.p_at_or_below`  ``#{x <= v} / n``
* :attr:`Location.percentile`     ``(#{x < v} + 0.5 * #{x == v}) / n``  (mid-rank)

``percentile`` is the headline and the mid-rank convention is the reason: on a
discrete metric ``p_below`` alone reports a plan sitting on the ensemble's modal
value as extreme-low and ``p_at_or_below`` reports the same plan as extreme-high.
:attr:`Location.two_sided_p` is ``2 * min(#{x <= v}, #{x >= v}) / n``, clipped to
1 — the tail probability a two-sided decision rule reads, computed inclusively so
that ties count *against* calling a plan extreme.

What a percentile rests on — resolution, not just count
------------------------------------------------------

A percentile computed from ``n`` reference draws cannot express an arbitrary
threshold, and round 1 of the bench is what this section was written from. With
``n`` draws the largest **interior** mid-rank percentile — the largest value
attainable by a plan that is inside the ensemble's own range — is ``(n - 0.5)/n``
when the maximum is unique, and lower when it is tied. At ``n = 28`` that is
0.9821, below a 0.99 decision threshold, so no plan strictly inside the reference
could ever fire and a "top 1%" rule silently degenerated into "outside the
observed support". Six false positives followed, two of them plans that sat
0.0005 of an efficiency-gap point outside a support pinched shut by 14 distinct
plans.

Three numbers are therefore reported on **every** :class:`Location`, and
:func:`required_n` states the arithmetic:

``n``
    Raw defined draws. The weakest of the three, and the one that round 1 gated
    on: duplicated draws inflate it without adding resolution.
``n_distinct_plans`` (or ``n_distinct`` values, when plan ids are not supplied)
    How many *different* things the reference actually contains. A reference of
    806 draws holding 177 distinct plans is a 177-plan reference with a large
    ``n``.
``ess``
    Kish effective sample size, ``n^2 / sum(m_i^2)`` over the multiplicities
    ``m_i`` of the repeated items — :func:`kish_ess`. It is 806's answer to
    "how many independent draws is this worth": the same 806-draw reference
    scored 11.7. This is a duplication-weighted count, **not** the
    autocorrelation ESS of ``generate.convergence`` (which needs chain structure
    this module is not given); the two answer different questions and are not
    interchangeable.

:attr:`Location.max_interior_percentile` and
:attr:`Location.min_interior_percentile` are the exact attainable bounds for
*this* column, ties included. This module does not decide whether they are
adequate — that depends on a threshold, and thresholds live in
``confusion.Rule``, which refuses to evaluate a rule its reference cannot
express rather than returning a 0.0 or a 1.0 that reads like a measurement.

Imports
-------

``detect`` may import ``generate``, ``evaluate`` and ``adversarial``
(``tools/firewall.yaml``). This module imports from ``evaluate`` only, and only
inside the two optional context builders, so the core of it is pure arithmetic
over numbers the caller already has and can be tested without geometry, election
data, or an ensemble run.
"""
from __future__ import annotations

import hashlib
import math
import statistics
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

# --------------------------------------------------------------------------- #
# statuses
# --------------------------------------------------------------------------- #

#: The plan's value was located in the ensemble. The only status carrying a
#: percentile.
LOCATED = "located"

#: The plan's metric is ``None`` — undefined, not zero. Declination under a
#: one-party sweep (CRITERIA.md section 5.1) is the case this exists for.
VALUE_UNDEFINED = "value_undefined"

#: The ensemble cannot distinguish plans on this metric: either the caller
#: flagged it degenerate (``evaluate.administrative``) or every defined draw has
#: the same value. No percentile — see the module docstring.
DEGENERATE = "degenerate"

#: Fewer than ``min_n`` defined ensemble draws. See :data:`MIN_ENSEMBLE`.
INSUFFICIENT_ENSEMBLE = "insufficient_ensemble"

#: The metric is absent from ``ensemble_metrics``, or every draw of it is
#: ``None``.
MISSING_FROM_ENSEMBLE = "missing_from_ensemble"

#: The metric is absent from ``plan_metrics``.
MISSING_FROM_PLAN = "missing_from_plan"

#: The value is not a real number — a string, a tuple, a bool, a NaN. Reported
#: rather than raised because callers pass whole ``all_metrics()`` dicts, which
#: legitimately carry bookkeeping keys like ``splits_layer``.
NON_NUMERIC = "non_numeric"

#: Every status, in the order a report should present them.
STATUSES: tuple[str, ...] = (
    LOCATED,
    VALUE_UNDEFINED,
    DEGENERATE,
    INSUFFICIENT_ENSEMBLE,
    MISSING_FROM_ENSEMBLE,
    MISSING_FROM_PLAN,
    NON_NUMERIC,
)

#: Minimum number of defined ensemble draws before a percentile is reported.
#:
#: This is a `VALUE` choice and it is a keyword parameter for that reason. The
#: rationale for 20: the finest tail probability an ``n``-draw ensemble can
#: express is ``1/n``, so at ``n = 20`` the smallest non-zero one-sided tail is
#: 0.05 — exactly the false-positive gate of CRITERIA.md section 8. Below that,
#: a percentile cannot even represent the threshold it is about to be compared
#: against, and reporting one invites a decision rule to read resolution that is
#: not there. It is a floor on arithmetic meaningfulness, not on statistical
#: adequacy: the bench runs ~14,000 draws (ARCHITECTURE.md section 5), and an
#: ensemble of 20 that clears this check is still far too small to trust.
#:
#: It is deliberately **not** the check that stops a decision rule from reading
#: resolution that is not there — this module does not know the rule's
#: threshold. That check is ``confusion.Rule.resolvable``, against
#: :func:`required_n`, ``n_distinct_plans`` and ``ess``. Round 2 had only this
#: floor, gated on raw draws, and 28 draws over 14 distinct plans cleared it.
MIN_ENSEMBLE = 20


# --------------------------------------------------------------------------- #
# resolution arithmetic
# --------------------------------------------------------------------------- #

def required_n(threshold: float) -> int | None:
    """Smallest reference size whose interior percentiles can reach ``threshold``.

    A mid-rank percentile over ``n`` draws with no ties runs from ``0.5/n`` to
    ``(n - 0.5)/n``. A decision threshold ``t`` (fired on either tail) is
    therefore expressible by a plan **inside** the ensemble only when
    ``(n - 0.5)/n >= t``, equivalently ``n >= 0.5/(1 - t)``, equivalently
    ``n >= 1/(2(1 - t))``. At ``t = 0.99`` that is 50; at ``t = 0.95`` it is 10.
    The lower tail fires at ``p <= 1 - t`` and needs ``0.5/n <= 1 - t``, the
    identical bound, so this holds for ``upper``, ``lower`` and ``two_sided``
    alike.

    ``None`` only at ``threshold = 1.0``, which no finite reference can express:
    the sole way to reach a mid-rank percentile of exactly 1.0 is to have no draw
    at or above the value, i.e. to be outside the observed support, and that is a
    support test rather than a percentile test. Low thresholds return 1 — a rule
    that fires at ``p >= 0.2`` asks nothing of the reference, which is why
    ``ALWAYS_FLAG`` (threshold 0.0) is never refused for lack of resolution and
    stays available as the control it exists to be.

    This is a floor, not a sufficiency criterion. It is the size at which the
    threshold stops being unreachable; ties at the extreme value push the real
    requirement higher, which is why :attr:`Location.max_interior_percentile`
    reports the attained bound for the actual column rather than this formula's
    idealisation.
    """
    t = float(threshold)
    if t >= 1.0:
        return None
    return max(1, int(math.ceil(0.5 / (1.0 - t))))


def kish_ess(multiplicities: Iterable[int]) -> float:
    """Kish effective sample size ``n^2 / sum(m_i^2)`` over item multiplicities.

    The duplication-weighted count of a reference. ``n`` distinct items each
    seen once gives ``n``; ``n`` copies of one item gives 1.0; the round-2 bench
    reference — 806 draws over 177 distinct plans — gives 11.7.

    It is the ordinary design-effect formula, read here with weights
    ``w_i = m_i / n``: ``1 / sum(w_i^2)``. **It is not** the autocorrelation ESS
    that ``generate.convergence.ess`` computes; that one needs the chain
    structure and draw order, neither of which reaches this module. Duplication
    is the part of the resolution loss ``detect`` can see from the columns
    alone, and it is the part that defeated ``Rule.min_n``.

    Returns 0.0 for an empty input.
    """
    ms = [int(m) for m in multiplicities if int(m) > 0]
    n = sum(ms)
    if n == 0:
        return 0.0
    return float(n * n) / float(sum(m * m for m in ms))


def _multiplicities(items: Iterable[Any]) -> dict[Any, int]:
    counts: dict[Any, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return counts


# --------------------------------------------------------------------------- #
# distribution summary
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Distribution:
    """Summary of one metric's ensemble distribution.

    Reported *beside* every percentile, because a percentile alone cannot
    distinguish "the plan is far outside a tight ensemble" from "the plan is
    just outside a broad one", and those are different findings. The quantiles
    are linear-interpolated order statistics (the ``numpy`` default, so numbers
    here compare against the literature without a convention footnote).

    ``n`` counts **defined** draws only; ``n_undefined`` counts draws dropped
    for being ``None``. ``n_distinct`` is the number of distinct values, which
    is 1 exactly when the ensemble is a point mass.

    ``ess``, ``max_multiplicity`` and ``min_multiplicity`` describe the
    resolution rather than the shape, and they are here because a count of draws
    does not: ``ess`` is :func:`kish_ess` over the value multiplicities, and the
    two multiplicities are how many draws tie the maximum and the minimum, which
    is what actually bounds the attainable interior percentiles
    (:attr:`max_interior_percentile`, :attr:`min_interior_percentile`).
    """

    n: int
    n_undefined: int
    n_distinct: int
    mean: float
    sd: float
    minimum: float
    p05: float
    p25: float
    median: float
    p75: float
    p95: float
    maximum: float
    ess: float = 0.0
    max_multiplicity: int = 1
    min_multiplicity: int = 1

    @property
    def constant(self) -> bool:
        """True when every defined draw has the same value."""
        return self.n_distinct <= 1

    @property
    def finest_tail(self) -> float:
        """``1/n`` — the smallest non-zero one-sided tail this column can state."""
        return 1.0 / self.n if self.n else 1.0

    @property
    def max_interior_percentile(self) -> float:
        """Largest mid-rank percentile a plan **inside** the ensemble can reach.

        A plan tying the ensemble maximum has ``(n - m_max) + 0.5 * m_max``
        draws at or below it, so this is ``1 - 0.5 * m_max / n``. Anything above
        it is only attainable by a plan strictly outside the observed support —
        which is a different claim from "in the top 1% of the ensemble" and must
        not be allowed to impersonate it. See :func:`required_n`.
        """
        if not self.n:
            return 0.0
        return 1.0 - 0.5 * self.max_multiplicity / self.n

    @property
    def min_interior_percentile(self) -> float:
        """Mirror of :attr:`max_interior_percentile` on the low tail."""
        if not self.n:
            return 1.0
        return 0.5 * self.min_multiplicity / self.n

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "n_undefined": self.n_undefined,
            "n_distinct": self.n_distinct,
            "ess": self.ess,
            "mean": self.mean,
            "sd": self.sd,
            "min": self.minimum,
            "p05": self.p05,
            "p25": self.p25,
            "median": self.median,
            "p75": self.p75,
            "p95": self.p95,
            "max": self.maximum,
            "constant": self.constant,
            "max_multiplicity": self.max_multiplicity,
            "min_multiplicity": self.min_multiplicity,
            "max_interior_percentile": self.max_interior_percentile,
            "min_interior_percentile": self.min_interior_percentile,
            "finest_tail": self.finest_tail,
        }


def summarize(values: Sequence[float], *, n_undefined: int = 0) -> Distribution:
    """Summarize defined draws. Raises on an empty sequence."""
    xs = sorted(float(v) for v in values)
    if not xs:
        raise ValueError("summarize: no defined values")
    n = len(xs)
    sd = statistics.pstdev(xs) if n > 1 else 0.0
    counts = _multiplicities(xs)
    return Distribution(
        n=n,
        n_undefined=int(n_undefined),
        n_distinct=len(counts),
        ess=kish_ess(counts.values()),
        mean=statistics.fmean(xs),
        sd=sd,
        minimum=xs[0],
        p05=_quantile(xs, 0.05),
        p25=_quantile(xs, 0.25),
        median=_quantile(xs, 0.50),
        p75=_quantile(xs, 0.75),
        p95=_quantile(xs, 0.95),
        maximum=xs[-1],
        max_multiplicity=counts[xs[-1]],
        min_multiplicity=counts[xs[0]],
    )


def _quantile(sorted_xs: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile of an already-sorted sequence."""
    n = len(sorted_xs)
    if n == 1:
        return float(sorted_xs[0])
    pos = (n - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return float(sorted_xs[int(pos)])
    return float(sorted_xs[low] + (sorted_xs[high] - sorted_xs[low]) * (pos - low))


# --------------------------------------------------------------------------- #
# one metric's location
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Location:
    """Where one metric of one plan sits in the ensemble — or why it does not.

    A ``Location`` is only a percentile when :attr:`status` is :data:`LOCATED`.
    In every other status ``percentile``, ``z`` and the tail probabilities are
    ``None`` and :attr:`reasons` says why, in prose. That is deliberate: an
    absent percentile must be visibly absent, because a caller that reads a
    default of 0.0 or 0.5 out of a dict gets a plausible number computed from
    nothing.

    ``trusted`` is three-valued and the three values are different claims:

    ``True``   assessed by ``evaluate.partisan.trusted_metrics`` and kept
    ``False``  assessed and rejected for this regime — **marked, not dropped**
    ``None``   not assessed (no context given, or the metric is outside the set
               the trust judgement covers, e.g. ``polsby_popper``)

    The resolution block — ``n``, ``n_distinct``, ``n_distinct_plans``, ``ess``,
    ``ess_basis``, ``max_interior_percentile``, ``min_interior_percentile`` —
    travels with the percentile so that a reader, and ``confusion.Rule``, can
    see what it rests on. ``n`` alone cannot distinguish 806 independent draws
    from 806 copies of one plan; ``ess`` can, and did (11.7). ``ess_basis`` says
    which multiset the effective size was computed over: ``"plans"`` when the
    caller supplied ensemble plan ids, ``"values"`` otherwise — the latter is
    conservative, because two distinct plans sharing a metric value inflate that
    value's multiplicity and so *lower* the reported ESS.

    ``outside_support`` is ``True`` when the plan's value is strictly beyond
    every draw. Such a plan gets percentile 0.0 or 1.0, which is a statement
    about the support, not a position in it, and the decision rule needs to know
    the difference.
    """

    metric: str
    status: str
    value: float | None = None
    percentile: float | None = None
    p_below: float | None = None
    p_at_or_below: float | None = None
    two_sided_p: float | None = None
    z: float | None = None
    n: int = 0
    n_distinct: int | None = None
    n_distinct_plans: int | None = None
    ess: float | None = None
    ess_basis: str | None = None
    max_interior_percentile: float | None = None
    min_interior_percentile: float | None = None
    outside_support: bool | None = None
    distribution: Distribution | None = None
    trusted: bool | None = None
    reasons: tuple[str, ...] = ()
    plan_id: str | None = None

    @property
    def located(self) -> bool:
        """True when this carries a percentile."""
        return self.status == LOCATED

    @property
    def n_distinct_reference(self) -> int | None:
        """Distinct plans if the caller supplied ids, else distinct values.

        The count a resolution check should read. Distinct values is the
        conservative stand-in: it can only be smaller than the distinct-plan
        count, never larger, so a rule that clears it would also clear the
        exact figure.
        """
        if self.n_distinct_plans is not None:
            return self.n_distinct_plans
        return self.n_distinct

    def resolution(self) -> dict[str, Any]:
        """What the percentile rests on, as a block. Never a judgement of it."""
        return {
            "n": self.n,
            "n_distinct_values": self.n_distinct,
            "n_distinct_plans": self.n_distinct_plans,
            "n_distinct_reference": self.n_distinct_reference,
            "ess": self.ess,
            "ess_basis": self.ess_basis,
            "max_interior_percentile": self.max_interior_percentile,
            "min_interior_percentile": self.min_interior_percentile,
            "outside_support": self.outside_support,
        }

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready. ``distribution`` is nested, or ``None``."""
        return {
            "metric": self.metric,
            "status": self.status,
            "value": self.value,
            "percentile": self.percentile,
            "p_below": self.p_below,
            "p_at_or_below": self.p_at_or_below,
            "two_sided_p": self.two_sided_p,
            "z": self.z,
            "n": self.n,
            "resolution": self.resolution(),
            "distribution": None if self.distribution is None
            else self.distribution.as_dict(),
            "trusted": self.trusted,
            "reasons": list(self.reasons),
            "plan_id": self.plan_id,
        }


# --------------------------------------------------------------------------- #
# context: what evaluate knows about this plan that a bare float does not
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Context:
    """Regime information from ``evaluate``, attached to locations by name.

    Built by :func:`election_context` and :func:`administrative_context`, or by
    hand in a test. Merge with :meth:`merge`.

    ``trusted`` / ``trust_assessed``
        ``trust_assessed`` is the set of metric names the trust judgement was
        made over — ``evaluate.partisan.METRICS`` for the election context. A
        metric inside it and not in ``trusted`` is marked untrusted; a metric
        outside it is left ``None``. Without this pair, "not trusted" and "never
        examined" collapse into the same falsy value.

    ``degenerate``
        ``{metric: reason}``. Names here get :data:`DEGENERATE` and no
        percentile even if the ensemble happens to show variation, because the
        caller is asserting a structural fact about the input that a finite
        sample cannot overrule.

    ``notes``
        Free prose carried into every location's ``reasons`` — e.g. the output
        of ``evaluate.partisan.caveats``.
    """

    trusted: frozenset[str] = frozenset()
    trust_assessed: frozenset[str] = frozenset()
    degenerate: Mapping[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def trust_of(self, metric: str) -> bool | None:
        """``True`` / ``False`` / ``None`` — see :class:`Location`."""
        if metric in self.trusted:
            return True
        if metric in self.trust_assessed:
            return False
        return None

    def merge(self, other: "Context") -> "Context":
        """Union of both, with ``other``'s degeneracy reasons winning ties."""
        degenerate = dict(self.degenerate)
        degenerate.update(other.degenerate)
        return Context(
            trusted=self.trusted | other.trusted,
            trust_assessed=self.trust_assessed | other.trust_assessed,
            degenerate=degenerate,
            notes=self.notes + tuple(n for n in other.notes if n not in self.notes),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "trusted": sorted(self.trusted),
            "trust_assessed": sorted(self.trust_assessed),
            "degenerate": dict(self.degenerate),
            "notes": list(self.notes),
        }


EMPTY_CONTEXT = Context()


def election_context(plan: Mapping[str, int], dem, rep, **kwargs) -> Context:
    """Trust context from ``evaluate.partisan``.

    Thin wrapper: ``trusted = trusted_metrics(plan, dem, rep)``,
    ``trust_assessed = partisan.METRICS``, ``notes = caveats(plan, dem, rep)``.
    Keyword arguments pass straight through to both, so the thresholds
    ``evaluate.partisan`` exposes (``predominance_band``,
    ``minority_district_share``, ``min_districts_for_declination``) stay
    changeable from here.

    On Iowa's enacted plan this returns ``trusted={"efficiency_gap"}`` over four
    assessed metrics, and three caveat sentences.
    """
    from evaluate import partisan

    return Context(
        trusted=frozenset(partisan.trusted_metrics(plan, dem, rep, **kwargs)),
        trust_assessed=frozenset(partisan.METRICS),
        notes=tuple(partisan.caveats(plan, dem, rep, **kwargs)),
    )


def administrative_context(plan: Any, units: Any) -> Context:
    """Degeneracy context from ``evaluate.administrative``.

    Every name in that module's ``constant_metrics`` and ``unavailable_metrics``
    becomes a :data:`DEGENERATE` entry carrying the module's own ``reason``
    string. ``evaluate.administrative.all_metrics`` states the rule this
    implements: *only names in* ``varying_metrics`` *may be fed to an outlier
    percentile*.

    On Iowa every administrative metric lands here, ``county_splits`` among
    them, which is why the Iowa bench reports no administrative percentile at
    all rather than a column of 0.5s.
    """
    from evaluate import administrative

    flags = administrative.degeneracy(plan, units)
    degenerate: dict[str, str] = {}
    for name, entry in flags["metrics"].items():
        if entry["constant"] or not entry["computable"]:
            degenerate[name] = entry["reason"] or "flagged by evaluate.administrative"
    return Context(degenerate=degenerate)


# --------------------------------------------------------------------------- #
# input normalisation
# --------------------------------------------------------------------------- #

def as_columns(
    rows: Iterable[Mapping[str, Any]], *, metrics: Sequence[str] | None = None
) -> dict[str, list[Any]]:
    """``[{metric: value}, ...]`` (one dict per ensemble plan) -> ``{metric: [values]}``.

    This is the shape ``evaluate.*.all_metrics`` produces when mapped over an
    ensemble, and the shape :func:`locate` wants. Missing keys become ``None``
    so that every column has one entry per plan and ``n_undefined`` counts them:
    a metric that only some draws define must not silently shrink its own
    denominator without saying so.
    """
    rows = list(rows)
    names: list[str]
    if metrics is not None:
        names = list(metrics)
    else:
        seen: dict[str, None] = {}
        for row in rows:
            for key in row:
                seen.setdefault(key, None)
        names = list(seen)
    return {name: [row.get(name) for row in rows] for name in names}


def _numeric(value: Any) -> float | None:
    """Real finite number, or ``None``. Bools are not numbers here."""
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    x = float(value)
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def plan_digest(plan: Mapping[str, int] | None) -> str | None:
    """Short stable fingerprint of a plan assignment, or ``None``.

    Carried on every :class:`Location` so a serialized location says which plan
    it locates. Order-independent (sorted by unit id) and label-sensitive: two
    plans differing only in district numbering hash differently, which is
    correct here — this identifies an assignment, it does not test equivalence.
    """
    if plan is None:
        return None
    body = ";".join(f"{unit}:{plan[unit]}" for unit in sorted(plan))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# the main entry point
# --------------------------------------------------------------------------- #

def locate(
    plan: Mapping[str, int] | None,
    ensemble_metrics: Mapping[str, Sequence[Any]] | Sequence[Mapping[str, Any]],
    plan_metrics: Mapping[str, Any],
    *,
    context: Context | None = None,
    metrics: Sequence[str] | None = None,
    ensemble_plan_ids: Sequence[Any] | None = None,
    min_n: int = MIN_ENSEMBLE,
) -> dict[str, Location]:
    """Locate ``plan_metrics`` in ``ensemble_metrics``, one :class:`Location` per metric.

    Parameters
    ----------
    plan
        The assignment the metrics were measured on, ``{unit: district}``, or
        ``None``. **Not re-measured here** — computing metrics is
        ``evaluate``'s job and doing it again in ``detect`` would be a second
        implementation of the same formula, free to disagree with the first. It
        is used for provenance: its :func:`plan_digest` is stamped on every
        location returned, so a location serialized on its own still names the
        plan it belongs to.
    ensemble_metrics
        Either ``{metric: [value per draw]}`` or ``[{metric: value}, ...]`` (one
        mapping per draw); the second is converted by :func:`as_columns`.
        ``None`` entries are dropped from the comparison set and counted.
    plan_metrics
        ``{metric: value}`` for the plan being located, e.g. the output of
        ``evaluate.partisan.all_metrics``.
    context
        :class:`Context` carrying trust and degeneracy from ``evaluate``. Absent,
        no metric is marked trusted or untrusted (all ``None``) and only
        empirical point masses are called degenerate.
    metrics
        Restrict and order the output. Absent, every metric appearing in either
        input is reported — including ones appearing in only one, which get
        :data:`MISSING_FROM_ENSEMBLE` or :data:`MISSING_FROM_PLAN` rather than
        being dropped.
    ensemble_plan_ids
        One identifier per ensemble draw, in the same order as the columns —
        ``generate``'s plan digests, or any hashable stand-in. Supplied, every
        :class:`Location` reports ``n_distinct_plans`` and an ``ess`` computed
        over plan multiplicities, which is what a reader needs to see that a
        806-draw reference contains 177 plans worth 11.7 independent draws.
        Omitted, the same two numbers are computed over the metric's own
        *values*, which is conservative in both directions (see
        :attr:`Location.n_distinct_reference`) and is marked ``ess_basis =
        "values"`` so it cannot be mistaken for the exact figure. A length
        mismatch raises: silently truncating would associate percentiles with
        the wrong plans.
    min_n
        Defined draws required before a percentile is reported
        (:data:`MIN_ENSEMBLE`).

    Returns
    -------
    ``{metric: Location}`` and nothing else. There is no summary key, no count
    of "how many metrics were extreme", and no ordering by extremeness — those
    are decisions, and decisions live in ``confusion.py`` behind a printable
    rule. See ARCHITECTURE.md section 6 and CRITERIA.md section 11.
    """
    ctx = context or EMPTY_CONTEXT
    columns = _as_column_mapping(ensemble_metrics)
    digest = plan_digest(plan)

    ids: list[Any] | None = None
    if ensemble_plan_ids is not None:
        ids = list(ensemble_plan_ids)
        for name, column in columns.items():
            if len(column) != len(ids):
                raise ValueError(
                    f"locate: ensemble_plan_ids has {len(ids)} entries but "
                    f"column {name!r} has {len(column)}. They index the same "
                    "draws; a mismatch would attach the wrong plan ids to the "
                    "wrong values."
                )

    if metrics is None:
        names: list[str] = list(plan_metrics)
        names += [m for m in columns if m not in plan_metrics]
    else:
        names = list(metrics)

    return {
        name: _locate_one(
            name,
            plan_metrics,
            columns,
            ctx,
            min_n=min_n,
            digest=digest,
            plan_ids=ids,
        )
        for name in names
    }


def _as_column_mapping(
    ensemble_metrics: Mapping[str, Sequence[Any]] | Sequence[Mapping[str, Any]],
) -> Mapping[str, Sequence[Any]]:
    """Accept either supported ensemble shape; reject anything else loudly."""
    if isinstance(ensemble_metrics, Mapping):
        return ensemble_metrics
    rows = list(ensemble_metrics)
    if rows and not all(isinstance(row, Mapping) for row in rows):
        raise TypeError(
            "locate: ensemble_metrics must be {metric: [values]} or a sequence "
            "of {metric: value} mappings"
        )
    return as_columns(rows)


def _locate_one(
    metric: str,
    plan_metrics: Mapping[str, Any],
    columns: Mapping[str, Sequence[Any]],
    ctx: Context,
    *,
    min_n: int,
    digest: str | None,
    plan_ids: Sequence[Any] | None = None,
) -> Location:
    trusted = ctx.trust_of(metric)
    base = dict(metric=metric, trusted=trusted, plan_id=digest)
    notes = tuple(ctx.notes)

    if metric not in plan_metrics:
        return Location(
            status=MISSING_FROM_PLAN,
            reasons=(f"{metric!r} is not in plan_metrics.",) + notes,
            **base,
        )

    raw = plan_metrics[metric]
    if raw is None:
        return Location(
            status=VALUE_UNDEFINED,
            reasons=(
                f"{metric} is None for this plan — undefined, not zero, and so "
                "not locatable. Declination is None wherever one party wins "
                "every seat (CRITERIA.md section 5.1).",
            ) + notes,
            **base,
        )

    value = _numeric(raw)
    if value is None:
        return Location(
            status=NON_NUMERIC,
            reasons=(
                f"{metric} = {raw!r} is not a real finite number, so it has no "
                "position in a distribution.",
            ) + notes,
            **base,
        )
    base["value"] = value

    # A structural degeneracy declared by the caller outranks anything a finite
    # sample shows: evaluate.administrative is asserting that no plan over these
    # units can move this metric, and an ensemble that appeared to move it would
    # mean the ensemble is wrong, not the flag.
    if metric in ctx.degenerate:
        return Location(
            status=DEGENERATE,
            reasons=(
                f"{metric} is flagged degenerate by the caller and gets no "
                f"percentile: {ctx.degenerate[metric]}",
            ) + notes,
            **base,
        )

    if metric not in columns:
        return Location(
            status=MISSING_FROM_ENSEMBLE,
            reasons=(f"{metric!r} is not in the ensemble.",) + notes,
            **base,
        )

    column = list(columns[metric])
    numeric = [_numeric(v) for v in column]
    defined = [x for x in numeric if x is not None]
    n_undefined = len(column) - len(defined)
    kept_ids: list[Any] | None = None
    if plan_ids is not None:
        kept_ids = [pid for pid, x in zip(plan_ids, numeric) if x is not None]
    undefined_note: tuple[str, ...] = ()
    if n_undefined:
        undefined_note = (
            f"{n_undefined} of {len(column)} ensemble draws have {metric} "
            "undefined and were dropped. The surviving draws are not a random "
            "subset — the same condition that undefines the metric selects "
            "them — so the percentile below is over that subset, not the "
            "ensemble.",
        )

    if not defined:
        return Location(
            status=MISSING_FROM_ENSEMBLE,
            n=0,
            reasons=(
                f"every ensemble draw of {metric} is undefined or non-numeric.",
            ) + undefined_note + notes,
            **base,
        )

    dist = summarize(defined, n_undefined=n_undefined)
    n = dist.n

    # Resolution: what the percentile about to be computed actually rests on.
    # Reported on every status from here down, including the ones that get no
    # percentile, because "no percentile, and here is how thin the reference
    # was" is a more useful record than either half alone.
    if kept_ids is not None:
        plan_counts = _multiplicities(kept_ids)
        n_distinct_plans: int | None = len(plan_counts)
        ess = kish_ess(plan_counts.values())
        ess_basis = "plans"
    else:
        n_distinct_plans = None
        ess = dist.ess
        ess_basis = "values"
    resolution = dict(
        n_distinct=dist.n_distinct,
        n_distinct_plans=n_distinct_plans,
        ess=ess,
        ess_basis=ess_basis,
        max_interior_percentile=dist.max_interior_percentile,
        min_interior_percentile=dist.min_interior_percentile,
        outside_support=value < dist.minimum or value > dist.maximum,
    )
    base.update(resolution)

    if dist.constant:
        return Location(
            status=DEGENERATE,
            n=n,
            distribution=dist,
            reasons=(
                f"every one of the {n} defined ensemble draws has "
                f"{metric} = {dist.minimum:g}. A percentile against a point "
                "mass is meaningless — the plan's value is simultaneously at "
                "the top and the bottom of the distribution — so none is "
                "reported.",
            ) + undefined_note + notes,
            **base,
        )

    if n < min_n:
        return Location(
            status=INSUFFICIENT_ENSEMBLE,
            n=n,
            distribution=dist,
            reasons=(
                f"only {n} defined ensemble draws of {metric} (min_n={min_n}); "
                f"the finest tail probability expressible is 1/{n} = "
                f"{1 / n:.3g}.",
            ) + undefined_note + notes,
            **base,
        )

    ordered = sorted(defined)
    below = bisect_left(ordered, value)
    at_or_below = bisect_right(ordered, value)
    ties = at_or_below - below
    p_below = below / n
    p_at_or_below = at_or_below / n
    percentile = (below + 0.5 * ties) / n
    tail_low = at_or_below / n
    tail_high = (n - below) / n
    two_sided = min(1.0, 2.0 * min(tail_low, tail_high))
    z = (value - dist.mean) / dist.sd if dist.sd > 0 else None

    reasons = undefined_note + notes
    reasons = reasons + (
        f"reference resolution for {metric}: n={n} draws, "
        f"{dist.n_distinct} distinct values"
        + ("" if n_distinct_plans is None else f", {n_distinct_plans} distinct plans")
        + f", ESS {ess:.4g} (basis: {ess_basis}). Interior percentiles reach "
        f"[{dist.min_interior_percentile:.4g}, "
        f"{dist.max_interior_percentile:.4g}]; a decision threshold outside "
        "that band is only reachable by a plan outside the observed support "
        "and is a support test, not a percentile test.",
    )
    if resolution["outside_support"]:
        reasons = reasons + (
            f"{metric} = {value:g} lies outside the ensemble's observed range "
            f"[{dist.minimum:g}, {dist.maximum:g}], so its percentile is a "
            "bound, not a position: every draw is on one side of it and no "
            "finite reference can say how far outside it is.",
        )
    if trusted is False:
        reasons = (
            f"{metric} is not trusted in this regime (CRITERIA.md section 5.1). "
            "The percentile is reported because dropping it would hide a "
            "disagreement between metrics, but it must not be read as a "
            "measurement.",
        ) + reasons
    if ties:
        reasons = reasons + (
            f"{ties} of {n} draws tie the plan's value exactly; percentile is "
            f"mid-rank, and p_below={p_below:.4g} / "
            f"p_at_or_below={p_at_or_below:.4g} bracket it.",
        )

    return Location(
        status=LOCATED,
        percentile=percentile,
        p_below=p_below,
        p_at_or_below=p_at_or_below,
        two_sided_p=two_sided,
        z=z,
        n=n,
        distribution=dist,
        reasons=reasons,
        **base,
    )


# --------------------------------------------------------------------------- #
# reporting helpers — descriptive only, never a decision
# --------------------------------------------------------------------------- #

def locations_as_dict(locations: Mapping[str, Location]) -> dict[str, Any]:
    """JSON-ready ``{metric: location}``, for ``bench-results.json``."""
    return {name: loc.as_dict() for name, loc in locations.items()}


def percentiles(locations: Mapping[str, Location]) -> dict[str, float | None]:
    """``{metric: percentile}``, ``None`` where none exists.

    The ``percentiles`` block of ARCHITECTURE.md section 5. The ``None``s are
    load-bearing: the schema must show that a metric was examined and could not
    be located, which an omitted key does not distinguish from a metric nobody
    computed.
    """
    return {name: loc.percentile for name, loc in locations.items()}


def by_status(locations: Mapping[str, Location]) -> dict[str, tuple[str, ...]]:
    """``{status: (metric names,)}`` over :data:`STATUSES`, empties included."""
    return {
        status: tuple(n for n, loc in locations.items() if loc.status == status)
        for status in STATUSES
    }


def review_report(
    locations: Mapping[str, Location],
    *,
    plan_id: str | None = None,
    source: str | None = None,
    context: Context | None = None,
    comparators: Mapping[str, Mapping[str, Any]] | None = None,
    tolerance: float = 0.0,
) -> dict[str, Any]:
    """Where a **real, in-force** plan sits in the ensemble. Deliberately no boolean.

    This is the sanctioned output for a plan that carries no manufactured ground
    truth — Iowa's enacted CD118 map being the case it exists for. It is not
    ``confusion.flag``'s job and must not be done with ``confusion.flag``:

        README.md and CRITERIA.md section 11 — *any output of this system that
        reads as a verdict rather than a distribution is a bug.*

    Round 2's artifact published ``plan_under_review.flagged = true``, a boolean
    judgement on a map that four million people live under, derived from a rule
    whose threshold its own reference could not express. There is no ``flagged``
    key here and no way to add one: the return value carries a location per
    metric, the trusted set by name, the untrusted set marked, the resolution
    each percentile rests on, and the metrics on which this system **cannot
    tell** the plan apart from something else.

    ``comparators``
        ``{name: {metric: value}}`` for other plans — planted gerrymanders, the
        ensemble median, whatever the caller wants compared. Any metric whose
        value matches within ``tolerance`` (default 0.0, i.e. bit-identical)
        lands in ``indistinguishable``, with prose. This exists because Iowa's
        enacted plan and manufactured R-gerrymanders have the *same* efficiency
        gap to the last bit. Measured on round 2's 62 scenarios, grouped by
        seat split:

        =============  =========================================
        seat split     distinct efficiency-gap values among them
        =============  =========================================
        0D-4R          **2**, differing in the 7th decimal
        1D-3R          25
        2D-2R          20
        =============  =========================================

        Under a 4-0 sweep every Democratic vote is lost and every Republican
        vote above the winning margin is surplus, so the wasted-vote arithmetic
        is essentially a function of the statewide totals and the seat split
        rather than of the lines. Three planted 2-seat R-gerrymanders *and* one
        neutral null carried the enacted plan's efficiency gap bit for bit. The
        enacted plan's percentile of 1.0 on that metric therefore says it sweeps
        4-0, not that its boundaries are unusual — and a detector reading that
        metric cannot tell the enacted map, a manufactured gerrymander and a
        neutral draw apart. The honest output says so rather than reporting a
        percentile as though it had discriminated.

    Returns a mapping with:

    ``metrics``            ``{metric: value}``
    ``percentiles``        ``{metric: percentile or None}``
    ``statuses``           ``{metric: status}``
    ``locations``          the full per-metric locations
    ``trusted``            names trusted in this regime, and the assessed set
    ``untrusted``          names assessed and rejected — marked, never dropped
    ``not_assessed``       names the trust judgement did not cover
    ``resolution``         ``{metric: what its percentile rests on}``
    ``indistinguishable``  ``{metric: [comparator names]}`` plus prose
    ``no_verdict``         the constant string this function exists to print
    """
    ctx = context or EMPTY_CONTEXT
    names = list(locations)

    trusted = [n for n in names if locations[n].trusted is True]
    untrusted = [n for n in names if locations[n].trusted is False]
    not_assessed = [n for n in names if locations[n].trusted is None]

    matches: dict[str, list[str]] = {}
    if comparators:
        for name in names:
            value = locations[name].value
            if value is None:
                continue
            hits = []
            for other, other_metrics in comparators.items():
                theirs = _numeric(other_metrics.get(name))
                if theirs is None:
                    continue
                if abs(theirs - value) <= tolerance:
                    hits.append(other)
            if hits:
                matches[name] = sorted(hits)

    notes: list[str] = list(ctx.notes)
    for metric, others in sorted(matches.items()):
        notes.append(
            f"{metric} is identical (within {tolerance:g}) between this plan "
            f"and {', '.join(others)}. On this metric the system cannot "
            "distinguish them, and neither can any rule built on it. A "
            "percentile reported for this metric locates the value, not the "
            "plan."
        )

    return {
        "plan_id": plan_id,
        "source": source,
        "metrics": {n: locations[n].value for n in names},
        "percentiles": percentiles(locations),
        "statuses": {n: locations[n].status for n in names},
        "locations": locations_as_dict(locations),
        "trusted": {
            "trusted": sorted(trusted),
            "untrusted_marked_not_dropped": sorted(untrusted),
            "not_assessed": sorted(not_assessed),
            "assessed_over": sorted(ctx.trust_assessed),
            "note": (
                "CRITERIA.md section 5.1: where one party predominates only the "
                "efficiency gap and declination are held to be trustworthy. "
                "Untrusted percentiles are printed because hiding a "
                "disagreement between metrics is worse than showing an "
                "unreliable one, and they are marked because printing one "
                "unmarked presents a VALUE choice as a computed result."
            ),
        },
        "resolution": {n: locations[n].resolution() for n in names},
        "indistinguishable": {
            "matches": matches,
            "tolerance": tolerance,
            "note": (
                "metrics on which this plan's value equals a comparator's. The "
                "system reports that it cannot tell them apart rather than "
                "reporting a number that looks like it did."
            ) if matches else "no comparator matched any metric",
        },
        "notes": notes,
        "summary_lines": summary_lines(locations),
        "no_verdict": (
            "This block reports a location in a distribution. It contains no "
            "flag, no score and no judgement, because this plan carries no "
            "manufactured ground truth against which a flag could be scored "
            "(README.md, CRITERIA.md section 11). A percentile is where this "
            "plan sits among the maps a neutral process drew; it is not a "
            "finding that the plan is or is not a gerrymander."
        ),
    }


def summary_lines(locations: Mapping[str, Location]) -> list[str]:
    """One human-readable line per metric. Prose, not a score.

    Deliberately reports every metric side by side in input order and refuses to
    sort by extremeness: an ordering by how unusual each metric is reads as a
    ranking of evidence, which is the verdict this module does not issue.
    """
    lines: list[str] = []
    for name, loc in locations.items():
        mark = "" if loc.trusted is not False else "  [UNTRUSTED in this regime]"
        if not loc.located:
            lines.append(f"{name}: {loc.status} ({loc.reasons[0] if loc.reasons else ''}){mark}")
            continue
        dist = loc.distribution
        z = "n/a" if loc.z is None else f"{loc.z:+.2f}"
        tail = "n/a" if loc.two_sided_p is None else f"{loc.two_sided_p:.4g}"
        spread = (
            f"n={loc.n} (no distribution summary)" if dist is None
            else f"n={dist.n} median={dist.median:.6g} "
                 f"[p05 {dist.p05:.6g}, p95 {dist.p95:.6g}]"
        )
        res = ""
        if loc.ess is not None:
            distinct = loc.n_distinct_reference
            res = (
                f" | rests on {distinct} distinct "
                f"{'plans' if loc.ess_basis == 'plans' else 'values'}, "
                f"ESS {loc.ess:.4g}, interior percentiles reach "
                f"{loc.max_interior_percentile:.4g}"
            )
        outside = " [OUTSIDE the ensemble's observed range]" if loc.outside_support else ""
        lines.append(
            f"{name}: value={loc.value:.6g} percentile={loc.percentile:.4f} "
            f"z={z} two_sided_p={tail} | ensemble {spread}{res}{outside}{mark}"
        )
    return lines


__all__ = [
    "LOCATED",
    "required_n",
    "kish_ess",
    "review_report",
    "VALUE_UNDEFINED",
    "DEGENERATE",
    "INSUFFICIENT_ENSEMBLE",
    "MISSING_FROM_ENSEMBLE",
    "MISSING_FROM_PLAN",
    "NON_NUMERIC",
    "STATUSES",
    "MIN_ENSEMBLE",
    "Distribution",
    "Location",
    "Context",
    "EMPTY_CONTEXT",
    "summarize",
    "election_context",
    "administrative_context",
    "as_columns",
    "plan_digest",
    "locate",
    "locations_as_dict",
    "percentiles",
    "by_status",
    "summary_lines",
]
