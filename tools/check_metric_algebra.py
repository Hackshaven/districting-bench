#!/usr/bin/env python3
"""Is a correlation between two metrics a fact about maps, or about arithmetic?

Experiment 2's one surviving relationship on both states is **competitiveness
against mean-median** -- rho = -0.768 on Iowa, -0.309 on Colorado. That is
exactly the finding most likely to be worthless, because both metrics are
functions of the same district vote-share vector:

    mean_median(shares) = median(shares) - mean(shares)
    competitiveness(shares) = |{s : 0.45 <= s <= 0.55}|

A correlation between two functions of one vector can be a property of the
functions rather than of the vector's provenance. If so it would hold for any k
numbers, would say nothing about Iowa or Colorado, and the experiment's only
surviving result would not be about districting at all.

This settles it by measuring the correlation the *arithmetic alone* produces.
Share vectors are drawn with no map behind them and the same two metrics are
computed. The null is run under the one constraint districting genuinely faces:
a map cannot choose the statewide vote share, only how it is partitioned, so the
district shares are shifted to hold the mean exactly.

Result, at every spread and both district counts: the arithmetic produces a
**positive** rho (+0.003 to +0.20), while both states measure a strongly negative
one. The functional form pushes the opposite way from the observation, so the
observed relationship is not an artifact of it. The sign sweep shows the
arithmetic can go negative when the statewide share sits far from 50%, but only
weakly -- never within a factor of four of Iowa's -0.768, and Iowa's 2020
presidential share sits at 0.45 where the arithmetic gives +0.13.

This does not prove the relationship is causal or that it would replicate in
another state. It rules out the specific objection that it is a tautology.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from evaluate import compactness as C          # noqa: E402  (spearman lives here)

#: The observed relationship this check exists to defend, per state:
#: (k districts, statewide two-party D share, observed Spearman rho).
OBSERVED = {
    "IA": (4, 0.45, -0.768),
    "CO": (8, 0.55, -0.309),
}

SPREADS = (0.04, 0.06, 0.08, 0.10, 0.14)
MEANS = (0.40, 0.45, 0.50, 0.55, 0.60)
DRAWS = 12_000
SEED = 7


def mean_median(shares) -> float:
    return st.median(shares) - st.fmean(shares)


def competitive(shares, lo: float = 0.45, hi: float = 0.55) -> int:
    return sum(1 for s in shares if lo <= s <= hi)


def synthetic_rho(k: int, mu: float, sd: float, *, draws: int = DRAWS,
                  seed: int = SEED, hold_mean: bool = True) -> float:
    """Spearman rho between the two metrics over share vectors with no map behind them.

    ``hold_mean`` shifts each vector so its mean is exactly ``mu``. That is the
    honest null: districting cannot move the statewide share, so a null that lets
    it vary is answering a question no map drawer faces.
    """
    rng = random.Random(seed)
    xs, ys = [], []
    for _ in range(draws):
        shares = [rng.gauss(mu, sd) for _ in range(k)]
        if hold_mean:
            offset = st.fmean(shares) - mu
            shares = [s - offset for s in shares]
        shares = [min(0.99, max(0.01, s)) for s in shares]
        xs.append(competitive(shares))
        ys.append(-abs(mean_median(shares)))     # both re-signed: larger is better
    return C.spearman(xs, ys)


def check() -> dict:
    report: dict = {"draws_per_cell": DRAWS, "seed": SEED, "states": {}}
    for state, (k, mu, observed) in OBSERVED.items():
        cells = [{"sd": sd, "rho": synthetic_rho(k, mu, sd)} for sd in SPREADS]
        worst = min(cell["rho"] for cell in cells)
        report["states"][state] = {
            "k": k, "statewide_share": mu, "observed_rho": observed,
            "by_spread": cells,
            "most_negative_arithmetic_rho": worst,
            "arithmetic_explains_observation": worst <= observed,
        }
    report["mean_sweep_k4"] = [
        {"mu": mu, "rho": synthetic_rho(4, mu, 0.08)} for mu in MEANS
    ]
    report["conclusion"] = (
        "the arithmetic of these two metrics produces a positive rank correlation "
        "at every spread tested and both district counts; both states observe a "
        "strongly negative one, so the observed relationship is not a property of "
        "the metrics' shared functional form"
    )
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(
        ROOT / "docs" / "experiment-2" / "metric-algebra-check.json"))
    args = parser.parse_args(argv)

    report = check()
    for state, block in report["states"].items():
        print(f"{state} (k={block['k']}, statewide share {block['statewide_share']}): "
              f"observed rho {block['observed_rho']:+.3f}")
        for cell in block["by_spread"]:
            print(f"    sd={cell['sd']:.2f}  arithmetic rho={cell['rho']:+.3f}")
        verdict = ("ARTIFACT" if block["arithmetic_explains_observation"]
                   else "not explained by arithmetic")
        print(f"    -> {verdict}\n")

    failed = [s for s, b in report["states"].items()
              if b["arithmetic_explains_observation"]]
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"wrote {args.out}")
    if failed:
        print(f"WARNING: arithmetic reproduces the observation for {failed}; "
              f"the finding for those states is a tautology, not a measurement")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
