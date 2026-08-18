"""How tight can the population constraint be before ReCom stops moving?

Karcher demands near-zero deviation for congressional districts. Iowa's enacted
plan achieves a 94-person max-min spread (0.0118% of ideal). This asks whether a
ReCom sampler can explore the space at that tolerance, or only at a looser one.
"""
import time, warnings
import numpy as np
from ensemble import build_graph, run, psrf

warnings.filterwarnings("ignore")

graph = build_graph()
print(f"{'epsilon':>9} {'max-min%':>9} {'sec':>7} {'ms/step':>8} {'cut mean':>9} "
      f"{'cut sd':>7} {'distinct':>9} {'PSRF':>7}  status")
print("-" * 88)

STEPS, CHAINS = 300, 4
for eps in (0.05, 0.01, 0.005, 0.002, 0.001, 0.0005, 0.0002, 0.0001):
    t0 = time.time()
    try:
        cuts, devs, uniqs = [], [], []
        for s in range(CHAINS):
            c, d, u, ideal = run(graph, STEPS, eps, seed=2000 + s)
            cuts.append(c); devs.append(d); uniqs.append(u)
        wall = time.time() - t0
        allc = np.concatenate(cuts)
        print(f"{eps:>9} {np.concatenate(devs).max()*100:>9.4f} {wall:>7.1f} "
              f"{wall/(CHAINS*STEPS)*1000:>8.1f} {allc.mean():>9.2f} {allc.std():>7.2f} "
              f"{sum(uniqs):>4d}/{CHAINS*STEPS:<4d} {psrf(cuts):>7.4f}  ok")
    except Exception as e:
        print(f"{eps:>9} {'':>9} {time.time()-t0:>7.1f} {'':>8} {'':>9} {'':>7} "
              f"{'':>9} {'':>7}  FAILED: {type(e).__name__}: {str(e)[:60]}")
