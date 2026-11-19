# Current work pointer

Updated: 2026-11-19.

- Latest completed stage is [05.7b bounded motion style](stages/05.7b-style.md),
  in the working tree based on e7b1fa8. See its
  [receipt](stages/receipts/05.7b.md) and
  [handoff](stages/handoffs/RESUME-05.7b.md).
- Six styles have 32 reviewed cases on Demo and Mixamo, with 3,812 samples.
  Publication and strict audit passed, verifying 1,216 bundles.
  Conservative accounting totals 3,965,897,323 bytes globally and 95,969,949
  bytes for the stage. Final temporary bytes and active writer leases are zero.
- Stop after 05.7b. Stage 06 awaits explicit assignment.
- Enable the visualizer with every runner launch. Normalized folder identity
  keeps one window across automatic and manual launches.
- Standing [context continuity policy](../docs/context-continuity-policy.md)
  applies at session start. Preserve all unstaged changes.
- Separate pending [maintenance assignment](validation-storage-handoff-maintenance.md)
  remains separate from movement-stage completion.
- README remains frozen.
