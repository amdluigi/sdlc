# Opt-in local execution management

The local manager provides one explicit flow: configure, import, inspect,
approve, record an attempt, receive its result, independently accept evidence,
and report. Its project Gantt and bounded context notes use the same manager
record and writer. The manual path never dispatches a worker, runs a
verification command or modifies a project file on a task's behalf.

The approved [roadmap requirements](prds/staged-execution-orchestration.md)
and [implementation plan](plans/staged-execution-orchestration.md) describe
the project-level plan, reusable specialist context, ownership and Gantt
experience. Existing host and automation limits remain separate qualification
gates. Legacy skills, configuration, metrics, run records and cursors stay
unchanged. Installing these helpers does not activate them or automatically
collect data.

## Policy and explicit consent

Create a policy input containing only:

```json
{
  "schemaVersion": 1,
  "enabled": true,
  "mode": "manual",
  "retention": "manual",
  "detailedTelemetry": false
}
```

Invoke [manage_execution.py](../skills/sdlc/scripts/manage_execution.py) from
the repository or installed skill, explicitly supplying the target project:

```text
python <installed-helper> configure --project-root <project> --input policy.json --dry-run
python <installed-helper> configure --project-root <project> --input policy.json
```

The dry-run validates without writing. Configure writes only the separate
project-local `.sdlc/execution-policy.json` consent envelope, containing
`schemaVersion`, a generated positive `generation`, and the input `policy`.
Every configure increments generation, even restoring earlier values.
Policy absence means disabled; import/task/approval operations fail without
creating storage. Configuring never changes `.sdlc/config.json`, measurement,
evaluation, extension maps or an installed/global skill.

Configure with `"enabled": false` to stop subsequent writes through official
manager operations. Existing records remain readable and explicitly deletable.
The project writer lock serializes configure with final execution replacements;
consent is checked again inside the lock. Arbitrary non-cooperating edits are
not claimed to have this linearizable boundary.

## Manual walkthrough

Prepare [version-1 plan and brief data plus a version-1 or version-2 task
result](EXECUTION-CONTRACTS.md) with matching execution, revision and
canonical plan bindings. Then:

```text
python <installed-helper> import --project-root <project> --input plan.json
python <installed-helper> inspect --project-root <project> --execution-id example
python <installed-helper> approve --project-root <project> --execution-id example --plan-digest <inspected-digest> --policy-digest <inspected-policy-digest>
python <installed-helper> record --project-root <project> --execution-id example --task-id implement --action ready
python <installed-helper> record --project-root <project> --execution-id example --task-id implement --action start --attempt-id attempt-one
python <installed-helper> receive --project-root <project> --execution-id example --result-id result-one --brief brief.json --result result.json
python <installed-helper> accept --project-root <project> --execution-id example --input acceptance.json
python <installed-helper> report --project-root <project> --execution-id example
```

IDs in these commands are placeholders that must match the supplied files.
The source-plan digest is still a declaration, not automatically verified
source approval. Inspect and review the actual source requirements before
approving the execution. Plan approval binds execution ID, immutable revision,
the entire canonical plan and the current consent digest.

Receiving a result moves the task to `reported`, not `accepted`. The caller
must independently inspect current evidence before supplying an acceptance:

```json
{
  "schemaVersion": 1,
  "taskId": "implement",
  "attemptId": "attempt-one",
  "resultId": "result-one",
  "acceptanceCriteria": ["AC-1"],
  "revision": "checked-project-revision",
  "command": "independent-verification-command",
  "summary": "Operator inspected the evidence for every criterion"
}
```

The complete criterion set must match the plan and result. Each reported
criterion must appear exactly once with `passed`, a non-null declared command
and the independently checked revision; reported blockers prevent acceptance.
The controller command can differ from worker commands. Neither command is
executed by this helper. This explicit judgment remains the operator's
responsibility; structural validation cannot establish that the commands ran
or the evidence is good. Worker data has no approval actor or acceptance field.
Local APIs are not an authenticated service or OS sandbox against a malicious
same-user caller. A future worker adapter must restrict manager access.

`ready` requires all prerequisites accepted. Manual attempts are serialized
across all execution IDs in the project, including blocked and reported work
pending resolution. The start transaction validates other confined records;
corrupt or unavailable peer records block new work. Start checks exact
file ownership against project confinement, links/reparse points, directory
claims and Windows device/trailing-dot aliases. It is a cooperative declaration,
not a sandbox that intercepts a human's or worker's filesystem edits.
Attempt/result IDs cannot be reused across plan revisions.

Additional record actions:

- `progress --attempt-id <id> --reason <text>` records a bounded message.
- `block --reason <text>` and `unblock` preserve the prior task state.
- `reject --attempt-id <id> --reason <text>` records failed independent validation.
- `fail --attempt-id <id> --reason <text>` records a manual failure.
- `cancel --reason <text>` records the operator's cancellation declaration.
  It does not stop a process or establish host cancellation.

Failed/unavailable/skipped/stale verification cannot be accepted. Reported
completion declarations alone do not unlock dependencies. New plan revisions
start unapproved and cannot replace running, blocked or unassessed reported
attempts. Changed policy requires a newer immutable plan revision and new
approval. Disable/re-enable cannot revive approval through digest reuse.

## Project Gantt and context

Render the same dependency-based relative Gantt for a proposed plan, the
current manager state or the final report:

```text
python <installed-helper> gantt --project-root <project> --input plan.json
python <installed-helper> gantt --project-root <project> --execution-id example
python <installed-helper> report --project-root <project> --execution-id example
```

Planned offsets use only declared estimates and prerequisites. Actual
intervals use manager event timestamps, not host timing. Unknown estimates,
starts or durations stay unknown. This is a readable projection, not a
resource-aware scheduler, calendar forecast or dispatch command.

Shared and specialist context are bounded, attributed notes stored under the
existing manager writer. A note is limited to 2048 characters. Read current
context with `inspect` or the explicitly selected manager dashboard. Update a
note only with the current plan digest and context revision:

```json
{
  "scope": "shared",
  "agentId": null,
  "content": "API contract agreed; add consumer compatibility tests.",
  "expectedPlanDigest": "sha256:<current-plan-digest>",
  "expectedContextRevision": 0
}
```

Pass that file to `context-update --input context.json`. For specialist notes,
use `"scope": "agent"` and the exact role ID in `agentId`. A stale binding or
revision fails without overwriting newer context. Version-2 worker results
may include an optional `contextUpdate`; the manager stores it as an
attributed, unaccepted note for the worker's specialist role. Context is not
approval, acceptance evidence or an instruction override. Keep notes concise;
never store secrets, transcripts or raw task output in them.

Operator context updates, including otherwise idempotent updates, fail with
`E_EXECUTION_CONTEXT_ACTIVE` while an attempt is running or blocked from a
running state. The same manager writer lock serializes attempt start and
context mutation, so the snapshot cannot change between a runtime step check
and model dispatch or during subsequent model/tool work. Unconfirmed native
attempts keep context frozen even after a local stop or an operator's terminal
declaration; those declarations do not prove remote termination.

A validated native receipt ends the active invocation, not the independent
acceptance process. Context may then be updated while its result awaits
review. A version-2 result's specialist note is committed atomically with that
receipt under the manager lock. Terminal manual attempts also release the
freeze. The next attempt must prepare and validate the latest context revision
and digest; an envelope prepared before a successful update is stale.

## Storage, failure and recovery boundary

Regular Git metadata uses `.git/sdlc/executions/<execution-id>.json`.
Gitfile/worktree and non-Git projects use `.sdlc/local/executions/` only when
Git's effective ignore evaluation proves the directory, lock and exact record
excluded. Negated record rules block writes. Unsupported Git/ignore inspection,
links/reparse points and unsafe paths fail closed. There is no global store.

One [execution record](../skills/sdlc/contracts/execution-record.schema.json)
holds immutable revision history, consent snapshots, events, receipts and
independent approval/acceptance records. Version 4 adds the digest-checked
context object; versions 1 through 3 remain readable. A context update or
version-2 task result upgrades the record through a validated manager
transaction. Detailed bounded-batch accounting is a separately versioned
controller event (legacy version 4 or lifecycle-aware version 5); it can be
read inside record versions 3 and 4
without changing the meanings of prior events. No stored projection has
authority. Reads validate the full history and rebuild state.
Atomic replacement is physical storage; manager operations cannot edit earlier
logical entries. Receipt re-delivery with matching identity/content is a
no-write idempotent operation; conflicting content fails.

Limits are 256 execution records per project, 256 revisions and 256
events/receipts/decisions per revision, and 2 MiB canonical bytes per record.
Capacity failures never prune history.
The exclusive project writer lock fails immediately when already present;
no guessed wait/expiry interval or automatic lock theft exists.
Files use restrictive permissions where supported, flush/fsync before atomic
promotion and safe temporary-file cleanup after ordinary failures. Filesystem
and platform power-loss durability is not guaranteed by atomic replacement,
especially on Windows. An abrupt process death can leave a temporary file and
lock, but never promotes a partial JSON record.

```text
python <installed-helper> recover --project-root <project> --execution-id example
```

Recovery is read-only inspection. An unknown active manual attempt remains
unresolved. Corrupt/truncated authoritative JSON blocks replay; it is never
silently truncated, reset or presented as successful. A writer lock may belong
to a live process: independently establish there is no writer before manually
removing that one exact lock. Never delete the containing storage directory.
Inspect any interrupted temporary file separately without promoting it over
validated history. No automatic restart/redispatch exists in this milestone.

Explicit deletion retains consent and removes only the selected record.
Unresolved attempts must be resolved before deletion; deleting their records
must not release project ownership claims:

```text
python <installed-helper> delete --project-root <project> --execution-id example --confirm-delete example
```

Disable first if subsequent official writes must also stop. Corrupt records
block manager deletion as well as replay. Independently establish that no work
or writer remains before manually removing one exact corrupt record.

## Reports, privacy and authority

### Local diagnostic signals

The CLI prints one bounded `error[CODE] /pointer: message` to stderr with a
nonzero exit status. Inspection/reporting exposes current bound metadata only.
There are no exporters, alerts or asynchronous services in this milestone.
The operator owns inspection and the documented recovery response.

| Signal | Diagnostic question |
|--------|---------------------|
| `E_EXECUTION_DISABLED` | Is current explicit consent absent or disabled? |
| `E_EXECUTION_APPROVAL` | Does approval match the current plan and consent generation? |
| `E_EXECUTION_BUSY` | Is a live or abandoned project writer lock preventing mutation? |
| `E_EXECUTION_CONFLICT` | Does another unresolved manual attempt hold project claims? |
| `E_EXECUTION_TRANSITION` | Are dependencies/evidence or task lifecycle order preventing progress? |
| `E_EXECUTION_LIMIT`, `E_INPUT_TOO_LARGE` | Have declared record/event/byte capacities been exhausted? |
| `E_JSON_*`, `E_EXECUTION_JSON`, `E_EXECUTION_READ`, `E_EXECUTION_WRITE` | Is stored data invalid or unavailable, or did persistence fail? |

Stored-input diagnostics suppress content and local paths. Structural input
errors identify schema fields, not retained raw command output. The closed
event vocabulary, field bounds and record capacities bound diagnostic history;
retention is manual. Correlation IDs are local execution/task/attempt metadata,
not high-cardinality remote metric labels. Interval units are seconds between
manager events; estimates are declared milliseconds, never observed host usage.

Reports escape Markdown/HTML/Mermaid labels and show task states, reported
outcomes, unavailable estimates, retained failed/unavailable verification and
a dependency-only critical-path bound. Missing estimates never become
zero-duration claims. The recorded interval is between manager metadata
events, not observed worker runtime or a resource-aware schedule. Reports do
not authorize PR handoff, risk acceptance, release or deployment.

Retention is manual. No automatic export, pruning, analytics, optimization,
telemetry or policy adoption is performed. Records contain structured metadata
only: no raw command output, code, prompts or transcripts. Local runtime
accounting separately retains bounded aggregate counters and prompt-component
byte totals, never prompt text, transcripts, source code or command output.
Persistent telemetry remains independently governed by its existing consent
and privacy controls. Titles, paths,
commands, revisions and summaries can nevertheless be sensitive. Do not put
secrets, customer data or private content into any metadata field, and do not
publish local records inadvertently. Validation is not a secret detector.

New [policy](../skills/sdlc/contracts/execution-policy.schema.json),
[consent](../skills/sdlc/contracts/execution-consent.schema.json),
[acceptance](../skills/sdlc/contracts/execution-acceptance.schema.json),
[record](../skills/sdlc/contracts/execution-record.schema.json),
[record version 4](../skills/sdlc/contracts/execution-record-v4.schema.json),
[task result version 2](../skills/sdlc/contracts/task-result-v2.schema.json)
and
[state](../skills/sdlc/contracts/execution-state.schema.json) schemas have
separate versioned identities. Register all schemas by `$id` for offline
Draft 2020-12 validation. Version-1 task results remain valid. Python
additionally validates context digests, relationships, transitions, evidence
and canonical byte limits, and rejects floating-point integer tokens. No
schema validation is approval, authentication or evidence-quality assessment.

## Reversal and later milestones

### M1 verification mapping

| Roadmap criterion | Current local evidence |
|-------------------|------------------------|
| AC-1 | Disabled/dry-run no-write test; unchanged legacy bundle hashes and full regressions |
| AC-2, AC-8 | Closed result/acceptance shapes, privileged-event binding rejection, stale approvals and disable/re-enable tests; no authenticated worker host is claimed |
| AC-4 | Pure immutable replay, duplicates/conflicts, exact capacities, real competing writers, interrupted promotion, corrupt/oversized/nested JSON and linked storage tests |
| AC-7, AC-9 | Accepted dependencies, exact ownership aliases, serialized attempts across execution IDs, peer corruption and unresolved-deletion regressions |
| AC-10, AC-11 | Escaped reports, declared/unknown estimates and dependency-only incomplete schedule; manager intervals are not host timing |
| AC-12 | Reports retain evidence and explicitly disclaim PR/release/deployment authority |
| AC-13 | Strict policy refuses detailed telemetry; legacy measurement/evaluation configuration is unchanged |

The project-level Gantt and context behaviors have focused local tests and a
native dashboard tree presentation. This does not qualify a real editor host,
screen reader, worker invocation, provider billing, remote cancellation or
host timing. Those remain separate, evidence-gated capabilities.

Reverting this code must retain version-4 records and must not silently
downgrade them. Keep version-aware inspection available when retained records
need examination. Earlier record versions and version-1 requests remain
supported; version-1 native requests are refused after context has been
recorded because they cannot bind that context.
