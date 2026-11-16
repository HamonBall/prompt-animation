# Handoff - token guardrails

Updated: 2026-11-16; HEAD: `30b3083`; status: complete.
Assignment: implement repository guardrails against excessive Sol token use.
Scope: AGENTS.md and context policy; preserve active 05.7a and frozen README.

## Done
- Added targeted retrieval, bounded output, reuse of loaded context, bounded
  unsuccessful exploration, concise reporting and authorization-only delegation.
- Separate tasks no longer load the unrelated movement handoff by default.
- Reused existing validation and managed-job rules; no new runtime settings.
- Official basis: [Codex prompting guide](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide)
  supports avoiding reread loops and bounding tool output;
  [best practices](https://learn.chatgpt.com/guides/best-practices)
  supports focused context and concise durable repository instructions.
- The 120-line/2,000-token defaults and two-unproductive-read trigger are local
  heuristics. No Sol-specific token savings benchmark or hard runtime cap claimed.

## Validation and limits
- Executed: scoped diff review, local link checks, `git diff --check` and
  `git check-ignore`; passed (ignore exit 1 means no matches). Pointer is 20 lines.
  No application tests/renders required; no generated evidence changed.
- Future assessment: use client-reported usage on comparable tasks if available;
  compare total tokens, repeated reads and quality/rework. Do not invent savings
  from text length, cached tokens or fewer tool calls alone.
- These instructions cannot remove context injected by the host or force model
  reasoning limits. No global configuration, model or reasoning setting changed.
- README update deferred under the freeze; none needed for these internal rules.

## Workspace and remaining work
- Owned: AGENTS.md, docs/context-continuity-policy.md, to do/CURRENT-WORK.md,
  and this handoff. Existing stage changes preserved; no staging or commit.
- No remaining implementation. No jobs launched, queried, cancelled or resumed.
- Continue stage work only under its existing assignment and handoff.
