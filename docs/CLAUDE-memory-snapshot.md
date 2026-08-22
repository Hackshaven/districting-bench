# Long-running research loops — start here

Earned from a ~40-hour computational research programme in an ephemeral container
that reclaimed itself ~9 times. Full reasoning and the specific failures behind
each rule: `docs/RESEARCH-LOOP-PLAYBOOK.md` in `hackshaven/districting-bench`
(copy it into any project doing similar work).

## Environment

1. **Only a pushed commit is durable.** Gitignored-in-repo is NOT — it survived
   one reclaim, then lost all 12 checkpoint files on the next. Scratchpad is
   unreliable. Running processes never survive.
2. **Commit expensive artifacts out of their cache the moment they exist**, before
   doing anything else. An hour of sampling survived only because of this.
3. **Long jobs may die *because* they are long** — if reclaim keys on session
   inactivity, any job worth backgrounding is long enough to trigger it. Size
   every unit to finish inside the shortest plausible window. A unit that cannot
   complete in one window makes *zero* progress, not slow progress.

## Architecture

4. **Split measurement from analysis.** Commit raw per-observation measurements;
   make analysis a pure function of them (`--from-committed`). A reclaim then
   costs minutes not hours, every analysis bug is fixable without re-measuring,
   and a reader can check a number by reading a file. Do this even in a stable
   environment.
5. **Checkpoint at the unit of independence** (chain / shard / pair), written
   temp-file-plus-atomic-rename.
6. **Write outputs incrementally**, never once at the end.
7. **Version datasets by name; never overwrite.** A published figure describing a
   replaced file is worse than two files.
8. **Cache keys must include every parameter that changes the result** — the
   thresholds, not just the inputs. Test the key changes under each one.

## The failure mode that matters

9. **Wrong-data paths that produce plausible numbers.** Four in one session, none
   of which crashed: a relative-vs-absolute path comparison silently reading the
   old dataset; a loader analysing 2 of 12 units while reporting a larger count;
   a sidecar filename that overwrote its own data file; `hash(str)` seeds (salted
   per process) making a determinism check non-deterministic.
   **Log which file you opened and which sample you used, in the artifact.**
   Three of the four were caught by a log line, not a test.

## Scientific practice

10. **Adversarially audit the instrument before writing up.** Two audits, 40
    defects alleged, 14 surviving independent refutation, and *both refuted my
    headline* — one with a larger number than the one I was claiming.
11. **A control must be able to fail.** Exercise it in both directions and test
    that it fails when a component is stubbed to a constant. Three "agreeing"
    tests were once one test plus two constants.
12. **Selecting on completion selects on the whole path.** A unit that died at
    step N still has N−1 valid observations. Truncate to a common prefix instead.
13. **Sample size ≠ statistical power.** If the resampling unit is the unit, more
    observations per unit buy nothing. The fixes are opposite: longer runs vs
    more runs.
14. **Convert parameters into the units the domain regulates in.** An effect can
    be real and entirely outside the range anyone is allowed to operate in.
15. **Never weaken a guard to admit your own code** — rename the code. A guard
    banning "score" in names correctly caught a function that returned no score;
    names shape what the next person builds.
16. **Apply multiplicity correction to the headline**, not beside it. Three of
    four "findings" once vanished under it, after I had already described them as
    a pattern and invented a mechanism for them.
