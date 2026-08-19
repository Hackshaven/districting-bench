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
``partisan_bias``      ``(S_D(v) - S_R(v))/2`` at ``v = 0.5``      favours D
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

**A number and the regime it was computed in are reported together.**
CRITERIA.md section 5.1 says mean-median and partisan bias should not be trusted
where one party predominates, and a bare float carries none of that.
:func:`one_party_predominates` decides the regime, :func:`trusted_metrics` says
which metrics survive it, and :func:`caveats` states both in prose — including,
positively, what remains usable. On Iowa 2020's enacted plan what remains is the
efficiency gap and nothing else.

**Two seat-share conventions, both named, neither silent.** A district exactly
tied at a 0.5 share is a seat for *neither* party in the observed election
(:func:`seat_counts`, ``all_metrics()["dem_seat_share"]``) and *half a seat for
each* in the counterfactual swing (:func:`partisan_bias`, and the default of
:func:`seats_votes_curve`). The first refuses to invent which of two candidates
a real district elected; the second is what makes the curve antisymmetric, which
is the property partisan bias is defined from. :data:`SEAT_TIE_RULES` names
them, and ``seats_votes_curve(..., tie="neither")`` at the observed vote share
reproduces the reported seat share exactly. **At the observed election the two
rules agree unless a district is exactly tied**, which :func:`caveats` reports;
away from it they part company at every swing that lands a district on 0.5,
which is the counterfactual's business and the reason it has its own rule.

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

#: First arm of :func:`one_party_predominates`: the **statewide margin**. A
#: two-party Democratic share outside ``0.5 +/- this`` puts the state in
#: CRITERIA.md section 5.1's "one party predominates" regime. **This threshold
#: is ours, not CRITERIA.md's** — section 5.1 names the regime and gives no
#: number. It is a `VALUE` choice, exposed here so it can be argued with.
#:
#: It is only *one* arm, and Iowa 2020 is the case that forced the other two:
#: the statewide Democratic share there is 0.458167, which is 0.041833 from 0.5
#: and so **inside** this band, while the Republicans hold four seats of four.
#: A test keyed to the statewide margin alone calls that competitive and lets
#: ``mean_median = -0.024256`` — a number whose sign reads as a *Democratic*
#: advantage — out of this module with nothing attached. That is CRITERIA.md
#: section 11 failure mode 4, "a defensible number concealing whose definition
#: it encodes", landing on the repository's only real plan.
PREDOMINANCE_BAND = 0.05

#: Second arm: the **district sweep**. Districts are sorted by which side of 0.5
#: their Democratic share falls on; when the weaker side holds no more than this
#: fraction of them, one party predominates whatever the statewide margin says.
#: 0.25 is "all, or all but one" in a four-district state (Iowa 2020: zero of
#: four), two of eight, and it leaves an even split competitive at every size.
#: Ours, `VALUE` class, arguable, and a keyword parameter for that reason.
#:
#: Stated on the district **shares** rather than on the seat tally from
#: :func:`seat_counts` because the shares are what mean-median, declination,
#: partisan bias and the seats-votes curve actually consume, and because an
#: exactly tied district then falls on neither side instead of silently on one.
#: On any plan without a tied district the two readings coincide, so this is the
#: seat sweep, measured where the metrics read it.
MINORITY_DISTRICT_SHARE = 0.25

#: Tie rules for a district sitting exactly on a 0.5 Democratic share. The
#: module uses **both**, deliberately and by name, because the observed election
#: and the counterfactual swing are different questions — see
#: :func:`_seat_share_at` and :func:`all_metrics`.
#:
#: ``"neither"``
#:     A tie elects nobody. The rule for the **observed** election, used by
#:     :func:`seat_count`, :func:`seat_counts` and :func:`all_metrics`.
#: ``"half"``
#:     A tie is half a seat for each party. The rule for the **counterfactual**
#:     swing, used by :func:`partisan_bias` and by default in
#:     :func:`seats_votes_curve`.
SEAT_TIE_RULES: tuple[str, ...] = ("neither", "half")

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

def _seat_share_at(
    shares: Sequence[float], target: float, observed: float, *, tie: str = "half"
) -> float:
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

    **The tie rule — the one place this module holds two conventions at once.**
    A district landing exactly on 0.5 after the shift is counted according to
    ``tie``:

    ``"half"`` (the default here)
        Half a seat for each party. In a counterfactual election a tie is a
        genuine coin-flip, and the half-seat rule is what makes the seats-votes
        curve antisymmetric — ``curve(v) = 1 - curve(1 - v)`` for a symmetric
        plan — which is the property :func:`partisan_bias` is *defined* in terms
        of. Under ``"neither"`` that property fails at every swing that lands a
        district exactly on 0.5, so partisan bias always uses ``"half"``.
    ``"neither"``
        A tie elects nobody: the rule :func:`seat_counts` applies to the
        **observed** election, where a real district returns one member and this
        module refuses to invent which. With ``target == observed`` this
        reproduces ``all_metrics()["dem_seat_share"]`` exactly — the identity
        ``tests/test_partisan.py`` pins.

    Both conventions are defensible; holding both *silently* is not, so the rule
    is a named parameter rather than a constant and each caller states which it
    uses. **At ``target == observed`` the two agree unless a district is exactly
    tied**, and :func:`caveats` reports that case; away from the observed
    election they differ at every swing that puts a district exactly on 0.5 —
    the step edges of the curve — which is a property of the counterfactual, not
    a disagreement about the election that happened. Iowa 2020 has no tied
    district, so no number published from the real data depends on the choice.
    """
    if tie not in SEAT_TIE_RULES:
        raise ValueError(f"tie must be one of {SEAT_TIE_RULES}; got {tie!r}")
    delta = target - observed
    won = 0.0
    for share in shares:
        moved = share + delta
        if moved > 0.5:
            won += 1.0
        elif moved == 0.5 and tie == "half":
            won += 0.5
    return won / len(shares)


def partisan_bias(
    plan: Plan, dem: Votes, rep: Votes, *, at: float = 0.5
) -> float:
    """Seat-share **asymmetry** at a hypothetical vote share, default 50-50.

    Applies a uniform swing (see :func:`_seat_share_at` for the assumption) to
    put the statewide two-party Democratic share at ``at``, and again to put the
    *Republican* share at ``at``, and returns half the difference between what
    the two parties get::

        bias(v) = (S_D(v) - S_R(v)) / 2,   S_R(v) = 1 - S_D(1 - v)

    where ``S_D(v)`` is the Democratic seat share when the Democrats hold ``v``
    of the statewide two-party vote. This is *partisan symmetry* as CRITERIA.md
    section 5.3 defines it — "each party should get the same seats for the same
    vote share" — and it is a property of the **plan**, not of the state's lean.

    At the default ``at = 0.5`` this reduces to ``S_D(0.5) - 0.5``, the familiar
    form, because ``S_R(0.5) = 1 - S_D(0.5)`` exactly: no number this module has
    ever published changes.

    **It does not reduce to that anywhere else, and the earlier implementation's
    ``S_D(at) - 0.5`` was wrong for ``at != 0.5``** — it measured how many seats
    the Democrats win at that vote share, which mixes the plan's asymmetry
    together with the state's lean and with the ordinary fact that a party with
    60% of the vote wins more than half the seats under any districting at all.
    The demonstration is a plan that is symmetric by construction (district
    shares 0.4, 0.4, 0.6, 0.6): the old expression returned +0.25 at
    ``at = 0.6`` and -0.25 at ``at = 0.4`` for a plan with no asymmetry
    whatsoever, while this one returns 0 at every ``at``.
    ``tests/test_partisan.py`` pins that, and pins that the default is unmoved.

    Because the formula compares the two parties at the same vote share,
    ``bias(v) == bias(1 - v)``: the asymmetry at 60-40 is one number, not two,
    and it does not matter which party is named as holding the 60.

    **Sign: positive means the Democrats take a larger seat share at ``at`` of
    the vote than the Republicans would at the same ``at``, which is a
    Democratic advantage; at the default it is the familiar "they would win
    more than half the seats in an election they tied".** Negative favours
    the Republicans. **Note this is the opposite orientation to the other three
    metrics in this module** — it is the orientation the literature and
    PlanScore use, and :data:`FAVOURS` records it so no consumer has to
    remember.

    The unit is **seat share**, in ``[-0.5, 0.5]``, not seats. Multiply by the
    number of districts for a figure in seats. Because it is half the difference
    of two seat shares it is quantised to multiples of ``1/(2n)`` — 0.125 on a
    four-district state, and ``1/(4n)`` at a swing that splits a tied district —
    so on a small state there is no such thing as a small bias.

    CRITERIA.md section 5.1: "requires a counterfactual election" is this
    metric's stated failure mode. Section 5.2: gameable; never optimise toward.

    Ties in the counterfactual are split half a seat each (:data:`SEAT_TIE_RULES`
    ``"half"``, not a parameter here): the antisymmetry that makes ``S_R(v) =
    1 - S_D(1 - v)`` hold is exactly what this metric is defined from, and the
    observed-election rule would break it.

    Raises ValueError if any district has no two-party votes, or if ``at`` is
    outside ``[0, 1]``.
    """
    if not 0.0 <= at <= 1.0:
        raise ValueError(f"at must be a vote share in [0, 1]; got {at!r}")
    shares = list(district_shares(plan, dem, rep).values())
    if not shares:
        raise ValueError("partisan_bias: plan has no districts")
    observed = statewide_dem_share(dem, rep)
    dem_seats_at = _seat_share_at(shares, at, observed, tie="half")
    rep_seats_at = 1.0 - _seat_share_at(shares, 1.0 - at, observed, tie="half")
    return (dem_seats_at - rep_seats_at) / 2.0


def seats_votes_curve(
    plan: Plan,
    dem: Votes,
    rep: Votes,
    swings: Sequence[float] | None = None,
    *,
    tie: str = "half",
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

    ``tie`` selects the rule for a district sitting exactly on 0.5 after the
    swing (:data:`SEAT_TIE_RULES`). The default ``"half"`` is what makes the
    curve antisymmetric and is the convention :func:`partisan_bias` is built on.
    ``"neither"`` is the observed-election rule from :func:`seat_counts`, and
    evaluating the curve at the observed statewide share under it returns
    exactly ``all_metrics()["dem_seat_share"]`` — the two seat-share
    conventions in this module, named rather than silent. At the observed share
    they differ by ``1/(2n)`` per tied district and not at all otherwise; at
    other swings they differ wherever the swing lands a district on 0.5.

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
        (float(target), _seat_share_at(shares, target, observed, tie=tie))
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
        ``dem_seats / n_districts``, under the **observed-election** tie rule
        (:data:`SEAT_TIE_RULES` ``"neither"``): a tied district is a seat for
        neither party, so this and the Republican seat share need not sum to 1.
        ``seats_votes_curve(plan, dem, rep, swings=[out["dem_vote_share"]],
        tie="neither")`` returns exactly this number; the curve's *default*
        ``tie="half"`` splits a tied district instead and is the convention
        partisan bias needs. Both rules are named, neither is silent, and at the
        observed election they differ only where :func:`caveats` reports a tied
        district.
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

    **This dict does not say which of its numbers can be trusted.** It cannot:
    that depends on the regime the plan and election sit in, which is what
    :func:`one_party_predominates`, :func:`trusted_metrics` and :func:`caveats`
    report. On Iowa 2020 this function returns ``mean_median = -0.024256``,
    whose sign reads as a Democratic advantage, for a plan on which the
    Republicans hold four seats of four with 54.2% of the two-party vote — the
    regime CRITERIA.md section 5.1 says to distrust exactly that number in.
    Publishing this dict without the caveats beside it is CRITERIA.md section 11
    failure mode 4, and every caller in this repository is expected to report
    both.

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


def one_party_predominates(
    plan: Plan,
    dem: Votes,
    rep: Votes,
    *,
    predominance_band: float = PREDOMINANCE_BAND,
    minority_district_share: float = MINORITY_DISTRICT_SHARE,
) -> list[str]:
    """Reasons this plan sits in CRITERIA.md 5.1's one-party-predominates regime.

    Returns one clause per reason found; an empty list means it does not.

    Section 5.1 names the regime — "published guidance holds that all of these
    are reliable in competitive states, but that only the efficiency gap and
    declination should be trusted where one party predominates" — and defines
    it no further. Quantifying it is therefore ours, `VALUE` class, and this
    function is where the whole judgement lives so that it can be argued with in
    one place. :func:`trusted_metrics` and :func:`caveats` both defer to it.

    **Predominance is not the statewide margin.** That was this module's
    original test and it was the wrong quantity: one party *predominating* is a
    statement about who ends up holding the seats and about how the district
    vote shares are distributed around 0.5, and a state can be within a couple
    of points of a tie statewide while one party holds every district. Iowa 2020
    is precisely that state, and under the margin-only test it drew no warning
    at all. Three arms, any one sufficient:

    1. **Statewide margin** — the two-party Democratic share lies outside
       ``0.5 +/- predominance_band``. Iowa 2020: 0.458167, inside the band, so
       this arm does **not** fire there.
    2. **District sweep** — the leading side of 0.5 holds all but at most
       ``minority_district_share`` of the districts. This is the seat sweep,
       read off the district shares rather than the seat tally. A district
       exactly at 0.5 is on **neither** side, and therefore counts against the
       sweep, in the minority: a plan cannot be said to sweep the districts it
       has not won. Counting ties out of both tallies instead — which is what
       this arm did until it was caught — deflates both and fires the arm on
       plans where nothing sweeps at all. Eight districts at 0.40, 0.45, 0.50,
       0.50, 0.50, 0.50, 0.55, 0.60 with a statewide tie is the case: 2 below,
       2 above, and no sweep by any reading. Iowa 2020: zero districts of four
       above 0.5 and none tied, so this arm fires, which is the whole point of
       the rewrite.
    3. **Median district** — the median district share itself lies outside
       ``0.5 +/- predominance_band``, so the middle of the distribution is not
       competitive. Mean-median compares the mean against that median; when the
       median district is nowhere near deciding anything, the comparison has no
       pivot. Iowa 2020: 0.481438, inside the band, so this arm does not fire
       either. It is here because it catches one-sided distributions that arms 1
       and 2 miss — an odd district count split 3-2 on shares 0.20, 0.42, 0.44,
       0.56, 0.90, say, at a statewide tie.

    Arms 2 and 3 overlap heavily with each other on real data, and that is
    accepted rather than engineered away: they are cheap, each is separately
    interpretable, and the union is the claim being made. What is *not* accepted
    is arm 1 standing alone, because Iowa 2020 shows what it lets through.

    The returned strings are clause-length reasons, meant to be joined by
    :func:`caveats`. Raises ValueError under the same conditions as
    :func:`district_shares`.
    """
    shares = sorted(district_shares(plan, dem, rep).values())
    n = len(shares)
    if n == 0:
        raise ValueError("one_party_predominates: plan has no districts")
    statewide = statewide_dem_share(dem, rep)
    below = sum(1 for s in shares if s < 0.5)
    above = sum(1 for s in shares if s > 0.5)
    tied = n - below - above
    median = statistics.median(shares)
    reasons: list[str] = []

    if abs(statewide - 0.5) > predominance_band:
        leader = "Democratic" if statewide > 0.5 else "Republican"
        reasons.append(
            f"statewide margin — the two-party Democratic share is "
            f"{statewide:.6f}, {abs(statewide - 0.5):.6f} from 0.5 and outside "
            f"the +/-{predominance_band:g} band, a {leader} lead"
        )
    majority = max(below, above)
    minority = n - majority  # everything not on the leading side, ties included
    if majority > minority and minority <= minority_district_share * n:
        leader = "Democratic" if above > below else "Republican"
        detail = f"{minority - tied} on the other"
        if tied:
            detail += f" and {tied} exactly tied, on neither side"
        reasons.append(
            f"district sweep — {majority} of {n} district vote shares fall on "
            f"the {leader} side of 0.5, {detail}, a minority share of "
            f"{minority / n:g} at or below the {minority_district_share:g} "
            f"threshold"
        )
    if abs(median - 0.5) > predominance_band:
        side = "Democratic" if median > 0.5 else "Republican"
        reasons.append(
            f"median district — the median district share is {median:.6f}, "
            f"{abs(median - 0.5):.6f} from 0.5 and outside the "
            f"+/-{predominance_band:g} band, so the middle of the distribution "
            f"is itself safely {side} and mean-median has no pivot to compare "
            f"its mean against"
        )
    return reasons


def trusted_metrics(
    plan: Plan,
    dem: Votes,
    rep: Votes,
    *,
    predominance_band: float = PREDOMINANCE_BAND,
    minority_district_share: float = MINORITY_DISTRICT_SHARE,
    min_districts_for_declination: int = DECLINATION_MIN_DISTRICTS,
) -> tuple[str, ...]:
    """Which of :data:`METRICS` remain usable on this plan and election.

    Returns a subset of ``METRICS`` in the same order — **names, never values**.
    Nothing here averages, weights, ranks or scores anything; a caller cannot
    reduce this to a number, and `prompt.md`'s prohibition on collapsing
    fairness to one number is not touched by it. It answers the question a bare
    dict of floats cannot: *which of these numbers is it honest to report as a
    measurement here?*

    The rule, in order:

    * Where :func:`one_party_predominates` returns any reason, keep only
      :data:`TRUSTED_WHERE_ONE_PARTY_PREDOMINATES` — the efficiency gap and
      declination, per CRITERIA.md section 5.1.
    * Drop declination where :func:`declination` returns ``None``: a metric that
      is undefined is not a metric that is trusted.
    * Drop declination below ``min_districts_for_declination`` districts. It is
      still arithmetic there, but each of its two lines rests on a handful of
      points (see :data:`DECLINATION_MIN_DISTRICTS`), and "coarse enough that a
      single district's side of 0.5 dominates the angle" is not a number to
      publish as a measurement.

    On Iowa 2020's enacted plan this returns ``("efficiency_gap",)`` — one
    metric of four. That is the honest size of the claim available from this
    module on the repository's only real dataset, and it is a large part of why
    this module reports a dict and a caveat list rather than a verdict. The
    surviving metric is still `VALUE` class and still gameable (CRITERIA.md
    section 5.2); "trusted" here means *not disqualified by the regime*, which
    is a much weaker statement than *correct*.

    Partisan bias survives the small-district test even though it is quantised
    to ``1/n`` of seat share there: quantisation is a resolution limit that
    :func:`caveats` states outright, not a failure of interpretation. That is a
    judgement call and it is stated here so it can be overturned.
    """
    predominates = bool(
        one_party_predominates(
            plan,
            dem,
            rep,
            predominance_band=predominance_band,
            minority_district_share=minority_district_share,
        )
    )
    usable = [
        m
        for m in METRICS
        if not predominates or m in TRUSTED_WHERE_ONE_PARTY_PREDOMINATES
    ]
    if "declination" in usable:
        n = len(district_votes(plan, dem, rep))
        if declination(plan, dem, rep) is None or n < min_districts_for_declination:
            usable.remove("declination")
    return tuple(usable)


def caveats(
    plan: Plan,
    dem: Votes,
    rep: Votes,
    *,
    predominance_band: float = PREDOMINANCE_BAND,
    minority_district_share: float = MINORITY_DISTRICT_SHARE,
    min_districts_for_declination: int = DECLINATION_MIN_DISTRICTS,
) -> list[str]:
    """Plain-language reliability warnings for this plan and this election.

    Returns a list of sentences, empty when none applies. This exists because
    CRITERIA.md section 5.1 names regimes in which particular metrics stop
    meaning what they appear to mean, and a float carries none of that with it.
    Nothing here changes a number; it says which numbers to distrust.

    The last note is the **positive** one: it names the metrics that survive
    every regime found, because a list of things that are broken is not the same
    statement as a list of things that are usable, and a reader given only the
    first will assume the rest are fine. On Iowa 2020 the survivor is the
    efficiency gap and nothing else. See :func:`trusted_metrics`.

    The thresholds are **ours**, not CRITERIA.md's, which names the regimes
    without quantifying them. They are keyword parameters for that reason. See
    :data:`PREDOMINANCE_BAND`, :data:`MINORITY_DISTRICT_SHARE` and
    :data:`DECLINATION_MIN_DISTRICTS`.
    """
    notes: list[str] = []
    totals = district_votes(plan, dem, rep)
    n = len(totals)
    if n == 0:
        raise ValueError("caveats: plan has no districts")
    d_seats, r_seats, tied = seat_counts(plan, dem, rep)

    predominance = one_party_predominates(
        plan,
        dem,
        rep,
        predominance_band=predominance_band,
        minority_district_share=minority_district_share,
    )
    if predominance:
        untrusted = [
            m for m in METRICS if m not in TRUSTED_WHERE_ONE_PARTY_PREDOMINATES
        ]
        notes.append(
            "One party predominates ("
            + "; ".join(predominance)
            + "). CRITERIA.md section 5.1 holds that only "
            + ", ".join(TRUSTED_WHERE_ONE_PARTY_PREDOMINATES)
            + " should be trusted in this regime; treat "
            + ", ".join(untrusted)
            + " as unreliable here, whatever their sign says."
        )
    if d_seats == n or r_seats == n:
        winner = "Democratic" if d_seats == n else "Republican"
        shares = district_shares(plan, dem, rep)
        loser = "Republican" if d_seats == n else "Democratic"
        closest = min(shares, key=lambda d: abs(shares[d] - 0.5))
        swing = abs(shares[closest] - 0.5)
        notes.append(
            f"One party wins every seat ({winner}, {n} of {n}), so declination "
            f"is undefined and returns None (CRITERIA.md section 5.1). The "
            f"sweep cannot get any wider, so the seats-votes curve is flat on "
            f"the {winner} side of the observed election — but it is not flat "
            f"through it, and how far it runs before it steps is a fact about "
            f"this plan and not a general one. Here district {closest} sits at "
            f"{shares[closest]:.6f}, so a uniform swing of {swing:.6f} — "
            f"{swing * 100:.2f} points of two-party vote share — moves the "
            f"{loser} seat share from 0 to {1 / n:g}. Read the sweep as that "
            f"margin, not as a structural fact."
        )
    if tied:
        notes.append(
            f"{tied} district(s) are exactly tied. They are seats for neither "
            "party, declination returns None, and any metric reported here "
            "should be read as a boundary case rather than a measurement. It "
            "is also the only way the module's two seat-share conventions can "
            "disagree about the election that happened: the observed seat share "
            "counts a tie for "
            "neither party, the seats-votes curve's default counts it as half a "
            f"seat each, so the two differ by {tied / (2 * n):g} here."
        )
    if n < min_districts_for_declination:
        notes.append(
            f"Only {n} districts. Declination fits one line through the "
            f"losing districts and one through the winning ones, so below "
            f"{min_districts_for_declination} districts each line rests on a "
            "handful of points and the angle it returns is dominated by which "
            "side of 0.5 a single district falls on. Partisan bias is quantised "
            f"to multiples of {1 / (2 * n):g} seat share for the same reason "
            f"({1 / (4 * n):g} where a swing splits a tied district), so it has "
            "no resolution below half a seat here."
        )

    usable = trusted_metrics(
        plan,
        dem,
        rep,
        predominance_band=predominance_band,
        minority_district_share=minority_district_share,
        min_districts_for_declination=min_districts_for_declination,
    )
    if len(usable) < len(METRICS):
        unusable = [m for m in METRICS if m not in usable]
        notes.append(
            "Still usable on this plan and election: "
            + ", ".join(usable)
            + f" ({len(usable)} of {len(METRICS)}). Do not report "
            + ", ".join(unusable)
            + " as measurements here — see the notes above for why each fails. "
            "What survives is still VALUE class and still gameable "
            "(CRITERIA.md section 5.2); surviving the regime test is not the "
            "same as being right."
        )
    return notes


def _sample(ids: Sequence[str]) -> str:
    """Render at most _MAX_LISTED ids for an error message."""
    head = list(ids[:_MAX_LISTED])
    tail = "" if len(ids) <= _MAX_LISTED else f" ... (+{len(ids) - _MAX_LISTED} more)"
    return f"{head}{tail}"
