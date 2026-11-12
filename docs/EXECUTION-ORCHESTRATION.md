# Finite local batch orchestration

The optional [two-isolated-project command](PARALLEL-BATCHES.md) can run two
independently consented batches concurrently in distinct, nonoverlapping
project roots. Each batch below remains serial and keeps its existing manager
and acceptance boundaries. No same-project parallel dispatch is enabled.

The explicit batch command schedules a finite, serial set of already approved
tasks through the existing native manager and fixed runtime bridge. It is
additive to **SDLC: Run Bounded Worker**. Batch preparation and preview do not
dispatch work. The native command displays the exact batch digest and bounds,
then requires a separate explicit confirmation before dispatch.

## Batch contract

A batch is strict, versioned JSON with these fields:

```json
{
  "schemaVersion": 1,
  "batchId": "review-batch",
  "executionId": "feature-one",
  "planRevision": 1,
  "tasks": [
    {
      "taskId": "implement",
      "role": "developer",
      "attempts": [
        {
          "attemptId": "implement-first",
          "modelId": "approved-model-id",
          "brief": {},
          "limits": {
            "maxIterations": 4,
            "maxToolCalls": 8,
            "maxInputBytes": 32768,
            "maxOutputBytes": 32768,
            "maxWallMs": 30000
          }
        }
      ]
    }
  ],
  "limits": {
    "maxCalls": 4,
    "maxToolCalls": 8,
    "maxWallMs": 60000,
    "maxInputBytes": 65536,
    "maxOutputBytes": 65536
  },
  "maxSpendMinor": null
}
```

Every attempt carries its own exact brief, attempt ID, model ID and runtime
bounds. Each brief binds to the imported plan revision. Attempts are a finite,
ordered list of exact model IDs and per-attempt runtime bounds. Every model ID
must already be permitted by the current controls policy and available from
the current IDE before the first dispatch. No worker chooses a model and no
current provider inventory is silently adopted. A later model ID is an
escalation only when the approved policy allows escalation.

`limits` cap cumulative model calls, wall time, input bytes and output bytes
for this batch. The runtime also enforces its existing per-attempt ceilings.
These limits do not measure or cap spend. If `maxSpendMinor` is non-null, the
controller fails closed before dispatch because it has no authoritative
provider billing and pricing capability.

Admission also checks the existing manager ledger's 256-event capacity.
Each unstarted finite attempt conservatively requires eight slots, covering
readiness or retry, start, request and batch markers, receipt attribution,
receipt, accounting and independent judgment. This check is repeated under
the sole writer lock before dispatch. An active batch reserves its remaining
receipt, accounting and judgment slots in the same event ledger; unrelated
progress cannot consume them. Retry readiness transfers the reservation to
the exact pending attempt until its start and batch marker convert it to
terminal slots. Blocking/unblocking does not release it; cancellation does.
Capacity failures are explicit
`E_ORCHESTRATION_CAPACITY` errors before a new provider invocation, not a
larger event limit or a separate reservation ledger.

The canonical batch digest binds the complete normalized batch, exact brief
contents, ordered model choices, per-attempt bounds, cumulative limits, and
current plan, execution-consent and controls digests. The user explicitly
approves that digest in the active IDE. Every exact model ID must be uniquely
available before consent; any input, policy, plan, approval, profile or
runtime-bound drift invalidates the batch.

## Versioning and retained history

Manual execution events remain version 1. Batch controls use version 3;
manager records use version 3 for batch receipts and controller events, while
version 4 adds the manager-owned context object. Controller event versions are
independent: version 2 records retries and legacy coarse accounting, version 3
marks an autonomous attempt start, version 4 records legacy detailed
bounded-execution accounting, and version 5 distinguishes request lifecycle
and unknown-attempt accounting. Existing revisions, receipts and approvals
remain readable and are not reinterpreted. The new reader replays legacy
history and explicitly versioned controller events under the existing manager
authority. The manager's writer lock and execution record remain the only
attempt ledger. Older readers fail closed when they encounter an unsupported
event or record version. Downgrade never discards controller history or
restores old approvals.

Every new batch requires consent bound to the current plan digest, execution
policy digest, controls generation and exact batch digest. A changed binding
requires fresh approval. Reconfiguring or disabling the controls policy
invalidates batch approval but does not erase attempt history or safety
barriers.
The controls approval stores the batch digest, finite task/attempt identities,
roles, exact model IDs, per-attempt and cumulative bounds, and one digest per
brief. Manager receipts retain only the result-validation scope tags (allowed
actions, owned paths and acceptance-criterion IDs) plus the brief digest.
Neither controls nor receipts persist guidance or verification prose, model
prompts, streamed responses or transcripts. The selected file must be supplied
again after a restart; this does not resume or redispatch work.

## Prompt construction and accounting

The bounded runtime passes the role identity and profile-digest-validated
instructions selected during request preparation, plus the exact applicable
shared-context revision/digest and specialist-context digest/content. It does
not select or reconstruct alternative context. Missing or stale bindings fail
before model dispatch.

Operator context mutation is refused for the lifetime of an active attempt
under the same manager writer lock used for start. The freeze covers the
validation-to-dispatch gap, subsequent requests and tool work. Unknown native
outcomes retain the freeze; a confirmed receipt releases it without accepting
the task. A later attempt binds the latest context revision and digest.

At each model call, `driver.js` assembles a deterministic prompt in fixed
components: execution protocol, task brief, selected role, shared context,
specialist context, requirements, security constraints, permitted tools, and
execution history. The runtime has no safe structured signal to declare a
distinct prior tool result irrelevant, so it conservatively retains distinct
results and evidence from the bounded run. Validated edits are referenced by
path and digest instead of repeating source contents. Consecutive read/search
observations that are identical under deterministic serialization are
represented once with their occurrence count; changed or nonconsecutive
observations remain distinct. Required content is neither silently truncated
nor semantically compressed. If the prompt exceeds the supported bound,
execution fails visibly before the provider request.

Distinct does not imply continuation-relevant: this conservative policy can
retain obsolete observations and exhaust a prompt limit. It deliberately
does not guess at relevance or delete unique evidence. The approved
[PRD version 2](prds/token-efficiency-foundation.md) permits this conservative
retention while preserving mandatory content and evidence. AC-2 was
successfully reassessed against that amended FR-2 contract using prompt tests
and independent review. This does not claim minimal history or token savings.
See the
[history acceptance decision](plans/token-efficiency-foundation.md#history-acceptance-decision).

The unexplained Windows cancellation, heartbeat and cleanup failures remain
tracked in [amdluigi/sdlc#42](https://github.com/amdluigi/sdlc/issues/42).
Passing tests do not establish their cause or a fix.

The local bounded-runtime record stores aggregate measurements only. Component
and total model-facing input bytes are UTF-8 byte lengths of transmitted prompt
text, summed across all model calls, including repeated components. Existing
`inputBytes` also includes tool arguments and remains the execution-limit
counter. Output bytes cover model response text and tool-result content.
Model calls include every request, tool calls include each dispatched
operation, retries count manager-approved attempts after the first, and
elapsed time covers an attempt; batch totals sum attempt durations rather than
the delay between attempts. Each accounting event contains cumulative measurements for one bounded
attempt. Version-5 `BATCH_ATTEMPT_ACCOUNTED` requires the matching receipt;
`BATCH_ATTEMPT_ACCOUNTING_UNKNOWN` instead preserves aggregates for a stopped
or unresolved attempt without creating a result or accepting work. Both bind
the exact batch ID/digest, task/attempt IDs, approved brief digest and model.
Summing matching attempt events derives batch measurements, including prompt
components, input bytes, calls, tools, retries, output bytes and attempt
durations; unknown events must not be presented as complete successful
execution totals. No separate aggregate event is persisted. The manager
enforces batch limits against cumulative attempt events. These records contain
no prompt, transcript, source-code or command-output content.

New local stores use version 5 and retain only numeric prompt reservations
and lifecycle aggregates. `step` prepares and budget-checks a request without
charging a model invocation or its input bytes. After the adapter is invoked,
`dispatch` records the invocation and charges its full prompt components once.
The host cannot establish remote transmission: normal adapter return is a
local dispatch observation, while a synchronous throw remains an unknown
invocation. A preparation abandoned before invocation charges neither.

The `requestAccounting` counters have explicit meanings:

- `prepared`: all successful local preparations, including abandonment.
- `dispatched`: normal adapter-return confirmations durably recorded locally,
  not proof of provider receipt.
- `completed`: the response stream ended and observed bytes were settled,
  not proof of valid protocol, task completion, receipt or acceptance.
- `interrupted`: a locally interrupted confirmed invocation.
- `unknown`: invocation or stream outcome cannot be confirmed.

`modelCalls` (local `iterations`) counts durably recorded adapter invocations,
including synchronous throws. If a process disappears between invocation and
durable confirmation, unresolved preparation is classified as unknown, not
silently promoted to a confirmed call. These measurements are not proof of
provider network traffic or billable usage.

If dispatch acknowledgement is lost while the driver remains available, it
reconciles the known invocation as unknown. The manager charges its prompt and
invocation once whether the original dispatch write committed or not; this
bookkeeping does not invoke the adapter again or claim remote delivery.
If reconciliation cannot be persisted, the driver surfaces an unconfirmed
accounting/stop failure rather than claiming complete measurements.

Streaming output counts UTF-8 bytes of the concatenated observed prefix,
including a delivered chunk that crosses the output limit; it does not sum
independently encoded chunks or retain their text. Completed settlements
enforce output bounds. Unknown/interrupted observations can truthfully exceed
the bound when the provider overshoots, but never authorize a tool, receipt
or another request. Post-invocation accounting can record these observations
after consent, source or control drift using the durable start binding;
authorization checks still protect every new step, tool and receipt.

Single-run `elapsedMs` is frozen from runtime start to local report
finalization or stop, including model waits and tool work. Receipt-backed
batch duration is sampled before receipt persistence; unknown-attempt duration
is frozen at local stop and can exceed the lease because of cleanup latency.
Repeated stop calls do not extend it. Neither duration proves remote stop.

Provider-reported input/output, cached and billable tokens remain distinct
from transmitted bytes and from one another. The current VS Code host path
does not expose authoritative token usage or pricing, so those values and
authoritative cost remain `null`; no token or cost values are estimated from
bytes. These local execution records are not persistent telemetry. Any
persistent telemetry continues to require its existing consent and privacy
controls.

## Dispatch, retry, and restart

Tasks dispatch serially. A task may dispatch only when every prerequisite is
independently accepted in the existing manager record. A worker completion or
reported receipt is not acceptance. If a parent is reported, blocked, failed,
waiting for review or otherwise not accepted, the scheduler stops and waits.
It never invokes acceptance or manager approval on a worker's behalf.

An attempt may be retried only after the manager has persisted a complete,
digest-bound failed receipt for that exact attempt and the approved finite
attempt allowance contains another exact attempt. A later permitted model may
be used only in its preapproved order. Unknown or absent receipts, cancellation,
timeouts, thrown calls, malformed or stale receipts, environment failures,
budget exhaustion, and unexplained provider errors are barriers and are never
retries.

A retryable result must be a completed native invocation with a validated,
worker-reported failed task and failed verification status. This closed result
is not independent proof that a test failed. Batch receipts retain only
closed outcome/status values and approved scope digests; a provider/runtime
error without such a complete result remains an unknown barrier.

Starting work persists the normal manager attempt before provider invocation.
On restart, the controller reads and replays all existing manager history.
An unresolved start, pending stop, unknown outcome, stale digest or malformed
record blocks dispatch. The controller does not resume a live call or
redispatch an attempt automatically. A safely recorded failed receipt may be
continued only by revalidating the same approved batch and its remaining
attempts.

There is no automatic result acceptance, manager approval, policy adoption,
telemetry consent, worker-to-worker delegation, concurrent shared-worktree
editing, daemon, SDK, provider credential storage, or monetary cap. Commands
continue to use the existing exact bounded Windows process containment;
POSIX execution remains unsupported. The cooperative local controller is not
an OS sandbox.

The IDE exposes a separate **SDLC: Run Approved Bounded Batch** command and
leaves the existing single-worker command unchanged. The batch command reads
one bounded local JSON file with duplicate-key rejection, asks the fixed
manager bridge for a read-only preview, and verifies that every exact model ID
is uniquely available in the active IDE before showing consent. Consent binds
the normalized batch digest and displays task/attempt IDs, brief digests,
models and limits. It then dispatches attempts serially through the existing
manager and runtime driver. Cancellation remains local-only; any unconfirmed
attempt blocks further dispatch.
