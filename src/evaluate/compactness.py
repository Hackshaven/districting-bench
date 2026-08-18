"""Compactness: Polsby-Popper, Reock, Schwartzberg, convex hull, cut edges.

`docs/CRITERIA.md` section 3 is authoritative here, and its heading is the point
of the module: *four measures that disagree*. All of them are `VALUE` class.
There is no correct compactness measure, so this module computes every one of
them, reports them side by side, and never combines them. Nothing here returns a
single compactness number for a plan, and nothing here ranks plans.

Each measure and the failure mode CRITERIA.md section 3 records for it:

===============  ===========================  ======================================
measure          formula                      failure mode (CRITERIA.md section 3)
===============  ===========================  ======================================
Polsby-Popper    4*pi*A / P^2                 perimeter-sensitive; punishes natural
                                              coastlines and river borders
Reock            A / A(min bounding circle)   insensitive to boundary detail; a
                                              ragged district can score well
Schwartzberg     P / circumference of the     same perimeter sensitivity as
                 equal-area circle            Polsby-Popper, different scaling
convex hull      A / A(convex hull)           punishes legitimately concave
                                              geography (bays, valleys)
cut edges        adjacent unit pairs split    immune to coastline fractality;
                 between districts            depends on the unit graph
===============  ===========================  ======================================

**Direction is not uniform, and this module does not silently normalise it.**
Polsby-Popper, Reock and convex hull are in ``(0, 1]`` with 1 the most compact.
Schwartzberg as CRITERIA.md defines it is a perimeter *ratio* in ``[1, inf)``
with 1 the most compact, so a *higher* Schwartzberg means a *worse* district;
many published tables report its reciprocal instead, which is exactly
``sqrt(polsby_popper)``. Cut edges is a count, and lower is more compact. See
:data:`DIRECTION`, which is the machine-readable form of this paragraph and is
what :func:`rank_correlation` uses so that its correlations are not sign
artifacts.

Geometry conventions, all of which change the numbers:

* ``geom`` is expected in an equal-area projected CRS (EPSG:5070 for this
  project, DECISIONS D-005). A geographic CRS raises: degrees are not a length
  unit and every area-based measure would be meaningless.
* Districts are formed by dissolving (unioning) the units assigned to them.
  Measures are taken on the dissolved district, never unit-by-unit.
* Perimeter is ``shapely``'s ``length``, which counts interior rings (holes) and
  every part of a multipart district. A district with an enclave is genuinely
  less compact under a perimeter measure, and hiding that would be a choice.
* No projection preserves both area and perimeter, so Polsby-Popper and
  Schwartzberg are projection-dependent in principle. D-005 measured the effect
  on Iowa at ~0.1% and standardised on EPSG:5070 anyway.

This module imports nothing from ``src/`` (``tools/firewall.yaml``:
``evaluate.allowed_imports = []``). It duplicates a little of what
``src/evaluate/plan.py`` does with district membership; that duplication is
cheaper than an import edge, and the plan loader lives there, not here.
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence

import shapely

Plan = Mapping[str, int]

#: The four shape-based measures, in the order they are reported.
SHAPE_MEASURES: tuple[str, ...] = (
    "polsby_popper",
    "reock",
    "schwartzberg",
    "convex_hull",
)

#: Every measure this module produces, shape-based plus the graph-based one.
MEASURES: tuple[str, ...] = SHAPE_MEASURES + ("cut_edges",)

#: ``+1`` where a larger value means a more compact district, ``-1`` where a
#: larger value means a less compact one. CRITERIA.md defines Schwartzberg as a
#: perimeter ratio (1 = circle, larger = worse); cut edges is a count of split
#: adjacencies. Consumers that need a common orientation should multiply by
#: this rather than assuming every measure points the same way.
DIRECTION: dict[str, int] = {
    "polsby_popper": +1,
    "reock": +1,
    "schwartzberg": -1,
    "convex_hull": +1,
    "cut_edges": -1,
}

#: Number of ids an error message lists before truncating.
_MAX_LISTED = 8


# --------------------------------------------------------------------------- #
# district geometry
# --------------------------------------------------------------------------- #

def district_geometries(plan: Plan, geom) -> dict[int, "shapely.Geometry"]:
    """Dissolve ``geom``'s units into one geometry per district.

    ``geom`` is a GeoDataFrame carrying a ``GEOID`` column (or a GEOID index)
    and a geometry column, as written by ``tools/prepare_data.py``.

    Raises ValueError if the CRS is geographic, if GEOIDs repeat, if the plan
    and the geometry table do not cover exactly the same units, or if a
    dissolved district is empty or invalid. Every one of those conditions
    otherwise yields a plausible-looking wrong number rather than an error:
    a missing county silently shrinks a district, and an invalid union silently
    corrupts its perimeter.
    """
    crs = getattr(geom, "crs", None)
    if crs is not None and getattr(crs, "is_geographic", False):
        raise ValueError(
            f"compactness needs a projected equal-area CRS; geom is in "
            f"{crs.name!r}, which is geographic. Areas and perimeters in "
            f"degrees are not comparable quantities. Reproject to EPSG:5070 "
            f"(DECISIONS D-005)."
        )

    if "GEOID" in getattr(geom, "columns", ()):
        keys = [str(k) for k in geom["GEOID"]]
    else:
        keys = [str(k) for k in geom.index]
    geometries = list(geom.geometry)

    seen: dict[str, int] = {}
    duplicates = []
    for key in keys:
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            duplicates.append(key)
    if duplicates:
        raise ValueError(
            f"geom has {len(duplicates)} repeated GEOID(s): "
            f"{_sample(sorted(duplicates))}"
        )

    lookup = dict(zip(keys, geometries))
    plan_keys = {str(g) for g in plan}
    missing = sorted(plan_keys - set(lookup))
    if missing:
        raise ValueError(
            f"no geometry for {len(missing)} unit(s) in the plan: "
            f"{_sample(missing)}"
        )
    extra = sorted(set(lookup) - plan_keys)
    if extra:
        raise ValueError(
            f"geom carries {len(extra)} unit(s) the plan does not assign: "
            f"{_sample(extra)}. Measuring a district from a partial plan "
            f"understates its area."
        )

    members: dict[int, list] = {}
    for unit, district in plan.items():
        members.setdefault(int(district), []).append(lookup[str(unit)])

    out: dict[int, "shapely.Geometry"] = {}
    for district in sorted(members):
        dissolved = shapely.union_all(members[district])
        if dissolved.is_empty:
            raise ValueError(f"district {district} dissolves to an empty geometry")
        if not dissolved.is_valid:
            raise ValueError(
                f"district {district} dissolves to an invalid geometry "
                f"({shapely.is_valid_reason(dissolved)}). Fix the unit "
                f"geometry rather than buffering it away here: buffer(0) "
                f"changes area and perimeter, which are the numbers being "
                f"measured."
            )
        out[district] = dissolved
    return out


def _area_perimeter(district: int, shape) -> tuple[float, float]:
    """Area and perimeter of a district, with the degenerate cases named."""
    area = float(shape.area)
    perimeter = float(shape.length)
    if area <= 0.0:
        raise ValueError(
            f"district {district} has zero area; every area-based compactness "
            f"measure is undefined for it"
        )
    if perimeter <= 0.0:
        raise ValueError(
            f"district {district} has zero perimeter; Polsby-Popper and "
            f"Schwartzberg are undefined for it"
        )
    return area, perimeter


# --------------------------------------------------------------------------- #
# the four shape measures
# --------------------------------------------------------------------------- #

def _polsby_popper_of(district: int, shape) -> float:
    area, perimeter = _area_perimeter(district, shape)
    return 4.0 * math.pi * area / (perimeter * perimeter)


def polsby_popper(plan: Plan, geom) -> dict[int, float]:
    """``4*pi*A / P**2`` per district. 1.0 for a circle, ``pi/4`` for a square.

    In ``(0, 1]``; higher is more compact.

    *Failure mode* (CRITERIA.md section 3): perimeter-sensitive, and perimeter
    is the least stable thing about a polygon. Natural borders — coastlines,
    river centerlines — are punished severely however the lines are drawn, and
    generalising the source geometry changes the score materially (D-003).
    """
    return {
        d: _polsby_popper_of(d, shape)
        for d, shape in district_geometries(plan, geom).items()
    }


def reock(plan: Plan, geom) -> dict[int, float]:
    """``A / A(minimum bounding circle)`` per district. 1.0 for a circle.

    In ``(0, 1]``; higher is more compact. ``2/pi`` for a square,
    ``3*sqrt(3)/(4*pi)`` for an equilateral triangle.

    *Failure mode* (CRITERIA.md section 3): insensitive to boundary detail. A
    district can be visibly ragged — a fractal border, a comb of tendrils —
    and still score well, because only the extreme points determine the circle.
    Reock and Polsby-Popper disagree on real plans for exactly this reason.
    """
    return {
        d: _reock_of(d, shape)
        for d, shape in district_geometries(plan, geom).items()
    }


def _reock_of(district: int, shape) -> float:
    area, _ = _area_perimeter(district, shape)
    radius = float(shapely.minimum_bounding_radius(shape))
    if radius <= 0.0:
        raise ValueError(
            f"district {district} has a degenerate minimum bounding circle; "
            f"Reock is undefined for it"
        )
    return area / (math.pi * radius * radius)


def schwartzberg(plan: Plan, geom) -> dict[int, float]:
    """``P / circumference of the equal-area circle``, per CRITERIA.md.

    Equivalently ``P / (2*sqrt(pi*A))``, and identically
    ``1 / sqrt(polsby_popper)``.

    In ``[1, inf)``; **1.0 is a circle and higher is worse** — the opposite
    direction from the other three measures. This module follows CRITERIA.md's
    definition rather than the reciprocal reported by some scorers, and records
    the direction in :data:`DIRECTION` so that no consumer has to infer it. A
    square scores ``2/sqrt(pi) ~ 1.1284``.

    *Failure mode* (CRITERIA.md section 3): the same perimeter sensitivity as
    Polsby-Popper, on a different scale. It is a monotone transform of
    Polsby-Popper, so it carries **no independent information about a plan** —
    it can reorder nothing. It is reported because it is the number some
    jurisdictions and scorers use, not because it is a fifth opinion.
    """
    return {
        d: _schwartzberg_of(d, shape)
        for d, shape in district_geometries(plan, geom).items()
    }


def _schwartzberg_of(district: int, shape) -> float:
    area, perimeter = _area_perimeter(district, shape)
    return perimeter / (2.0 * math.sqrt(math.pi * area))


def convex_hull(plan: Plan, geom) -> dict[int, float]:
    """``A / A(convex hull)`` per district. 1.0 for any convex district.

    In ``(0, 1]``; higher is more compact.

    *Failure mode* (CRITERIA.md section 3): punishes legitimately concave
    geography. A district following a bay, a mountain valley or a state border
    that bends inward scores badly for a reason that has nothing to do with how
    it was drawn. Note also that a square, a triangle and a long thin rectangle
    all score exactly 1.0 — convex hull says nothing whatever about elongation.
    """
    return {
        d: _convex_hull_of(d, shape)
        for d, shape in district_geometries(plan, geom).items()
    }


def _convex_hull_of(district: int, shape) -> float:
    area, _ = _area_perimeter(district, shape)
    hull = float(shape.convex_hull.area)
    if hull <= 0.0:
        raise ValueError(
            f"district {district} has a degenerate convex hull; the convex "
            f"hull ratio is undefined for it"
        )
    return area / hull


#: The four shape measures as functions of one dissolved district geometry.
_SHAPE_FUNCTIONS = {
    "polsby_popper": _polsby_popper_of,
    "reock": _reock_of,
    "schwartzberg": _schwartzberg_of,
    "convex_hull": _convex_hull_of,
}


def measure_districts(plan: Plan, geom) -> dict[str, dict[int, float]]:
    """All four shape measures, dissolving each district exactly once.

    ``{measure name: {district: value}}``. The single-measure functions above
    are the readable entry points; this one is what to call when you want more
    than one of them, since the union is the expensive step and calling four
    functions repeats it four times.
    """
    shapes = district_geometries(plan, geom)
    return {
        name: {d: fn(d, shape) for d, shape in shapes.items()}
        for name, fn in _SHAPE_FUNCTIONS.items()
    }


# --------------------------------------------------------------------------- #
# the graph measure
# --------------------------------------------------------------------------- #

def cut_edges(plan: Plan, adjacency: Mapping[str, Iterable[str]]) -> int:
    """Count adjacent unit pairs assigned to different districts.

    Edges are counted once. ``adjacency`` is the rook graph as
    ``{GEOID: [GEOID, ...]}`` (D-004); it is treated as undirected, so a pair
    listed in only one direction still counts once, and a pair listed in both
    directions still counts once.

    Whole-plan, not per-district: an edge belongs to two districts, so
    attributing it to one would be arbitrary. Lower is more compact.

    *Failure mode* (CRITERIA.md section 3): immune to coastline fractality,
    which is the point of it, but it depends entirely on the unit graph. The
    same plan measured on counties and on precincts gives unrelated numbers,
    and rook-versus-queen alone changes Iowa's graph by a third (FEASIBILITY.md
    section 3). It is also not intuitive to a non-technical reader.

    Raises ValueError if the plan and the graph do not cover the same units:
    an unassigned node silently drops every edge on it.
    """
    plan_str = {str(u): int(d) for u, d in plan.items()}
    nodes = {str(n) for n in adjacency}
    unassigned = sorted(nodes - set(plan_str))
    if unassigned:
        raise ValueError(
            f"cut_edges: {len(unassigned)} unit(s) in the adjacency graph are "
            f"unassigned: {_sample(unassigned)}"
        )
    unknown = sorted(set(plan_str) - nodes)
    if unknown:
        raise ValueError(
            f"cut_edges: the plan assigns {len(unknown)} unit(s) that are not "
            f"nodes of the adjacency graph: {_sample(unknown)}"
        )

    counted: set[frozenset[str]] = set()
    for unit, neighbours in adjacency.items():
        u = str(unit)
        for neighbour in neighbours:
            v = str(neighbour)
            if v not in plan_str:
                raise ValueError(
                    f"cut_edges: unit {u} is adjacent to {v}, which the plan "
                    f"does not assign"
                )
            if plan_str[u] != plan_str[v]:
                counted.add(frozenset((u, v)))
    return len(counted)


# --------------------------------------------------------------------------- #
# per-plan summaries
# --------------------------------------------------------------------------- #

def all_metrics(plan: Plan, geom, adjacency: Mapping[str, Iterable[str]]) -> dict[str, float]:
    """Per-plan summaries of every measure, reported side by side.

    Returns ``mean``, ``min`` and ``max`` across districts for each of the four
    shape measures, plus ``cut_edges`` and ``n_districts``.

    **Which end is the bad end differs by measure.** For Polsby-Popper, Reock
    and convex hull the ``min`` is the worst district; for Schwartzberg the
    ``max`` is. Both ends are reported for every measure so that no consumer has
    to know that, and :data:`DIRECTION` states it explicitly. There is
    deliberately no ``compactness`` key: collapsing four disagreeing `VALUE`
    measures into one number is the failure mode `prompt.md` forbids, and the
    disagreement between them is itself the finding (CRITERIA.md section 3).

    The mean is an unweighted mean over districts, not population- or
    area-weighted. That is a choice: it treats a 36-county district and a
    4-county district as equally important, which is what "the districts should
    each be compact" means, but it is not the only defensible reading.
    """
    per_measure = measure_districts(plan, geom)
    if not per_measure["polsby_popper"]:
        raise ValueError("all_metrics: plan has no districts")

    out: dict[str, float] = {}
    for name in SHAPE_MEASURES:
        values = [per_measure[name][d] for d in sorted(per_measure[name])]
        out[f"{name}_mean"] = sum(values) / len(values)
        out[f"{name}_min"] = min(values)
        out[f"{name}_max"] = max(values)
    out["cut_edges"] = cut_edges(plan, adjacency)
    out["n_districts"] = len(per_measure["polsby_popper"])
    return out


def metric_series(
    plans: Sequence[Plan], geom, adjacency: Mapping[str, Iterable[str]]
) -> dict[str, list[float]]:
    """One value per plan for each measure in :data:`MEASURES`.

    The shape measures are summarised by their **unweighted mean over
    districts**; ``cut_edges`` is already a whole-plan number. That summary
    choice is a real one — correlating the *minimum* district instead can give
    different answers, because the measures disagree most on the worst district
    — and it is stated here rather than buried in :func:`rank_correlation`.
    """
    if len(plans) == 0:
        raise ValueError("metric_series: no plans given")
    series: dict[str, list[float]] = {name: [] for name in MEASURES}
    for plan in plans:
        summary = all_metrics(plan, geom, adjacency)
        for name in SHAPE_MEASURES:
            series[name].append(float(summary[f"{name}_mean"]))
        series["cut_edges"].append(float(summary["cut_edges"]))
    return series


# --------------------------------------------------------------------------- #
# do the measures agree?
# --------------------------------------------------------------------------- #

def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman rank correlation, ties given average ranks.

    Returns ``nan`` when either input has zero variance in its ranks — every
    value tied. That is the honest answer: with one distinct value there is no
    ordering to agree or disagree about, and returning 0.0 would read as
    "the measures are unrelated", which is a different claim.
    """
    if len(x) != len(y):
        raise ValueError(f"spearman: length mismatch, {len(x)} vs {len(y)}")
    if len(x) < 2:
        raise ValueError("spearman: need at least 2 observations")
    rx = _average_ranks(x)
    ry = _average_ranks(y)
    n = len(rx)
    mx = sum(rx) / n
    my = sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx <= 0.0 or syy <= 0.0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def _average_ranks(values: Sequence[float]) -> list[float]:
    """Ranks 1..n, tied values sharing the average of the ranks they span."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def rank_correlation(
    plans: Sequence[Plan], geom, adjacency: Mapping[str, Iterable[str]]
) -> dict[tuple[str, str], float]:
    """Spearman correlation between every pair of measures across an ensemble.

    This answers the `EMPIRICAL` question CRITERIA.md section 3 asks: do these
    measures actually rank plans differently on this state's geography? If they
    correlate above ~0.9 the choice of measure does not matter here and we can
    say so; if they diverge, the choice is doing real work and must be surfaced
    to the user rather than resolved for them.

    It is also a correctness check on this module. `prompt.md`: "if all your
    compactness measures correlate above 0.95, either the state has simple
    geography or you have implemented the same measure five times." Read the
    result with that in mind, and with one caveat: ``schwartzberg`` is a
    monotone transform of ``polsby_popper`` *per district*, so those two
    should correlate at or very near 1.0 whatever the geography — the mean over
    districts is not quite a monotone transform of the mean, so the entry is
    near 1.0 rather than exactly 1.0, but it is not evidence of anything. Only
    the pairs among Polsby-Popper, Reock, convex hull and cut edges can tell
    you whether the choice of measure is doing work.

    **Every series is oriented so that higher means more compact** (multiplied
    by :data:`DIRECTION`) before ranking, so a positive correlation always means
    agreement. Without that, Schwartzberg and cut edges would report ``-1``
    where they agree perfectly, which is a sign artifact, not a finding.

    Keys are ``(measure_a, measure_b)`` with the pair in :data:`MEASURES` order,
    each unordered pair appearing once. A value is ``nan`` if either measure is
    constant across the ensemble (see :func:`spearman`).
    """
    if len(plans) < 2:
        raise ValueError(
            f"rank_correlation: need at least 2 plans to correlate; got "
            f"{len(plans)}"
        )
    series = metric_series(plans, geom, adjacency)
    oriented = {
        name: [DIRECTION[name] * v for v in series[name]] for name in MEASURES
    }
    out: dict[tuple[str, str], float] = {}
    for i, a in enumerate(MEASURES):
        for b in MEASURES[i + 1:]:
            out[(a, b)] = spearman(oriented[a], oriented[b])
    return out


def disagreements(
    correlations: Mapping[tuple[str, str], float], threshold: float = 0.9
) -> list[tuple[tuple[str, str], float]]:
    """Pairs correlating below ``threshold``, weakest first.

    CRITERIA.md section 3: "Report all of them, always, and highlight
    disagreements rather than resolving them." This is the highlight step. The
    default threshold is section 3's own ~0.9, above which "the choice does not
    matter there and you can say so". ``nan`` pairs are treated as
    disagreements, because an undefined correlation is not evidence of
    agreement.
    """
    flagged = [
        (pair, value)
        for pair, value in correlations.items()
        if math.isnan(value) or value < threshold
    ]
    flagged.sort(key=lambda item: (0.0 if math.isnan(item[1]) else item[1] + 1.0))
    return flagged


def _sample(ids: list[str]) -> str:
    """Render at most _MAX_LISTED ids for an error message."""
    head = list(ids[:_MAX_LISTED])
    tail = "" if len(ids) <= _MAX_LISTED else f" ... (+{len(ids) - _MAX_LISTED} more)"
    return f"{head}{tail}"
