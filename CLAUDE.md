# CLAUDE.md

## Rules that live elsewhere

This repo's rules are in its own documents. Read the one that covers a
change before making it. Where an agent's general advice and one of these
disagree, the document wins.

| Document | What it rules |
|---|---|
| `prompt.md` | The owner's brief, kept verbatim. Nobody edits it. The firewall is not modified or worked around, detection is optimized and generation is not, each experiment runs once, critics never read the builder's reasoning, and "any output that reads as a verdict rather than a distribution is a bug" |
| `tools/firewall.yaml`, `tools/check_firewall.py` | The boundary, written before any implementation code. Changing either is the owner's decision, in a commit that changes nothing else. If a check fails, fix the code; if the config looks wrong, stop and say so |
| `docs/CRITERIA.md` | Every criterion, threshold, and metric, each with a provenance class. It wins over anything found online, and only the owner amends it |
| `docs/ARCHITECTURE.md` | Package internals, the plan and data contracts, the `bench-results.json` schema, and seeding. A module that disagrees with it is wrong until the file changes |
| `src/*/README.md` | Each package's import rights, and why the duplication between `generate` and `evaluate` is deliberate |
| `docs/DECISIONS.md` | D-001 onward, appended as each choice is made. Entries aren't rewritten; a reversal is a new entry |
| `docs/progress.md`, `docs/experiment-*/INSTRUMENT-AUDIT.md` | The results record, retractions included. A refuted claim stays recorded as a failure (D-018), and the audits are kept verbatim |
| `docs/RESEARCH-LOOP-PLAYBOOK.md`, `docs/CLAUDE-memory-snapshot.md` | Long jobs in an ephemeral container. Only a pushed commit is durable, and agent memory is restored from the snapshot, never the other way round |

---

## Review agents

`.claude/agents/` holds a review team of 15 agents installed from the
[agency-agents catalog](https://github.com/Hackshaven/agency-agents/blob/hackshaven/strategy/runbooks/scenario-districting-bench.md)
by its districting-bench runbook, which carries the reasoning behind each
row below. Three of them were built for this repo: the
`Blinding & Leakage Auditor`, the `Computational Redistricting Scientist`,
and the `Election Law Analyst`. Their design records and blind-test
scorecards are in the catalog's `.designs/`.

The team covers what CI can't compute: whether a statistic supports a
verdict, whether a figure or a sentence reads as one, whether a data join
conserved its votes, and whether a legal sentence says what the opinion
says. It runs on the same model family that wrote most of this repo and
shares its blind spots, so it is not outside review. The people in
[When a person decides](#when-a-person-decides) are.

**When to run them.** Before reporting a change done or opening a PR,
route it by the paths it touches and run each matching reviewer through
the Agent tool, with `subagent_type` set to the name in the table exactly
as written. Not after every edit: one run rereads the diff and the
documents it cites. A change that matches several rows runs every one of
them. A change only to prose that no row names needs none. When the owner
names an agent, run that one.

- **Gates of record.** Every code change gets the `Code Reviewer`, and
  every change to a detection rule, a gate, or an experiment instrument
  gets the `Statistician`. These are never skipped. A second reader named
  in a row runs beside its gate, and a disagreement between the two is a
  finding. On a small change the second reader may be skipped, with two
  exceptions: under `src/generate/` the `Blinding & Leakage Auditor`
  always runs, and under `src/detect/` a change that moves a published
  number always gets its second reader.
- **CI first.** `python tools/check_firewall.py` must print clean, and
  `PYTHONPATH=src pytest tests -q --strict-markers` must match the counts
  in the README's Setup section. A change that adds tests updates those
  counts in the same commit; a count that moves without the change
  explaining it is a finding. Quote both counts, with and without the data
  (D-037).
- **Reviewers get the evidence, not the reasoning.** Give each one the
  diff and the evidence: `bench-results.json`, the committed results JSON
  and draws, the rendered figures. Never the commit message or the
  author's explanation (`prompt.md`'s critic rule).
- **Reviewers report; they don't edit.** Each returns findings with
  `file:line`. You fix, and the owner decides what stands. A value
  judgment `docs/CRITERIA.md` doesn't settle becomes a `docs/DECISIONS.md`
  entry, marked VALUE.
- **Two overrides for the `Code Reviewer`.** The duplication between
  `generate` and `evaluate` is required: never extract it, because a
  shared module is an import edge across the firewall. And a warning is
  never silenced to get a clean run: `filterwarnings("ignore")` hid the
  `node_repeats` defect that produced a false headline
  (`docs/FEASIBILITY.md` §5.1).
- **Don't hand-edit the catalog agents.** Each file in `.claude/agents/`
  is a verbatim copy from the catalog, and a reinstall replaces it. Change
  them in the catalog.

Use this prompt, filling in the brackets:

```
Review this districting-bench change as the [Agent]. Read the diff
(git diff origin/main...HEAD -- [paths]) and the evidence in [bench-results.json /
docs/experiment-<n>/*.json / docs/figures/*.png]. You are not given the author's
reasoning; judge the change from the diff and the evidence.
Report findings with file:line, most important first. Do not edit files.
The rules in prompt.md, docs/CRITERIA.md, and docs/ARCHITECTURE.md win over your
own defaults. The duplication between src/generate and src/evaluate is required:
never recommend sharing code across it, and never recommend changing
tools/firewall.yaml or tools/check_firewall.py. Nothing may combine the metrics
into one score, and any output that reads as a verdict rather than a
distribution is a finding.
```

| If the change touches… | Run | Why |
|---|---|---|
| `tools/firewall.yaml`, `tools/check_firewall.py` | Nobody edits them. Stop and tell the owner | An agent that finds a gap reports it with the probe that shows it. D-006's fixes are still open. Loosening the config makes later results suspect; closing a gap makes earlier results suspect until they are checked against the tightened rules (the README's firewall section, [issue #4](https://github.com/Hackshaven/districting-bench/issues/4)) |
| Any file under `src/generate/`, of any type; a new file or directory directly under `src/`; any new read of a file in `data/` | `Code Reviewer`; `Blinding & Leakage Auditor` as second reader, always | The static check never scans a file at the top of `src/` or a non-`.py` file, and can't see a file read that names no column. The schema allowlist in `units.py` is the only defence on those routes |
| `src/generate/{ensemble,convergence,seeds}.py`, `tools/convergence_rectangle.py` | `Code Reviewer` and `Statistician`; `Computational Redistricting Scientist` and `Blinding & Leakage Auditor` as second readers | Convergence is diagnosed on the largest common-prefix rectangle (D-035). Chain failures are counted, never retried. Seeds derive from one master seed |
| `src/detect/**`, a gate, the flag rule | `Statistician` and `Code Reviewer`; `Blinding & Leakage Auditor` as second reader when the null pool, the reference ensemble, or the planted cases change | A gate a constant can tie isn't a measurement, and a gate no detector could meet is reported `unreachable`, not failed (D-013) |
| `src/adversarial/**` | `Code Reviewer`; `Computational Redistricting Scientist` and `Blinding & Leakage Auditor` as second readers | The planted gerrymanders are the ground truth, and must be indistinguishable from neutral maps on non-partisan metrics (D-010). The Auditor's separability score is the measure |
| `src/evaluate/{partisan,compactness,administrative,plan,report,elections}.py` | `Code Reviewer`, with `docs/CRITERIA.md` §3, §5, and §7 as the spec; `Computational Redistricting Scientist` as second reader | Sign conventions differ by metric on purpose (`FAVOURS` in `partisan.py`). `report.py` reports every value and resolves nothing (D-032). `tests/test_experiment_3_plans.py` pins published values |
| `tools/experiment_*.py`, `tools/check_metric_algebra.py`, `tools/phase_2_report.py`, `docs/experiment-*/`, `docs/phase-2/` | `Statistician`, plus `Code Reviewer` for code; `Computational Redistricting Scientist` as second reader | The experiments ran once and aren't re-run. Analysis is a pure function of committed draws (D-027). The multiplicity correction rewrites the verdict (D-025). ReCom draws aren't independent (D-029) |
| `tools/prepare_data.py`, `tools/prepare_data_co.py`, `tools/prepare_municipalities.py`, `tools/fetch_raw.sh`, `feasibility/*.py` | `GIS QA Engineer` | Check that votes and population are conserved, not how many ids matched: a join reported "unmatched units: 0" while dropping 215,617 votes (D-016). Also rook adjacency (D-004) and membership versus districting layers (D-033) |
| `tools/plot_*.py`, `docs/figures/**` | `Scientific Visualization Reviewer` | Figures recompute from committed artifacts (D-036). The Experiment 3 figure inverts the alarm colour on purpose, and its legend says so |
| `docs/progress.md`, the README's "First result" and "The three experiments", the `CITATION.cff` abstract, a version bump | `Pre-Submission Peer Reviewer`; `Computational Redistricting Scientist` as second reader; on a version bump, then the `Scientific Data Steward` | CI doesn't check prose numbers, and each release archives them under a permanent DOI |
| The README's "Legal context", `docs/CRITERIA.md` §1, §2, and §4, any sentence about a holding, statute, or remedy, any report text that could read as a legal conclusion | `Election Law Analyst`, then the election-law reader | The Analyst checks each sentence against the primary text, dates it, and marks what needs a lawyer ATTORNEY. It never advises |
| The README's "What this is not" and status line, any text the report shows a user | `Science Communicator` | Distributions, never verdicts. The status line travels with every citation and is never softened |
| The README's Setup, Getting the data, and Reproducing; `tests/README.md`; `tests/dataguard.py`; `.github/workflows/tests.yml` | `Technical Writer` for prose, `Code Reviewer` for code | The suite must run on a machine that has never fetched the data (D-037) |
| A sentence that characterizes a paper | `Research Synthesist` | Traced to the paper itself. Legal sources go to the `Election Law Analyst` |
| `requirements.txt` | `Code Reviewer`, and the owner for any pinned scientific library | `gerrychain` is pinned exactly. A bump can move every ensemble, so results from before and after it are different ensembles |
| `.github/workflows/release.yml` | `Scientific Data Steward`, then the owner | It mints a permanent DOI (D-038) |
| `prompt.md`, `docs/experiment-*/INSTRUMENT-AUDIT.md` | Nobody edits them | Kept verbatim |
| Any other section of `docs/CRITERIA.md` | The owner | Agents propose. Decision-log entries marked VALUE are the queue |
| Any other code under `src/`, `tools/`, or `feasibility/` | `Code Reviewer` | No row above matches |

Paths are as of October 2026. When a row names a path that has moved,
route by what the code does and fix the row.

### Firewall checklist

The `Blinding & Leakage Auditor` walks its full channel inventory on any
change under `src/generate/` or any new read of a file in `data/`. Any
reviewer can run these five questions when it isn't available:

```
1. Does anything in src/generate/ import from another package under src/?
2. Does any file in src/generate/, of any type, name or open a file that
   docs/ARCHITECTURE.md §2 doesn't class as neutral?
3. Does every dataframe still pass the schema allowlist in units.py
   ({GEOID, NAME, pop, geometry}) before generate uses it?
4. Is there a new file directly under src/, outside every package?
   The static check never scans one.
5. Could a seed, cache key, config value, or test fixture carry anything
   derived from election or demographic data into generation?
Answer each with file:line or "no change".
```

### Before a write-up: the instrument audit

Any new result headed for `docs/progress.md`, the README, or a release
goes through the repo's own audit first (D-007):

```
Auditors   3–5 fresh-context agents, each attacking one lens of the instrument:
           Statistician (inference, power, controls), Computational Redistricting
           Scientist (sampler, metrics), Blinding & Leakage Auditor (overlap,
           separability), GIS QA Engineer (data), Code Reviewer (wiring),
           Scientific Visualization Reviewer (figures)
Refuters   one fresh agent per allegation, told to default to "refuted"
           and to reproduce the number before agreeing
Synthesis  Research Synthesist reads the allegations and refutations side by
           side and discards refutations that don't hold
Record     the synthesis goes verbatim into docs/experiment-<n>/INSTRUMENT-AUDIT.md
```

Size the audit to the claim: a headline result gets the full audit, and a
corrected number gets one auditor and one refuter.

### Not per change

- **`Blinding & Leakage Auditor`, periodic full-tree audits.** That is
  where its findings that nobody planted came from.
- **`Codebase Archaeologist`, quarterly:** every number in the README,
  `docs/progress.md`, and the `CITATION.cff` abstract against the
  committed results; the open-defects lists in `docs/progress.md` against
  the tree; decision-log entries against the code. Tell it the
  duplication between `generate` and `evaluate` is required.
- **`Mad Scientist`, only when a line of work stalls.** Each bet goes to
  the `Statistician` before anyone builds it, and the owner chooses. A
  bet that makes the adversary better at building gerrymanders is
  dual-use. A re-run of an experiment is a new experiment with its own
  name (D-036).
- **`Codebase Onboarding Engineer`, for succession:** two guides, one for
  the neutral half (`src/generate/`, the data build, the firewall) and one
  for everything downstream.

### When a person decides

The agents check claims; none of them owns one. Go to a person when:

| When… | Who decides |
|---|---|
| A change to `tools/firewall.yaml` or `tools/check_firewall.py` is proposed, D-006's open fixes included | Owner, in a commit that changes nothing else |
| A legal sentence is new, changed, or older than the latest relevant decision | The election-law reader (an election-law attorney or scholar), with the `Election Law Analyst`'s claim register |
| A decision-log entry marked VALUE is ready for `docs/CRITERIA.md` (D-013 now) | Owner |
| The `Statistician` or the `Computational Redistricting Scientist` says the evidence can't support a verdict, a ranking, or a "no tradeoff" | Owner: the claim waits, or is reworded to what the evidence supports. "Cannot tell" is its own finding (D-019, D-023) |
| A new state is added | Owner, with the election-law reader on that state's criteria and remedies |
| Election data would be committed, or VEST's licence or version question gets an answer | Owner. Nothing is committed under an unstated licence (`docs/CRITERIA.md` §9.1) |
| A version bump will mint a DOI | The science reviewer (someone outside the authoring loop who has built or used redistricting ensembles) and the election-law reader read the headline and legal claims first, then the owner releases |
| The ballot-styles metric is presented as a finding outside the repo | An election administrator: a county or state election official |
| Anyone proposes softening the status line, or presenting a result as evidence about a real map | Owner, after outside validation that doesn't exist yet. Until then the answer is no |
| The third review of the same claim fails | Owner, who drops the claim or takes it to the science reviewer |

Record each decision where the repo already records them: a firewall
change in its own commit, a value judgment in `docs/DECISIONS.md`, a
criteria change in `docs/CRITERIA.md`, a retraction in `docs/progress.md`,
and a release in its notes, naming who read the headline and legal
claims. A relayed "a lawyer said so" is a claim, not a source: ask for
the citation. An agent's referee report is never presented as outside
review.
