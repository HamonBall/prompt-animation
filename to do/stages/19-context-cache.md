# Stage 19 — Optional — bounded background reference context

Status: planned (optional extension). Dependencies: [18](18-acceptance.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Make available reference information usable behind the prompt flow without blocking the local movement library. This stage implements bounded retrieval plumbing; automatic web-search provider selection remains a separate explicitly scoped task.

**Permitted changes:** planning/reference.py and a context-provider/cache interface, associated workflow progress/fallback and tests. No provider selection or account setup.

## Execution

1. Wrap the existing supplied-public-URL adapter in a provider-neutral interface returning concise text, sources, retrieval time, expiry and availability. Support cached reference data for repeated unfamiliar terms.
2. Use known user-supplied/configured sources only. Add a hook for a future configured search provider without claiming a working automatic search service or scraping search-engine AI answers.
3. Use at most two configured URLs, a 12-second total wall deadline and 3,000 combined planner characters. Each URL has at most one fetch, bounded by remaining total time and the existing 200,000-byte response cap. Return available partial context at the deadline.
4. Preserve public-address/redirect/content checks and treat all remote text as data. Context can describe motion meaning; registry schemas and executable constraints remain authoritative.
5. On unavailable context, continue with local data and a concise limitation when relevant. Do not re-fetch context for an unrelated wrist/speed edit.

## Required outputs and handoff

Publish the context-result/cache schema and invalidation/source/fallback behavior. Total request budget: two configured URLs, 12 seconds wall time, 3,000 combined planner characters; retain the 200,000-byte per-response cap. Return partial context at the deadline. Context cannot redefine executable IDs/defaults. Unconfigured automatic search stays explicitly unavailable.

## Testing

- Test cached hits, expiry, timeout, unavailable provider, invalid URL, oversized/untrusted text and successful source attribution using controlled fixtures.
- Verify no network request for ordinary local joint edits, and no fetched instruction can alter supported IDs, validation or code execution.
- Run one authorized supplied-reference flow where available; label fixture-only coverage accurately.

## Validation / completion gate

Reference use is bounded, cached and optional; failures preserve useful local behavior. Sources and cache state are diagnosable. The receipt explicitly distinguishes this integration from an unimplemented automatic search provider.

Write the stage-19 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No paid services, account creation, background upload of avatar files, scraping Google/Gemini interfaces or promises of free unlimited APIs. Do not block core acceptance on this optional enhancement.

