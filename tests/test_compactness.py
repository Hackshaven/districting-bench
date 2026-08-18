"""Tests for src/evaluate/compactness.py.

Every shape measure here is checked against a figure whose answer is known
analytically — a circle, a square, an equilateral triangle, a regular hexagon,
an L, a rectangle, a square with a hole — not against the implementation's own
output on Iowa. Where a closed form exists it is written out and compared to
machine precision, so a sign error, a wrong denominator or a swapped area and
perimeter fails loudly rather than shifting a plausible number.

The Iowa checks at the end are cross-checks against numbers that were measured
independently and recorded in docs/FEASIBILITY.md before this module existed
(51 cut edges in the enacted plan; 222 rook edges in the graph).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import pytest
import shapely
from shapely.geometry import LineString, Polygon

from evaluate import compactness as C

PROCESSED = Path("data/processed")
HAVE_IOWA = (PROCESSED / "ia_units.gpkg").exists()
iowa = pytest.mark.skipif(not HAVE_IOWA, reason="data/processed not built")


# --------------------------------------------------------------------------- #
# helpers: one shape per unit, one unit per district unless stated
# --------------------------------------------------------------------------- #

#: CRS for the abstract figures below: Lambert azimuthal equal-area centred on
#: (0, 0) in metres. The figures sit at the origin, which is that projection's
#: point of *zero* distortion — both scale factors are exactly 1.0 and the
#: anisotropy is exactly 0.0 — so the analytic answers written out below are
#: the answers, and the numbers are not perturbed by the choice of tag.
#:
#: These frames used to be built with ``crs=None``, which meant roughly 40 of
#: the tests in this file never entered the CRS guard at all: the guard read
#: ``if crs is not None and crs.is_geographic``, so a table with no CRS went
#: straight through, and the one input most likely to be wrong (degrees, with
#: nobody having said so) was the one input never covered. Every synthetic
#: frame now carries a real projected CRS and takes the same guarded path
#: Iowa's EPSG:5070 data takes; ``crs=None`` is tested where it belongs, as a
#: refusal.
TEST_CRS = "+proj=laea +lat_0=0 +lon_0=0 +datum=WGS84 +units=m +no_defs"

#: Where to put a synthetic figure so it lands inside Iowa in EPSG:5070.
IOWA_5070 = (200_000.0, 2_100_000.0)


def frame(crs=TEST_CRS, **shapes):
    """GeoDataFrame of named shapes in a projected, undistorted CRS."""
    names = list(shapes)
    return gpd.GeoDataFrame(
        {"GEOID": names}, geometry=[shapes[n] for n in names], crs=crs
    )


def single(shape):
    """A one-unit, one-district plan carrying ``shape``, plus its geom table."""
    return {"A": 1}, frame(A=shape)


def cell(x, y, size=1.0):
    """The unit grid cell whose lower-left corner is (x, y)."""
    return shapely.box(x * size, y * size, (x + 1) * size, (y + 1) * size)


SQUARE = shapely.box(0, 0, 1, 1)
RECT_4x1 = shapely.box(0, 0, 4, 1)
# L: the 2x2 square with its top-right unit cell removed. Area 3, perimeter 8.
L_SHAPE = Polygon([(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)])
TRIANGLE = Polygon([(0, 0), (1, 0), (0.5, math.sqrt(3) / 2)])


def regular_ngon(n, radius=1.0):
    """Regular n-gon inscribed in a circle of the given radius."""
    return Polygon(
        [
            (radius * math.cos(2 * math.pi * k / n), radius * math.sin(2 * math.pi * k / n))
            for k in range(n)
        ]
    )


def ngon_polsby_popper(n):
    """Closed form: 4*pi*A/P^2 for a regular n-gon is (pi/n)*cot(pi/n)."""
    return (math.pi / n) / math.tan(math.pi / n)


def ngon_reock(n):
    """Closed form: A/(pi*R^2) for a regular n-gon is (n/(2*pi))*sin(2*pi/n)."""
    return (n / (2 * math.pi)) * math.sin(2 * math.pi / n)


# --------------------------------------------------------------------------- #
# Polsby-Popper
# --------------------------------------------------------------------------- #

def test_polsby_popper_circle_is_one():
    """A circle is the maximum of 4*pi*A/P^2, and the maximum is exactly 1."""
    n = 1024
    plan, geom = single(regular_ngon(n))
    value = C.polsby_popper(plan, geom)[1]
    # exact for the polygon actually measured ...
    assert value == pytest.approx(ngon_polsby_popper(n), rel=1e-12)
    # ... and that polygon is a circle to within 4e-6, so the measure is 1.
    assert value == pytest.approx(1.0, abs=1e-5)
    assert value <= 1.0


def test_polsby_popper_square_is_pi_over_four():
    plan, geom = single(SQUARE)
    assert C.polsby_popper(plan, geom)[1] == pytest.approx(math.pi / 4)
    assert C.polsby_popper(plan, geom)[1] == pytest.approx(0.7853981633974483)


def test_polsby_popper_equilateral_triangle():
    """4*pi*(sqrt(3)/4 s^2)/(3s)^2 = pi/(3*sqrt(3)) ~ 0.6046."""
    plan, geom = single(TRIANGLE)
    assert C.polsby_popper(plan, geom)[1] == pytest.approx(math.pi / (3 * math.sqrt(3)))


def test_polsby_popper_hexagon():
    """A value far from both 1 and pi/4, so the formula is pinned in between."""
    plan, geom = single(regular_ngon(6))
    assert C.polsby_popper(plan, geom)[1] == pytest.approx(ngon_polsby_popper(6))
    assert C.polsby_popper(plan, geom)[1] == pytest.approx(0.9068996821171089)


def test_polsby_popper_l_shape_scores_below_its_convex_hull():
    """The L is less compact than the hull that contains it: 3pi/16 < 0.800."""
    plan, geom = single(L_SHAPE)
    l_value = C.polsby_popper(plan, geom)[1]
    hull_plan, hull_geom = single(L_SHAPE.convex_hull)
    hull_value = C.polsby_popper(hull_plan, hull_geom)[1]
    assert l_value == pytest.approx(4 * math.pi * 3 / 8**2)  # A=3, P=8
    assert hull_value == pytest.approx(
        4 * math.pi * 3.5 / (6 + math.sqrt(2)) ** 2
    )
    assert l_value < hull_value
    assert l_value == pytest.approx(0.5890486225480862)


def test_polsby_popper_is_scale_invariant():
    plan, geom = single(SQUARE)
    big_plan, big_geom = single(shapely.affinity.scale(SQUARE, 1000, 1000))
    assert C.polsby_popper(plan, geom)[1] == pytest.approx(
        C.polsby_popper(big_plan, big_geom)[1]
    )


def test_polsby_popper_counts_the_perimeter_of_a_hole():
    """A district enclosing an enclave pays for the enclave's boundary.

    3x3 ring with the centre cell removed: A = 8, P = 12 + 4 = 16, so
    4*pi*8/256 = pi/8. Measuring only the outer ring would give 4*pi*8/144.
    """
    cells = {f"c{x}{y}": cell(x, y) for x in range(3) for y in range(3)}
    geom = frame(**cells)
    plan = {name: (2 if name == "c11" else 1) for name in cells}
    values = C.polsby_popper(plan, geom)
    assert values[1] == pytest.approx(math.pi / 8)
    assert values[2] == pytest.approx(math.pi / 4)  # the enclave is a unit square


# --------------------------------------------------------------------------- #
# Reock
# --------------------------------------------------------------------------- #

def test_reock_circle_is_one():
    n = 1024
    plan, geom = single(regular_ngon(n))
    value = C.reock(plan, geom)[1]
    assert value == pytest.approx(ngon_reock(n), rel=1e-9)
    assert value == pytest.approx(1.0, abs=1e-5)
    assert value <= 1.0


def test_reock_square_is_two_over_pi():
    """The bounding circle of a unit square has radius sqrt(2)/2, area pi/2."""
    plan, geom = single(SQUARE)
    assert C.reock(plan, geom)[1] == pytest.approx(2 / math.pi)
    assert C.reock(plan, geom)[1] == pytest.approx(0.6366197723675814)


def test_reock_equilateral_triangle():
    """Circumradius s/sqrt(3): (sqrt(3)/4 s^2)/(pi s^2/3) = 3*sqrt(3)/(4pi)."""
    plan, geom = single(TRIANGLE)
    assert C.reock(plan, geom)[1] == pytest.approx(3 * math.sqrt(3) / (4 * math.pi))


def test_reock_l_shape():
    """MBC of the L is centred at (1,1) with radius sqrt(2): 3/(2pi)."""
    plan, geom = single(L_SHAPE)
    assert C.reock(plan, geom)[1] == pytest.approx(3 / (2 * math.pi))


def test_reock_ignores_boundary_detail_that_polsby_popper_punishes():
    """CRITERIA.md section 3's stated failure mode, made to happen.

    A square with a fine sawtooth cut into one edge keeps almost all of its
    area and its bounding circle, so Reock barely moves, while the perimeter
    grows and Polsby-Popper collapses. If both measures moved together, one of
    them would be misimplemented.
    """
    teeth = 40
    step = 1.0 / teeth
    edge = [(0.0, 1.0)]
    for i in range(teeth):
        x = i * step
        edge.append((x + step / 2, 0.85))
        edge.append((x + step, 1.0))
    ragged = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)] + list(reversed(edge)))

    plain_plan, plain_geom = single(SQUARE)
    rag_plan, rag_geom = single(ragged)

    reock_drop = C.reock(plain_plan, plain_geom)[1] - C.reock(rag_plan, rag_geom)[1]
    pp_drop = (
        C.polsby_popper(plain_plan, plain_geom)[1]
        - C.polsby_popper(rag_plan, rag_geom)[1]
    )
    assert reock_drop < 0.05
    assert pp_drop > 0.4
    assert pp_drop > 10 * reock_drop


# --------------------------------------------------------------------------- #
# Schwartzberg
# --------------------------------------------------------------------------- #

def test_schwartzberg_circle_is_one():
    n = 1024
    plan, geom = single(regular_ngon(n))
    assert C.schwartzberg(plan, geom)[1] == pytest.approx(1.0, abs=1e-5)


def test_schwartzberg_square_is_two_over_root_pi():
    """P=4, equal-area circle circumference 2*sqrt(pi): 4/(2 sqrt(pi))."""
    plan, geom = single(SQUARE)
    assert C.schwartzberg(plan, geom)[1] == pytest.approx(2 / math.sqrt(math.pi))
    assert C.schwartzberg(plan, geom)[1] == pytest.approx(1.1283791670955126)


def test_schwartzberg_is_above_one_and_worse_when_larger():
    """Direction check: CRITERIA.md's Schwartzberg rises as compactness falls."""
    square_plan, square_geom = single(SQUARE)
    l_plan, l_geom = single(L_SHAPE)
    square = C.schwartzberg(square_plan, square_geom)[1]
    ell = C.schwartzberg(l_plan, l_geom)[1]
    assert square >= 1.0 and ell >= 1.0
    assert ell > square
    assert C.polsby_popper(l_plan, l_geom)[1] < C.polsby_popper(
        square_plan, square_geom
    )[1]
    assert C.DIRECTION["schwartzberg"] == -1


@pytest.mark.parametrize(
    "shape", [SQUARE, RECT_4x1, L_SHAPE, TRIANGLE, regular_ngon(7)]
)
def test_schwartzberg_is_exactly_one_over_root_polsby_popper(shape):
    """The identity that makes Schwartzberg a rescaling, not a fifth opinion."""
    plan, geom = single(shape)
    pp = C.polsby_popper(plan, geom)[1]
    assert C.schwartzberg(plan, geom)[1] == pytest.approx(1 / math.sqrt(pp), rel=1e-12)


# --------------------------------------------------------------------------- #
# convex hull
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("shape", [SQUARE, RECT_4x1, TRIANGLE, regular_ngon(5)])
def test_convex_hull_is_one_for_convex_shapes(shape):
    plan, geom = single(shape)
    assert C.convex_hull(plan, geom)[1] == pytest.approx(1.0)


def test_convex_hull_l_shape_is_six_sevenths():
    """L area 3; its hull is the pentagon of area 3.5. 3/3.5 = 6/7."""
    plan, geom = single(L_SHAPE)
    assert C.convex_hull(plan, geom)[1] == pytest.approx(6 / 7)
    assert L_SHAPE.convex_hull.area == pytest.approx(3.5)


def test_convex_hull_says_nothing_about_elongation():
    """Its blind spot, asserted: a 4x1 sliver scores 1.0, same as a square."""
    thin_plan, thin_geom = single(RECT_4x1)
    sq_plan, sq_geom = single(SQUARE)
    assert C.convex_hull(thin_plan, thin_geom)[1] == pytest.approx(1.0)
    assert C.convex_hull(sq_plan, sq_geom)[1] == pytest.approx(1.0)
    # while the measures that can see elongation both do:
    assert C.polsby_popper(thin_plan, thin_geom)[1] == pytest.approx(16 * math.pi / 100)
    assert C.reock(thin_plan, thin_geom)[1] == pytest.approx(16 / (17 * math.pi))


# --------------------------------------------------------------------------- #
# dissolving
# --------------------------------------------------------------------------- #

def test_districts_are_measured_after_dissolving_their_units():
    """Two unit squares in one district are a 2x1 rectangle, not two squares.

    Averaging the units instead would give pi/4 = 0.785; the dissolved answer
    is 4*pi*2/36 = 2pi/9 = 0.698.
    """
    geom = frame(a=cell(0, 0), b=cell(1, 0))
    plan = {"a": 1, "b": 1}
    assert C.polsby_popper(plan, geom)[1] == pytest.approx(2 * math.pi / 9)
    assert C.polsby_popper(plan, geom)[1] != pytest.approx(math.pi / 4)


def test_district_ids_are_preserved_and_sorted():
    geom = frame(a=cell(0, 0), b=cell(1, 0), c=cell(2, 0))
    plan = {"a": 3, "b": 1, "c": 2}
    assert list(C.polsby_popper(plan, geom)) == [1, 2, 3]
    assert list(C.reock(plan, geom)) == [1, 2, 3]


# --------------------------------------------------------------------------- #
# cut edges
# --------------------------------------------------------------------------- #

PATH4 = {"a": ["b"], "b": ["a", "c"], "c": ["b", "d"], "d": ["c"]}


def grid_adjacency(w, h):
    """Rook adjacency of a w x h grid, keys ``x,y``."""
    adj = {f"{x},{y}": [] for x in range(w) for y in range(h)}
    for x in range(w):
        for y in range(h):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    adj[f"{x},{y}"].append(f"{nx},{ny}")
    return adj


def test_cut_edges_on_a_path():
    assert C.cut_edges({"a": 1, "b": 1, "c": 2, "d": 2}, PATH4) == 1
    assert C.cut_edges({"a": 1, "b": 2, "c": 1, "d": 2}, PATH4) == 3
    assert C.cut_edges({"a": 1, "b": 1, "c": 1, "d": 1}, PATH4) == 0


def test_cut_edges_counts_each_undirected_edge_once():
    """The graph lists every edge twice; the count must not."""
    plan = {"a": 1, "b": 2, "c": 2, "d": 2}
    assert C.cut_edges(plan, PATH4) == 1
    one_way = {"a": ["b"], "b": [], "c": [], "d": []}
    assert C.cut_edges(plan, one_way) == 1


def test_cut_edges_on_a_grid_split_into_rows():
    """3x3 grid cut into three rows: 2 cuts x 3 columns = 6 edges."""
    adj = grid_adjacency(3, 3)
    plan = {f"{x},{y}": y + 1 for x in range(3) for y in range(3)}
    assert C.cut_edges(plan, adj) == 6
    # ... and into three columns: also 6, by symmetry
    plan_cols = {f"{x},{y}": x + 1 for x in range(3) for y in range(3)}
    assert C.cut_edges(plan_cols, adj) == 6


def test_cut_edges_every_unit_its_own_district_is_the_edge_count():
    adj = grid_adjacency(4, 4)
    total = 2 * 4 * 3  # 24 rook edges in a 4x4 grid
    plan = {node: i + 1 for i, node in enumerate(sorted(adj))}
    assert C.cut_edges(plan, adj) == total


def test_cut_edges_rejects_a_plan_that_does_not_cover_the_graph():
    with pytest.raises(ValueError, match="unassigned"):
        C.cut_edges({"a": 1, "b": 1, "c": 2}, PATH4)
    with pytest.raises(ValueError, match="not nodes of the adjacency graph"):
        C.cut_edges({"a": 1, "b": 1, "c": 2, "d": 2, "z": 3}, PATH4)


# --------------------------------------------------------------------------- #
# regimes CRITERIA.md flags: undefined, degenerate, or wrong-projection
# --------------------------------------------------------------------------- #

def lonlat_box_in(crs, minlon=-96.6, minlat=40.4, maxlon=-90.1, maxlat=43.5):
    """A frame covering Iowa's lon/lat extent, expressed in ``crs``.

    Used to probe the projection guard without needing data/processed: the
    guard's verdict depends on the projection *and* on the extent the data
    occupies, so the extent has to be a real one.
    """
    box = shapely.box(minlon, minlat, maxlon, maxlat)
    half = shapely.box(minlon, minlat, (minlon + maxlon) / 2, maxlat)
    rest = shapely.box((minlon + maxlon) / 2, minlat, maxlon, maxlat)
    return gpd.GeoDataFrame(
        {"GEOID": ["a", "b"]}, geometry=[half, rest], crs="EPSG:4326"
    ).to_crs(crs)


def test_geographic_crs_is_refused():
    geom = gpd.GeoDataFrame({"GEOID": ["A"]}, geometry=[SQUARE], crs="EPSG:4326")
    with pytest.raises(ValueError, match="geographic"):
        C.polsby_popper({"A": 1}, geom)


def test_a_missing_crs_is_refused():
    """crs=None is not "planar units"; it is "nobody said", and it used to pass.

    The old guard read ``if crs is not None and crs.is_geographic``, so the
    single most dangerous input — degrees, unlabelled — was the one input that
    went straight through and returned a plausible wrong number.
    """
    geom = gpd.GeoDataFrame({"GEOID": ["A"]}, geometry=[SQUARE], crs=None)
    with pytest.raises(ValueError, match="geom.crs is None"):
        C.polsby_popper({"A": 1}, geom)
    with pytest.raises(ValueError, match="geom.crs is None"):
        C.reock({"A": 1}, geom)
    with pytest.raises(ValueError, match="geom.crs is None"):
        C.all_metrics({"A": 1}, geom, {"A": []})


def test_a_crs_given_as_a_plain_string_is_normalised_not_crashed_on():
    """geopandas hands back a pyproj CRS; a hand-built table may not."""

    class Loose:
        columns = ("GEOID",)
        geometry = [SQUARE]
        crs = "EPSG:4326"

    with pytest.raises(ValueError, match="geographic"):
        C.polsby_popper({"A": 1}, Loose())


def test_an_object_with_no_crs_attribute_at_all_is_refused():
    class NotAGeoDataFrame:
        columns = ("GEOID",)
        index = ["A"]
        geometry = [SQUARE]

    with pytest.raises(ValueError, match="geom.crs is None"):
        C.polsby_popper({"A": 1}, NotAGeoDataFrame())


def test_an_equal_area_crs_can_still_be_refused():
    """EPSG:6933 is equal-area and is rejected anyway — the whole decision.

    A cylindrical equal-area projection buys exact area by shearing: at Iowa's
    latitude it stretches north-south and squashes east-west by ~16%, which
    lands directly on perimeter and on the minimum bounding circle (measured:
    8.5% on Polsby-Popper, 22.6% on Reock). "Equal-area" is not the property
    these measures need, so it is not the property the guard tests.
    """
    geom = lonlat_box_in("EPSG:6933")
    assert geom.crs.coordinate_operation.method_name == "Lambert Cylindrical Equal Area"
    with pytest.raises(ValueError, match="anisotropic"):
        C.polsby_popper({"a": 1, "b": 2}, geom)


def test_a_non_equal_area_crs_can_be_accepted():
    """EPSG:26975 is conformal, not equal-area, and is accepted — the converse.

    On Iowa it agrees to within 0.004% on Reock with a Lambert azimuthal
    equal-area projection centred on the state, which is the least-distorted
    projection available. Rejecting it for not being equal-area would reject a
    better answer than the one the project standardises on.
    """
    geom = lonlat_box_in("EPSG:26975")
    assert "Equal Area" not in geom.crs.coordinate_operation.method_name
    values = C.polsby_popper({"a": 1, "b": 2}, geom)
    assert all(0.0 < v <= 1.0 for v in values.values())


def test_web_mercator_is_refused_for_non_uniform_scale():
    """EPSG:3857 is near-conformal but its scale varies 5% across Iowa.

    A *constant* scale factor cancels out of every measure here, which is why
    scale is checked as a spread rather than as an offset from 1.0.
    """
    geom = lonlat_box_in("EPSG:3857")
    with pytest.raises(ValueError, match="scale is uniform"):
        C.polsby_popper({"a": 1, "b": 2}, geom)


def test_the_guard_reads_the_extent_not_the_epsg_code():
    """EPSG:5070 passes over Iowa and fails over its own origin.

    Albers CONUS is anisotropic by 1.78% over Iowa and by 3.71% at 23N/96W,
    where its false origin sits. A guard keyed on the EPSG code could not tell
    those apart; this one measures the projection where the data actually is.
    """
    ok = frame(crs="EPSG:5070", a=cell(0, 0), b=cell(1, 0))
    ok["geometry"] = ok.geometry.translate(*IOWA_5070)
    assert C.polsby_popper({"a": 1, "b": 1}, ok)[1] == pytest.approx(
        2 * math.pi / 9, rel=1e-9
    )

    at_origin = frame(crs="EPSG:5070", a=cell(0, 0), b=cell(1, 0))
    with pytest.raises(ValueError, match="anisotropic"):
        C.polsby_popper({"a": 1, "b": 1}, at_origin)


def test_crs_distortion_is_zero_for_an_undistorted_projection():
    report = C.crs_distortion(TEST_CRS, (-1.0, -1.0, 1.0, 1.0))
    assert report["anisotropy"] == pytest.approx(0.0, abs=1e-9)
    assert report["scale_spread"] == pytest.approx(0.0, abs=1e-9)


def test_crs_distortion_ranks_the_projections_the_docstring_ranks():
    """The table in the module docstring, as an assertion.

    Ordering, not exact values: the point is that EPSG:5070 is the most
    distorted CRS the guard accepts, and that the equal-area EPSG:6933 is an
    order of magnitude worse than the non-equal-area EPSG:26975.
    """
    iowa_bounds = {
        code: tuple(lonlat_box_in(code).total_bounds)
        for code in ("EPSG:5070", "EPSG:26975", "EPSG:6933", "EPSG:3857")
    }
    aniso = {
        code: C.crs_distortion(code, bounds)["anisotropy"]
        for code, bounds in iowa_bounds.items()
    }
    assert aniso["EPSG:26975"] < aniso["EPSG:5070"] < C.MAX_ANISOTROPY
    assert aniso["EPSG:6933"] > 8 * C.MAX_ANISOTROPY
    spread = C.crs_distortion("EPSG:3857", iowa_bounds["EPSG:3857"])["scale_spread"]
    assert spread > C.MAX_SCALE_SPREAD


def test_zero_area_district_is_refused_not_returned_as_zero():
    geom = frame(A=LineString([(0, 0), (1, 1)]))
    with pytest.raises(ValueError, match="zero area"):
        C.polsby_popper({"A": 1}, geom)
    with pytest.raises(ValueError, match="zero area"):
        C.reock({"A": 1}, geom)
    with pytest.raises(ValueError, match="zero area"):
        C.convex_hull({"A": 1}, geom)


def test_missing_and_extra_geometry_are_refused():
    geom = frame(a=cell(0, 0), b=cell(1, 0))
    with pytest.raises(ValueError, match="no geometry"):
        C.polsby_popper({"a": 1, "b": 1, "c": 1}, geom)
    with pytest.raises(ValueError, match="does not assign"):
        C.polsby_popper({"a": 1}, geom)


def test_duplicate_geoids_are_refused():
    geom = gpd.GeoDataFrame(
        {"GEOID": ["a", "a"]}, geometry=[cell(0, 0), cell(1, 0)], crs=TEST_CRS
    )
    with pytest.raises(ValueError, match="repeated GEOID"):
        C.polsby_popper({"a": 1}, geom)


def test_geoid_index_is_accepted_as_well_as_a_geoid_column():
    geom = frame(a=cell(0, 0), b=cell(1, 0))
    indexed = geom.set_index("GEOID")
    plan = {"a": 1, "b": 1}
    assert C.polsby_popper(plan, indexed)[1] == pytest.approx(
        C.polsby_popper(plan, geom)[1]
    )


# --------------------------------------------------------------------------- #
# per-plan summaries
# --------------------------------------------------------------------------- #

def test_all_metrics_reports_every_measure_and_no_composite():
    geom = frame(a=cell(0, 0), b=cell(1, 0), c=cell(0, 1), d=cell(1, 1))
    adj = grid_adjacency(2, 2)
    named = {"0,0": "a", "1,0": "b", "0,1": "c", "1,1": "d"}
    plan = {"a": 1, "b": 1, "c": 2, "d": 2}
    adjacency = {named[k]: [named[v] for v in vs] for k, vs in adj.items()}

    out = C.all_metrics(plan, geom, adjacency)
    for name in C.SHAPE_MEASURES:
        for stat in ("mean", "min", "max"):
            assert f"{name}_{stat}" in out
    assert out["cut_edges"] == 2
    assert out["n_districts"] == 2
    # both districts are 2x1 rectangles, so mean == min == max
    assert out["polsby_popper_mean"] == pytest.approx(2 * math.pi / 9)
    assert out["polsby_popper_min"] == pytest.approx(out["polsby_popper_max"])
    assert out["convex_hull_mean"] == pytest.approx(1.0)
    # no single-number compactness score, ever (prompt.md)
    assert not any(
        key in out for key in ("compactness", "score", "fairness_score", "index")
    )


def test_all_metrics_min_and_max_bracket_the_districts():
    geom = frame(a=cell(0, 0), b=cell(1, 0), c=cell(2, 0))
    adjacency = {"a": ["b"], "b": ["a", "c"], "c": ["b"]}
    plan = {"a": 1, "b": 1, "c": 2}  # a 2x1 rectangle and a unit square
    out = C.all_metrics(plan, geom, adjacency)
    assert out["polsby_popper_min"] == pytest.approx(2 * math.pi / 9)
    assert out["polsby_popper_max"] == pytest.approx(math.pi / 4)
    assert out["polsby_popper_mean"] == pytest.approx(
        (2 * math.pi / 9 + math.pi / 4) / 2
    )
    # Schwartzberg's worst district is its max, not its min
    assert out["schwartzberg_max"] == pytest.approx(1 / math.sqrt(2 * math.pi / 9))
    assert out["schwartzberg_min"] == pytest.approx(1 / math.sqrt(math.pi / 4))


# --------------------------------------------------------------------------- #
# Spearman
# --------------------------------------------------------------------------- #

def test_spearman_monotone_relationships():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert C.spearman(x, [10.0, 20.0, 30.0, 40.0, 50.0]) == pytest.approx(1.0)
    assert C.spearman(x, [1.0, 4.0, 9.0, 16.0, 25.0]) == pytest.approx(1.0)
    assert C.spearman(x, [5.0, 4.0, 3.0, 2.0, 1.0]) == pytest.approx(-1.0)


def test_spearman_known_value_by_hand():
    """Two adjacent swaps: 1 - 6*4/(5*24) = 0.8."""
    assert C.spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]) == pytest.approx(0.8)


def test_spearman_average_ranks_for_ties():
    """x ranks 1, 2.5, 2.5, 4 against 1, 2, 3, 4 gives 4.5/sqrt(4.5*5)."""
    assert C.spearman([1, 2, 2, 3], [1, 2, 3, 4]) == pytest.approx(
        4.5 / math.sqrt(4.5 * 5)
    )
    assert C.spearman([1, 2, 2, 3], [1, 2, 3, 4]) == pytest.approx(0.9486832980505138)


def test_spearman_is_nan_when_a_series_is_constant():
    value = C.spearman([1.0, 1.0, 1.0, 1.0], [1.0, 2.0, 3.0, 4.0])
    assert math.isnan(value)


def test_spearman_rejects_degenerate_input():
    with pytest.raises(ValueError):
        C.spearman([1.0], [1.0])
    with pytest.raises(ValueError):
        C.spearman([1.0, 2.0], [1.0])


# --------------------------------------------------------------------------- #
# rank correlation between measures
# --------------------------------------------------------------------------- #

def four_by_four():
    """A 4x4 unit grid, its rook graph, and three plans with hand-computed means.

    ================  =========================  ==========  =========  =====
    plan              districts                  mean PP     mean hull  cuts
    ================  =========================  ==========  =========  =====
    halves            two 4x2 rectangles         2pi/9       1.0        4
    stripe            1x4 and 3x4                (see below) 1.0        4
    ell               L (row 0 + column 0), 3x3  (see below) 0.804      6
    ================  =========================  ==========  =========  =====

    mean PP: halves 0.6981 > stripe 0.6361 > ell 0.5645, so the PP ordering is
    strict while the hull and cut-edge orderings both tie halves with stripe.
    That gives an exact expected Spearman of sqrt(3)/2 between PP and each of
    them, and exactly 1.0 between those two.
    """
    cells = {f"{x},{y}": cell(x, y) for x in range(4) for y in range(4)}
    geom = frame(**cells)
    adjacency = grid_adjacency(4, 4)
    halves = {f"{x},{y}": (1 if y < 2 else 2) for x in range(4) for y in range(4)}
    stripe = {f"{x},{y}": (1 if x < 1 else 2) for x in range(4) for y in range(4)}
    ell = {
        f"{x},{y}": (1 if (y == 0 or x == 0) else 2)
        for x in range(4)
        for y in range(4)
    }
    return geom, adjacency, [halves, stripe, ell]


def test_hand_computed_means_for_the_four_by_four_plans():
    """Pin the inputs to the correlation test before correlating them."""
    geom, adjacency, (halves, stripe, ell) = four_by_four()

    a = C.all_metrics(halves, geom, adjacency)
    assert a["polsby_popper_mean"] == pytest.approx(2 * math.pi / 9)  # 4x2 twice
    assert a["convex_hull_mean"] == pytest.approx(1.0)
    assert a["cut_edges"] == 4

    b = C.all_metrics(stripe, geom, adjacency)
    pp_1x4 = 4 * math.pi * 4 / 10**2
    pp_3x4 = 4 * math.pi * 12 / 14**2
    assert b["polsby_popper_mean"] == pytest.approx((pp_1x4 + pp_3x4) / 2)
    assert b["convex_hull_mean"] == pytest.approx(1.0)
    assert b["cut_edges"] == 4

    c = C.all_metrics(ell, geom, adjacency)
    pp_ell = 4 * math.pi * 7 / 16**2  # A=7, P=16
    pp_3x3 = 4 * math.pi * 9 / 12**2
    assert c["polsby_popper_mean"] == pytest.approx((pp_ell + pp_3x3) / 2)
    assert c["convex_hull_mean"] == pytest.approx((7 / 11.5 + 1.0) / 2)
    assert c["cut_edges"] == 6

    assert (
        a["polsby_popper_mean"] > b["polsby_popper_mean"] > c["polsby_popper_mean"]
    )


def test_rank_correlation_exact_values_on_the_four_by_four_ensemble():
    geom, adjacency, plans = four_by_four()
    rho = C.rank_correlation(plans, geom, adjacency)

    # convex hull and cut edges tie the same two plans and separate the third
    assert rho[("convex_hull", "cut_edges")] == pytest.approx(1.0)
    # against Polsby-Popper's strict ordering, one tie costs exactly sqrt(3)/2
    assert rho[("polsby_popper", "convex_hull")] == pytest.approx(math.sqrt(3) / 2)
    assert rho[("polsby_popper", "cut_edges")] == pytest.approx(math.sqrt(3) / 2)
    # every unordered pair once, no self-pairs
    assert len(rho) == len(C.MEASURES) * (len(C.MEASURES) - 1) // 2
    assert all(a != b for a, b in rho)


def test_rank_correlation_orients_measures_so_agreement_is_positive():
    """Schwartzberg and cut edges point the other way; the sign must not.

    Both of those measures fall as compactness rises, so without the
    orientation in DIRECTION their perfect agreement with the others would be
    reported as -1. Each assertion below would flip sign under that bug.
    """
    geom, adjacency, plans = four_by_four()
    rho = C.rank_correlation(plans, geom, adjacency)
    assert rho[("polsby_popper", "schwartzberg")] == pytest.approx(1.0)
    assert rho[("convex_hull", "cut_edges")] == pytest.approx(1.0)
    assert rho[("schwartzberg", "cut_edges")] == pytest.approx(math.sqrt(3) / 2)
    assert min(rho.values()) >= 0.0


def test_rank_correlation_records_a_genuine_reock_disagreement():
    """Reock ranks these three plans differently from the other measures.

    Reock: halves 0.5093 > ell 0.4576 > stripe 0.4554 — the 1x4 stripe plan is
    penalised for elongation that its convex hull ratio (1.0) cannot see, and
    it beats the L on Polsby-Popper. Ranks [3, 1, 2] against Polsby-Popper's
    [3, 2, 1] give exactly 0.5; against the hull's [2.5, 2.5, 1] exactly 0.0.
    """
    geom, adjacency, plans = four_by_four()
    values = C.metric_series(plans, geom, adjacency)["reock"]
    assert values[0] > values[2] > values[1]
    rho = C.rank_correlation(plans, geom, adjacency)
    assert rho[("polsby_popper", "reock")] == pytest.approx(0.5)
    assert rho[("reock", "convex_hull")] == pytest.approx(0.0, abs=1e-12)


def test_rank_correlation_is_nan_when_a_measure_never_moves():
    """Two plans that differ only in shape, not in cut edges."""
    geom, adjacency, plans = four_by_four()
    halves, stripe, _ = plans
    rho = C.rank_correlation([halves, stripe], geom, adjacency)
    assert math.isnan(rho[("polsby_popper", "cut_edges")])
    assert math.isnan(rho[("convex_hull", "cut_edges")])
    assert rho[("polsby_popper", "schwartzberg")] == pytest.approx(1.0)


def test_rank_correlation_needs_an_ensemble():
    geom, adjacency, plans = four_by_four()
    with pytest.raises(ValueError, match="at least 2 plans"):
        C.rank_correlation(plans[:1], geom, adjacency)


def test_disagreements_flags_weak_pairs_and_nans():
    pairs = {
        ("a", "b"): 0.99,
        ("a", "c"): 0.42,
        ("b", "c"): float("nan"),
        ("a", "d"): -0.30,
    }
    flagged = C.disagreements(pairs, threshold=0.9)
    assert [pair for pair, _ in flagged] == [("b", "c"), ("a", "d"), ("a", "c")]
    assert C.disagreements({("a", "b"): 0.97}) == []


# --------------------------------------------------------------------------- #
# MeasureCache: the ensemble path must be faster and identical
# --------------------------------------------------------------------------- #

def uncached_series(plans, geom, adjacency):
    """metric_series with the memoization genuinely switched off.

    ``cache=None`` means "no cache" everywhere in the module; the ensemble entry
    points default to a sentinel that builds one. That distinction exists
    because the first version of this test passed ``cache=None`` as its
    reference and silently benchmarked the fast path against itself.
    """
    return C.metric_series(plans, geom, adjacency, cache=None)


def six_cell_pair():
    """A 3x2 grid in three districts, and the plan one unit-move away from it.

    The ReCom pattern in miniature: the move changes districts 1 and 2 and
    leaves district 3 exactly as it was, so district 3 is the reusable one.
    """
    geom = frame(
        a=cell(0, 0), b=cell(1, 0), c=cell(2, 0),
        d=cell(0, 1), e=cell(1, 1), f=cell(2, 1),
    )
    adjacency = {
        "a": ["b", "d"], "b": ["a", "c", "e"], "c": ["b", "f"],
        "d": ["a", "e"], "e": ["b", "d", "f"], "f": ["c", "e"],
    }
    before = {"a": 1, "d": 1, "b": 2, "e": 2, "c": 3, "f": 3}
    after = {"a": 1, "b": 2, "d": 2, "e": 2, "c": 3, "f": 3}  # d moves 1 -> 2
    return geom, adjacency, [before, after]


def test_cache_changes_nothing_about_the_answer():
    """The only acceptable speedup is one that returns the same numbers."""
    geom, adjacency, plans = four_by_four()
    plain = uncached_series(plans, geom, adjacency)
    cached = C.metric_series(plans, geom, adjacency, cache=C.MeasureCache())
    assert plain.keys() == cached.keys()
    for name in plain:
        assert plain[name] == cached[name]  # exact, not approx


def test_metric_series_memoizes_by_default():
    """The default has to be the fast path, or the bench will not use it."""
    geom, adjacency, plans = four_by_four()
    default = C.metric_series(plans, geom, adjacency)
    assert default == uncached_series(plans, geom, adjacency)


def test_no_cache_really_means_no_cache(monkeypatch):
    """cache=None must not quietly build one, counted at the dissolve.

    A benchmark that passes cache=None to get the slow path has to actually get
    it; the first version of this module's benchmark did not, and reported a
    1.02x speedup because it was timing the memoized path against itself.
    """
    geom, adjacency, plans = six_cell_pair()
    calls = []
    real = C._dissolve
    monkeypatch.setattr(
        C, "_dissolve", lambda d, u, l: (calls.append(d), real(d, u, l))[1]
    )

    C.metric_series(plans, geom, adjacency, cache=None)
    assert len(calls) == 6            # three districts, both plans, no reuse

    calls.clear()
    C.metric_series(plans, geom, adjacency)
    assert len(calls) == 5            # the untouched district is dissolved once


def test_cache_reuses_the_districts_a_step_left_alone():
    """Two plans sharing one district: 4 lookups, 3 dissolves, 1 hit.

    This is the ReCom pattern in miniature — a step changes 2 of K districts
    and leaves the rest alone — and it is the whole reason the cache exists.
    """
    geom, adjacency, plans = six_cell_pair()
    cache = C.MeasureCache()
    C.metric_series(plans, geom, adjacency, cache)
    stats = cache.stats()
    assert stats["hits"] + stats["misses"] == 6   # three districts, twice
    assert stats["misses"] == 5                   # district 3 is the only repeat
    assert stats["hits"] == 1
    assert stats["hit_rate"] == pytest.approx(1 / 6)


def test_cache_is_invariant_to_district_relabelling():
    """Keying on the frozenset of units, not the district number, is the point.

    The same partition with the labels swapped dissolves to the same two
    geometries, so the second plan should be all hits.
    """
    geom = frame(a=cell(0, 0), b=cell(1, 0))
    adjacency = {"a": ["b"], "b": ["a"]}
    cache = C.MeasureCache()
    C.metric_series(
        [{"a": 1, "b": 2}, {"a": 2, "b": 1}], geom, adjacency, cache
    )
    assert cache.stats() == {
        "hits": 2, "misses": 2, "evictions": 0, "size": 2, "hit_rate": 0.5
    }


def test_cache_refuses_a_second_geometry_table():
    """Silently returning the first table's numbers would be the worst outcome."""
    small = frame(a=cell(0, 0), b=cell(1, 0))
    big = frame(a=cell(0, 0, size=10.0), b=cell(1, 0, size=10.0))
    adjacency = {"a": ["b"], "b": ["a"]}
    cache = C.MeasureCache()
    C.all_metrics({"a": 1, "b": 2}, small, adjacency, cache)
    with pytest.raises(ValueError, match="different geometry table"):
        C.all_metrics({"a": 1, "b": 2}, big, adjacency, cache)


def test_cache_evicts_least_recently_used_and_stays_correct():
    geom, adjacency, plans = four_by_four()
    tiny = C.MeasureCache(maxsize=1)
    plain = uncached_series(plans, geom, adjacency)
    cached = C.metric_series(plans, geom, adjacency, cache=tiny)
    for name in plain:
        assert plain[name] == cached[name]
    assert len(tiny) == 1
    assert tiny.stats()["evictions"] > 0


def test_cache_rejects_a_useless_maxsize():
    with pytest.raises(ValueError, match="maxsize"):
        C.MeasureCache(maxsize=0)


def test_measure_districts_matches_the_single_measure_functions():
    """The batched path and the four readable paths must not drift apart."""
    geom, _, plans = four_by_four()
    plan = plans[2]
    batched = C.measure_districts(plan, geom, C.MeasureCache())
    assert batched["polsby_popper"] == C.polsby_popper(plan, geom)
    assert batched["reock"] == C.reock(plan, geom)
    assert batched["schwartzberg"] == C.schwartzberg(plan, geom)
    assert batched["convex_hull"] == C.convex_hull(plan, geom)


# --------------------------------------------------------------------------- #
# Iowa: cross-checks against numbers measured before this module existed
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def iowa_geom():
    return gpd.read_file(PROCESSED / "ia_units.gpkg")


@pytest.fixture(scope="module")
def iowa_adjacency():
    return json.loads((PROCESSED / "ia_adjacency.json").read_text())


@pytest.fixture(scope="module")
def enacted():
    import csv

    with (PROCESSED / "ia_enacted_cd118.csv").open(newline="") as fh:
        return {row["GEOID"]: int(row["district"]) for row in csv.DictReader(fh)}


@iowa
def test_enacted_plan_has_51_cut_edges(enacted, iowa_adjacency):
    """FEASIBILITY.md section 5.3 reports 51 for the enacted plan, measured
    independently of this module."""
    assert C.cut_edges(enacted, iowa_adjacency) == 51


@iowa
def test_iowa_rook_graph_has_222_edges(enacted, iowa_adjacency):
    """FEASIBILITY.md section 3. Every county in its own district cuts them all."""
    singletons = {geoid: i + 1 for i, geoid in enumerate(sorted(iowa_adjacency))}
    assert C.cut_edges(singletons, iowa_adjacency) == 222


@iowa
def test_enacted_plan_measures_are_in_range_and_disagree(enacted, iowa_geom):
    pp = C.polsby_popper(enacted, iowa_geom)
    rk = C.reock(enacted, iowa_geom)
    ch = C.convex_hull(enacted, iowa_geom)
    sb = C.schwartzberg(enacted, iowa_geom)
    assert sorted(pp) == [1, 2, 3, 4]
    for values in (pp, rk, ch):
        assert all(0.0 < v <= 1.0 for v in values.values())
    assert all(v >= 1.0 for v in sb.values())
    for d in pp:
        assert sb[d] == pytest.approx(1 / math.sqrt(pp[d]), rel=1e-12)
    # the measures rank the enacted districts differently: CD4 is the worst
    # district on Polsby-Popper but not on Reock.
    assert min(pp, key=pp.get) == 4
    assert min(rk, key=rk.get) != 4


@iowa
def test_iowa_district_areas_sum_to_the_state_area(enacted, iowa_geom):
    """A dissolve that dropped or double-counted a county would fail here."""
    parts = C.district_geometries(enacted, iowa_geom)
    total = sum(shape.area for shape in parts.values())
    assert total == pytest.approx(iowa_geom.geometry.area.sum(), rel=1e-9)


@iowa
def test_projection_sensitivity_of_the_measures_matches_the_docstring(
    enacted, iowa_geom
):
    """Pin the numbers the module docstring's projection argument rests on.

    The docstring used to attribute "~0.1%" to Polsby-Popper by citing D-005,
    which measured *area* error and nothing else. Re-measured here on the
    measures themselves: Polsby-Popper moves ~0.42%, Reock ~1.15%, convex hull
    ~0.02%. If this test fails, the docstring is stale.
    """
    base = {
        name: getattr(C, name)(enacted, iowa_geom)
        for name in ("polsby_popper", "reock", "convex_hull")
    }
    worst = {name: 0.0 for name in base}
    for epsg in (26975, 26976, 26915):
        other = iowa_geom.to_crs(epsg=epsg)
        for name in base:
            values = getattr(C, name)(enacted, other)
            worst[name] = max(
                worst[name],
                max(
                    abs(values[d] - base[name][d]) / base[name][d]
                    for d in base[name]
                ),
            )
    assert 0.0035 < worst["polsby_popper"] < 0.0050    # ~0.42-0.43%
    assert 0.0100 < worst["reock"] < 0.0130            # ~1.15-1.16%
    assert worst["convex_hull"] < 0.0005               # ~0.03%
    # the ordering is the finding: Reock is the projection-sensitive one, and
    # it is sensitive by more than an order of magnitude over convex hull.
    assert worst["reock"] > 2 * worst["polsby_popper"] > 10 * worst["convex_hull"]


@iowa
def test_unlabelled_degrees_would_have_been_wrong_by_percent_not_by_a_rounding(
    enacted, iowa_geom
):
    """What the crs=None hole let through, measured rather than asserted.

    The measures are computed here by hand on lon/lat coordinates, because the
    module now refuses to compute them at all. District 1's Polsby-Popper comes
    out 5.2% low and its Reock 22.4% low — the size of a real difference between
    plans, arriving silently.
    """
    reference_pp = C.polsby_popper(enacted, iowa_geom)
    reference_reock = C.reock(enacted, iowa_geom)
    degrees = iowa_geom.to_crs(4326)
    lookup = dict(zip((str(g) for g in degrees["GEOID"]), degrees.geometry))
    members = {}
    for unit, district in enacted.items():
        members.setdefault(district, []).append(lookup[str(unit)])

    errors_pp, errors_reock = {}, {}
    for district, parts in members.items():
        shape = shapely.union_all(parts)
        pp = 4 * math.pi * shape.area / shape.length**2
        radius = shapely.minimum_bounding_radius(shape)
        reock = shape.area / (math.pi * radius**2)
        errors_pp[district] = abs(pp - reference_pp[district]) / reference_pp[district]
        errors_reock[district] = (
            abs(reock - reference_reock[district]) / reference_reock[district]
        )

    assert errors_pp[1] == pytest.approx(0.052, abs=0.005)
    assert errors_reock[1] == pytest.approx(0.224, abs=0.010)
    assert min(errors_pp.values()) > 0.05

    # and the module refuses to produce any of it
    unlabelled = degrees.set_crs(None, allow_override=True)
    with pytest.raises(ValueError, match="geom.crs is None"):
        C.polsby_popper(enacted, unlabelled)


@iowa
def test_the_project_crs_passes_the_guard_it_installed(iowa_geom):
    """EPSG:5070 must be accepted over Iowa, and its margin is worth knowing.

    It is the most distorted projection the guard admits (1.78% of a 3% budget),
    for the reason the module docstring gives: Iowa sits between Albers CONUS's
    standard parallels. This test is here so that a future tightening of
    MAX_ANISOTROPY cannot silently break the project's own data.
    """
    assert iowa_geom.crs.to_epsg() == 5070
    report = C.crs_distortion(iowa_geom.crs, iowa_geom.total_bounds)
    assert report["anisotropy"] == pytest.approx(0.0178, abs=0.001)
    assert report["anisotropy"] < C.MAX_ANISOTROPY
    assert report["scale_spread"] < 0.001


@iowa
def test_cache_matches_uncached_on_real_iowa_plans(enacted, iowa_geom, iowa_adjacency):
    """Same numbers, exactly, on the geometry that actually matters.

    The synthetic cache tests use squares; a dissolve of real county polygons
    is where a stale or mis-keyed entry would show up.
    """
    counties = sorted(enacted)
    variants = [dict(enacted)]
    for geoid in counties[:12]:
        variant = dict(enacted)
        variant[geoid] = 1 + (variant[geoid] % 4)
        variants.append(variant)

    plain = uncached_series(variants, iowa_geom, iowa_adjacency)
    cache = C.MeasureCache()
    cached = C.metric_series(variants, iowa_geom, iowa_adjacency, cache)
    for name in plain:
        assert plain[name] == cached[name]
    assert cache.stats()["hits"] > 0
