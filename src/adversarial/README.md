# src/adversarial/

Deliberately partisan. Builds known gerrymanders with known intent and magnitude, to serve as ground truth for the detector. Must never be imported by generate — its whole purpose is the thing generate must not do.

**May import from:** `evaluate`

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
