#!/usr/bin/env python3
"""Count each committed Iowa v2 draw's Democratic seats from the returns (D-043).

The draws file, ``docs/experiment-2/ia-draws-v2.csv.gz``, records each draw's
metrics but not its plan, so D-039 reads the seat count off the committed
|efficiency gap|. That reading cannot check itself: a plan that is not a sweep,
one party winning every district, can land where a sweep would. This script
checks it by counting.

It regenerates every committed chain from its seed, exactly as
``tools/experiment_2_tradeoffs.py`` drew it, and measures each draw with that
script's own ``measure_plan``. Every draw must reproduce its committed row: the
:data:`INTEGER_COLUMNS` exactly, and the others to within :data:`FLOAT_TOLERANCE`.
It counts each draw's Democratic seats under both contests from
``data/processed/ia_elections.csv``, whose statewide two-party totals must first
equal the certified ones, and keys each draw's plan in a way that ignores the
districts' numbers, so that distinct plans can be counted rather than bounded.

Run::

    python tools/recount_seats.py              # about 25 minutes on 4 cores
    python tools/recount_seats.py --jobs 2     # chains at once; default min(4, CPUs)
    python tools/recount_seats.py --out x.csv.gz

On fewer cores it takes longer, about 45 minutes on 2 and 1.5 hours on 1; more
than 4 helps only with ``--jobs`` above 4, down to about 18 minutes, which the
two 12,000-draw chains set.

It writes ``docs/first-result/ia-seats-v2.csv.gz``, or the ``--out`` path, which
must end in ``.csv.gz``: one row per committed draw, with its plan's key and its
seats. Beside it, with ``.json`` in place of ``.csv.gz``, it writes a record of
what it read: the draws file's hash, the configuration, every chain, the hashes
of its inputs and of VEST's file, the Python and gerrychain versions, and the
largest difference it found in each float column. It writes both only when every
committed draw reproduces and no district is tied; otherwise it exits non-zero
and writes nothing, so any earlier record at that path stays as it was. The
counts file's bytes depend on the counts and keys alone, so a passing run
rewrites it unchanged. The record also names the Python version, the input files
and VEST's file as found, and under Python 3.12 or later it records a
last-bit difference in mean Polsby-Popper (:data:`FLOAT_TOLERANCE`), so
``git diff`` on it shows where a run's environment differs from the committed
one's.

It refuses, printing one ``refused:`` line, if ``--out`` does not end in
``.csv.gz`` or a file it reads under ``data/processed`` is missing. It fails,
printing a ``FAIL:`` line for each problem (at most five per chain), if:

* a contest's statewide two-party totals are not the certified ones;
* the draws file and its sidecar disagree: on the configuration, on which
  chains there are, or on a chain's length;
* a chain's committed seed is not the one its index derives;
* a draw is misnumbered or does not reproduce its committed row, or its
  measured columns are not the committed ones;
* a district is tied under either contest; or
* the sampler stops or fails before a chain's committed length, or measuring a
  plan fails.

``tools/plot_seat_distribution.py`` reads each draw's seats off its
|efficiency gap| as D-039 does, and refuses to draw unless every reading agrees
with these counts and the record names the draws file it reads.

It needs the Iowa data built (``tools/fetch_raw.sh ia``, VEST's ``ia_2020.shp``,
``tools/prepare_data.py``) and gerrychain as ``requirements.txt`` pins it:
another version may draw other plans from the same seeds, and the run then
fails. No plan is kept: each is measured, counted, keyed and dropped. No vote
count is written, only seat counts.

These are the committed draws regenerated, not new ones: the sampler is asked
for each chain's committed draws and no more, and a draw that does not
reproduce its committed row fails the whole run.

Firewall: a ``tools/`` driver downstream of everything, like experiment 2, which
it imports. The sampler sees adjacency and population only, as it did there.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import experiment_2_tradeoffs as X      # noqa: E402
from evaluate import elections as E     # noqa: E402
from evaluate import partisan as P      # noqa: E402
from generate import ensemble, seeds    # noqa: E402

STATE, ENSEMBLE = "IA", "v2"
CONTESTS = (X.PRIMARY_CONTEST, X.ALTERNATE_CONTEST)
OUT = ROOT / "docs" / "first-result" / "ia-seats-v2.csv.gz"
ELECTIONS = X.PROCESSED / "ia_elections.csv"
NEUTRAL = tuple(X.PROCESSED / f"ia_{name}" for name in
                ("units.gpkg", "units.csv", "adjacency.json"))
#: VEST's file, if it is where tools/fetch_raw.sh says to put it. Its hashes
#: identify the returns in the sidecar; nothing else is read from it here.
VEST = tuple(ROOT / "data" / "raw" / "vest" / f"ia_2020.{ext}"
             for ext in ("zip", "dbf", "shp"))
#: The file the committed count was made from (D-043): VEST's 2020 precinct
#: returns on the Harvard Dataverse, with the MD5 Dataverse publishes for it.
#: The sidecar names it only when the zip present matches that MD5.
VEST_SOURCE = {"dataset": "doi:10.7910/DVN/K7760H", "version": "49.0",
               "file_id": 14304797, "file": "ia_2020.zip",
               "md5": "500252facae6107b93128406ebf5177b"}

#: Iowa's certified 2020 two-party totals, ``(D, R)``, as tools/prepare_data.py
#: and tests/test_elections.py assert them. The unsigned metrics the draws file
#: holds cannot tell the parties apart, so these totals are what fix which party
#: a seat is counted for.
CERTIFIED = {"G20PRE": (759_061, 897_672), "G20USS": (754_859, 864_997)}
#: The committed columns that identify a row rather than measure a plan.
IDENTITY_COLUMNS = frozenset({"chain_index", "chain_seed", "chain_completed", "draw"})
#: The committed columns that are counts, and must reproduce exactly.
INTEGER_COLUMNS = frozenset({"county_splits", "cut_edges", "population_spread",
                             *(f"competitive_districts@{c}" for c in CONTESTS)})
#: How far a committed float may sit from its regenerated value. Plans and vote
#: totals are integers; only the floats computed from them can move. Under
#: Python 3.11, which the README and CI pin, every committed float reproduces
#: exactly. Under 3.12 or later a mean Polsby-Popper can differ in its last bit:
#: the per-district values reproduce, but 3.12 made the built-in ``sum`` of
#: floats compensated, and ``measure_plan`` averages them with ``sum``.
FLOAT_TOLERANCE = 1e-12
#: Stop listing a chain's failures after this many: one is enough to refuse,
#: and a chain that has diverged would otherwise list every draw after it.
MAX_FAILURES_PER_CHAIN = 5


def committed() -> tuple[dict[int, list[dict]], dict]:
    """The committed rows by chain index, and the draws file's sidecar."""
    path = X.draws_path("ia", ENSEMBLE)
    rows: dict[int, list[dict]] = {}
    with gzip.open(path, "rt", newline="") as handle:
        for record in csv.DictReader(handle):
            rows.setdefault(int(record["chain_index"]), []).append(record)
    return rows, json.loads(X._sidecar_for(path).read_text())


def work_list(rows: dict[int, list[dict]], sidecar: dict) -> tuple[list, list[str]]:
    """The chains to regenerate, and every way the draws file and its sidecar
    disagree about them. A chain the draws file holds must be one the sidecar
    lists, with the same number of rows, under this configuration."""
    failures = []
    spec = X.ensemble_spec(STATE, ENSEMBLE)
    if sidecar.get("config_digest") != X.config_digest(spec):
        failures.append(f"the draws were made under configuration "
                        f"{sidecar.get('config_digest')}, not {X.config_digest(spec)}")
    listed = [chain["index"] for chain in sidecar["chains"]]
    if len(set(listed)) != len(listed):
        failures.append(f"the sidecar lists a chain twice: {sorted(listed)}")
    unlisted = sorted(set(rows) - set(listed))
    if unlisted:
        failures.append(f"the draws file holds chains {unlisted} the sidecar does not list")
    work = []
    for chain in sidecar["chains"]:
        got = len(rows.get(chain["index"], []))
        if got != chain["n_rows"]:
            failures.append(f"chain {chain['index']}: the sidecar records "
                            f"{chain['n_rows']} rows, the draws file {got}")
        elif got:
            work.append((chain["index"], chain["seed"], rows[chain["index"]]))
    work.sort(key=lambda w: -len(w[2]))       # longest first, so they overlap
    return work, failures


def check_totals(path: Path = ELECTIONS) -> list[str]:
    """Every contest whose statewide two-party totals are not the certified ones."""
    el = E.load_elections(path)
    failures = []
    for contest, certified in CERTIFIED.items():
        dem, rep = E.two_party(el, *E.two_party_columns(el, contest))
        got = (sum(dem.values()), sum(rep.values()))
        if got != certified:
            failures.append(f"{contest}: the returns total {got} (D, R), not the "
                            f"certified {certified}")
    return failures


def compare(measured: dict, record: dict) -> tuple[list[str], dict[str, float]]:
    """The columns of a committed row a regenerated draw does not reproduce,
    and each float column's absolute difference. The two must measure the same
    columns: a column dropped from measuring would otherwise go unchecked."""
    wrong, differences = [], {}
    expected = set(record) - IDENTITY_COLUMNS
    if set(measured) != expected:
        wrong.append(f"measured columns differ from the committed ones by "
                     f"{sorted(set(measured) ^ expected)}")
    for key in sorted(expected & set(measured)):
        value = measured[key]
        if key in INTEGER_COLUMNS:
            if int(value) != int(record[key]):
                wrong.append(f"{key} {value} against {record[key]}")
        else:
            difference = abs(float(value) - float(record[key]))
            differences[key] = difference
            if not difference <= FLOAT_TOLERANCE:
                wrong.append(f"{key} {value!r} against {record[key]}")
    return wrong, differences


def plan_key(plan: dict) -> str:
    """A key for the partition that does not depend on its district numbers:
    each district as its sorted units, the districts in order of their first."""
    districts: dict = {}
    for unit, district in plan.items():
        districts.setdefault(district, []).append(str(unit))
    canonical = "|".join(",".join(units) for units in
                         sorted(sorted(units) for units in districts.values()))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def recount_chain(work: tuple[int, int, list[dict]]) -> dict:
    """Regenerate one chain, check each draw against its row, count its seats.

    The sampler is asked for one plan per committed row and no more: a chain
    that died did so on the step after its last row, after up to 100,000
    attempts, and asking again would only repeat it.
    """
    index, seed, records = work
    spec = X.ensemble_spec(STATE, ENSEMBLE)
    result = {"index": index, "seed": seed, "seats": [], "plans": [],
              "differences": {}, "failures": [], "seconds": 0.0}
    expected = seeds.derive(X.MASTER_SEED, f"exp2-{spec.key.lower()}", index)
    if seed != expected:
        result["failures"].append(f"chain {index}: committed seed {seed}, but its "
                                  f"index derives {expected}")
        return result
    ctx = X.load_context(spec, CONTESTS)
    failures, differences = result["failures"], result["differences"]
    started = time.time()
    plans = iter(ensemble.sample(ctx["adjacency"], ctx["pops"], spec.k, spec.epsilon,
                                 spec.steps, seed, node_repeats=0))
    for draw, record in enumerate(records):
        if int(record["draw"]) != draw:
            failures.append(f"chain {index}: row {draw} is numbered {record['draw']}")
            break
        try:
            plan = next(plans)
        except StopIteration:
            failures.append(f"chain {index}: the sampler stopped after {draw} of "
                            f"{len(records)} committed draws")
            break
        except Exception as exc:          # the sampler dying before the committed length
            failures.append(f"chain {index}: the sampler failed at draw {draw}: "
                            f"{type(exc).__name__}: {exc}")
            break
        try:
            wrong, diffs = compare(X.measure_plan(plan, ctx), record)
            counts = []
            for contest in CONTESTS:
                dem, rep = ctx["contests"][contest]
                dem_seats, _, tied = P.seat_counts(plan, dem, rep)
                if tied:
                    wrong.append(f"{tied} tied district(s) under {contest}")
                counts.append(dem_seats)
        except Exception as exc:          # a defect in measuring, not in sampling
            failures.append(f"chain {index} draw {draw}: could not be measured: "
                            f"{type(exc).__name__}: {exc}")
            break
        for key, value in diffs.items():
            differences[key] = max(differences.get(key, 0.0), value)
        if wrong:
            failures.append(f"chain {index} draw {draw}: " + "; ".join(wrong))
            if len(failures) >= MAX_FAILURES_PER_CHAIN:
                break
        result["seats"].append(tuple(counts))
        result["plans"].append(plan_key(plan))
    result["seconds"] = time.time() - started
    return result


def recount(jobs: int) -> tuple[dict[int, dict], list[str]]:
    """Every committed chain recounted, and every way it failed to reproduce."""
    failures = check_totals()
    work, mismatched = work_list(*committed())
    failures += mismatched
    if failures:
        return {}, failures
    with ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
        results = {r["index"]: r for r in pool.map(recount_chain, work)}
    failures += [f for index in sorted(results) for f in results[index]["failures"]]
    return results, failures


def digest(path: Path, kind: str = "sha256") -> str | None:
    return hashlib.new(kind, path.read_bytes()).hexdigest() if path.exists() else None


def shown(path: Path) -> str:
    """``path`` as the repository names it, where it is inside the repository."""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def sidecar_path(out: Path) -> Path:
    return out.with_name(out.name.removesuffix(".csv.gz") + ".json")


def _write_atomically(path: Path, write) -> None:
    """``write(temporary)`` to a file beside ``path``, then put it in place, so
    a failure part-way leaves the last record that passed."""
    temporary = path.with_name(path.name + ".tmp")
    try:
        write(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def vest_digests() -> dict[str, dict[str, str]]:
    """VEST's files, where present: the zip by the MD5 its Dataverse record
    publishes, the files extracted from it by SHA-256."""
    found = {}
    for path in VEST:
        if path.exists():
            kind = "md5" if path.suffix == ".zip" else "sha256"
            found[shown(path)] = {kind: digest(path, kind)}
    return found


def write(results: dict[int, dict], out: Path) -> dict:
    """The counts and plan keys, one row per committed draw, and a sidecar."""
    out.parent.mkdir(parents=True, exist_ok=True)

    def counts(path: Path) -> None:
        # mtime=0 and no file name in the header, so the bytes depend on the data
        with open(path, "wb") as raw, \
                gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as binary, \
                io.TextIOWrapper(binary, encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["chain_index", "draw", "plan",
                             *(f"dem_seats@{c}" for c in CONTESTS)])
            for index in sorted(results):
                for draw, (plan, seats) in enumerate(
                        zip(results[index]["plans"], results[index]["seats"])):
                    writer.writerow([index, draw, plan, *seats])
    _write_atomically(out, counts)

    draws = X.draws_path("ia", ENSEMBLE)
    draws_sidecar = json.loads(X._sidecar_for(draws).read_text())
    rows = {i: len(r["seats"]) for i, r in results.items()}
    vest = vest_digests()
    fetched = vest.get(shown(VEST[0]), {}).get("md5")
    record = {
        "generated_by": "tools/recount_seats.py",
        "draws": shown(draws),
        "draws_sha256": digest(draws),
        "config_digest": X.config_digest(X.ensemble_spec(STATE, ENSEMBLE)),
        "chains": [{"index": c["index"], "seed": c["seed"],
                    "n_rows": rows.get(c["index"], 0)} for c in draws_sidecar["chains"]],
        "n_rows": sum(rows.values()),
        "contests": list(CONTESTS),
        "certified_two_party_totals": {c: list(t) for c, t in CERTIFIED.items()},
        "inputs_sha256": {shown(p): digest(p) for p in (*NEUTRAL, ELECTIONS)},
        "returns_source": VEST_SOURCE if fetched == VEST_SOURCE["md5"] else None,
        "vest": vest,
        "python": platform.python_version(),
        "gerrychain": importlib.metadata.version("gerrychain"),
        "integer_columns": sorted(INTEGER_COLUMNS),
        "float_tolerance": FLOAT_TOLERANCE,
        "largest_float_difference": {
            key: max(r["differences"].get(key, 0.0) for r in results.values())
            for key in sorted({k for r in results.values() for k in r["differences"]})},
    }
    _write_atomically(sidecar_path(out), lambda path: path.write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"))
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1),
                        help="chains recounted at once (default: the smaller of 4 "
                             "and the CPU count)")
    parser.add_argument("--out", type=Path, default=OUT,
                        help="counts file to write, ending in .csv.gz; the record goes "
                             "beside it as .json (default: "
                             "docs/first-result/ia-seats-v2.csv.gz)")
    args = parser.parse_args(argv)
    if not args.out.name.endswith(".csv.gz"):
        print(f"refused: --out must name a .csv.gz file, so its sidecar, "
              f"{sidecar_path(args.out).name}, cannot overwrite it", file=sys.stderr)
        return 1
    missing = [shown(p) for p in (*NEUTRAL, ELECTIONS) if not p.exists()]
    if missing:
        print(f"refused: {', '.join(missing)} not built; run tools/prepare_data.py "
              "(the README's 'Getting the data', then 'Building the analysis "
              "inputs')", file=sys.stderr)
        return 1
    results, failures = recount(args.jobs)
    for index in sorted(results):
        r = results[index]
        print(f"chain {index}: {len(r['seats'])} draws reproduced and counted, "
              f"{r['seconds']:.0f}s")
    if failures:
        for failure in failures:
            print("FAIL:", failure, file=sys.stderr)
        print(f"not written: {args.out} is unchanged", file=sys.stderr)
        return 1
    record = write(results, args.out)
    for c, contest in enumerate(CONTESTS):
        counts: dict[int, int] = {}
        for r in results.values():
            for seats in r["seats"]:
                counts[seats[c]] = counts.get(seats[c], 0) + 1
        print(f"{contest}: " + ", ".join(f"{s} D {n:,}" for s, n in sorted(counts.items())))
    plans = {p for r in results.values() for p in r["plans"]}
    print(f"wrote {args.out} ({record['n_rows']:,} draws, {len(plans):,} distinct plans); "
          "largest float difference "
          + ", ".join(f"{k} {v:.1e}" for k, v in record["largest_float_difference"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
