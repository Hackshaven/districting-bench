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
import csv
import gzip
import hashlib
import io
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


IOWA = StateSpec("IA", "ia", 4, 2e-4, 12, 1500, county_prefix_len=None)
COLORADO = StateSpec("CO", "co", 8, 1e-2, 8, 1000, county_prefix_len=5)
STATES = {"IA": IOWA, "CO": COLORADO}


# --------------------------------------------------------------------------- #
# criteria — the value choices, each one explicit and each one directional
# --------------------------------------------------------------------------- #

#: The contest whose partisan metrics the headline verdicts use. Every partisan
#: criterion is also measured on :data:`ALTERNATE_CONTEST` and the whole pair
#: analysis is re-run against it, because docs/progress.md records "one election"
#: as the first limitation of Experiment 3 and a finding that flips when the
#: office changes is a finding about the office.
PRIMARY_CONTEST = "G20PRE"
ALTERNATE_CONTEST = "G20USS"

#: ``name -> (row key, +1 if larger is better, human-readable statement)``.
#: A key containing ``@`` is contest-dependent and is bound by
#: :func:`criteria_for`; the rest are the same whatever the election.
CRITERIA: dict[str, tuple[str, int, str]] = {
    "compactness_pp": ("polsby_popper_mean", +1,
                       "mean Polsby-Popper over districts"),
    "compactness_cut": ("cut_edges", -1,
                        "cut edges on the rook graph"),
    "county_integrity": ("county_splits", -1,
                         "counties divided between districts"),
    "fairness_eg": ("abs_efficiency_gap@", -1,
                    "|efficiency gap|, two-party"),
    "fairness_mm": ("abs_mean_median@", -1,
                    "|mean-median|, two-party"),
    "competitiveness": ("competitive_districts@", +1,
                        "districts inside 45-55% two-party D share"),
    "population_equality": ("population_spread", -1,
                            "max-min district population, persons"),
}

#: Criteria whose value depends on which election is used.
PARTISAN_CRITERIA = tuple(
    name for name, (key, _, _) in CRITERIA.items() if key.endswith("@")
)


def criteria_for(contest: str) -> dict[str, tuple[str, int, str]]:
    """:data:`CRITERIA` with the contest-dependent row keys bound to ``contest``."""
    return {
        name: (key + contest if key.endswith("@") else key, direction, statement)
        for name, (key, direction, statement) in CRITERIA.items()
    }


def goodness(rows: list[dict], name: str,
             criteria: dict[str, tuple[str, int, str]] | None = None) -> list[float]:
    """The criterion's values re-signed so that larger is always better."""
    key, direction, _ = (criteria or criteria_for(PRIMARY_CONTEST))[name]
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

    partisan: dict[str, float] = {}
    for contest, (dem, rep) in ctx["contests"].items():
        shares = PA.district_shares(plan, dem, rep)
        partisan[f"competitive_districts@{contest}"] = sum(
            1 for s in shares.values() if 0.45 <= s <= 0.55
        )
        partisan[f"abs_efficiency_gap@{contest}"] = abs(
            PA.efficiency_gap(plan, dem, rep)
        )
        partisan[f"abs_mean_median@{contest}"] = abs(PA.mean_median(plan, dem, rep))

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
        "population_spread": spread,
        **partisan,
    }


def load_context(spec: StateSpec, contests: tuple[str, ...]) -> dict:
    geom = GU.load_geometry(PROCESSED / f"{spec.prefix}_units.gpkg")
    adjacency = GU.load_adjacency(PROCESSED / f"{spec.prefix}_adjacency.json")
    pops = EP.populations(PROCESSED / f"{spec.prefix}_units.csv")
    el = E.load_elections(PROCESSED / f"{spec.prefix}_elections.csv")
    votes, columns = {}, {}
    for contest in contests:
        dem_col, rep_col = E.two_party_columns(el, contest)
        votes[contest] = E.two_party(el, dem_col, rep_col)
        columns[contest] = [dem_col, rep_col]

    counties = None
    if spec.county_prefix_len is not None:
        n = spec.county_prefix_len
        counties = {geoid: geoid[:n] for geoid in pops}

    return {
        "geom": geom,
        "adjacency": adjacency,
        "pops": pops,
        "contests": votes,
        "counties": counties,
        "columns": columns,
        "cache": C.MeasureCache(maxsize=1 << 15),
    }


def _deterministic_gzip(path: Path):
    """A gzip writer whose bytes depend only on the data written.

    ``gzip`` stamps the wall clock *and* the source filename into its header, so
    an unchanged artifact re-written by an identical run produces a different
    file and a spurious diff. The reason for committing these draws is that a
    reader can check them without re-sampling, which requires the bytes to be a
    function of the data alone. ``gzip.open`` exposes neither field, so the
    ``GzipFile`` is built directly with both pinned.
    """
    raw = open(path, "wb")
    binary = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    return io.TextIOWrapper(binary, newline="", write_through=True)


def config_digest(spec: StateSpec) -> str:
    """Identity of the sampling configuration a checkpoint belongs to.

    A checkpoint is only reusable if it was produced by the same chain, in the
    same state, at the same k, epsilon and length, from the same master seed. If
    any of those change the cached rows describe a different ensemble, and
    silently reusing them would be the worst kind of stale result -- one that
    looks like a fresh run.
    """
    payload = json.dumps(
        {"state": spec.key, "k": spec.k, "epsilon": spec.epsilon,
         "steps": spec.steps, "master_seed": MASTER_SEED,
         "contests": [PRIMARY_CONTEST, ALTERNATE_CONTEST],
         "county_prefix_len": spec.county_prefix_len,
         "criteria": sorted(CRITERIA)},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def checkpoint_path(spec: StateSpec, index: int, root: Path) -> Path:
    return root / f"{spec.prefix}-chain-{index:02d}-{config_digest(spec)}.json.gz"


def save_checkpoint(spec: StateSpec, index: int, result: "ChainResult",
                    root: Path) -> Path:
    """Persist one finished chain, so a container restart costs one chain.

    This run has now been killed three times by the environment reclaiming its
    container mid-sample. Chains are independent by construction -- each is
    seeded from generate.seeds.derive(master_seed, purpose, index) and knows
    nothing about the others -- so a chain is the natural unit to checkpoint,
    and resuming from them is not an approximation of the un-interrupted run.
    It is the same run.
    """
    path = checkpoint_path(spec, index, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    with _deterministic_gzip(tmp) as handle:
        json.dump({"index": index, "seed": result.seed,
                   "steps_requested": result.steps_requested,
                   "failure": result.failure, "rows": result.rows}, handle)
    tmp.replace(path)      # atomic: a half-written file is never a checkpoint
    return path


def load_checkpoint(spec: StateSpec, index: int, root: Path):
    path = checkpoint_path(spec, index, root)
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt") as handle:
            data = json.load(handle)
    except (OSError, EOFError, json.JSONDecodeError):
        return None
    expected = seeds.derive(MASTER_SEED, f"exp2-{spec.key.lower()}", index)
    if data.get("seed") != expected:
        return None
    return ChainResult(seed=data["seed"],
                       steps_requested=data["steps_requested"],
                       rows=data["rows"], failure=data["failure"])


def run_one_chain(args) -> tuple[int, "ChainResult", float]:
    """Sample and measure one chain. Top level so it can be sent to a worker."""
    spec, index, contests = args
    ctx = load_context(spec, contests)
    seed = seeds.derive(MASTER_SEED, f"exp2-{spec.key.lower()}", index)
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
    return index, result, time.time() - started


def measure_ensemble(spec: StateSpec, ctx: dict, *, log=print, jobs: int = 1,
                     checkpoints: Path | None = None) -> list[ChainResult]:
    """One ReCom chain per derived seed, measured draw by draw.

    Metrics are computed as the chain runs and the plans are dropped, so a chain
    is never truncated to fit memory. The previous run of this experiment
    reported convergence over 216 of 36,784 draws because a driver had truncated
    every chain to the shortest survivor's length; here each chain keeps its own
    full trace and :func:`diagnostics` says exactly how many draws it used.

    Chains are independent, so they are run in parallel when ``jobs > 1`` and
    each is checkpointed as it finishes. Neither changes the result: a chain's
    seed comes from its index, not from execution order, so the ensemble is the
    same whatever order the chains complete in and whichever of them were
    restored from disk.
    """
    results: dict[int, ChainResult] = {}
    pending: list[int] = []
    for index in range(spec.chains):
        cached = load_checkpoint(spec, index, checkpoints) if checkpoints else None
        if cached is not None:
            results[index] = cached
            log(f"  chain {index} restored from checkpoint "
                f"draws={len(cached.rows)} failure={cached.failure}")
        else:
            pending.append(index)

    def finish(index: int, result: ChainResult, seconds: float) -> None:
        results[index] = result
        if checkpoints:
            save_checkpoint(spec, index, result, checkpoints)
        log(f"  chain {index} seed={result.seed} draws={len(result.rows)} "
            f"failure={result.failure} {seconds:.0f}s")

    contests = (PRIMARY_CONTEST, ALTERNATE_CONTEST)
    if jobs > 1 and pending:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=min(jobs, len(pending))) as pool:
            for index, result, seconds in pool.map(
                run_one_chain, [(spec, i, contests) for i in pending]
            ):
                finish(index, result, seconds)
    else:
        for index in pending:
            finish(*run_one_chain((spec, index, contests)))

    return [results[i] for i in range(spec.chains)]


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
    bound = criteria_for(PRIMARY_CONTEST)
    for name in ("compactness_cut", "fairness_eg", "population_equality"):
        key, _, _ = bound[name]
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
    """MAD rescaled to a normal SD, falling back to the plain SD.

    The MAD is preferred because a handful of extreme draws should not set the
    scale an effect size is measured against. But several criteria here are
    small integers -- competitiveness is a count of districts, county splits is
    a count of counties -- and when more than half the ensemble sits on the
    median the MAD is exactly zero while the criterion is plainly varying.
    Reporting that pair as degenerate would be a false negative caused by the
    choice of scale estimator, so the plain SD is used instead and only a
    genuinely constant criterion returns zero.
    """
    if not values:
        return 0.0
    centre = median(values)
    mad = 1.4826 * median([abs(v - centre) for v in values])
    if mad > 0:
        return mad
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


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
    """Median goodness(B) in the best decile of A, as a robust-SD shift.

    The decile is **tie-inclusive**: every draw whose A-goodness ties the decile
    boundary is in, so the selection is a property of the values and not of the
    order the draws happen to sit in.

    Taking the first ``cut`` of a descending sort instead -- the obvious way to
    write this, and how it was written -- breaks ties by position in the file.
    Three of Colorado's thirty-nine null verdicts flipped to ``tradeoff`` under a
    relabelling of the eight exchangeable chains, which carries no information
    whatsoever: `competitiveness -> compactness_cut` moved between -0.016 and
    -0.455 across eight orderings and fired in three of them. Many criteria here
    are small integers, so ties are the normal case rather than an edge case, and
    the permutation null cannot detect the problem because ``_circular_shift``
    preserves each chain's multiset and so reproduces the same tie structure on
    every replicate. :func:`test_achievability` already used ``>=``; this makes
    the two agree.
    """
    cut = max(1, int(round(DECILE * len(xs))))
    boundary = sorted(xs, reverse=True)[cut - 1]
    top = [y for x, y in zip(xs, ys) if x >= boundary]
    shift = median(top) - median(ys)
    return shift / scale, median(top), len(top)


def _attainable_effect(xs, ys, scale) -> float:
    """The most negative effect ANY ordering of A could produce for this B.

    Achieved by handing the decile the worst possible draws of B. If even that
    cannot reach :data:`EFFECT_TRADEOFF`, no arrangement of A can make the
    conditional test fire, and the test must abstain rather than return "none".

    This is not hypothetical. On the Iowa ensemble, ``competitiveness`` under the
    presidential contest has its median at the bottom of its attainable range --
    more than half the draws sit on the minimum -- so the worst decile's median
    equals the ensemble median and the best attainable effect is exactly +0.000,
    against a firing threshold of -0.20. The test was a proven constant on that
    column and reported ``none`` five times in Iowa's shipped results, each time
    inside a pair claiming ``n_deciding: 3``. That is the same defect the controls
    were written to prevent, recurring in the one regime the controls -- which
    generate only continuous Gaussian data -- never exercise.
    """
    cut = max(1, int(round(DECILE * len(xs))))
    worst = sorted(ys)[:cut]
    return (median(worst) - median(ys)) / scale


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

    attainable = _attainable_effect(xs, ys, scale)
    if attainable > EFFECT_TRADEOFF:
        return {"verdict": "degenerate", "effect": None,
                "attainable_effect": attainable,
                "reason": (f"no ordering of this criterion could reach the "
                           f"firing threshold: the worst possible decile of "
                           f"goodness(B) shifts its median by {attainable:+.3f} "
                           f"robust SD against a threshold of "
                           f"{EFFECT_TRADEOFF}, because goodness(B) is coarse "
                           f"enough that its median does not move")}

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
        "attainable_effect": attainable,
        "top_decile_median": top_median, "ensemble_median": median(ys),
        "robust_sd": scale,
        "thresholds": {"effect": EFFECT_TRADEOFF, "alpha": ALPHA},
        # The effect is NOT a comparable magnitude across pairs: a criterion
        # whose ensemble median sits on a mode boundary steps discontinuously as
        # dependence increases (Iowa's efficiency gap moved from -0.00 to -4.95
        # between two adjacent injected dependence levels). Read fired/not-fired.
        "effect_is_comparable": False,
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


def evaluate_pair(rows_by_chain, a: str, b: str, rng: random.Random,
                  criteria=None) -> dict:
    criteria = criteria or criteria_for(PRIMARY_CONTEST)
    a_chains = [goodness(rows, a, criteria) for rows in rows_by_chain]
    b_chains = [goodness(rows, b, criteria) for rows in rows_by_chain]
    results = {name: fn(a_chains, b_chains, rng) for name, fn in TESTS.items()}
    verdicts = {name: r["verdict"] for name, r in results.items()}
    deciding = [name for name, v in verdicts.items() if v != "degenerate"]
    votes = sum(1 for v in verdicts.values() if v == "tradeoff")

    # A test that cannot decide is not a vote against a tradeoff, and it is not
    # a reason to discard the tests that could. But "strong" is a claim that
    # three independent tests agreed, so it is unavailable when fewer than three
    # were able to answer.
    if not deciding:
        overall = "degenerate"
    elif votes == 0:
        overall = "none"
    elif len(deciding) == len(results) and votes == len(results):
        overall = "strong"
    else:
        overall = "weak"

    return {
        "a": a, "b": b, "verdict": overall, "votes": votes,
        "n_deciding": len(deciding),
        "partial": 0 < len(deciding) < len(results),
        "degenerate_tests": [name for name, v in verdicts.items()
                             if v == "degenerate"],
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
            elif kind == "discrete_tradeoff":
                # A perfect tradeoff, then B quantised onto the real frequencies
                # of Iowa's competitiveness column under the presidential
                # contest: most of the mass on the lowest of three levels, so the
                # median sits at the bottom of the range. See _attainable_effect.
                b.append(-xa)
            else:                                  # pragma: no cover
                raise ValueError(kind)
        a_chains.append(a)
        b_chains.append(b)

    if kind == "discrete_tradeoff":
        b_chains = _quantise(b_chains, DISCRETE_CONTROL_LEVELS)
    return a_chains, b_chains


#: ``(value, cumulative share)`` -- the real shape of a coarse criterion. Taken
#: from Iowa's ``competitive_districts@G20PRE``, where 62% of draws sit on the
#: lowest of three attainable values. A control arm that does not reproduce this
#: shape cannot exercise the regime in which the conditional test was a constant.
DISCRETE_CONTROL_LEVELS = ((0.0, 0.62), (1.0, 0.93), (2.0, 1.0))


def _quantise(chains, levels):
    """Map continuous chains onto discrete levels at the given cumulative shares."""
    pooled = sorted(v for chain in chains for v in chain)
    cuts = [(_quantile(pooled, share), value) for value, share in levels]

    def bucket(v):
        for edge, value in cuts:
            if v <= edge:
                return value
        return cuts[-1][1]

    return [[bucket(v) for v in chain] for chain in chains]


#: What each test must return on each synthetic structure. ``None`` means "any
#: verdict except ``none``": on data carrying a perfect tradeoff a test may
#: detect it or abstain, but it may not deny it, and which of those is right
#: depends on whether the effect is attainable for that test at all.
CONTROL_EXPECTATIONS: dict[str, str | None] = {
    "tradeoff": "tradeoff",
    "independent": "none",
    "synergy": "none",
    # The regime the original controls never generated. Every test here saw only
    # continuous Gaussian AR(1) data, so none of them was ever exercised against
    # a criterion taking three values -- which is what competitiveness and county
    # splits actually are. The conditional test returns "none" on a *perfect*
    # tradeoff in this regime; with the attainability guard it abstains instead.
    "discrete_tradeoff": None,
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
        report[kind] = {"expected": expected or "anything but 'none'", "got": got}
        for name, verdict in got.items():
            ok = (verdict != "none") if expected is None else (verdict == expected)
            if not ok:
                raise AssertionError(
                    f"control failed: on synthetic {kind!r} data the {name!r} "
                    f"test returned {verdict!r}, expected "
                    f"{expected or 'anything but none'}. The instrument cannot "
                    f"be trusted to report a tradeoff, so the experiment is not "
                    f"run."
                )
    report["conclusion"] = (
        "each of the three tests returned 'tradeoff' on synthetic tradeoff data "
        "and 'none' on both independent and synergistic data, so each can "
        "produce either verdict and none is a constant; and on a perfect "
        "tradeoff between a continuous criterion and a three-valued one, no test "
        "denied it -- the regime in which the conditional test was previously a "
        "proven constant"
    )
    return report


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# symmetry, multiplicity, and the instrument's own detection floor
# --------------------------------------------------------------------------- #

#: Tests whose statistic is mathematically symmetric in (A, B). Spearman rho is
#: symmetric by definition; the joint top-tercile rate and its independence
#: expectation are both symmetric in the two indicator sets. Only the conditional
#: test is directional -- it conditions on A's decile and measures B.
SYMMETRIC_TESTS = ("correlation", "achievability")


def check_symmetry(pairs: list[dict]) -> dict:
    """Verify empirically that the symmetric tests really are symmetric.

    This matters for how the result is *counted*. Reporting 42 ordered pairs
    invites a reader to treat them as 42 findings when two of the three tests
    cannot distinguish direction at all; Colorado has 21 relationships, not 42,
    and every directional disagreement in the matrix is produced by the single
    test that carries every defect the audit found. The claim is checked here
    rather than asserted, because a silent asymmetry would mean one of the two
    is not the statistic it is documented to be.
    """
    index = {(p["a"], p["b"]): p for p in pairs}
    mismatches, seen = [], set()
    for (a, b), pair in index.items():
        other = index.get((b, a))
        if other is None or tuple(sorted((a, b))) in seen:
            continue
        seen.add(tuple(sorted((a, b))))
        for name in SYMMETRIC_TESTS:
            if pair["tests"][name]["verdict"] != other["tests"][name]["verdict"]:
                mismatches.append({"pair": f"{a} <-> {b}", "test": name})
    return {
        "symmetric_tests": list(SYMMETRIC_TESTS),
        "directional_tests": ["conditional"],
        "n_checked": len(seen),
        "n_direction_dependent": len(mismatches),
        "mismatches": mismatches,
        "note": ("a non-zero count means a test documented as symmetric is not, "
                 "which would be a defect in that test rather than a finding"),
    }


def relationships(pairs: list[dict]) -> dict:
    """Collapse ordered pairs to unordered relationships.

    The headline count is over relationships. Direction is reported where it
    exists -- only the conditional test can produce it -- and a relationship whose
    two directions disagree is labelled as such rather than counted twice.
    """
    index = {(p["a"], p["b"]): p for p in pairs}
    seen, out = set(), []
    for (a, b), pair in index.items():
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        other = index.get((b, a))
        verdicts = [pair["verdict"]] + ([other["verdict"]] if other else [])
        out.append({
            "relationship": f"{key[0]} <-> {key[1]}",
            "verdict": ("strong" if all(v == "strong" for v in verdicts)
                        else "none" if all(v == "none" for v in verdicts)
                        else "degenerate" if all(v == "degenerate" for v in verdicts)
                        else "weak"),
            "directions": {f"{p['a']} -> {p['b']}": p["verdict"]
                           for p in (pair, other) if p},
            "direction_dependent": len(set(verdicts)) > 1,
        })
    counts: dict[str, int] = {}
    for r in out:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {
        "n_relationships": len(out),
        "counts": counts,
        "n_direction_dependent": sum(1 for r in out if r["direction_dependent"]),
        "direction_comes_only_from": "conditional",
        "relationships": out,
    }


def adjust_multiplicity(pairs: list[dict]) -> dict:
    """Benjamini-Hochberg across every conditional permutation test.

    Each state runs one permutation test per ordered pair per contest at
    alpha=0.05 with no correction, which under a global null produces false
    firings of the same order as the reported signal. The adjusted q-value is
    added to each pair and the verdict is recomputed from it; the raw p is kept
    so the correction is visible rather than silently applied.
    """
    live = [p for p in pairs
            if p["tests"]["conditional"].get("p") is not None]
    ranked = sorted(live, key=lambda p: p["tests"]["conditional"]["p"])
    n = len(ranked)
    running = 1.0
    for rank in range(n, 0, -1):
        pair = ranked[rank - 1]
        raw = pair["tests"]["conditional"]["p"]
        running = min(running, raw * n / rank)
        pair["tests"]["conditional"]["q_value"] = running
        pair["tests"]["conditional"]["fires_after_correction"] = (
            running < ALPHA
            and pair["tests"]["conditional"]["effect"] <= EFFECT_TRADEOFF
        )
    changed = [p for p in ranked
               if (p["tests"]["conditional"]["verdict"] == "tradeoff")
               != p["tests"]["conditional"]["fires_after_correction"]]
    return {
        "method": "Benjamini-Hochberg",
        "n_tests": n,
        "alpha": ALPHA,
        "n_verdicts_changed": len(changed),
        "changed": [f"{p['a']} -> {p['b']}" for p in changed],
    }


#: Noise weights swept when measuring the instrument's detection floor. The grid
#: must reach far enough at BOTH ends: 0 gives the strongest dependence the
#: marginals permit, and the large values must push the achieved rho close enough
#: to zero that every test has stopped firing, or the floor is merely "somewhere
#: below the weakest thing tried".
CALIBRATION_BLEND = (0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0)


def _inject(a_chains, b_chains, blend: float, rng: random.Random):
    """Re-pair B against A to induce anti-monotone dependence of a given strength.

    Each chain keeps its own multiset of B values exactly -- only the pairing
    changes -- so the marginals, the discreteness and the between-chain
    heterogeneity of the real ensemble are all preserved. ``blend`` is the weight
    on noise: 0 gives a perfect within-chain reversal, large values give
    independence.
    """
    out = []
    for a, b in zip(a_chains, b_chains):
        n = len(a)
        ranks = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: a[i]))}
        keys = [ranks[i] + blend * n * rng.random() for i in range(n)]
        order = sorted(range(n), key=lambda i: keys[i])
        values = sorted(b, reverse=True)      # best B to lowest-A slot
        paired = [0.0] * n
        for slot, i in enumerate(order):
            paired[i] = values[slot]
        out.append(paired)
    return a_chains, out


def detection_floor(rows_by_chain, a: str, b: str, criteria,
                    rng: random.Random, *, log=print) -> dict:
    """The weakest tradeoff this instrument can see, measured on the real draws.

    Without this number a null verdict is uninterpretable: "no tradeoff" and "no
    tradeoff my tests could resolve" are different claims and the artifact has to
    say which one it is making. Dependence of known strength is injected into the
    real ensemble, marginals held exact, and each test's firing threshold is read
    off in units of the achieved Spearman rho.
    """
    a_chains = [goodness(rows, a, criteria) for rows in rows_by_chain]
    b_chains = [goodness(rows, b, criteria) for rows in rows_by_chain]

    points = []
    for blend in CALIBRATION_BLEND:
        xs, ys = _inject(a_chains, b_chains, blend, random.Random(hash(blend) % 99991))
        flat_x = [v for c in xs for v in c]
        flat_y = [v for c in ys for v in c]
        rho = C.spearman(flat_x, flat_y)
        fired = {name: fn(xs, ys, rng)["verdict"] for name, fn in TESTS.items()}
        points.append({"blend": blend, "achieved_rho": rho, "verdicts": fired,
                       "any_fired": any(v == "tradeoff" for v in fired.values())})
        log(f"    calibration {a} x {b} blend={blend:<5} rho={rho:+.3f} "
            f"{ {k: v[:4] for k, v in fired.items()} }")

    # The strongest dependence the marginals permit. For a criterion taking three
    # values against a continuous one this can be small, and when it is, "the
    # test never fired" says nothing about the test -- no tradeoff of detectable
    # strength is even expressible in that pairing. The two cases are reported
    # separately because conflating them is exactly the error this block exists
    # to prevent.
    max_attainable = max(abs(p["achieved_rho"]) for p in points)

    def bracket(predicate):
        """(strongest that did not fire, weakest that did) -- the floor is between."""
        fired = [abs(p["achieved_rho"]) for p in points if predicate(p)]
        quiet = [abs(p["achieved_rho"]) for p in points if not predicate(p)]
        if not fired:
            return {"fires": False,
                    "reason": ("never fired at any injected strength; the "
                               "strongest dependence these marginals permit is "
                               f"|rho|={max_attainable:.3f}"
                               + (", which is itself below any plausible "
                                  "detection threshold, so this is a limit of "
                                  "the criterion's coarseness rather than of the "
                                  "test" if max_attainable < 0.2 else ""))}
        weakest_fired = min(fired)
        below = [q for q in quiet if q < weakest_fired]
        return {"fires": True,
                "weakest_detected_rho": weakest_fired,
                "strongest_missed_rho": max(below) if below else None,
                "monotone": not any(q > weakest_fired for q in quiet)}

    return {
        "pair": f"{a} x {b}",
        "method": ("anti-monotone re-pairing within each chain at a range of "
                   "noise levels; each chain's B multiset is preserved exactly, "
                   "so only the pairing changes"),
        "max_attainable_rho": max_attainable,
        "points": points,
        "floor_any_test": bracket(lambda p: p["any_fired"]),
        "floor_by_test": {
            name: bracket(lambda p, n=name: p["verdicts"][n] == "tradeoff")
            for name in TESTS
        },
        "interpretation": (
            "a 'none' verdict on this state means: no monotone tradeoff stronger "
            "than about this |rho|. It is not a claim about weaker dependence, "
            "nor about non-monotone dependence, which no test here can see, nor "
            "about a tradeoff confined to the frontier."
        ),
    }


def analyse(rows_by_chain, contest: str, *, log=print) -> dict:
    """Every ordered pair of varying criteria, under one election's metrics.

    Called twice per state -- once for :data:`PRIMARY_CONTEST` and once for
    :data:`ALTERNATE_CONTEST` -- over the *same* draws. The ensemble is neutral
    and knows nothing about either election, so re-scoring it costs no sampling
    and answers a question a single-election run cannot: whether a verdict is
    about the state's geography or about one office's returns.
    """
    criteria = criteria_for(contest)
    all_rows = [row for rows in rows_by_chain for row in rows]

    varying, degenerate = [], {}
    for name, (key, _, _) in criteria.items():
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

    # One RNG seeded per contest, so the primary run's numbers do not depend on
    # whether a replication happens to run before or after it.
    rng = random.Random(MASTER_SEED + 7 + sum(contest.encode()))
    pairs = []
    for i, a in enumerate(varying):
        for b in varying[i + 1:]:
            pairs.append(evaluate_pair(rows_by_chain, a, b, rng, criteria))
            pairs.append(evaluate_pair(rows_by_chain, b, a, rng, criteria))
            log(f"  [{contest}] {a} x {b}: "
                f"{pairs[-2]['verdict']} / {pairs[-1]['verdict']}")

    multiplicity = adjust_multiplicity(pairs)

    return {
        "contest": contest,
        "criteria": {
            "varying": varying,
            "degenerate": degenerate,
            "definitions": {n: {"row_key": k, "direction": d, "statement": s}
                            for n, (k, d, s) in criteria.items()},
        },
        "pairs": pairs,
        "symmetry": check_symmetry(pairs),
        "relationships": relationships(pairs),
        "multiplicity": multiplicity,
        "summary": {
            v: [f"{p['a']} -> {p['b']}" for p in pairs if p["verdict"] == v]
            for v in ("strong", "weak", "none", "degenerate")
        },
    }


def compare_contests(primary: dict, replication: dict) -> dict:
    """Where the two elections disagree about a pair. This is the robustness check."""
    index = {(p["a"], p["b"]): p["verdict"] for p in replication["pairs"]}
    agree, differ = [], []
    for pair in primary["pairs"]:
        key = (pair["a"], pair["b"])
        other = index.get(key)
        record = {"pair": f"{pair['a']} -> {pair['b']}",
                  primary["contest"]: pair["verdict"],
                  replication["contest"]: other}
        (agree if other == pair["verdict"] else differ).append(record)
    return {
        "n_pairs_compared": len(primary["pairs"]),
        "n_agree": len(agree),
        "n_differ": len(differ),
        "disagreements": differ,
        "note": ("a pair only present under one contest is counted as a "
                 "disagreement, since a criterion that goes degenerate under a "
                 "different election is itself a finding about the criterion"),
    }


def chains_from_draws(spec: StateSpec, path: Path) -> list[ChainResult]:
    """Rebuild the chain results from a committed draws file.

    The draws file holds every measured value for every draw, so the entire
    analysis can be re-derived from it without sampling. That matters for two
    reasons. A reader checking a verdict should not need an hour of CPU and a
    working GerryChain to do it -- the committed CSV plus this path is the whole
    computation. And this environment reclaims its container roughly every two
    hours, which has now destroyed four long runs; an analysis that reads a
    committed file cannot be killed halfway through anything expensive.

    Failed chains are carried through with their failure strings, so the failure
    rate and the analysis sample are the same as in the run that produced the
    file.
    """
    keys = sorted({key for contest in (PRIMARY_CONTEST, ALTERNATE_CONTEST)
                   for key, _, _ in criteria_for(contest).values()})
    rows: dict[int, list[dict]] = {}
    meta: dict[int, tuple[int, bool]] = {}
    with gzip.open(path, "rt", newline="") as handle:
        for record in csv.DictReader(handle):
            index = int(record["chain_index"])
            rows.setdefault(index, []).append(
                {key: float(record[key]) for key in keys})
            meta[index] = (int(record["chain_seed"]),
                           record["chain_completed"] == "1")

    # Recover chains that produced no rows at all from the sidecar, if present.
    sidecar = path.with_name(path.name.replace("-draws.csv.gz", "-chains.json"))
    empty: dict[int, dict] = {}
    if sidecar.exists():
        for record in json.loads(sidecar.read_text())["chains"]:
            empty[record["index"]] = record
            if record["n_rows"] == 0:
                rows.setdefault(record["index"], [])
                meta[record["index"]] = (record["seed"], record["completed"])

    out = []
    for index in sorted(rows):
        seed, completed = meta[index]
        expected = seeds.derive(MASTER_SEED, f"exp2-{spec.key.lower()}", index)
        if seed != expected:
            raise ValueError(
                f"{path}: chain {index} carries seed {seed}, but this "
                f"configuration derives {expected}. The file was produced by a "
                f"different run and re-analysing it would silently mix ensembles."
            )
        # Completion is READ from the file, not re-derived from the row count.
        # The file records what the run actually did; recomputing it here would
        # let a truncated or partially written file quietly re-describe a
        # completed chain as a failed one, which would change the failure rate
        # -- a reported result in its own right (ARCHITECTURE.md section 7).
        recorded = empty.get(index, {}).get("n_rows")
        if recorded is not None and recorded != len(rows[index]):
            raise ValueError(
                f"{path}: chain {index} holds {len(rows[index])} rows but the "
                f"sidecar records {recorded}. One of the two files is stale."
            )
        out.append(ChainResult(
            seed=seed, rows=rows[index],
            steps_requested=len(rows[index]) if completed else spec.steps,
            failure=None if completed else "recorded in the draws file as failed",
        ))
    return out


def run_state(spec: StateSpec, *, log=print, jobs: int = 1,
              checkpoints: Path | None = None,
              draws: Path | None = None) -> dict:
    if draws is not None:
        log(f"[{spec.key}] re-analysing {draws} without sampling")
        chains = chains_from_draws(spec, draws)
        return _analyse_chains(spec, chains, log=log)
    log(f"[{spec.key}] loading")
    ctx = load_context(spec, (PRIMARY_CONTEST, ALTERNATE_CONTEST))
    log(f"[{spec.key}] sampling {spec.chains} chains x {spec.steps} steps, "
        f"k={spec.k}, epsilon={spec.epsilon}, jobs={jobs}, "
        f"config={config_digest(spec)}")
    chains = measure_ensemble(spec, ctx, log=log, jobs=jobs,
                              checkpoints=checkpoints)
    return _analyse_chains(spec, chains, log=log)


def election_columns(spec: StateSpec) -> dict[str, list[str]]:
    """The ``(dem, rep)`` column pair backing each contest, for the record.

    Read from the election table rather than carried through from the sampling
    context, so the re-analysis path records exactly what the sampling path does.
    """
    el = E.load_elections(PROCESSED / f"{spec.prefix}_elections.csv")
    return {contest: list(E.two_party_columns(el, contest))
            for contest in (PRIMARY_CONTEST, ALTERNATE_CONTEST)}


def _analyse_chains(spec: StateSpec, chains: list[ChainResult], *, log=print):
    """Everything downstream of the draws. Identical whether they were just
    sampled or read back from the committed file."""

    completed = [c for c in chains if c.completed]
    rows_by_chain = [c.rows for c in completed]
    if len(rows_by_chain) < 2:
        raise RuntimeError(
            f"{spec.key}: only {len(rows_by_chain)} chains completed; "
            f"the chain-level bootstrap and permutation tests need at least two"
        )

    analysis = analyse(rows_by_chain, PRIMARY_CONTEST, log=log)
    replication = analyse(rows_by_chain, ALTERNATE_CONTEST, log=log)
    pairs = analysis["pairs"]
    all_rows = [row for rows in rows_by_chain for row in rows]

    # What a "none" on this state actually means. Measured on a continuous pair
    # and on a coarse one, because the audit found the floor is higher when the
    # costed criterion takes few values.
    log(f"[{spec.key}] measuring the detection floor")
    criteria = criteria_for(PRIMARY_CONTEST)
    floor_rng = random.Random(MASTER_SEED + 11)
    floors = [
        detection_floor(rows_by_chain, "compactness_pp", "fairness_mm",
                        criteria, floor_rng, log=log),
        detection_floor(rows_by_chain, "compactness_pp", "competitiveness",
                        criteria, floor_rng, log=log),
    ]

    report = {
        "state": spec.key,
        "config": {
            "k": spec.k, "epsilon": spec.epsilon, "chains": spec.chains,
            "steps": spec.steps, "master_seed": MASTER_SEED, "node_repeats": 0,
            "primary_contest": PRIMARY_CONTEST,
            "alternate_contest": ALTERNATE_CONTEST,
            "columns": election_columns(spec),
            "county_prefix_len": spec.county_prefix_len,
            "config_digest": config_digest(spec),
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
        "criteria": analysis["criteria"],
        "pairs": pairs,
        "symmetry": analysis["symmetry"],
        "relationships": analysis["relationships"],
        "multiplicity": analysis["multiplicity"],
        "detection_floor": floors,
        "summary": analysis["summary"],
        "replication": replication,
        "contest_agreement": compare_contests(analysis, replication),
    }
    return report, chains


def write_rows(spec: StateSpec, chains: list[ChainResult], path: Path) -> dict:
    """Every measured draw, so the finding can be re-derived without re-sampling.

    ReCom is deterministic given a seed, but a reader who wants to check a
    percentile should not have to spend an hour of CPU to do it, and
    docs/progress.md already records that Experiment 3's plots and plan CSVs
    were left in a scratch directory that no longer exists. Dead chains are
    written too, marked, because the failure rate is itself a sampling bias
    (ARCHITECTURE.md section 7) and a file holding only survivors cannot show it.
    """
    keys = sorted({key for contest in (PRIMARY_CONTEST, ALTERNATE_CONTEST)
                   for key, _, _ in criteria_for(contest).values()})
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    # mtime=0: gzip stamps the wall clock into its header by default, so an
    # unchanged artifact re-written by an identical run produces a different file
    # and a spurious diff. The point of committing these draws is that a reader
    # can check them, which requires the bytes to depend only on the data.
    with _deterministic_gzip(path) as handle:
        out = csv.writer(handle)
        out.writerow(["chain_index", "chain_seed", "chain_completed", "draw", *keys])
        for index, chain in enumerate(chains):
            for draw, row in enumerate(chain.rows):
                out.writerow([index, chain.seed, int(chain.completed), draw,
                              *[row[key] for key in keys]])
                n += 1
    # Chains that died before producing a single draw leave no rows, so the
    # draws file alone understates the failure rate -- and ARCHITECTURE.md
    # section 7 makes that rate part of the result, because surviving seeds are
    # not a random subset of attempted seeds. The sidecar carries every attempted
    # chain, including the empty ones.
    sidecar = path.with_name(path.name.replace("-draws.csv.gz", "-chains.json"))
    sidecar.write_text(json.dumps({
        "config_digest": config_digest(spec),
        "chains": [{"index": i, "seed": c.seed, "n_rows": len(c.rows),
                    "completed": c.completed, "failure": c.failure}
                   for i, c in enumerate(chains)],
    }, indent=2))

    try:
        shown = str(path.relative_to(ROOT))
    except ValueError:
        shown = str(path)
    return {"path": shown, "n_rows": n, "sidecar": str(sidecar.name),
            "columns": ["chain_index", "chain_seed", "chain_completed", "draw", *keys],
            "includes_failed_chains": True}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", action="append", choices=sorted(STATES),
                        help="repeatable; default is both")
    parser.add_argument("--out", default=str(OUT / "experiment-2-results.json"))
    parser.add_argument("--controls-only", action="store_true")
    parser.add_argument("--jobs", type=int, default=3,
                        help="chains to sample concurrently; they are "
                             "independent and seeded by index, so this changes "
                             "wall clock and nothing else")
    parser.add_argument("--checkpoints", default=str(OUT / "checkpoints"),
                        help="per-chain cache; a container restart then costs "
                             "one chain rather than the run")
    parser.add_argument("--from-draws", action="store_true",
                        help="re-derive every verdict from the committed draws "
                             "files instead of sampling; the whole analysis is "
                             "a pure function of those files")
    args = parser.parse_args(argv)

    control_report = controls()
    print("controls: every test can return both verdicts")
    if args.controls_only:
        print(json.dumps(control_report, indent=2))
        return 0

    # Iowa first: it is the cheap state, so a full result is banked early.
    order = {"IA": 0, "CO": 1}
    keys = sorted(args.state or STATES, key=lambda k: order.get(k, 99))
    checkpoints = Path(args.checkpoints) if args.checkpoints else None
    results = {"master_seed": MASTER_SEED, "controls": control_report, "states": {}}
    for key in keys:
        spec = STATES[key]
        rows_path = Path(args.out).parent / f"{spec.prefix}-draws.csv.gz"
        if args.from_draws:
            report, chains = run_state(spec, draws=rows_path)
            report["draws_file"] = {"path": str(rows_path.relative_to(ROOT)),
                                    "n_rows": sum(len(c.rows) for c in chains),
                                    "reanalysed_without_sampling": True}
        else:
            report, chains = run_state(spec, jobs=args.jobs,
                                       checkpoints=checkpoints)
            report["draws_file"] = write_rows(spec, chains, rows_path)
            print(f"wrote {rows_path} ({report['draws_file']['n_rows']} rows)")
        results["states"][key] = report

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, default=str))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
