---
name: sdlc-evaluator
description: 'Use only when a maintainer explicitly asks to audit or review completed sdlc-orchestrated work after the fact (friction, recurring corrections, or whether a targeted instruction change to sdlc or a delegated skill is warranted). Never load as a side effect of any other skill trigger, and never load mid-task: it is strictly post-execution and has no role in live development work.'
license: MIT
metadata:
  category: process
  architecture: standalone
  version: "1.0.0"
---

# SDLC Evaluator

Act as an auditor of the `sdlc` control plane and its delegated skills,
never as a participant in a live development task. Load only when a
maintainer explicitly invokes this skill to review a bounded window of
completed work. Never load as a side effect of any other skill's triggers,
and never act mid-task.

This skill is standalone: it is not part of the `sdlc` bundle, ships with
no `sdlc-capability.json`, and is not discovered or counted by the
bundle's manifest tooling. It reuses the bundle's existing, already-
validated scripts by relative path rather than duplicating them.

## Inputs, all required, none inferred

1. **Run records**: `.git/sdlc/runs/*.json` or `.sdlc/local/runs/*.json`
   conforming to `urn:sdlc:run-record:1`
   (see `../sdlc/contracts/run-record.schema.json`), for the window the
   maintainer names. A run record carries no timestamp by design, so name
   the window as an explicit list of task IDs; refuse to proceed on an
   unbounded request ("everything") and ask for specific task IDs instead.
2. **Requirement artifacts**: the committed PRD/plan/handoff packets for
   each task in the window, read at their existing paths, never
   reconstructed from memory.
3. **Delta artifacts**: merged PR review threads, commit history, and CI
   results for each task's PR, read through the host's existing tooling.

Run `python ../sdlc/scripts/evaluate_runs.py extract --project-root <root>
--task <task-id> [--task <task-id> ...]` first, once per named task ID.
It performs every reduction over run records mechanically (never a raw-log
read) and returns one normalized digest: per-module closed-enum counts, a
bounded set of deduplicated evidence gaps and blocker messages, and
`selfCheck`/`outcome` aggregates. Reason only over that digest plus the
requirement and delta artifacts named above. Do not open other projects'
run records, and do not re-derive counts from raw records by hand; the
digest is the audited surface, so recompute it with the script again
rather than editing or estimating it.

If a task's `outcome` block is still absent, ask the maintainer whether
the task's PR was human-corrected during review before treating that task
as clean; do not infer `humanCorrected: false` from silence. When the
maintainer confirms a correction, record it first with
`python ../sdlc/scripts/manage_runs.py set-outcome --project-root <root>
--task <task-id> --human-corrected true --reference <PR-review-thread-URL>`
so the same evidence is available to future evaluation runs, then continue
the audit using the refreshed digest.

## Analysis rules

- Every friction-log entry cites at least one run record `task.id` and at
  least one evidence or outcome reference. An entry with no reference is
  not a finding; state it as an open question instead.
- Assign root cause to exactly one of two buckets per entry:
  - **Routing failure (control plane)**: `sdlc` resolved the wrong
    module, a trigger did not fire that should have, a self-check did not
    catch a gap it should have, or configuration/replacement resolution
    produced an outcome inconsistent with what the project declared.
  - **Execution failure (specialized skill)**: the correctly-resolved
    module ran and its own output was what a human corrected; the control
    plane routed correctly, but the specialist's instructions or
    reasoning were the problem.
  A single incident may have both; report each cause against the
  component actually responsible, never against `sdlc` merely because it
  orchestrated the task.
- One occurrence is an observation, not a pattern. Do not propose a
  targeted diff from a single run record unless the same friction recurs
  across at least two independent tasks, or the one occurrence is a
  correctness bug regardless of frequency (for example, a self-check that
  provably failed to catch a gap it was designed to catch).
- A targeted diff is a minimal, quoted addition, modification, or deletion
  against the exact current text of the affected skill's own
  instructions, never a rewrite or a restatement of the whole file. If the
  current text cannot be quoted because the file was not read, do not
  propose a diff; report the gap instead.
- Never propose disabling a safeguard to resolve friction caused by that
  safeguard firing correctly; propose narrowing its trigger or wording
  instead, and say which.

## Output contract

Always return exactly these three sections, in this order.

### Friction Log

One row per finding: `task.id` references, the module(s) involved, and a
one-line description of the stall, hallucination, or human correction,
each with its evidence reference.

### Root Cause

For each Friction Log entry, state routing failure or execution failure
(never both without splitting the entry), the component responsible, and
the confidence (low, medium, or high) given the available evidence. State
"insufficient evidence" rather than guessing when references do not
support either bucket.

### Targeted Diffs

For each entry with at least medium confidence and at least two
independent occurrences (or one provable correctness bug), a minimal
quoted diff against the named skill's current instructions, with a
one-line rationale tying it back to the specific Friction Log entry it
addresses.

## Non-authority

This skill never edits `.sdlc/config.json`, never edits another skill's
instructions directly, never runs a script other than the two read-only
extraction and reconciliation helpers named above, and never merges
anything. Every proposed diff is a recommendation for a human to carry
through the project's ordinary review and PR flow.

## Stop signals

Stop and re-check when reasoning becomes:

- "This happened once, but it's clearly a pattern."
- "The fix is obvious, so I don't need to quote the current text."
- "The control plane orchestrated this task, so it's a routing failure by
  default."
- "The maintainer didn't give me a window, but I can just scan everything
  available."
- "The correction was minor, so it doesn't need an evidence reference."
