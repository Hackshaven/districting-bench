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

* ``geom`` must carry a projected CRS that is *locally undistorted over its own
  extent*. This is checked, not assumed; see "The projection guard" below.
* Districts are formed by dissolving (unioning) the units assigned to them.
  Measures are taken on the dissolved district, never unit-by-unit.
* Perimeter is ``shapely``'s ``length``, which counts interior rings (holes) and
  every part of a multipart district. A district with an enclave is genuinely
  less compact under a perimeter measure, and hiding that would be a choice.


The projection guard
--------------------

**The previous version of this docstring made a false claim, and it is worth
recording what it was.** It said: "D-005 measured the effect on Iowa at ~0.1%
and standardised on EPSG:5070 anyway." D-005 measured no such thing. It measured
**area** error between projections — total area +0.020% (EPSG:26975), +0.033%
(26976), -0.033% (26915), worst per-county +0.113%. It never measured the effect
on Polsby-Popper or on any other compactness measure. Those are ratios of area to
a *shape* quantity, and shape distortion does not have to be the size of area
distortion. Attaching an area figure to a compactness claim was the error, and it
was the sentence that justified accepting any projected CRS at all.

Re-measured directly, on Iowa's enacted CD118 plan, as the maximum change in the
per-district value against EPSG:5070:

======  =============  =============  ===========  ============  ==========
CRS     Polsby-Popper  Reock          convex hull  Schwartzberg  area
======  =============  =============  ===========  ============  ==========
26975   0.420%         **1.146%**     0.021%       0.211%        0.064%
26976   0.427%         **1.162%**     0.027%       0.214%        0.064%
26915   0.426%         **1.157%**     0.023%       0.214%        0.061%
======  =============  =============  ===========  ============  ==========

So the true sensitivity of Polsby-Popper is ~4x, and of Reock ~11x, the area
figure that was being quoted for it.

It is not decision-neutral either. On 308 distinct ReCom plans at eps=2e-4 plus
the enacted plan, reprojecting from EPSG:5070 to EPSG:26975 leaves the Spearman
correlation at 0.9987 for Reock but still moves **263 of 309** plans in the Reock
ranking, by up to 17 places, and moves the enacted plan's Reock percentile from
91.2 to 90.3. Polsby-Popper moves 176 of 309 and the enacted plan from 75.0 to
74.4. Those shifts are small, but an outlier test reports a percentile against a
tail threshold, and 1 percentile point at the 90th is not nothing.

**Decision: the module does NOT require an equal-area CRS. It requires a
measured local isometry instead.** Requiring equal area is the obvious fix, and
it was the one proposed when this was found. It was tested and rejected on
evidence, because it is wrong in both directions:

* EPSG:6933 (WGS84 / NSIDC EASE-Grid 2.0) **is** an equal-area CRS. On Iowa it
  moves Polsby-Popper by 8.5% and Reock by **22.6%**. A cylindrical equal-area
  projection buys exact area by stretching north-south and squashing east-west
  (measured at Iowa's centroid: 0.858 vs 1.166), and both of those land directly
  on perimeter and on the minimum bounding circle.
* EPSG:26975 (Iowa North, Lambert *conformal* conic) is **not** equal-area, and
  it agrees to within 0.004% on Reock with a Lambert azimuthal equal-area
  projection centred on Iowa, which is the least-distorted projection available
  for this state.

Equal area constrains the numerator of three of the four measures and says
nothing about the denominators, which is where the error actually is. The
property all four measures need is that the projection restricted to the data's
own extent is a *similarity* of the true surface: locally isotropic (so shape is
faithful) and of uniform scale across the extent (the measures are dimensionless,
so a constant scale factor cancels; a varying one does not). That is directly
measurable, and :func:`crs_distortion` measures it at five points spanning the
data's bounding box, using the ellipsoidal scale factors north and east:

============  ===============  ============  ==============================
CRS           max |h/k - 1|    scale spread  verdict
============  ===============  ============  ==============================
LAEA @ Iowa   0.03%            0.00%         reference; least distorted
EPSG:26975    0.00%            0.07%         accepted
EPSG:26915    0.00%            0.12%         accepted
EPSG:2163     0.70%            0.04%         accepted
**EPSG:5070** **1.78%**        0.00%         accepted (see below)
EPSG:3857     0.40%            **4.99%**     rejected: scale varies with lat
EPSG:6933     **29.75%**       0.00%         rejected: equal-area but sheared
============  ===============  ============  ==============================

Across those, anisotropy predicts the error well: measured deviation from a
locally fitted projection is ~0.32x the anisotropy for Polsby-Popper and ~0.85x
for Reock, holding over two decades (EPSG:5070 at 1.4% anisotropy at Iowa's
centroid -> 0.43% / 1.15%; EPSG:6933 at 26.4% -> 8.5% / 22.6%). The tolerances
are set from that, and from where EPSG:5070 itself lands: Albers CONUS is
anisotropic by 2.40% at 25N and 2.46% at 49N, so a 2% limit would reject the
project's own standard for Florida and for Minnesota. :data:`MAX_ANISOTROPY` is
therefore 3%, bounding the artifact at ~1.0% on Polsby-Popper and ~2.6% on Reock;
EPSG:6933 misses it by nearly a factor of ten (29.7%). The guard measures the
property, not the CRS's reputation — Web Mercator over a small enough extent is
very nearly conformal and uniform in scale, and would legitimately pass.

**The uncomfortable corollary, stated rather than buried: EPSG:5070 is the most
distorted CRS that passes.** Iowa sits between Albers CONUS's standard parallels
(29.5N / 45.5N), where the projection stretches north-south by 0.7% and compresses
east-west by 0.7%. The ~1.15% Reock and ~0.43% Polsby-Popper differences in the
first table are therefore better read as *EPSG:5070's* artifact than as the
alternatives'. EPSG:5070 is kept anyway, because it is the project standard
(D-005, ``tools/prepare_data.py``), because one fixed projection across the
ensemble and the subject plan matters far more than 1% on a `VALUE` measure, and
because the guard now bounds the artifact instead of assuming it away. That
EPSG:5070 is not the least-distorted choice for a single-state bench is a finding
for D-005 to consider; this module does not own that decision and does not
quietly override it.

**What the guard cannot do is enforce consistency between calls.** Percentiles
are only meaningful if the ensemble and the plan being located in it were measured
in the same CRS, and nothing visible from inside one call can check that. So
:func:`crs_distortion` is public: record its output next to any published number
(``bench-results.json``), and a later reader can tell whether two figures are
comparable.

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

#: Largest permitted ``|h/k - 1|`` — local anisotropy — anywhere over the data's
#: bounding box. See "The projection guard" in the module docstring. 3% is the
#: smallest round number that admits EPSG:5070 everywhere in CONUS: Albers CONUS
#: is anisotropic by 1.78% over Iowa but by 2.40% at 25N and 2.46% at 49N, so a
#: 2% limit would reject the project's own standard for Florida and Minnesota.
#: At 3% the projection artifact is bounded at ~1.0% on Polsby-Popper and ~2.6%
#: on Reock; EPSG:6933 exceeds it nearly tenfold, at 29.7% over Iowa.
MAX_ANISOTROPY = 0.03

#: Largest permitted spread in the local scale factor ``sqrt(h*k)`` across the
#: data's bounding box. The measures are dimensionless, so a *constant* scale
#: factor cancels exactly and is not checked; a scale factor that varies across
#: the extent does not cancel. This is what rejects EPSG:3857 (4.99% on Iowa).
MAX_SCALE_SPREAD = 0.02

#: Step length in metres used to probe the local scale factors. Small enough
#: that the projection is locally linear, large enough that float64 coordinate
#: differences carry ~10 significant digits.
_PROBE_METRES = 1000.0

#: Sentinel for "make me a cache". ``cache=None`` means *no* cache everywhere in
#: this module; the ensemble entry points default to :data:`AUTO_CACHE` instead,
#: which builds a fresh one. Without the distinction, ``cache=None`` would mean
#: "off" in one function and "on" in another, and a benchmark that passed
#: ``None`` expecting the slow path would silently measure the fast one. It did.
AUTO_CACHE = object()

#: Cached distortion reports, keyed by ``(crs wkt, rounded bounds)``. One entry
#: per (projection, dataset); the bench uses one of each.
_DISTORTION_CACHE: dict[tuple, dict] = {}
_DISTORTION_CACHE_MAX = 32


# --------------------------------------------------------------------------- #
# the projection guard
# --------------------------------------------------------------------------- #

def crs_distortion(crs, bounds: Sequence[float]) -> dict[str, float]:
    """Measure how far ``crs`` is from a similarity of the true surface.

    ``bounds`` is ``(minx, miny, maxx, maxy)`` **in ``crs``'s own units** — a
    GeoDataFrame's ``total_bounds``. Five points (the four corners and the
    centre) are probed; at each, a 1 km geodesic step north and a 1 km geodesic
    step east are projected and their projected lengths taken as the local scale
    factors ``h`` and ``k``.

    Returns ``{"anisotropy": max |h/k - 1|, "scale_spread": max/min of
    sqrt(h*k) minus 1, "crs": <srs string>}``.

    ``anisotropy`` is the shape distortion — the quantity Polsby-Popper and
    Reock are actually sensitive to. ``scale_spread`` is the non-uniformity of
    size; uniform scale cancels out of every measure here and is deliberately not
    reported as an error. Both are 0.0 for a projection that is locally a rigid
    motion over the extent.

    Record this next to any published compactness number. Two numbers measured
    under different projections are not comparable, and this is the evidence a
    later reader needs to tell.
    """
    from pyproj import CRS, Geod, Transformer

    crs = CRS.from_user_input(crs)
    minx, miny, maxx, maxy = (float(v) for v in bounds)
    if not all(math.isfinite(v) for v in (minx, miny, maxx, maxy)):
        raise ValueError(
            f"crs_distortion: bounds {tuple(bounds)!r} are not finite; an empty "
            f"geometry table has no extent to check a projection over"
        )
    to_lonlat = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
    from_lonlat = Transformer.from_crs(CRS.from_epsg(4326), crs, always_xy=True)
    geod = Geod(ellps="WGS84")

    samples = [
        (minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy),
        ((minx + maxx) / 2.0, (miny + maxy) / 2.0),
    ]
    anisotropy = 0.0
    scales: list[float] = []
    for x, y in samples:
        lon, lat = to_lonlat.transform(x, y)
        if not (math.isfinite(lon) and math.isfinite(lat)):
            raise ValueError(
                f"cannot invert {crs.srs!r} at the corner ({x}, {y}) of the "
                f"data's own bounding box; the geometry is not in this CRS, or "
                f"the CRS is not valid over the data's extent"
            )
        factors = []
        for azimuth in (0.0, 90.0):
            lon1, lat1, _ = geod.fwd(lon, lat, azimuth, _PROBE_METRES)
            x1, y1 = from_lonlat.transform(lon1, lat1)
            factors.append(math.hypot(x1 - x, y1 - y) / _PROBE_METRES)
        h, k = factors
        if h <= 0.0 or k <= 0.0:
            raise ValueError(
                f"{crs.srs!r} collapses a 1 km step to zero length at "
                f"({lon:.4f}, {lat:.4f}); it is degenerate over this extent"
            )
        anisotropy = max(anisotropy, abs(h / k - 1.0))
        scales.append(math.sqrt(h * k))
    return {
        "crs": crs.srs,
        "anisotropy": anisotropy,
        "scale_spread": max(scales) / min(scales) - 1.0,
    }


def _check_crs(geom) -> None:
    """Reject any ``geom`` whose CRS cannot support an area/perimeter measure.

    Three refusals, in the order a wrong input is most likely to arrive:

    1. **No CRS at all.** ``crs=None`` is not "unitless planar coordinates"; it
       is "nobody said", and the single most common thing it turns out to be is
       degrees. Iowa's counties read as lon/lat with no CRS give Polsby-Popper
       values 5.2% off on district 1 — plausible, wrong, and silent. There is no
       reading of ``None`` under which this module can promise anything, so it
       refuses. (Synthetic figures are not an exception: label them with the CRS
       whose planar arithmetic you mean, which is what the tests do.)
    2. **A geographic CRS.** Degrees are not a length unit.
    3. **A projected CRS that distorts shape over the data's own extent**, past
       :data:`MAX_ANISOTROPY` / :data:`MAX_SCALE_SPREAD`. See the module
       docstring: this is what "equal-area" is usually a proxy for, and it is a
       poor proxy in both directions.
    """
    crs = getattr(geom, "crs", None)
    if crs is not None and not hasattr(crs, "is_geographic"):
        # a plain string, an EPSG int, a proj4 dict: normalise rather than
        # crash on the first attribute this function reaches for.
        from pyproj import CRS

        crs = CRS.from_user_input(crs)
    if crs is None:
        raise ValueError(
            "compactness needs a geometry table with a CRS; geom.crs is None. "
            "Unlabelled coordinates are most often degrees, and every measure "
            "here would then return a plausible wrong number instead of "
            "raising. Set the CRS the coordinates are actually in — for this "
            "project's data that is EPSG:5070 (D-005)."
        )
    if getattr(crs, "is_geographic", False):
        raise ValueError(
            f"compactness needs a projected CRS; geom is in {crs.name!r}, "
            f"which is geographic. Areas and perimeters in degrees are not "
            f"comparable quantities. Reproject to EPSG:5070 (D-005)."
        )

    bounds = tuple(round(float(v), 3) for v in geom.total_bounds)
    key = (crs.to_wkt(), bounds)
    report = _DISTORTION_CACHE.get(key)
    if report is None:
        report = crs_distortion(crs, bounds)
        if len(_DISTORTION_CACHE) >= _DISTORTION_CACHE_MAX:
            _DISTORTION_CACHE.clear()
        _DISTORTION_CACHE[key] = report

    if report["anisotropy"] > MAX_ANISOTROPY:
        raise ValueError(
            f"compactness needs a projection that is locally undistorted over "
            f"the data's extent; {crs.name!r} is anisotropic by "
            f"{report['anisotropy'] * 100:.2f}% there (limit "
            f"{MAX_ANISOTROPY * 100:.0f}%). Shape distortion of that size lands "
            f"directly on perimeter and on the minimum bounding circle: "
            f"expect roughly {report['anisotropy'] * 32:.1f}% on Polsby-Popper "
            f"and {report['anisotropy'] * 85:.1f}% on Reock. Note that being "
            f"equal-area does not help here — EPSG:6933 is equal-area and is "
            f"22.6% out on Reock for Iowa. Reproject to EPSG:5070 (D-005)."
        )
    if report["scale_spread"] > MAX_SCALE_SPREAD:
        raise ValueError(
            f"compactness needs a projection whose scale is uniform over the "
            f"data's extent; {crs.name!r} varies by "
            f"{report['scale_spread'] * 100:.2f}% there (limit "
            f"{MAX_SCALE_SPREAD * 100:.0f}%). A constant scale factor would "
            f"cancel out of every measure here; a varying one does not. "
            f"Reproject to EPSG:5070 (D-005)."
        )


# --------------------------------------------------------------------------- #
# district geometry
# --------------------------------------------------------------------------- #

def _unit_lookup(geom) -> dict[str, "shapely.Geometry"]:
    """``{GEOID: geometry}`` from a checked geometry table."""
    _check_crs(geom)

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
    return dict(zip(keys, geometries))


def _members(plan: Plan, lookup: Mapping[str, object]) -> dict[int, list[str]]:
    """``{district: [GEOID, ...]}``, refusing any mismatch with ``lookup``."""
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
    out: dict[int, list[str]] = {}
    for unit, district in plan.items():
        out.setdefault(int(district), []).append(str(unit))
    return out


def _dissolve(district: int, units: Iterable[str], lookup: Mapping[str, object]):
    """Union one district's units, refusing an empty or invalid result."""
    dissolved = shapely.union_all([lookup[u] for u in units])
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
    return dissolved


def district_geometries(plan: Plan, geom) -> dict[int, "shapely.Geometry"]:
    """Dissolve ``geom``'s units into one geometry per district.

    ``geom`` is a GeoDataFrame carrying a ``GEOID`` column (or a GEOID index)
    and a geometry column, as written by ``tools/prepare_data.py``.

    Raises ValueError if the CRS is absent, geographic or shape-distorting over
    the data's extent (see :func:`_check_crs`), if GEOIDs repeat, if the plan
    and the geometry table do not cover exactly the same units, or if a
    dissolved district is empty or invalid. Every one of those conditions
    otherwise yields a plausible-looking wrong number rather than an error:
    a missing county silently shrinks a district, and an invalid union silently
    corrupts its perimeter.

    This is the un-memoized path and returns geometry rather than numbers. For
    measuring an ensemble use :func:`measure_districts` with a
    :class:`MeasureCache`; see that class for why.
    """
    lookup = _unit_lookup(geom)
    members = _members(plan, lookup)
    return {d: _dissolve(d, members[d], lookup) for d in sorted(members)}


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
    The projection matters too, by ~0.43% on Iowa; see the module docstring.
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

    It is also **the most projection-sensitive of the four**: ~1.15% on Iowa
    against ~0.43% for Polsby-Popper and ~0.03% for convex hull, because the
    bounding circle is fixed by two or three extreme points and any shear moves
    them. See the module docstring.
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

    It is the least projection-sensitive of the four (~0.03% on Iowa): both
    numerator and denominator are areas, so an affine distortion very nearly
    cancels.
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


# --------------------------------------------------------------------------- #
# memoization across an ensemble
# --------------------------------------------------------------------------- #

class MeasureCache:
    """Memoize the four shape measures on the frozenset of a district's units.

    **Why this exists.** Dissolving a district is ~93% of the cost of measuring
    a plan, and ReCom changes exactly 2 of K districts per step: the other K-2
    are the *same set of counties* as in the previous plan and dissolve to the
    same geometry. ARCHITECTURE.md section 5 specifies ~14,000 plans per bench
    round, regenerated every round, and ``detect/outlier.py`` calls
    :func:`metric_series` over all of them.

    Measured on real ReCom output for Iowa (K=4, eps=2e-4, EPSG:5070), against
    the un-memoized implementation this replaced:

    =========================  =====  ==========  =========  =======  ========
    plans                          n  before      after      speedup  hit rate
    =========================  =====  ==========  =========  =======  ========
    12 chains, chain order      1666  230.6 ms/p  21.9 ms/p  10.5x    0.923
    the 308 distinct of those    308  231.9 ms/p  105.3 ms/p  2.20x   0.586
    4 chains, chain order        320  234.9 ms/p  26.2 ms/p   8.98x   0.907
    the 61 distinct of those      61  226.0 ms/p  127.5 ms/p  1.77x   0.512
    =========================  =====  ==========  =========  =======  ========

    Scaled to ARCHITECTURE.md's 14,000 plans, that is 54 minutes down to 5 on
    the raw chain, or down to 25 on distinct plans only. Both paths return
    bit-identical series (checked, and there is a test).

    **Read the 10.5x with the caveat attached.** Most of it is that at eps=2e-4
    the ReCom proposal frequently fails to find a balanced cut and the chain
    stays where it is, so consecutive samples are often *identical* plans, not
    merely adjacent ones (1666 samples, 308 distinct). That is a property of the
    sampler, not of this cache. The honest lower bound is the distinct-plans
    row: **2.2x**, from a 0.586 hit rate against the 0.50 that "2 of 4 districts
    change per step" predicts on its own — the excess is districts that recur
    non-consecutively. A bench that deduplicates before measuring should expect
    ~2.2x; one that measures the chain as sampled gets more.

    The key is ``frozenset`` of the district's unit ids, so it is invariant to
    district *renumbering* as well — two plans that differ only by a relabelling
    share every entry. Values are four floats, not geometries: caching the
    dissolved polygons instead would hold hundreds of megabytes of coordinates
    for the same hit rate.

    **A cache belongs to exactly one geometry table.** Reusing one across two
    different tables would silently return the first table's numbers, so the
    cache fingerprints the table on first use and raises on a mismatch.

    ``maxsize`` bounds the entries; eviction is least-recently-used, which suits
    a chain walking through plan space. ``hits``, ``misses`` and ``evictions``
    are readable, and are what a bench should log to show the reuse was real.
    """

    __slots__ = ("_entries", "_fingerprint", "maxsize", "hits", "misses", "evictions")

    def __init__(self, maxsize: int = 1 << 16) -> None:
        if maxsize < 1:
            raise ValueError(f"MeasureCache: maxsize must be >= 1, got {maxsize}")
        self._entries: dict[frozenset, dict[str, float]] = {}
        self._fingerprint: tuple | None = None
        self.maxsize = int(maxsize)
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def __len__(self) -> int:
        return len(self._entries)

    def _bind(self, fingerprint: tuple) -> None:
        if self._fingerprint is None:
            self._fingerprint = fingerprint
        elif self._fingerprint != fingerprint:
            raise ValueError(
                "MeasureCache is bound to a different geometry table (a "
                "different CRS, unit set or extent). Reusing it here would "
                "return the other table's numbers. Use one cache per table."
            )

    def _get(self, units: frozenset) -> dict[str, float] | None:
        entry = self._entries.get(units)
        if entry is None:
            self.misses += 1
            return None
        self.hits += 1
        self._entries[units] = self._entries.pop(units)  # LRU: move to newest
        return entry

    def _put(self, units: frozenset, values: dict[str, float]) -> None:
        if len(self._entries) >= self.maxsize:
            self._entries.pop(next(iter(self._entries)))
            self.evictions += 1
        self._entries[units] = values

    def stats(self) -> dict[str, int | float]:
        """Hits, misses, evictions, size, and the hit rate."""
        looked = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "size": len(self._entries),
            "hit_rate": (self.hits / looked) if looked else 0.0,
        }


def _fingerprint(geom, lookup: Mapping[str, object]) -> tuple:
    crs = getattr(geom, "crs", None)
    return (
        crs.to_wkt() if crs is not None else None,
        len(lookup),
        hash(frozenset(lookup)),
        tuple(round(float(v), 3) for v in geom.total_bounds),
    )


def measure_districts(
    plan: Plan, geom, cache: MeasureCache | None = None
) -> dict[str, dict[int, float]]:
    """All four shape measures, dissolving each district exactly once.

    ``{measure name: {district: value}}``. The single-measure functions above
    are the readable entry points; this one is what to call when you want more
    than one of them, since the union is the expensive step and calling four
    functions repeats it four times.

    Pass a :class:`MeasureCache` when measuring more than one plan over the same
    geometry table: districts an ensemble step left untouched are then not
    re-dissolved. Results are identical with and without it — there is a test.
    """
    lookup = _unit_lookup(geom)
    members = _members(plan, lookup)
    if cache is not None:
        cache._bind(_fingerprint(geom, lookup))

    per_district: dict[int, dict[str, float]] = {}
    for district in sorted(members):
        units = frozenset(members[district])
        values = cache._get(units) if cache is not None else None
        if values is None:
            shape = _dissolve(district, units, lookup)
            values = {
                name: fn(district, shape) for name, fn in _SHAPE_FUNCTIONS.items()
            }
            if cache is not None:
                cache._put(units, values)
        per_district[district] = values

    return {
        name: {d: per_district[d][name] for d in sorted(per_district)}
        for name in _SHAPE_FUNCTIONS
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
    section 3). It is also not intuitive to a non-technical reader. It is the
    one measure here that is completely projection-independent.

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

def all_metrics(
    plan: Plan,
    geom,
    adjacency: Mapping[str, Iterable[str]],
    cache: MeasureCache | None = None,
) -> dict[str, float]:
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
    per_measure = measure_districts(plan, geom, cache)
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
    plans: Sequence[Plan],
    geom,
    adjacency: Mapping[str, Iterable[str]],
    cache=AUTO_CACHE,
) -> dict[str, list[float]]:
    """One value per plan for each measure in :data:`MEASURES`.

    The shape measures are summarised by their **unweighted mean over
    districts**; ``cut_edges`` is already a whole-plan number. That summary
    choice is a real one — correlating the *minimum* district instead can give
    different answers, because the measures disagree most on the worst district
    — and it is stated here rather than buried in :func:`rank_correlation`.

    A :class:`MeasureCache` is created internally by default, so an ensemble
    never pays to dissolve the same district twice. Pass your own to read the
    hit rate, to share it with a later call over the same geometry table, or to
    bound its memory; pass ``cache=None`` to switch memoization off, which is
    only useful for benchmarking against the un-memoized path. **Order matters
    for the hit rate, not for the result**: plans in chain order share districts
    with their neighbours, so leave them in the order the sampler produced.
    """
    if len(plans) == 0:
        raise ValueError("metric_series: no plans given")
    if cache is AUTO_CACHE:
        cache = MeasureCache()
    series: dict[str, list[float]] = {name: [] for name in MEASURES}
    for plan in plans:
        summary = all_metrics(plan, geom, adjacency, cache)
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
    plans: Sequence[Plan],
    geom,
    adjacency: Mapping[str, Iterable[str]],
    cache=AUTO_CACHE,
) -> dict[tuple[str, str], float]:
    """Spearman correlation between every pair of measures across an ensemble.

    This answers the `EMPIRICAL` question CRITERIA.md section 3 asks: do these
    measures actually rank plans differently on this state's geography? If they
    correlate above ~0.9 the choice of measure does not matter here and we can
    say so; if they diverge, the choice is doing real work and must be surfaced
    to the user rather than resolved for them.

    It is also a correctness check on this module. `prompt.md`: "if all your
    compactness measures correlate above 0.95, either the state has simple
    geometry or you have implemented the same measure five times." Read the
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

    ``cache`` is forwarded to :func:`metric_series`, which builds one by
    default.
    """
    if len(plans) < 2:
        raise ValueError(
            f"rank_correlation: need at least 2 plans to correlate; got "
            f"{len(plans)}"
        )
    series = metric_series(plans, geom, adjacency, cache)
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
