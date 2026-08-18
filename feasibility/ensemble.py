"""Small ReCom ensemble on Iowa's 99-county graph, Iowa Code ch. 42 criteria only.

Chapter 42 criteria, in statutory order:
  1. population equality   -> epsilon constraint below
  2. contiguity            -> guaranteed by ReCom on the rook graph
  3. whole counties        -> guaranteed by construction (counties are the units)
  4. compactness           -> measured, not constrained

No partisan or racial data is loaded anywhere in this file. It is the neutral
baseline probe, and it lives outside src/ because this is a feasibility pass.

Usage: python feasibility/ensemble.py [--steps N] [--chains K] [--epsilon E]
"""
import argparse, json, time
from functools import partial
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from gerrychain import Graph, MarkovChain, Partition, accept, constraints, updaters
from gerrychain.proposals import recom
from gerrychain.tree import recursive_tree_part

OUT = Path("data/processed")
POP, K = "P0010001", 4


def build_graph():
    g = nx.read_gml(OUT / "ia_county_rook.gml")
    pop = pd.read_csv(OUT / "ia_county_pop.csv", dtype={"GEOID": str}).set_index("GEOID")
    for n in g.nodes:
        g.nodes[n][POP] = int(pop.P0010001[n])
        g.nodes[n]["NAME"] = pop.NAME[n]
    return Graph.from_networkx(g)


def run(graph, steps, epsilon, seed):
    ideal = sum(graph.node_data(n)[POP] for n in graph.nodes) / K
    assign = recursive_tree_part(
        graph, range(K), ideal, POP, epsilon, node_repeats=10, rng=seed
    )
    init = Partition(graph, assign, {"population": updaters.Tally(POP, alias="population"),
                                     "cut_edges": updaters.cut_edges})
    chain = MarkovChain(
        proposal_fn=partial(recom, pop_col=POP, pop_target=ideal, epsilon=epsilon, node_repeats=10),
        constraints=[constraints.within_percent_of_ideal_population(init, epsilon)],
        acceptance_fn=accept.always_accept,
        initial_partition=init,
        total_steps=steps,
        rng=seed,
    )
    cut, dev, uniq = [], [], set()
    for p in chain:
        cut.append(len(p["cut_edges"]))
        pops = np.array(list(p["population"].values()))
        dev.append((pops.max() - pops.min()) / ideal)
        uniq.add(tuple(sorted(tuple(sorted(p.parts[d])) for d in p.parts)))
    return np.array(cut), np.array(dev), len(uniq), ideal


def psrf(chains):
    """Gelman-Rubin potential scale reduction factor over equal-length chains."""
    x = np.asarray(chains, dtype=float)
    m, n = x.shape
    if n < 2 or m < 2:
        return float("nan")
    means, varis = x.mean(axis=1), x.var(axis=1, ddof=1)
    B = n * means.var(ddof=1)
    W = varis.mean()
    if W == 0:
        return float("nan")
    var_hat = (n - 1) / n * W + B / n
    return float(np.sqrt(var_hat / W))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--chains", type=int, default=4)
    ap.add_argument("--epsilon", type=float, default=0.01)
    a = ap.parse_args()

    graph = build_graph()
    print(f"graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    print(f"epsilon = {a.epsilon}  ({a.chains} chains x {a.steps} steps)\n")

    cuts, devs, uniqs, t0 = [], [], [], time.time()
    for s in range(a.chains):
        t = time.time()
        c, d, u, ideal = run(graph, a.steps, a.epsilon, seed=1000 + s)
        cuts.append(c); devs.append(d); uniqs.append(u)
        print(f"  chain {s}: {time.time()-t:6.2f}s  cut_edges mean {c.mean():6.2f} "
              f"sd {c.std():5.2f}  distinct plans {u:5d}/{a.steps}  maxdev {d.max()*100:.4f}%")
    wall = time.time() - t0

    print(f"\nwall clock: {wall:.2f}s total, {wall/(a.chains*a.steps)*1000:.1f} ms/step")
    print(f"PSRF (cut_edges): {psrf(cuts):.4f}   target 1.00-1.01")
    allcut = np.concatenate(cuts)
    print(f"cut edges: mean {allcut.mean():.2f}  sd {allcut.std():.2f}  "
          f"min {allcut.min()}  max {allcut.max()}")
    print(f"max population deviation observed: {np.concatenate(devs).max()*100:.4f}%")
    print(f"distinct plans: {sum(uniqs)} of {a.chains*a.steps} sampled")
    print("\ncounty splits: 0 in every plan, by construction "
          "(districts are unions of whole counties)")
