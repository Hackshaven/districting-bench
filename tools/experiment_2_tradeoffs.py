"""Experiment 2 — the tradeoff frontier.

``prompt.md``: *"Stephanopoulos, Redistricting Without Tradeoffs, 126 Colum. L.
Rev. 1001 (2026), finds tradeoffs among criteria are generally weak to
nonexistent, using ~14 billion maps. Test on your states. One recent paper
against decades of contrary assumption — treat as hypothesis, not premise."*

``docs/CRITERIA.md`` section 5.5 marks the question ``EMPIRICAL`` and *"genuinely
open"*. This is a measurement, not an optimization loop: it runs once and reports
what it found.

What is measured
----------------
A neutral ReCom ensemble per state. For every draw, one scalar per criterion,
each with an explicit *direction* so that "goodness" always means larger. Then,
for every ordered pair (A, B), three independent tests of the claim *improving A
costs B*:

``correlation``
    Spearman rho between goodness(A) and goodness(B) over the pooled draws, with
    a chain-level block bootstrap. A tradeoff needs the whole 95% interval below
    ``-0.10`` — a point estimate that merely happens to be negative is not a
    finding at this sample size.

``conditional``
    Restrict to the best decile on A. Does the median goodness(B) fall relative
    to the full ensemble, by at least ``0.20`` robust SD, with a chain-level
    permutation test below 0.05? This is the test that matches how the criterion
    is actually used: a commission prioritising A does not sample the joint
    distribution, it takes the A-tail.

``achievability``
    Is the top tercile of A and the top tercile of B reachable *together*? Under
    independence 1/9 of draws land there. A tradeoff suppresses that rate; the
    test fires below half of it. This is the one test that can distinguish "no
    tradeoff" from "no variation", because it also reports whether the joint cell
    is populated at all.

Three tests rather than one because they fail differently, and because the
previous run of this experiment recorded that its "all three tests agree" was in
fact one test plus two quantities that could not have disagreed. :func:`controls`
is the fix: every test is run against a synthetic tradeoff, a synthetic
independence, and a synthetic synergy before any real data is touched, and the
run aborts if a test cannot produce the verdict it exists to produce.

Degenerate criteria
-------------------
A criterion that does not vary over the ensemble is reported ``degenerate`` and
never ``none``. Iowa's county-integrity criterion is identically zero by
construction (units are the counties, Iowa Code ch. 42; FEASIBILITY.md 5.3), and
scoring that as "no tradeoff with county integrity" would be a false negative
dressed as a finding.

Firewall
--------
This is a ``tools/`` driver, downstream of everything, and it reads partisan
data. It imports ``generate`` only for the sampler and the convergence
diagnostics — the same direction ``src/detect`` imports them. Nothing here is
imported by ``src/generate``.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from evaluate import compactness as C            # noqa: E402
from evaluate import elections as E              # noqa: E402
from evaluate import partisan as PA              # noqa: E402
from evaluate import plan as EP                  # noqa: E402
from evaluate import administrative as AD        # noqa: E402
from generate import convergence, ensemble, seeds, units as GU   # noqa: E402

PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "docs" / "experiment-2"

MASTER_SEED = 20260821

# --------------------------------------------------------------------------- #
# decision thresholds — stated here, not buried in the tests
# --------------------------------------------------------------------------- #

RHO_TRADEOFF = -0.10        # correlation test: upper CI bound must sit below this
DECILE = 0.10               # conditional test: "prioritising A" = best tenth
EFFECT_TRADEOFF = -0.20     # conditional test: robust-SD units
ALPHA = 0.05                # conditional test: permutation p
TERCILE = 1.0 / 3.0         # achievability test: "good on A" = best third
JOINT_SUPPRESSION = 0.5     # achievability: fires below half the independent rate
BOOTSTRAP = 1000
PERMUTATIONS = 1000


# --------------------------------------------------------------------------- #
# states
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class StateSpec:
    key: str
    prefix: str
    k: int
    epsilon: float
    chains: int
    steps: int
    #: how many leading GEOID characters name the county, or None when the units
    #: already *are* the counties and the criterion is degenerate by construction
    county_prefix_len: int | None


IOWA = StateSpec("IA", "ia", 4, 2e-4, 8, 1500, county_prefix_len=None)
COLORADO = StateSpec("CO", "co", 8, 1e-2, 8, 1000, county_prefix_len=5)
STATES = {"IA": IOWA, "CO": COLORADO}


# --------------------------------------------------------------------------- #
# criteria — the value choices, each one explicit and each one directional
# --------------------------------------------------------------------------- #

#: ``name -> (row key, +1 if larger is better, human-readable statement)``
CRITERIA: dict[str, tuple[str, int, str]] = {
    "compactness_pp": ("polsby_popper_mean", +1,
                       "mean Polsby-Popper over districts"),
    "compactness_cut": ("cut_edges", -1,
                        "cut edges on the rook graph"),
    "county_integrity": ("county_splits", -1,
                         "counties divided between districts"),
    "fairness_eg": ("abs_efficiency_gap", -1,
                    "|efficiency gap|, 2020 presidential two-party"),
    "fairness_mm": ("abs_mean_median", -1,
                    "|mean-median|, 2020 presidential two-party"),
    "competitiveness": ("competitive_districts", +1,
                        "districts inside 45-55% two-party D share"),
    "population_equality": ("population_spread", -1,
                            "max-min district population, persons"),
}


def goodness(rows: list[dict], name: str) -> list[float]:
    """The criterion's values re-signed so that larger is always better."""
    key, direction, _ = CRITERIA[name]
    return [direction * float(row[key]) for row in rows]


# --------------------------------------------------------------------------- #
# measurement
# --------------------------------------------------------------------------- #

@dataclass
class ChainResult:
    seed: int
    steps_requested: int
    rows: list[dict] = field(default_factory=list)
    failure: str | None = None

    @property
    def completed(self) -> bool:
        return self.failure is None and len(self.rows) == self.steps_requested


def measure_plan(plan, ctx) -> dict:
    """Every criterion's raw value for one draw."""
    shapes = C.measure_districts(plan, ctx["geom"], ctx["cache"])
    pp = list(shapes["polsby_popper"].values())

    dem, rep = ctx["dem"], ctx["rep"]
    shares = PA.district_shares(plan, dem, rep)
    competitive = sum(1 for s in shares.values() if 0.45 <= s <= 0.55)

    eg = PA.efficiency_gap(plan, dem, rep)
    mm = PA.mean_median(plan, dem, rep)

    totals = EP.aggregate(plan, ctx["pops"])
    spread = int(max(totals.values()) - min(totals.values()))

    if ctx["counties"] is None:
        splits = 0
    else:
        splits = AD.county_splits(plan, ctx["counties"])

    return {
        "polsby_popper_mean": sum(pp) / len(pp),
        "cut_edges": C.cut_edges(plan, ctx["adjacency"]),
        "county_splits": splits,
        "abs_efficiency_gap": abs(eg),
        "abs_mean_median": abs(mm),
        "competitive_districts": competitive,
        "population_spread": spread,
    }


def load_context(spec: StateSpec, contest: str) -> dict:
    geom = GU.load_geometry(PROCESSED / f"{spec.prefix}_units.gpkg")
    adjacency = GU.load_adjacency(PROCESSED / f"{spec.prefix}_adjacency.json")
    pops = EP.populations(PROCESSED / f"{spec.prefix}_units.csv")
    el = E.load_elections(PROCESSED / f"{spec.prefix}_elections.csv")
    dem_col, rep_col = E.two_party_columns(el, contest)
    dem, rep = E.two_party(el, dem_col, rep_col)

    counties = None
    if spec.county_prefix_len is not None:
        n = spec.county_prefix_len
        counties = {geoid: geoid[:n] for geoid in pops}

    return {
        "geom": geom,
        "adjacency": adjacency,
        "pops": pops,
        "dem": dem,
        "rep": rep,
        "counties": counties,
        "contest": contest,
        "columns": (dem_col, rep_col),
        "cache": C.MeasureCache(maxsize=1 << 15),
    }


def measure_ensemble(spec: StateSpec, ctx: dict, *, log=print) -> list[ChainResult]:
    """One ReCom chain per derived seed, measured draw by draw.

    Metrics are computed as the chain runs and the plans are dropped, so a chain
    is never truncated to fit memory. The previous run of this experiment
    reported convergence over 216 of 36,784 draws because a driver had truncated
    every chain to the shortest survivor's length; here each chain keeps its own
    full trace and :func:`diagnostics` says exactly how many draws it used.
    """
    results: list[ChainResult] = []
    chain_seeds = seeds.stream(MASTER_SEED, f"exp2-{spec.key.lower()}", spec.chains)
    for index, seed in enumerate(chain_seeds):
        started = time.time()
        result = ChainResult(seed=seed, steps_requested=spec.steps)
        try:
            for plan in ensemble.sample(
                ctx["adjacency"], ctx["pops"], spec.k, spec.epsilon,
                spec.steps, seed, node_repeats=0,
            ):
                result.rows.append(measure_plan(plan, ctx))
        except Exception as exc:                  # a chain dying is expected
            result.failure = f"{type(exc).__name__}: {exc}"
        results.append(result)
        log(f"  chain {index} seed={seed} draws={len(result.rows)} "
            f"failure={result.failure} {time.time() - started:.0f}s")
    return results


def diagnostics(chains: list[ChainResult]) -> dict:
    """Split R-hat and ESS over the completed chains, at their full length.

    Reports the sample it used. ``truncate`` still equalises chain lengths — the
    statistic needs a rectangle — but over *completed* chains that is a no-op,
    and the draw count is reported either way so a reader never has to assume it.
    """
    completed = [c for c in chains if c.completed]
    out: dict = {
        "sample": "completed_chains",
        "n_chains": len(completed),
        "n_draws_per_chain": [len(c.rows) for c in completed],
        "n_draws_total": sum(len(c.rows) for c in completed),
        "metrics": {},
    }
    if len(completed) < 2:
        out["note"] = "fewer than two completed chains; no diagnostic possible"
        return out
    for name in ("compactness_cut", "fairness_eg", "population_equality"):
        key, _, _ = CRITERIA[name]
        series = [[float(row[key]) for row in c.rows] for c in completed]
        equal = convergence.truncate(series)
        out["metrics"][name] = {
            "split_rhat": convergence.split_rhat(equal),
            "ess": convergence.ess(equal),
            "n_draws_used": len(equal) * len(equal[0]),
        }
    return out


# --------------------------------------------------------------------------- #
# the three tests
# --------------------------------------------------------------------------- #

def _robust_sd(values: list[float]) -> float:
    """MAD rescaled to a normal SD. Zero when the quantity does not vary."""
    if not values:
        return 0.0
    centre = median(values)
    return 1.4826 * median([abs(v - centre) for v in values])


def _varies(values: list[float]) -> bool:
    return len(set(values)) > 1


def _blocks(a: list[list[float]], b: list[list[float]], rng: random.Random):
    """Resample whole chains with replacement, returning pooled (a, b)."""
    picks = [rng.randrange(len(a)) for _ in range(len(a))]
    xs = [v for i in picks for v in a[i]]
    ys = [v for i in picks for v in b[i]]
    return xs, ys


def test_correlation(a_chains, b_chains, rng: random.Random) -> dict:
    """Spearman rho with a chain-level block bootstrap."""
    xs = [v for chain in a_chains for v in chain]
    ys = [v for chain in b_chains for v in chain]
    if not (_varies(xs) and _varies(ys)):
        return {"verdict": "degenerate", "rho": None,
                "reason": "one side does not vary over the ensemble"}
    rho = C.spearman(xs, ys)
    draws = []
    for _ in range(BOOTSTRAP):
        bx, by = _blocks(a_chains, b_chains, rng)
        if _varies(bx) and _varies(by):
            draws.append(C.spearman(bx, by))
    draws.sort()
    if len(draws) < BOOTSTRAP // 2:
        return {"verdict": "degenerate", "rho": rho,
                "reason": "bootstrap resamples were mostly constant"}
    lo = draws[int(0.025 * len(draws))]
    hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
    return {
        "verdict": "tradeoff" if hi < RHO_TRADEOFF else "none",
        "rho": rho, "ci_low": lo, "ci_high": hi,
        "threshold": RHO_TRADEOFF, "n_chains": len(a_chains), "n_draws": len(xs),
    }


def _circular_shift(chain: list[float], offset: int) -> list[float]:
    n = len(chain)
    offset %= n
    return chain[offset:] + chain[:offset]


def _conditional_effect(xs, ys, scale) -> tuple[float, float, int]:
    """Median goodness(B) in the best decile of A, as a robust-SD shift."""
    order = sorted(range(len(xs)), key=lambda i: xs[i], reverse=True)
    cut = max(1, int(round(DECILE * len(xs))))
    top = [ys[i] for i in order[:cut]]
    shift = median(top) - median(ys)
    return shift / scale, median(top), cut


def test_conditional(a_chains, b_chains, rng: random.Random) -> dict:
    """Does B degrade in the best decile of A? Permutation test over chains."""
    xs = [v for chain in a_chains for v in chain]
    ys = [v for chain in b_chains for v in chain]
    if not (_varies(xs) and _varies(ys)):
        return {"verdict": "degenerate", "effect": None,
                "reason": "one side does not vary over the ensemble"}
    scale = _robust_sd(ys)
    if scale == 0.0:
        return {"verdict": "degenerate", "effect": None,
                "reason": "goodness(B) has zero robust spread"}
    effect, top_median, cut = _conditional_effect(xs, ys, scale)

    worse = 0
    for _ in range(PERMUTATIONS):
        shifted = [
            _circular_shift(chain, rng.randrange(len(chain))) if len(chain) > 1
            else chain
            for chain in a_chains
        ]
        px = [v for chain in shifted for v in chain]
        null_effect, _, _ = _conditional_effect(px, ys, scale)
        if null_effect <= effect:
            worse += 1
    p = (worse + 1) / (PERMUTATIONS + 1)
    fires = effect <= EFFECT_TRADEOFF and p < ALPHA
    return {
        "verdict": "tradeoff" if fires else "none",
        "effect": effect, "p": p, "decile_n": cut,
        "top_decile_median": top_median, "ensemble_median": median(ys),
        "robust_sd": scale,
        "thresholds": {"effect": EFFECT_TRADEOFF, "alpha": ALPHA},
    }


def _quantile(sorted_xs: list[float], q: float) -> float:
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    pos = q * (len(sorted_xs) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_xs[int(pos)]
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


def test_achievability(a_chains, b_chains, _rng) -> dict:
    """Can the top third of A and the top third of B be had at once?"""
    xs = [v for chain in a_chains for v in chain]
    ys = [v for chain in b_chains for v in chain]
    if not (_varies(xs) and _varies(ys)):
        return {"verdict": "degenerate", "joint_rate": None,
                "reason": "one side does not vary over the ensemble"}
    ax = _quantile(sorted(xs), 1 - TERCILE)
    ay = _quantile(sorted(ys), 1 - TERCILE)
    good_x = [x >= ax for x in xs]
    good_y = [y >= ay for y in ys]
    joint = sum(1 for gx, gy in zip(good_x, good_y) if gx and gy)
    rate = joint / len(xs)
    # the marginals are not exactly 1/3 when the criterion is discrete
    expected = (sum(good_x) / len(xs)) * (sum(good_y) / len(ys))
    fires = expected > 0 and rate < JOINT_SUPPRESSION * expected
    return {
        "verdict": "tradeoff" if fires else "none",
        "joint_rate": rate, "expected_if_independent": expected,
        "ratio": (rate / expected) if expected else None,
        "n_joint": joint, "n_draws": len(xs),
        "threshold_ratio": JOINT_SUPPRESSION,
        "populated": joint > 0,
    }


TESTS = {
    "correlation": test_correlation,
    "conditional": test_conditional,
    "achievability": test_achievability,
}


def pareto_size(a_chains, b_chains) -> dict:
    """How many draws are non-dominated on (goodness A, goodness B).

    A real tradeoff makes the frontier long: many maps, each better on one
    criterion and worse on the other. A frontier that collapses toward a single
    point means one plan is close to best on both, which is what "no tradeoff"
    looks like geometrically.
    """
    xs = [v for chain in a_chains for v in chain]
    ys = [v for chain in b_chains for v in chain]
    points = sorted(set(zip(xs, ys)), key=lambda p: (-p[0], -p[1]))
    frontier = []
    best_y = -math.inf
    for x, y in points:
        if y > best_y:
            frontier.append((x, y))
            best_y = y
    return {
        "n_distinct_points": len(points),
        "n_frontier": len(frontier),
        "frontier_fraction": len(frontier) / len(points) if points else None,
        "best_a": max(xs), "best_b": max(ys),
        "b_at_best_a": max(y for x, y in zip(xs, ys) if x == max(xs)),
        "a_at_best_b": max(x for x, y in zip(xs, ys) if y == max(ys)),
    }


def evaluate_pair(rows_by_chain, a: str, b: str, rng: random.Random) -> dict:
    a_chains = [goodness(rows, a) for rows in rows_by_chain]
    b_chains = [goodness(rows, b) for rows in rows_by_chain]
    results = {name: fn(a_chains, b_chains, rng) for name, fn in TESTS.items()}
    verdicts = [r["verdict"] for r in results.values()]
    if all(v == "degenerate" for v in verdicts):
        overall = "degenerate"
    elif any(v == "degenerate" for v in verdicts):
        overall = "degenerate"
    else:
        votes = sum(1 for v in verdicts if v == "tradeoff")
        overall = {0: "none", 1: "weak", 2: "weak", 3: "strong"}[votes]
    return {
        "a": a, "b": b, "verdict": overall,
        "votes": sum(1 for v in verdicts if v == "tradeoff"),
        "tests": results,
        "pareto": (pareto_size(a_chains, b_chains)
                   if overall != "degenerate" else None),
    }


# --------------------------------------------------------------------------- #
# controls — every test must be able to say both words
# --------------------------------------------------------------------------- #

def _synthetic(kind: str, rng: random.Random, chains=8, steps=400):
    """AR(1) chains shaped like an ensemble, with a known joint structure."""
    phi = 0.9
    a_chains, b_chains = [], []
    for _ in range(chains):
        a, b = [], []
        xa = rng.gauss(0, 1)
        noise = rng.gauss(0, 1)
        for _ in range(steps):
            xa = phi * xa + math.sqrt(1 - phi * phi) * rng.gauss(0, 1)
            noise = phi * noise + math.sqrt(1 - phi * phi) * rng.gauss(0, 1)
            a.append(xa)
            if kind == "tradeoff":
                b.append(-xa + 0.3 * noise)
            elif kind == "synergy":
                b.append(xa + 0.3 * noise)
            elif kind == "independent":
                b.append(noise)
            else:                                  # pragma: no cover
                raise ValueError(kind)
        a_chains.append(a)
        b_chains.append(b)
    return a_chains, b_chains


#: what each test must return on each synthetic structure
CONTROL_EXPECTATIONS = {
    "tradeoff": "tradeoff",
    "independent": "none",
    "synergy": "none",
}


def controls(seed: int = MASTER_SEED) -> dict:
    """Run every test against known structures; raise if one cannot decide.

    This exists because the previous run of this experiment reported that "all
    three deciding tests agree" when two of the three could not have voted no.
    A test that cannot produce both verdicts is not evidence, and a run that
    proceeds on one is reporting its own defaults as a finding.
    """
    report: dict = {}
    for kind, expected in CONTROL_EXPECTATIONS.items():
        rng = random.Random(seed + hash(kind) % 10_000)
        a, b = _synthetic(kind, rng)
        got = {name: fn(a, b, rng)["verdict"] for name, fn in TESTS.items()}
        report[kind] = {"expected": expected, "got": got}
        for name, verdict in got.items():
            if verdict != expected:
                raise AssertionError(
                    f"control failed: on synthetic {kind!r} data the {name!r} "
                    f"test returned {verdict!r}, expected {expected!r}. The "
                    f"instrument cannot be trusted to report a tradeoff, so the "
                    f"experiment is not run."
                )
    report["conclusion"] = (
        "each of the three tests returned 'tradeoff' on synthetic tradeoff data "
        "and 'none' on both independent and synergistic data, so each can "
        "produce either verdict and none is a constant"
    )
    return report


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #

def run_state(spec: StateSpec, contest: str, *, log=print) -> dict:
    log(f"[{spec.key}] loading")
    ctx = load_context(spec, contest)
    log(f"[{spec.key}] sampling {spec.chains} chains x {spec.steps} steps, "
        f"k={spec.k}, epsilon={spec.epsilon}")
    chains = measure_ensemble(spec, ctx, log=log)

    completed = [c for c in chains if c.completed]
    rows_by_chain = [c.rows for c in completed]
    if len(rows_by_chain) < 2:
        raise RuntimeError(
            f"{spec.key}: only {len(rows_by_chain)} chains completed; "
            f"the chain-level bootstrap and permutation tests need at least two"
        )

    all_rows = [row for rows in rows_by_chain for row in rows]
    varying, degenerate = [], {}
    for name, (key, _, _) in CRITERIA.items():
        values = [row[key] for row in all_rows]
        if len(set(values)) > 1:
            varying.append(name)
        else:
            degenerate[name] = {
                "constant_value": values[0],
                "reason": ("units are the subdivisions, so no plan over them can "
                           "split one" if name == "county_integrity"
                           else "did not vary over this ensemble"),
            }

    rng = random.Random(MASTER_SEED + 7)
    pairs = []
    for i, a in enumerate(varying):
        for b in varying[i + 1:]:
            pairs.append(evaluate_pair(rows_by_chain, a, b, rng))
            pairs.append(evaluate_pair(rows_by_chain, b, a, rng))
            log(f"  {a} x {b}: {pairs[-2]['verdict']} / {pairs[-1]['verdict']}")

    return {
        "state": spec.key,
        "config": {
            "k": spec.k, "epsilon": spec.epsilon, "chains": spec.chains,
            "steps": spec.steps, "master_seed": MASTER_SEED, "node_repeats": 0,
            "contest": contest, "columns": list(ctx["columns"]),
            "county_prefix_len": spec.county_prefix_len,
        },
        "ensemble": {
            "n_requested": spec.chains * spec.steps,
            "n_completed_draws": sum(len(c.rows) for c in chains),
            "chain_failures": sum(1 for c in chains if not c.completed),
            "failure_rate": sum(1 for c in chains if not c.completed) / len(chains),
            "chains": [
                {"seed": c.seed, "draws": len(c.rows), "failure": c.failure,
                 "completed": c.completed}
                for c in chains
            ],
            "analysis_sample": {
                "sample": "completed_chains",
                "n_chains": len(rows_by_chain),
                "n_draws": len(all_rows),
            },
        },
        "convergence": diagnostics(chains),
        "criteria": {
            "varying": varying,
            "degenerate": degenerate,
            "definitions": {n: {"direction": d, "statement": s}
                            for n, (_, d, s) in CRITERIA.items()},
        },
        "pairs": pairs,
        "summary": {
            v: [f"{p['a']} -> {p['b']}" for p in pairs if p["verdict"] == v]
            for v in ("strong", "weak", "none")
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", action="append", choices=sorted(STATES),
                        help="repeatable; default is both")
    parser.add_argument("--contest", default="G20PRE")
    parser.add_argument("--out", default=str(OUT / "experiment-2-results.json"))
    parser.add_argument("--controls-only", action="store_true")
    args = parser.parse_args(argv)

    control_report = controls()
    print("controls: every test can return both verdicts")
    if args.controls_only:
        print(json.dumps(control_report, indent=2))
        return 0

    keys = args.state or sorted(STATES)
    results = {"master_seed": MASTER_SEED, "controls": control_report, "states": {}}
    for key in keys:
        results["states"][key] = run_state(STATES[key], args.contest)

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, default=str))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
