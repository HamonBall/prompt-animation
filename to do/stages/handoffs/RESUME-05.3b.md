# Stage 05.3b handoff

Status: **complete**, 2026-11-02. Stage 05.3b is closed;
05.4 and subsequent stages have not been started. Read AGENTS.md,
receipts/05.3b.md, docs/contracts/fingers-v1.md and both project policies.

Base commit: 84087da52b6e32f06142fa06bb1a188bfb8667aa. All implementation remains
uncommitted. No staging, commit, branch, stash/reset or ignore change was made.
Preserve the entire working tree. README was initially the only modified file.
It changed externally at 08:51:53 UTC by removing "prototype" from its title;
current SHA256 is 57dd7de96640eb40e5a6ac4541edc6c8e1784e693ead5ee970754be8238059ab.
Replacing only that title in memory exactly reproduces initial SHA256
25aa821a1ff205577f521ba99af02af5fec677f2f3448dab862cfcf3f1a6bfe8.
Do not edit/revert it. Its external title trailing space is the sole full-tree
diff-check issue; src/tools/tests diff checks pass.

## Delivered and verified

hand.gesture and finger.curl_spread, definition 1, fingers.targets.v1,
opt-in profile 6. Core: movement_library/fingers.py, blender/finger_mechanics.py.
Profile-5 controls retain their semantics. Snapshot version relabelling is not
migration: calibrate/use profile 6 and capture a fresh measured entry.

Versioned fixtures: tests/fixtures/fingers/v1, with profiles, exact schemas,
rebuildable examples and explicit reviews. Mixamo has ten existing three-joint
digits; thumb is an approximate hinge, without opposition/grasp. Demo has no
fingers and is explicitly unavailable_on_rig for both IDs. Catalog construction
never automatically grants reviewed status. No bones/rest transforms/weights/
source topology, downloads, contact solver, general composer, prompt handling
or product UI feature was added.

All 26 native cases /2,564 samples pass current independent audit. All 142 movies
/14,068 frames are retained in storage-v2 FFV1 media with decoded-pixel checks.
71 complete pages cover body front/side and palm/edge per active hand.
All current cases have actual full-motion inspection; receipt identifies
hash-checked reuse of previously inspected identical sheets separately.

Unit commands: 219 discovery tests, 12 existing explicit integration skips,
plus two later negative provenance tests and one publication test: total 222
run, 210 passed, 12 skipped. Native optional-anatomy/preservation/cancellation/
failed-review rollback checks pass. Six demo missing-detail variants preserve
major arm motion. Sixteen old/new profile regression executions agree exactly
on both rigs; eight signed finger calibration probes pass.

Independent maxima: tracking .000207445 degrees; unrelated .00308638 degrees
/.000003040 m; actual digit speed 269.956517 degrees/s, acceleration
688.137443 degrees/s²; floor penetration 1.00258e-8 m, contact error zero.
Unchanged tolerances apply. Native acceleration max is 688.139227 degrees/s².

Two strict resume passes preserve all 171 payload hashes/bytes/mtimes:
26 motions, 142 movies and all three shared avatars. No motion or media
executed during those checks. Stage artifact audit passes positive Mixamo
coverage and explicit demo unavailability. Historical stage matrices are not
blanket current-source cache hits or newly executed results.

## Important provenance and failures

The authored sequence initially exceeded the unchanged 256-track budget.
Only its redundant zero-spread channels were removed (210 tracks /190 samples).
The exact one-line non-sequence compatibility migration and negative tests
pin the 25 unaffected numeric cases; app source identity stays exact.

Floor occlusion invalidated old isolated bent-hand media. Corrected detail
views hide environment meshes and enforce per-frame visibility. All 26 saved
motions and 52 full-body movie records/mtimes remained unchanged; the 90 hand
views were regenerated from saved actions. Minimal framing diagnostics remain.

One Intel ig9icd64.dll shutdown crash followed completed corrected renders.
Original nonzero exit/log remains. Exact fresh read-only playback recovery
exited 0, checked all samples and payload identities. Final checker/driver/log/
runtime hashes are pinned in native-shutdown-recovery.json; cache reuse requires
that recovery. No motion/media was regenerated for it.

The first global storage scan overlapped pilot retirement, then failed on the
removed manifest. Its failure log is retained. The fresh full post-retirement
scan passed: 709 bundles, zero budget errors and zero active leases.

## Verified storage closure and stop boundary

Baseline artifacts: 2,064,288,980 bytes /58,979 files. Assets: 64,209,506 bytes;
no additions. Preserve 58,977 predecessor files, with only global current-
inventory.json and budget-check.json refreshes allowed. Verified obsolete
eight-file pilot retired: 2,247,840 bytes, durable hash journal.

Monitor stopped at zero temporary bytes; sampled peak 13,249,449 bytes over
1,442 observations, not a continuous maximum. Earlier numeric pilots were
unmonitored under a 32 MiB reservation. Largest combined reservation
494,927,872 bytes, below the 512 MiB temporary limit. No active native writers,
packed repeated avatars or stage Blender backups remain. Count fixtures and
all local code caches outside artifacts conservatively.

tools/complete_fingers_storage.py passed. Final artifact tree: 2,288,889,642
bytes /59,744 files. Stage 05.3b: 224,552,849 bytes /764 files. Outside artifacts:
fixtures 576,777 bytes and all local code caches conservatively 1,925,730 bytes.
Conservative stage total 227,055,356 bytes (216.54 MiB), global 2,291,392,149
bytes (2.134 GiB). Maximum case motion+manifest 902,527 bytes. All 58,977
protected predecessors, three assets, 26 motion payloads and 52 full-body movie
records/mtimes are preserved. No exceptions, active leases, backups, unresolved
failure pins or temporary bytes remain. Exact report:
artifacts/stages/05.3b/completion-accounting.json. Global budget/evidence reports
are in artifacts/maintenance/storage-v2/; original failures remain in stage logs.

Receipt, stage/index/ledger and AGENTS are complete. Full-tree git diff --check
reports only the concurrent README title trailing space; changed source/fixtures
pass whitespace/conflict checks. No README edit is authorized by completion.
Do not rerun passed native matrices or media without a relevant change or
unresolved concern. Work stopped before 05.4; wait for the user's next assignment.

Use the bundled Python at
C:/Program Files/Blender Foundation/Blender 5.1/5.1/python/bin/python.exe.
Blender is 5.1.0 build adfe2921d5f3, factory startup, two threads per worker.
InitializeDefaultDrives warnings are non-blocking when exit/assertions pass.
