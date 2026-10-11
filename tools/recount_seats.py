#!/usr/bin/env python3
"""Count each committed Iowa v2 draw's Democratic seats from the returns (D-043).

The draws file, ``docs/experiment-2/ia-draws-v2.csv.gz``, records each draw's
metrics but not its plan, so D-039 reads the seat count off the committed
|efficiency gap|. That reading cannot check itself: a plan that is not a sweep
can land where a sweep would. This script checks it by counting.

It regenerates every committed chain from its seed, exactly as
``tools/experiment_2_tradeoffs.py`` drew it, and measures each draw with that
script's own ``measure_plan``. A draw is counted only if it reproduces its
committed row: the integer columns exactly, and the others to within
:data:`FLOAT_TOLERANCE`. It then counts the draw's Democratic seats under both
contests from ``data/processed/ia_elections.csv``.

It writes ``docs/first-result/ia-seats-v2.csv.gz``, one row per committed draw,
and a sidecar recording what it read, only when every committed draw reproduces
and no district is tied. Otherwise it exits non-zero and writes nothing.
``tools/plot_seat_distribution.py`` checks its reading against these counts.

Run::

    python tools/recount_seats.py      # needs the data; about 25 minutes on 4 cores

It needs the Iowa data built (``tools/fetch_raw.sh ia``, VEST's ``ia_2020.shp``,
``tools/prepare_data.py``) and gerrychain as ``requirements.txt`` pins it. No
plan is kept: each is measured, counted and dropped. No vote count is written,
only seat counts.

Firewall: a ``tools/`` driver downstream of everything, like experiment 2, which
it imports. The sampler sees adjacency and population only, as it did there.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import experiment_2_tradeoffs as X      # noqa: E402
from evaluate import partisan as P      # noqa: E402
from generate import ensemble, seeds    # noqa: E402

STATE, ENSEMBLE = "IA", "v2"
CONTESTS = (X.PRIMARY_CONTEST, X.ALTERNATE_CONTEST)
OUT = ROOT / "docs" / "first-result" / "ia-seats-v2.csv.gz"
ELECTIONS = X.PROCESSED / "ia_elections.csv"
NEUTRAL = tuple(X.PROCESSED / f"ia_{name}" for name in
                ("units.gpkg", "units.csv", "adjacency.json"))

#: The committed columns that are counts, and must reproduce exactly.
INTEGER_COLUMNS = frozenset({"county_splits", "cut_edges", "population_spread",
                             *(f"competitive_districts@{c}" for c in CONTESTS)})
#: How far a committed float may sit from its regenerated value. Plans and vote
#: totals are integers; only the floats computed from them can move, and only
#: by rounding: a mean Polsby-Popper differs in its 17th significant digit
#: between machines whose geometry libraries sum in a different order.
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


def compare(measured: dict, record: dict) -> tuple[list[str], dict[str, float]]:
    """The columns of a committed row a regenerated draw does not reproduce,
    and each float column's absolute difference."""
    wrong, differences = [], {}
    for key, value in measured.items():
        if key in INTEGER_COLUMNS:
            if int(value) != int(record[key]):
                wrong.append(f"{key} {value} against {record[key]}")
        else:
            difference = abs(float(value) - float(record[key]))
            differences[key] = difference
            if not difference <= FLOAT_TOLERANCE:
                wrong.append(f"{key} {value!r} against {record[key]}")
    return wrong, differences


def recount_chain(work: tuple[int, int, list[dict]]) -> dict:
    """Regenerate one chain, check each draw against its row, count its seats.

    The committed rows lead the ``zip``, so the sampler is never asked for a
    draw past the last committed one: a chain that died did so on that step,
    after up to 100,000 attempts, and asking again would only repeat it.
    """
    index, seed, records = work
    spec = X.ensemble_spec(STATE, ENSEMBLE)
    expected = seeds.derive(X.MASTER_SEED, f"exp2-{spec.key.lower()}", index)
    if seed != expected:
        return {"index": index, "seed": seed, "seats": [], "differences": {},
                "seconds": 0.0, "failures": [
                    f"chain {index}: committed seed {seed}, but its index derives "
                    f"{expected}"]}
    ctx = X.load_context(spec, CONTESTS)
    seats: list[tuple[int, ...]] = []
    failures: list[str] = []
    differences: dict[str, float] = {}
    started = time.time()
    plans = ensemble.sample(ctx["adjacency"], ctx["pops"], spec.k, spec.epsilon,
                            spec.steps, seed, node_repeats=0)
    try:
        for draw, (record, plan) in enumerate(zip(records, plans)):
            if int(record["draw"]) != draw:
                failures.append(f"chain {index}: row {draw} is numbered {record['draw']}")
                break
            wrong, diffs = compare(X.measure_plan(plan, ctx), record)
            for key, value in diffs.items():
                differences[key] = max(differences.get(key, 0.0), value)
            counts = []
            for contest in CONTESTS:
                dem, rep = ctx["contests"][contest]
                dem_seats, _, tied = P.seat_counts(plan, dem, rep)
                if tied:
                    wrong.append(f"{tied} tied district(s) under {contest}")
                counts.append(dem_seats)
            if wrong:
                failures.append(f"chain {index} draw {draw}: " + "; ".join(wrong))
                if len(failures) >= MAX_FAILURES_PER_CHAIN:
                    break
            seats.append(tuple(counts))
    except Exception as exc:              # the sampler dying before the committed length
        failures.append(f"chain {index}: the sampler stopped at draw {len(seats)}: "
                        f"{type(exc).__name__}: {exc}")
    if not failures and len(seats) != len(records):
        failures.append(f"chain {index}: regenerated {len(seats)} draws of "
                        f"{len(records)} committed")
    return {"index": index, "seed": seed, "seats": seats, "failures": failures,
            "differences": differences, "seconds": time.time() - started}


def recount(jobs: int) -> tuple[dict[int, dict], list[str]]:
    """Every committed chain recounted, and every way it failed to reproduce."""
    rows, sidecar = committed()
    failures = []
    work = []
    for chain in sidecar["chains"]:
        got = len(rows.get(chain["index"], []))
        if got != chain["n_rows"]:
            failures.append(f"chain {chain['index']}: the sidecar records "
                            f"{chain['n_rows']} rows, the draws file {got}")
        elif got:
            work.append((chain["index"], chain["seed"], rows[chain["index"]]))
    work.sort(key=lambda w: -len(w[2]))       # longest first, so they overlap
    with ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
        results = {r["index"]: r for r in pool.map(recount_chain, work)}
    failures += [f for index in sorted(results) for f in results[index]["failures"]]
    return results, failures


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(results: dict[int, dict], out: Path) -> dict:
    """The seat counts, one row per committed draw, and a sidecar beside them."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with X._deterministic_gzip(out) as handle:
        writer = csv.writer(handle)
        writer.writerow(["chain_index", "draw", *(f"dem_seats@{c}" for c in CONTESTS)])
        for index in sorted(results):
            for draw, counts in enumerate(results[index]["seats"]):
                writer.writerow([index, draw, *counts])
    draws = X.draws_path("ia", ENSEMBLE)
    record = {
        "generated_by": "tools/recount_seats.py",
        "draws": str(draws.relative_to(ROOT)),
        "draws_sha256": sha256(draws),
        "config_digest": json.loads(X._sidecar_for(draws).read_text())["config_digest"],
        "elections_sha256": sha256(ELECTIONS),
        "contests": list(CONTESTS),
        "n_rows": sum(len(r["seats"]) for r in results.values()),
        "chains": [{"index": i, "seed": results[i]["seed"],
                    "n_rows": len(results[i]["seats"])} for i in sorted(results)],
        "integer_columns": sorted(INTEGER_COLUMNS),
        "float_tolerance": FLOAT_TOLERANCE,
        "largest_float_difference": {
            key: max(r["differences"].get(key, 0.0) for r in results.values())
            for key in sorted({k for r in results.values() for k in r["differences"]})},
        "tied_districts": 0,
    }
    out.with_name(out.name.replace(".csv.gz", ".json")).write_text(
        json.dumps(record, indent=2) + "\n")
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    missing = [str(p.relative_to(ROOT)) for p in (*NEUTRAL, ELECTIONS) if not p.exists()]
    if missing:
        print(f"refused: {', '.join(missing)} not built; see the README's "
              "'Getting the data'", file=sys.stderr)
        return 1
    results, failures = recount(args.jobs)
    for index in sorted(results):
        r = results[index]
        print(f"chain {index}: {len(r['seats'])} draws reproduced and counted, "
              f"{r['seconds']:.0f}s")
    if failures:
        for failure in failures:
            print("FAIL:", failure, file=sys.stderr)
        print(f"not written: {args.out} keeps the last record that passed",
              file=sys.stderr)
        return 1
    record = write(results, args.out)
    for c, contest in enumerate(CONTESTS):
        counts: dict[int, int] = {}
        for r in results.values():
            for seats in r["seats"]:
                counts[seats[c]] = counts.get(seats[c], 0) + 1
        print(f"{contest}: " + ", ".join(f"{s} D {n:,}" for s, n in sorted(counts.items())))
    print(f"wrote {args.out} ({record['n_rows']:,} draws); largest float difference "
          + ", ".join(f"{k} {v:.1e}" for k, v in record["largest_float_difference"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
