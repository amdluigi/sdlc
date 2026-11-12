---
type: prd
id: token-efficiency-foundation
status: approved
version: 2
---

# Product requirements: SDLC token efficiency foundation

## Problem and context

The execution manager validates a selected role and binds a context snapshot
to each bounded request, but the runtime prompt currently omits those
instructions and context. The model therefore may not receive the
task-specific guidance that the manager prepared. Prompt construction is also
not deterministic by component or explicit about which execution history is
necessary. Request accounting does not distinguish prompt components or
provider-reported usage. Existing byte limits measure bytes, not tokens.

## Target users and benefit

Maintainers and operators using the opt-in local bounded runtime gain
role-correct task execution and transparent, privacy-conscious measurements
of each model request.

## Outcome

Each bounded model request uses a deterministic prompt built from validated
task, role, context, requirements, constraints, tools, and conservatively
retained execution history, and produces attributable request-level efficiency
accounting without claiming unavailable token usage or cost.

## Goals

- Deliver the selected validated role instructions and only the applicable,
  digest-bound shared and specialist context selected by the execution
  manager to the model.
- Construct a deterministic prompt from identifiable required components.
- Preserve execution history needed for correct continuation. Retain distinct
  tool history from the current bounded attempt when relevance cannot be
  established deterministically. Prefer validated artifact references and
  safely compact consecutive identical read/search observations without
  losing their contents, order, occurrence count, or acceptance evidence.
- Preserve mandatory requirements and fail visibly rather than truncate or
  semantically compress required content when prompt limits are exceeded.
- Account cumulatively for prompt bytes by component, total input and output
  bytes, calls, tool iterations, retries, elapsed time, and available
  model/provider usage across the bounded execution.
- Preserve existing execution, approval, acceptance, privacy, and telemetry
  boundaries, including readability of existing persisted records.

## Non-goals

- Automatic model routing, parallel task execution, a new orchestration
  service, cache service, dependency, or model call.
- LLM-based prompt summarization or unsupported claims of token savings.
- Changing execution-manager authority, approval flows, task acceptance,
  bounded limits, or unknown-outcome handling.
- Storing raw prompts, transcripts, source code, or command output in
  aggregate telemetry.

## User scenarios

1. An operator approves an existing bounded task. The worker receives the
   selected role instructions, task brief, and current shared and
   role-specific context validated by the manager.
2. The context is missing, stale, invalid, or inconsistent with its digest;
   preparation fails rather than falling back to generic instructions.
3. Required prompt content exceeds the supported prompt limit; execution
   stops with an actionable error rather than silently dropping content.
4. The host does not expose usage or authoritative pricing; the corresponding
   measurements remain unavailable rather than being estimated.
5. Prior tool results or evidence are needed to continue a task; the prompt
   preserves the result or a validated artifact reference. When relevance
   cannot be established deterministically, distinct tool history from the
   current bounded attempt is retained rather than speculatively deleted.

## Functional requirements

- **FR-1**: The bounded runtime delivers exactly the content selected and
  validated by the execution manager: the selected role identity and profile
  digest, its corresponding role instructions, the shared context revision
  and digest, and only the applicable specialist context and its digest.
  Missing, stale, invalid, or mismatched bindings are rejected. The worker
  does not independently select or reconstruct alternative role or context
  content.
- **FR-2**: The runtime constructs a deterministic prompt from the mandatory
  protocol, task objective and approved brief, selected role instructions,
  relevant shared and specialist context, mandatory requirements and
  acceptance criteria, security and policy constraints, permitted tools and
  actions, and execution history. History preserves information needed for
  correct continuation and acceptance. When relevance cannot be established
  deterministically, distinct tool history from the current bounded attempt
  is retained. Validated artifact references are preferred over repeated full
  contents only when they preserve the information needed for correctness,
  security, and acceptance. Consecutive exactly identical read/search
  observations may be represented by one unchanged observation with an exact
  occurrence count, preserving order. Distinct or nonconsecutive observations
  and edit/execute outcomes must not be collapsed by this rule. Task
  instructions, mandatory requirements, security constraints, and acceptance
  evidence must not be removed or semantically compressed. No speculative
  history deletion or LLM summarization is permitted. If the complete prompt
  exceeds its supported limit, fail visibly with an actionable explanation
  rather than silently truncating content.
- **FR-3**: The runtime removes only exact duplicate content when safe,
  preserves all mandatory prompt content, and visibly rejects prompts that
  exceed supported limits with an actionable explanation. It never silently
  truncates or semantically compresses mandatory content.
- **FR-4**: The runtime reports cumulative bounded-execution accounting with
  these semantics:
  - Prompt bytes by component are UTF-8 byte lengths of the exact component
    text sent on each model call. Repeated components are counted again on
    every call; per-component totals cover all calls in the bounded execution.
  - Total input bytes are UTF-8 bytes of the model-facing prompt content
    transmitted by the runtime, summed across all calls. They do not claim to
    measure host/provider wrappers or provider-processed input.
  - Output bytes are UTF-8 bytes of model response text and tool-result
    content accounted by the bounded runtime, cumulatively across all calls
    and tool iterations.
  - Model calls count every model request in the bounded execution, including
    requests after tool results. Tool iterations count each dispatched tool
    operation, including one that returns an error. Retries count additional
    manager-approved attempts after the initial attempt; batch totals cover
    all dispatched attempts. Elapsed time covers the bounded execution,
    including model waits and tool iterations; batch totals aggregate attempt
    durations without representing them as wall-clock time between attempts.
  - Model and host/provider identifiers are reported only when available.
    Provider-reported input and output tokens are kept separate from
    transmitted bytes and are aggregated across all calls only when the
    provider reports them authoritatively. Cached input tokens and billable
    input/output tokens are separate provider-reported values; cached tokens
    are not subtracted from processed or transmitted values.
  - Authoritative cost is reported only when supplied by an authoritative
    usage/pricing source. Unavailable token, cached-token, billable-token, or
    cost values remain null. Partial provider observations are not presented
    as complete execution totals. No token count is inferred from bytes.
- **FR-5**: Local bounded-execution accounting and persistent telemetry remain
  separate. Local accounting may retain aggregate measurements needed for
  execution limits and reporting, but never raw prompts, transcripts, source
  code, or command output. Persistent telemetry remains subject to existing
  consent and privacy controls. The execution manager remains the authority
  for execution state, approvals, and acceptance; worker receipts do not
  automatically accept tasks.
- **FR-6**: Existing persisted plans, execution records, receipts, and
  telemetry records remain readable and valid. Any required schema change
  uses backward-compatible evolution or an explicit versioned migration and
  does not silently reinterpret existing data.

## Acceptance criteria

- **AC-1** (`FR-1`): Runtime and manager-boundary tests prove the prompt
  contains exactly the manager-validated selected role identity,
  profile-digest-bound instructions, shared-context revision and digest, and
  applicable specialist-context content and digest. Tests prove that the
  worker cannot select or reconstruct alternative context and that missing,
  stale, invalid, or mismatched role/context bindings are rejected.
- **AC-2** (`FR-2`): Prompt tests prove deterministic component ordering and
  conservative history retention. They show that distinct tool history from
  the current bounded attempt is retained when relevance cannot be
  established deterministically; validated artifact references preserve
  required information; and relevant tool results and acceptance evidence
  remain available. Tests prove that only consecutive exactly identical
  read/search observations are safely compacted, retaining the unchanged
  observation, its order, and its exact occurrence count. Distinct and
  nonconsecutive observations and edit/execute outcomes are not collapsed by
  this rule. Task instructions, mandatory requirements, security constraints,
  and acceptance evidence are neither removed nor semantically compressed.
  Exceeding a supported prompt limit fails visibly with an actionable
  explanation and no silent truncation. No speculative deletion or LLM
  summarization is introduced.
- **AC-3** (`FR-3`): Tests prove safe exact-duplicate removal does not remove
  meaningful content, mandatory content is never silently truncated or
  compressed, and over-limit required content produces a visible failure.
- **AC-4** (`FR-4`): Tests verify UTF-8 per-component and total transmitted
  input byte accounting across multiple model calls, repeated components,
  tool iterations, and approved retries; cumulative output bytes, model/tool
  call counts, retry counts, elapsed durations, and model/provider identity
  are accounted according to the stated definitions. Provider-reported
  input/output, cached, and billable tokens remain distinct from bytes and
  one another; absent or partial usage and non-authoritative cost are not
  represented as complete totals or estimated.
- **AC-5** (`FR-5`): Tests verify local accounting contains aggregate
  measurements only and no raw prompt, transcript, source code, or command
  output; persistent telemetry remains consent-gated. Existing manager
  approval, independent acceptance, bounded execution, and unknown-outcome
  behavior remains unchanged.
- **AC-6** (`FR-6`): Compatibility tests prove existing persisted plans,
  execution records, receipts, and telemetry records remain readable and
  valid. Any changed schema is backward-compatible or has an explicit,
  tested versioned migration, with no silent reinterpretation of old data.

## Data, permissions, privacy, and security

The execution manager remains the authority for execution state, context
validation, approval, and task acceptance. Role and context content are
untrusted model input and do not grant approval or execution authority. The
worker receives the manager-selected, digest-validated role and applicable
context; it cannot choose or reconstruct a different snapshot. Local
bounded-execution accounting may retain aggregate measurements needed for
execution limits and reporting, but never raw prompts, transcripts, source
code, or command output. Persistent telemetry remains separately subject to
existing consent and privacy controls. Provider token and cost values are
recorded only when authoritative values are available; otherwise they remain
unavailable. Transmitted bytes, provider-processed tokens, cached tokens,
and billable tokens are not interchangeable.

## Constraints and dependencies

- Preserve strict role/profile digest validation and current context
  revision/digest checks.
- Preserve existing bounded runtime limits and versioned execution
  contracts, including backward compatibility for existing plans, execution
  records, receipts, and telemetry records.
- Reuse existing prompt, accounting, telemetry, and execution structures
  where practical; add no external dependencies or model calls.
- The VS Code model host may not expose provider usage or authoritative
  pricing. Tool history and required prompt content may exceed supported
  limits; such cases must fail visibly rather than discard required content.

## Success measures

Behavioral acceptance criteria and accurate request-level byte accounting
define success. Before/after prompt bytes may be reported for deterministic
fixtures. No token savings or cost reduction is claimed without measured,
authoritative evidence.

## Open decisions

None. Provider usage and pricing remain unavailable when the host does not
expose authoritative values. Persistent telemetry remains subject to
existing consent.

## Approval

- Status: Approved
- Approver: Maintainer
- Evidence: Explicit maintainer approval of the version-2 FR-2 / AC-2
  amendment in the conversation on 2026-11-12.
- Approved version: 2
- Previous approval: Version 1 was explicitly approved by the maintainer
  in the conversation on 2026-11-12.
- Superseded requirement: Version 1 required proof that only
  continuation-relevant history was included. Version 2 permits conservative
  retention when relevance cannot be established deterministically, without
  weakening mandatory-content preservation or execution limits.
