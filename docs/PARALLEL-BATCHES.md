# Two isolated project batches

The optional runtime command **SDLC: Run Two Isolated Batches** runs the
existing finite batch controller for exactly two independent local projects.
It is not shared-worktree parallelism, a global scheduler, or automatic task
acceptance.

## Preparation

1. Prepare independent checkouts or worktrees yourself and open both as
   local workspace folders. Each needs its own enabled manager policy,
   approved plan and controls, installed specialist profiles and exact
   finite batch definition.
2. Keep dependencies inside their existing project plan. Do not select
   projects that depend on each other's unaccepted work or shared editable
   resources. The command does not infer cross-project independence.
3. Optionally use [task-aware model planning](MODEL-ROUTING.md) to materialize
   each batch's exact model choices before preview and consent.
4. Invoke the command, select exactly two folders and review their resolved
   roots. Identical directories, aliases to the same directory and
   parent/child roots are rejected.
5. Review each project's existing exact batch/model/brief/limit confirmation.
   Neither worker starts until both confirmations have completed.

Declining group confirmation writes no approval. If you approve the first
exact batch but decline the second, no workers start; the first explicit
approval remains recorded rather than being erased.

## Execution and safety

At most two per-project serial loops run. Each retains its own immutable
plan, specialist roster/context, manager writer, dependency/ownership checks,
finite attempts and cumulative budgets. All exact model IDs must be available
in the IDE and permitted by that project's current controls.

Cancellation of either progress notification or a worker failure requests
local cancellation of both loops. The extension waits for both to settle
before accepting another runtime command. Already observed requests and
output remain attributable. Local cancellation does not prove remote
termination, remove unknown-work barriers or authorize redispatch. Inspect
both manager histories after interruption.

Completion is still an unaccepted worker report. Each project's separate
operator judgment remains mandatory before dependent work or acceptance.
The existing project dashboard/Gantt continues to show its own plan,
specialists, context, observed intervals and acceptance state; this command
does not create a combined global timeline.

This is a cooperative same-user boundary, not a filesystem sandbox against
external replacement of project directories. Existing confined tools and
atomic compare-and-swap edits still apply. No shell/execute capability,
automatic worktree creation, automatic policy adoption, extra telemetry,
provider SDK, release or deployment is introduced.

## Compatibility and measurements

Single-worker and single-batch commands are unchanged. No manager, controls,
event, runtime-store or finite-batch format changes are required.

The concurrency budget is two active project workers and no unbounded queue.
Each project retains its existing finite limits; the group does not impose
an authoritative monetary cap. Use existing accounting and the
[offline baseline toolkit](../benchmarks/README.md) for your own observations.
Synthetic tests demonstrate bounded overlap and independent receipts, not
production throughput, economic improvement or token savings.
