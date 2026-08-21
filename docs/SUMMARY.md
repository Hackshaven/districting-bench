# What this project has produced so far

A plain-language summary for readers who have not followed the work. No prior
knowledge of redistricting or statistics assumed. The technical records are
listed at the end.

**Status: early research. The first phase is finished and ended in a negative
result.** Nothing here should be used in a court case, a political argument, or
any decision about a real map.

*Last updated: 21 August 2026.*

---

## The short version

- **The goal:** tell a rigged district map from an honest one, by comparing it
  against thousands of maps a computer draws using only the state's legal rules.
- **The detector does not work — and the reason turned out to be worth more than
  the detector.** In both states studied, honest maps already swing two seats on
  their own. To stand out, a gerrymander has to be bigger than that. Nobody could
  build one that big that was still legal and still normal-looking, so there was
  nothing to test the detector against.
- **Popular "fairness scores" can be fooled.** There is a perfectly legal
  Colorado map that hands one party 7 of 8 seats while scoring closer to perfect
  on a well-known fairness formula than any of 12,000 honestly drawn maps.
- **How detectable a gerrymander is depends on the state, not on the detector.**
  A national rule of thumb stated in seats cannot work.
- **Four separate "passing" scores turned out to mean nothing**, each for a
  different reason. All four are written down rather than quietly fixed.
- Of three planned side studies, one is finished, one is re-running, and one has
  not started.

The rest of this document explains each of those.

---

## The problem

Every ten years, states redraw the district boundaries that decide who elects
which representative. Whoever draws those lines can settle a lot of elections in
advance just by choosing where the boundaries go. That is gerrymandering.

The hard part is proving it happened. A map that favors one party might have
been drawn that way deliberately — or it might just reflect where people live.
Voters are not spread evenly across a state, so even a scrupulously honest map
can come out lopsided.

## The idea being tested

Rather than argue about whether a map *looks* fair, have a computer draw
thousands of maps that follow only the state's written legal rules: equal
population, connected districts, whole counties where required, reasonably
compact shapes. That computer is never allowed to see election results or racial
data — it works from population and geography alone.

Then find where the real map falls among those thousands. If it sits far outside
the normal range, that is evidence something other than the rules shaped it.

Two states have been built: Iowa, with 4 districts made of whole counties, and
Colorado, with 8 districts made of voting precincts.

### A few words that keep coming up

- **Compact** — a district that is a reasonable blob rather than a sprawling
  tentacle. There are five common ways to measure it and they disagree with each
  other, which is itself part of the problem.
- **Fairness score** — one of several published formulas that boil a whole map
  down to a single number meant to say whether it treats the parties evenly.
- **Competitive district** — one where the two parties are close enough that the
  seat could go either way.
- **County splits** — how many counties a map cuts through. Some states forbid
  it; others just discourage it.
- **Comparison maps** — the thousands of computer-drawn, politics-blind maps that
  everything else gets measured against.

---

## The main finding: how much luck looks like intent

The most useful thing this project has produced is not a detector. It is a
measurement of how much variation there is when nobody is trying to rig
anything.

Draw thousands of Iowa maps using only the legal rules, with no knowledge of how
anyone votes, and the number of seats Democrats win ranges from 0 to 2 out of 4.
A 2-seat outcome happens in 43% of them. Do the same for Colorado, and the range
is 4 to 6 out of 8.

**Both states have the same amount of wiggle room: two seats, with no intent
involved at all.** Doubling the number of districts did not narrow it.

That single fact reshapes the whole project. The original target was to reliably
catch a gerrymander worth two seats. But a two-seat swing is exactly what honest
chance already produces in both states. Asking a detector to flag that is asking
it to separate an outcome from ordinary luck, which nothing can do.

So the target has to move up to three seats. And there the project ran into the
wall that ended the phase.

## Why the first phase stopped

To test a detector you need maps you know are rigged. The project builds them on
purpose, subject to two conditions: the rigged map must be legal, and it must not
look strange — because a gerrymander that gives itself away by its shape is not
the adversary worth worrying about.

Under those two conditions, the map-rigging software tried 56 times, across both
states and both parties, to build a map that moves three seats.

**It succeeded zero times.**

That does not prove such a map is impossible. A better search might find one. But
it does mean the two halves of the test no longer meet: the gerrymander big
enough to stand out is bigger than the gerrymander a realistic search can build.

Rather than keep adjusting the detector until some number came back green, the
work stopped there.

**One half does work.** Telling the detector *not* to cry wolf turned out to be
the achievable half: on Colorado, checked against 24 honestly drawn maps, it
raised zero false alarms. One group of test maps was reported separately instead
of being counted in that score, because those maps had been picked using
something close to the detector's own yardstick — which would have skewed the
result whichever way it came out.

## Four times a test passed for the wrong reason

Across five rounds, one of the project's pass/fail scores came back green four
separate times without the system actually detecting anything:

1. A trial run scored perfectly because it was flagging every map put in front of
   it.
2. A threshold was set so high that, with the small number of comparison maps
   available, no map could ever have triggered it — so nothing did, and the
   false-alarm score looked excellent.
3. A rule that was supposed to check both directions was declared satisfied when
   only one direction could be checked.
4. A headline "100% success" rested on a single test case.

None of these was caught by the score itself. Each was found by asking what a
passing number would look like if the system were doing nothing at all. A score
computed on whatever test cases happen to exist will keep doing this.

---

## What the experiments found

Three one-off studies were planned. Two have been run.

### Can a popular "fairness score" be fooled?

Yes, badly, and this is the strongest positive result the project has produced.

Several published formulas claim to measure whether a map treats the parties
fairly. The experiment searched for maps that score beautifully on one of those
formulas while handing one party nearly every seat.

On Colorado it found them. The clearest example is a legal map — equal
population, connected districts, ordinary compact shapes — that gives one party
**7 of 8 seats** on 57% of the vote, while a widely used fairness score reads
essentially zero. That score is closer to perfect than any of the 12,000
honestly drawn maps it was compared against.

Other examples are sharper still:

- On a legal 7–1 map, **three of the four standard fairness scores read clean.**
  Only one of them noticed anything wrong.
- On a map giving one party **all 8 seats**, one score reported the map as
  favoring the party that won nothing, and another simply refused to produce a
  number.

The practical conclusion is the one the project was designed around: never let a
single fairness number decide anything. Report all of them side by side, and
report where a map falls among the honest ones rather than against a fixed
threshold — the two approaches disagreed, in opposite directions, on the two
states.

The experiment was also honest about its own failures. Seven searches were run;
two came back empty for good reasons, and two more claimed success that did not
survive checking — their "rigged" maps produced an outcome that honest maps
produce anyway. Those two are recorded as failures. And four of the seven maps
would not pass the project's own shape standard, which is why the single map that
does is the one the finding rests on.

### Do the criteria really trade off against each other?

Redistricting law assumes they do: make a map more compact and you must give up
something else. A recent law review article, using billions of computer-drawn
maps, argues the tradeoffs are mostly imaginary. The project set out to test that
on its own two states.

**This experiment is mid-flight and its numbers are provisional.** A first run
was completed and written up, then two of its problems turned out to be bugs in
the measuring apparatus rather than facts about maps, and its saved output was
lost. The apparatus has been rebuilt as permanent, tested code — it now checks
itself against known answers before it is allowed to touch real data — and the
run is repeating, this time scoring every map under two different elections
instead of one.

What the first run indicated, subject to that re-run:

- On Colorado, compactness and partisan fairness **do not trade off.** The most
  compact maps are just as fair as the rest.
- On Colorado, competitiveness and one fairness measure **do** trade off, and
  strongly. Forcing more close races in a state that leans heavily one way drags
  that score away from zero, for a reason that is simple arithmetic. This
  contradicts one specific sentence of the article.
- On Iowa there is a weak tradeoff, and it turns out to be entirely about one
  thing: whether Democrats win a second seat.
- On county integrity — how many counties a map cuts through — the answer is
  **"we cannot tell,"** not "no tradeoff." The map-drawing software never visits
  the range where the question is actually decided.

That last distinction is one the project insists on. "We found no tradeoff" and
"our instrument could not see" look identical in a results table and mean
completely different things.

### Which criteria actually matter?

Not run yet.

---

## What got built along the way

- Software that generates the honest comparison maps, and separate software that
  measures maps against the standard fairness, shape, and administrative
  yardsticks — kept deliberately apart so the map-drawing half never sees
  election data.
- Software that builds gerrymanders on purpose, to serve as answer keys.
- An automated test bench that runs the whole thing from a single random seed, so
  any result can be reproduced exactly.
- Two complete state datasets, Iowa and Colorado.
- About 600 automated tests covering the above.

---

## What we learned about the two states

**Iowa's current map is not as close to the legal ideal as one might assume.**
Its four districts differ by 94 people in population. The computer found valid
maps — whole counties, all districts connected — where the gap is 23 people,
roughly four times more equal. A simple search found a 70-person map in seconds.

**Iowa's current map gives Democrats zero of four seats, an outcome that occurs
in about 1% of honestly drawn maps.** This is deliberately *not* being reported
as a finding. The comparison is not like-for-like: the honest maps were not held
to the same population standard the real map meets, so the comparison is unfair
in an unmeasured direction. Doing it properly is a specific piece of future work.

**Two of Iowa's own legal rules pull against each other.** The most
population-equal maps are noticeably lumpier than average. Getting the population
closer to perfect costs you tidy district shapes.

**One of Iowa's four rules cannot distinguish between maps at all.** Districts
there are built from whole counties by law, so no map ever splits a county. That
criterion scores identically on every map and carries no information.

**Colorado is the better laboratory.** Its bigger, finer-grained map produced
12,000 comparison maps, nearly all of them different from one another, with no
failures — where Iowa's small county grid produced a few hundred usable ones and
crashed regularly. Most of the technical problems that dominated the early rounds
simply vanished on the larger state.

---

## What we got wrong, and caught

This project's record of its own mistakes is deliberate, and there are now
several.

**A dramatic early claim was wrong.** An early report said the map-drawing
software could not reach the population equality of Iowa's real map — that human
map-drawers had beaten the computer. One setting in our own test script was
misconfigured, and the software's warning about that exact setting had been
silenced by another line in the same script. Corrected, the computer comfortably
beats the real map.

**The same mistake was then made a second time, in a new costume.** A later round
concluded that a realistic-looking two-seat gerrymander of Iowa "appears not to
exist," because the search kept failing to find one. It was wrong: honest maps
produce that outcome 43% of the time. The counterexamples were sitting in the
same file the whole time. A number falling to zero is not evidence that something
is impossible until you have shown the search would have found it.

**A data join that looked perfect was quietly wrong.** Matching Colorado's
election results to its map units by identifier reported zero unmatched units
while silently dropping 215,617 votes — and the dropped votes leaned one way, so
the error had a political direction. It was caught by checking that the totals
still added up, not by checking that the identifiers matched.

**Code was pushed with five failing tests**, after running a narrower check and
reporting that it passed. A reviewer found it.

**The experiments were run in the wrong order.** The original instructions said
to run the fairness-score experiment early, in parallel, because it was the
result most likely to change how everything else got built. It was run last, and
the cost was visible: it was built without a safeguard the detection work had
already shown was necessary.

**The guardrail that keeps election data out of the map-drawing code has known
gaps.** They were found by testing it, reported rather than papered over, and
answered with a different mechanism — the map-drawing code now accepts only a
short list of approved data columns, rather than trying to blocklist every
dangerous one.

---

## What is still broken, and stays on the record

- **The practice gerrymanders are still recognizable by their shape.** A test
  looking at shape alone can still pick them out about two-thirds to
  three-quarters of the time. The goal is for it to be no better than a coin
  flip. Three rounds of work moved it from certain to three-quarters — real
  progress, short of the bar.
- **The collections of comparison maps have not fully settled.** There is a
  standard statistical check for whether a random sampling process has run long
  enough to be representative of everything it could have produced. Neither state
  passes it yet, which puts a question mark under every percentage here.
- **Colorado's real map, as approximated here, is not legally valid at the
  precision used** — one district comes apart into two pieces. That is a known
  side effect of working with whole precincts.
- **Charts from both experiments were left in temporary storage that no longer
  exists.** The numbers were all re-derived and are reproducible, but the
  original figures are gone. Committed chart-drawing code now exists so this
  cannot happen again.

---

## What has not been done yet

- The third planned study: which criteria actually constrain the outcome and
  which are decorative.
- Finishing the tradeoff re-run and replacing the provisional numbers above.
- Checking our measurements against an established public scorer.
- Measuring how much the privacy noise the Census Bureau adds to its published
  population counts affects the results.
- Any interactive tool. Everything so far runs from the command line.

---

## The bottom line

The system works as an instrument. It can build two states, generate tens of
thousands of legal maps, measure them a dozen ways, and report what it finds
without flattering itself. What it cannot do is the thing it was named for: it
cannot reliably tell a rigged map from an unlucky honest one.

Two results stand on their own, and both are more useful than a working detector
would have been. Popular single-number fairness scores can be fooled by legal,
ordinary-looking maps that hand one party nearly every seat. And how detectable a
gerrymander is depends on the state's own geography rather than on how clever the
detector is — which means a national standard stated in seats cannot work.

A design rule this project holds to: any output that reads as a verdict rather
than a range of possibilities is a bug. That applies to this summary too. Nothing
above should be read as a judgment about any real map or anyone who drew it.

---

## Where to read the details

| Document | Contents |
| --- | --- |
| `docs/CRITERIA.md` | Every rule, threshold, and measurement, with a note on who decided it and whether it can be argued with |
| `docs/FEASIBILITY.md` | The first pass on Iowa: data, geography, and whether the approach runs at all |
| `docs/progress.md` | The full record: five detection rounds, the phase-one conclusion, and both completed experiments |
| `docs/DECISIONS.md` | Every non-obvious choice made, and why — including the ones later reversed |
| `prompt.md` | The original task specification, kept unedited as a record |

Some of these documents are still in an open pull request and will appear here
once it is merged.
