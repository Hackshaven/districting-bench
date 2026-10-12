# Attribution — `ia-seats-v2.csv.gz`

The seat counts in `ia-seats-v2.csv.gz`, in this directory, are adapted from:

> Voting and Election Science Team, 2020, "2020 Precinct-Level Election Results",
> <https://doi.org/10.7910/DVN/K7760H>, Harvard Dataverse, V49 (file `ia_2020.zip`,
> Iowa).

The DOI resolves to the dataset's latest version. Version 49, the one the counts
were made from, is at
<https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/K7760H&version=49.0>.

VEST licenses that dataset under the Creative Commons Attribution 4.0
International licence (CC BY 4.0): <https://creativecommons.org/licenses/by/4.0/>.
VEST states the licence in the dataset's terms of use on Dataverse, and in the
end matter of its documentation file, `documentation.txt` (file 14304792 in
version 49). The record's structured licence field is empty, and DataCite lists
the dataset's rights as "Custom terms specific to this dataset". All three were
read on 2026-10-12.

**What was changed.** The file holds no vote count from the dataset.
`tools/prepare_data.py` summed Iowa's precinct returns to its 99 counties, and
`tools/recount_seats.py` counted, for each committed draw of the v2 ensemble, how
many districts the Democratic candidate won under the 2020 presidential vote and
under the 2020 U.S. Senate vote (D-043). Beside each draw's two counts the file
holds a key for its plan, which comes from the plan alone, not from the returns.
The record beside it, `ia-seats-v2.json`, names the dataset, version and file the
counts were made from, with their hashes, and carries the same credit and licence
link. How VEST built the Iowa file from its sources (the Iowa Secretary of State,
eight county governments and the Census Bureau), and which precincts it merged, is
in the Iowa section of `documentation.txt`.

**The file's columns.** One row per committed draw, in the order of
`docs/experiment-2/ia-draws-v2.csv.gz`:

| Column | What it holds |
| --- | --- |
| `chain_index` | The draw's chain, numbered as in the draws file. Chains 4 and 7 have no rows: both failed before their first draw (`docs/experiment-2/ia-draws-v2-chains.json`). |
| `draw` | The draw's place in its chain, counting from 0. The row with the same chain and draw in the draws file is the same draw. |
| `plan` | A key for the draw's plan, blind to the districts' numbers. Each district is written as its counties' GEOIDs, sorted and joined by commas; the districts, in order of their first GEOID, are joined by `\|`; the text is hashed with SHA-256 and cut to its first 16 hexadecimal digits (`plan_key` in `tools/recount_seats.py`). Draws with the same key drew the same plan. |
| `dem_seats@G20PRE` | How many of the 4 districts gave the Democratic candidate for President more votes than the Republican, in VEST's 2020 returns summed to counties. `G20PRE` is VEST's code for that contest. |
| `dem_seats@G20USS` | The same for the 2020 U.S. Senate race (`G20USS`). |

No district is tied in any draw: the recount writes nothing if one is.

**No warranty.** VEST's dataset carries this disclaimer, in its terms of use on
Dataverse: "THE DATA ARE PROVIDED “AS IS” WITHOUT WARRANTY OF ANY KIND. WE MAKE
NO AND DISCLAIM ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING THE IMPLIED
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT, WITH RESPECT TO THESE DATA. WE MAKE NO REPRESENTATIONS OR
WARRANTIES AS TO THE QUALITY, SUITABILITY OR ADEQUACY OF THESE DATA FOR ANY
PURPOSE OR USE." Its documentation file carries it too, punctuated differently.
CC BY 4.0 has its own disclaimer of warranties, in its Section 5.

The figure drawn from these counts, `docs/figures/ia-neutral-seat-distribution.png`,
credits VEST, the dataset's DOI and the licence and its link in its footer. This
repository's Apache License 2.0 covers its code and documentation; it is not the
licence of VEST's data. Which licence, if any, the repository offers the counts
under is not yet decided. The owner chose to commit the counts with this credit
and licence link (D-044).
