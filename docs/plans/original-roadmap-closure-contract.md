# Original roadmap closure change contract

## Outcome

Complete the remaining original execution-roadmap behavior in one opt-in
vertical slice: finite autonomous dispatch through the existing manager and a
native manager-connected dashboard that can inspect and safely act on current
manager state.

## Target user and benefit

Maintainers using the optional local execution manager can let a precisely
approved finite schedule continue through independent runnable tasks and can
inspect or control one explicitly selected execution without leaving the IDE.

## Acceptance criteria

1. The new autonomous policy is separately versioned and disabled by default.
   One explicit batch confirmation binds the approved plan, execution policy,
   controls generation, exact tasks, finite attempts, exact permitted models,
   runtime bounds, and cumulative bounds. The existing serial controller may
   continue independent runnable tasks and retries only inside that approval.
   It stops before an unaccepted prerequisite, unknown work, unresolved stop
   intent, pause, or exhausted bound. It never accepts a worker result or
   approves a plan or controls policy. (`FR-18`, `AC-18`)
2. The dashboard keeps the existing export viewer and adds explicit
   project/execution selection, native task detail and filters, progress, and
   manager event updates that run only after the user explicitly starts live
   updates for the selected view. (`FR-15`, `FR-19`, `AC-15`, `AC-19`)
3. Dashboard plan/control approval, acceptance, pause/resume, and cancellation
   intent reuse manager APIs, require explicit confirmation bound to displayed
   current digests, and revalidate under the existing writer before mutation.
   Acceptance requires a separate user-supplied judgment; worker declarations
   are insufficient. Opening either dashboard view starts no worker and
   enables no live polling. (`FR-19`, `AC-19`)
4. Existing manual, supervised, version-3 batch, export, policy, storage,
   and default-disabled behavior remains compatible. New state is bounded and
   retains no prompts, transcripts, or raw outputs. Unsupported remote stop
   and authoritative spend limits remain explicitly unavailable. (`FR-1`,
   `FR-2`, `FR-6`, `FR-7`, `FR-8`, `FR-9`, `FR-10`, `FR-11`, `FR-12`,
   `FR-13`, `FR-14`, `FR-16`, `FR-17`, `AC-1` through `AC-14`, `AC-16`,
   `AC-17`)

## Non-goals

- SDKs, provider lock-in, paid calls, credentials, global installation,
  releases, automatic acceptance, automatic plan/control approval, or policy
  adoption.
- Arbitrary shell execution, autonomous plan generation, concurrent shared
  worktree edits, daemon/background service, or forced editor restart.
- Remote cancellation, authoritative model billing, monetary spend caps,
  automatic history discovery, or exposing prompts/transcripts/raw outputs.
- Replacing or weakening the existing read-only export commands.

## PR boundary

Versioned execution controls and the existing bounded batch controller;
existing manager APIs and their fixed Python bridge; the optional VS Code
dashboard extension; related contracts, tests, documentation, and
qualification inventories. No unrelated runtime, provider, or deployment
surface.

## Invariants and interfaces

- The existing manager remains the sole writer and attempt ledger. No second
  scheduler, daemon, worker authority, or independent approval store.
- Autonomous mode uses a new explicit controls version. Existing manual,
  supervised, and version-3 batch inputs retain their current meanings.
- Every dispatch remains serial and exact-batch-bound. Only manager-confirmed
  failed receipts can authorize a preapproved retry.
- Dependencies require an already independently recorded acceptance. The
  controller may skip blocked tasks to run independent tasks, but it does not
  create judgments.
- Bounded batch receipts cannot carry runtime-command verification evidence.
  Their results are accepted only through a separately versioned acceptance
  (`urn:sdlc:execution-acceptance:2`) in a version-3 record: the operator
  supplies independent revision, command and summary bound to the exact task,
  attempt, result ID and result digest, with complete criteria and no
  blockers. Worker statuses are never treated as passed and a worker-reported
  failure requires a new attempt. This is the same mandatory operator
  acceptance gate; version-1 acceptance semantics are unchanged.
- Every consumer of a recorded acceptance keeps its provenance. Reports
  replay with the record's own version and label a version-2 acceptance as
  independent operator validation bound to the result digest. Snapshots move
  to version 2 (`urn:sdlc:execution-snapshot:2`, task `acceptanceBasis`) only
  when such an acceptance exists, so version-1 readers fail closed; other
  executions keep byte-identical version-1 snapshots and reports. The live
  view carries `acceptanceBasis`, and analysis accepts record versions 1-3.
- Dashboard confirmations are pinned to the explicit selection epoch, the
  displayed digests and the acted-on task state, not to the identity of the
  last refresh. Polling is suspended during confirmation, acceptance input and
  the write, then resumes only when it was enabled and the view is visible.
- Live reads are confined to an explicitly chosen trusted local workspace and
  execution ID. Only structured manager metadata is rendered.
- Mutations pass current digest bindings to manager operations and are
  revalidated under the manager writer, including a control-state digest that
  changes with pause, cancellation, or approval state. A displayed snapshot
  is not authority.
- Cancellation records intent only. Pause blocks new starts and does not stop
  a running remote operation. Unknown work stays a barrier.
- No new dependency or configuration file. Absence of project SDLC config
  continues to mean the existing default behavior.

## Repository evidence and constraints

- `docs/prds/staged-execution-orchestration.md` and
  `docs/plans/staged-execution-orchestration.md` describe the approved staged
  roadmap. Their current version-1 forms do not include an autonomous mode and
  define the dashboard as an export/read-only surface.
- `skills/sdlc/scripts/execution_controls.py` already validates an
  unqualified `autonomous` label but only configures manual, supervised, and
  version-3 batch controls. It explicitly reports autonomous capability as
  false.
- `skills/sdlc/scripts/execution_orchestration.py` owns finite batch approval,
  dependencies, retries, and serial attempt selection. Its current behavior
  stops on the first unaccepted dependency or result.
- `skills/sdlc/scripts/execution_manager.py` owns the writer, plan approval,
  independent acceptance, task state, pause and cancellation intent.
- `skills/sdlc/scripts/execution_insights.py` exports a signed read-only
  snapshot; `packages/sdlc-dashboard` displays selected exports only.
- Node tests and Python tests are already established. The dashboard and
  runtime packages use Node built-ins and VS Code APIs; no added dependency is
  required.
- Project root is `C:\dev\sdlc`, branch is
  `feature/original-roadmap-closure`, and the starting revision was clean
  `b0e4eb788dca56e625d4e31bdc7aa80d6265174f`.
- No `.sdlc/config.json`, project memory, or project standards file exists.
  The existing configuration absence is intentionally preserved. Repository
  conventions are taken from `AGENTS.md`, `CONTEXT.md`, `CONTRIBUTING.md`,
  package manifests, CI, and existing tests.

## Risk and rollback

This is a significant local permission/control and native UI change. New
autonomous execution remains opt-in; digest-bound explicit consent, bounded
serial dispatch, manager revalidation, and failure barriers are required.
Dashboard actions cannot bypass manager validation. Revert the feature branch
to remove the new mode and UI; persisted version-4 controls history must remain
inspectable and must not be silently downgraded by older code.

## Approval

The maintainer's explicit instruction in the implementation request on
2026-11-02 is the approval source only for the outcome and acceptance criteria
above. It does not approve SDK/provider/credential/billing/remote-stop,
automatic acceptance, unbounded execution, or any other behavior excluded
here.
