# Attribution — `ia-seats-v2.csv.gz`

The seat counts in `ia-seats-v2.csv.gz`, in this directory, are made from:

> Voting and Election Science Team, 2020, "2020 Precinct-Level Election Results",
> <https://doi.org/10.7910/DVN/K7760H>, Harvard Dataverse, V49 (file `ia_2020.zip`,
> Iowa).

The DOI resolves to the dataset's latest version. Version 49, the one the counts
were made from, is at
<https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/K7760H&version=49.0>.

VEST licenses that dataset under the Creative Commons Attribution 4.0
International licence (CC BY 4.0): <https://creativecommons.org/licenses/by/4.0/>.
VEST states the licence in the dataset's Terms of Use on Dataverse and at the end
of its documentation file, `documentation.txt` (Dataverse file id 14304792 in
version 49). Two places do not name it: the dataset's own licence field on
Dataverse is empty, and DataCite lists its rights as "Custom terms specific to
this dataset". All four were read on 2026-10-12.

**What the counts describe.** The file describes districting plans for Iowa drawn
by computer, not real districts, and its counts are not real election results.
Each plan splits Iowa's 99 counties into 4 congressional districts of near-equal
population. A ReCom Markov-chain sampler drew them without seeing any election
data: they are Experiment 2's v2 ensemble (`docs/experiment-2/`). A *chain* is
one run of the sampler from its own seed, and a *draw* is one plan in that run.
For each draw, the file counts how many of its districts the Democratic candidate
would have carried in 2020. Numbers such as D-043 are entries in
`docs/DECISIONS.md`, in this repository.

**What was changed.** The file holds no vote count from the dataset.
`tools/prepare_data.py` summed Iowa's precinct returns to its 99 counties, and
`tools/recount_seats.py` counted, for each committed draw of the v2 ensemble, how
many districts the Democratic candidate would have carried under the 2020
presidential vote and under the 2020 U.S. Senate vote (D-043). Beside each draw's
two counts the file holds a key for its plan, which comes from the plan alone,
not from the returns. The record beside it, `ia-seats-v2.json`, names the
dataset, version and file the counts were made from, with their hashes, and
carries the same credit and licence link. How VEST built the Iowa file from its
sources (the Iowa Secretary of State, county governments and the Census Bureau),
and which precincts it merged, is in the Iowa section of `documentation.txt`.

**The file's columns.** The file is gzip-compressed CSV: ASCII text, comma
separated, with a header row and CRLF line ends. It holds one row for each of the
57,553 committed draws, in the order of `docs/experiment-2/ia-draws-v2.csv.gz`,
and no cell is empty. The README's first result and its figure use 27,564 of
these rows: chains 0, 1, 2, 5, 6 and 10, each cut to its first 4,594 draws
(D-035). Shares taken over every row differ from the figure's.

| Column | What it holds |
| --- | --- |
| `chain_index` | An integer: the draw's chain, numbered as in the draws file. Chains 4 and 7 have no rows: both failed before their first draw (`docs/experiment-2/ia-draws-v2-chains.json`). |
| `draw` | An integer: the draw's place in its chain, counting from 0. The row with the same chain and draw in the draws file is the same draw. Successive draws often repeat a plan: the 57,553 rows hold 5,588 distinct keys. |
| `plan` | 16 lowercase hexadecimal digits: a key for the draw's plan that does not change if the districts are renumbered (see *The plan key*, below). Draws with the same key drew the same plan. |
| `dem_seats@G20PRE` | An integer from 0 to 4: how many of the plan's 4 districts gave Biden (VEST's column `G20PREDBID`) more votes than Trump (`G20PRERTRU`), with VEST's 2020 returns summed to counties and then to districts. `G20PRE` is the prefix VEST's column labels share for the 2020 general election for President. |
| `dem_seats@G20USS` | The same for the 2020 U.S. Senate race: Greenfield (`G20USSDGRE`) against Ernst (`G20USSRERN`). |

No district is tied in any draw: the recount writes nothing if one is.

**The plan key.** Write each district as its counties' five-digit GEOIDs, sorted
and joined by commas. Order the districts by their first GEOID and join them with
a vertical bar (|). Hash that text with SHA-256 and keep the first 16 hexadecimal
digits (`plan_key` in `tools/recount_seats.py`).

**No warranty.** VEST's dataset carries this disclaimer, in the Disclaimer field
of its record on Dataverse: "THE DATA ARE PROVIDED “AS IS” WITHOUT WARRANTY OF
ANY KIND. WE MAKE NO AND DISCLAIM ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING
THE IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT, WITH RESPECT TO THESE DATA. WE MAKE NO REPRESENTATIONS OR
WARRANTIES AS TO THE QUALITY, SUITABILITY OR ADEQUACY OF THESE DATA FOR ANY
PURPOSE OR USE." Its documentation file carries it too, punctuated differently.
CC BY 4.0 has its own disclaimer of warranties, in its Section 5.

The figure drawn from those 27,564 rows,
`docs/figures/ia-neutral-seat-distribution.png`, credits VEST, the version
counted, the dataset's DOI and the licence and its link in its footer. This
repository's Apache License 2.0 covers its code and documentation; it is not the
licence of VEST's data. The repository has not yet decided which licence, if
any, it offers the counts under, or the figure drawn from them, though `LICENSE`
and `CITATION.cff` declare Apache 2.0 for the repository as a whole. The
repository's owner chose to commit the counts with this credit and licence link
(D-044).
