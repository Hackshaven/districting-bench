# What this project has produced so far

A plain-language summary for readers who have not followed the work. No prior
knowledge of redistricting or statistics assumed. The technical records are
listed at the end.

**Status: early research, and the main tool does not work yet.** Nothing here
should be used in a court case, a political argument, or any decision about a
real map.

*Last updated: 19 August 2026.*

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
population, connected districts, whole counties, reasonably compact shapes. That
computer is never allowed to see election results or racial data — it works from
population and geography alone.

Then find where the real map falls among those thousands. If it sits far outside
the normal range, that is evidence something other than the rules shaped it.

Iowa is the first test case. Its districts are built from whole counties, so
there are only 99 pieces to arrange, and state law lists the rules in priority
order. Small enough to run in seconds, and the state has already made the
judgment calls that would otherwise be ours to make.

## Where things stand

**The detector does not work.** That is the honest headline, and the run that
proved it also showed why.

Three things went wrong, and the third is the important one:

**1. It missed the gerrymanders it was supposed to catch.** Given maps rigged
badly enough to move two seats, it flagged half of them. It was supposed to
catch nearly all. Given subtler rigging worth one seat, it caught none.

**2. Ranked head to head, it got the answer backwards.** Asked to sort maps from
most to least suspicious, it rated honestly drawn maps as *more* gerrymandered
than the ones deliberately rigged. That is worse than guessing at random.

**3. The test itself was too easy, for the wrong reason.** To test a detector you
need maps you know are rigged, so the project builds them on purpose. But those
built-to-be-rigged maps came out visibly misshapen — lumpy, ragged districts
that no honest map in the comparison set resembled. A crude rule that measures
nothing but lumpiness separated the rigged maps from the honest ones perfectly,
without ever looking at a single vote.

That third point matters more than the first two. It means the test was not
measuring whether the system can spot a gerrymander. It was measuring whether
the system can spot the particular way *we* built our fake ones. A real
gerrymander drawn by a professional would look perfectly normal. Until the
practice gerrymanders look normal too, no score from this test means anything —
including a good score.

There was also an earlier, encouraging-looking result that turned out to be
worthless. A quick trial run appeared to pass two of its four targets. It had
compared against far too few maps for its own threshold to be reachable, and a
detector that simply flagged *every* map would have scored just as well. It was
recorded as a failure rather than quietly dropped.

## What got built along the way

- Software that generates the neutral comparison maps, and separate software
  that measures maps against the standard fairness, compactness, and
  administrative yardsticks — kept deliberately apart so the map-drawing half
  never sees election data.
- Software that builds gerrymanders on purpose, to serve as answer keys.
- An automated test bench that runs the whole thing from a single random seed,
  so any result can be reproduced exactly.
- About 500 automated tests covering the above.

## What we learned about Iowa itself

**Iowa's current map is not as close to the legal ideal as one might assume.**
Its four districts differ by 94 people in population. The computer found valid
maps — whole counties, all districts connected — where the gap is 23 people,
roughly four times more equal. A simple search found a 70-person map in seconds.

**Two of Iowa's own legal rules pull against each other.** The most
population-equal maps are noticeably lumpier than average. Getting the
population closer to perfect costs you tidy district shapes. Iowa's law asks for
both, in that order, and the tension between them is measurable.

**One of Iowa's four rules cannot distinguish between maps at all.** Districts
there are built from whole counties by law, so no map ever splits a county. That
criterion scores identically on every map and carries no information.

## What we got wrong, and caught

An early report from this project led with a dramatic claim: that the map-drawing
software could not reach the population equality of Iowa's real map, and that
human map-drawers had beaten the computer. It was wrong. One setting in our own
test script was misconfigured, and the software's warning about that exact
setting had been silenced by another line in the same script. Fixed, the computer
comfortably beats the real map.

The claim was caught by a deliberate review pass whose only job was to attack the
findings. The wrong version is still in the history, marked as withdrawn, rather
than quietly rewritten. The lesson recorded at the time was that the wrong
finding was *more interesting* than the truth, which is exactly why it got less
scrutiny than it deserved.

Similarly, the automated guardrail that keeps election data out of the
map-drawing code was tested and found to have at least six gaps — real-world
data files could slip through it under common naming conventions. Those gaps
were reported rather than papered over, and the guardrail's configuration was
left untouched.

## What has not been done yet

- Three planned one-off studies: which criteria actually matter, whether
  improving a map on one measure really costs you on another, and a
  demonstration of how easily each popular "fairness score" can be gamed.
- Any second state. Colorado is next in line.
- Checking our measurements against an established public scorer.
- Measuring how much the privacy noise the Census Bureau adds to its published
  population counts affects the results.
- Any interactive tool. Everything so far runs from the command line.

## The bottom line

The plumbing works, the measurements are built and tested, and the project can
now run an experiment end to end and report what happened. The thing it exists to
do — reliably tell a rigged map from an unlucky-looking honest one — it cannot do
yet.

The most defensible statement available today is a negative one: *on Iowa, this
detector is no better than chance, and here is precisely why.* The next step is
to make the practice gerrymanders indistinguishable from honest maps except in
their political effect, then measure again.

A design rule this project holds to: any output that reads as a verdict rather
than a range of possibilities is a bug. That applies to this summary too. Nothing
above should be read as a judgment about Iowa's map or anyone who drew it.

---

## Where to read the details

| Document | Contents |
| --- | --- |
| `docs/CRITERIA.md` | Every rule, threshold, and measurement, with a note on who decided it and whether it can be argued with |
| `docs/FEASIBILITY.md` | The first pass on Iowa: data, geography, and whether the approach runs at all |
| `docs/progress.md` | The test-bench results, round by round, including the failures above |
| `docs/DECISIONS.md` | Every non-obvious choice made, and why |
| `prompt.md` | The original task specification, kept unedited as a record |

Some of these documents are still in an open pull request and will appear here
once it is merged.
