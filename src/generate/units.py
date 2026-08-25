"""Unit loading for the neutral baseline, with a positive schema allowlist.

docs/FEASIBILITY.md section 1 established that the static check cannot see three
of the routes by which outcome data could reach this package: column naming it
does not match, a file read that names no column, and non-.py files. So this
module does not ask "is this column name forbidden". It asks the opposite and
stronger question: "is this one of the four things generation is entitled to
see." Anything else raises, whatever it is called.

ALLOWED is deliberately a frozenset literal in this file rather than a config
value. A config the loader reads is one more thing an attacker or a careless
refactor can widen.
"""
from __future__ import annotations

import json
from pathlib import Path

ALLOWED = frozenset({"GEOID", "NAME", "pop", "geometry"})

PROCESSED = Path("data/processed")


class SchemaViolation(RuntimeError):
    """Raised when generation is offered a column it is not entitled to see."""


def guard(columns) -> None:
    """Reject any column outside the allowlist. The whole point of this module."""
    extra = sorted(set(columns) - ALLOWED)
    if extra:
        raise SchemaViolation(
            f"src/generate may see {sorted(ALLOWED)} and nothing else; "
            f"refusing columns: {extra}. If a column belongs in generation, that "
            f"is a human decision recorded in docs/DECISIONS.md, not a widening "
            f"of this list to make a caller work."
        )


def load_units(path: Path | None = None):
    """Units as a dataframe of GEOID, NAME, pop. Guarded."""
    import pandas as pd

    frame = pd.read_csv(path or PROCESSED / "ia_units.csv", dtype={"GEOID": str})
    guard(frame.columns)
    return frame


def load_geometry(path: Path | None = None):
    """Units with geometry. Guarded."""
    import geopandas as gpd

    frame = gpd.read_file(path or PROCESSED / "ia_units.gpkg")
    guard(frame.columns)
    return frame


def load_adjacency(path: Path | None = None) -> dict[str, list[str]]:
    """Rook adjacency as {GEOID: [GEOID, ...]}."""
    raw = json.loads((path or PROCESSED / "ia_adjacency.json").read_text())
    return {str(k): [str(x) for x in v] for k, v in raw.items()}
