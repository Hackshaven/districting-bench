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
MIN_ENSEMBLE = 20


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

    @property
    def constant(self) -> bool:
        """True when every defined draw has the same value."""
        return self.n_distinct <= 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "n_undefined": self.n_undefined,
            "n_distinct": self.n_distinct,
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
        }


def summarize(values: Sequence[float], *, n_undefined: int = 0) -> Distribution:
    """Summarize defined draws. Raises on an empty sequence."""
    xs = sorted(float(v) for v in values)
    if not xs:
        raise ValueError("summarize: no defined values")
    n = len(xs)
    sd = statistics.pstdev(xs) if n > 1 else 0.0
    return Distribution(
        n=n,
        n_undefined=int(n_undefined),
        n_distinct=len(set(xs)),
        mean=statistics.fmean(xs),
        sd=sd,
        minimum=xs[0],
        p05=_quantile(xs, 0.05),
        p25=_quantile(xs, 0.25),
        median=_quantile(xs, 0.50),
        p75=_quantile(xs, 0.75),
        p95=_quantile(xs, 0.95),
        maximum=xs[-1],
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
    distribution: Distribution | None = None
    trusted: bool | None = None
    reasons: tuple[str, ...] = ()
    plan_id: str | None = None

    @property
    def located(self) -> bool:
        """True when this carries a percentile."""
        return self.status == LOCATED

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
    defined = [x for x in (_numeric(v) for v in column) if x is not None]
    n_undefined = len(column) - len(defined)
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
        lines.append(
            f"{name}: value={loc.value:.6g} percentile={loc.percentile:.4f} "
            f"z={z} two_sided_p={tail} | ensemble {spread}{mark}"
        )
    return lines


__all__ = [
    "LOCATED",
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
