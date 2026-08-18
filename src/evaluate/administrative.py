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
degeneracy impossible to miss: :func:`degeneracy` detects it structurally, and
:func:`all_metrics` returns ``degenerate: True`` with a reason string alongside
the numbers. Anything that renders these metrics should render the reason.

The detection is structural, not a hardcoded "if Iowa": splits cannot occur when
every subdivision contains at most one unit, whatever the state.

--------------------------------------------------------------------------
The unit / subdivision distinction
--------------------------------------------------------------------------

A **unit** is what the plan assigns (``Plan`` is ``unit id -> district``). A
**subdivision** is the administrative container whose integrity is the criterion
— a county, a municipality, a precinct, depending on what is being asked. The
``units`` argument supplies the map from one to the other; see
:func:`subdivision_map` for the accepted forms. When the two coincide — Iowa —
the map is the identity and the degeneracy above follows.

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
)

#: The unit id column, when ``units`` is a DataFrame.
UNIT_COLUMN = "GEOID"

#: How many offending ids an error message lists before it truncates.
_MAX_LISTED = 8


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #

def subdivision_map(units: Any) -> dict[str, str]:
    """``{unit id: subdivision id}`` from whatever ``units`` the caller has.

    Four accepted forms, in the order they are tried:

    1. ``Mapping[str, str]`` — already a unit -> subdivision map. Used as given.
    2. a pandas DataFrame with a ``GEOID`` column and exactly one of
       :data:`SUBDIVISION_COLUMNS` — the general, precinct-level case.
    3. a pandas DataFrame with a ``GEOID`` column and none of them — **units are
       their own subdivisions.** This is ``data/processed/ia_units.csv``, and it
       is the degenerate case of the module docstring.
    4. any other iterable of unit ids — same identity treatment as (3).

    Ids are coerced to ``str``: GEOIDs have significant leading zeros outside
    Iowa, and a subdivision id read as an int silently merges ``01`` and ``1``.
    """
    if isinstance(units, Mapping):
        return {str(u): str(s) for u, s in units.items()}

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
        parents = [str(s) for s in units[found[0]]]
        return dict(zip(ids, parents))

    if isinstance(units, Iterable) and not isinstance(units, (str, bytes)):
        return {str(u): str(u) for u in units}

    raise TypeError(
        "subdivision_map: units must be a {unit: subdivision} mapping, a "
        f"DataFrame with a {UNIT_COLUMN!r} column, or an iterable of unit ids; "
        f"got {type(units).__name__}"
    )


def layers(plan: Any) -> dict[str, dict[str, int]]:
    """``{layer name: plan}`` from a single plan or several overlaid ones.

    A ballot style is determined by *every* district a voter sits in, so the
    general input is a set of districting layers — congressional, state senate,
    state house — not one plan. A bare ``Plan`` is treated as the single layer
    ``"district"``; a ``Mapping`` of name -> plan, or a sequence of plans, is
    used as given (sequences are named ``layer_0``, ``layer_1``, ...).

    Every layer must assign exactly the same set of units, since a voter has to
    be locatable in all of them.
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


# --------------------------------------------------------------------------- #
# the split metrics — two conventions, deliberately both
# --------------------------------------------------------------------------- #

def pieces_by_subdivision(plan: Any, units: Any) -> dict[str, set[int]]:
    """``{subdivision id: {district ids present in it}}``.

    The shared kernel of :func:`county_splits` and :func:`split_pieces`. Only the
    first districting layer is used — the splits criterion is about one plan
    against one set of subdivisions.

    The plan and the units table must describe exactly the same unit set. Both
    directions raise: a plan missing a unit and a units table listing a unit the
    plan never assigns are both errors that would otherwise produce a plausible
    wrong count rather than a failure.
    """
    parents = subdivision_map(units)
    assignment = next(iter(layers(plan).values()))

    missing = sorted(set(assignment) - set(parents))
    if missing:
        raise ValueError(
            f"{len(missing)} unit(s) in the plan are not in the units table: "
            f"{_sample(missing)}"
        )
    unassigned = sorted(set(parents) - set(assignment))
    if unassigned:
        raise ValueError(
            f"{len(unassigned)} unit(s) in the units table are not assigned by "
            f"the plan: {_sample(unassigned)}"
        )

    out: dict[str, set[int]] = {}
    for unit, district in assignment.items():
        out.setdefault(parents[unit], set()).add(int(district))
    return out


def county_splits(plan: Any, units: Any) -> int:
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
    """
    return sum(1 for districts in pieces_by_subdivision(plan, units).values()
               if len(districts) > 1)


def split_pieces(plan: Any, units: Any) -> int:
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
    readers who expect a splits-like metric to start at zero.

    **Pieces are district intersections, not connected fragments.** If a
    district's share of a county is itself in two disconnected parts, that is
    one piece here. Distinguishing them needs the adjacency graph, and this
    module deliberately takes no graph — see ``src/evaluate/compactness.py`` for
    the metrics that do.
    """
    return sum(len(districts)
               for districts in pieces_by_subdivision(plan, units).values())


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
    (see :func:`layers`). With the single congressional layer this project
    currently carries, a tuple is a 1-tuple and the count is therefore **exactly
    the number of districts** — 4 for Iowa, for every plan, forever. That is not
    a property of counties; it is a property of counting one layer, and it is
    reported by :func:`degeneracy` as such. The metric starts doing work as soon
    as a second layer is overlaid (a congressional plan over a state senate plan
    over a state house plan produces far more than ``max(k)`` combinations) or
    as soon as the administering subdivision is part of the ballot.

    ``by_subdivision=True`` switches to what an election office actually counts:
    distinct (subdivision, district tuple) pairs, i.e. one ballot style per
    combination *per county that prints it*. With a single layer that is
    identically :func:`split_pieces`, which is the connection between section 7
    and section 2.3 and the reason both live in this module. The default is
    ``False`` because it is section 7's stated definition, not because it is the
    more useful one.
    """
    parents = subdivision_map(units)
    named = layers(plan)
    unit_ids = set(next(iter(named.values())))

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
        unit_ids = set(next(iter(layers(plan).values())))
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
    """Which of these metrics are structural constants for this input.

    Returns ``{"splits": bool, "ballot_styles": bool, "degenerate": bool,
    "reason": str}``. ``reason`` is ``""`` when nothing is degenerate.

    Two independent conditions, both detected structurally rather than by
    recognising a state:

    ``splits``
        every subdivision contains at most one unit, so no plan can split one.
        ``county_splits`` is then identically 0 and ``split_pieces`` identically
        the unit count, for every plan over these units. True for Iowa
        congressional (units are counties, Iowa Code ch. 42) — FEASIBILITY.md
        section 5.3.

    ``ballot_styles``
        the plan has a single districting layer, so a ballot style tuple is a
        1-tuple and the count is identically the number of districts. True
        whatever the unit level; only overlaying a second layer (or counting
        ``by_subdivision``) removes it.

    A metric flagged here must not be fed to an outlier percentile: the ensemble
    distribution is a point mass, and "the plan sits at the 0th percentile of a
    constant" is a sentence with no content.
    """
    parents = subdivision_map(units)
    sizes: dict[str, int] = {}
    for parent in parents.values():
        sizes[parent] = sizes.get(parent, 0) + 1
    largest = max(sizes.values()) if sizes else 0
    splits_degenerate = largest <= 1

    named = layers(plan)
    styles_degenerate = len(named) == 1

    reasons: list[str] = []
    if splits_degenerate:
        reasons.append(
            f"every one of the {len(sizes)} subdivisions contains exactly one "
            "unit, so no plan over these units can split a subdivision: "
            "county_splits is identically 0 and split_pieces identically "
            f"{len(parents)} (docs/FEASIBILITY.md section 5.3; for Iowa "
            "congressional the units are the counties, Iowa Code ch. 42)"
        )
    if styles_degenerate:
        reasons.append(
            f"the plan has a single districting layer ({next(iter(named))!r}), "
            "so every ballot style tuple has length 1 and ballot_styles is "
            "identically the number of districts; the metric varies only once "
            "a second layer is overlaid or ballot styles are counted per "
            "subdivision"
        )
    return {
        "splits": splits_degenerate,
        "ballot_styles": styles_degenerate,
        "degenerate": bool(reasons),
        "reason": "; ".join(reasons),
    }


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #

def all_metrics(plan: Any, units: Any, voters: Any = None) -> dict[str, Any]:
    """Every administrative metric for one plan, with the degeneracy flags.

    Keys:

    ``county_splits``            count of split subdivisions (section 2.3)
    ``split_pieces``             count of pieces (section 2.3)
    ``excess_pieces``            ``split_pieces`` minus the subdivision count
    ``ballot_styles``            distinct district tuples (section 7)
    ``ballot_styles_by_subdivision``  distinct (subdivision, tuple) pairs
    ``ballot_styles_per_10k``    ``None`` unless ``voters`` is given
    ``n_units`` / ``n_subdivisions`` / ``n_districts`` / ``n_layers``
    ``degenerate``               ``True`` if any metric here is a structural
                                 constant for this input
    ``degenerate_splits`` / ``degenerate_ballot_styles``  which one
    ``degenerate_reason``        plain-language why, ``""`` if none

    Values are numbers except the three degeneracy entries; the flags are not
    optional decoration. On Iowa this function returns
    ``county_splits: 0, split_pieces: 99, ballot_styles: 4`` for every plan ever
    passed to it, and a reader who sees those three numbers without the reason
    string will mistake arithmetic for a result. See the module docstring.

    ``voters`` is left ``None`` by default and never inferred from a file; a
    caller that wants ``ballot_styles_per_10k`` states which electorate it
    means (1,690,871 votes cast in Iowa in the 2020 presidential election, if
    that is the one).
    """
    counts = pieces_by_subdivision(plan, units)
    named = layers(plan)
    assignment = next(iter(named.values()))
    flags = degeneracy(plan, units)

    n_subdivisions = len(counts)
    pieces = sum(len(d) for d in counts.values())
    out: dict[str, Any] = {
        "county_splits": sum(1 for d in counts.values() if len(d) > 1),
        "split_pieces": pieces,
        "excess_pieces": pieces - n_subdivisions,
        "ballot_styles": ballot_styles(plan, units),
        "ballot_styles_by_subdivision": ballot_styles(
            plan, units, by_subdivision=True
        ),
        "ballot_styles_per_10k": None,
        "n_units": len(assignment),
        "n_subdivisions": n_subdivisions,
        "n_districts": len(set(assignment.values())),
        "n_layers": len(named),
        "degenerate": flags["degenerate"],
        "degenerate_splits": flags["splits"],
        "degenerate_ballot_styles": flags["ballot_styles"],
        "degenerate_reason": flags["reason"],
    }
    if voters is not None:
        out["ballot_styles_per_10k"] = ballot_styles_per_10k(plan, units, voters)
    return out


def _sample(ids: list[str]) -> str:
    """Render at most _MAX_LISTED ids for an error message."""
    head = list(ids[:_MAX_LISTED])
    tail = "" if len(ids) <= _MAX_LISTED else f" ... (+{len(ids) - _MAX_LISTED} more)"
    return f"{head}{tail}"
