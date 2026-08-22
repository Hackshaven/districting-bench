#!/usr/bin/env python3
"""Convergence over the largest usable rectangle, not over full-length chains.

Split R-hat and ESS need a rectangle: every chain the same length. The obvious
way to get one is to keep only the chains that ran to completion, which is what
this project did, and at short chain lengths it was nearly free — Iowa lost 4 of
12 at 1,500 steps and the survivors were full length.

At 12,000 steps it stops being free. Iowa's chains die at 12,000, 8,133, 6,495,
4,282 and 0 draws, so "keep the complete ones" keeps **one chain** and there is no
ensemble left to diagnose.

The fix, and why it is also less biased
---------------------------------------
A chain that died at step 6,496 tells you something about step 6,496. It tells you
nothing about steps 1 through 6,495, which are draws from the same chain as any
other. Discarding them discards a whole chain because of its tail.

ARCHITECTURE.md section 7 is the reason full-length-only looked right: surviving
seeds are not a random subset of attempted seeds, so a summary over survivors is
biased. That argument is correct and it points the other way here. Selecting on
*completion* is selecting on the very property that correlates with the chain's
path; truncating every chain to a common prefix selects on nothing, because the
prefix was drawn before any chain knew it was going to die.

Two failure modes, and only one of them is about length
--------------------------------------------------------
Seeds derive from the chain index, so the same seeds fail every run. Iowa's chain
4 fails at 0 draws at every chain length tried — it cannot find an initial
partition at all. That is a property of the seed, not of the run, and no amount of
truncation recovers it. The mid-chain deaths are the length-dependent ones. Both
are counted and reported separately, because a fixed set of unusable seeds and a
length-dependent death rate are different facts about the sampler.

What this reports
-----------------
For each candidate prefix length, how many chains reach it, the resulting
rectangle, and R-hat and ESS over it. Longer prefixes use fewer chains; the choice
is a real tradeoff and it is shown rather than made silently.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import experiment_2_tradeoffs as E2          # noqa: E402
from generate import convergence             # noqa: E402

#: Diagnose on the columns that carry the experiments' verdicts.
COLUMNS = ("compactness_cut", "fairness_eg", "population_equality")

#: A rectangle needs at least this many chains to be worth reporting. Two is the
#: minimum R-hat is defined on; below four the between-chain variance estimate is
#: itself so noisy that the statistic says little.
MIN_CHAINS = 4

#: And at least this many draws per chain. split_rhat needs 4 to split at all,
#: but a rectangle that short says nothing about mixing: a chain that died at 49
#: draws would otherwise define a 12-chain rectangle of 49 draws and score
#: beautifully, because no chain has had time to go anywhere. The floor is the
#: point below which agreement between chains is evidence of nothing.
MIN_PREFIX = 500


def rectangles(chains, criteria) -> list[dict]:
    """R-hat and ESS at every prefix length a distinct chain count allows."""
    lengths = sorted({len(c.rows) for c in chains if len(c.rows) >= MIN_PREFIX},
                     reverse=True)
    out = []
    for length in lengths:
        usable = [c for c in chains if len(c.rows) >= length]
        if len(usable) < MIN_CHAINS:
            continue
        record = {
            "prefix_length": length,
            "n_chains": len(usable),
            "n_draws": length * len(usable),
            "chain_indices": [i for i, c in enumerate(chains)
                              if len(c.rows) >= length],
            "metrics": {},
        }
        for name in COLUMNS:
            key, _, _ = criteria[name]
            series = [[float(row[key]) for row in c.rows[:length]] for c in usable]
            record["metrics"][name] = {
                "split_rhat": convergence.split_rhat(series),
                "ess": convergence.ess(series),
            }
        out.append(record)
    return out


def best(records: list[dict], target: float = 1.01) -> dict | None:
    """The rectangle with the most draws whose worst R-hat meets ``target``.

    Falls back to the one with the lowest worst R-hat when none meets it, so the
    caller is told what the ensemble can actually support rather than nothing.
    """
    def worst(record):
        return max(m["split_rhat"] for m in record["metrics"].values())

    meeting = [r for r in records if worst(r) <= target]
    if meeting:
        return max(meeting, key=lambda r: r["n_draws"])
    return min(records, key=worst) if records else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", default="IA", choices=sorted(E2.STATES))
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--chains", type=int)
    parser.add_argument("--checkpoints", default=str(E2.OUT / "checkpoints"))
    args = parser.parse_args(argv)

    import dataclasses
    spec = E2.STATES[args.state]
    spec = dataclasses.replace(spec, steps=args.steps,
                               chains=args.chains or spec.chains)
    ctx = E2.load_context(spec, (E2.PRIMARY_CONTEST, E2.ALTERNATE_CONTEST))
    chains = E2.measure_ensemble(spec, ctx, log=lambda *_: None, jobs=1,
                                 checkpoints=Path(args.checkpoints))
    criteria = E2.criteria_for(E2.PRIMARY_CONTEST)

    dead_at_zero = [i for i, c in enumerate(chains) if not c.rows]
    too_short = [i for i, c in enumerate(chains)
                 if 0 < len(c.rows) < MIN_PREFIX]
    print(f"{args.state}: {len(chains)} chains requested at {args.steps} steps")
    print(f"  unusable seeds (no initial partition): {dead_at_zero or 'none'}")
    print(f"  died before {MIN_PREFIX} draws: {too_short or 'none'}")
    print(f"  draws reached: {[len(c.rows) for c in chains]}")

    records = rectangles(chains, criteria)
    print(f"\n  {'prefix':>8} {'chains':>7} {'draws':>8}  " +
          "  ".join(f"{n[:12]:>16}" for n in COLUMNS))
    for record in records:
        cells = "  ".join(
            f"{record['metrics'][n]['split_rhat']:>7.3f}/"
            f"{record['metrics'][n]['ess']:>8.0f}" for n in COLUMNS)
        print(f"  {record['prefix_length']:>8} {record['n_chains']:>7} "
              f"{record['n_draws']:>8}  {cells}")
    print("   (each cell is split R-hat / ESS)")

    chosen = best(records)
    if chosen:
        worst = max(m["split_rhat"] for m in chosen["metrics"].values())
        print(f"\n  best rectangle: {chosen['n_chains']} chains x "
              f"{chosen['prefix_length']} = {chosen['n_draws']:,} draws, "
              f"worst R-hat {worst:.3f}")
    print(json.dumps({"state": args.state, "requested_steps": args.steps,
                      "unusable_seeds": dead_at_zero,
                      "died_before_min_prefix": too_short,
                      "min_prefix": MIN_PREFIX, "min_chains": MIN_CHAINS,
                      "draws_reached": [len(c.rows) for c in chains],
                      "rectangles": records, "chosen": chosen},
                     indent=2, default=str),
          file=open(E2.OUT / f"{spec.prefix}-convergence-rectangles.json", "w"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
