# Architecture — Phase 1

The firewall fixes the package boundaries. Everything inside them is decided here.
This document is the contract that parallel builders work against; it is
prescriptive, and a module that disagrees with it is wrong until this file changes.

`prompt.md` says to decide the architecture rather than ask. This is that decision.

---

## 1. Package internals

```
src/generate/          population + geometry ONLY. Imports nothing from src/.
  units.py             load county units; SCHEMA-GUARDED (§4)
  ensemble.py          ReCom sampler: seeded, node_repeats=0, failure-tolerant
  convergence.py       rank-normalized split R-hat + ESS
  seeds.py             deterministic seed derivation

src/evaluate/          metrics. Imports nothing from src/.
  plan.py              Plan type; district aggregation
  elections.py         partisan data loader (the ONLY sanctioned entry point)
  partisan.py          efficiency gap, mean-median, declination, partisan bias, seats-votes
  compactness.py       Polsby-Popper, Reock, Schwartzberg, convex hull, cut edges
  administrative.py    county splits, ballot styles per 10,000 voters

src/adversarial/       may import evaluate
  gerrymander.py       seat-maximizing search subject to legal constraints
  nulls.py             neutral plans that look biased from geography alone

src/detect/            may import generate, evaluate, adversarial
  outlier.py           locate a plan within an ensemble, per metric
  confusion.py         TPR / FPR / detection-threshold curve
  bench.py             headless bench -> bench-results.json + plots
```

**Duplication between `generate` and `evaluate` is deliberate and required.** Both
need a plan representation and a unit loader. They do not share one, because a
shared module is an import edge and the firewall exists to forbid exactly that.
See the `src/*/README.md` files: "A commit that merges these packages, adds a
shared utility they all import, or relaxes `tools/firewall.yaml` invalidates every
result produced after it."

---

## 2. Data contract

Everything under `data/processed/`, produced by `tools/prepare_data.py`, gitignored,
regenerable from `feasibility/fetch_data.sh` plus that script.

| File | Columns | Class |
| --- | --- | --- |
| `ia_units.csv` | `GEOID`, `NAME`, `pop` | **neutral** |
| `ia_units.gpkg` | `GEOID`, `NAME`, `pop`, `geometry` | **neutral** |
| `ia_adjacency.json` | `{GEOID: [GEOID, ...]}` rook | **neutral** |
| `ia_enacted_cd118.csv` | `GEOID`, `district` | **neutral** |
| `ia_elections.csv` | `GEOID` + election columns | **PARTISAN** |

`ia_elections.csv` may be read by `evaluate`, `adversarial` and `detect`. It must
never be read by `generate`. This is enforced at runtime (§4), because — as
`docs/FEASIBILITY.md` §1 establishes — the static check cannot enforce it: the
column names in this file are VEST-style (`G20PREDBID`, `G20PRERTRU`), which the
denylist does not match, and a bare `read_csv` names no column at all.

**Units are counties.** Iowa congressional districts are whole counties (Iowa Code
ch. 42), so the unit graph is the 99-county rook graph and county splits are
identically zero. See FEASIBILITY.md §3, §5.3.

---

## 3. Plan representation

A plan is a mapping from unit id to district id:

```python
Plan = dict[str, int]      # GEOID -> district, districts numbered 1..K
```

Serialized as CSV with exactly the columns `GEOID,district`. Both `generate` and
`evaluate` implement their own loader for this format. That duplication is the
point.

Invariants every plan must satisfy, checked by `evaluate.plan.validate`:

- every unit assigned exactly once
- district ids are exactly `1..K`, none empty
- each district connected on the rook graph

---

## 4. The runtime schema guard — this Phase's main firewall decision

`docs/FEASIBILITY.md` §1 found that `tools/check_firewall.py` cannot see three of
the routes by which partisan data could reach `generate`: VEST-style column names,
a file read that names no column, and non-`.py` files. The static check is not
modified (`prompt.md` forbids it, and it would not help). Instead, `generate` gets
a **positive schema allowlist at load time**:

`src/generate/units.py` accepts a dataframe **only** if its column set is a subset
of `{GEOID, NAME, pop, geometry}`. Any other column — whatever it is called —
raises. A denylist asks "is this name forbidden"; an allowlist asks "is this name
one of the four things generation is entitled to see", which is the question that
actually protects the baseline.

This is defence in depth, not a replacement: `check_firewall.py` still runs in CI
and still gates every commit.

---

## 5. `bench-results.json` schema

Written by `src/detect/bench.py`. Deterministic given the seed. This is the file
critics read; they do not read builder reasoning.

```jsonc
{
  "schema_version": 1,
  "round": 3,
  "config": {
    "state": "IA", "units": "county", "n_districts": 4,
    "epsilon": 0.0002, "steps": 2000, "chains": 8,
    "master_seed": 20260818, "node_repeats": 0
  },
  "ensemble": {
    "n_requested": 16000, "n_completed": 14000,
    "chain_failures": 1, "failure_rate": 0.125,   // FEASIBILITY.md §5.1
    "distinct_plans": 4210,
    "convergence": {
      "cut_edges":  {"split_rhat": 1.004, "ess": 812},
      "pop_spread": {"split_rhat": 1.007, "ess": 640}
    },
    "population_spread": {"min": 23, "median": 310, "max": 1580}
  },
  "scenarios": [
    {"id": "gerry_r_2seat", "kind": "planted", "target_party": "R",
     "intended_seat_shift": 2, "realized_seat_shift": 2, "flagged": true,
     "metrics": {"efficiency_gap": 0.14, "mean_median": 0.03, "...": 0},
     "percentiles": {"efficiency_gap": 0.998, "...": 0}},
    {"id": "null_geography_07", "kind": "null", "intended_seat_shift": 0,
     "realized_seat_shift": 1, "flagged": false, "metrics": {}, "percentiles": {}}
  ],
  "confusion": {
    "tpr_at_2seat": 0.96, "fpr_on_nulls": 0.04,
    "min_detectable_seat_shift": 2,
    "by_magnitude": [{"seats": 1, "tpr": 0.42}, {"seats": 2, "tpr": 0.96}]
  },
  "gates": {
    "tpr_at_2seat":  {"target": 0.95, "value": 0.96,  "pass": true},
    "fpr_on_nulls":  {"target": 0.05, "value": 0.04,  "pass": true},
    "split_rhat":    {"target": 1.01, "value": 1.007, "pass": true},
    "legal_compliance": {"target": 1.0, "value": 1.0, "pass": true}
  },
  "firewall": {"clean": true, "config_sha256": "..."}
}
```

Gates are from `docs/CRITERIA.md` §8. `split_rhat` supersedes the unsplit statistic
used in the feasibility pass, which FEASIBILITY.md §5.4 showed has no resolution at
4 chains.

---

## 6. Detection — what is being optimized

The only loop. Ground truth is manufacturable: `adversarial` builds a plan with a
known intended seat shift, so a flag on it is a true positive and a flag on a null
case is a false positive.

**Null cases are as important as positive cases** (CRITERIA.md §8). A neutrally
drawn Iowa map can look biased purely from where Democrats live (Chen & Rodden;
CRITERIA.md §5.4) — Polk, Linn, Johnson and Scott counties hold the Democratic vote
and the rest of the state is rural. A detector that fires on those has learned
political geography, not gerrymandering.

**The detector reports a distribution, never a verdict** (README, CRITERIA.md §11).
`outlier.py` returns a percentile per metric plus the ensemble distribution; the
decision rule that turns percentiles into a flag lives in `confusion.py` and is an
explicit, logged parameter — never buried in a scoring function.

**No `fairness_score()`.** `prompt.md`: "If you find yourself writing a function
called `fairness_score()` that returns one number, stop." Metrics are reported side
by side with disagreements surfaced.

---

## 7. Seeding and determinism

One `master_seed` per bench run. Every downstream seed is derived from it by
`generate.seeds.derive(master_seed, purpose, index)`, so a run is reproducible from
one integer, and scenarios can be regenerated fresh each round (as Phase 1 requires)
by advancing the round number rather than reusing a fixed case.

Chain failures are expected at tight ε (FEASIBILITY.md §5.1: 63% at ε=1×10⁻⁴) and
must be **counted and reported**, never silently retried — surviving seeds are not a
random subset of attempted seeds, so the failure rate is itself a sampling bias.

---

## 8. Not in Phase 1

Ecological inference and racially polarized voting (CRITERIA.md §4.3, deferred with
reasons). COI as an objective function — supported as an input layer only, never
optimized against. Precinct-level states. Colorado.
