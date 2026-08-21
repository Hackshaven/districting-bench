"""Every metric, side by side, with disagreements surfaced rather than resolved.

``prompt.md``, Phase 2: *"Report all metrics side by side, always, with
disagreements between them highlighted rather than resolved."* The three metric
modules each do this within their own family — :func:`partisan.all_metrics`,
:func:`compactness.all_metrics`, :func:`administrative.all_metrics`. Nothing did
it *across* families, and nothing surfaced the disagreements in one place a reader
could not skip.

This module is that surface. It is the Phase 2 deliverable, and it is deliberately
the least clever file in the package.

What it refuses to do
---------------------
There is no score. ``prompt.md``: *"If you find yourself writing a function called
`fairness_score()` that returns one number, stop."* :func:`score_plan` returns a
mapping of every metric to its value plus a list of disagreements, and there is no
weighting, ranking, or aggregation anywhere in it. That is not an oversight to be
fixed by a later caller — a helper that reduced this to one number would defeat the
whole point of computing five compactness measures that disagree.

It also does not decide which metrics to believe. :func:`partisan.trusted_metrics`
names the ones that survive this plan's regime and :func:`partisan.caveats` says
why; both are carried into the report **beside** the untrusted values rather than
being used to filter them. A reader who wants only the trusted numbers can take
them; a reader who is handed a filtered dict cannot tell that filtering happened.

Disagreement is the point, not a defect
---------------------------------------
CRITERIA.md section 3: *"Report all of them, always, and highlight disagreements
rather than resolving them."* Three kinds are surfaced:

**Compactness measures ranking plans differently.** Polsby-Popper, Reock,
Schwartzberg and convex hull are not the same question, and CRITERIA.md section 3
records that they disagree. Over an ensemble that is a rank correlation
(:func:`compactness.rank_correlation`); on a single plan it is the spread of the
per-measure percentile ranks within that ensemble.

**Partisan metrics pointing in different directions.** A plan can have a
Republican-favouring efficiency gap and a Democratic-favouring mean-median.
CRITERIA.md section 5.2 is the reason both are reported; a sign split between them
is the single most useful disagreement in the file and is flagged explicitly.

**A metric that is constant by construction.** ``administrative.degeneracy``
already computes this — with one districting layer the ballot style count is
identically the number of districts, and where units are their own subdivisions
county splits are identically zero. A degenerate metric is not a low score, and
reporting it as a value beside varying ones invites exactly that misreading.

Ballot styles per 10,000 voters
-------------------------------
``prompt.md`` calls it a first-class output and *"not an afterthought"*. It is
therefore a required argument here rather than an optional one: :func:`score_plan`
takes an ``electorate`` and raises without it. The alternative -- defaulting it to
``None`` and letting the field come back empty -- is exactly how it stayed
uncomputed while appearing in the metric list.

With the single districting layer this project carries, the raw ballot style count
is degenerate (equal to the district count) and the report says so through
``degeneracy``. Pass a second layer -- a state legislative plan -- and it starts
doing work. See CRITERIA.md section 7.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import administrative, compactness, partisan
from .plan import Plan

#: Partisan metrics whose sign says which party a plan favours. A disagreement in
#: sign between any two of these is reported: they are answering the same question
#: and giving opposite answers, which no single-metric report would ever show.
SIGNED_PARTISAN = ("efficiency_gap", "mean_median", "declination", "partisan_bias")

#: Compactness measures that are all "how compact", on comparable [0, 1]-ish
#: scales where larger is better. Schwartzberg is excluded: it is a ratio where
#: *smaller* is better, so putting it in a spread with the others would
#: manufacture a disagreement out of a sign convention.
COMPARABLE_COMPACTNESS = ("polsby_popper_mean", "reock_mean", "convex_hull_mean")

#: Spread across :data:`COMPARABLE_COMPACTNESS` above which the measures are
#: treated as disagreeing about this plan. CRITERIA.md section 3 uses ~0.9
#: correlation over an ensemble; on a single plan there is no correlation to take,
#: so this is a different statistic with a threshold chosen here and flagged as
#: ours, not the document's.
COMPACTNESS_SPREAD = 0.15


def score_plan(
    plan: Plan,
    *,
    geometry,
    adjacency: Mapping[str, Any],
    units: Any,
    dem: Mapping[str, int],
    rep: Mapping[str, int],
    electorate: Any,
    subdivisions: Any = None,
    contest: str | None = None,
) -> dict:
    """Every metric for one plan, side by side, with disagreements listed.

    Args:
        plan: unit id -> district. A ``Mapping`` of layer name -> plan is also
            accepted and is what makes the ballot style count non-degenerate.
        geometry: units table carrying geometry, for the shape measures.
        adjacency: rook adjacency, for cut edges.
        units: units table or ``{unit: subdivision}`` map for the splits metrics.
        dem, rep: two-party votes by unit. **The partisan half is only as
            meaningful as this one election** -- see ``contest``.
        electorate: total voters, or ``{unit: voters}``. Required:
            ``prompt.md`` makes ballot styles per 10,000 voters a first-class
            output and it cannot be computed without a denominator.
        subdivisions: optional second subdivision layer (municipalities), for the
            municipality-splits metrics. ``None`` omits them rather than
            silently reporting the county numbers under a municipality label.
        contest: the election these votes came from, recorded in the report so a
            reader is never left guessing which one produced the partisan half.

    Returns:
        A mapping with ``partisan``, ``compactness``, ``administrative``,
        ``trust`` and ``disagreements`` keys. No score, no ranking, no weights.
    """
    shape = compactness.all_metrics(plan, geometry, adjacency)
    votes = partisan.all_metrics(plan, dem, rep)
    admin = administrative.all_metrics(plan, units, voters=electorate)

    municipal = None
    if subdivisions is not None:
        municipal = {
            "splits": administrative.county_splits(plan, subdivisions),
            "split_pieces": administrative.split_pieces(plan, subdivisions),
            "layer": "municipality",
            "note": ("municipalities are a partial layer: units in no "
                     "municipality are excluded from these counts, which is why "
                     "they are not comparable to the county figures above"),
        }

    trusted = partisan.trusted_metrics(plan, dem, rep)
    report = {
        "contest": contest,
        "partisan": votes,
        "compactness": shape,
        "administrative": admin,
        "municipal": municipal,
        "trust": {
            "trusted_partisan_metrics": list(trusted),
            "untrusted_partisan_metrics": [
                name for name in partisan.METRICS if name not in trusted
            ],
            "caveats": partisan.caveats(plan, dem, rep),
            "note": ("untrusted metrics are reported above with their values, "
                     "not filtered out: a reader handed a filtered dict cannot "
                     "tell that filtering happened"),
        },
    }
    report["disagreements"] = find_disagreements(report)
    report["combined_score"] = None
    report["combined_score_note"] = (
        "deliberately absent. prompt.md: 'If you find yourself writing a "
        "function called fairness_score() that returns one number, stop.' The "
        "five compactness measures disagree with each other and the partisan "
        "metrics disagree in sign; a single number would hide exactly the "
        "information this report exists to show."
    )
    return report


def find_disagreements(report: Mapping[str, Any]) -> list[dict]:
    """Where the metrics contradict each other, worst first.

    Returns a list of records rather than a verdict. Each says which metrics
    disagree, by how much, and what the disagreement means -- because "Reock and
    Polsby-Popper differ by 0.3" is not actionable to a reader who does not
    already know they measure different things.
    """
    found: list[dict] = []

    shape = report.get("compactness") or {}
    values = {name: shape[name] for name in COMPARABLE_COMPACTNESS if name in shape}
    if len(values) >= 2:
        spread = max(values.values()) - min(values.values())
        if spread > COMPACTNESS_SPREAD:
            found.append({
                "kind": "compactness_measures_disagree",
                "magnitude": spread,
                "values": values,
                "meaning": (
                    f"the compactness measures span {spread:.3f} on this plan "
                    f"({min(values, key=values.get)} lowest, "
                    f"{max(values, key=values.get)} highest). They answer "
                    f"different questions -- perimeter, circumscribing circle, "
                    f"convex hull -- so which one a rule names decides which "
                    f"plans pass it. CRITERIA.md section 3."),
            })

    votes = report.get("partisan") or {}
    signed = {name: votes[name] for name in SIGNED_PARTISAN
              if votes.get(name) is not None}
    positive = [n for n, v in signed.items() if v > 0]
    negative = [n for n, v in signed.items() if v < 0]
    if positive and negative:
        found.append({
            "kind": "partisan_metrics_disagree_in_sign",
            "favouring_one_party": positive,
            "favouring_the_other": negative,
            "values": signed,
            "meaning": (
                "these metrics disagree about which party this plan favours. "
                "Each is a defensible definition of fairness and they are not "
                "reconcilable by picking the 'best' one; CRITERIA.md section "
                "5.2 and arXiv:2409.17186 are the reason all of them are "
                "reported."),
        })

    degeneracy = (report.get("administrative") or {}).get("degeneracy") or {}
    constant = [name for name, record in degeneracy.items()
                if isinstance(record, Mapping) and record.get("constant")]
    if constant:
        found.append({
            "kind": "metrics_constant_by_construction",
            "metrics": sorted(constant),
            "meaning": (
                "these do not vary over any plan on these units, so their value "
                "is a property of the inputs rather than of this plan. A "
                "constant metric is not a good score and must not be read as "
                "one."),
            "reasons": {name: degeneracy[name].get("reason") for name in constant},
        })

    untrusted = (report.get("trust") or {}).get("untrusted_partisan_metrics") or []
    if untrusted:
        found.append({
            "kind": "partisan_metrics_not_trustworthy_here",
            "metrics": untrusted,
            "meaning": (
                "reported above with their values, but this plan and election "
                "sit in a regime where they stop meaning what they appear to "
                "mean. CRITERIA.md section 5.1."),
        })

    found.sort(key=lambda record: -float(record.get("magnitude", 0.0) or 0.0))
    return found


def summary_lines(report: Mapping[str, Any]) -> list[str]:
    """The report as text, for a terminal or a commit message.

    Every family is printed whether or not it is interesting, because
    ``prompt.md`` says *always*, and the disagreements are printed last so they
    are the thing a reader is left holding.
    """
    lines = [f"contest: {report.get('contest') or 'unspecified'}"]

    for family in ("partisan", "compactness", "administrative"):
        block = report.get(family) or {}
        lines.append(f"  {family}:")
        for name, value in block.items():
            if name == "degeneracy" or isinstance(value, (dict, list, tuple)):
                continue
            lines.append(f"    {name:34s} {value}")

    trust = report.get("trust") or {}
    if trust.get("caveats"):
        lines.append("  caveats:")
        lines.extend(f"    - {c}" for c in trust["caveats"])

    disagreements = report.get("disagreements") or []
    lines.append(f"  disagreements: {len(disagreements)}")
    for record in disagreements:
        lines.append(f"    [{record['kind']}] {record['meaning']}")
    return lines
