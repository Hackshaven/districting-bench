# tests/

Tests live outside `src/` deliberately. `tools/check_firewall.py` scans `src/` only,
so a test may import from any package without creating a firewall violation — a
test is not the neutral baseline. Keeping them here means the firewall's import
graph describes the system, not the test harness.

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/ -q`
