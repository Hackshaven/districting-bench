"""tools/recount_seats.py refuses every way a recount can go wrong, offline.

The recount itself needs the data and about 25 minutes, and its result is
committed: `docs/first-result/ia-seats-v2.csv.gz`, which
`tests/test_seat_distribution.py` checks the plotter's reading against on every
committed draw. These tests feed the script hand-built chains, so each way it
must refuse is exercised without the data: a draw that does not reproduce its
committed row, a tied district, a sampler that dies early, a seed its chain index
does not derive, and a run that fails and must write nothing. A check that cannot
fail is not a check (docs/RESEARCH-LOOP-PLAYBOOK.md section 4.2).

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

import recount_seats as R              # noqa: E402

#: Four units in two districts, and votes under which the Democrats win one
#: district of PLAN_A, both of PLAN_B, and tie one of TIED.
DEM = {"u1": 70, "u2": 60, "u3": 40, "u4": 45}
REP = {"u1": 30, "u2": 40, "u3": 60, "u4": 50}
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
               "contests": {c: (DEM, REP) for c in R.CONTESTS}}
    monkeypatch.setattr(R.X, "load_context", lambda spec, contests: context)

    def run(plans, measured=None, n=None, index=3, seed=None, die_at=None):
        n = len(plans) if n is None else n

        def sample(*args, **kwargs):
            for draw, plan in enumerate(plans):
                if draw == die_at:
                    raise RuntimeError("Could not find a possible cut")
                yield plan
            raise AssertionError("the sampler was asked past the last committed draw")
        monkeypatch.setattr(R.ensemble, "sample", sample)
        rows = iter(measured or [ROW] * len(plans))
        monkeypatch.setattr(R.X, "measure_plan", lambda plan, ctx: dict(next(rows)))
        return R.recount_chain((index, seed_of(index) if seed is None else seed,
                                records(n)))
    return run


def test_a_chain_that_reproduces_is_counted_and_the_sampler_goes_no_further(chain):
    result = chain([PLAN_A, PLAN_B, PLAN_A])
    assert result["failures"] == []
    assert result["seats"] == [(1, 1), (2, 2), (1, 1)]
    assert result["differences"]["polsby_popper_mean"] == 0.0
    # Two committed rows: the sampler's third plan is never asked for, which
    # is what keeps a chain that died on its next step from dying again here.
    result = chain([PLAN_A, PLAN_B, PLAN_A], n=2)
    assert (result["failures"], result["seats"]) == ([], [(1, 1), (2, 2)])


def test_a_draw_that_does_not_reproduce_its_row_refuses(chain):
    # Integers must match exactly; floats may move by rounding only.
    assert R.compare(ROW | {"polsby_popper_mean": 0.3 + 1e-13}, records(1)[0])[0] == []
    for changed in ({"cut_edges": 3}, {"competitive_districts@G20USS": 2},
                    {"polsby_popper_mean": 0.3 + 1e-11},
                    {"abs_efficiency_gap@G20PRE": 0.126}):
        result = chain([PLAN_A, PLAN_B], measured=[ROW, ROW | changed])
        key = next(iter(changed))
        assert len(result["failures"]) == 1
        assert result["failures"][0].startswith(f"chain 3 draw 1: {key} ")


def test_a_tie_a_dead_sampler_and_a_wrong_seed_refuse(chain):
    assert chain([PLAN_A, TIED])["failures"] == [
        "chain 3 draw 1: 1 tied district(s) under G20PRE; "
        "1 tied district(s) under G20USS"]
    died = chain([PLAN_A, PLAN_B], die_at=1)
    assert died["failures"] == ["chain 3: the sampler stopped at draw 1: "
                                "RuntimeError: Could not find a possible cut"]
    wrong = chain([PLAN_A], seed=seed_of(4))
    assert wrong["failures"] == [f"chain 3: committed seed {seed_of(4)}, but its index "
                                 f"derives {seed_of(3)}"]
    assert wrong["seats"] == []


def test_main_writes_only_when_every_draw_reproduces(monkeypatch, tmp_path, capsys):
    out = tmp_path / "ia-seats-v2.csv.gz"
    sidecar = tmp_path / "ia-seats-v2.json"
    # without the data, nothing is attempted
    monkeypatch.setattr(R, "NEUTRAL", (R.ROOT / "data" / "no-such-file",))
    assert R.main(["--out", str(out)]) == 1
    assert "refused" in capsys.readouterr().err and not out.exists()

    elections = tmp_path / "ia_elections.csv"
    elections.write_text("GEOID,G20PREDBID\n")
    monkeypatch.setattr(R, "NEUTRAL", (elections,))
    monkeypatch.setattr(R, "ELECTIONS", elections)
    good = {3: {"seed": seed_of(3), "seats": [(1, 1), (2, 2)], "failures": [],
                "differences": {"polsby_popper_mean": 5e-17}, "seconds": 1.0}}
    bad = {3: good[3] | {"failures": ["chain 3 draw 1: cut_edges 3 against 2"]}}
    monkeypatch.setattr(R, "recount", lambda jobs: (bad, bad[3]["failures"]))
    assert R.main(["--out", str(out)]) == 1
    assert "not written" in capsys.readouterr().err
    assert not out.exists() and not sidecar.exists()

    monkeypatch.setattr(R, "recount", lambda jobs: (good, []))
    assert R.main(["--out", str(out)]) == 0
    first = out.read_bytes()
    with gzip.open(out, "rt") as handle:
        assert handle.read().splitlines() == [
            "chain_index,draw,dem_seats@G20PRE,dem_seats@G20USS", "3,0,1,1", "3,1,2,2"]
    record = json.loads(sidecar.read_text())
    assert (record["n_rows"], record["chains"], record["tied_districts"]) == (
        2, [{"index": 3, "seed": seed_of(3), "n_rows": 2}], 0)
    assert record["largest_float_difference"] == {"polsby_popper_mean": 5e-17}
    # the bytes depend on the counts alone, so a rerun leaves no diff
    assert R.main(["--out", str(out)]) == 0
    assert out.read_bytes() == first
