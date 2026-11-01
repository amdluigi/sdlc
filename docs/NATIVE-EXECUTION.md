# Supervised native execution

This opt-in interactive flow uses the active agent host's native delegation.
It requires no SDK, separate model client or mandatory Copilot dependency.
The existing local manager remains the authority for plan approval, serial
claims, worker receipts and independent acceptance. Default skills and policy
behavior do not change.

## Locked M2 flow

The controller coordinates five host-neutral roles: controller, architecture,
developer, testing and review. VS Code profile packaging is supported first;
other host formats and Claude-host behavior require separate qualification.
Selecting a Claude model in another host does not establish Claude-host parity.
Profiles do not pin a model. Read/search-only roles cannot edit or execute;
execution-capable roles are not advertised as filesystem read-only.

`execution_profiles.install_profiles(root, mode="copy", dry_run=True)` stages
and promotes one owned `.github/agents` directory. It refuses a pre-existing
unowned directory, never merges or overwrites another agent's files, and has
no global mode. Copy and exact source-bound directory links are supported.
On Windows, directory junctions provide the existing installer-style link
fallback. A private adjacent ownership record distinguishes complete and
interrupted installation. Pending installation requires inspection, not
automatic recovery. Installing profiles does not enable execution policy.

`native_execution.prepare_request(root, execution_id, brief, role, host)`
returns a strict request without writes. `host` is the controller's observation
of the available native tool, not authentication or self-certification:
`id`, `build`, `delegationTool`, `allowedActions`. Unsupported or absent actions
fail closed. An explicit model or non-default model profile is blocked until
effective routing is supported; host-default identity is unverified.

The version-1 request contains `projectRoot`, `binding`, `policyDigest`, `role`,
`profileDigest`, `host`, `brief`, and the one planned task's `outcome`.
`native_execution.start_request(root, request, approved_request_digest)`
rechecks enabled consent, approved immutable plan, installed profile identity,
task dependencies and project-wide ownership/serialization under the existing
writer lock. It atomically records ready/start and a progress marker binding
the complete canonical request digest. Separate explicit digest approval is
required; manual policy enablement alone does not approve native delegation.

Only after start succeeds does the controller invoke the observed native tool
once with the exact root and request. Python does not impersonate a host or
launch a worker. There is no caller-imported adapter or forged CLI load result.
The controller must confirm profile/tool availability in the actual host.
Scope text and tool lists are not an OS sandbox. No automatic retry, parallel
dispatch, billing optimization, hard timeout or cancellation claim is made.

`native_execution.receive_receipt(root, request, receipt, result_id)` accepts a
strict host envelope: `schemaVersion`, `requestDigest`, `hostId`, `hostBuild`,
`callId`, `result`. It checks the recorded request marker, exact binding and
running attempt, rejects worker approval fields and conflicting/duplicate call
identities, and records host attribution plus the existing version-1 task
result atomically. The host call ID is a cooperative controller observation,
not authentication. Receipts remain reported, not accepted.
The controller independently validates evidence through the unchanged
`accept_task` operation. Transport failure or ambiguous work is blocked for
inspection; never retry or declare a worker stopped without host evidence.

## Compatibility and evidence

Request and receipt contracts are new strict boundaries. Existing execution
schemas, records, events and manual APIs retain their meaning. Digest and
attribution markers use existing progress messages; they do not add event types
or reinterpret ordinary manual progress. Existing manual attempts are not
native requests. Recovery of a lost request requires the original request
artifact; the digest marker alone cannot reconstruct or redispatch it.
Request markers must contain a valid digest and immediately follow the matching
task-start event; later request-like progress is not a dispatch record.
Attribution is recognized only when a unique preceding native request and an
immediately following result event bind the same task/attempt and stored
receipt. Canonical attribution bytes and the complete receipt digest are
checked. Ordinary progress containing similar text remains ordinary progress.

Reuse the shared strict JSON/binding validators and manager transaction,
ownership, consent, filesystem and atomic-write helpers. Repository-only
qualification installation code is not available in an installed portable
bundle; the profile installer reuses portable management primitives instead.
No runtime dependency or global execution store is introduced.

Automated checks cover policy refusal/drift, digest edits, prerequisite and
cross-execution conflicts, profile collisions/drift, copy/link identity,
interrupted installation, malformed/spoofed receipts, atomic failures,
attribution, reported-versus-accepted results and unchanged manual behavior.
Actual host discovery, tool restriction and harmless worker/result trials are
separate evidence. M2 is not accepted merely because fixtures pass.

## Explicit local workflow

Run the installed portable helper from the consumer project. The example
below uses PowerShell 7 and an already reviewed version-1 plan, brief and
execution policy. Substitute the installed script paths and your exact
execution ID. Profile installation is a separate opt-in operation.

```powershell
$native = '.github\skills\sdlc\scripts\manage_native.py'
$manager = '.github\skills\sdlc\scripts\manage_execution.py'
python -B $native install-profiles --project-root .
python -B $native install-profiles --project-root . --run
python -B $manager configure --project-root . --input policy.json
python -B $manager import --project-root . --input plan.json
$plan = python -B $manager inspect --project-root . --execution-id feature-one | ConvertFrom-Json
python -B $manager approve --project-root . --execution-id feature-one --plan-digest $plan.planDigest --policy-digest $plan.policyDigest
python -B $native prepare --project-root . --execution-id feature-one --role developer --brief brief.json --host host.json |
    Set-Content -Encoding utf8NoBOM request.json
$digest = python -B $native digest --project-root . --input request.json | ConvertFrom-Json
```

`host.json` must describe the controller's actual observed host capabilities,
not an invented host or a copied qualification fixture. Review the entire
request and approve its exact digest before running:

```powershell
python -B $native start --project-root . --request request.json --approved-request-digest $digest.requestDigest
```

At this point the active controller, not this CLI, invokes one native worker
using the installed role and exact request. If the host cannot discover that
role or enforce its tool restriction, stop before invocation. Save the
returned version-1 result inside an envelope containing the observed host
call ID and request digest, then record it:

```powershell
python -B $native receive --project-root . --request request.json --receipt receipt.json --result-id result-one
python -B $manager report --project-root . --execution-id feature-one
python -B $manager accept --project-root . --execution-id feature-one --input acceptance.json
```

Check each exit code before proceeding. `digest` is read-only bookkeeping,
not approval. A JSON receipt created for local testing is not a real worker
receipt or live-host qualification. Keep request and receipt artifacts private
and outside committed product files. Link mode tracks the bundled source;
source updates require renewed inspection and approval. There is no automatic
upgrade, repair, uninstall or migration of existing agent directories.
