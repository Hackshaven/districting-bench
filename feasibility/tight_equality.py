"""Can a ReCom ensemble represent the legal standard Iowa actually meets?

The enacted plan's max-min spread is 94 persons = 0.0118% of ideal. ReCom cannot
run below epsilon ~= 0.001. So: of the plans ReCom does sample at feasible
epsilon, what fraction are as population-equal as the enacted plan? That fraction
is the effective acceptance rate of a post-hoc filter, and it determines whether
the "neutral baseline" can be held to the same standard as the plan under review.

Also reports PSRF as a function of chain length, to see where mixing lands.
"""
import json, time, warnings
from pathlib import Path

import numpy as np
from ensemble import build_graph, run, psrf

warnings.filterwarnings("ignore")

ENACTED_SPREAD = 94 / 797592.25  # 0.0118%
THRESHOLDS = [0.05, 0.02, 0.01, 0.005, 0.002, 0.001]  # percent max-min spread
CHAINS, STEPS = 4, 1500

graph = build_graph()
results = {}

for eps in (0.002, 0.001):
    print(f"\n{'='*74}\nepsilon = {eps}   {CHAINS} chains x {STEPS} steps")
    t0 = time.time()
    cuts, devs = [], []
    for s in range(CHAINS):
        t = time.time()
        c, d, u, ideal = run(graph, STEPS, eps, seed=3000 + s)
        cuts.append(c); devs.append(d)
        print(f"  chain {s}: {time.time()-t:7.1f}s  cut mean {c.mean():6.2f}  "
              f"distinct {u}/{STEPS}")
    wall = time.time() - t0
    alld = np.concatenate(devs) * 100  # percent spread
    allc = np.concatenate(cuts)

    print(f"\n  wall {wall:.1f}s ({wall/(CHAINS*STEPS)*1000:.1f} ms/step)")
    print(f"  cut edges: mean {allc.mean():.2f} sd {allc.std():.2f} "
          f"range {allc.min()}-{allc.max()}")
    print(f"  population spread: median {np.median(alld):.4f}%  min {alld.min():.4f}%")

    # PSRF vs chain length
    print("  PSRF(cut_edges) by chain length: ", end="")
    for n in (250, 500, 1000, STEPS):
        print(f"n={n}:{psrf([c[:n] for c in cuts]):.4f}  ", end="")
    print()

    print(f"\n  {'spread <=':>10}  {'plans':>7}  {'rate':>8}")
    for th in THRESHOLDS:
        k = int((alld <= th).sum())
        print(f"  {th:>9.3f}%  {k:>7d}  {100*k/len(alld):>7.3f}%")
    k = int((alld <= ENACTED_SPREAD * 100).sum())
    print(f"  {'enacted':>9}   {k:>7d}  {100*k/len(alld):>7.3f}%   "
          f"(<= {ENACTED_SPREAD*100:.4f}%, the enacted plan's spread)")

    results[eps] = {"wall_s": wall, "ms_per_step": wall/(CHAINS*STEPS)*1000,
                    "cut_mean": float(allc.mean()), "cut_sd": float(allc.std()),
                    "psrf": psrf(cuts), "min_spread_pct": float(alld.min()),
                    "median_spread_pct": float(np.median(alld)),
                    "n_at_enacted_spread": k, "n_sampled": len(alld)}

Path("data/processed/tight_equality.json").write_text(json.dumps(results, indent=2))
print("\nwrote data/processed/tight_equality.json")
