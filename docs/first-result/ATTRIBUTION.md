# Attribution — `ia-seats-v2.csv.gz`

The seat counts in `ia-seats-v2.csv.gz`, in this directory, are adapted from:

> Voting and Election Science Team, 2020, "2020 Precinct-Level Election Results",
> <https://doi.org/10.7910/DVN/K7760H>, Harvard Dataverse, V49 (file `ia_2020.zip`,
> Iowa).

VEST licenses that dataset under the Creative Commons Attribution 4.0
International licence (CC BY 4.0): <https://creativecommons.org/licenses/by/4.0/>.

**What was changed.** The file holds no vote count from the dataset.
`tools/prepare_data.py` summed Iowa's precinct returns to its 99 counties, and
`tools/recount_seats.py` counted, for each committed draw of the v2 ensemble, how
many districts the Democratic candidate won under the 2020 presidential vote and
under the 2020 U.S. Senate vote (D-043). Beside each draw's two counts the file
holds a key for its plan, which comes from the plan alone, not from the returns.
The record beside it, `ia-seats-v2.json`, names the dataset, version and file the
counts were made from, with their hashes, and carries the same credit and licence
link.

**No warranty.** VEST's dataset carries this disclaimer: "THE DATA ARE PROVIDED
“AS IS” WITHOUT WARRANTY OF ANY KIND. WE MAKE NO AND DISCLAIM ALL WARRANTIES,
EXPRESS OR IMPLIED, INCLUDING THE IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT, WITH RESPECT TO THESE DATA. WE MAKE
NO REPRESENTATIONS OR WARRANTIES AS TO THE QUALITY, SUITABILITY OR ADEQUACY OF
THESE DATA FOR ANY PURPOSE OR USE." CC BY 4.0 has its own disclaimer of
warranties, in its Section 5.

The figure drawn from these counts, `docs/figures/ia-neutral-seat-distribution.png`,
credits VEST and the licence in its footer. This repository's Apache License 2.0
covers its code and documentation; it is not the licence of VEST's data. The
owner chose to commit the counts with this credit and licence link (D-044).
