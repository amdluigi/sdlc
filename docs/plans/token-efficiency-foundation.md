---
type: implementation-plan
prd-path: docs/prds/token-efficiency-foundation.md
prd-id: token-efficiency-foundation
prd-version: 2
---

# Token efficiency foundation implementation plan

## Outcome

The opt-in bounded runtime delivers the execution manager's exact validated
role/context to the model, builds a deterministic prompt without silently
discarding required history, and reports cumulative privacy-safe request
accounting while preserving existing approvals and stored records.

## Approach

Keep the existing Python manager and VS Code runtime boundary. Read role
instructions only from a profile whose bundled and installed content digests
match the request's profile digest. Keep context selection tied to the
validated request role, context revision, and context digests. Build named
prompt components in the runtime driver. Retain distinct tool history from
the current bounded attempt when relevance cannot be established
deterministically. Use validated references for prior edits where required
information and evidence remain available. Compact only consecutive exactly
identical read/search observations, retaining the unchanged observation and
its occurrence count in the same position. Do not collapse distinct or
nonconsecutive observations or edit/execute outcomes. Preserve task
instructions, mandatory requirements, security constraints, tool results and
acceptance evidence. Do not add a relevance classifier, speculative deletion
or an LLM summarizer. If the complete prompt exceeds its approved budget,
fail visibly before a provider call where possible and report an actionable
limit error without silently truncating content.

Keep existing execution-limit `inputBytes` semantics, which include prompt
and tool-argument bytes. Add a distinct cumulative model-facing `totalInputBytes`
and component byte totals. Keep output bytes as the existing bounded-runtime
measure of model responses plus tool results. Capture provider usage only
when the host supplies it; current host-unavailable values remain null. Use
a new strict controller-event version for detailed batch accounting while
retaining old event readers and records. Do not write prompt content to any
runtime or manager store.

## Stack and compatibility constraints

- Python standard library for manager/runtime helpers; Node.js built-ins for
  the VS Code driver. No new dependency or model call.
- Preserve native-request version 2, execution-manager authority, immutable
  plan history, current role/context digest validation, finite limits,
  explicit consent, and unknown-outcome barriers.
- Continue reading existing runtime stores and batch events. New detailed
  accounting uses an additive versioned event; no backfill or reinterpretation
  of prior events.
- Local aggregate execution accounting remains distinct from separately
  consented persistent telemetry.

## Dependency-aware tasks

| Task | PRD refs | Outcome | Prerequisites | Consumes | Produces | Execution | Verification |
|------|----------|---------|---------------|----------|----------|-----------|--------------|
| role-context | FR-1, AC-1 | Deliver profile-digest-bound role instructions and only the applicable validated shared/specialist context | none | native-request-v2, execution-context-v1, native-profile-digest | role-context-envelope | sequential | Python tests reject stale/missing/mismatched bindings and prove exact role/profile/context content is in the prepared envelope |
| deterministic-prompt | FR-2, FR-3, AC-2, AC-3 | Build fixed-order named prompt components with conservative attempt-history retention, validated artifact references, safe consecutive exact-observation compaction, and visible size failures | role-context | role-context-envelope | deterministic-prompt-components | sequential | Node tests prove distinct and nonconsecutive history retention, validated edit references, exact read/search occurrence counts, mandatory-content preservation, deterministic UTF-8 prompt bytes, and visible limit errors; revalidate against approved PRD v2 |
| request-accounting | FR-4, FR-5, FR-6, AC-4, AC-5, AC-6 | Record per-component/cumulative model-input measurements, calls, tools, retries, elapsed time, and nullable authoritative usage with old-record compatibility | deterministic-prompt | deterministic-prompt-components | versioned-request-accounting | sequential | Python/bridge tests prove component totals, UTF-8 byte values, cumulative counts and retry accounting, null unavailable usage, privacy, version-5 lifecycle and unknown-event replay with v2/v3/v4 compatibility, and legacy runtime-store readability |
| docs-and-integration | FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, AC-1, AC-2, AC-3, AC-4, AC-5, AC-6 | Reconcile architecture/runtime documentation and verify the complete changed path | request-accounting | role-context-envelope, deterministic-prompt-components, versioned-request-accounting | implementation-evidence | sequential | Focused Python and Node tests, relevant full suites, repository validation, PRD/plan validation, and final diff/review evidence |

## Files and scope

- Runtime role/profile path: `skills/sdlc/scripts/execution_profiles.py`,
  `skills/sdlc/scripts/bounded_runtime.py`, and focused tests in
  `tests/test_bounded_runtime.py` and `tests/test_native_execution.py`.
- Prompt and bridge path: `packages/sdlc-runtime/driver.js`,
  `skills/sdlc/scripts/manage_runtime.py`, and
  `packages/sdlc-runtime/test/driver.test.js`.
- Accounting/replay contracts: `skills/sdlc/scripts/execution_orchestration.py`,
  `skills/sdlc/scripts/execution_contracts.py`,
  `skills/sdlc/scripts/execution_state.py`, a new
  `skills/sdlc/contracts/execution-event-v4.schema.json`, the corrective
  `skills/sdlc/contracts/execution-event-v5.schema.json`, and focused
  orchestration/compatibility tests.
- Qualification inventory: `scripts/qualify.py`,
  `qualification/manifest.json`, `tests/test_qualification.py` and the
  runtime installation inventory in `tests/test_runtime_commands.py`.
- Direct documentation: `docs/ARCHITECTURE.md`,
  `docs/EXECUTION-MANAGEMENT.md`, `docs/EXECUTION-ORCHESTRATION.md`, and
  `packages/sdlc-runtime/README.md`.
- Corrective context-lifecycle coverage:
  `packages/sdlc-runtime/test/context-lifecycle.test.js` and
  `tests/test_context_lifecycle.py`, with the freeze enforced in
  `skills/sdlc/scripts/execution_manager.py`.

The repository has no project `.sdlc/config.json` or `.sdlc/memory/` in this
change. They are not delivered files or prerequisites of the runtime feature;
the earlier setup inventory was inaccurate. This corrective iteration does
not add unrelated project-policy scaffolding.

No product changes are planned to model routing, parallel execution,
telemetry consent, result acceptance, native-request schema, UI commands, or
dependencies.

## Corrective iteration

The maintainer requested these corrections after independent review of the
uncommitted implementation. The corrective iteration began against approved
PRD version 1. This plan now references the separately maintainer-approved
version-2 FR-2 / AC-2 amendment. That amendment changes the history acceptance
contract; it does not waive test failures, approve unavailable provider
metrics, or authorize a commit.

1. **FR-1 / AC-1:** reproduce the validation-to-dispatch race through the
   real manager and runtime bridge before fixing it. Reject operator context
   mutation under the manager lock for running, blocked-running and
   unconfirmed native attempts. Prove terminal release and latest-context
   rebinding in the next attempt.
2. **FR-4 / AC-4, FR-5 / AC-5, FR-6 / AC-6:** separate request preparation,
   adapter invocation, completed streams and interruption. Count confirmed
   invocation only after the adapter is invoked; preserve partial observed
   output, unknown-state attribution, exact batch/attempt bindings and local
   completion timing. Keep aggregate-only persistence, null unavailable
   provider values, legacy readability and unknown-work redispatch barriers.
3. **FR-2 / AC-2:** document and test the approved conservative history
   policy. Retain distinct history when deterministic relevance is
   unavailable; use validated artifact references and safe consecutive
   identical read/search compaction without losing mandatory content or
   evidence. Do not introduce speculative deletion or summarization.
4. Run targeted regressions, runtime/orchestration tests, the full Python
   suite, runtime JavaScript tests and checks, repository/artifact validation,
   qualification manifest verification and final diff checks. Obtain a fresh
   independent review. Do not commit, push or create a pull request.

These are corrections within the existing runtime boundary, not a new
orchestrator. Context freezes do not hold a file lock across provider waits.
Unknown work deliberately keeps the freeze until confirmed through the
existing native receipt boundary. New accounting versions must retain old
readers in the current implementation; rollback preserves retained history
and uses a compatible reader rather than rewriting records.

### History acceptance decision

PRD version 2 supersedes the version-1 requirement to prove that only
continuation-relevant history is included. When relevance cannot be
established deterministically, retain distinct tool history from the current
bounded attempt. Use validated artifact references where required information
and evidence remain available. Only consecutive exactly identical read/search
observations may be compacted into an unchanged observation with an exact
occurrence count, preserving order. Distinct or nonconsecutive observations
and edit/execute outcomes are not collapsed by that rule.

Task instructions, mandatory requirements, security constraints and acceptance
evidence remain mandatory. No relevance classifier, speculative deletion,
semantic compression of mandatory content, or LLM summarizer is introduced.
Conservatively retained history can exhaust the prompt bound; fail visibly
with an actionable explanation instead of dropping content. No minimal-history
or token-savings claim is made.

The maintainer's explicit approval of PRD version 2 changes the acceptance
contract, not the test result. AC-2 must be reassessed against the amended
requirements using fresh tests and independent review. This amendment does
not resolve or accept the unexplained Windows cancellation failures.

## Security and operational considerations

Role and context remain untrusted model input, not authority. The model may
receive only the manager-validated role and applicable context. Runtime
stores and manager events contain bounded aggregate numbers and identifiers,
never prompt text, transcripts, source code, or command output. Existing
explicit runtime/batch consent and manager checks remain in force.

The change is opt-in through existing runtime commands and finite bounds.
On rollback, preserve any version-4 accounting events and new runtime-store
records; do not delete or reinterpret them. Keep version-aware readers
available until retained records can be inspected with a compatible release.
No data backfill or destructive migration is planned.

## Review and verification strategy

Review correctness and scope, security/privacy, serialized-contract
compatibility, performance/accounting semantics, and maintainability.
Measure deterministic fixture prompt bytes before and after without claiming
token savings. Run:

```text
node --test packages/sdlc-runtime/test/driver.test.js
python -B -m unittest tests.test_bounded_runtime tests.test_native_execution tests.test_execution_orchestration tests.test_execution_management tests.test_execution_telemetry -v
npm --prefix packages/sdlc-runtime run check
npm --prefix packages/sdlc-runtime test
python -m unittest
python scripts/validate.py
```

Provider usage and cost remain null unless a supported host API exposes
authoritative values. No live model call is needed or authorized for
verification.
