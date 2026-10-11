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

---

# Second audit — the analysis added in review

Three rounds of review by the routing reviewers added analysis the first audit,
on `8d5d4fa`, never saw: the compactness caveat, the block-means and short-run
standard errors, the rectangle and chain-death checks, the reading of R-hat at
this effective sample size, and the flag-rule paragraph. They went through the
same audit, at commit `afab97e`.

- **Auditor:** the `Statistician` agent, a fresh instance, attacking the
  inference lens.
- **Refuter:** a general-purpose agent, told to default to "refuted" and to
  reproduce every number before agreeing.

Both reports are verbatim. The last section is the author's response, and is not
part of either report.

---

## Second auditor — Statistician

## Auditor (second audit): Statistician, inference lens

**Scope.** This audit covers commit `afab97e` on `claude/first-result-and-planscore`, against the first audit's commit `8d5d4fa`. I read:
- `git diff 8d5d4fa..afab97e` for `README.md`, `docs/progress.md`, `docs/DECISIONS.md`, `tools/plot_seat_distribution.py` and `tests/test_seat_distribution.py`;
- `docs/figures/ia-neutral-seat-distribution.png`;
- the committed evidence: `docs/experiment-2/ia-draws-v2.csv.gz` and its chain sidecar, `ia-draws.csv.gz`, `ia-convergence-rectangles.json`, and `docs/phase-2/phase-2-report.json`.

I was not given the author's reasoning, and I edited no repository file. `git status` is clean. Line numbers refer to `afab97e`.

**Summary.**
- Every number the section quotes reproduces exactly. I checked them with the plotter and with my own loader, which reads the CSV directly through `csv` and `gzip`.
- A fresh render (`tools/plot_seat_distribution.py --out <scratch>`) is byte-identical to the committed figure (sha256 `811cad73…`).
- `tests/test_seat_distribution.py` gives 30 passed, and `tools/check_firewall.py` prints clean.
- The headline survives: 0–2 seats, and 2 seats in about half the draws.
- The allegations concern what the numbers are taken to show: three material, four minor.

### Allegations

**1. The compactness contrast is quoted as robust ("in every chain", 4.5%), but it rests on one warm-up excursion and on the 500-draw warm-up choice, and it carries no interval.** Severity: material.
- **Location:**
  - `README.md:52-56`;
  - `docs/progress.md:2409-2416`;
  - `docs/DECISIONS.md:1213-1215` and `1225-1227`;
  - the figure note (`tools/plot_seat_distribution.py:534-542`, `600-610`);
  - pinned at `tests/test_seat_distribution.py:150-151` and `288-293`.
- **Claim:**
  - README: "in each of the six chains 0 seats is commoner among the draws with 51 or more. Pooled, 4.5% of those give 0 seats, or 2.2% once each chain's first 500 draws are dropped, against 1.0% of the rest".
  - progress.md: "Part of that is warm-up … Either way the enacted plan's outcome is commoner among plans as uncompact as it."
- **Reproduced.** The numbers themselves are exact. What they are taken to show is the problem:
  - **One excursion.** 89 of the 151 zero-seat draws at 51 or more cut edges come from a single excursion of chain 6, at draws 234–437 of its first 500. That excursion holds 8 distinct metric rows (plans), and 84 of its draws sit at exactly 51 cut edges. Dropping 500 draws removes about two-thirds of the excess (2.4 of 3.5 points), not "part" of it. A strict ">51" split on the full rectangle gives 2.18% against 1.36%.
  - **"In every chain" depends on the warm-up length.**

    | Draws dropped per chain | Chains higher at ≥51 |
    | --- | --- |
    | 0, 250, 500 | 6 of 6 |
    | 750, 1,000, 1,500 | 5 of 6 (chain 6 reverses, by −0.4 pts) |
    | 2,000 | 4 of 6 |

    After 500 dropped, chain 6's ≥51 cell holds 6 zero-seat draws from 2 visits. The whole after-warm-up contrast rests on 30 zero-seat visits at ≥51 and 45 below.
  - **No uncertainty is given.** The chain-level t(5) 95% interval for the per-chain difference:

    | Draws dropped | 95% interval (pts) |
    | --- | --- |
    | 0 (full rectangle) | −0.7 to +5.7 (includes zero) |
    | 500 | +0.3 to +2.3 |
    | 750 | −0.1 to +1.7 |
    | 1,000, 1,500, 2,000 | include zero |

    An autocorrelation-preserving test gives p = 0.0003 on the full rectangle and p = 0.04 after 500. The test shifts each chain's cut-edge series circularly against its seat series, 4,000 times, with offsets of at least 300 draws.
  - **The direction itself is sound**, and it has better support than the ≥51 split:
    - None of the 7,850 draws at 40–42 cut edges gives 0 seats.
    - At a ≥45 split the shares are 2.62% against 0.09%.
    - A chain-stratified Mantel–Haenszel ratio equals the crude ratio: 4.48 against 4.49 on the full rectangle, and 2.20 against 2.11 after 500. So the pooled figure is not a chain-composition artefact.
    - The ratio that survives warm-up is about 1.8–2.2, not 4.5. Pooled shares after any warm-up of 500 or more are 1.6–2.2% against 0.97–1.11%.
- **Assessment:**
  - "0 seats is commoner among less compact draws" is supported.
  - "In every chain" is a property of the 500-draw warm-up, and the quoted magnitudes need an interval.
  - The test at `tests/test_seat_distribution.py:150-151` pins only the full-rectangle sign.

**2. Compactness is presented as a second like-for-like failure. It is an outcome of the map, and conditioning on it would absorb a partisan effect as readily as a neutral one.** Severity: material.
- **Location:**
  - `README.md:50-56` ("not like-for-like … Nor are they as uncompact");
  - `docs/DECISIONS.md:1209-1231` (D-041, VALUE);
  - `docs/progress.md:2409-2421`;
  - the figure note.
- **Claim:** the comparison is not like-for-like "on two counts", population equality and compactness. D-041 lists filtering "as uncompact as the enacted plan" and re-sampling "under a compactness constraint" as the alternatives.
- **What is wrong:**
  - Population equality is a constraint the enacted plan had to meet. Matching the reference to it is matching on a cause.
  - Compactness is not a constraint the plan meets and the draws fail; the draws are more compact. It is an outcome of where the lines go.
  - In these draws compactness is tied to the seat outcome itself: no draw at 40–42 cut edges gives 0 seats. Any process that produces 0 seats here, neutral or partisan, produces less compact plans.
  - Conditioning the reference on the enacted plan's compactness therefore conditions on a variable between the map-drawer's choices and the seats, a mediator. It raises the reference's 0-seat share whether or not the plan was drawn for that outcome, which pushes the comparison toward "unremarkable" by construction.
  - D-041's alternatives are set aside for selection and normative reasons only. Neither D-041 nor the README records this argument.
- **What the repository's own evidence supports instead:** the compactness gap is largely downstream of the population gap.
  - The 454 population-tight draws (spread of 94 or less) average 48.1 cut edges against 45.5 for the rest.
  - 21.6% of them have 51 or more cut edges, against 12.0% of the rest.
  - This is consistent with `docs/FEASIBILITY.md` §5.3 as `docs/progress.md:2418-2420` cites it.
  - The adjustment that matches a cause is re-sampling at the 94-person tolerance, and compactness follows from it.
  - Presenting compactness as a coequal second caveat counts that one mismatch twice, and it invites an adjustment the data argue against.
- **Why material:** it misframes the caveat on the comparison with a real map, and the argument is missing from the record of a VALUE decision the owner has yet to make.

**3. "What the chains do show is drift" rests on numbers within Monte Carlo noise, contradicts the R-hat sentence before it, and omits the evidence that does exceed noise.** Severity: material.
- **Location:** `README.md:35-42`. `docs/progress.md:2325-2326` and `2330-2332` give the same numbers without the word "drift".
- **Claim:** "What the chains do show is drift: the 2-seat share is 46.1% over the first half of the rectangle and 53.0% over the second, and 45.3–50.5% on the other prefix rectangles the convergence report offers."
- **Reproduced. The half gap is within noise.**
  - Null model: a stationary geometric chain at the observed autocorrelation (τ 99–103, median ESS 271–285), 6 × 4,594 draws from a stationary start, 1,000 replicates.
  - In that model the 6.9-point half gap has SD 5.8–6.0 points, and a gap at least that large occurs in 24% of replicates.
  - At τ = 166, the all-rows block-means value, it occurs in 36%.
  - Calibrated instead to the mean single-chain τ of 88, the gap is about 1.25 SD, so p is about 0.2.
- **The rectangles are within noise.** Each lies within its own Monte Carlo error of 49.5%:

  | Rectangle | 2-seat share | z against 49.5% |
  | --- | --- | --- |
  | 4 × 8,133 | 45.3% | −1.27 |
  | 5 × 6,495 | 48.0% | −0.43 |
  | 7 × 4,282 | 50.5% | +0.26 |
  | 8 × 1,863 | 50.3% | +0.10 |

  They are also nested, overlapping samples of the same chains.
- **The two sentences contradict each other.**
  - The sentence before says R-hat cannot resolve convergence at this size.
  - Split R-hat is built from exactly these half-chain comparisons.
  - The observed 1.0136 sits at the 13th–16th percentile of the stationary null, whose median is 1.021–1.022. The halves agree better than a typical stationary sampler's halves would.
  - As written, the two sentences cannot both hold.
- **What does exceed noise is chain-level, and the README does not cite it:**
  - (a) Chains 0 and 6, the two that start at 1 seat, put 33.7% and 33.1% of their first halves at 2 seats. A stationary chain started at 1 seat does that in both chains with probability 0.006 at τ = 103, and 0.02 at τ = 166. By exchangeability, the two named half-chains are the two lowest of 12 with probability 1/66. This test is post hoc.
  - (b) Beyond the rectangle, the two chains that ran to 12,000 draws put 33.2% and 51.6% of their draws at 2 seats. On batch means the Welch t is −2.5 to −3.2, p = 0.004–0.024, for blocks of 500 to 3,000. Chain 0's four 3,000-draw blocks (41, 31, 35 and 26%) are four of the five lowest of the 16 such blocks.
- **Assessment:**
  - The caution may well be right in direction: it fits slow mixing between a 1-seat-heavy region and the rest.
  - But the evidence it states is noise. As written, the sentence is a verdict about the sampler that its own numbers do not carry.
  - The supportable version cites (a) and (b) with their uncertainty, and says that on the rectangle itself neither R-hat nor the half split can tell.

**4. How the Monte Carlo error is presented.** Severity: minor.
- **Location:**
  - `README.md:16` ("give or take about 6 points") and `README.md:20-21` ("3 to 4 points");
  - `tools/plot_seat_distribution.py:550-552` and `640-643` (labels and whiskers from the ESS-based standard error) and `580-584` (footer R-hat);
  - `tests/test_seat_distribution.py:84-86`.
- **(a) The whiskers use the lowest estimate.** The whiskers, the ±6.0 and ±6.1 labels and the alt text all use 3.00 and 3.05 points. Those are the lowest of the standard-error estimates the README endorses. By the README's own "3 to 4 points", two standard errors are 6–8 points.
- **(b) "3 to 4" assumes the chains mix.** It is a range of point estimates.
  - The longest-block estimate (b = 3,000, 16 batches) has its own 95% range of 3.0–6.2 points.
  - Allegation 3(b) is evidence that the chains do not fully mix. In that case every one of these estimates is a lower bound, and "at least 3 to 4 points" is what the evidence supports.
- **(c) The footer reads as a verdict.** It prints "outside CRITERIA §8's 1.00–1.01 band" without the README's qualifier. That qualifier is that a stationary sampler at 286 effective draws reads outside the band about 95% of the time. The figure travels alone, as the module docstring says, so the line reads as a convergence verdict the rectangle cannot deliver.

**5. The chain-death test cannot tell, and the text does not say so.** Severity: minor.
- **Location:** `docs/progress.md:2333-2337`.
- **Claim:** "5 of the 7 chains that died after their first draw died at a 2-seat plan … not significant (binomial p = 0.22)".
- **Reproduced.** 5 of 7 is correct.
  - **The p-value is one-sided, and the text doesn't say so.**
    - One-sided exact p is 0.20 against the all-rows exposure of 48.55%, and 0.21–0.23 for exposures of 49.3–50%.
    - Two-sided p is 0.28.
    - The direction was chosen after seeing the data, and the text doesn't say that either.
  - **The test has almost no power.**
    - With 7 deaths, a one-sided 5% test rejects only at 7 of 7, with actual α 0.006.
    - Its power is 5% at a hazard ratio of 2, 12% at 3 and 26% at 5.
    - The exact 95% interval on the hazard ratio is 0.43 to 28.
  - **"Died after their first draw" excludes chain 9.** That chain stopped at its first step from a 0-seat start. Including it gives 5 of 8, p = 0.33.
- **Assessment:**
  - "Not significant" here means the test could not have told either way.
  - The sentence's "but it is the direction a selection effect would push" is right.
  - Without the interval, "not significant" reads as reassurance.

**6. The flag-rule calls hold only when the rule is given plan ids.** Severity: minor.
- **Location:** `docs/progress.md:2435-2439`.
- **Claim:** "would be flagged … would not … would be".
- **Reproduced.** The mid-ranks 0.9896, 0.9968 and 0.9928 are exact. But:
  - The rule of record (`src/detect/bench.py:309-317`) decides only when the location's effective sample size reaches `required_ess`, which is 50 at threshold 0.99 (`src/detect/confusion.py:466-473`).
  - Without plan ids, that ESS is Kish over value multiplicities (`src/detect/outlier.py:899-906`): 39.0 on this reference.
  - Over metric tuples standing in for plan ids, it is 269.8.
  - The committed draws carry no plan ids, so against this reference the rule refuses rather than flags.
- **What the record said:** the audit record this paragraph cites included that condition ("Without plan ids (Kish ESS 39 < 50), the rule refuses to decide at all"). The paragraph drops it.

**7. "Because zero-seat plans come early" generalizes one chain.** Severity: minor.
- **Location:** `docs/progress.md:2327-2328`.
- **Reproduced.** The six chains' first 500 draws hold 112 zero-seat draws:

  | Chain | Zero-seat draws in its first 500 |
  | --- | --- |
  | 6 (one excursion, draws 234–437) | 89 |
  | 2 | 21 |
  | 0 | 2 |
  | 1, 5, 10 | 0 |

  The 1.43% to 1.15% shift is one chain's early visit, not a property of zero-seat plans.

### Checked and found sound

- **Every quoted number** reproduces from my own loader:
  - counts 395 / 13,516 / 13,653, and 832 / 28,780 / 27,941 over all committed rows;
  - ESS 987 / 278 / 268 (my own Geyer estimate gives 268.1) and MCSE 0.38 / 3.00 / 3.05;
  - seat-count R-hat 1.0136 and ESS 286.1;
  - halves 46.1 / 53.0%;
  - shares after dropping 500 draws: 1.15% at 0 seats and 50.24% at 2;
  - the rectangle shares, the chain fates and the Senate counts;
  - 454 draws at or under 94 persons, and a median spread of 225;
  - the cut-edge splits, 151 of 3,341 and 244 of 24,223;
  - 216 sweeps at 2.5 votes and 179 at 3.5.
- **Item 2: block means.**
  - 3.33, 3.66 and 3.88 reproduce.
  - The chains outside the rectangle do not drive them: restricted to the six rectangle chains at full length they are 3.16, 3.33 and 3.62.
  - Within the rectangle, batch means give 2.1–2.9 and single-chain τ ranges from 31 to 437. That fits the stated reason for using all rows, that the rectangle's horizon understates the dependence.
  - "3 to 4 points" is a fair summary of the point estimates; allegation 4(b) covers the caveat.
- **Item 3: the short-run standard error.**
  - 10.77, 8.88 and 11.88 reproduce. A finite-length correction to the asymptotic estimate gives 10.65.
  - z against 43% is 0.52–0.70, with either 3.05 or 3.9 as the new standard error.
  - The conclusion is stronger than stated. Run as v0.1.0 ran, v2's own chains reproduce a 43%-like number: every 7-of-8 subset of their eight first-260-draw windows gives 30.4–41.6%, and the mean of the eight is 36.4%.
  - The start-based estimate measures spread around the starts' own mean, so it leaves out a start-state bias of about −13 points. A cold-start 7 × 260 estimate's error is nearer 16 points RMSE.
  - "Do not disagree" holds. "Cannot be told apart" would be more exact, since the old estimate's 95% interval spans roughly 20% to 66%.
- **Item 4: arithmetic.** The rectangle shares reproduce. 5 of 7 reproduces, and p = 0.22 lies within 0.20–0.23 across the exposure bases.
- **Item 5: R-hat cannot resolve the band.**
  - My own simulation reproduces it. Geometric chains at τ 99–103 give a median split R-hat of 1.021–1.022 and P(≤ 1.01) of 0.04–0.05.
  - The real dependence is heavier-tailed, with all-rows block-means τ of 122–177. At τ = 166 the median is 1.037 and P(≤ 1.01) is 0.007, so the statement is conservative.
  - "With the same autocorrelation" (`docs/progress.md:2294`) means the same integrated autocorrelation time.
- **Item 6: arithmetic.**
  - The enacted plan's |EG| sits 3.50 votes above the 0-seat level, in the 179-draw group.
  - The rule's statistic is max(p, 1 − p) ≥ 0.99 (`src/detect/confusion.py:1027-1055`), so the stated calls are right whenever the rule decides (allegation 6).
  - The parity account is right: with T odd and k = 4, j odd districts in {1, 3} give offsets of 3.5 and 2.5 votes.
- **Other claims that hold:**
  - "45 per chain, 22 per split chain".
  - "At least 4,020 distinct plans" is a valid lower bound.
  - 18,303 repeats.
  - The rule-of-three bound of 3/286 = 1.05%, which is conservative against the rare-event ESS.
  - The 1-versus-2-seat order is not identified.
  - The Senate's 3-seat draws all fall at chain 0, draws 232–239.
  - The two contests agree on 82.5% of draws.
  - Vehtari's "400" is the four-chain form of 100 per chain, which would be 600 for six chains. The conclusion is unaffected.

### Reproduction

Every quoted number above comes from the scripts in `/tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/audit2-stat/`; their outputs are saved there as `*.out`.

- `repro_audit2.py` is self-contained. Run it from the worktree root with `PYTHONPATH=src python <path>/repro_audit2.py`. It runs in about 26 s and rebuilds allegations 1, 3, 5 and 6 and the item-3 subsets.
- Its R-hat null uses 300 replicates and gives median 1.023, P(≤ 1.01) 0.06 and P(≤ observed) 0.13. The 1,000-replicate figures quoted above come from `a5_null.py`.
- The other scripts:
  - `load.py`: the independent loader;
  - `a1_compact.py`, `a1b_compact.py`, `a1c_mh.py`, `a1d_tight.py`: allegations 1 and 2;
  - `a2_mcse.py`, `a2b_mcse.py`: the Monte Carlo error;
  - `a3_shortrun.py`: item 3;
  - `a4_rect.py`, `a4b_death.py`: item 4;
  - `a5_null.py`, `a5b_starts.py`: allegation 3 and item 5;
  - `a6_flag.py`, `a6b_kish.py`: allegation 6.

Core of `repro_audit2.py`. Seats are read off by nearest level; the plotter's sweep and margin checks pass on these draws, so the readings coincide.

```python
rows = {}
for r in csv.DictReader(gzip.open("docs/experiment-2/ia-draws-v2.csv.gz", "rt")):
    rows.setdefault(int(r["chain_index"]), []).append(r)
V, T = 759_061 / 1_656_733, 1_656_733
L = np.array([abs(2 * V - 0.5 - s / 4) for s in range(5)])
eg = {i: np.array([float(r["abs_efficiency_gap@G20PRE"]) for r in v]) for i, v in rows.items()}
seats = {i: np.abs(x[:, None] - L).argmin(1) for i, x in eg.items()}
cut = {i: np.array([int(r["cut_edges"]) for r in v]) for i, v in rows.items()}
RC, N = (0, 1, 2, 5, 6, 10), 4594
# 1: per-chain (S[i][burn:][C>=51]==0).mean() - (...<51...).mean(), t(5) CI, burn in 0..2000;
#    toroidal null: np.roll(cut series, rng.integers(300, n-300)) per chain, 4,000 times
# 3: geometric null -- per step redraw the seat state from the rectangle marginal with prob 2/(tau+1);
#    6 x 4,594, stationary start; half gap and CV.split_rhat; chains 0 vs 6 Welch t on batch means
# 5: stats.binomtest(5, 7, 0.4855, alternative="greater"); exact CI -> hazard ratio; power at 7/7
# 6: mid-rank ((ref<v)+0.5*(ref==v))/n on the sign-aligned EG; O.kish_ess over values vs metric tuples
```

---

## Second refuter

## Refutation of the Statistician's second-audit allegations (refuter, fresh context)

**Overall.** No allegation is refuted outright, and all of the auditor's numbers reproduce, with small exceptions noted below. Two allegations are upheld (3, and 7 on stronger evidence than alleged). Five are partly upheld (1, 2, 4, 5 and 6). I lower allegation 1 from material to minor. Allegation 2 stays material only as to D-041's record. Two of the auditor's "checked and found sound" claims do not reproduce as stated: the single-chain τ range and the reading of Vehtari et al.'s 400. Neither changes a conclusion.

**What I checked against.**
- **Commit:** `afab97e`. The working tree was clean before and after. I edited no repository file. I read the allegations, the text under audit, the code and the committed evidence. I did not read commit messages or the auditor's scripts.
- **Loader:** my own, using pandas with round-trip float parsing. The default parser merges distinct decimals: it gives 3,718 distinct rows on the rectangle instead of 4,020, and 19,088 repeats instead of 18,303. That would corrupt every tie count below.
- **Seat reading:** each draw gets the nearest folded level |2V − ½ − s/4|. Both D-039 checks are asserted on all 57,553 rows: every sweep sits 2.5 or 3.5 votes above its level, and every other draw is within half the half-gap. A second reading in a separate loader unfolds the sign; it agreed on every draw.
- **Diagnostics:** ESS and split R-hat come from `generate.convergence`. My own Geyer ESS matches it on every indicator (986.8 / 278.3 / 268.1).
- **Rule of record:** `detect.bench.RULE`, run through `outlier.locate` and `confusion.flag`.
- **Nulls for allegation 3:** two of my own, neither the auditor's.
  - A geometric-redraw chain: at each step it redraws from the rectangle marginal with probability 2/(τ+1).
  - A circular block bootstrap of the observed rectangle.
- **Figure, tests, firewall:**
  - `tools/plot_seat_distribution.py --out <scratch>` writes a PNG byte-identical to the committed figure (sha256 `811cad73…`).
  - `tests/test_seat_distribution.py` gives 30 passed.
  - `tools/check_firewall.py` prints clean.

**Baseline, reproduced exactly:**
- Rectangle counts 395 / 13,516 / 13,653; over all rows, 832 / 28,780 / 27,941.
- ESS 986.8 / 278.3 / 268.1; MCSE 0.38 / 3.00 / 3.05 pts.
- Seat-count split R-hat 1.0136, ESS 286.1.
- 4,020 distinct rows on the rectangle (6,703 over all rows); 18,303 repeats.
- Senate counts 270 / 11,410 / 15,876 / 8.

### 1. [material → minor] The compactness contrast — **PARTLY UPHELD**

**Reproduced:**

| Draws dropped per chain | Chains higher at ≥51 | 0 seats at ≥51 vs below | Ratio | t(5) 95% for the per-chain difference |
| --- | --- | --- | --- | --- |
| 0 | 6 of 6 | 4.52% vs 1.01% | 4.49 | −0.68 to +5.73 pts |
| 250 | 6 of 6 | 4.50% vs 1.05% | 4.28 | −0.61 to +5.75 |
| 500 | 6 of 6 | 2.16% vs 1.02% | 2.11 | +0.29 to +2.27 |
| 750 | 5 of 6 | 1.63% vs 0.97% | 1.68 | −0.11 to +1.68 |
| 1,000 | 5 of 6 | 1.78% vs 1.03% | 1.72 | −0.03 to +1.72 |
| 1,500 | 5 of 6 | 1.95% vs 1.10% | 1.77 | −0.15 to +1.99 |
| 2,000 | 4 of 6 | 1.64% vs 1.11% | 1.47 | −1.08 to +2.31 |

- **The excursion:** chain 6's draws 234–437 hold 89 of the 151 zero-seat draws at ≥51 cut edges, from 8 distinct metric rows. 84 of them sit at exactly 51, which is the enacted plan's own value and so the split point. A strict >51 split gives 2.18% against 1.36%.
- **Visits:**
  - 40 zero-seat visits at ≥51 against 51 below on the full rectangle, and 30 against 45 after 500 draws are dropped.
  - After 500, chain 6's ≥51 cell holds 6 draws from 2 visits.
- **Composition and dependence:**
  - The chain-stratified Mantel–Haenszel ratio is 4.48 (crude 4.49), and 2.20 after 500 (crude 2.11).
  - A circular-shift test (4,000 shifts, offsets of at least 300) gives one-sided p = 0.0005, and 0.039 after 500.
- **Other splits:**
  - At splits of 45 and of 47 cut edges, the direction holds in all six chains at every warm-up I tried (0, 500, 750, 1,000 and 2,000).
  - At ≥45 the shares are 2.62% against 0.09%.
  - None of the 7,850 draws at 40–42 cut edges gives 0 seats.

**Upheld:**
- The full-rectangle 4.5% rests mostly on one excursion that sits on the split value.
- "In each of the six chains" at the enacted plan's level holds only for warm-ups of 500 or less.
- No interval is given anywhere for the contrast: not at README.md:52–55, not at docs/progress.md:2412–2416, not in the figure note (tools/plot_seat_distribution.py:600–610), and not in D-041.

**Not upheld:**
- That the text claims more than is true. Both variants it quotes are 6 of 6, and it prints the 500-draw variant that removes the excursion.
- That "Part of that is warm-up" is wrong. Two-thirds (2.4 of 3.5 points) is a part; "most of it" would be more exact.

**Correction:** the ratio "that survives warm-up" is 1.47–2.11 crude for warm-ups of 500–2,000 (Mantel–Haenszel 2.20 at 500). That makes it about 1.5–2.2, not 1.8–2.2.

**Severity: minor.**
- The numbers serve one inference: the zero-seat share depends on compactness, so the unconditioned 1.43% is not like-for-like.
- That inference holds at every warm-up, at splits of 45 and 47 in every chain, and under the shift test.
- What is fragile is the magnitude and the per-chain claim at exactly 51. The text already brackets the magnitude. What it lacks is an interval and the excursion fact.

### 2. [material → material for D-041 only] Compactness as a second like-for-like failure — **PARTLY UPHELD**

**Reproduced:**
- The 454 draws with a population spread of 94 or less average 48.09 cut edges, against 45.47 for the rest. 21.6% of them have 51 or more, against 12.0%.
- No zero-seat draw falls at 40–42 cut edges. Zero-seat draws average 49.16 cut edges, against 45.46.

**Upheld: the argument.**
- Population spread and compactness are both properties of the plan the drawer chose. What separates them is this:
  - Population equality is the binding constraint, first in Iowa's ordered criteria (`docs/CRITERIA.md` §2.1), and the ensemble fails it.
  - Compactness is a lower-ranked criterion that the ensemble already over-satisfies. The enacted plan's level of compactness is therefore discretionary.
- Conditioning the reference on that level conditions on a post-treatment property that is associated with the outcome. Strictly, compactness is a co-outcome of the plan rather than a mediator, but the bias is the same. The conditioning raises the reference's zero-seat share however the plan was drawn, which moves the comparison toward "unremarkable".
- D-041 (`docs/DECISIONS.md`:1220–1231) treats the two features symmetrically in both of its alternatives and does not record this argument. Nor do README.md:50–55 or docs/progress.md:2409–2421.
- For a VALUE decision the owner has yet to make, that omission is material.

**Not upheld: the evidence offered for the remedy.**
- **"The compactness gap is largely downstream of the population gap."**
  - In these draws, population tightness moves the enacted plan's cut-edge mid-rank only from 0.899 (among the rest) to 0.794 (among the tight draws). The tight draws still average about 3 cut edges fewer than its 51.
  - Over the rectangle, spread and cut edges are barely associated (Spearman 0.05).
  - Mean cut edges by spread band (≤94 / 95–150 / 151–225 / 226–400) are 48.1 / 44.8 / 45.7 / 45.5, so the 95–150 band is the most compact.
  - The 454 tight draws are a filter of 100 visits, which D-041 itself says is not the matched comparison.
  - `docs/FEASIBILITY.md` §5.3's 57–67 cut edges come from a targeted search, so they support a mechanism, not a magnitude.
  - What the evidence carries is "partly downstream, by an amount these draws cannot measure".
- **"Counts that one mismatch twice."** docs/progress.md:2418–2421 already ties the two caveats together through FEASIBILITY §5.3. The README and D-041 present them as two counts. That is consistent with tightness explaining only part of the gap.
- **"Any process that produces 0 seats here, neutral or partisan, produces less compact plans."**
  - This is an association inside this ensemble, and it is concentrated in the 151–300-person spread band. 148 of the 151 zero-seat draws at ≥51 cut edges sit there (38 visits, against 46 below 51).
  - The ≤150 band holds 7 zero-seat visits in all (1 at ≥51, 6 below). That is too few to show the association either way.
  - A neutral ensemble cannot speak for a partisan process.

**Severity:**
- Material for D-041's record.
- Minor for the README, which conditions on nothing and calls the comparison not yet a finding.
- The correction is to add the post-treatment argument to D-041, not to merge the two caveats.

### 3. [material] "What the chains do show is drift" — **UPHELD**, one sub-claim corrected

**Reproduced:**
- **The half gap:** 6.87 pts (from 46.10% to 52.97%). Using each half's own ESS, the standard errors are 4.15 and 5.61 pts, so z = 0.98.
- **As a contrast:** among the 12 half-chain means, the first-versus-second contrast is χ²₁ = 1.27 (p = 0.26), against the stationary variance at τ = 102.8.
- **Stationary nulls,** 1,000 replicates of 6 × 4,594 draws each:

| Null | 2-seat ESS (median) | SD of the half gap | P(\|gap\| ≥ 6.87) | Split R-hat median | P(R-hat ≤ 1.01) | P(R-hat ≤ 1.0136) |
| --- | --- | --- | --- | --- | --- | --- |
| geometric, τ 88 | 315 | 5.50 | 0.21 | 1.0190 | 0.117* | 0.26 |
| geometric, τ 103 | 272 | 5.85 | 0.24 | 1.0221 | 0.054 | 0.145 |
| geometric, τ 166 | 166 | 7.70 | 0.36 | 1.0365 | 0.011 | 0.028 |
| block bootstrap, B 500 | 362 | 5.49 | 0.21 | 1.0165 | 0.145 | 0.34 |
| block bootstrap, B 1,000 | 323 | 5.26 | 0.19 | 1.0161 | 0.179 | 0.36 |

\* This is one run's value. Pooled over 17,600 further replicates the figure is 0.082 (see Reproduction). No conclusion uses it.

- **What the bootstrap means here:** it cuts all dependence longer than B, so it mixes faster than the real chains (ESS 323–362 against 268). That makes it anti-conservative for the gap, and the gap is still inside noise under it.
- **The other rectangles,** each against its own MCSE: 45.35% (z −1.28), 48.05% (−0.43), 50.45% (+0.26) and 50.25% (+0.10). They are nested samples of the same chains.
- **(a) The start effect is beyond noise.**
  - Chains 0 and 6, the two that start at 1 seat, put 33.7% and 33.1% of their first halves at 2 seats.
  - For chains started at 1 seat, P(both ≤ 33.7%) is 0.0067 under the geometric null at τ = 103, and 0.020 at τ = 166.
  - Under block bootstraps whose first block starts at an observed 1-seat draw, it is 0.0018 at B = 500 and 0.0025 at B = 1,000.
  - These two half-chains are the lowest 2 of the 12 (probability 1/66 under exchangeability; the test is post hoc).
- **(b) The disagreement between the two long chains is beyond noise.**
  - Over 12,000 draws, chains 0 and 6 sit at 33.2% and 51.6% at 2 seats.
  - Welch's t on batch means is −3.08, −2.54, −2.88 and −3.15 at b = 500, 1,000, 2,000 and 3,000 (p = 0.0035–0.024).
  - Chain 0's blocks of 3,000 draws are four of the five lowest of the 16 such blocks.

**Assessment:**
- README.md:39–42 offers two contrasts as evidence of drift. Both are inside Monte Carlo noise under every null I ran, parametric or not.
- As written, the sentence is a verdict about the sampler that its own numbers do not carry.
- The README's preceding sentence holds under both nulls:
  - At matched ESS, a stationary sampler reads 1.01 or below in about 5% of replicates.
  - Even under the faster-mixing bootstrap, it does so in only 15–18%.
- The caution itself can stand on (a) and (b). The fix swaps the evidence, not the direction.

**Correction to the evidence:** "As written, the two sentences cannot both hold" overstates the logic.
- The pooled half contrast is one of the 11 degrees of freedom that split R-hat pools. A targeted contrast could therefore detect a drift that R-hat misses.
- Here it does not: χ²₁ = 1.27, and the observed R-hat sits below the stationary median under both nulls (the 14.5th percentile at τ = 103, the 34th–36th under the bootstrap).
- In substance, the auditor is right.

### 4. [minor] How the Monte Carlo error is presented — **PARTLY UPHELD**

- **(a) Partly upheld.**
  - The whiskers and labels (`tools/plot_seat_distribution.py`:550–552 and 640–643) use the ESS-based 3.00 / 3.05 pts. So does the alt text's "give or take about 6 points (2 Monte Carlo standard errors)" (README.md:16).
  - That is the bottom of the prose's own "3 to 4 points" (README.md:20–21), as alleged. On that range, two standard errors are 6–8 points; block means put them at 6.7–7.8.
  - But 3.05 is not the lowest estimate on record. The spread of the six chain means gives 2.58, and batch means inside the rectangle give 2.65–2.87 at b = 500–3,000.
  - The figure's footer prints the 3.3–3.9 block-means range beside the whiskers. The inconsistency worth fixing is the alt text's "about 6" next to the prose's "3 to 4".
- **(b) Upheld, with its lower-bound claim made conditional.**
  - The b = 3,000 block-means estimate rests on 16 batches. Its own 95% range is 2.96–6.20 pts on the ddof-1 estimate (4.00 pts). On the ddof-0 estimate the plotter prints (3.88 pts), it is 2.86–6.00.
  - Restricted to the six rectangle chains at full length, block means give 3.16 / 3.33 / 3.62.
  - Allegation 3(b) makes it plausible that every one of these estimates understates the error, so "at least 3 to 4 points" is the defensible wording.
  - "Every one of these estimates is a lower bound" holds only if mixing is slower than the batch length. 3(b) suggests that but does not establish it.
- **(c) Upheld.**
  - The footer (`tools/plot_seat_distribution.py`:582–583, as rendered) reads "Seat count split R-hat 1.014, outside CRITERIA §8's 1.00–1.01 band". Nothing says the band cannot be resolved at about 286 effective draws.
  - The subtitle gives the 286 but does not link it to the band.
  - The first audit's refuter warned of exactly this: "Printed on its own, the 1.00–1.01 band would read as non-convergence that this ESS cannot diagnose".
  - The module docstring says the figure travels without the README (`tools/plot_seat_distribution.py`:8–9).
  - D-013 (`docs/DECISIONS.md`:309–311) reports a gate no method could pass as "unreachable", not "failed". That convention is written for detection gates, so here it is an analogy, not a rule.

### 5. [minor] The chain-death test — **PARTLY UPHELD**

**Reproduced:**
- Seven chains died after more than one draw: 1, 2, 3, 5, 8, 10 and 11. Five of them died at a 2-seat plan; chains 10 and 11 died at 1 seat.
- One-sided binomial p:
  - 0.203 against the all-rows exposure (48.55% of draws at 2 seats);
  - 0.219 against the rectangle's (49.53%);
  - 0.227 against one half;
  - 0.278 against the dying chains' own time at risk (52.96%).
- Two-sided p is 0.276–0.285 on the first two bases, and 0.453 at one half.
- A one-sided 5% test rejects only at 7 of 7 (α = 0.0064).
- Its power is 0.051, 0.120 and 0.260 at hazard ratios of 2, 3 and 5.
- The exact 95% interval on the hazard ratio is 0.43–27.8.
- Including chain 9 gives 5 of 8, p = 0.33. That chain has one row: it died at its first step from its 0-seat start.

**Upheld:**
- The p-value at docs/progress.md:2336 is one-sided, the text does not say so, and the direction was chosen after seeing the data.
- The test could not have told either way, and an interval would say so.
- The wording "died after their first draw", read literally, includes chain 9, which recorded its first draw and then died. Leaving out a chain that died at its seeded start is defensible, but the text should say "after more than one draw". Including it changes nothing.

**Not upheld:** "Without the interval, 'not significant' reads as reassurance." The sentence continues "but it is the direction a selection effect would push". It sits inside a paragraph whose point is that the chains the rectangle drops lean toward 2 seats.

### 6. [minor] The flag-rule calls — **PARTLY UPHELD**

**Reproduced** with the repository's own code (`bench.RULE` through `outlier.locate` and `confusion.flag`), on the rectangle's signed efficiency gap:
- The zero-seat draws take two values, 2.5 and 3.5 votes above the 0-seat level, held by 216 and 179 draws. The enacted plan's gap equals the 3.5-vote value.
- Their mid-ranks are 0.9896 and 0.9968. Treated as one tied value, all 395 sit at 0.9928.
- **Without plan ids:** the Kish ESS over values is 39.0, below the rule's `required_ess` of 50. The rule returns `flagged=None` (UNRESOLVED) for all three values.
- **With metric tuples standing in for plan ids:** the ESS is 269.8. The 2.5-vote value gets `False` and the 3.5-vote value `True`, which are exactly the paragraph's calls.

**Upheld:**
- docs/progress.md:2435–2439 cites the audit record but drops a condition the record stated: "Without plan ids (Kish ESS 39 < 50), the rule refuses to decide at all".
- A reader reproducing the calls from the committed draws, which carry no plan ids, gets UNRESOLVED.

**Not upheld:** "against this reference the rule refuses rather than flags."
- That holds only for a caller who passes no ids. The bench always passes them:
  - `src/detect/bench.py`:1607–1618 builds them (`reference_ids`);
  - `relocate` (:1621–1641) and :2324–2325 and :2342–2348 hand them to `locate`.
- Identical plans have identical metric rows, so grouping by plan splits the draws at least as finely as grouping by metric tuple. The true Kish ESS is therefore at least 269.8.
- Under the rule as the bench runs it, the paragraph's calls stand. The fix is one clause: "given plan ids, as the bench supplies them".
- The value-based ESS is low because distinct plans share values. The three largest value multiplicities (3,219, 2,504 and 785 draws) are all 1-seat values, and the Kish ESS over metric rows is about seven times that over values.

### 7. [minor] "Because zero-seat plans come early" — **UPHELD**, on stronger evidence

**Reproduced:**
- The six chains' first 500 draws hold 112 of the 395 zero-seat draws, against 43 if they were spread evenly:

| Chain | Zero-seat draws in its first 500 |
| --- | --- |
| 6 (draws 234–437) | 89 |
| 2 | 21 |
| 0 | 2 |
| 1, 5, 10 | 0 |

- In four of the six chains, the first 500 draws hold proportionally fewer zero-seat draws than the rest:

| Chain | 0 seats in its first 500 | 0 seats in the rest |
| --- | --- | --- |
| 0 | 0.40% | 1.61% |
| 1 | 0% | 1.71% |
| 5 | 0% | 1.17% |
| 10 | 0% | 0.49% |

- Without chain 6, dropping the first 500 draws moves the zero-seat share from 1.23% to 1.27%: up, not down.
- So the move from 1.43% to 1.15% at docs/progress.md:2326–2328 is chain 6's early visit, plus a little of chain 2's. It is not a property of zero-seat plans.

### The auditor's "checked and found sound" claims

**Reproduced as stated:**
- the counts, shares, ESS, MCSE and R-hat;
- the halves, the after-500 shares (1.15% and 50.24%), the rectangle shares, the chain fates and the Senate counts, including its 3-seat draws at chain 0, draws 232–239;
- 454 draws at or under 94 persons, and a median spread of 225;
- the cut-edge splits, 151 of 3,341 and 244 of 24,223;
- 216 sweeps at 2.5 votes and 179 at 3.5, and the enacted plan's offset of 3.500 votes;
- block means of 3.33 / 3.66 / 3.88 over all rows, and 3.16 / 3.33 / 3.62 for the six rectangle chains at full length;
- batch means inside the rectangle within 2.1–2.9;
- item 3:
  - standard errors of 10.77, 8.88 and 11.88 pts, and 10.65 with the finite-length correction;
  - z between 0.52 and 0.70;
  - a first-260-draw mean of 36.4%, with 7-of-8 subsets of 30.4–41.6%;
  - a start-state bias of −13.1 pts and an RMSE of 15.9;
  - an interval of 19.7–66.3%;
- item 5's R-hat null:
  - at τ = 103, median 1.0221 and P(≤ 1.01) = 0.054 in this run, and 1.0220–1.0226 and 0.045–0.056 over four runs;
  - at τ = 166, 1.0365 and 0.011;
- 44.7 effective draws per chain and 22.3 per split chain;
- the rule-of-three bound of 1.05%;
- the 1-versus-2-seat order not identified, with chains 0 and 6 favouring 1 seat and the other four 2;
- the two contests agreeing on 82.5% of draws;
- the figure hash, 30 tests passed, and the firewall clean.

**Not reproduced as stated:**
- **"Single-chain τ ranges from 31 to 437" (item 2).** No estimator I tried gives that range:
  - Unsplit Geyer per chain gives 49, 165, 31, 81, 57 and 148. That is a range of 31–165 and a mean of 88.5, which is allegation 3's "88".
  - The repository's split ESS, run on each chain's two halves, gives 62, 464, 37, 84, 58 and 145.
  - The point the claim supports holds under both: dependence varies widely by chain, and some chains exceed the pooled 103.
- **"Vehtari's '400' is the four-chain form of 100 per chain, which would be 600 for six chains."** This is half right, checked against arXiv:1903.08008v5.
  - §3.2 reads: "we only recommend relying on the R̂ estimate to make decisions about the quality of the chain if each of the split chains has an average ESS estimate of at least 50. In our minimum recommended setup of four parallel chains, the total ESS should be at least 400 before we expect R̂ to be useful". For that criterion, six chains need 600.
  - §2, "Recommendations for practice", gives an absolute figure: "we recommend requiring that the rank-normalized ESS is greater than 400, … as typically sufficient to get a stable estimate of the Monte Carlo standard error."
  - docs/progress.md:2284–2286's "a total above 400, and 50 per split chain" paraphrases both as written.
  - 268 meets neither threshold, so nothing changes.

**Smaller corrections inside the allegations:**
- **Allegation 1:**
  - The surviving ratio is about 1.5–2.2, not 1.8–2.2.
  - My shift test gives p = 0.0005 on 4,000 shifts against the auditor's 0.0003; that is the same resolution.
- **Allegation 3:** the z for the 4 × 8,133 rectangle is −1.28.
- **Allegation 4(b):** the range 3.0–6.2 is computed on a ddof-1 estimate.
- **Allegation 5:** the two-sided 0.28 depends on the exposure base.

### Reproduction

**Where things are:** scratch copies of the per-allegation scripts and their outputs are in `/tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/refute2-stat/`. Scripts `r0` to `r7` cover the allegations, and `r3b` to `r3g` check the τ = 88 tail. Every number in this report comes from the script below, from the plotter, or from the Vehtari text.

**Commands,** from the worktree root at `afab97e`:

```
PYTHONPATH=src python tools/plot_seat_distribution.py --out /tmp/fig.png && sha256sum /tmp/fig.png docs/figures/ia-neutral-seat-distribution.png
PYTHONPATH=src python -m pytest tests/test_seat_distribution.py -q --strict-markers
python tools/check_firewall.py
PYTHONPATH=src python repro_refute2.py        # about 5 minutes
pdftotext 1903.08008v5.pdf - | grep -n "greater than 400\|at least 50"   # Vehtari et al. §2 and §3.2
```

**The τ = 88 tail.** This script's random stream prints P(R-hat ≤ 1.01) = 0.117 on the τ = 88 line. Other runs give:
- 0.066–0.097 from fifteen fresh-seed runs of the same null;
- 0.086 from the same stream's next 1,600 replicates.

Pooled over 17,600 replicates the figure is 0.082. The first 1,000 replicates of that stream are an extreme segment, and no conclusion uses the figure.

```python
"""Refuter, second first-result audit (Statistician lens). Self-contained; reads committed files only.

Run from the worktree root:  PYTHONPATH=src python repro_refute2.py   (about 5 minutes)
Simulated tails carry Monte Carlo error. In this stream the tau-88 line prints P(R-hat <= 1.01) = 0.117;
fifteen fresh-seed runs of that null and the next 1,600 replicates of this stream (17,600 in all) give
0.066-0.097 run by run, 0.082 pooled. No verdict uses that number.
Own loader (pandas, round-trip float parsing); seats read off |EG| with both D-039 checks
asserted; ESS and split R-hat from generate.convergence; the rule of record from detect.bench.
"""
import itertools
import json
from collections import Counter

import numpy as np
import pandas as pd
from scipy import stats

from detect import bench, confusion as C, outlier as O
from generate import convergence as CV

E2 = "docs/experiment-2/"
# round_trip: pandas' default parser merges distinct decimals (3,718 distinct rows, not 4,020)
df = pd.read_csv(E2 + "ia-draws-v2.csv.gz", float_precision="round_trip")
side = {c["index"]: c for c in json.load(open(E2 + "ia-draws-v2-chains.json"))["chains"]}
rep = json.load(open("docs/phase-2/phase-2-report.json"))["IA"]
METRICS = list(df.columns[4:])
TOT = {"G20PRE": (759_061, 897_672), "G20USS": (754_859, 864_997)}
K, RC, N, CUT = 4, (0, 1, 2, 5, 6, 10), 4594, rep["compactness"]["cut_edges"]
for i, c in side.items():
    assert (df.chain_index == i).sum() == c["n_rows"]


def read_seats(contest):
    d, r = TOT[contest]
    T, V = d + r, d / (d + r)
    c, L = 2 * V - 0.5, np.abs(2 * V - 0.5 - np.arange(K + 1) / K)
    g = df[f"abs_efficiency_gap@{contest}"].to_numpy()
    s = np.abs(g[:, None] - L).argmin(1)
    res, sweep = g - L[s], (s == 0) | (s == K)
    assert np.all(np.abs(res[~sweep]) <= np.diff(np.sort(L)).min() / 4)          # margin
    grid = [K - j / 2 for j in range(K + 1) if j % 2 == T % 2]
    assert np.all(np.min(np.abs(res[sweep, None] * T - np.array(grid)), 1) < 1e-6)  # sweeps
    return s, np.where(c - s / K >= 0, g, -g), T, L


df["s"], df["eg"], T, L = read_seats("G20PRE")
df["s_uss"] = read_seats("G20USS")[0]
ch = {i: g.reset_index(drop=True) for i, g in df.groupby("chain_index")}
R = {i: ch[i].iloc[:N] for i in RC}
P = pd.concat(R.values(), ignore_index=True)
S = np.array([R[i].s.to_numpy() for i in RC])
t5 = stats.t.ppf(0.975, 5)
rng = np.random.default_rng(20261011)


def ind(X, s):
    return list((np.asarray(X) == s).astype(float))


def visits(hit):
    return int(hit[0]) + int((hit[1:] & ~hit[:-1]).sum())


print("== baseline ==")
p = {s: (S == s).mean() for s in range(3)}
ess = {s: CV.ess(ind(S, s)) for s in range(3)}
print("counts", [int((S == s).sum()) for s in range(5)], "all rows", [int((df.s == s).sum()) for s in range(5)],
      "| ESS", [round(ess[s], 1) for s in range(3)], "| MCSE pts",
      [round(float(100 * np.sqrt(p[s] * (1 - p[s]) / ess[s])), 2) for s in range(3)])
print("seat-count split R-hat %.4f ESS %.1f | distinct rows %d / %d | repeats %d | Senate %s"
      % (CV.split_rhat(S.astype(float)), CV.ess(list(S.astype(float))), len(P[METRICS].drop_duplicates()),
         len(df[METRICS].drop_duplicates()),
         sum(int((R[i][METRICS].to_numpy()[1:] == R[i][METRICS].to_numpy()[:-1]).all(1).sum()) for i in RC),
         [int((P.s_uss == s).sum()) for s in range(5)]))

print("\n== allegation 1: 0 seats at >= 51 cut edges vs below ==")
for burn in (0, 250, 500, 750, 1000, 1500, 2000):
    d, A, B = [], [], []
    for i in RC:
        g = R[i].iloc[burn:]
        z, hi = (g.s == 0).to_numpy(), (g.cut_edges >= CUT).to_numpy()
        d.append(z[hi].mean() - z[~hi].mean()); A.append(z[hi]); B.append(z[~hi])
    d, A, B = np.array(d), np.concatenate(A), np.concatenate(B)
    m, se = d.mean(), d.std(ddof=1) / np.sqrt(6)
    print(f"burn {burn:4d}: {(d > 0).sum()}/6 chains; {100*A.mean():.2f}% vs {100*B.mean():.2f}% "
          f"(ratio {A.mean()/B.mean():.2f}); t(5) {100*(m-t5*se):+.2f} to {100*(m+t5*se):+.2f}")
e6 = np.where((R[6].s == 0).to_numpy() & (R[6].cut_edges >= CUT).to_numpy())[0]
ex = R[6].iloc[e6[e6 < 500]]
print(f"chain 6, first 500: {len(ex)} of {int(((P.s == 0) & (P.cut_edges >= CUT)).sum())} at draws "
      f"{ex.draw.min()}-{ex.draw.max()}, {len(ex[METRICS].drop_duplicates())} distinct rows, "
      f"{int((ex.cut_edges == CUT).sum())} at exactly {CUT}")
for cut in (45, 47, CUT):
    pos = [sum(R[i].iloc[b:].pipe(lambda g: (g.s[g.cut_edges >= cut] == 0).mean() > (g.s[g.cut_edges < cut] == 0).mean())
               for i in RC) for b in (0, 500, 750, 1000, 2000)]
    print(f"split >= {cut}: chains higher at burn 0/500/750/1000/2000: {[int(x) for x in pos]}")
z = P.s == 0
print(f"> {CUT}: {100*z[P.cut_edges > CUT].mean():.2f}% vs {100*z[P.cut_edges <= CUT].mean():.2f}%; >= 45: "
      f"{100*z[P.cut_edges >= 45].mean():.2f}% vs {100*z[P.cut_edges < 45].mean():.2f}%; 40-42: "
      f"{int(P.cut_edges.between(40, 42).sum())} draws, {int(z[P.cut_edges.between(40, 42)].sum())} at 0")
for burn in (0, 500):
    va = sum(visits(((R[i].s == 0) & (R[i].cut_edges >= CUT)).to_numpy()[burn:]) for i in RC)
    vb = sum(visits(((R[i].s == 0) & (R[i].cut_edges < CUT)).to_numpy()[burn:]) for i in RC)
    h6 = ((R[6].s == 0) & (R[6].cut_edges >= CUT)).to_numpy()[burn:]
    print(f"burn {burn}: zero-seat visits at >= {CUT} {va}, below {vb}; chain 6 at >= {CUT}: {int(h6.sum())} draws, {visits(h6)} visits")
for burn in (0, 500):
    num = den = 0.0
    for i in RC:
        g = R[i].iloc[burn:]
        zz, hi = (g.s == 0).to_numpy(), (g.cut_edges >= CUT).to_numpy()
        num += zz[hi].sum() * (~hi).sum() / len(g); den += zz[~hi].sum() * hi.sum() / len(g)
    Z = [(R[i].s.to_numpy()[burn:] == 0) for i in RC]
    Cc = [R[i].cut_edges.to_numpy()[burn:] for i in RC]
    f = lambda cs: (lambda hi, zz: zz[hi].mean() - zz[~hi].mean())(np.concatenate([c >= CUT for c in cs]), np.concatenate(Z))
    obs = f(Cc)
    null = np.array([f([np.roll(c, rng.integers(300, len(c) - 300)) for c in Cc]) for _ in range(4000)])
    print(f"burn {burn}: MH ratio {num/den:.2f}; circular-shift p {(1 + (null >= obs).sum())/4001:.4f}")

print("\n== allegation 2: population-tight draws ==")
tight = P.population_spread <= 94
print("tight-region visits", sum(visits((R[i].population_spread <= 94).to_numpy()) for i in RC))
for lab, mk in (("tight", tight), ("rest", ~tight)):
    print(f"{lab}: n {mk.sum()}, mean cut {P.cut_edges[mk].mean():.2f}, >= 51 {100*(P.cut_edges[mk] >= CUT).mean():.1f}%, "
          f"0 seats {100*(P.s[mk] == 0).mean():.2f}%, enacted mid-rank "
          f"{((P.cut_edges[mk] < CUT).sum() + 0.5*(P.cut_edges[mk] == CUT).sum())/mk.sum():.3f}")
print(f"Spearman(spread, cut) {stats.spearmanr(P.population_spread, P.cut_edges).statistic:.3f}; mean cut by band",
      P.groupby(pd.cut(P.population_spread, [0, 94, 150, 225, 400]), observed=True).cut_edges.mean().round(1).tolist(),
      f"; 0-seat draws mean cut {P.cut_edges[z].mean():.2f} vs {P.cut_edges[~z].mean():.2f}")
for lo, hi in ((0, 150), (151, 300)):
    for lab, cond in ((">=51", P.cut_edges >= CUT), ("<51", P.cut_edges < CUT)):
        mk = P.population_spread.between(lo, hi) & cond
        hits = [visits(((R[i].s == 0) & R[i].population_spread.between(lo, hi) &
                        ((R[i].cut_edges >= CUT) if lab == ">=51" else (R[i].cut_edges < CUT))).to_numpy()) for i in RC]
        print(f"  spread {lo}-{hi}, {lab}: {int(z[mk].sum())} zero-seat draws of {mk.sum()}, {sum(hits)} visits")

print("\n== allegation 3: drift ==")
h = N // 2
gap = (S[:, h:] == 2).mean() - (S[:, :h] == 2).mean()
rh_obs = CV.split_rhat(S.astype(float))
se_h = [np.sqrt(x.mean() * (1 - x.mean()) / CV.ess(list(x.astype(float)))) for x in (S[:, :h] == 2, S[:, h:] == 2)]
Hm = np.array([[(S[i, :h] == 2).mean(), (S[i, h:] == 2).mean()] for i in range(6)])
v_half = p[2] * (1 - p[2]) * (6 * N / ess[2]) / h
print(f"gap {100*gap:.2f} pts; per-half SE {np.round(100*np.array(se_h), 2)}, z {gap/np.hypot(*se_h):.2f}; "
      f"1-df contrast chi2 {6*((Hm.mean(0)-Hm.mean())**2).sum()/v_half:.2f}; half-chains {np.round(100*Hm, 1).tolist()}")


def chunked(make, reps, size=200):
    return np.concatenate([make(min(size, reps - k)) for k in range(0, reps, size)])


def geometric(tau, reps, chains=6, start=None):
    """Stationary geometric-redraw chain: redraw from the rectangle marginal w.p. 2/(tau+1)."""
    r = 2 / (tau + 1)

    def make(m):
        redraw = rng.random((m, chains, N)) < r
        new = rng.choice(3, size=(m, chains, N), p=[p[0], p[1], p[2]]).astype(np.int8)
        redraw[..., 0] = True
        if start is not None:
            new[..., 0] = start
        idx = np.maximum.accumulate(np.where(redraw, np.arange(N, dtype=np.int32), 0), axis=2)
        return np.take_along_axis(new, idx, axis=2)
    return chunked(make, reps)


def block_boot(B, reps, chains=6, first=None):
    """Circular block bootstrap of the observed rectangle: blocks of B draws, random chain and offset."""
    nb = -(-N // B)

    def make(m):
        src, off = rng.integers(0, 6, (m, chains, nb)), rng.integers(0, N, (m, chains, nb))
        if first is not None:
            k = rng.integers(0, len(first[0]), (m, chains))
            src[..., 0], off[..., 0] = first[0][k], first[1][k]
        pos = (off[..., None] + np.arange(B)) % N
        return S[src[..., None], pos].astype(np.int8).reshape(m, chains, nb * B)[..., :N]
    return chunked(make, reps)


def null(X, label):
    g = (X[:, :, h:] == 2).mean((1, 2)) - (X[:, :, :h] == 2).mean((1, 2))
    rh = np.array([CV.split_rhat(x.astype(float)) for x in X])
    es = np.array([CV.ess(ind(x, 2)) for x in X])
    print(f"{label}: ESS {np.median(es):.0f}; gap SD {100*g.std():.2f}, P(|gap|>=obs) {(np.abs(g) >= abs(gap)).mean():.3f}; "
          f"R-hat median {np.median(rh):.4f}, P(<=1.01) {(rh <= 1.01).mean():.3f}, P(<=obs) {(rh <= rh_obs).mean():.3f}")


for tau in (88, 103, 166):
    null(geometric(tau, 1000), f"geometric tau {tau}")
for B in (500, 1000):
    null(block_boot(B, 1000), f"block bootstrap B={B}")
thr = (S[[0, 4], :h] == 2).mean(1).max()
for tau in (103, 166):
    f = (geometric(tau, 4000, chains=2, start=1)[:, :, :h] == 2).mean(2)
    print(f"(a) geometric tau {tau}, start 1: P(both <= {100*thr:.1f}%) {(f <= thr).all(1).mean():.4f}")
ones = np.where(S == 1)
for B in (500, 1000):
    f = (block_boot(B, 4000, chains=2, first=ones)[:, :, :h] == 2).mean(2)
    print(f"(a) block bootstrap B={B}, first block at a 1-seat draw: P(both) {(f <= thr).all(1).mean():.4f}")
c0, c6 = (ch[0].s.to_numpy() == 2), (ch[6].s.to_numpy() == 2)
for b in (500, 1000, 2000, 3000):
    t = stats.ttest_ind(c0.reshape(-1, b).mean(1), c6.reshape(-1, b).mean(1), equal_var=False)
    print(f"(b) b={b}: Welch t {t.statistic:.2f}, p {t.pvalue:.4f}")
blocks = sorted((100 * (g.s.to_numpy()[j*3000:(j+1)*3000] == 2).mean(), i) for i, g in ch.items() for j in range(len(g) // 3000))
print(f"(b) {len(blocks)} blocks of 3,000, lowest five (share, chain)", [(round(float(v), 1), int(i)) for v, i in blocks[:5]])
for r in json.load(open(E2 + "ia-convergence-rectangles.json"))["rectangles"]:
    n = r["prefix_length"]
    kept = [ch[i].s.to_numpy()[:n] for i in ch if len(ch[i]) >= n]
    s2 = np.mean(np.concatenate(kept) == 2)
    print(f"rectangle {len(kept)}x{n}: {100*s2:.2f}%, z {(s2 - p[2])/np.sqrt(s2*(1-s2)/CV.ess(ind(kept, 2))):+.2f}")

print("\n== allegation 4: Monte Carlo error ==")
def bm(series, b, ddof=0):
    x = np.concatenate(series)
    m = np.array([s[j*b:(j+1)*b].mean() for s in series for j in range(len(s) // b)])
    return b * ((m - x.mean())**2).sum() / (len(m) - ddof) / x.var(), len(m)
rows = [(g.s.to_numpy() == 2).astype(float) for g in ch.values() if len(g)]
six = [(ch[i].s.to_numpy() == 2).astype(float) for i in RC]
for lab, ser in (("all rows", rows), ("six chains full", six), ("rectangle", ind(S, 2))):
    print(lab, "b=500/1000/3000:", [round(float(100*np.sqrt(p[2]*(1-p[2])*bm(ser, b)[0]/(6*N))), 2) for b in (500, 1000, 3000)])
tau1, nb = bm(rows, 3000, ddof=1)
se1 = np.sqrt(p[2]*(1-p[2])*tau1/(6*N))
print(f"b=3000: {nb} batches, ddof-1 SE {100*se1:.2f}, 95% {100*se1*np.sqrt((nb-1)/stats.chi2.ppf(.975, nb-1)):.2f}-"
      f"{100*se1*np.sqrt((nb-1)/stats.chi2.ppf(.025, nb-1)):.2f}; chain-spread SE {100*S.__eq__(2).mean(1).std(ddof=1)/np.sqrt(6):.2f}")
se0 = np.sqrt(p[2]*(1-p[2])*bm(rows, 3000)[0]/(6*N))
print(f"b=3000 ddof-0 SE {100*se0:.2f} (the plotter's), 95% {100*se0*np.sqrt((nb-1)/stats.chi2.ppf(.975, nb-1)):.2f}-"
      f"{100*se0*np.sqrt((nb-1)/stats.chi2.ppf(.025, nb-1)):.2f}")
def geyer(x):
    n = len(x); xc = x - x.mean(); f = np.fft.rfft(xc, 2*n); a = np.fft.irfft(f*np.conj(f))[:n]; rho = a / a[0]
    pr = [rho[t] + rho[t+1] for t in range(0, n - 1, 2)]
    cut = next((k for k in range(1, len(pr)) if pr[k] <= 0), len(pr))
    return -1 + 2 * np.minimum.accumulate(pr[:cut]).sum()
print("single-chain tau, unsplit Geyer", [int(round(geyer((S[i] == 2).astype(float)))) for i in range(6)],
      "split CV.ess", [round(h * 2 / CV.ess([(S[i, :h] == 2).astype(float), (S[i, -h:] == 2).astype(float)])) for i in range(6)])

print("\n== allegation 5: deaths ==")
died = [i for i, c in side.items() if not c["completed"] and c["n_rows"] > 1]
k = sum(int(ch[i].s.iloc[-1] == 2) for i in died)
for lab, q in (("all rows", (df.s == 2).mean()), ("rectangle", p[2]), ("half", 0.5),
               ("dying chains' rows", np.mean(np.concatenate([ch[i].s for i in died]) == 2))):
    print(f"{k}/{len(died)} vs {lab} {100*q:.2f}%: one-sided {stats.binomtest(k, len(died), q, alternative='greater').pvalue:.3f}, "
          f"two-sided {stats.binomtest(k, len(died), q).pvalue:.3f}; with chain 9 (5/8) "
          f"{stats.binomtest(k, len(died) + 1, q, alternative='greater').pvalue:.3f}")
q0 = (df.s == 2).mean()
print("power at HR 2/3/5:", [round(float((hr*q0/(hr*q0 + 1 - q0))**7), 3) for hr in (2, 3, 5)], "alpha", round(float(q0**7), 4),
      "HR interval", [round(float((x/(1-x))/(q0/(1-q0))), 2) for x in stats.binomtest(k, 7).proportion_ci(0.95, "exact")])

print("\n== allegation 6: the rule of record ==")
eg = P.eg.to_numpy()
ids = [tuple(r) for r in P[METRICS].itertuples(index=False)]
print(f"all zero-seat draws as one tied value: mid-rank {((eg < eg[P.s == 0].min()).sum() + 0.5*(P.s == 0).sum())/len(eg):.4f}")
kish = lambda items: len(items)**2 / (np.array(list(Counter(items).values()), float)**2).sum()
print(f"Kish ESS: values {kish(list(eg)):.1f}, metric tuples {kish(ids):.1f}; largest value multiplicities "
      f"{[(n, int(np.bincount(P.s[eg == v]).argmax())) for v, n in Counter(eg).most_common(3)]}")
for v in sorted(set(eg[P.s == 0])) + [rep["partisan"]["efficiency_gap"]]:
    for lab, pid in (("no ids", None), ("tuple ids", ids)):
        locs = O.locate(None, {"efficiency_gap": list(eg)}, {"efficiency_gap": float(v)},
                        metrics=["efficiency_gap"], ensemble_plan_ids=pid)
        d = C.flag(locs, bench.RULE)
        print(f"  {(v - L[0])*T:.1f} votes [{lab}]: mid-rank {locs['efficiency_gap'].percentile:.4f}, "
              f"ESS {locs['efficiency_gap'].ess:.1f}, flagged={d.flagged}")

print("\n== allegation 7 and item 3 ==")
print("zero-seat draws in first 500 by chain", {i: int((R[i].s.iloc[:500] == 0).sum()) for i in RC},
      "| first-500 vs rest %", {i: (round(float(100*(R[i].s.iloc[:500] == 0).mean()), 2), round(float(100*(R[i].s.iloc[500:] == 0).mean()), 2)) for i in RC})
no6 = [R[i].s.to_numpy() for i in RC if i != 6]
print(f"without chain 6: {100*np.mean(np.concatenate(no6) == 0):.2f}% -> {100*np.mean(np.concatenate([x[500:] for x in no6]) == 0):.2f}% after 500")
allc = [g.s.to_numpy() for g in ch.values() if len(g)]
w = [(x[j*260:(j+1)*260] == 2).mean() for x in allc for j in range(len(x) // 260)]
st = [(x[:260] == 2).mean() for x in allc if len(x) >= 260]
sub = [np.mean(c) for c in itertools.combinations(st, 7)]
print(f"7x260 SE: windows {100*np.std(w, ddof=1)/np.sqrt(7):.2f}, starts {100*np.std(st, ddof=1)/np.sqrt(7):.2f}, "
      f"asymptotic {100*np.sqrt(p[2]*(1-p[2])*(6*N/ess[2])/1820):.2f}; starts mean {100*np.mean(st):.1f}%, 7-of-8 "
      f"{100*min(sub):.1f}-{100*max(sub):.1f}%")
tau2 = 6 * N / ess[2]; rho = (tau2 - 1) / (tau2 + 1)
fin = np.sqrt(p[2]*(1-p[2])*((1+rho)/(1-rho) - 2*rho*(1-rho**260)/(260*(1-rho)**2))/1820)
old = [np.std(w, ddof=1)/np.sqrt(7), np.std(st, ddof=1)/np.sqrt(7), np.sqrt(p[2]*(1-p[2])*tau2/1820)]
zs = [(p[2] - 782/1820)/np.hypot(new, o) for new in (np.sqrt(p[2]*(1-p[2])/ess[2]), 0.039) for o in old]
print(f"finite-length SE {100*fin:.2f}; z vs 43%: {min(zs):.2f}-{max(zs):.2f}; start bias {100*(np.mean(st)-p[2]):.1f} pts, "
      f"RMSE {100*np.hypot(np.mean(st)-p[2], old[1]):.1f}; 43% +/- 1.96 x {100*old[2]:.2f} = {43-196*old[2]:.1f}-{43+196*old[2]:.1f}%")
```

---

## Author's response to the second audit

The refuter refuted no allegation outright, so each is answered by a change, in
the commit that follows `afab97e`. Numbers the answers quote are printed by
`tools/plot_seat_distribution.py` and pinned by `tests/test_seat_distribution.py`,
except where they come from the reports above.

| # | Allegation | Refuter | What changed |
| --- | --- | --- | --- |
| 1 | The compactness contrast is quoted as robust, but rests on one excursion and on the 500-draw warm-up, with no interval | Partly upheld; minor | `docs/progress.md` gives the excursion (89 of the 151 zero-seat draws at 51 or more cut edges are chain 6's), how "every chain" depends on the warm-up, the chain-level intervals (−0.7 to +5.7 points on the full rectangle, +0.3 to +2.3 after 500), the surviving ratio of about 1.5 to 2.2, and the direction's sturdier support (no zero-seat draw at 40–42 cut edges; the chain-stratified ratio equals the crude one). The README and the figure's note no longer quote the magnitudes or "in every chain"; they state the direction only. |
| 2 | Compactness is presented as a second like-for-like failure, though conditioning on it would absorb a partisan effect | Partly upheld; material for D-041 | D-041 records the argument: population equality is the first of Iowa's ordered criteria and the draws fall short of the enacted plan on it; compactness is the fourth, the draws exceed the enacted plan on it, and conditioning on it would raise the reference's zero-seat share however the plan was drawn. The README and `docs/progress.md` call compactness context, not a second adjustment. The part not upheld, that the gap is "largely downstream" of population, is written as "part of the gap may follow from the population gap, by an amount these draws cannot measure". The plotter prints the population-tight draws' cut edges against the rest's. |
| 3 | "What the chains do show is drift" rests on numbers within noise | Upheld | The README's evidence for slow mixing is now chain by chain: the two chains that started at 1 seat put a third of their first halves at 2, and the two chains that completed disagree, 33.2% against 51.6%, each with its probability from these reports. The half split and the rectangles are described as within Monte Carlo noise. |
| 4 | How the Monte Carlo error is presented | Partly upheld | (a) The alt text says the ±6-point whiskers are one estimate and others run higher. (b) The README says "3 to 4 points or more", and that 3 to 4 "may understate" the error. (c) The footer now adds, computed from the effective sample, that 24 effective draws per split chain is below the 50 Vehtari et al. (2021) ask for before relying on R-hat. |
| 5 | The chain-death test cannot tell, and the text does not say so | Partly upheld | `docs/progress.md` gives the p-value as one-sided for a direction chosen after looking, adds the exact 95% interval on the hazard ratio (0.43 to 28), and says "after more than one draw". |
| 6 | The flag-rule calls hold only when the rule is given plan ids | Partly upheld | `docs/progress.md` says the calls hold "given plan identities, as the bench supplies them", and that a reader of the committed draws, which carry none, gets no decision. |
| 7 | "Because zero-seat plans come early" generalizes one chain | Upheld | `docs/progress.md` says the shift is chain 6's early excursion (89 of the 112 zero-seat draws in the six chains' first 500), and that without chain 6 the share rises from 1.23% to 1.27%. The plotter prints each chain's draws by seats in its first 500, and the test pins the zero-seat counts. |
| — | The auditor's "single-chain τ ranges from 31 to 437" | Not reproduced | No text uses it. |
| — | The auditor's reading of Vehtari et al.'s 400 | Half right | The `Research Synthesist`, checking the sentence against the paper separately, found its purpose clause overstated. `docs/progress.md` now says the two thresholds are what the paper recommends for reliable R-hat and ESS estimates. |

The `Research Synthesist` also found that `src/generate/convergence.py`'s rank
normalization divides by `S − 1/4` where the paper's Eq. 14 has `S + 1/4`.
Patched in memory, the correction moves none of the diagnostics this section
quotes at the precision quoted. `docs/progress.md` records it as an open defect,
for its own change under `src/generate/`'s review.

---

# Third audit — the compactness sentence, at the final check

The final routing check, at commit `4d7a5ab`, sent the figure's wording to the
`Statistician`. Its report found that the note's compactness sentence held on one
compactness measure only, and argued one side of a question D-041 leaves to the
owner. A changed claim headed for the README goes through the audit first (D-007),
sized to a corrected claim: the Statistician's report serves as the auditor, and
each of its two material allegations went to its own fresh refuter.

- **Audited state:** commit `4d7a5ab`. Line numbers in the reports refer to it.
- **Auditor:** the `Statistician` agent, a fresh instance reviewing the figure's
  wording.
- **Refuters:** a `Computational Redistricting Scientist` agent for allegation 1
  and a `Statistician` agent for allegation 2, each a fresh instance told to
  default to "refuted" and to reproduce every number before agreeing.

All three reports are verbatim. The last section is the author's response, and is
not part of any report. The same commit also went to the `Scientific
Visualization Reviewer`, the `Code Reviewer` and the `Research Synthesist`; their
findings are answered in the same revision and are not reproduced here.

---

## Third auditor — Statistician

## Statistician review of 4d7a5ab (`tools/plot_seat_distribution.py`, `README.md`), against 7bf57db

**Short answer.**
- **Claim 1, the footer's R-hat clause:** it follows from the evidence for these draws. Its one defect is latent: whether the clause prints depends only on the effective sample size, never on the R-hat value.
- **Claim 2, the note's compactness sentence:** the numbers reproduce on cut edges, and the problems are what the sentence takes them to mean.
  - It reports one compactness measure's ranking as compactness in general. On Polsby-Popper, the other measure the draws carry, the plan sits mid-ensemble.
  - Its last clause is not a valid reason for "context, not an adjustment". The clause is true of any reference set, it gives only one side of a question D-041 leaves to the owner, and its premise shows only in the draws least like the plan on population.

**What I checked.** No worktree file was edited and `git status` is clean.
- **Re-render:** a fresh render is byte-identical to the committed PNG (sha256 `9da55255…`), and its printed summary matches `work2/seat-summary-final.txt` line for line.
- **Tests and firewall:** `tests/test_seat_distribution.py` gives 31 passed; `tools/check_firewall.py` prints clean.
- **Reproduction:** every number below comes from my own csv/gzip loader over `docs/experiment-2/ia-draws-v2.csv.gz` (chains 0, 1, 2, 5, 6, 10 × 4,594) and `docs/phase-2/phase-2-report.json`. Scripts and outputs are in `/tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/review-stat5/`: `repro.py`/`.out`, `strata.py`/`.out`, `rhat_null.py`/`.out`, `spearman.out`.

## Findings, most important first

### 1. [material] "Less compact than 88% of the draws" holds on cut edges only, and the note does not name the measure
**Location:** `tools/plot_seat_distribution.py:559-560` (text), `:459` (`more_compact_share` counts cut edges only), `:437-439`.

- **Cut edges reproduce exactly.** 24,223 of 27,564 draws (87.88%) have fewer than the plan's 51; 999 tie and 2,342 have more.
- **Polsby-Popper is a fair comparison.** The draws carry `polsby_popper_mean`. It is computed by the same `evaluate.compactness.measure_districts`, on the same `ia_units.gpkg`, as the plan's 0.33338 in the Phase 2 report. PlanScore independently gives 0.33325 (`docs/progress.md`, "Compactness, where the comparison is clean").
- **On Polsby-Popper the plan is mid-ensemble.**
  - 48.7% of draws are more compact than the plan and 51.3% less; the draws' median is 0.3325.
  - Counting each distinct plan once does not rescue the 88%. Of 4,020 distinct metric rows, 68.5% have fewer cut edges, but only 19.4% have a higher Polsby-Popper.
- **CRITERIA §3 requires surfacing this.** The two measures' rank correlation over the draws is −0.76 (−0.70 over distinct rows), below the ~0.9 bar in `docs/CRITERIA.md:169-170`, so "the choice is doing real work and must be surfaced". `docs/CRITERIA.md:165` adds: "Report all of them, always, and highlight disagreements rather than resolving them." The note resolves the disagreement silently, on a figure that travels without the README.
- **The "commoner" direction survives on Polsby-Popper, but weaker.**
  - 1.99% (281/14,139) against 0.85% (114/13,425).
  - 1.42% against 0.87% once each chain's first 500 draws are dropped.
  - Chain 2 reverses: 1.18% against 2.20%.
- **The same premise sits outside the diff.**
  - `README.md:56-58`.
  - D-041's "the draws already exceed the enacted plan's level of it" (`docs/DECISIONS.md:1230-1231`, `docs/progress.md:2460-2462`). That holds on cut edges, not on Polsby-Popper, and it is D-041's reason for treating compactness differently from population. The owner should see this before deciding D-041.
  - `docs/progress.md:2442-2445` does name cut edges.
- **Preferring cut edges is a VALUE choice.** A case for it, for instance closeness to Iowa's statutory standard, is one §3 says to surface; any reading of the statute belongs to the Election Law Analyst. The figure cannot make that choice silently.

### 2. [material] The last clause does not support "context, not an adjustment", and it argues one side of D-041's open question
**Location:** `tools/plot_seat_distribution.py:561-566`, framed by `:557-560`.

The mechanical part is right. Keeping only the 3,341 draws with 51 or more cut edges raises the 0-seat share from 1.43% to 4.52%. It is 1.15% to 2.16% after the warm-up, and 2.18% at a strict >51.

**(a) "Whether or not it was drawn for that outcome" holds for every choice of reference, so it cannot be the reason.**
- The reference never sees how the plan was drawn.
- Restricting to the population-tight draws, which the note's like-for-like caveat points to, lowers the 0-seat share to 0.44% (2 of 454 draws, one plan), equally "whether or not".
- Not restricting keeps it at 1.43%, also "whether or not".
- So the clause does not separate compactness from population.

**(b) The argument the clause stands in for is over-adjustment, and it is only one side.** That argument, from audit 2 and D-041, is that conditioning on a consequence of how the plan was drawn absorbs the very effect being tested for.
- It holds only if the plan's lower compactness came from how it was drawn.
- If it came from constraints the draws don't share, conditioning corrects the comparison, and the unconditioned 1.4% overstates how rare 0 seats is. D-041 names the population gap as a possible part of this, "by an amount these draws cannot measure" (`docs/DECISIONS.md:1235-1237`).
- The note states only the first case, as a consequence.
- D-041 is marked VALUE and "leave[s] any conditioning to the owner" (`docs/DECISIONS.md:1223-1225`); the figure presents the question as settled.

**(c) The association the clause relies on lives in the draws least like the plan on Iowa's first criterion, population equality.**

| Population spread | 0 seats at ≥51 cut edges | 0 seats below 51 |
|---|---|---|
| ≤94 persons | 0 of 98 | 2 of 356 |
| ≤150 persons | 1 of 521 (1 visit) | 24 of 4,116 (7 visits) |
| 151–300 persons | 148 of 2,744 | 220 of 19,747 |

- The one zero-seat plan among the population-tight draws has 45 cut edges and Polsby-Popper 0.350: more compact than the enacted plan on both measures.
- In the ≤150 band the shares point the other way, on too few visits to tell.
- 148 of the 151 zero-seat draws at 51 or more cut edges lie in the 151–300 band. 89 of them are chain 6's warm-up excursion, at spreads of 232–271.
- The Mantel–Haenszel ratio across spread bands roughly equals the crude one (4.44 against 4.49; 2.03 against 2.11 after the warm-up), so population spread does not confound the pooled association.
- But in the comparison the note itself treats as like-for-like, it cannot be told whether conditioning on compactness would raise the 0-seat share.

**What the evidence supports:** the facts, with the measure named and Polsby-Popper beside it. Then either no inference, or both cases plus "these draws cannot tell which", with the choice marked as the owner's (D-041).

### 3. [minor for my lens] "Drawn for that outcome" puts a question about the real plan's purpose on the headline figure
**Location:** `tools/plot_seat_distribution.py:566`. Route to the Science Communicator and the Election Law Analyst.

- By 2(a), the clause carries no evidence.
- A neutral ensemble cannot speak for a partisan process (`docs/first-result/INSTRUMENT-AUDIT.md:814`).
- Its only effect on a reader is to raise the question of purpose. Next to the cut-edge-only "88%", the note reads as pointing at the plan's shape.
- `CLAUDE.md` sends anything that could read as evidence about a real map to the owner.

### 4. [minor, latent] "Settles convergence neither way" prints whenever the ESS is low, whatever the R-hat
**Location:** `tools/plot_seat_distribution.py:608-612`; not tested at `tests/test_seat_distribution.py:329-342`.

- **Correct for 1.014.** I simulated stationary chains at the observed autocorrelation: 600 replicates of 6 × 4,594 geometric-redraw chains.
  - At τ = 96 (median ESS 291): split R-hat median 1.021, P(≤ 1.01) = 0.068, and the observed 1.0136 sits at the 18th percentile.
  - At τ = 103: median 1.022, P(≤ 1.01) = 0.052, observed at the 17th percentile.
- **The same simulation shows where the clause would turn false.** Its 99th percentile is 1.050 and its 99.9th 1.061. At 24 effective draws per split chain, a reading of 1.08 would be evidence of non-convergence, and the code would still print "settles convergence neither way".
- **The test's own rule is half met.** The test says each word is "read off the number it describes" (`:330-331`). "Outside" is read off the R-hat; this clause is read off the ESS only, and the test exercises it only at R-hat 1.0136 and 1.004.
- **Unreachable on the committed draws**, but the plotter is written to follow whatever values it is given.

## Claim 1 otherwise holds
- **Reproduced:**
  - seat-count split R-hat 1.01357, with the bulk value the larger;
  - bulk ESS 286.14 over 12 split chains, which is 23.85, printed as "24";
  - tail ESS (5% quantile indicator) 268, or 22.3 per split chain, also below 50.
- **The rank-normalization defect doesn't matter here.** Patching `convergence.py`'s S − 1/4 to the paper's S + 1/4 in memory leaves both values unchanged to five decimals.
- **The citation matches.** "The 50 Vehtari et al. (2021) ask for before relying on R-hat" matches the paper's sentence as quoted at `INSTRUMENT-AUDIT.md:979`.
- **"May understate" is calibrated.**
  - The footer's own block-means standard errors (3.3–3.9 points) exceed the whiskers' 3.05.
  - The record has chain-level evidence beyond the rectangle: the two completed chains sit at 33.2% against 51.6%.
  - 286 is below Vehtari's total of 400 for a stable Monte Carlo standard error.
- **Two "per split chain" figures, both right.** `docs/progress.md:2284-2285` says 22 per split chain, for the 2-seat share's ESS of 268. The figure's 24 is for the seat count, which is the right one for this R-hat.

## Outside the diff
- `README.md:56-58` carries the unlabelled "less compact than 88%" (finding 1).
- Two comments from 7bf57db overstate what the population-tight profile shows:
  - `tools/plot_seat_distribution.py:460-461`: "how much of the compactness gap follows from the population gap";
  - `tests/test_seat_distribution.py:154-155`: "much of the compactness gap follows from the population gap".

  Both contradict D-041's "by an amount these draws cannot measure", and audit 2's refuter, who did not uphold "largely downstream".

---

## Third refuter, allegation 1 — Computational Redistricting Scientist

## Refuter report, allegation 1 (Statistician): "'Less compact than 88% of the draws' holds on cut edges only"

**Overall: UPHELD (material).** I started from REFUTED and could not refute any bullet. Every number reproduces from committed files at HEAD 4d7a5ab. Two bullets need small corrections: one leg of bullet 2 is inferred rather than verified, and bullet 5 understates how weak the contrast is. Neither correction helps the note. The rendered PNG (`docs/figures/ia-neutral-seat-distribution.png`) says "the plan is less compact than 88% of the draws" and never names the measure. `tests/test_seat_distribution.py:311-313` pins that exact wording. README.md:56-58 doesn't name the measure either.

**How I reproduced it.** I loaded the rectangle through the plotter's own loader, `X.chains_from_draws(..., rectangle=4594)`: chains [0, 1, 2, 5, 6, 10] × 4,594 = 27,564 draws, with seats from `P.recover_seats`. I asserted that my draws and seats match `P.seat_distribution()` exactly. The enacted plan's values come from `docs/phase-2/phase-2-report.json`. `data/` doesn't exist anywhere on this machine, so I could recompute nothing from geometry. The worktree is unmodified.

### Bullet verdicts

**Title claim: UPHELD.** `more_compact_share` at plot_seat_distribution.py:459 counts cut edges only. The text at :559-560 doesn't name the measure. The figure carries no other mention of it.

**Bullet 1, cut edges: UPHELD.**
- 24,223 draws have fewer cut edges than the plan's 51 (87.88%), 999 tie (3.62%) and 2,342 have more (8.50%).
- This share has its own Monte Carlo error. The note gives none:
  - indicator ESS 343, split R-hat 1.022
  - 2 SE about 3.5 points
  - chain range 77.1–91.9% (chain 6 is the low one)

**Bullet 2, Polsby-Popper is a like-for-like comparison: UPHELD.** The geometry-identity leg is inferred, not verified.
- **Same code.** Draws: experiment_2_tradeoffs.py:237-238 and :260, an unweighted mean of `measure_districts` over the 4 districts. Report: report.py:149 → `compactness.all_metrics` → `measure_districts`, mean at compactness.py:1012-1014.
- **Same loader and file.** Both read `generate.units.load_geometry` on `data/processed/ia_units.gpkg` (experiment_2_tradeoffs.py:269, phase_2_report.py:38). The loader reads the file as stored: no reprojection, only a column guard (units.py:49-55).
- **The cache doesn't change values.** It is tested exact on real Iowa plans (tests/test_compactness.py:1077-1096).
- **Byte identity of the gpkg can't be checked here.** The evidence for it:
  - No visible commit after the shallow boundary (bdd1abe) touches compactness.py, generate/units.py or tools/prepare_data.py.
  - The report was written at d09bcad (2026-08-21) and the v2 draws at 9f2b13f (2026-08-22).
  - All six rectangle chains reproduce v1's first 1,500 rows bit for bit, `polsby_popper_mean` included.
- **What PlanScore's 0.33325 shows.** It confirms the plan's own value, independently and on PlanScore's outlines. It says nothing about the draws.

**Bullet 3, the plan is mid-ensemble on Polsby-Popper: UPHELD.**
- 13,425 draws score higher (48.70%) and 14,139 lower (51.30%), with no exact ties. The draws' median is 0.33252 and their IQR 0.3119–0.3538.
- Monte Carlo error: indicator ESS 285, split R-hat 1.027, 2 SE about 5.9 points, chain range 36.1–60.4%.
- The location barely moves with measurement error. I shifted the plan's value alone by ±0.43%, the Polsby-Popper projection sensitivity compactness.py documents for Iowa, as an upper bound on any measurement difference between the plan and the draws. The share moves only between 47.8% and 51.4%.
- **Distinct rows.** There are 4,020 distinct rows: 68.5% have fewer cut edges and 19.4% a higher Polsby-Popper. This is a sensitivity check, not the ensemble's distribution: 66.4% of draws repeat the draw before them, and rows above the plan's Polsby-Popper are held 17.2 draws each against 4.4 below.
- Counted that way, the two measures point in opposite directions about the plan. That strengthens the allegation.

**Bullet 4, CRITERIA §3 applies: UPHELD.**
- Spearman ρ(Polsby-Popper, cut edges) is −0.7579 over the draws (scipy and the repo's `C.spearman` agree) and −0.6960 over distinct rows. By chain it runs from −0.696 to −0.819.
- The committed Experiment 2 result says the same: +0.7579 in goodness orientation, chain-level CI 0.722–0.794 (`docs/experiment-2/experiment-2-results-v2.json`). The whole interval is below §3's ~0.9 bar.
- **The rule applies to this note.** CRITERIA.md:163-171 covers it, and so does the owner's brief: prompt.md:107-108 ("side by side… highlighted rather than resolved") and :191-193 ("must be surfaced to users"). The figure travels without the README (plotter docstring, line 9).
- **The plan sits off the ensemble's ridge.** The two measures disagree about it on 40.2% of draws: 39.7% are more compact on cut edges only and 0.5% on Polsby-Popper only. Among the 999 draws with exactly 51 cut edges, only 7.5% have a higher Polsby-Popper (their median is 0.2989).

**Bullet 5, "commoner" survives on Polsby-Popper but weaker: UPHELD, and understated.**
- The quoted figures reproduce exactly:
  - 1.99% (281/14,139) against 0.85% (114/13,425)
  - 1.42% against 0.87% after dropping 500 draws per chain
  - chain 2 reversed, 1.18% against 2.20%
- At the chain level the contrast is indistinguishable from zero at every warm-up. Chain-level t(5) 95% intervals for the per-chain difference: full −0.62 to +2.70; after 500, −0.65 to +1.77; after 1,000, −0.79 to +1.44; after 2,000, −1.24 to +1.83.
- My method reproduces the record's cut-edge intervals exactly: −0.68 to +5.73 on the full rectangle and +0.29 to +2.27 after 500. On the full rectangle the figure plots, neither measure's interval excludes zero.

**Bullet 6, the same premise outside the diff: UPHELD.**
- The line cites check out: README.md:56-58, DECISIONS.md:1230-1231 and progress.md:2460-2462. The premise is that the draws already exceed the enacted plan's compactness. That holds on cut edges and fails on Polsby-Popper, where the median draw (0.3325) sits just below the plan (0.3334).
- D-041 names cut edges in its statement of facts (DECISIONS.md:1219-1220), and so does progress.md:2442-2445. But its "why the two are not treated alike" generalizes the premise to compactness as a whole.
- The materiality is to D-041's stated reasoning, not necessarily to its choice. On Polsby-Popper the draws already match the plan, so there's nothing to adjust for there either. Sending this to the owner is proportionate.

**Bullet 7, VALUE choice: UPHELD.** CRITERIA.md:150-152 says "`VALUE` throughout." The strongest non-legal case for leading with cut edges is the plotter's own rationale at :437-438, "ReCom leans compact." In my reading that lean acts on the unit graph, so cut edges is the measure that shows it. That is a reason to name the measure, not to leave it unnamed: on Polsby-Popper the draws don't lean compact relative to the plan. I didn't verify Iowa Code ch. 42's compactness provisions, and the repository doesn't state them.

### The four questions you set
- **Like-for-like:** yes on code, projection (the stored CRS, read the same way on both paths) and aggregation (an unweighted 4-district mean). The geometry file's identity is strongly supported but not verifiable here.
- **Is mean Polsby-Popper a reasonable stand-in?** As a measurement, yes.
  - PlanScore agrees with the plan's value to 0.04%, and the location is insensitive to plausible measurement error.
  - It carries Polsby-Popper's known perimeter failure mode on Iowa's two river borders (FEASIBILITY.md:191).
  - The unweighted mean hides the worst district (enacted minimum 0.2755). The draws don't store a minimum, so the worst-district comparison can't be made.
  - Cut edges has its own failure mode: it depends on the graph and ignores the outer boundary.
  - Nothing committed shows Polsby-Popper to be the misleading one. The two measures answer different questions about this plan, which is what §3 predicts.
- **Can Reock, Schwartzberg or convex hull be placed?** No. The draws carry only `cut_edges` and `polsby_popper_mean`, and the v2 plans aren't committed.
  - Schwartzberg's mean can't be derived from the Polsby-Popper mean. On the enacted plan the gap is 1.75097 against 1/√0.33338 = 1.73192, a gap of 0.019.
  - The only five-measure Iowa reference in the tree is the 806-draw round-02 range at progress.md:688. It gives min and max only, comes from a different ensemble, and its per-draw values aren't committed. The plan falls inside every range there.
  - Recovering the plans would mean re-sampling, which is a new experiment under D-036 and the owner's call.
- **Does §3 apply to this sentence?** Yes; see bullet 4.

### What the evidence supports
On the two compactness measures these draws carry, the enacted plan's location depends on the measure. The sample is 27,564 ReCom draws at ε = 2×10⁻⁴, six chains truncated to 4,594 each. On cut edges in Iowa's rook county graph, the plan's 51 exceed 87.9% of the draws (2 SE about 3.5 points; chains 77–92%). On mean Polsby-Popper over its four districts, computed by the same code on the same county geometry, its 0.33338 sits near the median: 48.7% of draws score higher (2 SE about 5.9 points; chains 36–60%). The measures rank the draws at |ρ| = 0.76, below §3's bar. Among draws with the plan's own cut-edge count, only 7.5% have a higher Polsby-Popper. Reock, Schwartzberg and convex hull can't be placed. A sentence the evidence supports reads roughly: "the plan has more cut edges than 88% of these draws, but sits near their median on mean Polsby-Popper; the draws carry no other compactness measure." It should keep the "commoner" contrast in pooled terms only, since on neither measure is it distinguishable from zero at the chain level on the plotted rectangle. Unqualified, "less compact than 88% of the draws" settles a disagreement in favour of one measure, which §3 and prompt.md:107-108 say to show rather than resolve. None of this is a finding about the enacted map: it locates one plan in one ensemble whose population mismatch remains (454 of 27,564 draws are as equal), and whose split R-hats fall outside the 1.00–1.01 band.

### Adjacent issues (outside the allegation)
- **The 88% is quoted without an interval:** 2 SE about 3.5 points, chain range 77–92%. This goes to the Statistician.
- **progress.md:2451-2456 compresses the audit record.** It says "after any warm-up of 500 to 2,000 draws … a chain-level 95% interval … of +0.3 to +2.3", and that the contrast holds "in five of six after dropping more." The record (`docs/first-result/INSTRUMENT-AUDIT.md`:512-523 and :756-758), which I reproduced, shows the interval holds only at 500. It includes zero from 750 on, and at 2,000 only 4 of 6 chains hold. The phrase "The direction is robust" (progress.md:2447) leans on this. It goes to the Statistician and the Pre-Submission Peer Reviewer.
- **Population-tight draws (454 draws, 96 distinct rows):** 78.4% have fewer cut edges than the plan, and 33.7% a higher Polsby-Popper. This is context only for the owner's D-041 decision.

### Handoffs
- **Owner:** which compactness measure to lead with (a VALUE choice), and D-041's measure-dependent premise.
- **Election Law Analyst:** only if the author argues that Iowa's statutory standard favours one measure.
- **Scientific Visualization Reviewer:** any change to the figure's note, which has 41 characters per line.

### Files
All in /tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/refute-pp/:
- reproduce.py and reproduce.out: shares, 2×2 table, Monte Carlo error, distinct rows, Spearman, zero-seat splits, sensitivity
- chain_intervals.py and chain_intervals.out: chain-level intervals and the Schwartzberg gap
- tight.py and tight.out: population-tight draws
- prefix.out: v1/v2 prefix identity

This is an AI-assisted review from the same model family that wrote the repo, so it is a partial check. A redistricting scientist outside the authoring loop should read any claim headed for publication.

---

## Third refuter, allegation 2 — Statistician

## Refutation of allegation 2: "context, not an adjustment"

**Verdicts**
- **(a): UPHELD.**
- **(b): UPHELD**, with one sub-claim corrected: its own counter-case is overstated.
- **(c): PARTLY UPHELD.** The conclusion stands, but its framing overstates and one count is mislabelled.
- **The recommendation: UPHELD, and strengthened.** On Polsby-Popper the "88%" is about 49%.

Severity: material for the figure note and for README.md:56-61. The figure carries one side of an open VALUE question (D-041) as the reason for a methodological position. No number moves, the headline is unaffected, and "Not yet a finding" stands.

**How I reproduced it**
- **Worktree:** HEAD 4d7a5ab. `git status` was clean before and after, and I edited nothing in the repository. I read the diff of 4d7a5ab but not its message.
- **Figure:** `tools/plot_seat_distribution.py --out <scratch>` renders a PNG byte-identical to the committed one (sha256 9da55255…). The note's text matches the sentence under audit.
- **Loader:** my own (`load.py`). It reads `ia-draws-v2.csv.gz` with `csv` and `gzip`, and checks draw order, the sidecar row counts and the seeds. It cuts chains 0, 1, 2, 5, 6 and 10 to their first 4,594 draws.
- **Seat recovery:** my own nearest-level reading, asserting both D-039 checks. On all 27,564 draws it equals the plotter's `seat_distribution()` lists.
- **Enacted values:** from `docs/phase-2/phase-2-report.json` (51 cut edges, Polsby-Popper mean 0.3334). Both sides compute Polsby-Popper with `evaluate.compactness.measure_districts` on the same `ia_units.gpkg`, as an unweighted district mean, so the two values compare.

**Mechanical numbers: all reproduce**
- 0 seats in 395 of 27,564 draws (1.43%).
- At 51 or more cut edges: 151 of 3,341 (4.52%), against 244 of 24,223 below (1.01%).
- After dropping each chain's first 500 draws: 1.15% overall, and 2.16% (61 of 2,826) at 51 or more.
- At a strict >51: 2.18% (51 of 2,342).
- 87.88% of the draws have fewer cut edges than the enacted plan.
- At a spread of 94 or less: 2 of 454 (0.44%). This is one plan, chain 5's draws 1,584–1,585, with spread 74, 45 cut edges and Polsby-Popper 0.3503. It is more compact than the enacted plan on both measures.
- The line references are right: plot_seat_distribution.py:557-566, DECISIONS.md:1223-1225 and :1235-1237.

### (a) UPHELD
- The reference's 0-seat share is a property of the draws alone:
  - 1.43% unfiltered;
  - 0.44% filtered on population;
  - 4.52% filtered at 51 or more cut edges.
- So "whether or not it was drawn for that outcome" is true of every one of these references, and cannot be what separates compactness from population.
- The charitable reading is that the adjustment would hide an effect if the plan was drawn for 0 seats. That reading discriminates only with a premise the note doesn't state: compactness lies downstream of how the plan was drawn, and population doesn't. That premise is in D-041, and it is what (b) disputes.
- In the clause's own "or not" branch, a higher share under conditioning is no defect. It is either a valid conditional reference or a partial correction for unmet constraints.
- The clause is not false: "would raise" is true of these draws on both measures.

### (b) UPHELD, one sub-claim corrected
**Reproduced from the documents:**
- The clause lifts the over-adjustment argument from audit 2's allegation 2 (INSTRUMENT-AUDIT.md, second audit).
- D-041 concedes the other premise at DECISIONS.md:1235-1237.
- D-041 is marked VALUE and leaves any conditioning to the owner (:1223-1225).
- The note states one case, as a consequence, with no owner flag.

**Corrected sub-claim:** "conditioning corrects the comparison, and the unconditioned 1.4% overstates how rare 0 seats is" is too strong.
- Even when the gap comes from constraints, conditioning at the plan's own level is not the correction. The correction would weight to a matched reference's compactness profile, which these draws don't supply.
- Applying the full ensemble's P(0 seats | cut edges) gives a different answer under each candidate profile:

  | Profile | 0-seat share |
  | --- | --- |
  | The 454 population-tight draws' cut-edge profile | 2.36% (2.32% after the warm-up) |
  | Uniform over FEASIBILITY §5.3's 57–67 | 0.97% |
  | Filtering on population directly | 0.44% |
  | Conditioning at 51 or more | 4.52% |
  | Exactly 51 | 10.0% (100 of 999; 84 of the 100 are chain 6's warm-up) |

- The relationship is not monotone:

  | Cut edges | P(0 seats) |
  | --- | --- |
  | 43–50 | 1.49% |
  | 51 | 10.0% |
  | 52–57 | 2.40% |
  | 58–66 | 0 of 221 |

- So under (b)'s scenario the 1.43% could overstate or understate how rare 0 seats is.
- **Additional support for (b):** the premise "how uncompact the plan is was a choice" holds only on cut edges. See the recommendation below.

### (c) PARTLY UPHELD
**The table reproduces:**

| Spread | 0 seats at ≥51 | 0 seats below 51 |
| --- | --- | --- |
| ≤94 | 0 of 98 | 2 of 356 |
| ≤150 (cumulative) | 1 of 521 (1 visit) | 24 of 4,116 |
| 95–150 | 1 of 423 | 22 of 3,760 |
| 151–300 | 148 of 2,744 (5.39%) | 220 of 19,747 (1.11%) |
| >300 | 2 of 76 | 0 of 360 |

- The single draw at ≥51 in the ≤150 band is chain 5's draw 3,579: 57 cut edges, spread 116.
- 148 of the 151 zero-seat draws at ≥51 sit in the 151–300 band. 89 of them are chain 6's draws 234–437, at spreads 232–271; 84 of those are at exactly 51, and they are 8 distinct rows.
- **Mantel–Haenszel ratio:** the auditor's 4.44 and 2.03 reproduce with five bands (≤94, 95–150, 151–225, 226–300, >300): 4.438 and 2.025, against crude ratios of 4.487 and 2.114.
  - Across eight bandings it runs 4.21–4.55 on the full rectangle and 2.00–2.13 after the warm-up.
  - Stratified by chain it is 4.48 and 2.21, which matches audit 2.
  - So spread does not confound the association.
- **The conclusion holds:** the population-tight end cannot show the association.
  - The ≤150 band's zero-seat draws form 4 excursions: chain 0 at 149–150; chain 5 at 1,576–1,585 and at 3,550–3,592; chain 6 at 3,484.
  - One of them touches ≥51.
  - Tested against a ratio of 4.44 at the excursion level, p = 0.17. That neither shows nor excludes the association.

**Not upheld:**
- **"7 visits".** By my definitions that cell is 6 consecutive zero-seat runs, 9 runs of identical rows, or 4 excursions; it is 7 only as distinct plans. Audit 2's "7" was the band's total, with 1 of them at ≥51.
- **"Lives in the draws least like the plan".** The 151–300 band holds 81.6% of all draws and 82.1% of those at ≥51. The band that really is least like the plan, >300, points the same way. The association can't be *observed* in population-tight draws; nothing shows it is *specific to* the loose ones.
- **"The comparison the note itself treats as like-for-like".** The note treats no comparison as like-for-like.
- This blind spot also undercuts (b)'s "corrects".

### Recommendation: UPHELD, strengthened
- The draws carry two compactness measures, and on them the plan's position differs:

  | Draws compared | More compact by cut edges | More compact by Polsby-Popper |
  | --- | --- | --- |
  | All 27,564 | 87.9% | 48.7% |
  | The 454 at spread ≤94 | 78.4% | 33.7% |

- On Polsby-Popper the plan sits mid-ensemble overall, and is more compact than two-thirds of the population-tight draws.
- Spearman ρ between cut edges and Polsby-Popper over the rectangle is −0.758. That is under the ~0.9 at which CRITERIA §3 lets the choice of measure go unstated, and §3 requires every measure reported and disagreements surfaced.
- The note (plot_seat_distribution.py:559-560) and README.md:56 both say "less compact than 88%" without naming cut edges.
- On Polsby-Popper, 0 seats is still commoner among less compact draws, but only slightly:
  - 1.99% of draws at or below the plan's value (281 of 14,139), against 0.85% above;
  - 1.42% against 0.87% after the warm-up.

### Outside the allegation
- **The same argument appears in three more places:**
  - README.md:56-61, with the measure unnamed and no owner flag;
  - progress.md:2463-2465, which does flag the owner's choice at :2474-2475;
  - DECISIONS.md:1232-1235. D-041 isn't rewritten; a reversal would be a new entry.
- **A test comment makes the opposite overclaim.** tests/test_seat_distribution.py:154-155 says "much of the compactness gap follows from the population gap", which audit 2's refuter did not uphold.
- **The note is pinned verbatim** at tests/test_seat_distribution.py:311-314, so any rewording needs that test changed in the same commit.

### What the evidence supports saying
These draws support the facts, with the measure named:
- **By cut edges:** the enacted plan's 51 is more than 88% of the draws have. 0 seats is commoner among draws at 51 or more (4.52%, 151 of 3,341) than among the rest (1.01%). Once each chain's first 500 draws are dropped it is 2.16% against 1.02%, and most of the full-rectangle excess is one excursion of chain 6 at exactly 51.
- **By Polsby-Popper,** the other measure the draws carry, the plan sits mid-ensemble: 48.7% of draws are more compact. It is more compact than two-thirds of the population-tight draws. 0 seats is only modestly commoner below its value: 1.99% against 0.85%.

Whether to condition the reference on compactness depends on why the plan is less compact on cut edges, and these draws cannot say:
- **If it came from how the plan was drawn,** conditioning absorbs part of what the comparison tests.
- **If it came from constraints the draws don't meet,** population equality first, conditioning moves the reference toward a matched one. These draws fix neither the size of that move nor its direction: 2.4%, 1.0% or 0.44% under the three candidate profiles, against 4.5% conditioning at the plan's own level.

So the note should give the facts and either stop there, or state both cases, say these draws cannot tell which, and mark the choice as the owner's under D-041. Nothing in these draws speaks to how the enacted plan was drawn, and the comparison stays not yet a finding.

### Files
All in /tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/refute-cond/:
- load.py
- repro.py
- extra.py
- final.py
- repro.out
- extra.out
- final.out
- plotter-summary.txt
- fig.png

---

## Author's response to the third audit

Both refuters upheld their allegations, so each is answered by a change, in the
commit that follows `4d7a5ab`. Numbers the answers quote are printed by
`tools/plot_seat_distribution.py` and pinned by `tests/test_seat_distribution.py`,
except where they come from the reports above.

| # | Allegation | Refuter | What changed |
| --- | --- | --- | --- |
| 1 | "Less compact than 88% of the draws" holds on cut edges only, and the measure is not named | Upheld | Compactness is off the figure: its note gives the population mismatch as the reason the comparison is not like-for-like, cites D-041, and stops. The README, `docs/progress.md` and D-041 give both measures the draws carry, with their chain ranges: 87.9% of the draws have fewer cut edges than the enacted plan (77.1–91.9% by chain), and 48.7% a higher mean Polsby-Popper (36.1–60.4%). They give the rank correlation of 0.76 against `CRITERIA.md` §3's ~0.9, and say that Reock, Schwartzberg and convex hull cannot be placed. The plotter computes both measures the same way, and the tests pin them. D-041 no longer says the draws already exceed the enacted plan's compactness. |
| 2 | The clause "whether or not it was drawn for that outcome" does not support "context, not an adjustment", and argues one side of D-041's open question | (a) and (b) upheld, with (b)'s "corrects" overstated; (c) partly upheld | The clause is gone from the figure, the README and `docs/progress.md`. Each of those, and D-041, now states both cases. If the plan's shape follows from how it was drawn, conditioning absorbs part of what the comparison tests. If it follows from constraints the draws do not meet, conditioning moves the reference toward a matched one, by an amount and in a direction these draws cannot fix: the refuter's candidate references give 0.44% to 2.4%, against 4.5% at or above the plan's cut-edge count. These draws cannot tell which case holds, and the choice is the owner's. `docs/progress.md` gives the Mantel–Haenszel ratios across population bands, and says that the 454 population-tight draws are too few to show the association either way. The parts of (c) not upheld (the "7 visits", "lives in the draws least like the plan", and a like-for-like comparison the note never made) appear in no text. |
| 3 | "Drawn for that outcome" raises the real plan's purpose on the headline figure | Not sent to a refuter (minor) | Gone with the clause in 2. |
| 4 | The footer's "settles convergence neither way" prints whenever the effective sample is low, whatever the R-hat | Not sent to a refuter (minor) | The phrase is gone. The footer says that 24 effective draws per split chain are below the 50 Vehtari et al. (2021) ask for before relying on R-hat. It says the standard errors may understate the uncertainty, and that caution now also prints when the R-hat is above the band at any effective sample. The test holds both at R-hat 1.08. |
| — | Two comments say the population gap explains much of the compactness gap | Upheld by both refuters | Both now say that how much of the cut-edge gap follows from the population gap these draws cannot measure (D-041). |
| — | `docs/progress.md` compresses the second audit's warm-up result | Raised by the first refuter | Corrected to what the record shows. The chain-level interval excludes zero only at the 500-draw cut, and includes it from 750 draws on and on the full rectangle. The contrast holds in all six chains up to 500, in five of six at 750 to 1,500, and in four of six at 2,000. On Polsby-Popper the interval includes zero at every warm-up. |
| — | D-041 "isn't rewritten; a reversal would be a new entry" | Raised by the second refuter | D-041 is new in this unmerged change, and what it chose is unchanged: the unconditioned share is reported, population is the reason the comparison is not yet a finding, and any conditioning is left to the owner. Its facts and reasoning are corrected in place, and its last line points here. |

**After the routing reviews.** The `Computational Redistricting Scientist`, the
`Pre-Submission Peer Reviewer` and the `Election Law Analyst`, reading the commit
that answered this audit, found that the answer itself overreached. The commit
after it corrects that:

- The cut-edge gap has a third possible source, the sampler's own preference for
  few cut edges, under which conditioning would undo part of the reference's
  target. The README, `docs/progress.md` and D-041 give all three cases, and make
  the second conditional on the draws' relation between compactness and seats
  carrying over to plans drawn at the enacted plan's tolerance.
- The second refuter's reweightings are illustrative, not candidate matched
  references. The 0.44% is a population filter the same documents set aside, the
  2.4% carries the whole ensemble's zero-seat share at each cut-edge count over to
  the population-tight draws, and is 2.32% after the warm-up, the 1.0% rests on the
  126 draws at 57 cut edges, and the 57–67 range is what a beam search found, not
  what population-tight plans carry in general.
- The README again quoted the contrast's magnitudes, which the second audit had
  removed as not robust. It now gives the direction, and says the size is not
  robust.
- `docs/progress.md` read `CRITERIA.md` §3 as letting the choice of measure go
  unstated above a rank correlation of about 0.9. §3 says the choice does not
  matter there, and asks for all five of its measures always.
- Iowa Code §42.4(4) names length-width and perimeter compactness for comparing
  plans, and the draws carry neither. The enacted plan's 94-person spread is the
  level it reached, not a legal requirement. The Analyst's register is
  `docs/first-result/LEGAL-CLAIMS.md`.

The plotter now prints each location's Monte Carlo error, each measure's own split
R-hat, the draws' median Polsby-Popper, the population-tight draws' split on each
measure, and the draws by cut edges, so the counts these answers quote are pinned.

The reviews of that commit corrected four details in it, in the commit after: the
support it first gave the 2.4%, its quotation of *Karcher v. Daggett*, its account
of how the sampler's per-district tolerance relates to the spread, and a README
sentence that left a lay reader to infer the enacted plan's purpose. The README
paragraph was also rewritten for readers outside the field.

---

# Fourth audit — the 0-seat reading, after review of pull request #7

GitHub Copilot's automated review of pull request #7, at commit `1cc22f8`, showed
that the half-vote grid D-039 relied on to call the 0-seat count verified is
necessary, not sufficient: it constructed district vote totals that give the
Democrats 2 of 4 seats and land on the grid. Commit `ef1060c` withdrew "verified"
from D-039, `docs/progress.md` and the plotter. A corrected claim goes through the
audit first (D-007), sized to a corrected claim: one auditor, and one refuter for
its four allegations.

- **Audited state:** commit `ef1060c`. Line numbers in the reports refer to it.
- **Auditor:** the `Statistician` agent, a fresh instance, with an inference lens.
- **Refuter:** a `Computational Redistricting Scientist` agent, a fresh instance
  told to default to "refuted" and to reproduce every number with its own code
  before agreeing.

Both reports are verbatim. The last section is the author's response, and is not
part of either report. The same commit also went to the `Code Reviewer`, the
`Computational Redistricting Scientist`, the `Pre-Submission Peer Reviewer`, the
`Technical Writer` and the `Scientific Visualization Reviewer`; their findings are
answered in the same revision and are not reproduced here.

---

## Fourth auditor — Statistician

## Instrument audit, inference lens: the corrected 0-seat claim (git diff 1cc22f8 HEAD)

**Verdict:** The arithmetic of the correction is right, and "only a recount would verify it" is right as a statement about proof. Four problems remain:
- The sentence that ends with "only a recount would verify it" now **understates** the 0-seat count. The difference from the other counts is one of kind, not only of distance.
- The recount D-039 points to would **not** verify the 0-seat count.
- The 0.0143 yardstick is a residual measured after the readings it is used to defend, and it is selected.
- Nothing in the changed text reads as a verdict.

I reproduced everything below from committed files. The plotter exits 0 and the two changed tests pass. My scripts and outputs are in `/tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/audit4-stat/` (`probe.py` to `probe4.py`, `probe-out.txt`, `plotter-stdout.txt`). Nothing was written in the repo.

### Allegations

**1. "Rests on the turnout assumption like the others, with more room" understates the evidence in kind.**
- **Where:** `docs/progress.md:2414-2417`, `docs/DECISIONS.md:1139-1141`, `tools/plot_seat_distribution.py:53-57`, `tests/test_seat_distribution.py:236-237` ("a reading like the others").
- **Why it is wrong:** the sentence compares distance only. The two kinds of misread need different things, and fail differently on a near miss.
  - **1 vs 2 seats:** a misread is admitted silently for any turnout term from 0.062 to 0.103. That band is 0.041 wide, about 68,000 votes.
  - **A non-sweep entering the 0 bar:** admitted only if the districts the Democrats win total 1,379,511 plus 0 to 6 votes. The exact window is 3 to 6 at 1 seat, 1.5 to 4.5 at 2, and 0 to 3 at 3. In turnout-term units that target is about 4e-6 wide.
  - **A near miss:** any other value in the 0 bar's window (|EG| from 0.375 to 0.500, residuals from −68,000 to +139,000 votes) makes `recover_seats` refuse the whole sample (`plot_seat_distribution.py:192-202`).
  - So if the turnout assumption failed, the 0 bar would show it as a refusal, while the 1-vs-2 split could pass it silently. That is the opposite of "like the others".
- **What the committed data show:**
  - **No refusals.** Under the presidential vote, none over all 57,553 committed rows (the plotter reads them all). Under the Senate vote, none either: I read all rows; the plotter reads only the rectangle.
  - **Nothing near the 0 bar.** No non-sweep has |EG| above 0.1730. The nearest sits 0.243 (about 403,000 votes) below the 0-seat level.
  - **The binding 3-seat case.** The only 3-seat plans observed (the Senate vote's 8 draws, 2 plans) carry a turnout term of 0.007, against the 0.083 a misread would need.
  - **The Senate vote.** 194 of the 395 also sit exactly on the Senate sweep grid. The other 201 read as 1 or 2 Senate seats, within 0.006 of their levels.
- **Smallest fix:** replace the clause with something like: "is a reading too, but a harder one to get wrong: a non-sweep is admitted only on one of a few vote totals, and one that came near and missed would stop the plotter, which no committed row does". In the test comment, change "a reading like the others" to "a reading, not a count".

**2. The recount D-039 names would not verify the 0-seat count.**
- **Where:** `docs/DECISIONS.md:1141` ("only the recount above would verify it") points to `docs/DECISIONS.md:1119-1121` ("A one-time recount of one chain would turn this reading into a verified count").
- **Why it is wrong:**
  - **One chain cannot cover the 395.** They are spread over all six chains: 68, 70, 76, 48, 113 and 20 (chains 0, 1, 2, 5, 6, 10). One chain covers at most 113.
  - **A one-chain recount verifies only that chain.** For the other five chains it tests the method; it does not verify their readings.
  - **The 0-seat reading can only overcount.** A true sweep always lands on its grid point and is always read as 0. The plotter refuses a bad draw rather than dropping it. So the count can be too high, never too low.
  - **A recount of only the draws read as 0 is enough.** That is 395 draws, at least 97 distinct plans counted by distinct metric rows. It would verify the count outright, whatever the other draws hold.
- **Smallest fix:**
  - At `:1141`: "only a recount of the draws read as 0 would verify it (every sweep is read as one, so the count can be too high, not too low)".
  - At `:1120-1121`: "would verify that chain's readings and test the method on the rest".

**3. The 0.0143 yardstick is a residual measured after the readings, and it is selected.**
- **Where:**
  - `docs/DECISIONS.md:1145` ("four times the largest imbalance in the data")
  - `docs/progress.md:2424-2425` ("four times the largest in these draws")
  - `tools/plot_seat_distribution.py:61-62` ("four times the largest imbalance in these draws")
  - Used as evidence for the 0 bar at `progress.md:2414-2415`, `plot_seat_distribution.py:53-54` and `tests/test_seat_distribution.py:240`.
- **Why it is unsupported:** a residual is measured from the level a draw was assigned to. It equals the draw's turnout term only if the reading is right.
- **The selection effect (Q1):**
  - **Draws read as 0 are excluded.** Any non-sweep read as 0 is outside the population 0.0143 is computed on, by construction. So 0.0143 says nothing directly about the turnout term of draws read as sweeps. It bears on them only through the assumption that all plans share one turnout distribution, which is the turnout assumption itself. The evidence that doesn't need that assumption is in allegation 1.
  - **1-vs-2 misreads stay in, at small residuals.** The draw that sets the 0.0143 (chain 2, draw 667, |EG| 0.09797, read as 2 seats) lies on the side facing the 1-seat level. Read as 1 seat, its turnout term would be 0.068, inside the band that is admitted silently.
  - **The tail is one-sided.** The 2-seat residuals have 195 draws beyond 0.008 on the side facing the 1-seat level and none on the other side.
  - So "four times the largest imbalance" assumes the readings it is offered to defend.
- **Evidence that does not assume the readings is committed:**
  - Draw 667 reads as 2 seats under the Senate vote too, with residual 0.0159, the Senate maximum.
  - 161 of the 195 tail draws read as 2 under the Senate vote, with residuals within 0.0024 of their presidential ones.
  - Same-seat residuals correlate at 0.95 across the two contests.
  - A misread 1-seat plan would repeat its residual only if a second district happened to carry a particular share of the vote.
- **Smallest fix:** change "imbalance" to "residual" at all three places. Optionally, cite the cross-contest agreement as the support that does not assume the readings.

**4. (Q2) "With more room" is true, but it measures the smaller of the two differences.**
- **Where:** same places as allegation 1.
- **The numbers:**
  - At the binding case (3 seats, 0.083) the room is about 1.3 times the 1-vs-2 room (0.062).
  - That comparison sets a 3-seat turnout term against 1- and 2-seat residuals, and no draw is read as 3 under the presidential vote.
  - At the seat counts that do occur, the room is 0.333 and 0.583: 5.4 and 9.4 times.
  - The difference that matters more is the target width in allegation 1, about 4e-6 against 0.041.
- **Fix:** covered by allegation 1. If the room comparison stays, cite the Senate vote's 3-seat plans (0.007) for the 3-seat case.

### Q3: what else rests on verification

- **Only one sentence claims verification:** `DECISIONS.md:1120-1121` (allegation 2).
- **I checked these and none calls the 0-seat count verified:**
  - README:16 (alt text) and README:53-58
  - the figure's note and footer; the footer says "Seats are read off each draw's |efficiency gap| (D-039)"
  - the `progress.md:2272` table: MCSE 0.38 points, chains 0.4–2.5%
  - `progress.md` at 2353-2357, 2428-2434, 2440-2443, 2471-2498 and 2565
  - D-041 at 1232-1234
  - CITATION.cff, which doesn't quote the share
  - the verbatim audit record
- **Two sentences depend on the readings and are consistent with the corrected status. Neither needs a change:**
  - The mid-ranks at `progress.md:2578-2582` need each draw's sign, which the committed |EG| doesn't carry. A non-sweep on the 0 grid would have the opposite sign (−0.4163), and would sit at the bottom of the ranking, not the top.
  - `progress.md:2312`, "no draw gives Democrats 3 or more seats", inherits the same protection. The 3→0 misread is exactly the case the corrected text names.
- **Intervals:** the MCSE (0.38), the figure's ±0.8 points and the chain range are Monte Carlo errors only, and labelled as such. The 0 bar's reading error can only push the count up, and on this evidence it is negligible. They need no change.

### Q4: verdict wording

None in the changed text. One caution about allegation 2's fix: "can only be too high" implies the true 0-seat share is at most 1.43%. Put it in D-039's method text, not next to the enacted-plan comparison, or keep "not yet a finding" beside it.

### Checked and sound

- **The algebra.** For a non-sweep landing on the grid, the winning districts' total minus 1,379,511 must be the grid value plus (Σ_R δ − Σ_D δ). So "4V − 1, to within a few votes" and "83%" (0.83267) are right. The turnout terms are 0.0827, 0.3327 and 0.5827.
- **The 0 grid is the only hole.** The positive branch and the 4-seat grid would each need the winning districts' total, or the losing district's total, to be zero or negative.
- **The plotter reproduces every number:** 395 draws; the grid split {2.5: 216, 3.5: 179}; largest residual 0.0143; half-gap 0.0413; residual SDs 0.0020 and 0.0030; the Senate grid split {2: 23, 3: 222, 4: 25}; Senate largest residual 0.0159.
- **"Necessary, not sufficient" is right.** No committed column (mean-median, competitive districts) separates a sweep from a non-sweep landing on the grid, so "only a recount" holds as a statement about proof.
- **"Iowa's is a sweep, exact whatever the turnout"** (`progress.md:2430-2431`, `DECISIONS.md:1147-1148`) is about the enacted plan, counted from the returns. Correct.
- **The test's constructed 2-seat plan lands on the 3.5 grid.** Its bound of K holds for that 2-seat example. The general window reaches 6 votes at 1 seat, which "a few votes" covers.

Not in my lens and not assessed: whether rewriting D-039 in place fits the decision log's append-only rule while the PR is still open.

---

## Fourth refuter — Computational Redistricting Scientist

## Refuter report: instrument audit of the D-039 0-seat wording (refute4)

**Scope**: `git diff 1cc22f8 HEAD` on docs/DECISIONS.md, docs/progress.md, tools/plot_seat_distribution.py and tests/test_seat_distribution.py, at ef1060c. Evidence: docs/experiment-2/ia-draws-v2.csv.gz and its sidecar, src/evaluate/partisan.py, the plotter and the loader.

I did not open the auditor's scratch directory (`audit4-stat`) and did not read any commit message.

**Method**: I wrote my own scripts and did not use `recover_seats`.
- Every committed |EG| multiplied by T lands within 6e-11 votes of a half-integer, for all 57,553 rows under both contests. So the CSV keeps full precision, the totals in `TWO_PARTY` are the ones the gaps were computed on, and each row's |wasted D − wasted R| can be recovered exactly.
- With the majority threshold (partisan.py:325-334), the identity is W = 2D − T/2 − N_W + Δ, where N_W is the two-party vote cast in the districts the Democrats win.
- I implemented the reading rule myself in exact fractions. It reproduces every pinned count:
  - Rectangle, presidential: 395 / 13,516 / 13,653 / 0 / 0.
  - Rectangle, Senate: 270 / 11,410 / 15,876 / 8 / 0.
  - All committed rows, presidential: 832 / 28,780 / 27,941 / 0 / 0.
  - Sweep grid offsets: {2.5: 216, 3.5: 179} presidential and {2: 23, 3: 222, 4: 25} Senate.
- Zero refusals over all 57,553 rows under either contest.

---

### Allegation 1: UPHELD

The concluding phrase "rests on the turnout assumption like the others, with more room" (DECISIONS.md:1140-1141, progress.md:2415-2417, plotter:54-56) presents the protection as a matter of distance only. The protection is different in kind.

My reproduction, under the presidential vote:
- **Silent band for 1-seat plans.** A 1-seat plan is read as 2 without complaint for turnout terms from 0.062002 to 0.103337. That band is 0.041335 wide, or 68,481 votes.
- **Exact target for the 0 bar.** With integrality and parity enforced, a non-sweep is read as 0 only if N_W − (4D − T) = N_W − 1,379,511 takes one of these values:
  - {1, 2} at 3 seats;
  - {2, 3, 4} at 2 seats;
  - {3, 4, 5, 6} at 1 seat.
  
  The auditor's ranges ("0 to 6", "1.5 to 4.5", "0 to 3") are correct bounds, but the exact set is 1 to 6. Measured in turnout-term units, the target is at most 1.8e-6 wide per seat count, and 6e-7 at the binding 3-seat case. "About 4e-6" overstates the width, which works against the auditor's own point.
- **Other routes in are impossible.** A non-sweep with a positive gap would need N_W ≤ 0. Reaching the 4-seat grid would need N_W ≥ T.
- **Refusals.** Every |EG| of 0.354333 or more that misses the admissible totals is refused. That covers the 0 window [0.375, 0.5], the band just above the 3-seat margin, and the 4-seat window.
- **Committed data.**
  - The largest non-sweep |EG| is 0.17303 over all rows (0.17244 on the rectangle). So "above 0.1730" is off in the fifth decimal.
  - That draw sits 0.24330 below the 0-seat level, which is 403,086 votes.
  - 194 of the 395 zero draws also sit on the Senate sweep grid. The other 201 read as 1 Senate seat (187 draws) or 2 (14), with residuals of at most 0.00597.
- **Scope slip.** "The only observed 3-seat plans (8 draws, 2 plans), turnout term 0.007" holds on the rectangle (t3 = 0.00696). Over all committed rows, which is the scope the same bullet uses for refusals, there are 14 draws, 6 distinct rows, with t3 from 0.0039 to 0.0088. The conclusion is unchanged.
- **Mitigation.** The diff already says "to within a few votes". What is missing is a conclusion that uses that fact, and any statement that near misses are refused.
- **Refinement.** The plotter also runs the Senate check on the rectangle (plot_seat_distribution.py:425). It would refuse a plan that is 1 seat under both votes with t1 between 0.0620 and 0.0855. So the band that is silent under both contests is 0.0855 to 0.1033, about 29,500 votes. That is still about four orders of magnitude wider than the 0-bar target.

**The proposed fix is accurate in substance, with two precision points:**
- **"One that came near and missed would stop the plotter"** holds for every miss within 0.062 below the target in turnout-term units (about 103,000 votes), and for any miss above it. Failures further below are read silently as 3 instead of stopping the plotter: 1-seat plans with t1 from 0.479 to 0.521, and 2-seat plans with t2 from 0.229 to 0.271. Say "any other plan whose gap lands in the 0-seat window stops the plotter", not "came near".
- **Name the contest and the totals.**

Suggested wording: "So the 0-seat count is a reading too, but a harder one to get wrong than the 1-versus-2 split. Under the presidential vote, a plan that is not a sweep is read as 0 only if the districts the Democrats win cast one of six totals, 1,379,512 to 1,379,517 of 1,656,733. Any other plan whose gap lands in the 0-seat window stops the plotter, and none of the 57,553 committed rows does. A 1-seat plan would be read as 2 anywhere in a band about 68,000 votes wide."

### Allegation 2: UPHELD

- DECISIONS.md:1141 ("only the recount above would verify it") points to :1119-1121 ("A one-time recount of one chain would turn this reading into a verified count").
- The 395 zero draws by chain are 68, 70, 76, 48, 113 and 20 (chains 0, 1, 2, 5, 6, 10). One chain covers at most 113 of them (29%).
- "The recount above" could also be read as the whole bullet, "Recount from plans and returns". Under either reading the one-chain sentence overstates for the pooled count, so the ambiguity should go.
- progress.md:2417 ("a recount") and plotter:56-57 are fine.

**The fix ("recount the draws read as 0; the count can be too high, never too low") needs two qualifications:**
- **"Never too low" is exact only for plans with no exactly tied district.** A plan the Democrats win none of, with one tied district, has `seat_counts` (0, 3, 1) under the repo's own rule (partisan.py:271-277), but it is not a sweep: a tie wastes both sides' votes (partisan.py:333-334). I tested this on Iowa's totals with the repo's `efficiency_gap` (scratch tie.py):
  - with the tied district at equal turnout, |EG| is 0.29139 and the plan is refused;
  - if the tied district casts 12.4% to 20.7% of the vote, the plan is read silently as 3 (|EG| 0.33787, residual +0.0042).
  
  No draw is read as 3 under the presidential vote and nothing is refused, so in these data the count is not too low. The only exception would be a tied district casting 46-54% or 62-71% of all votes. Suggested wording: "every plan the Democrats win none of, with no exactly tied district, is read as 0".
- **"Verify outright" holds in logic, if each regenerated draw reproduces its committed row.** The cost is regeneration:
  - No plans are committed. The pair-cache holds Experiment 2 pair tests, not plans.
  - All six chains must be rerun through draws 4,388, 2,335, 3,779, 3,602, 3,484 and 2,533 (0-based). That is 20,127 of the 27,564 rectangle draws.
  - Recounting the whole rectangle costs about 37% more regeneration and would also verify the 1-versus-2 split.
  - The figure of 97 distinct metric rows is correct, and it is a lower bound on distinct plans.

### Allegation 3: UPHELD, with two corrections to its supporting argument

Reproduced:
- `worst` is updated only on the non-sweep branch (plot_seat_distribution.py:192-212).
- The residual 0.0143 comes from one draw: chain 2, draw 667, |EG| 0.0979699, residual +0.0143047. Read as 1 seat instead, its turnout term would be t1 = 0.06836, inside the silent band.
- Under the Senate vote the same draw reads as 2, with residual 0.015875.
- Among 2-seat reads, 195 residuals lie beyond +0.008 and none beyond −0.008 (the minimum is −0.00756).
- These are 2-seat draws read as 2 under the Senate vote: 161 of the 195 do so, all within 0.00237 of their presidential residuals. The other 34 read as 1 under the Senate.
- Same-seat residuals correlate at r = 0.952 across the two contests.

A further point on selection that the auditor did not make: the margin rule caps every admitted residual at 0.020667. The 1-to-2 edge, 0.062002, is exactly three times that. So "four times the largest" is at least three times by construction, and the data add only a factor of 1.44.

**Correction (a): the one-sided tail does not by itself point to misreading.**
- The 1-seat bucket leans the same way: 8 draws beyond 0.008 toward the 2-seat level, and none on the other side.
- The mean turnout term is positive in both buckets: +0.0011 at 1 seat and +0.0012 at 2. The share of positive terms is 77% and 60%.
- One physical effect, Democratic-won districts casting slightly more than an equal share of the vote, explains both tails.

**Correction (b): "support that does not assume the readings" overstates.**
- **It uses the readings.** Residuals are taken from each contest's read level, and the comparison is restricted to draws read the same in both contests. It also assumes that a district's share of the two-party vote is nearly the same in both races.
- **It is still a real test.** The levels are spaced differently in the two contests, so a 1-seat plan misread as 2 in both would show a Senate residual 0.031346 above its presidential one.
- **No draw shows that signature.** Observed same-seat differences run from −0.0015 to +0.0080 overall, and from −0.0001 to +0.0026 at 2 seats. None comes near ±0.031.
- **The 0.95 correlation does not test misreading.** Correlation ignores a constant offset, so it supports the stable-share assumption, not the readings. The per-draw agreement is the evidence that counts.
- **The 34 tail draws read as 1 under the Senate.** For those to be 1-seat plans in both contests, one district's share of the vote would have to differ by at least 0.064 between the two contests: 0.0719-0.0746 implied by the presidential reading, 0.0058-0.0078 under the Senate.
- **The evidence rests on fewer plans than draws.** The 195 tail draws are 66 distinct metric rows; the 161 are 56 and the 34 are 10.

**On the fix:** "Residual" is accurate. The sentence's force still depends on the readings, and the "three times by construction" point should go beside it. The same circularity sits in the existing, pre-diff text at progress.md:2420-2425 ("turnout term's standard deviation", "thirty-one standard deviations"). The SD framing also implies a thinner tail than the data show: the largest residual is 4.7 SD at 2 seats and 4.8 SD at 1 seat.

### Allegation 4: UPHELD

- The ratio of the two rooms, 0.082669 / 0.062002, is exactly 4/3. After folding, the 3-to-0 gap and the 1-to-2 gap are both 4V − 7/4, which is twice the half-gap (2h). The silent edge sits at 1.5h because MARGIN = 0.5. So "more room" comes from the level geometry and the margin rule; the draws did not measure it.
- No draw is read as 3 under the presidential vote, on the rectangle or over all rows. The diff compares the binding 3-seat room with a yardstick taken from 1- and 2-seat draws (progress.md:2414-2415, plotter:52-54). The only 3-seat evidence comes from the Senate vote: t3 = 0.007 on the rectangle, 0.004 to 0.009 over all rows.
- "Matters more" is a judgment, but the numbers back it: target width versus band width differs by about four orders of magnitude, distance by 1.33 times. Allegation 1's fix covers this one too.

---

### Checked and found sound

- The exact decoding and the identity.
- 4V − 1 = 0.832669. The turnout terms 0.0827, 0.3327 and 0.5827 round to the diff's 0.083, 0.333 and 0.583. "To within a few votes" is right: the admissible offsets are 1 to 6.
- Half-gap 0.041335, margin 0.020667, largest residual 0.014305 (0.346 of the half-gap, "about a third"). 25% + 6.2% gives the diff's "31%".
- Residual SDs of 0.00197 at 1 seat and 0.00303 at 2 match the quoted 0.0020 and 0.0030.
- The diff's constructed 2-seat plan lands on the 3.5-vote grid point, at offset 3. Five grid and margin tests pass. The plotter runs.
- The tree is clean. Nothing was written to the repository, and the figure went to scratch.
- No verdict language appears in the audited lines.

Scripts are in /tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/refute4/: decode.py, analyze.py, allegations.py, more.py, tails.py, tie.py, last.py and grid.py.

AI-assisted review, a partial measure. A redistricting scientist outside the authoring loop should read any claim headed for publication.

---

## Author's response to the fourth audit

The refuter upheld all four allegations, with corrections to the evidence offered
for the first and third, so each is answered by a change in the commit that
follows `35feb62`. Numbers the answers quote are pinned by
`tests/test_seat_distribution.py`, except where they come from the reports above.

| # | Allegation | Refuter | What changed |
| --- | --- | --- | --- |
| 1 | "Like the others, with more room" understates the 0-seat reading in kind | Upheld. The admissible totals are 1 to 6 votes above 4D − T, not 0 to 6, and the refusal holds for any plan whose gap lands nearest the 0-seat level, not for every near miss | D-039, `docs/progress.md` and the plotter say a plan that is not a sweep, and has no exactly tied district, reads as 0 only if the districts the Democrats win cast one of six totals, 1,379,512 to 1,379,517 votes, under the presidential vote. Any other plan whose gap lands nearest the 0-seat level stops the plotter, and none of the 57,553 committed draws does. The count is a reading, but a harder one to get wrong than the 1-versus-2 split, whose silent band is about 68,000 votes wide. The test enumerates the six totals from the wasted-vote identity, and pins the band. |
| 2 | The one-chain recount D-039 pointed to would not verify the 0-seat count | Upheld. "Never too low" holds only for a plan with no exactly tied district | D-039 says a one-chain recount verifies that chain's readings and tests the method on the rest, and that verifying the 0-seat count takes the draws read as 0 in all six chains. D-039 and `docs/progress.md` say that, short of an exactly tied district, a misreading could only add to the count. That sentence sits in the method text, away from the enacted-plan comparison. |
| 3 | The 0.0143 yardstick is a residual measured after the readings it defends | Upheld. The one-sided tail does not by itself point to misreading, and the cross-contest comparison uses the readings too | "Imbalance" is now "residual" where it means one. D-039 and `docs/progress.md` say the residuals are measured from the level each draw was read at, so they cannot show on their own that the readings are right, and that the 1-versus-2 edge of 0.062 is three times the margin by construction and four times the largest residual by measurement. "Thirty-one standard deviations" is gone from `docs/progress.md`. The cross-contest evidence the refuter reproduced is not added to the prose: no test pins it, and it stays in the reports above. |
| 4 | "With more room" measures the smaller of the two differences | Upheld | Answered by 1. The passages no longer rest on the room comparison. |

The routing reviews of `ef1060c` also found that `docs/progress.md` gave
presidential figures right after a sentence about the Senate vote; that the
plotter's general statement of the collision condition holds only while `V` is
below ½; that the bold lead "Sweeps are exact, to the half vote" and the phrase
"zero-seat draws" assumed the draws were sweeps; that the test did not assert its
own plan's 2 seats; and that D-039's review note misstated its own history.

**After the routing reviews.** The `Code Reviewer`, the `Computational
Redistricting Scientist`, the `Pre-Submission Peer Reviewer` and the `Technical
Writer`, reading `5c2a650`, found that its answers needed these corrections, made
in the commit after it:

- A tied district is another way onto the 0-seat grid: with one, it is the votes
  cast where the Democrats win plus half the tied district's that must hit the
  six totals. The six-totals sentence and the bullet's opening now say "with no
  exactly tied district".
- The prose now says what row 3 says it does: the 0.062 edge is three times the
  margin by construction, and four times the largest residual by measurement. It
  also says that the silent band runs both ways, so that a 2-seat plan in it
  would be read as 1.
- The README said the script checks each difference from PlanScore's published
  values against the turnout term. It checks the difference from PlanScore's
  formula before rounding: against the published four-place values the identity
  misses by 32 to 109 votes on Colorado, against a tolerance of 8. The paragraph is
  now a list of what each check compares, with its tolerance.
- The script's docstring now lists every refusal, including a file that repeats a
  district number, which the script now refuses.
- The plotter's printed summary says "draws read as sweeps" and "residual SD by
  seats read", where it said "sweeps" and "turnout-term SD". No number moved.
- D-039 gives the recount's cost: rerunning each chain to its last draw read as 0
  is 20,127 of the 27,564 draws, and the whole rectangle is 37% more.
- The test probes `recover_seats` itself at the edges of the 1-versus-2 band,
  where it had checked only the arithmetic on the margin.
