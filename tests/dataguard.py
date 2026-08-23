"""One definition of "the data is not built", for every test module.

`data/` is gitignored: the election returns are not redistributable, so they are
fetched by `tools/prepare_data.py` rather than committed. Tests that need them
must therefore skip, not fail, on a checkout where they have not been fetched.

Eight modules each grew their own version of that guard and four of them never
grew one at all, so on a fresh clone the suite produced 45 errors and 2 failures
instead of skips -- every one a `FileNotFoundError` from a module-scoped fixture
loading Iowa. The suite could only be run green inside a container that already
had the data, which meant "719 passed" was a claim nobody else could check.

Two further defects this file fixes by existing:

**The paths were relative to the working directory.** Four modules wrote
`Path("data/processed")`, which resolves against wherever pytest was invoked
rather than against the repository. Running the suite from any other directory
made those guards report the data missing and skip tests that could have run --
silently, since a skip is not a failure. Everything here is anchored to this
file's location.

**A guard on a test is the wrong place when a fixture does the loading.** Marking
each of forty-six tests is churn that the next new test will forget. `require()`
is called inside the fixture instead, so a module-scoped fixture skips every test
that depends on it, including ones written later.
"""
from __future__ import annotations

from pathlib import Path

import pytest

#: Anchored to this file, never to the working directory.
ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

REASON = "data/processed not built; run tools/prepare_data.py"


def missing(*names: str) -> list[str]:
    """Which of these files under data/processed are absent."""
    return [name for name in names if not (PROCESSED / name).exists()]


def have(*names: str) -> bool:
    return not missing(*names)


def require(*names: str) -> None:
    """Skip the calling test — or every test using the calling fixture.

    Call this at the top of a fixture that loads real data. Raising skip from a
    fixture skips each test that requests it, which is what makes a new test
    inherit the guard without anyone remembering to mark it.
    """
    absent = missing(*names)
    if absent:
        pytest.skip(f"{REASON} (missing: {', '.join(absent)})")


def requires(*names: str):
    """A skipif mark, for tests that read a path directly rather than via a fixture."""
    absent = missing(*names)
    return pytest.mark.skipif(
        bool(absent), reason=f"{REASON} (missing: {', '.join(absent)})")


#: The two convenience marks the modules already used, under their old names so
#: each module's call sites stay unchanged.
iowa = requires("ia_units.csv")
colorado = requires("co_units.csv")
