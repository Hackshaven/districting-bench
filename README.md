# districting-bench

[![DOI](https://zenodo.org/badge/1337936265.svg)](https://doi.org/10.5281/zenodo.22102853)

A research system for evaluating legislative districting plans: it detects
likely gerrymanders against a neutral baseline, scores plans on many criteria at
once, and makes every value judgment an explicit, changeable parameter.

**Status: exploratory. Not validated. Do not use for litigation, advocacy, or
map adoption.**

---

## First result

![Bar chart of Democratic seats won, of 4, across 27,564 neutral ReCom draws for Iowa under the 2020 presidential vote: 0 seats in 1.4% of draws, 1 seat in 49.0% and 2 seats in 49.5%, each of those two give or take about 6 points (2 Monte Carlo standard errors), and none at 3 or 4; the six chains range from 41% to 58% at 2 seats. Iowa's enacted plan is marked at 0 seats; the figure's note gives the reasons that comparison is not like-for-like and not yet a finding.](docs/figures/ia-neutral-seat-distribution.png)

Across 27,564 draws from a ReCom sampler with no access to election data, **a
neutral ensemble for Iowa gives Democrats 0–2 of 4 seats under the 2020
presidential vote, and 2 seats in about half of its draws** (49.5%, with a Monte
Carlo standard error of 3 to 4 points; the six chains range from 41% to 58%).
Under the 2020 Senate vote the same draws reach 3 seats, though only in two plans
early in one chain, so the top of that range depends on the election. It is also
the sampler's range, not the limit of what is possible: a 3-seat plan meeting the
same population and contiguity constraints exists under the presidential vote,
and `tests/test_adversarial.py` builds one when the data are present.

The consequence is a limit, not a score. Detectability is bounded below by the
width of the neutral distribution, and that width is set by the state, the
election and the ensemble, not by the detection method. A detection target stated
in absolute seats — such as `docs/CRITERIA.md` §8's "≥0.95 true-positive rate at
a 2-seat shift" — asks a detector to separate an outcome from its own null, and
is unreachable on a four-district state whose null already spans two seats.

Two cautions travel with these numbers. The seat count's split R-hat is 1.014,
just outside `docs/CRITERIA.md` §8's 1.00–1.01 band, and with about 286 effective
draws the diagnostic cannot resolve that band: a simulated chain that is
stationary at the same effective size usually reads above it
(`docs/first-result/INSTRUMENT-AUDIT.md`). What the chains do show is drift: the
2-seat share is 46.1% over the first half of the rectangle and 53.0% over the
second, and 45.3–50.5% on the other prefix rectangles the convergence report
offers. And v0.1.0 reported the 2-seat share as 43%, from a 1,820-draw ensemble
that was never committed: seven chains of 260 draws with no convergence
diagnostic. Estimated three ways from the committed chains, an estimate that size
carries a standard error of 9 to 12 points, so the two numbers do not disagree.
The 0–2 range is the same in both.

Iowa's enacted plan returns 0 D seats, as 1.4% of these draws do (0.4–2.5% across
the six chains), and its 0 turns on one district at 49.8% Democratic. That
comparison is **not yet a finding**, because it is not like-for-like. The draws
are not held to the 94-person population equality the enacted plan meets: only
454 of the 27,564 are that equal. Nor are they as uncompact: 88% have fewer cut
edges than its 51, and in each of the six chains 0 seats is commoner among the
draws with 51 or more. Pooled, 4.5% of those give 0 seats, or 2.2% once each
chain's first 500 draws are dropped, against 1.0% of the rest. See
`docs/progress.md` and D-041.

---

## The three experiments

`prompt.md` asked for three measurements, each run once. All three are derived on
both states, with a written finding in `docs/progress.md` and a committed figure.

| | finding | figure |
| --- | --- | --- |
| **Criteria sensitivity** | competitiveness and mean-median bind; compactness barely moves anything. The *ordering* does not replicate across elections — only the bind/no-bind classification does. | `docs/figures/exp1-{ia,co}-v2-sensitivity.png` |
| **Tradeoff frontier** | Colorado: 20 of 21 relationships show nothing, testing Stephanopoulos (126 Colum. L. Rev. 1001). Iowa: 5 of 15, one large. Every null means "nothing stronger than ρ ≈ 0.13–0.22", not "no tradeoff". | `docs/figures/exp2-*.png` |
| **Metric gameability** | three legal Colorado plans on which a named fairness metric reads ≈0 while one party takes 7 or 8 of 8 seats. arXiv:2409.17186, reproduced here. | `docs/figures/exp3-gameability.png` |

The third is the one that constrains the other two: it is the demonstration of
why nothing in this repository emits a single fairness score.

---

## What this is not

This is not a tool that produces fair maps, and it does not claim to be
non-political.

There is no neutral districting criterion. Compactness, county integrity,
competitiveness, community preservation, and proportionality are all normative
choices with predictable and differing partisan consequences. Applying
"neutral" rules is itself a choice: because of how voters are distributed
geographically, criteria drawn blind to election results produce systematic
partisan effects. No amount of mathematics dissolves this.

What this system attempts is narrower and more defensible: make every choice
explicit, parameterized, and logged, so that a reader can see whose definition
of fair a given result encodes and substitute their own.

Any output of this system that reads as a verdict rather than a distribution is
a bug.

---

## The two halves, and why only one of them is optimized

**Detection** asks whether a given plan is an outlier relative to what the stated
legal criteria produce. This has manufacturable ground truth: build a
gerrymander deliberately, and you know it is one. That makes it measurable,
falsifiable, and safe to optimize against.

**Generation** asks what the fair map is. This has no ground truth, because
"fair" is contested at the definitional level. Every single-number fairness
metric in the literature — efficiency gap, mean-median, declination, GEO — is
provably gameable: a plan can produce a lopsided seat outcome while the metric
sits inside any reasonable bound. Optimizing toward such a metric produces a
gerrymander with a certificate of fairness attached.

So this repository builds both halves and optimizes only the first. See
`docs/CRITERIA.md` §8 for the detection gates and §5.2 for the gameability
result.

---

## The firewall

The ensemble generator must never see partisan or racial data. It receives
population, adjacency, geography, and subdivision boundaries — nothing else.
Partisan and demographic evaluation happens strictly downstream, in separate
code, with no path back into generation.

If those two halves touch, the neutral baseline is no longer neutral and every
outlier claim built on it is void.

This is enforced mechanically by `tools/check_firewall.py`, run in CI. The check
was written before any implementation code and **must not be modified, relaxed,
or worked around.** Which results a change to the config casts doubt on depends
on its direction. Loosening it makes every result produced after the change
suspect. Closing a gap in it makes the results produced before the change
suspect, until they are checked against the tightened rules.

```
src/generate/     population + geometry only. May not import from any sibling.
src/evaluate/     partisan + demographic metrics. Downstream only.
src/adversarial/  deliberately partisan: builds known gerrymanders for testing.
src/detect/       compares a plan to an ensemble. May import from all of the above.
```

Everything inside each package is an open design question. The boundary between
them is not.

---

## Setup

Python 3.11. From a clean clone:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**The tests run at this point, and most of them pass.** No data required:

```bash
PYTHONPATH=src pytest tests -q        # 634 passed, 151 skipped
```

The 151 skips are not a problem to fix — they are every test that needs real
census and election data, which is not in this repository (see below). CI runs
exactly this configuration on every push.

### Getting the data

`data/` is gitignored. The census inputs are public domain and scripted; the
election returns are neither.

```bash
tools/fetch_raw.sh            # ~700 MB of Census files, both states
                              #   (or: tools/fetch_raw.sh ia | co)
```

Then the election returns, **by hand** — VEST publishes on the Harvard Dataverse
behind a click-through that a script cannot accept for you:

- VEST, *2020 Precinct-Level Election Results*, <https://doi.org/10.7910/DVN/K7760H>
- Unpack Iowa to `data/raw/vest/ia_2020.shp` and Colorado to
  `data/raw/vest_co/co_2020.shp`. Those directory names are this repository's
  convention, not VEST's.

`tools/fetch_raw.sh` prints these instructions itself if the files are absent.

### Building the analysis inputs

```bash
python tools/prepare_data.py            # Iowa   -> data/processed/ia_*
python tools/prepare_data_co.py         # Colorado -> data/processed/co_*
python tools/prepare_municipalities.py  # place / statehouse / statesenate layers
```

`prepare_data.py` asserts the Iowa presidential totals (897,672 R, 759,061 D), so
a wrong or mis-vintaged VEST file fails loudly rather than quietly changing every
downstream number.

With the data built, the full suite runs:

```bash
PYTHONPATH=src pytest tests -q         # 780 passed, 5 skipped (derived; see below)
python tools/check_firewall.py         # must print: clean
```

The 780 is derived, not measured: this file recorded 719 with the data at
v0.1.0; the 61 tests added since need neither the data nor the network; and no
code an earlier test runs has changed except docstrings.

**Without the election returns you can still generate.** The neutral half needs
population, geometry and adjacency only — that is the firewall, not a
limitation. Every partisan metric and all three experiments need VEST. The
first-result figure and the PlanScore cross-check below do not: they read only
committed files, and PlanScore's.

### Reproducing the results

The experiments were each run once and are not meant to be re-run
(`prompt.md`: *"Run each once… do not iterate to improve the result"*). Their
outputs are committed. What you can re-derive from those committed artifacts
(`phase_2_report.py` and `plot_experiment_3.py` also need the data built above):

```bash
python tools/experiment_1_sensitivity.py --ensemble v2
python tools/experiment_2_tradeoffs.py --ensemble v2      # hours; reads committed draws
python tools/phase_2_report.py

python tools/plot_experiment_1.py --ensemble v2   # -> docs/figures/exp1-*.png
python tools/plot_experiment_2.py --ensemble v2   # -> docs/figures/exp2-*.png
python tools/plot_experiment_3.py                # -> docs/figures/exp3-gameability.png
python tools/plot_seat_distribution.py           # -> docs/figures/ia-neutral-seat-distribution.png
                                                 #    (no data needed)
```

One check reaches outside the repository: it fetches PlanScore's scores for
both enacted plans (two files pinned by sha256) and recomputes the per-election
metrics from PlanScore's district totals with `evaluate.partisan`. It exits 0
only if every efficiency gap PlanScore publishes is reproduced, and its
definitions of mean-median, partisan bias and declination match ours once
converted to its sign and scale; it rewrites its record only then. PlanScore
titles the Iowa plan a draft; `docs/progress.md`, "The plans are the ones this
repository studies", says why it is the enacted one.

```bash
python tools/check_planscore.py   # -> docs/cross-checks/planscore.json
                                  #    (needs the network, not the data)
```

---

## Start here

1. `docs/CRITERIA.md` — every criterion, threshold, and metric, with a provenance
   class saying who decided it and whether it can be argued with. Read this
   before any code.
2. `prompt.md` — the task specification handed to the agent that built this.
3. `tools/check_firewall.py` — the boundary enforcement.
4. `docs/progress.md` — the full write-up: what was run, what it found, and
   every result that was later retracted and why.
5. `docs/DECISIONS.md` — D-001…D-041, each non-obvious choice logged when it was
   made rather than reconstructed afterwards.

---

## Scope

**Iowa** congressional districting came first: 99 whole counties, and Iowa Code
Chapter 42 supplies an explicitly ordered criteria list, which removes our
discretion over value choices that would otherwise be ours to make.

**Colorado** followed, and is precinct-level: 3,108 VTDs, 8 districts, drawn by an
independent commission under Amendments Y and Z. It exists because a four-district
whole-county state cannot exercise most of the machinery — Iowa's county-integrity
criterion is constant by construction, and its neutral seat distribution is too
narrow to test detection against. Colorado supplies the k=8 regime where fairness
metrics have room to be gamed.

Deliberately out of scope for now: ecological inference and racially polarized
voting analysis (documented in `docs/CRITERIA.md` §4.3, deferred for scope, not
because it is unimportant).

---

## Legal context, briefly

Partisan gerrymandering claims are not justiciable in federal court
(*Rucho v. Common Cause*, 2019). State courts have split on whether their own
constitutions permit such claims. Voting Rights Act §2 was substantially
narrowed by *Louisiana v. Callais* (April 2026).

The practical consequence is that the available remedy is jurisdiction-dependent
and currently narrow. Output from this system should not imply a cause of action
that does not exist where the reader lives.

---

## Attribution

Independent research project. Not affiliated with, endorsed by, or produced on
behalf of any redistricting commission, court, political party, campaign, or
advocacy organization. It takes no position on the merits of any cited decision
and is not connected to the author's employment.

## Citing this work

Cite the archived release, not the repository — a release is a fixed state with a
DOI, a branch is not. `CITATION.cff` carries the metadata; GitHub renders a
"Cite this repository" button from it.

Releases are archived to [Zenodo](https://zenodo.org), which mints a DOI for
each one plus a *concept* DOI that always resolves to the newest. A release is
cut when the `version` in `CITATION.cff` changes on `main` — deliberately not on
every merge, because a DOI is permanent and cannot be withdrawn, only superseded.
`.github/workflows/release.yml` runs the firewall check and the full test suite
before tagging: a permanent identifier should not point at a tree whose own
checks fail.

The badge at the top of this file points at the **concept DOI**,
[10.5281/zenodo.22102853](https://doi.org/10.5281/zenodo.22102853), which always
resolves to the newest release. To cite one specific version instead, use its own
DOI — v0.1.0 is
[10.5281/zenodo.22102854](https://doi.org/10.5281/zenodo.22102854).

Anything citing this should carry its status with it: **exploratory, not
validated, not for litigation, advocacy, or map adoption.**

## License

Apache License 2.0 — see `LICENSE`.

This covers the code and documentation in this repository. It does **not** cover
the input data, none of which is redistributed here. Census inputs are public
domain (17 U.S.C. §105); the election returns carry no declared licence at all,
which is why `data/` is gitignored and `tools/fetch_raw.sh` sends you to the
source. See `docs/CRITERIA.md` §9.1.
