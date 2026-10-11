"""tools/recount_seats.py refuses every way a recount can go wrong, offline.

The recount itself needs the data and about 25 minutes, and its result is
committed: `docs/first-result/ia-seats-v2.csv.gz`, which
`tests/test_seat_distribution.py` checks the plotter's reading against on every
committed draw. These tests feed the script hand-built chains, so each way it
must refuse is exercised without the data: a draw that does not reproduce its
committed row, a tied district, a sampler that dies or stops early, a seed its
chain index does not derive, a draws file and sidecar that disagree, returns
whose totals are not the certified ones, and a run that fails and must write
nothing. A check that cannot fail is not a check
(docs/RESEARCH-LOOP-PLAYBOOK.md section 4.2).

No data and no network.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import plot_seat_distribution as S    # noqa: E402
import recount_seats as R              # noqa: E402

#: Four units in two districts. Under the presidential votes the Democrats win
#: one district of PLAN_A, both of PLAN_B, and tie one of TIED; under the Senate
#: votes they win none of PLAN_A and one of PLAN_B, so a count that swaps the
#: contests, or counts both with one contest's votes, comes out different.
DEM = {"u1": 70, "u2": 60, "u3": 40, "u4": 45}
REP = {"u1": 30, "u2": 40, "u3": 60, "u4": 50}
SENATE_DEM = {"u1": 65, "u2": 30, "u3": 45, "u4": 40}
SENATE_REP = {"u1": 35, "u2": 70, "u3": 55, "u4": 60}
PLAN_A = {"u1": 1, "u2": 1, "u3": 2, "u4": 2}
PLAN_B = {"u1": 1, "u2": 2, "u3": 1, "u4": 2}
TIED = {"u1": 1, "u2": 2, "u3": 2, "u4": 1}

#: What each plan's committed row holds, every column the draws file carries.
ROW = {"abs_efficiency_gap@G20PRE": 0.125, "abs_efficiency_gap@G20USS": 0.125,
       "abs_mean_median@G20PRE": 0.0625, "abs_mean_median@G20USS": 0.0625,
       "competitive_districts@G20PRE": 1, "competitive_districts@G20USS": 1,
       "county_splits": 0, "cut_edges": 2, "polsby_popper_mean": 0.3,
       "population_spread": 5}


def seed_of(index: int) -> int:
    return R.seeds.derive(R.X.MASTER_SEED, "exp2-ia", index)


def records(n: int) -> list[dict]:
    """``n`` committed rows, as the draws file's reader returns them: strings."""
    return [{"draw": str(d), **{k: repr(v) for k, v in ROW.items()}} for d in range(n)]


@pytest.fixture
def chain(monkeypatch):
    """Patch the context, sampler and measurement; return a runner for one chain."""
    context = {"adjacency": {}, "pops": {},
               "contests": {"G20PRE": (DEM, REP), "G20USS": (SENATE_DEM, SENATE_REP)}}
    monkeypatch.setattr(R.X, "load_context", lambda spec, contests: context)

    def run(plans, measured=None, n=None, index=3, seed=None, die_at=None, rows=None):
        n = len(plans) if n is None else n

        def sample(*args, **kwargs):
            for draw, plan in enumerate(plans):
                if draw == die_at:
                    raise RuntimeError("Could not find a possible cut")
                yield plan
            if len(plans) >= n:
                raise AssertionError("the sampler was asked past the last committed draw")
        monkeypatch.setattr(R.ensemble, "sample", sample)
        rows_ = iter(measured or [ROW] * len(plans))
        monkeypatch.setattr(R.X, "measure_plan", lambda plan, ctx: dict(next(rows_)))
        return R.recount_chain((index, seed_of(index) if seed is None else seed,
                                records(n) if rows is None else rows))
    return run


def test_a_chain_that_reproduces_is_counted_and_the_sampler_goes_no_further(chain):
    result = chain([PLAN_A, PLAN_B, PLAN_A])
    assert result["failures"] == []
    # (presidential, Senate), in that order
    assert result["seats"] == [(1, 0), (2, 1), (1, 0)]
    assert result["plans"] == [R.plan_key(PLAN_A), R.plan_key(PLAN_B), R.plan_key(PLAN_A)]
    assert result["differences"]["polsby_popper_mean"] == 0.0
    # Two committed rows: the sampler's third plan is never asked for, which
    # is what keeps a chain that died on its next step from dying again here.
    result = chain([PLAN_A, PLAN_B, PLAN_A], n=2)
    assert (result["failures"], result["seats"]) == ([], [(1, 0), (2, 1)])


def test_a_draw_that_does_not_reproduce_its_row_refuses(chain):
    # Integers must match exactly; floats may move by rounding only, either way.
    assert R.compare(ROW | {"polsby_popper_mean": 0.3 + 1e-13}, records(1)[0])[0] == []
    assert R.compare(ROW | {"polsby_popper_mean": 0.3 - 1e-13}, records(1)[0])[0] == []
    for changed in ({"cut_edges": 3}, {"cut_edges": 1},
                    {"competitive_districts@G20USS": 2},
                    {"polsby_popper_mean": 0.3 + 1e-11},
                    {"polsby_popper_mean": 0.3 - 1e-11},
                    {"abs_efficiency_gap@G20PRE": 0.126},
                    {"abs_mean_median@G20USS": 0.0624},
                    {"abs_efficiency_gap@G20USS": float("nan")}):
        result = chain([PLAN_A, PLAN_B], measured=[ROW, ROW | changed])
        key = next(iter(changed))
        assert len(result["failures"]) == 1
        assert result["failures"][0].startswith(f"chain 3 draw 1: {key} ")


def test_a_column_measured_or_committed_alone_refuses():
    # A column dropped from measuring would otherwise go unchecked.
    dropped = {k: v for k, v in ROW.items() if k != "polsby_popper_mean"}
    wrong, _ = R.compare(dropped, records(1)[0])
    assert wrong == ["measured columns differ from the committed ones by "
                     "['polsby_popper_mean']"]
    wrong, _ = R.compare(ROW | {"reock_mean": 0.4}, records(1)[0])
    assert wrong == ["measured columns differ from the committed ones by ['reock_mean']"]


def test_the_largest_difference_is_kept_not_the_last(chain):
    result = chain([PLAN_A, PLAN_B, PLAN_A],
                   measured=[ROW | {"polsby_popper_mean": 0.3 + 4e-13},
                             ROW | {"polsby_popper_mean": 0.3 - 9e-13},
                             ROW | {"polsby_popper_mean": 0.3 + 1e-13}])
    assert result["failures"] == []
    # approx's default absolute tolerance, 1e-12, would pass the last difference
    assert result["differences"]["polsby_popper_mean"] == pytest.approx(9e-13, abs=1e-15)


def test_a_tie_a_dead_sampler_and_a_wrong_seed_refuse(chain):
    assert chain([PLAN_A, TIED])["failures"] == [
        "chain 3 draw 1: 1 tied district(s) under G20PRE"]
    died = chain([PLAN_A, PLAN_B], die_at=1)
    assert died["failures"] == ["chain 3: the sampler failed at draw 1: "
                                "RuntimeError: Could not find a possible cut"]
    stopped = chain([PLAN_A], n=2)
    assert stopped["failures"] == ["chain 3: the sampler stopped after 1 of 2 "
                                   "committed draws"]
    wrong = chain([PLAN_A], seed=seed_of(4))
    assert wrong["failures"] == [f"chain 3: committed seed {seed_of(4)}, but its index "
                                 f"derives {seed_of(3)}"]
    assert wrong["seats"] == []


def test_rows_out_of_order_and_a_defect_in_measuring_refuse(chain, monkeypatch):
    rows = records(3)
    rows[1], rows[2] = rows[2], rows[1]
    assert chain([PLAN_A, PLAN_B, PLAN_A], rows=rows)["failures"] == [
        "chain 3: row 1 is numbered 2"]
    # a measuring error is named as one, not blamed on the sampler
    rows = [{k: v for k, v in r.items() if k != "cut_edges"} for r in records(1)]
    result = chain([PLAN_A], rows=rows)
    assert result["failures"] == [
        "chain 3 draw 0: measured columns differ from the committed ones by "
        "['cut_edges']"]

    def broken(plan, ctx):
        raise KeyError("geometry")
    assert chain([PLAN_A])["failures"] == []     # the sampler, patched for one draw
    monkeypatch.setattr(R.X, "measure_plan", broken)
    result = R.recount_chain((3, seed_of(3), records(1)))
    assert result["failures"] == ["chain 3 draw 0: could not be measured: "
                                  "KeyError: 'geometry'"]


def test_a_plan_key_ignores_district_numbers_and_nothing_else():
    renumbered = {u: 3 - d for u, d in PLAN_A.items()}
    assert R.plan_key(renumbered) == R.plan_key(PLAN_A)
    assert R.plan_key({u: f"d{d}" for u, d in PLAN_A.items()}) == R.plan_key(PLAN_A)
    assert len({R.plan_key(p) for p in (PLAN_A, PLAN_B, TIED)}) == 3
    assert len(R.plan_key(PLAN_A)) == 16 and int(R.plan_key(PLAN_A), 16) >= 0


def test_the_draws_file_and_its_sidecar_must_agree():
    spec = R.X.ensemble_spec("IA", "v2")
    sidecar = {"config_digest": R.X.config_digest(spec),
               "chains": [{"index": 3, "seed": seed_of(3), "n_rows": 2},
                          {"index": 4, "seed": seed_of(4), "n_rows": 0},
                          {"index": 5, "seed": seed_of(5), "n_rows": 1}]}
    rows = {3: records(2), 5: records(1)}
    work, failures = R.work_list(rows, sidecar)
    assert failures == []
    # longest first, and a chain with no rows is never sent to the sampler
    assert [(i, s, len(r)) for i, s, r in work] == [(3, seed_of(3), 2), (5, seed_of(5), 1)]
    _, failures = R.work_list({3: records(2), 5: records(2)}, sidecar)
    assert failures == ["chain 5: the sidecar records 1 rows, the draws file 2"]
    _, failures = R.work_list(rows | {12: records(1)}, sidecar)
    assert failures == ["the draws file holds chains [12] the sidecar does not list"]
    twice = sidecar | {"chains": sidecar["chains"] + sidecar["chains"][:1]}
    assert R.work_list(rows, twice)[1][0].startswith("the sidecar lists a chain twice")
    _, failures = R.work_list(rows, sidecar | {"config_digest": "0" * 16})
    assert failures == [f"the draws were made under configuration {'0' * 16}, "
                        f"not {R.X.config_digest(spec)}"]


def test_the_returns_must_total_the_certified_votes(tmp_path):
    assert R.CERTIFIED == S.TWO_PARTY
    path = tmp_path / "ia_elections.csv"
    path.write_text("GEOID,G20PREDBID,G20PRERTRU,G20USSDGRE,G20USSRERN\n"
                    "19001,759061,897672,754859,864997\n")
    assert R.check_totals(path) == []
    path.write_text("GEOID,G20PREDBID,G20PRERTRU,G20USSDGRE,G20USSRERN\n"
                    "19001,759061,897672,864997,754859\n")
    assert R.check_totals(path) == [
        "G20USS: the returns total (864997, 754859) (D, R), not the certified "
        "(754859, 864997)"]


def test_a_failed_check_stops_the_run_before_any_chain(monkeypatch):
    def no_pool(*args, **kwargs):
        raise AssertionError("no chain may be regenerated")
    monkeypatch.setattr(R, "ProcessPoolExecutor", no_pool)
    monkeypatch.setattr(R, "check_totals", lambda: ["G20PRE: wrong"])
    monkeypatch.setattr(R, "committed", lambda: ({}, {}))
    monkeypatch.setattr(R, "work_list", lambda rows, sidecar: ([], ["chain 5: short"]))
    assert R.recount(1) == ({}, ["G20PRE: wrong", "chain 5: short"])


def test_a_write_that_fails_part_way_leaves_the_last_record(tmp_path):
    path = tmp_path / "ia-seats-v2.csv.gz"
    path.write_bytes(b"the last record that passed")

    def fails(temporary):
        temporary.write_bytes(b"half a rec")
        raise OSError("disk full")
    with pytest.raises(OSError, match="disk full"):
        R._write_atomically(path, fails)
    assert path.read_bytes() == b"the last record that passed"
    assert [p.name for p in tmp_path.iterdir()] == [path.name]


def test_main_writes_only_when_every_draw_reproduces(monkeypatch, tmp_path, capsys):
    out = tmp_path / "ia-seats-v2.csv.gz"
    sidecar = tmp_path / "ia-seats-v2.json"
    # without the data, nothing is attempted
    monkeypatch.setattr(R, "NEUTRAL", (R.ROOT / "data" / "no-such-file",))
    assert R.main(["--out", str(out)]) == 1
    assert "refused" in capsys.readouterr().err and not out.exists()
    # a name its sidecar would overwrite is refused before anything runs
    for name in ("seats.csv", "seats.gz", "seats.json"):
        assert R.main(["--out", str(tmp_path / name)]) == 1
        assert "must name a .csv.gz file" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []

    elections = tmp_path / "ia_elections.csv"
    elections.write_text("GEOID,G20PREDBID\n")
    zipped = tmp_path / "ia_2020.zip"
    zipped.write_bytes(b"not VEST's zip")
    monkeypatch.setattr(R, "NEUTRAL", (elections,))
    monkeypatch.setattr(R, "ELECTIONS", elections)
    monkeypatch.setattr(R, "VEST", (zipped, tmp_path / "ia_2020.dbf"))
    good = {5: {"seed": seed_of(5), "seats": [(2, 1)], "plans": ["b" * 16],
                "failures": [], "differences": {"polsby_popper_mean": 1e-17},
                "seconds": 1.0},
            3: {"seed": seed_of(3), "seats": [(1, 0), (2, 1)],
                "plans": ["a" * 16, "a" * 16], "failures": [],
                "differences": {"polsby_popper_mean": 5e-17}, "seconds": 1.0}}
    bad = {3: good[3] | {"failures": ["chain 3 draw 1: cut_edges 3 against 2"]}}
    monkeypatch.setattr(R, "recount", lambda jobs: (bad, bad[3]["failures"]))
    assert R.main(["--out", str(out)]) == 1
    assert "not written" in capsys.readouterr().err
    assert not out.exists() and not sidecar.exists()

    monkeypatch.setattr(R, "recount", lambda jobs: (good, []))
    assert R.main(["--out", str(out)]) == 0
    assert "2 distinct plans" in capsys.readouterr().out
    first = out.read_bytes()
    with gzip.open(out, "rt") as handle:
        # chains in index order, each draw's seats under (presidential, Senate)
        assert handle.read().splitlines() == [
            "chain_index,draw,plan,dem_seats@G20PRE,dem_seats@G20USS",
            f"3,0,{'a' * 16},1,0", f"3,1,{'a' * 16},2,1", f"5,0,{'b' * 16},2,1"]
    record = json.loads(sidecar.read_text())
    spec = R.X.ensemble_spec("IA", "v2")
    listed = json.loads(R.X._sidecar_for(R.X.draws_path("ia", "v2")).read_text())["chains"]
    assert record["n_rows"] == 3
    # every chain the draws sidecar lists, those with no rows included
    assert record["chains"] == [{"index": c["index"], "seed": c["seed"],
                                 "n_rows": {3: 2, 5: 1}.get(c["index"], 0)}
                                for c in listed]
    assert record["config_digest"] == R.X.config_digest(spec)
    assert record["certified_two_party_totals"] == {
        c: list(t) for c, t in R.CERTIFIED.items()}
    assert record["largest_float_difference"] == {"polsby_popper_mean": 5e-17}
    assert record["inputs_sha256"] == {str(elections): R.digest(elections)}
    # a zip that is not the one D-043 names is hashed, and not named as it
    assert record["returns_source"] is None
    assert record["vest"] == {str(zipped): {"md5": R.digest(zipped, "md5")}}
    assert "tied_districts" not in record
    # the bytes depend on the counts alone, so a rerun leaves no diff, and no
    # temporary file is left beside them
    assert R.main(["--out", str(out)]) == 0
    assert out.read_bytes() == first
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [out.name, sidecar.name, elections.name, zipped.name])
