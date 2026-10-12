# districting-bench

[![DOI](https://zenodo.org/badge/1337936265.svg)](https://doi.org/10.5281/zenodo.22102853)

A research system for evaluating legislative districting plans: it detects
likely gerrymanders against a neutral baseline, scores plans on many criteria at
once, and makes every value judgment an explicit, changeable parameter.

**Status: exploratory. Not validated. Do not use for litigation, advocacy, or
map adoption.**

---

## First result

![Bar chart of Democratic seats won, of 4, across 27,564 neutral ReCom draws for Iowa under the 2020 presidential vote: 0 seats in 1.4% of draws (±0.8 points), 1 seat in 49.0% and 2 seats in 49.5%, each of those two with whiskers of about ±6 points (2 Monte Carlo standard errors by one estimate; others run higher), and none at 3 or 4; the six chains range from 41% to 58% at 2 seats and from 0.4% to 2.5% at 0. Iowa's enacted plan is marked at 0 seats; the figure's note says its 0 turns on one district at 49.8% Democratic, that the comparison is not like-for-like because the draws are not held to the plan's 94-person population spread, and that it is not yet a finding. The footer's last lines read: "Election returns, licensed CC BY 4.0 (creativecommons.org/licenses/by/4.0): Voting and Election Science Team (VEST), 2020, version 49, doi.org/10.7910/DVN/K7760H. Each draw's seats are counted from them (D-043, D-044)."](docs/figures/ia-neutral-seat-distribution.png)

Across 27,564 draws from a ReCom sampler with no access to election data, **a
neutral ensemble for Iowa gives Democrats 0–2 of 4 seats under the 2020
presidential vote, and 2 seats in about half of its draws** (49.5%, with a Monte
Carlo standard error of 3 to 4 points or more; the six chains, separately seeded
runs of the sampler, range from 41% to 58%). Each draw's plan is regenerated
from its chain's seed, and its seats are counted from VEST's 2020 precinct
returns, aggregated to counties (D-043). Under the 2020 Senate vote the same
draws reach 3 seats in two plans early in one chain, and committed draws outside
the 27,564 reach it in three more plans, so the top of the 0–2 range depends on
the election. It is also the sampler's range, not the limit of what is possible: a
3-seat plan meeting the same population and contiguity constraints exists under
the presidential vote, and `tests/test_adversarial.py` builds one when the data
are present.

The consequence is a limit, not a score. Detectability is bounded below by the
width of the neutral distribution, and that width is set by the state, the
election and the ensemble, not by the detection method. A detection target stated
in absolute seats — such as `docs/CRITERIA.md` §8's "≥0.95 true-positive rate at
a 2-seat shift" — asks a detector to separate an outcome from its own null, and
is unreachable on a four-district state whose null already spans two seats.

Two cautions travel with these numbers. The seat count's split R-hat is 1.014,
just above `docs/CRITERIA.md` §8's 1.00–1.01 band, but with about 286 effective
draws the diagnostic cannot resolve that band: a simulated chain that is
stationary at the same effective size usually reads above it, and the two halves
of the rectangle (46.1% and 53.0% at 2 seats) differ by no more than such a
chain's often do. What does point to slow mixing is chain by chain: the two chains
that ran to 12,000 draws put 33.2% and 51.6% of them at 2 seats, and the two that
started at 1-seat plans put about a third of their first halves there, both
unlikely for a stationary sampler (`docs/first-result/INSTRUMENT-AUDIT.md`, as is
every estimate below). So 3 to 4 points may understate the standard error. And
v0.1.0 reported the 2-seat share as 43%, from a 1,820-draw ensemble that was never
committed: seven chains of 260 draws with no convergence diagnostic. Estimated
three ways from the committed chains, an estimate that size carries a standard
error of 9 to 12 points, and started cold, as those chains were, v2's own chains
give 30–42%; the two numbers cannot be told apart. The 0–2 range is the same in
both.

Under the 2020 presidential vote, Iowa's enacted plan gives Democrats 0 of 4
seats, as 1.4% of these draws do (0.4–2.5% across the six chains): a share of the
draws, not a probability about the enacted plan. Its 0 turns on one district at
49.8% Democratic, of the two-party vote: a shift of 0.18 points toward Democrats
in every district would move it into the 1-seat bar. That comparison is **not yet
a finding** either way, because it is not like-for-like: the draws are not held to
the enacted plan's 94-person population spread, the gap between its most and least
populous districts, and only 454 of the 27,564 are that equal.

How its compactness compares depends on the measure, and the draws were scored on
two. On cut edges, the number of pairs of counties sharing a border, not just a
corner, that district lines separate (fewer is more compact), 88% of the draws
have fewer than its 51 (77–92% across chains). On mean Polsby-Popper, a score
comparing each district's area with that of a circle with the same perimeter,
averaged over the four (higher is more compact), it sits mid-ensemble, with 48.7%
of the draws more compact (36–60% across chains). Taking all the draws together, 0
seats is more common among those no more compact than it on either measure, but
how much more common is not robust, and changes with which draws are counted: most
of the cut-edge excess comes from one stretch early in one chain's run, and judged
across the six chains, neither difference is clearly told apart from zero. Whether
to match the comparison on compactness, adjusting it so the draws resemble the
plan in compactness, is open. The cut-edge gap may come from choices made in
drawing the plan, from constraints the draws are not held to, such as the plan's
tighter population spread, or from the sampler's own preference for few cut edges.
These draws cannot tell the cases apart, so they cannot show whether the gap
reflects any choice made in drawing the plan, let alone why one was made. Matching
means something different in each case (D-041 sets out how), and restricting the
draws to those no more compact than the plan would be a properly matched
comparison in none of them. On the measure, Iowa Code §42.4(4) (Iowa Code 2026)
names the tests for comparing the compactness of districts or plans, length-width
and perimeter compactness. The draws were scored on neither, and the statute does
not say how to weigh its two tests if they disagree. Whether to match is the
repository owner's choice (D-041 in `docs/DECISIONS.md`). See `docs/progress.md`.

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
PYTHONPATH=src pytest tests -q        # 663 passed, 151 skipped
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

Then the election returns, **by hand**: this repository does not fetch them.
VEST publishes them on the Harvard Dataverse:

- VEST, *2020 Precinct-Level Election Results*, <https://doi.org/10.7910/DVN/K7760H>.
  The DOI resolves to the latest version; the seat counts were made from version
  49 (<https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/K7760H&version=49.0>),
  and the recount names only those files as its returns.
- Save Iowa's `ia_2020.zip` in `data/raw/vest/` and unpack it there, so that
  `data/raw/vest/ia_2020.shp` exists; `tools/recount_seats.py` identifies the
  returns by the unpacked files, and by the zip if you keep it (D-043). Unpack
  Colorado to `data/raw/vest_co/co_2020.shp`. Those directory names are this
  repository's convention, not VEST's.

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
PYTHONPATH=src pytest tests -q         # 809 passed, 5 skipped (derived; see below)
python tools/check_firewall.py         # must print: clean
```

The 809 and the 5 are derived, not measured: with the data, this file
recorded 719 passed and 5 skipped at v0.1.0; the 90 tests added since need
neither the data nor the network (without the data, passes rose from 573 to
663 and skips stayed at 151); and no code that a v0.1.0 test runs has
changed since, except docstrings.

**Without the election returns you can still generate.** The neutral half needs
population, geometry and adjacency only — that is the firewall, not a
limitation. Every partisan metric and all three experiments need VEST. The
first-result figure and the PlanScore cross-check below do not: they read only
committed files, and PlanScore's.

### Reproducing the results

The experiments were each run once and are not meant to be re-run
(`prompt.md`: *"Run each once… do not iterate to improve the result"*). Their
outputs are committed. What you can re-derive from those committed artifacts
(`experiment_2_tradeoffs.py`, `phase_2_report.py`, `plot_experiment_3.py` and
`recount_seats.py` also need the data built above):

```bash
python tools/experiment_1_sensitivity.py --ensemble v2
python tools/experiment_2_tradeoffs.py --ensemble v2      # hours; reads committed draws
python tools/phase_2_report.py

python tools/plot_experiment_1.py --ensemble v2   # -> docs/figures/exp1-*.png
python tools/plot_experiment_2.py --ensemble v2   # -> docs/figures/exp2-*.png
python tools/plot_experiment_3.py                # -> docs/figures/exp3-gameability.png
python tools/recount_seats.py                    # -> docs/first-result/ia-seats-v2.csv.gz, .json
                                                 #    (needs the Iowa data; ~25–30 min on an idle 4-core machine)
python tools/plot_seat_distribution.py           # -> docs/figures/ia-neutral-seat-distribution.png
                                                 #    (no data needed)
```

The committed PNG was rendered in Inter 4.000 with hinting off
(`font.family: Inter, sans-serif, DejaVu Sans` and `text.hinting: no_hinting` in a
matplotlibrc). Nothing in the repository sets these, so a stock matplotlib renders
in DejaVu Sans: the text, numbers and line breaks are the same, but the PNG's
bytes are not, and `git status` shows it as changed. The bytes also depend on the
Pillow and zlib that write the PNG, which `requirements.txt` does not pin. To
compare, write elsewhere with `--out`; to restore the committed PNG, run
`git checkout -- docs/figures/ia-neutral-seat-distribution.png`.

Every seat value in the first result equals a count from the returns.
Experiment 2's draws file,
`docs/experiment-2/ia-draws-v2.csv.gz`, records each draw's metrics, not its
plan, so `tools/plot_seat_distribution.py` reads each draw's seats off its
committed |efficiency gap| (D-039). `tools/recount_seats.py` checks that reading
by counting (D-043): it regenerates every committed Iowa v2 draw from its
chain's seed, checks that the draw reproduces its committed row, and counts its
seats from the returns. It runs Experiment 2's sampler again, but asks it only
for the committed draws, so it counts the same draws rather than drawing new
ones. The plotter refuses to draw unless its reading of every draw agrees with
that count, and unless the count's record describes what the plotter reads: the
draws file (its SHA-256, and its sidecar's chains, seeds and row counts), the
counts file (its SHA-256 and row count), the ensemble's configuration, the two
contests and their certified statewide totals, and the VEST dataset and version
the figure's footer credits as the returns counted. It also refuses if one plan
key names draws that differ. Replace the counts file and its record together, as
the recount does.

The recount writes only if every draw reproduces and no district is tied;
otherwise it exits non-zero and writes nothing. Its docstring lists every
condition under which it refuses or fails. Nothing reaches standard output until
every chain is done; meanwhile gerrychain prints about 6,100
`BipartitionWarning`s on standard error, one for each ReCom step that took over
1,000 tries to split two districts, and they are not failures. By default a
passing run rewrites the committed `docs/first-result/ia-seats-v2.csv.gz` and its
record, `ia-seats-v2.json`. To check them without changing them, write elsewhere
and compare:

```bash
python tools/recount_seats.py --out /tmp/ia-seats.csv.gz 2> /tmp/recount.log; echo "exit $?"
grep -E '^(FAIL|refused|not written)' /tmp/recount.log
cmp <(gzip -dc /tmp/ia-seats.csv.gz) <(gzip -dc docs/first-result/ia-seats-v2.csv.gz)
diff /tmp/ia-seats.json docs/first-result/ia-seats-v2.json
```

The rows should match exactly; the compressed bytes also depend on your zlib.
The record differs wherever your setup does:

- `python`: your Python version.
- `counts_sha256`: if your zlib compresses the same rows to different bytes.
- `inputs_sha256` for `data/processed/ia_units.gpkg`: on every build, because a
  GeoPackage stores the time it was written.
- `largest_float_difference.polsby_popper_mean`: a last-bit difference rather
  than 0.0 under Python 3.12 or later, which made `sum` of floats compensated on
  most builds.
- `returns_source`: `null` unless the `.dbf` and `.shp` unpacked in
  `data/raw/vest/` are VEST's version 49, and the zip, if you kept it, is too.
- `vest`: the hashes of the VEST files you have, with no entry for the zip if
  you did not keep it.

A record written in place fails `tests/test_seat_distribution.py` wherever it
differs from the committed one in `python`, `gerrychain` or the float
differences, and a `null` `returns_source` also fails
`tests/test_recount_seats.py` and makes the plotter refuse to draw. If you ran
the recount in place, `git checkout -- docs/first-result/` restores the
committed files.

One check reaches outside the repository. It needs the network, not the data:

```bash
python tools/check_planscore.py   # -> docs/cross-checks/planscore.json
```

It fetches PlanScore's scores for both enacted plans (two files pinned by
sha256) and computes this repository's metrics, "ours" below, from PlanScore's
district totals for four past elections, the 2016 and 2020 presidential and
U.S. Senate races, with `evaluate.partisan`. It exits 0 and rewrites its record
only if every check passes, so `git diff` on that file shows what a passing run
changed (`--out <path>` writes elsewhere). Its docstring lists every condition
under which it refuses or fails instead, writing nothing. The checks compare
three kinds of thing:

- **Numbers PlanScore publishes.** The efficiency gap PlanScore publishes for
  each race, to four decimal places, must be reproduced by PlanScore's own
  formula, (S − ½) − 2(V − ½), where S and V are the Democratic seat share and
  statewide two-party vote share that `evaluate.partisan` computes. Iowa's
  district populations must match the enacted plan's in districts 2 to 4 and
  fall exactly 8 people short in district 1, as PlanScore's file did when it was
  pinned. PlanScore titles the Iowa plan a draft; `docs/progress.md`, "The plans
  are the ones this repository studies", says why it is the enacted one.
- **PlanScore's definitions, re-implemented.** PlanScore publishes mean-median,
  partisan bias and declination only as averages over elections it simulates,
  so the script re-implements the three from PlanScore's source, and each must
  match ours once ours is converted to PlanScore's sign and scale. Declination is
  compared with ours on Colorado only. Every Iowa race is a Republican sweep,
  where ours is undefined, so on Iowa the re-implementation is compared with
  −ln(4)/2 (−0.693), the value PlanScore's source assigns a Republican sweep.
- **This repository's own results, and GerryChain's.** Ours counts wasted votes.
  Its difference from PlanScore's formula, computed here rather than read from
  the rounded published value, must be the turnout term D-040 derives, τ − S (τ
  is the share of votes cast in districts the Democrats won), to within one vote
  per district (k/T, for k districts and T votes cast). The efficiency gap from
  GerryChain's count of wasted votes must match ours to the same tolerance. On
  Iowa, where the Phase 2 report (`docs/phase-2/phase-2-report.json`) and
  PlanScore describe the same whole-county plan, ours on PlanScore's totals must
  reproduce the report's 2020 presidential seats exactly and its metrics to
  within 10⁻⁴. Colorado's Phase 2 plan only approximates the enacted one
  (D-015), so there the difference is recorded, not checked.

So ours differs from PlanScore's published values on every Colorado race, by a
factor of nearly two under the 2016 presidential vote, and agrees with them to
four decimal places on Iowa's four, each a sweep.

---

## Start here

1. `docs/CRITERIA.md` — every criterion, threshold, and metric, with a provenance
   class saying who decided it and whether it can be argued with. Read this
   before any code.
2. `prompt.md` — the task specification handed to the agent that built this.
3. `tools/check_firewall.py` — the boundary enforcement.
4. `docs/progress.md` — the full write-up: what was run, what it found, and
   every result that was later retracted and why.
5. `docs/DECISIONS.md` — D-001…D-044, each non-obvious choice logged when it was
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

This covers the code and documentation in this repository; whether it covers the
files that hold values computed from VEST's returns is not settled (below). It
does **not** cover the input data, which are not redistributed here: `data/` is
gitignored, and `tools/fetch_raw.sh` sends you to the sources. Census inputs are
public domain (17 U.S.C. §105). The election returns are the Voting and Election
Science Team's *2020 Precinct-Level Election Results*
(<https://doi.org/10.7910/DVN/K7760H>), which VEST licenses under CC BY 4.0
(<https://creativecommons.org/licenses/by/4.0/>).

`docs/first-result/ia-seats-v2.csv.gz`, the seat counts of every committed Iowa
draw, is made from version 49 of that dataset and committed with VEST's credit
and licence link: `docs/first-result/ATTRIBUTION.md` gives the credit, the
licence link, what was changed and the file's columns (D-044), and the
first-result figure credits VEST in its footer. The repository's owner has not
yet decided which licence, if any, the repository offers the counts under, or the
figure drawn from them, though `LICENSE` and `CITATION.cff` declare Apache 2.0 for the
repository as a whole. Other committed files hold values computed from the same
returns and carry no such credit, among them: metrics in the experiments' draws
files, results and figures, the Phase 2 report and the PlanScore cross-check;
numbers this README and `docs/progress.md` quote, and the tests that pin them;
and the enacted plan's district vote totals in `tests/test_partisan.py`, which
v0.1.0's archive also holds. Whether they need a credit, and under which licence
the repository offers them, is open (D-044).

`docs/CRITERIA.md` §9.1 and the VEST entry in `CITATION.cff` say VEST declares no
licence, and §9.1 says the version used was not recorded. Both licence statements
rest on the dataset's licence field on Dataverse, which is empty; VEST's Terms of
Use state CC BY 4.0, as version 48's already did when §9.1 was written, and the
counts were made from version 49 (D-043). Only the repository's owner amends
§9.1.
