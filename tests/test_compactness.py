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

def frame(**shapes):
    """GeoDataFrame of named shapes, no CRS (the figures are abstract)."""
    names = list(shapes)
    return gpd.GeoDataFrame(
        {"GEOID": names}, geometry=[shapes[n] for n in names], crs=None
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

def test_geographic_crs_is_refused():
    geom = gpd.GeoDataFrame({"GEOID": ["A"]}, geometry=[SQUARE], crs="EPSG:4326")
    with pytest.raises(ValueError, match="geographic"):
        C.polsby_popper({"A": 1}, geom)


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
        {"GEOID": ["a", "a"]}, geometry=[cell(0, 0), cell(1, 0)], crs=None
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
