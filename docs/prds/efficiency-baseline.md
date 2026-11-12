---
type: prd
id: efficiency-baseline
status: draft
version: 1
---

# Product requirements: SDLC efficiency baseline

## Problem and context

The reliable execution foundation merged in
[amdluigi/sdlc#43](https://github.com/amdluigi/sdlc/pull/43) provides validated
context delivery, deterministic prompts and attributable local request
accounting. It does not establish a comparable efficiency baseline or prove
token or cost savings.

The current VS Code adapter consumes model response text but does not expose
authoritative input, output, cached or billable token usage, actual cost or
an enforceable monetary cap. Existing null values are intentional, not zero
consumption. See the [runtime documentation](../../packages/sdlc-runtime/README.md)
and [accounting boundary](../EXECUTION-ORCHESTRATION.md).

The official [VS Code API declarations](https://github.com/microsoft/vscode/blob/main/src/vscode-dts/vscode.d.ts),
checked on 2026-11-12, expose `LanguageModelChatResponse.stream` and `.text`,
not request usage or billing. `countTokens` counts supplied text or messages;
it is not evidence of actual provider input, cached tokens or billing.

Measurement must precede optimization and intelligent orchestration. This
PRD covers the baseline stage only. The maintainer endorsed version 1 and
its proposed protocol on 2026-11-12. That approval does not supply a usage
source, spending policy or independent quality judgments.

## Target users and benefit

Maintainers evaluating SDLC execution changes need reproducible, attributable
usage and quality evidence before choosing optimizations or more autonomous
behavior.

## Outcome

Produce a reproducible baseline over an explicitly approved representative
task set, with authoritative usage where available, measured execution
behavior and independent quality assessment. Incomplete evidence is reported
as incomplete, never as measured savings or permission to advance the roadmap.

## Goals

- Fix the task set, source revision, execution configuration and quality
  rubric before collecting baseline results.
- Keep provider usage, prompt bytes, observed calls, duration and cost
  distinct and attributable to the same executions.
- Include failures, cancellations and unknown outcomes rather than reporting
  only successful runs.
- Preserve existing consent, finite limits, privacy and independent
  acceptance boundaries.
- Make absent usage or quality evidence a visible decision gate.

## Non-goals

- Context-reduction changes, alternative-model experiments or claims that an
  optimization is cheaper.
- Task-aware model selection, decomposition, parallel specialists, new
  orchestration services or changes to manager authority.
- A new provider integration, credential setup or paid benchmark calls under
  this draft.
- Estimating provider token consumption or savings from prompt bytes,
  tokenizer estimates or unrelated coding-session usage.
- Resolving or closing the separate Windows cancellation investigation.
- Enabling persistent telemetry or changing existing metric or qualification
  schemas to store benchmark data.

## User scenarios

1. A maintainer approves representative tasks and a quality rubric, then
   collects comparable executions with exact configuration and revision
   provenance.
2. A host supplies complete authoritative request-level usage; measurements
   are attributed without double counting retries or cached input.
3. Usage is absent, partial, duplicated or cannot be bound to the execution;
   the report exposes the gap and refuses a complete token or cost total.
4. An execution is fast but its deliverable fails independent validation;
   that quality failure remains visible alongside its consumption.
5. A task reaches an unknown outcome or cancellation; observed accounting
   remains attributable without a successful receipt or accepted task.

## Functional requirements

- **FR-1**: Identify an immutable, versioned task manifest and source
  revision. Each task has a bounded objective, permitted actions, acceptance
  criteria, verification procedure and independent quality rubric. Record
  the model requested, effective model when authoritatively known, host
  version, execution bounds, repetitions and relevant configuration.
- **FR-2**: Collect request-level authoritative input/output tokens and,
  where exposed, cached and billable tokens, with inspectable source and
  coverage provenance. Bind observations to the exact execution, task,
  attempt and request. Reject duplicate or mismatched observations rather
  than double counting or silently assigning them elsewhere.
- **FR-3**: Report provider tokens separately from local UTF-8 prompt/input
  and output bytes. Missing values remain null. Cached tokens are not
  subtracted from transmitted input or reclassified as billable tokens.
  Partial usage must not be presented as complete execution totals.
- **FR-4**: Report observed model invocations, retries, handoffs, tool
  iterations, elapsed duration and terminal outcome using explicit,
  predeclared definitions. Count only observed handoffs, not inferred ones.
  Distinguish adapter invocation from provider receipt and stream completion
  from successful task acceptance. Include all relevant attempts, including
  failed, interrupted and unknown work. A retry is an additional
  manager-approved attempt after the initial attempt; a tool iteration is a
  dispatched tool operation, including an error. A handoff is an observed
  task/role transfer to another worker attempt, not a tool call. Unobservable
  handoffs remain null. Attempt-duration sums are separate from observed
  end-to-end elapsed time.
- **FR-5**: Report actual cost only when authoritative usage and applicable
  billing evidence establish that cost, with currency and scope. Otherwise
  cost remains null. Public list prices or an assumed model choice do not
  establish an actual bill. A required spend bound must be enforceable before
  any new paid execution is authorized.
- **FR-6**: Independently assess each deliverable against the predeclared
  rubric and acceptance evidence. The producing worker cannot validate its
  own quality or accept its own task. Preserve quality failures, missing
  assessments and evidence limitations in the baseline report.
- **FR-7**: Baseline reporting is explicitly opt-in and separate from
  persistent telemetry and existing host qualification. Retain only the
  approved aggregate measurements, configuration metadata and validated
  evidence references needed for reproducibility. Do not retain raw prompts,
  transcripts, responses, source code, command output, credentials or account
  data in aggregate artifacts. Do not modify manager records or grant
  execution authority through imported measurements.
- **FR-8**: Produce an evidence-based baseline readiness decision. A complete
  token/cost comparison requires comparable task/configuration coverage and
  authoritative usage for the claimed scope; quality conclusions require
  independent assessments. Missing evidence blocks the corresponding claim.
  Offline fixtures are labeled synthetic and cannot satisfy the live
  measurement gate. No optimization, routing or parallel-agent milestone
  advances automatically from a structural validator or passing fixture.

## Acceptance criteria

- **AC-1** (`FR-1`): Manifest/configuration validation proves stable task and
  revision binding, finite repetition/bound definitions and complete
  acceptance/rubric fields. Changing the workload or execution configuration
  creates a separately identified cohort, not a silently comparable result.
- **AC-2** (`FR-2`, `FR-3`): Focused tests cover exact attribution,
  duplicate/mismatch rejection, repeated requests and retries, complete and
  partial usage, distinct cached/billable fields and absent values remaining
  null. A real authoritative observation must be traceable before a live
  provider-usage result is claimed.
- **AC-3** (`FR-4`): Tests and representative executions verify cumulative
  durations, calls, tools, retries and handoffs under their declared
  definitions, including interruption and unknown outcomes. No successful
  acceptance or confirmed remote delivery is inferred from local completion.
- **AC-4** (`FR-5`): Tests reject unsupported actual-cost claims and preserve
  null unavailable cost. Before paid runs, the approved budget, enforcement
  mechanism and stop behavior are demonstrated; inability to enforce a
  required cap blocks execution.
- **AC-5** (`FR-6`): Every baseline task has a frozen rubric and independently
  recorded assessment or an explicit missing-assessment status. Worker
  receipts alone cannot satisfy quality or manager acceptance.
- **AC-6** (`FR-7`): Tests verify opt-in behavior, aggregate-only persistence,
  invalid-input rejection and no raw-content or credential retention.
  Existing telemetry consent, execution/acceptance behavior and legacy
  artifacts remain unchanged.
- **AC-7** (`FR-8`): The report clearly separates measured, partial,
  unavailable and synthetic evidence. Incomplete usage or quality prevents
  a complete efficiency conclusion. No token-savings claim is derived from
  bytes, and later roadmap milestones remain separately gated.

## Data, permissions, privacy, and security

Use synthetic or explicitly approved public task inputs; private management
context and sensitive data must not be sent to a provider. External usage
records are untrusted inputs and require validation and exact attribution.
An aggregate report is not an execution, consent or acceptance authority.

Any future benchmark artifact must have its own explicitly approved data and
retention contract. Do not broaden private local metrics or sanitized host
qualification records to accommodate benchmark identifiers or model metadata.
Normal task artifacts and independently inspectable evidence remain separate
from aggregate measurements. Never request secrets in a specification or
report.

## Constraints and dependencies

- Preserve the approved
  [token-efficiency-foundation v2](token-efficiency-foundation.md), manager
  authority, existing immutable plans and finite execution limits.
- No production implementation begins from this draft. Provider integration,
  artifact shapes and implementation sequencing require the approved
  baseline contract first.
- No new paid benchmark calls, provider changes, credential access or
  monetary authorization are inferred from the unattended roadmap request.
  Preparation uses no new provider spend.
- Reuse existing request accounting, tests and validation where their
  semantics fit; do not reinterpret existing telemetry or qualification data
  as benchmark usage.
- Preserve [amdluigi/sdlc#42](https://github.com/amdluigi/sdlc/issues/42) as an
  open, unexplained Windows investigation. Passing tests do not establish a
  cause or fix.
- Optimization follows a credible baseline. Model routing and parallel
  orchestration require later, separately approved contracts and evidence.

## Success measures

Baseline success means reproducible provenance, complete coverage for each
claimed measurement and independently assessed quality. It is not a reduction
in tokens or cost. Report per-task observations, repetition counts, failures,
missingness and suitable aggregate distributions without pooling incompatible
cohorts or hiding unknown attempts.

The proposed initial protocol is five synthetic or public task categories,
with five repetitions of each under one fixed configuration: a focused bug
fix, a small additive validation change, a regression-test task, a
documentation consistency task, and a multi-step read/search/edit task.
Create and freeze the exact fixtures and acceptance evidence before collecting
results. These 25 proposed executions are not measured runs or monetary
authorization; an exhausted budget produces an explicitly incomplete cohort, not a
post-hoc reduction of the required sample.

The proposed independent rubric records pass/fail/unavailable separately for
requirement correctness, verification evidence, security/boundary compliance
and scope compliance. All mandatory task criteria must pass for that
deliverable to pass; a missing assessment is not a pass. Reviewers assess
artifacts independently of the producing worker, with configuration labels
hidden where practical. The baseline report records failures as observations
rather than excluding them. It does not record manager acceptance on a
reviewer's behalf.

## Open decisions

| Decision | Owner | Blocks approval | Resolution |
|----------|-------|-----------------|------------|
| Authoritative usage source and exact execution/request attribution | Maintainer | yes | Unresolved; current adapter supplies text, not authoritative usage. |
| Export-only or live collection, budget, consent and enforceable spending boundary | Maintainer | yes | Unresolved; no new paid calls authorized during preparation. |

## Approval

- Status: Draft
- Approver: Maintainer
- Evidence: Explicit approval of the attached version 1 and a request to
  continue execution were received on 2026-11-12. A subsequent request for
  the usage source and spending boundary could not obtain those inputs.
- Approved version: 1, requirements and proposed protocol endorsed

The explicit endorsement is recorded, not treated as missing approval.
The artifact remains draft for implementation gates because the two
approval-blocking operational decisions above are still unresolved. No
provider, export, spend authorization or quality result is inferred from
endorsement. Until those inputs exist, preparation makes no new provider
calls or expenditure. The measured baseline and later milestones remain
blocked, not complete.
