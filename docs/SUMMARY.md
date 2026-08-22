# What this project has produced so far

A plain-language summary for readers who have not followed the work. No prior
knowledge of redistricting or statistics assumed. The technical records are
listed at the end.

**Status: early research.** Nothing here should be used in a court case, a
political argument, or any decision about a real map.

*Last updated: 22 August 2026.*

---

## The short version

- **The goal:** tell a rigged district map from an honest one, by comparing it
  against thousands of maps a computer draws using only the state's legal rules.
- **The detector does not work — and the reason turned out to be worth more than
  the detector.** In both states studied, honest maps already swing two seats on
  their own. To stand out, a gerrymander has to be bigger than that, and nobody
  could build one that big that was still legal and still normal-looking. There
  was nothing to test the detector against.
- **Popular "fairness scores" can be fooled.** There is a perfectly legal
  Colorado map that hands one party 7 of 8 seats while scoring closer to perfect
  on a well-known fairness formula than any of 12,000 honestly drawn maps.
- **On Iowa's real, currently-in-force map, two respected fairness measures
  disagree about which party it favors.** Same map, same election, opposite
  answers. This is the single clearest argument for the way the project is built.
- **The criteria mostly do not trade off against each other.** Redistricting law
  assumes that improving a map one way costs you another. Across every pairing in
  two states, almost none of that showed up — with one exception that appeared in
  both states.
- **The famous tension between equal population and tidy shapes is real, but
  lives entirely outside the law.** Inside the range a congressional map may
  legally occupy, tightening population equality costs nothing measurable.
- **Four separate "passing" scores turned out to mean nothing**, each for a
  different reason. All four are written down rather than quietly fixed.
- All three planned side studies are now finished, and every result can be
  regenerated from data files kept in the repository.

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

## Why the detection phase stopped

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

## What the three experiments found

All three are now complete. Each was run once and written up, rather than tuned
until it produced a nicer answer.

### 1. Can a popular "fairness score" be fooled?

Yes, badly.

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

### 2. Do the criteria really trade off against each other?

Redistricting law assumes they do: make a map more compact and you must give up
something else. A recent law review article, using billions of computer-drawn
maps, argues the tradeoffs are mostly imaginary. The project tested that on
20,000 of its own maps, checking every pairing of seven criteria in both states.

**Almost nothing traded off.** In Colorado, 20 of 21 pairings showed no tradeoff
at all. In Iowa, 10 of 15. Nothing involving compactness, county splits, or
population equality traded against anything in Colorado.

**One relationship survived, in both states:** pushing for more competitive
districts drags one of the fairness measures away from zero. It is strong in
Iowa and mild in Colorado. The reason is arithmetic rather than politics — in a
state that leans heavily one way, forcing lots of close races has to pull the
typical district away from the statewide average, and that gap is exactly what
the measure reports.

Two things make this result more trustworthy than the first attempt at it:

- **The obvious objection was tested and ruled out.** Those two measures are both
  built from the same underlying numbers, so a correlation between them could be
  pure arithmetic, true of any list of numbers and meaningless about maps. So the
  arithmetic was measured on its own, with no maps involved. It pushes the
  *opposite* direction. The observed relationship is therefore not an artifact of
  how the two measures are defined.
- **Every "we found nothing" comes with a measurement of what it could have
  missed.** Known relationships of increasing strength were injected into the
  real data to find out how weak a signal each test could still see. Colorado's
  tests go blind below a certain strength, Iowa's below a slightly higher one. So
  "no tradeoff" here means "no tradeoff stronger than this", with the number
  stated — not "we looked and there was nothing".

A statistical correction for the sheer number of comparisons being run was also
applied, which knocked five borderline results down to nothing.

The honest verdict: this agrees with the article's direction, from 20,000 maps
rather than fourteen billion, on two states rather than fifty.

### 3. Which criteria actually matter?

The instruction was to vary each criterion's weight and report which ones really
bind. Two things had to be resolved first.

Neither state uses weights. Iowa and Colorado both rank their criteria in order
of priority instead. So the question was answered the other way the instruction
allows: by varying each criterion's *tolerance* — how tight you set the rule.

And only one criterion has a tolerance anyone has actually written down.
Population equality has a legal standard: a court struck down a map that was off
by 0.6984%, which for Iowa works out to about 5,570 people. Compactness has no
threshold anywhere. Neither does competitiveness. A rule with no stated line
cannot bind, because binding means being on the wrong side of a line.

**The headline finding is about that one criterion with a real line, and it is
clean:**

> Push population equality tighter and tighter, and the maps do get less compact
> — but every step where that effect is measurable sits **at or past the point
> where a congressional map becomes unconstitutional.** Inside the legal range,
> tightening population equality has no detectable effect on compactness at all.

The tradeoff everyone assumes exists is real. It just lives entirely in territory
no state is allowed to use.

Two side results came out of the same sweep. Chains of map-drawing fail 75% of
the time at the very tightest setting and never at looser ones — so that
criterion binds on the *search* long before it binds on the maps. And the
resulting maps track whatever tolerance you set almost exactly, meaning the
number a state writes into its law effectively determines the outcome.

On the other criteria, the ranking is thinner than it looks. In Colorado only two
of seven push the others around: competitiveness, and one fairness measure. Iowa
shows more, but Iowa's measurements are about twice as noisy, so some of "Iowa
binds harder" is just Iowa being measured less precisely. And Iowa's own ranking
is dominated by criteria that **Iowa law forbids anyone from considering** — so
that table describes what those criteria would do if Iowa used them, not a
ranking of Iowa's actual rules.

One word was deliberately removed from this experiment's report. The instruction
asked which criteria are "decorative." The answer is that none of them are: a
criterion that pushes nothing else around still changes which maps survive.
Colorado's compactness rule at its strictest throws away 90% of the maps. It
reshapes the pool without displacing any other criterion, and a
displacement-based measurement cannot see that. The report now says
"non-displacing on this collection of maps," which is what was actually measured.

---

## The other half: reporting instead of scoring

Alongside the detection work, the project was told to build every standard
measurement fully — and optimize toward none of them. Most of the measurements
already existed. What was missing was the thing that makes them useful: somewhere
they all appear together, with their disagreements pointed out rather than
resolved.

That now exists, and it has one deliberately strange feature. The report contains
a field for a combined score, and that field is permanently empty, with the
reason attached to it. An absent field reads like an oversight; an empty one with
an explanation reads like a decision.

**On Iowa's real, in-force congressional map, the report shows this:** the
efficiency gap says the map favors one party. The mean-median measure says it
favors the other. Both are published, respected definitions of partisan fairness.
Same map, same election, opposite answers. On top of that, a separate check
warns that only one of the two can be trusted in a state where one party
dominates statewide — and the report shows the untrustworthy one anyway, labeled,
rather than hiding it.

No single-number report could show any of that. It is the whole argument for how
this project is built, sitting on a real map rather than a constructed one.

Colorado's real map shows the same problem in a different place: its five
compactness measures span a range of 0.476 out of a possible 1.0. Which measure a
compactness rule names decides which maps pass it.

Three other things were finished here:

- **Ballot styles**, which nobody else computes and which election officials care
  about a great deal. Every distinct combination of districts a voter can live in
  means a separate ballot to print, proof, and hand out correctly. Counting only
  congressional districts, the answer was a meaningless 4 for Iowa and 8 for
  Colorado. Overlaying the state house and senate maps as well gives **62 for
  Iowa and 177 for Colorado** — meaning Colorado's map costs about half again as
  many distinct ballots per voter. That is an objective administrative cost with
  no political direction at all.
- **Municipalities.** Colorado's map splits 4 of its 152 cities. Iowa has none to
  split, because no Iowa county has half its area inside a single city. The
  report distinguishes "zero splits" from "zero splits because there is no data"
  — those look identical in a table and mean opposite things.
- **Communities of interest** are supported as something a user can supply, and
  the project deliberately ships none. Any choice of definition would be a
  political judgment made silently on the user's behalf. The report says the
  criterion is supported and unsupplied, in a field, so nobody assumes it was
  forgotten.

---

## What got built along the way

- Software that generates the honest comparison maps, and separate software that
  measures maps against the standard fairness, shape, and administrative
  yardsticks — kept deliberately apart so the map-drawing half never sees
  election data.
- Software that builds gerrymanders on purpose, to serve as answer keys.
- A reporting surface that shows every measurement side by side and refuses to
  combine them.
- Two complete state datasets, plus municipal and state-legislative map layers.
- Committed data files holding every measured map from the experiments, so every
  published number can be recomputed without re-running an hour of sampling.
- About 640 automated tests covering the above.

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

**One of Iowa's four legal rules cannot distinguish between maps at all.**
Districts there are built from whole counties by law, so no map ever splits a
county. That criterion scores identically on every map and carries no
information. The project reports it as "cannot be measured here" rather than as
"no problem found," which is a distinction it makes a point of throughout.

**Colorado is the better laboratory.** Its bigger, finer-grained map produces
comparison maps that are nearly all different from one another, with no failures
— where Iowa's small county grid produces far fewer usable ones and crashes
regularly. Most of the technical problems that dominated the early rounds simply
vanished on the larger state.

**Iowa's comparison maps now mix properly, and the fix was counterintuitive.**
There is a standard check for whether a random sampling process has run long
enough to be trusted. Iowa was failing it. The fix was not more chains of
map-drawing but *longer* ones: six long chains scored far better than eight short
ones. Short chains agree with each other because none of them has gone anywhere
yet, and that false agreement reads as success. The measurement improved roughly
six-fold. The published findings still rest on the older, shorter collection until
they are recomputed on the new one.

---

## What we got wrong, and caught

This project's record of its own mistakes is deliberate, and it is long.

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

**An experiment's headline was refuted by its own audit, using a bigger number
than the one it claimed.** The tradeoff study asserted that a certain effect was
invisible to a whole class of method. The audit found the effect using that exact
class of method, at a larger size than the study's own headline figure — and
found that the study's published data file already contained a version of it. The
refuted claim is kept verbatim rather than rewritten.

**A data join that looked perfect was quietly wrong.** Matching Colorado's
election results to its map units by identifier reported zero unmatched units
while silently dropping 215,617 votes — and the dropped votes leaned one way, so
the error had a political direction. It was caught by checking that the totals
still added up, not by checking that the identifiers matched.

**The safety checks were themselves unreliable.** One experiment refuses to run
until it has proved each of its tests can produce both a positive and a negative
answer. Those proofs were drawing a fresh random number every time the program
started, so they could pass on the day you looked and fail on the day you did
not. As the commit recording it puts it: this is exactly the defect the checks
exist to prevent, one level up.

**A filename bug destroyed an hour of computed results.** Writing a small
metadata file next to a data file, the code built the second name from the first
by text replacement — and for one filename the replacement did nothing, so the
metadata was written directly over 57,553 rows of sampled maps. Recovered from
checkpoints, committed, and covered by tests that try five filename shapes.

**Code was pushed with five failing tests**, after running a narrower check and
reporting that it passed. A reviewer found it.

**The experiments were run in the wrong order.** The instructions said to run the
fairness-score experiment early because it was the result most likely to change
how everything else got built. It was run last, and the cost was visible: it was
built without a safeguard the detection work had already shown was necessary.

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
- **Some conclusions rest on far fewer independent maps than the raw counts
  suggest.** Consecutive maps in a chain resemble each other, so 12,000 maps can
  carry only a few dozen genuinely independent ones on the measurements that
  matter most. This is the largest single weakness in the tradeoff results, and
  more statistical tests do not fix it.
- **Colorado's real map, as approximated here, is not legally valid at the
  precision used** — one district comes apart into two pieces. That is a known
  side effect of working with whole precincts.
- **Every result here comes from one election cycle and one map-drawing method.**
  That method favors compact maps by design, so "compactness does not trade off"
  may hold only inside the range of maps it is willing to visit.

---

## What has not been done yet

These are the project's own stated next steps, taken from its working record —
not recommendations added by this summary.

- Recomputing the finished experiments on the better-mixed collection of maps.
- Checking our measurements against an established public scorer.
- Measuring how much the privacy noise the Census Bureau adds to its published
  population counts affects the results.
- The like-for-like comparison that would make Iowa's 1% number meaningful.
- Any interactive tool. Everything so far runs from the command line.

---

## The bottom line

The system works as an instrument. It can build two states, generate tens of
thousands of legal maps, measure them a dozen ways, report every measurement side
by side, and refuse to collapse them into a verdict. What it cannot do is the
thing it was named for: it cannot reliably tell a rigged map from an unlucky
honest one.

Three results stand on their own, and together they are worth more than a working
detector would have been:

1. **Single-number fairness scores can be fooled** by legal, ordinary-looking maps
   that hand one party nearly every seat — and on a real enacted map, two
   respected scores flatly disagree about who benefits.
2. **How detectable a gerrymander is depends on the state's own geography**
   rather than on how clever the detector is, which means a national standard
   stated in seats cannot work.
3. **The tradeoffs redistricting law is built around are mostly not there** in
   these two states — and the most famous one, equal population against tidy
   shapes, only appears once you leave the range the Constitution allows.

A design rule this project holds to: any output that reads as a verdict rather
than a range of possibilities is a bug. That applies to this summary too. Nothing
above should be read as a judgment about any real map or anyone who drew it.

---

## Where to read the details

| Document | Contents |
| --- | --- |
| `docs/CRITERIA.md` | Every rule, threshold, and measurement, with a note on who decided it and whether it can be argued with |
| `docs/FEASIBILITY.md` | The first pass on Iowa: data, geography, and whether the approach runs at all |
| `docs/progress.md` | The full record: five detection rounds, all three experiments, and the reporting work |
| `docs/DECISIONS.md` | Every non-obvious choice made, and why — including the ones later reversed |
| `docs/experiment-1/`, `docs/experiment-2/` | The measured data behind the experiments, plus the audits that attacked them |
| `prompt.md` | The original task specification, kept unedited as a record |

Some of these documents are still in an open pull request and will appear here
once it is merged.
