---
type: implementation-plan
prd-path: docs/prds/staged-execution-orchestration.md
prd-id: staged-execution-orchestration
prd-version: 3
---

# Project-level orchestration

Implement approved PRD `staged-execution-orchestration`, version 3, as one
opt-in vertical outcome using the existing plan contract, manager writer,
native controller, and dashboard. Activities reuse specialist role names;
context remains manager-owned and non-authoritative; the Gantt uses declared
estimates and recorded manager event times without inventing observations.
Keep old record and task-result versions readable, add new versions
additively, and add no dependencies or second scheduler.

| Task | PRD refs | Outcome | Prerequisites | Consumes | Produces | Execution | Verification |
|------|----------|---------|---------------|----------|----------|-----------|--------------|
| preserve | FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15, FR-16, FR-17, FR-18, FR-19, AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15, AC-16, AC-17, AC-18, AC-19 | Preserve all approved existing execution and dashboard behavior | none | none | compatibility-baseline | sequential | Existing execution, controls, orchestration, runtime, insight, renderer, native bridge, and dashboard tests pass unchanged |
| project-decomposition | FR-20, FR-21, AC-20, AC-21 | Teach the control plane to plan 10 to 20 major activities for substantial projects without padding smaller work, and reuse specialists across activities | preserve | approved-prd, execution-plan-contract | orchestration-instructions | sequential | Focused narrative and evaluation tests prove large-project decomposition, concise small plans, dependency and verification coverage, and repeated specialist assignments |
| manager-context | FR-22, FR-23, AC-22, AC-23 | Add bounded, attributed, plan-bound shared and per-specialist context, preserve old records, and propagate context through digest-bound native requests and worker results | preserve | execution-manager-v3, task-result-v1, native-request-v1 | execution-manager-v4, task-result-v2, native-request-v2 | sequential | Python contract, migration, manager, native request, stale-binding, size-limit, replay, and real bridge tests prove old-version compatibility and that context cannot approve or accept work |
| ownership-safety | FR-24, AC-24 | Prove same-project unresolved-work serialization and exact-path conflict rejection remain in force across execution IDs | preserve | execution-manager-start-boundary | ownership-safety-evidence | sequential | Isolated manager tests reject overlapping active ownership across executions and show disjoint plans remain valid after serialized-work barriers are resolved |
| gantt-projection | FR-25, AC-25 | Provide a shared dependency-aware relative-time Gantt model for draft plans, live state, and final reports with estimate and observation provenance | preserve | execution-plan-contract, execution-state-v3 | execution-gantt-model | sequential | Python tests cover estimates, dependencies, parallel groups, observed intervals, running work, missing values, invalid state, and escaped Markdown |
| dashboard-gantt-context | FR-26, AC-26 | Add the Gantt and shared/per-agent context to the explicitly selected native manager view with accessible text and explicit refresh | manager-context, gantt-projection | execution-gantt-model, manager-context-view | accessible-live-gantt | sequential | Dashboard and Python bridge tests cover plan/live/final modes, keyboard access, semantic names, text alternatives, empty/error states, explicit refresh, no auto-dispatch, and export compatibility |
| integrate | FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15, FR-16, FR-17, FR-18, FR-19, FR-20, FR-21, FR-22, FR-23, FR-24, FR-25, FR-26, AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15, AC-16, AC-17, AC-18, AC-19, AC-20, AC-21, AC-22, AC-23, AC-24, AC-25, AC-26 | Synchronize contracts, documentation, qualification scope, memory, and final evidence | project-decomposition, manager-context, ownership-safety, gantt-projection, dashboard-gantt-context | orchestration-instructions, execution-manager-v4, task-result-v2, native-request-v2, accessible-live-gantt | project-orchestration-complete | sequential | Validate PRD and plan; run focused red/green tests, all relevant Python and dashboard suites, repository validation and static checks; inspect the full branch diff and review evidence |

## Interface and compatibility decisions

- Existing execution-plan version 1 remains authoritative. Its per-activity
  `assignment.agent`, estimate, dependencies, and exact file ownership already
  express a reusable specialist roster without a new agent-per-task model.
- New manager context adds schema version 4 and is stored with the execution
  record under the existing manager writer. Versions 1 through 3 are read
  unchanged. A context write upgrades only through the manager's validated
  write path; unsupported older readers fail closed on version 4.
- The version-4 record adds a `context` object with schema version, monotonic
  context revision, one shared entry, and entries keyed by specialist role.
  Each entry stores bounded content, source (`operator` or `worker`), author,
  update time, source plan revision, and content digest. Context writes bind
  the current plan digest and context revision; stale writes fail.
- Task results add version 2 with an optional bounded context note. Version-1
  worker results remain valid. Worker notes are attributed and unaccepted.
- Native requests add version 2 to bind the latest shared and role-specific
  context into the request digest. Version-1 native requests remain readable
  only when no context has been recorded for that execution.
- The Gantt is one shared projection over an immutable plan and manager state.
  Planned offsets are relative estimates, not calendar commitments. Actual
  intervals come only from recorded manager events; unknown durations remain
  unknown. Dependency and assignment rules are visible, and the Gantt does
  not schedule or dispatch work.
- The existing manager bridge remains the sole writer and owner of approvals,
  context, ownership checks, execution events, and independent acceptance.
  Opening or refreshing a view never dispatches work.
- No transcript, prompt, raw output, secret, billing data, model-cost claim,
  or unsupported host observation is added to context or Gantt data.

## Risk and rollback

No existing plan or record is rewritten by import or read. Context-bearing
records are additive version 4; prior record formats and task results remain
readable. New context writes are atomic manager transactions. Reverting code
must preserve version-4 records and must not silently downgrade them. New UI
paths remain opt-in through the existing explicit manager selection. Live
provider, billing, remote cancellation, and human assistive-technology
qualification remain separate claims requiring their own direct evidence.
