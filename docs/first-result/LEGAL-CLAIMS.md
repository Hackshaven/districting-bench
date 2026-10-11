# Legal claims — the first result and D-041

The `Election Law Analyst`'s claim register for the sentences about Iowa law in the
README's "First result", `docs/progress.md` ("The enacted plan's caveats, now with
numbers") and D-041, as of 2026-10-11. It was asked three questions the routing
reviewers raised: whether Iowa Code §42.4(4) prescribes tests for comparing
compactness, whether the enacted plan's 94-person spread is a legal requirement,
and whether plans like the reference draws could be lawful.

The register is verbatim. It is not legal advice, its author is not a lawyer, and
it has not yet been read by the election-law reader that `CLAUDE.md` ("When a
person decides") requires for a new or changed legal sentence. Every item it marks
ATTORNEY is open.

The commit after `3199ae7` revised the reviewed sentences with its suggested
wording W1 to W4. W5 concerns `docs/CRITERIA.md` §2.1, which only the owner
amends, and the items it lists under "Related text outside the named scope" are
not changed here; both are left to the owner.

---

## Election law review: Iowa sentences in D-041, progress.md and the README (commit 3199ae7)

**Verdict: NEEDS CHANGES, with ATTORNEY items.** None of the Iowa text is stale. By search (not by a citator), nothing enacted or decided since 2012 changes §42.4, and nothing since *Tennant* (2012) changes the federal standard. The problems are in how the texts are described:
- The sentences treat the enacted plan's 94-person spread as a requirement. It is the level that plan reached.
- They call the choice of compactness measure open, but Iowa's statute names the tests to use when comparing districts or plans.
- CRITERIA.md §2.1 gets the statute's order wrong and leaves out the provisions these three questions turn on.

**Scope:** D-041 ([D]:1215–1273), progress.md "The enacted plan's caveats, now with numbers" ([P]:2430–2510), the README's Iowa paragraph ([R]:52–66), and CRITERIA.md §2.1 ([C]:107–122). I found 18 legal statements; they are in the register below.

**Checked:** 2026-10-11. Subsequent history was checked by search, not by a citator.

**I could not read the commit itself.** I have no shell here, so `git show 3199ae7:<path>` couldn't run. I read the worktree instead. Its HEAD is branch `claude/round2-fixes` at 3199ae758cbe3d93da4bfdaec14a5e9e7c17fd54 (per `/home/user/districting-bench/.git/refs/heads/claude/round2-fixes`). Fetching that SHA from GitHub returned 404.
- I can't rule out uncommitted edits, so the line numbers below are working-tree line numbers.
- Every sentence you quoted matches the lines I read.
- I read no commit messages, COMMIT_EDITMSG or reflogs, and I edited nothing.

**Paths.** All under `/tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/wt-fix/`:
- [D] `/tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/wt-fix/docs/DECISIONS.md`
- [P] `/tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/wt-fix/docs/progress.md`
- [R] `/tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/wt-fix/README.md`
- [C] `/tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/wt-fix/docs/CRITERIA.md`
- [F] `/tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/wt-fix/docs/FEASIBILITY.md`
- [A] `/tmp/claude-0/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/scratchpad/wt-fix/docs/ARCHITECTURE.md`

### Primary sources, all read 2026-10-11
- **Iowa Code §42.4**, PDF footer "Iowa Code 2026, Section 42.4 (26, 0)", generated 2025-12-10. Its source note ends "2012 Acts, ch 1021, §36, 141, 143". https://www.legis.iowa.gov/docs/code/42.4.pdf
- **Iowa Code §40.1** (Iowa Code 2026): the enacted map, county by county. Source note "2021 Acts, 2nd Ex, ch 2, §1, 6", annotated "Constitutional provision, Iowa Constitution, Art. III, §37". Its county lists match [F]:216–221. https://www.legis.iowa.gov/docs/code/2026/40.1.pdf
- **Iowa Const. art. III, §§34–37**, the codified edition (its annotations run to Amendment 51 (2024)). §37 is marked "Repealed and rewritten by Amendment 26 (1968)". https://www.legis.iowa.gov/docs/publications/ICP/1518288.pdf
- **Iowa Legislature, "Code & Acts Sections Amended – 2026 Report"** (provisional). Its ascending list goes from 39A.8 straight to 43.111, so no 2026 Act touches chapter 40 or 42. The official version is to appear in the 2026 Iowa Acts. https://www.legis.iowa.gov/law/statutory/acts/amended?year=2026
- ***Karcher v. Daggett*, 462 U.S. 725 (1983)**, No. 81-2057, decided June 22, 1983. Brennan, J., wrote for the Court, joined by Marshall, Blackmun, Stevens and O'Connor, JJ. Stevens, J., concurred. White, J., dissented, joined by Burger, C.J., and Powell and Rehnquist, JJ. Powell, J., also dissented. I read pages 725–734 and 738–744. https://tile.loc.gov/storage-services/service/ll/usrep/usrep462/usrep462725/usrep462725.pdf
- ***Tennant v. Jefferson County Comm'n*, 567 U.S. 758 (2012)** (per curiam), No. 11-1184, decided Sept. 25, 2012. I read pages 758–765. https://www.govinfo.gov/content/pkg/USREPORTS-567/pdf/USREPORTS-567-758.pdf
- **Iowa Legislative Services Agency (LSA), "Second Redistricting Plan" report, Oct. 21, 2021**, pp. 1–8 and Table 1. This is an agency document: it shows how the State's drafter worked and read the law, not what a court held. https://www.legis.iowa.gov/docs/publications/REDST/2021/Updates/Plan2_Report.pdf
- **Secondary, for orientation only:** https://redistricting.lls.edu/state/iowa/ and web searches. The CRS report R44798 returned 403.
- **Local copies** in `/root/.claude/projects/-home-user-districting-bench/c90a28a9-74fd-5bae-b74a-5033b5ec6055/tool-results/`:
  - `webfetch-1791699384657-w02pku.pdf` (§42.4)
  - `webfetch-1791699447086-q10k0v.pdf` (§40.1)
  - `webfetch-1791699521107-r63mtb.pdf` (Constitution)
  - `webfetch-1791699433822-g1pjm3.pdf` (*Karcher*)
  - `webfetch-1791699749090-8b6fed.pdf` (*Tennant*)
  - `webfetch-1791699747747-lxejcr.pdf` (LSA report)

### Q1. Does §42.4(4) prescribe the tests? Yes.

Iowa Code §42.4(4), Iowa Code 2026:
> "Districts shall be reasonably compact in form, to the extent consistent with the standards established by subsections 1, 2, and 3. In general, reasonably compact districts are those which are square, rectangular, or hexagonal in shape, and not irregularly shaped, to the extent permitted by natural or political boundaries. If it is necessary to compare the relative compactness of two or more districts, or of two or more alternative districting plans, the tests prescribed by paragraphs “a” and “b” shall be used.
> a. Length-width compactness. The compactness of a district is greatest when the length of the district and the width of the district are equal. The measure of a district’s compactness is the absolute value of the difference between the length and the width of the district. In general, the length-width compactness of a district is calculated by measuring the distance from the northernmost point or portion of the boundary of a district to the southernmost point or portion of the boundary of the same district and the distance from the westernmost point or portion of the boundary of the district to the easternmost point or portion of the boundary of the same district. The absolute values computed for individual districts under this paragraph may be cumulated for all districts in a plan in order to compare the overall compactness of two or more alternative districting plans for the state, or for a portion of the state.
> b. Perimeter compactness. The compactness of a district is greatest when the distance needed to traverse the perimeter boundary of a district is as short as possible. The total perimeter distance computed for individual districts under this paragraph may be cumulated for all districts in a plan in order to compare the overall compactness of two or more alternative districting plans for the state, or for a portion of the state."

**What the text settles.**
- When the compactness of districts or of alternative plans is compared, the tests are length-width and perimeter compactness ("shall be used").
- Plan-level comparisons sum the district values ("may be cumulated").
- The State's drafter reads it the same way. LSA report, p. 6: "The Legislative Services Agency further notes that the statute specifies that if it is necessary to compare the relative compactness of two or more districts or alternative districting plans, the length-width compactness and perimeter compactness tests shall be used."
- The enacted plan's values on those tests are on the official record. LSA Table 1 gives it a "Total Perimeter Score: 2,931.87 miles" and an "Average Length-Width Compactness: 31.03 miles".

**What the text leaves open.**
- How to rank or combine the two tests when they disagree.
- Comparisons made outside drawing plans under §42.4, such as a research benchmark. Nothing in the text forbids reporting other measures alongside.
- I found no Iowa decision applying §42.4(4).

**How it bears on the repository's framing.**
- Neither measure the draws carry is a §42.4(4) test, by name or by definition. Cut edges counts county adjacencies, and Polsby-Popper is 4πA/P² ([C]:157). Whether either tracks a statutory test on Iowa's county map is a technical question for the Computational Redistricting Scientist.
- "on which measure, is open" ([R]:61–62) and "on which compactness measure, is a value choice" ([P]:2500–2501) leave out that the statute names the measures for comparing districts or plans. Both are OVERSTATED.
- D-041's narrower wording, "is a judgment `docs/CRITERIA.md` does not settle" ([D]:1266–1268), is true as written. §2.1 never mentions the tests, and §3 classes compactness `VALUE` throughout ([C]:152). The gap is in CRITERIA.md.
- The committed draws carry neither statutory measure, and their plans aren't committed ([P]:2455–2457). So a comparison on the statutory tests can't be computed from them.
- Whether the benchmark adopts the statutory tests is a design decision, not a legal question.
- Even under the statute, a disagreement between its two tests is left unresolved. That is the same situation as the cut-edges versus Polsby-Popper disagreement.
- **ATTORNEY:** whether a court reviewing an Iowa plan would treat these tests as the only ones, and how it would resolve a disagreement between them.

### Q2. §42.4(1) sets a standard, not a person count. 94 is the level the enacted plan reached.

Iowa Code §42.4(1), Iowa Code 2026:
> "Legislative and congressional districts shall be established on the basis of population."
>
> "b. Congressional districts shall each have a population as nearly equal as practicable to the ideal district population, derived as prescribed in paragraph “a” of this subsection. No congressional district shall have a population which varies by more than one percent from the applicable ideal district population, except as necessary to comply with Article III, section 37 of the Constitution of the State of Iowa."
>
> "c. If a challenge is filed with the supreme court alleging excessive population variance among districts established in a plan adopted by the general assembly, the general assembly has the burden of justifying any variance in excess of one percent between the population of a district and the applicable ideal district population."

Iowa Const. art. III, §37:
> "When a congressional district is composed of two or more counties it shall not be entirely separated by a county belonging to another district and no county shall be divided in forming a congressional district."

Federal law (U.S. Const. art. I, §2):
- *Karcher*, 462 U.S. at 730, quoting *Kirkpatrick v. Preisler*, 394 U.S. 526, 531 (1969): art. I, §2 "permits only the limited population variances which are unavoidable despite a good-faith effort to achieve absolute equality, or for which justification is shown."
- *Id.* at 731, quoting *Kirkpatrick*, 394 U.S. at 530: "The whole thrust of the 'as nearly as practicable' approach is inconsistent with adoption of fixed numerical standards which excuse population variances without regard to the circumstances of each particular case."
- *Id.* at 734: "We thus reaffirm that there are no de minimis population variations, which could practicably be avoided, but which nonetheless meet the standard of Art. I, § 2, without justification."
- *Tennant*, 567 U.S. at 759: the standard "does not require that congressional districts be drawn with 'precise mathematical equality,' but instead that the State justify population differences between districts that could have been avoided by 'a good-faith effort to achieve absolute equality.'"

**What follows from the texts.**
- **No person count.** Neither the statute nor *Karcher* or *Tennant* states one. The only number in §42.4(1)(b) is the one-percent cap per district, about 7,976 persons at Iowa's ideal of 797,592.
- **94 belongs to the enacted plan.** It is the "Overall Range" the LSA reported for that plan (Table 1: absolute 94, or 0.012%). Nothing in §42.4, art. III §37, *Karcher* or *Tennant* makes it a requirement for any other plan.
- **The LSA's own reading.** The report says federal law requires that "a second proposed congressional redistricting plan must have equal or lower population deviations than the first plan submitted" (p. 7). That is the agency's view about its successive plans, not a holding I traced, and it sets no level for anyone else. The LSA also reads population equality as "the most important factor", given "greater weight by Iowa Code section 42.4 than compactness" (p. 7). That is consistent with D-041's ranking.
- **"matches on a constraint" is only partly accurate.**
  - Population equality is a constraint. It is mandatory under §42.4(1)(b) and art. I, §2, and it comes first in §42.4.
  - But the sentence says "matching the reference to it", and the nearest antecedent of "it" is "the enacted plan's level of it". So the sentence reads as if the 94-person level were the constraint.
  - The texts set a practicability standard and, in the statute, a one-percent cap. The draws, at ±0.02% per district, sit inside that cap.
  - Matching the reference to 94 matches it on the enacted plan's achieved level of a mandatory, first-ranked standard, not on a legal threshold. Status: OVERSTATED.
  - If the sentence means the sampler's sense (ε is an input constraint, compactness an output), it doesn't need the legal premise.
- **ATTORNEY:** whether 94, or any other spread, meets "as nearly equal as practicable". *Karcher* at 741 says this "requires case-by-case attention" to the factors. Nothing here says whether the enacted plan's spread is lawful or not.
- **Office.** All of this is the congressional standard. §42.4(1)(a) sets different numbers for state legislative districts (mean deviation at most 1%; no district more than 5% larger than another of its kind), and nothing here carries over to them.

### Q3. Could plans at ±0.02% per district (spread up to about 319, median 225) be lawful? Their size doesn't decide it. ATTORNEY.

**Under the Iowa statute.**
- Each such district is inside §42.4(1)(b)'s one-percent cap: about 159 persons, against about 7,976.
- §42.4(1)(c)'s burden rule applies only to variance "in excess of one percent".
- That much is arithmetic on the text. Whether such a plan is "as nearly equal as practicable" is ATTORNEY. I found no Iowa decision applying the phrase to congressional districts.
- Population isn't the only standard. Contiguity (§42.4(3)), compactness on the statutory tests (§42.4(4), not measured for the draws), purpose and data (§42.4(5)), and art. III §37 all apply.
- The repository says its draws are whole-county, rook-contiguous, and generated without partisan or racial data ([A]:65–66; [R]:127–130). I did not verify that; it is the Blinding & Leakage Auditor's area.

**Under federal law.**
- **Size alone doesn't decide.** There is no de minimis safe harbor for variances that could practicably be avoided (*Karcher* at 734).
- **First step: avoidability.** Challengers must show the differences "could practicably be avoided" (*Tennant* at 760, quoting *Karcher* at 734).
  - The repository's own record reports whole-county plans at 94 persons (the enacted plan), 70, and 23 ([F]:223, :357–361, :288–290).
  - But *Karcher* at 740 n.10 says the Court did not "indicate that a plan cannot represent a good-faith effort whenever a court can conceive of minor improvements."
- **Second step: justification.** If the first step is met, the State must "show with some specificity that a particular objective required the specific deviations in its plan" (*Karcher* at 741). The test weighs "the size of the deviations, the importance of the State's interests, the consistency with which the plan as a whole reflects those interests, and the availability of alternatives that might substantially vindicate those interests yet approximate population equality more closely" (*id.*).
- **Objectives the Court has recognized.** *Karcher* at 740 lists "making districts compact, respecting municipal boundaries, preserving the cores of prior districts, and avoiding contests between incumbent Representatives". *Tennant* at 764: "avoiding contests between incumbents and not splitting political subdivisions are valid, neutral state districting policies".
- **Whole counties.** The two opinions say different things, and both apply.
  - *Tennant* at 764: "if a State wishes to maintain whole counties, it will inevitably have population variations between districts reflecting the fact that its districts are composed of unevenly populated counties".
  - *Karcher* at 733 n.5: preserving political subdivisions "is not a sufficient excuse for failing to achieve population equality without the specific showing described infra, at 740–741."
- **Scale, for context only.** *Karcher* struck New Jersey's unjustified 0.6984% (3,674 persons; 462 U.S. at 728). *Tennant* upheld West Virginia's justified 0.79% (567 U.S. at 761, 765), adding: "This is not to say that anytime a State must choose between serving an additional legitimate objective and achieving a lower variance, it may choose the former." The draws reach about 0.040% of ideal (median 0.028%); the enacted plan is at 0.012%.
- **Nothing for the second step to weigh.** The draws are sampler output at a tolerance chosen for the sampler ([F] §5). They are not plans a State adopted with stated objectives.
- **ATTORNEY:** whether whole-county Iowa plans at 225–319 persons would be lawful under art. I, §2 and §42.4(1)(b). Also, how §42.4(4)'s ranking of compactness below population would bear on *Karcher*'s "consistency" factor if compactness were offered as the justification.

### Claim register (as of 2026-10-11 for every row)

| # | Claim (quoted) | Where | Kind | Primary source checked | Status → category |
|---|---|---|---|---|---|
| 1 | "the draws are not held to the enacted plan's 94-person population spread" | [D]:1221–1222 | characterization | LSA Table 1 | SUPPORTED → supported |
| 2 | "population equality is the first of Iowa's ordered criteria (`CRITERIA.md` §2.1)" | [D]:1236–1237 | state statute | §42.4(1), (2), (4) | SUPPORTED → needs change: cite §42.4 (Iowa Code 2026) rather than CRITERIA.md, and add the art. III §37 exception for congressional districts (W1) |
| 3 | "the draws do not meet the enacted plan's level of it, so matching the reference to it matches on a constraint" | [D]:1237–1238 | characterization of state and federal law | §42.4(1)(b); *Karcher* at 730–731, 734; LSA Table 1 | OVERSTATED → needs change (W1). Whether any spread meets the standard: ATTORNEY |
| 4 | "Compactness is the fourth" | [D]:1239 | state statute | §42.4(4) | SUPPORTED → needs a citation (W1) |
| 5 | "Which measure to match on is a further choice, since the draws are more compact than the plan on cut edges and not on Polsby-Popper." | [D]:1246–1248 | characterization | §42.4(4)(a)–(b) | OVERSTATED (leaves out the statutory tests) → needs change (W4) |
| 6 | "…and on which compactness measure, is a judgment `docs/CRITERIA.md` does not settle" | [D]:1266–1268 | characterization | CRITERIA.md §2.1 and §3, against §42.4(4) | SUPPORTED as written → supported. The gap is row 16 |
| 7 | "the reference is not held to the enacted plan's 94-person max–min spread" | [P]:2432–2433 | characterization | LSA Table 1 | SUPPORTED → supported |
| 8 | "Population equality is the first of Iowa's ordered criteria (`CRITERIA.md` §2.1)" | [P]:2480–2481 | state statute | as row 2 | SUPPORTED → needs a citation (W1) |
| 9 | "the draws do not meet the enacted plan's level of it, so matching the reference to it matches on a constraint" | [P]:2481–2483 | as row 3 | as row 3 | OVERSTATED → needs change (W1). ATTORNEY as in row 3 |
| 10 | "Compactness is the fourth" | [P]:2483 | state statute | §42.4(4) | SUPPORTED → needs a citation |
| 11 | "Whether, and on what, to condition, and on which compactness measure, is a value choice for the owner (D-041)." | [P]:2500–2501 | characterization | §42.4(4) | OVERSTATED (the measure clause) → needs change (W3) |
| 12 | "the draws are not held to the 94-person population equality the enacted plan meets" | [R]:54–55 | characterization | §42.4(1)(b); *Karcher* at 731, 734; LSA Table 1 | OVERSTATED: "meets" reads 94 as a standard → needs change (W2) |
| 13 | "Whether to match the comparison on compactness, and on which measure, is open." | [R]:61–62 | characterization | §42.4(4) | OVERSTATED (the measure clause) → needs change (W3) |
| 14 | "`STATE`. Iowa Code Chapter 42." and Sources "Iowa Code Chapter 42 (ordered redistricting criteria, whole-county districts)" | [C]:109, [C]:476 | source attribution | art. III §37; §§40.1, 42.4 | OVERSTATED: incomplete and undated → needs change (W5, owner) |
| 15 | "Congressional districts are composed of whole counties." | [C]:109–110 | state constitution | art. III §37; §40.1 | SUPPORTED → needs a citation to art. III §37 (W5) |
| 16 | "Criteria are explicitly ordered: 1. Population equality 2. Contiguity 3. Political subdivision integrity (whole counties) 4. Compactness" | [C]:110–115 | state statute | §42.4(1)–(4) | WRONG on items 2 and 3; OVERSTATED ("explicitly") for contiguity → needs change (W5, owner) |
| 17 | "And Iowa **explicitly forbids** considering political affiliation, prior election results, incumbent addresses, or demographic data other than population." | [C]:117–118 | state statute | §42.4(5) | OVERSTATED: leaves out "except as required by the Constitution and the laws of the United States" and the purpose clause → needs change (W5, owner) |
| 18 | "a statutory criteria ordering that removes our discretion entirely" | [C]:120–121 | characterization | §42.4(3), (4) | OVERSTATED: the statute gives contiguity no rank and leaves its two compactness tests unranked, yet it names the measure that §3 treats as open → needs change (owner) |

### Suggested wording
- **W1** (for [D]:1236–1239 and [P]:2480–2483): "Population equality ranks first in Iowa Code §42.4 (Iowa Code 2026) and compactness fourth, 'to the extent consistent with the standards established by subsections 1, 2, and 3.' For congressional districts the statute and *Karcher v. Daggett*, 462 U.S. 725 (1983), set a standard ('as nearly equal as practicable', with the statute's one-percent cap yielding to Iowa Const. art. III, §37), not a person count. 94 persons is the spread the enacted plan reached (LSA, Plan 2 Report, Table 1, Oct. 21, 2021). Matching the reference to it matches on the enacted plan's achieved level of the first-ranked standard, not on a legal threshold."
- **W2** (for [R]:54–55): "the draws are not held to the enacted plan's 94-person population spread". This mirrors rows 1 and 7.
- **W3** (for [R]:61–62 and [P]:2500–2501): "Whether to match the comparison on compactness is open. Iowa Code §42.4(4) (Iowa Code 2026) names the tests for comparing the compactness of districts or plans, length-width and perimeter compactness. The draws carry neither, and the statute does not say how to weigh its two tests when they disagree."
- **W4** (for [D]:1246–1248): "Which measure to match on is a further question. Iowa Code §42.4(4) names length-width and perimeter compactness for comparing plans, and the draws carry neither. Of the two measures they do carry, the draws are more compact than the plan on cut edges and not on Polsby-Popper."
- **W5** (for [C] §2.1; only the owner amends CRITERIA.md): "`STATE`, as of Iowa Code 2026 (§42.4 last amended 2012) and Iowa Const. art. III, §37 (Amendment 26, 1968); checked 2026-10-11. Congressional districts: 'no county shall be divided in forming a congressional district,' and a multi-county district 'shall not be entirely separated by a county belonging to another district' (art. III, §37; the enacted map is Iowa Code §40.1). Iowa Code §42.4, in its own order: (1) population 'as nearly equal as practicable', with no congressional district more than one percent from ideal 'except as necessary to comply with Article III, section 37'; (2) political subdivisions, 'To the extent consistent with subsection 1'; (3) 'convenient contiguous territory', with no stated rank; (4) 'reasonably compact', 'to the extent consistent with the standards established by subsections 1, 2, and 3', compared by the length-width and perimeter tests in §42.4(4)(a)–(b); (5) no district 'drawn for the purpose of favoring a political party, incumbent legislator or member of Congress, or other person or group', and no use of incumbents' addresses, voters' political affiliations, previous election results, or 'Demographic information, other than population head counts, except as required by the Constitution and the laws of the United States.'"

### CRITERIA.md §2.1 against the current texts
- **Date.** §2.1 states none, and its Sources line ([C]:476) names no edition. So "since the date it states" can't be measured; I checked it against the current texts instead.
- **Changes since then.** I found none.
  - §42.4 was last amended in 2012; art. III §37 was last rewritten in 1968.
  - The 2026 provisional report lists no section in chapter 40 or 42. §40.1 still holds the 2021 map.
  - Searches found no Iowa mid-decade map and no Iowa decision on the 2021 plans. The Loyola page is secondary and was last updated 2021–22; it says neither plan appears to have been challenged and lists only the Iowa Supreme Court's deadline order of Sept. 14, 2021 (No. 21-1281), which LSA report p. 5 also describes.
  - I found no Supreme Court decision on congressional population equality after *Tennant*.
  - All of this was checked by search, not by a citator. An extraordinary session listed outside the 2026 report would not be covered.
- **Order is wrong.** §42.4 numbers political subdivisions as subsection 2 ("To the extent consistent with subsection 1") and contiguity as subsection 3, which has no qualifier. §2.1 swaps them. The statute's ordering language only places subdivisions below population and compactness below subsections 1–3; it gives contiguity no rank.
- **Whole counties for congressional districts.** The rule is constitutional, and §42.4(1)(b)'s one-percent cap yields to it. It isn't simply third in line.
- **Source.** The whole-county rule comes from art. III §37, not chapter 42. §2.1 also drops §37's "entirely separated" clause.
- **Data rule.** §2.1 drops §42.4(5)(d)'s exception for federal law and the purpose prohibition in §42.4(5)'s first sentence.
- **Omissions that matter for this review:** §42.4(1)(b)'s standard and cap, §42.4(1)(c)'s burden rule, and §42.4(4)'s two tests.

### Implied legal conclusions
- **[R]:55, "the 94-person population equality the enacted plan meets".** This can read as saying the enacted plan meets the legal standard. That is a lawfulness claim the work can't support (ATTORNEY). W2 removes it.
- **"matches on a constraint" ([D]:1237–1238; [P]:2481–2483).** This can read as saying the draws fall short of a legal requirement, which is also unsupported (see Q3). W1 removes it.
- **No remedy is implied.** No reviewed sentence implies a claim against the enacted plan. "Not yet a finding" ([R]:54; [P]:2503) and the status line ([R]:9–10) stand.

### Remedy map: Iowa, congressional office, as of 2026-10-11

| Claim | Law | Forum | Who may bring it | What it requires | Does this work supply it? | Status |
|---|---|---|---|---|---|---|
| Population inequality | U.S. Const. art. I, §2 | Federal court. *Karcher* was heard by a three-judge court convened under 28 U.S.C. §2284(a) (462 U.S. at 729) | Not checked: ATTORNEY | Step 1: differences could practicably be avoided (*Karcher* at 730–731, 734). Step 2: the State's specific, flexible justification (740–741; *Tennant* at 760, 765) | No. The status line says "Do not use for litigation". Its tighter whole-county plans ([F] §5) are arithmetic; whether they bear on step 1, given 740 n.10, is ATTORNEY. It offers nothing on step 2 | *Karcher* (1983) and *Tennant* (2012) control. No later Supreme Court decision and no challenge to Iowa's 2021 plan found by search |
| Population variance | Iowa Code §42.4(1)(b)–(c) | Art. III §36 gives the Iowa Supreme Court "original jurisdiction of all litigation questioning the apportionment of the general assembly or any apportionment plan adopted by the general assembly". Whether that reaches a congressional plan: ATTORNEY | Art. III §36: "Upon verified application by any qualified elector". Scope: ATTORNEY | "as nearly equal as practicable"; at most 1% per district except as art. III §37 requires; the General Assembly's burden above 1% | No | Iowa Code 2026 |
| Compactness | §42.4(4) | As above | As above | Districts "reasonably compact", ranked below subsections 1–3; comparisons by the two statutory tests | No: the draws carry neither test | Iowa Code 2026 |
| Prohibited purpose or data | §42.4(5) | ATTORNEY | ATTORNEY | Drawing for a listed purpose, or using the listed data | Whether a seat-outcome comparison bears on purpose: ATTORNEY | Iowa case law on §42.4(5) not checked |

### For an attorney
1. Would whole-county Iowa congressional plans with spreads of 225–319 persons satisfy art. I, §2 and §42.4(1)(b), given that whole-county plans at 94 persons or fewer exist? How does *Karcher* at 740 n.10 bear on that?
2. Do Iowa courts read §42.4(1)(b)'s "as nearly equal as practicable" as the federal standard? How does §42.4(1)(c)'s one-percent burden rule sit beside *Karcher*'s holding that no avoidable variance is de minimis?
3. If compactness were offered as a justification, how would §42.4(4)'s ranking of it below population, and art. III §37's whole-county rule, bear on *Karcher*'s "consistency" and "alternatives" factors?
4. Are §42.4(4)'s two tests the only ones a court would use in reviewing an Iowa plan? How is a disagreement between them resolved?
5. Does art. III §36 reach congressional plans? What are the forum and standing for a §42.4 claim against one?
6. If art. III §37's whole-county rule and art. I, §2 ever diverge in Iowa, which controls?

### Related text outside the named scope (pointers only; each needs its own pass)
- **[C]:80, the §1 row.** "any deviation must be justified … In practice single-digit persons." *Karcher* requires justification only for variances not shown to be "unavoidable despite a good-faith effort" (at 730). "Single-digit persons" appears nowhere in *Karcher*; Iowa's enacted plan is at 94, and *Tennant* upheld 0.79%. Status: OVERSTATED / UNSOURCED.
- **[D]:794–798 (D-030); [P]:1515–1517, :1605–1609, :1670–1673.** These treat *Karcher*'s 0.6984% as "that line" or "the legal boundary", and treat lower tolerances as ones "a congressional plan could lawfully occupy". *Karcher* set no line (at 731, 734), and *Tennant* upheld 0.79% (at 765). Status: WRONG as statements of what *Karcher* held. D-030 is merged, so under CLAUDE.md a correction would be a new entry.
- **"Karcher-tight" ([P]:379, :404; [D]:374–377).** This uses a case name as if it set a tolerance. *Karcher* states none.
- **[F]:293, :321, :399, :404.** These call the 94-person spread "the legal standard" or "the enacted standard": the same issue as Q2.
- **[A]:65–66, [F]:239–240, [P]:979.** These attribute the whole-county rule to chapter 42; its source is art. III §37.
- **[R]:281–283.** Repeats "removes our discretion" (row 18).
- **docs/experiment-1/INSTRUMENT-AUDIT.md:22, :202.** Same "line" reading. These are verbatim audit records, so I note them only.

### Handoffs
- **Computational Redistricting Scientist:** whether cut edges or mean Polsby-Popper track §42.4(4)'s tests on the 99-county map, and whether LSA Table 1's values can be reproduced from the repository's geometry.
- **Science Communicator:** the README wording at [R]:54–55 and :61–62.
- **The election-law reader (a person):** every ATTORNEY item and this register.

This review describes the law as of 2026-10-11. It is not legal advice, and the reviewer is not a lawyer. Anyone deciding whether or how to act on a map should consult an election-law attorney.
