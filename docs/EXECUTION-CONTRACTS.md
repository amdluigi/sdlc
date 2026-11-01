# Inactive execution contracts

Version 1 defines data for a possible execution manager. It does not implement
or enable that manager. Existing SDLC skills, commands, configuration,
providers, plan cursors, metrics, and evaluator run records are unchanged.

The separately opt-in [local manual manager](EXECUTION-MANAGEMENT.md) now
consumes these unchanged contracts. Its replay/storage/controller judgments
are additional boundaries, not authority granted by these validators.

The approved scope is recorded in
[the PRD](prds/execution-contracts-foundation.md) and
[implementation plan](plans/execution-contracts-foundation.md).

## Explicit library boundary

[execution_contracts.py](../skills/sdlc/scripts/execution_contracts.py) exposes:

```python
validate_execution_plan(data)
validate_task_brief(data, plan)
validate_task_result(data, plan, brief)
validate_execution_event(data, plan)
```

Each argument is explicitly supplied parsed JSON data. Success returns
`{"contractValid": true, "semanticApproval": "not-assessed", "notice": "...",
"data": <independent copy of the input>}`. No input is modified.

Structural validation does not approve product decisions, evidence quality,
risk acceptance, or PR readiness. In particular:

- Assignment names and model profiles are assertions, not loaded agents,
  available models, routing preferences, or enforced budgets.
- Ownership and allowed actions describe a brief, not authorization.
- A result reporting `completed` can contain failed, missing, or unavailable
  verification. It is an unaccepted report, not accepted task completion.
- An event is not authenticated or appended, replayed, or applied to state.
  Sequence uniqueness, stream order, legal transitions, actual timestamps,
  approvals, and cancellation are not enforced.
- Source paths and digests are declarations. The source plan, PRD approval,
  artifact existence, filesystem confinement, and evidence are not inspected.

There is no CLI, scheduler, reducer, persistence, configuration resolution,
network access, subprocess dispatch, clock sampling, or telemetry. Importing
the module does not change the existing runtime. Do not execute supplied
commands or treat supplied guidance as instructions merely because validation
succeeds.

For explicit file input, use the existing
[strict_load_json](../skills/sdlc/scripts/artifact_contracts.py) reader:

```python
from artifact_contracts import ContractIssue, strict_load_json
from execution_contracts import validate_task_result

try:
    checked = validate_task_result(
        strict_load_json("result.json"),
        strict_load_json("plan.json"),
        strict_load_json("brief.json"),
    )
except ContractIssue as error:
    print(error.cli_message())
    raise SystemExit(error.exit_code)
```

These helpers are installed under `sdlc/scripts`; explicitly place that
directory on the caller's import path. The example never creates an execution.

## Common conventions

All fields shown by the schemas are required, including nullable fields.
All objects and event payload variants are closed. Unknown fields or versions
fail. All four contracts use `schemaVersion: 1` and distinct identities:

| Contract | Schema identity |
|----------|-----------------|
| [Execution plan](../skills/sdlc/contracts/execution-plan.schema.json) | `urn:sdlc:execution-plan:1` |
| [Task brief](../skills/sdlc/contracts/task-brief.schema.json) | `urn:sdlc:task-brief:1` |
| [Task result](../skills/sdlc/contracts/task-result.schema.json) | `urn:sdlc:task-result:1` |
| [Execution event](../skills/sdlc/contracts/execution-event.schema.json) | `urn:sdlc:execution-event:1` |

The schemas use Draft 2020-12. Register all four bundled schemas by `$id` in
an offline schema tool. Shared scalar definitions refer to the execution-plan
schema by URN; no remote retrieval is required. The Python library does not
load schemas or depend on a JSON Schema engine.

- IDs: lowercase kebab-case, at most 128 characters.
- Requirement references: `FR-<positive integer>` and `AC-<positive integer>`,
  at most 128 characters.
- Text: nonempty, non-whitespace, single-line, without ASCII control
  characters, at most 2,048 characters. Agent/model text is limited to 128.
- Arrays: at most 256 entries. String arrays reject duplicates.
- Counters/revisions: integers from 1 through `2**63 - 1`.
  `estimateMs` permits 0 through that maximum or explicit `null`.
  Booleans, fractional numbers, nonfinite numbers, and decimal/exponent
  representations parsed as Python floats are rejected as counters.
- Paths: exact, project-relative, slash-separated ASCII file references,
  at most 1,024 characters. Components permit letters, digits, `_`, `.`,
  `@`, hyphens, and interior spaces. Absolute paths, drive/URL prefixes,
  colons, backslashes, traversal, percent escapes, empty components, and
  leading/trailing component spaces are rejected. No globs or recursive
  ownership are supported. This is lexical validation, not filesystem access
  or protection against symlinks or platform-specific aliases.
- Digests: `sha256:` followed by 64 lowercase hexadecimal digits.
- Input: the strict reader rejects malformed JSON/UTF-8, duplicate keys,
  nonstandard constants, and files larger than 2 MiB. Each Python validation
  additionally limits the supplied artifact to 2 MiB of canonical JSON bytes.

JSON Schema checks shapes and scalar restrictions. Python additionally checks
graph relationships, declared scope, canonical binding, real calendar dates,
and timestamp ordering. JSON Schema's mathematical `integer` type can accept
`1.0`; Python deliberately requires an actual integer token after parsing.

## Execution plan

A plan carries `executionId`, positive `revision`, a `sourcePlan` object
(`path`, `digest`, `prd.id`, `prd.version`), and one to 256 tasks.

Each task carries:

| Fields | Meaning |
|--------|---------|
| `id`, `title`, `outcome` | Stable task identity and declared outcome |
| `prdRefs`, `acceptanceCriteria`, `verification` | Requirement references and verification description |
| `prerequisites`, `consumes`, `produces` | Task IDs and named artifact IDs |
| `execution.mode`, `execution.group` | `sequential` with null group, or `parallel` with a group ID |
| `assignment.agent`, `assignment.modelProfile`, `assignment.model` | Declared assignment; model may be null |
| `estimateMs` | Declared estimate or null, never inferred from a clock |
| `ownership` | Exact file references planned for the task |

`prdRefs` must include at least one functional requirement and every task
acceptance criterion. The validator checks unique task IDs, known non-self
prerequisites, acyclicity, unique artifact producers, and producer ancestry
for consumers. Artifact IDs without a plan-local producer represent external
inputs. A task cannot consume its own produced artifact.

Members of one parallel group cannot depend on each other, even transitively,
or share exact ownership paths. Different groups are not scheduled or compared
for concurrent availability. These checks align with existing Markdown-plan
graph invariants without altering that validator.

## Binding a brief, result, or event

Each carries:

```json
{
  "binding": {
    "executionId": "feature-one",
    "planRevision": 2,
    "planDigest": "sha256:<64 lowercase hex characters>"
  }
}
```

The digest binds the entire validated execution plan, not just its source
Markdown file. Compute SHA-256 of the UTF-8 bytes from Python
`json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
allow_nan=False)`, then prefix `sha256:`. Object key order is irrelevant;
array order and every declared field are significant. There is no digest
field inside the plan itself. `sourcePlan.digest` remains an independently
declared source digest.

Bindings from another execution, revision, or plan content are rejected.
The supplied plan is validated before relational checks.

## Task brief and result

A brief identifies an existing `taskId` and an `attemptId`. It supplies
`allowedActions` from `read`, `search`, `edit`, `execute`; `ownership`;
`guidance` file references; `acceptanceCriteria`; and a `verification`
description. Ownership must be a subset of the task's planned exact paths.
An edit action requires nonempty ownership. Criteria must equal the planned
task criteria; a brief cannot silently drop acceptance obligations.

A result identifies the same task and attempt as its supplied brief, which
is also validated. It supplies:

- `status`: `completed`, `failed`, `blocked`, or `cancelled`.
- `artifacts`: changed file references inside the brief's edit ownership.
  A read-only brief cannot report changed artifacts.
- `verification`: entries with `acceptanceCriterion`, nullable `command`,
  `result`, nullable `revision`, and `summary`.
- `findings` and `blockers`: bounded arrays of declared text.

Verification results are `passed`, `failed`, `not-run`, `skipped`, or
`unavailable`. Each criterion must belong to the brief. Empty verification,
findings, blockers, and artifact arrays are permitted because this contract
checks a report, not its completeness or evidence quality. No command is run.

## Execution events

Every event declares `eventId`, a binding, positive `sequence`, `occurredAt`,
`recordedAt`, `actor` (`role`, `id`), `type`, nullable `taskId`/`attemptId`,
and a closed `payload`.

Timestamps use exactly `YYYY-MM-DDTHH:MM:SSZ`, with valid UTC calendar
values and `recordedAt >= occurredAt`. Fractions, non-UTC offsets, leap
seconds, and fabricated timing defaults are not supported.

| Type | Task | Attempt | Payload fields |
|------|------|---------|----------------|
| `PLAN_PROPOSED` | null | null | none |
| `PLAN_UPDATED` | null | null | `previousRevision`, positive and below current revision |
| `PLAN_APPROVED` | null | null | `decisionId` |
| `TASK_READY` | required | null | none |
| `TASK_STARTED` | required | required | none |
| `TASK_PROGRESS_UPDATED` | required | required | `message` |
| `TASK_BLOCKED` | required | null | `reason` |
| `TASK_UNBLOCKED` | required | null | none |
| `TASK_RESULT_RECEIVED` | required | required | `resultId` |
| `VALIDATION_PASSED` | required | required | `acceptanceCriteria` |
| `VALIDATION_FAILED` | required | required | `acceptanceCriteria`, `reason` |
| `TASK_COMPLETED` | required | required | none |
| `TASK_FAILED` | required | required | `reason` |
| `TASK_CANCELLED` | required | null | `reason` |
| `APPROVAL_REQUESTED` | null | null | `decisionId`, `reason` |
| `APPROVAL_GRANTED` | null | null | `decisionId` |
| `APPROVAL_REJECTED` | null | null | `decisionId`, `reason` |

Payload IDs follow the common ID convention. Validation criteria must belong
to the declared task. Actor roles are `user`, `host`, `manager`, `worker`,
and `validator`. Approval declarations require a declared `user` or `host`
role, but that role is not authenticated and grants no authority.

Attempts, result IDs, and decision IDs are syntactically checked only; there
is no attempt registry, receipt lookup, or approval-request correlation.
Retry, escalation, pause, and recovery events are deliberately excluded.

## Errors, compatibility, and rollback

Failures raise the existing `ContractIssue` with `code`, JSON-style `pointer`,
`message`, and `exit_code`. `cli_message()` is a bounded single-line diagnostic.
The `E_SCHEMA_*` and strict-reader codes are reused. New stable families are:
`E_EXECUTION_VERSION`, `ID`, `NUMBER`, `ENUM`, `LIMIT`, `PATH`, `GRAPH`,
`BINDING`, `REFERENCE`, `SCOPE`, `TIME`, `ACTOR`, and `JSON`, all with the
`E_EXECUTION_` prefix. Diagnostics describe restrictions rather than echoing
supplied commands or evidence.

There are no legacy consumers to migrate or runtime activation flags to set.
The qualified control-plane bundle adds exactly four schemas and one helper.
It still contains 23 discoverable skills and 22 lifecycle implementations.
Existing users do not need to reinstall for unchanged behavior, and installed
skills are never refreshed automatically.

Future consumers must separately establish authorization, filesystem safety,
evidence acceptance, lifecycle transitions, persistence, privacy/retention,
and host support. Incompatible contract evolution requires a new schema
identity/version and explicit migration guidance. The broader runtime is not
approved by this foundation.

Rollback is an ordinary revert of this additive change and its inventories
together. No execution data is written, so no production data migration or
destructive cleanup is needed.

Executable fixtures and boundary assertions are in
[test_execution_contracts.py](../tests/test_execution_contracts.py).
