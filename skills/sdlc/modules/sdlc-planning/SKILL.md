---
name: sdlc-planning
description: "Use when the change is Standard or Significant."
metadata:
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "planning"
---

# Planning module

For Standard/Significant changes classified by the
[change-contract module](../sdlc-change-contract/SKILL.md), write a short plan
before editing code. Keep it proportional: a few bullet points for a Standard
change, more detail for Significant ones.

Before decomposing work, re-read the current authoritative specification or
change contract and compare it with repository state. If either changed since
approval, mark the existing plan stale and reconcile the difference first.

When the PRD module is selected:

- require `status: approved` before planning;
- cite the PRD path, stable ID, and approved version;
- for reconciled requirements, cite both the sole authoritative artifact and
  `.sdlc/reconciliation/FEATURE_ID.json`;
- map every task to the `FR-*` and `AC-*` identifiers it implements or
  verifies;
- reject requirements with no planned implementation or acceptance evidence.

Use deterministic validation before implementation:

```text
python PATH_TO_SDLC/scripts/validate_artifacts.py validate-plan PLAN_PATH --project-root PROJECT_ROOT
```

The normalized success shape is documented by
`contracts/plan-result.schema.json`. Task details expose PRD references,
prerequisites, consumed and produced interfaces, execution mode, and the
verification description. Validation does not interpret that description as
proof that a command ran and reports `semanticApproval: not-assessed`.

The plan begins with scalar frontmatter:

```yaml
---
type: implementation-plan
prd-path: docs/prds/FEATURE_ID.md
prd-id: stable-feature-id
prd-version: 1
---
```

The PRD path is project-relative. Its ID and approved positive version must
match the validated PRD.

For a reconciliation-backed PRD, replace `prd-path` with both identity fields:

```yaml
prd-artifact: docs/specifications/FEATURE_ID.md
prd-reconciliation: .sdlc/reconciliation/FEATURE_ID.json
```

The artifact must match the report's sole nominated authority. Missing
canonical fields, blocking conflicts, approval tied to another source digest
or version, stale selectors, or a changed generated view block planning.

## Plan should cover

1. **Approach** - the chosen solution and, if non-obvious, the alternatives
   considered and why they were rejected.
2. **Stack/tech constraints** - languages, frameworks, libraries already used
   in this area of the codebase (prefer these over introducing new
   dependencies unless justified).
3. **Files/modules to touch** - a concrete list, so scope is visible before
   you start.
4. **Scope justification** - why each changed surface is necessary for the
   single outcome, plus adjacent work explicitly deferred to another change.
5. **Sequencing** - order of steps, especially for multi-file or multi-service
   changes (e.g., add migration -> update model -> update API -> update UI).
6. **Test strategy** - when testing is selected, map acceptance criteria to
   tests and verification commands from the
   [testing module](../sdlc-testing/SKILL.md).
7. **Review strategy** - identify the expert perspectives the final diff
   needs based on its risk.
8. **Security/authz touchpoints** - when security-auth is selected, flag its
   relevant categories now.
9. **Risks & rollback** - what could go wrong, and how to revert or mitigate
   if it does (feature flag, migration reversibility, etc.).

## Dependency-aware execution for Significant changes

For Significant work, add a compact dependency map:

- Give each task one independently reviewable outcome.
- State its prerequisites.
- State the interfaces or artifacts it consumes.
- State the interfaces or artifacts it produces for later tasks.
- Mark tasks as sequential or place independent tasks in a named parallel
  group.

Use this shape so dependencies remain explicit:

| Task | PRD refs | Outcome | Prerequisites | Consumes | Produces | Execution | Verification |
|------|-----------|---------|---------------|----------|----------|-----------|--------------|
| `<id>` | `<FR/AC ids or not applicable>` | `<reviewable result>` | `<task ids or none>` | `<interfaces/artifacts>` | `<interfaces/artifacts>` | `sequential` or `parallel group <name>` | `<fresh evidence>` |

For Significant work, use every column explicitly. Do not collapse
`Consumes` and `Produces` into a generic dependency description. Write `none`
when a task has no consumed or produced interface. `none` represents an empty
list, is case-insensitive, and must be the only list item. Otherwise, separate
interface names with commas. Each interface has exactly one producing task,
and every consuming task names that producer as a direct or transitive
prerequisite.

Use these ordering rules:

1. Establish shared contracts, types, fixtures, and repository setup before
   work that consumes them.
2. Parallelize only tasks that do not modify the same ownership surface,
   depend on each other's uncommitted output, or compete for shared mutable
   state.
3. Keep uncertain dependencies sequential.
4. Place integration, cross-boundary verification, and reconciliation after
   the parallel group.
5. Give every delegated task its own scope, acceptance evidence, and return
   contract.

Do not call tasks parallel when their `Consumes` entries depend on another
task in the same group, when they produce the same interface, or when they
modify the same ownership surface. Put a producer before or after the group
when a consumer requires its output.

Parallelism is an execution option, not a reason to split one coherent
vertical slice into disconnected horizontal layers.

## Long-plan continuity

For a plan that cannot finish in one session, record only a deterministic
execution cursor:

```text
python PATH_TO_SDLC/scripts/validate_artifacts.py cursor PLAN_PATH --project-root PROJECT_ROOT --task TASK_ID --complete COMPLETED_TASK_ID
python PATH_TO_SDLC/scripts/validate_artifacts.py cursor-status PLAN_PATH --project-root PROJECT_ROOT
```

The default cursor lives under `.git/`, so it is project-local and untracked.
Use `--cursor PROJECT_RELATIVE_PATH` when repository policy provides another
ignored location. The helper records the plan path and digest, current task,
and completed task IDs. It rejects stale plans, unknown tasks, and unmet
prerequisites. Do not add timestamps, narrative completion summaries, or the
ephemeral coverage ledger. Delete the cursor when the plan is complete.

## During implementation

- Prefer surgical, scoped changes over drive-by refactors.
- If you discover the plan was wrong mid-way, stop and revise it rather than
  improvising silently - note the change and why.
- If new work has independent value or acceptance criteria, defer or split it
  instead of expanding the current change.
- Necessary supporting work is not scope creep. Include it and explain why it
  is required for a safe, complete outcome.
- Keep the user informed at meaningful checkpoints, especially if the plan
  changes.
