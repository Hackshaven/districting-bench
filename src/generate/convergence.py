"""Convergence diagnostics: rank-normalized split R-hat and effective sample size.

Why not the textbook statistic. The feasibility pass used a plain, unsplit
Gelman-Rubin R-hat over 4 chains. It is a correct implementation of the wrong
statistic for this job: docs/FEASIBILITY.md section 5.4 shows that on *perfectly
mixed i.i.d.* chains at m=4 it returns a median of 0.9996 with P(R-hat < 1) =
0.62, so the sub-1.0 values it produced were the modal outcome for a converged
chain rather than evidence of anything, and the 1.0033-vs-1.0208 contrast an
argument was built on was smaller than the noise from reshuffling which chains
went in. It is also blind by construction to a chain that drifts monotonically:
within-chain trend inflates W and B together, and the ratio barely moves.

What is implemented instead, following Vehtari, Gelman, Simpson, Carpenter and
Buerkner, "Rank-normalization, folding, and localization: an improved R-hat for
assessing convergence of MCMC" (Bayesian Analysis 16(2), 2021):

* **Split.** Each chain is halved and the halves treated as separate chains. A
  chain that drifts now disagrees with itself, and m doubles, which is where the
  resolution at 4 chains comes from.
* **Rank normalization.** Draws are replaced by pooled ranks pushed through the
  inverse normal CDF. R-hat is a ratio of variances and therefore assumes a
  finite variance the sampler need not have; ranks make the statistic invariant
  to any strictly increasing transform of the quantity being tracked, which
  matters here because "cut edges" and "population spread" are on wildly
  different and non-normal scales.
* **Folding.** The rank-normalized statistic sees location, not scale, so it can
  pass chains that agree on the centre and disagree on the spread. Folding about
  the median and repeating gives the tail statistic; the reported value is the
  larger of the two, as the paper recommends.

ESS is the Geyer initial-positive/initial-monotone estimator on split,
rank-normalized draws, matching Stan's ``ess_bulk``. Report it alongside R-hat
and never instead: R-hat is a statement about agreement between chains, ESS about
how much independent information the draws carry, and docs/FEASIBILITY.md section
5.4 found the two disagreeing in direction as well as magnitude on this problem.

Degenerate regimes are handled explicitly rather than returned as a plausible
number: a constant quantity gives ``nan`` (no variance to compare), chains each
stuck at a different constant give ``inf`` (they will never agree), and inputs too
short or too few to support the statistic raise.
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Sequence

import numpy as np

# Minimum draws per chain. Splitting halves them, and a variance with ddof=1
# needs two, so anything shorter cannot support the statistic at all.
MIN_DRAWS = 4
_NORMAL = NormalDist()


def truncate(chains: Sequence[Sequence[float]]) -> list[list[float]]:
    """Cut every chain to the shortest one's length.

    Ragged input is refused by the diagnostics rather than silently trimmed,
    because dropping the tail of a long chain is a decision about the sample. Use
    this when that decision is deliberate.
    """
    if not chains:
        raise ValueError("no chains given")
    shortest = min(len(chain) for chain in chains)
    return [list(chain[:shortest]) for chain in chains]


def _matrix(chains: Sequence[Sequence[float]]) -> np.ndarray:
    if chains is None or len(chains) < 2:
        raise ValueError(
            f"need at least 2 chains, got {0 if chains is None else len(chains)}; "
            "a single chain cannot support a between-chain diagnostic"
        )
    lengths = {len(chain) for chain in chains}
    if len(lengths) != 1:
        raise ValueError(
            f"chains have unequal lengths {sorted(lengths)}; pass "
            "convergence.truncate(chains) if trimming to the shortest is what "
            "you mean"
        )
    length = lengths.pop()
    if length < MIN_DRAWS:
        raise ValueError(
            f"need at least {MIN_DRAWS} draws per chain to split, got {length}"
        )
    matrix = np.asarray(chains, dtype=float)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("chains contain non-finite values")
    return matrix


def _split(matrix: np.ndarray) -> np.ndarray:
    """Halve each chain. An odd middle draw is dropped, as Stan does."""
    half = matrix.shape[1] // 2
    return np.concatenate([matrix[:, :half], matrix[:, -half:]], axis=0)


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Ranks 1..S with ties averaged."""
    size = values.size
    order = np.argsort(values, kind="stable")
    ordered = values[order]
    ranks = np.empty(size, dtype=float)
    start = 0
    while start < size:
        stop = start
        while stop + 1 < size and ordered[stop + 1] == ordered[start]:
            stop += 1
        ranks[order[start : stop + 1]] = (start + stop) / 2.0 + 1.0
        start = stop + 1
    return ranks


def _rank_normalize(matrix: np.ndarray) -> np.ndarray:
    """Pooled ranks through the inverse normal CDF (Blom, as in Vehtari 2021)."""
    flat = matrix.reshape(-1)
    size = flat.size
    ranks = _average_ranks(flat)
    quantiles = (ranks - 3.0 / 8.0) / (size - 1.0 / 4.0)
    normalized = np.array([_NORMAL.inv_cdf(q) for q in quantiles])
    return normalized.reshape(matrix.shape)


def _fold(matrix: np.ndarray) -> np.ndarray:
    """Absolute deviation from the pooled median: the tail (scale) view."""
    return np.abs(matrix - np.median(matrix))


def _variance_parts(matrix: np.ndarray) -> tuple[float, float]:
    """Return ``(W, var_hat)`` for a chains-by-draws matrix."""
    m, n = matrix.shape
    within = float(matrix.var(axis=1, ddof=1).mean())
    between = float(n * matrix.mean(axis=1).var(ddof=1))
    var_hat = (n - 1) / n * within + between / n
    return within, var_hat


def _all_equal(matrix: np.ndarray) -> bool:
    """True when nothing varies anywhere. Exact, and it has to be.

    A floating-point variance of identical values is not reliably 0.0 — the
    two-pass mean leaves a residue around 1e-37 — so a ``var == 0`` test lets a
    constant quantity through as a confident-looking 0.99. Rank normalization
    maps equal inputs to exactly equal outputs, so this test is still exact after
    the transform.
    """
    flat = matrix.reshape(-1)
    return bool(np.all(flat == flat[0]))


def _each_chain_constant(matrix: np.ndarray) -> bool:
    return bool(np.all(matrix == matrix[:, :1]))


def _rhat(matrix: np.ndarray) -> float:
    if _all_equal(matrix):
        return float("nan")  # nothing varies: the ratio is 0/0
    if _each_chain_constant(matrix):
        return float("inf")  # every chain stuck at its own value: never agrees
    within, var_hat = _variance_parts(matrix)
    if within <= 0.0:
        return float("nan") if var_hat <= 0.0 else float("inf")
    return math.sqrt(var_hat / within)


def split_rhat(
    chains: Sequence[Sequence[float]],
    rank_normalize: bool = True,
    folded: bool = True,
) -> float:
    """Rank-normalized split R-hat (Vehtari et al. 2021).

    Args:
        chains: one sequence of draws per chain, all the same length.
        rank_normalize: set False for the raw-scale statistic. Only useful for
            checking the implementation against a hand computation.
        folded: also compute the folded (tail) statistic and return the larger.
            The unfolded value alone is blind to chains that disagree on scale.

    Returns:
        R-hat. Target 1.00-1.01 (docs/CRITERIA.md section 8). ``nan`` if the
        quantity never varies; ``inf`` if every chain is stuck at its own value.
    """
    matrix = _split(_matrix(chains))
    bulk = _rhat(_rank_normalize(matrix) if rank_normalize else matrix)
    if not folded:
        return bulk
    folded_matrix = _fold(matrix)
    tail = _rhat(_rank_normalize(folded_matrix) if rank_normalize else folded_matrix)
    if math.isnan(bulk) and math.isnan(tail):
        return float("nan")
    if math.isnan(bulk):
        return tail
    if math.isnan(tail):
        return bulk
    return max(bulk, tail)


def _autocovariance(chain: np.ndarray) -> np.ndarray:
    """Biased autocovariance at lags 0..n-1, by FFT."""
    n = chain.size
    centred = chain - chain.mean()
    size = 1 << (2 * n - 1).bit_length()
    spectrum = np.fft.rfft(centred, size)
    acov = np.fft.irfft(spectrum * np.conjugate(spectrum), size)[:n]
    return acov / n


def ess(chains: Sequence[Sequence[float]], rank_normalize: bool = True) -> float:
    """Effective sample size on split, rank-normalized draws (Stan's ess_bulk).

    Geyer's initial-positive sequence estimator with the initial-monotone
    correction. For i.i.d. draws this lands near ``n * m``; for an AR(1) process
    with coefficient ``phi`` it lands near ``n * m * (1 - phi) / (1 + phi)``.

    Returns ``nan`` when the quantity never varies.
    """
    matrix = _split(_matrix(chains))
    if _all_equal(matrix):
        return float("nan")
    if rank_normalize:
        matrix = _rank_normalize(matrix)
    m, n = matrix.shape
    draws = m * n

    within, var_hat = _variance_parts(matrix)
    if within <= 0.0 or var_hat <= 0.0:
        return float("nan")

    acov = np.mean([_autocovariance(matrix[i]) for i in range(m)], axis=0)
    # Stan's rho_hat: pooled autocorrelation corrected for between-chain spread.
    rho = 1.0 - (within - acov) / var_hat
    rho[0] = 1.0

    # Geyer initial positive sequence: sum adjacent pairs, stop at the first
    # non-positive pair. The first pair is always kept, so that a strongly
    # antithetic quantity gets a tau below 1 rather than an empty sum.
    pairs: list[float] = []
    for t in range(0, n - 1, 2):
        pair = float(rho[t] + rho[t + 1])
        if t > 0 and pair <= 0.0:
            break
        pairs.append(pair)

    # Initial monotone sequence: the true pair sequence is non-increasing, so
    # clamp any rise. Without this the estimator is noisy at long lags.
    for i in range(1, len(pairs)):
        if pairs[i] > pairs[i - 1]:
            pairs[i] = pairs[i - 1]

    tau = -1.0 + 2.0 * sum(pairs)
    # Stan's floor. Antithetic chains can drive tau below 1; without a floor the
    # estimate can exceed the number of draws by an arbitrary factor.
    tau = max(tau, 1.0 / math.log10(draws)) if draws > 1 else tau
    if tau <= 0.0:
        return float("nan")
    return float(draws / tau)
