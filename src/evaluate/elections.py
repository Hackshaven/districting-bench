"""The partisan data loader — the ONLY sanctioned entry point to election data.

`data/processed/ia_elections.csv` is the one PARTISAN file in the data contract
(docs/ARCHITECTURE.md section 2). It may be read by evaluate, adversarial and
detect, and never by generate. Everything downstream of it should come through
this module rather than opening the file itself, so that the set of code paths
that touch partisan data stays enumerable.

Columns follow VEST's published convention: ``G`` + two-digit year + three-letter
office + one-letter party + three letters of the candidate's surname, e.g.
``G20PREDBID`` (2020 president, Democratic, Biden) and ``G20PRERTRU``
(Republican, Trump). docs/FEASIBILITY.md section 1 notes that the firewall's
denylist does not match this convention; that is a gap in the static check, and
the reason the ban on generate reading this file is enforced by the schema guard
in src/generate/units.py rather than by column names.

Verified statewide against Iowa's certified 2020 returns: G20PRERTRU = 897,672,
G20PREDBID = 759,061, two-party D share 0.4582. See tests/test_elections.py.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Mapping

DEFAULT_DEM = "G20PREDBID"
DEFAULT_REP = "G20PRERTRU"

PROCESSED = Path("data/processed")

Elections = dict[str, dict[str, int]]

#: G + 2-digit year + 3-letter office (the contest), then party letter, then
#: 3 letters of the candidate's surname.
_VEST = re.compile(r"^(G\d{2}[A-Z]{3})([A-Z])([A-Z]{3})$")

_PARTY_NAMES = {
    "D": "Democratic",
    "R": "Republican",
    "L": "Libertarian",
    "G": "Green",
    "C": "Constitution",
    "I": "Independent",
    "O": "Other/write-in",
}


def load_elections(path: str | Path | None = None) -> Elections:
    """Read election results as ``{GEOID: {column: votes}}``.

    Vote counts must be non-negative integers; a blank, non-integer or negative
    cell raises ValueError rather than becoming a zero, because a silently
    zeroed county is a wrong number that looks right.
    """
    path = Path(path) if path is not None else PROCESSED / "ia_elections.csv"
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        if "GEOID" not in fields:
            raise ValueError(f"{path}: election CSV must have a GEOID column; found {fields}")
        columns = [c for c in fields if c != "GEOID"]
        if not columns:
            raise ValueError(f"{path}: election CSV has no vote columns")

        out: Elections = {}
        for lineno, row in enumerate(reader, start=2):
            geoid = (row["GEOID"] or "").strip()
            if not geoid:
                raise ValueError(f"{path}:{lineno}: empty GEOID")
            if geoid in out:
                raise ValueError(f"{path}:{lineno}: unit {geoid} appears more than once")
            record: dict[str, int] = {}
            for column in columns:
                raw = (row[column] or "").strip()
                try:
                    votes = int(raw)
                except ValueError:
                    raise ValueError(
                        f"{path}:{lineno}: {column} for unit {geoid} must be an "
                        f"integer number of votes; got {raw!r}"
                    ) from None
                if votes < 0:
                    raise ValueError(
                        f"{path}:{lineno}: {column} for unit {geoid} is negative ({votes})"
                    )
                record[column] = votes
            out[geoid] = record
    if not out:
        raise ValueError(f"{path}: election CSV has no rows")
    return out


def columns(elections: Mapping[str, Mapping[str, int]]) -> list[str]:
    """Every vote column present, in a stable order.

    Taken from the first unit and checked against the rest: a file where units
    carry different column sets is malformed, not something to paper over.
    """
    if not elections:
        raise ValueError("no election data")
    first = next(iter(elections))
    names = list(elections[first])
    reference = set(names)
    for geoid, record in elections.items():
        if set(record) != reference:
            raise ValueError(
                f"unit {geoid} has columns {sorted(record)}, but unit {first} has "
                f"{sorted(reference)}; the election table is ragged"
            )
    return names


def available_contests(elections: Mapping[str, Mapping[str, int]]) -> list[str]:
    """The distinct contests in the data, e.g. ``['G20PRE', 'G20USS']``.

    A contest is the VEST year-and-office prefix; the several candidate columns
    of one contest collapse to one entry. A column that does not parse as VEST
    is returned unchanged rather than dropped, so nothing is hidden from a
    caller enumerating what is available.
    """
    seen: list[str] = []
    for column in columns(elections):
        match = _VEST.match(column)
        contest = match.group(1) if match else column
        if contest not in seen:
            seen.append(contest)
    return sorted(seen)


def contest_columns(
    elections: Mapping[str, Mapping[str, int]], contest: str
) -> dict[str, str]:
    """``{column: party letter}`` for one contest, e.g. ``{'G20PREDBID': 'D', ...}``."""
    out = {}
    for column in columns(elections):
        match = _VEST.match(column)
        if match and match.group(1) == contest:
            out[column] = match.group(2)
    if not out:
        raise ValueError(
            f"no columns for contest {contest!r}; available: {available_contests(elections)}"
        )
    return out


def two_party_columns(
    elections: Mapping[str, Mapping[str, int]], contest: str
) -> tuple[str, str]:
    """The ``(dem_col, rep_col)`` pair of one contest.

    Raises if the contest does not have exactly one D column and one R column —
    a fusion or multi-candidate ballot is a real situation that the two-party
    reduction cannot represent, and the caller must decide what to do about it.
    """
    parties = contest_columns(elections, contest)
    dem = [c for c, p in parties.items() if p == "D"]
    rep = [c for c, p in parties.items() if p == "R"]
    if len(dem) != 1 or len(rep) != 1:
        raise ValueError(
            f"contest {contest!r} does not reduce to two parties: "
            f"D columns {sorted(dem)}, R columns {sorted(rep)}"
        )
    return dem[0], rep[0]


def two_party(
    elections: Mapping[str, Mapping[str, int]],
    dem_col: str = DEFAULT_DEM,
    rep_col: str = DEFAULT_REP,
) -> tuple[dict[str, int], dict[str, int]]:
    """``(dem, rep)`` votes by GEOID for one contest.

    Third-party and write-in votes are dropped: that is what "two-party" means,
    and CRITERIA.md's conventions define vote share as the two-party Democratic
    fraction. The drop is not free — CRITERIA.md section 10 lists uncontested
    races and turnout as unmodelled — so callers reporting shares should say
    which contest they used.

    Units whose two-party total is zero are returned as zeros, not as shares;
    the D share is undefined there, and deciding what to do about it belongs to
    the metric, not the loader. :func:`zero_vote_units` lists them.
    """
    present = set(columns(elections))
    for name in (dem_col, rep_col):
        if name not in present:
            raise ValueError(
                f"no column {name!r} in the election data; available: {sorted(present)}"
            )
    if dem_col == rep_col:
        raise ValueError(f"dem_col and rep_col are the same column ({dem_col!r})")
    dem = {geoid: int(record[dem_col]) for geoid, record in elections.items()}
    rep = {geoid: int(record[rep_col]) for geoid, record in elections.items()}
    return dem, rep


def zero_vote_units(
    dem: Mapping[str, int], rep: Mapping[str, int]
) -> list[str]:
    """Units with no two-party votes at all, where the D share is undefined.

    Empty for Iowa counties in 2020, but not for every unit set — precincts with
    no residents exist — so downstream metrics should check rather than assume.
    """
    if set(dem) != set(rep):
        raise ValueError("dem and rep cover different units")
    return sorted(g for g in dem if dem[g] + rep[g] == 0)


def totals(elections: Mapping[str, Mapping[str, int]]) -> dict[str, int]:
    """Statewide sum of every vote column. Used for cross-checks against
    certified returns."""
    names = columns(elections)
    out = {name: 0 for name in names}
    for record in elections.values():
        for name in names:
            out[name] += int(record[name])
    return out


def party_name(letter: str) -> str:
    """Human-readable party for a VEST party letter; the letter itself if unknown."""
    return _PARTY_NAMES.get(letter.upper(), letter)
