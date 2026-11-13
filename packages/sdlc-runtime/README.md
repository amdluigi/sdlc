# Optional SDK-free bounded worker

This experimental VS Code extension owns a small native Language Model API
loop. It is not the read-only dashboard, the old native bookkeeping helper,
or a full-roadmap completion claim. Nothing installs, activates or calls a
model automatically. No dependencies, SDK, network client or global settings
are added. Start with the independently usable
[manual tryout](../../docs/EXECUTION-TRYOUT.md).

**SDLC: Run Two Isolated Batches** explicitly groups exactly two independent
local project batches, each with its own current exact consent and serial
controller. It never runs concurrent workers in the same project. See
[isolation, cancellation and acceptance](../../docs/PARALLEL-BATCHES.md)
before using it. Existing single-worker and single-batch commands are
unchanged.

## Run from the public source checkout

Requirements: VS Code 1.95 or newer with a native chat model available,
Node 20 or newer for offline tests, and an installed Python 3 executable
named `python` on the extension host's PATH. Keep this package in the public
checkout: its bridge is fixed to
`skills/sdlc/scripts/manage_runtime.py` in that same checkout. Copying just
this folder or shipping it as a standalone VSIX is not supported.

Open a **separate local target project**, not the trusted extension/helper
source, in an Extension Development Host. Use the executable that matches the
IDE channel and build you are currently running; do not substitute a different
stable/preview installation:

```powershell
$CurrentIde = "C:\absolute\path\to\the\currently-running-IDE\Code.exe"
& $CurrentIde --new-window --extensionDevelopmentPath "$SdlcCheckout\packages\sdlc-runtime" "$TargetProject"
```

In the target project, explicitly install native profiles, enable execution,
import and approve a plan using the existing manager/native CLI. These steps
are separate from starting this extension. The selected source plan must
exist and its SHA-256 must match the imported plan's `sourcePlan.digest`.
Create a current bound task brief with exact owned files and guidance.
The original version-1 runtime supports only `read`, `search` and `edit`.
An execute brief requires the separately confirmed version-2 flow below;
never silently downgrade an approved brief.
Explicit task model/modelProfile assignments remain unsupported by the old
native request path. Use `model: null` and `modelProfile: "host-default"`;
the picker is a separate per-run user choice, not effective-routing proof.

Run **SDLC: Run Bounded Worker** explicitly. Select the local project,
brief, matching role, and one model from `vscode.lm.selectChatModels`.
The modal confirmation shows the exact native request digest and a separate
runtime digest binding selected model metadata, bounds and control state.
Authorize only after checking the project, files and provider/model.
VS Code/provider consent can additionally be required by the host.
Choosing a model alone does not dispatch. Dismissing any prompt starts
nothing. This development task did not authorize or perform inference.

The default per-run allowance is 8 iterations, 16 tool calls, 128 KiB
cumulative input, 128 KiB cumulative output and a 120-second local lease.
Portable hard ceilings are 16 iterations, 32 tool calls, 256 KiB input and
output, and 300 seconds. Files are bounded to 64 KiB. Input accounting
includes every full submitted protocol/context/history prompt and every
tool argument; output includes streamed model text and tool results.
These byte limits are **not token, billing or monetary caps**.

## Explicit finite batches

The additive **SDLC: Run Approved Bounded Batch** command accepts one bounded
local JSON batch definition. It strictly rejects duplicate JSON keys, previews
the current plan and controls without dispatch, and requires every exact model
ID in the batch to be uniquely available in the active IDE. The consent dialog
binds the normalized batch digest and displays task/attempt IDs, brief digests,
model IDs, per-attempt bounds, and cumulative bounds. The user must inspect the
selected JSON file and current manager approvals before authorizing it.

Tasks run serially and only after every prerequisite has an independent manager
acceptance. The finite ordered attempt lists are the complete retry allowances;
any model escalation is preselected and requires the controls policy to allow
it. A retry is eligible only after a complete failed manager receipt and
accounting record. Unknown, cancelled, timed-out, thrown, malformed, stale,
environmental, or otherwise unexplained outcomes stop the batch. Restart
requires the same batch input and fresh explicit consent; it never resumes or
redispatches active or unknown work.

No full batch brief, guidance/verification prose, prompt, streamed response,
or transcript is persisted. Controls retain exact batch/brief digests,
task/attempt identities, model choices and limits. Manager receipts add only
the result-validation scope tags (allowed actions, owned paths and criterion
IDs). Provider billing, actual spend, and remote termination remain
unobservable; the batch supports no monetary cap. A non-null `maxSpendMinor`
is refused before dispatch.

## Deterministic prompts and local accounting

The bounded request supplies the selected role identity, profile-digest-bound
instructions, shared-context revision/digest, and applicable
specialist-context digest/content. The worker cannot select or reconstruct a
different role or context. Missing, stale, invalid or mismatched bindings are
rejected rather than replaced with generic instructions.

The manager freezes operator context mutation from attempt start through
confirmed completion, including the gap between step validation and adapter
invocation. A local stop does not release unconfirmed native work. After a
validated receipt, context can change without accepting the task, and the next
attempt must bind the latest revision and digest.

The driver builds a fixed-order prompt from named components: execution
protocol, task brief, selected role, shared context, specialist context,
requirements, security constraints, permitted tools, and necessary history.
The runtime has no safe structured signal to declare a distinct prior tool
result irrelevant, so it conservatively retains distinct results and evidence
from the bounded run. Validated edits are referenced by path and digest instead
of repeating source contents. Consecutive read/search observations that are
identical under deterministic serialization are represented once with their
occurrence count; changed or nonconsecutive observations remain distinct.
Required content is never silently truncated or semantically compressed.
Prompts over the supported limit fail visibly before a model request.

This conservative retention policy does not prove that every distinct result
remains necessary. The approved foundation PRD's stronger FR-2 / AC-2
relevance claim remains partially satisfied. The
[implementation plan](../../docs/plans/token-efficiency-foundation.md#history-acceptance-decision)
records a proposed amendment requiring explicit maintainer approval; the
implementation does not silently waive that criterion.

The ignored local runtime record stores aggregate measurements, not prompt
text, transcripts, source code or command output. Prompt-component and total
input bytes are UTF-8 bytes of the exact model-facing prompt, counted on every
call and accumulated across the bounded execution. Existing input bytes also
include tool arguments and remain the execution-limit counter. Output bytes
include model response text and tool-result content. Model calls, dispatched
tool operations, manager-approved retries, elapsed attempt time, and
model/provider/host identifiers are recorded as available. Batch accounting
events preserve these aggregates per attempt. Summing events for the exact
approved batch ID and digest derives cumulative batch totals, including prompt
components, total input bytes, retries, and elapsed attempt durations; no
separate aggregate event is persisted. Batch limits are checked cumulatively
across all attempts. New local accounting stores use schema version 5 for all
bounded runs, with request lifecycle aggregates and terminal timing. Existing
version-1 through version-4 stores remain readable without migration.
Supported legacy operations update counters and status in the existing store
version; reading does not migrate it. A newly admitted attempt writes version 5
only after the previous runtime is reported. Active or unknown stores block
restart.
Versions 1 and 2 cannot accept prompt-component accounting; versions 3 and 4
retain their original reservation-based counters rather than being silently
reinterpreted as lifecycle observations.

Request preparation (`step`) checks the full prompt budget and records a
bounded numeric reservation, not a confirmed call or transmitted-byte charge.
The driver invokes the adapter before confirming dispatch through the bridge.
Stream completion and interruption are separate settlements; cancellation
before invocation abandons the reservation without adding a model call.
Observed partial response text is counted as UTF-8 bytes of the concatenated
prefix, never persisted as text. Unknown outcomes remain unknown and block
redispatch. A process crash between adapter invocation and durable accounting
cannot establish remote transmission; unresolved preparation is explicitly
classified as unknown, not invented as confirmed dispatch.

`modelCalls` counts durably recorded adapter invocations, including a
synchronous throw; `requestAccounting.dispatched` counts normal adapter-return
confirmations, not remote delivery. Stream completion means only that the
stream ended. Even completed streams may contain invalid protocol and leave
the task unknown. Delivered overflow bytes are recorded on unknown/interrupted
outcomes rather than clamped; exceeding the output budget still stops work
before any further tool or receipt. See the
[complete lifecycle definitions](../../docs/EXECUTION-ORCHESTRATION.md#prompt-construction-and-accounting).

Single-run terminal timing is persisted on reported completion or local stop.
A local stop records elapsed attempt time without claiming remote termination.
Batch version-5 events distinguish receipt-backed accounting from
unknown-attempt aggregates and preserve exact batch and attempt bindings.
Unknown aggregates are not complete successful-execution totals. No raw
prompt, transcript or tool output is retained.

Transmitted bytes are not provider-processed or billable tokens. The current
host path does not expose authoritative input/output, cached or billable token
usage, or pricing, so those fields and authoritative cost remain `null`.
There is no byte-to-token estimate. Local accounting is separate from
persistent telemetry, which remains governed by existing consent and privacy
controls.

## Supported tools and authority

- Read and literal line search: only exact brief ownership/guidance paths.
- Edit: full UTF-8 LF replacement of one exact owned file, using the digest
  from a previous read as compare-and-swap protection. New files require an
  existing parent. Atomic same-directory staging preserves existing file
  mode and is cleaned on normal failure; interrupted staging requires
  inspection. No automatic retry or rollback is attempted.
- Execute: only a separately selected version-2 envelope. The worker supplies
  exactly `{"commandId":"approved-id"}`, never an executable, argv or shell.
  Each configured ID is single-use per run; there are no automatic retries.

Every model iteration, observation, tool and receipt crosses the real fixed
Python CLI. It rechecks current manager approval, consent generation,
profile/source/guidance digests, exact native attempt, root, control bindings,
and wall-time lease. Edits and manager writes use the same serial writer.
Reparse/symlink paths, hardlinked files, aliases, source/guidance ownership,
manager controls and trusted implementation paths are refused.
This is a cooperative same-user boundary, **not an OS sandbox**.

Enabled version-1 manual controls remain incompatible with native dispatch.
The runtime refuses them without changing them. Do not disable safeguards
just to run it. Explicitly selected version-2 supervised controls integrate
the same manager's approval, attempt, pause/cancel and unknown-work barriers.
The selected model ID must be permitted. See
[controls compatibility and retention](../../docs/EXECUTION-CONTROLS.md).
Automatic policy adoption, open-ended autonomous scheduling, and remote-stop
recovery are not implemented or advertised. The separately consented finite
batch command is not an autonomous policy.

The model uses a strict one-object text JSON protocol rather than access to
VS Code's general agent tools. Only the extension maps permitted messages
to the confined tools. Completion returns a structured task receipt through
`native_execution.receive_receipt`; it never accepts the result, runs
verification without the separately authorized execute tool, approves a plan
or advances an SDLC gate. Version-1 command verification remains
`unavailable`, `not-run` or `skipped`.

## Separately authorized exact local commands

Execute is supported only on the qualified local Windows path. POSIX execute
fails with `E_RUNTIME_UNSUPPORTED` before preparation/dispatch can start a
command. Process groups alone cannot guarantee descendant cleanup if their
supervisor receives SIGTERM, is killed by a bridge watchdog, or disappears.
There is deliberately no success-shaped POSIX fallback. Non-execute tools
and supervised manager controls remain portable.

An execute brief opens a separate local JSON definitions file picker and a
separate modal confirmation before the usual runtime/model confirmation.
Definitions are an array of objects matching
`skills/sdlc/contracts/runtime-command.schema.json`, for example:

```json
[{"id":"unit-check","executable":"C:\\Python314\\python.exe","argv":["-I","-S","-m","unittest"],"cwd":"C:\\work\\approved-project","timeoutMs":5000,"maxOutputBytes":4096}]
```

Use the actual absolute resolved executable and exact selected project root.
The envelope adds the executable's SHA-256; changed executable bytes, root,
source, profile, approval, consent, control state or runtime budgets block
dispatch and receipt. There is no shell, arbitrary command string, worker
argument selection, dependency/network installation or global configuration
tool. Approved local executables still run with the user's permissions:
this is not an OS sandbox, filesystem sandbox or network isolation. Review
the complete trusted definition before authorizing it.

Hard ceilings are 16 command definitions, 64 arguments each, 10 seconds per
command and 64 KiB output per command, additionally constrained by the
runtime's cumulative budgets and lease. Enough output budget is reserved
before dispatch. Command output is bounded text returned only in memory.
Only structured command ID/digest, containment, exit/status and byte-count
metadata are retained. Version-2 receipts reject nonempty `findings` and
`blockers` and arbitrary verification text, rather than relying on a model
instruction not to copy raw output. For `unavailable`, `not-run` or `skipped`
verification use null command/revision and summary exactly matching that
status. This restriction is additive to version 2; old receipts are unchanged.

Windows uses native `CreateProcessW` **suspended**, a kill-on-close Job
Object, restricted inherited pipe handles, assignment **before** resume,
and observes zero active job processes after termination. Assignment failure
never resumes the process. Missing guarantees fail before user code starts.
Descendant heartbeat tests exercise real Windows subprocesses.
These are containment guarantees for cooperative local commands, not a
security sandbox against deliberately escaping processes.

Evidence distinguishes exit-zero (`passed`), `nonzero`, `timeout`,
`output-limit`, spawn failure and unresolved work. Timeout/output flooding
terminates the contained tree, marks the runtime unknown and blocks further
progress or success receipt; provider work remains unconfirmed. Pause,
cancellation or stale bindings also kill the local tree without asserting
remote stop. Interrupted commands are never replayed.

A version-2 verification claim must reference unique observed evidence:
`command: "runtime-command:<id>"`, `revision: <commandDigest>`,
`summary: "passed"` with `result: "passed"` or `summary: "nonzero"` with
`result: "failed"`. A zero exit is only process evidence, not independent
acceptance of an acceptance criterion. Fabricated, ambiguous and mismatched
claims are refused at the receipt transaction.

## Failure, cancellation and retention

Invalid protocol, errors, changed bindings, exhausted budgets, timeout or
local cancellation stop the loop without another provider attempt or a
success receipt. A failure after dispatch leaves native manager work
unresolved; restart never redispatches that attempt. The persistent runtime
marker is active, unknown or reported, not evidence that a remote model
stopped. The local lease prevents later privileged operations after expiry;
cleanup and a timed-out CLI can take additional time. A host/process failure
can leave a writer lock or partial staging that requires inspection.

Cancellation requests the VS Code cancellation token and stops local
progress. It is **not remote acknowledgement**. Do not resolve unknown work
by assuming that cancellation rolled back an already-started atomic tool
operation or receipt transaction. Do not resolve unknown work
by deleting files, stealing locks or falsely declaring completion. Inspect
using the existing manager and controls reconciliation; authoritative remote
stop recovery is not supplied by this slice.

An in-flight tool wait races UI cancellation and the runtime deadline.
Cancellation promptly persists the real manager stop marker; only explicit
`E_EXECUTION_BUSY` stop-lock contention is retried, at most eight times and
only while a two-second monotonic retry window remains. Each real helper's
startup and validation time counts toward that window; an already-started
helper is still awaited, not killed to meet the retry deadline.
This is a retry-admission bound, not a two-second total-stop guarantee.
A stop helper admitted before the deadline retains the fixed bridge's
15-second process timeout; the driver also awaits any in-flight execute
helper's Job Object cleanup. Thus stop reporting can take the retry window
plus that helper timeout and execute cleanup (and local scheduling delays).
Success after the retry window is valid observed persistence, not a timeout;
a helper timeout or exhausted busy retries remains explicit
`E_RUNTIME_STOP_UNCONFIRMED`. The stop helper is separate from the execute
helper that owns descendant cleanup; cancellation never kills that owner.
The execute watchdog holds the shared writer lock only for its stop-marker
check; its full read-only qualification runs outside that critical section,
so polling cannot monopolize the lock needed to persist cancellation.
On Windows, JSON readers share deletion and existing manager records use
`FileRenameInfoEx` replacement with POSIX rename semantics, preserving
reader snapshots without blocking atomic updates or merging old file metadata.
Confinement still resolves each full leaf after checking components. Only
writer-lock checks tolerate an NTFS deleted-file identity, after rechecking
the lock is absent or regular and its parent remains confined. No write
retries are added; unsupported rename capability, incompatible external readers
and other persistence failures still fail closed.
The execute helper is kept alive and awaited so its Job Object can finish
local descendant cleanup. A failed stop persistence is explicitly reported
as `E_RUNTIME_STOP_UNCONFIRMED`, never silently treated as a successful stop.
Neither path redispatches work or creates a fallback receipt.

No automatic telemetry, transcript, prompt, response stream, tool-content
log or export is written. Context/history lives only in memory. Ignored
manager-local storage retains counters, binding digests, local call ID and
status and lease-enforcement clock boundaries; the existing manager retains
its structured task receipt metadata.
Workers must not embed transcripts or file contents in receipt text fields.
Selected brief and requested allowed file content are sent to the selected
model only after explicit consent. Provider retention and billing are
external policies, not controlled by this package.

## Offline validation and CLI

```powershell
python -B -m unittest tests.test_bounded_runtime tests.test_runtime_commands tests.test_native_execution tests.test_execution_controls -q
npm --prefix packages\sdlc-runtime run check
npm --prefix packages\sdlc-runtime test
```

Driver integration tests normally replace only the external model response seam.
Their filesystem, CLI subprocess, profile installation, manager approval,
native request, tools and receipt boundaries are real. Two deadline cases
also control the Node monotonic-clock or watchdog seam after the provider
boundary is reached; slow real CLI startup must not invalidate their intended
timeout assertion before a provider is called. Extension-logic and
offline-harness guard unit tests also use explicitly substituted VS Code APIs;
they are not actual native UI evidence. No external model is invoked.

The bridge is also directly runnable:

```powershell
$Payload | python -B -I -S skills\sdlc\scripts\manage_runtime.py prepare --project-root "$TargetProject"
```

JSON stdin is strict and bounded. `prepare` accepts exactly `executionId`,
`brief`, `role`, `model` (`id`, `vendor`, `family`, `version`) and `limits`.
It returns a read-only runtime envelope. `start` requires that envelope plus
independently confirmed `approvedRuntimeDigest` and `approvedRequestDigest`.
`check`, `step` (plus `prompt`), `observe` (plus `response`),
`tool` (plus `name`, `arguments`), `receive` (plus `result`) and `stop`
all require the exact envelope. The extension, not worker text, owns these
operations. There is no arbitrary import path, command runner or approval
operation. Diagnostics contain neutral classes rather than model content.
The fixed interpreter explicitly uses `-B -I -S`, so isolated imports do not
rely on `PYTHONDONTWRITEBYTECODE` and do not write helper bytecode caches.

The additive `prepare_execute` operation requires those same fields plus
`commands`, returning a version-2 envelope. The old `prepare` operation still
rejects execute; old readers fail closed on version 2. Existing native request
schema version 1 and its explicit-model restrictions are unchanged.

See [qualification and external gates](QUALIFICATION.md) before considering
live use. Actual native version-2 selection, both consent-decline paths and
a reported/unaccepted execute flow were observed with an explicitly offline
synthetic model on a pre-review source snapshot. This is native UI/transport
evidence, not real inference, provider identity, billing or remote-stop proof.
The corrected driver also passed a real progress-Cancel trial: the trusted
ten-second command's heartbeat stopped after an observed lifetime of about
1.04 seconds, with no receipt or acceptance. This is local command-tree
evidence, not a remote-stop acknowledgement. The
[offline native reproduction](QUALIFICATION.md#reproduce-the-offline-native-dialogs-and-command-trial)
uses a fresh marked synthetic workspace and isolated editor profile.
