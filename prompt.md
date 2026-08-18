# Task specification

Committed as the reproducibility record. This is what was asked for; the repo is
what came back. Preserved verbatim — do not edit to match what got built.

---

Build districting-bench: a system that scores districting plans against
explicitly-stated criteria, detects likely gerrymanders against a neutral
baseline, and generates alternatives — with every value judgment surfaced as a
parameter rather than buried in a scoring function.

**Read `docs/CRITERIA.md` first.** It is authoritative for every criterion,
threshold, metric, and provenance class. Where it disagrees with something you
find online, it wins — the unresolved questions in it are deliberate and
documented. Also read `README.md` and the four `src/*/README.md` files.

## Framing, and do not drift from it

There is no neutral districting criterion. Compactness, county integrity,
competitiveness, and proportionality are all value choices with predictable and
differing partisan consequences. The goal is **not** an unbiased system — no such
thing exists. The goal is a system where every choice is explicit, parameterized,
swappable, and logged.

If you find yourself writing a function called `fairness_score()` that returns
one number, stop.

## Do not build an ensemble engine from scratch

Use GerryChain (Python, MGGG) or `redist` (R, ALARM Project). Both are
court-tested. Data: ALARM 2020 Redistricting Data Files, VEST precinct-level
election data, Redistricting Data Hub. Cross-check your metric implementations
against PlanScore on plans it has already scored.

2020 Census PL 94-171 data carries differential-privacy noise from the TopDown
algorithm, with the largest relative error in small-population units. Quantify
its effect on your metrics; do not ignore it. See `docs/CRITERIA.md` §9.

## The firewall — pre-built, non-negotiable

`tools/check_firewall.py` and `tools/firewall.yaml` were written before any
implementation code, deliberately, so that the thing being graded did not build
its own grader.

**Do not modify, relax, or work around either file.** If a check fails, fix the
code. If you believe the config is genuinely wrong, stop and say so rather than
editing it.

The package boundary in `src/` is specified because the firewall requires it.
Everything *inside* each package is yours to design — module layout, data
structures, libraries, test framework. I have deliberately not prescribed any of
it.

## Start with Iowa

Iowa congressional districts are built from 99 whole counties, and Iowa Code
Chapter 42 supplies an explicitly ordered criteria list, which removes our
discretion over value choices that would otherwise be ours. Tiny adjacency graph,
ensembles in seconds, full loop closable in an evening.

**Get the complete loop working on Iowa before touching any precinct-level
state.** Do not spend time on shapefile plumbing, VTD-to-block crosswalks, or
VEST joins until Iowa works end to end. That work is real but teaches nothing
about the method.

Colorado is the second target when Iowa is done — ordered criteria plus a rare
explicit competitiveness mandate (Amendments Y and Z).

## Phase gate

### Phase 1 — OPTIMIZE THIS IN A LOOP: detection

Ground truth is free here because you manufacture it.

- **Adversarial generator** (`src/adversarial/`): optimize a plan to maximize
  seat share for a chosen party, subject to passing every legal constraint. That
  map is a known gerrymander with known intent and known magnitude.
- **Null cases, equally important**: neutrally-drawn maps that look biased purely
  from political geography (Chen & Rodden — see `docs/CRITERIA.md` §5.4). The
  detector must **not** flag these. A detector that fires on every state with
  clustered urban population has learned where Democrats live, not gerrymandering.
- **Score a full confusion matrix**: true positive rate on planted gerrymanders,
  false positive rate on null cases, and detection threshold as a function of
  gerrymander magnitude. Report the smallest seat shift the detector reliably
  catches — that number is the honest headline for the whole system.
- Regenerate scenarios with fresh random seeds every round so nothing overfits to
  a fixed case.
- Report ensemble convergence (Gelman–Rubin PSRF, 1.00–1.01 target) every round.
  A detector built on an unconverged ensemble is measuring the sampler.

Gates are in `docs/CRITERIA.md` §8. Loop until the confusion matrix stops
improving or I stop you.

### Phase 2 — BUILD BUT DO NOT OPTIMIZE: scoring and generation

Implement fully and unit-test fully: efficiency gap, mean-median, declination,
partisan bias, seats-votes curves, compactness (Polsby-Popper, Reock,
Schwartzberg, convex hull, cut edges), county and municipality splits,
community-of-interest splits, and the administrative metrics in
`docs/CRITERIA.md` §7.

Do **not** optimize toward any of them. Each is provably gameable in isolation —
see `docs/CRITERIA.md` §5.2. Optimizing toward a gameable metric produces a
gerrymander that scores clean.

Report all metrics side by side, always, with disagreements between them
highlighted rather than resolved.

Compute and report **ballot styles per 10,000 voters** — the count of unique
district tuples a plan produces. It is objective, administratively meaningful,
orthogonal to every partisan measure, and almost nobody computes it. Treat it as
a first-class output, not an afterthought.

## Three experiments — measure once

These are measurements, not optimization loops. Run each once, produce a plot and
a written finding, do not iterate to improve the result.

**Run experiment 3 early, in parallel with Phase 1.** It is largely independent
of the detection loop and it is the result most likely to change how the rest is
built.

1. **Criteria sensitivity.** Vary each criterion's weight and tolerance across
   its plausible range; report which ones actually bind and which are decorative.
   Output a ranked list.
2. **Tradeoff frontier.** Stephanopoulos, *Redistricting Without Tradeoffs*, 126
   Colum. L. Rev. 1001 (2026), finds tradeoffs among criteria are generally weak
   to nonexistent, using ~14 billion maps. Test on your states. One recent paper
   against decades of contrary assumption — treat as hypothesis, not premise. If
   it holds, much of redistricting law's framing is empirically wrong, which is
   the most interesting finding available in this project.
3. **Metric gameability, adversarial.** For each fairness metric, search for a
   plan that scores well on it while producing a lopsided seat outcome.
   Reproduce arXiv:2409.17186 on your own data. This is the honest demonstration
   of why single-metric scoring must never ship.

## Legal constraints — configuration, not hardcode

Full treatment in `docs/CRITERIA.md` §1, §2, §4. Summary of what must be
parameterized per jurisdiction:

- Population equality: near-zero for congressional (*Karcher*), ~10% total
  deviation safe harbor for state legislative (*Brown v. Thomson*).
- Contiguity, including water-contiguity edge cases that break naive adjacency
  graphs. Expect disconnected components from raw shapefile topology in nearly
  every state; fix before anything else.
- Race may not predominate (*Shaw*, *Miller*, *Cooper*).
- VRA §2 as substantially narrowed by *Louisiana v. Callais* (Apr. 29, 2026).
  **Read the opinion, not summaries** — coverage is heavily polarized in both
  directions. Three changes matter algorithmically; see `docs/CRITERIA.md` §4.2.
- Partisan gerrymandering is nonjusticiable in **federal** court (*Rucho*, 2019).
  State courts split. Encode the available remedy per jurisdiction; never produce
  output implying a cause of action that does not exist where the reader lives.

## Deferred, with reasons

- **Ecological inference and racially polarized voting analysis.** Large lift,
  little methodological learning for a first build. Document as a known omission
  and state why it matters. See `docs/CRITERIA.md` §4.3.
- **Communities of interest as an objective function.** Support COI as an input
  layer that reports splits. Never let the optimizer chase a COI score —
  self-reported COI data systematically favors communities organized enough to
  submit it, which is the opposite of what the criterion exists to protect.

## Output design

The primary artifact is never a single map or a single score. It is a
distribution with the plan under review located inside it, plus a plain-language
statement of which criteria were prioritized and what that choice cost on every
other dimension. Any user must be able to change the priorities and re-run.

Any output that reads as a verdict rather than a distribution is a bug.

## Two interfaces, same core

- **Interactive**: explore ensembles, locate a plan in the distribution, adjust
  criteria weights and watch the picture move. For a human building intuition and
  for checking that metrics track what a reader would call a problem.
- **Headless bench**: runs N seeded scenarios, writes `bench-results.json` plus
  plots to disk. Deterministic. This is what critics read. Never screenshot a live
  interface for scoring.

## Progress page

Live, updated as work proceeds:

1. Confusion matrix over rounds — the primary signal.
2. Detection threshold curve: detection rate vs. gerrymander magnitude in seats.
3. Ensemble distribution with the plan under review marked, per metric.
4. Metric disagreement matrix: rank correlation between compactness measures, and
   between fairness measures, on the current ensemble. Low correlation means the
   choice of metric is doing real work and must be surfaced to users.
5. PSRF convergence trace.
6. The three experiment plots as they complete.
7. Firewall status: last check result and whether `tools/firewall.yaml` has been
   touched.

Item 4 is a correctness check disguised as a visual — if all your compactness
measures correlate above 0.95, either the state has simple geography or you have
implemented the same measure five times.

## Loop mechanics — Phase 1 only

Break the work into the smallest pieces that can be improved and judged
separately. You decide the decomposition; I have not prescribed it.

Each piece gets a builder and a separate critic with fresh context. Critics read
`bench-results.json` and the rendered plots — never the builder's reasoning or
explanation. When a metric fails its gate, name the single largest contributor
and send it back.

Keep a decision log at `docs/DECISIONS.md`: every non-obvious choice, the
alternatives considered, and why. Especially every place where you had to make a
value judgment `docs/CRITERIA.md` did not settle for you — those are the entries
that matter most, and they are candidates for promotion into CRITERIA.md as new
`VALUE`-class rows.

Use subagents. No fixed round count. Do not prescribe or ask me for the
architecture — decide it.
