---
type: implementation-plan
prd-path: docs/prds/staged-execution-orchestration.md
prd-id: staged-execution-orchestration
prd-version: 1
---

# Staged execution orchestration

Build optional execution management around the working control plane.
Keep legacy workflows/configuration and merged version-1 data contracts intact.

| Task | PRD refs | Outcome | Prerequisites | Consumes | Produces | Execution | Verification |
|------|----------|---------|---------------|----------|----------|-----------|--------------|
| authority | FR-1, FR-2, FR-4, FR-8, FR-13, AC-1, AC-2, AC-4, AC-8, AC-13 | Public requirements and locked optional interfaces | none | none | roadmap-contract | sequential | PRD and plan validate; baseline recorded |
| local | FR-1, FR-2, FR-4, FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, AC-1, AC-2, AC-4, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13 | M1 replayable local execution and reports | authority | roadmap-contract | local-preview | sequential | State, writer, approval, receipt and report tests plus full qualification |
| supervised | FR-1, FR-2, FR-3, FR-7, FR-8, FR-9, FR-12, AC-1, AC-2, AC-3, AC-7, AC-8, AC-9, AC-12 | M2 bounded profiles and qualified host delegation | local | local-preview | supervised-runtime | sequential | Installation, ownership, evidence and real host receipt checks |
| controlled | FR-5, FR-6, FR-10, FR-13, FR-14, AC-5, AC-6, AC-10, AC-13, AC-14 | M3 verified routing, attempts and lifecycle controls | supervised | supervised-runtime | controlled-runtime | sequential | Inventory, policy exhaustion, consent, cancellation and restart tests |
| views | FR-11, FR-12, FR-15, FR-16, FR-17, AC-11, AC-12, AC-15, AC-16, AC-17 | M4 qualified optional dashboard and analytical proposals | controlled | controlled-runtime | complete-roadmap | sequential | UI transport/accessibility/security and reproducible analytics/proposal checks |

## M1 interface and storage boundary

New policy is a separate project-local `.sdlc/execution-policy.json`; absence
means disabled. M1 supports explicitly recorded manual work, not worker
dispatch. New policy/state/receipt formats have separate versioned identities.

Use pure initial-state/replay and read-only rendering. Manager operations
explicitly import plans, approve current plan/policy bindings, record manual
attempts/receipts and independent acceptance judgments, inspect recovery
barriers and explicitly delete one selected record.

Keep immutable revisions and logically append-only event history in one
bounded atomic execution record, protected by a single-writer lock. Whole-file
replacement is physical storage; earlier logical event entries cannot be edited
through manager operations. Derived state is rebuilt by replay, not trusted as
an independent snapshot. Corrupt records or incomplete writes fail closed;
never automatically truncate, steal a lock or redispatch unknown work.

Exact portable API: `initial_execution_state(plan)` and
`replay_execution(plan, events, receipts=None, policy_digest=None,
acceptances=None, approvals=None)`. Events preserve the existing schema;
separately versioned records retain receipt and controller-judgment bindings.
Replay rejects privileged events without corresponding manager records.
The revision stores the consent snapshot, events and keyed receipts,
acceptances and approvals. A policy consent generation changes on every
explicit configure, including restoring earlier settings. Existing execution
approval cannot revive after disable/re-enable. A changed policy requires a
new immutable plan revision and new approval.

Manager functions are `configure_policy(root, policy, dry_run=False)`,
`import_plan(root, plan)`, `inspect_execution(root, execution_id)`,
`approve_plan(root, execution_id, plan_digest, policy_digest)`,
`record_task(root, execution_id, task_id, action, attempt_id=None, reason=None)`,
`receive_result(root, execution_id, result_id, brief, result)`,
`accept_task(root, execution_id, acceptance)`, and
`delete_execution(root, execution_id)`. No arbitrary event append is public.
Manual acceptance records have version, task/attempt/result identity, complete
criteria, checked revision, command and summary. They declare an independent
operator judgment; they neither run a command nor prove evidence quality.
All manual attempts are serialized across execution IDs in the same project.
Under the writer lock, start validates peer records for unresolved work; record
deletion cannot release unresolved claims. Receipt identities and attempt IDs are
unique across execution revisions. Capacity: at most 256 execution records
per project, and 256 revisions, events
per revision and receipts/decisions per revision, and 2 MiB canonical bytes
per authoritative record. Exhaustion is an explicit failure without pruning.

Reuse existing strict contracts and compatible local path/reparse/Git-ignore
patterns. Existing metrics/run-record helpers are not rewritten. Policy
consent is rechecked inside the writer lock. No automatic export/cleanup.

M1 additions: `execution_state.py`, `execution_manager.py`,
`manage_execution.py`, `execution_renderers.py`, new strict policy/record/
acceptance contracts, corresponding tests and `EXECUTION-MANAGEMENT.md`.
Update only required exact inventories, qualification and architecture links.
M2-M4 public interfaces are locked at their integration seams before coding.

## M2 native execution boundary

Use the [supervised native flow](../NATIVE-EXECUTION.md): opt-in host-neutral
roles, collision-safe project profile installation, separately approved
digest-bound requests, one actual native host invocation and attributable
receipts reconciled by the existing manager. No SDK is required. Preserve
manual execution policy and all existing version-1 formats; progress markers
bind native requests without adding event types or granting worker authority.
VS Code packaging is the first supported format, not evidence that all hosts
or models have identical tools, routing, cancellation or background execution.
Actual host qualification remains necessary before M2 acceptance.

## M3 portable controls boundary

The [execution controls](../EXECUTION-CONTROLS.md) slice provides separately
approved manual attempt limits, escalation checks, persistent pause and
cancellation-intent barriers, read-only reconciliation, and pure resolution
of supplied model inventory/pricing. These portable checks can be verified
while live host qualification is blocked. They do not qualify supervised or
autonomous mode, host cancellation, effective runtime routing or billing.

## Safety, verification and reversal

New execution is opt-in; detailed telemetry is separately disabled. Approval
and evidence acceptance are explicit cooperative controller judgments, never
inferred from worker data. Serial edits and exact canonical ownership claims
protect the shared-worktree path. Actual host/tool/model capabilities require
live qualification before delegation or optimization is claimed.

Use red/green behavior assertions, focused tests during implementation and
one fresh full regression/qualification gate per milestone. Public branches
and draft PRs remain independently reviewable or explicitly stacked.
Do not merge, release or activate policy automatically.

Reversal removes milestone code and inventories together while preserving
retained local data for version-aware inspection. No destructive reset,
global skill refresh or private management dependency is introduced.
