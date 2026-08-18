"""Partisan fairness metrics: efficiency gap, mean-median, declination,
partisan bias, seats-votes curve.

`docs/CRITERIA.md` section 5 is authoritative here, and section 5.2 is the
reason this module is shaped the way it is: **every metric below is `VALUE`
class and every one of them is provably gameable** (arXiv:2409.17186 — plans
exist with a lopsided seat count whose metric value stays inside any reasonable
bound). So this module computes them, reports them side by side, and never
combines them. There is no ``fairness_score``. :func:`all_metrics` returns a
dict of independent numbers and deliberately provides no way to reduce it.

Nothing here optimises anything, ranks plans, or emits a verdict.

Sign conventions, all stated in full because a transposed party is the easiest
bug in this file to write and the hardest to see
=====================  ==========================================  ==========
metric                 formula as implemented                      + means
=====================  ==========================================  ==========
``efficiency_gap``     ``(wasted_D - wasted_R) / total votes``     favours R
``mean_median``        ``mean(D share) - median(D share)``         favours R
``declination``        Warrington's angle, ``2*(gamma-theta)/pi``  favours R
``partisan_bias``      ``D seat share at 50-50 minus 0.5``         favours D
=====================  ==========================================  ==========

**The directions are not uniform and this module does not silently flip them.**
Three of the four are written the way the definition in CRITERIA.md section 5.1
writes them, and partisan bias is written the way the literature and PlanScore
write it — as a seat-share advantage for the party named. Normalising all four
to a common direction would mean departing from at least one published
definition, which is worse than stating the mismatch. :data:`FAVOURS` is the
machine-readable form of the table above and is what any consumer comparing
metrics should multiply through.

The literature is not internally consistent either: several sources report the
efficiency gap with the opposite sign (positive = favours Democrats) and the
mean-median as ``median - mean``. When comparing a number here against a
published one, check the sign convention before concluding anything.

What every metric here shares, and what makes them all `VALUE` class:

* All of them use **votes cast**, not eligible voters. CRITERIA.md section 10
  lists turnout differences between districts as unmodelled, and this matters
  most for the efficiency gap, whose denominator is total votes.
* All of them reduce a real multi-candidate election to two parties. Third-party
  and write-in votes were already dropped upstream by
  ``evaluate.elections.two_party``.
* Uncontested races break every vote-share metric and are not imputed here
  (CRITERIA.md section 10).
* :func:`partisan_bias` and :func:`seats_votes_curve` require a counterfactual
  election that never happened, produced by a uniform swing whose assumption is
  stated in their docstrings.

Imports: this module imports from ``evaluate.plan`` only, which is an
intra-package import and permitted (``tools/firewall.yaml`` sets
``evaluate.allowed_imports = []``, and ``check_firewall.py`` exempts a package
importing from itself). It imports nothing else from ``src/``.
"""
from __future__ import annotations

import math
import statistics
from typing import Mapping, Sequence

from evaluate.plan import Plan, aggregate

Votes = Mapping[str, int]

#: The four asymmetry metrics, in the order they are reported.
METRICS: tuple[str, ...] = (
    "efficiency_gap",
    "mean_median",
    "declination",
    "partisan_bias",
)

#: Which party a **positive** value of each metric indicates an advantage for.
#: See the module docstring: the directions are not uniform. A consumer that
#: needs one orientation should multiply by ``+1`` for the metrics marked ``R``
#: and ``-1`` for those marked ``D`` (or the reverse), rather than assuming.
FAVOURS: dict[str, str] = {
    "efficiency_gap": "R",
    "mean_median": "R",
    "declination": "R",
    "partisan_bias": "D",
}

#: CRITERIA.md section 5.1: published guidance holds that all of these metrics
#: are reliable in competitive states, but that only the efficiency gap and
#: declination should be trusted where one party predominates.
TRUSTED_WHERE_ONE_PARTY_PREDOMINATES: tuple[str, ...] = (
    "efficiency_gap",
    "declination",
)

#: Statewide two-party D share outside ``0.5 +/- this`` counts as "one party
#: predominates" for :func:`caveats`. **This threshold is ours, not
#: CRITERIA.md's** — section 5.1 names the regime and gives no number. It is a
#: `VALUE` choice, exposed here so it can be argued with and changed.
PREDOMINANCE_BAND = 0.05

#: Below this many districts, :func:`caveats` warns that declination is coarse.
#: Also ours: declination fits one line through the losing districts and one
#: through the winning districts, so with four districts each line is fitted to
#: between one and three points and the angle it returns is dominated by which
#: side of 0.5 a single district happens to fall on.
DECLINATION_MIN_DISTRICTS = 8

#: Default x-coordinates of :func:`seats_votes_curve`: statewide two-party D
#: vote shares from 0.30 to 0.70 in steps of 0.01, built from integers so that
#: 0.50 is exactly representable.
DEFAULT_SWINGS: tuple[float, ...] = tuple(i / 100 for i in range(30, 71))

_MAX_LISTED = 8


# --------------------------------------------------------------------------- #
# district aggregation
# --------------------------------------------------------------------------- #

def district_votes(
    plan: Plan, dem: Votes, rep: Votes
) -> dict[int, tuple[int, int]]:
    """``{district: (dem votes, rep votes)}``.

    ``dem`` and ``rep`` come from ``evaluate.elections.two_party`` and must
    cover exactly the units the plan assigns; ``evaluate.plan.aggregate``
    raises otherwise, in both directions. A county silently dropped from the
    sum produces a plausible wrong number, which is the failure this module can
    least afford.
    """
    if set(dem) != set(rep):
        only_dem = sorted(set(dem) - set(rep))
        only_rep = sorted(set(rep) - set(dem))
        raise ValueError(
            "dem and rep cover different units: "
            f"{len(only_dem)} only in dem {_sample(only_dem)}, "
            f"{len(only_rep)} only in rep {_sample(only_rep)}"
        )
    for name, votes in (("dem", dem), ("rep", rep)):
        negative = sorted(g for g, v in votes.items() if v < 0)
        if negative:
            raise ValueError(
                f"{name} has negative vote counts in {len(negative)} unit(s): "
                f"{_sample(negative)}"
            )
    d_by_district = aggregate(plan, dem)
    r_by_district = aggregate(plan, rep)
    return {
        d: (int(d_by_district[d]), int(r_by_district[d]))
        for d in sorted(d_by_district)
    }


def district_shares(plan: Plan, dem: Votes, rep: Votes) -> dict[int, float]:
    """``{district: two-party Democratic vote share}``.

    Raises ValueError if any district has no two-party votes at all. The share
    is genuinely undefined there — not zero, not one half — and every metric
    below that consumes shares would otherwise report a number that looks fine.
    ``evaluate.elections.zero_vote_units`` finds such units before aggregation.
    """
    totals = district_votes(plan, dem, rep)
    empty = sorted(d for d, (dv, rv) in totals.items() if dv + rv == 0)
    if empty:
        raise ValueError(
            f"district(s) {empty} have no two-party votes, so the Democratic "
            "vote share there is undefined; the metrics that use vote shares "
            "(mean-median, declination, partisan bias, seats-votes) cannot be "
            "computed on this plan and this election"
        )
    return {d: dv / (dv + rv) for d, (dv, rv) in totals.items()}


def statewide_dem_share(dem: Votes, rep: Votes) -> float:
    """Statewide two-party Democratic vote share, turnout-weighted.

    This is ``sum(dem) / (sum(dem) + sum(rep))`` over all units — the share of
    votes actually cast, which is **not** the unweighted mean of the district
    shares unless every district has identical turnout. The difference between
    those two quantities is exactly what the mean-median difference is built to
    detect, so the two must not be interchanged.
    """
    d = sum(int(v) for v in dem.values())
    r = sum(int(v) for v in rep.values())
    if d + r == 0:
        raise ValueError("no two-party votes at all; the vote share is undefined")
    return d / (d + r)


# --------------------------------------------------------------------------- #
# seats
# --------------------------------------------------------------------------- #

def seat_count(plan: Plan, dem: Votes, rep: Votes) -> int:
    """Number of districts the Democratic candidate wins outright.

    A district is won by whoever has strictly more two-party votes. **An exact
    tie is a seat for neither party** and is counted for neither, so
    ``seat_count(D) + seat_count(R)`` can be less than the number of districts;
    :func:`seat_counts` reports the tie count so a caller can see when that
    happens. Ties do not occur in the Iowa 2020 data but do occur in
    hand-constructed and adversarially-constructed plans, and quietly awarding
    them to one party would break the party-swap symmetry every metric here is
    tested against.
    """
    return seat_counts(plan, dem, rep)[0]


def seat_counts(plan: Plan, dem: Votes, rep: Votes) -> tuple[int, int, int]:
    """``(D seats, R seats, tied districts)``. See :func:`seat_count`."""
    totals = district_votes(plan, dem, rep)
    d_seats = sum(1 for dv, rv in totals.values() if dv > rv)
    r_seats = sum(1 for dv, rv in totals.values() if rv > dv)
    tied = len(totals) - d_seats - r_seats
    return d_seats, r_seats, tied


# --------------------------------------------------------------------------- #
# efficiency gap
# --------------------------------------------------------------------------- #

def wasted_votes(
    plan: Plan, dem: Votes, rep: Votes, *, threshold: str = "majority"
) -> dict[int, tuple[float, float]]:
    """``{district: (wasted D votes, wasted R votes)}``.

    A vote is wasted if it did not contribute to electing anyone:

    * **every** vote for the losing party is wasted;
    * for the winning party, every vote **above the threshold needed to win**
      is wasted.

    ``threshold`` selects what "needed to win" means, because the literature
    uses two different answers and they give slightly different gaps:

    ``"majority"`` (default)
        ``floor(n/2) + 1`` — the smallest number of votes that is a strict
        majority of the ``n`` two-party votes cast in the district. This is the
        definition in the task specification and the one a returning officer
        would recognise.
    ``"half"``
        ``n/2`` — the convention under which the efficiency gap satisfies the
        exact algebraic identity ``EG = 2*V_D - 0.5 - S_D`` when every district
        has the same turnout (``V_D`` the statewide D vote share, ``S_D`` the D
        seat share). Useful as a check, and used as one in the tests.

    The two differ by at most one vote per district, so on Iowa the choice moves
    the gap by about ``4 / 1.66e6`` — nothing. It is a parameter rather than a
    constant because it is a definitional choice, and definitional choices in
    this repository are visible.

    An exactly tied district elects nobody, so **both** parties waste all of
    their votes there. That is the only tie rule that keeps the gap
    antisymmetric under swapping the two parties.
    """
    if threshold not in ("majority", "half"):
        raise ValueError(
            f"threshold must be 'majority' or 'half'; got {threshold!r}"
        )
    out: dict[int, tuple[float, float]] = {}
    for district, (dv, rv) in district_votes(plan, dem, rep).items():
        cast = dv + rv
        if threshold == "majority":
            needed: float = cast // 2 + 1
        else:
            needed = cast / 2
        if dv > rv:
            out[district] = (dv - needed, float(rv))
        elif rv > dv:
            out[district] = (float(dv), rv - needed)
        else:  # tie, including an empty district: nobody is elected
            out[district] = (float(dv), float(rv))
    return out


def efficiency_gap(
    plan: Plan, dem: Votes, rep: Votes, *, threshold: str = "majority"
) -> float:
    """``(wasted D votes - wasted R votes) / total two-party votes``.

    **Sign: a positive efficiency gap means the Democrats wasted more votes
    than the Republicans, which is a Republican advantage.** Negative favours
    the Democrats. Zero means the two parties wasted votes in equal measure,
    which is what a symmetric plan does.

    Be careful comparing this against published figures: several sources —
    PlanScore among them — report the gap with the opposite sign, so that a
    positive number means a Democratic advantage. The magnitude is the same;
    only the convention differs. :data:`FAVOURS` records the one used here.

    See :func:`wasted_votes` for the wasted-vote definition and the
    ``threshold`` parameter.

    CRITERIA.md section 5.1: the gap "fails when" the threshold for *too much*
    is arbitrary and sensitive to voter geography — this function returns the
    number, and takes no position on what value is too large. CRITERIA.md
    section 5.2: it is gameable, so it must never be optimised toward.

    Raises ValueError if the plan and election have no two-party votes at all.
    """
    totals = district_votes(plan, dem, rep)
    cast = sum(dv + rv for dv, rv in totals.values())
    if cast == 0:
        raise ValueError(
            "no two-party votes in this plan, so the efficiency gap's "
            "denominator is zero and the gap is undefined"
        )
    wasted = wasted_votes(plan, dem, rep, threshold=threshold)
    wasted_d = sum(w[0] for w in wasted.values())
    wasted_r = sum(w[1] for w in wasted.values())
    return (wasted_d - wasted_r) / cast


# --------------------------------------------------------------------------- #
# mean-median
# --------------------------------------------------------------------------- #

def mean_median(plan: Plan, dem: Votes, rep: Votes) -> float:
    """``mean(district D share) - median(district D share)``.

    **Sign: a positive value means the median district is less Democratic than
    the average district**, i.e. Democratic votes are concentrated in a few
    very Democratic districts while the typical district is safer for
    Republicans. That is a Republican advantage. Negative favours the Democrats.

    Both statistics are over districts, **unweighted by turnout**: each district
    contributes one share regardless of how many votes were cast in it. That is
    the standard definition and it is also a choice — a low-turnout district
    counts as much as a high-turnout one.

    **CRITERIA.md section 5.1 records this metric as unreliable when one party
    predominates**, and section 5.1's guidance is that only the efficiency gap
    and declination should be trusted in that regime. The number returned here
    is still well-defined arithmetic; it is its *interpretation* that degrades,
    which is exactly the failure mode a plain float conceals. :func:`caveats`
    reports the regime explicitly, and :data:`TRUSTED_WHERE_ONE_PARTY_PREDOMINATES`
    records which metrics survive it.

    Raises ValueError if any district has no two-party votes (see
    :func:`district_shares`).
    """
    shares = list(district_shares(plan, dem, rep).values())
    if not shares:
        raise ValueError("mean_median: plan has no districts")
    return statistics.fmean(shares) - statistics.median(shares)


# --------------------------------------------------------------------------- #
# declination
# --------------------------------------------------------------------------- #

def declination(plan: Plan, dem: Votes, rep: Votes) -> float | None:
    """Warrington's declination. **Returns None where it is undefined.**

    Sort the districts by Democratic vote share and plot them against their
    normalised rank. Let ``k`` districts be Republican-won (share below 0.5) and
    ``n - k`` Democratic-won (share above 0.5). Take the centre of mass of each
    group and the point where the plot crosses 0.5. ``theta`` is the angle of
    the segment from the Republican-won centre up to the crossing point, and
    ``gamma`` the angle from the crossing point up to the Democratic-won centre.
    The declination is ``2 * (gamma - theta) / pi``, which puts it on a scale
    where +/-1 is the extreme and 0 is a plan whose two halves are treated
    alike::

        tan(theta) = (1 - 2 * mean(R-won shares)) * n / k
        tan(gamma) = (2 * mean(D-won shares) - 1) * n / (n - k)

    **Sign: positive means the Democratic-won districts sit further above 0.5
    than the Republican-won districts sit below it, relative to how many there
    are of each** — the signature of Democratic votes packed into a few
    landslide districts, which is a Republican advantage. Negative favours the
    Democrats.

    **None is returned, rather than a number, in two cases:**

    1. **One party wins every seat.** CRITERIA.md section 5.1 states declination
       is undefined here, and it is: one of the two groups is empty, so one of
       the two lines has no points to fit and ``k/n`` or ``(n-k)/n`` is zero.
       Returning any float here — 0.0 especially — would assert an absence of
       asymmetry that was never measured.
    2. **Some district is exactly tied at a 0.5 share.** It belongs to neither
       group, and assigning it to one (as several published implementations do,
       by testing ``share <= 0.5``) makes the metric depend on which party is
       nominally listed first: swap the two parties' votes and the same district
       moves to the other group, so the metric stops being antisymmetric. A tie
       is rare in real data and common in constructed plans, which is precisely
       where the metric would be trusted least.

    Declination is one of the two metrics CRITERIA.md section 5.1 says can be
    trusted where one party predominates. It is still gameable (section 5.2) and
    it is still coarse on a four-district state — see
    :data:`DECLINATION_MIN_DISTRICTS` and :func:`caveats`.

    Raises ValueError if any district has no two-party votes.
    """
    shares = sorted(district_shares(plan, dem, rep).values())
    n = len(shares)
    if n == 0:
        raise ValueError("declination: plan has no districts")
    if any(share == 0.5 for share in shares):
        return None
    losing = [s for s in shares if s < 0.5]
    winning = [s for s in shares if s > 0.5]
    k = len(losing)
    if k == 0 or k == n:
        return None
    theta = math.atan((1 - 2 * statistics.fmean(losing)) * n / k)
    gamma = math.atan((2 * statistics.fmean(winning) - 1) * n / (n - k))
    return 2.0 * (gamma - theta) / math.pi


# --------------------------------------------------------------------------- #
# the counterfactual: uniform swing
# --------------------------------------------------------------------------- #

def _seat_share_at(shares: Sequence[float], target: float, observed: float) -> float:
    """Democratic seat share under a uniform swing to ``target`` vote share.

    **The uniform partisan swing assumption**, stated once and used by both
    :func:`partisan_bias` and :func:`seats_votes_curve`: every district's
    Democratic vote share moves by the *same additive amount*
    ``delta = target - observed``. Because the statewide share is the
    turnout-weighted mean of the district shares, adding ``delta`` to every
    district share moves the statewide share by exactly ``delta``, so this hits
    the target exactly.

    What the assumption buys and what it costs:

    * It is the standard counterfactual behind partisan bias and every
      seats-votes curve, and CRITERIA.md section 5.1 flags it as the reason both
      metrics are `VALUE` class: "requires a counterfactual election" and
      "requires uniform-swing assumption".
    * Real swings are not uniform. Districts swing by different amounts, and the
      amount correlates with composition, so a curve far from the observed
      election is extrapolation, not measurement.
    * At extreme targets the shifted shares leave ``[0, 1]``. They are not
      clamped, because clamping would silently change which districts win while
      pretending the counterfactual was physical. Only the comparison against
      0.5 is used, so a share of -0.1 and one of 0.0 behave identically; the
      unphysicality is in the premise, not the arithmetic.

    A district landing exactly on 0.5 after the shift is counted as **half a
    seat for each party**. In a counterfactual election a tie is a genuine
    coin-flip, and the half-seat rule is what makes the seats-votes curve
    antisymmetric — ``curve(v) = 1 - curve(1 - v)`` for a symmetric plan — which
    is the property partisan bias is defined in terms of.
    """
    delta = target - observed
    won = 0.0
    for share in shares:
        moved = share + delta
        if moved > 0.5:
            won += 1.0
        elif moved == 0.5:
            won += 0.5
    return won / len(shares)


def partisan_bias(
    plan: Plan, dem: Votes, rep: Votes, *, at: float = 0.5
) -> float:
    """Seat-share asymmetry at a hypothetical tied election.

    Applies a uniform swing (see :func:`_seat_share_at` for the assumption)
    until the statewide two-party Democratic vote share is exactly ``at``,
    defaulting to 0.5, then returns ``D seat share - 0.5``.

    **Sign: positive means the Democrats would win more than half the seats in
    an election they tied, which is a Democratic advantage.** Negative favours
    the Republicans. **Note this is the opposite orientation to the other three
    metrics in this module** — it is the orientation the literature and
    PlanScore use, and :data:`FAVOURS` records it so no consumer has to
    remember.

    Equivalent to the symmetry formulation ``(S_D(0.5) - S_R(0.5)) / 2``: under
    a uniform swing the Republican seat share at 50-50 is ``1 - S_D(0.5)``
    exactly, so the two definitions coincide.

    The unit is **seat share**, in ``[-0.5, 0.5]``, not seats. Multiply by the
    number of districts for a figure in seats; on a four-district state one seat
    is 0.25, so the metric is quantised to steps of 0.25 and there is no such
    thing as a small bias.

    CRITERIA.md section 5.1: "requires a counterfactual election" is this
    metric's stated failure mode. Section 5.2: gameable; never optimise toward.

    Raises ValueError if any district has no two-party votes, or if ``at`` is
    outside ``[0, 1]``.
    """
    if not 0.0 <= at <= 1.0:
        raise ValueError(f"at must be a vote share in [0, 1]; got {at!r}")
    shares = list(district_shares(plan, dem, rep).values())
    if not shares:
        raise ValueError("partisan_bias: plan has no districts")
    observed = statewide_dem_share(dem, rep)
    return _seat_share_at(shares, at, observed) - 0.5


def seats_votes_curve(
    plan: Plan,
    dem: Votes,
    rep: Votes,
    swings: Sequence[float] | None = None,
) -> list[tuple[float, float]]:
    """The full mapping from statewide vote share to Democratic seat share.

    Returns ``[(vote share, seat share), ...]``, one pair per entry of
    ``swings``, in the order given.

    ``swings`` is the sequence of **counterfactual statewide two-party
    Democratic vote shares** at which to evaluate the curve — the
    x-coordinates, not increments. Each must lie in ``[0, 1]``. The increment
    actually applied to every district is ``v - observed statewide share``; see
    :func:`_seat_share_at` for the uniform-swing assumption that makes this a
    counterfactual rather than a measurement. Defaults to
    :data:`DEFAULT_SWINGS`, 0.30 to 0.70 in steps of 0.01, which brackets any
    plausible statewide result and contains 0.50 exactly.

    The curve is a step function: with ``n`` districts the seat share can only
    take values that are multiples of ``1/(2n)`` (halves appear only at an exact
    tie). It is non-decreasing in the vote share by construction. On a
    four-district state it has at most five steps, so reading a "responsiveness"
    slope off it is not meaningful — that is a property of the state, not of
    this implementation.

    CRITERIA.md section 5.1 lists the uniform-swing requirement as this
    metric's failure mode, and section 5.2's gameability result applies to
    anything derived from it.

    Raises ValueError if any district has no two-party votes, or if any entry of
    ``swings`` is outside ``[0, 1]``.
    """
    targets = list(DEFAULT_SWINGS if swings is None else swings)
    if not targets:
        raise ValueError("seats_votes_curve: swings is empty")
    bad = [v for v in targets if not 0.0 <= v <= 1.0]
    if bad:
        raise ValueError(
            f"swings must be vote shares in [0, 1]; {len(bad)} are not: "
            f"{_sample([repr(v) for v in bad])}"
        )
    shares = list(district_shares(plan, dem, rep).values())
    if not shares:
        raise ValueError("seats_votes_curve: plan has no districts")
    observed = statewide_dem_share(dem, rep)
    return [
        (float(target), _seat_share_at(shares, target, observed))
        for target in targets
    ]


# --------------------------------------------------------------------------- #
# reporting them side by side
# --------------------------------------------------------------------------- #

def all_metrics(plan: Plan, dem: Votes, rep: Votes) -> dict[str, float | None]:
    """Every partisan metric, side by side, combined into nothing.

    Keys:

    ``n_districts``, ``dem_seats``, ``rep_seats``, ``tied_districts``
        Counts. ``dem_seats + rep_seats + tied_districts == n_districts``.
    ``dem_seat_share``
        ``dem_seats / n_districts``. Tied districts count for neither, so this
        and the Republican seat share need not sum to 1.
    ``dem_vote_share``
        Statewide, turnout-weighted, two-party (:func:`statewide_dem_share`).
    ``efficiency_gap``, ``mean_median``, ``declination``, ``partisan_bias``
        The four asymmetry metrics. ``declination`` is ``None`` where it is
        undefined — see :func:`declination`; the others are always floats.

    **There is deliberately no summary key.** CRITERIA.md section 5.2: every
    metric here is provably gameable in isolation, so a plan optimised against
    any single one of them is a gerrymander that scores clean. `prompt.md`
    forbids collapsing these to one number, and this dict is the whole output.
    Consumers wanting a headline should report the disagreement between the
    metrics, not their average.

    The metrics can and do disagree in sign about which party a plan favours;
    that disagreement is a finding, not an error, and :data:`FAVOURS` is needed
    to read it because the four are not oriented alike.

    Raises ValueError if any district has no two-party votes, because four of
    the six numbers below would be undefined and returning the other two under
    the same call would hide that.
    """
    totals = district_votes(plan, dem, rep)
    n = len(totals)
    if n == 0:
        raise ValueError("all_metrics: plan has no districts")
    d_seats, r_seats, tied = seat_counts(plan, dem, rep)
    return {
        "n_districts": n,
        "dem_seats": d_seats,
        "rep_seats": r_seats,
        "tied_districts": tied,
        "dem_seat_share": d_seats / n,
        "dem_vote_share": statewide_dem_share(dem, rep),
        "efficiency_gap": efficiency_gap(plan, dem, rep),
        "mean_median": mean_median(plan, dem, rep),
        "declination": declination(plan, dem, rep),
        "partisan_bias": partisan_bias(plan, dem, rep),
    }


def caveats(
    plan: Plan,
    dem: Votes,
    rep: Votes,
    *,
    predominance_band: float = PREDOMINANCE_BAND,
    min_districts_for_declination: int = DECLINATION_MIN_DISTRICTS,
) -> list[str]:
    """Plain-language reliability warnings for this plan and this election.

    Returns a list of sentences, empty when none applies. This exists because
    CRITERIA.md section 5.1 names regimes in which particular metrics stop
    meaning what they appear to mean, and a float carries none of that with it.
    Nothing here changes a number; it says which numbers to distrust.

    The thresholds are **ours**, not CRITERIA.md's, which names the regimes
    without quantifying them. They are keyword parameters for that reason. See
    :data:`PREDOMINANCE_BAND` and :data:`DECLINATION_MIN_DISTRICTS`.
    """
    notes: list[str] = []
    totals = district_votes(plan, dem, rep)
    n = len(totals)
    if n == 0:
        raise ValueError("caveats: plan has no districts")
    share = statewide_dem_share(dem, rep)
    d_seats, r_seats, tied = seat_counts(plan, dem, rep)

    if abs(share - 0.5) > predominance_band:
        leader = "Democratic" if share > 0.5 else "Republican"
        untrusted = [
            m for m in METRICS if m not in TRUSTED_WHERE_ONE_PARTY_PREDOMINATES
        ]
        notes.append(
            f"One party predominates: the statewide two-party Democratic share "
            f"is {share:.4f}, more than {predominance_band:g} from 0.5, a "
            f"{leader} lead. CRITERIA.md section 5.1 holds that only "
            f"{', '.join(TRUSTED_WHERE_ONE_PARTY_PREDOMINATES)} should be "
            f"trusted in this regime; treat {', '.join(untrusted)} as "
            f"unreliable here."
        )
    if d_seats == n or r_seats == n:
        winner = "Democratic" if d_seats == n else "Republican"
        notes.append(
            f"One party wins every seat ({winner}, {n} of {n}), so declination "
            "is undefined and returns None (CRITERIA.md section 5.1), and the "
            "seats-votes curve is flat through the observed election."
        )
    if tied:
        notes.append(
            f"{tied} district(s) are exactly tied. They are seats for neither "
            "party, declination returns None, and any metric reported here "
            "should be read as a boundary case rather than a measurement."
        )
    if n < min_districts_for_declination:
        notes.append(
            f"Only {n} districts. Declination fits one line through the "
            f"losing districts and one through the winning ones, so below "
            f"{min_districts_for_declination} districts each line rests on a "
            "handful of points and the angle it returns is dominated by which "
            "side of 0.5 a single district falls on. Partisan bias is quantised "
            f"to steps of {1 / n:g} seat share for the same reason."
        )
    return notes


def _sample(ids: Sequence[str]) -> str:
    """Render at most _MAX_LISTED ids for an error message."""
    head = list(ids[:_MAX_LISTED])
    tail = "" if len(ids) <= _MAX_LISTED else f" ... (+{len(ids) - _MAX_LISTED} more)"
    return f"{head}{tail}"
