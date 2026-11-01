# Separately consented execution observations

Detailed execution telemetry is absent and disabled by default. Execution
policy, local controls, anonymous measurement and evaluator consent do not
enable it. This interface records only explicitly supplied structured
observations; it never collects host events, prompts, transcripts, command
output, code or environment data.

## Explicit consent and retention

Use installed `scripts/manage_telemetry.py` with an explicit project root:

```text
python scripts/manage_telemetry.py inspect --project-root PROJECT
python scripts/manage_telemetry.py configure --input telemetry-policy.json --dry-run --project-root PROJECT
```

A policy contains exactly `schemaVersion: 1` and the boolean `enabled`.
Configuration without `--dry-run` explicitly changes local consent. Enabling
also requires enabled base execution consent. Dry run and absent/disabled
recording write nothing. The private store is beside the existing execution
manager lock under Git metadata, or a confined fallback proven ignored for
the exact telemetry path.

Configure, recording and deletion use that same project writer lock and
atomic replacement. Recording rechecks consent and its generation inside the lock. Successful
revocation prevents later official observations and retains prior data.
Every configure changes the consent generation; an old observation ID cannot
be renewed under a new generation. No background collection or pruning occurs.
A competing disable/re-enable or deletion cannot authorize an observation
that already passed preflight under an earlier consent generation.

Explicit `delete --store-digest DIGEST` clears observations only when the
current inspected store digest matches. It preserves enabled/disabled consent
and changes the generation. Deletion does not disable future authorized
recording. Existing manager history, controls and other measurement stores
are untouched.

## Observation contract

The version-1 observation contains `id`, exact execution-plan `binding`,
`taskId`, `attemptId`, `source`, `requestedModel`, `observedModel`,
`inventoryDigest`, `window`, `durationMs`, `usage`, and `pricing`.
All fields are required; unavailable model, duration, usage and prices are
explicit nulls rather than zero. Unknown fields, controls in text, malformed
IDs, unsafe storage and invalid numeric values fail explicitly.

`source` contains `kind`, `hostId`, `hostBuild`, and `callId`.

- `manual-declaration` records declared timing for an existing manual attempt.
  Host identity, observed model, inventory, usage and pricing must be null.
  It cannot masquerade as a native host observation.
- `host-observation` must match an existing attributable native receipt for
  the exact plan revision, task, attempt, host build and call identity.
  It does not authenticate the host or establish actual runtime model support.

`requestedModel` preserves the existing plan's model-text preference, including
legacy labels rather than only inventory IDs, and must match that immutable
assignment. `observedModel` remains a strict supplied inventory ID. When an observed
model is supplied, a strict supplied inventory is required for recording:
host/build, inventory digest, available model identity and nullable pricing
must agree. The full inventory is checked but not retained in the telemetry
store. Missing model observation cannot imply inventory or pricing.

`window` contains an explicitly identified monotonic `clockId`, `startMs`,
and `endMs`; values are bounded nonnegative integers. End cannot precede
start and supplied duration cannot exceed that interval. Usage is incremental
for that window, not a cumulative counter. Windows cannot overlap within
the same attributed call/clock, or the same manual attempt/clock.
Identical windows, including zero-length windows, cannot be counted twice.

`usage` contains nullable `requests`, `inputTokens` and `outputTokens`.
Pricing reuses the strict supplied model rate contract: currency, rate
version, unit, units and integer minor-unit price. Missing units or prices
stay unavailable; computable estimates are checked for integer overflow.
No live billing, hard spend enforcement or savings claim follows from these
supplied observations.

## Recording and inspecting

`record --input observation-input.json` accepts exactly:

```json
{"schemaVersion":1,"observation":{},"inventory":null}
```

Replace the empty observation with all required contract fields. The optional
inventory value is required for a supplied observed model and otherwise null.
Exact observation repeats are idempotent; conflicting IDs, stale consent,
ambiguous native attribution and duplicate windows fail without capture.

The bounded store retains at most 256 observations and 2 MiB. Capacity
exhaustion fails explicitly rather than dropping old data. `inspect` is
read-only and can inspect retained history after revocation. Selected-history
analytics may consume it, but never activate recording or infer consent.

This portable recording interface is not a live host collector. Actual
native permissions, model/usage attribution and cancellation qualification
remain separate runtime gates.
