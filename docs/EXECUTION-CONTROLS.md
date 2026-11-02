# Opt-in execution controls

This M3 slice adds local safety controls and pure model resolution around the
existing manual/native manager. Its additive version-3 mode enables only the
separately consented finite batch controller described in
[finite local batch orchestration](EXECUTION-ORCHESTRATION.md). It does not
complete live host qualification, enable telemetry, claim autonomous policy
adoption or enforce spend. Absence of controls preserves existing behavior.

## Locked interfaces and invariants

The separate version-1 controls policy contains `schemaVersion`, `enabled`,
`mode`, `maxAttempts`, `allowEscalation`, and `permittedModels`. Limits are
explicit, not inferred. The policy validator recognizes manual, supervised
and autonomous modes; version-1 configuration still supports only manual.
Unsupported version-1 modes fail before any write. Enabled manual controls block native
dispatch preparation from being promoted to a worker invocation.

The explicitly selected version-2 policy uses the same fields but requires
`schemaVersion: 2` and `mode: "supervised"`. It permits only the owned
[bounded runtime](../packages/sdlc-runtime/README.md), never the old native
request CLI. It still requires separately approved controls, a permitted
per-run model ID, explicit runtime bounds and per-run digest confirmation.
It does not schedule attempts, retry, escalate, enforce money limits or
qualify autonomous operation. Attempts and unknown-work protection still
come from the existing manager's immutable history.

The separately selected version-3 policy requires `schemaVersion: 3` and
`mode: "batch"`. It adds explicit `maxBatchTasks`, `maxBatchCalls`,
`maxBatchToolCalls`, `maxBatchWallMs`, `maxBatchInputBytes`, and
`maxBatchOutputBytes` bounds. The policy permits only the finite batch
controller and an explicit, per-batch consent digest. Ordered attempt/model
choices must already be permitted. It does not enable open-ended autonomous
dispatch, worker-selected models, automatic acceptance, manager approval or
money limits.

There is no automatic conversion. Only an explicit version-2 configure
operation selects the new mode. The new record retains
the entire previous manual record under `retainedManual`, including its
existing approvals, and inherits pause, cancellation and safety latches.
Retained approvals are historical, never approval of the new controls.
New controls approval is independently required before native dispatch. Later
version-2 changes retain that snapshot. Old readers reject the new record
and policy rather than treating them as manual. Automatic downgrade is
refused even after disabling: reverting code does not erase attempt history,
stop unknown work or authorize restoration of old approvals. Keep the current
reader available for inspection/disable/reconciliation. No destructive
migration or automatic rollback is supplied.
Version-3 configuration retains the preceding complete version-1 or
version-2 controls record. Reconfiguring version 3 invalidates all batch
approvals, increments the generation, and retains that original historical
snapshot; it never stores raw batch briefs in controls state. Version-1 and
version-2 manager history remains inspectable in the existing execution
record. Older readers fail closed on additive versioned records.

`configure_controls(root, policy, dry_run=False)` stores a generation-bound
policy in private metadata beside the existing manager lock. Every configure
changes the generation and invalidates controls approvals. Enabled controls
also require enabled execution policy. Dry run never writes.
`approve_controls(root, execution_id, plan_digest, execution_policy_digest,
controls_digest)` separately binds the approved current plan, execution
consent and controls generation. It never approves the base plan itself.

`set_pause(root, paused, reason)` controls a project-wide start barrier.
`request_cancel(root, execution_id, task_id, reason)` records intent, not a
worker-stop acknowledgment or task cancellation. Pending cancellation blocks
new work across executions, including after disabling controls. Pauses also
remain latched until explicitly resumed; disabling controls never silently
releases either safety barrier.
The private `safetyActivated` latch records that controls were explicitly
enabled. Native stop protection remains latched after disabling controls:
neither legacy cancel nor an unreported failure can free an unknown worker.
Native acceptance or reported failure/rejection requires a bound native host
receipt; an ordinary manual receipt cannot stand in for that observation.

`resolve_manual_cancel(root, execution_id, task_id, reason)` clears only
intent associated with a terminal, purely manual attempt. Native attempts
remain pending without supported host-stop evidence. Legacy cancellation
cannot relabel a controlled native attempt as stopped.
`inspect_controls(root)` and `reconcile_execution(root, execution_id)` are
read-only. Reconciliation reports active/unknown work and pending intent;
it never redispatches, steals a lock, truncates records or calls a host.
Historical native starts without bound host receipts remain unknown even
after a legacy manual terminal declaration. Once controls are activated,
such history blocks new work across executions. Read-only reconciliation
reports these attempts; it cannot certify their stops or erase their history.

Start checks and controls mutations share the existing project writer lock.
Retry counts are rebuilt from task starts across every immutable revision,
not maintained in a second reservation ledger. Changing plan revisions or
restoring an old controls policy cannot reset consumed attempts. Assignment
escalation requires explicit consent, and explicit model identifiers must be
permitted. A fresh controls approval is required after plan or policy changes.
Existing version-1 execution records/events retain their meaning.
After activation, started execution history cannot be deleted through the
manager, even after controls are disabled. It is the consumed-attempt ledger.
Pending cancellation also retains its referenced history. There is no implicit
pruning or retry-counter reset operation.

## CLI

Use the installed `scripts/manage_controls.py` with an explicit project root.
For example, inspect without activating controls:

```text
python scripts/manage_controls.py inspect --project-root PROJECT
python scripts/manage_controls.py configure --input controls-policy.json --dry-run --project-root PROJECT
```

An example policy is:

```json
{"schemaVersion":1,"enabled":true,"mode":"manual","maxAttempts":2,"allowEscalation":false,"permittedModels":[]}
```

For explicitly selected supervised operation, use version 2 and list the
exact picker model ID:

```json
{"schemaVersion":2,"enabled":true,"mode":"supervised","maxAttempts":1,"allowEscalation":false,"permittedModels":["approved-model-id"]}
```

For the finite batch controller, explicitly configure version 3 and list
every exact model ID that may appear in an approved batch:

```json
{"schemaVersion":3,"enabled":true,"mode":"batch","maxAttempts":2,"allowEscalation":true,"permittedModels":["approved-model-id","approved-escalation-model"],"maxBatchTasks":8,"maxBatchCalls":32,"maxBatchToolCalls":32,"maxBatchWallMs":300000,"maxBatchInputBytes":262144,"maxBatchOutputBytes":262144}
```

Batch runtime and cumulative bounds are separate fields in the selected batch
file. They must fit these controls ceilings and the finite attempt list. A
non-null spend request is refused because authoritative provider usage and
pricing are unavailable. Use **SDLC: Run Approved Bounded Batch** only after
the current plan, base execution policy, controls policy and controls approval
are current. The command displays the exact batch digest and requires
independent user consent before dispatch.

After explicitly configuring base execution consent and approving its plan,
configure controls without `--dry-run`, inspect both sets of digests, and
approve their exact bindings:

```text
python scripts/manage_controls.py approve --execution-id EXECUTION --plan-digest PLAN_DIGEST --execution-policy-digest POLICY_DIGEST --controls-digest CONTROLS_DIGEST --project-root PROJECT
python scripts/manage_controls.py pause --reason "Review pending" --project-root PROJECT
python scripts/manage_controls.py resume --reason "Review complete" --project-root PROJECT
python scripts/manage_controls.py request-cancel --execution-id EXECUTION --task-id TASK --reason "Stop requested" --project-root PROJECT
python scripts/manage_controls.py reconcile --execution-id EXECUTION --project-root PROJECT
```

Record a terminal manual outcome separately using the
[execution manager](EXECUTION-MANAGEMENT.md), then use
`resolve-manual-cancel` with the same execution/task IDs and an explicit
`--reason`. This does not resolve native cancellation. `resolve --input`
accepts `schemaVersion`, `inventory`, `profile`, `permittedModels`,
`requestedModel`, and `observation`; `estimate --input` accepts `model`
and `units`. Both are offline JSON operations, not host calls.

## Model resolution

`resolve_model(inventory, profile, permitted_models, requested_model=None,
observation=None)` operates only on supplied strict data. Inventory contains
`schemaVersion`, `hostId`, `hostBuild`, `source`, and `models`; unavailable
inventory has null host identity and no models. Each model has `id`,
`available`, and nullable `pricing`. Profiles contain `id` and ordered
`candidates`. Missing/disallowed models fail explicitly.

Pricing, when supplied, contains `currency`, `rateVersion`, `unit`, `units`,
and `priceMinor`. Currency is a three-letter uppercase code, rate identity is
required, units are positive integers and monetary values are bounded integer
minor units. Missing pricing remains null, never free.
`estimate_cost(model, units)` preserves unavailable prices and checks integer
overflow. Estimates do not prove a billing charge or authorize dispatch.

An observation contains `hostId`, `hostBuild`, `inventoryDigest`, and
`modelId`. Mismatched host, snapshot or effective model is rejected. Results
distinguish the requested candidate from a matching supplied observation;
they do not authenticate observations or launch an optimized route. Model
selection and pricing need actual attributable host evidence before runtime
activation. No Copilot SDK or provider-specific model client is required.

## Exposure, failure and reversal

Controls storage is a bounded, strict record under `.git/sdlc`, or a confined
fallback proven ignored for its exact path. It uses the shared atomic-write
and confinement helpers. Corrupt inputs, locks, stale approvals, exhausted
attempts, pending cancellation and failed promotions produce explicit errors.
It retains cancellation bindings and does not silently reset or prune data.

Existing workflows remain unchanged when controls are absent or cleanly
disabled without prior activation. Pause/cancellation barriers and activated
native stop protection deliberately survive disabling.
Rollback of an opted-in project requires inspecting unresolved work and
explicitly resolving manual intent/resuming first; never remove a barrier
to pretend a native worker stopped. No production data migration is needed.

Automated evidence must cover absent/disabled behavior, dry run, approvals,
cross-revision retry/escalation, pause/cancel bypasses, corrupt/failed writes,
model identity/pricing and real CLI operation. Telemetry, live routing,
autonomous policies and host cancellation remain separate unfinished gates.
