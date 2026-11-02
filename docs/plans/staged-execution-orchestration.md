---
type: implementation-plan
prd-path: docs/prds/staged-execution-orchestration.md
prd-id: staged-execution-orchestration
prd-version: 2
---

# Original roadmap closure

Complete the approved original roadmap scope as one opt-in vertical slice.
Use the existing Python manager, versioned controls, sole writer, exact finite
batch controller, native VS Code APIs, and standard Node/Python libraries.
Do not add an SDK, dependency, daemon, or second scheduler. Existing version-1
manual data, version-2 supervised controls, version-3 batch behavior, and
read-only export commands remain compatible.

| Task | PRD refs | Outcome | Prerequisites | Consumes | Produces | Execution | Verification |
|------|----------|---------|---------------|----------|----------|-----------|--------------|
| preserve | FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-16, FR-17, AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-16, AC-17 | Lock backward-compatibility evidence for existing contracts, controls, reports, and disabled defaults | none | none | compatibility-evidence | sequential | Existing focused controls, manager, orchestration, runtime, insight, and export-view tests pass unchanged |
| autonomous | FR-6, FR-7, FR-8, FR-9, FR-14, FR-18, AC-6, AC-7, AC-8, AC-9, AC-14, AC-18 | Add explicit version-4 autonomous controls and bounded independent-task continuation through the existing controller | preserve | compatibility-evidence | autonomous-manager-contract | sequential | New Python tests prove default-off, policy validation, exact digest binding, independent runnable tasks, retries, dependency judgment barrier, pause/cancel/unknown barrier, and unchanged version-3 scheduling |
| dashboard | FR-1, FR-2, FR-9, FR-11, FR-12, FR-15, FR-19, AC-1, AC-2, AC-9, AC-11, AC-12, AC-15, AC-19 | Add selected manager-connected native tree, explicit live updates, accessible detail/filter/progress, and confirmed manager actions alongside the export viewer | autonomous | autonomous-manager-contract | live-manager-dashboard | sequential | Node UI tests plus real Python manager/filesystem bridge tests cover selection, filters, events, stale bindings, unchanged-poll confirmation stability, selection-change invalidation, write/poll races, approvals, digest-bound independent acceptance, pause/cancel, hidden-view polling shutdown, selection-change/refresh-failure polling shutdown, errors, and export compatibility |
| integrate | FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15, FR-16, FR-17, FR-18, FR-19, AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15, AC-16, AC-17, AC-18, AC-19 | Synchronize documentation, schemas, qualification inventory, and final focused evidence | autonomous, dashboard | autonomous-manager-contract, live-manager-dashboard | original-roadmap-closure | sequential | Validate PRD/plan/schema/manifests; run runtime and dashboard Node suites serially, focused Python tests after final text normalization, static checks, and final diff review |

## Interface and compatibility decisions

- Controls schema version 4 uses `mode: "autonomous"` and the same closed,
  finite task/call/tool-call/wall-time/input/output bounds as batch mode.
  Version-4 controls storage retains prior version-1, version-2, or version-3
  state. There is no implicit migration or downgrade.
- Autonomous dispatch writes a version-3 execution manager record with a
  separately versioned start marker bound to the exact approved batch,
  attempt brief and model. Existing version-2 retry/accounting events remain
  version 2. Version-1/2 records and event meanings are unchanged; readers
  that do not understand version 3 fail closed.
- Autonomous work reuses the existing exact batch definition and approval
  digest. The current sole-writer controller continues serially across
  independent runnable tasks and receipt-bound preapproved retries. It skips
  tasks waiting on unaccepted prerequisites and stops when no independent
  work is runnable. Version-3 batch mode keeps its current stop-on-first-wait
  behavior.
- A fixed dashboard bridge exposes only manager inspection, plan/control
  approval, independent acceptance, pause/resume, and cancellation-intent
  operations. Each write is checked by the existing manager under its writer
  lock against current plan, policy, controls policy and control-state
  digests, task, attempt, and result bindings.
- The export viewer and its commands remain unchanged in meaning. A separate
  explicit native live view is selected by workspace and execution ID. Live
  polling is opt-in and read-only; opening either view does not poll or
  dispatch.
- The dashboard displays only bounded structured metadata. It does not retain
  prompts, transcripts, or raw outputs. Host cancellation and spend enforcement
  remain unavailable and are not represented as supported.

## Risk and rollback

No execution plan is migrated. The new controls and manager-record versions
are additive; prior control state and version-1/2 event meanings are retained,
and old readers fail closed on new manager records. Runtime failures remain
unknown barriers. Reverting code must not discard or reinterpret version-4
controls or version-3 execution records. No live host qualification is
claimed by Node mocks; manager bridge tests exercise the real local manager
and filesystem boundaries.
