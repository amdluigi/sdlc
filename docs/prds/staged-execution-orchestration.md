---
type: prd
id: staged-execution-orchestration
status: approved
version: 3
---

# Product requirements: Staged execution orchestration

## Problem and context

The inactive execution contracts are available, but users need a complete
approved local execution flow and progressively qualified automation.
Deliver usable milestones while preserving existing workflows by default.

## Target users and benefit

Users gain inspectable local plans, approvals, task receipts, reports and
optional qualified delegation, controls, dashboards and historical proposals.

## Outcome

Deliver opt-in execution management and a project-level orchestration
experience. A substantial project is planned as a reviewable set of major
activities, assigned across a reusable specialist roster, with shared context,
per-agent context, safe ownership, and one Gantt view from proposal through
execution and final review. Preserve the existing staged execution, manager,
and host safety boundaries.

## Goals

- Preserve current workflows, evidence gates and controller/worker boundaries.
- Deliver coherent milestones with current tests and qualified integrations.
- Make failures, blocked activation and missing host observations explicit.
- Make a large feature's activity plan, dependencies, shared context, and
  progress understandable in one project-level view.
- Reuse a small specialist roster across activities instead of creating one
  agent session per activity.

## Non-goals

- Wholesale skill rewrites or automatic runtime activation.
- Concurrent shared-worktree edits without approved isolation.
- Global execution databases, automatic policy adoption, merges or releases.
- Guaranteed cost savings, fabricated observations or skipped validation.

## User scenarios

1. A user explicitly enables local policy, imports and approves a plan,
   records manual attempts/results and inspects an execution report.
2. A user explicitly selects autonomous mode, approves one exact finite batch,
   and lets the existing controller continue only work within that approval.
3. A user explicitly opens a manager-connected dashboard for one selected
   project and execution, reviews current task details, and performs
   digest-bound manager actions.
4. A stale approval, failed evidence, unknown worker or conflicting ownership
   blocks automation without repeating a possibly running operation.
5. A qualified host executes bounded work; unavailable capabilities remain
   explicit blockers rather than simulated successful dispatch.
6. A user separately approves telemetry, runtime limits and analytical policy
   proposals before they take effect.
7. For a substantial feature, a user reviews a plan of major activities,
   approves the assignments and dependencies, and sees specialist roles reused
   across those activities.
8. Each worker receives current shared project context and its role-specific
   context. Context notes remain bounded, attributed, visible to other workers,
   and separate from approval or acceptance.
9. A user inspects one Gantt view before execution, while work is in progress,
   and after completion. Unknown estimates and actual intervals stay visibly
   unknown rather than being fabricated.

## Functional requirements

- **FR-1**: Preserve legacy workflow/configuration and default-disabled execution.
- **FR-2**: Preserve independent controller judgments; workers cannot approve.
- **FR-3**: Provide bounded opt-in agent profiles and collision-safe installation.
- **FR-4**: Manage immutable plan revisions, local event history and safe replay.
- **FR-5**: Resolve permitted model profiles using verified host inventory,
  distinguishing requested and observed identities and missing pricing.
- **FR-6**: Permit retries/escalation only within explicitly approved limits.
- **FR-7**: Enforce dependencies, evidence and ownership; serialize edits.
- **FR-8**: Bind explicit approval to current plan and policy; reapprove changes.
- **FR-9**: Track task/attempt state, failures and independent result acceptance.
- **FR-10**: Preserve estimate/timing provenance and unavailable observations.
- **FR-11**: Render safe task tables and Markdown/Mermaid execution views.
- **FR-12**: Link execution reports to, not replacing, existing SDLC handoff.
- **FR-13**: Keep attributed telemetry separately consented and existing
  anonymous measurement/evaluator records independent.
- **FR-14**: Provide bounded modes, pause/cancel and safe restart reconciliation.
- **FR-15**: Provide an optional native manager-connected dashboard with
  explicit project and execution selection, task details, filters, progress,
  live manager events, and confirmed manager-mediated actions.
- **FR-16**: Analyze explicitly selected confined local records reproducibly.
- **FR-17**: Produce inactive estimate/routing proposals requiring explicit adoption.
- **FR-18**: Provide a separately enabled finite autonomous mode that dispatches
  only preapproved tasks, attempts, models, and bounds through the existing
  sole-writer controller, continuing independent runnable tasks while stopping
  at any prerequisite that lacks an independent acceptance judgment.
- **FR-19**: Revalidate dashboard approvals, acceptance judgments, pause/resume,
  and cancellation intent against current manager state; opening the dashboard
  alone must not enable live updates or start work.
- **FR-20**: For a user-identified substantial project, decompose the scope
  into 10 to 20 independently reviewable major activities when the scope
  supports it. Do not pad smaller projects to meet a count.
- **FR-21**: Assign activities to a reusable specialist roster; a specialist
  may own multiple activities, and the number of agents need not equal the
  number of activities.
- **FR-22**: Maintain bounded, attributed shared project context and
  per-specialist context under the execution manager's existing writer
  boundary. Limit each note to the existing 2048-character execution-text
  bound. Make current context readable by the orchestrator and every delegated
  worker, without granting context any approval authority.
- **FR-23**: Let the manager record worker-reported context separately from
  operator-authored context. Bind context reads and writes to the selected
  execution and current plan, reject stale updates, and preserve previous
  records without interpreting worker notes as accepted evidence.
- **FR-24**: Prevent conflicting active file ownership across tasks and
  executions in the same project before dispatch, while preserving the
  existing exact-path and manager-lock checks.
- **FR-25**: Provide a single time-scaled Gantt projection for proposed,
  active, and completed project plans. Show dependencies, declared estimates,
  observed intervals, and current status; label unknown or incomplete timing
  rather than inventing calendar dates or observations.
- **FR-26**: Make the Gantt and shared context available in the optional
  manager-connected dashboard with accessible names, keyboard-operable
  selection, readable text alternatives, and explicit refresh behavior.

## Acceptance criteria

- **AC-1** (`FR-1`): Disabled execution writes nothing; old regressions and
  configuration semantics pass unchanged.
- **AC-2** (`FR-2`): Worker artifacts cannot invoke approval or progression judgments.
- **AC-3** (`FR-3`): Dry-run/collision/copy/link parity and actual harmless
  worker/tool-boundary host trials demonstrate supported profiles.
- **AC-4** (`FR-4`): Replay, immutable revisions, duplicate/conflicting receipts,
  competing writers, corrupt/truncated inputs and interrupted writes are tested.
- **AC-5** (`FR-5`): Absent/disallowed models, ignored preferences and missing
  prices are tested; effective routing requires attributable host observations.
- **AC-6** (`FR-6`): Exhausted/denied retries, spend and environment failures
  never trigger uncontrolled loops or implicit escalation.
- **AC-7** (`FR-7`): Unmet dependencies/evidence, case/path aliases, shared
  resources and absent concurrency policy block dispatch.
- **AC-8** (`FR-8`): Explicit manager approval binds plan/policy digests;
  changed bindings and worker-spoofed approval declarations fail.
- **AC-9** (`FR-9`): Lifecycle transitions reject invalid orders and reported
  completion is not accepted without an explicit independent judgment.
- **AC-10** (`FR-10`): Timing distinguishes declarations from observations and
  rejects impossible values without replacing missing data with zero.
- **AC-11** (`FR-11`): Exact reports cover pending approval, blocked/failed
  attempts, unknown estimates, incomplete critical paths and escaped labels.
- **AC-12** (`FR-12`): Reports preserve failed/unavailable evidence and cannot
  authorize PR, release or deployment readiness.
- **AC-13** (`FR-13`): Execution opt-in leaves telemetry/measurement/evaluation
  off; revocation, attribution ambiguity and duplicate windows are tested.
- **AC-14** (`FR-14`): Pause blocks new work; unsupported cancellation stays
  pending and restart does not redispatch unknown non-idempotent attempts.
- **AC-15** (`FR-15`): The native dashboard supports explicit selection,
  task details and filters, progress, explicitly enabled live manager events,
  accessible interactions, and digest-bound manager actions while preserving
  the existing read-only export viewer.
- **AC-16** (`FR-16`): Analytics inspect only selected confined records and
  preserve insufficient/missing data and quality/rework context.
- **AC-17** (`FR-17`): Proposals retain provenance, cannot mutate policy, and
  require explicit approval or rejection.
- **AC-18** (`FR-18`): Autonomous mode is opt-in and versioned, preserves
  manual/supervised/batch behavior, requires current plan and controls
  approval plus per-batch digest consent, enforces finite attempt/model/runtime
  limits, continues independent runnable tasks, and stops before unaccepted
  dependencies or any unconfirmed/unknown work. Workers cannot accept results
  or approve plans or controls. A bounded result is accepted only by a
  separately versioned operator validation bound to its exact result digest;
  worker verification is never treated as passed, and an accepted result then
  allows its dependents to dispatch through the same controller.
- **AC-19** (`FR-19`): Live dashboard reads occur only for an explicitly
  selected project and execution. Live updates require an explicit command.
  Consequential actions require user confirmation and current digest binding;
  stale views are rejected under the existing manager writer, and opening any
  dashboard view never dispatches work. Unchanged live reads never invalidate
  an open confirmation or report a false failure after a successful write;
  polling is suspended during confirmation and mutation, and a changed
  selection invalidates the pending action.
- **AC-20** (`FR-20`): Large-project planning examples produce 10 to 20
  distinct, outcome-oriented activities with dependencies and verification;
  small-project examples remain concise and contain no filler activities.
- **AC-21** (`FR-21`): Contract and controller tests demonstrate that the same
  specialist may be assigned to multiple activities, while unrelated task
  count does not force additional agent sessions.
- **AC-22** (`FR-22`): Shared and per-specialist context can be read by a
  prepared delegated worker, is bounded and attributed, and is included in
  the digest-bound request without changing approval or acceptance state.
- **AC-23** (`FR-23`): Manager tests cover operator and worker-reported notes,
  stale plan/context bindings, invalid or over-2048-character content,
  persistence and replay. Worker notes remain unaccepted and cannot approve a
  plan or task.
- **AC-24** (`FR-24`): Isolated competing starts with overlapping paths are
  rejected before dispatch, including across execution IDs. Disjoint paths
  remain valid planned ownership, while the existing serialized-work barrier
  stays in force until an earlier unresolved task is resolved.
- **AC-25** (`FR-25`): Renderer and dashboard tests show one Gantt for a
  proposal, an active execution, and a final execution report; dependencies,
  estimates, actual intervals, and unknown values retain their provenance.
- **AC-26** (`FR-26`): Dashboard tests and runtime checks prove keyboard
  operability, accessible task names and text alternatives, explicit refresh,
  empty/error states, and no dispatch from opening the Gantt.

## Data, permissions, privacy, and security

Execution and detailed telemetry are disabled by default. Structured metadata
is local only, under safe Git metadata or proven ignored project-local storage.
Context notes are bounded local metadata, not transcripts. No code, secrets,
raw prompts/transcripts or raw command-output retention.
Titles, paths and verification descriptions may still be sensitive metadata.
Retain records until explicit deletion; no automatic deletion/export.
Automation requires explicit concurrency, timing, attempts and spend policies.
Local controller operations are a cooperative same-user boundary, not an OS
sandbox against a malicious filesystem owner.

## Constraints and dependencies

Preserve the merged version-1 contracts and all legacy helper behavior.
The portable runtime remains standard-library-only. New optional packages
require explicit dependencies and qualification.
Real host/model/cancellation/usage/UI transport availability must be verified
before advertising or activating those capabilities. Actual adoption of
policy, runtime activation, publication of arbitrary worker changes, release
and deployment require their own scoped authority.

## Success measures

Every criterion needs current automated and applicable integration/live-host
evidence. Explicitly report incomplete milestones and blocked external gates.
No speed or savings claim is justified without comparable quality evidence.

## Open decisions

None block portable prerequisite work. Concrete host/build, permitted models,
runtime limits, spend basis, telemetry and dashboard transport are deferred
activation decisions that block their respective activation/completion claims.

## Approval

- Status: Approved
- Approver: Maintainer
- Evidence: Version 1 was approved for the safe default-disabled baseline on
  2026-11-01. Version 2 added finite autonomous dispatch and the native
  manager dashboard. The maintainer explicitly approved the clarified
  project-level orchestration scope on 2026-11-02, including major activities,
  reusable specialist assignments, shared and per-agent context, ownership
  protection, and one Gantt view across planning, execution, and review.
- Approved version: 3
