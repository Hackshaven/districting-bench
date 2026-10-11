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

## Refutation of the Statistician's allegations (refuter, fresh context)

**Overall:** 7 allegations upheld (1, 3, 4, 5, 6, 8, 9, 10; three of them with a correction to their evidence) and 3 partly upheld (2, 7, 11). None refuted. One of the auditor's "sound" claims (chain death not tied to seat state) does not reproduce as stated.

**What I checked against.**
- **Commit:** HEAD of `claude/readme-v2-seat-distribution`. The working tree was clean before and after, and I read no commit message.
- **Seat recovery:** my own loader. It reads `docs/experiment-2/ia-draws-v2.csv.gz` directly with `csv`/`gzip` and assigns each draw the nearest level |2V − ½ − s/4|, with V and k from `docs/phase-2/phase-2-report.json`. It does not go through the plotter or `chains_from_draws`.
- **ESS and split R-hat:** these come from `generate.convergence`. My own Geyer ESS matches it on every indicator (986.8 / 278.3 / 268.1), and my own rank-normalized split R-hat gives 1.0136.
- **Script:** at the end. "script `n:`" refers to the lines it prints.

**Baseline, reproduced exactly:**
- Rectangle counts 395 / 13,516 / 13,653, shares 1.43 / 49.03 / 49.53%.
- ESS 987 / 278 / 268; MCSE 0.38 / 3.00 / 3.05 pts.
- Seat-count split R-hat 1.0136, ESS 286.1.
- No 3- or 4-seat draw, in the rectangle or in all 57,553 rows (832 / 28,780 / 27,941). Max residual 0.0143.
- `tools/plot_seat_distribution.py --out <scratch>` writes a PNG byte-identical to the committed figure.

### 1. [material] "What changed is the shares" — **UPHELD**, one qualification

**Reproduced (script `1:`):**
- **Old estimate's SE:** 10.77 pts from 218 non-overlapping 260-draw windows; 8.88 from the first 260 draws of the 8 chains that reached 260; 11.88 asymptotically (τ = 102.8, ESS(1,820) = 17.7).
- **Combined z** against 782/1,820 = 42.97%: 0.59, 0.70, 0.54.
- **P(mean of 7 random windows ≤ 43%)** = 0.310.
- **0 seats:** old SE 1.40, combined z 0.31. The new 95% interval, 0.69–2.17%, contains 1.0%.
- **2 seats:** t(5) CI 42.90–56.16%. All-rows block-means MCSE 3.66 gives 42.4–56.7%. Chains 0 and 6 run to completion give 42.39%.

**Reasoning:** "about two of the new standard errors" (2.15) is arithmetically right, but it omits the old estimate's own error. With that error included, the gap is 0.54–0.70 combined SEs. So "rather than 43%" and "rather than 1.0%" present as a change something the data cannot tell from no change. "Imprecise, not different in kind" holds.

**Qualification:** by the table's own MCSE (3.05), the new data alone do exclude 43.0% (95% interval 43.55–55.52%). So "new data alone do not exclude 43%" holds only for the chain-level and all-rows estimators. The conclusion does not depend on it.

Borrowing v2's mixing to model the old error is fair. The 1,820-draw ensemble had 323 distinct plans (17.7%). Any 7 of v2's 8 cold-start 260-draw prefixes hold 358–404 distinct metric tuples, so the old chains moved no faster.

### 2. [material] MCSE states more precision than the sample supports — **PARTLY UPHELD**

**Reproduced (script `2:`):**
- **ESS:** 268.1 is 44.7 per chain, or 22.3 per split chain. Vehtari et al. (2021) ask for total rank-normalized ESS > 400 (§2) and an average of 50 per split chain (§3.2). 268 meets neither.
- **Chain-level SE:** 2.58, 95% range 1.61–6.32.
- **Block means over all 57,553 rows:** τ = 122 / 147 / 166 at b = 500 / 1,000 / 3,000, giving a rectangle MCSE of 3.33 / 3.66 / 3.88.
- **Two complete chains, b = 3,000:** τ = 190 only with a ddof = 1 batch variance (166 with ddof = 0). That rests on 8 batches, whose χ² 95% interval is 83–788.

**Upheld:**
- The MCSE is itself uncertain by roughly 2×.
- Dependence beyond the 4,594-draw horizon pushes τ above 103. Split Geyer over full-length chain 0 gives τ = 120, and chain 6 gives 131.
- So "3 to 4 points" is defensible.

**Not upheld:**
- "3.05 is the low end." On the rectangle itself, the chain-level SE is 2.58, and batch means give τ 46–103 for b ≥ 400 (MCSE 2.0–3.05).
- "Without levelling" cannot be shown from 8 batches.

### 3. [material] Footer "a 2-seat shift is not detectable" — **UPHELD**, its evidence corrected

**Reproduced (script `3:`):**
- The enacted plan's signed-EG mid-rank against the rectangle is 0.9968.
- Per chain: 0.9985, 0.9988, 0.9966, 0.9980, 0.9891, 0.9995.
- A plan at the 2-seat level scores 0.701.
- The repo's own `outlier.locate` plus `confusion.flag` flags the enacted value. Settings: threshold 0.99, two-sided, efficiency gap, metric tuples standing in for plan ids, Kish ESS 270.

**Reasoning:** the footer states a categorical conclusion. Its reason (49.5% at 2 seats) covers only D+2 plants from the enacted 0-seat baseline. An R+2 plant from `ensemble_max_d` (src/detect/bench.py:1361) lands on the 1.43% bar that the figure itself draws.

**Correction:** under the rule of record, whether a 0-seat plan fires depends on the strict-majority threshold's vote parity. The rectangle's 395 zero-seat draws sit at two efficiency-gap values one vote in 1.66 million apart:
- 216 sit at mid-rank 0.9896, which does not fire.
- 179 sit at the enacted plan's value, 0.9968, which fires.

So R-direction plants are flagged erratically, not cleanly. Only the efficiency gap can be checked from committed files. Without plan ids (Kish ESS 39 < 50), the rule refuses to decide at all.

### 4. [material] "prints every number above" — **UPHELD**, one sub-claim corrected

**Reproduced:**
- **Missing from the plotter's 8 output lines:** 454, 1.65%, 225, the seat levels, 0.0827, 0.068, the Colorado read-back, the 4/1.66×10⁶ offset, and the v1 numbers.
- **What it prints instead:** the half-gap 0.0413, and the report's directly counted seats rather than a read-back.
- **Tests:** no assertion in tests/test_seat_distribution.py covers MCSE, ESS, R-hat or the chain ranges.

**Reasoning:** progress.md:2320 is false as written.

**Correction:** the tests pin more than the counts and the enacted seat count. They also pin:
- the contest;
- (6, 4,594, 27,564);
- max residual < half-gap/2;
- both read-backs (IA 0 of 4, CO 5 of 8).

**Aside:** the plotter reads three committed files, not two. `chains_from_draws` also opens ia-draws-v2-chains.json, though that file cannot move any rectangle number.

### 5. [minor] 1.4% without an interval — **UPHELD**

**Reproduced (script `5:`):**
- MCSE 0.38; t(5) 95% CI 0.73–2.14%; chain shares 0.44–2.46%.
- The 395 zero-seat draws come from 77 separate visits.
- 89 of chain 6's 113 zero-seat draws fall in its first 500.
- Discarding 500 draws per chain gives 1.15%.

**Reasoning:** README:31 quotes 1.4% with no interval, while README:20–21 give the 2-seat share a chain range. The interval exists only in progress.md.

### 6. [minor] Seat-recovery evidence weaker than stated — **UPHELD**

**Reproduced (script `6:`):**
- Turnout-term SD is 0.0020 at 1 seat and 0.0030 at 2 seats. The 0-seat residual is exactly 0; the maximum is 0.0143.
- Gap minus max is 0.0684. That is 22.6 SD for 2-seat draws and 34.7 SD for 1-seat draws. The half-gap, 0.0413, is 13.7 and 21.0 SD.
- The Iowa read-back residual is 2.1×10⁻⁶, which is the threshold offset alone.

**Reasoning:** τ = 0 identically on a 0-seat plan, so the Iowa read-back cannot exercise the turnout term. Soundness rests on the residual scale. Colorado's read-back does exercise it (residual 0.00098 against a half-gap of 0.0138), but on the other state.

**The guard is weaker than the auditor says.** Between the 1- and 2-seat levels, which are 0.0827 apart, it refuses only at the exact midpoint. So `recover_seats([0.1287], levels)` returns 1 without refusing, and 0.1287 is what a 2-seat plan with a +0.045 turnout term would read. On the committed draws, the margin is enforced by the test (max residual < half-gap/2), not by the guard. Compare progress.md:2297–2299, "cannot quietly become a guess".

### 7. [minor] "nothing else" — **PARTLY UPHELD**

**Reproduced (script `7:`):** zero 3-seat draws in 57,553 rows. The rule-of-three upper bound is:
- 3.04 per 1,000 at the 0-seat-indicator ESS of 987;
- 1.5 per 1,000 counting all rows at that τ;
- 10 per 1,000 at the seat-count ESS of 286.

**Reasoning:** progress.md:2270 states as certain what the sample only bounds at a few per thousand. Two of the auditor's supporting numbers are wrong:
- 57,553 rows hold 6,703 distinct metric tuples. 4,020 is the rectangle's count.
- Only 16 of round 5's "0 of 32" could have produced a 3-D-seat plan. The 16 R+3 attempts ask for 5 R seats of 4 from the 2-D-seat baseline, and `plant_gerrymander` returns None before searching (src/adversarial/gerrymander.py:1705–1706). The evidence is 0 of 16 D+3 searches, which progress.md:464 itself calls "not proof".

### 8. [minor] "8 chains × 260" — **UPHELD**

**Reproduced:** 8 × 260 = 2,080, while 1,820 = 7 × 260. progress.md:263 has "8 chains × 260 …, 1 chain failure". Lines 2245 and 2274 drop the failure.

### 9. [minor] "archived in v0.1.0" — **UPHELD**

**Reproduced:**
- `git ls-tree -r --name-only d7381bf` (the v0.1.0 tag's commit) lists the PNG and the old plotter. That plotter read the gitignored data/results/ia_neutral_seat_distribution.json.
- The tree contains no data/ file and no per-draw or per-plan file from the 1,820-draw ensemble.
- Zenodo record 22102854 holds only districting-bench-v0.1.0.zip (6.0 MB), and release.yml archives "the repository at this commit".

So v0.1.0 archived the figure and the numbers, not the ensemble.

### 10. [minor] R-hat printed without its target — **UPHELD**

**Reproduced:** the footer reads "Seat count: split R-hat 1.014, effective sample 286." with no target, and README:14–34 never mention convergence.

**Reasoning:** the fix needs to carry the ESS, not just the band. I simulated a stationary 3-state chain calibrated to ESS 286 (1,000 replicates). Its split R-hat has median 1.022 and P(≤ 1.01) = 0.045. Printed on its own, the 1.00–1.01 band would read as non-convergence that this ESS cannot diagnose.

### 11. [minor] Labels "49.0%" vs "49.5%" — **PARTLY UPHELD**

**Reproduced (script `11:`):** share(2) − share(1) = 0.50 pts, MCSE 6.04 (ESS 270). Chain differences: −12.5, +8.4, +17.5, +1.2, −14.9, +3.3.

**Reasoning:** the ordering is unresolved (P ≈ 0.53), and the labels carry precision the estimates lack. But the decimal count is not what implies the order: whole-percent labels would read 49% and 50%, a larger apparent gap. The per-chain dots already show the two bars overlapping.

### The auditor's "sound" claims

**Not reproduced as stated: "chain death not tied to seat state."** Eight deaths are too few to establish that. The data support "no significant tie on 8 deaths":
- 5 of the 7 deaths that came after a chain's first draw were in a 2-seat state, against 49.3% exposure (binomial p = 0.22).
- 5 of the 6 chains that died after more than 1,000 draws died at 2 seats (p = 0.10).
- Chain lifetime falls as a chain's 2-seat share rises (Spearman −0.67, p = 0.07; completed chains counted at 12,000).
- The two chains the rectangle drops for dying early, chains 3 and 8, have the highest 2-seat shares of any chain (58.3% and 70.0%).

**Reproduced in substance, with a wording fix: R-hat at this ESS.** I get median 1.022 and P(≤ 1.01) = 0.045; the auditor reported 1.021 and 0.06. The simulated sampler is stationary with this autocorrelation, not "perfectly mixed": an i.i.d. sampler would give ESS ≈ 27,564 and R-hat ≈ 1.00.

**Reproduced as stated:**
- every published value, including 454 draws ≤ 94 persons (448 strictly under), 1.65% and median 225;
- the v1 figures: 51.90%, 1.58%, chains 32.3–75.9%, R-hat 1.138, ESS 39.6;
- v1 rows identical to the first rows of every v2 chain on every column except chain_completed;
- the 2-seat share staying within 49.05–50.24% for discards of 0–1,500 draws;
- ESS of the indicator as the MCSE basis;
- the chain range as a display (a judgement; I found no contrary evidence).

### Reproduction script

Run from the repo root with `PYTHONPATH=src`:

```python
import csv, gzip, json, sys
import numpy as np
from scipy import stats
sys.path.insert(0, "src")
from generate import convergence as CV

p = json.load(open("docs/phase-2/phase-2-report.json"))["IA"]["partisan"]
V, k, EG_ENACTED = p["dem_vote_share"], p["n_districts"], p["efficiency_gap"]
L = np.array([abs(2 * V - 0.5 - s / k) for s in range(k + 1)])          # seat levels
rows = {}
for r in csv.DictReader(gzip.open("docs/experiment-2/ia-draws-v2.csv.gz", "rt")):
    rows.setdefault(int(r["chain_index"]), []).append(r)
eg = {i: np.array([float(r["abs_efficiency_gap@G20PRE"]) for r in v]) for i, v in rows.items()}
seats = {i: np.abs(x[:, None] - L).argmin(1) for i, x in eg.items()}
RC, n = (0, 1, 2, 5, 6, 10), 4594                                        # D-035 rectangle
rect = [seats[i][:n] for i in RC]
pool = np.concatenate(rect)
ind = lambda s: [(c == s).astype(float) for c in rect]
share = {s: (pool == s).mean() for s in (0, 1, 2)}
ess = {s: CV.ess(ind(s)) for s in (0, 1, 2)}
mcse = {s: np.sqrt(share[s] * (1 - share[s]) / ess[s]) for s in (0, 1, 2)}
t5 = stats.t.ppf(0.975, 5)
def tci(x): x = np.asarray(x); m, se = x.mean(), x.std(ddof=1) / np.sqrt(len(x)); return m - t5 * se, m + t5 * se, se
print("counts", {s: int((pool == s).sum()) for s in range(5)}, "all-rows", {s: int(sum((v == s).sum() for v in seats.values())) for s in range(5)})
print("shares %", {s: round(100 * share[s], 2) for s in share}, "ESS", {s: round(ess[s], 1) for s in ess}, "MCSE pts", {s: round(100 * mcse[s], 2) for s in mcse})
print("seat count R-hat %.4f ESS %.1f" % (CV.split_rhat([c.astype(float) for c in rect]), CV.ess([c.astype(float) for c in rect])))

# 1 -- the old estimate's own error
w = np.array([(seats[i][j * 260:(j + 1) * 260] == 2).mean() for i in seats for j in range(len(seats[i]) // 260)])
pre = np.array([(seats[i][:260] == 2).mean() for i in seats if len(seats[i]) >= 260])
tau2 = n * 6 / ess[2]
se_old = {"windows": w.std(ddof=1) / np.sqrt(7), "cold-start": pre.std(ddof=1) / np.sqrt(7), "asymptotic": np.sqrt(share[2] * (1 - share[2]) * tau2 / 1820)}
for lab, se in se_old.items():
    print(f"1: {len(w)} windows; old SE ({lab}) {100*se:.2f} pts; combined z {(share[2]-782/1820)/np.hypot(mcse[2], se):.2f}")
rng = np.random.default_rng(1)
print("1: P(mean of 7 random windows <= 0.43) = %.3f" % np.mean([w[rng.choice(len(w), 7, replace=False)].mean() <= 0.43 for _ in range(100000)]))
w0 = np.array([(seats[i][j * 260:(j + 1) * 260] == 0).mean() for i in seats for j in range(len(seats[i]) // 260)])
se0 = w0.std(ddof=1) / np.sqrt(7)
print(f"1: 0 seats old SE {100*se0:.2f}, combined z {(share[0]-18/1820)/np.hypot(mcse[0], se0):.2f}; new 95% {100*(share[0]-1.96*mcse[0]):.2f}-{100*(share[0]+1.96*mcse[0]):.2f}")
lo, hi, se_c = tci([c.mean() for c in ind(2)])
print(f"1: 2-seat t(5) CI {100*lo:.2f}-{100*hi:.2f}; table-MCSE normal CI {100*(share[2]-1.96*mcse[2]):.2f}-{100*(share[2]+1.96*mcse[2]):.2f}; chains 0+6 full: {100*np.concatenate([seats[0], seats[6]]).__eq__(2).mean():.2f}%")

# 2 -- how uncertain is the MCSE
print("2: chain-level SE %.2f, 95%% range %.2f-%.2f" % (100 * se_c, 100 * se_c * np.sqrt(5 / stats.chi2.ppf(.975, 5)), 100 * se_c * np.sqrt(5 / stats.chi2.ppf(.025, 5))))
def batch_tau(chs, b, ddof=0):
    x = np.concatenate(chs); bm = np.array([c[j*b:(j+1)*b].mean() for c in chs for j in range(len(c)//b)])
    return b * np.sum((bm - x.mean())**2) / (len(bm) - ddof) / x.var(), len(bm)
allc = [(seats[i] == 2).astype(float) for i in seats]
two = [(seats[i] == 2).astype(float) for i in (0, 6)]
for b in (500, 1000, 3000):
    ta, _ = batch_tau(allc, b); tr, _ = batch_tau(ind(2), b); t2, nb = batch_tau(two, b, ddof=1)
    print(f"2: b={b}: tau all rows {ta:.0f} (rect MCSE {100*np.sqrt(share[2]*(1-share[2])*ta/(6*n)):.2f}), rectangle {tr:.0f}, two 12k chains (ddof=1, {nb} batches) {t2:.0f}")

# 3 -- the footer under the rule of record (mid-rank, two-sided, 0.99)
sg = np.concatenate([np.where(seats[i][:n] == 2, -eg[i][:n], eg[i][:n]) for i in RC])
mid = lambda ref, v: ((ref < v).sum() + 0.5 * (ref == v).sum()) / len(ref)
z0 = np.unique(sg[pool == 0], return_counts=True)
print("3: enacted mid-rank %.4f; per chain" % mid(sg, EG_ENACTED),
      [round(mid(np.where(seats[i][:n] == 2, -eg[i][:n], eg[i][:n]), EG_ENACTED), 4) for i in RC])
print("3: 0-seat EG values and counts", list(zip(z0[0], z0[1])), "mid-ranks", [round(mid(sg, v), 4) for v in z0[0]], "; 2-seat level stat %.3f" % max(mid(sg, -L[2]), 1 - mid(sg, -L[2])))

# 5 -- the 0-seat share
runs = sum(int(c[0] == 0) + int(((c[1:] == 0) & (c[:-1] != 0)).sum()) for c in rect)
lo0, hi0, _ = tci([c.mean() for c in ind(0)])
print(f"5: visits {runs}; chain 6 first 500: {(rect[4][:500]==0).sum()} of {(rect[4]==0).sum()}; drop 500: {100*np.mean(np.concatenate([c[500:] for c in rect])==0):.2f}%; t(5) CI {100*lo0:.2f}-{100*hi0:.2f}")

# 6 -- turnout term
res = np.concatenate([eg[i][:n] for i in RC]) - L[pool]
print("6: residual SD 1 seat %.4f, 2 seats %.4f; max |res| %.4f; gap %.4f; gap - max %.4f; Iowa read-back residual %.2e" % (
    res[pool == 1].std(ddof=1), res[pool == 2].std(ddof=1), np.abs(res).max(), np.diff(np.sort(L)).min(), np.diff(np.sort(L)).min() - np.abs(res).max(), abs(EG_ENACTED) - L[0]))

# 7 -- distinct plans (metric tuples)
cols = [c for c in rows[0][0] if c not in ("chain_index", "chain_seed", "chain_completed", "draw")]
print("7: distinct tuples all rows", len({tuple(r[c] for c in cols) for v in rows.values() for r in v}),
      "rectangle", len({tuple(r[c] for c in cols) for i in RC for r in rows[i][:n]}), "; 3/ESS(0 seats) per 1000 = %.2f" % (3000 / ess[0]))

# 11 -- 2-seat minus 1-seat
dd = [a - b for a, b in zip(ind(2), ind(1))]
x = np.concatenate(dd)
print("11: diff %.2f pts, MCSE %.2f; chains %s" % (100 * x.mean(), 100 * x.std() / np.sqrt(CV.ess(dd)), np.round([100 * c.mean() for c in dd], 1)))
```

**Other checks:**
- **Rule of record:** `outlier.locate(None, {"efficiency_gap": signed_eg}, {"efficiency_gap": v}, metrics=["efficiency_gap"], ensemble_plan_ids=metric_tuples)`, then `confusion.flag` with `Rule(0.99, "two_sided", "any", ("efficiency_gap",), "exclude")`.
- **Guard probe:** `recover_seats([0.1287], seat_levels(V, 4))`.
- **R-hat simulation:** 6 chains × 4,594 draws per replicate. At each step the chain redraws from (0.0143, 0.4904, 0.4953) with probability 0.02, else stays. Scored with `CV.split_rhat` and `CV.ess`.
- **v0.1.0 tree:** `git ls-tree -r --name-only d7381bfdce05b37ede2ddccc84e41bfb6e1df06c`.
- **Vehtari et al. (2021) text:** checked against arXiv:1903.08008v5.

---

## Author's response

The refuter found no allegation to refute, so every one is answered by a change,
in the commits that follow `8d5d4fa`. Numbers the answers quote are printed by
`tools/plot_seat_distribution.py` and pinned by `tests/test_seat_distribution.py`,
except where they come from the two reports above.

| # | Allegation | Refuter | What changed |
| --- | --- | --- | --- |
| 1 | "What changed is the shares" presents as a change what the data cannot tell from none | Upheld | The README and `docs/progress.md` now say 43% and 49.5% do not disagree. The plotter prints the standard error of a seven-chain, 260-draw estimate three ways: 8.9 points from chain starts, 10.8 from all 260-draw windows, 11.9 from the autocorrelation time. |
| 2 | The Monte Carlo standard error states more precision than the sample supports | Partly upheld; "the low end" not upheld | "The low end" is dropped. The README says 3 to 4 points. `docs/progress.md` gives the ESS-based 3.05, block means of 3.3–3.9 over all committed rows, which the plotter now prints, and the refuter's chain-level 2.6. The figure's footer quotes the block-means range beside the ESS-based whiskers. |
| 3 | The footer's "a 2-seat shift is not detectable" | Upheld, evidence corrected | The verdict was removed in the first revision. The refuter's correction, that the flag rule fires on a zero-seat plan or not by the parity of its district totals, is recorded in `docs/progress.md` as an open defect of the rule, for the `Statistician` and the owner. This change does not touch `src/detect/`. |
| 4 | "Prints every number above" is false | Upheld, a sub-claim corrected | The plotter now prints every number `docs/progress.md` quotes about the sample, except those marked as coming from this record, and the tests pin them. `docs/progress.md` lists all five committed files it reads. |
| 5 | 1.4% is quoted without an interval | Upheld | The README, the figure's note and `docs/progress.md` give the six chains' 0.4–2.5%, and `docs/progress.md` the warm-up check, 1.15%. |
| 6 | The seat-recovery evidence is weaker than stated | Upheld | `recover_seats` refuses any non-sweep draw beyond half of the half-gap, and requires every sweep to sit on the half-vote grid the statewide total's parity allows. Controls in the tests must make it refuse. D-039 and `docs/progress.md` call the read-back weak, and the tests pin that Colorado's draws are refused. |
| 7 | "Nothing else" states as certain what the sample only bounds | Partly upheld | `docs/progress.md` bounds the 3-seat share below about 1% by the rule of three, calls 0–2 the sampler's range, and names the 3-seat plan in `src/adversarial/gerrymander.py` that meets the same constraints. The round-5 evidence is stated as 0 of 16 D+3 searches. Distinct plans are counted for the rectangle (4,020) and for all committed rows (6,703). |
| 8 | "8 chains × 260" | Upheld | Now "8 chains of 260 draws requested, 7 completed". |
| 9 | "Archived in v0.1.0" | Upheld | Now "never committed; v0.1.0 archived only its figure and its numbers". |
| 10 | R-hat is printed without its target | Upheld | The figure and the README give `CRITERIA.md` §8's 1.00–1.01 band, and the figure reads inside or outside off the value. The README and `docs/progress.md` add the refuter's simulation: at 286 effective draws the band cannot be resolved. |
| 11 | The labels 49.0% and 49.5% imply an order | Partly upheld | Each share is labelled with its ±2 standard errors and the per-chain dots stay. `docs/progress.md` says the order is not identified and the chains disagree about its sign. |
| — | The auditor's "chain death is not tied to seat state" | Not reproduced as stated | `docs/progress.md` now says the tie is not significant on seven deaths (p = 0.22), notes that the two chains the rectangle drops for dying early have the highest 2-seat shares, and gives the 2-seat share on every rectangle the convergence report offers, from 45.3% to 50.5%. |

The `Statistician`'s "Outside the diff" items are both answered:
`src/adversarial/gerrymander.py` now names the ensemble behind each number it
quotes, and `docs/progress.md` lists `tools/plot_experiment_3.py` among the
places that still read the gitignored file.

The routing reviewers' second round on the revised change is answered in the same
commit as this response, and, like their first, is not reproduced here.
