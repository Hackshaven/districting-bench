"""Administrative and logistical metrics: subdivision splits and ballot styles.

`docs/CRITERIA.md` section 7 — "Logistical and administrative constraints — the
underrated section" — is authoritative here. These are the criteria that decide
whether a map can actually be *run* by the people who print ballots, and section
7 makes two claims this module implements literally:

* **ballot styles are `DERIVED`, not `VALUE`.** "It is objective,
  administratively meaningful, and orthogonal to every partisan measure — which
  makes it one of the few criteria in this document that is not a `VALUE` choice
  in disguise." Nothing in this module is a normative choice about what a good
  map is. It is a count of the ballots an election office has to print.
* **splits have two incompatible counting conventions.** Section 2.3: "Count of
  split subdivisions, or count of split *pieces* — these differ and rank plans
  differently. Pick one and say which." Both are implemented, under names that
  say which is which, and the difference is demonstrated in
  ``tests/test_administrative.py`` on a case where the two orderings invert.

--------------------------------------------------------------------------
THE DEGENERACY WARNING — read this before quoting a number from this module
--------------------------------------------------------------------------

For Iowa congressional districting **these metrics are structurally constant and
carry no information about the plan.**

Iowa Code ch. 42 builds congressional districts from whole counties, so the unit
graph *is* the county graph (docs/ARCHITECTURE.md section 2). A unit is never
split because a unit is the atom of assignment, and a county is never split
because a county is a unit. Therefore, for every legal Iowa congressional plan
that has ever existed or could ever exist:

    county_splits == 0            always
    split_pieces  == 99           always (one piece per county)
    ballot_styles == 4            always (one per district)

docs/FEASIBILITY.md section 5.3 established this and measured it: "County
splits: identically zero in every plan, by construction ... The distribution is a
point mass at 0." A zero here is **not** a good score, it is arithmetic. A
detector that treats it as a signal is measuring nothing, and an ensemble
percentile computed against a point mass is undefined.

The response is not to omit the metric — the general implementation is correct
and does real work the moment the unit level is finer than the subdivision level
(precincts inside counties, blocks inside precincts). The response is to make the
degeneracy impossible to miss, **per metric**: :func:`degeneracy` returns one
flag with its own reason for each reported quantity, and :func:`all_metrics`
carries those flags alongside the numbers.

**Why per metric, and not one boolean (this is a fixed defect).** Two *different*
and *independent* structural conditions cause constancy here:

``subdivisions_are_units``
    every subdivision contains at most one unit, so no plan can split one.
    Freezes ``county_splits``, ``split_pieces``, ``excess_pieces`` **and**
    ``ballot_styles_by_subdivision``.

``single_layer``
    the plan has one districting layer, so a ballot style tuple is a 1-tuple.
    Freezes ``ballot_styles`` and ``ballot_styles_per_10k`` at the district
    count. Says nothing whatever about splits.

Iowa satisfies both at once, which is exactly what made an earlier single
``degenerate: True`` boolean look adequate. It was not. On a sub-county geography
with one congressional layer — 10 counties of 4 precincts, the geography
``tests/test_administrative.py`` is built on — ``single_layer`` holds and
``subdivisions_are_units`` does not, and the measured values across three plans
are::

    plan A   county_splits 1   split_pieces 13   ballot_styles_by_subdivision 13
    plan B   county_splits 3   split_pieces 13   ballot_styles_by_subdivision 13
    plan C   county_splits 2   split_pieces 14   ballot_styles_by_subdivision 14

Four live, varying metrics. A consumer obeying the rule below against a single
ORed boolean would have thrown all four away. So there is no ORed boolean any
more: :func:`degeneracy` reports ``metrics[name]["constant"]`` with
``metrics[name]["reason"]``, and the ready-made lists ``constant_metrics``,
``varying_metrics`` and ``unavailable_metrics``.

**The consumer rule, restated precisely:** feed a metric to an outlier percentile
only if its name is in ``varying_metrics``. A name in ``constant_metrics`` has a
point-mass ensemble distribution and its percentile has no content; a name in
``unavailable_metrics`` was not computed at all and is ``None``.

The detection is structural, not a hardcoded "if Iowa": splits cannot occur when
every subdivision contains at most one unit, whatever the state.

--------------------------------------------------------------------------
The unit / subdivision distinction, and which subdivisions are supported
--------------------------------------------------------------------------

A **unit** is what the plan assigns (``Plan`` is ``unit id -> district``). A
**subdivision** is the administrative container whose integrity is the criterion.
The ``units`` argument supplies the map from one to the other; see
:func:`subdivision_map` for the accepted forms. When the two coincide — Iowa —
the map is the identity and the degeneracy above follows.

Subdivisions come in two shapes and this module supports both explicitly:

*Partitioning* subdivisions — counties, precincts — cover the state. Every unit
belongs to exactly one.

*Partial* subdivisions — **municipalities**, which `docs/CRITERIA.md` section 2.3
and ``prompt.md`` Phase 2 both name — do **not** cover the state. Most of Iowa's
land area is unincorporated and belongs to no city. Two wrong answers are easy
here and both are now impossible:

* demanding total coverage and raising on a municipal layer, which makes the
  criterion uncomputable for every real state;
* giving every unincorporated unit the same sentinel parent, which creates one
  giant pseudo-municipality spanning the state that is counted as split by
  essentially every plan — inflating ``county_splits`` by one and
  ``split_pieces`` by up to ``K - 1`` out of nowhere.

Instead a unit may map to ``None`` (see :data:`MISSING_SUBDIVISION_STRINGS` for
the values that mean it), meaning **this unit is in no subdivision**. Such units
are excluded from the split counts entirely: they are not a subdivision, they are
not part of one, and nothing about them can be split. ``all_metrics`` reports
``n_units_in_no_subdivision`` so the exclusion is visible rather than implied.

The one thing partial coverage cannot support is
``ballot_styles(by_subdivision=True)``, which raises. That metric counts styles
per *administering* body, and a voter outside every municipality still gets a
ballot printed by somebody — so the answer is not "exclude them", it is "you have
handed me the wrong layer". CRITERIA.md section 7 makes the distinction itself:
"County election administration — counties administer ... Distinct from the
county-splits criterion, which is about representation, not logistics." Splits
are representation and tolerate a partial layer; administered ballot styles are
logistics and require the total-coverage layer that actually administers.

--------------------------------------------------------------------------
Layers are never chosen implicitly
--------------------------------------------------------------------------

A ballot style depends on every district a voter sits in, so :func:`ballot_styles`
takes a *set* of districting layers and uses all of them. The splits criterion is
about one plan against one set of subdivisions, so it needs exactly one layer.
When several are supplied, :func:`select_layer` **raises** rather than taking the
first one in dict insertion order — an earlier version did take the first, so
``county_splits({"a": L1, "b": L2}, units)`` returned 1 and
``county_splits({"b": L2, "a": L1}, units)`` returned 0 for the same two plans.
Pass ``layer="a"``. Every other ambiguity in this module raises too
(:func:`subdivision_map` refuses to choose between two candidate columns); this
one is no different.

--------------------------------------------------------------------------
Voters are a parameter, never a file read
--------------------------------------------------------------------------

:func:`ballot_styles_per_10k` takes ``voters`` as an argument. This module does
**not** read ``data/processed/ia_elections.csv`` and does not know what an
electorate is, because "per 10,000 voters" has at least four defensible
denominators — votes cast in a named contest, registered voters, citizen voting
age population, voting age population — and they differ by hundreds of thousands
of people in Iowa alone. Choosing one silently would bury a `VALUE` choice inside
a metric CRITERIA.md section 7 classes as `DERIVED`. The caller decides and the
caller is named in the output.

For reference, the denominator this project uses when it means "votes cast in the
2020 presidential election in Iowa" is **1,690,871**, the sum of the ``G20PRE*``
columns of ``data/processed/ia_elections.csv`` (all candidates, not two-party).
CRITERIA.md section 10 records that every metric here uses votes cast rather than
eligible voters, and that this is a modelling limitation rather than a neutral
default.

This module imports nothing from ``src/`` (``tools/firewall.yaml``:
``evaluate.allowed_imports = []``). It re-derives district membership rather than
importing ``src/evaluate/plan.py``; that duplication is cheaper than an import
edge.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

Plan = Mapping[str, int]

#: Column names accepted as "the subdivision containing this unit" when
#: ``units`` is a pandas DataFrame. Exactly one may be present; two would be an
#: ambiguity this module refuses to resolve on the caller's behalf.
SUBDIVISION_COLUMNS: tuple[str, ...] = (
    "subdivision",
    "SUBDIVISION",
    "county",
    "COUNTY",
    "county_geoid",
    "COUNTY_GEOID",
    "COUNTYFP",
    "COUNTYNS",
    "municipality",
    "MUNICIPALITY",
    "place",
    "PLACE",
    "PLACEFP",
)

#: The unit id column, when ``units`` is a DataFrame.
UNIT_COLUMN = "GEOID"

#: Subdivision values that mean "this unit is in no subdivision" — the
#: unincorporated case of a municipal layer. ``None`` and NaN mean it too, as
#: does an empty or whitespace-only string. These particular strings are what
#: ``str()`` of a missing value produces on a CSV round trip; a real subdivision
#: id is a GEOID or a name, never one of these.
MISSING_SUBDIVISION_STRINGS: frozenset[str] = frozenset({"", "nan", "none", "<na>"})

#: Names of the quantities :func:`all_metrics` reports, in report order. Every
#: one of them has an entry in ``degeneracy()["metrics"]``.
REPORTED_METRICS: tuple[str, ...] = (
    "county_splits",
    "split_pieces",
    "excess_pieces",
    "ballot_styles",
    "ballot_styles_by_subdivision",
    "ballot_styles_per_10k",
    "n_units",
    "n_units_in_no_subdivision",
    "n_subdivisions",
    "n_districts",
    "n_layers",
)

#: How many offending ids an error message lists before it truncates.
_MAX_LISTED = 8


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #

def subdivision_map(units: Any) -> dict[str, str | None]:
    """``{unit id: subdivision id or None}`` from whatever ``units`` the caller has.

    Four accepted forms, in the order they are tried:

    1. ``Mapping[str, str | None]`` — already a unit -> subdivision map. Used as
       given.
    2. a pandas DataFrame with a ``GEOID`` column and exactly one of
       :data:`SUBDIVISION_COLUMNS` — the general, precinct-level case.
    3. a pandas DataFrame with a ``GEOID`` column and none of them — **units are
       their own subdivisions.** This is ``data/processed/ia_units.csv``, and it
       is the degenerate case of the module docstring.
    4. any other iterable of unit ids — same identity treatment as (3).

    A value of ``None``, NaN, or one of :data:`MISSING_SUBDIVISION_STRINGS` maps
    the unit to ``None``: **it is in no subdivision.** That is the normal state
    of most units under a municipal layer and it is not an error; see the module
    docstring. Forms (3) and (4) can never produce it — a unit is always its own
    subdivision.

    Ids are coerced to ``str``: GEOIDs have significant leading zeros outside
    Iowa, and a subdivision id read as an int silently merges ``01`` and ``1``.
    """
    if isinstance(units, Mapping):
        return {str(u): _subdivision_id(s) for u, s in units.items()}

    columns = getattr(units, "columns", None)
    if columns is not None:
        names = list(columns)
        if UNIT_COLUMN not in names:
            raise ValueError(
                f"subdivision_map: units table must have a {UNIT_COLUMN!r} "
                f"column; found {names}"
            )
        found = [c for c in SUBDIVISION_COLUMNS if c in names]
        if len(found) > 1:
            raise ValueError(
                f"subdivision_map: units table has more than one subdivision "
                f"column ({found}); pass an explicit "
                f"{{unit: subdivision}} mapping instead of guessing which "
                f"containment the criterion means"
            )
        ids = [str(u) for u in units[UNIT_COLUMN]]
        if not found:
            return {u: u for u in ids}
        parents = [_subdivision_id(s) for s in units[found[0]]]
        return dict(zip(ids, parents))

    if isinstance(units, Iterable) and not isinstance(units, (str, bytes)):
        return {str(u): str(u) for u in units}

    raise TypeError(
        "subdivision_map: units must be a {unit: subdivision} mapping, a "
        f"DataFrame with a {UNIT_COLUMN!r} column, or an iterable of unit ids; "
        f"got {type(units).__name__}"
    )


def _subdivision_id(value: Any) -> str | None:
    """One subdivision cell -> an id, or ``None`` for "in no subdivision"."""
    if value is None:
        return None
    try:
        if value != value:              # NaN, pandas NA/NaT
            return None
    except (TypeError, ValueError):      # pragma: no cover - exotic cell types
        pass
    text = str(value).strip()
    if text.lower() in MISSING_SUBDIVISION_STRINGS:
        return None
    return text


def layers(plan: Any) -> dict[str, dict[str, int]]:
    """``{layer name: plan}`` from a single plan or several overlaid ones.

    A ballot style is determined by *every* district a voter sits in, so the
    general input is a set of districting layers — congressional, state senate,
    state house — not one plan. A bare ``Plan`` is treated as the single layer
    ``"district"``; a ``Mapping`` of name -> plan, or a sequence of plans, is
    used as given (sequences are named ``layer_0``, ``layer_1``, ...).

    Every layer must assign exactly the same set of units, since a voter has to
    be locatable in all of them. That guarantee is what lets the rest of this
    module read the unit set off any one layer without caring which.
    """
    named: dict[str, dict[str, int]]
    if isinstance(plan, Mapping):
        values = list(plan.values())
        if values and all(isinstance(v, Mapping) for v in values):
            named = {str(k): {str(u): int(d) for u, d in v.items()}
                     for k, v in plan.items()}
        else:
            named = {"district": {str(u): int(d) for u, d in plan.items()}}
    elif isinstance(plan, Sequence) and not isinstance(plan, (str, bytes)):
        named = {
            f"layer_{i}": {str(u): int(d) for u, d in p.items()}
            for i, p in enumerate(plan)
        }
    else:
        raise TypeError(
            "layers: plan must be a {unit: district} mapping, a mapping of "
            f"layer name -> plan, or a sequence of plans; got "
            f"{type(plan).__name__}"
        )
    if not named:
        raise ValueError("layers: no districting layers given")
    for name, one in named.items():
        if not one:
            raise ValueError(f"layers: layer {name!r} assigns no units")
    reference = set(next(iter(named.values())))
    for name, one in named.items():
        if set(one) != reference:
            differing = sorted(set(one) ^ reference)
            raise ValueError(
                f"layers: layer {name!r} does not assign the same units as the "
                f"first layer; {len(differing)} unit(s) differ: "
                f"{_sample(differing)}"
            )
    return named


def select_layer(plan: Any, layer: str | None = None) -> tuple[str, dict[str, int]]:
    """``(name, assignment)`` for the one layer a splits metric is about.

    The splits criterion compares **one** districting plan against one set of
    subdivisions, but :func:`layers` accepts several. This function is where that
    mismatch is resolved, and it resolves it by *asking*, never by guessing:

    * one layer — returned, whether or not ``layer`` names it;
    * several layers and ``layer`` given — that one, or ``KeyError`` if no layer
      has that name;
    * several layers and ``layer`` omitted — ``ValueError`` listing the names.

    The last case used to be ``next(iter(...))``, the first layer in dict
    insertion order, which made ``county_splits`` depend on the order the caller
    happened to build the dict — 1 or 0 for the same pair of plans, with no error
    and no warning. Order of a mapping is not a statement about which districting
    layer the splits criterion means, so it is not treated as one.
    """
    named = layers(plan)
    if len(named) == 1:
        name, only = next(iter(named.items()))
        if layer is not None and layer != name:
            raise KeyError(
                f"select_layer: no layer named {layer!r}; the only layer is "
                f"{name!r}"
            )
        return name, only
    if layer is None:
        raise ValueError(
            f"select_layer: {len(named)} districting layers were given "
            f"({sorted(named)}) but a splits metric is about exactly one plan "
            "against one set of subdivisions; pass layer=<name> to say which. "
            "Taking the first layer would make the answer depend on the order "
            "the caller built the mapping, which is not a statement about the "
            "criterion"
        )
    if layer not in named:
        raise KeyError(
            f"select_layer: no layer named {layer!r}; layers are "
            f"{sorted(named)}"
        )
    return layer, named[layer]


def _unit_ids(named: Mapping[str, Mapping[str, int]]) -> set[str]:
    """The unit set of a layer collection.

    Order-independent despite reading one layer: :func:`layers` has already
    rejected any collection whose layers disagree about the unit set.
    """
    return set(next(iter(named.values())))


def _check_unit_coverage(unit_ids: set[str], parents: Mapping[str, Any]) -> None:
    """The plan and the units table must describe exactly the same **units**.

    Both directions raise: a units table missing a unit the plan assigns and a
    units table listing a unit the plan never assigns are both errors that would
    otherwise produce a plausible wrong count rather than a failure. This is
    about the *unit* set only — a unit that is in the table with no subdivision
    is fine and is handled by the split metrics themselves.
    """
    missing = sorted(unit_ids - set(parents))
    if missing:
        raise ValueError(
            f"{len(missing)} unit(s) in the plan are not in the units table: "
            f"{_sample(missing)}"
        )
    unassigned = sorted(set(parents) - unit_ids)
    if unassigned:
        raise ValueError(
            f"{len(unassigned)} unit(s) in the units table are not assigned by "
            f"the plan: {_sample(unassigned)}"
        )


# --------------------------------------------------------------------------- #
# the split metrics — two conventions, deliberately both
# --------------------------------------------------------------------------- #

def pieces_by_subdivision(
    plan: Any, units: Any, *, layer: str | None = None
) -> dict[str, set[int]]:
    """``{subdivision id: {district ids present in it}}``.

    The shared kernel of :func:`county_splits` and :func:`split_pieces`. One
    districting layer is used and it is :func:`select_layer` that picks it —
    with several layers and no ``layer=`` argument this raises rather than
    silently taking the first.

    The plan and the units table must describe exactly the same unit set; see
    :func:`_check_unit_coverage`. **Units whose subdivision is ``None`` are
    excluded from the result**, which is how a partial (municipal) layer is
    supported: a unit in no city contributes to no city's split count. It is not
    lumped into a shared "no subdivision" bucket, because that bucket would span
    the state and read as a single enormous split municipality. See the module
    docstring.
    """
    parents = subdivision_map(units)
    _, assignment = select_layer(plan, layer)
    _check_unit_coverage(set(assignment), parents)

    out: dict[str, set[int]] = {}
    for unit, district in assignment.items():
        parent = parents[unit]
        if parent is None:
            continue
        out.setdefault(parent, set()).add(int(district))
    return out


def county_splits(plan: Any, units: Any, *, layer: str | None = None) -> int:
    """Count of split **subdivisions**: how many counties are cut at all.

    One of the two conventions CRITERIA.md section 2.3 distinguishes. A county
    divided among three districts contributes **1** to this count, exactly as
    much as a county divided between two. It answers "how many county
    governments have to deal with more than one member of Congress".

    The other convention is :func:`split_pieces`. They rank plans differently
    and neither is more correct; see that function's docstring for the worked
    contrast.

    Structurally zero whenever every subdivision holds one unit — Iowa
    congressional, always. See the module docstring and :func:`degeneracy`.

    Under a partial subdivision layer this counts split **municipalities** and
    nothing else; units in no municipality cannot be split and are not counted.
    """
    return sum(1 for districts in pieces_by_subdivision(plan, units, layer=layer).values()
               if len(districts) > 1)


def split_pieces(plan: Any, units: Any, *, layer: str | None = None) -> int:
    """Count of **pieces**: into how many parts the plan cuts the subdivisions.

    The other convention of CRITERIA.md section 2.3, and the one that measures
    *how badly* rather than *how often*. Defined as the number of distinct
    (subdivision, district) intersections in the plan, summed over every
    subdivision — so an uncut map scores the number of subdivisions, **not
    zero**, and a county divided among three districts contributes 3.

    Why the two rank differently, which is the whole reason CRITERIA.md insists
    on saying which you used. Against 10 counties:

    * plan A cuts one county four ways:   ``county_splits = 1``, ``split_pieces = 13``
    * plan B cuts three counties two ways: ``county_splits = 3``, ``split_pieces = 13``
    * plan C cuts two counties three ways: ``county_splits = 2``, ``split_pieces = 14``

    A ranks best on splits and ties B on pieces; C ranks between them on splits
    and worst on pieces. There is no reordering that makes both agree, and which
    ordering is right is a question about what the criterion is *for* — a
    representation criterion counts governments cut, an administrative one
    counts ballots printed. ``tests/test_administrative.py`` pins exactly this.

    ``excess_pieces`` in :func:`all_metrics` is ``split_pieces`` minus the
    subdivision count, i.e. the same ordering shifted to 0 for an uncut map, for
    readers who expect a splits-like metric to start at zero. Under a partial
    layer both terms count only real subdivisions, so an uncut municipal layer
    still gives ``excess_pieces == 0``.

    **Pieces are district intersections, not connected fragments.** If a
    district's share of a county is itself in two disconnected parts, that is
    one piece here. Distinguishing them needs the adjacency graph, and this
    module deliberately takes no graph — see ``src/evaluate/compactness.py`` for
    the metrics that do.
    """
    return sum(len(districts)
               for districts in pieces_by_subdivision(plan, units, layer=layer).values())


# --------------------------------------------------------------------------- #
# ballot styles
# --------------------------------------------------------------------------- #

def ballot_styles(plan: Any, units: Any, *, by_subdivision: bool = False) -> int:
    """Count of distinct district combinations — CRITERIA.md section 7's metric.

    Section 7 defines the ballot style count as the "count of unique district
    tuples across the map", and calls it "the single best proxy for
    administrative burden". A ballot style is a distinct ballot that has to be
    laid out, proofed, printed, tested and tabulated; every additional one is
    cost and an opportunity for misassignment.

    A unit's tuple is its district in each layer of ``plan``, in layer order
    (see :func:`layers`) — **all** layers, which is why this function takes no
    ``layer`` argument where the splits metrics do. With the single congressional
    layer this project currently carries, a tuple is a 1-tuple and the count is
    therefore **exactly the number of districts** — 4 for Iowa, for every plan,
    forever. That is not a property of counties; it is a property of counting one
    layer, and it is reported by :func:`degeneracy` as such, against this metric
    alone. The metric starts doing work as soon as a second layer is overlaid (a
    congressional plan over a state senate plan over a state house plan produces
    far more than ``max(k)`` combinations) or as soon as the administering
    subdivision is part of the ballot.

    ``by_subdivision=True`` switches to what an election office actually counts:
    distinct (subdivision, district tuple) pairs, i.e. one ballot style per
    combination *per county that prints it*. With a single layer that is
    identically :func:`split_pieces`, which is the connection between section 7
    and section 2.3 and the reason both live in this module. The default is
    ``False`` because it is section 7's stated definition, not because it is the
    more useful one.

    ``by_subdivision=True`` **requires a total-coverage subdivision layer and
    raises without one.** Every voter's ballot is printed by some administering
    body, so a unit in no subdivision is not an exclusion here the way it is for
    splits — it is evidence that the layer supplied administers nothing. Pass the
    county layer. CRITERIA.md section 7 keeps these apart itself: county election
    administration is "distinct from the county-splits criterion, which is about
    representation, not logistics".
    """
    parents = subdivision_map(units)
    named = layers(plan)
    unit_ids = _unit_ids(named)
    _check_unit_coverage(unit_ids, parents)

    if by_subdivision:
        uncovered = sorted(u for u in unit_ids if parents[u] is None)
        if uncovered:
            raise ValueError(
                f"ballot_styles(by_subdivision=True): {len(uncovered)} unit(s) "
                f"belong to no subdivision: {_sample(uncovered)}. Ballot styles "
                "per administering subdivision need a layer that covers every "
                "voter — every ballot is printed by somebody — so a partial "
                "layer such as municipalities cannot answer this; pass the "
                "county (administering) layer. The split metrics do accept a "
                "partial layer and exclude these units"
            )

    styles = set()
    for unit in unit_ids:
        tuple_ = tuple(one[unit] for one in named.values())
        styles.add((parents[unit], tuple_) if by_subdivision else tuple_)
    return len(styles)


def ballot_styles_per_10k(
    plan: Any, units: Any, voters: Any, *, by_subdivision: bool = False
) -> float:
    """Ballot styles per 10,000 voters — ``prompt.md``'s first-class output.

    ``10_000 * ballot_styles / voters``. CRITERIA.md section 7 names this as the
    `DERIVED` metric "worth computing and reporting, because nobody else does".

    **The denominator is voters, not population**, and this module does not
    choose which voters. ``voters`` is either a positive number (a total) or a
    ``Mapping[unit id, count]`` summed over the units the plan assigns. See the
    module docstring: the electorate is the caller's `VALUE` choice, and the
    project's 2020-presidential-votes-cast figure for Iowa is 1,690,871.

    A non-positive, non-finite, or missing electorate raises rather than
    returning ``inf`` or ``nan``. A rate per zero voters is not a large number,
    it is an undefined one, and a metric that quietly returns ``inf`` here
    propagates into percentile machinery that will happily rank it.
    """
    total = _voter_total(plan, voters)
    return 10_000.0 * ballot_styles(plan, units, by_subdivision=by_subdivision) / total


def _voter_total(plan: Any, voters: Any) -> float:
    """Resolve ``voters`` to a positive finite total, or raise saying why."""
    if isinstance(voters, Mapping):
        unit_ids = _unit_ids(layers(plan))
        by_unit = {str(u): float(n) for u, n in voters.items()}
        missing = sorted(unit_ids - set(by_unit))
        if missing:
            raise ValueError(
                f"ballot_styles_per_10k: no voter count for {len(missing)} "
                f"unit(s) in the plan: {_sample(missing)}"
            )
        total = float(sum(by_unit[u] for u in unit_ids))
    elif isinstance(voters, bool) or not isinstance(voters, (int, float)):
        raise TypeError(
            "ballot_styles_per_10k: voters must be a number or a "
            f"{{unit: count}} mapping; got {type(voters).__name__}"
        )
    else:
        total = float(voters)

    if math.isnan(total) or math.isinf(total):
        raise ValueError(
            f"ballot_styles_per_10k: voters must be finite; got {total!r}"
        )
    if total <= 0:
        raise ValueError(
            "ballot_styles_per_10k: ballot styles per 10,000 voters is "
            f"undefined for an electorate of {total:g}; the rate has no value "
            "at zero voters and returning inf would let it be ranked"
        )
    return total


# --------------------------------------------------------------------------- #
# degeneracy — the point of this module that is easiest to get wrong
# --------------------------------------------------------------------------- #

def degeneracy(plan: Any, units: Any) -> dict[str, Any]:
    """Which **individual** metrics are structural constants for this input.

    Returns::

        {
          "conditions": {"subdivisions_are_units": bool,
                         "no_subdivision_coverage": bool,
                         "total_subdivision_coverage": bool,
                         "single_layer": bool},
          "metrics": {name: {"constant": bool, "computable": bool,
                             "value": <the constant, or None>, "reason": str}},
          "constant_metrics":    (names whose value cannot vary),
          "unavailable_metrics": (names that cannot be computed at all),
          "varying_metrics":     (names that are computable and can vary),
        }

    ``metrics`` has an entry for every name in :data:`REPORTED_METRICS`, and
    ``reason`` is ``""`` exactly when the metric is both computable and free to
    vary.

    **There is deliberately no top-level ``degenerate`` boolean.** An earlier
    version returned one, ORing the two conditions below together, and it was
    wrong in the way that matters: it read as "the numbers in this report are
    constants" while meaning only "at least one of them is". The two conditions
    are independent and freeze *disjoint* sets of metrics:

    ``subdivisions_are_units``
        every subdivision contains at most one unit, so no plan can split one.
        Freezes ``county_splits`` at 0, ``split_pieces`` and
        ``ballot_styles_by_subdivision`` at the unit count, ``excess_pieces`` at
        0. True for Iowa congressional (units are counties, Iowa Code ch. 42) —
        FEASIBILITY.md section 5.3. It is also trivially true when no unit
        belongs to any subdivision, reported separately as
        ``no_subdivision_coverage``.

    ``single_layer``
        the plan has a single districting layer, so a ballot style tuple is a
        1-tuple. Freezes ``ballot_styles`` — and hence
        ``ballot_styles_per_10k`` at a fixed electorate — at the number of
        districts. It says nothing about splits and nothing about
        ``ballot_styles_by_subdivision``, both of which vary freely under it on
        any sub-county geography.

    Iowa satisfies both, which is why the conflation survived: there every metric
    really is constant. On 10 counties of 4 precincts with one congressional
    layer, only ``ballot_styles`` and ``ballot_styles_per_10k`` are.

    ``n_units``, ``n_units_in_no_subdivision``, ``n_subdivisions`` and
    ``n_layers`` are always reported constant: they are properties of the inputs,
    not of the assignment. ``n_districts`` is not — it is a property of the plan.
    It is nonetheless constant across a fixed-K ensemble, but that is a fact about
    how the ensemble was built, which this module cannot see and will not assert.

    **Consumer rule:** feed a metric to an outlier percentile only if its name is
    in ``varying_metrics``. A ``constant_metrics`` name has a point-mass ensemble
    distribution, and "the plan sits at the 0th percentile of a constant" is a
    sentence with no content. An ``unavailable_metrics`` name is ``None``.
    """
    parents = subdivision_map(units)
    covered = {u: p for u, p in parents.items() if p is not None}
    n_uncovered = len(parents) - len(covered)

    sizes: dict[str, int] = {}
    for parent in covered.values():
        sizes[parent] = sizes.get(parent, 0) + 1
    largest = max(sizes.values()) if sizes else 0
    subdivisions_are_units = largest <= 1
    no_coverage = not covered
    total_coverage = n_uncovered == 0

    named = layers(plan)
    single_layer = len(named) == 1
    n_units = len(_unit_ids(named))
    n_districts = (
        len(set(next(iter(named.values())).values())) if single_layer else None
    )

    if no_coverage:
        splits_reason = (
            f"none of the {len(parents)} units belongs to any subdivision, so "
            "there is nothing for a plan to split: county_splits is identically "
            "0 and split_pieces identically 0. This is an empty subdivision "
            "layer, not a result"
        )
    elif subdivisions_are_units:
        splits_reason = (
            f"every one of the {len(sizes)} subdivisions contains exactly one "
            "unit, so no plan over these units can split a subdivision: "
            f"county_splits is identically 0 and split_pieces identically "
            f"{len(covered)} (docs/FEASIBILITY.md section 5.3; for Iowa "
            "congressional the units are the counties, Iowa Code ch. 42)"
        )
    else:
        splits_reason = ""

    if single_layer:
        layer_reason = (
            f"the plan has a single districting layer ({next(iter(named))!r}), "
            "so every ballot style tuple has length 1 and ballot_styles is "
            f"identically the number of districts ({n_districts}); the metric "
            "varies only once a second layer is overlaid. This says nothing "
            "about the split metrics or about ballot_styles_by_subdivision, "
            "which vary under it whenever a subdivision holds more than one unit"
        )
    else:
        layer_reason = ""

    partial_reason = (
        f"{n_uncovered} of {len(parents)} unit(s) belong to no subdivision, so "
        "this subdivision layer administers no ballot for them; ballot styles "
        "per administering subdivision are not defined against a partial layer "
        "(pass the county layer). The split metrics are defined and are reported"
    )

    splits_constant = bool(splits_reason)
    metrics: dict[str, dict[str, Any]] = {
        "county_splits": _flag(splits_constant, True, 0, splits_reason),
        "split_pieces": _flag(
            splits_constant, True, len(covered), splits_reason
        ),
        "excess_pieces": _flag(splits_constant, True, 0, splits_reason),
        "ballot_styles": _flag(single_layer, True, n_districts, layer_reason),
        "ballot_styles_by_subdivision": _flag(
            splits_constant,
            total_coverage,
            len(covered),
            "; ".join(r for r in (splits_reason,
                                  "" if total_coverage else partial_reason) if r),
        ),
        "ballot_styles_per_10k": _flag(
            single_layer,
            True,
            None,
            (layer_reason + "; the rate is that constant times 10,000 over the "
             "electorate, so it too is fixed once the electorate is")
            if single_layer else "",
        ),
        "n_units": _flag(True, True, n_units, _INPUT_CONSTANT),
        "n_units_in_no_subdivision": _flag(
            True, True, n_uncovered, _INPUT_CONSTANT
        ),
        "n_subdivisions": _flag(True, True, len(sizes), _INPUT_CONSTANT),
        "n_districts": _flag(False, True, None, ""),
        "n_layers": _flag(True, True, len(named), _INPUT_CONSTANT),
    }
    assert set(metrics) == set(REPORTED_METRICS)

    return {
        "conditions": {
            "subdivisions_are_units": subdivisions_are_units,
            "no_subdivision_coverage": no_coverage,
            "total_subdivision_coverage": total_coverage,
            "single_layer": single_layer,
        },
        "metrics": metrics,
        "constant_metrics": tuple(
            n for n in REPORTED_METRICS if metrics[n]["constant"]
        ),
        "unavailable_metrics": tuple(
            n for n in REPORTED_METRICS if not metrics[n]["computable"]
        ),
        "varying_metrics": tuple(
            n for n in REPORTED_METRICS
            if metrics[n]["computable"] and not metrics[n]["constant"]
        ),
    }


_INPUT_CONSTANT = (
    "a property of the inputs rather than of the assignment: it is the same for "
    "every plan over these units, so it is a label on the ensemble, not a "
    "metric of a plan within it"
)


def _flag(
    constant: bool, computable: bool, value: Any, reason: str
) -> dict[str, Any]:
    """One per-metric degeneracy entry."""
    return {
        "constant": bool(constant),
        "computable": bool(computable),
        "value": value if (constant and computable) else None,
        "reason": reason if (constant or not computable) else "",
    }


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #

def all_metrics(
    plan: Any, units: Any, voters: Any = None, *, layer: str | None = None
) -> dict[str, Any]:
    """Every administrative metric for one plan, with per-metric degeneracy flags.

    Metric keys — every one of them also has an entry in ``degeneracy``:

    ``county_splits``            count of split subdivisions (section 2.3)
    ``split_pieces``             count of pieces (section 2.3)
    ``excess_pieces``            ``split_pieces`` minus the subdivision count
    ``ballot_styles``            distinct district tuples (section 7)
    ``ballot_styles_by_subdivision``  distinct (subdivision, tuple) pairs, or
                                 ``None`` under a partial subdivision layer
    ``ballot_styles_per_10k``    ``None`` unless ``voters`` is given
    ``n_units`` / ``n_units_in_no_subdivision`` / ``n_subdivisions`` /
    ``n_districts`` / ``n_layers``

    Bookkeeping keys:

    ``degeneracy``           ``{metric name: {constant, computable, value,
                             reason}}`` — :func:`degeneracy`'s ``metrics``
    ``constant_metrics`` / ``varying_metrics`` / ``unavailable_metrics``
                             the same information as three ready-made name lists
    ``degeneracy_conditions``  the two independent structural conditions
    ``n_districts_by_layer``   districts in each layer, by name
    ``splits_layer``           which layer the split metrics were computed on

    **Only names in ``varying_metrics`` may be fed to an outlier percentile.**
    There is no single ``degenerate`` boolean because the metrics here do not
    stand or fall together — on a sub-county geography with one congressional
    layer, ``ballot_styles`` is a constant while ``county_splits``,
    ``split_pieces``, ``excess_pieces`` and ``ballot_styles_by_subdivision`` all
    vary. On Iowa this function does return ``county_splits: 0,
    split_pieces: 99, ballot_styles: 4`` for every plan ever passed to it, and
    there all five names appear in ``constant_metrics``, each with its own reason.

    ``layer`` names the districting layer the split metrics use; it is required
    when ``plan`` carries more than one, and :func:`select_layer` raises rather
    than picking one. ``ballot_styles`` always uses every layer.

    ``voters`` is left ``None`` by default and never inferred from a file; a
    caller that wants ``ballot_styles_per_10k`` states which electorate it
    means (1,690,871 votes cast in Iowa in the 2020 presidential election, if
    that is the one).
    """
    named = layers(plan)
    splits_layer, assignment = select_layer(plan, layer)
    counts = pieces_by_subdivision(plan, units, layer=splits_layer)
    flags = degeneracy(plan, units)

    n_subdivisions = len(counts)
    pieces = sum(len(d) for d in counts.values())
    styles_by_subdivision: int | None
    if flags["conditions"]["total_subdivision_coverage"]:
        styles_by_subdivision = ballot_styles(plan, units, by_subdivision=True)
    else:
        styles_by_subdivision = None

    out: dict[str, Any] = {
        "county_splits": sum(1 for d in counts.values() if len(d) > 1),
        "split_pieces": pieces,
        "excess_pieces": pieces - n_subdivisions,
        "ballot_styles": ballot_styles(plan, units),
        "ballot_styles_by_subdivision": styles_by_subdivision,
        "ballot_styles_per_10k": None,
        "n_units": len(assignment),
        "n_units_in_no_subdivision": flags["metrics"][
            "n_units_in_no_subdivision"
        ]["value"],
        "n_subdivisions": n_subdivisions,
        "n_districts": len(set(assignment.values())),
        "n_layers": len(named),
        "n_districts_by_layer": {
            name: len(set(one.values())) for name, one in named.items()
        },
        "splits_layer": splits_layer,
        "degeneracy": flags["metrics"],
        "constant_metrics": flags["constant_metrics"],
        "varying_metrics": flags["varying_metrics"],
        "unavailable_metrics": flags["unavailable_metrics"],
        "degeneracy_conditions": flags["conditions"],
    }
    if voters is not None:
        out["ballot_styles_per_10k"] = ballot_styles_per_10k(plan, units, voters)
    return out


def _sample(ids: list[str]) -> str:
    """Render at most _MAX_LISTED ids for an error message."""
    head = list(ids[:_MAX_LISTED])
    tail = "" if len(ids) <= _MAX_LISTED else f" ... (+{len(ids) - _MAX_LISTED} more)"
    return f"{head}{tail}"
