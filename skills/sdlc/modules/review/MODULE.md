# PR review and readiness checklist

Review the actual final diff and fresh verification evidence before
presenting a change as done or PR-ready.

## 1. Scope and contract pass

- Compare the diff with the stated outcome, acceptance criteria, and
  non-goals.
- Confirm every changed file supports the coherent outcome.
- Remove accidental edits and unrelated cleanup. Record independently useful
  work as a separate follow-up instead of bundling it.
- Confirm the change is complete: necessary tests, docs, migrations,
  compatibility, and error handling are present.

## 2. Independent expert review

Use independent reviewers by default when the host supports subagents or
delegated review. Scale effort to risk:

- **Trivial**: one concise final-diff self-review; an independent reviewer is
  optional unless risk is hidden.
- **Standard**: at least one independent reviewer, asked to cover correctness,
  scope, tests, and maintainability.
- **Significant**: multiple independent reviewers when the host supports
  them. Assign only relevant perspectives, but always include correctness
  and scope.

Select perspectives based on the diff:

| Perspective | Use when |
|-------------|----------|
| Correctness & scope | Every behavioral change |
| Tests & failure modes | Every behavioral change |
| Security, authN & authZ | Inputs, data, network, identity, permissions, secrets, dependencies |
| Compatibility & data | APIs, schemas, migrations, serialization, public contracts |
| Performance & concurrency | Hot paths, parallel work, queues, caching, resource use |
| Maintainability | Non-trivial structure, abstractions, or refactors |
| UX & accessibility | User-visible interfaces or workflows |

Give reviewers the goal, acceptance criteria, non-goals, final diff, and test
evidence. Ask for actionable findings with severity, location, reasoning, and
confidence. Do not ask them merely to confirm the implementation is good.

Only when independent review is unavailable, perform distinct self-review
passes for the relevant perspectives and disclose that limitation. Do not
substitute self-review merely to save time or avoid delegation.

## Correctness

- Does the change actually do what was asked? Re-check against the original
  request and the plan.
- Are edge cases handled (empty/null inputs, zero/negative numbers, empty
  collections, concurrency, network failures, timeouts)?
- Any off-by-one errors, incorrect operator precedence, or wrong
  comparisons?

## Scope & hygiene

- Is the change scoped to one coherent outcome, with no unrelated drive-by
  edits?
- No leftover debug code, commented-out blocks, TODOs without context, or
  dead code.
- Naming, formatting, and structure consistent with the surrounding
  codebase.

## Tests & verification

- When testing was selected, test coverage matches the
  [testing module](../testing/MODULE.md)'s definition of done.
- Tests were actually run, not just written.

## Security

- When security-auth was selected, its relevant items were addressed.

## Readability & maintainability

- Would another engineer (or the user) understand this diff without extra
  explanation? Add comments only where the "why" isn't obvious from the
  code itself.
- Is error handling explicit and informative, not swallowed silently?

## Before declaring done

- Triage every finding. Fix findings caused by or tightly coupled to the
  change, then re-run affected tests and checks.
- Do not expand the PR to fix unrelated pre-existing issues. Report them as
  follow-ups. If one blocks safe delivery, do not call the change PR-ready.
- Re-review the resulting diff when a fix materially changes behavior or
  scope.
- Summarize what changed, what was tested, and any known limitations or
  follow-ups. Include the reviewer perspectives used and any unresolved risk.
- When project-memory was selected, use it to record any durable decision or
  do/don't rule that emerged from review.

## Common shortcuts that fail

| Shortcut | Why it is insufficient |
|----------|------------------------|
| "CI will catch it" | CI runs configured checks; it does not validate intent, scope, or missing cases. |
| "The happy path passed" | Error paths, boundaries, permissions, and compatibility can still fail. |
| "It is only a small diff" | Risk comes from behavior and context, not line count. |
| "Review found adjacent cleanup" | A useful finding is not automatically part of this coherent change. |
