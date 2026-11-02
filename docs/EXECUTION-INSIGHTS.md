# Execution insights

This optional, standard-library-only surface reads explicitly selected local
execution IDs. It never discovers all execution histories, records telemetry,
starts workers, changes consent or controls, adopts policy, or grants readiness.
It builds on [execution management](EXECUTION-MANAGEMENT.md),
[native receipts](NATIVE-EXECUTION.md), and
[execution controls](EXECUTION-CONTROLS.md).

## Explicit commands

Run the scripts from the installed bundle or repository. Every command requires
an existing project root. JSON is emitted only to stdout; exporting is an
explicit shell redirection, not an automatic operation.

```powershell
python skills\sdlc\scripts\manage_insights.py snapshot --project-root PROJECT --execution-id feature-one
python skills\sdlc\scripts\manage_insights.py analyze --project-root PROJECT --execution-id feature-one --execution-id feature-two
python skills\sdlc\scripts\manage_insights.py propose --project-root PROJECT --execution-id feature-one
python skills\sdlc\scripts\manage_insights.py validate --project-root PROJECT --input proposal.json
python skills\sdlc\scripts\manage_insights.py review --project-root PROJECT --input proposal.json --decision approved --reason "Reviewed evidence and limits"
python skills\sdlc\scripts\manage_insights.py review --project-root PROJECT --input proposal.json --decision rejected --reason "Insufficient comparable evidence"
```

`snapshot` accepts exactly one ID. `analyze` and `propose` accept 1 to 256
unique IDs through repeated `--execution-id`; duplicates are errors. Selection
order does not change canonical output. `review` and `validate` read strict
JSON, reject duplicate keys and unknown fields, and return an artifact only.
Errors follow the existing `error[CODE] /pointer: message` convention on stderr,
with a nonzero status and no success JSON.

Library APIs in `execution_insights.py`:

- `build_snapshot(project_root, execution_id)`
- `analyze_executions(project_root, execution_ids)`
- `propose_estimates(project_root, execution_ids)`
- `validate_proposal(value)`
- `review_proposal(value, approved, reason)`

There is no output-path, recording, discovery, adoption or dispatch API.

## Snapshot contract

`execution-snapshot.schema.json`, version 1, contains exactly:

- `schemaVersion`, `kind` (`sdlc-execution-snapshot`);
- `binding`: `executionId`, `planRevision`, `planDigest`;
- `approved`, bound to the current execution consent, not merely historical
  approval; `writerLockPresent`, which is an inspection barrier, not permission
  to steal a lock;
- `tasks`: `id`, `title`, `status`, `attemptId`, `reportedStatus`, `estimateMs`,
  `recordedIntervalMs`, `requestedModel`;
- `controls`: `enabled`, `paused`, `pendingCancellationCount`,
  `unknownNativeAttemptCount`;
- `snapshotDigest`.

`execution-snapshot-v2.schema.json`, version 2, is emitted only when at least
one accepted task used independent-validation acceptance
(`urn:sdlc:execution-acceptance:2`). It is version 1 plus a required task
`acceptanceBasis`: `independent-operator-validation`,
`worker-verification-with-operator-judgment` or `null`, non-null exactly when
the task is accepted. The version bump makes version-1-only readers refuse it
rather than present an independently validated batch result as worker-verified.
Executions without such an acceptance still export byte-identical version 1.
Analysis sources may contain execution records of version 1, 2 or 3.

Snapshot tasks cover the latest immutable revision. Statuses are `waiting`,
`ready`, `running`, `blocked`, `reported`, `accepted`, `failed`, `cancelled`.
Reported completion is not independent acceptance. Titles and strings are
plain metadata, never executable commands or interpreted Markdown/HTML.
Consumers must display them as plain labels, not a script context.

`estimateMs` is a plan declaration. `recordedIntervalMs` is the interval between
the manager's recorded start and end events, with second-resolution timestamps;
it is not host runtime, monotonic timing, billable time or active effort.
Unavailable values are `null`, not zero. An explicitly recorded zero remains
zero. Requested model preference is not observed model identity.

Snapshot digest is `execution_state.digest` of every other field: sorted,
compact ASCII JSON (`ensure_ascii=True`, no NaN), UTF-8 encoded, SHA-256 prefixed
with `sha256:`. Integer fields support the existing signed-64-bit range.
JavaScript consumers must preserve integer precision before verifying digests.
Snapshots have at most 256 tasks and 2 MiB canonical bytes. They are local
read-only observations, not transactional authority or proof of a live worker.

Cancellation count is the project controls store's pending intents. Unknown
native count covers only the selected execution's retained attempts; it is
not a claim that unselected project history is clear.

## Reproducible analysis and privacy

`execution-analysis.schema.json`, version 1, retains `sources`, `telemetry`,
`summary` and `analysisDigest`. Each selected source includes the validated
complete execution record, its digest, and current policy digest. All immutable
revisions, attempts, failed receipts, verification outcomes, independent
acceptances, rejection reasons and cancellation/rework context remain available,
including when a later revision succeeds.

Summary counts are across revisions, not just current tasks. `rejectedCount`
counts independent `VALIDATION_FAILED` events. `failedCount` includes rejected
attempts and other failed tasks. `reworkTaskCount` counts execution/task identities
started more than once across revisions. Missing-estimate count covers all
revision/task entries; missing recorded interval and missing telemetry counts
cover started attempts only. Telemetry presence does not imply that duration,
usage, price or model was observed; inspect their nullable fields separately.

Telemetry is read only through `execution_telemetry.inspect_telemetry(root)`.
The full store is validated by that helper, then observations are filtered to
exact selected execution/revision/plan-digest/task/attempt bindings.
Revoked consent does not hide retained observations. Absent data stays empty
with a null store digest; corrupt or unavailable inspection is an explicit
error, never silently converted to missing data.

Each selected observation retains its consent generation, declared or supplied
host source, clock window, timing, requested and observed models, inventory
digest, usage and price. `telemetry.costs` contains one cost projection per
observation. A price without its corresponding usage yields `costMinor: null`.
Known costs use the existing ceiling-to-minor-unit calculation for the one
quoted request/input-token/output-token unit. Costs are never summed across
currencies, rate versions or pricing units; this is not total billing.

Records and exports may contain sensitive structured titles, ownership paths,
verification command declarations and operator summaries. This surface adds no
prompts, transcripts, code, environment dumps or raw command output. Keep
exports private unless reviewed for disclosure. No automatic retention cleanup
or export occurs.

Manager confinement, strict record replay, regular-file checks and actual Git
ignore proof protect every selected read. An unselected corrupt execution file
is not read. Corruption in the shared telemetry or controls metadata is still
reported. Reads do not acquire or remove the writer lock, and observations of
separate files are not an atomic project-wide transaction.

## Inactive proposals and review

`execution-proposal.schema.json`, version 1, embeds the reproducible analysis,
source digests, estimate evidence, fixed sample/quality/rework limits, and a
proposal digest. `active` is always `false`, including after approval.
Validation replays embedded records, rechecks exact attempt/native attribution,
recomputes summary/costs/estimates, and verifies all derived digests.

Estimate candidates group the same execution/task and full task-definition
digest excluding only `estimateMs`. Changes to outcome, ownership, assignment,
criteria or other task metadata do not silently share a sample pool.
Only independently accepted attempts enter estimates; failed, rejected,
unaccepted and rework evidence still remains in the embedded analysis.

Each candidate names its timing basis and sample references. Manager intervals
and supplied host durations are separate pools. Host pools also separate
host/build, observed model and inventory digest. Manual declared telemetry is
not host timing. Multiple duration windows for one attempt are neither summed
nor counted as independent task samples. At least three eligible attempt
samples are required for an integer median estimate (even medians round down);
fewer samples yield `estimateMs: null`. No eligible samples yield no candidate.
This threshold is a visibility guard, not statistical confidence or a promised
forecast. Second-resolution manager intervals and supplied host duration
windows do not prove active effort or equivalent task scope.

Routing recommendations remain empty because this portable slice has no
qualified comparable model evidence. It claims no speed, quality or savings
improvement. Inventory/model/pricing digests retain supplied historical
provenance, not host authentication or proof of an original inventory file.
Digests detect inconsistent artifacts, not a malicious same-user author who
can rewrite all data and recompute every digest.

Review accepts only an unreviewed proposal and returns `approved` or `rejected`,
with a nonempty reason bound to the original proposal digest. It never updates
a stored artifact, manager judgment, execution plan, controls, configuration,
extension or model policy. `validate` is structural/derivation verification,
not semantic approval; an approved artifact still requires a separate,
explicitly authorized adoption process outside this surface.

## Verification and reversal

```powershell
python -m unittest tests.test_execution_insights -v
python -m unittest tests.test_execution_insights tests.test_execution_management tests.test_execution_controls tests.test_execution_telemetry -q
```

Tests use real isolated Git projects, manager replay and native receipt
metadata; no mock removes those integration boundaries. They cover fixed
snapshot fields, null timing, current-policy drift, Unicode/integer digests,
selected-only reads, corrupt metadata, ignore negation, writer-lock retention,
all revisions, rejected/failed/rework evidence, telemetry revocation and
filtering, separated pricing, inactive review, derivation tampering and CLI
errors. Native receipt fixtures are supplied metadata, not live host, inference,
cancellation or effective-routing qualification.

Reversal removes these additive scripts, schemas and documentation together
with their packaging references. Retained manager/telemetry data is unchanged.
This portable prerequisite does not complete live-host M2/M3 qualification,
dashboard qualification, adoption, merge or release gates.
