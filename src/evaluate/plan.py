"""The plan type, its invariants, and evaluate's own data loaders.

A plan is ``dict[str, int]``: unit GEOID -> district id, districts numbered
1..k (docs/ARCHITECTURE.md section 3).

**This module deliberately duplicates the unit and adjacency loaders in
src/generate/units.py.** See src/evaluate/README.md: the two packages do not
share a loader, because a shared module is an import edge and the firewall
exists to forbid exactly that edge. Factoring these into a common utility
invalidates every result produced afterwards. Do not do it.

Unlike the generator's loader, this one has no schema guard: evaluate is
entitled to see partisan columns (tools/firewall.yaml sets
``forbidden_columns: false`` for this package). The asymmetry is the point.
"""
from __future__ import annotations

import csv
import json
from collections import deque
from pathlib import Path
from typing import Iterable, Mapping

Plan = dict[str, int]

PROCESSED = Path("data/processed")

#: How many offending ids an error message lists before it truncates.
_MAX_LISTED = 8


class AdjacencyError(ValueError):
    """The adjacency graph itself is malformed — not the plan drawn on it.

    A subclass of ValueError so existing callers catching ValueError still see
    it, but :func:`is_valid` re-raises it instead of folding it into ``False``.
    A filter that quietly rejected every plan because the *graph* was broken
    would look exactly like a filter that found no valid plan.
    """


# --------------------------------------------------------------------------- #
# loading and saving
# --------------------------------------------------------------------------- #

def load_plan(path: str | Path) -> Plan:
    """Read a plan from CSV with exactly the columns ``GEOID,district``.

    GEOIDs are kept as strings (leading zeros are significant outside Iowa).
    Raises ValueError on a missing column, a repeated GEOID, or a district id
    that is not an integer.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        for required in ("GEOID", "district"):
            if required not in fields:
                raise ValueError(
                    f"{path}: plan CSV must have columns GEOID,district; "
                    f"found {fields}"
                )
        plan: Plan = {}
        for lineno, row in enumerate(reader, start=2):
            geoid = (row["GEOID"] or "").strip()
            raw = (row["district"] or "").strip()
            if not geoid:
                raise ValueError(f"{path}:{lineno}: empty GEOID")
            if geoid in plan:
                raise ValueError(
                    f"{path}:{lineno}: unit {geoid} assigned more than once "
                    f"(already assigned to district {plan[geoid]})"
                )
            try:
                district = int(raw)
            except ValueError:
                raise ValueError(
                    f"{path}:{lineno}: district id for unit {geoid} must be an "
                    f"integer; got {raw!r}"
                ) from None
            plan[geoid] = district
    if not plan:
        raise ValueError(f"{path}: plan CSV has no rows")
    return plan


def save_plan(plan: Plan, path: str | Path) -> None:
    """Write a plan as CSV with the columns ``GEOID,district``, sorted by GEOID.

    Sorted output makes two runs of the same pipeline byte-comparable.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["GEOID", "district"])
        for geoid in sorted(plan):
            writer.writerow([geoid, int(plan[geoid])])


def load_adjacency(path: str | Path | None = None) -> dict[str, list[str]]:
    """Rook adjacency as ``{GEOID: [GEOID, ...]}``.

    evaluate's own loader; see the module docstring for why it is not shared
    with src/generate.
    """
    path = Path(path) if path is not None else PROCESSED / "ia_adjacency.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    adjacency = {str(k): [str(x) for x in v] for k, v in raw.items()}
    try:
        check_adjacency(adjacency)
    except AdjacencyError as exc:
        raise AdjacencyError(f"{path}: {exc}") from None
    return adjacency


def load_units(path: str | Path | None = None):
    """Units as a pandas DataFrame of GEOID (str), NAME, pop.

    evaluate's own loader. Returns a DataFrame rather than a dict so that
    downstream metric modules keep whatever columns the file carries; use
    :func:`populations` when all you want is GEOID -> pop.
    """
    import pandas as pd

    path = Path(path) if path is not None else PROCESSED / "ia_units.csv"
    return pd.read_csv(path, dtype={"GEOID": str})


def populations(path: str | Path | None = None) -> dict[str, int]:
    """Convenience view of :func:`load_units`: ``{GEOID: pop}``."""
    frame = load_units(path)
    return {str(g): int(p) for g, p in zip(frame["GEOID"], frame["pop"])}


# --------------------------------------------------------------------------- #
# structure
# --------------------------------------------------------------------------- #

def check_adjacency(adjacency: Mapping[str, Iterable[str]]) -> None:
    """Raise :class:`AdjacencyError` unless the graph is a well-formed undirected
    rook graph: non-empty, every neighbour is itself a node, and every edge is
    recorded from both ends.

    **Decision: validate, do not symmetrize.** Contiguity is the one FEDERAL
    pass/fail constraint in CRITERIA.md section 1, and connectivity is read from
    this mapping by following ``adjacency[node]`` outward. On an asymmetric
    mapping that read is directed, and the answer then depends on which node the
    traversal happens to start from — i.e. on the alphabetical order of unit ids::

        {'a': ['b'], 'b': []}   -> 'a' reaches 'b', district looks connected
        {'a': [], 'b': ['a']}   -> 'a' reaches nothing, district looks split

    Identical edge set, opposite verdicts. Symmetrizing (taking the union of both
    directions) would also remove the order dependence, and it was rejected: an
    asymmetric map is not a formatting quirk to repair, it is evidence that
    whoever built or filtered it dropped a unit from one side only — exactly what
    happens when adversarial or detect subsets the graph. Repairing it silently
    would hand that caller a contiguity verdict on an edge set they never wrote,
    which is the failure mode this package refuses everywhere else. Raising puts
    the defect where it was introduced.

    Self-loops are not an error here; they cannot change a connectivity verdict.

    O(E), so it is re-run on every :func:`validate` call rather than cached —
    the same order as the connectivity BFS it precedes, and 222 edges on the
    Iowa county graph.
    """
    if not adjacency:
        raise AdjacencyError("adjacency graph is empty")
    nodes = set(adjacency)
    dangling: list[str] = []
    one_sided: list[str] = []
    for node, neighbours in adjacency.items():
        for neighbour in neighbours:
            if neighbour not in nodes:
                dangling.append(f"{node}->{neighbour}")
            elif node not in set(adjacency[neighbour]):
                one_sided.append(f"{node}->{neighbour}")
    if dangling or one_sided:
        parts = []
        if dangling:
            parts.append(
                f"{len(dangling)} edge(s) name a unit that is not a node: "
                f"{_sample(sorted(dangling))}"
            )
        if one_sided:
            parts.append(
                f"{len(one_sided)} edge(s) are recorded from one end only: "
                f"{_sample(sorted(one_sided))}"
            )
        raise AdjacencyError(
            "adjacency graph is not symmetric, so contiguity would depend on "
            "unit id order: " + "; ".join(parts)
        )


def districts(plan: Plan) -> dict[int, list[str]]:
    """``{district id: [GEOID, ...]}``, ids ascending and members sorted."""
    out: dict[int, list[str]] = {}
    for geoid, district in plan.items():
        out.setdefault(int(district), []).append(geoid)
    return {d: sorted(out[d]) for d in sorted(out)}


def aggregate(plan: Plan, values: Mapping[str, float]) -> dict[int, float]:
    """Sum ``values`` over the units of each district.

    Every unit in the plan must have a value and every value must belong to a
    unit in the plan. Silently dropping a county's population or votes is the
    kind of error that produces a plausible wrong number, so both directions
    raise instead.
    """
    missing = sorted(set(plan) - set(values))
    if missing:
        raise ValueError(
            f"aggregate: no value for {len(missing)} unit(s) in the plan: "
            f"{_sample(missing)}"
        )
    extra = sorted(set(values) - set(plan))
    if extra:
        raise ValueError(
            f"aggregate: {len(extra)} value(s) for unit(s) not in the plan: "
            f"{_sample(extra)}"
        )
    out: dict[int, float] = {}
    for geoid, district in plan.items():
        d = int(district)
        out[d] = out.get(d, 0) + values[geoid]
    return {d: out[d] for d in sorted(out)}


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #

def validate(plan: Plan, adjacency: Mapping[str, Iterable[str]], k: int) -> None:
    """Raise ValueError unless the plan satisfies every invariant.

    Checked, in order (ARCHITECTURE.md section 3):

    1. every unit of the adjacency graph is assigned exactly once, and no unit
       outside it is assigned;
    2. the district ids are exactly ``1..k``, with none empty;
    3. every district is connected on the rook graph.

    ``adjacency`` defines the universe of units: a plan that omits one of its
    nodes, or names a unit it does not contain, is invalid.

    Before any of that, the graph is checked by :func:`check_adjacency` and an
    :class:`AdjacencyError` is raised if it is malformed — see that function for
    why an asymmetric mapping is rejected rather than symmetrized. That error
    describes the graph, not the plan, and :func:`is_valid` propagates it.
    """
    if int(k) != k or k < 1:
        raise ValueError(f"validate: k must be a positive integer; got {k!r}")
    k = int(k)

    check_adjacency(adjacency)
    nodes = set(adjacency)

    non_integer = sorted(
        str(g) for g, d in plan.items() if not isinstance(d, int) or isinstance(d, bool)
    )
    if non_integer:
        raise ValueError(
            f"district ids must be integers; {len(non_integer)} unit(s) are not: "
            f"{_sample(non_integer)}"
        )

    assigned = set(plan)
    missing = sorted(nodes - assigned)
    if missing:
        raise ValueError(
            f"plan does not assign every unit: {len(missing)} of {len(nodes)} "
            f"unit(s) unassigned: {_sample(missing)}"
        )
    unknown = sorted(assigned - nodes)
    if unknown:
        raise ValueError(
            f"plan assigns {len(unknown)} unit(s) that are not in the "
            f"adjacency graph: {_sample(unknown)}"
        )

    members = districts(plan)
    ids = set(members)
    expected = set(range(1, k + 1))
    empty = sorted(expected - ids)
    surplus = sorted(ids - expected)
    if empty or surplus:
        parts = []
        if empty:
            parts.append(f"district(s) {empty} are empty")
        if surplus:
            parts.append(f"district id(s) {surplus} are outside 1..{k}")
        raise ValueError(
            f"district ids must be exactly 1..{k}: " + "; ".join(parts)
        )

    for district in sorted(members):
        components = _components(members[district], adjacency)
        if len(components) > 1:
            sizes = [len(c) for c in components]
            raise ValueError(
                f"district {district} is not connected on the rook graph: "
                f"{len(components)} components with sizes {sizes}; "
                f"smallest is {_sample(components[-1])}"
            )


def is_valid(plan: Plan, adjacency: Mapping[str, Iterable[str]], k: int) -> bool:
    """:func:`validate` as a predicate, for callers filtering many plans.

    False means *this plan* is invalid. A malformed graph raises
    :class:`AdjacencyError` through this function rather than returning False,
    because every plan on a broken graph would be "invalid" and the filter would
    report an empty result instead of a defect.
    """
    try:
        validate(plan, adjacency, k)
    except AdjacencyError:
        raise
    except ValueError:
        return False
    return True


def _components(
    unit_ids: Iterable[str], adjacency: Mapping[str, Iterable[str]]
) -> list[list[str]]:
    """Connected components of the induced subgraph, largest first.

    Reads the mapping in one direction only, which is correct exactly because
    :func:`check_adjacency` has already established that both directions are
    present. Called on an unchecked mapping it would inherit that mapping's
    directedness; every entry point here checks first.
    """
    members = set(unit_ids)
    seen: set[str] = set()
    found: list[list[str]] = []
    for start in sorted(members):
        if start in seen:
            continue
        queue = deque([start])
        seen.add(start)
        component = []
        while queue:
            node = queue.popleft()
            component.append(node)
            for neighbour in adjacency.get(node, ()):  # type: ignore[arg-type]
                if neighbour in members and neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        found.append(sorted(component))
    found.sort(key=lambda c: (-len(c), c))
    return found


def _sample(ids: list[str]) -> str:
    """Render at most _MAX_LISTED ids for an error message."""
    head = list(ids[:_MAX_LISTED])
    tail = "" if len(ids) <= _MAX_LISTED else f" ... (+{len(ids) - _MAX_LISTED} more)"
    return f"{head}{tail}"
