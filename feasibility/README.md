# feasibility/

Throwaway probes for the pre-Phase-1 feasibility pass. **Not implementation code.**

`src/` is deliberately still empty of Python. These scripts answer "can this be
built at all, on this data, in this environment" — they are not the system, and
they are not designed to become it. Expect them to be deleted or rewritten from
scratch when Phase 1 starts.

They live outside `src/` so that no code lands inside the firewall's package
boundaries before the architecture for those packages has been decided.

Run from the repository root, in order:

```
python feasibility/parse_pl.py            # county populations from PL 94-171
python feasibility/adjacency.py           # rook/queen graph + Census cross-check
python feasibility/enacted.py             # enacted plan, deviations, topology
python feasibility/enacted_connectivity.py
PYTHONPATH=feasibility python feasibility/ensemble.py
PYTHONPATH=feasibility python feasibility/epsilon_sweep.py
PYTHONPATH=feasibility python feasibility/tight_equality.py
```

`feasibility/fetch_data.sh` downloads the inputs. Nothing under `data/` is
committed — see `.gitignore`.
