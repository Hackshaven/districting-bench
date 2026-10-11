# Instrument audit — the README's first result, re-derived on the v2 ensemble

The audit `CLAUDE.md` and D-007 require before a corrected number goes to the
README: one auditor and one refuter, each a fresh agent given the diff and the
committed evidence and not the author's reasoning.

- **Audited state:** commit `8d5d4fa`, the first commit of this change, which
  re-derived the figure and the numbers from the v2 draws. Line numbers in the
  reports refer to that commit.
- **Auditor:** the `Statistician` agent, attacking the inference lens.
- **Refuter:** a general-purpose agent, told to default to "refuted" and to
  reproduce every number before agreeing.

Both reports are verbatim. The last section is the author's response, and is not
part of either report.

The same commit also went to the routing reviewers: the `Pre-Submission Peer
Reviewer`, the `Computational Redistricting Scientist`, the `Scientific
Visualization Reviewer` and the `Code Reviewer`. Their findings overlap these
and are answered in the same revision. They are not reproduced here.

---

## Auditor — Statistician

Statistician instrument audit of the corrected-number change on branch `claude/readme-v2-seat-distribution`. I worked from the diff and the evidence files only. I did not modify any repository file, and `git status` is clean. The fresh render to scratch is byte-identical to `docs/figures/ia-neutral-seat-distribution.png` (sha256 3abf47d5…).

Every number below comes from one script that reads committed files only. Its sections are labelled A1 to A6:

`cd /home/user/districting-bench && PYTHONPATH=src /tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/venv/bin/python /tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/review-stat/repro_all.py`

Supporting scripts in the same folder:
- `a4_rhat_null.py`: R-hat and ESS under a perfectly stationary chain.
- `a6_v1.py`: the v1 numbers.
- `a1_mcse.py`: batch means and overlapping batch means.

A refuter without the scratch folder can rebuild the published sample with:
`d=S.seat_distribution(); ch=X.chains_from_draws(X.ensemble_spec('IA','v2'),X.draws_path('ia','v2'),rectangle=4594); M=np.array([S.recover_seats([r['abs_efficiency_gap@G20PRE'] for r in c.rows],d['levels'])[0] for c in ch])`
Here S is `tools/plot_seat_distribution`, X is `tools/experiment_2_tradeoffs`, and the chain order is 0, 1, 2, 5, 6, 10.

No allegation is blocking. Every published number reproduces exactly, and the README headline ("about half") survives every alternative estimate (42.4% to 50.5%). The problems are in the inferences drawn from those numbers and in the stated precision.

### Allegations

**1. The data do not show the shares changed. They show the estimate moved within its own error.**
- **Location:** `docs/progress.md:2271-2275`.
- **Disputed:** "What changed is the shares. A 2-seat outcome is about half the distribution rather than 43%, and the enacted plan's outcome is 1.4% rather than 1.0%. The old 2-seat figure sits about two of the new standard errors away … imprecise, not different in kind."
- **Reproduced:**
  - The arithmetic is right: (49.53 − 43.0) / 3.053 = 2.14. The yardstick is wrong, because it omits the old estimate's own error.
  - I estimated that error from the v2 chains themselves, as the spread of 7 × 260-draw estimates. It is about 10.8 points from 218 non-overlapping 260-draw windows, 8.9 from cold-start chain prefixes, and 11.8 asymptotically (τ = 103, so ESS ≈ 17.7).
  - On the combined SE, the 2-seat difference is z = 0.54 to 0.70. A 7 × 260 estimate falls at or below 43% with probability 0.31.
  - For 0 seats, the old SE is about 1.4 points, the combined z is 0.31, and P(estimate ≤ 1.0%) = 0.49.
  - The new data alone do not exclude 43%. The chain-level t(5) 95% CI is 42.9-56.2%. With the all-rows block-means MCSE of 3.66 the interval is 42.4-56.7%. Only the published MCSE puts 43% just outside (43.5-55.5%).
  - The two completed 12,000-draw chains alone give 42.4%.
- **Assessment:** "Imprecise, not different in kind" is supported, and more strongly than the text says. "What changed is the shares", "rather than 43%" and "rather than 1.0%" are not supported.
- **Reproduce:** A1.
- **Severity:** material.

**2. The MCSE table states more precision than the sample supports.**
- **Location:** `docs/progress.md:2258-2267` (the table, "3.05 pts", ESS 268) and `tools/plot_seat_distribution.py:143-146`.
- **Disputed:** that ±3.05 points is the Monte Carlo SE of the 49.53% share.
- **Reproduced:**
  - The ESS-of-indicator basis is correct, and inside the rectangle it agrees with batch means (2.9 to 3.0 at b ≥ 574), overlapping batch means (2.96) and the chain-level SE (2.58).
  - The 2-seat ESS is 268, which is 44.7 per chain and 22 per split half. That is below the roughly 100 effective draws per chain that Vehtari et al. (2021) recommend before trusting ESS and R-hat. That is the paper `src/generate/convergence.py:13-15` cites. `CRITERIA.md` itself sets no ESS gate.
  - With six chains, the SE is itself uncertain by a factor of about 2: the 95% range for the chain-level SE is 1.61 to 6.32 points.
  - The committed rows outside the rectangle show longer-range dependence. Block means over all 57,553 rows give τ = 122 to 166 (MCSE 3.33 to 3.88) against 103 inside the rectangle. On the two 12,000-draw chains, batch means rise to τ ≈ 190 at b = 3,000 without levelling off. Within single chains, 1,000-draw block shares run from 8% to 97%.
  - Of the five rectangles in `docs/experiment-2/ia-convergence-rectangles.json`, the chosen 6 × 4,594 has the highest ESS (268.1) and the lowest R-hat (1.0134) for this indicator. The others give 45.3% to 50.5%, with MCSE 3.28 to 7.03.
- **Assessment:** "3.05 pts" is the low end. "3 to 4 points" is defensible.
- **Reproduce:** A2, and `a1_mcse.py`.
- **Severity:** material.

**3. The figure footer is a verdict that the figure's own data contradict in one direction.**
- **Location:** `tools/plot_seat_distribution.py:251-254`, the rendered footer.
- **Disputed:** "A 2-seat outcome is 49.5% of the neutral distribution, so a 2-seat shift is not detectable as a gerrymander on Iowa."
- **Reproduced:**
  - The sentence is true for D-direction plants, which are measured from the enacted 0-seat plan (`src/detect/bench.py:61-64, 1361`): 0 → 2 seats lands on a 49.5% outcome.
  - It is false for R-direction plants, measured from `ensemble_max_d`: 2 → 0 seats lands on the 1.43% outcome.
  - Under the rule of record (`src/detect/bench.py:309-317`: two-sided, mid-rank 0.99, with efficiency gap the eligible metric per `src/detect/confusion.py:173`), the enacted 0-seat plan's EG mid-rank against this rectangle is 0.9968. Per chain it runs 0.9891 to 0.9995. Any 0-seat plan falls in 0.9857 to 1.0, depending on how sub-vote rounding ties break. That is inside the firing region.
  - `docs/progress.md:321-322` already calls this outcome "unusual against this reference, in the R-favouring direction".
- **Assessment:** The README's prose about the gate being unreachable still holds, because the gate pools both directions. The footer's blanket verdict does not hold. It was carried forward from the 43% version, but this change regenerates and republishes it, and `prompt.md` treats verdict-reading output as a bug.
- **Reproduce:** A3.
- **Severity:** material.

**4. The reproducibility claim is false.**
- **Location:** `docs/progress.md:2320-2322`, and `tests/test_seat_distribution.py:32-44`.
- **Disputed:** "This reads two committed files and no data, and prints every number above", and "pins the counts".
- **Reproduced:** The plotter does not print any of these:
  - 454, 1.65% and the median 225 (`docs/progress.md:2308-2309`, `README.md:33`);
  - the four seat levels (`docs/progress.md:2292-2293`);
  - 0.0827 and 0.068 (`docs/progress.md:2296`);
  - the Colorado 5-of-8 read-back (`docs/progress.md:2300`);
  - the v1 sentence's 51.9%, 1.6%, 32-76%, 1.14 and 40 (`docs/progress.md:2278-2280`), which need a third file, `docs/experiment-2/ia-draws.csv.gz`.

  All of these do reproduce (A4, `a6_v1.py`), so they are correct, but nothing checks them by machine. The tests pin only the counts and the enacted seat count. The MCSEs, ESS values, R-hat 1.014 (printed on the figure) and the chain ranges (README "41% to 58%") are unpinned, so a change to `src/generate/convergence.py` would silently move published numbers.
- **Reproduce:** run `tools/plot_seat_distribution.py --out <scratch>` and compare its output with the section.
- **Severity:** material.

**5. The enacted plan's 1.4% is given without an interval.**
- **Location:** `README.md:31`.
- **Disputed:** "which occurs in 1.4% of this ensemble".
- **Reproduced:**
  - MCSE is 0.38 points; the chain-level t(5) 95% CI is 0.73-2.14%; chain shares run 0.44% to 2.46%.
  - The 395 zero-seat draws come from 77 separate visits. 89 of chain 6's 113 zero-seat draws fall in its first 500 draws, and dropping 500 draws per chain gives 1.15%.
  - The chain range straddles 2%, which is roughly where a tied 0-seat plan's EG mid-rank crosses 0.99 (see allegation 3).
- **Assessment:** The README gives the 2-seat share its chain range but not the share the enacted-plan comparison rests on. The comparison is withheld as "not yet a finding", so this is minor.
- **Reproduce:** A5, A1.
- **Severity:** minor.

**6. The evidence offered for seat recovery is weaker than stated, though the method is sound for Iowa.**
- **Location:** `docs/DECISIONS.md:1120-1124`, `docs/progress.md:2297-2300`, `tests/test_seat_distribution.py:57-76`.
- **Disputed:** "the assignment cannot quietly become a guess", and the Iowa read-back offered as "Why it is a measurement and not a guess".
- **Reproduced:**
  - For any 0-seat plan τ ≡ 0, so the Iowa enacted read-back (residual 2.11×10⁻⁶) tests only the 2V − ½ algebra. It cannot fail on the turnout term that the 1- and 2-seat draws (98.6% of the sample) depend on. Colorado is one plan in a state where D-039 says the method "is not established".
  - The refusal guard only catches draws in the ambiguous band. A draw more than half a gap from its true level lands near the wrong level with a small residual and passes.
  - What actually makes the method sound is physical scale. The turnout term has SD 0.0020 (1 seat) and 0.0030 (2 seats), with maximum |δ| 0.0143. A misassignment would need |δ| ≥ 0.068, which is more than 20 SD.
  - The `half_gap/2` test is a margin tripwire, not a correctness control.
- **Reproduce:** A6.
- **Severity:** minor.

**7. "Nothing else" is absence of evidence.**
- **Location:** `docs/progress.md:2269-2270`.
- **Disputed:** "Iowa's neutral process produces 0, 1 or 2 Democratic seats and nothing else".
- **Reproduced:** There are zero 3-seat draws in 57,553 rows. But those rows hold about 4,020 distinct metric tuples, and rare-indicator ESS is about 10³, which bounds an unseen outcome only to about 3/1,000. The stronger evidence is the adversarial search (0 of 32 3-seat plants, `docs/progress.md:712`), which the sentence does not cite. D-013 is unaffected either way.
- **Severity:** minor.

**8. "8 chains × 260" contradicts the 1,820 draw count.**
- **Location:** `docs/progress.md:2245` and `:2274`.
- **Disputed:** "8 chains × 260 draws" and "8 chains of 260 draws".
- **Reproduced:** 8 × 260 = 2,080. The draw count is 1,820 = 7 × 260, and `docs/progress.md:263` records "8 chains × 260 … 1 chain failure". Seven chains contributed.
- **Severity:** minor.

**9. The old ensemble was not archived.**
- **Location:** `README.md:21`.
- **Disputed:** "The 1,820-draw ensemble archived in v0.1.0".
- **Reproduced:** Its data lived in `data/results/`, which is gitignored (`.gitignore`: `data/`), and `docs/progress.md:2246-2249` says no one could regenerate it. v0.1.0 archived the figure and the 43% number, not the ensemble.
- **Severity:** minor.

**10. Convergence is reported without its target.**
- **Location:** `tools/plot_seat_distribution.py:255-258`, and `README.md:18-22`.
- **Disputed:** The footer prints "split R-hat 1.014, effective sample 286" with no 1.00-1.01 target, so a figure reader cannot tell it is outside the band. The README headline does not mention convergence at all. `prompt.md` asks for convergence reported against that target; `docs/progress.md:2267` does this correctly.
- **Severity:** minor.

**11. The bar labels imply an ordering the data cannot resolve.**
- **Location:** `tools/plot_seat_distribution.py:193`.
- **Disputed:** labels to one decimal place, "49.0%" against "49.5%".
- **Reproduced:** share(2) − share(1) = 0.50 ± 6.04 points (MCSE). The chains disagree in sign, from −14.9 to +17.5 points. The modal seat count is not identified.
- **Reproduce:** A2, last line.
- **Severity:** minor.

### Checked and found sound

- **Published values:** The counts (395, 13,516, 13,653), the shares, ESS (987, 278, 268), MCSE (0.38, 3.00, 3.05), the chain ranges, the seat-count R-hat (1.0136) and ESS (286.1) all reproduce exactly.
- **ESS of the indicator is the right basis** for the MCSE of a probability. Rank normalization is affine on a two-valued series, and ESS(rank) = ESS(raw) for all three shares. In a simulated two-state chain at τ = 103, the MCSE interval covers at 96%.
- **The R-hat statement is correct** ("near the 1.00-1.01 band, not inside it"). At this ESS the band is not attainable even for a perfectly mixed sampler: simulated median R-hat 1.021, P(≤ 1.01) = 0.06 (`a4_rhat_null.py`). So R-hat adds nothing beyond the ESS here, and ESS is the diagnostic that binds.
- **The chain range is a fair uncertainty display with six chains.** The expected range of six chain means (about 2.5σ) is about 1.2 times the width of a t(5) 95% CI for the pooled mean (about 2.1σ). It is slightly conservative, and it honestly shows the chains' disagreement.
- **The 454 claim holds.** 454 draws have a spread of 94 or less (448 strictly under, 6 at exactly 94), which is 1.65%, and the median spread is 225. The caution is correct: the 454 come from about 100 separate visits with 76 distinct tuples and include 2 zero-seat draws. "Filtering a tail is not sampling at that tolerance" is also correct.
- **The v1 sentence reproduces:** 51.90%, 1.58%, chains 32.3-75.9%, R-hat 1.138, ESS 40. Note that v1 is exactly the first 1,500 draws of each v2 chain (same seeds, identical rows), so it is not independent corroboration. The text does not claim it is.
- **Seat-recovery numbers hold:** levels 0.416335, 0.166335, 0.083665, 0.333665; gap 0.0827; half-gap 0.0413; maximum residual 0.0143. The 0-seat draws pin 2V − ½ to within 2×10⁻⁶ of the Phase 2 value.
- **Burn-in does not bias the headline.** The 2-seat share stays at 49.1-50.2% for burn-in discards of 0 to 1,500 draws.
- **Chain death is not tied to seat state:** 5 of 7 chains that died ended at 2 seats, p ≈ 0.23.
- **Suite and tests:** with no data, the suite gives 578 passed and 151 skipped, matching the README. The 5 new tests pass and raise no RuntimeWarning.

### Outside the diff

- `tools/plot_experiment_3.py:116-133` still reads the gitignored `data/results/ia_neutral_seat_distribution.json` for its neutral band. That is the same D-036 problem this change fixed for the seat figure.
- `src/adversarial/gerrymander.py:200` still says "43%".

---

## Refuter

REFUTER_PENDING

---

## Author's response

RESPONSE_PENDING
