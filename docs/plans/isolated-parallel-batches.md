---
type: implementation-plan
prd-path: docs/prds/staged-execution-orchestration.md
prd-id: staged-execution-orchestration
prd-version: 3
---

# Two isolated finite batches

## Contract and scope

Expose exactly two independent, explicitly selected local project batches
through the existing runtime extension. Preserve each project's current
manager, finite serial controller, exact consent, model choices, cumulative
bounds, unknown-work protection and independent acceptance. Parallelism is
only across resolved, nonoverlapping project directories, never two workers
in the same project or a shared editable checkout.

This implements the approved staged PRD's ownership, finite execution and
reusable-specialist requirements without changing manager authority. The
maintainer authorized autonomous implementation and ordinary reviewed merges.
No automatic worktree creation, shared scheduler/store, cross-project
dependency inference, automatic approval/acceptance, provider experiment,
deployment, new dependency or economic-improvement claim is introduced.

The new explicit `sdlc.runtime.runParallelBatches` command shares the existing
extension busy latch. It requires a trusted local workspace, exactly two
selected file-backed workspace folders and canonical directory separation.
Reject identical filesystem directory identities and parent/child roots.
Display the resolved roots and independence requirement before starting either
batch. Each project then retains its existing exact batch/model/digest/budget
confirmation. Declining a selection/confirmation cancels the group; an already
authorized sibling stops locally without fabricated remote-stop evidence.

Reuse `runBatchCommand` with optional internally supplied folder and group
abort controller. The existing per-project serial loop is unchanged. At most
two such loops exist. Failure or cancellation requests sibling cancellation;
wait for both loops to settle before releasing the busy latch. Expose errors
explicitly and preserve both projects' manager histories. No retry crosses
project boundaries or unknown outcomes. Independent projects retain their
existing context/roster and dashboard/Gantt; this is not a combined global
timeline or a way to evade same-project prerequisites.

## Compatibility, verification and reversal

No persisted format changes. The single-worker and single-batch commands keep
their names and behavior. The new command is opt-in and uses existing VS Code
QuickPick, modal confirmation and progress components, with descriptive
accessible names and keyboard cancellation.

Concurrency budget: exactly two selected roots and at most two active
per-project serial workers; no pending unbounded queue. Each retains the
existing finite batch and per-attempt limits. Measure repeated synthetic
two-root trials, peak adapter concurrency, calls and local duration/resource
observations without claiming production throughput or cost improvement.
Test root aliases/nesting, denied trust/remote hosts, declined consent, busy
state, independent receipt attribution, cancellation and failure propagation.
Exercise the rendered native command in an isolated development host with
synthetic provider/file-selection seams, keyboard and accessibility snapshots;
never attach to the user's existing editor session or call a real provider.

The boundary remains cooperative same-user safety, not a filesystem sandbox
against arbitrary external directory replacement. Existing manager/path
checks and atomic edits remain authoritative. Removing the additive command
and internal group path reverses exposure without erasing any execution
history, changing policy or migrating state.

## Dependency-aware tasks

| Task | PRD refs | Outcome | Prerequisites | Consumes | Produces | Execution | Verification |
|------|----------|---------|---------------|----------|----------|-----------|--------------|
| isolation | FR-7, FR-8, FR-24, AC-7, AC-8, AC-24 | Lock and test explicit two-root isolation and consent | none | none | parallel-contract | sequential | Red command-availability and root/consent boundary tests |
| execution | FR-2, FR-6, FR-9, FR-14, FR-18, AC-2, AC-6, AC-9, AC-14, AC-18 | Reuse two finite serial controllers with shared cancellation and bounded settlement | isolation | parallel-contract | parallel-command | sequential | Actual Python managers plus synthetic model adapters; concurrent starts, independent unaccepted receipts and group stop/error |
| interaction | FR-15, FR-19, AC-15, AC-19 | Deliver the explicit native command without automatic dispatch | execution | parallel-command | parallel-interface | sequential | Existing runtime tests, keyboard/native-host interaction and accessible labels/states |
| regression | FR-1, FR-3, FR-4, FR-5, FR-10, FR-11, FR-12, FR-13, FR-16, FR-17, FR-20, FR-21, FR-22, FR-23, FR-25, FR-26, AC-1, AC-3, AC-4, AC-5, AC-10, AC-11, AC-12, AC-13, AC-16, AC-17, AC-20, AC-21, AC-22, AC-23, AC-25, AC-26 | Preserve formats, context, specialist reuse, independent acceptance and project Gantt | interaction | parallel-interface | parallel-delivery | sequential | Full runtime tests/syntax, exact-head Python CI, repository/PRD/plan/manifest checks, independent review; existing live qualification limits remain explicit |

## Files and review

Change runtime extension/package registration, focused runtime tests and
runtime/orchestration documentation. Add no installed Python helper or schema.
Review isolation, consent and failure/cancellation/accounting boundaries,
single-command regression, native accessibility and concurrency saturation.
Public decisions remain in this plan and documentation, not root `.sdlc/`.

## Verification checkpoint

The complete runtime suite passed 66 tests before two additional alias and
second-consent regression cases, which also passed. Three synthetic
two-manager trials each reached exactly two overlapping adapters and retained
separate unaccepted receipts. Pre-start cancellation invoked neither adapter;
active cancellation preserved unknown status and observed request attribution
in both managers. A reproduced already-cancelled-token propagation defect was
fixed without changing any original timeout or assertion.

The final complete suite passed all 68 tests, zero skips or failures, in
84.121 seconds, and runtime syntax checks passed. In that run the three
successful two-root trials took 3.975 to 4.541 seconds after fixture creation,
each with two synthetic calls and exactly two overlapping adapters. Recorded
Node CPU/heap deltas are local observations, exclude Python child resources
and are not peak-memory or production-throughput measurements. Fresh
independent read-only review found no significant code issues. Repository,
PRD, plan, installed manifest and diff checks also passed.

Native rendered-interface qualification was initially blocked on
2026-11-12 and the first retry on 2026-11-13: the shared
`vscodeinsiders-updating` mutex prevented development-host startup after the
editor's own approximately 31-second wait. No shared updater or user editor
was stopped and no lock was bypassed.

After the maintainer completed the update, current-build VS Code Insiders
1.147.0-insider (build prefix `54ab79431a`, Electron 43.8.6) started a
separate development host on 2026-11-13. Fresh disposable projects, an isolated
profile and disabled non-test extensions prevented interference with normal
editor use. Only external model discovery/response and batch file selection
were synthetic; production commands, native QuickPick/custom dialogs,
progress notifications, Python managers and execution records were real.

The following actual rendered checks passed:

- The named multi-select exposed both project paths, checkbox states and
  keyboard arrow/space/Enter selection. Escape restored editor focus and
  dispatched zero requests.
- The group dialog exposed its roots and independence/remote-stop warnings.
  Escape rejected it without requests. Both exact batch dialogs displayed
  their own project, current digests, model IDs, limits and billing caveats.
  Declining the second dispatched neither worker.
- Native custom-dialog mode was tested at 800 by 600 and approximately
  1440 by 900. Screenshots and DOM geometry showed contained dialogs,
  wrapping paths/digests, vertical scrolling for long consent text and
  visible action buttons. Keyboard focus, Cancel, Escape and restoration
  were exercised with reduced motion enabled.
- Scoped automated DOM checks passed for dialog role, existing accessible
  label targets, named actions and viewport containment. Accessible snapshots
  exposed selection, consent, progress/cancel and completion/error states.
  This is scoped integration evidence, not a whole-editor accessibility audit.
- Both exact approvals produced two synthetic adapter calls, maximum overlap
  two and zero real-provider calls. Each actual manager retained one start
  and one received result, with no completion/validation acceptance.
- A separate fresh-project trial cancelled one rendered progress control.
  Both managers retained `unknown`, one observed iteration and no
  `TASK_CANCELLED`, completion or validation event. The error notification
  warned against redispatch; reopening the selector verified busy-latch
  release after settlement.

Trial elapsed times of 17.986 seconds for completion and 24.408 seconds for
cancellation include interactive consent and are not performance benchmarks.
The host's Windows OS-dialog rendering could not be inspected with the
available browser tool, so the supported custom-dialog mode was selected only
in the disposable profile. OS-dialog-specific behavior and a physical screen
reader were not qualified; no host API or production setting was changed.
An earlier reused-fixture trial was excluded from dispatch evidence because
its tasks were already reported. A cancellation-host restart also encountered
a transient occupied debug port; a verified unused port resolved it.

The original native-startup blocker is resolved for the tested current build
and custom-dialog configuration. This evidence does not explain or resolve
the separate historical Windows cancellation investigation, qualify remote
termination or billing, or establish native custom-profile/pin execution.

After these checks, the complete unchanged runtime suite passed again:
68 tests, zero skips or failures, 95.447 seconds on Windows. Runtime syntax,
plan, repository, manifest and diff checks also passed. Test-owned hosts and
debug endpoints were closed; no user editor or updater was terminated.
