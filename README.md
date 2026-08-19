# districting-bench

A research system for evaluating legislative districting plans: it detects
likely gerrymanders against a neutral baseline, scores plans on many criteria at
once, and makes every value judgment an explicit, changeable parameter.

**Status: exploratory. Not validated. Do not use for litigation, advocacy, or
map adoption.**

---

## First result

![Iowa's neutral seat distribution](docs/figures/ia-neutral-seat-distribution.png)

Over 1,820 plans drawn with no access to election data, **Iowa's neutral process
spans 0–2 Democratic seats of 4, and a 2-seat outcome is 43% of the distribution.**

The consequence is a limit, not a score. Detectability is bounded below by the
width of the neutral distribution, and that width is a property of the state rather
than of the method. A detection target stated in absolute seats — such as
`docs/CRITERIA.md` §8's "≥0.95 true-positive rate at a 2-seat shift" — asks a
detector to separate an outcome from its own null, and is unreachable on a
four-district state whose null already spans two seats.

Iowa's enacted plan returns 0 D seats, which occurs in 1.0% of this ensemble. That
comparison is **not yet a finding**: the reference is not held to the 94-person
population equality the enacted plan meets, so it is not like-for-like. See
`docs/progress.md`.

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
or worked around.** A change to the firewall config invalidates every result
produced after it.

```
src/generate/     population + geometry only. May not import from any sibling.
src/evaluate/     partisan + demographic metrics. Downstream only.
src/adversarial/  deliberately partisan: builds known gerrymanders for testing.
src/detect/       compares a plan to an ensemble. May import from all of the above.
```

Everything inside each package is an open design question. The boundary between
them is not.

---

## Start here

1. `docs/CRITERIA.md` — every criterion, threshold, and metric, with a provenance
   class saying who decided it and whether it can be argued with. Read this
   before any code.
2. `prompt.md` — the task specification handed to the agent that built this.
3. `tools/check_firewall.py` — the boundary enforcement.

---

## Scope

First target is Iowa congressional districting: 99 whole counties, and Iowa Code
Chapter 42 supplies an explicitly ordered criteria list, which removes our
discretion over the value choices that would otherwise be ours to make. Precinct-
level states come later, if at all.

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

## License

TBD before any public release.
