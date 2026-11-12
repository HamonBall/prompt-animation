# Stage 05.6a handoff

Status **complete, 2026-11-10**. The implementation checkpoint is
`0cff22e`. The fixture publisher and closure documentation were added
in the working tree. Read [AGENTS.md](../../../AGENTS.md), the
[specification](../05.6a-root-travel-flight.md), [receipt](../receipts/05.6a.md),
and [root-motion contract](../../../docs/contracts/root-travel-flight-v1.md).

- Profile 8 supplies the measured world `object_root.position` and
  `object_root.orientation` controls. Their baked armature channels
  preserve the local pelvis and limb pose. The legacy snapshot
  `root_transform` describes the semantic pelvis frame. Capture the
  next entry at the solved endpoint. Active floor anchors stay fixed in
  world space and released contacts are absent from the solved exit.
- Airborne fragments preserve their achieved endpoint and explicitly
  require released support, except hover takeoff, which releases both
  soles. A grounded turn supports a single captured sole with the
  opposite foot already raised. The boundary check rejects two locked
  soles. General support acquisition and transfer remain in 05.6b.
- The 32-case matrix passed numeric, saved playback, and complete front
  and side review on Demo and Mixamo. The native compatibility, floor,
  and primitive bridge checks passed. Profile-8 examples and reviewed
  envelopes are in `tests/fixtures/root_travel_flight/v1/`.
- Global storage passed for 1,025 bundles. Final temporary bytes and
  writer leases are zero. Conservative stage and global totals are
  60,868,231 and 3,159,183,556 bytes, respectively.

Closure and verification details are in
`artifacts/maintenance/jobs/stage-05.6a-closure/report.json`.
See `artifacts/stages/05.6a/completion-accounting.json`,
`publication-summary.json`, and `visual-review.json` for recorded
evidence. Reuse only with current matching identities. The README
freeze remains in force. [05.6b](../05.6b-support-transfers.md) awaits
assignment.
