# Long-running research loops: an architecture that survives

Written after a ~40-hour research programme in an ephemeral container that
reclaimed itself roughly nine times. Every rule here was paid for by a specific
failure, and the failures are named so the rules can be argued with rather than
taken on faith.

This is about **computational research loops** — sampling, measurement, analysis,
write-up — run by an agent in an environment it does not control. It is not
specific to redistricting.

---

## Part 1 — The environment constraint

### 1.1 Establish the durability hierarchy before doing any expensive work

Measured, not assumed:

| | survived reclaims |
| --- | --- |
| Pushed commits | **always** — 72 of 72 |
| Committed-but-unpushed | untested; do not rely on it |
| Gitignored files inside the repo | **no** — survived one reclaim, then 0 of 12 |
| Scratchpad / tmp | unreliable — partial, silent |
| Running processes | **never** |

The middle row is the trap. Gitignored checkpoints survived one restart, which
taught the wrong lesson; the next restart destroyed all twelve. **An hour of
sampling survived only because it had been committed out of the checkpoint cache
beforehand.**

> **Rule: the only durable thing is a pushed commit. Everything else is a cache.**

### 1.2 Long jobs may die *because* they are long

If reclaim keys on session inactivity rather than process activity, then any job
long enough to be worth backgrounding is also long enough to trigger the reclaim
that kills it. Every observed failure fit this: a 90-minute sample, two 40-minute
analyses. Short jobs never died.

> **Rule: size every unit of work to finish inside the shortest plausible window,
> and assume anything longer will never finish at all.**

A unit that cannot complete in one window does not make slow progress. It makes
**zero** progress, forever, however many windows pass. One re-sample banked
nothing across ninety minutes for exactly this reason, while an identical job at
40% the length completed every chain.

---

## Part 2 — The architecture

### 2.1 Separate *measurement* from *analysis*, and commit the measurements

The single highest-leverage change. Sampling is expensive, irreproducible without
the original environment, and slow. Analysis is cheap, frequently rerun, and the
thing you actually iterate on.

Commit the raw per-observation measurements, then make analysis a **pure function
of committed files**:

```
tool.py                 # samples, writes measurements
tool.py --from-draws    # re-derives every result from committed measurements
```

Three separate wins, and only the first was the motivation:

- A reclaim during analysis costs minutes, not hours.
- Every analysis bug — and there were four — is fixable without re-sampling.
- **A reader can verify a published number by reading a file** instead of
  reproducing an hour of CPU with a working sampler. This is the reason to do it
  even in a stable environment.

### 2.2 Checkpoint at the natural unit of independence — *durably*

Find the unit that shares no state with its siblings — a chain, a shard, a
document, a pair — and checkpoint per unit. Write with temp-file-plus-atomic-
rename so a half-written file is never mistaken for a complete one.

> **Correction.** An earlier draft of this document ended here with "then a
> reclaim costs one unit, not the run." **That is false, and I proved it twice
> after writing it.** A checkpoint only bounds the loss if the checkpoint itself
> outlives the failure. Both times I wrote one to a gitignored directory, and both
> times a reclaim destroyed every checkpoint and the entire run with it — twelve
> sampling checkpoints, then, hours later, the cache I had added specifically to
> stop that happening.

**Crash-safe is not reclaim-safe.** These are different guarantees and it is easy
to build the first while believing you have the second:

| failure | survived by |
| --- | --- |
| process crash, OOM, killed job | any on-disk checkpoint |
| **container reclaim / host loss** | **only a pushed commit** |

A gitignored checkpoint buys you the first row. If the second row is your actual
failure mode — and in an ephemeral environment it is — the checkpoint is
decoration.

**So: track the checkpoints, and push them while the run is going.** They are
usually tiny; the cache that cost this project four re-runs was 1.1 KB per entry
and under 100 KB in total, so there was never a size argument for excluding it.
Default to committing them, and size the artifact to make that possible rather
than reaching for `.gitignore`.

### 2.2a Bank progress on a timer, not only at the end

A checkpoint written to a tracked path still only survives if something commits
it. Run a background loop alongside the job:

```bash
while pgrep -f "$JOB" >/dev/null; do
  if <new results since last time>; then
    git add "$CACHE_DIR" && git commit -q -m "Bank N results" && git push -q  # with retry
  fi
  sleep 180
done
```

Then a reclaim costs *the units in flight at that moment*, which is the guarantee
the earlier draft claimed without earning.

**The meta-lesson, and the reason this correction is kept rather than edited
away:** Part 1 of this document already said "the only durable thing is a pushed
commit; everything else is a cache." I wrote that sentence and then, four hours
later, built a cache that assumed otherwise — the same mistake that had already
cost twelve checkpoints. **Stating a rule is not applying it.** The rule needs to
fire at a specific moment: *whenever you create a new artifact directory, before
writing anything to it, decide whether it is tracked.* That is why it is a
checklist item in Part 5 and not only a principle here.

### 2.3 Key every cache by everything that changes the result

Not just the inputs. Include the thresholds, the parameters, the code-version-
relevant constants. A cached verdict computed under a different alpha is not the
same verdict, and silently reusing it mixes two configurations inside one table
with nothing to show it happened.

Test that the key changes under *each* parameter individually.

### 2.4 Write results incrementally, never once at the end

A file holding one finished state is worth far more than a file that would have
held two. Two runs were destroyed after finishing their computation but before
writing their output.

### 2.5 Version datasets; never overwrite one in place

When you re-measure, keep both and address them by name (`v1`, `v2`). A published
figure describing a file that has been replaced underneath it is worse than two
files on disk. It also lets you diff the old and new conclusions, which is where
the interesting result usually is.

---

## Part 3 — The failure mode that matters most

**Wrong-data paths that produce entirely plausible numbers.** Four occurred in one
session, and not one of them crashed, errored, or produced an obviously wrong
value:

1. A path comparison of a *relative* against an *absolute* path silently took a
   fallback branch and re-analysed the **old** dataset while the run was labelled
   with the new one throughout.
2. A loader filtered on "completed" units and analysed **2 of 12** while reporting
   a larger draw count than the run it replaced — in an exercise whose entire
   purpose was raising the sample size.
3. A sidecar filename derived by substring replacement became a no-op on an
   unexpected name, so the metadata file **overwrote the data file**.
4. Seeds derived from `hash(str)` — salted per process — made a determinism check
   non-deterministic, so it passed or failed by luck.

> **Rule: log which file you opened and which sample you used, in the artifact,
> every time.** Three of the four were caught by a log line naming the file, not
> by a test. Tests check the logic you thought of; the log catches the input you
> did not.

Corollary: an artifact should state its own provenance — sample size, source
file, parameters, subset rule — so that a wrong-data run is visible in its own
output rather than only in the code that produced it.

---

## Part 4 — Scientific practice that caught real defects

These are not generic advice. Each one refuted a claim I had already written down.

### 4.1 Adversarial audit beats testing for measurement code

Two multi-agent audits, each attacking along independent lenses with every
allegation handed to a separate refuter told to default to *refuted*. Between
them: 40 defects alleged, 14 surviving refutation, and **both refuted the
headline claim** — one of them using a *larger* number than the one being claimed.

Tests verify the properties you thought to check. An adversary looks for the
property you assumed.

### 4.2 A control must be able to fail

Any check gating whether an experiment may run should be exercised against data
where the answer is known — in **both** directions — and the pipeline should abort
when it cannot produce the expected verdict. Then test that the control *fails*
when a component is stubbed to a constant.

Discovered the hard way: three tests reported agreement, and two of them were
constants that could not have disagreed. The finding was one test wearing three
hats. The fix was real but covered the wrong regime, and the same defect recurred
in the gap — a coarse, discrete variable the synthetic controls never generated.

### 4.3 Selecting on completion selects on the whole path

Excluding units that failed partway is not conservative. A unit that died at step
N is excluded for a property of step N, while its first N−1 observations are as
valid as any others. Truncating everything to a common prefix selects on nothing,
because the prefix was drawn before any unit knew it was going to fail.

This inverted a rule I had justified with the *opposite* argument — that survivors
are a biased subset. The argument was right; it pointed the other way.

### 4.4 Distinguish sample size from statistical power

Raising observations-per-unit improved effective sample size five-fold and left
detection power **slightly worse**, because the resampling unit was the *unit*,
not the observation, and the unit count never changed. More observations per unit
add no bootstrap units.

The two goals can be in direct tension: the fix for one (longer runs) is the
opposite of the fix for the other (more runs). Know which you are buying.

### 4.5 Convert parameters into the units the domain actually uses

An effect that looked like the largest in the project turned out to exist only
outside the range the governing legal standard permits. Real, and inert. Nothing
in the statistics revealed that — only converting the sweep parameter into the
units the authority regulates in.

### 4.6 Name things so your own guards catch them

A structural test banning any definition containing "score" or "fairness" caught a
new entry point named `score_plan`. It returned no score. **The guard was right
anyway**: names shape what the next person builds, and whoever maintains
`score_plan` will eventually make it live up to its name.

> **Rule: never weaken a guard to admit your own code.** That is the same move the
> project forbids for its security config. Rename the code.

### 4.7 Correct for multiplicity, and apply it to the headline

Running one test per pair across dozens of pairs at α = 0.05 produces false
positives of the same order as the signal. Computing the correction and reporting
it *beside* an uncorrected verdict table is not applying it. Three of four
"findings" in one state did not survive correction — with rank correlations of
−0.02, +0.006 and −0.08 — and I had already described them to the user as a
coherent pattern with a mechanism I had invented for them.

---

## Part 5 — The checklist

Before starting a long research loop in an uncontrolled environment:

- [ ] Measure the durability hierarchy. Do not assume gitignored survives.
- [ ] Split measurement from analysis; make analysis a pure function of committed
      files, with a `--from-committed` path.
- [ ] Identify the unit of independence; checkpoint per unit, atomically, **to a
      tracked path**. Ask at the moment you create the directory: is this
      gitignored? If yes, it does not survive a reclaim and it is decoration.
- [ ] Run a banker loop that commits and pushes checkpoints on a timer while the
      job runs. A tracked checkpoint nobody commits is still lost.
- [ ] Time one unit. If it exceeds the shortest plausible window, make it smaller
      — not slower to lose.
- [ ] Write outputs incrementally.
- [ ] Version datasets by name; never overwrite.
- [ ] Cache keys include every parameter that changes a result.
- [ ] Every artifact records its own provenance: source file, sample size, subset
      rule, parameters.
- [ ] Every gating control is tested in both directions, and tested to fail.
- [ ] Commit expensive artifacts out of caches the moment they exist, before
      doing anything else with them.
- [ ] Plan an adversarial audit of the instrument *before* writing up results.
