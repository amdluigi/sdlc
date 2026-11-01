# Opt-in local execution management

The local preview provides one manual flow: configure, import, inspect,
approve, record an attempt, receive its result, independently accept evidence,
and report. It never dispatches a worker, runs a verification command or
modifies a project file on a task's behalf.

The approved [roadmap requirements](prds/staged-execution-orchestration.md)
and [implementation plan](plans/staged-execution-orchestration.md) separate
this milestone from future host delegation, routing, controls and dashboards.
Legacy skills, configuration, metrics, run records and cursors stay unchanged.
Installing these helpers does not activate them or automatically collect data.

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

Prepare [version-1 plan/brief/result data](EXECUTION-CONTRACTS.md) with matching
execution, revision and canonical plan bindings. Then:

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

## Storage, failure and recovery boundary

Regular Git metadata uses `.git/sdlc/executions/<execution-id>.json`.
Gitfile/worktree and non-Git projects use `.sdlc/local/executions/` only when
Git's effective ignore evaluation proves the directory, lock and exact record
excluded. Negated record rules block writes. Unsupported Git/ignore inspection,
links/reparse points and unsafe paths fail closed. There is no global store.

One [execution record](../skills/sdlc/contracts/execution-record.schema.json)
holds immutable revision history, consent snapshots, version-1 events,
receipts and independent approval/acceptance records. No stored projection
has authority. Reads validate the full history and rebuild state.
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
only: no raw command output, code, prompts or transcripts. Titles, paths,
commands, revisions and summaries can nevertheless be sensitive. Do not put
secrets, customer data or private content into any metadata field, and do not
publish local records inadvertently. Validation is not a secret detector.

New [policy](../skills/sdlc/contracts/execution-policy.schema.json),
[consent](../skills/sdlc/contracts/execution-consent.schema.json),
[acceptance](../skills/sdlc/contracts/execution-acceptance.schema.json),
[record](../skills/sdlc/contracts/execution-record.schema.json) and
[state](../skills/sdlc/contracts/execution-state.schema.json) schemas have
separate version-1 identities. Register all schemas by `$id` for offline
Draft 2020-12 validation. Existing execution contracts are unchanged.
Python additionally validates relationships, transitions, evidence and
canonical byte limits, and rejects floating-point integer tokens. No schema
validation is approval, authentication or evidence-quality assessment.

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

Other roadmap criteria, live worker/model attribution and UI/analytics
acceptance remain later-milestone work, not completed by these local tests.

This additive preview can be removed with its inventory/manifest additions,
without changing legacy behavior or deleting retained local data. Keep
version-aware inspection available when retained records need examination.
Later profiles, real host dispatch, model routing, limits/cancellation,
attributed telemetry, UI transport and analytics remain separately qualified
and inactive until their respective gates are satisfied.
