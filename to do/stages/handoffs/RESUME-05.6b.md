# Stage 05.6b handoff

**Complete 2026-11-11.** The implementation and fixtures were committed
as `d2f2e74`, based on `c6183e1`. Read the [project instructions](../../../AGENTS.md),
[stage receipt](../receipts/05.6b.md) and
[support contact contract](../../../docs/contracts/support-transfers-v1.md).

- `support.acquire_release`, `support.transfer` and `body.balance`
  use the single-fragment bridge and measured profile-8 anchors.
  Transfer keeps the old support until the new anchor is held.
  Body balance measures the pelvis projection over one captured sole.
- Heel and forefoot use calibrated ankle-frame points. Palm, pelvis,
  back and knee depend on calibrated skin landmarks. Targets use
  resolved horizontal surfaces. Check anchor capabilities and entry
  compatibility before choosing a route.
- Demo and Mixamo passed all 38 cases with 6,088 reviewed view frames.
  Eight earlier renders were reused after fresh-bake equivalence.
  Six published examples are in the
  [fixture manifest](../../../tests/fixtures/support_transfers/v1/manifest.json).
- The repository-wide audit passed for 1,063 bundles. Final temporary
  bytes and writer leases were zero. Accounting is recorded in
  `artifacts/stages/05.6b/completion-accounting.json`.

[Stage 05.6c](../05.6c-coordinated-body-moves.md) awaits explicit assignment.
Project Markdown under `docs/` and `to do/`, and root `AGENTS.md`, is
eligible for normal Git tracking. Include relevant instructions and
handoffs when committing; do not assume untracked documents are already
part of the implementation commit. Source avatars and local evidence
remain governed by their separate ignore and retention rules.
