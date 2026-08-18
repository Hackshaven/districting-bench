# src/generate/

Produces the neutral baseline ensemble. If partisan or demographic data reaches this package by any route, the baseline is not neutral and every outlier claim built on it is void.

**May import from:** nothing under `src/`

This boundary is enforced mechanically by `tools/check_firewall.py`, run in CI.

## Do not refactor this boundary away

You will notice duplication and coupling across these packages that ordinary
code-quality instincts say should be extracted into a shared module. The
duplication is deliberate. Extracting it destroys the property the whole system
depends on: that the neutral baseline was produced without any knowledge of
partisan or demographic outcomes.

A commit that merges these packages, adds a shared utility they all import, or
relaxes `tools/firewall.yaml` invalidates every result produced after it.

Everything *inside* this package is an open design question. The boundary is not.
