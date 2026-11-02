# Finite local batch orchestration

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

Manual execution records/events remain version 1. Supervised controls remain
version 2. A separate version-3 batch policy and manager-owned version-2
execution record add controller consent and retry events; existing version-1
revisions, receipts and approvals are retained byte-for-byte as historical
content. Version-1 replay keeps its original transition rules and rejects
failed-to-ready transitions. The new reader replays the version-1 history and
the explicitly versioned controller events without reinterpreting old events.
The manager's existing writer lock and execution record remain the only
attempt ledger. Older readers fail closed on the additive record version.
Downgrade never discards controller history or restores old approvals.

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
