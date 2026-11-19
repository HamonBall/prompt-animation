# Handoff — Stage 07 animation compiler

Updated 2026-11-19. HEAD `09db162`. Complete for the documented envelope.
Assignment was [Stage 07](../07-animation-compiler.md). Stage 08 awaits assignment.

- The [receipt](../receipts/07.md) records the managed runs, measured Blender
  results, reviewed cases, and storage. The
  [execution contract](../../../docs/contracts/recipe-execution-v1.md) describes
  the compiler, surface identity and measured activation boundary.
- Eight bundles with 1,227 frames passed saved playback and both full-motion
  view inspections. Hash-bound observations are in
  `artifacts/stages/07/visual-review.json`. The runner's `needs_review` result
  preceded inspection. The review and storage commands passed afterward.
- Full discovery ran 326 tests with 12 skips. The final compiler set passed
  eight focused tests. Both legacy preset runs and clip passed. The Andrejs
  lying floor-height assertion failed on the current and baseline source.
- Stage 08 can use the compiler for supported recipes. Its landscape of
  unsupported transitions, ownership, and loop cases is in the contract.
- Stage artifacts total about 28.57 MB and global accounting passed at about
  3.991 GB. Zero active writer leases or scratch remained. Changes are unstaged.
  README remains frozen.
